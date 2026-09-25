import json
import logging
from dataclasses import replace
from datetime import timedelta

from ..valueshape import shape_lines
from .errors import DataError
from .models import Lesson, TimetableWeek

logger = logging.getLogger(__name__)

TIMETABLE_SHAPE_KEY = "api.timetable.unreadable"
TIME_TABLE_SOURCE = "time-table"
SHAPE_DIAGNOSIS_LINES = 40

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


def data_params(child_id, reference):
    start, end = week_bounds(reference)
    week_filter = build_filter(child_id, start, end)
    if not child_id:
        week_filter.pop("child")
    params = {"filter": json.dumps(week_filter, separators=(",", ":"))}
    if child_id:
        params["childId"] = child_id
    return params


def slot_key(date_value, period):
    return f"{date_value}|{period}"


def lesson_key(date_value, period, subject, teacher=None):
    base = f"{date_value}|{period}|{subject}"
    return base if teacher is None else f"{base}|{teacher}"


def crowded_keys(*groups):
    crowded = set()
    for lessons in groups:
        counts = {}
        rooms = {}
        for lesson in lessons:
            base = lesson_key(lesson.date, lesson.period, lesson.subject)
            counts[base] = counts.get(base, 0) + 1
            taught = lesson_key(lesson.date, lesson.period, lesson.subject, lesson.teacher)
            rooms.setdefault(taught, set()).add(lesson.room)
        crowded.update(base for base, count in counts.items() if count > 1)
        crowded.update(taught for taught, seen in rooms.items() if len(seen) > 1)
    return crowded


def change_key(lesson, crowded):
    base = lesson_key(lesson.date, lesson.period, lesson.subject)
    if base not in crowded:
        return base
    taught = lesson_key(lesson.date, lesson.period, lesson.subject, lesson.teacher)
    return f"{taught}|{lesson.room}" if taught in crowded else taught


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


def _text(value):
    return value if isinstance(value, str) else ""


def _refinements(raw_changes):
    result = []
    for raw in raw_changes or []:
        if not isinstance(raw, dict):
            continue
        kind = _kind_from_type(raw.get("type"))
        if kind:
            result.append((_raw_slot(raw), _text(raw.get("subject")), _text(raw.get("teacher")), _text(raw.get("room")), kind))
    return result


def _refinement_targets(indices, combined, teacher, room, crowded):
    exact = [index for index in indices if teacher and combined[index].teacher == teacher]
    if len(exact) > 1 and room:
        exact = [index for index in exact if combined[index].room == room] or exact
    if exact:
        return exact
    first = combined[indices[0]]
    if teacher and lesson_key(first.date, first.period, first.subject) in crowded:
        return []
    return indices


def _refinement_maps(raw_changes, combined, crowded):
    by_subject = {}
    for index, lesson in enumerate(combined):
        by_subject.setdefault((_lesson_slot(lesson), lesson.subject), []).append(index)
    by_index = {}
    by_slot = {}
    for slot, subject, teacher, room, kind in _refinements(raw_changes):
        candidates = by_subject.get((slot, subject)) if subject else None
        if not candidates:
            by_slot[slot] = kind
            continue
        for index in _refinement_targets(candidates, combined, teacher, room, crowded):
            by_index[index] = kind
    return by_index, by_slot


def _previous_values(lesson):
    if lesson is None:
        return {"subject": "", "teacher": "", "room": ""}
    return {"subject": lesson.subject, "teacher": lesson.teacher, "room": lesson.room}


def _entry(kind, fields, previous):
    return {"kind": kind, "fields": list(fields), "previous": previous}


def _cancelled_entry():
    return _entry("cancelled", [], _previous_values(None))


PAIRING_RULES = (
    lambda lesson, candidate: candidate.subject == lesson.subject
    and candidate.teacher == lesson.teacher
    and candidate.room == lesson.room,
    lambda lesson, candidate: candidate.subject == lesson.subject and candidate.teacher == lesson.teacher,
    lambda lesson, candidate: candidate.subject == lesson.subject and candidate.room == lesson.room,
    lambda lesson, candidate: candidate.subject == lesson.subject,
    lambda lesson, candidate: True,
)


def _take_partner(lesson, bucket, flags, rule):
    for position, candidate in enumerate(bucket):
        if flags[position] or not rule(lesson, candidate):
            continue
        flags[position] = True
        return candidate
    return None


def _pair_with_plain(combined, plain_by_slot, taken):
    partners = [None] * len(combined)
    pending = list(range(len(combined)))
    for rule in PAIRING_RULES:
        unmatched = []
        for index in pending:
            slot = _lesson_slot(combined[index])
            match = _take_partner(combined[index], plain_by_slot.get(slot) or [], taken.get(slot) or [], rule)
            if match is None:
                unmatched.append(index)
            else:
                partners[index] = match
        pending = unmatched
    return partners


def _differing(lesson, previous):
    return [name for name in COMPARED_FIELDS if getattr(lesson, name) != getattr(previous, name)]


def _combined_entries(combined, partners, diffable, refined_by_index, refined_by_slot):
    entries = []
    unexplained = {}
    for index, lesson in enumerate(combined):
        previous = partners[index]
        if not diffable:
            kind, fields = "", []
        elif previous is None:
            kind, fields = "added", []
        else:
            fields = _differing(lesson, previous)
            kind = "changed" if fields else ""
        refined = refined_by_index.get(index)
        if previous is not None and not kind and refined == "changed":
            unexplained.setdefault((_lesson_slot(lesson), lesson.subject), index)
        refined = refined or refined_by_slot.get(_lesson_slot(lesson))
        if refined:
            kind = refined
        if not kind:
            entries.append(None)
            continue
        values = _previous_values(previous) if kind == "changed" else _previous_values(None)
        entries.append(_entry(kind, fields if kind == "changed" else [], values))
    return entries, unexplained


