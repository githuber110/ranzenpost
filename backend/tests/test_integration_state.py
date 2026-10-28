from datetime import datetime, timedelta, timezone

from app import holidays, integration
from app.marks import MarkRegistry

from tests.test_calendar_feed import FakeHolidayCalendar, _day, _lesson, _snapshot
from tests.test_integration_api import (
    CHILD_ID,
    CHILD_QUERY,
    NOW_EPOCH,
    PREFIX,
    SCHOOL,
    SECOND_CHILD_ID,
    THURSDAY,
    WEDNESDAY,
    Clock,
    _app,
    _auth,
    _today_snapshot,
)

SATURDAY = datetime(2026, 9, 5, 1, 50)
CURRENT_INTEGRATION = "2611.1.0"
RELEASED_INTEGRATION = "2610.5.0"
SATURDAY_EPOCH = int(SATURDAY.replace(tzinfo=timezone.utc).timestamp())
MONDAY = "07.09.2026"
LETTERS = [
    {"title": "Wandertag", "sender": "Frau Muster", "published": "01.09.2026 14:02", "child": "Zwiebelfisch Quastenflosser", "unread": True},
    {"title": "Elternabend", "sender": "Herr Beispiel", "published": "31.08.2026 09:15", "child": "Kraakebolle Nebelkraehe", "unread": True},
]
POSTS = [{"title": "Mensa", "owner": "Sekretariat", "unread": True}]


def _saturday_snapshot(store):
    lessons = [
        _lesson(day=WEDNESDAY, period=1),
        _lesson(day=THURSDAY, period=2),
        _lesson(day=MONDAY, period=2, subject_code="MA", subject_label="Mathe", teacher_code="OTT", teacher_label="Otte", room="R2"),
        _lesson(day=MONDAY, period=1, subject_code="D", subject_label="Deutsch", teacher_surname="Behrens"),
        _lesson(day=MONDAY, period=3, subject_code="SP", subject_label="Sport", change_kind="cancelled"),
    ]
    store.save_calendar_snapshot(_snapshot(lessons))
    marks = MarkRegistry(store, clock=lambda: SATURDAY_EPOCH)
    marks.create(CHILD_ID, "2026-09-09", 2, "MA", "Klassenarbeit")
    marks.create(CHILD_ID, "2026-09-11", 1, "D", "")
    marks.create(CHILD_ID, "2026-10-20", 1, "D", "Zu spaet")
    marks.create(CHILD_ID, "2026-09-01", 1, "D", "Vorbei")
    marks.create(SECOND_CHILD_ID, "2026-09-08", 1, "D", "Fremd")
    integration.record_school_poll(
        store,
        SCHOOL,
        SATURDAY_EPOCH - 60,
        True,
        letters=integration.unread_notices(LETTERS),
        posts=integration.unread_notices(POSTS),
    )


def _current(store, version=CURRENT_INTEGRATION):
    return dict(_auth(store), **{"X-Ranzenpost-Integration": version})


def _state(tmp_path, snapshot, epoch, calendar=None, child=CHILD_QUERY):
    client, store, _ = _app(tmp_path, clock=Clock(epoch), calendar=calendar)
    snapshot(store)
    return client.get(PREFIX + f"/state?{child}", headers=_auth(store)).json()


def test_on_a_saturday_night_the_next_lesson_is_the_first_lesson_on_monday(tmp_path):
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH)

    assert body["now_lesson"] is None
    assert body["next_lesson"] == {
        "date": "2026-09-07",
        "weekday": "monday",
        "period": 1,
        "subject": "Deutsch",
        "subject_code": "D",
        "teacher": "Behrens",
        "room": "R1",
        "start": "2026-09-07T08:00:00+02:00",
        "end": "2026-09-07T08:45:00+02:00",
        "substitution": False,
        "cancelled": False,
        "kind": "",
        "moved": "",
        "before": {},
        "after": {},
        "note": "",
        "minutes_until": 2 * 24 * 60 + 4 * 60 + 10,
        "minutes_left": 2 * 24 * 60 + 4 * 60 + 55,
    }
    assert body["school_day_today"] is False
    assert body["school_end_today"] is None
    assert body["changes_today"] == []


