import logging
from pathlib import Path

import pytest

from app import modules
from app.iserv.children import CHILD_PAGE_FORBIDDEN_KEY
from app.iserv.errors import DataError
from app.iserv.models import Child
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import SCHOOL_ONE, SCHOOL_TWO, add_school
from tests.test_service_modules import ProbeClient, Response

FIXTURES = Path(__file__).parent / "fixtures"
LETTERS_WITH_CHILD_COLUMN = (FIXTURES / "letters_index.html").read_text(encoding="utf-8")
NOW_EPOCH = 1_790_000_000
START_PAGE = """
<html><body>
<a href="/iserv/time-table/">Stundenplan</a>
<a href="/iserv/parentletter/">Elternbriefe</a>
<a href="/iserv/parentconference/">Elternsprechtage</a>
<a href="/iserv/dsa-absences/absence-parents">Abwesenheiten</a>
<a href="/iserv/messenger">Messenger</a>
<footer>IServ 3.9.1</footer>
</body></html>
"""
REPORT_START_PAGE = """
<html><body>
<a href="/iserv/dsa-absences/absence-parents">Abwesenheiten</a>
<a href="/iserv/parentletter/">Elternbriefe</a>
<a href="/iserv/parentconference/">Elternsprechtage</a>
<a href="/iserv/klassengeld/redirect">Klassengeld</a>
<a href="/iserv/messenger">Messenger</a>
</body></html>
"""
ACCOUNT_WITHOUT_CHILDREN = {"id": "parent-2", "displayname": "Parent Two", "roles": ["guardian"]}
REPORT_USERS_ME = {"id": "9f3c2a10", "displayname": "Elternteil Zwei", "username": None, "roles": ["guardian"]}
REPORT_CURRENT_TIMETABLE = {"vacations": [], "schoolEvents": [], "students": []}
DSA_PREFIX = "/iserv/dieschulapp/api/1.0/"
REPORT_DSA_ANSWERS = {
    "users/me": REPORT_USERS_ME,
    "sickNotes/userSelection/": [],
    "current-timetable/": REPORT_CURRENT_TIMETABLE,
    "pinboards/": [],
    "students/": [],
    "school-settings/": [],
    "schools/": [],
}
REFUSED_PAGES = ("/iserv/time-table/", "/iserv/timetable/", "/iserv/timetable/data", "/iserv/dsa-timetable/")


class ReportSession:
    def __init__(self, base_url):
        self.base_url = base_url
        self.asked = []

    def get(self, url, params=None, timeout=None):
        path = url.split(DSA_PREFIX, 1)[1] if DSA_PREFIX in url else url
        self.asked.append(path)
        if path in REPORT_DSA_ANSWERS:
            return Response(200, url, json_data=REPORT_DSA_ANSWERS[path])
        return Response(404, url)


class ReportClient(ProbeClient):
    def __init__(self, url, refused):
        super().__init__(url, start_page=REPORT_START_PAGE if refused else START_PAGE)
        self.refused = refused
        if refused:
            self.session = ReportSession(self.base_url)

    def fetch(self, path, params=None):
        if path.startswith("/iserv/parentletter/parent/"):
            self.calls.append(path)
            return Response(200, self.base_url + path, LETTERS_WITH_CHILD_COLUMN)
        if self.refused and path in REFUSED_PAGES:
            self.calls.append(path)
            return Response(403, self.base_url + path, "<html><body>Zugriff verweigert</body></html>")
        if self.refused and path.startswith(DSA_PREFIX):
            self.calls.append(path)
            return self.session.get(self.base_url + path, params)
        return super().fetch(path, params)

    def fetch_or_raise(self, path, params=None):
        return self.fetch(path, params)

    def get_children(self):
        from app.iserv.children import child_page_message_key

        page = self.fetch("/iserv/time-table/")
        if page.status_code != 200:
            raise DataError(
                "child list page was not readable",
                message_key=child_page_message_key(page.status_code),
                detail={"status": page.status_code},
            )
        return [Child("uuid-1", "Mia Muster")]


class ReportSchoolApp:
    def __init__(self, children):
        self.children = children

    def me_with_children(self):
        return dict(ACCOUNT_WITHOUT_CHILDREN)

    def sick_note_children(self):
        return list(self.children)

    def sick_note_children_or_raise(self):
        return list(self.children)

    def students(self):
        return list(self.children)

    def school_settings(self):
        return {}


def recorder(calls, name, answer):
    def call(*args, **kwargs):
        calls.append(name)
        return answer

    return call


