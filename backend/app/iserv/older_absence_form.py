import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from .dsa import name_words
from .older_absences import LIST_PATH, fold
from .pages import action_link

ROLE_PROFILE = "profile"
ROLE_FROM = "from"
ROLE_TILL = "till"
ROLE_FROM_TIME = "from_time"
ROLE_TILL_TIME = "till_time"
ROLE_WHOLE_DAY = "whole_day"
ROLE_REASON = "reason"
ROLE_KIND = "kind"
ROLE_PERIOD = "period"
CREATE_SEGMENTS = frozenset("add new create".split())
CREATE_WORDS = frozenset("neu neue neuen hinzufuegen melden krankmeldung add new report create".split())
BLOCKED_SEGMENTS = frozenset("delete remove edit update export print".split())
SIGN_IN_PREFIX = "/iserv/auth/"
PROFILE_WORDS = frozenset("schueler schuelerin student pupil child person user benutzer".split())
FROM_WORDS = frozenset("von from start beginn begin ab since".split())
TILL_WORDS = frozenset("bis to till until end ende".split())
TIME_WORDS = frozenset("zeit time uhrzeit uhr".split())
DATE_WORDS = frozenset("datum date tag day".split())
PERIOD_WORDS = frozenset("zeitraum period range daterange dates".split())
WHOLE_DAY_WORDS = frozenset("ganztaegig ganztags ganztag allday wholeday fullday".split())
WHOLE_WORDS = frozenset("all whole full ganzer ganzen ganze".split())
REASON_WORDS = frozenset(
    "grund reason bemerkung kommentar comment notiz note anmerkung beschreibung description text nachricht message "
    "begruendung hinweis".split()
)
KIND_WORDS = REASON_WORDS | frozenset("art typ type kategorie category abwesenheitsart".split())
CANCEL_WORDS = frozenset("abbrechen cancel zurueck back nein no".split())
ERROR_SELECTORS = (".form-error-message", ".invalid-feedback", ".has-error .help-block", "li.error", ".error-message", ".text-danger")
GENERAL_ERROR_SELECTORS = (".alert-danger", ".alert-error", ".form-errors")
HOLDER_DEPTH = 4
SKIPPED_KINDS = frozenset({"submit", "button", "image", "reset"})
EXPOSED_KINDS = {
    "select": "select", "radio": "select", "checkbox": "checkbox", "date": "date", "time": "time",
    "text": "text", "textarea": "textarea", "number": "text", "email": "text", "tel": "text",
}
TEXT_DATE_KINDS = ("text", "date", "datetime-local")
FORMAT_ISO = "iso"
FORMAT_GERMAN = "german"
TEXT_LIMIT = 2000
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
ISO_HINT = re.compile(r"\d{4}-\d{2}-\d{2}|yyyy-mm-dd|jjjj-mm-tt", re.IGNORECASE)
TIME_HINT = re.compile(r"\d{1,2}:\d{2}|hh:mm|hh:ii", re.IGNORECASE)
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
WORD = re.compile(r"[^\W\d_]+")

ERROR_PROFILE = "profile"
ERROR_DATE = "date"
ERROR_RANGE = "range"
ERROR_TIME = "time"
ERROR_REQUIRED = "required"
ERROR_CHOICE = "choice"
ERROR_TEXT = "text"


class OlderFormError(ValueError):
    def __init__(self, reason, field_key=""):
        super().__init__(reason)
        self.reason = reason
        self.field_key = field_key


@dataclass
class FormField:
    name: str
    kind: str
    label: str = ""
    required: bool = False
    options: list = field(default_factory=list)
    value: str = ""
    checked: bool = False
    minimum: str = ""
    maximum: str = ""
    hint: str = ""
    multiple: bool = False
    role: str = ""


@dataclass
class OlderForm:
    action: str
    method: str
    controls: list
    submit: tuple = None
    roles: dict = field(default_factory=dict)
    profiles: dict = field(default_factory=dict)
    profile_options: int = 0
    extras: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)
    hidden_profile: object = None
    files: object = None


def words(*texts):
    found = set()
    for text in texts:
        found.update(WORD.findall(fold(CAMEL.sub(" ", str(text or "")))))
    return frozenset(found)


def _text(node):
    return " ".join(node.get_text(" ").split()) if node is not None else ""