def test_the_next_school_day_skips_the_weekend_and_counts_only_held_lessons(tmp_path):
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH)

    assert body["next_school_day"] == {
        "date": "2026-09-07",
        "weekday": "monday",
        "days_until": 2,
        "start": "2026-09-07T08:00:00+02:00",
        "end": "2026-09-07T09:35:00+02:00",
        "lessons": 2,
        "first_lesson": "Deutsch",
    }


def test_the_next_school_day_is_tomorrow_on_a_school_morning(tmp_path):
    body = _state(tmp_path, _today_snapshot, NOW_EPOCH)

    assert body["next_school_day"]["date"] == "2026-09-03"
    assert body["next_school_day"]["weekday"] == "thursday"
    assert body["next_school_day"]["days_until"] == 1
    assert body["next_school_day"]["start"] == "2026-09-03T08:50:00+02:00"
    assert body["next_school_day"]["lessons"] == 1
    assert "school_start_tomorrow" not in body


def test_the_next_school_day_is_today_before_the_first_lesson_starts(tmp_path):
    before_first_lesson = int(datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc).timestamp())

    body = _state(tmp_path, _today_snapshot, before_first_lesson)

    assert body["next_school_day"]["date"] == "2026-09-02"
    assert body["next_school_day"]["weekday"] == "wednesday"
    assert body["next_school_day"]["days_until"] == 0
    assert body["next_school_day"]["start"] == "2026-09-02T08:00:00+02:00"
    assert body["next_school_day"]["lessons"] == 3
    assert body["next_school_day"]["first_lesson"] == "Deutsch"


def test_the_next_school_day_is_today_just_after_midnight_local_time(tmp_path):
    just_after_midnight = int(datetime(2026, 9, 1, 22, 10, tzinfo=timezone.utc).timestamp())

    body = _state(tmp_path, _today_snapshot, just_after_midnight)

    assert body["next_school_day"]["date"] == "2026-09-02"
    assert body["next_school_day"]["days_until"] == 0
    assert body["next_school_day"]["start"] == "2026-09-02T08:00:00+02:00"


def test_the_next_school_day_moves_on_once_todays_first_held_lesson_started(tmp_path):
    after_start = int(datetime(2026, 9, 2, 6, 5, tzinfo=timezone.utc).timestamp())

    body = _state(tmp_path, _today_snapshot, after_start)

    assert body["next_school_day"]["date"] == "2026-09-03"
    assert body["next_school_day"]["days_until"] == 1


def test_the_next_school_day_skips_a_fully_cancelled_today(tmp_path):
    from app.cancellations import CancellationRegistry

    before_first_lesson = int(datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc).timestamp())
    client, store, _ = _app(tmp_path, clock=Clock(before_first_lesson))
    _today_snapshot(store)
    cancellations = CancellationRegistry(store, clock=lambda: before_first_lesson)
    cancellations.create(CHILD_ID, "2026-09-02", 1)
    cancellations.create(CHILD_ID, "2026-09-02", 2)
    cancellations.create(CHILD_ID, "2026-09-02", 3)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["next_school_day"]["date"] == "2026-09-03"
    assert body["next_school_day"]["days_until"] == 1
    assert body["next_school_day"]["first_lesson"] == "Deutsch"


def test_a_holiday_week_pushes_the_next_school_day_behind_it(tmp_path):
    calendar = FakeHolidayCalendar(
        days={f"2026-09-{day:02d}": _day(free=True, overrides=True, kind="school", name="Ferien") for day in range(7, 12)}
    )
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH, calendar=calendar)

    assert body["next_lesson"] is None
    assert body["next_school_day"] is None


