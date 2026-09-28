from dataclasses import replace
from datetime import date, datetime
from typing import NamedTuple

from .dsa_timetable import entry_lessons, parse_vacations
from .timetable import (
    CANCEL_TOKENS,
    DATE_FORMAT,
    change_items,
    compare_plans,
    row_changes,
    week_bounds,
    with_markers,
    with_moves,
)

NOT_ASKED = "not asked"
COMPARED = "compared"
REGULAR_UNREAD = "regular plan not read"
REGULAR_EMPTY = "regular plan empty"
TOO_DIFFERENT = "more than half differ"
NOT_UNDERSTOOD = "not understood"
UNDERSTOOD_ERRORS = (AttributeError, KeyError, TypeError, ValueError)
SUBSTITUTION_TOKENS = ("substitut", "vertret")
OUTCOME_TEXTS = {
    NOT_ASKED: "no comparison, the school does not release substitutions",
    COMPARED: "marks shown",
    REGULAR_UNREAD: "marks left out, the regular plan was not read",
    REGULAR_EMPTY: "marks left out, the regular plan is empty",
    TOO_DIFFERENT: "marks left out, more than half of the lessons differ",
    NOT_UNDERSTOOD: "marks left out, the answers were not understood",
}


class Comparison(NamedTuple):
    outcome: str
    regular: object
    current: int
    changed: int = 0
    only_regular: int = 0
    only_current: int = 0
    marked: int = 0
    markers_used: bool = False
    failure: str = ""


def _blank(value):
    return value is None or value is False or value == "" or value == 0 or value == [] or value == {}


def _token_kind(text):
    lowered = str(text or "").lower()
    if any(token in lowered for token in CANCEL_TOKENS):
        return "cancelled"
    if any(token in lowered for token in SUBSTITUTION_TOKENS):
        return "changed"
    return ""


def entry_marker(entry):
    kinds = set()
    for key, value in entry.items():
        if _blank(value):
            continue
        kind = _token_kind(key)
        if kind and isinstance(value, str) and _token_kind(value) == "cancelled":
            kind = "cancelled"
        if kind:
            kinds.add(kind)
    if "cancelled" in kinds:
        return "cancelled"
    return "changed" if kinds else ""


def course_identity(lesson, entry):
    course_subject = entry.get("courseSubject")
    course_subject_id = course_subject.get("id") if isinstance(course_subject, dict) else None
    if course_subject_id is not None:
        return ("course", course_subject_id)
    return ("lesson", lesson.subject, lesson.class_name)


def _pairing_rules(identities):
    def same_entry(lesson, candidate):
        return lesson.lesson_id is not None and lesson.lesson_id == candidate.lesson_id

    def same_course(lesson, candidate):
        mine = identities.get(id(lesson))
        return bool(mine) and mine[0] == "course" and mine == identities.get(id(candidate))

    return (same_entry, same_course)


def _kinds(rows):
    counts = {}
    for _, entry in rows:
        kind = (entry or {}).get("kind")
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def _day(text):
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def holiday_spans(*payloads):
    spans = []
    for payload in payloads:
        items = payload.get("vacations") if isinstance(payload, dict) else None
        for vacation in parse_vacations(items if isinstance(items, list) else None):
            first, last = _day(vacation["start_date"]), _day(vacation["end_date"])
            if first is not None and last is not None and first <= last:
                spans.append((first, last))
    return spans


def _on_holiday(lesson, spans):
    if not spans:
        return False
    day = datetime.strptime(lesson.date, DATE_FORMAT).date()
    return any(first <= day <= last for first, last in spans)


def _with_holidays(lessons, compared, rows):
    compared_rows = iter(rows[: len(compared)])
    kept = {id(lesson) for lesson in compared}
    merged = [next(compared_rows) if id(lesson) in kept else (lesson, None) for lesson in lessons]
    return merged + rows[len(compared):]


def _teacher_slot(lesson):
    return lesson.date, lesson.period, tuple(sorted(lesson.teacher.split(", ")))


def _in_current_order(lesson, orders):
    teacher = orders.get(_teacher_slot(lesson), lesson.teacher)
    return lesson if teacher == lesson.teacher else replace(lesson, teacher=teacher)