def report_schools(tmp_path):
    store = Store(tmp_path / "data")
    first = add_school(store, SCHOOL_ONE)
    second = add_school(store, SCHOOL_TWO)
    clients = {}

    def factory(url):
        clients[url] = ReportClient(url, refused=url == SCHOOL_TWO)
        return clients[url]

    service = IServService(store, client_factory=factory)
    calls = {first: [], second: []}
    first_connection = service.connection(first)
    first_connection._dsa = lambda: ReportSchoolApp([{"id": 7, "name": "Mia Muster", "class_name": "3b"}])
    for connection_id in (first, second):
        connection = service.connection(connection_id)
        own = calls[connection_id]
        connection.pinboard = recorder(own, "pinboard", {"folders": [], "feed": []})
        connection.conferences = recorder(own, "conferences", {"items": [], "empty": True})
        connection.messenger_unread_pulse = recorder(own, "messenger", 2)
        connection.absences_overview = recorder(own, "absences", {"children": [], "entries": []})
        connection.timetable = recorder(own, "timetable", {"lessons": [], "changes": [], "start_date": "2026-09-21"})
    return store, service, first, second, calls, clients


def warnings_of(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


def test_a_school_whose_account_lists_no_children_keeps_polling_its_other_modules(tmp_path, caplog):
    store, service, first, second, calls, clients = report_schools(tmp_path)
    with caplog.at_level(logging.INFO):
        events = Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    messages_seen = [record.getMessage() for record in caplog.records]
    assert not [line for line in messages_seen if "stopped" in line], messages_seen
    assert {"pinboard", "conferences", "messenger"} <= set(calls[second])
    assert "/iserv/parentletter/parent/index" in clients[SCHOOL_TWO].calls
    assert "/iserv/time-table/" in clients[SCHOOL_TWO].calls
    assert not [event for event in events if event.get("connection_id") == second and event.get("error")]
    poll_end = [line for line in messages_seen if line.startswith("poll end")]
    assert poll_end and ", 0 errors" in poll_end[-1], poll_end


def test_the_refused_child_list_is_a_visible_state_of_that_school_and_not_an_error(tmp_path):
    store, service, first, second, _, _ = report_schools(tmp_path)
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    states = {row["id"]: row["children_state"] for row in service.summaries()}
    assert states == {first: "listed", second: "refused"}
    overall, rows = service.health_overview(clock=lambda: NOW_EPOCH)
    assert {row["id"]: row["status"] for row in rows} == {first: "ok", second: "ok"}


def test_the_school_with_children_still_lists_them_next_to_the_refusing_one(tmp_path):
    _, service, first, second, _, _ = report_schools(tmp_path)
    listed = service.children()
    assert [(child["connection_id"], child["name"]) for child in listed] == [(first, "Mia Muster")]
    with pytest.raises(DataError) as caught:
        service.children(second)
    assert caught.value.message_key == CHILD_PAGE_FORBIDDEN_KEY


def test_letters_of_the_school_without_listed_children_carry_their_child_column_and_school(tmp_path):
    _, service, first, second, _, _ = report_schools(tmp_path)
    letters = service.letters()["letters"]
    from_second = [letter for letter in letters if letter["connection_id"] == second]
    assert from_second and all(letter.get("child") for letter in from_second)
    assert all(letter["key"].startswith(f"{second}:") for letter in from_second)


def test_an_unreadable_child_list_counts_as_an_error_but_does_not_stop_the_school(tmp_path, caplog):
    store, service, first, second, calls, clients = report_schools(tmp_path)
    connection = service.connection(second)

    def broken():
        raise DataError("child list unreadable", message_key="api.children.unreadable")

    connection.children = broken
    with caplog.at_level(logging.INFO):
        events = Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert not [record for record in caplog.records if "stopped" in record.getMessage()]
    assert {"pinboard", "conferences", "messenger"} <= set(calls[second])
    assert [event.get("module") for event in events if event.get("error")] == ["children"]


SCHOOL_TWO_SYNC = {
    "rooms": {
        "join": {
            "!class5a:school-two.example": {
                "state": {"events": [{"type": "m.room.name", "state_key": "", "content": {"name": "Klasse 5a"}}]},
                "timeline": {
                    "events": [
                        {
                            "type": "m.room.message",
                            "sender": "@teacher:school-two.example",
                            "origin_server_ts": 3000,
                            "content": {"msgtype": "m.text", "body": "Bis Montag."},
                        }
                    ]
                },
                "unread_notifications": {"notification_count": 1},
            }
        }
    }
}
POSTED_CREDENTIALS = {
    "messenger_authentication": {
        "access_token": "tok-two",
        "device_id": "dev-two",
        "home_server": "school-two.example",
        "user_id": "@parent:school-two.example",
        "iserv_token": "it-two",
        "iserv_cryptkey": "ck-two",
    }
}
TEACHER_HITS = [{"value": "userid:22222222-3333-4444-5555-666666666666", "label": "Fr. Zweig"}]


def messenger_school(page, sync_body, posted=None):
    from tests.test_messenger_matrix import SYNC_BODY
    from tests.test_messenger_service import (
        TEACHER_FORM_HTML,
        DictStore,
        FakeIServ,
        FakeIServClient,
        FakeMatrixResponse,
        FakePage,
        make_factory,
    )
    from app.messenger import MessengerService

    base = SCHOOL_TWO if sync_body is not None else SCHOOL_ONE
    form = FakePage(200, TEACHER_FORM_HTML, url=base + "/iserv/messenger/form/room/teacher_new")
    search = FakePage(200, "", json_data=TEACHER_HITS)
    client = FakeIServClient(
        base_url=base,
        page=FakePage(200, page),
        pages={"/iserv/messenger/form/room/teacher_new": form, "/iserv/messenger/autocomplete/teacher": search},
        posted=posted,
    )
    plan = {"sync": FakeMatrixResponse(json_data=sync_body if sync_body is not None else SYNC_BODY)}
    service = MessengerService(FakeIServ(DictStore(), client), matrix_client_factory=make_factory(plan))
    service.sleeper = lambda seconds: None
    return service, client


def messenger_schools(tmp_path, second_page, posted=None):
    from tests.test_messenger_service import BOOTSTRAP_HTML

    store, service, first, second, _, _ = report_schools(tmp_path)
    one, one_client = messenger_school(BOOTSTRAP_HTML, None)
    two, two_client = messenger_school(second_page, SCHOOL_TWO_SYNC, posted)
    service.connection(first)._messenger_service = one
    service.connection(second)._messenger_service = two
    return service, first, second, one_client, two_client


def credential_pages():
    from tests.test_messenger_service import BOOTSTRAP_HTML, WITHHELD_HTML, FakePage

    posted = FakePage(200, "", json_data=POSTED_CREDENTIALS, headers={"content-type": "application/json"})
    withheld = WITHHELD_HTML.replace(
        '"messenger_authentication":null}',
        '"messenger_authentication":null,"messenger_routing":{"messenger_authenticate":"/iserv/messenger/authenticate"}}',
    )
    return {"embedded": (BOOTSTRAP_HTML, None), "withheld": (withheld, posted)}


@pytest.mark.parametrize("variant", ["embedded", "withheld"])
def test_the_chat_list_carries_the_rooms_of_the_second_school_in_both_credential_variants(tmp_path, variant):
    page, posted = credential_pages()[variant]
    service, first, second, _, two_client = messenger_schools(tmp_path, page, posted)
    payload = service.messenger_rooms()
    from_second = [room for room in payload["rooms"] if room["connection_id"] == second]
    assert [room["name"] for room in from_second] == ["Klasse 5a"]
    assert payload["unavailable"] == []
    assert payload["teacher_schools"] == [first, second]
    if variant == "withheld":
        assert [url for url, _ in two_client.posts] == [SCHOOL_TWO + "/iserv/messenger/authenticate"]


def test_the_teacher_search_of_the_second_school_asks_the_second_school(tmp_path):
    from tests.test_messenger_service import BOOTSTRAP_HTML

    service, first, second, one_client, two_client = messenger_schools(tmp_path, BOOTSTRAP_HTML)
    found = service.messenger_teacher_search(second, "Zwe")
    assert [hit["label"] for hit in found["teachers"]] == ["Fr. Zweig"]
    assert any("autocomplete" in path for path in two_client.fetched_paths)
    assert not any("autocomplete" in path for path in one_client.fetched_paths)


def test_the_teacher_room_of_the_school_without_listed_children_offers_its_form_children(tmp_path):
    from tests.test_messenger_service import BOOTSTRAP_HTML, CHILD_ONE, FakePage

    service, first, second, one_client, two_client = messenger_schools(tmp_path, BOOTSTRAP_HTML)
    with pytest.raises(DataError):
        service.children(second)
    offered = service.messenger_teacher_room_children(second)
    assert [child["name"] for child in offered["children"]] == ["Mia Muster", "Tom Muster"]
    two_client.posted = FakePage(200, "", json_data={"room_id": "!new:school-two.example"}, headers={"content-type": "application/json"})
    result = service.messenger_create_teacher_room(second, "userid:2222", [CHILD_ONE], False)
    assert result["ok"] is True
    assert [url for url, _ in two_client.posts] == [SCHOOL_TWO + "/iserv/messenger/form/room/teacher_new"]
    assert one_client.posts == []


def test_without_a_school_the_teacher_search_asks_for_one_instead_of_the_first_school(tmp_path):
    from tests.test_messenger_service import BOOTSTRAP_HTML

    service, first, second, one_client, two_client = messenger_schools(tmp_path, BOOTSTRAP_HTML)
    with pytest.raises(DataError) as caught:
        service.messenger_teacher_search(None, "Zwe")
    assert caught.value.message_key == "api.school.required"
    assert one_client.fetched_paths == [] and two_client.fetched_paths == []


def test_asking_for_the_children_again_does_not_warn_about_the_refusing_school(tmp_path, caplog):
    _, service, first, second, _, _ = report_schools(tmp_path)
    with caplog.at_level(logging.INFO):
        service.children()
        service.children()
    assert warnings_of(caplog) == []
    assert [record.getMessage() for record in caplog.records if "refused for this account" in record.getMessage()] == [
        f"child list of school#{second} refused for this account"
    ] * 2


def test_the_child_list_state_survives_a_restart_before_the_next_poll(tmp_path):
    store, service, first, second, _, _ = report_schools(tmp_path)
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    restarted = IServService(store, client_factory=lambda url: pytest.fail("no school is asked after a restart"))
    states = {row["id"]: row["children_state"] for row in restarted.summaries()}
    assert states == {first: "listed", second: "refused"}


class SessionLostClient(ReportClient):
    def get_children(self):
        from app.iserv.children import child_page_message_key

        self.calls.append("/iserv/time-table/")
        raise DataError("child list page was not readable", message_key=child_page_message_key(401), detail={"status": 401})


def test_a_lost_session_on_the_child_page_is_not_a_refused_child_list(tmp_path, caplog):
    from app.iserv.children import CHILD_PAGE_SESSION_KEY

    store = Store(tmp_path / "data")
    second = add_school(store, SCHOOL_TWO)
    service = IServService(store, client_factory=lambda url: SessionLostClient(url, refused=False))
    connection = service.connection(second)
    asked = []

    class CountingSchoolApp(ReportSchoolApp):
        def sick_note_children(self):
            asked.append("sick notes")
            return [{"id": 7, "name": "Mia Muster"}]

    connection._dsa = lambda: CountingSchoolApp([])
    forgotten = []
    connection._forget_session = lambda client: forgotten.append(client)
    with pytest.raises(DataError) as caught:
        service.children(second)
    assert caught.value.message_key == CHILD_PAGE_SESSION_KEY
    assert len(forgotten) == 1
    assert asked == []
    assert connection.child_list_state() == "unreadable"
    children, event = Poller(service, store=store)._children_for_poll(connection, second)
    assert event["module"] == "children" and event.get("error")


def test_the_report_facts_of_the_second_school_are_read_through_the_real_paths(tmp_path):
    store, service, first, second, _, clients = report_schools(tmp_path)
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    client = clients[SCHOOL_TWO]
    assert "/iserv/time-table/" not in REPORT_START_PAGE
    assert modules.DSA_TIMETABLE_PATH in client.calls
    registry = service.connection(second).stored_modules()
    assert registry["probes"][modules.TIMETABLE]["path"] == modules.DSA_TIMETABLE_PATH
    assert registry["modules"][modules.TIMETABLE] is True
    assert {"users/me", "sickNotes/userSelection/"} <= set(client.session.asked)
    assert "/iserv/time-table/" in client.calls
    assert service.connection(second).child_list_state() == "refused"


def test_a_new_message_at_the_second_school_pushes_once_and_its_old_letters_do_not(tmp_path):
    store, service, first, second, calls, _ = report_schools(tmp_path)
    pushed = []
    notifiers = {
        name: (lambda name_=name: lambda child, message: pushed.append((name_, message)) or True)()
        for name in ("letters", "messenger", "pinboard", "conferences")
    }
    counts = {first: 2, second: 1}
    for connection_id in (first, second):
        service.connection(connection_id).messenger_unread_pulse = lambda connection_id=connection_id: counts[connection_id]
    poller = Poller(service, store=store, notifiers=notifiers, clock=lambda: NOW_EPOCH)
    poller.poll_once()
    assert pushed == []
    counts[second] = 2
    poller.poll_once()
    assert [name for name, _ in pushed] == ["messenger"]
    assert service.connection(second).display_name() in pushed[0][1]
    poller.poll_once()
    assert [name for name, _ in pushed] == ["messenger"]