def test_the_next_exam_and_the_upcoming_exams_come_from_the_marks(tmp_path):
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH)

    assert body["next_exam"] == {
        "date": "2026-09-09",
        "weekday": "wednesday",
        "days_until": 4,
        "period": 2,
        "subject": "Mathe",
        "subject_code": "MA",
        "name": "Klassenarbeit",
        "start": "2026-09-09T08:50:00+02:00",
        "end": "2026-09-09T09:35:00+02:00",
        "teacher": "",
        "room": "",
    }
    assert body["exams_upcoming"]["count"] == 2
    assert [item["date"] for item in body["exams_upcoming"]["items"]] == ["2026-09-09", "2026-09-11"]
    assert body["exams_upcoming"]["items"][1]["name"] == ""
    assert body["exams_upcoming"]["items"][1]["subject"] == "Deutsch"
    assert body["exams_upcoming"]["days"] == integration.EXAM_DAYS_AHEAD


def test_an_exam_names_teacher_and_room_from_a_fresh_week(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(NOW_EPOCH))
    _today_snapshot(store)
    snapshot = store.load_calendar_snapshot()
    snapshot["children"][CHILD_ID]["weeks"]["31.08.2026"]["fetched_at"] = NOW_EPOCH - 60
    store.save_calendar_snapshot(snapshot)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-03", 2, "D", "Diktat")

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["next_exam"]["teacher"] == "Behrens"
    assert body["next_exam"]["room"] == "R1"
    assert body["next_exam"]["days_until"] == 1


def test_a_child_without_marks_has_no_exam_and_an_empty_list(tmp_path):
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH, child=f"child={SECOND_CHILD_ID}")

    assert body["next_exam"]["name"] == "Fremd"
    body = _state(tmp_path / "other", _today_snapshot, NOW_EPOCH, child=f"child={SECOND_CHILD_ID}")
    assert body["next_exam"] is None
    assert body["exams_upcoming"] == {"count": 0, "items": [], "days": integration.EXAM_DAYS_AHEAD}


def test_unread_letters_and_posts_carry_title_sender_date_and_first_name(tmp_path):
    body = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH)

    assert body["unread_letters"] == {
        "count": 1,
        "items": [{"title": "Wandertag", "sender": "Frau Muster", "date": "2026-09-01", "child": "Zwiebelfisch"}],
    }
    assert body["unread_posts"] == {
        "count": 1,
        "items": [{"title": "Mensa", "sender": "Sekretariat", "date": "", "child": ""}],
    }


def test_the_notice_list_is_capped_at_ten_while_the_count_stays_honest(tmp_path):
    client, store, _ = _app(tmp_path)
    letters = [{"title": f"Brief {index}", "unread": True} for index in range(14)]
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=integration.unread_notices(letters))

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["unread_letters"]["count"] == 14
    assert len(body["unread_letters"]["items"]) == integration.MAX_NOTICES
    assert body["unread_letters"]["items"][0] == {"title": "Brief 0", "sender": "", "date": "", "child": ""}


def test_titles_stored_by_an_older_build_still_become_notices(tmp_path):
    client, store, _ = _app(tmp_path)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=["Alt"], posts=["Post"])

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["unread_letters"] == {"count": 1, "items": [{"title": "Alt", "sender": "", "date": "", "child": ""}]}
    assert body["unread_posts"]["items"][0]["title"] == "Post"


def test_unread_notices_keep_only_unread_entries_and_squeeze_whitespace():
    entries = [
        {"title": "  Zwei   Worte ", "sender": " X ", "published": "02.09.2026", "child": "Kind Name", "unread": True},
        {"title": "Gelesen", "unread": False},
        "junk",
    ]

    assert integration.unread_notices(entries) == [
        {"title": "Zwei Worte", "sender": "X", "date": "2026-09-02", "child": "Kind"}
    ]


