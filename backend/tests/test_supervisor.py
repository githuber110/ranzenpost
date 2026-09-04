import pytest
import requests
from fastapi.testclient import TestClient

from app import supervisor
from app.server import create_app
from app.store import Store
from app.subscriptions import SubscriptionRegistry
from app.supervisor import (
    CONTAINER_PORT_KEY,
    DEFAULT_HOST,
    FEED_PORT,
    HOST_SOURCE_EXTERNAL,
    HOST_SOURCE_FALLBACK,
    HOST_SOURCE_INTERNAL,
    PORT_ALREADY_OPEN_KEY,
    PORT_FAILED_KEY,
    PORT_OPENED_KEY,
    PORT_UNAVAILABLE_KEY,
    calendar_access,
    feed_port_open,
    feed_port_state,
    host_state,
    is_remote_ui_host,
    mapped_feed_port,
    open_feed_port,
    resolve_host,
    sanitize_host,
)

CHILD_ID = "child-uuid-a"
CHILD_NAME = "Zwiebelfisch Quastenflosser"


class FakeResponse:
    def __init__(self, payload, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _install(monkeypatch, core=None, info=None, options=None):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, None))
        if url.endswith("/core/api/config"):
            if isinstance(core, Exception):
                raise core
            return FakeResponse(core)
        if url.endswith("/addons/self/info"):
            if isinstance(info, Exception):
                raise info
            return FakeResponse(info)
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, json))
        if isinstance(options, Exception):
            raise options
        return FakeResponse(options if options is not None else {"result": "ok"})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return calls


def _no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no supervisor call may happen without a token")

    monkeypatch.setattr("requests.get", forbidden)
    monkeypatch.setattr("requests.post", forbidden)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10.10.2.2:8123", "10.10.2.2"),
        ("http://homeassistant.local:8123/lovelace", "homeassistant.local"),
        ("https://ha.example.test/", "ha.example.test"),
        ("webcal://ha.example.test:8100/calendar/abc.ics", "ha.example.test"),
        ("  homeassistant.local  ", "homeassistant.local"),
        ("homeassistant.local.", "homeassistant.local"),
        ("http://homeassistant.local./", "homeassistant.local"),
        ("HTTP://HomeAssistant.Local:8123", "homeassistant.local"),
        ("[fd00::1]:8123", "fd00::1"),
        ("[fd00::1]", "fd00::1"),
        ("http://[fd00::1]:8123/lovelace", "fd00::1"),
        ("fd00::1", "fd00::1"),
        ("//homeassistant.local:8123", "homeassistant.local"),
        ("http://user:secret@ha.example.test:8123/x", "ha.example.test"),
        ("10.10.2.2", "10.10.2.2"),
        ("ha.example.test?x=1", "ha.example.test"),
        ("ha.example.test#frag", "ha.example.test"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("http://", ""),
        ("://", ""),
        (":8123", ""),
        ("/lovelace", ""),
        ("[fd00::1", ""),
        ("ha example.test", ""),
        (12345, "12345"),
    ],
)
def test_sanitize_host_reduces_every_input_to_a_bare_host(value, expected):
    assert sanitize_host(value) == expected


def test_sanitize_host_fixes_the_regression_that_killed_the_calendar_link():
    typed = "10.10.2.2:8123"
    host = sanitize_host(typed)
    assert host == "10.10.2.2"
    assert f"webcal://{host}:{FEED_PORT}/calendar/token.ics" == "webcal://10.10.2.2:8100/calendar/token.ics"


def test_sanitize_host_never_leaves_a_scheme_or_a_port_behind():
    for value in ("http://a.test:1/b", "webcal://a.test:2", "https://a.test:3?q=1"):
        host = sanitize_host(value)
        assert "://" not in host and ":" not in host and "/" not in host


@pytest.mark.parametrize(
    "host,expected",
    [
        ("abcdef.ui.nabu.casa", True),
        ("nabu.casa", True),
        ("NABU.CASA", True),
        ("abcdef.ui.nabu.casa.", True),
        ("homeassistant.local", False),
        ("nabu.casa.example.test", False),
        ("mynabu.casa", False),
        ("", False),
        (None, False),
    ],
)
def test_is_remote_ui_host_only_flags_the_nabu_casa_domain(host, expected):
    assert is_remote_ui_host(host) is expected


