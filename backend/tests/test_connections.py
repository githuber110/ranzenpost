import logging

import pytest
import requests

from app import integration, modules
from app.iserv.errors import DataError, LoginError
from app.iserv.models import Child, Lesson, TimetableWeek
from app.poller import Poller
from app.service import IServService, NotConfiguredError
from app.store import Store
from tests.support import DEFAULT_SECRETS, add_school, connection_service

SCHOOL_ONE = "https://school-one.example"
SCHOOL_TWO = "https://school-two.example"


class FakeClient:
    def __init__(self, url, children=(), letters=(), fail=None):
        self.url = url
        self.authed = False
        self._children = list(children)
        self.fail = fail
        self.fetched = []

    def login(self, username, password, code_provider):
        if self.fail is not None:
            raise self.fail
        code_provider()
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        return [Child(child_id, name) for child_id, name in self._children]

    def get_timetable(self, child_id, reference=None):
        lessons = [Lesson("31.08.2026", 1, 1, "D", "BEH", "R1", "1a")]
        return TimetableWeek("31.08.2026", "06.09.2026", "22.07.2026 12:25", lessons, lessons, [])

    def fetch_or_raise(self, path, params=None):
        raise DataError("no such page")


def two_schools(tmp_path, factories=None):
    store = Store(tmp_path / "data")
    one = add_school(store, SCHOOL_ONE, connection_id="a1b2c3d4", school_name="School One")
    two = add_school(store, SCHOOL_TWO, connection_id="b2c3d4e5", school_name="School Two")
    clients = {}

    def factory(url):
        maker = (factories or {}).get(url)
        client = maker(url) if maker else FakeClient(url, children=[("c1", "Alice Example")])
        clients[url] = client
        return client

    return IServService(store, client_factory=factory), store, one, two, clients


def test_children_of_every_school_carry_key_connection_and_school_name_ordered_by_name_not_school(tmp_path):
    service, store, one, two, _ = two_schools(
        tmp_path,
        {
            SCHOOL_ONE: lambda url: FakeClient(url, children=[("c2", "Bob Example"), ("c1", "alice Example")]),
            SCHOOL_TWO: lambda url: FakeClient(url, children=[("c1", "Alice Other"), ("c3", "Ada Other")]),
        },
    )
    listed = service.children()
    assert [child["key"] for child in listed] == [f"{two}:c3", f"{one}:c1", f"{two}:c1", f"{one}:c2"]
    assert [child["connection_id"] for child in listed] == [two, one, two, one]
    assert [child["school"] for child in listed] == ["School Two", "School One", "School Two", "School One"]
    assert [child["child_id"] for child in listed] == ["c3", "c1", "c1", "c2"]
    assert [child["child_id"] for child in store.connection(one)["children"]] == ["c2", "c1"]
    assert [child["child_id"] for child in store.connection(two)["children"]] == ["c1", "c3"]


def test_children_of_one_school_keep_the_name_order_too(tmp_path):
    service, store, one, two, _ = two_schools(
        tmp_path,
        {SCHOOL_ONE: lambda url: FakeClient(url, children=[("c1", "Musterkind, Tom"), ("c2", "Lena Musterkind")])},
    )
    listed = [child for child in service.children() if child["connection_id"] == one]
    assert [child["child_id"] for child in listed] == ["c2", "c1"]


def test_a_failing_school_falls_back_to_its_stored_children_while_the_other_answers(tmp_path, caplog):
    service, store, one, two, _ = two_schools(
        tmp_path, {SCHOOL_TWO: lambda url: FakeClient(url, fail=LoginError("password changed"))}
    )
    store.update_connection(two, children=[{"child_id": "c9", "name": "Stored Child"}])
    with caplog.at_level(logging.WARNING, logger="app.service"):
        listed = service.children()
    assert [child["key"] for child in listed] == [f"{one}:c1", f"{two}:c9"]
    assert listed[1]["unavailable"] is True
    assert any(f"school#{two}" in record.getMessage() for record in caplog.records)
    assert not any(SCHOOL_TWO in record.getMessage() for record in caplog.records)


def test_when_every_school_fails_the_first_error_is_raised(tmp_path):
    service, _, _, _, _ = two_schools(
        tmp_path,
        {
            SCHOOL_ONE: lambda url: FakeClient(url, fail=LoginError("one")),
            SCHOOL_TWO: lambda url: FakeClient(url, fail=requests.ConnectionError("two")),
        },
    )
    with pytest.raises(LoginError):
        service.children()