def test_a_notice_names_the_given_name_of_a_surname_first_child():
    entry = {"title": "Brief", "published": "02.09.2026", "child": "Quastenflosser,  Zwiebelfisch", "unread": True}

    assert integration.notice_of(entry)["child"] == "Zwiebelfisch"


def test_a_lesson_on_a_school_morning_names_period_weekday_kind_and_the_change(tmp_path):
    body = _state(tmp_path, _today_snapshot, NOW_EPOCH)

    assert body["now_lesson"]["date"] == "2026-09-02"
    assert body["now_lesson"]["weekday"] == "wednesday"
    assert body["now_lesson"]["period"] == 1
    assert body["now_lesson"]["kind"] == ""
    assert body["now_lesson"]["minutes_until"] == 0
    assert body["now_lesson"]["minutes_left"] == 35
    assert body["next_lesson"]["period"] == 2
    assert body["next_lesson"]["kind"] == "room_change"
    assert body["next_lesson"]["before"] == {"room": "R1"}
    assert body["next_lesson"]["after"] == {"room": "R7"}
    assert body["next_lesson"]["minutes_until"] == 40
    assert [(item["period"], item["kind"]) for item in body["changes_today"]] == [(2, "room_change"), (4, "cancellation")]
    assert body["changes_today"][1]["before"] == {}
    assert body["changes_today"][1]["substitution"] is False


def test_the_timetable_stamp_falls_back_to_the_last_fetch_and_names_its_source(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(NOW_EPOCH))
    _today_snapshot(store)
    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    assert body["timetable_last_updated"] == "2026-09-02T06:00:00+02:00"
    assert body["timetable_last_updated_source"] == "iserv"

    store.update_connection(SCHOOL, poll_state={CHILD_ID: {"last_updated": None}})
    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    assert body["timetable_last_updated"] == "2026-09-02T08:00:00+02:00"
    assert body["timetable_last_updated_source"] == "app"

    client, store, _ = _app(tmp_path / "bare")
    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    assert body["timetable_last_updated"] is None
    assert body["timetable_last_updated_source"] == ""


def test_the_school_names_days_until_and_the_conference_details(tmp_path):
    calendar = FakeHolidayCalendar(
        days={"2026-10-05": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1")}
    )
    client, store, _ = _app(tmp_path, calendar=calendar)
    integration.record_school_poll(
        store, SCHOOL, NOW_EPOCH, True, conferences=[["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]]
    )

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert body["next_holiday"] == {"name": "Herbstferien", "start": "2026-10-05", "end": "2026-10-05", "days_until": 33}
    assert body["next_conference"] == {
        "date": "2026-09-15",
        "title": "Frau Muster · Raum 101",
        "details": ["Frau Muster", "Raum 101", "Termin buchen"],
        "days_until": 13,
    }


def test_a_conference_date_inside_a_longer_cell_is_found_and_left_out_of_the_title(tmp_path):
    client, store, _ = _app(tmp_path, calendar=FakeHolidayCalendar(days={}))
    integration.record_school_poll(
        store,
        SCHOOL,
        NOW_EPOCH,
        True,
        conferences=[["Elternsprechtag Herbst", "Donnerstag, 17.09.2026, 14:00 - 18:00 Uhr", "Buchungszeitraum: 01.09.2026 - 10.09.2026"]],
    )

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert body["next_conference"]["date"] == "2026-09-17"
    assert body["next_conference"]["title"] == "Elternsprechtag Herbst · Buchungszeitraum: 01.09.2026 - 10.09.2026"
    assert "Donnerstag, 17.09.2026, 14:00 - 18:00 Uhr" in body["next_conference"]["details"]
    assert "/iserv/" not in str(body["next_conference"])


def test_a_running_holiday_counts_zero_days(tmp_path):
    calendar = FakeHolidayCalendar(
        days={"2026-09-02": _day(free=True, overrides=True, kind="school", name="Ferien", period_id="h1")}
    )
    client, store, _ = _app(tmp_path, calendar=calendar)

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert body["next_holiday"]["days_until"] == 0


def test_info_names_the_last_successful_poll_of_each_school(tmp_path):
    client, store, _ = _app(tmp_path)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 120, True)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 60, False, integration.ERROR_NETWORK)

    school = client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]

    assert school["last_success"] == "2026-09-02T08:08:00+02:00"
    assert school["last_poll"] == "2026-09-02T08:09:00+02:00"
    assert school["status"] == "error"


