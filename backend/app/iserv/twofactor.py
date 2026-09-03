import re
from dataclasses import dataclass, field as dataclass_field

from bs4 import BeautifulSoup

from .forms import affirmative_submit, parse_forms

CONFIRM_NAME = "confirm[name]"
CONFIRM_VERIFICATION = "confirm[verification]"
CONFIRM_CODE = "confirm[code]"
CONFIRM_HONEYPOT = "confirm[_fake_username]"
CONFIRM_TOKEN = "confirm[_token]"

PASSWORD_CURRENT = "password_change[current]"
PASSWORD_FIRST = "password_change[new][first]"
PASSWORD_SECOND = "password_change[new][second]"
PASSWORD_TOKEN = "password_change[_token]"

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


def parse_token_rows(html):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    for row in soup.select("tbody tr"):
        row_id = row.get("id") or ""
        if not row_id.startswith(ROW_ID_PREFIX):
            continue
        cells = row.find_all("td")
        name = cells[0].get_text(strip=True) if cells else ""
        rows.append({"name": name, "uuid": row_id[len(ROW_ID_PREFIX):]})
    return rows


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


def extract_form_errors(html):
    soup = BeautifulSoup(html or "", "html.parser")
    messages = []
    for selector in ERROR_SELECTORS:
        for node in soup.select(selector):
            text = " ".join(node.get_text(" ", strip=True).split())
            if text and text not in messages:
                messages.append(text)
    return messages
