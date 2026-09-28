from datetime import date

import pytest

from app.iserv.dsa_substitutions import (
    COMPARED,
    NOT_ASKED,
    NOT_UNDERSTOOD,
    REGULAR_EMPTY,
    REGULAR_UNREAD,
    TOO_DIFFERENT,
    compare,
    describe,
    entry_marker,
    mark,
)
from app.iserv.dsa_timetable import parse_current_timetable
from app.iserv.timetable import display_rows, shown_changes
from tests.time_table_school import SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED, school_app_plan, school_app_plan_entry

WEDNESDAY = date(2026, 9, 9)


def answer(rows, extra=None):
    entries = school_app_plan(rows)
    for entry in entries:
        entry.update((extra or {}).get(entry["id"], {}))
    return {"vacations": [], "schoolEvents": [], "students": [{"student": {"id": 1}, "entries": entries}]}


def marked_week(current, regular):
    week = parse_current_timetable(current, WEDNESDAY)
    comparison = mark(week, current, regular, WEDNESDAY)
    return week, comparison


def kinds(week):
    return {(lesson.date, lesson.period, lesson.subject): (entry or {}).get("kind", "") for lesson, entry in display_rows(week)}


def row_of(week, day, period, subject):
    return next(entry for lesson, entry in display_rows(week) if (lesson.date, lesson.period, lesson.subject) == (day, period, subject))


def replaced(rows, entry_id, **changes):
    fields = ("entry_id", "weekday", "period", "subject", "teacher", "room", "course_subject")
    result = []
    for row in rows:
        if row[0] == entry_id:
            values = dict(zip(fields, row), **changes)
            row = tuple(values[name] for name in fields)
        result.append(row)
    return tuple(result)


def test_a_substitute_teacher_is_marked_with_the_regular_teacher_as_before():
    current = replaced(SCHOOL_APP_REGULAR, 92003, teacher="VER")
    week, comparison = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    entry = row_of(week, "07.09.2026", 3, "E")
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["teacher"]
    assert entry["previous"] == {"subject": "E", "teacher": "WOL", "room": "R204"}
    assert (comparison.outcome, comparison.regular, comparison.current, comparison.changed) == (COMPARED, 10, 10, 1)
    assert sum(1 for kind in kinds(week).values() if kind) == 1


def test_a_lesson_only_in_the_regular_plan_is_shown_as_cancelled():
    current = tuple(row for row in SCHOOL_APP_REGULAR if row[0] != 92005)
    week, comparison = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    assert kinds(week)[("08.09.2026", 2, "SP")] == "cancelled"
    assert [(lesson.date, lesson.period, lesson.subject) for lesson in week.cancelled] == [("08.09.2026", 2, "SP")]
    assert "08.09.2026|2|SP" in week.lesson_changes
    assert comparison.only_regular == 1 and comparison.only_current == 0


def test_a_course_that_leaves_one_slot_and_appears_in_another_is_marked_as_moved():
    week, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), answer(SCHOOL_APP_REGULAR))
    away = row_of(week, "09.09.2026", 2, "KU")
    here = row_of(week, "11.09.2026", 3, "KU")
    assert away["kind"] == "cancelled"
    assert away["moved_to"] == {"date": "11.09.2026", "period": 3, "period_end": 3}
    assert here["kind"] == "added"
    assert here["moved_from"] == {"date": "09.09.2026", "period": 2, "period_end": 2}
    assert [item["moved"] for item in shown_changes(week) if item["subject"] == "KU"] == [True, True]
    assert (comparison.changed, comparison.only_regular, comparison.only_current) == (1, 2, 1)


def test_an_extra_lesson_of_a_course_without_a_gap_is_added_not_moved():
    current = SCHOOL_APP_REGULAR + ((92011, 4, 4, "INF", "NEU", "R301", 82009),)
    week, comparison = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    entry = row_of(week, "11.09.2026", 4, "INF")
    assert entry["kind"] == "added"
    assert "moved_from" not in entry
    assert comparison.only_current == 1


