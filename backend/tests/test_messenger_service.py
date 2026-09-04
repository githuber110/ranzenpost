import pytest
import requests

from app.iserv.errors import LoginError
from app.iserv.messenger import MatrixAuthError
from app.messenger import MessengerService

BASE = "https://school.example"
BOOTSTRAP_HTML = (
    "<html><body><script>"
    '{"messenger_user_privileges":{"canCreateRoom":false,"canWriteToTeacher":true},'
    '"messenger_authentication":{"access_token":"tok-1","device_id":"dev-1",'
    '"home_server":"srv-1","user_id":"@me:srv-1","iserv_token":"it-1","iserv_cryptkey":"ck-1"}}'
    "</script></body></html>"
)
KNOWN_PRIVILEGES = {"messenger_privileges_known": "1", "messenger_can_write_to_teacher": "1"}
TEACHER_FORM_HTML = (
    '<html><body><form method="post">'
    '<input name="teacher_room[_token]" value="csrf-9">'
    '<input name="teacher_room[teacher_id]" value="">'
    "</form></body></html>"
)


class FakePage:
    def __init__(self, status_code=200, text="", url="", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeIServClient:
    def __init__(self, base_url=BASE, page=None, pages=None, posted=None):
        self.base_url = base_url
        self.page = page or FakePage(200, BOOTSTRAP_HTML)
        self.pages = pages or {}
        self.posted = posted
        self.fetched_paths = []
        self.fetched_params = []
        self.posts = []

    def fetch(self, path, params=None):
        self.fetched_paths.append(path)
        self.fetched_params.append(params)
        return self.pages.get(path, self.page)

    def post_absolute(self, url, data, timeout=30):
        self.posts.append((url, data))
        return self.posted or FakePage(200, "")


class FakeIServ:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or FakeIServClient()

    def iserv_session(self):
        return self.client


class DictStore:
    def __init__(self, initial=None):
        self._secrets = dict(initial or {})

    def load_secrets(self):
        return dict(self._secrets)

    def save_secrets(self, secrets):
        self._secrets = dict(secrets)


class FakeMatrixResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._json


class FakeMatrixClient:
    def __init__(self, base_url, access_token, plan=None):
        self.base_url = base_url
        self.access_token = access_token
        self.plan = plan or {}
        self.calls = []

    def sync(self, since=None, timeout_ms=0):
        self.calls.append(("sync", self.access_token))
        return self._resolve("sync")

    def room_messages(self, room_id, before_token=None, limit=30):
        self.calls.append(("room_messages", self.access_token, room_id, before_token))
        return self._resolve("room_messages")

    def send_message(self, room_id, txn_id, body):
        self.calls.append(("send_message", self.access_token, room_id, txn_id, body))
        return self._resolve("send_message")

    def fetch_media(self, server_name, media_id):
        self.calls.append(("fetch_media", self.access_token, server_name, media_id))
        return self._resolve("fetch_media")

    def _resolve(self, name):
        outcome = self.plan.get(name)
        if outcome is None:
            return FakeMatrixResponse()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_factory(plan, tokens_seen=None):
    def factory(base_url, access_token):
        if tokens_seen is not None:
            tokens_seen.append(access_token)
        return FakeMatrixClient(base_url, access_token, plan)

    return factory


def test_bootstrap_stores_the_matrix_auth_set_alongside_existing_iserv_secrets():
    store = DictStore({"username": "parent1", "password": "pw"})
    iserv = FakeIServ(store)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    service.rooms()
    secrets = store.load_secrets()
    assert secrets["username"] == "parent1"
    assert secrets["messenger_access_token"] == "tok-1"
    assert secrets["messenger_device_id"] == "dev-1"
    assert secrets["messenger_home_server"] == "srv-1"
    assert secrets["messenger_user_id"] == "@me:srv-1"


def test_the_bootstrap_page_is_fetched_through_the_normal_iserv_session():
    store = DictStore()
    client = FakeIServClient()
    iserv = FakeIServ(store, client)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    service.rooms()
    assert client.fetched_paths == ["/iserv/messenger/"]


def test_a_stored_token_is_reused_without_a_fresh_bootstrap_fetch():
    store = DictStore(
        dict(
            KNOWN_PRIVILEGES,
            messenger_access_token="cached-tok",
            messenger_home_server="srv-1",
        )
    )
    client = FakeIServClient()
    iserv = FakeIServ(store, client)
    tokens_seen = []
    service = MessengerService(iserv, matrix_client_factory=make_factory({}, tokens_seen))
    service.rooms()
    assert client.fetched_paths == []
    assert tokens_seen == ["cached-tok"]


def test_a_401_triggers_exactly_one_bootstrap_refresh_then_succeeds():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="stale-tok"))
    client = FakeIServClient()
    iserv = FakeIServ(store, client)
    tokens_seen = []

    def factory(base_url, access_token):
        tokens_seen.append(access_token)

        def sync_plan(since=None, timeout_ms=0):
            if access_token == "stale-tok":
                raise MatrixAuthError("expired")
            return FakeMatrixResponse(json_data={"rooms": {"join": {}}})

        matrix = FakeMatrixClient(base_url, access_token)
        matrix.sync = sync_plan
        return matrix

    service = MessengerService(iserv, matrix_client_factory=factory)
    result = service.rooms()
    assert result == {"rooms": [], "self_user_id": "@me:srv-1", "can_write_to_teacher": True}
    assert tokens_seen == ["stale-tok", "tok-1"]
    assert client.fetched_paths == ["/iserv/messenger/"]


