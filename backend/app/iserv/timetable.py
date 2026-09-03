from datetime import timedelta

from .models import Lesson, TimetableWeek

COMPARED_FIELDS = ("subject", "teacher", "room")
CANCEL_TOKENS = ("cancel", "entfall", "ausfall")
CHANGE_TOKENS = ("substitut", "vertret", "change")


def week_bounds(reference):
    monday = reference - timedelta(days=reference.weekday())
    return monday, monday + timedelta(days=6)


def build_filter(child_id, start, end):
    return {
        "startDate": start.strftime("%d.%m.%Y"),
        "endDate": end.strftime("%d.%m.%Y"),
        "classes": [],
        "teachers": [],
        "rooms": [],
        "child": child_id,
    }


def slot_key(date_value, period):
    return f"{date_value}|{period}"


def lesson_key(date_value, period, subject):
    return f"{date_value}|{period}|{subject}"


def _to_lesson(raw):
    return Lesson(
        date=raw.get("date", ""),
        day_of_week=int(raw.get("dow", 0)),
        period=int(raw.get("period", 0)),
        subject=raw.get("subject", ""),
        teacher=raw.get("teacher", ""),
        room=raw.get("room", ""),
        class_name=raw.get("class", ""),
        lesson_id=raw.get("id"),
        internal_id=raw.get("internal_id"),
    )


def _lesson_slot(lesson):
    return slot_key(lesson.date, lesson.period)


def _lesson_key(lesson):
    return lesson_key(lesson.date, lesson.period, lesson.subject)


def _raw_slot(raw):
    try:
        period = int(raw.get("period", 0))
    except (TypeError, ValueError):
        period = 0
    return slot_key(raw.get("date", ""), period)


def _kind_from_type(value):
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    if not text:
        return ""
    if any(token in text for token in CANCEL_TOKENS):
        return "cancelled"
    if any(token in text for token in CHANGE_TOKENS):
        return "changed"
    return ""


def _refinements(raw_changes):
    result = []
    for raw in raw_changes or []:
        if not isinstance(raw, dict):
            continue
        kind = _kind_from_type(raw.get("type"))
        if kind:
            subject = raw.get("subject")
            result.append((_raw_slot(raw), subject if isinstance(subject, str) else "", kind))
    return result


def _refinement_maps(raw_changes, combined):
    subjects_by_slot = {}
    for lesson in combined:
        subjects_by_slot.setdefault(_lesson_slot(lesson), set()).add(lesson.subject)
    by_lesson = {}
    by_slot = {}
    for slot, subject, kind in _refinements(raw_changes):
        if subject and subject in subjects_by_slot.get(slot, ()):
            by_lesson[f"{slot}|{subject}"] = kind
        else:
            by_slot[slot] = kind
    return by_lesson, by_slot


def _previous_values(lesson):
    if lesson is None:
        return {"subject": "", "teacher": "", "room": ""}
    return {"subject": lesson.subject, "teacher": lesson.teacher, "room": lesson.room}


def _entry(kind, fields, previous):
    return {"kind": kind, "fields": list(fields), "previous": previous}


def _pair_with_plain(combined, plain_by_slot, taken):
    partners = [None] * len(combined)
    pending = []
    for index, lesson in enumerate(combined):
        slot = _lesson_slot(lesson)
        bucket = plain_by_slot.get(slot) or []
        flags = taken.get(slot) or []
        match = None
        for position, candidate in enumerate(bucket):
            if flags[position] or candidate.subject != lesson.subject:
                continue
            flags[position] = True
            match = candidate
            break
        if match is None:
            pending.append(index)
        else:
            partners[index] = match
    for index in pending:
        slot = _lesson_slot(combined[index])
        bucket = plain_by_slot.get(slot) or []
        flags = taken.get(slot) or []
        for position, candidate in enumerate(bucket):
            if flags[position]:
                continue
            flags[position] = True
            partners[index] = candidate
            break
    return partners


def detect_changes(combined, plain, raw_changes=None):
    plain_by_slot = {}
    for lesson in plain:
        plain_by_slot.setdefault(_lesson_slot(lesson), []).append(lesson)
    taken = {slot: [False] * len(bucket) for slot, bucket in plain_by_slot.items()}
    refined_by_lesson, refined_by_slot = _refinement_maps(raw_changes, combined)
    partners = _pair_with_plain(combined, plain_by_slot, taken)

    lesson_changes = {}
    diffable = bool(plain_by_slot)
    for index, lesson in enumerate(combined):
        previous = partners[index]
        if not diffable:
            kind = ""
            fields = []
        elif previous is None:
            kind = "added"
            fields = []
        else:
            fields = [
                name
                for name in COMPARED_FIELDS
                if getattr(lesson, name) != getattr(previous, name)
            ]
            kind = "changed" if fields else ""
        key = _lesson_key(lesson)
        refined = refined_by_lesson.get(key) or refined_by_slot.get(_lesson_slot(lesson))
        if refined:
            kind = refined
        if not kind:
            continue
        values = _previous_values(previous) if kind == "changed" else _previous_values(None)
        lesson_changes[key] = _entry(kind, fields if kind == "changed" else [], values)

    combined_keys = {_lesson_key(lesson) for lesson in combined}
    cancelled = []
    seen = set()
    cursor = {}
    for lesson in plain:
        slot = _lesson_slot(lesson)
        position = cursor.get(slot, 0)
        cursor[slot] = position + 1
        if taken[slot][position]:
            continue
        key = _lesson_key(lesson)
        if key in seen:
            continue
        seen.add(key)
        cancelled.append(lesson)
        if key not in combined_keys:
            lesson_changes[key] = _entry("cancelled", [], _previous_values(None))
    return lesson_changes, cancelled


def parse_timetable(payload):
    meta = payload.get("meta", {})
    data = payload.get("data", {})
    combined = [_to_lesson(item) for item in data.get("timetable", [])]
    plain = [_to_lesson(item) for item in payload.get("plain-timetable", [])]
    changes = list(payload.get("plain-changes", []) or data.get("orphan-changes", []))
    week = TimetableWeek(
        start_date=meta.get("filter", {}).get("startDate", ""),
        end_date=meta.get("filter", {}).get("endDate", ""),
        last_updated=meta.get("last-updated"),
        combined=combined,
        plain=plain,
        changes=changes,
    )
    lesson_changes, cancelled = detect_changes(combined, plain, changes)
    week.lesson_changes = lesson_changes
    week.cancelled = cancelled
    return week
