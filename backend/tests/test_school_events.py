from datetime import date, datetime, timedelta

import pytest

from app import feed, integration, modules
from app.iserv.errors import DataError, OutageError, SchoolCalendarRefusedError
from app.iserv.school_calendar import SchoolCalendarRead
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
    assert service.module_available(modules.CALENDAR) is False
    service.store.save_modules({"modules": {modules.CALENDAR: True}})
    assert service.module_available(modules.CALENDAR) is True


class CalendarConnection:
    def __init__(self, connection_id, events=None, failure=None, failed=()):
        self.id = connection_id
        self.events = events or []
        self.failure = failure
        self.failed = tuple(failed)
        self.answered = ()
        self.windows = []

    def read_school_calendar(self, first, last):
        self.windows.append((first, last))
        if self.failure is not None:
            raise self.failure
        return SchoolCalendarRead(list(self.events), self.failed, (), self.answered)


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    poller = Poller(None, store=store)
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id


def test_the_poll_keeps_the_school_events_per_school(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    connection = CalendarConnection(connection_id, [TIMED, ALL_DAY])
    event = poller._poll_school_calendar(connection, connection_id, True)
    assert event == {"module": "school_calendar", "events": 2}
    stored = store.load_calendar_snapshot()["schools"][connection_id]
    assert stored == {"events": [TIMED, ALL_DAY], "last_success": 1_791_000_000, "sources": {}}
    first, last = connection.windows[0]
    assert (last - first).days == 127


def test_a_failed_school_calendar_read_keeps_the_last_events_and_reports_the_error(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id, True)
    event = poller._poll_school_calendar(CalendarConnection(connection_id, failure=DataError("request failed: 500")), connection_id, True)
    assert event["error"] and event["module"] == "school_calendar"
    assert store.load_calendar_snapshot()["schools"][connection_id]["events"] == [TIMED]


def test_a_school_without_the_calendar_is_not_asked(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    connection = CalendarConnection(connection_id, [TIMED])
    assert poller._poll_school_calendar(connection, connection_id, False) is None
    assert connection.windows == []
    assert "schools" not in store.load_calendar_snapshot()


def test_disconnecting_a_school_drops_its_events(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id, True)
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


TODAY = date(2026, 10, 12)


def snapshot_service(tmp_path, monkeypatch, schools, offered=("one",)):
    from app import holidays
    from tests.test_connections import two_schools

    service, store, one, two, _ = two_schools(tmp_path)
    monkeypatch.setattr(holidays, "berlin_today", lambda: TODAY)
    ids = {"one": one, "two": two}
    for name in offered:
        store.connection_store(ids[name]).save_modules({"modules": {modules.CALENDAR: True}})

    def change(snapshot):
        snapshot["schools"] = {ids[name]: {"events": events, "last_success": 1} for name, events in schools.items()}

    edit(store, store.load_calendar_snapshot, store.save_calendar_snapshot, change)
    for connection in service.connections():
        connection.school_events = lambda first, last: pytest.fail("the app must not ask IServ")
    return service, ids


def test_the_app_gets_the_stored_events_of_every_school_with_the_calendar_sorted_and_tagged(tmp_path, monkeypatch):
    service, ids = snapshot_service(tmp_path, monkeypatch, {"one": [dict(ALL_DAY), dict(TIMED)]})
    body = service.school_events()
    assert [event["title"] for event in body["events"]] == ["Parents evening", "Sports day"]
    assert {event["school"] for event in body["events"]} == {"School One"}
    assert {event["connection_id"] for event in body["events"]} == {ids["one"]}
    assert body["unavailable"] == []


def test_the_app_leaves_out_a_school_whose_calendar_is_not_offered_even_with_old_events(tmp_path, monkeypatch):
    service, _ = snapshot_service(tmp_path, monkeypatch, {"one": [TIMED], "two": [ALL_DAY]})
    body = service.school_events()
    assert {event["school"] for event in body["events"]} == {"School One"}
    assert body["unavailable"] == []


def connection_of(service, connection_id):
    return next(connection for connection in service.connections() if connection.id == connection_id)


def test_a_school_not_polled_yet_is_read_once_from_iserv(tmp_path, monkeypatch):
    service, ids = snapshot_service(tmp_path, monkeypatch, {"one": [TIMED]}, offered=("one", "two"))
    asked = []

    def live(first, last):
        asked.append((first, last))
        return [dict(ALL_DAY)]

    connection_of(service, ids["two"]).school_events = live
    body = service.school_events()
    assert asked == [(TODAY, TODAY + timedelta(days=60))]
    assert {event["connection_id"] for event in body["events"]} == {ids["one"], ids["two"]}
    assert body["unavailable"] == []


def test_a_school_with_stored_but_empty_events_is_not_read_again(tmp_path, monkeypatch):
    service, _ = snapshot_service(tmp_path, monkeypatch, {"one": [], "two": []}, offered=("one", "two"))
    assert service.school_events() == {"events": [], "unavailable": []}


def test_a_refused_calendar_before_the_first_poll_stays_quiet(tmp_path, monkeypatch):
    service, ids = snapshot_service(tmp_path, monkeypatch, {}, offered=("one",))

    def refused(first, last):
        raise SchoolCalendarRefusedError("refused")

    connection_of(service, ids["one"]).school_events = refused
    assert service.school_events() == {"events": [], "unavailable": []}


def test_an_unreadable_calendar_before_the_first_poll_is_unavailable_not_empty(tmp_path, monkeypatch):
    service, ids = snapshot_service(tmp_path, monkeypatch, {}, offered=("one",))

    def broken(first, last):
        raise DataError("school calendar answered 500")

    connection_of(service, ids["one"]).school_events = broken
    assert service.school_events() == {"events": [], "unavailable": [ids["one"]]}


def test_the_app_shows_only_events_in_the_window_of_sixty_days(tmp_path, monkeypatch):
    before = dict(TIMED, uid="old", title="Old", start="2026-10-05T10:00:00+02:00", end="2026-10-05T11:00:00+02:00")
    running = dict(ALL_DAY, uid="run", title="Running", start="2026-10-10", end="2026-10-13")
    ended = dict(ALL_DAY, uid="end", title="Ended", start="2026-10-10", end="2026-10-12")
    far = dict(TIMED, uid="far", title="Far", start="2026-12-20T10:00:00+01:00", end="2026-12-20T11:00:00+01:00")
    edge = dict(TIMED, uid="edge", title="Edge", start="2026-12-11T10:00:00+01:00", end="2026-12-11T11:00:00+01:00")
    service, _ = snapshot_service(tmp_path, monkeypatch, {"one": [before, running, ended, far, edge]})
    assert [event["title"] for event in service.school_events()["events"]] == ["Running", "Edge"]


def test_the_app_still_needs_a_connected_school(tmp_path):
    from app.not_configured import NotConfiguredError
    from app.service import IServService

    with pytest.raises(NotConfiguredError):
        IServService(Store(tmp_path / "data")).school_events()


def test_the_app_does_not_change_the_stored_events(tmp_path, monkeypatch):
    service, ids = snapshot_service(tmp_path, monkeypatch, {"one": [TIMED]})
    service.school_events()["events"][0]["title"] = "changed"
    assert service.store.load_calendar_snapshot()["schools"][ids["one"]]["events"] == [TIMED]


def test_events_of_a_school_that_lost_its_calendar_are_dropped(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id, True)
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id, False)
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
    poller._poll_school_calendar(CalendarConnection(connection_id, [TIMED]), connection_id, True)
    with caplog.at_level(logging.INFO):
        event = poller._poll_school_calendar(CalendarConnection(connection_id, failure=SchoolCalendarRefusedError("school calendar refused: 403")), connection_id, True)
    assert event == {"module": "school_calendar", "state": "refused"}
    assert "error" not in event
    assert connection_id not in store.load_calendar_snapshot().get("schools", {})
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


@pytest.mark.parametrize(
    "stored, expected",
    [(None, False), ({}, False), ({"modules": {}}, False), ({"modules": {modules.CALENDAR: False}}, False), ({"modules": {modules.CALENDAR: True}}, True)],
)
def test_the_listing_and_the_connection_agree_on_the_school_calendar(tmp_path, stored, expected):
    from app.calendar_routes import school_calendar_ready
    from tests.test_connections import two_schools

    service, store, one, _two, _ = two_schools(tmp_path)
    if stored is not None:
        store.connection_store(one).save_modules(stored)
    assert school_calendar_ready(store, one) is expected
    assert service.connection(one).module_available(modules.CALENDAR) is expected


OWN_HOME = {"label": "Mine", "id": "/f.parent/home", "subscription": False, "color": "#112233", "textColor": "#ffffff", "url": "/iserv/calendar/feed/calendar?cal=%2Ff.parent%2Fhome", "type": "cal", "droppable": True}
GROUP_HOME = {"label": "Class 7b", "id": "/class.7b/home", "subscription": False, "color": "#223344", "textColor": "#ffffff", "url": "/iserv/calendar/feed/calendar?cal=%2Fclass.7b%2Fhome", "type": "cal", "droppable": False}
SCHOOL_CAL = {"label": "School", "id": "/school.all/calendar", "subscription": True, "color": "#334455", "textColor": "#ffffff", "url": "/iserv/calendar/feed/calendar?cal=%2Fschool.all%2Fcalendar", "type": "cal", "droppable": False}
EXAMS = {"label": "Exam plan", "id": "exam", "subscription": False, "color": "#445566", "textColor": "#000000", "url": "/iserv/calendar/feed/plugin?plugin=exam", "type": "plugin", "droppable": False}
HOLIDAYS = {"label": "Holidays", "id": "holiday", "subscription": False, "color": "#556677", "textColor": "#000000", "url": "/iserv/calendar/feed/plugin?plugin=holiday", "type": "plugin", "droppable": False}
SOURCES = [OWN_HOME, GROUP_HOME, SCHOOL_CAL, EXAMS, HOLIDAYS]


def raw(uid, title, start, end, calendar_id="", name=None):
    item = {"id": uid + "-id", "uid": uid, "title": title, "start": start, "end": end, "allDay": False, "calendarId": calendar_id, "location": None, "category": None}
    if name is not None:
        item["calendarName"] = name
    return item


CONCERT = raw("concert@school.example", "Concert", "2026-10-20T18:00:00+02:00", "2026-10-20T20:00:00+02:00", "/school.all/calendar", "School")
TRIP = raw("trip@school.example", "Class trip", "2026-10-22T08:00:00+02:00", "2026-10-22T16:00:00+02:00", "/class.7b/home", "Class 7b")
EXAM = raw("exam-1", "Maths exam", "2026-11-03T08:00:00+01:00", "2026-11-03T09:30:00+01:00", "")
DENTIST = raw("dentist@school.example", "Dentist", "2026-10-21T10:00:00+02:00", "2026-10-21T11:00:00+02:00", "/f.parent/home", "Mine")
SOURCES_PATH = "/iserv/calendar/api/eventsources"
GROUP_FEED = "/iserv/calendar/feed/calendar?cal=/class.7b/home"
SCHOOL_FEED = "/iserv/calendar/feed/calendar?cal=/school.all/calendar"
EXAM_FEED = "/iserv/calendar/feed/plugin?plugin=exam"
HOLIDAY_FEED = "/iserv/calendar/feed/plugin?plugin=holiday"
OWN_FEED = "/iserv/calendar/feed/calendar?cal=/f.parent/home"
FEED_ANSWERS = {
    SOURCES_PATH: Answer(200, SOURCES),
    OWN_FEED: Answer(200, [DENTIST]),
    GROUP_FEED: Answer(200, [TRIP, dict(CONCERT)]),
    SCHOOL_FEED: Answer(200, [CONCERT, DENTIST]),
    EXAM_FEED: Answer(200, [EXAM]),
    HOLIDAY_FEED: Answer(500, None),
}
WINDOW = (date(2026, 10, 1), date(2026, 11, 30))


class FeedClient(CalendarClient):
    def __init__(self, url, answers):
        super().__init__(url)
        self.answers = answers
        self.strict = False

    def fetch(self, path, params=None):
        if self.strict:
            self.asked.append((path, params))
        own = [(key, value) for key, value in params or () if key not in ("start", "end")] if isinstance(params, list) else []
        key = path + ("?" + "&".join("%s=%s" % pair for pair in own) if own else "")
        if not self.strict or not path.startswith("/iserv/calendar/"):
            return Answer(200, {})
        answer = self.answers.get(key)
        if answer is None:
            pytest.fail("unexpected calendar request %s" % key)
        return answer


def feed_service(tmp_path, answers=None):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    client = FeedClient("https://school.example", dict(FEED_ANSWERS if answers is None else answers))
    service = connection_service(store, connection_id, lambda url: client)
    service.iserv_session()
    client.strict = True
    return service, client


def titles(events):
    return [event["title"] for event in events]


def test_every_school_source_is_read_over_its_own_feed_with_the_window(tmp_path):
    service, client = feed_service(tmp_path)
    read = service.read_school_calendar(*WINDOW)
    assert titles(read.events) == ["Concert", "Dentist", "Class trip", "Maths exam"]
    window = [("start", "2026-10-01"), ("end", "2026-11-30")]
    assert client.asked == [
        (SOURCES_PATH, None),
        ("/iserv/calendar/feed/calendar", [("cal", "/f.parent/home")] + window),
        ("/iserv/calendar/feed/calendar", [("cal", "/class.7b/home")] + window),
        ("/iserv/calendar/feed/calendar", [("cal", "/school.all/calendar")] + window),
        ("/iserv/calendar/feed/plugin", [("plugin", "exam")] + window),
        ("/iserv/calendar/feed/plugin", [("plugin", "holiday")] + window),
    ]
    assert read.failed == ("holiday",)
    assert read.answered == ("/f.parent/home", "/class.7b/home", "/school.all/calendar", "exam")


def test_a_window_already_in_the_source_url_is_replaced_by_the_own_window(tmp_path):
    exams = dict(EXAMS, url="/iserv/calendar/feed/plugin?plugin=exam&start=2020-01-01&end=2020-02-01")
    service, client = feed_service(tmp_path, {SOURCES_PATH: Answer(200, [exams]), EXAM_FEED: Answer(200, [EXAM])})
    service.read_school_calendar(*WINDOW)
    assert client.asked[-1] == ("/iserv/calendar/feed/plugin", [("plugin", "exam"), ("start", "2026-10-01"), ("end", "2026-11-30")])


def test_an_event_from_two_sources_is_shown_once_and_names_its_calendar(tmp_path):
    service, _ = feed_service(tmp_path)
    events = service.read_school_calendar(*WINDOW).events
    concerts = [event for event in events if event["title"] == "Concert"]
    assert len(concerts) == 1
    assert concerts[0]["calendar"] == "School"
    exam = next(event for event in events if event["title"] == "Maths exam")
    assert (exam["calendar"], exam["source"]) == ("Exam plan", "exam")


def test_the_personal_calendar_is_read_and_shown_once_with_its_name(tmp_path):
    service, _ = feed_service(tmp_path)
    events = service.read_school_calendar(*WINDOW).events
    dentist = [event for event in events if event["title"] == "Dentist"]
    assert len(dentist) == 1
    assert (dentist[0]["calendar"], dentist[0]["source"]) == ("Mine", "/f.parent/home")


def test_one_failing_source_is_logged_once_and_does_not_drop_the_others(tmp_path, caplog):
    import logging

    service, _ = feed_service(tmp_path)
    with caplog.at_level(logging.INFO, logger="app.service"):
        first = service.read_school_calendar(*WINDOW)
        service.read_school_calendar(*WINDOW)
    assert len(first.events) == 4
    records = [record for record in caplog.records if "calendar source" in record.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    line = records[0].getMessage()
    assert "plugin /iserv/calendar/feed/plugin not read: OutageError" in line
    assert "holiday" not in line and "f.parent" not in line


def test_a_source_that_answers_again_is_logged_again_when_it_fails_later(tmp_path, caplog):
    import logging

    service, client = feed_service(tmp_path)
    with caplog.at_level(logging.INFO, logger="app.service"):
        service.read_school_calendar(*WINDOW)
        client.answers[HOLIDAY_FEED] = Answer(200, [])
        service.read_school_calendar(*WINDOW)
        client.answers[HOLIDAY_FEED] = Answer(500, None)
        service.read_school_calendar(*WINDOW)
    assert len([record for record in caplog.records if "calendar source" in record.getMessage()]) == 2


def test_when_every_source_fails_the_read_fails_and_is_not_empty(tmp_path):
    answers = {key: Answer(500, None) for key in FEED_ANSWERS}
    answers[SOURCES_PATH] = Answer(200, SOURCES)
    service, _ = feed_service(tmp_path, answers)
    with pytest.raises(OutageError):
        service.read_school_calendar(*WINDOW)


def test_when_every_source_refuses_the_calendar_is_refused(tmp_path):
    answers = {key: Answer(403, None) for key in FEED_ANSWERS}
    answers[SOURCES_PATH] = Answer(200, SOURCES)
    service, _ = feed_service(tmp_path, answers)
    with pytest.raises(SchoolCalendarRefusedError):
        service.read_school_calendar(*WINDOW)


def test_a_refused_source_is_left_out_and_not_kept_from_before(tmp_path):
    answers = dict(FEED_ANSWERS)
    answers[HOLIDAY_FEED] = Answer(403, None)
    service, _ = feed_service(tmp_path, answers)
    read = service.read_school_calendar(*WINDOW)
    assert read.failed == ()
    assert len(read.events) == 4


def test_an_unreadable_source_is_a_failed_source(tmp_path):
    answers = dict(FEED_ANSWERS)
    answers[HOLIDAY_FEED] = Answer(200, {"error": "denied"})
    service, _ = feed_service(tmp_path, answers)
    assert service.read_school_calendar(*WINDOW).failed == ("holiday",)


def test_a_rate_limit_stops_the_read_at_once(tmp_path):
    answers = dict(FEED_ANSWERS)
    answers[GROUP_FEED] = Answer(429, None)
    service, client = feed_service(tmp_path, answers)
    with pytest.raises(OutageError):
        service.read_school_calendar(*WINDOW)
    assert len(client.asked) == 3


def test_a_source_outside_the_calendar_feeds_is_never_requested(tmp_path):
    bad = [
        dict(EXAMS, id="a", url="/iserv/calendar/delete?id=1"),
        dict(EXAMS, id="b", url="https://other.example/iserv/calendar/feed/plugin?plugin=exam"),
        dict(EXAMS, id="c", url="/iserv/calendar/feed/../edit"),
        dict(EXAMS, id="d", url="//other.example/iserv/calendar/feed/plugin"),
        dict(EXAMS, id="e", url="/iserv/calendar/feed/calendar/actions/delete"),
        dict(EXAMS, id="f", url=""),
        dict(EXAMS, id="g", url=None),
    ]
    answers = {SOURCES_PATH: Answer(200, [EXAMS] + bad), EXAM_FEED: Answer(200, [EXAM])}
    service, client = feed_service(tmp_path, answers)
    assert titles(service.read_school_calendar(*WINDOW).events) == ["Maths exam"]
    assert [path for path, _ in client.asked] == [SOURCES_PATH, "/iserv/calendar/feed/plugin"]


@pytest.mark.parametrize(
    "sources",
    [Answer(200, {"error": "x"}), Answer(200, ValueError("no json")), Answer(404, None), Answer(200, [dict(EXAMS, url="/elsewhere")])],
)
def test_unusable_sources_fall_back_to_the_combined_feed(tmp_path, sources):
    multi = {"/school.all/calendar": [CONCERT], "/f.parent/home": [DENTIST]}
    answers = {SOURCES_PATH: sources, "/iserv/calendar/feed/calendar-multi": Answer(200, multi)}
    service, client = feed_service(tmp_path, answers)
    assert titles(service.read_school_calendar(*WINDOW).events) == ["Concert", "Dentist"]
    assert client.asked[-1] == ("/iserv/calendar/feed/calendar-multi", {"start": "2026-10-01", "end": "2026-11-30"})


def test_a_server_failure_on_the_source_list_is_an_outage_and_not_a_fallback(tmp_path):
    service, client = feed_service(tmp_path, {SOURCES_PATH: Answer(503, None)})
    with pytest.raises(OutageError):
        service.read_school_calendar(*WINDOW)
    assert len(client.asked) == 1


def test_an_empty_source_list_means_no_school_events(tmp_path):
    service, client = feed_service(tmp_path, {SOURCES_PATH: Answer(200, [])})
    assert service.read_school_calendar(*WINDOW).events == []
    assert len(client.asked) == 1


def test_only_the_personal_calendar_listed_still_shows_its_events(tmp_path):
    service, _ = feed_service(tmp_path, {SOURCES_PATH: Answer(200, [OWN_HOME]), OWN_FEED: Answer(200, [DENTIST])})
    assert titles(service.read_school_calendar(*WINDOW).events) == ["Dentist"]


def test_the_live_read_returns_the_merged_events(tmp_path):
    service, _ = feed_service(tmp_path)
    assert titles(service.school_events(*WINDOW)) == ["Concert", "Dentist", "Class trip", "Maths exam"]


def test_a_failed_source_keeps_its_last_events_in_the_poll_and_the_others_update(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    old_exam = dict(TIMED, uid="exam-old", title="Old exam", source="exam")
    old_school = dict(ALL_DAY, uid="school-old", title="Old school", source="/school.all/calendar")
    poller._poll_school_calendar(CalendarConnection(connection_id, [old_exam, old_school]), connection_id, True)
    fresh = dict(TIMED, uid="school-new", title="New school", start="2026-10-13T19:00:00+02:00", source="/school.all/calendar")
    event = poller._poll_school_calendar(CalendarConnection(connection_id, [fresh, dict(old_exam)], failed=("exam",)), connection_id, True)
    stored = store.load_calendar_snapshot()["schools"][connection_id]["events"]
    assert titles(stored) == ["Old exam", "New school"]
    assert event == {"module": "school_calendar", "events": 2}


def test_events_of_a_source_that_answers_again_are_replaced(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    poller._poll_school_calendar(CalendarConnection(connection_id, [dict(TIMED, source="exam")]), connection_id, True)
    poller._poll_school_calendar(CalendarConnection(connection_id, []), connection_id, True)
    assert store.load_calendar_snapshot()["schools"][connection_id]["events"] == []


def test_events_of_a_source_that_keeps_failing_are_carried_for_seven_days_only(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    now = [1_791_000_000]
    poller.clock = lambda: now[0]
    exam = dict(TIMED, uid="exam-old", title="Old exam", source="exam")
    answered = CalendarConnection(connection_id, [exam])
    answered.answered = ("exam",)
    poller._poll_school_calendar(answered, connection_id, True)
    failing = CalendarConnection(connection_id, [], failed=("exam",))
    for day in range(1, 7):
        now[0] += 24 * 3600
        poller._poll_school_calendar(failing, connection_id, True)
        assert titles(store.load_calendar_snapshot()["schools"][connection_id]["events"]) == ["Old exam"]
    now[0] += 24 * 3600
    poller._poll_school_calendar(failing, connection_id, True)
    assert store.load_calendar_snapshot()["schools"][connection_id]["events"] == []


def test_an_old_snapshot_without_source_stamps_still_ages_its_carried_events(tmp_path):
    poller, store, connection_id = poller_for(tmp_path)
    now = [1_791_000_000]
    poller.clock = lambda: now[0]
    exam = dict(TIMED, uid="exam-old", title="Old exam", source="exam")
    store.save_calendar_snapshot({"schools": {connection_id: {"events": [exam], "last_success": now[0]}}})
    failing = CalendarConnection(connection_id, [], failed=("exam",))
    now[0] += 6 * 24 * 3600
    poller._poll_school_calendar(failing, connection_id, True)
    assert titles(store.load_calendar_snapshot()["schools"][connection_id]["events"]) == ["Old exam"]
    now[0] += 24 * 3600
    poller._poll_school_calendar(failing, connection_id, True)
    assert store.load_calendar_snapshot()["schools"][connection_id]["events"] == []