def _compared(lessons, identities, regular, monday, spans):
    if regular is NOT_ASKED:
        return Comparison(NOT_ASKED, None, len(lessons)), None, lessons
    if not isinstance(regular, dict):
        return Comparison(REGULAR_UNREAD, None, len(lessons)), None, lessons
    spans = spans + holiday_spans(regular)
    compared = [lesson for lesson in lessons if not _on_holiday(lesson, spans)]
    orders = {}
    for lesson in compared:
        orders.setdefault(_teacher_slot(lesson), lesson.teacher)
    plain = []
    for lesson, entry in entry_lessons(regular, monday):
        if _on_holiday(lesson, spans):
            continue
        lesson = _in_current_order(lesson, orders)
        identities[id(lesson)] = course_identity(lesson, entry)
        plain.append(lesson)
    if not plain and compared:
        return Comparison(REGULAR_EMPTY, 0, len(lessons), only_current=len(compared)), None, lessons
    _, cancelled, rows = compare_plans(compared, plain, _pairing_rules(identities))
    counts = _kinds(rows[: len(compared)])
    comparison = Comparison(
        COMPARED,
        len(plain),
        len(lessons),
        changed=counts.get("changed", 0),
        only_regular=len(cancelled),
        only_current=counts.get("added", 0),
    )
    differing = comparison.changed + comparison.only_regular + comparison.only_current
    if differing * 2 > max(len(plain), len(compared)):
        return comparison._replace(outcome=TOO_DIFFERENT), None, lessons
    rows = with_moves(rows, lambda lesson: identities.get(id(lesson)))
    return comparison, _with_holidays(lessons, compared, rows), plain


def compare(payload, regular, reference):
    monday, _ = week_bounds(reference)
    current = entry_lessons(payload, monday)
    lessons = [lesson for lesson, _ in current]
    identities = {id(lesson): course_identity(lesson, entry) for lesson, entry in current}
    markers = {} if regular is NOT_ASKED else {id(lesson): entry_marker(entry) for lesson, entry in current}
    comparison, rows, plain = _compared(lessons, identities, regular, monday, holiday_spans(payload))
    marked = sum(1 for kind in markers.values() if kind)
    used = bool(marked) and marked * 2 <= len(lessons)
    comparison = comparison._replace(marked=marked, markers_used=used)
    if rows is None and not used:
        return comparison, None
    rows = rows if rows is not None else [(lesson, None) for lesson in lessons]
    if used:
        rows = with_markers(rows, lambda lesson: markers.get(id(lesson), ""))
    return comparison, (lessons, plain, rows)


def comparison_of(payload, regular, reference):
    try:
        return compare(payload, regular, reference)[0]
    except UNDERSTOOD_ERRORS as error:
        return Comparison(NOT_UNDERSTOOD, None, 0, failure=type(error).__name__)


def mark(week, payload, regular, reference, failure=""):
    try:
        comparison, marked = compare(payload, regular, reference)
    except UNDERSTOOD_ERRORS as error:
        return Comparison(NOT_UNDERSTOOD, None, len(week.combined), failure=type(error).__name__)
    comparison = comparison._replace(failure=failure)
    if marked is None:
        return comparison
    lessons, plain, rows = marked
    shown = {id(lesson) for lesson in lessons}
    week.combined = lessons
    week.plain = plain
    week.rows = rows
    week.lesson_changes = row_changes(rows, lessons, plain)
    week.cancelled = [lesson for lesson, entry in rows if id(lesson) not in shown and (entry or {}).get("kind") == "cancelled"]
    week.change_items = change_items(rows)
    return comparison


def describe(comparison):
    if comparison.outcome == NOT_ASKED:
        regular = "not asked"
    else:
        regular = "not read" if comparison.regular is None else "%d lessons" % comparison.regular
    text = "regular plan %s, current %d, changed %d, only in the regular plan %d, only in the current plan %d, marked by the school %d, %s" % (
        regular,
        comparison.current,
        comparison.changed,
        comparison.only_regular,
        comparison.only_current,
        comparison.marked,
        OUTCOME_TEXTS.get(comparison.outcome, comparison.outcome),
    )
    if comparison.marked and not comparison.markers_used:
        text += ", school marks left out, more than half of the lessons are marked"
    if comparison.failure:
        text += " (%s)" % comparison.failure
    return text
