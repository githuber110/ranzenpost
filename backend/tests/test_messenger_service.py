import pytest
import requests

from app.iserv.errors import LoginError
from app.iserv.messenger import MatrixAuthError
from app.messenger import MessengerService

BASE = "https://school.example"
BOOTSTRAP_HTML = (
    "<html><body><script>"
    '{"messenger_authentication":{"access_token":"tok-1","device_id":"dev-1",'
    '"home_server":"srv-1","user_id":"@me:srv-1","iserv_token":"it-1","iserv_cryptkey":"ck-1"}}'
    "</script></body></html>"
)


class FakePage:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeIServClient:
    def __init__(self, base_url=BASE, page=None):
        self.base_url = base_url
        self.page = page or FakePage(200, BOOTSTRAP_HTML)
        self.fetched_paths = []

    def fetch(self, path):
        self.fetched_paths.append(path)
        return self.page


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
    store = DictStore({"messenger_access_token": "cached-tok", "messenger_home_server": "srv-1"})
    client = FakeIServClient()
    iserv = FakeIServ(store, client)
    tokens_seen = []
    service = MessengerService(iserv, matrix_client_factory=make_factory({}, tokens_seen))
    service.rooms()
    assert client.fetched_paths == []
    assert tokens_seen == ["cached-tok"]


def test_a_401_triggers_exactly_one_bootstrap_refresh_then_succeeds():
    store = DictStore({"messenger_access_token": "stale-tok"})
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
    assert result == {"rooms": []}
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
