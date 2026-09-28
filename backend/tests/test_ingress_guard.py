from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.integration_api import INGRESS_ONLY_ENV, INGRESS_PROXY_ADDRESS, IntegrationAccess
from app.server import create_app
from app.subscriptions import SubscriptionRegistry
from tests.test_calendar_feed import FakeHolidayCalendar
from tests.test_integration_api import Clock, FakeService, _auth, _store

OTHER_ADDRESS = "172.30.32.1"
INGRESS = {"X-Ingress-Path": "/api/hassio_ingress/abc"}
APP_ROUTES = ("/api/config", "/api/health", "/api/absences", "/", "/api/integration/info/")


@pytest.fixture(autouse=True)
def _plain_environment(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv(INGRESS_ONLY_ENV, raising=False)
    monkeypatch.setenv("ISERV_ADDON_VERSION", "2609.2.0")


def _app(store, ingress_only=None):
    access = IntegrationAccess(store, clock=Clock(), announce=lambda token: None)
    return create_app(
        FakeService(store),
        holiday_calendar=FakeHolidayCalendar(),
        registry=SubscriptionRegistry(store),
        integration_access=access,
        calendar_warmer=lambda child_id: None,
        ingress_only=ingress_only,
    )


def _client(app, address):
    return TestClient(app, client=(address, 50000))


@pytest.mark.parametrize("path", APP_ROUTES)
def test_the_app_refuses_every_other_address_when_ingress_only(tmp_path, path):
    app = _app(_store(tmp_path), ingress_only=True)

    response = _client(app, OTHER_ADDRESS).get(path, headers=INGRESS)

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"
    assert response.json()["message_key"] == "api.integration.ingressRequired"


def test_the_app_answers_the_ingress_proxy_when_ingress_only(tmp_path):
    app = _app(_store(tmp_path), ingress_only=True)

    response = _client(app, INGRESS_PROXY_ADDRESS).get("/api/config", headers=INGRESS)

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_a_write_from_another_address_changes_nothing(tmp_path):
    store = _store(tmp_path)
    app = _app(store, ingress_only=True)

    response = _client(app, OTHER_ADDRESS).post("/api/config", json={"language": "en"}, headers=INGRESS)

    assert response.status_code == 403
    assert store.load_config()["language"] == "de"


def test_the_token_status_and_rotation_answer_only_the_ingress_proxy(tmp_path):
    store = _store(tmp_path)
    app = _app(store, ingress_only=True)
    token = store.load_integration_token()
    other = _client(app, OTHER_ADDRESS)

    assert other.get("/api/integration-status", headers=INGRESS).status_code == 403
    assert other.post("/api/integration-status/rotate", headers=INGRESS).status_code == 403
    assert token not in other.get("/api/integration-status", headers=INGRESS).text
    assert store.load_integration_token() == token
    assert _client(app, INGRESS_PROXY_ADDRESS).get("/api/integration-status", headers=INGRESS).json()["token"] == token


def test_the_integration_keeps_its_token_check_from_any_address(tmp_path):
    store = _store(tmp_path)
    app = _app(store, ingress_only=True)
    other = _client(app, OTHER_ADDRESS)

    assert other.get("/api/integration/info", headers=_auth(store)).status_code == 200
    assert other.get("/api/integration/info").status_code == 401
    assert other.get("/api/integration/info", headers=dict(_auth(store), **INGRESS)).status_code == 403


def test_without_ingress_only_the_app_answers_as_before(tmp_path):
    app = _app(_store(tmp_path), ingress_only=False)

    assert _client(app, OTHER_ADDRESS).get("/api/config").status_code == 200
    assert TestClient(app).get("/api/config").status_code == 200


@pytest.mark.parametrize(
    ("supervisor_token", "setting", "refused"),
    [(None, None, False), ("token", None, True), ("token", "0", False), (None, "1", True)],
)
def test_the_add_on_mode_comes_from_the_supervisor_token_or_the_setting(
    tmp_path, monkeypatch, supervisor_token, setting, refused
):
    if supervisor_token:
        monkeypatch.setenv("SUPERVISOR_TOKEN", supervisor_token)
    if setting:
        monkeypatch.setenv(INGRESS_ONLY_ENV, setting)
    app = _app(_store(tmp_path))

    assert (_client(app, OTHER_ADDRESS).get("/api/config").status_code == 403) is refused
    assert _client(app, INGRESS_PROXY_ADDRESS).get("/api/config").status_code == 200


SPOOFED_PATHS = (
    "//api/config",
    "/API/config",
    "/api/integration/info/../../config",
    "/api/integration/%2e%2e/config",
    "/docs",
    "/openapi.json",
)
SPOOFED_HEADERS = (
    {"X-Forwarded-For": INGRESS_PROXY_ADDRESS},
    {"Forwarded": f"for={INGRESS_PROXY_ADDRESS}"},
)


@pytest.mark.parametrize("path", SPOOFED_PATHS)
@pytest.mark.parametrize("headers", SPOOFED_HEADERS)
def test_forwarding_headers_and_odd_paths_do_not_pass_as_the_ingress_proxy(tmp_path, path, headers):
    app = ProxyHeadersMiddleware(_app(_store(tmp_path), ingress_only=True), trusted_hosts="127.0.0.1")

    response = TestClient(app, client=(OTHER_ADDRESS, 50000)).get(path, headers={**INGRESS, **headers})

    assert response.status_code == 403


def test_the_add_on_starts_the_server_without_trusting_forwarding_headers():
    command = (Path(__file__).resolve().parents[2] / "iserv_connector" / "run.sh").read_text(encoding="utf-8")

    assert "--no-proxy-headers" in command
    assert "forwarded-allow-ips" not in command


def test_the_app_offers_no_websocket_route_the_guard_would_miss(tmp_path):
    app = _app(_store(tmp_path), ingress_only=True)

    assert [route for route in app.routes if type(route).__name__ == "WebSocketRoute"] == []
