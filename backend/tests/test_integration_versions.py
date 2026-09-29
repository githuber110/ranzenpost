import logging

import pytest
from fastapi.testclient import TestClient

from app import integration, versions
from app.integration_api import INGRESS_PROXY_ADDRESS, IntegrationAccess
from app.server import create_app
from app.subscriptions import SubscriptionRegistry
from tests.test_calendar_feed import FakeHolidayCalendar
from tests.test_integration_api import INGRESS, PREFIX, Clock, FakeService, _app, _auth, _store

APP_VERSION = "2609.4.1"
VERSION = "X-Ranzenpost-Integration"
INSTALLED = "X-Ranzenpost-Integration-Installed"


@pytest.fixture(autouse=True)
def _app_version(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("ISERV_ADDON_VERSION", APP_VERSION)


def _call(client, store, version=None, installed=None):
    headers = dict(_auth(store))
    if version is not None:
        headers[VERSION] = version
    if installed is not None:
        headers[INSTALLED] = installed
    return client.get(PREFIX + "/info", headers=headers)


def _status(client):
    return client.get("/api/integration-status", headers=INGRESS).json()


@pytest.mark.parametrize(
    ("app", "loaded", "installed", "steps"),
    [
        ("2609.4.1", "2609.4.1", "", []),
        ("2609.3.0", "2609.4.0", "", ["app"]),
        ("2609.4.0", "2609.4.1", "", ["app"]),
        ("2609.4.1b1", "2609.4.1", "", ["app"]),
        ("2609.4.1", "2609.4.0", "", ["integration"]),
        ("2609.4.0", "2609.3.0", "", ["integration"]),
        ("2609.4.0", "2609.3.0", "2609.4.0", ["restart"]),
        ("2609.3.0", "2609.3.0", "2609.4.0", ["app", "restart"]),
        ("2609.4.1", "2609.3.0", "2609.4.0", ["integration", "restart"]),
        ("2609.4.0", "2609.4.0", "2609.3.0", []),
        ("", "2609.4.0", "", []),
        ("2609.4.0", "", "", []),
        ("2609.4.0", "garbage", "", []),
        ("2609.04.00", "2609.4.0", "", []),
    ],
)
def test_pending_updates_name_each_side_that_is_behind(app, loaded, installed, steps):
    assert versions.pending_updates(app, loaded, installed) == steps


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("2609.4.1", "2609.4.1"),
        (" 2609.4.1 ", "2609.4.1"),
        ("2609.4.1b2", "2609.4.1b2"),
        ("", ""),
        (None, ""),
        ("latest", ""),
        ("2609.4.1<script>", ""),
        ("2609.4.1" + "0" * 40, ""),
    ],
)
def test_only_a_plain_version_is_kept_from_a_header(given, kept):
    assert versions.clean_version(given) == kept


def test_the_status_names_the_integration_version_the_integration_sent(tmp_path):
    client, store, _ = _app(tmp_path)
    before = _status(client)
    assert before["integration_version"] == ""
    assert before["app_version"] == APP_VERSION
    assert before["updates"] == []

    assert _call(client, store, version=APP_VERSION).status_code == 200

    after = _status(client)
    assert after["integration_version"] == APP_VERSION
    assert after["integration_installed"] == ""
    assert after["updates"] == []


def test_an_app_behind_the_integration_asks_for_the_app_update(tmp_path):
    client, store, _ = _app(tmp_path)
    _call(client, store, version="2609.5.0")

    assert _status(client)["updates"] == ["app"]


def test_an_integration_behind_the_app_asks_for_the_integration_update(tmp_path):
    client, store, _ = _app(tmp_path)
    _call(client, store, version="2609.3.0")

    assert _status(client)["updates"] == ["integration"]


def test_an_integration_installed_but_not_loaded_asks_for_the_restart(tmp_path):
    client, store, _ = _app(tmp_path)
    _call(client, store, version="2609.3.0", installed=APP_VERSION)

    status = _status(client)
    assert status["integration_version"] == "2609.3.0"
    assert status["integration_installed"] == APP_VERSION
    assert status["updates"] == ["restart"]

    _call(client, store, version=APP_VERSION)
    assert _status(client)["updates"] == []


def test_the_seen_version_survives_a_restart_and_is_written_only_when_it_changes(tmp_path, monkeypatch):
    store = _store(tmp_path)
    client, _, _ = _app(tmp_path, store=store)
    writes = []
    original = integration.note_integration
    monkeypatch.setattr(integration, "note_integration", lambda *args: (writes.append(args), original(*args)))

    for _ in range(3):
        _call(client, store, version="2609.3.0")

    assert len(writes) == 1
    client, _, _ = _app(tmp_path, store=store)
    assert _status(client)["integration_version"] == "2609.3.0"


def test_a_call_without_a_valid_token_never_records_a_version(tmp_path):
    client, store, _ = _app(tmp_path)

    refused = client.get(PREFIX + "/info", headers={"Authorization": "Bearer " + "z" * 43, VERSION: "2609.9.0"})

    assert refused.status_code == 401
    assert _status(client)["integration_version"] == ""
    assert integration.seen_integration(store) == ("", "")


