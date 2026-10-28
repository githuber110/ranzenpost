import logging

import pytest

from app import integration, modules, school_lists
from app.iserv import exercises
from app.iserv.errors import DataError, ModulePageRefusedError, OutageError
from app.iserv.exercises import EXERCISE_PATH, PAST_EXERCISE_PATH
from app.iserv.news import NEWS_PATH
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_refused_probes import Answer, Rig

BASE = "https://school.example"
HEAD = "<thead><tr><th></th><th>Aufgabe</th><th>Starttermin</th><th>Abgabetermin</th><th>Tags</th><th>Erledigt</th></tr></thead>"


def task_row(number, title, due, done="Nein"):
    return (
        f'<tr><td><input type="checkbox"></td><td><a href="/iserv/exercise/show/{number}">{title}</a></td>'
        f"<td>01.10.2026</td><td>{due}</td><td></td><td>{done}</td></tr>"
    )


def task_page(rows, extra=""):
    return f'<html><body><table id="crud-table">{HEAD}<tbody>{"".join(rows)}</tbody></table>{extra}</body></html>'


NEWS_PAGE = """<html><body><h1>Alle News</h1><ul>
<li><a href="/iserv/news/general/2">Second</a> <span class="date">02.10.2026</span></li>
<li><a href="/iserv/news/general/1">First</a></li></ul></body></html>"""


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def fetch(self, path, params=None):
        self.asked.append(path)
        found = self.pages.get(path)
        if found is None:
            return Answer(404, BASE + path)
        if isinstance(found, Answer):
            return found
        return Answer(200, BASE + path, found)


def test_tasks_read_the_current_and_the_past_list_without_school_links():
    pages = Pages({
        EXERCISE_PATH: task_page([task_row(2, "Later", "20.10.2026"), task_row(1, "Sooner", "10.10.2026")]),
        PAST_EXERCISE_PATH: task_page([task_row(9, "Old", "01.09.2026", "Ja")]),
    })
    listed = school_lists.read_tasks(pages)
    assert [(task["title"], task["past"]) for task in listed["tasks"]] == [("Sooner", False), ("Later", False), ("Old", True)]
    assert listed["tasks"][0]["path"] == "/iserv/exercise/show/1"
    assert "open_url" not in listed and all("open_url" not in task for task in listed["tasks"])
    assert pages.asked == [EXERCISE_PATH, PAST_EXERCISE_PATH]


def test_every_further_page_of_a_list_is_read_once():
    second = EXERCISE_PATH + "?page=2"
    pagination = f'<ul class="pagination"><li><a href="{second}">2</a></li></ul>'
    pages = Pages({
        EXERCISE_PATH: task_page([task_row(1, "One", "10.10.2026")], pagination),
        second: task_page([task_row(2, "Two", "11.10.2026")], pagination.replace(second, EXERCISE_PATH + "?page=1")),
        EXERCISE_PATH + "?page=1": task_page([task_row(1, "One", "10.10.2026")]),
        PAST_EXERCISE_PATH: task_page([]),
    })
    listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1", "2"]
    assert pages.asked.count(second) == 1


def test_a_refused_or_unknown_past_list_still_shows_the_current_tasks_and_is_logged_once(caplog):
    exercises._NOTED.clear()
    pages = Pages({EXERCISE_PATH: task_page([task_row(1, "One", "10.10.2026")])})
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(3):
            listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1"]
    assert len([record for record in caplog.records if "past/exercise" in record.getMessage()]) == 1


@pytest.mark.parametrize("status, error", [(403, ModulePageRefusedError), (404, ModulePageRefusedError), (302, DataError)])
def test_a_refused_current_list_is_an_error_and_not_an_empty_list(status, error):
    with pytest.raises(error):
        school_lists.read_tasks(Pages({EXERCISE_PATH: Answer(status, BASE + EXERCISE_PATH)}))


def test_a_server_failure_is_an_outage():
    with pytest.raises(OutageError):
        school_lists.read_news(Pages({NEWS_PATH: Answer(503, BASE + NEWS_PATH)}))


