import json
import re
from datetime import date
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .errors import DataError
from .pages import path_of

MAIL_PAGE = "/iserv/mail"
CALENDAR_PAGE = "/iserv/calendar"
CREATE_EVENT_KEY = "calendar_create_event"
CREATE_EVENT_FALLBACK = "/iserv/calendar/create"
TITLE_WORDS = ("subject", "title", "summary", "name")
DESCRIPTION_WORDS = ("description", "note", "body", "text", "comment")
DAY_WORDS = ("start", "begin", "date", "day")
TIME_WORDS = ("starttime", "begintime", "time")
ALL_DAY_WORDS = ("allday", "wholeday", "ganztag")
CALENDAR_WORDS = ("calendar", "kalender")
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)")
ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
GERMAN_DAY = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})")
PHP_DATA = "php-data"
SERVER_CONFIG = "serverConfig"
LOGIN_MARKS = ("/iserv/auth/", "/iserv/login")
SETTING_WORDS = {
    "vacation": ("vacation", "absence", "autorespond", "autoreply", "abwesen", "outofoffice", "out-of-office"),
    "forward": ("forward", "redirect", "weiterleit"),
    "filter": ("filter", "rule", "regel", "sieve"),
    "signature": ("signature", "signatur"),
    "tags": ("tag", "label", "schlagw"),
    "settings": ("setting", "einstellung", "preference", "option"),
}
GUESSED_PAGES = (
    "/iserv/mail/settings",
    "/iserv/mail/settings/vacation",
    "/iserv/mail/settings/forward",
    "/iserv/mail/settings/filter",
    "/iserv/mail/settings/signature",
    "/iserv/mail/vacation",
    "/iserv/mail/forward",
    "/iserv/mail/filter",
)
PAGE_LIMIT = 14
SKIPPED_PARTS = ("/help", "/static", "/assets", "/api/", "/logout")
PAGE_SIZE_RANGE = (5, 500)
LOOKUP_PARAMS = ("query", "q", "term", "search")
LOOKUP_LIMIT = 25
QUERY_LIMIT = 80
ADDRESS = re.compile(r"^[^@\s<>\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z0-9-]{2,63}$")
PATH_TEXT = re.compile(r"^/iserv/[A-Za-z0-9_./{}-]{1,200}$")
LOOKUP_UNKNOWN_KEY = "api.mail.lookupUnknown"
IDENTITY_WORD = re.compile(r"identit|alias|sender", re.IGNORECASE)


def read_php_data(html):
    soup = BeautifulSoup(html or "", "html.parser")
    tag = soup.find("script", id=PHP_DATA)
    if tag is None:
        return False, None
    try:
        data = json.loads(tag.get_text() or "")
    except ValueError:
        return True, None
    return True, data if isinstance(data, dict) else None


def php_data(html):
    return read_php_data(html)[1]


def walk(value, trail=()):
    yield trail, value
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from walk(inner, trail + (str(key),))
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner, trail + ("[]",))


def config_paths(data):
    config = (data or {}).get(SERVER_CONFIG)
    found = []
    for trail, value in walk(config if isinstance(config, (dict, list)) else {}):
        if isinstance(value, str) and PATH_TEXT.match(value):
            found.append((".".join(trail), value))
    return found


def lookup_paths(data):
    found = []
    for trail, value in config_paths(data):
        lowered = trail.lower()
        if ("auto" in lowered or "complete" in lowered or "lookup" in lowered or "search" in lowered) and value not in found:
            found.append(value)
    return found


def page_size(data):
    user = (data or {}).get("userData")
    if not isinstance(user, dict):
        return None
    for key, value in user.items():
        if str(key).lower().startswith("list") and isinstance(value, int) and not isinstance(value, bool):
            if PAGE_SIZE_RANGE[0] <= value <= PAGE_SIZE_RANGE[1]:
                return value
    return None


def _first_text(entry, keys):
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:120]
    return ""