def _segments(path):
    return [part.casefold() for part in path.split("/") if part]


def create_path(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    page = urlsplit(page_url or "")
    by_text = ""
    for anchor in soup.find_all("a", href=True):
        target = urlsplit(urljoin(page_url or "", str(anchor.get("href") or "").strip()))
        if target.netloc.lower() != page.netloc.lower() or not target.path.startswith(LIST_PATH):
            continue
        parts = _segments(target.path[len(LIST_PATH):])
        if not parts or set(parts) & BLOCKED_SEGMENTS or any(part.isdigit() for part in parts):
            continue
        if parts[-1] in CREATE_SEGMENTS:
            return target.path
        label = words(_text(anchor), anchor.get("title"), anchor.get("aria-label"))
        if not by_text and label & CREATE_WORDS and len(parts) == 1 and not target.query:
            by_text = target.path
    return by_text


def _write_form(soup):
    best = None
    best_count = -1
    for form in soup.find_all("form"):
        if str(form.get("method") or "get").strip().lower() == "get":
            continue
        if urlsplit(str(form.get("action") or "")).path.startswith(SIGN_IN_PREFIX):
            continue
        count = sum(1 for node in form.find_all(("input", "select", "textarea")) if _visible(node))
        if count > best_count:
            best, best_count = form, count
    return best


def _visible(node):
    if not node.get("name") or node.has_attr("disabled"):
        return False
    return node.name != "input" or str(node.get("type") or "text").lower() not in SKIPPED_KINDS | {"hidden"}


def _label_node(form, node):
    found = form.find("label", attrs={"for": node.get("id")}) if node.get("id") else None
    return found or node.find_parent("label")


def _group_label(form, node):
    holder = node
    for _ in range(HOLDER_DEPTH):
        holder = holder.parent
        if holder is None or holder is form:
            return None
        if holder.get("id"):
            found = form.find("label", attrs={"for": holder.get("id")})
            if found is not None:
                return found
        if holder.name == "fieldset" and holder.find("legend") is not None:
            return holder.find("legend")
    return None


def _required(node, label):
    if node.has_attr("required"):
        return True
    return label is not None and "required" in {str(name) for name in label.get("class") or []}


def _option_value(option):
    value = option.get("value")
    return str(value if value is not None else _text(option)).strip()


def _select_field(form, node):
    label = _label_node(form, node)
    options = [(_option_value(option), _text(option)) for option in node.find_all("option")]
    chosen = [_option_value(option) for option in node.find_all("option") if option.has_attr("selected")]
    multiple = node.has_attr("multiple")
    default = chosen if multiple else (chosen[0] if chosen else (options[0][0] if options else ""))
    return FormField(
        name=str(node.get("name")), kind="select", label=_text(label), required=_required(node, label),
        options=[option for option in options if option[0]], value=default, multiple=multiple,
    )


def _input_field(form, node, kind):
    label = _label_node(form, node)
    return FormField(
        name=str(node.get("name")), kind=kind, label=_text(label), required=_required(node, label),
        value=str(node.get("value") or ("on" if kind == "checkbox" else "")), checked=node.has_attr("checked"),
        minimum=str(node.get("min") or ""), maximum=str(node.get("max") or ""),
        hint=" ".join(str(node.get(name) or "") for name in ("placeholder", "data-format", "data-date-format")),
    )


def _radio_group(form, nodes):
    first = nodes[0]
    label = _group_label(form, first)
    options = [(str(node.get("value") or "on"), _text(_label_node(form, node))) for node in nodes]
    checked = next((str(node.get("value") or "on") for node in nodes if node.has_attr("checked")), "")
    required = any(_required(node, label) for node in nodes)
    return FormField(name=str(first.get("name")), kind="radio", label=_text(label), required=required, options=options, value=checked)


def _controls(form):
    controls = []
    radios = {}
    for node in form.find_all(("input", "select", "textarea")):
        name = str(node.get("name") or "").strip()
        if not name or node.has_attr("disabled"):
            continue
        if node.name == "select":
            controls.append(_select_field(form, node))
            continue
        if node.name == "textarea":
            label = _label_node(form, node)
            controls.append(FormField(name=name, kind="textarea", label=_text(label), required=_required(node, label), value=node.get_text()))
            continue
        kind = str(node.get("type") or "text").strip().lower()
        if kind in SKIPPED_KINDS:
            continue
        if kind == "radio":
            if name not in radios:
                radios[name] = []
                controls.append(name)
            radios[name].append(node)
            continue
        controls.append(_input_field(form, node, kind))
    return [_radio_group(form, radios[item]) if isinstance(item, str) else item for item in controls]


def _submit(form):
    for node in form.find_all(("button", "input")):
        kind = str(node.get("type") or ("submit" if node.name == "button" else "text")).lower()
        if kind not in ("submit", "image"):
            continue
        caption = _text(node) if node.name == "button" else str(node.get("value") or "")
        if words(caption, node.get("name")) & CANCEL_WORDS:
            continue
        name = str(node.get("name") or "").strip()
        return (name, str(node.get("value") or "")) if name else None
    return None


def matched_profiles(options, children):
    known = [(str(child.get("child_id") or ""), name_words(child.get("name"))) for child in children or []]
    offered = {}
    for value, label in options:
        label_words = name_words(label)
        matches = [child_id for child_id, child_words in known if child_id and label_words and child_words == label_words]
        if len(matches) == 1 and matches[0] not in offered:
            offered[matches[0]] = value
    return offered


def _field_words(control):
    return words(control.name.replace("[", " ").replace("]", " "), control.label)


def _whole_day(found):
    return bool(found & WHOLE_DAY_WORDS) or bool(found & WHOLE_WORDS and found & DATE_WORDS)


def _date_role(control, found):
    timed = control.kind == "time" or (found & TIME_WORDS and not found & DATE_WORDS and control.kind == "text")
    if control.kind == "text" and found & PERIOD_WORDS and not found & (FROM_WORDS | TILL_WORDS):
        return ROLE_PERIOD
    if found & FROM_WORDS:
        return ROLE_FROM_TIME if timed else ROLE_FROM
    if found & TILL_WORDS:
        return ROLE_TILL_TIME if timed else ROLE_TILL
    return ""


def _role_of(control, found, children):
    if control.kind in ("select", "radio") and not control.multiple:
        if matched_profiles(control.options, children) or found & PROFILE_WORDS:
            return ROLE_PROFILE
        if found & KIND_WORDS:
            return ROLE_KIND
        return ""
    if control.kind == "checkbox":
        return ROLE_WHOLE_DAY if _whole_day(found) else ""
    if control.kind == "textarea":
        return ROLE_REASON
    if control.kind in TEXT_DATE_KINDS or control.kind == "time":
        role = _date_role(control, found)
        if role:
            return role
    if control.kind == "text" and found & REASON_WORDS:
        return ROLE_REASON
    return ""


def _unique_names(controls):
    seen = {}
    for control in controls:
        seen[control.name] = seen.get(control.name, 0) + 1
    return {name for name, count in seen.items() if count == 1}


def known_ids(child):
    return {str(child.get(name)) for name in ("child_id", "student_id", "id") if child.get(name) not in (None, "")}


def _hidden_profile(form, children):
    for control in form.controls:
        if control.kind == "hidden" and _field_words(control) & PROFILE_WORDS:
            matches = [str(child.get("child_id")) for child in children or [] if control.value and control.value in known_ids(child)]
            form.hidden_profile = matches[0] if len(matches) == 1 else ""
            if not form.hidden_profile:
                form.unsupported.append(control)
            return


def _file_field(form):
    files = [control for control in form.controls if control.kind == "file"]
    if len(files) == 1:
        form.files = files[0]
        return
    form.unsupported.extend(control for control in files if control.required)


def _assign_roles(form, children):
    unique = _unique_names(form.controls)
    for control in form.controls:
        if control.kind == "hidden" or control.name not in unique:
            continue
        role = _role_of(control, _field_words(control), children)
        if role and role not in form.roles:
            control.role = role
            form.roles[role] = control
    if ROLE_FROM not in form.roles:
        for control in form.controls:
            if not control.role and control.kind in ("date", "datetime-local") and control.name in unique:
                control.role = ROLE_FROM
                form.roles[ROLE_FROM] = control
                break
    for control in form.controls:
        if control.role or control.kind in ("hidden", "file") or not control.required:
            continue
        if control.name in unique and control.kind in EXPOSED_KINDS and not control.multiple:
            form.extras.append(control)
        else:
            form.unsupported.append(control)


def parse_create_form(html, page_url, children):
    soup = BeautifulSoup(html or "", "html.parser")
    node = _write_form(soup)
    if node is None:
        return None
    form = OlderForm(
        action=urljoin(page_url or "", str(node.get("action") or "").strip() or (page_url or "")),
        method=str(node.get("method") or "post").strip().lower(),
        controls=_controls(node),
        submit=_submit(node),
    )
    _assign_roles(form, children)
    if ROLE_PROFILE not in form.roles:
        _hidden_profile(form, children)
    _file_field(form)
    profile = form.roles.get(ROLE_PROFILE)
    if profile is not None:
        form.profile_options = len(profile.options)
        form.profiles = matched_profiles(profile.options, children)
    return form


def parse_confirm_form(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    node = _write_form(soup)
    if node is None:
        return None
    return OlderForm(
        action=urljoin(page_url or "", str(node.get("action") or "").strip() or (page_url or "")),
        method=str(node.get("method") or "post").strip().lower(),
        controls=_controls(node),
        submit=_submit(node),
    )


def carries_time(control):
    if control is None:
        return False
    if control.kind == "datetime-local":
        return True
    return control.kind == "text" and bool(TIME_HINT.search(control.hint + " " + control.value))


def text_format(control):
    return FORMAT_ISO if ISO_HINT.search(control.hint + " " + control.value) else FORMAT_GERMAN


def _public(control):
    if control is None:
        return None
    return {
        "name": control.name,
        "type": EXPOSED_KINDS.get(control.kind, control.kind),
        "label": control.label,
        "required": control.required,
        "options": [{"value": value, "label": label} for value, label in control.options],
        "min": control.minimum,
        "max": control.maximum,
    }


def form_schema(form, children):
    names = {str(child.get("child_id") or ""): child.get("name") or "" for child in children or []}
    from_field = form.roles.get(ROLE_FROM) or form.roles.get(ROLE_PERIOD)
    return {
        "profiles": [{"id": child_id, "name": names.get(child_id, "")} for child_id in offered_profiles(form, children)],
        "profile_options": form.profile_options,
        "till": ROLE_TILL in form.roles or ROLE_PERIOD in form.roles,
        "times": ROLE_FROM_TIME in form.roles or carries_time(from_field),
        "whole_day": ROLE_WHOLE_DAY in form.roles,
        "min": from_field.minimum[:10] if from_field is not None else "",
        "reason": _public(form.roles.get(ROLE_REASON)),
        "kind": _public(form.roles.get(ROLE_KIND)),
        "extras": [_public(control) for control in form.extras],
        "files": {"required": form.files.required, "multiple": form.files.multiple} if form.files is not None else None,
    }


def offered_profiles(form, children):
    if ROLE_PROFILE in form.roles:
        return list(form.profiles)
    if form.hidden_profile is not None:
        return [form.hidden_profile] if form.hidden_profile else []
    known = [str(child.get("child_id")) for child in children or [] if child.get("child_id")]
    return known if len(known) == 1 else []


def _day(value):
    text = str(value or "").strip()
    if not ISO_DAY.match(text):
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _clock(value):
    text = str(value or "").strip()
    return text if CLOCK.match(text) else ""


def _date_text(control, day, clock):
    if control.kind == "date":
        return day
    if control.kind == "datetime-local":
        return "%sT%s" % (day, clock)
    if text_format(control) == FORMAT_ISO:
        shown = day
    else:
        shown = "%s.%s.%s" % (day[8:10], day[5:7], day[:4])
    return "%s %s" % (shown, clock) if clock and carries_time(control) else shown


def _plain_text(value, control, key):
    text = str(value or "").strip()
    if len(text) > TEXT_LIMIT:
        raise OlderFormError(ERROR_TEXT, key)
    if control.required and not text:
        raise OlderFormError(ERROR_REQUIRED, key)
    return text


def _choice(value, control, key):
    text = str(value or "").strip()
    if not text:
        if control.required:
            raise OlderFormError(ERROR_REQUIRED, key)
        return ""
    if text not in {option for option, _label in control.options}:
        raise OlderFormError(ERROR_CHOICE, key)
    return text


def _generic_value(control, value):
    kind = EXPOSED_KINDS.get(control.kind)
    if kind == "select":
        return _choice(value, control, control.name)
    if kind == "checkbox":
        if control.required and value is not True:
            raise OlderFormError(ERROR_REQUIRED, control.name)
        return value is True
    if kind == "date":
        day = _day(value)
        if not day and (control.required or str(value or "").strip()):
            raise OlderFormError(ERROR_DATE, control.name)
        return day
    if kind == "time":
        clock = _clock(value)
        if not clock and (control.required or str(value or "").strip()):
            raise OlderFormError(ERROR_TIME, control.name)
        return clock
    return _plain_text(value, control, control.name)


def _time_pair(form, payload, whole_day):
    from_time = _clock(payload.get("from_time"))
    till_time = _clock(payload.get("till_time"))
    start = form.roles.get(ROLE_FROM) or form.roles.get(ROLE_PERIOD)
    needs_time = not whole_day and (ROLE_FROM_TIME in form.roles or carries_time(start))
    if needs_time and not (from_time and till_time):
        raise OlderFormError(ERROR_TIME, ROLE_FROM_TIME)
    return (from_time, till_time) if needs_time else ("", "")


def form_values(form, payload, child_id, offered):
    if not child_id or child_id not in offered:
        raise OlderFormError(ERROR_PROFILE, ROLE_PROFILE)
    values = {}
    profile = form.roles.get(ROLE_PROFILE)
    if profile is not None:
        values[profile.name] = form.profiles[child_id]
    first = _day(payload.get("from_date"))
    if not first:
        raise OlderFormError(ERROR_DATE, ROLE_FROM)
    raw_till = str(payload.get("till_date") or "").strip()
    last = _day(raw_till) if raw_till else first
    if not last:
        raise OlderFormError(ERROR_DATE, ROLE_TILL)
    if last < first:
        raise OlderFormError(ERROR_RANGE, ROLE_TILL)
    if ROLE_TILL not in form.roles and ROLE_PERIOD not in form.roles:
        last = first
    whole_day = payload.get("whole_day") is True and ROLE_WHOLE_DAY in form.roles
    from_time, till_time = _time_pair(form, payload, whole_day)
    if first == last and from_time and till_time and till_time <= from_time:
        raise OlderFormError(ERROR_TIME, ROLE_TILL_TIME)
    if ROLE_FROM in form.roles:
        values[form.roles[ROLE_FROM].name] = _date_text(form.roles[ROLE_FROM], first, from_time or "00:00")
    if ROLE_PERIOD in form.roles:
        period = form.roles[ROLE_PERIOD]
        values[period.name] = "%s - %s" % (_date_text(period, first, from_time), _date_text(period, last, till_time))
    if ROLE_TILL in form.roles:
        values[form.roles[ROLE_TILL].name] = _date_text(form.roles[ROLE_TILL], last, till_time or "23:59")
    for role, clock in ((ROLE_FROM_TIME, from_time), (ROLE_TILL_TIME, till_time)):
        if role in form.roles:
            values[form.roles[role].name] = clock
    if ROLE_WHOLE_DAY in form.roles:
        values[form.roles[ROLE_WHOLE_DAY].name] = whole_day
    if ROLE_REASON in form.roles:
        values[form.roles[ROLE_REASON].name] = _plain_text(payload.get("reason"), form.roles[ROLE_REASON], ROLE_REASON)
    if ROLE_KIND in form.roles:
        values[form.roles[ROLE_KIND].name] = _choice(payload.get("kind"), form.roles[ROLE_KIND], ROLE_KIND)
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    for control in form.extras:
        values[control.name] = _generic_value(control, extra.get(control.name))
    return values, {"from_date": first, "till_date": last, "from_time": from_time, "till_time": till_time}


def form_pairs(form, values=None):
    values = values or {}
    pairs = []
    for control in form.controls:
        chosen = values.get(control.name, None)
        if control.kind == "checkbox":
            if chosen is True or (chosen is None and control.checked):
                pairs.append((control.name, control.value or "on"))
            continue
        if control.kind == "select" and control.multiple:
            pairs.extend((control.name, value) for value in control.value)
            continue
        value = control.value if chosen is None else chosen
        if control.kind == "radio" and not value:
            continue
        if control.kind == "file":
            continue
        pairs.append((control.name, value))
    if form.submit is not None:
        pairs.append(form.submit)
    return pairs


def _holder(node, name):
    holder = node
    for _ in range(HOLDER_DEPTH):
        parent = holder.parent
        if parent is None or parent.name in ("form", "body", "[document]"):
            break
        names = {str(other.get("name")) for other in parent.find_all(("input", "select", "textarea")) if other.get("name")}
        if names - {name}:
            break
        holder = parent
    return holder


def _error_texts(holder):
    texts = []
    for selector in ERROR_SELECTORS:
        for found in holder.select(selector):
            text = _text(found)
            if WORD.search(text) and text not in texts:
                texts.append(text)
    return texts


def answer_errors(html, form):
    soup = BeautifulSoup(html or "", "html.parser")
    known = {control.name: control for control in form.controls}
    fields = {}
    present = False
    for node in soup.find_all(("input", "select", "textarea")):
        name = str(node.get("name") or "")
        control = known.get(name)
        if control is None or control.kind == "hidden":
            continue
        present = True
        key = control.role or control.name
        if key in fields:
            continue
        texts = _error_texts(_holder(node, name))
        if texts:
            fields[key] = texts[0]
    general = []
    holders = [soup.select(selector) for selector in GENERAL_ERROR_SELECTORS]
    written = node_of(soup, known)
    texts = [_text(found) for group in holders for found in group] + (_error_texts(written) if written is not None else [])
    for text in texts:
        if WORD.search(text) and text not in general and text not in fields.values():
            general.append(text)
    return present, fields, general


def node_of(soup, known):
    for form in soup.find_all("form"):
        if any(str(node.get("name") or "") in known for node in form.find_all(("input", "select", "textarea"))):
            return form
    return None


def _share(part, whole):
    if part == 0:
        return "none"
    return "all" if part == whole else "some"


def structure_text(form, name_shape=str):
    hidden = [control for control in form.controls if control.kind == "hidden"]
    token = any("token" in words(control.name) for control in hidden)
    parts = ["%s, hidden %d, token %s, submit %s" % (form.method.upper(), len(hidden), "yes" if token else "no", "named" if form.submit else "unnamed")]
    for control in form.controls:
        if control.kind == "hidden":
            continue
        facts = [control.kind]
        if control.required:
            facts.append("required")
        if control.kind in ("select", "radio"):
            facts.append("options %d" % len(control.options))
        if control.role == ROLE_PROFILE:
            facts.append("matching profiles %s" % _share(len(form.profiles), len(control.options)))
        if any(control is other for other in form.unsupported):
            facts.append("not fillable")
        parts.append("%s %s (%s)" % (control.role or "other", name_shape(control.name), ", ".join(facts)))
    return "; ".join(parts)


ATTACHMENT_SEGMENTS = frozenset("attachment attachments anhang anhaenge file files download".split())
ATTACHMENT_ADD_WORDS = frozenset("anhang attachment datei file hochladen upload".split())
ADD_WORDS = frozenset("hinzufuegen add hochladen upload neu new".split())
REMOVE_SEGMENTS = frozenset("delete remove".split())


def _own_link(anchor, page_url):
    target = urlsplit(urljoin(page_url or "", str(anchor.get("href") or "").strip()))
    if target.netloc.lower() != urlsplit(page_url or "").netloc.lower() or not target.path.startswith("/iserv/"):
        return None
    return target


@dataclass
class Attachment:
    name: str
    path: str
    delete_link: str = ""
    delete_form: OlderForm = None


def _file_link(anchor, page_url):
    target = _own_link(anchor, page_url)
    if target is None or not target.path.startswith(LIST_PATH) or anchor.has_attr("data-method"):
        return None
    parts = set(_segments(target.path))
    if not parts & ATTACHMENT_SEGMENTS or action_link(target.path):
        return None
    return target


def delete_target(path):
    parts = set(_segments(path))
    return path.startswith(LIST_PATH) and bool(parts & REMOVE_SEGMENTS) and bool(parts & ATTACHMENT_SEGMENTS)


def _attachment_holder(anchor, page_url):
    holder = anchor
    for _ in range(HOLDER_DEPTH):
        parent = holder.parent
        if parent is None or parent.name in ("body", "[document]"):
            break
        files = [_file_link(other, page_url) for other in parent.find_all("a", href=True)]
        if len({(target.path, target.query) for target in files if target is not None}) > 1:
            break
        holder = parent
    return holder


def _attachment_delete(holder, page_url):
    for anchor in holder.find_all("a", href=True):
        target = _own_link(anchor, page_url)
        if target is not None and delete_target(target.path):
            return target.path + ("?" + target.query if target.query else ""), None
    for node in holder.find_all("form"):
        action = urlsplit(urljoin(page_url or "", str(node.get("action") or "").strip()))
        if str(node.get("method") or "get").strip().lower() == "post" and delete_target(action.path):
            return "", OlderForm(action=urljoin(page_url or "", action.path), method="post", controls=_controls(node), submit=_submit(node))
    return "", None


def attachment_entries(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for anchor in soup.find_all("a", href=True):
        target = _file_link(anchor, page_url)
        if target is None:
            continue
        path = target.path + ("?" + target.query if target.query else "")
        if path in [item.path for item in found]:
            continue
        link, form = _attachment_delete(_attachment_holder(anchor, page_url), page_url)
        found.append(Attachment(_text(anchor) or target.path.rsplit("/", 1)[-1], path, link, form))
    return found


def attachment_key(path):
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


def attachment_links(html, page_url):
    return [(item.name, item.path) for item in attachment_entries(html, page_url)]


LOG_WORDS = frozenset("aenderungsprotokoll protokoll verlauf history changelog aenderungen changes log".split())
LOG_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6", "legend", "caption", "strong", "summary")
LOG_LIMIT = 50


def change_log(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for heading in soup.find_all(LOG_HEADINGS):
        if not words(_text(heading)) & LOG_WORDS:
            continue
        holder = heading.find_next(("table", "ul", "ol", "dl"))
        if holder is None:
            return []
        if holder.name == "table":
            rows = [row for row in holder.find_all("tr") if row.find("td") is not None]
            lines = [" · ".join(_text(cell) for cell in row.find_all(("td", "th")) if _text(cell)) for row in rows]
        elif holder.name == "dl":
            lines = [" · ".join(filter(None, (_text(term), _text(term.find_next_sibling("dd"))))) for term in holder.find_all("dt")]
        else:
            lines = [_text(item) for item in holder.find_all("li")]
        return [line for line in lines if line][:LOG_LIMIT]
    return []


EXPORT_WORDS = frozenset("export exportieren csv".split())


def export_path(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    for anchor in soup.find_all("a", href=True):
        target = _own_link(anchor, page_url)
        if target is None or not target.path.startswith(LIST_PATH):
            continue
        parts = set(_segments(target.path[len(LIST_PATH):]))
        if parts & (REMOVE_SEGMENTS | BLOCKED_SEGMENTS - {"export"}) or any(part.isdigit() for part in parts):
            continue
        if "export" in parts or words(_text(anchor), anchor.get("title")) & EXPORT_WORDS:
            return target.path + ("?" + target.query if target.query else "")
    return ""


def names_entry(url, entry_id):
    target = urlsplit(url or "")
    return bool(entry_id) and (entry_id in target.path.split("/") or entry_id in [value for _key, value in parse_qsl(target.query)])


def upload_link(html, page_url, entry_id):
    soup = BeautifulSoup(html or "", "html.parser")
    for anchor in soup.find_all("a", href=True):
        target = _own_link(anchor, page_url)
        if target is None or not target.path.startswith(LIST_PATH) or not names_entry(target.geturl(), entry_id):
            continue
        label = words(_text(anchor), anchor.get("title"), " ".join(_segments(target.path)))
        if label & ATTACHMENT_ADD_WORDS and label & ADD_WORDS and not set(_segments(target.path)) & REMOVE_SEGMENTS:
            return target.path
    return ""


def upload_form(html, page_url, entry_id):
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all("form"):
        if str(node.get("method") or "get").strip().lower() != "post":
            continue
        files = [field for field in node.find_all("input") if str(field.get("type") or "").lower() == "file" and field.get("name")]
        action = urljoin(page_url or "", str(node.get("action") or "").strip() or (page_url or ""))
        if len(files) != 1 or not names_entry(action, entry_id):
            continue
        form = OlderForm(
            action=action,
            method="post",
            controls=_controls(node),
            submit=_submit(node),
        )
        return form, str(files[0].get("name"))
    return None, ""
