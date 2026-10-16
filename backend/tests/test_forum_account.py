import pytest
import requests

from app import account_lists, account_poll, integration, modules, school_lists
from app.forum_service import ForumService, read_form, read_payload
from app.iserv.errors import DataError, ModulePageRefusedError, OutageError
from app.iserv.forums import FORUMS_PATH
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_refused_probes import Answer

BASE = "https://school.example"
HEAD = "<thead><tr><th>Titel</th><th>Beiträge</th><th>Neu</th><th>Letzter Beitrag</th></tr></thead>"
READ_FORM = (
    '<form action="/iserv/forum/read" method="post"><input type="hidden" name="forum_mark_read[_token]" value="tok-1">'
    '<button type="submit" name="forum_mark_read[submit]">Alle gelesen markieren</button></form>'
)


def overview(unread=(3, 0), form=READ_FORM):
    rows = "".join(
        f'<tr><td><a href="/iserv/forum/{1000 + index}">Forum {index}</a></td><td>9</td><td>{count}</td><td>03.10.2026 14:05</td></tr>'
        for index, count in enumerate(unread)
    )
    return f'<html><body>{form}<table id="forum-list">{HEAD}<tbody>{rows}</tbody></table></body></html>'


class School:
    def __init__(self, pages, answer=None, failure=None):
        self.pages = list(pages)
        self.posted = []
        self.answer = answer or Answer(200, BASE + FORUMS_PATH, "<html></html>")
        self.failure = failure

    def fetch(self, path, params=None):
        html = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        return Answer(200, BASE + path, html)

    def post_form(self, url, data, files=None, headers=None, timeout=60):
        self.posted.append((url, list(data), dict(headers or {})))
        if self.failure is not None:
            raise self.failure
        return self.answer


class Connection:
    def __init__(self, store, connection_id, school):
        self.store = store
        self.id = connection_id
        self.school = school
        self.clock = lambda: 1_791_000_000

    def _session(self):
        return self.school


@pytest.fixture
def store_and_id(tmp_path):
    store = Store(tmp_path / "data")
    return store, add_school(store, BASE)


def service_for(store, connection_id, school):
    return ForumService(Connection(store, connection_id, school))


def test_marking_everything_read_needs_the_confirmation_and_sends_nothing_without(store_and_id):
    store, connection_id = store_and_id
    school = School([overview()])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=False)
    assert result["ok"] is False
    assert result["message_key"] == "api.forums.read.unconfirmed"
    assert school.posted == []


def test_marking_everything_read_posts_the_form_of_the_page_and_checks_the_overview(store_and_id):
    store, connection_id = store_and_id
    school = School([overview((3, 0)), overview((0, 0))])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["ok"] is True
    assert result["outcome"] == "done"
    url, data, headers = school.posted[0]
    assert url == BASE + "/iserv/forum/read"
    assert data == [("forum_mark_read[_token]", "tok-1"), ("forum_mark_read[submit]", "")]
    assert headers["Referer"] == BASE + FORUMS_PATH
    stored = school_lists.stored_list(store, connection_id, account_lists.FORUMS_FIELD)
    assert [forum["unread"] for forum in stored["forums"]] == [0, 0]


def test_a_page_without_the_read_form_sends_nothing(store_and_id):
    store, connection_id = store_and_id
    school = School([overview(form="")])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["outcome"] == "unavailable"
    assert school.posted == []


def test_unread_posts_after_sending_leave_the_outcome_open(store_and_id):
    store, connection_id = store_and_id
    school = School([overview((3, 0)), overview((3, 0))])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["ok"] is False
    assert result["outcome"] == "uncertain"


@pytest.mark.parametrize("answer", [
    Answer(403, BASE + "/iserv/forum/read", "<html>Verboten</html>"),
    Answer(200, BASE + "/iserv/auth/login", '<form method="post"><input type="password" name="_password"></form>'),
])
def test_a_refusing_school_is_reported_as_refused(store_and_id, answer):
    store, connection_id = store_and_id
    school = School([overview((3, 0))], answer=answer)
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["outcome"] == "rejected"


def test_a_failed_request_leaves_the_outcome_open(store_and_id):
    store, connection_id = store_and_id
    school = School([overview((3, 0)), overview((0, 0))], failure=requests.ConnectionError("down"))
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["outcome"] == "uncertain"