def tags(data):
    user = (data or {}).get("userData")
    listed = user.get("tags") if isinstance(user, dict) else None
    found = []
    for entry in listed if isinstance(listed, list) else []:
        if isinstance(entry, str):
            found.append({"id": entry, "name": entry, "color": ""})
            continue
        if not isinstance(entry, dict):
            continue
        name = _first_text(entry, ("name", "label", "title", "displayName"))
        ident = _first_text(entry, ("keyword", "imapKeyword", "flag", "id", "key")) or name
        color = _first_text(entry, ("color", "colour", "bgColor", "backgroundColor"))
        if ident:
            found.append({"id": ident, "name": name or ident, "color": color if re.match(r"^#?[0-9A-Fa-f]{3,8}$|^[a-z]{3,20}$", color) else ""})
    return found


def account_flags(data):
    flags = {}
    for trail, value in walk(data or {}):
        if not trail or not isinstance(value, bool):
            continue
        key = trail[-1]
        if key.startswith("hasActive") and re.match(r"^[A-Za-z]{1,40}$", key):
            flags[key] = value
    return flags


def auto_archive(data):
    for trail, value in walk(data or {}):
        if trail and trail[-1].lower().startswith("autoarchive") and isinstance(value, list):
            return [{"path": str(entry.get("path") or ""), "days": entry.get("days")} for entry in value if isinstance(entry, dict)]
    return []


