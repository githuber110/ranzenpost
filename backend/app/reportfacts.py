import json
import re
from datetime import timedelta

from bs4 import BeautifulSoup

from . import modules
from .iserv.children import child_select_present, parse_children
from .iserv.dsa import SICK_NOTE_SELECTION_PATH as dsa_selection_path
from .iserv.dsa import (
    CHILDREN_FIELDS,
    CURRENT_TIMETABLE_PATH,
    LESSON_FILTER,
    SUBSTITUTIONS_SETTING,
    TIMETABLE_SETTING,
    parse_children_from_me,
    parse_students,
)
from .iserv.dsa_substitutions import comparison_of, describe as describe_substitutions, describe_marker_fields, marker_fields
from .iserv.dsa_timetable import course_filter, query_date
from .iserv.letters import parse_letter_list
from .iserv.older_absence_form import (
    attachment_entries,
    change_log,
    create_path,
    export_path,
    parse_create_form,
    structure_text,
    upload_form,
    upload_link,
)
from .iserv.older_absences import (
    DELETE_SEGMENTS,
    EDIT_SEGMENTS,
    OlderAbsenceShapeError,
    action_paths,
    column_roles,
    list_table,
    parse_older_absences,
)
from .iserv.timetable import DATE_FORMAT, week_bounds
from .iserv.pages import status_of
from .pageshape import code_text, json_of, unique
from .pathpattern import path_pattern, placeholders
from .reportcrawl import MENU_LINK_PREFIX, SCHOOL_ACCOUNT_PATH
from .valueshape import table_cell

SICK_NOTE_SELECTION_PATH = modules.DSA_API + "/" + dsa_selection_path
TIME_TABLE_PAGE_PATH = "/iserv/time-table/"
CHILDREN_TABLE_HEAD = "| Source | Count | Duplicate ids | Duplicate names |"
CHILDREN_TABLE_RULE = "|---|---|---|---|"
CHILDREN_NOT_READ = "| %s | not read | - | - |"
SCHOOL_SETTINGS_PATH = modules.DSA_API + "/school-settings/"
CURRENT_TIMETABLE_QUERY_PATH = modules.DSA_API + "/" + CURRENT_TIMETABLE_PATH
TIMETABLE_SLOTS_PATH = modules.DSA_API + "/timetable-slots/"
KNOWN_SETTINGS = (TIMETABLE_SETTING, SUBSTITUTIONS_SETTING)
ABSENCE_SETTING_PREFIXES = ("sickNotes_", "requestToSchools_", "dayCare_")
CLOCK_VALUE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
OLDER_ABSENCE_SLUG = "absence_obsolete"
OLDER_ABSENCE_PAGE = "/iserv/absence/"
SICK_NOTES_PATH = modules.DSA_API + "/sickNotes/"
EVIDENCE_DAYS = 120
SMALL_SETTING_MAX = 100
RELEASE_OFF_LINE = "- Timetable release: off, the app reads the time-table module instead of the school app"
TIME_TABLE_PRESENT = "supported"
FALLBACK_NOTES = {
    TIME_TABLE_PRESENT: "the app reads the time-table module instead",
    "missing": "the time-table module is absent too, so no timetable is available",
}
UNCHECKED_FALLBACK = "the time-table module was not checked"
LETTER_ACTION = re.compile(r"\[actions\]\[([^\]]+)\]")
SUBMIT_TYPES = ("submit", "image")
MAX_LETTER_ACTIONS = 20
MAX_REPLY_FORM_SHAPES = 6
CONFIRMATION_NOT_COUNTED = "- Confirmation needed: not counted, the list does not show it and each letter would need its own request"
VERSION_SOURCES = (
    ("start page", MENU_LINK_PREFIX),
    ("legal page", modules.ISERV_ROOT + "/app/legal"),
)
VERSION_PLACES_LINE = "- Looked in: generator tag, footer, page text, scripts, response headers"


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
    payload = fetch_json(client, SCHOOL_ACCOUNT_PATH, {"fields": CHILDREN_FIELDS})
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


