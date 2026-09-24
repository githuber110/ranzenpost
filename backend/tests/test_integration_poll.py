import copy
from datetime import datetime, timezone

from app import integration
from app.iserv.errors import LoginError
from app.poller import Poller
from app.store import Store
from app.subscriptions import SubscriptionRegistry

from tests.test_poller import FakeStore, _timetable
from tests.test_poller import _display_lesson as _plain_lesson

SCHOOL = "a1b2c3d4"
RAW_CHILD_ID = "child-uuid-a"
CHILD_ID = f"{SCHOOL}:{RAW_CHILD_ID}"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
NOW = datetime(2026, 9, 2, 6, 0)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
DAY = 24 * 60 * 60
WEEK_STARTS = ["31.08.2026", "07.09.2026", "14.09.2026", "21.09.2026"]


def _display_lesson(date="2026-08-31", period=1, change_kind="", changed_fields=None):
    lesson = _plain_lesson(date=date, period=period)
    lesson["change_kind"] = change_kind
    lesson["changed_fields"] = list(changed_fields or [])
    return lesson


def _week(lessons=None):
    return _timetable("02.09.2026 06:00", lessons=lessons, start_date="31.08.2026")


class RecordingService:
    def __init__(self, store, timetable=None, letters=None, pinboard=None, conferences=None, overview=None):
        self.store = store
        self.id = SCHOOL
        self.calls = []
        self.me_calls = 0
        self.timetable_value = timetable if timetable is not None else _week([_display_lesson(date="02.09.2026")])
        self.letters_value = letters if letters is not None else {"letters": []}
        self.pinboard_value = pinboard if pinboard is not None else {"feed": []}
        self.conferences_value = conferences if conferences is not None else {"empty": True, "items": []}
        self.overview = overview
        self.school_name = "Testschule"

    def is_configured(self):
        return True

    def children(self):
        return [{"child_id": RAW_CHILD_ID, "name": CHILD_NAME, "student_id": 7}]

    def timetable(self, child_id, week_offset=0):
        self.calls.append((child_id, week_offset))
        value = copy.deepcopy(self.timetable_value)
        if week_offset:
            value["start_date"] = WEEK_STARTS[week_offset]
            value["lessons"] = []
        return value

    def letters(self, tab="current"):
        return self.letters_value

    def pinboard(self):
        return self.pinboard_value

    def conferences(self):
        return self.conferences_value

    def absences_overview(self):
        if self.overview is None:
            raise RuntimeError("no absences")
        return self.overview

    def me(self):
        self.me_calls += 1
        return {"school_name": self.school_name}