def test_the_overall_connection_state_is_ok_when_any_school_answers(tmp_path):
    service, _, _, _, _ = two_schools(
        tmp_path, {SCHOOL_TWO: lambda url: FakeClient(url, fail=LoginError("password changed"))}
    )
    assert service.check_connection() == "ok"
    summaries = service.summaries(with_status=True)
    assert [row["status"] for row in summaries] == ["ok", "auth_failed"]
    assert [row["name"] for row in summaries] == ["School One", "School Two"]


def test_the_overall_state_is_auth_failed_only_when_every_school_fails_that_way(tmp_path):
    service, _, _, _, _ = two_schools(
        tmp_path,
        {
            SCHOOL_ONE: lambda url: FakeClient(url, fail=LoginError("one")),
            SCHOOL_TWO: lambda url: FakeClient(url, fail=LoginError("two")),
        },
    )
    assert service.check_connection() == "auth_failed"
    mixed, _, _, _, _ = two_schools(
        tmp_path / "mixed",
        {
            SCHOOL_ONE: lambda url: FakeClient(url, fail=LoginError("one")),
            SCHOOL_TWO: lambda url: FakeClient(url, fail=requests.ConnectionError("two")),
        },
    )
    assert mixed.check_connection() == "network"


class HangingClient:
    def __init__(self, url):
        self.url = url
        self.authed = False
        self.timeout = None

    def login(self, username, password, code_provider):
        raise requests.exceptions.ReadTimeout("hanging")

    def is_authenticated(self):
        return self.authed


def test_health_status_trusts_a_fresh_stored_poll_without_touching_the_network(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE)
    calls = []

    def factory(url):
        calls.append(url)
        raise AssertionError("should not contact the school while the stored state is fresh")

    service = connection_service(store, connection_id, factory)
    clock = [1_000.0]
    integration.record_school_poll(store, connection_id, clock[0], True)
    clock[0] += 60
    assert service.health_status(clock=lambda: clock[0]) == {"status": "ok", "stale": False}
    assert calls == []


def test_health_status_verifies_live_once_the_stored_poll_is_older_than_five_minutes(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE)
    clock = [1_000.0]
    integration.record_school_poll(store, connection_id, clock[0], True)
    clock[0] += 301

    def factory(url):
        return FakeClient(url, children=[("c1", "Alice Example")])

    service = connection_service(store, connection_id, factory)
    assert service.health_status(clock=lambda: clock[0]) == {"status": "ok", "stale": False}


def test_health_status_falls_back_to_the_stale_stored_state_when_the_live_check_hangs(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE)
    clock = [1_000.0]
    integration.record_school_poll(store, connection_id, clock[0], True)
    clock[0] += 301

    made = {}

    def factory(url):
        client = HangingClient(url)
        made["client"] = client
        return client

    service = connection_service(store, connection_id, factory)
    assert service.health_status(clock=lambda: clock[0]) == {"status": "ok", "stale": True}
    assert made["client"].timeout == 5


def test_health_status_verifies_live_with_a_short_timeout_when_never_polled_before(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE)
    made = {}

    def factory(url):
        client = FakeClient(url, children=[("c1", "Alice Example")])
        made["client"] = client
        return client

    service = connection_service(store, connection_id, factory)
    assert service.health_status(clock=lambda: 1_000.0) == {"status": "ok", "stale": False}
    assert made["client"].timeout == 5


def test_health_status_of_an_unconfigured_connection_is_not_configured(tmp_path):
    empty_service = connection_service(Store(tmp_path / "empty"), "deadbeef", lambda url: FakeClient(url))
    assert empty_service.health_status() == {"status": "not_configured", "stale": False}


def test_a_timetable_is_fetched_from_the_school_named_in_the_key(tmp_path):
    service, _, one, two, clients = two_schools(tmp_path)
    service.children()
    assert service.timetable(f"{two}:c1")["lessons"][0]["subject_code"] == "D"
    with pytest.raises(DataError) as unknown:
        service.timetable(f"{one}:nope")
    assert unknown.value.message_key == "api.child.unknown"
    with pytest.raises(DataError):
        service.timetable("c1")
    with pytest.raises(DataError):
        service.timetable("deadbeef:c1")


def test_a_pending_school_is_left_out_until_its_setup_is_complete(tmp_path):
    service, store, one, two, _ = two_schools(tmp_path)
    store.update_connection(two, setup_complete=False)
    assert [connection.id for connection in service.connections()] == [one]
    assert [child["connection_id"] for child in service.children()] == [one]
    assert [connection.id for connection in service.connections(include_pending=True)] == [one, two]
    assert [child["connection_id"] for child in service.children(two)] == [two]


