import json
import re

from bs4 import BeautifulSoup

from . import modules
from .iserv.children import child_select_present, parse_children
from .iserv.dsa import (
    CHILDREN_FIELDS,
    CURRENT_TIMETABLE_PATH,
    LESSON_FILTER,
    SUBSTITUTIONS_SETTING,
    TIMETABLE_SETTING,
    parse_children_from_me,
    parse_students,
)
from .iserv.dsa_timetable import course_filter, query_date
from .iserv.letters import parse_letter_list
from .iserv.timetable import DATE_FORMAT, week_bounds
from .pageshape import code_text, json_of, status_of, unique
from .pathpattern import path_pattern, placeholders
from .reportcrawl import MENU_LINK_PREFIX
from .valueshape import table_cell

SCHOOL_ACCOUNT_ME_PATH = modules.DSA_API + "/users/me"
SICK_NOTE_SELECTION_PATH = modules.DSA_API + "/sickNotes/userSelection/"
TIME_TABLE_PAGE_PATH = "/iserv/time-table/"
CHILDREN_TABLE_HEAD = "| Source | Count | Duplicate ids | Duplicate names |"
CHILDREN_TABLE_RULE = "|---|---|---|---|"
CHILDREN_NOT_READ = "| %s | not read | - | - |"
SCHOOL_SETTINGS_PATH = modules.DSA_API + "/school-settings/"
CURRENT_TIMETABLE_QUERY_PATH = modules.DSA_API + "/" + CURRENT_TIMETABLE_PATH
TIMETABLE_SLOTS_PATH = modules.DSA_API + "/timetable-slots/"
KNOWN_SETTINGS = (TIMETABLE_SETTING, SUBSTITUTIONS_SETTING)
RELEASE_OFF_LINE = "- Timetable release: off, the app reads the time-table module instead of the school app"
LETTER_ACTION = re.compile(r"\[actions\]\[([^\]]+)\]")
SUBMIT_TYPES = ("submit", "image")
MAX_LETTER_ACTIONS = 20
CONFIRMATION_NOT_COUNTED = "- Confirmation needed: not counted, the list does not show it and each letter would need its own request"
VERSION_SOURCES = (
    ("start page", MENU_LINK_PREFIX),
    ("legal page", modules.ISERV_ROOT + "/app/legal"),
)


def listed_children(children):
    return [child for child in children or () if isinstance(child, dict) and str(child.get("child_id") or "").strip()]


def _name_fold(name):
    return " ".join(str(name or "").split()).casefold()


def _duplicate_counts(entries, id_key="child_id", name_key="name"):
    ids = {}
    names = {}
    for entry in entries:
        child_id = str((entry or {}).get(id_key) or "").strip()
        if child_id:
            ids[child_id] = ids.get(child_id, 0) + 1
        name = _name_fold((entry or {}).get(name_key))
        if name:
            names[name] = names.get(name, 0) + 1
    dup_ids = sum(1 for count in ids.values() if count > 1)
    dup_names = sum(1 for count in names.values() if count > 1)
    return dup_ids, dup_names


def _children_source_line(label, entries):
    if entries is None:
        return CHILDREN_NOT_READ % table_cell(label)
    dup_ids, dup_names = _duplicate_counts(entries)
    return "| %s | %d | %d | %d |" % (table_cell(label), len(entries), dup_ids, dup_names)


def fetch_answer(client, path, params=None):
    try:
        response = client.fetch(path, params)
    except Exception:
        return 0, None
    if response is None:
        return 0, None
    status = status_of(response)
    if status != 200:
        return status, None
    try:
        return status, json_of(response)
    except (ValueError, TypeError):
        return status, None


def fetch_json(client, path, params=None):
    return fetch_answer(client, path, params)[1]


def _school_account_children(client):
    payload = fetch_json(client, SCHOOL_ACCOUNT_ME_PATH, {"fields": CHILDREN_FIELDS})
    return parse_children_from_me(payload) if isinstance(payload, dict) else None


def _school_app_children(client):
    payload = fetch_json(client, SICK_NOTE_SELECTION_PATH)
    if not isinstance(payload, list):
        return None
    return [{"child_id": str(student.get("id") or ""), "name": student.get("name")} for student in parse_students(payload)]


def _timetable_page_children(client):
    try:
        response = client.fetch(TIME_TABLE_PAGE_PATH)
    except Exception:
        return None
    if response is None or status_of(response) != 200:
        return None
    html = getattr(response, "text", "") or ""
    if not child_select_present(html):
        return None
    return [{"child_id": option.child_id, "name": option.name} for option in parse_children(html)]


def _letters_children(client):
    try:
        response = client.fetch(modules.PROBES[modules.LETTERS][0])
    except Exception:
        return None
    if response is None or status_of(response) != 200:
        return None
    letters = parse_letter_list(getattr(response, "text", "") or "", str(getattr(response, "url", "") or ""))
    names = []
    for letter in letters:
        name = " ".join(str(letter.get("child") or "").split())
        if name and name not in names:
            names.append(name)
    return [{"child_id": _name_fold(name), "name": name} for name in names]


CHILDREN_SOURCES = (
    ("School account", _school_account_children),
    ("Timetable page", _timetable_page_children),
    ("School app", _school_app_children),
    ("Letters", _letters_children),
)