def test_a_double_lesson_moved_to_another_day_keeps_its_span():
    regular = SCHOOL_APP_REGULAR + ((93010, 0, 4, "CH", "NEU", "R5", 83010), (93011, 0, 5, "CH", "NEU", "R5", 83010))
    current = SCHOOL_APP_REGULAR + ((93010, 3, 4, "CH", "NEU", "R5", 83010), (93011, 3, 5, "CH", "NEU", "R5", 83010))
    week, _ = marked_week(answer(current), answer(regular))
    for period in (4, 5):
        assert row_of(week, "07.09.2026", period, "CH")["moved_to"] == {"date": "10.09.2026", "period": 4, "period_end": 5}
        assert row_of(week, "10.09.2026", period, "CH")["moved_from"] == {"date": "07.09.2026", "period": 4, "period_end": 5}


def test_a_course_that_drops_lessons_on_two_days_is_not_guessed_as_moved():
    current = tuple(row for row in SCHOOL_APP_REGULAR if row[0] not in (92001, 92006)) + ((92012, 4, 5, "D", "KLE", "R101", 82001),)
    week, _ = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    assert "moved_to" not in row_of(week, "07.09.2026", 1, "D")
    assert "moved_from" not in row_of(week, "11.09.2026", 5, "D")


def test_an_identical_week_carries_no_mark_but_the_change_list_format():
    week, comparison = marked_week(answer(SCHOOL_APP_REGULAR), answer(SCHOOL_APP_REGULAR))
    assert not any(kinds(week).values())
    assert week.change_items == []
    assert (comparison.outcome, comparison.changed, comparison.only_regular, comparison.only_current) == (COMPARED, 0, 0, 0)


def test_a_failed_regular_plan_leaves_the_week_as_the_school_app_sent_it():
    week, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), None)
    assert not any(kinds(week).values())
    assert week.change_items is None
    assert week.lesson_changes == {} and week.cancelled == []
    assert comparison.outcome == REGULAR_UNREAD


def test_a_regular_plan_in_an_unknown_shape_marks_nothing():
    regular = answer(SCHOOL_APP_REGULAR)
    regular["students"][0]["entries"][0]["weekday"] = "monday"
    week, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), regular)
    assert not any(kinds(week).values())
    assert week.change_items is None
    assert (comparison.outcome, comparison.failure) == (NOT_UNDERSTOOD, "ValueError")


def test_an_empty_regular_plan_marks_nothing():
    week, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), answer(()))
    assert not any(kinds(week).values())
    assert week.change_items is None
    assert (comparison.outcome, comparison.regular, comparison.only_current) == (REGULAR_EMPTY, 0, 9)


def test_more_than_half_differing_lessons_mark_nothing():
    current = tuple(row[:4] + ("NEW",) + row[5:] for row in SCHOOL_APP_REGULAR[:6]) + SCHOOL_APP_REGULAR[6:]
    week, comparison = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    assert not any(kinds(week).values())
    assert week.change_items is None
    assert (comparison.outcome, comparison.changed) == (TOO_DIFFERENT, 6)


def test_exactly_half_differing_lessons_are_still_marked():
    current = tuple(row[:4] + ("NEW",) + row[5:] for row in SCHOOL_APP_REGULAR[:5]) + SCHOOL_APP_REGULAR[5:]
    week, comparison = marked_week(answer(current), answer(SCHOOL_APP_REGULAR))
    assert comparison.outcome == COMPARED
    assert sum(1 for kind in kinds(week).values() if kind) == 5


def test_an_empty_week_in_both_plans_is_compared_without_marks():
    week, comparison = marked_week(answer(()), answer(()))
    assert comparison.outcome == COMPARED
    assert week.change_items == []


