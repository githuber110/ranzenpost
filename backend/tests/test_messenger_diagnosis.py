import json
import logging
import pathlib
import re

import pytest
import requests
from fastapi.testclient import TestClient

from app import messages
from app.iserv.messenger import (
    INITIAL_SYNC_TIMELINE_LIMIT,
    MAX_CONTINUATION_HOPS,
    SCALAR_TYPES,
    STAGE_BOOTSTRAP,
    STAGE_LOGIN,
    STAGE_MATRIX,
    STAGE_MESSAGE_KEYS,
    STAGE_MODULE,
    STAGE_NETWORK,
    STAGE_NO_CREDENTIALS,
    STAGE_TIMEOUT,
    BootstrapNotFoundError,
    MessengerStageError,
    discover_matrix_base_url,
    flat_detail,
    looks_like_auth_page,
    page_diagnosis,
    parse_authenticate_paths,
    parse_authentication,
    parse_room_list,
)
from app.messenger import MessengerService
from app.server import create_app
from app.store import Store

from tests.test_messenger_service import (
    BASE,
    BOOTSTRAP_HTML,
    DictStore,
    FakeIServ,
    FakeIServClient,
    FakePage,
)

ALL_STAGES = (
    STAGE_MODULE,
    STAGE_LOGIN,
    STAGE_BOOTSTRAP,
    STAGE_MATRIX,
    STAGE_NETWORK,
    STAGE_TIMEOUT,
)

AUTH_REDIRECT_URL = (
    f"{BASE}/iserv/auth/login?_target_path=/iserv/auth/auth"
    "&client_id=00000000-0000-0000-0000-000000000000&response_type=code"
)
SPA_PAGE_HTML = (
    "<html><body><script>"
    '{"messenger_routing":{"messenger_authenticate":"/messenger/authenticate"}}'
    "</script></body></html>"
)
AUTHENTICATE_PAYLOAD = {
    "messenger_authentication": {
        "access_token": "tok-x",
        "device_id": "dev-x",
        "home_server": "srv-x",
        "user_id": "@me:srv-x",
        "iserv_token": "it-x",
        "iserv_cryptkey": "ck-x",
    }
}

OAUTH_CONTINUATION_URL = f"{BASE}/iserv/auth/auth?authok"
OAUTH_RETURN_PATH = "/iserv/app/authentication/redirect?code=fake-oauth-code-000000"
OAUTH_RETURN_URL = f"{BASE}{OAUTH_RETURN_PATH}"
CONTINUATION_HTML = (
    "<html><head>"
    f'<meta http-equiv="refresh" content="0;url={OAUTH_RETURN_PATH}">'
    "</head><body>weiter</body></html>"
)
LOGIN_PAGE_HTML = (
    "<html><head>"
    '<meta http-equiv="refresh" content="0;url=/iserv/portal">'
    "</head><body><form>"
    '<input name="_username"><input name="_password">'
    "</form></body></html>"
)
LOOP_URL = f"{BASE}/iserv/loop"
LOOP_HTML = (
    '<html><head><meta http-equiv="refresh" content="0;url=/iserv/loop">'
    "</head><body></body></html>"
)
FOREIGN_CONTINUATION_HTML = (
    '<html><head><meta http-equiv="refresh" content="0;url=https://evil.example/steal">'
    "</head><body></body></html>"
)

LEAKED_TOKEN = "syt-fake-leaked-access-token-00000000000000"
LEAKED_CODE = "fake-oauth-code-111111"
LEAKY_PAGE_URL = f"{BASE}/iserv/app/authentication/redirect?code={LEAKED_CODE}"
LEAKY_PAGE_HTML = (
    "<html><body><script>"
    '{"messenger_authentication":{"access_token":"' + LEAKED_TOKEN + '",'
    '"device_id":"ISEfakedevice00000000"}}'
    "</script></body></html>"
)

