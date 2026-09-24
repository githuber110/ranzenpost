import json
from datetime import date

import pytest

from app.iserv.errors import DataError
from app.iserv.timetable import (
    TIMETABLE_SHAPE_KEY,
    build_filter,
    change_key,
    crowded_keys,
    detect_changes,
    display_rows,
    lesson_key,
    parse_timetable,
    slot_key,
    week_bounds,
)


def raw(period, subject="D", teacher="AAA", room="R1", date_value="31.08.2026", **extra):
    entry = {
        "id": 1000 + period,
        "class": "01A",
        "teacher": teacher,
        "subject": subject,
        "room": room,
        "dow": 1,
        "period": period,
        "internal_id": str(period),
        "date": date_value,
        "period_reference": None,
    }
    entry.update(extra)
    return entry


def payload(combined=None, plain=None, changes=None):
    return {
        "meta": {
            "filter": {"startDate": "31.08.2026", "endDate": "06.09.2026"},
            "last-updated": "22.07.2026 12:25",
        },
        "data": {"timetable": combined or [], "orphan-changes": []},
        "plain-timetable": plain or [],
        "plain-changes": changes or [],
    }


def parse_fixture(fixture):
    return parse_timetable(json.loads(fixture("timetable_data.json")))


def test_week_bounds_spans_monday_to_sunday():
    start, end = week_bounds(date(2026, 9, 2))
    assert start == date(2026, 8, 31)
    assert end == date(2026, 9, 6)


def test_build_filter_shape():
    week_filter = build_filter("child-1", date(2026, 8, 31), date(2026, 9, 6))
    assert week_filter["startDate"] == "31.08.2026"
    assert week_filter["endDate"] == "06.09.2026"
    assert week_filter["child"] == "child-1"
    assert week_filter["classes"] == []


def test_parse_timetable(fixture):
    week = parse_fixture(fixture)
    assert week.last_updated == "22.07.2026 12:25"
    assert week.start_date == "31.08.2026"
    assert len(week.combined) == 2
    assert len(week.plain) == 3
    assert len(week.changes) == 1
    first = week.combined[0]
    assert first.subject == "D"
    assert first.day_of_week == 1
    assert first.period == 1
    assert first.lesson_id == 1001


def test_slot_key_joins_date_and_period():
    assert slot_key("31.08.2026", 2) == "31.08.2026|2"


def test_fixture_regular_lesson_has_no_change_entry(fixture):
    week = parse_fixture(fixture)
    assert "31.08.2026|1|D" not in week.lesson_changes


def test_fixture_substitution_is_detected_by_diff(fixture):
    week = parse_fixture(fixture)
    entry = week.lesson_changes["31.08.2026|2|M"]
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["teacher", "room"]
    assert entry["previous"] == {"subject": "M", "teacher": "BBB", "room": "R1"}


def test_fixture_cancellation_is_detected_by_diff(fixture):
    week = parse_fixture(fixture)
    assert week.lesson_changes["31.08.2026|3|SP"]["kind"] == "cancelled"
    assert [lesson.subject for lesson in week.cancelled] == ["SP"]
    assert week.cancelled[0].room == "GYM"
    assert all(lesson.period != 3 for lesson in week.combined)


def test_empty_plain_timetable_marks_nothing_as_added():
    week = parse_timetable(payload(combined=[raw(1), raw(2, subject="M")], plain=[]))
    assert week.lesson_changes == {}
    assert week.cancelled == []


def test_empty_plain_timetable_still_honours_change_types():
    week = parse_timetable(payload(combined=[raw(1)], plain=[], changes=[raw(1, type="Entfall")]))
    assert week.lesson_changes["31.08.2026|1|D"]["kind"] == "cancelled"


def test_added_lesson_when_slot_missing_from_plain():
    week = parse_timetable(payload(combined=[raw(1), raw(4, subject="EN")], plain=[raw(1)]))
    entry = week.lesson_changes["31.08.2026|4|EN"]
    assert entry["kind"] == "added"
    assert entry["fields"] == []
    assert entry["previous"] == {"subject": "", "teacher": "", "room": ""}
    assert "31.08.2026|1|D" not in week.lesson_changes
    assert week.cancelled == []


def test_identical_lessons_produce_no_changes():
    week = parse_timetable(payload(combined=[raw(1)], plain=[raw(1)]))
    lesson_changes, cancelled = detect_changes(week.combined, week.plain, [])
    assert lesson_changes == {}
    assert cancelled == []
    assert week.lesson_changes == {}