def test_the_substitutions_week_is_the_one_that_is_shown():
    week, _ = marked_week(answer(SCHOOL_APP_SUBSTITUTED), answer(SCHOOL_APP_REGULAR))
    assert len(week.combined) == 9
    assert len(week.plain) == 10
    assert any(lesson.teacher == "VER" for lesson in week.combined)


def test_the_same_entry_id_wins_over_the_subject_when_a_period_holds_parallel_courses():
    regular = (
        (93001, 0, 1, "REL", "AAA", "R1", 83001),
        (93002, 0, 1, "REL", "BBB", "R2", 83002),
    ) + SCHOOL_APP_REGULAR
    current = (
        (93001, 0, 1, "REL", "BBB", "R1", 83001),
        (93002, 0, 1, "REL", "DDD", "R2", 83002),
    ) + SCHOOL_APP_REGULAR
    week, comparison = marked_week(answer(current), answer(regular))
    changed = sorted(
        (lesson.teacher, entry["previous"]["teacher"], tuple(entry["fields"]))
        for lesson, entry in display_rows(week)
        if entry and entry["kind"] == "changed"
    )
    assert changed == [("BBB", "AAA", ("teacher",)), ("DDD", "BBB", ("teacher",))]
    assert comparison.changed == 2


def test_a_planted_substitution_object_marks_the_lesson_even_without_a_comparison():
    current = answer(SCHOOL_APP_REGULAR, {92004: {"substitution": {"id": 1}}})
    week, comparison = marked_week(current, None)
    entry = row_of(week, "08.09.2026", 1, "M")
    assert entry["kind"] == "changed"
    assert entry["no_details"] is True
    assert comparison.outcome == REGULAR_UNREAD
    assert (comparison.marked, comparison.markers_used) == (1, True)
    assert week.change_items is not None


def test_a_planted_cancellation_marker_wins_over_an_unchanged_comparison():
    current = answer(SCHOOL_APP_REGULAR, {92008: {"isCancelled": True}})
    week, comparison = marked_week(current, answer(SCHOOL_APP_REGULAR))
    assert row_of(week, "10.09.2026", 1, "E")["kind"] == "cancelled"
    assert comparison.marked == 1


def test_a_substitution_type_naming_a_cancellation_means_cancelled():
    assert entry_marker({"substitutionType": "Entfall"}) == "cancelled"
    assert entry_marker({"substitutionType": "Raumvertretung"}) == "changed"
    assert entry_marker({"vertretung": {"teacher": "X"}}) == "changed"


def test_empty_and_unrelated_keys_are_no_markers():
    entry = school_app_plan_entry(*SCHOOL_APP_REGULAR[0])
    assert entry_marker(entry) == ""
    assert entry_marker(dict(entry, timetableBlock={"id": 4})) == ""
    assert entry_marker({"substitution": None, "cancelled": False, "substitutionText": "", "cancellations": []}) == ""


def test_markers_on_more_than_half_of_the_lessons_are_left_out():
    extra = {row[0]: {"substitution": {"id": 1}} for row in SCHOOL_APP_REGULAR[:6]}
    week, comparison = marked_week(answer(SCHOOL_APP_REGULAR, extra), answer(SCHOOL_APP_REGULAR))
    assert not any(kinds(week).values())
    assert (comparison.marked, comparison.markers_used) == (6, False)


def test_without_released_substitutions_nothing_is_compared():
    week, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), NOT_ASKED)
    assert comparison.outcome == NOT_ASKED
    assert week.change_items is None


def test_the_description_names_counts_only():
    _, comparison = marked_week(answer(SCHOOL_APP_SUBSTITUTED), answer(SCHOOL_APP_REGULAR))
    assert describe(comparison) == (
        "regular plan 10 lessons, current 9, changed 1, only in the regular plan 2, only in the current plan 1, "
        "marked by the school 0, marks shown"
    )
    unread, _ = compare(answer(SCHOOL_APP_SUBSTITUTED), None, WEDNESDAY)
    assert describe(unread._replace(failure="answer 500")) == (
        "regular plan not read, current 9, changed 0, only in the regular plan 0, only in the current plan 0, "
        "marked by the school 0, marks left out, the regular plan was not read (answer 500)"
    )