def test_exam_and_absence_events_name_the_mark_and_the_kind(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-03", 2, "D", "Diktat")

    exams = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=exams", headers=_auth(store)).json()
    absences = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=absences", headers=_auth(store)).json()
    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons", headers=_auth(store)).json()

    assert exams[0]["name"] == "Diktat" and exams[0]["kind"] == ""
    assert absences[0]["kind"] == "sick" and absences[0]["name"] == ""
    assert all(event["name"] == "" and event["kind"] == "" for event in lessons)

def test_lesson_events_name_their_own_substitution(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-02&end=2026-09-02", headers=_auth(store)).json()
    timed = sorted((event for event in lessons if not event["all_day"]), key=lambda event: event["start"])

    assert [(event["start"][11:16], event["cancelled"], event["substitution"]) for event in timed] == [
        ("08:00", False, False),
        ("08:50", False, True),
        ("09:45", False, False),
        ("10:30", True, False),
    ]


def _parallel_snapshot(store):
    lessons = [
        _lesson(day=WEDNESDAY, period=6, subject_code="G", subject_label="G", teacher_code="", teacher_label="", room="A3.07", start_time="12:10", change_kind="cancelled"),
        _lesson(day=WEDNESDAY, period=6, subject_code="GB", subject_label="G-bili", teacher_code="", teacher_label="", room="A3.07", start_time="12:10", change_kind="cancelled"),
    ]
    store.save_calendar_snapshot(_snapshot(lessons))


def test_two_parallel_cancelled_lessons_stay_two_changes_with_their_own_subject(tmp_path):
    body = _state(tmp_path, _parallel_snapshot, NOW_EPOCH)

    changes = body["changes_today"]
    assert [(item["start"], item["subject_code"], item["cancelled"]) for item in changes] == [
        ("2026-09-02T12:10:00+02:00", "G", True),
        ("2026-09-02T12:10:00+02:00", "GB", True),
    ]


def _hour_school_snapshot(store):
    store.update_connection(SCHOOL, period_grid={"lessons": {"1": {"duration": 60}}})
    lessons = [
        _lesson(day=WEDNESDAY, period=1),
        dict(_lesson(day=WEDNESDAY, period=3, subject_code="MA", subject_label="Mathe", start_time="09:45"), end_time="10:55"),
    ]
    store.save_calendar_snapshot(_snapshot(lessons))
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-09", 1, "D", "Diktat")


def test_lesson_and_exam_ends_follow_the_school_lesson_length(tmp_path):
    body = _state(tmp_path, _hour_school_snapshot, NOW_EPOCH)

    assert body["now_lesson"]["end"] == "2026-09-02T09:00:00+02:00"
    assert body["now_lesson"]["minutes_left"] == 50
    assert body["next_lesson"]["end"] == "2026-09-02T10:55:00+02:00"
    assert body["school_end_today"] == "2026-09-02T10:55:00+02:00"
    assert body["next_exam"]["end"] == "2026-09-09T09:00:00+02:00"


def _broken_times_snapshot(store):
    store.update_connection(SCHOOL, period_times={"1": "8:00 Uhr", "2": "25:99", "5": "08:00:00"})
    lessons = [
        _lesson(day=WEDNESDAY, period=1, start_time="09:00:00"),
        _lesson(day=WEDNESDAY, period=3, subject_code="MA", subject_label="Mathe", start_time="kaputt"),
    ]
    snapshot = _snapshot(lessons)
    snapshot["children"][CHILD_ID]["absences"] = [
        {"id": 7, "kind": "leave", "status": "accepted", "from_date": "2026-09-03", "till_date": "2026-09-03", "from_period": 1, "till_period": 2, "label_key": "absence.kind.leave"},
        {"id": 8, "kind": "leave", "status": "accepted", "from_date": "2026-09-04", "till_date": "2026-09-04", "from_period": 5, "till_period": 5, "label_key": "absence.kind.leave"},
    ]
    store.save_calendar_snapshot(snapshot)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-03", 2, "D", "Diktat")


def test_a_broken_period_time_never_turns_state_or_events_into_an_error(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(NOW_EPOCH))
    _broken_times_snapshot(store)

    state = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store))
    exams = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=exams", headers=_auth(store))
    absences = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=absences", headers=_auth(store))
    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons", headers=_auth(store))

    assert [response.status_code for response in (state, exams, absences, lessons)] == [200, 200, 200, 200]
    assert state.json()["next_lesson"]["start"] == "2026-09-02T09:00:00+02:00"
    assert exams.json()[0]["all_day"] is True
    assert [event["all_day"] for event in absences.json()] == [True, False]
    assert absences.json()[1]["start"] == "2026-09-04T08:00:00+02:00"
    timed = [event for event in lessons.json() if not event["all_day"]]
    assert [event["start"] for event in timed] == ["2026-09-02T09:00:00+02:00"]