def test_the_payload_keeps_hidden_fields_and_one_submit():
    form = read_form(
        '<form action="/iserv/forum/read" method="post"><input type="hidden" name="a[_token]" value="t">'
        '<input type="checkbox" name="a[x]" value="1"><button name="a[submit]">Go</button><button name="a[other]">No</button></form>',
        BASE + FORUMS_PATH,
    )
    assert read_payload(form) == [("a[_token]", "t"), ("a[submit]", "")]


FORUM = {"id": "1000", "title": "Schulhof", "category": "Allgemein", "unread": 2, "last_post": "Pausen 03.10.2026 14:05", "last_post_date": "2026-10-03T14:05", "path": "/iserv/forum/1000", "extra": []}


class ForumConnection:
    def __init__(self, connection_id, forums=None, failure=None, texts=None, screens=None, complete=True):
        self.id = connection_id
        self.listed = forums or []
        self.complete = complete
        self.failure = failure
        self.listed_texts = texts or []
        self.listed_screens = screens or []

    def forums(self):
        if self.failure is not None:
            raise self.failure
        return {"forums": [dict(forum) for forum in self.listed], "carry": [], "mark_read": True, "complete": self.complete}

    def texts(self):
        if self.failure is not None:
            raise self.failure
        return {"texts": list(self.listed_texts), "carry": [], "filters": [{"value": "all", "label": "Alle", "default": True}]}

    def infodisplay(self):
        if self.failure is not None:
            raise self.failure
        return {"infodisplay": list(self.listed_screens), "carry": []}


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    pushes = []
    poller = Poller(None, store=store, notifiers={"forums": lambda name, message: pushes.append(message) or True})
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id, pushes


class HolidaysStub:
    def range_info(self, first, last, config):
        return {"status": "ok", "days": {}}


def forum_posts(store, connection_id):
    return integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)["unread_forum_posts"]


def poll(poller, connection_id, state, forums=None, failure=None, offered=True):
    return account_poll.poll_forums(poller, ForumConnection(connection_id, forums, failure), connection_id, offered, state, "en")


