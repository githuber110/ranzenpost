from datetime import datetime, timezone

from app import integration
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
        "count": 2,
        "items": [
            {"title": "Wandertag", "sender": "Frau Muster", "date": "2026-09-01", "child": "Zwiebelfisch"},
            {"title": "Elternabend", "sender": "Herr Beispiel", "date": "2026-08-31", "child": "Kraakebolle"},
        ],
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