def display_name(data):
    user = (data or {}).get("userData")
    for key in ("displayName", "displayname", "name"):
        value = user.get(key) if isinstance(user, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def sender_addresses(data):
    found = []
    for trail, value in walk(data or {}):
        if not trail or not isinstance(value, str) or trail[0] == SERVER_CONFIG:
            continue
        owned = any(IDENTITY_WORD.search(step) for step in trail)
        if owned and ADDRESS.match(value.strip()):
            address = value.strip().lower()
            if address not in found:
                found.append(address)
    return found


def account(html):
    data = php_data(html)
    if data is None:
        return None
    return {
        "page_size": page_size(data),
        "tags": tags(data),
        "flags": account_flags(data),
        "auto_archive": auto_archive(data),
        "display_name": display_name(data),
        "addresses": sender_addresses(data),
        "lookup": bool(lookup_paths(data)),
    }


def _entries(value):
    found = []
    for _trail, entry in walk(value):
        if not isinstance(entry, dict):
            continue
        address = _first_text(entry, ("email", "mail", "address", "emailAddress", "value"))
        if not ADDRESS.match(address):
            continue
        name = _first_text(entry, ("name", "label", "displayName", "displayname", "text", "title"))
        kind = _first_text(entry, ("type", "kind", "category")).lower()
        found.append({"name": name, "address": address, "group": "group" in kind or "list" in kind})
    return found


def lookup(client, paths, query, remembered=None):
    text = " ".join(str(query or "").split())[:QUERY_LIMIT]
    if len(text) < 2:
        return [], remembered
    found = []
    seen = set()
    answered = False
    for path in paths:
        params = (remembered.get(path),) if remembered and remembered.get(path) else LOOKUP_PARAMS
        for param in params:
            response = client.fetch(path, {param: text})
            if int(getattr(response, "status_code", 0) or 0) != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            answered = True
            entries = _entries(payload)
            if entries or isinstance(payload, (list, dict)):
                remembered = dict(remembered or {}, **{path: param})
            for entry in entries:
                key = entry["address"].lower()
                if key not in seen:
                    seen.add(key)
                    found.append(entry)
            if entries:
                break
    if not answered and paths:
        raise DataError("recipient lookup unknown", message_key=LOOKUP_UNKNOWN_KEY)
    return found[:LOOKUP_LIMIT], remembered


def setting_kind(path, title=""):
    text = (path + " " + title).lower()
    for kind, words in SETTING_WORDS.items():
        if any(word in text for word in words):
            return kind
    return "settings"


def _own_path(href, base):
    if not href:
        return ""
    parts = urlsplit(href)
    if parts.scheme and parts.netloc and parts.netloc != urlsplit(base).netloc:
        return ""
    path = parts.path or ""
    return path.rstrip("/") if path.startswith("/iserv/") else ""


def candidate_pages(html, base_url):
    found = []

    def keep(path, guessed=False):
        if path and PATH_TEXT.match(path) and "/api/" not in path and path != MAIL_PAGE and not any(mark in path for mark in LOGIN_MARKS):
            if path not in [entry["path"] for entry in found]:
                found.append({"path": path, "guessed": guessed})

    soup = BeautifulSoup(html or "", "html.parser")
    for anchor in soup.find_all("a", href=True):
        path = _own_path(anchor.get("href"), base_url)
        if path.startswith(MAIL_PAGE + "/") and not any(part in path for part in SKIPPED_PARTS):
            keep(path)
    data = php_data(html) or {}
    for _trail, value in walk(data):
        if isinstance(value, str) and value.startswith(MAIL_PAGE + "/"):
            keep(value.rstrip("/"))
    for path in GUESSED_PAGES:
        keep(path, True)
    return found[:PAGE_LIMIT]


def settings_page(response, path):
    final = path_of(getattr(response, "url", "") or "") or path
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return None
    if any(mark in final for mark in LOGIN_MARKS) or final.rstrip("/") == MAIL_PAGE:
        return None
    headers = getattr(response, "headers", None) or {}
    kind = str(headers.get("content-type") or headers.get("Content-Type") or "text/html").lower()
    if "html" not in kind:
        return None
    return final.rstrip("/") or path


def embedded_json(html):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for tag in soup.find_all("script"):
        kind = str(tag.get("type") or "").split(";", 1)[0].strip().lower()
        if kind not in ("application/json", "application/ld+json"):
            continue
        try:
            found.append(json.loads(tag.get_text() or ""))
        except ValueError:
            continue
    return found


def create_event_path(html):
    for data in embedded_json(html):
        for trail, value in walk(data):
            if trail and trail[-1] == CREATE_EVENT_KEY and isinstance(value, str) and PATH_TEXT.match(value):
                return value.rstrip("/")
    return ""


def calendar_routes(html):
    found = []
    for data in embedded_json(html):
        for trail, value in walk(data):
            if trail and "create" in trail[-1] and isinstance(value, str) and PATH_TEXT.match(value) and (trail[-1], value) not in found:
                found.append((trail[-1], value))
    return found


def event_form_of(forms):
    usable = [form for form in forms if form["method"] == "post" and form["fields"]]
    if not usable:
        return None
    return max(usable, key=lambda form: len(form["fields"]))


def _named(form, words, kinds):
    for word in words:
        for field in form["fields"]:
            if field["kind"] in kinds and word in field["name"].lower():
                return field["name"]
    return ""


def event_title_field(form):
    return _named(form, TITLE_WORDS, ("text",))


def event_description_field(form):
    found = _named(form, DESCRIPTION_WORDS, ("textarea",))
    if found:
        return found
    return next((field["name"] for field in form["fields"] if field["kind"] == "textarea"), "")


def _day(value):
    text = str(value or "").strip()
    iso = ISO_DAY.match(text)
    german = GERMAN_DAY.match(text)
    try:
        if iso:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        if german:
            return date(int(german.group(3)), int(german.group(2)), int(german.group(1)))
    except ValueError:
        return None
    return None


def _first(pairs, name):
    return next((str(value) for key, value in pairs if key == name), None)


def event_time(form, pairs):
    for word in TIME_WORDS:
        for field in form["fields"]:
            if word in field["name"].lower().replace("_", "") and field["kind"] in ("time", "text"):
                found = CLOCK.match(str(_first(pairs, field["name"]) or "").strip())
                if found:
                    return "%02d:%s" % (int(found.group(1)), found.group(2))
    return ""


def event_all_day(form, pairs):
    for field in form["fields"]:
        if field["kind"] == "checkbox" and any(word in field["name"].lower().replace("_", "") for word in ALL_DAY_WORDS):
            return _first(pairs, field["name"]) is not None
    return False


def event_calendar(form, pairs):
    for field in form["fields"]:
        if field["kind"] == "select" and any(word in field["name"].lower() for word in CALENDAR_WORDS):
            chosen = _first(pairs, field["name"])
            option = next((option for option in field.get("options") or [] if option["value"] == chosen), None)
            return " ".join(str(option["label"] if option else "").split())
    return ""


def event_day(form, values):
    for word in DAY_WORDS:
        for field in form["fields"]:
            if word in field["name"].lower() and field["kind"] in ("date", "text", "datetime-local"):
                found = _day(values.get(field["name"], field.get("value")))
                if found:
                    return found
    return None
