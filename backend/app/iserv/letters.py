from html import escape as escape_html
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .forms import affirmative_submit, find_login_form, parse_forms
from .html import clean_html

LIST_TABLE_ID = "crud-table"
MULTI_FIELD = "iserv_crud_multi_select[multi][]"
UNREAD_CLASS = "parent-index-table-unread"
TOKEN_FIELD = "iserv_crud_multi_select[_token]"
ACTION_FIELD_MARKER = "[actions]["
RESTORE_ACTION = "iserv_crud_multi_select[actions][parent-restore-letter]"
SHOW_LINK_RE = re.compile(r"/parentletter/parent/show/([^/?#]+)/([^/?#]+)")
MORE_SENDERS_RE = re.compile(r"^\+\s*\d+\s*weitere\b", re.IGNORECASE)
ATTACHMENT_RE = re.compile(r"/parentletter/attachment/([^/?#]+)")
ARCHIVE_RE = re.compile(r"/parentletter/parent/parent_hide/")
CONTENT_SELECTORS = ("div.letter-content", "div.panel-body", "main", "div#content")
CHROME_SELECTORS = ("nav", "header", "footer", ".navbar", ".breadcrumb", ".sidebar")


def parse_letter_list(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=LIST_TABLE_ID)
    letters = []
    if table is None:
        return letters
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        anchor = None
        match = None
        for candidate in row.find_all("a"):
            match = SHOW_LINK_RE.search(candidate.get("href") or "")
            if match:
                anchor = candidate
                break
        if anchor is None:
            continue
        cells = row.find_all("td")
        checkbox = row.find("input", attrs={"name": MULTI_FIELD})
        multi_value = ""
        if checkbox is not None:
            multi_value = (checkbox.get("value") or "").strip()
        letters.append(
            {
                "letter_id": match.group(1),
                "recipient_id": match.group(2),
                "title": anchor.get_text(strip=True),
                "child": _cell_text(cells, 2),
                "sender": _cell_text(cells, 3),
                "additional_senders": _additional_senders_text(cells),
                "recipients": _cell_text(cells, 5),
                "published": _cell_text(cells, 6),
                "show_url": urljoin(base_url, anchor.get("href")),
                "multi_value": multi_value,
                "unread": _is_unread(row),
            }
        )
    return letters


def _is_unread(row):
    if _has_unread_class(row):
        return True
    for element in row.find_all(True):
        if _has_unread_class(element):
            return True
    return False


def _has_unread_class(element):
    classes = element.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return any(UNREAD_CLASS in str(name) for name in classes)