def _entry_count(entries):
    return len(entries) if isinstance(entries, list) else 0


def _entries_fact(payload):
    blocks = payload.get("students") if isinstance(payload.get("students"), list) else []
    counts = [_entry_count(block.get("entries")) for block in blocks if isinstance(block, dict)]
    return "students %d, entries per student %s" % (len(counts), ", ".join(str(count) for count in counts) or "-")


def _fallback_note(time_table):
    return FALLBACK_NOTES.get(time_table, UNCHECKED_FALLBACK)


def _child_query(client, child, account, today, substitutions, time_table=TIME_TABLE_PRESENT):
    if account is None:
        return "course ids not read, the school account did not answer", None
    listed = account.get(str(child.get("child_id") or ""))
    if listed is None:
        return "not in the school account, " + _fallback_note(time_table), None
    course_ids = listed.get("course_ids")
    if not course_ids:
        return "no course ids in the school account, " + _fallback_note(time_table), None
    try:
        selector = course_filter(course_ids)
    except (TypeError, ValueError):
        return "course ids are unreadable", None
    params = {"date": query_date(today), "week": "true", "substitutions": "true" if substitutions else "false"}
    if selector:
        params["filterBy"] = selector
    count = selector.count("|") + 1 if selector else 0
    status, payload = fetch_answer(client, CURRENT_TIMETABLE_QUERY_PATH, params)
    if not isinstance(payload, dict):
        refused = ", answer %d" % status if status and status != 200 else ""
        return "courses in filter %d, not read%s" % (count, refused), None
    return "courses in filter %d, %s" % (count, _entries_fact(payload)), (params, payload)


def _substitutions_fact(client, answered, today):
    params, payload = answered
    status, regular = fetch_answer(client, CURRENT_TIMETABLE_QUERY_PATH, dict(params, substitutions="false"))
    comparison = comparison_of(payload, regular if isinstance(regular, dict) else None, today)
    if not isinstance(regular, dict):
        comparison = comparison._replace(failure="answer %s" % (status or "-"))
    return describe_substitutions(comparison)


def _setting_fact(value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value) if 0 <= value <= SMALL_SETTING_MAX else "number"
    if isinstance(value, (list, dict)):
        return "list %d" % len(value)
    if value is None or str(value).strip() == "":
        return "empty"
    text = str(value).strip()
    return text if CLOCK_VALUE.match(text) else "text"


def absence_settings_line(settings):
    if not isinstance(settings, dict):
        return "- Absence settings: not read"
    keys = sorted(key for key in settings if str(key).startswith(ABSENCE_SETTING_PREFIXES))
    facts = ", ".join("%s=%s" % (key, _setting_fact(settings[key])) for key in keys)
    return "- Absence settings: " + (facts or "none")


def school_app_query_lines(client, config, today, time_table=TIME_TABLE_PRESENT):
    lines = ["### School app"]
    settings = _school_settings(client) if client is not None else None
    lines.append("- Settings: " + ", ".join("%s=%s" % (key, _switch(settings, key)) for key in KNOWN_SETTINGS))
    lines.append(absence_settings_line(settings))
    if isinstance(settings, dict) and settings.get(TIMETABLE_SETTING) is False:
        lines.append(RELEASE_OFF_LINE if time_table == TIME_TABLE_PRESENT else "- Timetable release: off, " + _fallback_note(time_table))
    if client is None:
        lines.append("- Timetable query: not read, no session")
        return lines
    substitutions = isinstance(settings, dict) and settings.get(SUBSTITUTIONS_SETTING) is True
    if substitutions:
        lines.append("- Timetable query: week=true, substitutions=true, one query per child, and one with substitutions=false for the regular plan")
    else:
        lines.append("- Timetable query: week=true, substitutions=false, one query per child")
    children = listed_children(config.get("children"))
    if not children:
        lines.append("- Children: none stored")
    account = _school_account_children(client) if children else None
    by_id = {child["child_id"]: child for child in account} if account is not None else None
    for number, child in enumerate(children, 1):
        fact, answered = _child_query(client, child, by_id, today, substitutions, time_table)
        lines.append("- Child %d: %s" % (number, fact))
        if substitutions and answered is not None:
            lines.append("- Child %d substitutions: %s" % (number, _substitutions_fact(client, answered, today)))
            lines.append("- Child %d school markers: %s" % (number, describe_marker_fields(marker_fields(answered[1]))))
    slots = fetch_json(client, TIMETABLE_SLOTS_PATH, {"filterBy": LESSON_FILTER})
    lines.append("- Timetable slots: %s" % (len(slots) if isinstance(slots, list) else "not read"))
    if isinstance(slots, list):
        lines.append("- Timetable slot numbers: %s" % slot_numbers_fact(slots))
    start, end = week_bounds(today)
    lines.append("- Week: %s to %s" % (start.strftime(DATE_FORMAT), end.strftime(DATE_FORMAT)))
    return lines


