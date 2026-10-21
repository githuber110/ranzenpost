from collections import Counter
from datetime import date
from pathlib import Path

from app import modules
from app.iserv.client import IServClient
from app.iserv.school_calendar import CALENDAR_EVENTS_PATH, CALENDAR_SOURCES_PATH, window_params
from app.refusals import REFUSAL_SECONDS, Refusals
from app.store import Store
from tests.support import add_school, connection_service

BASE = "https://school.example"
API = "/iserv/dieschulapp/api/1.0/"
HOUR = 3600
FIXTURES = Path(__file__).parent / "fixtures"
START_PAGE = (
    "<html><body><a href='/iserv/time-table/'>Plan</a>"
    "<a href='/iserv/parentletter/parent/index'>Letters</a></body></html>"
)
LETTER_LIST = (
    '<html><body><table id="crud-table"><tbody>'
    '<tr><td><a href="/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001/'
    '20000000-0000-4000-8000-000000000001">Letter</a></td><td>Alex Sample</td><td>M. Sample</td><td></td>'
    "<td>Class 3b</td><td>01.09.2026 08:00</td></tr></tbody></table></body></html>"
)
SETTINGS_PATH = API + "school-settings/"
ME_PATH = API + "users/me"
SLOTS_PATH = API + "timetable-slots/"
PINBOARD_PATH = API + "pinboards/"
LETTERS_PATH = modules.PROBES[modules.LETTERS][0]
TIME_TABLE_PATH = modules.PROBES[modules.TIMETABLE][0]
CONFERENCES_PATH = modules.PROBES[modules.CONFERENCES][0]


class Cookie:
    def __init__(self, name):
        self.name = name


class Answer:
    def __init__(self, status, url, text="", payload=None):
        self.status_code = status
        self.url = url
        self.text = text
        self.payload = payload
        self.headers = {"Content-Type": "application/json" if payload is not None else "text/html"}
        self.content = text.encode("utf-8")

    def json(self):
        if self.payload is None:
            raise ValueError("no json")
        return self.payload


class School:
    def __init__(self):
        self.headers = {}
        self.cookies = []
        self.hits = Counter()
        self.statuses = {}
        self.payloads = {}
        self.start_page = START_PAGE

    def get(self, url, params=None, timeout=None, **kwargs):
        path = url[len(BASE):]
        self.hits[path] += 1
        status = self.statuses.get(path)
        if status is None:
            status = 403 if path.startswith(API) else 200
        if status != 200:
            return Answer(status, url)
        if path == "/iserv/":
            return Answer(200, url, self.start_page)
        if path == TIME_TABLE_PATH:
            return Answer(200, url, (FIXTURES / "timetable_page.html").read_text(encoding="utf-8"))
        if path == LETTERS_PATH:
            return Answer(200, url, LETTER_LIST)
        if path in self.payloads:
            return Answer(200, url, payload=self.payloads[path])
        if path in (CALENDAR_SOURCES_PATH, CALENDAR_EVENTS_PATH):
            return Answer(200, url, payload=[])
        if path == "/iserv/messenger/":
            return Answer(404, url)
        return Answer(200, url, "<html></html>")


class SchoolClient(IServClient):
    def login(self, username, password, code_provider):
        self.session.cookies = [Cookie("IServSession")]
        return self


class Rig:
    def __init__(self, tmp_path):
        self.school = School()
        self.now = [1_788_000_000.0]
        store = Store(tmp_path / "data")
        connection_id = add_school(store, BASE)
        self.service = connection_service(store, connection_id, lambda url: SchoolClient(url, session=self.school))
        self.service.clock = lambda: self.now[0]

    def hits(self, path):
        return self.school.hits[path]

    def advance(self, seconds):
        self.now[0] += seconds

    def poll(self):
        self.service._settings_cache = (0.0, None)
        self.service.refresh_modules()
        self.service._school_settings()
        self.service._school_period_slots()
        self.service.me()
        self.service._dsa().pinboards()

    def polls(self, count):
        for _ in range(count):
            self.advance(30 * 60)
            self.poll()