def test_a_page_that_lands_on_the_sign_in_is_no_list():
    with pytest.raises(DataError):
        school_lists.read_news(Pages({NEWS_PATH: Answer(200, BASE + "/iserv/auth/login", "<html></html>")}))


def test_a_task_page_without_its_table_is_unreadable_and_not_empty():
    with pytest.raises(DataError):
        school_lists.read_tasks(Pages({EXERCISE_PATH: "<html><body>maintenance</body></html>"}))


EMPTY_NEWS = '<html><body><h1>Alle News</h1><ul class="nav"><li><a href="/iserv/news/general">General</a></li></ul><p>Keine News</p></body></html>'


def test_a_news_page_without_item_links_is_an_empty_list_logged_once(caplog):
    exercises._NOTED.clear()
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            assert school_lists.read_news(Pages({NEWS_PATH: EMPTY_NEWS}))["news"] == []
    assert [record.getMessage() for record in caplog.records] == ["news page shape unknown at /iserv/news: no item links"]


def test_a_news_page_without_any_news_list_is_unreadable_and_not_empty():
    with pytest.raises(DataError):
        school_lists.read_news(Pages({NEWS_PATH: "<html><body><h1>Bitte Passwort ändern</h1><p>Text</p></body></html>"}))


@pytest.mark.parametrize("landing", ["/iserv/", "/iserv/profile/password", "/iserv/terms"])
def test_a_list_page_answered_by_another_page_is_unreadable_and_not_empty(landing):
    with pytest.raises(DataError):
        school_lists.read_news(Pages({NEWS_PATH: Answer(200, BASE + landing, EMPTY_NEWS)}))
    with pytest.raises(DataError):
        school_lists.read_tasks(Pages({EXERCISE_PATH: Answer(200, BASE + landing, task_page([]))}))


def test_the_first_page_link_is_not_fetched_again():
    pagination = f'<ul class="pagination"><li><a href="?page=1">1</a></li><li><a href="?page=2">2</a></li></ul>'
    pages = Pages({
        EXERCISE_PATH: task_page([task_row(1, "One", "10.10.2026")], pagination),
        EXERCISE_PATH + "?page=2": task_page([task_row(2, "Two", "11.10.2026")], pagination),
        PAST_EXERCISE_PATH: task_page([]),
    })
    listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1", "2"]
    assert pages.asked == [EXERCISE_PATH, EXERCISE_PATH + "?page=2", PAST_EXERCISE_PATH]
    assert listed["carry"] == []


def test_paging_stops_when_a_page_brings_no_new_entry():
    def pagination(number):
        return f'<ul class="pagination"><li><a href="{NEWS_PATH}?page={number}">{number}</a></li></ul>'

    pages = Pages({
        NEWS_PATH: NEWS_PAGE.replace("</body>", pagination(2) + "</body>"),
        NEWS_PATH + "?page=2": NEWS_PAGE.replace("</body>", pagination(3) + "</body>"),
        NEWS_PATH + "?page=3": NEWS_PAGE,
    })
    listed = school_lists.read_news(pages)
    assert [item["id"] for item in listed["news"]] == ["general/2", "general/1"]
    assert pages.asked == [NEWS_PATH, NEWS_PATH + "?page=2"]


@pytest.mark.parametrize("failure", [Answer(429, BASE + EXERCISE_PATH + "?page=2"), Answer(503, BASE + EXERCISE_PATH + "?page=2"), "<html>no table</html>"])
def test_a_failing_deeper_page_keeps_the_first_pages_and_asks_to_carry_the_rest(failure):
    pagination = f'<ul class="pagination"><li><a href="{EXERCISE_PATH}?page=2">2</a></li></ul>'
    pages = Pages({
        EXERCISE_PATH: task_page([task_row(1, "One", "10.10.2026")], pagination),
        EXERCISE_PATH + "?page=2": failure,
        PAST_EXERCISE_PATH: task_page([task_row(9, "Old", "01.09.2026", "Ja")]),
    })
    listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1", "9"]
    assert listed["carry"] == ["current"]