def test_subject_only_difference_is_changed():
    week = parse_timetable(payload(combined=[raw(1, subject="EN")], plain=[raw(1, subject="D")]))
    entry = week.lesson_changes["31.08.2026|1|EN"]
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["subject"]
    assert entry["previous"]["subject"] == "D"


def test_cancel_tokens_refine_an_otherwise_regular_slot():
    for value in ("cancelled", "Entfall", "AUSFALL", " Unterricht faellt aus (Ausfall) "):
        week = parse_timetable(
            payload(combined=[raw(1)], plain=[raw(1)], changes=[raw(1, type=value)])
        )
        assert week.lesson_changes["31.08.2026|1|D"]["kind"] == "cancelled", value


def test_substitution_tokens_refine_an_otherwise_regular_slot():
    for value in ("substitution", "Vertretung", "CHANGE", "Lehrer-Vertretung"):
        week = parse_timetable(
            payload(combined=[raw(1)], plain=[raw(1)], changes=[raw(1, type=value)])
        )
        assert week.lesson_changes["31.08.2026|1|D"]["kind"] == "changed", value


def test_unknown_change_type_keeps_the_diff_result():
    week = parse_timetable(
        payload(
            combined=[raw(1, teacher="ZZZ")],
            plain=[raw(1, teacher="AAA")],
            changes=[raw(1, type="irgendwas-neues")],
        )
    )
    entry = week.lesson_changes["31.08.2026|1|D"]
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["teacher"]


def test_unknown_change_type_does_not_invent_a_change():
    week = parse_timetable(
        payload(combined=[raw(1)], plain=[raw(1)], changes=[raw(1, type="irgendwas-neues")])
    )
    assert week.lesson_changes == {}


def test_missing_or_broken_change_type_never_crashes():
    entry_without_type = raw(1)
    entry_without_type.pop("period", None)
    week = parse_timetable(
        payload(
            combined=[raw(1, teacher="ZZZ")],
            plain=[raw(1, teacher="AAA")],
            changes=[raw(1), raw(1, type=None), raw(1, type=42), entry_without_type, "kaputt", None],
        )
    )
    assert week.lesson_changes["31.08.2026|1|D"]["kind"] == "changed"


def test_change_entry_with_unparsable_period_is_ignored():
    broken = raw(1, type="Entfall")
    broken["period"] = "x"
    week = parse_timetable(payload(combined=[raw(1)], plain=[raw(1)], changes=[broken]))
    assert week.lesson_changes == {}


def test_exact_duplicate_plain_entries_yield_one_cancelled_entry():
    week = parse_timetable(payload(combined=[], plain=[raw(5), raw(5)]))
    assert len(week.cancelled) == 1
    assert week.lesson_changes["31.08.2026|5|D|AAA"]["kind"] == "cancelled"


def test_parallel_groups_of_one_subject_are_each_cancelled():
    week = parse_timetable(payload(combined=[], plain=[raw(5), raw(5, teacher="BBB")]))
    assert sorted(lesson.teacher for lesson in week.cancelled) == ["AAA", "BBB"]
    assert week.lesson_changes["31.08.2026|5|D|AAA"]["kind"] == "cancelled"
    assert week.lesson_changes["31.08.2026|5|D|BBB"]["kind"] == "cancelled"


def test_changes_are_scoped_per_day():
    week = parse_timetable(
        payload(
            combined=[raw(1, date_value="01.09.2026", teacher="ZZZ")],
            plain=[raw(1, date_value="31.08.2026"), raw(1, date_value="01.09.2026")],
        )
    )
    assert week.lesson_changes["01.09.2026|1|D"]["kind"] == "changed"
    assert week.lesson_changes["31.08.2026|1|D"]["kind"] == "cancelled"


def test_lesson_key_joins_date_period_and_subject():
    assert lesson_key("01.09.2026", 4, "TEAM") == "01.09.2026|4|TEAM"


def test_parse_timetable_keeps_a_genuinely_empty_week():
    week = parse_timetable(payload(combined=[], plain=[]))
    assert week.combined == []
    assert week.plain == []


def test_parse_timetable_rejects_a_payload_with_no_data_key():
    broken = payload()
    del broken["data"]
    with pytest.raises(DataError) as caught:
        parse_timetable(broken)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY


def test_parse_timetable_rejects_a_payload_with_no_timetable_key():
    broken = payload()
    del broken["data"]["timetable"]
    with pytest.raises(DataError) as caught:
        parse_timetable(broken)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY


def test_parse_timetable_reads_a_missing_plain_timetable_as_empty():
    week_payload = payload(combined=[raw(1)])
    del week_payload["plain-timetable"]
    week = parse_timetable(week_payload)
    assert [lesson.subject for lesson in week.combined] == ["D"]
    assert week.plain == []
    assert week.lesson_changes == {}
    assert week.cancelled == []


def test_parse_timetable_reads_a_null_plain_timetable_as_empty():
    week_payload = payload()
    week_payload["plain-timetable"] = None
    week = parse_timetable(week_payload)
    assert week.plain == []


def test_parse_timetable_rejects_a_payload_with_no_meta_key():
    broken = payload()
    del broken["meta"]
    with pytest.raises(DataError) as caught:
        parse_timetable(broken)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY


def test_double_slot_survives_parse_timetable(fixture):
    week = parse_timetable(json.loads(fixture("timetable_double_slot.json")))
    shared = [lesson for lesson in week.combined if lesson.period == 4]
    assert len(shared) == 2
    assert sorted(lesson.subject for lesson in shared) == ["M", "TEAM"]
    assert len([lesson for lesson in week.plain if lesson.period == 4]) == 2
    assert week.lesson_changes == {}
    assert week.cancelled == []


def test_partial_cancellation_hits_only_the_missing_subject():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="M", teacher="ERN")],
            plain=[raw(4, subject="M", teacher="ERN"), raw(4, subject="TEAM", teacher="BEH", room="R2")],
        )
    )
    assert list(week.lesson_changes) == ["31.08.2026|4|TEAM"]
    assert week.lesson_changes["31.08.2026|4|TEAM"]["kind"] == "cancelled"
    assert [lesson.subject for lesson in week.cancelled] == ["TEAM"]
    assert week.cancelled[0].room == "R2"


def test_double_slot_substitution_is_paired_by_subject():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="M", teacher="ERN"), raw(4, subject="TEAM", teacher="REZ")],
            plain=[raw(4, subject="M", teacher="ERN"), raw(4, subject="TEAM", teacher="BEH")],
        )
    )
    assert list(week.lesson_changes) == ["31.08.2026|4|TEAM"]
    entry = week.lesson_changes["31.08.2026|4|TEAM"]
    assert entry["kind"] == "changed"
    assert entry["fields"] == ["teacher"]
    assert entry["previous"]["teacher"] == "BEH"
    assert week.cancelled == []


def test_double_slot_pairing_ignores_feed_order():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="TEAM", teacher="REZ"), raw(4, subject="M", teacher="ERN")],
            plain=[raw(4, subject="M", teacher="ERN"), raw(4, subject="TEAM", teacher="BEH")],
        )
    )
    assert list(week.lesson_changes) == ["31.08.2026|4|TEAM"]


def test_change_with_subject_refines_only_that_lesson_of_the_slot():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="M"), raw(4, subject="TEAM")],
            plain=[raw(4, subject="M"), raw(4, subject="TEAM")],
            changes=[raw(4, subject="TEAM", type="Entfall")],
        )
    )
    assert list(week.lesson_changes) == ["31.08.2026|4|TEAM"]
    assert week.lesson_changes["31.08.2026|4|TEAM"]["kind"] == "cancelled"


def test_change_without_subject_refines_every_lesson_of_the_slot():
    anonymous = raw(4, type="Entfall")
    anonymous["subject"] = ""
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="M"), raw(4, subject="TEAM")],
            plain=[raw(4, subject="M"), raw(4, subject="TEAM")],
            changes=[anonymous],
        )
    )
    assert set(week.lesson_changes) == {"31.08.2026|4|M", "31.08.2026|4|TEAM"}
    assert all(entry["kind"] == "cancelled" for entry in week.lesson_changes.values())


def test_change_with_unmatched_subject_still_refines_the_whole_slot():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="M"), raw(4, subject="TEAM")],
            plain=[raw(4, subject="M"), raw(4, subject="TEAM")],
            changes=[raw(4, subject="XYZ", type="Entfall")],
        )
    )
    assert set(week.lesson_changes) == {"31.08.2026|4|M", "31.08.2026|4|TEAM"}


def parse_parallel(fixture):
    return parse_timetable(json.loads(fixture("timetable_parallel_courses.json")))


def test_lesson_key_with_teacher_appends_the_teacher():
    assert lesson_key("01.09.2026", 4, "SP", "GGG") == "01.09.2026|4|SP|GGG"


