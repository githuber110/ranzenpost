import json
from datetime import date, time, timedelta

import pytest

from app.iserv.absences import (
    BODY_FORM,
    berlin_offset,
    BODY_JSON,
    DAY_TODAY,
    DAY_TOMORROW,
    HISTORY_LOCKED,
    KIND_DAYCARE,
    KIND_DEREGISTER,
    KIND_LEAVE,
    KIND_SICK,
    NO_DEFAULT_CONTENT_TYPE,
    build_request,
    delete_path,
    form_fields,
    merge_absence_history,
    normalize_sick_note,
    normalize_user_request,
    prune_absence_history,
    record_absence_history,
    resolve_day,
    seed_absence_history,
    sick_day_options,
    _date_part,
    _epoch,
)

TUESDAY = date(2026, 9, 1)
STUDENT = 16451809


def test_sick_note_matches_captured_request():
    request = build_request(
        KIND_SICK,
        STUDENT,
        {"day_from": DAY_TOMORROW, "day_till": DAY_TOMORROW, "from_period": 1, "till_period": 8},
        today=TUESDAY,
    )
    assert request.path == "sickNotes/"
    assert request.body_mode == BODY_JSON
    assert request.payload == {
        "sickUser": STUDENT,
        "sickFromDate": "2026-09-02",
        "sickTillDate": "2026-09-02",
        "isDutyToReport": False,
        "sickFromLessonNumber": 1,
        "sickTillLessonNumber": 8,
    }


def test_sick_note_omits_empty_comment_and_periods():
    request = build_request(KIND_SICK, STUDENT, {"day_from": DAY_TODAY}, today=TUESDAY)
    assert "note" not in request.payload
    assert "sickFromLessonNumber" not in request.payload
    assert request.payload["sickTillDate"] == "2026-09-01"


def test_sick_note_sends_explicit_periods_for_ganztaegig_from_dynamic_period_config():
    request = build_request(
        KIND_SICK,
        STUDENT,
        {"day_from": DAY_TODAY},
        today=TUESDAY,
        periods=[
            {"number": 1, "name": "1. Stunde"},
            {"number": 2, "name": "2. Stunde"},
            {"number": 5, "name": "5. Stunde"},
        ],
    )
    assert request.payload["sickFromLessonNumber"] == 1
    assert request.payload["sickTillLessonNumber"] == 5


def test_sick_note_keeps_comment():
    request = build_request(
        KIND_SICK, STUDENT, {"day_from": DAY_TODAY, "comment": " Fieber "}, today=TUESDAY
    )
    assert request.payload["note"] == "Fieber"


def test_sick_note_rejects_reversed_range():
    with pytest.raises(ValueError):
        build_request(
            KIND_SICK,
            STUDENT,
            {"day_from": "2026-09-04", "day_till": "2026-09-02"},
            today=TUESDAY,
        )


def test_deregister_matches_captured_request():
    request = build_request(
        KIND_DEREGISTER,
        STUDENT,
        {"deregister_from": "bus", "date": "2026-09-03"},
        today=TUESDAY,
    )
    assert request.path == "user-requests-to-school/not-attend/bus/"
    assert request.body_mode == BODY_FORM
    assert request.headers == NO_DEFAULT_CONTENT_TYPE
    assert request.payload == {
        "student": {"id": STUDENT},
        "type": "not-attend-bus",
        "topic": "",
        "requestDescriptionHtml": "",
        "absentDate": "2026-09-02T22:00:00.000Z",
        "repeatWeekly": False,
        "repeatWeeklyUntil": None,
    }


def test_deregister_uses_winter_offset_in_january():
    request = build_request(
        KIND_DEREGISTER, STUDENT, {"deregister_from": "lunch", "date": "2027-01-12"}
    )
    assert request.payload["absentDate"] == "2027-01-11T23:00:00.000Z"


def test_daycare_matches_captured_request():
    request = build_request(
        KIND_DAYCARE,
        STUDENT,
        {"daycare_kind": "deregister", "repeat": "once", "date": "2026-09-04"},
        today=TUESDAY,
    )
    assert request.path == "user-requests-to-school/not-attend/afternoon-care/"
    assert request.payload == {
        "student": {"id": STUDENT},
        "type": "not-attend-afternoon-care",
        "absentDate": "2026-09-03T22:00:00.000Z",
        "note": None,
        "topic": "",
        "requestDescriptionHtml": "",
        "pickupTime": None,
        "repeatWeekly": False,
        "repeatWeeklyUntil": None,
    }