FRIDAY_OFF = [{"id": 1, "name": "Ferientag", "startDate": "2026-09-11", "endDate": "2026-09-11"}]


@pytest.mark.parametrize("side", ["current", "regular"])
def test_a_holiday_day_missing_from_the_substituted_week_is_not_cancelled(side):
    current = answer(tuple(row for row in SCHOOL_APP_REGULAR if row[1] != 4))
    regular = answer(SCHOOL_APP_REGULAR)
    (current if side == "current" else regular)["vacations"] = FRIDAY_OFF
    week, comparison = marked_week(current, regular)
    assert not any(kinds(week).values())
    assert week.cancelled == []
    assert (comparison.outcome, comparison.only_regular, comparison.regular) == (COMPARED, 0, 9)


def test_a_lesson_on_a_holiday_in_the_substituted_week_stays_shown_without_a_mark():
    current = answer(replaced(SCHOOL_APP_REGULAR, 92010, teacher="VER"))
    current["vacations"] = [{"name": "Ferien", "startDate": "2026-09-10T00:00:00+02:00", "endDate": "2026-09-20"}]
    week, comparison = marked_week(current, answer(SCHOOL_APP_REGULAR))
    assert row_of(week, "11.09.2026", 1, "D") is None
    assert len(week.combined) == 10
    assert comparison.changed == 0


def test_a_vacation_with_unreadable_dates_is_ignored():
    current = answer(tuple(row for row in SCHOOL_APP_REGULAR if row[1] != 4))
    current["vacations"] = [{"name": "Ferien", "startDate": "soon", "endDate": "later"}]
    week, comparison = marked_week(current, answer(SCHOOL_APP_REGULAR))
    assert kinds(week)[("11.09.2026", 1, "D")] == "cancelled"
    assert comparison.outcome == COMPARED


def test_the_same_teachers_in_another_order_are_no_change():
    current, regular = answer(SCHOOL_APP_REGULAR), answer(SCHOOL_APP_REGULAR)
    teacher = current["students"][0]["entries"][0]["courseSubject"]["teachers"][0]
    second = dict(teacher, id=999, externalId="ZZZ")
    current["students"][0]["entries"][0]["courseSubject"]["teachers"] = [teacher, second]
    regular["students"][0]["entries"][0]["courseSubject"]["teachers"] = [second, teacher]
    week, comparison = marked_week(current, regular)
    assert not any(kinds(week).values())
    assert comparison.changed == 0
    assert week.combined[0].teacher == "KLE, ZZZ"


def test_a_teacher_added_to_a_lesson_is_still_a_change():
    current, regular = answer(SCHOOL_APP_REGULAR), answer(SCHOOL_APP_REGULAR)
    teacher = current["students"][0]["entries"][0]["courseSubject"]["teachers"][0]
    current["students"][0]["entries"][0]["courseSubject"]["teachers"] = [teacher, dict(teacher, id=999, externalId="ZZZ")]
    week, comparison = marked_week(current, regular)
    entry = row_of(week, "07.09.2026", 1, "D")
    assert (entry["kind"], entry["fields"], entry["previous"]["teacher"]) == ("changed", ["teacher"], "KLE")
    assert comparison.changed == 1


def test_school_markers_are_ignored_when_substitutions_are_not_released():
    current = answer(SCHOOL_APP_REGULAR, {92004: {"substitution": {"id": 1}}, 92008: {"isCancelled": True}})
    week, comparison = marked_week(current, NOT_ASKED)
    assert not any(kinds(week).values())
    assert week.change_items is None
    assert (comparison.outcome, comparison.marked, comparison.markers_used) == (NOT_ASKED, 0, False)
