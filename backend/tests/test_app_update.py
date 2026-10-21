import pytest
import requests

from app import app_update, diagnostics, supervisor
from tests.test_diagnostics import build, two_school_service
from tests.test_integration_api import INGRESS, _app
from tests.test_supervisor import _install, _no_network

APP = "2610.3.0"
LATEST = "2610.4.0"


@pytest.fixture(autouse=True)
def _fresh_check():
    app_update.CHECK.forget()
    yield
    app_update.CHECK.forget()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize(
    ("info", "state", "latest"),
    [
        ({"version": APP, "latest": LATEST, "slug": "abc_ranzenpost"}, "newer", LATEST),
        ({"version": LATEST, "latest": LATEST, "slug": "abc_ranzenpost"}, "current", ""),
        ({"version": LATEST, "latest": APP, "slug": "abc_ranzenpost"}, "current", ""),
        ({"version": APP, "latest": "", "slug": "abc_ranzenpost"}, "unknown", ""),
        ({"version": "", "latest": LATEST, "slug": "abc_ranzenpost"}, "unknown", ""),
        ({"version": APP, "latest": "latest<script>", "slug": "abc_ranzenpost"}, "unknown", ""),
        (None, "unknown", ""),
        ("garbage", "unknown", ""),
    ],
)
def test_only_two_readable_versions_decide_whether_a_newer_app_exists(info, state, latest):
    result = app_update.evaluate(info)
    assert result["state"] == state
    assert result["latest"] == latest


def test_without_a_supervisor_the_check_is_unknown_and_never_calls_out(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)

    assert app_update.status() == {"state": "unknown", "latest": "", "slug": ""}


def test_the_supervisor_names_the_newer_app_version(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    calls = _install(monkeypatch, info={"data": {"slug": "abc_ranzenpost", "version": APP, "version_latest": LATEST}})

    assert app_update.status() == {"state": "newer", "latest": LATEST, "slug": "abc_ranzenpost"}
    assert [url for _, url, _ in calls] == ["http://supervisor/addons/self/info"]


@pytest.mark.parametrize("failure", [requests.ConnectionError("down"), requests.HTTPError("500"), ValueError("not json")])
def test_a_supervisor_that_answers_badly_leaves_the_check_unknown(monkeypatch, failure):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    _install(monkeypatch, info=failure)

    assert app_update.status()["state"] == "unknown"


def test_a_crashing_check_is_unknown_and_not_up_to_date():
    def broken():
        raise RuntimeError("boom")

    assert app_update.AppUpdateCheck(fetch=broken).status()["state"] == "unknown"


def test_the_answer_is_kept_for_an_hour_and_a_failure_retried_sooner():
    clock = Clock()
    answers = [None, {"version": APP, "latest": LATEST}, {"version": LATEST, "latest": LATEST}]
    calls = []

    def fetch():
        calls.append(True)
        return answers[len(calls) - 1]

    check = app_update.AppUpdateCheck(fetch=fetch, clock=clock)
    assert check.status()["state"] == "unknown"
    clock.now += app_update.RETRY_SECONDS - 1
    assert check.status()["state"] == "unknown"
    assert len(calls) == 1
    clock.now += 2
    assert check.status()["state"] == "newer"
    clock.now += app_update.CACHE_SECONDS - 1
    assert check.status()["state"] == "newer"
    assert len(calls) == 2
    clock.now += 2
    assert check.status()["state"] == "current"
    assert len(calls) == 3


def test_the_status_route_tells_the_app_about_a_newer_version(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "self_update_info", lambda: {"version": APP, "latest": LATEST, "slug": "abc_ranzenpost"})
    client, _, _ = _app(tmp_path)

    body = client.get("/api/integration-status", headers=INGRESS).json()

    assert body["app_update"] == {"state": "newer", "latest": LATEST, "slug": "abc_ranzenpost"}


def test_the_status_route_without_a_supervisor_says_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    client, _, _ = _app(tmp_path)

    assert client.get("/api/integration-status", headers=INGRESS).json()["app_update"]["state"] == "unknown"


@pytest.mark.parametrize(
    ("result", "line"),
    [
        ({"state": "newer", "latest": LATEST, "slug": "abc_ranzenpost"}, "- Newer app available: " + LATEST),
        ({"state": "current", "latest": "", "slug": "abc_ranzenpost"}, "- App update check: up to date"),
        ({"state": "unknown", "latest": "", "slug": ""}, "- App update check: unknown"),
    ],
)
def test_the_report_header_names_the_app_update_state(tmp_path, result, line):
    service, _first, _second = two_school_service(tmp_path)

    report = build(service, versions={"app": APP, "home_assistant": "2026.9.1", "app_update": result}, structure=False)

    lines = report.splitlines()
    assert lines[lines.index("- Home Assistant: 2026.9.1") - 1] == line


def test_the_report_without_a_supervisor_says_the_check_is_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    _no_network(monkeypatch)
    service, _first, _second = two_school_service(tmp_path)

    report = diagnostics.build_report(service, structure=False, clock=lambda: 1_788_000_000, versions={"app": APP, "home_assistant": "x"})

    assert "- App update check: unknown" in report.splitlines()
    assert "up to date" not in report