def _slot_number(slot):
    number = slot.get("number") if isinstance(slot, dict) else None
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def slot_numbers_fact(slots):
    numbers = [_slot_number(slot) for slot in slots]
    known = sorted({number for number in numbers if number is not None})
    without = numbers.count(None)
    if not numbers:
        return "none"
    text = ", ".join(str(number) for number in known) or "-"
    return text + ("; without a number %d" % without if without else "")


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


def letter_reply_form_lines(store):
    try:
        cache = store.load_letters_search_cache()
    except Exception:
        return ["- Reply forms in opened letters: not read"]
    shapes = {}
    for entry in (cache or {}).values() if isinstance(cache, dict) else []:
        if not isinstance(entry, dict):
            continue
        confirmation = entry.get("confirmation")
        if isinstance(confirmation, dict):
            key = (
                str(confirmation.get("type") or "-"),
                bool(confirmation.get("sendable")),
                str(confirmation.get("shape") or "shape not recorded"),
            )
            shapes[key] = shapes.get(key, 0) + 1
        if entry.get("answer_shape"):
            key = ("answer edit", False, str(entry["answer_shape"]))
            shapes[key] = shapes.get(key, 0) + 1
    if not shapes:
        return ["- Reply forms in opened letters: none"]
    lines = ["- Reply forms in opened letters: %d" % sum(shapes.values())]
    for (kind, sendable, shape), count in sorted(shapes.items())[:MAX_REPLY_FORM_SHAPES]:
        lines.append("- Reply form %s, %s, x%d: %s" % (kind, "sendable" if sendable else "not sendable", count, shape))
    return lines


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
    if not found:
        lines.append(VERSION_PLACES_LINE)
    return lines


def older_page_lines(html):
    try:
        listed = parse_older_absences(html)
    except OlderAbsenceShapeError as error:
        return ["- Older absence page: not readable, %s" % error, older_columns_line(html)], None
    line = "- Older absence page: entries %s, unreadable %s" % (_amount(len(listed.rows)), _amount(listed.unreadable))
    return [line, older_columns_line(html)], [{row.from_date, row.till_date} for row in listed.rows]


def older_columns_line(html):
    table = list_table(html)
    if table is None:
        return "- Older absence columns: no list table"
    roles = column_roles(table)
    named = [role for role, _index in sorted(roles.items(), key=lambda item: item[1])]
    return "- Older absence columns: " + (", ".join(named) or "none recognised")


def older_actions_line(html):
    table = list_table(html)
    rows = table.find_all("tr") if table is not None else []
    deletes = sum(1 for row in rows if action_paths(row, DELETE_SEGMENTS))
    edits = sum(1 for row in rows if action_paths(row, EDIT_SEGMENTS))
    return "- Older absence row actions: delete links %s, edit links %s, detail links %s, export %s" % (
        _amount(deletes), _amount(edits), _amount(len(_detail_rows(html))), "yes" if export_path(html, "") else "no",
    )


def _name_shape(name):
    return code_text(placeholders(name))