@pytest.mark.parametrize("failure", [Answer(503, BASE + PAST_EXERCISE_PATH), Answer(200, BASE + "/iserv/"), "<html>maintenance</html>"])
def test_a_failing_past_list_asks_to_carry_the_earlier_past_tasks(failure):
    pages = Pages({EXERCISE_PATH: task_page([task_row(1, "One", "10.10.2026")]), PAST_EXERCISE_PATH: failure})
    listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1"]
    assert listed["carry"] == ["past"]


def test_the_page_limit_is_logged_once(caplog, monkeypatch):
    exercises._NOTED.clear()
    monkeypatch.setattr(school_lists, "PAGE_LIMIT", 2)
    def numbered(number):
        link = f'<ul class="pagination"><li><a href="{EXERCISE_PATH}?page={number + 1}">next</a></li></ul>'
        return task_page([task_row(number, "Task %d" % number, "10.10.2026")], link)

    pages = Pages({EXERCISE_PATH: numbered(1), **{EXERCISE_PATH + "?page=%d" % number: numbered(number) for number in range(2, 6)}, PAST_EXERCISE_PATH: task_page([])})
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            listed = school_lists.read_tasks(pages)
    assert [task["id"] for task in listed["tasks"]] == ["1", "2"]
    assert [record.getMessage() for record in caplog.records if "limit" in record.getMessage()] == [
        "exercise page shape unknown at /iserv/exercise: page limit 2 reached"
    ]


def test_carried_entries_fill_in_only_the_parts_that_could_not_be_read():
    stored = [dict(TASK, id="5"), dict(PAST, id="6"), dict(TASK, id="1", title="Old title")]
    listed = {"tasks": [TASK], "carry": ["past"]}
    assert [item["id"] for item in school_lists.carried(listed, "tasks", stored)] == ["1", "6"]
    assert school_lists.carried({"tasks": [TASK], "carry": []}, "tasks", stored) == [TASK]
    assert [item["id"] for item in school_lists.carried({"tasks": [TASK], "carry": ["current"]}, "tasks", stored)] == ["1", "5"]


def test_news_read_every_item_without_school_links():
    listed = school_lists.read_news(Pages({NEWS_PATH: NEWS_PAGE}))
    assert [(item["title"], item["date"]) for item in listed["news"]] == [("Second", "2026-10-02"), ("First", "")]
    assert listed["news"][0]["path"] == "/iserv/news/general/2"
    assert "open_url" not in listed and all("open_url" not in item for item in listed["news"])


class ListSchoolRig(Rig):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        original = self.school.get

        def get(url, params=None, timeout=None, **kwargs):
            path = url[len(BASE):]
            if path == EXERCISE_PATH:
                self.school.hits[path] += 1
                return Answer(200, url, task_page([task_row(1, "One", "10.10.2026")]))
            if path == NEWS_PATH:
                self.school.hits[path] += 1
                return Answer(200, url, NEWS_PAGE)
            return original(url, params, timeout, **kwargs)

        self.school.get = get


def test_the_probe_and_the_read_share_one_request_per_poll(tmp_path):
    rig = ListSchoolRig(tmp_path)
    rig.service.check_connection()
    assert rig.service.module_available(modules.TASKS) is True
    assert rig.service.module_available(modules.NEWS) is True
    assert rig.hits(EXERCISE_PATH) == 1
    assert rig.hits(NEWS_PATH) == 1
    rig.service.tasks()
    rig.service.news()
    assert rig.hits(EXERCISE_PATH) == 1
    assert rig.hits(NEWS_PATH) == 1
    rig.advance(30 * 60)
    rig.service.refresh_modules()
    rig.service.tasks()
    assert rig.hits(EXERCISE_PATH) == 2


