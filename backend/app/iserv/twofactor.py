import re
from dataclasses import dataclass, field as dataclass_field
from datetime import date
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..valueshape import link_shape
from .forms import affirmative_submit, parse_forms

CONFIRM_NAME = "confirm[name]"
CONFIRM_VERIFICATION = "confirm[verification]"
CONFIRM_CODE = "confirm[code]"
CONFIRM_HONEYPOT = "confirm[_fake_username]"
CONFIRM_TOKEN = "confirm[_token]"

PASSWORD_CURRENT = "password_change[current]"
PASSWORD_FIRST = "password_change[new][first]"
PASSWORD_SECOND = "password_change[new][second]"

OTPAUTH_SECRET = re.compile(r"otpauth://[^\s\"'<>]*[?&]secret=([A-Za-z2-7]+)", re.IGNORECASE)
DATA_SECRET = re.compile(r"data-secret=[\"']([A-Za-z2-7 ]+)[\"']", re.IGNORECASE)

INVALID_CODE_MARKERS = (
    "ungultiger code",
    "ungultiger bestatigungscode",
    "code ist ungultig",
    "code ist falsch",
    "falscher code",
    "invalid code",
    "verifizierung fehlgeschlagen",
    "bestatigung fehlgeschlagen",
    "gultigen 2fa-code",
    "gultigen code",
    "bitte geben sie einen gultigen",
)

ERROR_SELECTORS = (
    ".invalid-feedback",
    ".help-block.error",
    ".alert-danger",
    ".form-error-message",
    "li.error",
    ".has-error .help-block",
)

PASSWORD_ERROR_MARKERS = (
    "aktuelles passwort ist falsch",
    "aktuelles passwort war falsch",
    "passwort ist falsch",
    "passworter stimmen nicht uberein",
    "stimmen nicht uberein",
    "zu kurz",
    "zu einfach",
    "umlaut",
    "nicht erlaubt",
    "fehlgeschlagen",
)

PASSWORD_SUCCESS_MARKERS = (
    "passwort wurde geandert",
    "passwort erfolgreich geandert",
    "passwort erfolgreich gespeichert",
    "erfolgreich geandert",
)

_TAG = re.compile(r"<[^>]+>")


@dataclass
class TwoFactorRegistration:
    action: str
    secret: str
    token: str
    fields: dict
    submits: dict = dataclass_field(default_factory=dict)


def _extract_secret(html):
    match = OTPAUTH_SECRET.search(html or "")
    if match:
        return match.group(1).upper()
    match = DATA_SECRET.search(html or "")
    if match:
        return match.group(1).replace(" ", "").upper()
    return None


def parse_registration(html, base_url):
    secret = _extract_secret(html)
    if not secret:
        return None
    for form in parse_forms(html, base_url):
        if CONFIRM_TOKEN in form.fields or CONFIRM_CODE in form.fields:
            return TwoFactorRegistration(
                action=form.action,
                secret=secret,
                token=form.fields.get(CONFIRM_TOKEN, ""),
                fields=dict(form.fields),
                submits=dict(getattr(form, "submits", {}) or {}),
            )
    return None


SETUP_TOPIC_MARKERS = ("zwei-faktor", "2fa", "two-factor")
SETUP_BLOCKING_MARKERS = (
    "bevor sie fortfahren",
    "um fortzufahren",
    "before you can continue",
    "in order to continue",
)
SETUP_ACTION_MARKERS = ("einrichten", "set up two-factor", "set up 2fa")


def setup_required(html, url="", authenticated=False):
    if parse_registration(html, url) is not None:
        return True
    text = _normalize(html)
    if not any(marker in text for marker in SETUP_TOPIC_MARKERS):
        return False
    if any(marker in text for marker in SETUP_BLOCKING_MARKERS):
        return True
    return not authenticated and any(marker in text for marker in SETUP_ACTION_MARKERS)