def test_a_401_after_refresh_raises_a_login_error_instead_of_looping():
    store = DictStore({"messenger_access_token": "stale-tok"})
    iserv = FakeIServ(store)
    plan = {"sync": MatrixAuthError("still rejected")}
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    with pytest.raises(LoginError):
        service.rooms()


def test_a_non_200_sync_response_is_raised_as_a_request_exception():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    plan = {"sync": FakeMatrixResponse(status_code=500)}
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    with pytest.raises(requests.RequestException):
        service.rooms()


def test_a_failed_bootstrap_page_fetch_is_raised_as_a_request_exception():
    store = DictStore()
    client = FakeIServClient(page=FakePage(500, ""))
    iserv = FakeIServ(store, client)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    with pytest.raises(requests.RequestException):
        service.rooms()


def test_send_message_uses_a_fresh_transaction_id_and_returns_the_event_id():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    plan = {"send_message": FakeMatrixResponse(status_code=200, json_data={"event_id": "$abc"})}
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    result = service.send_message("!room:school.example", "hello there")
    assert result["ok"] is True
    assert result["event_id"] == "$abc"


def test_send_message_rejects_an_empty_body_without_calling_matrix():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    calls = []
    service = MessengerService(
        iserv, matrix_client_factory=make_factory({}, tokens_seen=calls)
    )
    result = service.send_message("!room:school.example", "   ")
    assert result["ok"] is False
    assert calls == []


def test_send_message_rejects_a_malformed_room_id():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    from app.iserv.errors import DataError

    with pytest.raises(DataError):
        service.send_message("not-a-room-id", "hello")


def test_room_messages_forwards_the_before_token_and_builds_media_urls():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    plan = {
        "room_messages": FakeMatrixResponse(
            json_data={
                "end": "batch-2",
                "chunk": [
                    {
                        "type": "m.room.message",
                        "event_id": "$1",
                        "sender": "@teacher:srv",
                        "origin_server_ts": 1,
                        "content": {
                            "msgtype": "m.image",
                            "body": "x.png",
                            "url": "mxc://school-server/media-9",
                            "info": {},
                        },
                    }
                ],
            }
        )
    }
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    result = service.room_messages("!room:school.example", before="batch-1")
    assert result["before"] == "batch-2"
    assert result["messages"][0]["media_url"] == "api/messenger/media/school-server/media-9"


def test_both_read_endpoints_name_the_own_matrix_user_so_the_ui_can_tell_the_sides_apart():
    store = DictStore(
        dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1", messenger_user_id="@me:srv")
    )
    iserv = FakeIServ(store)
    plan = {
        "sync": FakeMatrixResponse(json_data={"rooms": {"join": {}}}),
        "room_messages": FakeMatrixResponse(json_data={"end": "", "chunk": []}),
    }
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    assert service.rooms()["self_user_id"] == "@me:srv"
    assert service.room_messages("!room:school.example")["self_user_id"] == "@me:srv"