def test_a_refused_school_app_path_is_asked_once_per_day_not_per_poll(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    rig.polls(40)
    assert rig.hits(SETTINGS_PATH) == 1
    assert rig.hits(ME_PATH) == 1
    assert rig.hits(SLOTS_PATH) == 1
    assert rig.hits(PINBOARD_PATH) == 1
    assert rig.hits(modules.PROBES[modules.ABSENCES][0]) == 1


def test_a_refused_module_is_probed_once_per_day_not_per_poll(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[LETTERS_PATH] = 403
    rig.school.statuses[CONFERENCES_PATH] = 404
    rig.service.check_connection()
    rig.polls(40)
    assert rig.hits(LETTERS_PATH) == 1
    assert rig.hits(CONFERENCES_PATH) == 1
    assert rig.service.modules()["modules"][modules.LETTERS] is False
    assert rig.service.modules()["modules"][modules.CONFERENCES] is False
    assert rig.hits(TIME_TABLE_PATH) >= 40


def test_calendar_feeds_that_all_refuse_are_probed_once_per_day_not_per_poll(tmp_path):
    rig = Rig(tmp_path)
    feeds = ["/iserv/calendar/feed/calendar", "/iserv/calendar/api/plugin"]
    rig.school.payloads[CALENDAR_SOURCES_PATH] = [
        {"id": "/school/calendar", "label": "School", "type": "cal", "url": feeds[0] + "?calendar=school"},
        {"id": "/class/calendar", "label": "Class", "type": "cal", "url": feeds[0] + "?calendar=class"},
        {"id": "/own/calendar", "label": "Own", "type": "cal", "url": feeds[0] + "?calendar=own"},
        {"id": "exams", "label": "Exams", "type": "plugin", "url": feeds[1] + "?plugin=exams"},
    ]
    for feed in feeds:
        rig.school.statuses[feed] = 403
    rig.school.statuses[CALENDAR_EVENTS_PATH] = 403
    rig.service.check_connection()
    first_day = {feed: rig.hits(feed) for feed in feeds}
    sources = rig.hits(CALENDAR_SOURCES_PATH)
    assert sources == 1 and all(first_day.values())
    rig.polls(40)
    assert rig.service.modules()["modules"][modules.CALENDAR] is False
    assert {feed: rig.hits(feed) for feed in feeds} == first_day
    assert rig.hits(CALENDAR_SOURCES_PATH) == sources
    assert rig.hits(CALENDAR_EVENTS_PATH) == 0
    rig.advance(4 * HOUR)
    rig.poll()
    assert rig.hits(CALENDAR_SOURCES_PATH) == sources + 1


def test_a_refused_path_is_asked_again_once_the_day_is_over(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[LETTERS_PATH] = 403
    rig.service.check_connection()
    rig.polls(40)
    assert rig.hits(SETTINGS_PATH) == 1
    assert rig.hits(LETTERS_PATH) == 1
    rig.advance(REFUSAL_SECONDS)
    rig.poll()
    assert rig.hits(SETTINGS_PATH) == 2
    assert rig.hits(LETTERS_PATH) == 2
    rig.polls(10)
    assert rig.hits(SETTINGS_PATH) == 2
    assert rig.hits(LETTERS_PATH) == 2


def test_a_path_that_turns_200_is_used_again_after_the_day(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[LETTERS_PATH] = 404
    rig.service.check_connection()
    assert rig.service.modules()["modules"][modules.LETTERS] is False
    rig.polls(10)
    rig.school.statuses.pop(LETTERS_PATH)
    rig.school.statuses[SETTINGS_PATH] = 200
    rig.school.payloads[SETTINGS_PATH] = {"timetable_availableForGuardiansAndStudents": True}
    rig.polls(10)
    assert rig.service.modules()["modules"][modules.LETTERS] is False
    assert rig.service._school_settings() == {}
    rig.advance(REFUSAL_SECONDS)
    rig.poll()
    assert rig.service.modules()["modules"][modules.LETTERS] is True
    assert rig.service._school_settings() == {"timetable_availableForGuardiansAndStudents": True}


def test_a_skipped_module_is_probed_in_the_poll_where_the_menu_newly_links_it(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[CONFERENCES_PATH] = 404
    rig.service.check_connection()
    rig.polls(5)
    assert rig.hits(CONFERENCES_PATH) == 1
    rig.school.statuses.pop(CONFERENCES_PATH)
    rig.school.start_page = START_PAGE.replace("</body>", "<a href='/iserv/parentconference/'>Talks</a></body>")
    rig.polls(1)
    assert rig.hits(CONFERENCES_PATH) == 2
    assert rig.service.modules()["modules"][modules.CONFERENCES] is True


def test_a_module_the_menu_linked_all_along_is_not_probed_again_before_the_day_is_over(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[CONFERENCES_PATH] = 404
    rig.school.start_page = START_PAGE.replace("</body>", "<a href='/iserv/parentconference/'>Talks</a></body>")
    rig.service.check_connection()
    rig.polls(20)
    assert rig.hits(CONFERENCES_PATH) == 1


def test_pressing_check_modules_again_asks_every_refused_path_again(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[LETTERS_PATH] = 403
    rig.service.check_connection()
    rig.polls(5)
    rig.school.statuses.pop(LETTERS_PATH)
    rig.advance(HOUR)
    result = rig.service.recheck_modules(clock=lambda: rig.now[0])
    assert result["ok"] is True
    assert rig.hits(LETTERS_PATH) == 2
    assert rig.service.modules()["modules"][modules.LETTERS] is True
    rig.poll()
    assert rig.hits(SETTINGS_PATH) == 2
    assert rig.hits(ME_PATH) == 2


def test_a_new_sign_in_asks_every_refused_path_again(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[LETTERS_PATH] = 403
    rig.service.check_connection()
    rig.polls(5)
    assert rig.hits(LETTERS_PATH) == 1
    rig.service._sign_in._client = None
    rig.advance(HOUR)
    rig.poll()
    assert rig.hits(LETTERS_PATH) == 2
    assert rig.hits(SETTINGS_PATH) >= 2
    assert rig.hits(ME_PATH) == 2


def test_an_expired_school_app_session_is_not_remembered_as_refused(tmp_path):
    rig = Rig(tmp_path)
    rig.school.statuses[SETTINGS_PATH] = 401
    rig.service.check_connection()
    before = rig.hits(SETTINGS_PATH)
    rig.service._settings_cache = (0.0, None)
    rig.service._school_settings()
    assert rig.hits(SETTINGS_PATH) == before + 1


def test_the_menu_probe_and_the_letter_list_read_the_index_once_per_poll(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    assert rig.hits(LETTERS_PATH) == 1
    rig.service.letters()
    assert rig.hits(LETTERS_PATH) == 1
    for poll in range(2, 6):
        rig.advance(30 * 60)
        rig.service.refresh_modules()
        rig.service.letters()
        assert rig.hits(LETTERS_PATH) == poll


def test_the_calendar_probe_and_the_event_read_ask_the_school_once_per_poll(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    window = window_params(date.fromtimestamp(rig.now[0]))
    first = date.fromisoformat(window["start"])
    last = date.fromisoformat(window["end"])
    assert rig.hits(CALENDAR_EVENTS_PATH) == 1
    rig.service.school_events(first, last)
    assert rig.hits(CALENDAR_EVENTS_PATH) == 1
    for poll in range(2, 5):
        rig.advance(30 * 60)
        rig.service.refresh_modules()
        rig.service.school_events(first, last)
        assert rig.hits(CALENDAR_EVENTS_PATH) == poll


def test_the_calendar_probe_hands_its_source_feed_to_the_event_read(tmp_path):
    rig = Rig(tmp_path)
    feed = "/iserv/calendar/feed/calendar"
    plugin = "/iserv/calendar/api/plugin"
    rig.school.payloads[CALENDAR_SOURCES_PATH] = [
        {"id": "/school/calendar", "label": "School", "type": "cal", "url": feed + "?calendar=school"},
        {"id": "exams", "label": "Exams", "type": "plugin", "url": plugin + "?plugin=exams"},
    ]
    rig.school.payloads[feed] = []
    rig.school.payloads[plugin] = []
    rig.service.check_connection()
    assert rig.service.module_available(modules.CALENDAR) is True
    window = window_params(date.fromtimestamp(rig.now[0]))
    first = date.fromisoformat(window["start"])
    last = date.fromisoformat(window["end"])
    for poll in range(1, 4):
        if poll > 1:
            rig.advance(30 * 60)
            rig.service.refresh_modules()
        rig.service.school_events(first, last)
        assert rig.hits(CALENDAR_SOURCES_PATH) == poll
        assert rig.hits(feed) == poll
        assert rig.hits(plugin) == poll
    assert rig.hits(CALENDAR_EVENTS_PATH) == 0


def test_the_menu_probe_and_the_child_list_read_the_time_table_page_once_per_poll(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    client = rig.service._client
    assert rig.hits(TIME_TABLE_PATH) == 1
    client.get_children()
    assert rig.hits(TIME_TABLE_PATH) == 1
    rig.service.refresh_modules()
    client.get_children()
    assert rig.hits(TIME_TABLE_PATH) == 2


def test_a_kept_answer_is_handed_out_only_once(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    client = rig.service._client
    client.get_children()
    client.get_children()
    assert rig.hits(TIME_TABLE_PATH) == 2


def test_a_kept_answer_is_not_handed_out_after_two_minutes(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    client = rig.service._client
    client.get_children()
    stamp = [1000.0]
    client.clock = lambda: stamp[0]
    client.fetch_and_keep(TIME_TABLE_PATH)
    stamp[0] += 121
    client.get_children()
    assert rig.hits(TIME_TABLE_PATH) == 3


def _posting(school):
    school.posted = []

    def post(url, data=None, timeout=None, **kwargs):
        school.posted.append(url)
        return Answer(200, url, "<html></html>")

    def request(method, url, data=None, timeout=None, **kwargs):
        school.posted.append(url)
        return Answer(200, url, "<html></html>")

    school.post = post
    school.request = request


def test_a_write_to_the_school_drops_every_kept_answer_so_the_next_read_is_live(tmp_path):
    rig = Rig(tmp_path)
    _posting(rig.school)
    rig.service.check_connection()
    client = rig.service._client
    for write in (
        lambda: client.post_absolute(BASE + LETTERS_PATH, {"a": "1"}),
        lambda: client.post_form(BASE + LETTERS_PATH, {"a": "1"}),
        lambda: client._post(LETTERS_PATH, {"a": "1"}),
        lambda: client._delete(LETTERS_PATH, {"a": "1"}),
    ):
        client.fetch_and_keep(LETTERS_PATH)
        hits = rig.hits(LETTERS_PATH)
        write()
        client.fetch(LETTERS_PATH)
        assert rig.hits(LETTERS_PATH) == hits + 1
    assert len(rig.school.posted) == 4


def test_a_write_that_reads_with_get_can_drop_the_kept_answers_too(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    client = rig.service._client
    client.fetch_and_keep(LETTERS_PATH)
    hits = rig.hits(LETTERS_PATH)
    client.forget_kept()
    client.fetch(LETTERS_PATH)
    assert rig.hits(LETTERS_PATH) == hits + 1


def test_the_ledger_forgets_after_its_window_and_on_clear():
    now = [0.0]
    ledger = Refusals(lambda: now[0])
    ledger.note("a", 404)
    assert ledger.status_of("a") == 404
    now[0] += REFUSAL_SECONDS - 1
    assert ledger.refused("a")
    now[0] += 1
    assert not ledger.refused("a")
    ledger.note("b")
    ledger.clear()
    assert not ledger.refused("b")


def test_a_failing_calendar_feed_neither_hides_the_calendar_nor_stops_the_probe(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    assert rig.service.module_available(modules.CALENDAR) is True
    rig.school.statuses[CALENDAR_EVENTS_PATH] = 503
    rig.polls(3)
    assert rig.service.module_available(modules.CALENDAR) is True
    assert rig.hits(CALENDAR_SOURCES_PATH) == 4
    rig.school.statuses.pop(CALENDAR_EVENTS_PATH)
    rig.school.payloads[CALENDAR_EVENTS_PATH] = {"error": "busy"}
    rig.polls(3)
    assert rig.hits(CALENDAR_SOURCES_PATH) == 7
    rig.school.payloads.pop(CALENDAR_EVENTS_PATH)
    rig.polls(1)
    assert rig.service.module_available(modules.CALENDAR) is True


def test_a_kept_answer_does_not_stop_a_read_with_listed_or_odd_parameters(tmp_path):
    rig = Rig(tmp_path)
    rig.service.check_connection()
    client = rig.service._client
    assert client._kept
    for params in ({"filterBy": ["a", "b"]}, [("filterBy", ["a"]), ("x", "1")], {"nested": {"a": [1]}}, "a=1"):
        assert client.fetch(LETTERS_PATH, params).status_code == 200
    client.fetch_and_keep(LETTERS_PATH, {"filterBy": ["a", "b"]})
    hits = rig.hits(LETTERS_PATH)
    client.fetch(LETTERS_PATH, {"filterBy": ["a", "b"]})
    assert rig.hits(LETTERS_PATH) == hits


class WeekSession:
    def __init__(self, refused):
        self.refused = refused
        self.asked = []

    def get(self, url, params=None, timeout=None):
        self.asked.append((url[len(BASE):], dict(params or {})))
        values = {str(value) for value in (params or {}).values()}
        status = 403 if values & self.refused else 200
        return Answer(status, url, payload=[] if status == 200 else None)


def test_a_refused_week_or_child_does_not_block_another_one():
    from app.iserv.dsa import DieSchulAppClient, timetable_params

    first, second = date(2026, 10, 12), date(2026, 10, 19)
    refused_week = timetable_params(first, [], False)["date"]
    session = WeekSession({refused_week})
    client = DieSchulAppClient(BASE, session, refusals=Refusals(lambda: 0.0))
    assert client.current_timetable(first, []) is None
    assert client.current_timetable(second, []) == []
    assert client.current_timetable(first, []) is None
    assert client.current_timetable(second, []) == []
    assert [params["date"] for path, params in session.asked] == [refused_week, timetable_params(second, [], False)["date"], timetable_params(second, [], False)["date"]]
    session.asked.clear()
    session.refused = {"initiatingRepeatRequest:is(null)"}
    path = "requestToSchools/studentAbsence/"
    assert client.user_requests(path) == []
    assert client.user_requests(path, 8) == []
    assert client.user_requests(path) == []
    assert len(session.asked) == 2


def test_a_readable_plugin_source_makes_the_calendar_available_when_the_own_feed_is_refused(tmp_path):
    rig = Rig(tmp_path)
    feed = "/iserv/calendar/feed/calendar"
    plugin = "/iserv/calendar/api/plugin"
    rig.school.payloads[CALENDAR_SOURCES_PATH] = [
        {"id": "/own/home", "label": "Own", "type": "cal", "url": feed + "?cal=own"},
        {"id": "exam-plan", "label": "Exams", "type": "plugin", "url": plugin + "?plugin=exam-plan"},
    ]
    rig.school.statuses[feed] = 403
    rig.school.payloads[plugin] = []
    rig.service.check_connection()
    assert rig.service.module_available(modules.CALENDAR) is True
    assert rig.hits(plugin) >= 1
