import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import NamedTuple

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
DATE_FORMAT = "%d.%m.%Y"
SUBSTITUTED_FIELDS = (
    ("subject", "substitutionSubject"),
    ("teacher", "substitutionTeacher"),
    ("room", "substitutionRoom"),
)
PLACEHOLDER_CHARACTERS = frozenset("-+?–— ")
CHANGE_ITEMS_FORMAT = "lessons"


def week_bounds(reference):
    monday = reference - timedelta(days=reference.weekday())
    return monday, monday + timedelta(days=6)


def build_filter(child_id, start, end):
    return {
        "startDate": start.strftime(DATE_FORMAT),
        "endDate": end.strftime(DATE_FORMAT),
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


def _field(raw, key):
    value = raw.get(key)
    return "" if value is None else value


def _to_lesson(raw):
    return Lesson(
        date=raw.get("date", ""),
        day_of_week=int(raw.get("dow", 0)),
        period=int(raw.get("period", 0)),
        subject=_field(raw, "subject"),
        teacher=_field(raw, "teacher"),
        room=_field(raw, "room"),
        class_name=_field(raw, "class"),
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


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _change_periods(record):
    first = _number(record.get("periodStart")) or _number(record.get("period"))
    if first is None:
        return range(0)
    last = _number(record.get("periodEnd")) or first
    return range(first, max(first, last) + 1)


def _value(record, key):
    text = _text(record.get(key)).strip()
    return "" if set(text) <= PLACEHOLDER_CHARACTERS else text


def _classes(value):
    names = set()
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str):
            names.update(part.strip() for part in item.replace(";", ",").split(","))
    names.discard("")
    return names


def _change_cancels(record):
    if any(_kind_from_type(kind) == "cancelled" for kind in record.get("change_types") or []):
        return True
    return not any(_value(record, key) for _, key in SUBSTITUTED_FIELDS)


def _change_hits(entry, record):
    wanted = _classes(record.get("origClass"))
    teacher = _value(record, "origTeacher")
    return (
        entry.get("date") == record.get("date")
        and _number(entry.get("period")) in _change_periods(record)
        and entry.get("subject") == record.get("origSubject")
        and (not teacher or entry.get("teacher") == teacher)
        and (not wanted or bool(_classes(entry.get("class")) & wanted))
    )


def _change_targets(original, record):
    hits = [index for index, entry in enumerate(original) if isinstance(entry, dict) and _change_hits(entry, record)]
    if len(hits) > 1 and not _value(record, "origTeacher"):
        room = _value(record, "origRoom")
        hits = [index for index in hits if room and original[index].get("room") == room]
        if len(hits) > 1:
            return []
    return hits


def _teacher_withheld(record):
    if "substitutionTeacher" not in record or _value(record, "substitutionTeacher") or _change_cancels(record):
        return False
    subject = _value(record, "substitutionSubject")
    if subject and subject != _text(record.get("origSubject")).strip():
        return True
    room = _value(record, "substitutionRoom")
    return not room or room == _value(record, "origRoom")


def _substituted(entry, record):
    result = dict(entry)
    for field, key in SUBSTITUTED_FIELDS:
        value = _value(record, key)
        if value:
            result[field] = value
    if _teacher_withheld(record):
        result["teacher"] = ""
    return result


def _weekday(value):
    try:
        return datetime.strptime(str(value), DATE_FORMAT).isoweekday()
    except ValueError:
        return None


def _added_lessons(record, original, current):
    subject = _value(record, "substitutionSubject")
    weekday = _weekday(record.get("date"))
    shown = set().union(*(_classes(entry.get("class")) for entry in original if isinstance(entry, dict)))
    reached = sorted(_classes(record.get("substitutionClass")) & shown) if shown else []
    if not subject or weekday is None or (shown and not reached):
        return []
    added = []
    for period in _change_periods(record):
        if any(
            isinstance(entry, dict) and entry.get("date") == record.get("date")
            and _number(entry.get("period")) == period and entry.get("subject") == subject
            for entry in current
        ):
            continue
        added.append({
            "id": record.get("id"),
            "class": ",".join(reached),
            "teacher": _value(record, "substitutionTeacher"),
            "subject": subject,
            "room": _value(record, "substitutionRoom"),
            "dow": weekday,
            "period": period,
            "internal_id": record.get("internal_id"),
            "date": record.get("date"),
            "period_reference": None,
        })
    return added


def _apply_changes(combined, records):
    original = list(combined)
    current = list(combined)
    added = []
    applied = []
    touched = []
    for record in records:
        if not _text(record.get("origSubject")):
            lessons = _added_lessons(record, original, current + added)
            added.extend(lessons)
            if lessons:
                applied.append(record)
                touched.append((record, [], lessons))
            continue
        targets = _change_targets(original, record)
        cancels = _change_cancels(record)
        for index in targets:
            base = current[index] if current[index] is not None else original[index]
            current[index] = None if cancels else _substituted(base, record)
        if targets:
            applied.append(record)
            touched.append((record, targets, []))
    kept = [index for index, entry in enumerate(current) if entry is not None]
    position = {index: spot for spot, index in enumerate(kept)}
    extra = {id(entry): len(kept) + spot for spot, entry in enumerate(added)}
    reach = [
        {
            "record": record,
            "dropped": [original[index] for index in targets if index not in position],
            "shown": [(position[index], original[index]) for index in targets if index in position]
            + [(extra[id(entry)], None) for entry in lessons],
        }
        for record, targets, lessons in touched
    ]
    return [current[index] for index in kept] + added, applied, reach


def _changes_with_reach(payload):
    raw = payload.get("plain-changes") or []
    records = sorted(
        (record for record in raw if isinstance(record, dict)),
        key=lambda record: str(record.get("updated") or ""),
    )
    data = payload.get("data")
    combined = data.get("timetable") if isinstance(data, dict) else None
    if not records or not isinstance(combined, list):
        return payload, [], []
    try:
        timetable, applied, reach = _apply_changes(combined, records)
    except (AttributeError, TypeError, ValueError) as error:
        logger.warning("time-table changes left out, their records were not understood: %s", type(error).__name__)
        return payload, [], []
    return {**payload, "data": {**data, "timetable": timetable}}, applied, reach


def _class_list(names):
    return ", ".join(sorted(names))


def _raw_previous(entry):
    if entry is None:
        return _previous_values(None)
    return {"subject": _field(entry, "subject"), "teacher": _field(entry, "teacher"), "room": _field(entry, "room")}


def _with_note(entry, record):
    note = _text(record.get("text")).strip()
    if not note:
        return
    notes = [part for part in (entry.get("note") or "").split("\n") if part]
    if note not in notes:
        notes.append(note)
    entry["note"] = "\n".join(notes)


def _with_classes(entry, record):
    before = _classes(record.get("origClass"))
    after = _classes(record.get("substitutionClass"))
    if entry["kind"] != "changed" or not before or not after or before == after:
        return
    if "class" not in entry["fields"]:
        entry["fields"].append("class")
    entry["previous"] = dict(entry["previous"], **{"class": _class_list(before)})
    entry["classes"] = _class_list(after)


def _marked(entry, record, before, move, teacher):
    if entry:
        result = dict(entry)
    else:
        result = _entry("added" if before is None else "changed", [], _raw_previous(before))
    result["fields"] = list(result.get("fields") or [])
    if result["kind"] == "changed" and _teacher_withheld(record):
        result["fields"] = [name for name in COMPARED_FIELDS if name in result["fields"] or name == "teacher"]
        result["teacher_hidden"] = True
    if result.get("teacher_hidden") and not result["previous"].get("teacher") and not teacher:
        result["fields"] = [name for name in result["fields"] if name != "teacher"]
    _with_classes(result, record)
    _with_note(result, record)
    result.update(move)
    if result["kind"] == "changed" and not result["fields"] and not result.get("teacher_hidden"):
        result["no_details"] = True
    return result


def _identity(date_value, period, subject, teacher, room):
    return (str(date_value or ""), _number(period), subject or "", teacher or "", room or "")


def _dropped_row(rows, dropped):
    wanted = _identity(
        dropped.get("date"), dropped.get("period"), _field(dropped, "subject"), _field(dropped, "teacher"), _field(dropped, "room")
    )
    loose = wanted[:3] + ("", "")
    matchers = (
        ("cancelled", lambda lesson, previous: _identity(lesson.date, lesson.period, lesson.subject, lesson.teacher, lesson.room) == wanted),
        ("changed", lambda lesson, previous: _identity(lesson.date, lesson.period, previous.get("subject"), previous.get("teacher"), previous.get("room")) == wanted),
        ("cancelled", lambda lesson, previous: _identity(lesson.date, lesson.period, lesson.subject, "", "") == loose),
    )
    for kind, matches in matchers:
        for spot, (lesson, entry) in enumerate(rows):
            if entry and entry.get("kind") == kind and matches(lesson, entry.get("previous") or {}):
                return spot
    return None


class MoveSide(NamedTuple):
    direction: str
    subject: str
    classes: set
    teacher: str
    places: list
    codes: frozenset


def _span(places):
    periods = sorted({period for _, period in places})
    return {"date": places[0][0], "period": periods[0], "period_end": periods[-1]}


def _move_side(item, rows):
    record = item["record"]
    if item["dropped"] and not item["shown"]:
        places = [(str(entry.get("date") or ""), _number(entry.get("period"))) for entry in item["dropped"]]
        if any(period is None for _, period in places):
            return None
        return MoveSide("away", _text(record.get("origSubject")), _classes(record.get("origClass")), _value(record, "origTeacher"), places, _codes(record))
    subject = _value(record, "substitutionSubject")
    if item["shown"] and subject and subject != _text(record.get("origSubject")):
        places = [(rows[spot][0].date, rows[spot][0].period) for spot, _ in item["shown"]]
        return MoveSide("here", subject, _classes(record.get("substitutionClass")), _value(record, "substitutionTeacher"), places, _codes(record))
    return None


def change_type_texts(values):
    if not isinstance(values, list):
        return None
    return [str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else None for value in values]


def _codes(record):
    return frozenset(text.strip() for text in change_type_texts(record.get("change_types")) or [] if text and text.strip())


def _moves_together(away, here):
    return (
        away.subject == here.subject
        and (not away.codes or not here.codes or bool(away.codes & here.codes))
        and (not away.classes or not here.classes or bool(away.classes & here.classes))
        and (not away.teacher or not here.teacher or away.teacher == here.teacher)
        and not set(away.places) & set(here.places)
    )


def _moves(reach, rows):
    sides = [(number, _move_side(item, rows)) for number, item in enumerate(reach)]
    aways = [(number, side) for number, side in sides if side and side.direction == "away"]
    heres = [(number, side) for number, side in sides if side and side.direction == "here"]
    moves = {}
    for number, away in aways:
        partners = [(other, here) for other, here in heres if _moves_together(away, here)]
        if len(partners) != 1:
            continue
        partner, here = partners[0]
        if sum(1 for _, other in aways if _moves_together(other, here)) != 1:
            continue
        moves[number] = {"moved_to": _span(here.places)}
        moves[partner] = {"moved_from": _span(away.places)}
    return moves


def _overlay(rows, reach):
    rows = list(rows)
    moves = _moves(reach, rows)
    for number, item in enumerate(reach):
        record = item["record"]
        move = moves.get(number, {})
        for spot, before in item["shown"]:
            lesson, entry = rows[spot]
            rows[spot] = (lesson, _marked(entry, record, before, move, lesson.teacher))
        for dropped in item["dropped"]:
            spot = _dropped_row(rows, dropped)
            if spot is None:
                lesson = _to_lesson(dropped)
                rows.append((lesson, _marked(_cancelled_entry(), record, None, move, lesson.teacher)))
            else:
                lesson, entry = rows[spot]
                rows[spot] = (lesson, _marked(entry or _cancelled_entry(), record, None, move, lesson.teacher))
    return rows


def change_items(rows):
    return [
        {
            "date": lesson.date,
            "period": lesson.period,
            "subject": lesson.subject,
            "teacher": lesson.teacher,
            "room": lesson.room,
            "kind": entry.get("kind") or "",
            "fields": list(entry.get("fields") or []),
            "note": entry.get("note") or "",
            "moved": bool(entry.get("moved_to") or entry.get("moved_from")),
        }
        for lesson, entry in rows
        if entry
    ]


def with_time_table_changes(payload):
    changed, applied, _ = _changes_with_reach(payload)
    return changed, applied


def _effect(item):
    if item["dropped"] and not item["shown"]:
        return "cancelled"
    if item["shown"] and all(before is None for _, before in item["shown"]):
        return "added"
    return "changed"


def _record_fact(record, effect, move):
    before = _text(record.get("origSubject")).strip()
    after = _value(record, "substitutionSubject")
    classes = _classes(record.get("origClass"))
    other = _classes(record.get("substitutionClass"))
    return {
        "types": record.get("change_types"),
        "effect": effect,
        "move": move,
        "subject_changed": (before != after) if before and after else None,
        "classes_changed": bool(classes and other and classes != other),
        "text": bool(_text(record.get("text")).strip()),
    }


def change_record_facts(payload):
    changed, _, reach = _changes_with_reach(payload)
    try:
        moves = _moves(reach, parse_timetable(changed).rows)
    except (DataError, AttributeError, TypeError, ValueError):
        moves = {}
    effects = {}
    for number, item in enumerate(reach):
        move = moves.get(number, {})
        effects[id(item["record"])] = (_effect(item), "to" if "moved_to" in move else "from" if "moved_from" in move else "")
    return [
        _record_fact(record, *effects.get(id(record), ("none", "")))
        for record in payload.get("plain-changes") or []
        if isinstance(record, dict)
    ]


def changes_format(week):
    return CHANGE_ITEMS_FORMAT if week.change_items is not None else ""


def shown_changes(week):
    return week.changes if week.change_items is None else week.change_items


def parse_time_table(payload):
    if not isinstance(payload, dict):
        raise time_table_shape_error("the time-table answer was not an object", payload)
    try:
        changed, _, reach = _changes_with_reach(payload)
        week = parse_timetable(changed)
        week.rows = _overlay(week.rows, reach)
        week.change_items = change_items(week.rows)
        return week
    except DataError as error:
        raise time_table_shape_error(str(error), payload) from error
    except (AttributeError, TypeError, ValueError) as error:
        raise time_table_shape_error("the time-table entries were not understood", payload) from error
