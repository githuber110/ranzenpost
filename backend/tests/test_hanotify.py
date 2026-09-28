import pytest

from app import hanotify, haservices


@pytest.fixture(autouse=True)
def supervisor_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")


def test_is_valid_service_format_accepts_domain_dot_name():
    assert hanotify.is_valid_service_format("notify.mobile_app_phone") is True
    assert hanotify.is_valid_service_format("persistent_notification.create") is True


@pytest.mark.parametrize(
    "service",
    [
        "",
        None,
        "notify",
        "notify.",
        ".create",
        "notify..create",
        "notify.mobile_app/../secrets",
        "notify.mobile app",
        "Notify.Mobile",
        "notify.mobile_app.extra",
        "../../etc/passwd",
    ],
)
def test_is_valid_service_format_rejects_malformed_or_traversal_input(service):
    assert hanotify.is_valid_service_format(service) is False


def test_notify_without_token_does_nothing(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert hanotify.notify("hi") is False


def test_notify_rejects_malformed_service(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append((a, k)))

    assert hanotify.notify("hi", service="../../secrets") is False
    assert calls == []


def test_notify_without_a_target_sends_nothing(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(
        haservices, "list_notify_services", lambda: pytest.fail("must not be called")
    )

    assert hanotify.notify("hi") is False
    assert hanotify.notify("hi", service="") is False
    assert hanotify.notify("hi", service=None) is False
    assert calls == []


def test_notify_allows_service_present_in_allowlist(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": True, "services": ["notify.mobile_app_phone"]},
    )

    assert hanotify.notify("hi", service="notify.mobile_app_phone") is True
    assert calls == ["http://supervisor/core/api/services/notify/mobile_app_phone"]


def test_notify_rejects_service_absent_from_allowlist_when_supervisor_reachable(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": True, "services": ["notify.mobile_app_phone"]},
    )

    assert hanotify.notify("hi", service="notify.unknown_device") is False
    assert calls == []


def test_notify_falls_back_to_format_check_when_supervisor_unreachable(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": False, "services": []},
    )

    assert hanotify.notify("hi", service="notify.mobile_app_phone") is True
    assert calls == ["http://supervisor/core/api/services/notify/mobile_app_phone"]


@pytest.mark.parametrize("service", ["light.turn_on", "homeassistant.restart", "persistent_notification.create"])
def test_notify_refuses_other_domains_when_supervisor_unreachable(monkeypatch, service):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": False, "services": []},
    )

    assert hanotify.notify("hi", service=service) is False
    assert calls == []


def test_notify_refuses_other_domains_even_when_listed(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": True, "services": ["light.turn_on"]},
    )

    assert hanotify.notify("hi", service="light.turn_on") is False
    assert calls == []


def test_notify_service_list_keeps_only_notify_services():
    values = ["notify.phone", " notify.tablet ", "light.turn_on", "notify.phone", 7, None, "notify.", "../x"]
    assert hanotify.notify_service_list(values) == ["notify.phone", "notify.tablet"]
    assert hanotify.notify_service_list("notify.phone") == []
    assert hanotify.notify_service_list(None) == []


def test_notify_allows_a_service_from_the_enriched_allowlist(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {
            "supervisor": True,
            "services": [
                {
                    "service": "notify.mobile_app_phone",
                    "name": "Test Phone",
                    "name_source": "entity",
                    "category": "mobile",
                }
            ],
        },
    )

    assert hanotify.notify("hi", service="notify.mobile_app_phone") is True
    assert calls == ["http://supervisor/core/api/services/notify/mobile_app_phone"]


def test_notify_rejects_a_foreign_service_against_the_enriched_allowlist(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {
            "supervisor": True,
            "services": [
                {
                    "service": "notify.mobile_app_phone",
                    "name": "Test Phone",
                    "name_source": "entity",
                    "category": "mobile",
                }
            ],
        },
    )

    assert hanotify.notify("hi", service="notify.unknown_device") is False
    assert calls == []


def test_notify_does_not_confuse_the_display_name_with_the_service_id(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {
            "supervisor": True,
            "services": [
                {
                    "service": "notify.mobile_app_phone",
                    "name": "notify.mobile_app_other",
                    "name_source": "entity",
                    "category": "mobile",
                }
            ],
        },
    )

    assert hanotify.notify("hi", service="notify.mobile_app_other") is False
    assert calls == []


def test_notify_quotes_service_segments(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda url, **k: calls.append(url))
    monkeypatch.setattr(
        "app.haservices.list_notify_services",
        lambda: {"supervisor": True, "services": ["notify.a_b"]},
    )

    hanotify.notify("hi", service="notify.a_b")
    assert "%2F" not in calls[0]
    assert calls[0] == "http://supervisor/core/api/services/notify/a_b"