def _store(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["language"] = "de"
    store.save_config(config)
    store.add_connection(
        "https://school-one.example",
        connection_id=SCHOOL,
        setup_complete=True,
        holiday_region="DE-NI",
        children=[{"child_id": RAW_CHILD_ID, "name": CHILD_NAME, "class_name": "5A"}],
    )
    return store


def _poller(store, service, clock=NOW_EPOCH):
    return Poller(service, store=store, registry=SubscriptionRegistry(store), clock=lambda: clock)


def test_without_an_integration_request_the_poller_snapshots_nothing_extra(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)

    _poller(store, service).poll_once()

    assert service.calls == [(RAW_CHILD_ID, 0)]
    assert store.load_calendar_snapshot() == {}


def test_a_recent_integration_request_makes_the_poller_snapshot_every_child(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH - 600)
    service = RecordingService(store)

    _poller(store, service).poll_once()

    assert sorted(offset for _, offset in service.calls) == [0, 1, 2, 3]
    assert "31.08.2026" in store.load_calendar_snapshot()["children"][CHILD_ID]["weeks"]


def test_an_integration_request_older_than_a_day_no_longer_counts(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH - DAY - 1)
    service = RecordingService(store)

    _poller(store, service).poll_once()

    assert service.calls == [(RAW_CHILD_ID, 0)]


def test_an_active_integration_gets_the_absences_of_every_child(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH)
    overview = {
        "children": [{"id": 7, "name": CHILD_NAME}],
        "entries": [
            {"id": 1, "kind": "sick", "student_id": 7, "status": "", "from_date": "2026-09-02", "till_date": "2026-09-02"},
        ],
    }
    service = RecordingService(store, overview=overview)

    _poller(store, service).poll_once()

    stored = store.load_calendar_snapshot()["children"][CHILD_ID]["absences"]
    assert [entry["id"] for entry in stored] == [1]


def test_the_poll_records_unread_letters_posts_and_conferences(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(
        store,
        letters={"letters": [
            {"letter_id": "a", "recipient_id": "r", "title": "Wandertag", "sender": "Frau Muster", "published": "01.09.2026 14:02", "child": "Zwiebelfisch Quastenflosser", "unread": True},
            {"letter_id": "b", "recipient_id": "r", "title": "Elternabend", "unread": False},
        ]},
        pinboard={"feed": [
            {"id": 2, "title": "Mensa", "owner": "Sekretariat", "unread": True},
            {"id": 1, "title": "Sportfest", "unread": False},
        ]},
        conferences={"empty": False, "items": [{"cells": ["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]}]},
    )

    _poller(store, service).poll_once()

    state = integration.school_state(store, SCHOOL)
    assert state["letters"] == [{"title": "Wandertag", "sender": "Frau Muster", "date": "2026-09-01", "child": "Zwiebelfisch"}]
    assert state["posts"] == [{"title": "Mensa", "sender": "Sekretariat", "date": "", "child": ""}]
    assert state["conferences"] == [["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]]
    assert state["last_poll"] == NOW_EPOCH
    assert state["last_poll_ok"] is True
    assert state["last_error"] == ""
    shared = store.load_integration_state()
    assert shared["last_poll"] == NOW_EPOCH
    assert shared["last_poll_ok"] is True
    assert "letters" not in shared


def test_the_first_poll_records_no_change_events(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store, timetable=_week([_display_lesson(date="02.09.2026", change_kind="cancelled")]))

    _poller(store, service).poll_once()

    assert store.load_integration_state()["changes"] == []


def test_a_change_that_appears_between_two_polls_becomes_a_change_event(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)
    _poller(store, service).poll_once()
    service.timetable_value = _week([_display_lesson(date="02.09.2026", change_kind="cancelled")])

    _poller(store, service, clock=NOW_EPOCH + 60).poll_once()

    changes = store.load_integration_state()["changes"]
    assert len(changes) == 1
    assert changes[0]["child_key"] == CHILD_ID
    assert changes[0]["school_id"] == SCHOOL
    assert changes[0]["kind"] == "cancellation"
    assert changes[0]["new"] is True
    assert "Mathe" in changes[0]["summary"]
    assert changes[0]["at"] == "2026-09-02T08:01:00+02:00"
    assert changes[0]["date"] == "2026-09-02"
    assert changes[0]["period"] == 1


def test_a_change_event_is_new_only_until_the_next_poll(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)
    _poller(store, service).poll_once()
    service.timetable_value = _week([_display_lesson(date="02.09.2026", change_kind="cancelled")])
    _poller(store, service, clock=NOW_EPOCH + 60).poll_once()

    _poller(store, service, clock=NOW_EPOCH + 120).poll_once()

    changes = store.load_integration_state()["changes"]
    assert len(changes) == 1
    assert changes[0]["new"] is False


def test_change_kinds_follow_what_changed(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)
    _poller(store, service).poll_once()
    service.timetable_value = _week([
        _display_lesson(date="02.09.2026", period=1, change_kind="changed", changed_fields=["room"]),
        _display_lesson(date="02.09.2026", period=2, change_kind="changed", changed_fields=["teacher"]),
        _display_lesson(date="02.09.2026", period=3, change_kind="changed", changed_fields=["room", "subject"]),
        _display_lesson(date="02.09.2026", period=4, change_kind="added"),
    ])

    _poller(store, service, clock=NOW_EPOCH + 60).poll_once()

    kinds = sorted((entry["period"], entry["kind"]) for entry in store.load_integration_state()["changes"])
    assert kinds == [(1, "room_change"), (2, "substitution"), (3, "substitution"), (4, "new_lesson")]


def test_the_change_log_keeps_only_the_newest_fifty(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)
    _poller(store, service).poll_once()
    for round_number in range(1, 8):
        cancelled = [
            _display_lesson(date=f"{day:02d}.09.2026", period=period, change_kind="cancelled")
            for day in range(1, 6)
            for period in range(1, 3)
        ]
        added = [_display_lesson(date="02.09.2026", period=round_number + 2, change_kind="added")]
        service.timetable_value = _week(cancelled + added)
        _poller(store, service, clock=NOW_EPOCH + 60 * round_number).poll_once()

    changes = store.load_integration_state()["changes"]
    assert len(changes) <= integration.MAX_CHANGES
    assert changes[0]["kind"] == "new_lesson"
    assert changes[0]["period"] == 9


def test_a_login_failure_marks_the_poll_as_failed(tmp_path):
    store = _store(tmp_path)

    class Failing(RecordingService):
        def children(self):
            raise LoginError("bad credentials")

    _poller(store, Failing(store)).poll_once()

    state = store.load_integration_state()
    assert state["last_poll"] == NOW_EPOCH
    assert state["last_poll_ok"] is False
    assert state["last_error"] == "auth_failed"
    assert integration.school_state(store, SCHOOL)["last_error"] == "auth_failed"


def test_the_school_name_is_fetched_once_and_kept(tmp_path):
    store = _store(tmp_path)
    service = RecordingService(store)

    _poller(store, service).poll_once()
    _poller(store, service, clock=NOW_EPOCH + 60).poll_once()

    assert integration.school_state(store, SCHOOL)["school_name"] == "Testschule"
    assert store.connection(SCHOOL)["school_name"] == "Testschule"
    assert service.me_calls == 1


def test_a_store_without_integration_files_does_not_break_the_poll():
    store = FakeStore()

    class Plain:
        id = "s1"

        def is_configured(self):
            return True

        def children(self):
            return [{"child_id": "c1", "name": "Alice"}]

        def timetable(self, child_id, week_offset=0):
            return _timetable("x")

    events = Poller(Plain(), store=store).poll_once()

    assert events == [{"child_key": "s1:c1", "changed": True, "has_changes": False}]


def test_note_request_persists_the_time_and_is_active_reads_it_back(tmp_path):
    store = _store(tmp_path)

    assert integration.is_active(store, NOW_EPOCH) is False
    integration.note_request(store, NOW_EPOCH)

    assert integration.last_request(store) == NOW_EPOCH
    assert integration.is_active(store, NOW_EPOCH + DAY - 1) is True
    assert integration.is_active(store, NOW_EPOCH + DAY + 1) is False


def test_note_request_writes_at_most_once_a_minute(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH)
    integration.note_request(store, NOW_EPOCH + 30)

    assert integration.last_request(store) == NOW_EPOCH

    integration.note_request(store, NOW_EPOCH + 61)

    assert integration.last_request(store) == NOW_EPOCH + 61


class SessionLosingService(RecordingService):
    session_lost = False

    def letters(self, tab="current"):
        if self.session_lost:
            from app.iserv.errors import TwoFactorError

            raise TwoFactorError(
                "session was not established", message_key="api.login.session", detail={"login_stage": "session"}
            )
        return super().letters(tab)

    def session_not_opened_held(self):
        return self.session_lost


def test_a_change_found_before_the_session_is_lost_later_in_the_poll_still_reaches_home_assistant(tmp_path):
    store = _store(tmp_path)
    service = SessionLosingService(store)
    _poller(store, service).poll_once()
    service.timetable_value = _week([_display_lesson(date="02.09.2026", change_kind="cancelled")])
    service.session_lost = True

    events = _poller(store, service, clock=NOW_EPOCH + 60).poll_once()

    changes = store.load_integration_state()["changes"]
    assert [(change["child_key"], change["kind"]) for change in changes] == [(CHILD_ID, "cancellation")]
    assert {"connection_id": SCHOOL, "error": "session_not_opened"} in events
    assert any(event.get("child_key") == CHILD_ID and event.get("changed") for event in events)
    slot = integration.school_state(store, SCHOOL)
    assert (slot["last_error"], slot["auth_reason"]) == (integration.ERROR_AUTH, "session_not_opened")
