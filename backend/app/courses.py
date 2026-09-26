import hashlib
import json
import re

from .iserv.timetable import CHANGE_ITEMS_FORMAT

CONFIRMED_EMPTY_KEY = "confirmed_empty"
FILTERS_KEY = "course_filters"
KEY_SEPARATOR = "|"
PARALLEL_MIN = 2
MAX_KEYS = 400
MAX_KEY_LENGTH = 200
STEM_PATTERN = re.compile(r"[\s\-_.]*\d+$")


def course_key(subject, teacher):
    return f"{subject or ''}{KEY_SEPARATOR}{teacher or ''}"


def split_course_key(key):
    subject, _, teacher = str(key or "").rpartition(KEY_SEPARATOR)
    return subject, teacher


def regular_course_key(lesson, change=None):
    change = change or {}
    previous = (change.get("previous") or {}) if change.get("kind") == "changed" else {}
    subject = previous.get("subject") or lesson.subject
    teacher = previous.get("teacher") or lesson.teacher
    return course_key(subject, teacher)


def _clean_keys(value):
    if not isinstance(value, (list, tuple)):
        return None
    keys = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or len(text) > MAX_KEY_LENGTH or KEY_SEPARATOR not in text or text in keys:
            continue
        keys.append(text)
    return keys[:MAX_KEYS]


def normalize_filter(value):
    if not isinstance(value, dict):
        return None
    chosen = _clean_keys(value.get("chosen"))
    known = _clean_keys(value.get("known"))
    if chosen is None or known is None:
        return None
    known = sorted(set(known) | set(chosen))
    cleaned = {"chosen": sorted(set(chosen)), "known": known}
    if not chosen and known:
        if value.get(CONFIRMED_EMPTY_KEY) is not True:
            return None
        cleaned[CONFIRMED_EMPTY_KEY] = True
    return cleaned


def filters_of(config):
    value = (config or {}).get(FILTERS_KEY)
    return value if isinstance(value, dict) else {}


def filter_of(config, child_id):
    return normalize_filter(filters_of(config).get(str(child_id or "")))


def with_filter(config, child_id, value):
    filters = dict(filters_of(config))
    cleaned = normalize_filter(value)
    if cleaned is None:
        filters.pop(str(child_id), None)
    else:
        filters[str(child_id)] = cleaned
    merged = dict(config)
    merged[FILTERS_KEY] = filters
    return merged


def moved_filter(config, old_id, new_id):
    filters = filters_of(config)
    if str(old_id) not in filters or str(new_id) in filters:
        return None
    moved = dict(filters)
    moved[str(new_id)] = moved.pop(str(old_id))
    merged = dict(config)
    merged[FILTERS_KEY] = moved
    return merged


def _slot(lesson):
    return (str(lesson.get("date") or ""), str(lesson.get("day_of_week") or ""), str(lesson.get("period") or ""))


def parallel_keys(lessons):
    by_slot = {}
    for lesson in lessons or []:
        if lesson.get("course_key"):
            by_slot.setdefault(_slot(lesson), set()).add(lesson["course_key"])
    keys = set()
    for bucket in by_slot.values():
        if len(bucket) >= PARALLEL_MIN:
            keys.update(bucket)
    return keys


def shows(lesson, active):
    if active is None:
        return True
    key = lesson.get("course_key") or ""
    return not key or key in active["chosen"] or key not in active["known"]