def test_resolve_host_prefers_the_internal_url(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, core={"internal_url": "http://homeassistant.local:8123"})

    assert resolve_host() == "homeassistant.local"
    assert calls == [("GET", "http://supervisor/core/api/config", None)]
    assert host_state()["host_source"] == HOST_SOURCE_INTERNAL


def test_resolve_host_accepts_an_internal_url_without_a_port(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"internal_url": "http://10.10.2.2"})

    assert resolve_host() == "10.10.2.2"


def test_resolve_host_unwraps_a_bracketed_ipv6_internal_url(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"internal_url": "http://[fd00::1]:8123"})

    assert resolve_host() == "fd00::1"


def test_resolve_host_uses_the_external_url_only_as_a_second_choice(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"internal_url": "", "external_url": "https://ha.example.test:8123"})

    state = host_state()
    assert state == {"host": "ha.example.test", "host_source": HOST_SOURCE_EXTERNAL}


def test_resolve_host_never_hands_out_a_nabu_casa_address(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(
        monkeypatch,
        core={"internal_url": None, "external_url": "https://abcdef123456.ui.nabu.casa"},
    )

    state = host_state()
    assert state == {"host": DEFAULT_HOST, "host_source": HOST_SOURCE_FALLBACK}
    assert "nabu.casa" not in state["host"]


def test_resolve_host_rejects_a_nabu_casa_internal_url_too(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"internal_url": "https://abcdef.ui.nabu.casa"})

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_falls_back_when_the_config_names_no_url(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"location_name": "Home"})

    assert host_state() == {"host": DEFAULT_HOST, "host_source": HOST_SOURCE_FALLBACK}