CHILD_NAME_FIRST = "Zwiebelfisch"
LESSON_FIELDS = sorted(integration.TODAY_FIELDS + (integration.FIELD_NEXT_LESSON, integration.FIELD_NEXT_SCHOOL_DAY))


def _epoch(*parts):
    return int(datetime(*parts, tzinfo=timezone.utc).timestamp())


def _year_end_snapshot(store):
    lessons = [_lesson(day="30.12.2026", period=1), _lesson(day="04.01.2027", period=1)]
    store.save_calendar_snapshot(_snapshot(lessons, week="28.12.2026"))


def test_unknown_holiday_dates_make_the_lesson_fields_unknown_instead_of_empty(tmp_path):
    body = _state(tmp_path, _today_snapshot, NOW_EPOCH, calendar=FakeHolidayCalendar(status=holidays.STATUS_UNKNOWN))

    assert body["unknown"] == LESSON_FIELDS
    assert body["now_lesson"] is None and body["next_lesson"] is None and body["next_school_day"] is None


def test_without_a_holiday_region_the_lessons_show_unfiltered_like_in_the_app(tmp_path):
    body = _state(tmp_path, _today_snapshot, NOW_EPOCH, calendar=FakeHolidayCalendar(status=holidays.STATUS_DISABLED))

    assert body["unknown"] == []
    assert body["now_lesson"]["period"] == 1
    assert body["school_day_today"] is True


def test_a_known_day_stays_known_when_only_the_next_year_lacks_holiday_dates(tmp_path):
    calendar = FakeHolidayCalendar(missing_years=[2027])

    morning = _state(tmp_path, _year_end_snapshot, _epoch(2026, 12, 30, 6, 30), calendar=calendar)
    evening = _state(tmp_path / "later", _year_end_snapshot, _epoch(2026, 12, 30, 17, 0), calendar=calendar)

    assert morning["unknown"] == []
    assert morning["next_lesson"]["date"] == "2026-12-30"
    assert morning["next_school_day"]["date"] == "2026-12-30"
    assert evening["unknown"] == ["next_lesson", "next_school_day"]
    assert evening["next_lesson"] is None
    assert evening["school_day_today"] is True