def children_lines(client, config):
    stored = listed_children(config.get("children"))
    lines = ["### Children", CHILDREN_TABLE_HEAD, CHILDREN_TABLE_RULE]
    lines.append(_children_source_line("Stored", stored))
    for label, reader in CHILDREN_SOURCES:
        lines.append(_children_source_line(label, reader(client) if client is not None else None))
    return lines


def _school_settings(client):
    payload = fetch_json(client, SCHOOL_SETTINGS_PATH)
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    return payload if isinstance(payload, dict) else None


def _switch(settings, key):
    if not isinstance(settings, dict):
        return "not read"
    if key not in settings:
        return "missing"
    value = settings.get(key)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "not a boolean"


def _entries_fact(payload):
    blocks = payload.get("students") if isinstance(payload.get("students"), list) else []
    counts = [len(block.get("entries") or []) for block in blocks if isinstance(block, dict)]
    return "students %d, entries per student %s" % (len(counts), ", ".join(str(count) for count in counts) or "-")


def _child_query_fact(client, child, today, substitutions):
    course_ids = child.get("course_ids")
    if not course_ids:
        return "no course ids stored, the app reads the time-table module instead"
    try:
        selector = course_filter(course_ids)
    except (TypeError, ValueError):
        return "stored course ids are unreadable"
    params = {"date": query_date(today), "week": "true", "substitutions": "true" if substitutions else "false"}
    if selector:
        params["filterBy"] = selector
    count = selector.count("|") + 1 if selector else 0
    status, payload = fetch_answer(client, CURRENT_TIMETABLE_QUERY_PATH, params)
    if not isinstance(payload, dict):
        refused = ", answer %d" % status if status and status != 200 else ""
        return "courses in filter %d, not read%s" % (count, refused)
    return "courses in filter %d, %s" % (count, _entries_fact(payload))


def school_app_query_lines(client, config, today):
    lines = ["### School app"]
    settings = _school_settings(client) if client is not None else None
    lines.append("- Settings: " + ", ".join("%s=%s" % (key, _switch(settings, key)) for key in KNOWN_SETTINGS))
    if isinstance(settings, dict) and settings.get(TIMETABLE_SETTING) is False:
        lines.append(RELEASE_OFF_LINE)
    if client is None:
        lines.append("- Timetable query: not read, no session")
        return lines
    substitutions = isinstance(settings, dict) and settings.get(SUBSTITUTIONS_SETTING) is True
    lines.append("- Timetable query: week=true, substitutions=%s, one query per child" % ("true" if substitutions else "false"))
    children = listed_children(config.get("children"))
    if not children:
        lines.append("- Children: none stored")
    for number, child in enumerate(children, 1):
        lines.append("- Child %d: %s" % (number, _child_query_fact(client, child, today, substitutions)))
    slots = fetch_json(client, TIMETABLE_SLOTS_PATH, {"filterBy": LESSON_FILTER})
    lines.append("- Timetable slots: %s" % (len(slots) if isinstance(slots, list) else "not read"))
    start, end = week_bounds(today)
    lines.append("- Week: %s to %s" % (start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)))
    return lines


def _action_name(field):
    if field.name == "input" and str(field.get("type") or "").lower() not in SUBMIT_TYPES:
        return ""
    name = str(field.get("name") or "").strip()
    if not name:
        return ""
    match = LETTER_ACTION.search(name)
    return code_text(placeholders(match.group(1) if match else name))


def letter_actions(html):
    soup = BeautifulSoup(html or "", "html.parser")
    forms = soup.find_all("form")
    names = unique((_action_name(field) for form in forms for field in form.find_all(("button", "input"))), MAX_LETTER_ACTIONS)
    return len(forms), names


def letters_summary_lines(client):
    if client is None:
        return ["### Letters", "- Not read: no session"]
    try:
        response = client.fetch(modules.PROBES[modules.LETTERS][0])
    except Exception:
        return ["### Letters", "- Not read: request failed"]
    if response is None or status_of(response) != 200:
        return ["### Letters", "- Not read: page answered %s" % (status_of(response) if response is not None else "no answer")]
    html = getattr(response, "text", "") or ""
    letters = parse_letter_list(html, str(getattr(response, "url", "") or ""))
    unread = sum(1 for letter in letters if letter.get("unread"))
    forms, actions = letter_actions(html)
    return [
        "### Letters",
        "- Rows: %d, unread: %d" % (len(letters), unread),
        "- Forms: %d, actions: %s" % (forms, ", ".join(actions) or "none"),
        CONFIRMATION_NOT_COUNTED,
    ]


def iserv_version_lines(client):
    lines = ["### IServ version"]
    if client is None:
        lines.append("- Not read: no session")
        return lines
    found = ""
    for label, path in VERSION_SOURCES:
        try:
            response = client.fetch(path)
        except Exception:
            lines.append("- %s (%s): request failed" % (label, path_pattern(path)))
            continue
        if response is None:
            lines.append("- %s (%s): no answer" % (label, path_pattern(path)))
            continue
        status = status_of(response)
        if status != 200:
            lines.append("- %s (%s): status %d" % (label, path_pattern(path), status))
            continue
        version = modules.iserv_version(getattr(response, "text", "") or "")
        if not version:
            try:
                header_text = json.dumps(dict(getattr(response, "headers", None) or {}))
            except TypeError:
                header_text = ""
            version = modules.iserv_version(header_text)
        lines.append("- %s (%s): %s" % (label, path_pattern(path), version or "not found"))
        if version and not found:
            found = version
    lines.append("- Chosen: %s" % (found or "unknown"))
    return lines