def build_confirm_payload(registration, name, verification_code, activation_code):
    payload = dict(registration.fields)
    payload.update(affirmative_submit(getattr(registration, "submits", {}) or {}))
    payload[CONFIRM_NAME] = name
    payload[CONFIRM_VERIFICATION] = verification_code
    payload[CONFIRM_CODE] = activation_code
    payload[CONFIRM_HONEYPOT] = ""
    payload[CONFIRM_TOKEN] = registration.token
    return payload


def registration_rejected(html):
    return _matches(html, INVALID_CODE_MARKERS)


def parse_password_form(html, base_url):
    for form in parse_forms(html, base_url):
        if PASSWORD_CURRENT in form.fields:
            return form
    return None


def build_password_payload(form, current, new):
    payload = dict(form.fields)
    payload[PASSWORD_CURRENT] = current
    payload[PASSWORD_FIRST] = new
    payload[PASSWORD_SECOND] = new
    return payload


def password_changed(html):
    if _matches(html, PASSWORD_ERROR_MARKERS):
        return False
    return _matches(html, PASSWORD_SUCCESS_MARKERS)


def _matches(html, markers):
    text = _normalize(html)
    return any(marker in text for marker in markers)


def _normalize(html):
    stripped = _TAG.sub(" ", html or "")
    lowered = " ".join(stripped.split()).lower()
    table = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})
    return lowered.translate(table)