def test_the_lessons_calendar_of_home_assistant_needs_no_holiday_region(tmp_path):
    client, store, _ = _app(tmp_path, calendar=FakeHolidayCalendar(status=holidays.STATUS_DISABLED))
    _today_snapshot(store)

    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-02&end=2026-09-02", headers=_auth(store)).json()

    assert len([event for event in lessons if not event["all_day"]]) == 4
    assert not any("Ferienabgleich" in event["summary"] for event in lessons)


def _cancelled_day_snapshot(store):
    lessons = [
        _lesson(day=WEDNESDAY, period=1, change_kind="cancelled"),
        _lesson(day=WEDNESDAY, period=2, subject_code="MA", subject_label="Mathe", change_kind="cancelled"),
    ]
    store.save_calendar_snapshot(_snapshot(lessons))


def test_a_day_of_only_cancelled_lessons_is_no_school_day(tmp_path):
    body = _state(tmp_path, _cancelled_day_snapshot, NOW_EPOCH)

    assert body["school_day_today"] is False
    assert body["school_end_today"] is None
    assert body["timetable_changed_today"] is True
    assert len(body["changes_today"]) == 2


def test_a_letter_for_one_child_counts_for_that_child_only_while_posts_count_for_all(tmp_path):
    second = _state(tmp_path, _saturday_snapshot, SATURDAY_EPOCH, child=f"child={SECOND_CHILD_ID}")
    client, store, _ = _app(tmp_path / "school")
    _saturday_snapshot(store)
    school = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert [item["title"] for item in second["unread_letters"]["items"]] == ["Elternabend"]
    assert second["unread_posts"]["count"] == 1
    assert school["unread_letters"]["count"] == 2


def test_new_letters_are_named_by_the_full_id_list_beyond_the_ten_listed(tmp_path):
    client, store, _ = _app(tmp_path)
    letters = [{"letter_id": f"l{index}", "recipient_id": "r", "title": f"Brief {index}", "unread": True} for index in range(14)]
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=integration.unread_notices(letters))

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()

    assert len(body["unread_letters"]["items"]) == integration.MAX_NOTICES
    assert body["unread_letters"]["ids"] == [f"l{index}:r" for index in range(14)]
    assert body["unread_letters"]["items"][0]["id"] == "l0:r"


def test_letters_and_posts_read_unknown_after_a_poll_that_could_not_read_them(tmp_path):
    client, store, _ = _app(tmp_path)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 60, True, letters=integration.unread_notices(LETTERS), posts=[])
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, False, integration.ERROR_NETWORK)

    state = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()
    school = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_current(store)).json()

    assert state["unread_letters"] is None and state["unread_posts"] is None
    assert school["unread_letters"] is None and school["unread_posts"] is None


def test_the_lessons_ahead_run_to_the_end_of_the_next_day_with_lessons(tmp_path):
    morning = _state(tmp_path, _today_snapshot, NOW_EPOCH)
    weekend = _state(tmp_path / "weekend", _saturday_snapshot, SATURDAY_EPOCH)

    assert [(item["date"], item["period"]) for item in morning["lessons_ahead"]] == [
        ("2026-09-02", 1),
        ("2026-09-02", 2),
        ("2026-09-02", 3),
        ("2026-09-03", 2),
    ]
    assert [(item["date"], item["period"]) for item in weekend["lessons_ahead"]] == [("2026-09-07", 1), ("2026-09-07", 2)]


def test_no_lesson_ahead_is_named_behind_a_day_without_holiday_dates(tmp_path):
    body = _state(tmp_path, _today_snapshot, NOW_EPOCH, calendar=FakeHolidayCalendar(status=holidays.STATUS_UNKNOWN))

    assert body["lessons_ahead"] == []


