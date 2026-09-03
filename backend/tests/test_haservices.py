import json

import pytest
import requests

from app.haservices import (
    CATEGORY_GROUP,
    CATEGORY_MOBILE,
    CATEGORY_OTHER,
    CATEGORY_PERSISTENT,
    SOURCE_DEVICE_TRACKER,
    SOURCE_ENTITY,
    allowed_service_ids,
    describe_notify_services,
    list_notify_services,
    parse_entity_names,
    parse_notify_services,
    resolve_service_name,
    service_category,
)
from tests.conftest import load_fixture


@pytest.fixture
def catalog():
    return json.loads(load_fixture("ha_services.json"))


@pytest.fixture
def states():
    return json.loads(load_fixture("ha_states.json"))


def test_parse_notify_services_extracts_notify_domain():
    data = [
        {"domain": "notify", "services": {"mobile_app_phone": {}, "persistent_notification": {}}},
        {"domain": "light", "services": {"turn_on": {}}},
    ]
    assert parse_notify_services(data) == ["notify.mobile_app_phone", "notify.persistent_notification"]


def test_parse_notify_services_handles_empty():
    assert parse_notify_services([]) == []
    assert parse_notify_services(None) == []


def test_parse_notify_services_tolerates_a_plain_list_of_service_names():
    data = [{"domain": "notify", "services": ["mobile_app_phone", "notify"]}]
    assert parse_notify_services(data) == ["notify.mobile_app_phone", "notify.notify"]


def test_parse_notify_services_ignores_malformed_entries():
    data = [None, "notify", {"domain": "notify"}, {"domain": "notify", "services": 5}]
    assert parse_notify_services(data) == []


@pytest.mark.parametrize(
    "service,expected",
    [
        ("notify.mobile_app_test_phone", CATEGORY_MOBILE),
        ("notify.persistent_notification", CATEGORY_PERSISTENT),
        ("notify.notify", CATEGORY_GROUP),
        ("notify.custom_webhook", CATEGORY_OTHER),
        ("notify.mobile_app_", CATEGORY_OTHER),
        ("", CATEGORY_OTHER),
    ],
)
def test_service_category_sorts_targets_without_guessing(service, expected):
    assert service_category(service) == expected


def test_parse_entity_names_keeps_only_real_friendly_names(states):
    names = parse_entity_names(states)
    assert names["device_tracker.test_tablet"] == "Test Tablet"
    assert "sensor.without_name" not in names


def test_parse_entity_names_survives_malformed_payloads():
    assert parse_entity_names(None) == {}
    assert parse_entity_names([None, 7, {"entity_id": 1}, {"entity_id": "a.b"}]) == {}
    assert parse_entity_names([{"entity_id": "a.b", "attributes": {"friendly_name": "  "}}]) == {}


def test_resolve_service_name_prefers_the_notify_entity_over_the_device_tracker(states):
    names = parse_entity_names(states)
    assert resolve_service_name("notify.mobile_app_test_phone", names) == ("Test Phone", SOURCE_ENTITY)


def test_resolve_service_name_falls_back_to_the_device_tracker(states):
    names = parse_entity_names(states)
    assert resolve_service_name("notify.mobile_app_test_tablet", names) == (
        "Test Tablet",
        SOURCE_DEVICE_TRACKER,
    )


def test_resolve_service_name_invents_nothing_when_no_entity_matches(states):
    names = parse_entity_names(states)
    assert resolve_service_name("notify.mobile_app_unregistered_device", names) == (None, None)
    assert resolve_service_name("notify.custom_webhook", names) == (None, None)
    assert resolve_service_name("notify.mobile_app_test_phone", {}) == (None, None)


def test_describe_notify_services_enriches_every_target(catalog, states):
    described = describe_notify_services(catalog, parse_entity_names(states))
    by_service = {entry["service"]: entry for entry in described}

    assert by_service["notify.mobile_app_test_phone"] == {
        "service": "notify.mobile_app_test_phone",
        "name": "Test Phone",
        "name_source": SOURCE_ENTITY,
        "category": CATEGORY_MOBILE,
    }
    assert by_service["notify.mobile_app_test_tablet"]["name"] == "Test Tablet"
    assert by_service["notify.mobile_app_test_tablet"]["name_source"] == SOURCE_DEVICE_TRACKER
    assert by_service["notify.mobile_app_unregistered_device"]["name"] is None
    assert by_service["notify.notify"]["category"] == CATEGORY_GROUP
    assert by_service["notify.persistent_notification"]["category"] == CATEGORY_PERSISTENT
    assert by_service["notify.custom_webhook"]["category"] == CATEGORY_OTHER


def test_describe_notify_services_without_states_keeps_the_technical_ids(catalog):
    described = describe_notify_services(catalog, {})
    assert all(entry["name"] is None and entry["name_source"] is None for entry in described)
    assert [entry["service"] for entry in described] == parse_notify_services(catalog)


def test_allowed_service_ids_reads_the_enriched_shape():
    payload = {"supervisor": True, "services": [{"service": "notify.a"}, {"service": "notify.b"}]}
    assert allowed_service_ids(payload) == ["notify.a", "notify.b"]


def test_allowed_service_ids_tolerates_plain_strings_and_junk():
    payload = {"services": ["notify.a", {"service": "notify.b"}, None, 7, {"name": "x"}]}
    assert allowed_service_ids(payload) == ["notify.a", "notify.b"]
    assert allowed_service_ids(None) == []
    assert allowed_service_ids({}) == []


def test_list_notify_services_reports_supervisor_unreachable_without_token(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    assert list_notify_services() == {"supervisor": False, "services": []}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _install_core_api(monkeypatch, catalog, states=None, states_error=None):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if url.endswith("/services"):
            return FakeResponse(catalog)
        if states_error is not None:
            raise states_error
        return FakeResponse(states)

    monkeypatch.setattr("requests.get", fake_get)
    return calls


def test_list_notify_services_enriches_from_the_live_core_api(monkeypatch, catalog, states):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install_core_api(monkeypatch, catalog, states)

    result = list_notify_services()

    assert calls == ["http://supervisor/core/api/services", "http://supervisor/core/api/states"]
    assert result["supervisor"] is True
    names = {entry["service"]: entry["name"] for entry in result["services"]}
    assert names["notify.mobile_app_test_phone"] == "Test Phone"
    assert names["notify.mobile_app_unregistered_device"] is None


def test_list_notify_services_keeps_the_targets_when_states_fails(monkeypatch, catalog):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install_core_api(monkeypatch, catalog, states_error=requests.ConnectionError("boom"))

    result = list_notify_services()

    assert result["supervisor"] is True
    assert [entry["service"] for entry in result["services"]] == parse_notify_services(catalog)
    assert all(entry["name"] is None for entry in result["services"])


def test_list_notify_services_keeps_the_targets_when_states_returns_garbage(monkeypatch, catalog):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install_core_api(monkeypatch, catalog, states={"not": "a list"})

    result = list_notify_services()

    assert result["supervisor"] is True
    assert all(entry["name"] is None for entry in result["services"])


def test_list_notify_services_skips_the_states_call_when_nothing_to_name(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install_core_api(monkeypatch, [{"domain": "light", "services": {"turn_on": {}}}], [])

    assert list_notify_services() == {"supervisor": True, "services": []}
    assert calls == ["http://supervisor/core/api/services"]


def test_list_notify_services_reports_unreachable_when_the_service_catalog_fails(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")

    def fake_get(url, headers=None, timeout=None):
        raise requests.Timeout("slow")

    monkeypatch.setattr("requests.get", fake_get)

    assert list_notify_services() == {"supervisor": False, "services": []}