def test_the_first_poll_learns_the_counts_and_pushes_nothing(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    event = poll(poller, connection_id, state, [FORUM, dict(FORUM, id="2000", unread=0)])
    assert event == {"module": "forums", "forums": 2, "unread": 2, "initialized": True}
    assert pushes == []
    assert state["forum_unread"]["1000"]["unread"] == 2
    posts = forum_posts(store, connection_id)
    assert posts["count"] == 2
    assert [item["title"] for item in posts["items"]] == ["Schulhof"]
    assert posts["items"][0]["sender"] == "Allgemein"
    assert posts["items"][0]["date"] == "2026-10-03"
    assert posts["fresh"] == []


def test_more_unread_posts_push_once_and_reach_home_assistant_as_fresh(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [FORUM])
    event = poll(poller, connection_id, state, [dict(FORUM, unread=5, last_post="Neu 04.10.2026 09:00")])
    assert event == {"module": "forums", "forums": 1, "unread": 5, "new": 3}
    assert pushes == ["3 new forum posts: open the app to read them"]
    assert [item["title"] for item in forum_posts(store, connection_id)["fresh"]] == ["Schulhof"]
    assert poll(poller, connection_id, state, [dict(FORUM, unread=5, last_post="Neu 04.10.2026 09:00")])["new"] == 0
    assert len(pushes) == 1


def test_reading_some_posts_is_not_new_but_a_new_last_post_is(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [dict(FORUM, unread=5)])
    assert poll(poller, connection_id, state, [dict(FORUM, unread=2)])["new"] == 0
    assert poll(poller, connection_id, state, [dict(FORUM, unread=0, last_post="Anders")])["new"] == 0
    assert poll(poller, connection_id, state, [dict(FORUM, unread=1, last_post="Noch anders")])["new"] == 1
    assert pushes == ["New forum post: open the app to read it"]


def test_unknown_counts_are_no_zero_for_home_assistant(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [dict(FORUM, unread=None)])
    assert forum_posts(store, connection_id) is None
    assert poll(poller, connection_id, state, [dict(FORUM, unread=None)])["new"] == 0
    assert pushes == []


def test_an_unreadable_overview_keeps_the_last_list(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [FORUM])
    assert poll(poller, connection_id, state, failure=DataError("no table")) == {"module": "forums", "state": "unreadable"}
    assert store.load_calendar_snapshot()["forums"][connection_id]["forums"][0]["id"] == "1000"
    assert forum_posts(store, connection_id)["count"] == 2


def test_a_refused_or_switched_off_forum_module_is_dropped(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [FORUM])
    assert poll(poller, connection_id, state, failure=ModulePageRefusedError("403")) == {"module": "forums", "state": "refused"}
    assert connection_id not in store.load_calendar_snapshot()["forums"]
    assert forum_posts(store, connection_id) is None
    assert "forum_unread" not in state
    poll(poller, connection_id, state, [FORUM])
    assert poll(poller, connection_id, state, offered=False) is None
    assert connection_id not in store.load_calendar_snapshot()["forums"]


def test_an_outage_reaches_the_poll(tmp_path):
    poller, _store, connection_id, _pushes = poller_for(tmp_path)
    with pytest.raises(OutageError):
        poll(poller, connection_id, {}, failure=OutageError("timeout"))


def text_poller(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    pushes = []
    poller = Poller(None, store=store, notifiers={"texts": lambda name, message: pushes.append(message) or True})
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id, pushes


TEXT_SPEC = next(spec for spec in __import__("app.poller", fromlist=["SCHOOL_LISTS"]).SCHOOL_LISTS if spec[0] == modules.TEXTS)
TEXT = {"id": "a", "title": "Protokoll", "owner": "Kim Muster", "changed": "2026-10-07T22:47", "created": "2026-09-01T08:00", "filters": ["all"]}


def poll_texts(poller, connection_id, state, texts=None, failure=None, offered=True):
    return poller._poll_school_list(ForumConnection(connection_id, texts=texts, failure=failure), connection_id, offered, TEXT_SPEC, state, "en")


def test_new_texts_are_pushed_once_and_reach_home_assistant_with_owner_and_change(tmp_path):
    poller, store, connection_id, pushes = text_poller(tmp_path)
    state = {}
    assert poll_texts(poller, connection_id, state, [TEXT]) == {"module": "texts", "items": 1, "initialized": 1}
    assert pushes == []
    shared = dict(TEXT, id="b", title="Ideen", owner="Förderverein")
    assert poll_texts(poller, connection_id, state, [TEXT, shared]) == {"module": "texts", "items": 2, "new": 1}
    assert pushes == ["New text: open the app to see it"]
    assert poll_texts(poller, connection_id, state, [TEXT, shared]) == {"module": "texts", "items": 2, "new": 0}
    assert len(pushes) == 1
    listed = integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)["texts"]
    assert listed["count"] == 2
    assert listed["items"][1] == {"title": "Ideen", "sender": "Förderverein", "date": "2026-10-07", "child": "", "id": "b"}
    assert [item["title"] for item in listed["fresh"]] == ["Ideen"]
    stored = store.load_calendar_snapshot()["texts"][connection_id]
    assert stored["filters"] == [{"value": "all", "label": "Alle", "default": True}]
    assert state["text_ids"] == {"a": 1_791_000_000, "b": 1_791_000_000}


def test_a_refused_or_switched_off_text_list_is_dropped_for_the_app_and_home_assistant(tmp_path):
    poller, store, connection_id, _pushes = text_poller(tmp_path)
    state = {}
    poll_texts(poller, connection_id, state, [TEXT])
    assert poll_texts(poller, connection_id, state, failure=ModulePageRefusedError("403")) == {"module": "texts", "state": "refused"}
    assert connection_id not in store.load_calendar_snapshot()["texts"]
    assert integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)["texts"] is None
    poll_texts(poller, connection_id, state, [TEXT])
    assert poll_texts(poller, connection_id, state, offered=False) is None
    assert connection_id not in store.load_calendar_snapshot()["texts"]