def test_a_malformed_version_header_is_ignored(tmp_path):
    client, store, _ = _app(tmp_path)
    _call(client, store, version=APP_VERSION)

    _call(client, store, version="not-a-version")

    assert _status(client)["integration_version"] == APP_VERSION


def test_an_integration_silent_for_a_day_raises_no_update_hint(tmp_path):
    clock = Clock()
    client, store, _ = _app(tmp_path, clock=clock)
    _call(client, store, version="2609.3.0")
    assert _status(client)["updates"] == ["integration"]

    clock.epoch += integration.ACTIVE_WINDOW_SECONDS + 1

    status = _status(client)
    assert status["updates"] == []
    assert status["integration_version"] == "2609.3.0"


def test_a_version_change_is_logged_once(tmp_path, caplog):
    client, store, _ = _app(tmp_path)
    with caplog.at_level(logging.INFO, logger="app.integration_api"):
        _call(client, store, version="2609.3.0")
        _call(client, store, version="2609.3.0")
        _call(client, store, version="2609.4.0", installed="2609.4.1")

    lines = [record.getMessage() for record in caplog.records if "integration reports version" in record.getMessage()]
    assert lines == [
        "the Home Assistant integration reports version 2609.3.0 (was unknown)",
        "the Home Assistant integration reports version 2609.4.0 with 2609.4.1 installed (was 2609.3.0)",
    ]


def test_the_version_header_opens_no_app_route_when_ingress_only(tmp_path):
    store = _store(tmp_path)
    access = IntegrationAccess(store, clock=Clock(), announce=lambda token: None)
    app = create_app(
        FakeService(store),
        holiday_calendar=FakeHolidayCalendar(),
        registry=SubscriptionRegistry(store),
        integration_access=access,
        calendar_warmer=lambda child_id: None,
        ingress_only=True,
    )
    outside = TestClient(app, client=("172.30.32.1", 50000))

    for path in ("/api/config", "/api/health", "/api/integration-status"):
        response = outside.get(path, headers={VERSION: APP_VERSION, INSTALLED: APP_VERSION})
        assert response.status_code == 403, path
    assert outside.get(PREFIX + "/info", headers={VERSION: APP_VERSION}).status_code == 401
    assert outside.get(PREFIX + "/info", headers={**_auth(store), VERSION: APP_VERSION}).status_code == 200
    proxy = TestClient(app, client=(INGRESS_PROXY_ADDRESS, 50000))
    assert proxy.get("/api/integration-status", headers=INGRESS).json()["integration_version"] == APP_VERSION


def test_an_integration_without_a_version_header_predates_the_check_and_needs_its_update(tmp_path, caplog):
    client, store, _ = _app(tmp_path)
    _call(client, store, version="2609.4.1")
    with caplog.at_level(logging.INFO, logger="app.integration_api"):
        _call(client, store)
        _call(client, store)

    status = _status(client)
    assert status["updates"] == ["integration"]
    assert status["integration_version"] == ""
    lines = [record.getMessage() for record in caplog.records if "sends no version" in record.getMessage()]
    assert len(lines) == 1

    _call(client, store, version=APP_VERSION)
    status = _status(client)
    assert status["updates"] == []
    assert status["integration_version"] == APP_VERSION


def test_a_malformed_header_is_not_mistaken_for_an_older_integration(tmp_path):
    client, store, _ = _app(tmp_path)

    _call(client, store, version="not-a-version")

    assert _status(client)["updates"] == []


def test_an_integration_without_a_version_stays_known_across_an_app_restart(tmp_path, monkeypatch):
    store = _store(tmp_path)
    client, _, _ = _app(tmp_path, store=store)
    writes = []
    original = integration.note_unversioned
    monkeypatch.setattr(integration, "note_unversioned", lambda *args: (writes.append(args), original(*args)))

    for _ in range(3):
        _call(client, store)

    assert len(writes) == 1
    client, _, _ = _app(tmp_path, store=store)
    _call(client, store)
    assert _status(client)["updates"] == ["integration"]
    assert len(writes) == 1

    _call(client, store, version=APP_VERSION)
    assert integration.integration_unversioned(store) is False
    client, _, _ = _app(tmp_path, store=store)
    assert _status(client)["updates"] == []


def test_an_update_after_a_call_without_a_version_is_logged_as_new(tmp_path, caplog):
    client, store, _ = _app(tmp_path)
    _call(client, store, version=APP_VERSION)
    _call(client, store)
    with caplog.at_level(logging.INFO, logger="app.integration_api"):
        _call(client, store, version=APP_VERSION)

    lines = [record.getMessage() for record in caplog.records if "integration reports version" in record.getMessage()]
    assert lines == ["the Home Assistant integration reports version %s (was unknown)" % APP_VERSION]


@pytest.mark.parametrize(("app", "steps"), [("2609.4.1", ["integration"]), ("", []), ("garbage", [])])
def test_an_integration_without_a_version_is_older_than_any_known_app(app, steps):
    assert versions.pending_updates(app, "2609.4.1", "2609.4.1", unversioned=True) == steps