def _orphans(plain, taken):
    orphans = []
    seen = set()
    cursor = {}
    for lesson in plain:
        slot = _lesson_slot(lesson)
        position = cursor.get(slot, 0)
        cursor[slot] = position + 1
        if taken[slot][position]:
            continue
        identity = (slot, lesson.subject, lesson.teacher, lesson.room)
        if identity in seen:
            continue
        seen.add(identity)
        orphans.append(lesson)
    return orphans


def _absorb(orphans, combined, entries, unexplained):
    merged = []
    cancelled = []
    for lesson in orphans:
        index = unexplained.get((_lesson_slot(lesson), lesson.subject))
        if index is None:
            cancelled.append(lesson)
            continue
        host = combined[index]
        entries[index] = None
        shown = replace(host, class_name=lesson.class_name, lesson_id=lesson.lesson_id, internal_id=lesson.internal_id)
        merged.append((lesson, shown, _entry("changed", _differing(host, lesson), _previous_values(lesson))))
    return merged, cancelled


def _analyse(combined, plain, raw_changes):
    plain_by_slot = {}
    for lesson in plain:
        plain_by_slot.setdefault(_lesson_slot(lesson), []).append(lesson)
    taken = {slot: [False] * len(bucket) for slot, bucket in plain_by_slot.items()}
    crowded = crowded_keys(combined, plain)
    refined_by_index, refined_by_slot = _refinement_maps(raw_changes, combined, crowded)
    partners = _pair_with_plain(combined, plain_by_slot, taken)
    entries, unexplained = _combined_entries(combined, partners, bool(plain_by_slot), refined_by_index, refined_by_slot)
    merged, cancelled = _absorb(_orphans(plain, taken), combined, entries, unexplained)

    lesson_changes = {}
    for lesson, entry in zip(combined, entries):
        if entry:
            lesson_changes[change_key(lesson, crowded)] = entry
    combined_keys = {change_key(lesson, crowded) for lesson in combined}
    for lesson, _, entry in merged:
        key = change_key(lesson, crowded)
        if key not in combined_keys:
            lesson_changes[key] = entry
    for lesson in cancelled:
        key = change_key(lesson, crowded)
        if key not in combined_keys:
            lesson_changes[key] = _cancelled_entry()

    rows = list(zip(combined, entries))
    rows.extend((shown, entry) for _, shown, entry in merged)
    rows.extend((lesson, _cancelled_entry()) for lesson in cancelled)
    return lesson_changes, cancelled, rows


def detect_changes(combined, plain, raw_changes=None):
    lesson_changes, cancelled, _ = _analyse(combined, plain, raw_changes)
    return lesson_changes, cancelled


def display_rows(week):
    rows = getattr(week, "rows", None)
    if rows is not None:
        return rows
    lesson_changes = getattr(week, "lesson_changes", None) or {}
    crowded = crowded_keys(week.combined, week.plain)
    result = [(lesson, lesson_changes.get(change_key(lesson, crowded))) for lesson in week.combined]
    for lesson in getattr(week, "cancelled", None) or []:
        change = dict(lesson_changes.get(change_key(lesson, crowded)) or {})
        change["kind"] = "cancelled"
        result.append((lesson, change))
    return result


def parse_timetable(payload):
    meta = payload.get("meta")
    data = payload.get("data")
    combined_raw = data.get("timetable") if isinstance(data, dict) else None
    plain_raw = payload.get("plain-timetable") or []
    if meta is None or data is None or combined_raw is None:
        logger.warning(
            "timetable payload shape not understood (meta=%s data=%s timetable=%s)",
            meta is not None, data is not None, combined_raw is not None,
        )
        raise DataError(
            "the timetable payload shape was not understood",
            message_key=TIMETABLE_SHAPE_KEY,
            detail={"source": "json-api"},
        )
    combined = [_to_lesson(item) for item in combined_raw]
    plain = [_to_lesson(item) for item in plain_raw]
    changes = list(payload.get("plain-changes", []) or data.get("orphan-changes", []))
    week = TimetableWeek(
        start_date=meta.get("filter", {}).get("startDate", ""),
        end_date=meta.get("filter", {}).get("endDate", ""),
        last_updated=meta.get("last-updated"),
        combined=combined,
        plain=plain,
        changes=changes,
    )
    lesson_changes, cancelled, rows = _analyse(combined, plain, changes)
    week.lesson_changes = lesson_changes
    week.cancelled = cancelled
    week.rows = rows
    return week


def time_table_shape_error(note, payload):
    return DataError(
        note,
        message_key=TIMETABLE_SHAPE_KEY,
        detail={"source": TIME_TABLE_SOURCE, "shape": shape_lines(payload)[:SHAPE_DIAGNOSIS_LINES]},
    )


def parse_time_table(payload):
    if not isinstance(payload, dict):
        raise time_table_shape_error("the time-table answer was not an object", payload)
    try:
        return parse_timetable(payload)
    except DataError as error:
        raise time_table_shape_error(str(error), payload) from error
    except (AttributeError, TypeError, ValueError) as error:
        raise time_table_shape_error("the time-table entries were not understood", payload) from error
