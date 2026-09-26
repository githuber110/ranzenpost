import copy

from app.iserv.timetable import display_rows, parse_time_table, parse_timetable, shown_changes
from tests.time_table_school import time_table_week

START = "05.10.2026"
END = "11.10.2026"
MONDAY = "05.10.2026"
TUESDAY = "06.10.2026"
FRIDAY = "09.10.2026"


def change(date, period, subject, teacher, room, new_subject="", new_teacher="", new_room="", **extra):
    record = {
        "id": 700 + period,
        "date": date,
        "chgdow": "1",
        "period": period,
        "origTeacher": teacher,
        "substitutionTeacher": new_teacher,
        "origSubject": subject,
        "substitutionSubject": new_subject,
        "origRoom": room,
        "substitutionRoom": new_room,
        "origClass": ["5A", "5B", "5C", "5D"],
        "substitutionClass": ["5A", "5B", "5C", "5D"],
        "text": "",
        "change_types": [],
        "updated": "202610050700",
        "internal_id": "901",
        "periodStart": period,
        "periodEnd": period,
    }
    record.update(extra)
    return record


def week_with(*changes):
    payload = time_table_week(START, END)
    payload["plain-changes"] = list(changes)
    return payload


def rows_by_slot(week):
    return {(lesson.date, lesson.period): (lesson, entry) for lesson, entry in display_rows(week)}


def test_a_room_change_shows_the_new_room_and_the_old_one():
    week = parse_time_table(week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305")))
    lesson, entry = rows_by_slot(week)[(MONDAY, 1)]
    assert lesson.room == "R305"
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["room"]
    assert entry["previous"]["room"] == "R101"


def test_a_teacher_change_shows_the_substitute_and_the_regular_teacher():
    week = parse_time_table(week_with(change(TUESDAY, 1, "EN", "WOL", "R204", "EN", "MEY", "R204")))
    lesson, entry = rows_by_slot(week)[(TUESDAY, 1)]
    assert lesson.teacher == "MEY"
    assert entry["fields"] == ["teacher"]
    assert entry["previous"]["teacher"] == "WOL"


def test_a_change_with_blank_substitution_values_keeps_the_regular_values():
    week = parse_time_table(week_with(change(MONDAY, 2, "MA", "BRA", "R101", new_teacher="HOF")))
    lesson, entry = rows_by_slot(week)[(MONDAY, 2)]
    assert (lesson.subject, lesson.teacher, lesson.room) == ("MA", "HOF", "R101")
    assert entry["fields"] == ["teacher"]


def test_a_change_marked_as_cancellation_cancels_the_lesson():
    week = parse_time_table(week_with(change(FRIDAY, 1, "KU", "HAS", "R12", change_types=["cancellation"])))
    lesson, entry = rows_by_slot(week)[(FRIDAY, 1)]
    assert entry["kind"] == "cancelled"
    assert lesson.subject == "KU"


def test_a_change_that_only_repeats_the_regular_values_changes_nothing():
    week = parse_time_table(week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R101")))
    assert rows_by_slot(week)[(MONDAY, 1)][1] is None


def test_a_change_spanning_two_periods_reaches_both_lessons():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", periodStart=1, periodEnd=2)
    payload = week_with(record)
    payload["data"]["timetable"][1].update(subject="D", teacher="KLE")
    payload["plain-timetable"][1].update(subject="D", teacher="KLE")
    rows = rows_by_slot(parse_time_table(payload))
    assert rows[(MONDAY, 1)][0].room == "R305"
    assert rows[(MONDAY, 2)][0].room == "R305"


def test_a_change_for_another_class_is_ignored():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass=["6B"], substitutionClass=["6B"])
    assert rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)][1] is None


def test_a_combined_plan_that_already_carries_the_change_is_not_changed_twice():
    payload = week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305"))
    payload["data"]["timetable"][0]["room"] = "R305"
    lesson, entry = rows_by_slot(parse_time_table(payload))[(MONDAY, 1)]
    assert lesson.room == "R305"
    assert entry["fields"] == ["room"]
    assert entry["previous"]["room"] == "R101"


def test_applying_changes_leaves_the_answer_untouched():
    payload = week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305"))
    before = copy.deepcopy(payload)
    parse_time_table(payload)
    assert payload == before


