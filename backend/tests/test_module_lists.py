import json
from types import SimpleNamespace

from app import account_poll, integration
from app.iserv.errors import DataError, OutageError
from app.module_pages import ModulePages
from app.store import Store
from tests.account_fakes import page as school_page
from tests.module_pages_school import ModuleConnection, ModuleSchool, TODO_ANSWER
from tests.support import add_school

NOW = 1_791_000_000


def pages(school=None):
    return ModulePages(ModuleConnection(school or ModuleSchool()))


class Account:
    def __init__(self, offered=None, lists=None):
        self.offered = offered or {}
        self.lists = lists or {}
        self.read = []

    def account_modules(self):
        return self.offered

    def module_notices(self, slug):
        self.read.append(slug)
        answer = self.lists[slug]
        if isinstance(answer, Exception):
            raise answer
        return answer


def setup(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school-one.example")
    poller = SimpleNamespace(store=store, clock=lambda: poller.now, now=NOW)
    integration.note_request(store, NOW)
    return poller, store, connection_id


def stored(store, connection_id, field):
    return integration.school_list(integration.school_state(store, connection_id), field)


def test_the_rows_of_a_module_page_are_counted_and_named_by_their_first_cell():
    listed = pages().notices("print")
    assert listed["count"] == 2
    assert [item["title"] for item in listed["items"]] == ["Elternbrief.pdf", "Liste.pdf"]


def test_only_open_to_dos_count_and_keep_their_due_date():
    listed = pages().notices("todo")
    still_open = [task for task in TODO_ANSWER["tasks"] if not task.get("completed")]
    assert listed["count"] == len(still_open)
    assert [item["title"] for item in listed["items"]] == [task["summary"] for task in still_open]
    assert all("date" in item for item in listed["items"])


def test_a_to_do_without_a_summary_is_listed_by_its_description():
    answer = {"tasks": [{"uid": "u1", "summary": "", "description": "Sportzeug", "completed": None}], "revision": "x"}
    school = ModuleSchool(pages={"/iserv/todo/api/frontend/tasks": json.dumps(answer)})
    assert pages(school).notices("todo")["items"][0]["title"] == "Sportzeug"


def test_a_page_without_a_list_is_unknown_and_not_empty():
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", "<p>Hier steht etwas.</p>")})
    assert pages(school).notices("poll") is None


def test_an_empty_table_counts_as_empty():
    body = "<table><thead><tr><th>Titel</th></tr></thead><tbody></tbody></table>"
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", body)})
    assert pages(school).notices("poll") == {"items": [], "count": 0}


def test_only_offered_modules_are_read_and_stored(tmp_path):
    account = Account({"print": True}, {"print": {"items": [{"title": "Brief.pdf"}], "count": 3}})
    poller, store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert account.read == ["print"]
    assert stored(store, connection_id, "print_jobs")["count"] == 3
    assert stored(store, connection_id, "print_jobs")["items"][0]["title"] == "Brief.pdf"
    assert stored(store, connection_id, "polls") is None


def test_a_module_is_read_at_most_once_an_hour(tmp_path):
    account = Account({"print": True}, {"print": {"items": [], "count": 0}})
    poller, _store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    poller.now += account_poll.MODULE_LIST_SECONDS - 1
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert account.read == ["print"]
    poller.now += 1
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert account.read == ["print", "print"]


def test_an_unreadable_page_keeps_the_last_list_and_is_asked_again_an_hour_later(tmp_path):
    account = Account({"print": True}, {"print": {"items": [], "count": 2}})
    poller, store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    account.lists["print"] = DataError("unreadable")
    poller.now += account_poll.MODULE_LIST_SECONDS
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert stored(store, connection_id, "print_jobs")["count"] == 2
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert account.read == ["print", "print"]


def test_a_refused_page_is_unknown():
    assert pages(ModuleSchool(status=403)).notices("print") is None
    assert pages(ModuleSchool(status=403)).notices("todo") is None


def test_a_page_without_a_list_makes_the_count_unknown(tmp_path):
    account = Account({"poll": True}, {"poll": {"items": [], "count": 1}})
    poller, store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    account.lists = {"poll": None}
    poller.now += account_poll.MODULE_LIST_SECONDS
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert stored(store, connection_id, "polls") is None


def test_a_row_that_only_says_nothing_is_there_does_not_count():
    body = '<table><thead><tr><th>Titel</th><th>Stand</th></tr></thead><tbody><tr><td colspan="2">Keine Einträge</td></tr></tbody></table>'
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", body)})
    assert pages(school).notices("poll") == {"items": [], "count": 0}


def test_a_list_with_more_pages_is_unknown():
    body = (
        "<table><thead><tr><th>Titel</th></tr></thead><tbody><tr><td>Eins</td></tr></tbody></table>"
        '<ul><li><a href="/iserv/poll?page=2">Weiter</a></li></ul>'
    )
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", body)})
    assert pages(school).notices("poll") is None


def test_a_page_with_two_tables_is_unknown():
    table = "<table><thead><tr><th>Titel</th></tr></thead><tbody><tr><td>Eins</td></tr></tbody></table>"
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", table + table)})
    assert pages(school).notices("poll") is None


def test_a_date_in_the_first_cell_does_not_become_the_title():
    body = "<table><thead><tr><th>Datum</th><th>Titel</th></tr></thead><tbody><tr><td>12.10.2026</td><td>Klassenfahrt</td></tr></tbody></table>"
    school = ModuleSchool(pages={"/iserv/poll": school_page("Umfragen", body)})
    assert pages(school).notices("poll")["items"] == [{"title": "Klassenfahrt"}]


def test_a_count_that_cannot_be_read_again_for_a_day_becomes_unknown(tmp_path):
    account = Account({"print": True}, {"print": {"items": [], "count": 2}})
    poller, store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    account.lists["print"] = DataError("unreadable")
    poller.now += account_poll.MODULE_LIST_STALE_SECONDS - 1
    integration.note_request(store, poller.now)
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert stored(store, connection_id, "print_jobs")["count"] == 2
    poller.now += account_poll.MODULE_LIST_SECONDS
    integration.note_request(store, poller.now)
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert stored(store, connection_id, "print_jobs") is None


def test_nothing_is_read_while_home_assistant_is_not_connected(tmp_path):
    account = Account({"print": True}, {"print": {"items": [], "count": 2}})
    poller, _store, connection_id = setup(tmp_path)
    poller.now += integration.ACTIVE_WINDOW_SECONDS + 1
    account_poll.poll_module_lists(poller, account, connection_id, {})
    assert account.read == []


def test_a_module_the_school_no_longer_offers_is_forgotten(tmp_path):
    account = Account({"print": True}, {"print": {"items": [], "count": 2}})
    poller, store, connection_id = setup(tmp_path)
    state = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    account.offered = {}
    account_poll.poll_module_lists(poller, account, connection_id, state)
    assert stored(store, connection_id, "print_jobs") is None
    assert state[account_poll.MODULE_LISTS_KEY] == {}


def test_an_outage_does_not_fail_the_school_and_stops_the_other_modules(tmp_path):
    account = Account({"todo": True, "print": True}, {"todo": OutageError("rate_limited"), "print": {"items": [], "count": 1}})
    poller, _store, connection_id = setup(tmp_path)
    account_poll.poll_module_lists(poller, account, connection_id, {})
    assert account.read == ["todo"]