def test_a_probe_that_is_sent_back_to_the_start_page_keeps_the_modules_off(tmp_path):
    rig = Rig(tmp_path)
    original = rig.school.get

    def get(url, params=None, timeout=None, **kwargs):
        if url.endswith(EXERCISE_PATH) or url.endswith(NEWS_PATH):
            return Answer(200, BASE + "/iserv/")
        return original(url, params, timeout, **kwargs)

    rig.school.get = get
    rig.service.check_connection()
    assert rig.service.module_available(modules.TASKS) is False
    assert rig.service.module_available(modules.NEWS) is False


TASK = {"id": "1", "title": "One", "due": "2026-10-10", "past": False, "done": False, "path": "/iserv/exercise/show/1"}
PAST = {"id": "9", "title": "Old", "due": "2026-09-01", "past": True, "done": True, "path": ""}
NEWS = {"id": "general/1", "title": "First", "date": "2026-10-01", "category": "General", "category_slug": "general"}


class ListConnection:
    def __init__(self, connection_id, tasks=None, news=None, failure=None):
        self.id = connection_id
        self.listed_tasks = tasks if tasks is not None else []
        self.listed_news = news if news is not None else []
        self.failure = failure
        self.store = None
        self.carry = []

    def tasks(self):
        if self.failure is not None:
            raise self.failure
        return {"tasks": list(self.listed_tasks), "carry": list(self.carry)}

    def news(self):
        if self.failure is not None:
            raise self.failure
        return {"news": list(self.listed_news)}


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    pushes = []
    poller = Poller(None, store=store, notifiers={
        "tasks": lambda name, message: pushes.append(("tasks", message)) or True,
        "news": lambda name, message: pushes.append(("news", message)) or True,
    })
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id, pushes


TASK_SPEC = next(spec for spec in __import__("app.poller", fromlist=["SCHOOL_LISTS"]).SCHOOL_LISTS if spec[0] == modules.TASKS)
NEWS_SPEC = next(spec for spec in __import__("app.poller", fromlist=["SCHOOL_LISTS"]).SCHOOL_LISTS if spec[0] == modules.NEWS)


