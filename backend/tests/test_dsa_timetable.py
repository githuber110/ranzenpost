import json
import pathlib
from datetime import date

import pytest

from app.iserv.dsa_timetable import (
    course_filter,
    entry_to_lesson,
    parse_current_timetable,
    parse_vacations,
    query_date,
)

FIXTURE = json.loads(
    (pathlib.Path(__file__).resolve().parent / "fixtures" / "dsa_current_timetable.json").read_text(encoding="utf-8")
)
MONDAY = date(2026, 9, 7)


@pytest.fixture
def week():
    return parse_current_timetable(FIXTURE, MONDAY)


def test_the_week_carries_the_old_contract_start_and_end(week):
    assert week.start_date == "07.09.2026"
    assert week.end_date == "13.09.2026"
    assert week.last_updated is None


def test_every_entry_becomes_a_lesson_with_the_fields_the_app_already_reads(week):
    first = week.combined[0]
    assert first.date == "07.09.2026"
    assert first.day_of_week == 1
    assert first.period == 1
    assert first.subject == "D"
    assert first.teacher == "BEI"
    assert first.class_name == "Klasse 01D"


def test_weekday_zero_is_monday_and_four_is_friday(week):
    by_id = {lesson.lesson_id: lesson for lesson in week.combined}
    assert by_id[91001].date == "07.09.2026" and by_id[91001].day_of_week == 1
    assert by_id[91003].date == "09.09.2026" and by_id[91003].day_of_week == 3
    assert by_id[91004].date == "11.09.2026" and by_id[91004].day_of_week == 5


def test_any_day_of_the_week_maps_to_the_same_monday():
    assert parse_current_timetable(FIXTURE, date(2026, 9, 9)).start_date == "07.09.2026"
    assert parse_current_timetable(FIXTURE, date(2026, 9, 13)).start_date == "07.09.2026"


def test_an_empty_room_name_is_tolerated_not_invented(week):
    by_id = {lesson.lesson_id: lesson for lesson in week.combined}
    assert by_id[91001].room == ""
    assert by_id[91002].room == "Sporthalle"


def test_the_new_fields_travel_with_the_lesson(week):
    by_id = {lesson.lesson_id: lesson for lesson in week.combined}
    first = by_id[91001]
    assert first.subject_name == "Deutsch"
    assert first.subject_color == "#0f3beb"
    assert first.teacher_name == "Beispiel Katrin"
    assert first.start_time == "08:00"
    assert first.end_time == "08:45"


def test_several_teachers_are_joined_in_both_code_and_name(week):
    by_id = {lesson.lesson_id: lesson for lesson in week.combined}
    assert by_id[91003].teacher == "BEI, ZWE"
    assert by_id[91003].teacher_name == "Beispiel Katrin, Zweit Olga"


def test_a_lesson_without_a_teacher_keeps_an_empty_code_instead_of_failing(week):
    by_id = {lesson.lesson_id: lesson for lesson in week.combined}
    assert by_id[91004].teacher == ""
    assert by_id[91004].subject == "M"


def test_lessons_come_out_ordered_by_day_then_period(week):
    order = [(lesson.day_of_week, lesson.period) for lesson in week.combined]
    assert order == sorted(order)


def test_plain_equals_combined_so_no_change_is_ever_invented(week):
    assert week.plain == week.combined
    assert week.changes == []
    assert week.lesson_changes == {}
    assert week.cancelled == []


def test_vacations_are_kept_in_a_shape_the_app_can_use(week):
    assert week.vacations == [{"name": "Herbstferien", "start_date": "2026-10-17", "end_date": "2026-10-31"}]


def test_vacations_without_dates_are_dropped():
    assert parse_vacations([{"name": "x"}, {"name": "y", "startDate": "2026-01-01", "endDate": "2026-01-02"}]) == [
        {"name": "y", "start_date": "2026-01-01", "end_date": "2026-01-02"}
    ]


def test_an_empty_or_odd_payload_gives_an_empty_week_not_an_error():
    for payload in ({}, None, {"students": None}, {"students": [{"entries": None}]}, {"students": [{"entries": ["junk"]}]}):
        week = parse_current_timetable(payload, MONDAY)
        assert week.combined == [] and week.vacations == []


def test_the_course_filter_is_the_exact_form_the_module_sends():
    assert course_filter([1968718, 1651289, 1968716, 2308870]) == "courseSubject.course:in(1651289|1968716|1968718|2308870)"
    assert course_filter([7, 7, None]) == "courseSubject.course:in(7)"
    assert course_filter([]) == ""


def test_the_query_date_is_iso():
    assert query_date(date(2026, 9, 7)) == "2026-09-07"


def test_a_subject_without_an_acronym_falls_back_to_its_name():
    entry = {
        "courseSubject": {"subject": {"name": "Religion", "acronym": ""}, "teachers": [], "course": {"name": "1a"}},
        "timeTableSlot": {"number": 2},
        "weekday": 1,
        "room": {"name": "R2"},
    }
    lesson = entry_to_lesson(entry, MONDAY)
    assert lesson.subject == "Religion"
    assert lesson.date == "08.09.2026"