def parse_token_names(html):
    soup = BeautifulSoup(html or "", "html.parser")
    names = []
    for row in soup.select("tbody tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        value = cells[0].get_text(strip=True)
        if value:
            names.append(value)
    return names


ROW_ID_PREFIX = "client-twofactor-row-"
TOKEN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
CREATED_HEADERS = ("erstellt", "angelegt", "hinzugef", "registriert", "created", "added", "datum", "date")
DOTTED_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


def _created_column(table):
    if table is None:
        return None
    for index, cell in enumerate(table.select("thead th")):
        text = " ".join(cell.get_text(" ", strip=True).split()).lower()
        if any(word in text for word in CREATED_HEADERS):
            return index
    return None


def _calendar_date(year, month, day):
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def _created_date(cell):
    if cell is None:
        return ""
    stamp = cell.find("time")
    for text in ((stamp.get("datetime") or "") if stamp else "", cell.get_text(" ", strip=True)):
        match = ISO_DATE.search(text)
        if match:
            return _calendar_date(*match.groups())
        match = DOTTED_DATE.search(text)
        if match:
            day, month, year = match.groups()
            return _calendar_date(year, month, day)
    return ""


def parse_token_list(html):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    for row in soup.select("tbody tr"):
        cells = row.find_all("td")
        name = cells[0].get_text(strip=True) if cells else ""
        if not name:
            continue
        row_id = row.get("id") or ""
        uuid = row_id[len(ROW_ID_PREFIX):] if row_id.startswith(ROW_ID_PREFIX) else ""
        column = _created_column(row.find_parent("table"))
        created = _created_date(cells[column]) if column is not None and column < len(cells) else ""
        rows.append({"name": name, "uuid": uuid if TOKEN_ID.fullmatch(uuid) else "", "created": created})
    return rows


def parse_token_rows(html):
    return [{"name": row["name"], "uuid": row["uuid"]} for row in parse_token_list(html) if row["uuid"]]


def parse_delete_token(html):
    soup = BeautifulSoup(html or "", "html.parser")
    form = soup.find("form", id="deleteTwoFactorForm")
    if form is None:
        return None
    field = form.find("input", attrs={"name": "delete[_token]"})
    if field is None:
        return None
    value = field.get("value", "")
    return value or None


def recognised_token_list(html):
    if parse_delete_token(html) is None:
        return None
    listed = BeautifulSoup(html or "", "html.parser").select("tbody tr")
    rows = parse_token_list(html)
    if len(listed) != len(rows):
        return None
    return rows


def token_listed(html, rows, uuid):
    wanted = str(uuid or "").lower()
    return any(row.get("uuid", "").lower() == wanted for row in rows) or wanted in (html or "").lower()


def extract_form_errors(html):
    soup = BeautifulSoup(html or "", "html.parser")
    messages = []
    for selector in ERROR_SELECTORS:
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if text and text not in messages:
                messages.append(text)
    return messages


SETUP_TOPIC = "twofactor"
MANUAL_SECRET = re.compile(r"^[A-Z2-7]{16,128}$")
MANUAL_SECRET_SELECTORS = ("code", "[class*=secret]", "[class*=manual]", "[data-secret]")
SETUP_STEP_ACTIVATE = "activate"
SETUP_STEP_NAME = "name"


@dataclass
class TwoFactorSetup:
    step: str
    action: str
    fields: dict
    control_types: dict
    submits: dict
    secret: str = ""
    uri: str = ""
    listed_before: object = None


def _field_role(name, kind):
    lowered = name.lower()
    if kind == "password":
        return "password"
    if "_fake_" in lowered:
        return "honeypot"
    if lowered.endswith("[_token]") or lowered == "_token" or kind == "hidden":
        return "hidden"
    if lowered.endswith("[name]"):
        return "name"
    if lowered.endswith("[code]"):
        return "code"
    if lowered.endswith("[verification]"):
        return "verification"
    if kind in ("submit", "button", "checkbox", "radio"):
        return kind
    return "other"


def _roles(form):
    return {name: _field_role(name, kind) for name, kind in form.control_types.items()}


def _manual_secret(soup):
    for selector in MANUAL_SECRET_SELECTORS:
        for node in soup.select(selector):
            value = node.get("data-secret") or node.get_text(" ", strip=True)
            candidate = "".join(str(value or "").split()).upper()
            if MANUAL_SECRET.match(candidate):
                return candidate
    return ""


def setup_secret(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all(True):
        for value in node.attrs.values():
            if isinstance(value, str) and value.lower().startswith("otpauth://"):
                match = OTPAUTH_SECRET.search(value)
                if match:
                    return match.group(1).upper(), value
    secret = _extract_secret(html) or _manual_secret(soup)
    return secret or "", ""


def _topic_form(form):
    return SETUP_TOPIC in urlsplit(form.action).path.lower().replace("-", "")


def parse_setup_page(html, base_url):
    secret, uri = setup_secret(html)
    forms = parse_forms(html or "", base_url)
    for form in forms:
        roles = set(_roles(form).values())
        if secret and "code" in roles and _topic_form(form) and not _login_like(form):
            return TwoFactorSetup(SETUP_STEP_ACTIVATE, form.action, dict(form.fields), dict(form.control_types),
                                  dict(form.submits or {}), secret, uri)
    if secret:
        return None
    for form in forms:
        roles = set(_roles(form).values())
        if "name" in roles and "code" not in roles and _topic_form(form) and not _login_like(form):
            return TwoFactorSetup(SETUP_STEP_NAME, form.action, dict(form.fields), dict(form.control_types),
                                  dict(form.submits or {}))
    return None


def _login_like(form):
    return "_username" in form.fields or "_password" in form.fields


def build_setup_payload(setup, name, code, password):
    payload = dict(setup.fields)
    payload.update(affirmative_submit(setup.submits))
    for field, role in _roles(setup).items():
        if role == "name":
            payload[field] = name
        elif role == "code":
            payload[field] = code
        elif role in ("password", "verification"):
            payload[field] = password
        elif role == "honeypot":
            payload[field] = ""
    return payload


def setup_shape(response, setup=None):
    text = getattr(response, "text", "") or ""
    secret, uri = setup_secret(text)
    soup = BeautifulSoup(text, "html.parser")
    forms = []
    for form in parse_forms(text, getattr(response, "url", "")):
        forms.append({
            "action": link_shape(form.action),
            "fields": sorted("%s:%s" % (name, role) for name, role in _roles(form).items()),
            "submits": sorted(form.submits or {}),
        })
    return {
        "step": setup.step if setup is not None else "none",
        "secret_found": bool(secret),
        "otpauth_link": bool(uri),
        "picture": any(soup.find(tag) is not None for tag in ("img", "svg", "canvas")),
        "forms": forms,
        "errors": len(extract_form_errors(text)),
        "rejected_wording": registration_rejected(text),
    }