def test_the_module_registry_is_merged_and_kept_per_school(tmp_path):
    service, store, one, two, _ = two_schools(tmp_path)
    store.connection_store(one).save_modules(
        {"modules": {name: name != modules.LETTERS for name in modules.MODULES}, "checked_at": 5}
    )
    store.connection_store(two).save_modules(
        {"modules": {name: name == modules.LETTERS for name in modules.MODULES}, "checked_at": 9}
    )
    merged = service.modules()
    assert all(merged["modules"].values())
    assert merged["checked_at"] == 9
    assert service.modules_of(one)["modules"][modules.LETTERS] is False
    assert service.modules_of(two)["modules"][modules.TIMETABLE] is False
    with pytest.raises(DataError):
        service.modules_of("deadbeef")


def test_disconnecting_one_school_leaves_the_other_untouched(tmp_path):
    service, store, one, two, _ = two_schools(tmp_path)
    service.children()
    store.connection_store(one).save_seen({"pinboard": [1]})
    store.connection_store(two).save_seen({"pinboard": [2]})
    result = service.disconnect(one)
    assert result["attempted"] is False
    assert [entry["id"] for entry in store.connections()] == [two]
    assert store.load_secrets(one) == {}
    assert store.load_secrets(two)["username"] == DEFAULT_SECRETS["username"]
    assert set(store.load_seen()) == {two}
    assert [child["connection_id"] for child in service.children()] == [two]
    assert service.is_configured() is True
    service.disconnect(two)
    assert store.connections() == []
    assert service.is_configured() is False
    assert service.check_connection() == "not_configured"


def test_without_any_school_the_reads_say_not_configured(tmp_path):
    service = IServService(Store(tmp_path / "data"), client_factory=lambda url: FakeClient(url))
    assert service.children() == []
    with pytest.raises(NotConfiguredError):
        service.letters()
    with pytest.raises(NotConfiguredError):
        service.me()


def test_merged_letters_carry_the_school_and_a_prefixed_key(tmp_path):
    service, _, one, two, _ = two_schools(tmp_path)
    service.connection(one).letters = lambda tab="current": {
        "letters": [{"letter_id": "l1", "recipient_id": "r1", "title": "One", "published": "01.09.2026"}]
    }
    service.connection(two).letters = lambda tab="current": {
        "letters": [{"letter_id": "l1", "recipient_id": "r1", "title": "Two", "published": "03.09.2026"}]
    }
    body = service.letters()
    assert [entry["title"] for entry in body["letters"]] == ["Two", "One"]
    assert [entry["key"] for entry in body["letters"]] == [f"{two}:l1:r1", f"{one}:l1:r1"]
    assert [entry["school"] for entry in body["letters"]] == ["School Two", "School One"]
    assert body["unavailable"] == []


def test_marking_letters_read_routes_every_key_to_its_school(tmp_path):
    service, _, one, two, _ = two_schools(tmp_path)
    seen = {}

    def recorder(school):
        def mark(keys=None, mark_all=False):
            seen[school] = list(keys or [])
            return {"read": len(keys or []), "blocked": 0, "failed": 0}

        return mark

    for name in (one, two):
        service.connection(name).mark_letters_read = recorder(name)
    assert service.mark_letters_read([f"{one}:l1:r1", f"{two}:l2:r2", f"{one}:l3:r3"]) == {
        "read": 3,
        "blocked": 0,
        "failed": 0,
    }
    assert seen == {one: ["l1:r1", "l3:r3"], two: ["l2:r2"]}
    with pytest.raises(DataError):
        service.mark_letters_read(["deadbeef:l1:r1"])


def test_a_school_that_does_not_answer_is_named_as_unavailable_in_the_merge(tmp_path, caplog):
    service, _, one, two, _ = two_schools(tmp_path)
    service.connection(one).pinboard = lambda: {"folders": [{"id": 1, "title": "Board"}], "feed": [{"id": 7, "folder_id": 1}]}

    def boom():
        raise requests.ConnectionError("down")

    service.connection(two).pinboard = boom
    with caplog.at_level(logging.WARNING, logger="app.service"):
        body = service.pinboard()
    assert body["unavailable"] == [two]
    assert body["feed"][0]["key"] == f"{one}:7"
    assert body["feed"][0]["folder_key"] == f"{one}:1"
    assert body["folders"][0]["key"] == f"{one}:1"
    assert body["folders"][0]["school"] == "School One"
    assert any(f"school#{two}" in record.getMessage() for record in caplog.records)