def test_the_poll_keeps_the_lists_per_school_and_pushes_only_new_open_tasks(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    first = poller._poll_school_list(ListConnection(connection_id, [TASK, PAST]), connection_id, True, TASK_SPEC, state, "en")
    assert first == {"module": "tasks", "items": 2, "initialized": 1}
    assert pushes == []
    stored = store.load_calendar_snapshot()["tasks"][connection_id]
    assert stored == {"tasks": [TASK, PAST], "last_success": 1_791_000_000}
    newer = dict(TASK, id="2", title="Two")
    old_past = dict(PAST, id="8")
    second = poller._poll_school_list(ListConnection(connection_id, [TASK, newer, PAST, old_past]), connection_id, True, TASK_SPEC, state, "en")
    assert second == {"module": "tasks", "items": 4, "new": 1}
    assert pushes == [("tasks", "New task: open the app to see it")]


def test_the_poll_pushes_new_news(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poller._poll_school_list(ListConnection(connection_id, news=[NEWS]), connection_id, True, NEWS_SPEC, state, "en")
    fresh = [dict(NEWS, id="general/2"), dict(NEWS, id="general/3"), NEWS]
    event = poller._poll_school_list(ListConnection(connection_id, news=fresh), connection_id, True, NEWS_SPEC, state, "en")
    assert event == {"module": "news", "items": 3, "new": 2}
    assert pushes == [("news", "2 new news items: open the app to read them")]


def test_an_unreadable_list_keeps_the_last_one_and_does_not_fail_the_poll(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poller._poll_school_list(ListConnection(connection_id, [TASK]), connection_id, True, TASK_SPEC, state)
    event = poller._poll_school_list(ListConnection(connection_id, failure=DataError("no table")), connection_id, True, TASK_SPEC, state)
    assert event == {"module": "tasks", "state": "unreadable"}
    assert store.load_calendar_snapshot()["tasks"][connection_id]["tasks"] == [TASK]
    assert state["task_ids"] == {"1": 1_791_000_000}


def test_a_refused_or_switched_off_list_is_dropped(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poller._poll_school_list(ListConnection(connection_id, [TASK]), connection_id, True, TASK_SPEC, state)
    event = poller._poll_school_list(ListConnection(connection_id, failure=ModulePageRefusedError("403")), connection_id, True, TASK_SPEC, state)
    assert event == {"module": "tasks", "state": "refused"}
    assert connection_id not in store.load_calendar_snapshot()["tasks"]
    assert "task_ids" not in state
    poller._poll_school_list(ListConnection(connection_id, news=[NEWS]), connection_id, True, NEWS_SPEC, state)
    assert poller._poll_school_list(ListConnection(connection_id), connection_id, False, NEWS_SPEC, state) is None
    assert connection_id not in store.load_calendar_snapshot()["news"]
    assert integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)["news"] is None


def test_an_outage_is_raised_to_the_poll(tmp_path):
    poller, _store, connection_id, _pushes = poller_for(tmp_path)
    with pytest.raises(OutageError):
        poller._poll_school_list(ListConnection(connection_id, failure=OutageError("timeout")), connection_id, True, NEWS_SPEC, {})


class HolidaysStub:
    def range_info(self, first, last, config, partial=False):
        return {"status": "ok", "days": {}}


def test_home_assistant_reads_open_tasks_and_news_per_school(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    poller._poll_school_list(ListConnection(connection_id, [TASK, PAST]), connection_id, True, TASK_SPEC, {})
    poller._poll_school_list(ListConnection(connection_id, news=[NEWS]), connection_id, True, NEWS_SPEC, {})
    school = integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)
    assert school["open_tasks"] == {
        "count": 1,
        "items": [{"title": "One", "sender": "", "date": "2026-10-10", "child": "", "id": "1"}],
        "fresh": [],
    }
    assert school["news"] == {
        "count": 1,
        "items": [{"title": "First", "sender": "General", "date": "2026-10-01", "child": "", "id": "general/1"}],
        "fresh": [],
    }


def test_a_school_never_polled_for_tasks_answers_none_for_home_assistant(tmp_path):
    _poller, store, connection_id, _pushes = poller_for(tmp_path)
    school = integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)
    assert school["open_tasks"] is None
    assert school["news"] is None


def test_the_app_lists_merge_the_stored_snapshot_of_every_school(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    store.save_modules({"modules": {modules.TASKS: True, modules.NEWS: True}})
    poller._poll_school_list(ListConnection(connection_id, [PAST, TASK]), connection_id, True, TASK_SPEC, {})
    service = IServService(store)
    connection = service.connections()[0]
    connection.store.save_modules({"modules": {modules.TASKS: True, modules.NEWS: True}})
    listed = service.tasks()
    assert [task["id"] for task in listed["tasks"]] == ["1", "9"]
    assert listed["tasks"][0]["connection_id"] == connection_id
    assert listed["schools"][0]["last_success"] == 1_791_000_000
    assert all("open_url" not in entry for entry in listed["schools"] + listed["tasks"])
    assert listed["unavailable"] == []


def poll_list(poller, connection_id, spec, state, clock, **listed):
    poller.clock = lambda: clock
    return poller._poll_school_list(ListConnection(connection_id, **listed), connection_id, True, spec, state, "en")


def open_tasks(store, connection_id, now=1_791_000_000):
    return integration.build_school(store, HolidaysStub(), now, connection_id)["open_tasks"]


def test_a_snapshot_from_before_the_update_answers_without_its_school_links(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    stale = dict(TASK, open_url=BASE + "/iserv/exercise/show/1")
    store.save_calendar_snapshot({"tasks": {connection_id: {"tasks": [stale], "open_url": BASE + "/iserv/exercise", "last_success": 1_791_000_000}}})
    service = IServService(store)
    service.connections()[0].store.save_modules({"modules": {modules.TASKS: True, modules.NEWS: True}})
    listed = service.tasks()
    assert [task["id"] for task in listed["tasks"]] == ["1"]
    assert all("open_url" not in entry for entry in listed["schools"] + listed["tasks"])

def test_a_new_task_is_pushed_and_offered_to_home_assistant_once_with_its_id(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=[TASK])
    newer = dict(TASK, id="2", title="Two")
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_001_800, tasks=[TASK, newer])
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_003_600, tasks=[TASK, newer])
    assert pushes == [("tasks", "New task: open the app to see it")]
    assert open_tasks(store, connection_id)["fresh"] == [{
        "title": "Two", "sender": "", "date": "2026-10-10", "child": "", "id": "2", "seen": 1_791_001_800,
    }]


def test_a_changed_due_date_or_a_shifted_window_does_not_count_as_new(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    many = [dict(TASK, id=str(number), title="Task %d" % number, due="2026-10-%02d" % (number + 10)) for number in range(1, 13)]
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=many)
    moved = [dict(task, due="2026-11-30") if task["id"] == "1" else task for task in many]
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_001_800, tasks=moved)
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_003_600, tasks=moved[1:])
    assert pushes == []
    assert open_tasks(store, connection_id)["fresh"] == []