MESSENGER_WRITE_ROUTES = (
    ("/api/messenger/send", {"room_id": "!r:school.example", "text": "hi"}),
    ("/api/messenger/read", {"room_id": "!r:school.example", "event_id": "$e1"}),
    (
        "/api/messenger/room/teacher",
        {"teacher": "userid:t1", "child_ids": ["c1"], "add_other_parents": False},
    ),
)

CLASS_GROUP_JOIN_BURST = 12


def _service(client, store=None):
    return MessengerService(FakeIServ(store or DictStore(), client))


class StageRaisingService:
    def __init__(self, store, error):
        self.store = store
        self.error = error

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            raise self.error

        return call


class StubWizard:
    def status(self):
        return {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            return {}

        return call


def _stage_api(tmp_path, stage):
    store = Store(tmp_path / "data")
    error = MessengerStageError(stage, {"status": 502, "where": "matrix"})
    return TestClient(create_app(StageRaisingService(store, error), wizard=StubWizard()))


def test_a_redirect_into_the_oauth_flow_is_reported_as_a_refused_login():
    client = FakeIServClient(page=FakePage(200, "<html></html>", url=AUTH_REDIRECT_URL))
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_LOGIN
    assert caught.value.message_key == "api.messenger.error.login"
    assert caught.value.detail["final_path"].startswith("/iserv/auth/")


def test_the_oauth_continuation_page_is_followed_instead_of_being_called_a_refused_login():
    client = FakeIServClient(
        pages={
            "/iserv/messenger/": FakePage(200, CONTINUATION_HTML, url=OAUTH_CONTINUATION_URL),
            OAUTH_RETURN_URL: FakePage(200, BOOTSTRAP_HTML, url=f"{BASE}/iserv/messenger/"),
        }
    )
    auth = _service(client)._bootstrap()
    assert auth["access_token"] == "tok-1"
    assert OAUTH_RETURN_URL in client.fetched_paths


def test_a_page_that_really_asks_for_the_password_is_still_a_refused_login():
    client = FakeIServClient(
        pages={"/iserv/messenger/": FakePage(200, LOGIN_PAGE_HTML, url=f"{BASE}/iserv/auth/login")}
    )
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_LOGIN
    assert caught.value.detail["continuation_hops"] == 0


def test_a_continuation_that_never_arrives_gives_up_after_a_bounded_number_of_hops():
    assert 1 <= MAX_CONTINUATION_HOPS <= 6
    loop = FakePage(200, LOOP_HTML, url=LOOP_URL)
    client = FakeIServClient(page=loop, pages={"/iserv/messenger/": loop})
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_BOOTSTRAP
    assert caught.value.detail["continuation_hops"] == MAX_CONTINUATION_HOPS
    assert client.fetched_paths.count(LOOP_URL) == MAX_CONTINUATION_HOPS


def test_a_continuation_that_points_off_the_school_host_is_never_followed():
    client = FakeIServClient(
        pages={
            "/iserv/messenger/": FakePage(
                200, FOREIGN_CONTINUATION_HTML, url=f"{BASE}/iserv/messenger/"
            )
        }
    )
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.detail["continuation_hops"] == 0
    assert not any("evil.example" in path for path in client.fetched_paths)


@pytest.mark.parametrize("status", [403, 404, 500])
def test_a_messenger_page_that_is_not_served_is_reported_as_a_missing_module(status):
    client = FakeIServClient(page=FakePage(status, "", url=f"{BASE}/iserv/messenger/"))
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_MODULE
    assert caught.value.detail["status"] == status


def test_a_page_without_credentials_falls_back_to_the_authenticate_call():
    client = FakeIServClient(
        page=FakePage(200, SPA_PAGE_HTML, url=f"{BASE}/iserv/messenger/"),
        pages={
            "/iserv/messenger/": FakePage(200, SPA_PAGE_HTML, url=f"{BASE}/iserv/messenger/"),
            "/messenger/authenticate": FakePage(200, "", json_data=AUTHENTICATE_PAYLOAD),
        },
    )
    auth = _service(client)._bootstrap()
    assert auth["access_token"] == "tok-x"
    assert "/messenger/authenticate" in client.fetched_paths


def test_both_authenticate_prefixes_are_tried_before_giving_up():
    client = FakeIServClient(
        page=FakePage(200, "<html><body></body></html>", url=f"{BASE}/iserv/messenger/")
    )
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_BOOTSTRAP
    tried = caught.value.detail["authenticate_attempts"]
    assert "/iserv/messenger/authenticate" in tried
    assert "/messenger/authenticate" in tried


def test_the_bootstrap_diagnosis_carries_only_flat_display_ready_values():
    client = FakeIServClient(
        page=FakePage(404, "", url=f"{BASE}/messenger/authenticate"),
        pages={
            "/iserv/messenger/": FakePage(
                200, "<html><body></body></html>", url=f"{BASE}/iserv/messenger/"
            )
        },
    )
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    detail = caught.value.detail
    for key, value in detail.items():
        assert isinstance(key, str), f"{key!r} is not a display ready field name"
        assert value is None or isinstance(value, SCALAR_TYPES), f"{key} is not display ready"
    assert "/iserv/messenger/authenticate 404" in detail["authenticate_attempts"]
    assert "/messenger/authenticate 404" in detail["authenticate_attempts"]


def test_flat_detail_turns_a_nested_payload_into_display_ready_text():
    flat = flat_detail(
        {
            "attempts": [{"path": "/a", "status": 404}],
            "status": 200,
            "reached": True,
            "hint": None,
        }
    )
    assert flat["attempts"] == "path=/a, status=404"
    assert flat["status"] == 200
    assert flat["reached"] is True
    assert flat["hint"] is None


def test_the_bootstrap_diagnosis_names_the_stage_without_leaking_a_secret():
    client = FakeIServClient(
        page=FakePage(404, "", url=f"{BASE}/messenger/authenticate"),
        pages={"/iserv/messenger/": FakePage(200, LEAKY_PAGE_HTML, url=LEAKY_PAGE_URL)},
    )
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    detail = caught.value.detail
    assert LEAKED_TOKEN in LEAKY_PAGE_HTML
    assert LEAKED_CODE in LEAKY_PAGE_URL
    assert detail["marker_present"] is True
    assert set(detail) >= {
        "stage",
        "status",
        "final_path",
        "content_type",
        "length",
        "marker_present",
        "script_blocks",
    }
    rendered = json.dumps(detail)
    assert LEAKED_TOKEN not in rendered
    assert LEAKED_CODE not in rendered
    assert "ISEfakedevice00000000" not in rendered
    assert detail["page_fields"] == "access_token,device_id"
    assert detail["final_path"] == "/iserv/app/authentication/redirect"


def test_a_dead_network_is_reported_as_network_and_a_slow_one_as_a_timeout():
    class Dead(FakeIServClient):
        def fetch(self, path, params=None):
            raise requests.ConnectionError("down")

    class Slow(FakeIServClient):
        def fetch(self, path, params=None):
            raise requests.Timeout("slow")

    with pytest.raises(MessengerStageError) as dead:
        _service(Dead())._bootstrap()
    assert dead.value.stage == STAGE_NETWORK
    with pytest.raises(MessengerStageError) as slow:
        _service(Slow())._bootstrap()
    assert slow.value.stage == STAGE_TIMEOUT


def test_every_stage_carries_a_translatable_message():
    for stage in ALL_STAGES:
        key = MessengerStageError(stage).message_key
        for language in messages.LANGUAGES:
            assert messages.text_in(language, key).strip()


def test_a_failing_bootstrap_leaves_a_warning_with_a_traceback_in_the_log(caplog):
    class Dead(FakeIServClient):
        def fetch(self, path, params=None):
            raise requests.ConnectionError("down")

    with caplog.at_level(logging.WARNING, logger="app.messenger"):
        with pytest.raises(MessengerStageError):
            _service(Dead())._bootstrap()
    assert caplog.records
    assert caplog.records[0].levelno == logging.WARNING
    assert caplog.records[0].exc_info is not None


@pytest.mark.parametrize("path,body", MESSENGER_WRITE_ROUTES)
@pytest.mark.parametrize("stage", ALL_STAGES)
def test_a_messenger_write_route_keeps_the_stage_instead_of_collapsing_it_into_network(
    tmp_path, path, body, stage
):
    payload = _stage_api(tmp_path, stage).post(path, json=body).json()
    assert payload["ok"] is False
    assert payload["message_key"] == STAGE_MESSAGE_KEYS[stage]
    assert payload["message"] == messages.text(STAGE_MESSAGE_KEYS[stage])
    assert payload["diagnosis"]["stage"] == stage
    assert payload["diagnosis"]["status"] == 502


def test_a_messenger_write_route_reports_the_same_stage_as_a_read_route(tmp_path):
    api = _stage_api(tmp_path, STAGE_BOOTSTRAP)
    read = api.get("/api/messenger/rooms").json()
    write = api.post("/api/messenger/send", json={"room_id": "!r:x.example", "text": "hi"}).json()
    assert read["message_key"] == STAGE_MESSAGE_KEYS[STAGE_BOOTSTRAP]
    assert write["message_key"] == read["message_key"]
    assert write["diagnosis"] == read["diagnosis"]


def test_the_homeserver_is_only_taken_from_well_known_over_https_on_the_school_host():
    def answer(base_url):
        return FakePage(200, "", json_data={"m.homeserver": {"base_url": base_url}})

    assert discover_matrix_base_url(answer(f"{BASE}/matrix/"), BASE) == f"{BASE}/matrix"
    assert discover_matrix_base_url(answer("http://school.example"), BASE) == BASE
    assert discover_matrix_base_url(answer("https://matrix.example"), BASE) == BASE
    assert discover_matrix_base_url(answer("matrix.example"), BASE) == BASE
    assert discover_matrix_base_url(answer(""), BASE) == BASE
    assert discover_matrix_base_url(FakePage(404, ""), BASE) == BASE
    assert discover_matrix_base_url(FakePage(200, "no json"), BASE) == BASE
    assert discover_matrix_base_url(FakePage(200, "", json_data={"m.homeserver": {}}), BASE) == BASE
    assert discover_matrix_base_url(None, BASE) == BASE


def test_the_matrix_token_never_travels_to_a_homeserver_the_school_host_did_not_serve():
    built = {}

    def factory(base_url, token):
        built["base_url"] = base_url
        built["token"] = token
        return object()

    def built_on(base_url):
        client = FakeIServClient(
            pages={
                "/iserv/messenger/": FakePage(200, BOOTSTRAP_HTML, url=f"{BASE}/iserv/messenger/"),
                "/.well-known/matrix/client": FakePage(
                    200, "", json_data={"m.homeserver": {"base_url": base_url}}
                ),
            }
        )
        service = MessengerService(
            FakeIServ(DictStore(), client), matrix_client_factory=factory
        )
        service._matrix_client()
        return built["base_url"]

    assert built_on("https://matrix.example") == BASE
    assert built_on("http://school.example") == BASE
    assert built_on(f"{BASE}/matrix") == f"{BASE}/matrix"
    assert built["token"] == "tok-1"


def test_the_first_sync_is_filtered_so_it_cannot_outlast_the_request_window():
    class Recorder:
        def __init__(self):
            self.params = None

        def get(self, url, headers=None, params=None, timeout=None):
            self.params = params
            return FakePage(200, "", json_data={})

    from app.iserv.messenger import MatrixClient

    session = Recorder()
    MatrixClient(BASE, "tok", session=session).sync(timeout_ms=0)
    assert "filter" in session.params
    assert f'"limit":{INITIAL_SYNC_TIMELINE_LIMIT}' in session.params["filter"]
    session2 = Recorder()
    MatrixClient(BASE, "tok", session=session2).sync(since="s_1", timeout_ms=0)
    assert "filter" not in session2.params


def _message_event(timestamp):
    return {
        "type": "m.room.message",
        "event_id": f"$msg-{timestamp}",
        "sender": "@teacher:school.example",
        "origin_server_ts": timestamp,
        "content": {"msgtype": "m.text", "body": f"note {timestamp}"},
    }


def _join_event(index):
    return {
        "type": "m.room.member",
        "state_key": f"@parent{index}:school.example",
        "event_id": f"$join-{index}",
        "origin_server_ts": 9100 + index,
        "content": {"membership": "join", "displayname": f"Parent {index}"},
    }


def _room(name, events):
    return {
        "state": {"events": [{"type": "m.room.name", "content": {"name": name}}]},
        "timeline": {"events": events[-INITIAL_SYNC_TIMELINE_LIMIT:]},
    }


def test_the_first_sync_keeps_enough_timeline_for_the_room_list_to_stay_in_order():
    assert INITIAL_SYNC_TIMELINE_LIMIT >= 10
    busy = [_message_event(9000)] + [_join_event(index) for index in range(CLASS_GROUP_JOIN_BURST)]
    body = {
        "rooms": {
            "join": {
                "!class:school.example": _room("Class 3b", busy),
                "!teacher:school.example": _room("Teacher", [_message_event(1000)]),
            }
        }
    }
    rooms = parse_room_list(body, "@me:school.example")
    assert [room["room_id"] for room in rooms] == [
        "!class:school.example",
        "!teacher:school.example",
    ]
    assert rooms[0]["last_message"] == "note 9000"
    assert rooms[0]["last_message_at"] == 9000


def test_the_helpers_read_the_page_the_way_the_spa_writes_it():
    assert looks_like_auth_page(AUTH_REDIRECT_URL)
    assert not looks_like_auth_page(f"{BASE}/iserv/messenger/")
    assert parse_authenticate_paths(SPA_PAGE_HTML)[0] == "/messenger/authenticate"
    assert parse_authentication(AUTHENTICATE_PAYLOAD)["user_id"] == "@me:srv-x"
    diagnosis = page_diagnosis(FakePage(200, "<script>x</script>", url=f"{BASE}/iserv/messenger/"))
    assert diagnosis["script_blocks"] == 1
    assert diagnosis["marker_present"] is False


def test_the_parser_accepts_iservs_camel_case_field_names():
    from app.iserv.messenger import parse_authentication

    payload = {
        "messenger_authentication": {
            "accessToken": "syt-fake-token-for-tests-0000000000",
            "deviceId": "FAKEDEVICE0000",
            "homeServer": "11111111-1111-1111-1111-111111111111",
            "userId": "@22222222-2222-2222-2222-222222222222:11111111-1111-1111-1111-111111111111",
        }
    }
    auth = parse_authentication(payload)
    assert auth["access_token"] == "syt-fake-token-for-tests-0000000000"
    assert auth["home_server"] == "11111111-1111-1111-1111-111111111111"
    assert auth["user_id"].startswith("@")


def test_the_parser_still_accepts_snake_case():
    from app.iserv.messenger import parse_authentication

    payload = {
        "access_token": "syt-fake-token-for-tests-1111111111",
        "home_server": "33333333-3333-3333-3333-333333333333",
        "user_id": "@44444444-4444-4444-4444-444444444444:33333333-3333-3333-3333-333333333333",
    }
    assert parse_authentication(payload)["access_token"].endswith("1111111111")


def test_an_unparsable_answer_reports_its_field_names_but_never_a_value():
    from app.iserv.messenger import shape_of

    shape = shape_of({"accessToken": "syt-secret-value", "homeServer": "h", "somethingElse": 1})
    assert "accessToken" in shape
    assert "homeServer" in shape
    assert "syt-secret-value" not in shape


def test_the_page_diagnosis_describes_the_shape_without_repeating_the_content():
    from app.iserv.messenger import embedded_shape

    secret = "syt-fake-value-must-not-appear-000000"
    html = '<html><body><div data-messenger_authentication=\'{"accessToken":"' + secret + '"}\'></div></body></html>'
    shape = embedded_shape(html)
    assert "no marked object" in shape
    assert "occurrences=1" in shape
    assert "in_script=False" in shape
    assert secret not in shape
    assert "accessToken" not in shape


def test_the_page_diagnosis_says_when_the_marker_is_not_there_at_all():
    from app.iserv.messenger import embedded_shape

    assert "marker absent" in embedded_shape("<html><body>nothing here</body></html>")


def test_a_non_json_answer_is_described_by_type_and_shape_only():
    from app.iserv.messenger import _shape_only

    described = _shape_only('<!DOCTYPE h')
    assert "<" in described
    assert "DOCTYPE" not in described


def test_the_diagnosis_lists_the_addresses_the_page_points_at():
    from app.iserv.messenger import endpoint_hints

    html = (
        '<script>{"messenger_authentication":true,'
        '"routes":{"a":"/iserv/messenger/api/session","b":"/iserv/mail/inbox",'
        '"c":"/_matrix/client/v3/login"}}</script>'
    )
    hints = endpoint_hints(html)
    assert "/iserv/messenger/api/session" in hints
    assert "/_matrix/client/v3/login" in hints
    assert "/iserv/mail/inbox" not in hints


def test_a_page_without_any_such_address_says_so():
    from app.iserv.messenger import endpoint_hints

    assert endpoint_hints("<html><body>nothing</body></html>") == "none"


DIAGNOSIS_ASSIGNMENT = re.compile(r'diagnosis\["([a-z_]+)"\]\s*=')


def _diagnosis_keys():
    source = (pathlib.Path(__file__).resolve().parents[1] / "app" / "messenger.py").read_text(
        encoding="utf-8"
    )
    assigned = set(DIAGNOSIS_ASSIGNMENT.findall(source))
    assert assigned, "the scan found no diagnosis field at all, so it guards nothing"
    return assigned | set(page_diagnosis(FakePage(200, "", url=BASE))) | {"stage"}


def test_every_reported_diagnosis_field_has_a_wording_in_every_language():
    bundles = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "i18n"
    missing = []
    for language in ("de", "en", "ar", "tr", "ru", "uk"):
        texts = json.loads((bundles / f"{language}.json").read_text(encoding="utf-8"))
        for field in sorted(_diagnosis_keys()):
            if not str(texts.get(f"messenger.diagnosis.{field}") or "").strip():
                missing.append(f"{language}: {field}")
    assert missing == [], (
        "a diagnosis field without a wording reaches the reader as a raw English field "
        f"name: {missing}"
    )


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
WITH_CREDENTIALS = (FIXTURES / "messenger_page.html").read_text(encoding="utf-8")
WITHOUT_CREDENTIALS = (FIXTURES / "messenger_page_without_credentials.html").read_text(
    encoding="utf-8"
)


def test_the_credentials_are_read_from_the_element_iserv_puts_them_in():
    from app.iserv.messenger import PHP_DATA_ID, php_data

    assert PHP_DATA_ID in WITH_CREDENTIALS
    payload = php_data(WITH_CREDENTIALS)
    assert payload["messenger_authentication"]["access_token"].startswith("fixture-access-token")
    assert payload["messenger_routing_basepath"] == "/iserv/messenger"
    assert php_data("<html><body>no such element</body></html>") is None
    assert php_data('<script type="application/json" id="php-data">not json</script>') is None


def test_a_page_whose_credentials_iserv_left_empty_is_told_apart_from_a_missing_page():
    from app.iserv.messenger import credentials_note, credentials_withheld

    assert credentials_withheld(WITHOUT_CREDENTIALS)
    assert not credentials_withheld(WITH_CREDENTIALS)
    assert not credentials_withheld("<html><body></body></html>")
    assert credentials_note(WITHOUT_CREDENTIALS) == "messenger_authentication is null"
    assert credentials_note(WITH_CREDENTIALS) == "messenger_authentication complete"
    assert credentials_note("<html><body></body></html>") == "no php-data element"


def test_a_page_whose_credentials_are_incomplete_names_the_missing_fields_only():
    from app.iserv.messenger import credentials_note

    half = WITH_CREDENTIALS.replace('"iserv_cryptkey"', '"unused_field"')
    note = credentials_note(half)
    assert note == "messenger_authentication misses iserv_cryptkey"
    assert "fixture-cryptkey" not in note


DECOY_SCRIPT = (
    "<script>window.old = "
    '{"messenger_authentication":{"access_token":"stale-token-from-another-script",'
    '"home_server":"stale.example","user_id":"@stale:stale.example"}}'
    ";</script>"
)


def test_the_credentials_come_from_the_element_iserv_reads_not_from_any_script_that_names_them():
    from app.iserv.messenger import parse_bootstrap

    auth = parse_bootstrap(WITH_CREDENTIALS)
    assert auth["access_token"].startswith("fixture-access-token")
    assert auth["user_id"].startswith("@")

    decoyed = WITH_CREDENTIALS.replace("<body>", "<body>" + DECOY_SCRIPT, 1)
    assert "stale-token-from-another-script" in decoyed
    assert parse_bootstrap(decoyed)["access_token"].startswith("fixture-access-token")

    with pytest.raises(BootstrapNotFoundError):
        parse_bootstrap(WITHOUT_CREDENTIALS)


def _page_client(html):
    return FakeIServClient(
        page=FakePage(404, "", url=f"{BASE}/messenger/authenticate"),
        pages={"/iserv/messenger/": FakePage(200, html, url=f"{BASE}/iserv/messenger/")},
    )


def test_withheld_credentials_are_their_own_answer_not_the_catch_all_bootstrap_one():
    client = _page_client(WITHOUT_CREDENTIALS)
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert caught.value.stage == STAGE_NO_CREDENTIALS
    assert caught.value.message_key == "api.messenger.error.noCredentials"
    assert caught.value.detail["page_credentials"] == "messenger_authentication is null"


def test_withheld_credentials_stop_the_pointless_calls_that_follow():
    client = _page_client(WITHOUT_CREDENTIALS)
    with pytest.raises(MessengerStageError):
        _service(client)._bootstrap()
    assert not any("authenticate" in path for path in client.fetched_paths)


def test_a_page_that_does_carry_credentials_signs_in_without_any_extra_call():
    client = _page_client(WITH_CREDENTIALS)
    auth = _service(client)._bootstrap()
    assert auth["access_token"].startswith("fixture-access-token")
    assert not any("authenticate" in path for path in client.fetched_paths)


def test_the_withheld_answer_never_carries_a_value_out_of_the_page():
    client = _page_client(WITHOUT_CREDENTIALS)
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    rendered = json.dumps(caught.value.detail)
    assert "fixture-csrf-token" not in rendered
    assert "11111111-1111-1111-1111-111111111111" not in rendered


def test_the_new_stage_is_readable_in_every_language():
    key = MessengerStageError(STAGE_NO_CREDENTIALS).message_key
    for language in messages.LANGUAGES:
        assert messages.text_in(language, key).strip()


def test_the_diagnosis_names_the_permissions_iserv_did_grant():
    from app.iserv.messenger import granted_privileges

    granted = granted_privileges(WITHOUT_CREDENTIALS)
    assert "canWriteToTeacher" in granted
    assert "isParent" in granted
    assert "isStudent" not in granted
    assert granted_privileges("<html><body></body></html>") == "no messenger_user_privileges"


def test_a_withheld_answer_says_whether_iserv_knows_this_account_in_the_messenger_at_all():
    client = _page_client(WITHOUT_CREDENTIALS)
    with pytest.raises(MessengerStageError) as caught:
        _service(client)._bootstrap()
    assert "canWriteToTeacher" in caught.value.detail["page_privileges"]


def test_the_teacher_permission_is_read_from_the_element_iserv_puts_it_in():
    from app.iserv.messenger import parse_privileges

    assert parse_privileges(WITH_CREDENTIALS) == {"can_write_to_teacher": True}
    assert parse_privileges("<html><body></body></html>") is None