def test_deregister_sends_repeat_until_as_iso_utc():
    request = build_request(
        KIND_DEREGISTER,
        STUDENT,
        {"deregister_from": "bus", "date": "2026-09-03", "weekly": True, "repeat_until": "2026-10-01"},
        today=TUESDAY,
    )
    assert request.payload["repeatWeekly"] is True
    assert request.payload["repeatWeeklyUntil"] == "2026-09-30T22:00:00.000Z"


def test_daycare_sends_repeat_until_as_iso_utc():
    request = build_request(
        KIND_DAYCARE,
        STUDENT,
        {
            "daycare_kind": "deregister",
            "repeat": "weekly",
            "date": "2026-09-04",
            "repeat_until": "2026-10-02",
        },
        today=TUESDAY,
    )
    assert request.payload["repeatWeekly"] is True
    assert request.payload["repeatWeeklyUntil"] == "2026-10-01T22:00:00.000Z"


def test_daycare_early_end_needs_pickup_time():
    with pytest.raises(ValueError):
        build_request(
            KIND_DAYCARE,
            STUDENT,
            {"daycare_kind": "early_end", "date": "2026-09-04"},
            today=TUESDAY,
        )


def test_daycare_early_end_keeps_pickup_time():
    request = build_request(
        KIND_DAYCARE,
        STUDENT,
        {"daycare_kind": "early_end", "date": "2026-09-04", "pickup_time": "15:00"},
        today=TUESDAY,
    )
    assert request.payload["pickupTime"] == "15:00"


def test_daycare_deregister_drops_pickup_time():
    request = build_request(
        KIND_DAYCARE,
        STUDENT,
        {"daycare_kind": "deregister", "date": "2026-09-04", "pickup_time": "15:00"},
        today=TUESDAY,
    )
    assert request.payload["pickupTime"] is None


def test_leave_uses_unix_seconds():
    request = build_request(
        KIND_LEAVE,
        STUDENT,
        {
            "subject": "Testantrag",
            "body": "Testtext",
            "from_date": "2026-09-04",
            "from_time": "08:00",
            "till_date": "2026-09-04",
            "till_time": "14:00",
        },
        today=TUESDAY,
    )
    assert request.path == "user-requests-to-school/student-absences/"
    assert request.payload["absentFrom"] == 1788501600
    assert request.payload["absentUntil"] == 1788523200
    assert request.payload["requestDescriptionHtml"] == "<p>Testtext</p>"
    assert request.payload["type"] == "student-absence"
    assert request.payload["student"] == {"id": STUDENT}


def test_leave_escapes_html_and_splits_lines():
    request = build_request(
        KIND_LEAVE,
        STUDENT,
        {"subject": "A", "body": "eins <b>\nzwei", "from_date": "2026-09-04"},
        today=TUESDAY,
    )
    assert request.payload["requestDescriptionHtml"] == "<p>eins &lt;b&gt;</p><p>zwei</p>"


def test_leave_carries_attachments_on_the_request():
    request = build_request(
        KIND_LEAVE,
        STUDENT,
        {"subject": "A", "body": "x", "from_date": "2026-09-04"},
        today=TUESDAY,
        attachments=[{"filename": "beleg.pdf", "content": b"x", "content_type": "application/pdf"}],
    )
    assert request.attachments == [
        {"filename": "beleg.pdf", "content": b"x", "content_type": "application/pdf"}
    ]


def test_leave_defaults_to_no_attachments():
    request = build_request(
        KIND_LEAVE, STUDENT, {"subject": "A", "body": "x", "from_date": "2026-09-04"}, today=TUESDAY
    )
    assert request.attachments == []


def test_leave_requires_subject_and_body():
    with pytest.raises(ValueError):
        build_request(KIND_LEAVE, STUDENT, {"body": "x", "from_date": "2026-09-04"})
    with pytest.raises(ValueError):
        build_request(KIND_LEAVE, STUDENT, {"subject": "x", "from_date": "2026-09-04"})


def test_form_fields_carry_single_data_entry():
    request = build_request(
        KIND_DEREGISTER, STUDENT, {"deregister_from": "lunch", "date": "2026-09-03"}
    )
    fields = form_fields(request.payload)
    assert list(fields) == ["data"]
    assert json.loads(fields["data"])["type"] == "not-attend-lunch"


def test_a_sick_note_has_no_delete_path_at_all():
    with pytest.raises(ValueError):
        delete_path(KIND_SICK, 7)