def parse_letter_detail(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(["script", "style"]):
        element.decompose()
    for selector in CHROME_SELECTORS:
        for element in soup.select(selector):
            element.decompose()
    title = ""
    heading = soup.find("h1")
    if heading is not None:
        title = heading.get_text(strip=True)
    elif soup.title is not None:
        title = soup.title.get_text(strip=True)
    attachments = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        match = ATTACHMENT_RE.search(href)
        if match:
            attachments.append(
                {
                    "url": urljoin(base_url, href),
                    "attachment_id": match.group(1),
                    "filename": anchor.get_text(strip=True),
                }
            )
    archive_url = ""
    archive_anchor = soup.find("a", href=ARCHIVE_RE)
    if archive_anchor is not None:
        archive_url = urljoin(base_url, archive_anchor.get("href"))
    container = _find_content(soup)
    _drop_attachment_links(container)
    return {
        "title": title,
        "body_html": clean_html(container.decode_contents()),
        "attachments": _unique_attachments(attachments),
        "archive_url": archive_url,
    }


def _drop_attachment_links(container):
    for anchor in container.find_all("a"):
        if not ATTACHMENT_RE.search(anchor.get("href") or ""):
            continue
        holder = anchor
        for _ in range(3):
            parent = holder.parent
            if parent is None or parent is container:
                break
            if len(parent.find_all("a")) > 1 or parent.get_text(strip=True) != holder.get_text(strip=True):
                break
            holder = parent
        holder.decompose()


def _unique_attachments(attachments):
    seen = set()
    result = []
    for entry in attachments:
        key = entry.get("attachment_id")
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def parse_archive_form(html, base_url, action=None):
    for form in parse_forms(html, base_url):
        token = form.fields.get(TOKEN_FIELD)
        if token is None:
            continue
        submits = dict(getattr(form, "submits", None) or {})
        action_field = _select_action(form, submits, action)
        if action_field is None:
            continue
        return {
            "action": form.action,
            "token": token,
            "action_field": action_field,
            "submits": submits,
        }
    return None


def build_archive_payload(form, multi_values, action=None):
    selected = action or form["action_field"]
    return {
        MULTI_FIELD: list(multi_values),
        selected: _action_value(form, action),
        TOKEN_FIELD: form["token"],
    }


def _select_action(form, submits, action):
    if action is None:
        return next((name for name in form.fields if ACTION_FIELD_MARKER in name), None)
    if action in form.fields or action in submits:
        return action
    return None


def _action_value(form, action):
    if action is None:
        return ""
    submits = form.get("submits") or {}
    if action not in submits:
        return ""
    return affirmative_submit({action: submits[action]}).get(action, "")


def _cell_text(cells, index):
    if index >= len(cells):
        return ""
    return cells[index].get_text(strip=True)


def _additional_senders_text(cells):
    if 4 >= len(cells):
        return ""
    cell = cells[4]
    children = cell.find_all(True, recursive=False)
    if not children:
        return cell.get_text(strip=True)
    names = []
    for child in children:
        text = child.get_text(strip=True)
        if not text or MORE_SENDERS_RE.match(text):
            continue
        title = (child.get("title") or child.get("data-original-title") or "").strip()
        for name in (title.split(",") if title else [text]):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    if not names:
        return cell.get_text(strip=True)
    return ", ".join(names)


def _find_content(soup):
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            return node
    best = None
    best_length = -1
    for div in soup.find_all("div"):
        length = len(div.get_text(strip=True))
        if length > best_length:
            best = div
            best_length = length
    if best is not None:
        return best
    return soup.body or soup


HIDE_TOKEN = "hide_confirm[_token]"


def parse_hide_confirm(html, base_url):
    for form in parse_forms(html, base_url):
        if HIDE_TOKEN in form.fields:
            return form
    return None


def build_hide_payload(form):
    payload = dict(form.fields)
    payload.update(affirmative_submit(getattr(form, "submits", {}) or {}))
    return payload


CONFIRMATION_ATTR = "confirmation-type"
CONFIRMATION_NONE = "none"
CONFIRMATION_SEEN = "seen"
SENDABLE_CONFIRMATIONS = (CONFIRMATION_SEEN,)


EDITOR_TAG = "iserv-editor"
EDITOR_MODES = ("rich", "plain")
EMPTY_EDITOR_HTML = "<p></p>"


def _form_custom_fields(form):
    prefix = f"{form.get('name') or 'form'}["
    found = []
    for control in form.find_all(True):
        if "-" not in control.name:
            continue
        name = control.get("name") or ""
        if name.startswith(prefix):
            found.append((control, name))
    return found


def _editor_mode(control):
    chosen = (control.get("initial-mode") or "").strip()
    if chosen:
        return chosen
    raw = control.get("config") or ""
    try:
        config = json.loads(raw) if raw else {}
    except ValueError:
        config = {}
    if isinstance(config, dict):
        for mode in EDITOR_MODES:
            if config.get(mode):
                return mode
    return EDITOR_MODES[0]


def _plain_to_html(text):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = "".join(f"<p>{escape_html(line)}</p>" for line in lines if line != "")
    return body or EMPTY_EDITOR_HTML


def _editor_fields(control, name):
    mode = _editor_mode(control)
    initial = control.get("initial-content") or ""
    if mode == "rich" and initial.strip():
        html_value = initial
        plain_value = BeautifulSoup(initial, "html.parser").get_text("\n").strip()
    else:
        plain_value = initial if mode == "plain" else ""
        html_value = _plain_to_html(plain_value)
    return {f"{name}[html]": html_value, f"{name}[plain]": plain_value, f"{name}[mode]": mode}


def parse_confirmation(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    button = soup.find(attrs={CONFIRMATION_ATTR: True})
    if button is None:
        return None
    kind = (button.get(CONFIRMATION_ATTR) or "").strip().lower()
    if not kind or kind == CONFIRMATION_NONE:
        return None
    if confirmation_closed(soup):
        return None
    form = button.find_parent("form")
    if form is None:
        return None
    action = urljoin(base_url, button.get("formaction") or form.get("action") or base_url)
    return _confirmation_from_form(form, kind, action, base_url)


def _open_marks(soup):
    return [
        node
        for node in soup.find_all(attrs={CONFIRMATION_ATTR: True})
        if (node.get(CONFIRMATION_ATTR) or "").strip().lower() not in ("", CONFIRMATION_NONE)
    ]


def confirmation_closed(page):
    soup = page if isinstance(page, BeautifulSoup) else BeautifulSoup(page or "", "html.parser")
    marks = _open_marks(soup)
    if not marks or not all(node.has_attr("disabled") for node in marks):
        return ""
    return (marks[0].get(CONFIRMATION_ATTR) or "").strip().lower()


def reply_problem(html, url=""):
    text = html or ""
    return find_login_form(parse_forms(text, url or SHAPE_BASE)) is not None or reply_form_errors(text) > 0


def _confirmation_from_form(form, kind, action, base_url):
    fields = {}
    submits = {}
    submit_controls = []
    text_field = ""
    for control in form.find_all(["input", "textarea", "select"]):
        name = control.get("name")
        if not name or control.name == "select":
            continue
        if control.name == "textarea":
            text_field = name
            fields[name] = control.get_text() or ""
            continue
        control_type = (control.get("type") or "text").lower()
        if control_type == "submit":
            submits[name] = control.get("value") or ""
            submit_controls.append(control)
            continue
        if control_type in CHOICE_INPUT_TYPES:
            continue
        fields[name] = control.get("value") or ""
    for control in form.find_all("button"):
        name = control.get("name")
        if not name or (control.get("type") or "submit").lower() != "submit":
            continue
        submits[name] = control.get("value") or ""
        submit_controls.append(control)
    editor = ""
    for control, name in _form_custom_fields(form):
        if control.name == EDITOR_TAG:
            editor = editor or name
            fields.update(_editor_fields(control, name))
    plain = kind in SENDABLE_CONFIRMATIONS and len(submits) == 1 and not _choice_groups(form)
    choice = None if plain else _confirmation_choice(form, submit_controls, action, base_url)
    if kind == ANSWER_EDIT and choice and choice["mode"] == CHOICE_SUBMIT and len(choice["options"]) == 1:
        if editor or text_field:
            plain = True
            choice = None
            submits = {choice_name: value for choice_name, value in submits.items() if choice_name in _enabled_names(submit_controls)}
    return {
        "editor": editor,
        "type": kind,
        "action": action,
        "fields": fields,
        "submits": submits,
        "text_field": text_field,
        "text": fields.get(text_field, "") if text_field else "",
        "choice": choice,
        "sendable": plain or choice is not None,
    }


ANSWER_EDIT = "edit"
ANSWER_EDIT_HINTS = ("edit", "bearbeiten", "ändern", "aendern", "change")
ANSWER_EDIT_SKIP = re.compile(r"/parentletter/(?:attachment/|parent/(?:index|archive|show/|parent_hide/))")
ANSWER_FORM_SKIP = re.compile(r"/parentletter/(?:attachment/|parent/parent_hide/)")
CHOICE_SUBMIT = "submit"
CHOICE_RADIO = "radio"
CHOICE_SELECT = "select"
CHOICE_CHECKBOX = "checkbox"
CHOICE_INPUT_TYPES = (CHOICE_RADIO, CHOICE_CHECKBOX)
CHOICE_PLAIN_INPUT_TYPES = ("hidden", "submit", "button", "reset", CHOICE_RADIO, CHOICE_CHECKBOX)
CHOICE_LABEL_LENGTH = 200
CHOICE_ID_LENGTH = 16
CHOICE_LIMIT = 30
SUBMIT_MARK_CLASSES = ("active", "selected", "checked")


def _enabled(control):
    return not control.has_attr("disabled")


def _enabled_names(controls):
    return {control.get("name") for control in controls if _enabled(control)}


def _module_link(url, base_url):
    path = urlparse(url).path
    return _origin(url) == _origin(base_url) and "%" not in path and path.startswith(REPLY_MODULE_PATH)


def _module_anchors(soup, base_url):
    for anchor in soup.find_all("a", href=True):
        if not _outside_letter_body(anchor) or anchor.find_parent(["nav", "header", "footer"]) is not None:
            continue
        url = urljoin(base_url, anchor["href"])
        if _module_link(url, base_url):
            yield anchor, url


def _names_letter(url, letter_id, recipient_id):
    segments = urlparse(str(url or "")).path.lower().split("/")
    return str(letter_id or "").lower() in segments and str(recipient_id or "").lower() in segments


def find_answer_edit(html, base_url, letter_id, recipient_id):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for anchor, url in _module_anchors(soup, base_url):
        path = urlparse(url).path.lower()
        if ANSWER_EDIT_SKIP.search(path) or not _names_letter(url, letter_id, recipient_id):
            continue
        text = " ".join(anchor.get_text(" ").split()).lower()
        if any(hint in path or hint in text for hint in ANSWER_EDIT_HINTS):
            if url not in found:
                found.append(url)
    return found[0] if len(found) == 1 else None


def parse_answer_form(html, base_url, letter_id, recipient_id):
    found = parse_confirmation(html, base_url)
    if found is not None:
        return found if _names_letter(found["action"], letter_id, recipient_id) else None
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []
    for form in soup.find_all("form"):
        if not _outside_letter_body(form) or (form.get("method") or "get").strip().lower() != "post":
            continue
        action = urljoin(base_url, form.get("action") or base_url)
        if not _module_link(action, base_url) or ANSWER_FORM_SKIP.search(urlparse(action).path.lower()):
            continue
        if not _names_letter(action, letter_id, recipient_id):
            continue
        names = [str(control.get("name") or "") for control in form.find_all("input")]
        if any(name.endswith("[_token]") for name in names) and not any(MULTI_FIELD == name for name in names):
            candidates.append((form, action))
    if len(candidates) != 1:
        return None
    form, action = candidates[0]
    return _confirmation_from_form(form, ANSWER_EDIT, action, base_url)


def _choice_groups(form):
    radios = {
        control.get("name")
        for control in form.find_all("input")
        if (control.get("type") or "").strip().lower() == CHOICE_RADIO and control.get("name")
    }
    boxes = [
        control
        for control in form.find_all("input")
        if (control.get("type") or "").strip().lower() == CHOICE_CHECKBOX and control.get("name")
    ]
    selects = [control for control in form.find_all("select") if control.get("name")]
    return len(radios) + (1 if boxes else 0) + len(selects)


def _choice_text(text):
    return " ".join(str(text or "").split())[:CHOICE_LABEL_LENGTH]


def _choice_id(mode, name, value, label):
    digest = hashlib.sha256("\0".join((mode, name, value, label)).encode("utf-8")).hexdigest()
    return digest[:CHOICE_ID_LENGTH]


def _choice_option(mode, name, value, label, selected=False):
    label = _choice_text(label) or _choice_text(value)
    return {
        "id": _choice_id(mode, name, value, label),
        "name": name,
        "value": value,
        "label": label,
        "selected": bool(selected),
    }


def _input_label(form, control):
    control_id = control.get("id")
    if control_id:
        label = form.find("label", attrs={"for": control_id})
        if label is not None and _choice_text(label.get_text(" ")):
            return label.get_text(" ")
    holder = control.find_parent("label")
    if holder is not None and _choice_text(holder.get_text(" ")):
        return holder.get_text(" ")
    sibling = control.next_sibling
    while sibling is not None and getattr(sibling, "name", None) is None:
        if _choice_text(sibling):
            return str(sibling)
        sibling = sibling.next_sibling
    return ""


def _foreign_controls(form):
    for control in form.find_all("input"):
        if (control.get("type") or "text").strip().lower() not in CHOICE_PLAIN_INPUT_TYPES:
            return True
    for control, _ in _form_custom_fields(form):
        if control.name != EDITOR_TAG:
            return True
    return len(form.find_all(EDITOR_TAG)) > 1 or len(form.find_all("textarea")) > 1


def _group_options(form):
    radios = [
        control
        for control in form.find_all("input")
        if (control.get("type") or "").strip().lower() == CHOICE_RADIO and control.get("name") and _enabled(control)
    ]
    if radios:
        return CHOICE_RADIO, False, [
            _choice_option(CHOICE_RADIO, control["name"], control.get("value") or "on", _input_label(form, control), control.has_attr("checked"))
            for control in radios
        ]
    boxes = [
        control
        for control in form.find_all("input")
        if (control.get("type") or "").strip().lower() == CHOICE_CHECKBOX and control.get("name") and _enabled(control)
    ]
    if boxes:
        return CHOICE_CHECKBOX, True, [
            _choice_option(CHOICE_CHECKBOX, control["name"], control.get("value") or "on", _input_label(form, control), control.has_attr("checked"))
            for control in boxes
        ]
    select = form.find("select", attrs={"name": True})
    if select is None or not _enabled(select):
        return None, False, []
    options = []
    for option in select.find_all("option"):
        value = option.get("value")
        value = option.get_text(" ") if value is None else value
        if not str(value).strip() or not _enabled(option):
            continue
        options.append(_choice_option(CHOICE_SELECT, select["name"], str(value), option.get_text(" "), option.has_attr("selected")))
    return CHOICE_SELECT, select.has_attr("multiple"), options


def _confirmation_choice(form, submit_controls, action, base_url):
    if _foreign_controls(form) or not _module_link(action, base_url):
        return None
    submits = [control for control in submit_controls if _enabled(control)]
    groups = _choice_groups(form)
    if groups == 0:
        if not submits:
            return None
        mode, multiple, submit = CHOICE_SUBMIT, False, {}
        options = [
            _choice_option(
                CHOICE_SUBMIT,
                control["name"],
                control.get("value") or "",
                control.get_text(" ") if control.name == "button" else control.get("value"),
                _submit_marked(control),
            )
            for control in submits
        ]
    else:
        if groups != 1 or len(submits) != 1:
            return None
        mode, multiple, options = _group_options(form)
        submit = {submits[0]["name"]: submits[0].get("value") or ""}
    ids = [option["id"] for option in options]
    if not options or len(options) > CHOICE_LIMIT or len(set(ids)) != len(ids):
        return None
    if any(not option["label"] for option in options):
        return None
    return {"mode": mode, "multiple": multiple, "options": options, "submit": submit}


def answer_text(confirmation):
    confirmation = confirmation or {}
    field = confirmation.get("text_field") or ""
    if field:
        return str((confirmation.get("fields") or {}).get(field) or "")
    editor = confirmation.get("editor") or ""
    if editor:
        return str((confirmation.get("fields") or {}).get(f"{editor}[plain]") or "")
    return ""


def public_choice(choice):
    if not choice:
        return None
    return {
        "mode": choice["mode"],
        "multiple": bool(choice["multiple"]),
        "options": [
            {"id": option["id"], "label": option["label"], "selected": bool(option["selected"])}
            for option in choice["options"]
        ],
    }


def picked_options(choice, chosen):
    chosen = [str(item) for item in chosen or [] if isinstance(item, str)]
    if not choice or not chosen or len(set(chosen)) != len(chosen):
        return None
    if not choice["multiple"] and len(chosen) != 1:
        return None
    by_id = {option["id"]: option for option in choice["options"]}
    if any(item not in by_id for item in chosen):
        return None
    return [by_id[item] for item in chosen]


def build_choice_payload(confirmation, picked, text=None):
    payload = build_confirmation_payload(dict(confirmation, submits={}), text)
    values = {}
    for option in picked:
        values.setdefault(option["name"], []).append(option["value"])
    for name, chosen in values.items():
        payload[name] = chosen[0] if len(chosen) == 1 else chosen
    payload.update(confirmation["choice"].get("submit") or {})
    return payload


def _submit_marked(control):
    classes = control.get("class") or []
    classes = classes.split() if isinstance(classes, str) else classes
    pressed = (control.get("aria-pressed") or control.get("aria-checked") or "").strip().lower() == "true"
    return pressed or any(name in SUBMIT_MARK_CLASSES for name in classes)


def choice_recorded(confirmation, picked):
    choice = (confirmation or {}).get("choice")
    if not choice:
        return False
    selected = {(option["name"], option["value"]) for option in choice["options"] if option["selected"]}
    wanted = {(option["name"], option["value"]) for option in picked}
    return bool(wanted) and selected == wanted


def build_confirmation_payload(confirmation, text=None):
    payload = dict(confirmation.get("fields") or {})
    field = confirmation.get("text_field") or ""
    if field and text is not None:
        payload[field] = text
    editor = confirmation.get("editor") or ""
    if editor and not field and text is not None:
        payload[f"{editor}[plain]"] = text
        payload[f"{editor}[html]"] = _plain_to_html(text)
    submits = dict(confirmation.get("submits") or {})
    name = next(iter(submits), "")
    if name:
        payload[name] = submits[name]
    return payload


REPLY_PRESENT = "present"
REPLY_ABSENT = "absent"
REPLY_UNKNOWN = "unknown"
REPLY_HINTS = ("reply", "answer", "respond")
REPLY_ENCODING = "application/x-www-form-urlencoded"
REPLY_MODULE_PATH = "/iserv/parentletter/"
SUBMIT_INPUT_TYPES = ("submit", "image")


def _is_submit(control):
    if control.name == "button":
        return (control.get("type") or "submit").strip().lower() == "submit"
    return control.name == "input" and (control.get("type") or "text").strip().lower() in SUBMIT_INPUT_TYPES


def _origin(url):
    parts = urlparse(str(url or ""))
    return (parts.scheme.lower(), parts.netloc.lower())


def _outside_letter_body(node):
    return node.find_parent(class_=LETTER_BODY_CLASS) is None


def _reply_hint_count(soup):
    count = 0
    for node in soup.find_all(["a", "form", "button"]):
        if not _outside_letter_body(node):
            continue
        target = node.get("href") or node.get("action") or node.get("formaction") or ""
        path = urlparse(str(target)).path.lower()
        if any(word in path for word in REPLY_HINTS):
            count += 1
    return count


def _reply_candidates(soup):
    candidates = []
    for form in soup.find_all("form"):
        if not _outside_letter_body(form):
            continue
        if form.find(EDITOR_TAG) is not None or form.find("textarea") is not None:
            candidates.append(form)
    return candidates


def _strict_reply_form(form, base_url):
    name = (form.get("name") or "").strip()
    if not name or form.find(attrs={CONFIRMATION_ATTR: True}) is not None:
        return None
    if (form.get("method") or "get").strip().lower() != "post":
        return None
    if (form.get("enctype") or REPLY_ENCODING).strip().lower() != REPLY_ENCODING:
        return None
    if form.find_all(["textarea", "select"]) or len(form.find_all(EDITOR_TAG)) != 1:
        return None
    custom = _form_custom_fields(form)
    if len(custom) != 1 or custom[0][0].name != EDITOR_TAG:
        return None
    editor, editor_name = custom[0]
    if editor.has_attr("disabled") or editor.has_attr("readonly"):
        return None
    fields = {}
    for control in form.find_all("input"):
        if _is_submit(control):
            continue
        if (control.get("type") or "text").strip().lower() != "hidden":
            return None
        if control.get("name"):
            fields[control["name"]] = control.get("value") or ""
    if f"{name}[_token]" not in fields:
        return None
    submits = [control for control in form.find_all(["button", "input"]) if _is_submit(control)]
    if len(submits) != 1:
        return None
    submit = submits[0]
    if not submit.get("name") or submit.has_attr("disabled"):
        return None
    action = urljoin(base_url, submit.get("formaction") or form.get("action") or base_url)
    path = urlparse(action).path
    if _origin(action) != _origin(base_url) or "%" in path or not path.startswith(REPLY_MODULE_PATH):
        return None
    fields.update(_editor_fields(editor, editor_name))
    return {
        "action": action,
        "fields": fields,
        "submits": {submit["name"]: submit.get("value") or ""},
        "editor": editor_name,
    }


def parse_reply_form(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = _reply_candidates(soup)
    outline = {
        "candidates": len(candidates),
        "editors": sum(len(form.find_all(EDITOR_TAG)) for form in candidates),
        "textareas": sum(len(form.find_all("textarea")) for form in candidates),
        "submits": sum(
            len([control for control in form.find_all(["button", "input"]) if _is_submit(control)])
            for form in candidates
        ),
        "marked": sum(1 for form in candidates if form.find(attrs={CONFIRMATION_ATTR: True}) is not None),
        "hints": _reply_hint_count(soup),
    }
    if len(candidates) == 1:
        form = _strict_reply_form(candidates[0], base_url)
        if form is not None:
            return {"state": REPLY_PRESENT, "form": form, "outline": outline}
    if candidates or outline["hints"]:
        return {"state": REPLY_UNKNOWN, "form": None, "outline": outline}
    return {"state": REPLY_ABSENT, "form": None, "outline": outline}


def build_reply_payload(form, text):
    payload = dict(form.get("fields") or {})
    editor = form.get("editor") or ""
    payload[f"{editor}[plain]"] = text
    payload[f"{editor}[html]"] = _plain_to_html(text)
    payload.update(form.get("submits") or {})
    return payload


REPLY_ERROR_SELECTORS = (".alert-danger", ".form-error-message", ".invalid-feedback", ".has-error .help-block")


def reply_form_errors(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return sum(
        1
        for selector in REPLY_ERROR_SELECTORS
        for node in soup.select(selector)
        if _outside_letter_body(node) and node.get_text(" ", strip=True)
    )


REPLY_WARNING_SELECTORS = (".alert-warning",)
REPLY_HIDDEN_TAGS = ("script", "style", "template", "noscript", "form", EDITOR_TAG, "textarea")


def reply_warnings(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return sum(
        1
        for selector in REPLY_WARNING_SELECTORS
        for node in soup.select(selector)
        if _outside_letter_body(node) and node.get_text(" ", strip=True)
    )


def reply_count(html, text):
    wanted = " ".join(str(text or "").split()).casefold()
    if not wanted:
        return 0
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all(REPLY_HIDDEN_TAGS):
        node.decompose()
    for node in soup.find_all(class_=LETTER_BODY_CLASS):
        node.decompose()
    return " ".join(soup.get_text(" ").split()).casefold().count(wanted)


NOTICE_SELECTORS = (".alert", ".form-error-message", ".invalid-feedback", ".help-block", ".error")
NOTICE_LIMIT = 3
NOTICE_LENGTH = 80
BUTTON_TEXT_LENGTH = 40
LETTER_BODY_CLASS = "parent-letter-body"


def _short(text, limit):
    return " ".join(str(text or "").split())[:limit]


def page_notices(html):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for selector in NOTICE_SELECTORS:
        for node in soup.select(selector):
            if node.find_parent(class_=LETTER_BODY_CLASS) is not None:
                continue
            text = _short(node.get_text(" "), NOTICE_LENGTH)
            if text and text not in found:
                found.append(text)
            if len(found) >= NOTICE_LIMIT:
                return found
    return found


def _field_label(control):
    marks = []
    if control.name in ("textarea", "select"):
        marks.append(control.name)
    else:
        kind = (control.get("type") or "text").lower()
        if kind not in ("hidden", "text"):
            marks.append(kind)
    for flag in ("required", "disabled"):
        if control.has_attr(flag):
            marks.append(flag)
    name = control.get("name") or ""
    return f"{name} ({', '.join(marks)})" if marks else name


def _is_named_submit(control):
    if not control.get("name"):
        return False
    if control.name == "button":
        return (control.get("type") or "submit").lower() == "submit"
    return control.name == "input" and (control.get("type") or "text").lower() == "submit"


OUTLINE_VALUE_ATTRIBUTES = (
    "type",
    "name",
    "id",
    "role",
    "method",
    "action",
    "enctype",
    "formaction",
    "formmethod",
    "formenctype",
    "target",
    "class",
    CONFIRMATION_ATTR,
)
OUTLINE_LENGTH = 1200
OUTLINE_VALUE_LENGTH = 60
OUTLINE_PATH_LENGTH = 160
SCRIPT_LIMIT = 12


def _path_only(value):
    parsed = urlparse(str(value or ""))
    if parsed.scheme or parsed.netloc or parsed.query:
        return parsed.path
    return str(value or "")


def _outline_node(node):
    parts = []
    for name, value in node.attrs.items():
        if name == "value":
            continue
        text = " ".join(value) if isinstance(value, list) else str(value or "")
        if name in OUTLINE_VALUE_ATTRIBUTES or name.startswith("data-"):
            if "/" in text or "?" in text:
                text = _short(_path_only(text), OUTLINE_PATH_LENGTH)
            else:
                text = _short(text, OUTLINE_VALUE_LENGTH)
            parts.append(f"{name}={text}" if text else name)
        else:
            parts.append(name)
    label = node.name + (f"[{', '.join(parts)}]" if parts else "")
    if node.name == "button":
        label += f" '{_short(node.get_text(' '), BUTTON_TEXT_LENGTH)}'"
    return label


def _form_outline(form):
    nodes = [form] + list(form.find_all(True))
    return " | ".join(_outline_node(node) for node in nodes)[:OUTLINE_LENGTH]


def _script_sources(soup):
    found = []
    for node in soup.find_all("script", src=True):
        path = urlparse(node.get("src") or "").path
        if path and path not in found:
            found.append(path)
        if len(found) >= SCRIPT_LIMIT:
            break
    return found


def confirmation_evidence(html):
    soup = BeautifulSoup(html or "", "html.parser")
    marked = soup.find_all(attrs={CONFIRMATION_ATTR: True})
    if not marked:
        return None
    first = marked[0]
    form = first.find_parent("form")
    fields = []
    submits = 0
    controls = form.find_all(["input", "textarea", "select", "button"]) if form is not None else []
    for control in controls:
        if _is_named_submit(control):
            submits += 1
        elif control.name != "button" and control.get("name"):
            fields.append(_field_label(control))
    if form is not None:
        for control, name in _form_custom_fields(form):
            fields.append(f"{name} ({control.name})")
    classes = first.get("class") or []
    return {
        "confirmation_marks": [str(node.get(CONFIRMATION_ATTR) or "").strip() for node in marked],
        "confirmation_disabled": first.has_attr("disabled") or "disabled" in classes,
        "confirmation_button": _short(first.get_text(" "), BUTTON_TEXT_LENGTH),
        "confirmation_fields": fields,
        "confirmation_submits": submits,
        "page_notices": page_notices(html),
        "confirmation_target": _path_only(first.get("formaction") or (form.get("action") if form is not None else "")),
        "confirmation_button_attributes": sorted(first.attrs.keys()),
        "confirmation_form": _form_outline(form) if form is not None else "",
        "script_sources": _script_sources(soup),
    }


SHAPE_ID = re.compile(r"[0-9a-fA-F]{8,}(?:-[0-9a-fA-F]{4,})*")
SHAPE_NUMBER = re.compile(r"\d+")
SHAPE_NAME_LIMIT = 12
SHAPE_LENGTH = 600
SHAPE_BASE = "https://school.invalid/iserv/parentletter/"


def _shape_name(name):
    return SHAPE_NUMBER.sub("<n>", SHAPE_ID.sub("<id>", str(name or "")))[:OUTLINE_VALUE_LENGTH]


def confirmation_shape(html, base_url=""):
    soup = BeautifulSoup(html or "", "html.parser")
    marked = soup.find_all(attrs={CONFIRMATION_ATTR: True})
    if not marked:
        return ""
    marks = sorted({str(node.get(CONFIRMATION_ATTR) or "").strip().upper() or "-" for node in marked})
    form = marked[0].find_parent("form")
    if form is None:
        return "marks=%s; form=none" % ",".join(marks)
    parsed = parse_confirmation(html, base_url or SHAPE_BASE)
    return _form_shape(form, "marks=%s" % ",".join(marks), parsed)


def answer_form_shape(html, base_url, letter_id, recipient_id):
    soup = BeautifulSoup(html or "", "html.parser")
    forms = [
        form
        for form in soup.find_all("form")
        if _outside_letter_body(form) and form.find_parent(["nav", "header"]) is None
    ]
    if not forms:
        return "edit page; forms=0"
    parsed = parse_answer_form(html, base_url, letter_id, recipient_id)
    parts = [_form_shape(form, "edit page form %d/%d" % (index, len(forms)), parsed) for index, form in enumerate(forms[:3], 1)]
    return " | ".join(parts)[:SHAPE_LENGTH]


def _form_shape(form, head, parsed):
    counts = {}
    names = []
    disabled = 0
    for control in form.find_all(["input", "textarea", "select", "button", "option", EDITOR_TAG]):
        if control.name == "input":
            key = "input:" + (control.get("type") or "text").strip().lower()
        elif control.name == "button":
            key = "button:" + (control.get("type") or "submit").strip().lower()
        else:
            key = control.name
        counts[key] = counts.get(key, 0) + 1
        if control.has_attr("disabled"):
            disabled += 1
        name = _shape_name(control.get("name"))
        if name and name not in names and len(names) < SHAPE_NAME_LIMIT:
            names.append(name)
    labels = len(form.find_all("label"))
    choice = (parsed or {}).get("choice")
    if parsed is None:
        mode = "none"
    elif choice:
        mode = "%s options=%d%s" % (choice["mode"], len(choice["options"]), " multiple" if choice["multiple"] else "")
    else:
        mode = "plain" if parsed.get("sendable") else "unsupported"
    controls = ", ".join("%s x%d" % (key, counts[key]) for key in sorted(counts))
    text = "%s; method=%s; action=%s; controls=%s; disabled=%d; labels=%d; names=%s; mode=%s" % (
        head,
        (form.get("method") or "get").strip().lower(),
        _shape_name(urlparse(str(form.get("action") or "")).path) or "-",
        controls or "none",
        disabled,
        labels,
        ", ".join(names) or "none",
        mode,
    )
    return text[:SHAPE_LENGTH]


def answered_page_shape(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    paths = []
    for _, url in _module_anchors(soup, base_url):
        path = _shape_name(urlparse(url).path)
        if path not in paths and len(paths) < SHAPE_NAME_LIMIT:
            paths.append(path)
    buttons = []
    for control in soup.find_all(["button", "input"]):
        if not _outside_letter_body(control) or not _is_submit(control):
            continue
        name = _shape_name(control.get("name")) or "-"
        if name not in buttons and len(buttons) < SHAPE_NAME_LIMIT:
            buttons.append(name)
    forms = [form for form in soup.find_all("form") if _outside_letter_body(form)]
    text = "answered page; forms=%d; module links=%s; submits=%s" % (
        len(forms),
        ", ".join(paths) or "none",
        ", ".join(buttons) or "none",
    )
    return text[:SHAPE_LENGTH]


CONFIRM_FIELD = "iserv_crud_multi_select[confirm]"


def parse_batch_confirm(html, base_url):
    for form in parse_forms(html, base_url):
        if MULTI_FIELD in form.fields or CONFIRM_FIELD in form.fields:
            names = set(form.fields) | set(getattr(form, "submits", None) or {})
            if any(ACTION_FIELD_MARKER in name for name in names):
                return form
    return None


def build_batch_confirm_payload(form, action):
    payload = {name: value for name, value in form.fields.items() if ACTION_FIELD_MARKER not in name}
    payload.setdefault(CONFIRM_FIELD, "1")
    submits = dict(getattr(form, "submits", None) or {})
    if action in submits or action in form.fields:
        payload[action] = submits.get(action, form.fields.get(action, ""))
    else:
        payload.update(affirmative_submit(submits))
    return payload
