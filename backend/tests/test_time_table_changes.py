import copy
from datetime import date

from app import feed, messages
from app.mapping import to_display

from app.iserv.timetable import display_rows, parse_time_table, parse_timetable, shown_changes
from tests.time_table_school import MOVED_WEEK_CHANGES, MOVED_WEEK_PLAN, moved_week_changes, time_table_week

START = "05.10.2026"
END = "11.10.2026"
MONDAY = "05.10.2026"
TUESDAY = "06.10.2026"
WEDNESDAY = "07.10.2026"
THURSDAY = "08.10.2026"
FRIDAY = "09.10.2026"
NEXT_MONDAY = "12.10.2026"


def change(day, period, subject, teacher, room, new_subject="", new_teacher="", new_room="", **extra):
    record = {
        "id": 700 + period,
        "date": day,
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


def without_teachers(payload):
    for entry in payload["data"]["timetable"] + payload["plain-timetable"]:
        entry["teacher"] = None
    return payload


def marked(week):
    return {(lesson.date, lesson.period, lesson.subject): entry for lesson, entry in display_rows(week) if entry}


def span(day, period, last=None):
    return {"date": day, "period": period, "period_end": period if last is None else last}


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


def test_a_change_that_only_repeats_the_regular_values_marks_the_lesson_without_a_changed_field():
    week = parse_time_table(week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R101")))
    lesson, entry = rows_by_slot(week)[(MONDAY, 1)]
    assert (lesson.subject, lesson.teacher, lesson.room) == ("D", "KLE", "R101")
    assert (entry["kind"], entry["fields"], entry["no_details"]) == ("changed", [], True)
    shown = to_display(lesson, {}, entry)
    title = messages.text_in("de", "calendar.event.summary", {"period": 1, "subject": "D", "teacher": "KLE"})
    neutral = messages.text_in("de", "timetable.change.school")
    assert feed.lesson_summary("de", shown) == messages.text_in("de", "calendar.event.summary.prefixed", {"prefix": neutral, "title": title})
    status = messages.text_in("de", "calendar.detail.line", {"label": messages.text_in("de", "calendar.detail.status"), "value": messages.text_in("de", "timetable.banner.school")})
    assert status in feed.lesson_description("de", shown, date(2026, 10, 5), 1)
    assert messages.text_in("de", "timetable.banner.changed") not in feed.lesson_description("de", shown, date(2026, 10, 5), 1)


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
    assert [(item["date"], item["period"], item["subject"], item["room"]) for item in shown_changes(week)] == [(MONDAY, 1, "D", "R305")]


def test_a_week_of_the_older_module_shows_every_change_record():
    week = parse_timetable(week_with(change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305", origClass=["6B"])))
    assert week.change_items is None
    assert shown_changes(week) == week.changes
    assert len(week.changes) == 1


def test_lessons_without_a_teacher_read_as_an_empty_teacher():
    week = parse_time_table(without_teachers(week_with()))
    assert {lesson.teacher for lesson in week.combined + week.plain} == {""}
    assert all(entry is None for _, entry in display_rows(week))


def test_digit_change_types_with_null_teachers_neither_break_nor_cancel_the_week():
    same = change(MONDAY, 1, "D", None, "R101", "D", None, "R101", change_types=["1", "2"])
    moved = change(TUESDAY, 1, "EN", None, "R204", "EN", None, "R305", change_types=["1", "4"])
    week = parse_time_table(without_teachers(week_with(same, moved)))
    rows = rows_by_slot(week)
    assert len(display_rows(week)) == len(week.combined)
    assert (rows[(MONDAY, 1)][1]["fields"], rows[(MONDAY, 1)][1]["teacher_hidden"]) == ([], True)
    assert "no_details" not in rows[(MONDAY, 1)][1]
    lesson, entry = rows[(TUESDAY, 1)]
    assert (lesson.subject, lesson.teacher, lesson.room) == ("EN", "", "R305")
    assert entry == {"kind": "changed", "fields": ["room"], "previous": {"subject": "EN", "teacher": "", "room": "R204"}}
    assert [(item["date"], item["period"]) for item in shown_changes(week)] == [(MONDAY, 1), (TUESDAY, 1)]
    assert all(entry is None or entry["kind"] != "cancelled" for _, entry in display_rows(week))


def test_a_change_without_a_visible_difference_marks_a_substitute_whose_teacher_is_not_given():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", None, "R101", change_types=["2", "4"])
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert (lesson.subject, lesson.teacher, lesson.room) == ("D", "", "R101")
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["teacher"]
    assert entry["previous"]["teacher"] == "KLE"
    assert entry["teacher_hidden"] is True


def test_a_change_that_joins_classes_marks_the_lesson_with_both_class_lists():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R101", origClass=["5A"], substitutionClass=["5C", "5A", "5B"])
    entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)][1]
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["class"]
    assert entry["previous"]["class"] == "5A"
    assert entry["classes"] == "5A, 5B, 5C"
    assert "teacher_hidden" not in entry


def test_the_note_of_a_change_stays_at_its_lesson_as_sent():
    record = change(FRIDAY, 1, "KU", "HAS", "R12", text="  Material mitbringen ")
    entry = rows_by_slot(parse_time_table(week_with(record)))[(FRIDAY, 1)][1]
    assert entry["kind"] == "cancelled"
    assert entry["note"] == "Material mitbringen"


def test_a_cancelled_lesson_missing_from_the_regular_plan_still_shows_as_cancelled():
    payload = week_with(change(FRIDAY, 1, "KU", "HAS", "R12"))
    payload["plain-timetable"] = [entry for entry in payload["plain-timetable"] if entry["subject"] != "KU"]
    lesson, entry = rows_by_slot(parse_time_table(payload))[(FRIDAY, 1)]
    assert (lesson.subject, entry["kind"]) == ("KU", "cancelled")


def test_a_cancellation_and_a_new_lesson_of_the_same_subject_read_as_one_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101", change_types=["1", "5"])
    here = change(FRIDAY, 1, "KU", "HAS", "R12", "MA", "", "R12", change_types=["3", "5"])
    week = parse_time_table(week_with(away, here))
    marks = marked(week)
    assert marks[(MONDAY, 2, "MA")]["kind"] == "cancelled"
    assert marks[(MONDAY, 2, "MA")]["moved_to"] == span(FRIDAY, 1)
    assert marks[(FRIDAY, 1, "MA")]["kind"] == "changed"
    assert marks[(FRIDAY, 1, "MA")]["moved_from"] == span(MONDAY, 2)
    assert "moved_from" not in marks[(MONDAY, 2, "MA")]
    assert [item["moved"] for item in shown_changes(week)] == [True, True]


def test_an_added_lesson_can_be_the_new_place_of_a_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101")
    here = change(TUESDAY, 5, "", "", "", "MA", "BRA", "R101")
    marks = marked(parse_time_table(week_with(away, here)))
    assert marks[(TUESDAY, 5, "MA")]["kind"] == "added"
    assert marks[(TUESDAY, 5, "MA")]["moved_from"] == span(MONDAY, 2)
    assert marks[(MONDAY, 2, "MA")]["moved_to"] == span(TUESDAY, 5)


def test_a_cancellation_without_a_counterpart_in_the_week_is_no_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101")
    next_week = change(NEXT_MONDAY, 1, "D", "KLE", "R101", "MA", "", "R101")
    week = parse_time_table(week_with(away, next_week))
    entry = marked(week)[(MONDAY, 2, "MA")]
    assert entry["kind"] == "cancelled"
    assert "moved_to" not in entry
    assert [(item["date"], item["period"], item["kind"]) for item in shown_changes(week)] == [(MONDAY, 2, "cancelled")]


def test_two_candidates_for_the_new_place_leave_the_move_open():
    away = change(MONDAY, 2, "MA", "BRA", "R101")
    first = change(FRIDAY, 1, "KU", "HAS", "R12", "MA", "", "R12")
    second = change(TUESDAY, 1, "EN", "WOL", "R204", "MA", "", "R204")
    marks = marked(parse_time_table(week_with(away, first, second)))
    assert not any("moved_to" in entry or "moved_from" in entry for entry in marks.values())
    assert len(marks) == 3


def test_two_cancellations_for_one_new_place_leave_the_move_open():
    payload = week_with(change(MONDAY, 2, "MA", "BRA", "R101"), change(THURSDAY, 2, "MA", "BRA", "R101"), change(FRIDAY, 1, "KU", "HAS", "R12", "MA", "", "R12"))
    marks = marked(parse_time_table(payload))
    assert not any("moved_to" in entry or "moved_from" in entry for entry in marks.values())
    assert sorted(entry["kind"] for entry in marks.values()) == ["cancelled", "cancelled", "changed"]


def test_a_change_that_keeps_its_subject_is_no_new_place_of_a_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101")
    same = change(THURSDAY, 2, "MA", "BRA", "R101", "MA", "", "R305")
    marks = marked(parse_time_table(week_with(away, same)))
    assert "moved_to" not in marks[(MONDAY, 2, "MA")]
    assert "moved_from" not in marks[(THURSDAY, 2, "MA")]


def test_different_known_teachers_are_no_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101")
    here = change(FRIDAY, 1, "KU", "HAS", "R12", "MA", "ZZZ", "R12")
    marks = marked(parse_time_table(week_with(away, here)))
    assert "moved_to" not in marks[(MONDAY, 2, "MA")]


def test_classes_without_overlap_are_no_move():
    away = change(MONDAY, 2, "MA", "BRA", "R101", origClass=["5A"])
    here = change(FRIDAY, 1, "KU", "HAS", "R12", "MA", "", "R12", origClass=["5A"], substitutionClass=["5B"])
    marks = marked(parse_time_table(week_with(away, here)))
    assert "moved_to" not in marks[(MONDAY, 2, "MA")]


def test_a_double_period_moves_as_one_span():
    plan = ((1, 1, "D", "KLE", "R101"), (1, 2, "D", "KLE", "R101"), (4, 3, "MA", "BRA", "R101"), (4, 4, "MA", "BRA", "R101"))
    payload = time_table_week(START, END, plan=plan)
    payload["plain-changes"] = [
        change(MONDAY, 1, "D", "KLE", "R101", periodStart=1, periodEnd=2),
        change(THURSDAY, 3, "MA", "BRA", "R101", "D", "KLE", "R101", periodStart=3, periodEnd=4),
    ]
    week = parse_time_table(payload)
    marks = marked(week)
    assert marks[(MONDAY, 1, "D")]["moved_to"] == span(THURSDAY, 3, 4)
    assert marks[(MONDAY, 2, "D")]["moved_to"] == span(THURSDAY, 3, 4)
    assert marks[(THURSDAY, 3, "D")]["moved_from"] == span(MONDAY, 1, 2)
    assert marks[(THURSDAY, 4, "D")]["moved_from"] == span(MONDAY, 1, 2)
    assert len(shown_changes(week)) == len(marks) == 4


def test_every_marked_lesson_is_one_listed_change():
    records = [
        change(MONDAY, 1, "D", "KLE", "R101", "D", "KLE", "R305"),
        change(MONDAY, 2, "MA", "BRA", "R101"),
        change(TUESDAY, 1, "EN", "WOL", "R204", "EN", None, "R204"),
    ]
    week = parse_time_table(week_with(*records))
    items = shown_changes(week)
    assert len(items) == len(marked(week)) == 3
    assert {(item["date"], item["period"], item["subject"], item["kind"]) for item in items} == {
        (MONDAY, 1, "D", "changed"), (MONDAY, 2, "MA", "cancelled"), (TUESDAY, 1, "EN", "changed"),
    }
    assert set(items[0]) == {"date", "period", "subject", "teacher", "room", "kind", "fields", "note", "moved"}


def test_the_moved_week_marks_every_record_and_reads_both_moves():
    payload = time_table_week(START, END, plan=MOVED_WEEK_PLAN)
    payload["plain-changes"] = moved_week_changes(START)
    week = parse_time_table(payload)
    marks = marked(week)
    assert len(marks) == len(shown_changes(week)) == len(MOVED_WEEK_CHANGES) == 7
    assert {key: (entry["kind"], entry["fields"]) for key, entry in marks.items()} == {
        (MONDAY, 4, "M"): ("changed", ["subject", "room"]),
        (TUESDAY, 2, "Eth"): ("changed", ["class"]),
        (TUESDAY, 6, "L"): ("cancelled", []),
        (WEDNESDAY, 3, "Bio"): ("changed", []),
        (THURSDAY, 5, "L"): ("changed", ["subject"]),
        (FRIDAY, 4, "Eth"): ("changed", ["class"]),
        (FRIDAY, 6, "M"): ("cancelled", []),
    }
    assert marks[(TUESDAY, 6, "L")]["moved_to"] == span(THURSDAY, 5)
    assert marks[(THURSDAY, 5, "L")]["moved_from"] == span(TUESDAY, 6)
    assert marks[(FRIDAY, 6, "M")]["moved_to"] == span(MONDAY, 4)
    assert marks[(MONDAY, 4, "M")]["moved_from"] == span(FRIDAY, 6)
    assert marks[(TUESDAY, 6, "L")]["note"] == "Material mitbringen"
    assert marks[(TUESDAY, 2, "Eth")]["classes"] == "5A, 5B, 5C"
    assert marks[(WEDNESDAY, 3, "Bio")]["teacher_hidden"] is True
    assert sum(1 for entry in marks.values() if entry.get("moved_to") or entry.get("moved_from")) == 4


def test_a_new_subject_without_a_named_teacher_does_not_keep_the_replaced_teacher():
    record = change(MONDAY, 1, "D", "KLE", "R101", "MA", None, "R101")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert (lesson.subject, lesson.teacher) == ("MA", "")
    assert entry["fields"] == ["subject", "teacher"]
    assert entry["previous"]["teacher"] == "KLE"
    assert entry["teacher_hidden"] is True


def test_a_blank_substitute_teacher_counts_as_not_given_when_the_subject_changes():
    record = change(MONDAY, 1, "D", "KLE", "R101", "MA", " -- ", "R305")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert (lesson.subject, lesson.teacher, lesson.room) == ("MA", "", "R305")
    assert entry["fields"] == ["subject", "teacher", "room"]


def test_a_room_change_without_a_named_teacher_keeps_the_regular_teacher():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", None, "R305")
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert (lesson.teacher, lesson.room) == ("KLE", "R305")
    assert entry["fields"] == ["room"]
    assert "teacher_hidden" not in entry


def test_a_record_without_a_teacher_field_keeps_the_regular_teacher():
    record = change(MONDAY, 1, "D", "KLE", "R101", "MA", None, "R101")
    del record["substitutionTeacher"]
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert (lesson.subject, lesson.teacher) == ("MA", "KLE")
    assert entry["fields"] == ["subject"]
    assert "teacher_hidden" not in entry


def test_a_substitute_record_without_a_teacher_field_marks_the_lesson_without_naming_a_teacher_change():
    record = change(MONDAY, 1, "D", "KLE", "R101", "D", None, "R101")
    del record["substitutionTeacher"]
    lesson, entry = rows_by_slot(parse_time_table(week_with(record)))[(MONDAY, 1)]
    assert lesson.teacher == "KLE"
    assert (entry["kind"], entry["fields"]) == ("changed", [])
    assert "teacher_hidden" not in entry


def test_a_cancellation_and_a_substitution_without_a_shared_change_type_are_no_move():
    away = change(MONDAY, 2, "MA", None, "R101", change_types=["11"])
    here = change(FRIDAY, 1, "KU", None, "R12", "MA", None, "R12", change_types=["12"])
    marks = marked(parse_time_table(week_with(away, here)))
    assert "moved_to" not in marks[(MONDAY, 2, "MA")]
    assert "moved_from" not in marks[(FRIDAY, 1, "MA")]


def test_a_shared_change_type_keeps_the_move():
    away = change(MONDAY, 2, "MA", None, "R101", change_types=["11", "13"])
    here = change(FRIDAY, 1, "KU", None, "R12", "MA", None, "R12", change_types=["12", "13"])
    marks = marked(parse_time_table(week_with(away, here)))
    assert marks[(MONDAY, 2, "MA")]["moved_to"] == span(FRIDAY, 1)
    assert marks[(FRIDAY, 1, "MA")]["moved_from"] == span(MONDAY, 2)


def test_change_types_on_only_one_side_do_not_block_a_move():
    away = change(MONDAY, 2, "MA", None, "R101", change_types=["11"])
    here = change(FRIDAY, 1, "KU", None, "R12", "MA", None, "R12", change_types=[])
    assert marked(parse_time_table(week_with(away, here)))[(MONDAY, 2, "MA")]["moved_to"] == span(FRIDAY, 1)


def test_a_cancellation_next_to_a_new_lesson_in_the_same_slot_never_hides_the_named_teacher():
    cancelled = change(MONDAY, 1, "D", "KLE", "R101", None, None, None)
    added = change(MONDAY, 1, "", "", "", "MA", "ORF", "R8")
    rows = [(lesson, entry) for lesson, entry in display_rows(parse_time_table(week_with(cancelled, added))) if (lesson.date, lesson.period) == (MONDAY, 1)]
    assert len(rows) == 1
    lesson, entry = rows[0]
    assert (lesson.subject, lesson.teacher) == ("MA", "ORF")
    assert "teacher_hidden" not in entry


def test_a_cancelled_lesson_stays_one_row_when_the_regular_plan_names_another_room():
    payload = week_with(change(FRIDAY, 1, "KU", "HAS", "R12"))
    next(entry for entry in payload["plain-timetable"] if entry["subject"] == "KU")["room"] = "R13"
    week = parse_time_table(payload)
    rows = [(lesson, entry) for lesson, entry in display_rows(week) if (lesson.date, lesson.period) == (FRIDAY, 1)]
    assert len(rows) == 1
    assert rows[0][1]["kind"] == "cancelled"
    assert len(shown_changes(week)) == 1


def test_each_cancelled_parallel_lesson_keeps_its_own_note():
    plan = ((3, 3, "SP", "FUC", "GYM"), (3, 3, "SP", "ZZZ", "GYM2"))
    payload = time_table_week(START, END, plan=plan)
    payload["plain-changes"] = [
        change(WEDNESDAY, 3, "SP", "FUC", "GYM", text="first"),
        change(WEDNESDAY, 3, "SP", "ZZZ", "GYM2", text="second"),
    ]
    rows = display_rows(parse_time_table(payload))
    assert sorted((lesson.teacher, entry["kind"], entry["note"]) for lesson, entry in rows) == [
        ("FUC", "cancelled", "first"), ("ZZZ", "cancelled", "second"),
    ]
