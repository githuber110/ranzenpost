import json
from datetime import date

from app.iserv.timetable import (
    build_filter,
    detect_changes,
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


def test_duplicate_plain_slots_yield_one_cancelled_entry():
    week = parse_timetable(payload(combined=[], plain=[raw(5), raw(5, teacher="BBB")]))
    assert len(week.cancelled) == 1
    assert week.lesson_changes["31.08.2026|5|D"]["kind"] == "cancelled"


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