def test_delete_paths_have_no_trailing_slash():
    assert delete_path(KIND_LEAVE, 7) == "user-requests-to-school/student-absences/7"
    assert (
        delete_path(KIND_DAYCARE, 7)
        == "user-requests-to-school/not-attend/afternoon-care/7"
    )
    assert (
        delete_path(KIND_DEREGISTER, 7, "kindergarten")
        == "user-requests-to-school/not-attend/kindergarten/7"
    )


def test_delete_deregister_needs_target():
    with pytest.raises(ValueError):
        delete_path(KIND_DEREGISTER, 7)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        build_request("phantasie", STUDENT, {})


def test_missing_student_is_rejected():
    with pytest.raises(ValueError):
        build_request(KIND_SICK, None, {"day_from": DAY_TODAY})


def test_sick_day_options_offer_today_and_tomorrow_only():
    options = sick_day_options(TUESDAY)
    assert [item["label"] for item in options["from"]] == ["Heute", "Morgen"]


def test_sick_day_options_run_six_days_from_tuesday():
    options = sick_day_options(TUESDAY)
    assert [item["label"] for item in options["till"]] == [
        "Heute",
        "Morgen",
        "Donnerstag, 03.09.",
        "Freitag, 04.09.",
        "Samstag, 05.09.",
        "Sonntag, 06.09.",
    ]


def test_every_start_day_keeps_at_least_one_end_day():
    for offset in range(0, 7):
        day = date(2026, 8, 31) + timedelta(days=offset)
        options = sick_day_options(day)
        ends = [item["value"] for item in options["till"]]
        for start in options["from"]:
            reachable = [value for value in ends if value >= start["value"]]
            assert reachable, f"{day} would leave an empty end list for {start['label']}"


def test_sick_day_options_on_wednesday_roll_into_next_monday():
    options = sick_day_options(date(2026, 9, 2))
    labels = [item["label"] for item in options["till"]]
    values = [item["value"] for item in options["till"]]
    assert len(labels) == 6
    assert labels[0] == "Heute"
    assert labels[1] == "Morgen"
    assert labels[-1] == "Montag, 07.09."
    assert values[-1] == "2026-09-07"


def test_sick_day_options_on_friday_roll_into_next_wednesday():
    options = sick_day_options(date(2026, 9, 4))
    labels = [item["label"] for item in options["till"]]
    values = [item["value"] for item in options["till"]]
    assert len(labels) == 6
    assert labels[0] == "Heute"
    assert labels[1] == "Morgen"
    assert labels[-1] == "Mittwoch, 09.09."
    assert values[-1] == "2026-09-09"


def test_sick_day_options_on_sunday_reach_into_next_friday():
    options = sick_day_options(date(2026, 9, 6))
    labels = [item["label"] for item in options["till"]]
    values = [item["value"] for item in options["till"]]
    assert len(labels) == 6
    assert labels[0] == "Heute"
    assert labels[1] == "Morgen"
    assert labels[-1] == "Freitag, 11.09."
    assert values[-1] == "2026-09-11"


def test_resolve_day_keeps_explicit_dates():
    assert resolve_day("2026-12-24", TUESDAY) == "2026-12-24"
    assert resolve_day(DAY_TOMORROW, TUESDAY) == "2026-09-02"
    assert resolve_day("", TUESDAY) is None


def test_normalize_sick_note_reads_string_fields():
    entry = normalize_sick_note(
        {
            "id": 4,
            "sickFromDateAsString": "2026-09-01",
            "sickTillDateAsString": "2026-09-02",
            "note": "Fieber",
            "isDutyToReport": True,
            "sickFromLessonNumber": 1,
        }
    )
    assert entry["kind"] == KIND_SICK
    assert entry["from_date"] == "2026-09-01"
    assert entry["comment"] == "Fieber"
    assert entry["duty_to_report"] is True
    assert entry["deletable"] is False
    assert "Sekretariat" in entry["locked_reason"]
    assert entry["status"] == ""


def test_normalize_user_request_keeps_answered_entries_deletable():
    entry = normalize_user_request({"id": 9, "accepted": True}, KIND_LEAVE)
    assert entry["status"] == "accepted"
    assert entry["deletable"] is True, "IServ accepted these live and still allowed the DELETE"
    assert entry["locked_reason"] == ""


def test_normalize_user_request_keeps_open_entries_deletable():
    entry = normalize_user_request(
        {"id": 9, "accepted": None, "absentDate": "2026-09-03T22:00:00+00:00"},
        KIND_DEREGISTER,
        "bus",
    )
    assert entry["status"] == "open"
    assert entry["deletable"] is True
    assert entry["from_date"] == "2026-09-03"
    assert entry["label"] == "Abmeldung Bus"