def test_pinboard_keys_are_split_by_school_when_marking_seen(tmp_path):
    service, _, one, two, _ = two_schools(tmp_path)
    seen = {}

    def recorder(school):
        def mark(tile_ids=None, mark_all=False, unseen=False):
            seen[school] = list(tile_ids or [])
            return {"seen": len(tile_ids or [])}

        return mark

    for name in (one, two):
        service.connection(name).mark_pinboard_seen = recorder(name)
    assert service.mark_pinboard_seen([f"{one}:7", f"{two}:7", f"{one}:x"]) == {"seen": 2}
    assert seen == {one: [7], two: [7]}


def test_messenger_rooms_merge_across_schools_with_their_own_user_ids(tmp_path):
    service, _, one, two, _ = two_schools(tmp_path)
    service.connection(one).messenger_rooms = lambda: {
        "self_user_id": "@one:x",
        "rooms": [{"room_id": "!a:x", "last_message_at": 5}],
        "can_write_to_teacher": False,
    }
    service.connection(two).messenger_rooms = lambda: {
        "self_user_id": "@two:y",
        "rooms": [{"room_id": "!b:y", "last_message_at": 9}],
        "can_write_to_teacher": True,
    }
    body = service.messenger_rooms()
    assert [room["room_id"] for room in body["rooms"]] == ["!b:y", "!a:x"]
    assert [room["self_user_id"] for room in body["rooms"]] == ["@two:y", "@one:x"]
    assert [room["connection_id"] for room in body["rooms"]] == [two, one]
    assert body["self_user_ids"] == {one: "@one:x", two: "@two:y"}
    assert body["can_write_to_teacher"] is True


def test_messenger_media_urls_name_the_school_they_belong_to(tmp_path):
    service, _, one, _, _ = two_schools(tmp_path)
    service.connection(one).messenger_room_messages = lambda room_id, before=None: {
        "messages": [{"event_id": "$1", "media_url": "api/messenger/media/s/m"}, {"event_id": "$2"}],
        "before": "",
    }
    body = service.messenger_room_messages(one, "!a:x")
    assert body["messages"][0]["media_url"] == f"api/messenger/media/s/m?connection={one}"
    assert "media_url" not in body["messages"][1]


def test_the_absence_overview_names_its_school(tmp_path):
    service, _, one, two, _ = two_schools(tmp_path)
    service.connection(two).absences_overview = lambda: {"children": [], "entries": []}
    body = service.absences_overview(two)
    assert body["connection_id"] == two
    assert body["school"] == "School Two"
    service.connection(one).absences_overview = lambda: {"children": [], "entries": []}
    assert service.absences_overview()["connection_id"] == one