def _detail_rows(html):
    try:
        return [row for row in parse_older_absences(html).rows if row.detail_path]
    except OlderAbsenceShapeError:
        return []


def older_detail_lines(client, html):
    rows = _detail_rows(html)
    if not rows:
        return []
    paths = [rows[0].detail_path]
    try:
        answer = client.fetch(paths[0])
    except Exception:
        answer = None
    status = status_of(answer) if answer is not None else 0
    lines = ["- Older absence detail page: %s answer %d" % (path_pattern(paths[0]), status)]
    if status != 200:
        return lines
    text = getattr(answer, "text", "") or ""
    url = str(getattr(answer, "url", "") or "")
    form, field = upload_form(text, url, rows[0].entry_id)
    if form is not None:
        upload = "form %s, file field %s" % (structure_text(form, _name_shape), _name_shape(field))
    else:
        upload = "link %s" % ("yes" if upload_link(text, url, rows[0].entry_id) else "no")
    entries = attachment_entries(text, url)
    removable = sum(1 for item in entries if item.delete_link or item.delete_form)
    lines.append("- Older absence attachments: links %s, removable %s, upload %s" % (_amount(len(entries)), _amount(removable), upload))
    lines.append("- Older absence change log: rows %s" % _amount(len(change_log(text))))
    return lines


def older_form_lines(client, page, children):
    html = getattr(page, "text", "") or ""
    lines = [older_actions_line(html)]
    lines.extend(older_detail_lines(client, html))
    path = create_path(html, str(getattr(page, "url", "") or ""))
    if not path:
        lines.append("- Older absence create page: not linked")
        return lines
    try:
        answer = client.fetch(path)
    except Exception:
        answer = None
    status = status_of(answer) if answer is not None else 0
    lines.append("- Older absence create page: %s answer %d" % (path_pattern(path), status))
    if status != 200:
        return lines
    form = parse_create_form(getattr(answer, "text", "") or "", str(getattr(answer, "url", "") or ""), children)
    if form is None:
        lines.append("- Older absence form: no write form")
        return lines
    lines.append("- Older absence form: " + structure_text(form, _name_shape))
    return lines


def _sick_note_dates(notes):
    dates = []
    for note in notes:
        if not isinstance(note, dict):
            continue
        wanted = (note.get("sickFromDateAsString") or note.get("sickFromDate"), note.get("sickTillDateAsString") or note.get("sickTillDate"))
        dates.append({str(value)[:10] for value in wanted if value})
    return dates


def absence_evidence_lines(client, today, children=()):
    lines = ["### Absence lists"]
    if client is None:
        lines.append("- Not read, no session")
        return lines
    try:
        response = client.fetch(OLDER_ABSENCE_PAGE)
    except Exception:
        response = None
    status = status_of(response) if response is not None else 0
    older = None
    if status == 200:
        page_lines, older = older_page_lines(getattr(response, "text", "") or "")
        lines.extend(page_lines)
        lines.extend(older_form_lines(client, response, children))
    else:
        lines.append("- Older absence page: not read, answer %d" % status)
    since = (today - timedelta(days=EVIDENCE_DAYS)).isoformat()
    notes = fetch_json(client, SICK_NOTES_PATH, {"filterBy": "sickTillDateAsString:greaterOrEqualThan(%s)" % since})
    if not isinstance(notes, list):
        lines.append("- School app sick notes: not read")
        return lines
    school_app = _sick_note_dates(notes)
    lines.append("- School app sick notes in the last %d days: %s" % (EVIDENCE_DAYS, _amount(len(school_app))))
    dated = [dates for dates in (older or []) if dates]
    if dated:
        known = set().union(*school_app) if school_app else set()
        shared = sum(1 for dates in dated if dates & known)
        lines.append("- Older page entries sharing a date with a school app sick note: %s" % _share(shared, len(dated)))
    return lines


def _amount(count):
    return "none" if count == 0 else "some"


def _share(part, whole):
    if part == 0:
        return "none"
    return "all" if part == whole else "some"