def test_crowded_keys_name_slots_with_one_subject_twice():
    week = parse_timetable(payload(combined=[raw(1), raw(1, teacher="BBB"), raw(2, subject="M")]))
    assert crowded_keys(week.combined) == {"31.08.2026|1|D"}
    assert change_key(week.combined[0], {"31.08.2026|1|D"}) == "31.08.2026|1|D|AAA"
    assert change_key(week.combined[2], {"31.08.2026|1|D"}) == "31.08.2026|2|M"


def test_parallel_fixture_keeps_every_lesson_of_a_period(fixture):
    week = parse_parallel(fixture)
    third = [lesson for lesson in week.combined if lesson.date == "31.08.2026" and lesson.period == 3]
    assert len(third) == 6
    assert sorted((lesson.subject, lesson.teacher) for lesson in third) == [
        ("E1", "CCC"),
        ("E2", "DDD"),
        ("F1", "EEE"),
        ("L1", "FFF"),
        ("SP", "GGG"),
        ("SP", "HHH"),
    ]
    assert not any(key.startswith("31.08.2026|") for key in week.lesson_changes)


def test_parallel_fixture_substitution_hits_only_its_course(fixture):
    week = parse_parallel(fixture)
    changed = {key: entry for key, entry in week.lesson_changes.items() if key.startswith("01.09.2026|1|")}
    assert list(changed) == ["01.09.2026|1|E2"]
    assert changed["01.09.2026|1|E2"]["kind"] == "changed"
    assert changed["01.09.2026|1|E2"]["fields"] == ["teacher"]
    assert changed["01.09.2026|1|E2"]["previous"]["teacher"] == "DDD"


def test_parallel_fixture_cancellation_hits_only_the_missing_group(fixture):
    week = parse_parallel(fixture)
    assert [(lesson.subject, lesson.teacher) for lesson in week.cancelled] == [("SP", "HHH")]
    assert week.lesson_changes["01.09.2026|2|SP|HHH"]["kind"] == "cancelled"
    assert "01.09.2026|2|SP|GGG" not in week.lesson_changes


def test_parallel_groups_pair_by_teacher_before_subject():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="SP", teacher="HHH"), raw(4, subject="SP", teacher="ZZZ")],
            plain=[raw(4, subject="SP", teacher="GGG"), raw(4, subject="SP", teacher="HHH")],
        )
    )
    assert list(week.lesson_changes) == ["31.08.2026|4|SP|ZZZ"]
    assert week.lesson_changes["31.08.2026|4|SP|ZZZ"]["previous"]["teacher"] == "GGG"
    assert week.cancelled == []


def test_change_type_on_a_crowded_subject_needs_the_teacher():
    week = parse_timetable(
        payload(
            combined=[raw(4, subject="SP", teacher="GGG"), raw(4, subject="SP", teacher="HHH")],
            plain=[raw(4, subject="SP", teacher="GGG"), raw(4, subject="SP", teacher="HHH")],
            changes=[raw(4, subject="SP", teacher="HHH", type="Entfall"), raw(4, subject="SP", teacher="QQQ", type="Vertretung")],
        )
    )
    assert week.lesson_changes == {"31.08.2026|4|SP|HHH": {"kind": "cancelled", "fields": [], "previous": {"subject": "", "teacher": "", "room": ""}}}


def sport(teacher, room, **extra):
    return raw(3, subject="SP", teacher=teacher, room=room, date_value="01.09.2026", **extra)


def filtered_view(week, chosen, known):
    from app import courses
    from app.mapping import to_display

    lessons = [
        dict(to_display(lesson, {}, change), course_key=courses.regular_course_key(lesson, change))
        for lesson, change in display_rows(week)
    ]
    active = courses.normalize_filter({"chosen": chosen, "known": known})
    return courses.apply({"lessons": lessons, "changes": week.changes}, active)


def shown(view):
    return sorted((lesson["teacher_code"], lesson["room"], lesson["change_kind"], lesson["course_key"]) for lesson in view["lessons"])