def test_a_sick_note_can_never_be_withdrawn_by_a_parent():
    entry = normalize_sick_note({"id": 1})
    assert entry["deletable"] is False, "IServ refuses DELETE on sickNotes for guardian accounts"


def test_normalize_sick_note_carries_technical_fields():
    entry = normalize_sick_note(
        {
            "id": 7000001,
            "createdAt": 1788273476,
            "sickUser": {
                "id": 16000001,
                "displayname": "Example Alex",
                "mainCourse": {"externalId": "klasse.01d", "name": "Klasse 01D"},
            },
            "reporter": {"displayname": "Example Guardian"},
            "hasWrittenConfirmation": False,
            "isDutyToReport": True,
            "needsOfficialConfirmation": False,
            "hasOfficialConfirmation": False,
            "isCountedAsAnAbsenceInStatistics": True,
        }
    )
    assert entry["technical"] == {
        "id": 7000001,
        "created_at": 1788273476,
        "reporter": "Example Guardian",
        "duty_to_report": True,
        "class_code": "klasse.01d",
        "has_written_confirmation": False,
        "needs_official_confirmation": False,
        "has_official_confirmation": False,
        "counted_in_statistics": True,
    }


def test_normalize_sick_note_technical_fields_default_safely_without_sick_user():
    entry = normalize_sick_note({"id": 1, "sickUser": 16000001})
    assert entry["technical"]["class_code"] == ""
    assert entry["technical"]["reporter"] == ""


def test_normalize_user_request_carries_technical_fields_and_repeat_until():
    entry = normalize_user_request(
        {
            "id": 42,
            "createdAt": 1700000000,
            "updatedAt": 1700003600,
            "author": {"displayname": "Example Guardian"},
            "responseAuthor": {"displayname": "Example Teacher"},
            "repeatWeekly": True,
            "repeatWeeklyUntil": "2026-12-24",
            "staticFiles": [],
        },
        KIND_LEAVE,
    )
    assert entry["weekly"] is True
    assert entry["repeat_until"] == "2026-12-24"
    assert entry["attachments"] == []
    assert entry["technical"] == {
        "id": 42,
        "created_at": 1700000000,
        "updated_at": 1700003600,
        "author": "Example Guardian",
        "response_author": "Example Teacher",
    }


def test_normalize_user_request_normalizes_static_files():
    entry = normalize_user_request(
        {
            "id": 43,
            "staticFiles": [
                {
                    "id": 1,
                    "originalFilename": "reparatur.pdf",
                    "extension": "pdf",
                    "mimetype": "application/pdf",
                    "size": 100,
                    "filename": "abc123-1.pdf",
                }
            ],
        },
        KIND_LEAVE,
    )
    assert entry["attachments"] == [
        {
            "id": 1,
            "filename": "reparatur.pdf",
            "extension": "pdf",
            "mimetype": "application/pdf",
            "size": 100,
            "file": "abc123-1.pdf",
        }
    ]


def test_summer_time_starts_on_the_last_sunday_in_march():
    assert _iso("2026-03-28") == "2026-03-27T23:00:00.000Z"
    assert _iso("2026-03-29") == "2026-03-28T23:00:00.000Z"
    assert _iso("2026-03-30") == "2026-03-29T22:00:00.000Z"


def test_summer_time_ends_on_the_last_sunday_in_october():
    assert _iso("2026-10-25") == "2026-10-24T22:00:00.000Z"
    assert _iso("2026-10-26") == "2026-10-25T23:00:00.000Z"


def test_a_march_date_is_not_shifted_to_the_day_before():
    assert _iso("2026-03-10").startswith("2026-03-09T23")


def test_the_offset_follows_the_wall_clock_on_the_switch_day():
    from datetime import datetime

    assert berlin_offset(datetime(2026, 3, 29, 0, 0)) == 1
    assert berlin_offset(datetime(2026, 3, 29, 8, 0)) == 2
    assert berlin_offset(datetime(2026, 10, 25, 0, 0)) == 2
    assert berlin_offset(datetime(2026, 10, 26, 0, 0)) == 1


def test_date_part_reads_the_captured_incident_epoch_as_the_correct_berlin_day():
    assert _date_part(1788300000) == "2026-09-02"


def test_date_part_handles_a_winter_epoch_crossing_midnight():
    assert _date_part(1796166000) == "2026-12-02"