def signature(active):
    if active is None:
        return ""
    blob = json.dumps(active, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _period(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _change_slot(entry):
    return (str(entry.get("date") or ""), _period(entry.get("period")), str(entry.get("subject") or ""))


def _lesson_change_slot(lesson):
    return (str(lesson.get("date") or ""), _period(lesson.get("period")), str(lesson.get("subject_key") or ""))


def _identities(lesson):
    slot = _lesson_change_slot(lesson)
    _, regular = split_course_key(lesson.get("course_key"))
    previous = lesson.get("previous") if isinstance(lesson.get("previous"), dict) else {}
    teachers = {str(lesson.get("teacher_code") or ""), regular} - {""}
    rooms = {str(lesson.get("room") or ""), str(previous.get("room") or "")} - {""}
    found = {slot}
    for teacher in teachers:
        found.add(slot + (teacher,))
        found.update(slot + (teacher, room) for room in rooms)
    return found


def _index(lessons):
    found = set()
    for lesson in lessons:
        found |= _identities(lesson)
    return found


def _hides(entry, hidden_index, visible_index):
    slot = _change_slot(entry)
    teacher = str(entry.get("teacher") or "")
    room = str(entry.get("room") or "")
    probes = ([slot + (teacher, room)] if teacher and room else []) + ([slot + (teacher,)] if teacher else []) + [slot]
    for probe in probes:
        in_hidden = probe in hidden_index
        in_visible = probe in visible_index
        if in_hidden or in_visible:
            return in_hidden and not in_visible
    return False


def visible_changes(changes, visible, hidden):
    if not hidden:
        return list(changes or [])
    hidden_index = _index(hidden)
    visible_index = _index(visible)
    return [
        entry
        for entry in changes or []
        if not (isinstance(entry, dict) and _hides(entry, hidden_index, visible_index))
    ]


def _changes_of_visible_lessons(payload, lessons, visible):
    changes = list(payload.get("changes") or [])
    marked = [lesson for lesson in lessons if lesson.get("change_kind")]
    if len(marked) != len(changes):
        return None
    shown = {id(lesson) for lesson in visible}
    return [change for lesson, change in zip(marked, changes) if id(lesson) in shown]


def apply(payload, active):
    lessons = list(payload.get("lessons") or [])
    parallel = parallel_keys(lessons)
    visible = [lesson for lesson in lessons if shows(lesson, active)]
    hidden = [lesson for lesson in lessons if not shows(lesson, active)]
    known = set(active["known"]) if active else set()
    filtered = dict(payload)
    filtered["lessons"] = visible
    by_lesson = _changes_of_visible_lessons(payload, lessons, visible) if payload.get("changes_format") == CHANGE_ITEMS_FORMAT else None
    filtered["changes"] = visible_changes(payload.get("changes"), visible, hidden) if by_lesson is None else by_lesson
    filtered["change_count"] = sum(1 for lesson in visible if lesson.get("change_kind"))
    filtered["courses"] = {
        "parallel": len(parallel),
        "chosen": active is not None,
        "hidden": len(hidden),
        "new": len(parallel - known) if active is not None else 0,
        "signature": signature(active),
    }
    return filtered


def stem(code):
    text = str(code or "").strip()
    return STEM_PATTERN.sub("", text) or text


def _entry(key, lesson, config):
    subject, teacher = split_course_key(key)
    subjects = (config or {}).get("subjects") or {}
    teachers = (config or {}).get("teachers") or {}
    mapped_subject = subjects.get(subject) if isinstance(subjects.get(subject), dict) else {}
    mapped_teacher = teachers.get(teacher) if isinstance(teachers.get(teacher), dict) else {}
    code = mapped_subject.get("code") or subject
    label = mapped_subject.get("label") or ""
    named = label if label not in (subject, code) else ""
    return {
        "key": key,
        "subject_key": subject,
        "subject_code": code,
        "subject_label": label or code,
        "group": named or stem(code),
        "color": (lesson or {}).get("color") or mapped_subject.get("color") or "",
        "teacher_code": teacher,
        "teacher_label": mapped_teacher.get("label") or teacher,
        "rooms": [],
        "count": 0,
    }


def catalogue(lessons, active, config):
    parallel = parallel_keys(lessons)
    known = set(active["known"]) if active else set()
    chosen = set(active["chosen"]) if active else set()
    entries = {}
    for lesson in lessons or []:
        key = lesson.get("course_key") or ""
        if key not in parallel and key not in known:
            continue
        entry = entries.get(key)
        if entry is None:
            entry = entries[key] = _entry(key, lesson, config)
        entry["count"] += 1
        if entry["teacher_label"] == entry["teacher_code"] and lesson.get("teacher_code") == entry["teacher_code"]:
            entry["teacher_label"] = lesson.get("teacher_label") or entry["teacher_label"]
        room = str(lesson.get("room") or "")
        if room and room not in entry["rooms"]:
            entry["rooms"].append(room)
    for key in known:
        if key not in entries:
            entries[key] = _entry(key, None, config)
    listed = []
    for key, entry in entries.items():
        entry["new"] = active is not None and key not in known
        entry["chosen"] = active is None or key in chosen or entry["new"]
        listed.append(entry)
    listed.sort(key=lambda entry: (entry["group"].casefold(), entry["subject_code"].casefold(), entry["teacher_label"].casefold()))
    return {"courses": listed, "chosen": active is not None}
