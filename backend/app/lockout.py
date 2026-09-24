import re

from . import messages

LOCKED_MARKERS = (
    "gesperrt",
    "konto gesperrt",
    "zugang gesperrt",
    "benutzerkonto gesperrt",
    "account locked",
    "temporarily locked",
    "zu viele fehlversuche",
    "zu viele fehlgeschlagenen anmeldeversuche",
    "zu viele anmeldeversuche",
    "vorübergehend gesperrt",
    "vorubergehend gesperrt",
)

CAPTCHA_MARKERS = (
    "captcha",
    "recaptcha",
    "sicherheitsabfrage",
    "ich bin kein roboter",
    "i'm not a robot",
    "bestätigen sie, dass sie kein roboter",
    "bestaetigen sie, dass sie kein roboter",
)

PASSWORD_EXPIRED_MARKERS = (
    "passwort ist abgelaufen",
    "passwort abgelaufen",
    "passwort ändern",
    "passwort aendern",
    "passwort muss geändert werden",
    "passwort muss geaendert werden",
    "neues passwort vergeben",
)

BAD_CREDENTIALS = "bad_credentials"
LOCKED = "locked"
CAPTCHA = "captcha"
UNKNOWN_ACCOUNT = "unknown_account"
DEFAULT_PASSWORD_BLOCKED = "default_password_blocked"
TWOFACTOR_REQUIRED_SETUP = "twofactor_required_setup"

BAD_CREDENTIALS_MARKERS = ("anmeldung fehlgeschlagen",)

UNKNOWN_ACCOUNT_MARKERS = ("account existiert nicht",)

DEFAULT_PASSWORD_MARKERS = (
    "mit dem standardpasswort",
    "standardpasswort, welches dem accountnamen entspricht",
)

HUMAN_MESSAGE_KEYS = {
    "locked": "api.lockout.locked",
    "captcha": "api.lockout.captcha",
    "password_expired": "api.lockout.passwordExpired",
    UNKNOWN_ACCOUNT: "api.lockout.unknownAccount",
    DEFAULT_PASSWORD_BLOCKED: "api.lockout.defaultPassword",
    "normal": "api.lockout.normal",
}

_TAG_RE = re.compile(r"<[^>]+>")


def login_refusal(html):
    text = _normalize(html)
    if _matches_any(text, DEFAULT_PASSWORD_MARKERS):
        return DEFAULT_PASSWORD_BLOCKED
    if _matches_any(text, UNKNOWN_ACCOUNT_MARKERS):
        return UNKNOWN_ACCOUNT
    if _matches_any(text, LOCKED_MARKERS):
        return None
    if _matches_any(text, BAD_CREDENTIALS_MARKERS):
        return BAD_CREDENTIALS
    return None


def classify_login_response(html):
    text = _normalize(html)
    if _matches_any(text, DEFAULT_PASSWORD_MARKERS):
        return DEFAULT_PASSWORD_BLOCKED
    if _matches_any(text, UNKNOWN_ACCOUNT_MARKERS):
        return UNKNOWN_ACCOUNT
    if _matches_any(text, LOCKED_MARKERS):
        return LOCKED
    if _matches_any(text, CAPTCHA_MARKERS):
        return CAPTCHA
    if _matches_any(text, PASSWORD_EXPIRED_MARKERS):
        return "password_expired"
    return "normal"


def human_message_key(kind):
    return HUMAN_MESSAGE_KEYS.get(kind, HUMAN_MESSAGE_KEYS["normal"])


def human_message(kind):
    return messages.text(human_message_key(kind))


def _matches_any(text, markers):
    return any(marker in text for marker in markers)


def _normalize(html):
    text = _TAG_RE.sub(" ", html or "")
    return " ".join(text.split()).lower()