def test_screens_are_stored_per_school_without_push(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    connection = ForumConnection(connection_id, screens=[{"id": "9", "title": "Foyer"}])
    flags = {modules.FORUMS: False, modules.TEXTS: True, modules.INFODISPLAY: True}
    events = account_poll.poll_account_lists(poller, connection, connection_id, flags, {}, "en")
    assert events == [{"module": "infodisplay", "items": 1}]
    assert store.load_calendar_snapshot()["infodisplay"][connection_id]["infodisplay"] == [{"id": "9", "title": "Foyer"}]
    assert pushes == []
    flags = {modules.FORUMS: False, modules.TEXTS: False, modules.INFODISPLAY: False}
    account_poll.poll_account_lists(poller, connection, connection_id, flags, {}, "en")
    assert connection_id not in store.load_calendar_snapshot()["infodisplay"]


def test_the_app_lists_carry_the_school_and_the_iserv_filters(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    connection = ForumConnection(connection_id, [FORUM], texts=[{"id": "a", "title": "Eins", "filters": ["all"]}])
    flags = {modules.FORUMS: True, modules.TEXTS: True, modules.INFODISPLAY: False}
    account_poll.poll_account_lists(poller, connection, connection_id, flags, {}, "en")
    poller._poll_school_list(connection, connection_id, True, TEXT_SPEC, {}, "en")
    service = IServService(store)
    service.connections()[0].store.save_modules({"modules": {modules.FORUMS: True, modules.TEXTS: True}})
    forums = service.forums()
    assert forums["forums"][0]["connection_id"] == connection_id
    assert forums["schools"][0]["last_success"] == 1_791_000_000
    texts = service.texts()
    assert texts["texts"][0]["title"] == "Eins"
    assert texts["schools"][0]["filters"] == [{"value": "all", "label": "Alle", "default": True}]
    assert service.infodisplay()["infodisplay"] == []


def test_the_forum_overview_and_the_text_and_screen_pages_are_supported_segments_not_unknown_ones():
    page = '<a href="/iserv/forums">Foren</a><a href="/iserv/forum/123">Forum</a><a href="/iserv/etherpad">Texte</a><a href="/iserv/infodisplay/index">Infobildschirm</a>'
    assert modules.split_links(modules.harvest_links(page)) == ([], [])


def test_the_three_modules_are_confirmed_by_their_own_pages_and_stay_off_otherwise():
    paths = {modules.FORUMS: "/iserv/forums", modules.TEXTS: "/iserv/etherpad", modules.INFODISPLAY: "/iserv/infodisplay/index"}
    for module, path in paths.items():
        assert modules.PROBES[module] == (path, None)
        assert module in modules.CONFIRMED_ONLY
        assert modules.default_registry()["modules"][module] is False

    def served(path, params=None):
        return Answer(200, BASE + path, "<html></html>")

    def sent_home(path, params=None):
        return Answer(200, BASE + "/iserv/", "<html></html>")

    def refused(path, params=None):
        return Answer(403, BASE + path, "")

    for fetch, wanted in ((served, True), (sent_home, False), (refused, False)):
        registry = modules.detect("<html></html>", fetch, None, clock=lambda: 1_791_000_000)
        assert [registry["modules"][name] for name in paths] == [wanted] * 3


def test_the_read_route_passes_only_an_explicit_confirmation(tmp_path, monkeypatch):
    from tests.test_server import FakeService, client

    calls = []

    def mark(self, connection_id, confirmed=False):
        calls.append((connection_id, confirmed))
        return {"ok": confirmed, "message_key": "api.forums.read.done" if confirmed else "api.forums.read.unconfirmed"}

    monkeypatch.setattr(FakeService, "forum_mark_read", mark, raising=False)
    monkeypatch.setattr(FakeService, "forums", lambda self: {"forums": [], "schools": [], "unavailable": []}, raising=False)
    api, _store = client(tmp_path)
    assert api.post("/api/forums/read", json={"connection_id": "c1", "confirmed": "yes"}).json()["ok"] is False
    assert api.post("/api/forums/read", json={"connection_id": "c1", "confirmed": True}).json()["ok"] is True
    assert calls == [("c1", False), ("c1", True)]
    assert api.get("/api/forums").json() == {"forums": [], "schools": [], "unavailable": []}


def test_a_relative_date_turning_over_or_an_own_post_pushes_nothing(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [dict(FORUM, unread=2, last_post="Pausen · heute 09:40")])
    assert poll(poller, connection_id, state, [dict(FORUM, unread=2, last_post="Pausen · gestern 09:40")])["new"] == 0
    assert poll(poller, connection_id, state, [dict(FORUM, unread=2, last_post="Eigener Beitrag · heute 10:00")])["new"] == 0
    assert pushes == []


def test_a_first_poll_without_counts_does_not_push_the_backlog_later(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [dict(FORUM, unread=None)])
    assert poll(poller, connection_id, state, [dict(FORUM, unread=40)])["new"] == 0
    assert pushes == []
    assert poll(poller, connection_id, state, [dict(FORUM, unread=41)])["new"] == 1


def test_a_forum_seen_for_the_first_time_sets_its_baseline_quietly(tmp_path):
    poller, _store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [FORUM])
    assert poll(poller, connection_id, state, [FORUM, dict(FORUM, id="2000", title="Neu", unread=5)])["new"] == 0
    assert pushes == []


def test_an_unreadable_count_keeps_the_earlier_baseline(tmp_path):
    poller, _store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    poll(poller, connection_id, state, [dict(FORUM, unread=2)])
    poll(poller, connection_id, state, [dict(FORUM, unread=None)])
    assert poll(poller, connection_id, state, [dict(FORUM, unread=3)])["new"] == 1


def test_partly_unknown_counts_are_no_definite_sum_for_home_assistant(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    poll(poller, connection_id, {}, [FORUM, dict(FORUM, id="2000", unread=None)])
    assert forum_posts(store, connection_id) is None


def test_skipped_forum_rows_are_no_definite_sum_for_home_assistant(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    connection = ForumConnection(connection_id, [FORUM], complete=False)
    account_poll.poll_forums(poller, connection, connection_id, True, {}, "en")
    assert forum_posts(store, connection_id) is None


class LoginFailingSchool(School):
    def __init__(self, pages):
        super().__init__(pages)
        self.reads = 0

    def fetch(self, path, params=None):
        self.reads += 1
        if self.reads > 1:
            from app.iserv.errors import LoginError

            raise LoginError("session gone")
        return super().fetch(path, params)


def test_a_sign_in_failure_while_reading_again_leaves_the_outcome_open(store_and_id):
    store, connection_id = store_and_id
    school = LoginFailingSchool([overview((3, 0))])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["outcome"] == "uncertain"
    assert len(school.posted) == 1


def test_an_overview_without_any_forum_after_sending_is_no_proof(store_and_id):
    store, connection_id = store_and_id
    school = School([overview((3, 0)), overview(())])
    result = service_for(store, connection_id, school).mark_all_read(confirmed=True)
    assert result["outcome"] == "uncertain"


def test_the_app_learns_whether_iserv_offers_marking_read(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    poll(poller, connection_id, {}, [FORUM])
    service = IServService(store)
    service.connections()[0].store.save_modules({"modules": {modules.FORUMS: True}})
    assert service.forums()["schools"][0]["mark_read"] is True


def test_marking_read_is_refused_for_a_school_without_the_forum_module(tmp_path, monkeypatch):
    from app.service import ConnectionService

    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    called = []
    monkeypatch.setattr(ConnectionService, "forum_mark_read", lambda self, confirmed=False: called.append(confirmed) or {"ok": True})
    service = IServService(store)
    service.connections()[0].store.save_modules({"modules": {modules.FORUMS: False}})
    result = service.forum_mark_read(connection_id, confirmed=True)
    assert result["ok"] is False
    assert result["message_key"] == "api.forums.read.unavailable"
    assert called == []
    service.connections()[0].store.save_modules({"modules": {modules.FORUMS: True}})
    assert service.forum_mark_read(connection_id, confirmed=True) == {"ok": True}


def test_an_unreadable_forum_page_is_named_apart_from_an_unreachable_school(tmp_path, monkeypatch):
    from app.iserv.errors import OutageError as Outage
    from app.service import ConnectionService

    store = Store(tmp_path / "data")
    add_school(store, BASE)
    service = IServService(store)
    connection_id = service.connections()[0].id
    service.connections()[0].store.save_modules({"modules": {modules.FORUMS: True, modules.TASKS: True}})
    monkeypatch.setattr(ConnectionService, "forums", lambda self: (_ for _ in ()).throw(DataError("no forum table")))
    listed = service.forums()
    assert listed["forums"] == []
    assert listed["unavailable"] == [connection_id]
    assert listed["unreadable"] == [connection_id]
    monkeypatch.setattr(ConnectionService, "forums", lambda self: (_ for _ in ()).throw(Outage("timeout")))
    listed = service.forums()
    assert listed["unavailable"] == [connection_id]
    assert listed["unreadable"] == []


def test_an_unreadable_first_poll_leaves_home_assistant_unknown_and_no_baseline(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    state = {}
    assert poll(poller, connection_id, state, failure=DataError("no forum table")) == {"module": "forums", "state": "unreadable"}
    assert forum_posts(store, connection_id) is None
    assert "forum_unread" not in state
    poll(poller, connection_id, state, [dict(FORUM, unread=4)])
    poll(poller, connection_id, state, failure=DataError("no forum table"))
    assert state["forum_unread"] == {"1000": {"unread": 4}}
    assert forum_posts(store, connection_id)["count"] == 4
    assert pushes == []