def test_the_holiday_sensors_of_a_school_are_unknown_without_holiday_dates(tmp_path):
    for name, status in (("missing", holidays.STATUS_UNKNOWN), ("off", holidays.STATUS_DISABLED)):
        client, store, _ = _app(tmp_path / name, calendar=FakeHolidayCalendar(status=status))

        body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

        assert body["unknown"] == ["next_holiday", "next_free_day"]
        assert body["next_holiday"] is None and body["next_free_day"] is None


def test_a_released_integration_keeps_the_last_known_letters_without_ids_after_a_failed_read(tmp_path):
    client, store, _ = _app(tmp_path)
    letters = [{"letter_id": "l1", "recipient_id": "r", "title": "Wandertag", "child": CHILD_NAME_FIRST, "unread": True}]
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 60, True, letters=integration.unread_notices(letters), posts=[])
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, False, integration.ERROR_NETWORK)

    for headers in (_auth(store), _current(store, RELEASED_INTEGRATION)):
        state = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=headers).json()
        school = client.get(PREFIX + f"/school?id={SCHOOL}", headers=headers).json()

        assert state["unread_letters"] == {"count": 1, "items": [{"title": "Wandertag", "sender": "", "date": "", "child": CHILD_NAME_FIRST}]}
        assert state["unread_posts"] == {"count": 0, "items": []}
        assert school["unread_letters"]["count"] == 1 and "ids" not in school["unread_letters"]
    assert client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()["unread_letters"] is None


def test_a_released_integration_gets_an_empty_list_before_the_first_read(tmp_path):
    client, store, _ = _app(tmp_path)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["unread_letters"] == {"count": 0, "items": []}
    assert client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()["unread_letters"] is None


def test_a_good_read_after_a_failed_one_makes_the_letters_known_again(tmp_path):
    client, store, _ = _app(tmp_path)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 120, True, letters=[], posts=[])
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 60, False, integration.ERROR_NETWORK)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=[], posts=[])

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()

    assert body["unread_letters"] == {"count": 0, "items": [], "ids": []}


def test_a_letter_whose_child_matches_no_configured_child_counts_for_every_child(tmp_path):
    client, store, _ = _app(tmp_path)
    letters = [
        {"letter_id": "l1", "recipient_id": "r", "title": "Wandertag", "child": "Quastenflosser Zwiebelfisch", "unread": True},
        {"letter_id": "l2", "recipient_id": "r", "title": "Elternabend", "child": "Kraakebolle Nebelkraehe", "unread": True},
    ]
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=integration.unread_notices(letters))

    first = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_current(store)).json()
    second = client.get(PREFIX + f"/state?child={SECOND_CHILD_ID}", headers=_current(store)).json()

    assert [item["title"] for item in first["unread_letters"]["items"]] == ["Wandertag"]
    assert [item["title"] for item in second["unread_letters"]["items"]] == ["Wandertag", "Elternabend"]


def _christmas():
    first = datetime(2026, 12, 23).date()
    return {
        (first + timedelta(days=offset)).isoformat(): _day(free=True, overrides=True, kind="school", name="Weihnachtsferien", period_id="x1")
        for offset in range(15)
    }


def test_a_holiday_found_before_the_missing_year_stays_known(tmp_path):
    december = _epoch(2026, 12, 10, 9, 0)
    client, store, _ = _app(tmp_path, calendar=FakeHolidayCalendar(days=_christmas(), missing_years=[2027]), clock=Clock(december))
    late = _epoch(2026, 12, 28, 9, 0)
    after, after_store, _ = _app(tmp_path / "after", calendar=FakeHolidayCalendar(missing_years=[2027]), clock=Clock(late))

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()
    empty = after.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(after_store)).json()

    assert body["unknown"] == []
    assert body["next_holiday"] == {"name": "Weihnachtsferien", "start": "2026-12-23", "end": "2027-01-06", "days_until": 13}
    assert body["next_free_day"]["start"] == "2026-12-23"
    assert empty["unknown"] == ["next_holiday", "next_free_day"]
    assert empty["next_holiday"] is None