def test_unread_pulse_returns_the_total_across_rooms():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    plan = {
        "sync": FakeMatrixResponse(
            json_data={
                "rooms": {
                    "join": {
                        "!a:srv": {"unread_notifications": {"notification_count": 3}},
                        "!b:srv": {"unread_notifications": {"notification_count": 1}},
                    }
                }
            }
        )
    }
    service = MessengerService(iserv, matrix_client_factory=make_factory(plan))
    assert service.unread_pulse() == 4


def test_media_rejects_a_malformed_server_name_or_media_id():
    store = DictStore({"messenger_access_token": "tok-1"})
    iserv = FakeIServ(store)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    from app.iserv.errors import DataError

    with pytest.raises(DataError):
        service.media("../etc", "media-1")
    with pytest.raises(DataError):
        service.media("school-server", "../../secret")


def test_an_installation_without_a_stored_privilege_flag_learns_it_once():
    store = DictStore({"messenger_access_token": "cached-tok"})
    client = FakeIServClient()
    iserv = FakeIServ(store, client)
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    assert service.rooms()["can_write_to_teacher"] is True
    assert client.fetched_paths == ["/iserv/messenger/"]
    assert service.rooms()["can_write_to_teacher"] is True
    assert client.fetched_paths == ["/iserv/messenger/"]


def test_an_account_without_the_teacher_privilege_reports_it_to_the_ui():
    page = FakePage(
        200,
        BOOTSTRAP_HTML.replace('"canWriteToTeacher":true', '"canWriteToTeacher":false'),
    )
    store = DictStore()
    iserv = FakeIServ(store, FakeIServClient(page=page))
    service = MessengerService(iserv, matrix_client_factory=make_factory({}))
    assert service.rooms()["can_write_to_teacher"] is False


def test_marking_a_room_read_sends_exactly_one_read_marker_for_the_named_event():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    iserv = FakeIServ(store)
    markers = []

    def factory(base_url, access_token):
        matrix = FakeMatrixClient(base_url, access_token)
        matrix.send_read_marker = lambda room_id, event_id: (
            markers.append((room_id, event_id)) or FakeMatrixResponse(status_code=200)
        )
        return matrix

    service = MessengerService(iserv, matrix_client_factory=factory)
    result = service.mark_room_read("!room:school.example", "$evt-9")
    assert result["ok"] is True
    assert markers == [("!room:school.example", "$evt-9")]


def test_marking_a_room_read_rejects_a_malformed_room_or_event_id():
    from app.iserv.errors import DataError

    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    service = MessengerService(FakeIServ(store), matrix_client_factory=make_factory({}))
    with pytest.raises(DataError):
        service.mark_room_read("not-a-room", "$evt-9")
    with pytest.raises(DataError):
        service.mark_room_read("!room:school.example", "evt-9")


def test_the_teacher_search_forwards_the_query_and_keeps_the_value_untouched():
    store = DictStore(KNOWN_PRIVILEGES)
    page = FakePage(
        200,
        json_data=[
            {"label": "Fr. Behrend", "value": "userid:11111111-2222-3333-4444-555555555555"},
            {"label": "", "value": "userid:empty"},
        ],
    )
    client = FakeIServClient(pages={"/iserv/messenger/autocomplete/teacher": page})
    service = MessengerService(FakeIServ(store, client), matrix_client_factory=make_factory({}))
    result = service.search_teachers("Beh")
    assert client.fetched_paths == ["/iserv/messenger/autocomplete/teacher"]
    assert client.fetched_params == [{"type": "userid", "query": "Beh"}]
    assert result["teachers"] == [
        {
            "label": "Fr. Behrend",
            "value": "userid:11111111-2222-3333-4444-555555555555",
            "extra": "",
        }
    ]


def test_an_empty_teacher_query_never_reaches_iserv():
    store = DictStore(KNOWN_PRIVILEGES)
    client = FakeIServClient()
    service = MessengerService(FakeIServ(store, client), matrix_client_factory=make_factory({}))
    assert service.search_teachers("  ") == {"teachers": [], "allowed": True}
    assert client.fetched_paths == []


def test_the_teacher_search_stays_shut_without_the_privilege():
    store = DictStore({"messenger_privileges_known": "1", "messenger_can_write_to_teacher": ""})
    client = FakeIServClient()
    service = MessengerService(FakeIServ(store, client), matrix_client_factory=make_factory({}))
    assert service.search_teachers("Beh") == {"teachers": [], "allowed": False}
    assert client.fetched_paths == []