def test_date_part_handles_all_four_2026_dst_edges():
    assert _date_part(_epoch(date(2026, 3, 28), time(23, 30))) == "2026-03-28"
    assert _date_part(_epoch(date(2026, 3, 29), time(0, 30))) == "2026-03-29"
    assert _date_part(_epoch(date(2026, 10, 24), time(23, 30))) == "2026-10-24"
    assert _date_part(_epoch(date(2026, 10, 25), time(0, 30))) == "2026-10-25"


def test_date_part_roundtrips_every_day_of_2026():
    day = date(2026, 1, 1)
    end = date(2027, 1, 1)
    while day < end:
        assert _date_part(_epoch(day, time(0, 0))) == day.isoformat()
        day += timedelta(days=1)


def test_date_part_converts_a_utc_z_string_across_midnight():
    assert _date_part("2026-09-01T22:00:00.000Z") == "2026-09-02"


def test_date_part_keeps_a_plain_date_string_untouched():
    assert _date_part("2026-09-01") == "2026-09-01"


def test_record_absence_history_keys_by_id():
    history = record_absence_history({}, [{"id": 5, "kind": KIND_SICK, "till_date": "2026-09-01"}])
    assert "5" in history
    assert history["5"]["kind"] == KIND_SICK
    assert "seen_at" in history["5"]


def test_record_absence_history_skips_entries_without_id():
    history = record_absence_history({}, [{"kind": KIND_SICK, "till_date": "2026-09-01"}])
    assert history == {}


def test_record_absence_history_overwrites_the_same_id():
    history = record_absence_history({}, [{"id": 5, "status": "open"}])
    history = record_absence_history(history, [{"id": 5, "status": "accepted"}])
    assert history["5"]["status"] == "accepted"


def test_prune_absence_history_drops_entries_older_than_30_days():
    history = {
        "old": {"id": 1, "till_date": "2026-07-01"},
        "fresh": {"id": 2, "till_date": "2026-08-20"},
    }
    pruned = prune_absence_history(history, today=date(2026, 9, 2))
    assert list(pruned) == ["fresh"]


def test_prune_absence_history_keeps_entry_exactly_30_days_old():
    history = {"boundary": {"id": 1, "till_date": "2026-08-03"}}
    pruned = prune_absence_history(history, today=date(2026, 9, 2))
    assert "boundary" in pruned


def test_prune_absence_history_drops_undated_entries():
    history = {"broken": {"id": 1}}
    assert prune_absence_history(history, today=date(2026, 9, 2)) == {}


def test_merge_absence_history_adds_vanished_entry_marked_from_history():
    live = []
    history = {"7": {"id": 7, "kind": KIND_SICK, "till_date": "2026-08-20", "deletable": False}}
    merged = merge_absence_history(live, history, today=date(2026, 9, 2))
    assert len(merged) == 1
    assert merged[0]["from_history"] is True
    assert merged[0]["deletable"] is False
    assert merged[0]["locked_reason"] == HISTORY_LOCKED
    assert "seen_at" not in merged[0]


def test_merge_absence_history_prefers_live_entry_over_history_duplicate():
    live = [{"id": 7, "kind": KIND_SICK, "status": "open"}]
    history = {"7": {"id": 7, "kind": KIND_SICK, "status": "stale", "till_date": "2026-08-20"}}
    merged = merge_absence_history(live, history, today=date(2026, 9, 2))
    assert len(merged) == 1
    assert merged[0]["status"] == "open"
    assert "from_history" not in merged[0]


def test_merge_absence_history_drops_history_entries_older_than_30_days():
    live = []
    history = {"7": {"id": 7, "till_date": "2026-07-01"}}
    merged = merge_absence_history(live, history, today=date(2026, 9, 2))
    assert merged == []


def test_seed_absence_history_adds_a_given_entry_once():
    entry = {"id": 42, "kind": KIND_SICK, "till_date": "2026-09-01"}
    history = seed_absence_history({}, entry)
    assert history["42"] == entry
    again = seed_absence_history(history, entry)
    assert again["42"] == entry


def test_seed_absence_history_does_not_override_an_already_recorded_entry():
    history = record_absence_history({}, [{"id": 42, "status": "changed"}])
    seeded = seed_absence_history(history, {"id": 42, "status": "seed-default"})
    assert seeded["42"]["status"] == "changed"


def test_seed_absence_history_ignores_an_entry_without_id():
    assert seed_absence_history({}, {"status": "no id"}) == {}


def _iso(day):
    request = build_request(
        KIND_DEREGISTER, STUDENT, {"deregister_from": "bus", "date": day}
    )
    return request.payload["absentDate"]