def test_resolve_host_falls_back_on_an_unparseable_internal_url(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core={"internal_url": "http://"})

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_falls_back_without_a_token(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)

    assert host_state() == {"host": DEFAULT_HOST, "host_source": HOST_SOURCE_FALLBACK}


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError("boom"),
        requests.Timeout("slow"),
        requests.HTTPError("500"),
    ],
)
def test_resolve_host_swallows_every_transport_failure(monkeypatch, failure):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core=failure)

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_survives_a_non_200_answer(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(None, error=requests.HTTPError("401"))

    monkeypatch.setattr("requests.get", fake_get)

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_survives_a_body_that_is_not_json(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(ValueError("not json"))

    monkeypatch.setattr("requests.get", fake_get)

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_survives_a_json_body_that_is_not_an_object(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, core=["not", "a", "mapping"])

    assert resolve_host() == DEFAULT_HOST


def test_resolve_host_sends_the_supervisor_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["headers"] = headers
        seen["timeout"] = timeout
        return FakeResponse({"internal_url": "http://ha.example.test:8123"})

    monkeypatch.setattr("requests.get", fake_get)

    assert resolve_host() == "ha.example.test"
    assert seen["headers"] == {"Authorization": "Bearer test-token"}
    assert seen["timeout"] == supervisor.REQUEST_TIMEOUT


@pytest.mark.parametrize(
    "info,expected",
    [
        ({"network": {CONTAINER_PORT_KEY: 8100}}, 8100),
        ({"network": {CONTAINER_PORT_KEY: "8100"}}, 8100),
        ({"network": {CONTAINER_PORT_KEY: None}}, 0),
        ({"network": {CONTAINER_PORT_KEY: True}}, 0),
        ({"network": {CONTAINER_PORT_KEY: 0}}, 0),
        ({"network": {CONTAINER_PORT_KEY: "nope"}}, 0),
        ({"network": {"8099/tcp": 8099}}, 0),
        ({"network": None}, 0),
        ({}, 0),
        (None, 0),
    ],
)
def test_mapped_feed_port_reads_only_the_declared_container_port(info, expected):
    assert mapped_feed_port(info) == expected


def test_feed_port_state_reports_an_already_open_port(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info={"result": "ok", "data": {"network": {CONTAINER_PORT_KEY: 8100}}})

    assert feed_port_state() == {"supervisor": True, "port_open": True, "mapped_port": 8100}
    assert feed_port_open() is True


def test_feed_port_state_reads_an_answer_without_the_supervisor_envelope(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info={"network": {CONTAINER_PORT_KEY: 8100}})

    assert feed_port_state()["port_open"] is True


def test_feed_port_state_reports_a_closed_port(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info={"result": "ok", "data": {"network": {CONTAINER_PORT_KEY: None}}})

    assert feed_port_state() == {"supervisor": True, "port_open": False, "mapped_port": 0}
    assert feed_port_open() is False


def test_feed_port_state_admits_it_cannot_see_the_supervisor(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info=requests.ConnectionError("boom"))

    assert feed_port_state() == {"supervisor": False, "port_open": False, "mapped_port": 0}


def test_feed_port_state_without_a_token_makes_no_call(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)

    assert feed_port_state() == {"supervisor": False, "port_open": False, "mapped_port": 0}


def test_open_feed_port_maps_the_declared_port_and_asks_for_a_restart(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, info={"data": {"network": {CONTAINER_PORT_KEY: None}}})

    result = open_feed_port()

    assert result["ok"] is True
    assert result["message_key"] == PORT_OPENED_KEY
    assert result["port_open"] is True
    assert result["restart_required"] is True
    assert calls[-1] == (
        "POST",
        "http://supervisor/addons/self/options",
        {"network": {CONTAINER_PORT_KEY: FEED_PORT}},
    )


def test_open_feed_port_never_restarts_the_addon_itself(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, info={"data": {"network": {CONTAINER_PORT_KEY: None}}})

    open_feed_port()

    assert [url for _, url, _ in calls if url.endswith("/restart")] == []


def test_open_feed_port_is_idempotent_when_the_port_is_already_mapped(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, info={"data": {"network": {CONTAINER_PORT_KEY: 8100}}})

    result = open_feed_port()

    assert result["ok"] is True
    assert result["message_key"] == PORT_ALREADY_OPEN_KEY
    assert result["port_open"] is True
    assert result["restart_required"] is False
    assert [method for method, _, _ in calls] == ["GET"]


def test_open_feed_port_reports_an_unreachable_supervisor(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info=requests.Timeout("slow"))

    result = open_feed_port()

    assert result["ok"] is False
    assert result["message_key"] == PORT_UNAVAILABLE_KEY
    assert result["port_open"] is False
    assert result["restart_required"] is False


def test_open_feed_port_reports_a_missing_token_without_calling_out(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)

    result = open_feed_port()

    assert result["ok"] is False
    assert result["message_key"] == PORT_UNAVAILABLE_KEY
    assert result["restart_required"] is False


def test_open_feed_port_reports_a_rejected_write(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(
        monkeypatch,
        info={"data": {"network": {CONTAINER_PORT_KEY: None}}},
        options=requests.HTTPError("403"),
    )

    result = open_feed_port()

    assert result["ok"] is False
    assert result["message_key"] == PORT_FAILED_KEY
    assert result["port_open"] is False
    assert result["restart_required"] is False


def test_open_feed_port_reports_a_non_200_from_the_options_call(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    def fake_get(url, headers=None, timeout=None):
        return FakeResponse({"data": {"network": {CONTAINER_PORT_KEY: None}}})

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(None, error=requests.HTTPError("400"))

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)

    assert open_feed_port()["message_key"] == PORT_FAILED_KEY


def test_calendar_access_merges_the_host_and_the_port_state(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(
        monkeypatch,
        core={"internal_url": "http://10.10.2.2:8123"},
        info={"data": {"network": {CONTAINER_PORT_KEY: 8100}}},
    )

    assert calendar_access() == {
        "host": "10.10.2.2",
        "host_source": HOST_SOURCE_INTERNAL,
        "supervisor": True,
        "port_open": True,
        "mapped_port": 8100,
        "restart_pending": False,
    }


class FakeService:
    def __init__(self, store):
        self.store = store

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def children(self):
        return [{"child_id": CHILD_ID, "name": CHILD_NAME}]


def _api(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["holiday_region"] = "DE-NI"
    config["children"] = [{"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"}]
    store.save_config(config)
    registry = SubscriptionRegistry(store)
    return TestClient(create_app(FakeService(store), registry=registry)), store


def test_the_subscription_listing_carries_the_resolved_host_and_the_port_state(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(
        monkeypatch,
        core={"internal_url": "http://10.10.2.2:8123"},
        info={"data": {"network": {CONTAINER_PORT_KEY: None}}},
    )
    client, _ = _api(tmp_path)

    body = client.get("/api/calendar/subscriptions").json()

    assert body["host"] == "10.10.2.2"
    assert body["host_source"] == HOST_SOURCE_INTERNAL
    assert body["port_open"] is False
    assert body["supervisor"] is True
    assert body["port"] == FEED_PORT
    assert body["path_template"] == "/calendar/{token}.ics"
    assert body["subscriptions"] == []
    assert body["holiday_region"] == "DE-NI"
    assert body["components"]


def test_the_subscription_listing_still_answers_without_a_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)
    client, _ = _api(tmp_path)

    body = client.get("/api/calendar/subscriptions").json()

    assert body["host"] == DEFAULT_HOST
    assert body["host_source"] == HOST_SOURCE_FALLBACK
    assert body["supervisor"] is False
    assert body["port_open"] is False
    assert body["port"] == FEED_PORT


def test_the_port_route_opens_the_feed_port_on_demand(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, info={"data": {"network": {CONTAINER_PORT_KEY: None}}})
    client, _ = _api(tmp_path)

    body = client.post("/api/calendar/port").json()

    assert body["ok"] is True
    assert body["message_key"] == PORT_OPENED_KEY
    assert body["restart_required"] is True
    assert body["port_open"] is True
    assert calls[-1][1] == "http://supervisor/addons/self/options"


def test_the_port_route_answers_honestly_without_a_supervisor(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)
    client, _ = _api(tmp_path)

    body = client.post("/api/calendar/port").json()

    assert body["ok"] is False
    assert body["message_key"] == PORT_UNAVAILABLE_KEY
    assert body["restart_required"] is False


def test_the_container_port_key_matches_the_declaration_in_the_addon_config():
    from pathlib import Path

    config = (
        Path(__file__).resolve().parents[2] / "iserv_connector" / "config.yaml"
    ).read_text(encoding="utf-8")

    assert f"{CONTAINER_PORT_KEY}:" in config, (
        "a port must be declared in config.yaml before the supervisor can map it"
    )


class PendingStore:
    def __init__(self, config=None):
        self._config = dict(config or {})
        self.saves = 0

    def load_config(self):
        return dict(self._config)

    def save_config(self, config):
        self._config = dict(config)
        self.saves += 1


def test_opening_the_port_persists_the_pending_restart(monkeypatch):
    store = PendingStore()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"network": {"8100/tcp": None}})

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr("requests.post", lambda *a, **k: Response())

    result = supervisor.open_feed_port(store=store)

    assert result["ok"] is True
    assert result["restart_required"] is True
    assert supervisor.restart_pending(store) is True


def test_the_pending_restart_survives_a_closed_and_reopened_sheet(monkeypatch):
    store = PendingStore({supervisor.RESTART_PENDING_KEY: True})
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"network": {"8100/tcp": 8100}})

    access = supervisor.calendar_access(store=store)

    assert access["port_open"] is True
    assert access["restart_pending"] is True


def test_a_second_port_call_after_the_write_still_reports_the_pending_restart(monkeypatch):
    store = PendingStore({supervisor.RESTART_PENDING_KEY: True})
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"network": {"8100/tcp": 8100}})

    result = supervisor.open_feed_port(store=store)

    assert result["ok"] is True
    assert result["restart_required"] is True


def test_the_boot_clears_the_pending_restart_because_the_mapping_is_live(monkeypatch):
    store = PendingStore({supervisor.RESTART_PENDING_KEY: True})

    supervisor.clear_restart_pending(store)

    assert supervisor.restart_pending(store) is False
    assert supervisor.RESTART_PENDING_KEY not in store.load_config()


def test_clearing_an_already_clean_state_writes_nothing():
    store = PendingStore()

    supervisor.clear_restart_pending(store)

    assert store.saves == 0


def test_a_failed_port_write_never_arms_the_restart(monkeypatch):
    import requests

    store = PendingStore()
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"network": {"8100/tcp": None}})

    def refusing_post(*args, **kwargs):
        raise requests.RequestException("nope")

    monkeypatch.setattr("requests.post", refusing_post)

    result = supervisor.open_feed_port(store=store)

    assert result["ok"] is False
    assert supervisor.restart_pending(store) is False


def test_calendar_access_without_a_store_reports_no_pending_restart():
    assert supervisor.calendar_access(store=None)["restart_pending"] is False