def test_the_poller_walks_every_school_and_a_failing_one_does_not_stop_the_other(tmp_path):
    service, store, one, two, _ = two_schools(
        tmp_path, {SCHOOL_TWO: lambda url: FakeClient(url, fail=LoginError("password changed"))}
    )
    sent = []
    timetable_only = {"modules": {name: name == modules.TIMETABLE for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(one).save_modules(timetable_only)
    poller = Poller(
        service,
        notifier=lambda name, message: sent.append(message) or True,
        notifiers={"auth": lambda name, message: sent.append(message) or True},
    )
    events = poller.poll_once()
    keys = [entry.get("child_key") for entry in events if entry.get("child_key")]
    assert keys == [f"{one}:c1"]
    assert {"connection_id": two, "error": "bad_credentials"} in events
    assert store.connection(one)["poll_state"][f"{one}:c1"]["changes_count"] == 0
    assert store.connection(two)["poll_state"] == {}
    assert store.connection(two)["auth_incident_sent"] is True
    assert integration.school_state(store, one)["last_poll_ok"] is True
    assert integration.school_state(store, two)["last_error"] == integration.ERROR_AUTH
    shared = store.load_integration_state()
    assert shared["last_poll_ok"] is False
    assert shared["last_error"] == integration.ERROR_AUTH
    assert sent == ["School Two: " + __import__("app.messages", fromlist=["text"]).text("notify.auth.badCredentials")]


@pytest.mark.parametrize(
    "failure",
    [requests.ConnectionError("school one is down"), DataError("school one answered with garbage")],
    ids=["connection_error", "data_error"],
)
def test_a_school_that_fails_outside_the_login_does_not_stop_the_other_school(tmp_path, caplog, failure):
    service, store, one, two, _ = two_schools(tmp_path, {SCHOOL_ONE: lambda url: FakeClient(url, fail=failure)})
    for name in (one, two):
        store.connection_store(name).save_modules(
            {"modules": {name: name == modules.TIMETABLE for name in modules.MODULES}, "checked_at": 1}
        )
    poller = Poller(service, notifier=lambda name, message: True)
    with caplog.at_level(logging.WARNING, logger="app.poller"):
        events = poller.poll_once()
    keys = [entry.get("child_key") for entry in events if entry.get("child_key")]
    assert keys == [f"{two}:c1"]
    assert store.connection(two)["poll_state"][f"{two}:c1"]["changes_count"] == 0
    assert integration.school_state(store, two)["last_poll_ok"] is True
    assert integration.school_state(store, one)["last_poll_ok"] is False
    assert integration.school_state(store, one)["last_error"] == integration.ERROR_NETWORK
    shared = store.load_integration_state()
    assert shared["last_poll_ok"] is False
    assert shared["last_error"] == integration.ERROR_NETWORK
    lines = [record.getMessage() for record in caplog.records if record.name == "app.poller"]
    assert len(lines) == 1
    assert one in lines[0]
    assert type(failure).__name__ in lines[0]
    assert "school one" not in lines[0]
    assert "u" != lines[0]
    assert DEFAULT_SECRETS["username"] not in lines[0].split()
    assert "Alice" not in lines[0]


def test_push_texts_name_the_school_only_when_there_is_more_than_one(tmp_path):
    from app import messages

    service, store, one, two, _ = two_schools(tmp_path)
    sent = []
    notifiers = {"letters": lambda name, message: sent.append(message) or True}
    for name in (one, two):
        service.connection(name).letters = lambda tab="current", school=name: {
            "letters": [{"letter_id": school, "recipient_id": "r", "title": "New", "unread": True}]
        }
        service.connection(name).pending_confirmation_keys = lambda tab="current": set()
    Poller(service, notifiers=notifiers).poll_once()
    for name in (one, two):
        service.connection(name).letters = lambda tab="current", school=name: {
            "letters": [
                {"letter_id": school, "recipient_id": "r", "title": "New", "unread": True},
                {"letter_id": school + "-2", "recipient_id": "r", "title": "Newer", "unread": True},
            ]
        }
    Poller(service, notifiers=notifiers).poll_once()
    plain = messages.text_count("de", "notify.letters.new", 1)
    assert sent == [f"School One: {plain}", f"School Two: {plain}"]

    store.remove_connection(two)
    sent.clear()
    service.connection(one).letters = lambda tab="current": {
        "letters": [
            {"letter_id": "x", "recipient_id": "r", "title": "New", "unread": True},
            {"letter_id": "y", "recipient_id": "r", "title": "Newer", "unread": True},
            {"letter_id": "z", "recipient_id": "r", "title": "Newest", "unread": True},
        ]
    }
    Poller(service, notifiers=notifiers).poll_once()
    assert sent == [messages.text_count("de", "notify.letters.new", 3)]


def test_the_poller_stores_the_school_name_it_learns_from_the_profile(tmp_path):
    service, store, one, _, _ = two_schools(tmp_path)
    store.update_connection(one, school_name="")
    service.connection(one).me = lambda: {"school_name": "Learned School"}
    Poller(service).poll_once()
    assert store.connection(one)["school_name"] == "Learned School"
    assert integration.school_state(store, one)["school_name"] == "Learned School"
    assert service.connection(one).display_name() == "Learned School"


def test_the_short_name_of_a_school_defaults_to_its_host_without_the_top_level_label(tmp_path):
    from app.store import connection_short_name, default_short_name

    assert default_short_name("https://gym-sued.example") == "gym-sued"
    assert default_short_name("https://iserv.gym-sued.example/iserv/") == "iserv.gym-sued"
    assert default_short_name("https://localhost") == "localhost"
    assert default_short_name("") == ""
    service, store, one, two, _ = two_schools(tmp_path)
    assert connection_short_name(store.connection(one)) == "school-one"
    store.update_connection(two, short_name="Gym Süd")
    assert connection_short_name(store.connection(two)) == "Gym Süd"
    assert [row["short_name"] for row in service.summaries()] == ["school-one", "Gym Süd"]