def test_unreadable_change_records_are_skipped():
    payload = week_with({"date": MONDAY}, "text", change(MONDAY, 1, "D", "KLE", "R101", new_room="R305"))
    assert rows_by_slot(parse_time_table(payload))[(MONDAY, 1)][0].room == "R305"


def test_a_note_about_a_failure_does_not_cancel_a_room_change():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", text="Raum wegen Ausfall der Heizung")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert entry["kind"] == "changed"
    assert lesson.room == "R305"


def test_a_change_without_any_substitute_values_is_a_cancellation():
    lesson, entry = rows_by_slot(parse_time_table(week_with(change(FRIDAY, 1, "KU", "HAS", "R12"))))[(FRIDAY, 1)]
    assert entry["kind"] == "cancelled"


def test_placeholder_dashes_count_as_no_value():
    record = change(FRIDAY, 1, "KU", "HAS", "R12", "---", "---", "---")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(FRIDAY, 1)]
    assert entry["kind"] == "cancelled"
    assert (lesson.teacher, lesson.room) == ("HAS", "R12")


def test_two_changes_to_one_lesson_both_show():
    room = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", updated="202610050700")
    teacher = change(MONDAY, 1, "D", "KLE", "R101", "D", "MEY", "", updated="202610050800")
    lesson, entry = rows_by_slot(parse_time_table(week_with(teacher, room)))[(MONDAY, 1)]
    assert (lesson.teacher, lesson.room) == ("MEY", "R305")
    assert entry["fields"] == ["teacher", "room"]


def test_a_change_without_a_teacher_leaves_ambiguous_parallel_lessons_alone():
    payload = week_with(change(MONDAY, 1, "D", "", "", "D", "", "R305"))
    parallel = dict(payload["data"]["timetable"][0], teacher="ZZZ", room="R102", id=4999)
    payload["data"]["timetable"].append(parallel)
    payload["plain-timetable"].append(dict(parallel))
    rooms = sorted(lesson.room for lesson, _ in display_rows(parse_time_table(payload)) if (lesson.date, lesson.period) == (MONDAY, 1))
    assert rooms == ["R101", "R102"]


def test_a_change_without_a_teacher_uses_the_room_to_find_the_lesson():
    payload = week_with(change(MONDAY, 1, "D", "", "R102", "D", "", "R305"))
    parallel = dict(payload["data"]["timetable"][0], teacher="ZZZ", room="R102", id=4999)
    payload["data"]["timetable"].append(parallel)
    payload["plain-timetable"].append(dict(parallel))
    rooms = sorted(lesson.room for lesson, _ in display_rows(parse_time_table(payload)) if (lesson.date, lesson.period) == (MONDAY, 1))
    assert rooms == ["R101", "R305"]


def test_class_fields_in_other_forms_never_break_the_week():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass="5A")
    payload = week_with(record)
    del payload["data"]["timetable"][0]["class"]
    week = parse_time_table(payload)
    assert len(display_rows(week)) == len(payload["data"]["timetable"])


def test_a_lesson_of_several_classes_is_matched_by_any_of_them():
    payload = week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass=["5B"]))
    payload["data"]["timetable"][0]["class"] = "5A,5B"
    assert rows_by_slot(parse_time_table(payload))[(MONDAY, 1)][0].room == "R305"


def test_an_extra_lesson_shows_as_added():
    record = change(MONDAY, 4, "", "", "", "MU", "ORF", "R8")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 4)]
    assert (lesson.subject, lesson.teacher, lesson.room, lesson.day_of_week) == ("MU", "ORF", "R8", 1)
    assert entry["kind"] == "added"


def test_an_extra_lesson_for_another_class_is_not_added():
    record = change(MONDAY, 4, "", "", "", "MU", "ORF", "R8", substitutionClass=["9C"])
    assert (MONDAY, 4) not in rows_by_slot(parse_time_table(week_with(record)))


def test_the_week_counts_only_the_changes_that_reached_a_lesson():
    shown = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305")
    elsewhere = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass=["6B"])
    week = parse_time_table(week_with(shown, elsewhere))
    assert week.changes == [shown, elsewhere]
    assert week.applied_changes == [shown]
    assert shown_changes(week) == [shown]


def test_a_week_of_the_older_module_shows_every_change_record():
    week = parse_timetable(week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass=["6B"])))
    assert week.applied_changes is None
    assert shown_changes(week) == week.changes
    assert len(week.changes) == 1
