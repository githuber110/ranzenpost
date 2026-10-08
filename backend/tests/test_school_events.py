from datetime import date, datetime

import pytest

from app import feed, integration, modules
from app.iserv.errors import DataError
from app.poller import Poller
from app.store import Store, edit
from tests.support import add_school, connection_service
from tests.test_integration_api import PREFIX, SCHOOL, _app, _auth

TIMED = {
    "uid": "u1",
    "title": "Parents evening",
    "start": "2026-10-12T19:00:00+02:00",
    "end": "2026-10-12T20:30:00+02:00",
    "all_day": False,
    "location": "Hall",
    "calendar": "Parents 5a",
    "category": "",
    "description": "Bring the form",
}
ALL_DAY = {
    "uid": "u2",
    "title": "Sports day",
    "start": "2026-10-15",
    "end": "2026-10-16",
    "all_day": True,
    "location": "",
    "calendar": "School",
    "category": "",
    "description": "",
}


class Answer:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload
        self.headers = {}
        self.text = ""

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class CalendarClient:
    def __init__(self, url, answer=None):
        self.base_url = url
        self.answer = answer
        self.asked = []

    def login(self, username, password, code_provider):
        return self

    def is_authenticated(self):
        return True

    def fetch_or_raise(self, path, params=None):
        self.asked.append((path, params))
        if self.answer.status_code != 200:
            raise DataError("request failed: %d" % self.answer.status_code)
        return self.answer

    def fetch(self, path, params=None):
        self.asked.append((path, params))
        return self.answer


def calendar_service(tmp_path, answer):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    client = CalendarClient("https://school.example", answer)
    service = connection_service(store, connection_id, lambda url: client)
    return service, client, store, connection_id


def test_school_events_are_read_for_the_window_and_parsed(tmp_path):
    payload = {"/group/calendar": [{"uid": "u1", "title": "Concert", "start": "2026-10-01T18:00:00+02:00", "end": "2026-10-01T20:00:00+02:00"}]}
    service, client, _, _ = calendar_service(tmp_path, Answer(200, payload))
    events = service.school_events(date(2026, 10, 1), date(2026, 10, 31))
    assert [event["title"] for event in events] == ["Concert"]
    assert client.asked[-1] == ("/iserv/calendar/feed/calendar-multi", {"start": "2026-10-01", "end": "2026-10-31"})


@pytest.mark.parametrize("answer", [Answer(403, None), Answer(200, ValueError("no json")), Answer(200, "text")])
def test_an_unreadable_school_calendar_is_an_error_and_not_an_empty_calendar(tmp_path, answer):
    service, _, _, _ = calendar_service(tmp_path, answer)
    with pytest.raises(DataError):
        service.school_events(date(2026, 10, 1), date(2026, 10, 31))


def test_the_school_calendar_is_only_available_once_its_probe_confirmed_it(tmp_path):
    service, _, _, _ = calendar_service(tmp_path, Answer(200, {}))
    assert service.school_calendar_available() is False
    service.store.save_modules({"modules": {modules.CALENDAR: True}})
    assert service.school_calendar_available() is True


class CalendarConnection:
    def __init__(self, connection_id, events=None, failure=None, available=True):
        self.id = connection_id
        self.events = events or []
        self.failure = failure
        self.available = available
        self.windows = []

    def school_calendar_available(self):
        return self.available

    def school_events(self, first, last):
        self.windows.append((first, last))
        if self.failure is not None:
            raise self.failure
        return list(self.events)


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    poller = Poller(None, store=store)
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id