def test_a_list_that_blinks_empty_or_a_task_that_comes_back_is_not_new_again(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=[TASK, PAST])
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_001_800, tasks=[])
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_003_600, tasks=[TASK, PAST])
    returned = dict(PAST, past=False, done=False)
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_005_400, tasks=[TASK, returned])
    assert pushes == []
    assert open_tasks(store, connection_id)["fresh"] == []


def test_ids_from_before_the_update_count_as_known(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {"task_ids": ["1"]}
    event = poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=[TASK])
    assert event == {"module": "tasks", "items": 1, "new": 0}
    assert pushes == []
    assert state["task_ids"] == {"1": 1_791_000_000}


def test_ids_unseen_for_half_a_year_are_forgotten(tmp_path):
    poller, _store, connection_id, _pushes = poller_for(tmp_path)
    state = {"news_ids": {"general/0": 1_791_000_000 - 181 * 86400, "general/1": 1_791_000_000 - 10}}
    poll_list(poller, connection_id, NEWS_SPEC, state, 1_791_000_000, news=[NEWS])
    assert state["news_ids"] == {"general/1": 1_791_000_000}


def test_a_partly_read_list_keeps_the_stored_entries_of_the_unread_part(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=[TASK, PAST])
    connection = ListConnection(connection_id, [TASK])
    connection.carry = ["past"]
    poller._poll_school_list(connection, connection_id, True, TASK_SPEC, state, "en")
    assert [task["id"] for task in store.load_calendar_snapshot()["tasks"][connection_id]["tasks"]] == ["1", "9"]


def test_an_unexpected_failure_keeps_the_list_and_does_not_fail_the_poll(tmp_path, caplog):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poll_list(poller, connection_id, TASK_SPEC, state, 1_791_000_000, tasks=[TASK])
    with caplog.at_level(logging.WARNING, logger="app.poller"):
        event = poller._poll_school_list(ListConnection(connection_id, failure=KeyError("x")), connection_id, True, TASK_SPEC, state)
    assert event == {"module": "tasks", "state": "unreadable", "kind": "KeyError"}
    assert store.load_calendar_snapshot()["tasks"][connection_id]["tasks"] == [TASK]
    assert [record.exc_info is not None for record in caplog.records] == [True]


def test_the_app_reads_a_list_before_the_first_poll_once_and_keeps_it(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    service = IServService(store)
    connection = service.connections()[0]
    connection.store.save_modules({"modules": {modules.TASKS: True, modules.NEWS: True}})
    reads = []
    connection.tasks = lambda: reads.append("tasks") or {"tasks": [TASK], "carry": []}
    first = service.tasks()
    second = service.tasks()
    assert reads == ["tasks"]
    assert [task["id"] for task in first["tasks"]] == [task["id"] for task in second["tasks"]] == ["1"]
    assert store.load_calendar_snapshot()["tasks"][connection_id]["tasks"] == [TASK]
