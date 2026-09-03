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

LOCKED_STATUS_CODES = (403, 429)

HUMAN_MESSAGE_KEYS = {
    "locked": "api.lockout.locked",
    "captcha": "api.lockout.captcha",
    "password_expired": "api.lockout.passwordExpired",
    "normal": "api.lockout.normal",
}

_TAG_RE = re.compile(r"<[^>]+>")


def classify_login_response(html, status_code=200):
    text = _normalize(html)
    if _matches_any(text, LOCKED_MARKERS) or status_code in LOCKED_STATUS_CODES:
        return "locked"
    if _matches_any(text, CAPTCHA_MARKERS):
        return "captcha"
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