def test_the_poll_keeps_the_school_events_per_school(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    connection = CalendarConnection(connection_id, [TIMED, ALL_DAY])
    event = poller._poll_school_calendar(connection, connection_id)
    assert event == {"module": "school_calendar", "events": 2}
    stored = store.load_calendar_snapshot()["schools"][connection_id]
    assert stored == {"events": [TIMED, ALL_DAY], "last_success": 1_791_000_000}
    first, last = connection.windows[0]
    assert (last - first).days == 127


def test_a_failed_school_calendar_read_keeps_the_last_events_and_reports_the_error(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id)
    event = poller._poll_school_calendar(CalendarConnection(connection_id, failure=DataError("request failed: 500")), connection_id)
    assert event["error"] and event["module"] == "school_calendar"
    assert store.load_calendar_snapshot()["schools"][connection_id]["events"] == [TIMED]


def test_a_school_without_the_calendar_is_not_asked(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    connection = CalendarConnection(connection_id, [TIMED], available=False)
    assert poller._poll_school_calendar(connection, connection_id) is None
    assert connection.windows == []
    assert "schools" not in store.load_calendar_snapshot()


def test_disconnecting_a_school_drops_its_events(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id)
    store.remove_connection(connection_id)
    assert connection_id not in (store.load_calendar_snapshot().get("schools") or {})


def test_timed_events_become_berlin_local_times_and_all_day_events_dates():
    snapshot = {"schools": {"s1": {"events": [TIMED, ALL_DAY, {"title": ""}, "junk"]}}}
    events = feed.school_calendar_events("en", snapshot, "s1")
    assert [(event.summary, event.start, event.end, event.all_day) for event in events] == [
        ("Parents evening", datetime(2026, 10, 12, 19, 0), datetime(2026, 10, 12, 20, 30), False),
        ("Sports day", date(2026, 10, 15), date(2026, 10, 16), True),
    ]
    assert events[0].description == "Calendar: Parents 5a\nBring the form"
    assert events[0].location == "Hall"
    assert events[0].kind == "school_event"
    assert events[0].uid == feed.school_calendar_events("en", snapshot, "s1")[0].uid
    other = {"schools": {"s2": {"events": [TIMED]}}}
    assert events[0].uid != feed.school_calendar_events("en", other, "s2")[0].uid


def test_a_utc_time_is_shown_in_berlin_time():
    snapshot = {"schools": {"s1": {"events": [dict(TIMED, start="2026-12-01T17:00:00Z", end="2026-12-01T18:00:00Z")]}}}
    event = feed.school_calendar_events("en", snapshot, "s1")[0]
    assert (event.start, event.end) == (datetime(2026, 12, 1, 18, 0), datetime(2026, 12, 1, 19, 0))


def test_another_school_has_no_events():
    assert feed.school_calendar_events("en", {"schools": {"s1": {"events": [TIMED]}}}, "s2") == []


def test_home_assistant_reads_school_events_without_a_child(tmp_path):
    client, store, _ = _app(tmp_path)

    def change(snapshot):
        snapshot["schools"] = {SCHOOL: {"events": [TIMED, ALL_DAY], "last_success": 1}}

    edit(store, store.load_calendar_snapshot, store.save_calendar_snapshot, change)
    body = client.get(
        PREFIX + f"/events?kind=school_events&school={SCHOOL}&start=2026-10-01&end=2026-10-31", headers=_auth(store)
    ).json()
    assert [(event["summary"], event["start"], event["all_day"], event["kind"]) for event in body] == [
        ("Parents evening", "2026-10-12T19:00:00+02:00", False, "school_event"),
        ("Sports day", "2026-10-15", True, "school_event"),
    ]


def test_school_events_need_a_known_school(tmp_path):
    client, store, _ = _app(tmp_path)
    answer = client.get(PREFIX + "/events?kind=school_events&school=deadbeef", headers=_auth(store))
    assert answer.status_code == 404
    assert integration.KIND_SCHOOL_EVENTS in integration.SCHOOL_KINDS


def test_the_app_gets_the_events_of_every_school_with_the_calendar_sorted_and_tagged(tmp_path):
    from tests.test_connections import two_schools

    service, store, one, two, _ = two_schools(tmp_path)
    store.connection_store(one).save_modules({"modules": {modules.CALENDAR: True}})
    service.connection(one).school_events = lambda first, last: [dict(TIMED), dict(ALL_DAY)]
    service.connection(two).school_events = lambda first, last: pytest.fail("the second school has no calendar")
    body = service.school_events()
    assert [event["title"] for event in body["events"]] == ["Parents evening", "Sports day"]
    assert {event["school"] for event in body["events"]} == {"School One"}
    assert body["unavailable"] == []


def test_events_of_a_school_that_lost_its_calendar_are_dropped(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED], available=False), connection_id)
    assert connection_id not in store.load_calendar_snapshot().get("schools", {})


def test_a_refused_school_calendar_is_its_own_quiet_state(tmp_path):
    from app.iserv.errors import SchoolCalendarRefusedError

    service, _, _, _ = calendar_service(tmp_path, Answer(403, None))
    with pytest.raises(SchoolCalendarRefusedError):
        service.school_events(date(2026, 10, 1), date(2026, 10, 31))


def test_a_refused_school_calendar_does_not_fail_the_poll_and_drops_old_events(tmp_path, caplog):
    import logging

    from app.iserv.errors import SchoolCalendarRefusedError

    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id)
    with caplog.at_level(logging.INFO):
        event = poller._poll_school_calendar(CalendarConnection(connection_id, failure=SchoolCalendarRefusedError("school calendar refused: 403")), connection_id)
    assert event == {"module": "school_calendar", "state": "refused"}
    assert "error" not in event
    assert connection_id not in store.load_calendar_snapshot().get("schools", {})
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_the_app_leaves_out_a_school_whose_calendar_is_refused(tmp_path):
    from app.iserv.errors import SchoolCalendarRefusedError
    from tests.test_connections import two_schools

    service, store, one, _two, _ = two_schools(tmp_path)
    store.connection_store(one).save_modules({"modules": {modules.CALENDAR: True}})

    def refused(first, last):
        raise SchoolCalendarRefusedError("school calendar refused: 403")

    service.connection(one).school_events = refused
    assert service.school_events() == {"events": [], "unavailable": []}