def test_one_substitute_for_two_groups_keeps_both_groups_apart():
    week = parse_timetable(
        payload(
            combined=[sport("SCH", "GYM1"), sport("SCH", "GYM2")],
            plain=[sport("MUE", "GYM1"), sport("SCH", "GYM2")],
            changes=[sport("SCH", "GYM1", type="Vertretung")],
        )
    )
    view = filtered_view(week, ["SP|MUE"], ["SP|MUE", "SP|SCH"])
    assert shown(view) == [("SCH", "GYM1", "changed", "SP|MUE")]
    assert view["lessons"][0]["previous"]["teacher"] == "MUE"
    assert view["change_count"] == 1
    assert len(view["changes"]) == 1
    both = filtered_view(week, ["SP|MUE", "SP|SCH"], ["SP|MUE", "SP|SCH"])
    assert shown(both) == [("SCH", "GYM1", "changed", "SP|MUE"), ("SCH", "GYM2", "", "SP|SCH")]


def test_a_substitute_taking_both_groups_does_not_cancel_the_other_group():
    week = parse_timetable(
        payload(
            combined=[sport("SCH", "GYM2")],
            plain=[sport("MUE", "GYM1"), sport("SCH", "GYM2")],
            changes=[sport("SCH", "GYM2", type="Vertretung")],
        )
    )
    view = filtered_view(week, ["SP|MUE"], ["SP|MUE", "SP|SCH"])
    assert shown(view) == [("SCH", "GYM2", "changed", "SP|MUE")]
    assert view["lessons"][0]["previous"]["teacher"] == "MUE"
    assert view["lessons"][0]["previous"]["room"] == "GYM1"
    assert len(view["changes"]) == 1
    assert week.cancelled == []
    other = filtered_view(week, ["SP|SCH"], ["SP|MUE", "SP|SCH"])
    assert shown(other) == [("SCH", "GYM2", "", "SP|SCH")]


def test_a_missing_group_without_a_substitution_note_stays_cancelled():
    week = parse_timetable(
        payload(combined=[sport("SCH", "GYM2")], plain=[sport("MUE", "GYM1"), sport("SCH", "GYM2")])
    )
    view = filtered_view(week, ["SP|MUE"], ["SP|MUE", "SP|SCH"])
    assert shown(view) == [("MUE", "GYM1", "cancelled", "SP|MUE")]


def test_a_change_of_a_hidden_group_named_by_its_regular_teacher_stays_hidden():
    week = parse_timetable(
        payload(
            combined=[sport("MUE", "GYM1"), sport("ZZZ", "GYM2")],
            plain=[sport("MUE", "GYM1"), sport("SCH", "GYM2")],
            changes=[sport("SCH", "GYM2", type="Vertretung")],
        )
    )
    view = filtered_view(week, ["SP|MUE"], ["SP|MUE", "SP|SCH"])
    assert shown(view) == [("MUE", "GYM1", "", "SP|MUE")]
    assert view["changes"] == []
    assert view["change_count"] == 0


def test_groups_of_one_teacher_pair_by_room():
    week = parse_timetable(
        payload(
            combined=[sport("ZZZ", "GYM1"), sport("YYY", "GYM2")],
            plain=[sport("GGG", "GYM2"), sport("HHH", "GYM1")],
        )
    )
    previous = sorted((lesson.teacher, change["previous"]["teacher"]) for lesson, change in display_rows(week))
    assert previous == [("YYY", "GGG"), ("ZZZ", "HHH")]


def test_twin_lessons_keep_their_own_change_entries():
    week = parse_timetable(
        payload(
            combined=[sport("SCH", "GYM1"), sport("SCH", "GYM1")],
            plain=[sport("MUE", "GYM1"), sport("SCH", "GYM1")],
        )
    )
    kinds = sorted((change or {}).get("kind", "") for _, change in display_rows(week))
    assert kinds == ["", "changed"]


def test_display_rows_fall_back_to_keys_for_a_hand_built_week():
    from app.iserv.models import TimetableWeek

    week = parse_timetable(payload(combined=[raw(1, teacher="ZZZ")], plain=[raw(1), raw(2)]))
    bare = TimetableWeek(start_date="", end_date="", last_updated=None, combined=week.combined, plain=week.plain)
    bare.lesson_changes, bare.cancelled = detect_changes(week.combined, week.plain, [])
    rows = display_rows(bare)
    assert [(lesson.period, change["kind"]) for lesson, change in rows] == [(1, "changed"), (2, "cancelled")]


def test_crowded_keys_add_the_room_when_one_teacher_has_two_groups():
    week = parse_timetable(payload(combined=[sport("SCH", "GYM1"), sport("SCH", "GYM2")]))
    crowded = crowded_keys(week.combined)
    assert change_key(week.combined[0], crowded) == "01.09.2026|3|SP|SCH|GYM1"
    assert change_key(week.combined[1], crowded) == "01.09.2026|3|SP|SCH|GYM2"