def _teacher_room_service(store, posted, sync_plan=None):
    form = FakePage(200, TEACHER_FORM_HTML, url=BASE + "/iserv/messenger/form/room/teacher_new")
    client = FakeIServClient(
        pages={"/iserv/messenger/form/room/teacher_new": form}, posted=posted
    )
    service = MessengerService(
        FakeIServ(store, client),
        matrix_client_factory=make_factory(sync_plan or {}),
    )
    service.sleeper = lambda seconds: None
    return service, client


def test_creating_a_teacher_room_pulls_a_fresh_token_and_posts_the_iserv_field_names():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    posted = FakePage(
        200,
        "",
        json_data={"room_id": "!new:school.example"},
        headers={"content-type": "application/json"},
    )
    sync = {
        "sync": FakeMatrixResponse(json_data={"rooms": {"join": {"!new:school.example": {}}}})
    }
    service, client = _teacher_room_service(store, posted, sync)
    result = service.create_teacher_room("userid:abc", ["child-1", "child-2"], True)
    assert result["ok"] is True
    assert result["room_id"] == "!new:school.example"
    assert result["joined"] is True
    url, data = client.posts[0]
    assert url == BASE + "/iserv/messenger/form/room/teacher_new"
    assert data == [
        ("teacher_room[_token]", "csrf-9"),
        ("teacher_room[teacher_id]", "userid:abc"),
        ("teacher_room[add_other_parents]", "1"),
        ("teacher_room[child_ids][]", "child-1"),
        ("teacher_room[child_ids][]", "child-2"),
    ]


def test_the_parent_flag_travels_as_zero_when_the_box_stays_empty():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    posted = FakePage(
        200,
        "",
        json_data={"room_id": "!new:school.example"},
        headers={"content-type": "application/json"},
    )
    sync = {
        "sync": FakeMatrixResponse(json_data={"rooms": {"join": {"!new:school.example": {}}}})
    }
    service, client = _teacher_room_service(store, posted, sync)
    service.create_teacher_room("userid:abc", ["child-1"], False)
    assert ("teacher_room[add_other_parents]", "0") in client.posts[0][1]


def test_an_html_answer_is_a_generic_failure_and_never_parsed():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    posted = FakePage(200, "<html><form>error</form></html>", headers={"content-type": "text/html"})
    service, _client = _teacher_room_service(store, posted)
    result = service.create_teacher_room("userid:abc", ["child-1"], False)
    assert result["ok"] is False
    assert result["message_key"] == "api.messenger.room.rejected"


def test_json_without_a_room_id_counts_as_rejected():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    posted = FakePage(200, "", json_data={"ok": True}, headers={"content-type": "application/json"})
    service, _client = _teacher_room_service(store, posted)
    result = service.create_teacher_room("userid:abc", ["child-1"], False)
    assert result["ok"] is False
    assert result["message_key"] == "api.messenger.room.rejected"


def test_a_room_that_never_joins_within_the_timeout_ends_in_the_pending_way_out():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    posted = FakePage(
        200,
        "",
        json_data={"room_id": "!new:school.example"},
        headers={"content-type": "application/json"},
    )
    sync = {"sync": FakeMatrixResponse(json_data={"rooms": {"join": {}}})}
    service, _client = _teacher_room_service(store, posted, sync)
    ticks = iter([0.0, 5.0, 10.0, 20.0, 30.0, 40.0])
    service.clock = lambda: next(ticks)
    result = service.create_teacher_room("userid:abc", ["child-1"], False)
    assert result["ok"] is True
    assert result["joined"] is False
    assert result["message_key"] == "api.messenger.room.pending"


def test_creating_a_room_without_a_child_never_touches_the_network():
    store = DictStore(dict(KNOWN_PRIVILEGES, messenger_access_token="tok-1"))
    service, client = _teacher_room_service(store, None)
    result = service.create_teacher_room("userid:abc", [], False)
    assert result["ok"] is False
    assert result["message_key"] == "api.messenger.room.incomplete"
    assert client.fetched_paths == []
    assert client.posts == []


def test_creating_a_room_without_the_privilege_never_touches_the_network():
    store = DictStore({"messenger_privileges_known": "1", "messenger_can_write_to_teacher": ""})
    service, client = _teacher_room_service(store, None)
    result = service.create_teacher_room("userid:abc", ["child-1"], False)
    assert result["ok"] is False
    assert result["message_key"] == "api.messenger.room.forbidden"
    assert client.posts == []
