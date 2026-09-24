import logging

import pytest
import requests

from app import supervisor

TOKEN = "t" * 43


class FakeResponse:
    def __init__(self, error=None):
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return {"result": "ok"}


class Timers:
    def __init__(self):
        self.scheduled = []

    def __call__(self, delay, function, args=()):
        self.scheduled.append((delay, function, args))

    def fire(self):
        pending = list(self.scheduled)
        self.scheduled.clear()
        for _, function, args in pending:
            function(*args)


def _install(monkeypatch, info=None, post=None):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, None))
        if isinstance(info, Exception):
            raise info
        response = FakeResponse()
        response.json = lambda: info if info is not None else {"data": {"hostname": "local-ranzenpost"}}
        return response

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, json))
        outcome = post.pop(0) if isinstance(post, list) else post
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return calls


def _posts(calls):
    return [entry for entry in calls if entry[0] == "POST"]


def test_the_announcement_posts_the_service_the_host_the_port_and_the_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch)
    timers = Timers()

    done = supervisor.announce_discovery(TOKEN, schedule=timers)

    assert done is True
    assert _posts(calls) == [
        (
            "POST",
            "http://supervisor/discovery",
            {
                "service": supervisor.DISCOVERY_SERVICE,
                "config": {"host": "local-ranzenpost", "port": 8099, "token": TOKEN},
            },
        )
    ]
    assert timers.scheduled == []


def test_the_announcement_carries_the_supervisor_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        response = FakeResponse()
        response.json = lambda: {"data": {"hostname": "local-ranzenpost"}}
        return response

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["headers"] = headers
        seen["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)

    supervisor.announce_discovery(TOKEN, schedule=Timers())

    assert seen["headers"] == {"Authorization": "Bearer supervisor-token"}
    assert seen["timeout"] == supervisor.REQUEST_TIMEOUT


def test_without_a_supervisor_token_nothing_is_called_and_nothing_is_logged(monkeypatch, caplog):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("no supervisor call may happen without a token")

    monkeypatch.setattr("requests.get", forbidden)
    monkeypatch.setattr("requests.post", forbidden)

    with caplog.at_level(logging.INFO, logger="app.supervisor"):
        done = supervisor.announce_discovery(TOKEN, schedule=Timers())

    assert done is None
    assert caplog.records == []


def test_a_failed_announcement_logs_one_line_and_retries_after_a_minute(monkeypatch, caplog):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, post=[requests.ConnectionError("down"), None])
    timers = Timers()

    with caplog.at_level(logging.WARNING, logger="app.supervisor"):
        done = supervisor.announce_discovery(TOKEN, schedule=timers)

    assert done is False
    assert len([record for record in caplog.records if record.levelno == logging.WARNING]) == 1
    assert [delay for delay, _, _ in timers.scheduled] == [supervisor.DISCOVERY_RETRY_SECONDS]

    timers.fire()

    assert len(_posts(calls)) == 2
    assert timers.scheduled == []


def test_the_retries_stop_after_five_attempts(monkeypatch, caplog):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, post=requests.ConnectionError("down"))
    timers = Timers()

    with caplog.at_level(logging.WARNING, logger="app.supervisor"):
        supervisor.announce_discovery(TOKEN, schedule=timers)
        for _ in range(10):
            timers.fire()

    assert len(_posts(calls)) == supervisor.DISCOVERY_MAX_ATTEMPTS
    assert timers.scheduled == []
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == supervisor.DISCOVERY_MAX_ATTEMPTS


def test_a_retry_gives_up_when_the_token_was_rotated_in_the_meantime(monkeypatch, caplog):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, post=[requests.ConnectionError("down"), None, None])
    timers = Timers()
    rotated = "r" * 43

    supervisor.announce_discovery(TOKEN, schedule=timers)
    assert len(timers.scheduled) == 1
    assert supervisor.announce_discovery(rotated, schedule=timers) is True
    with caplog.at_level(logging.INFO, logger="app.supervisor"):
        timers.fire()

    assert [post[2]["config"]["token"] for post in _posts(calls)] == [TOKEN, rotated]
    assert timers.scheduled == []
    assert any("rotated" in record.getMessage() for record in caplog.records)


def test_a_retry_still_runs_when_the_token_is_unchanged(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, post=[requests.ConnectionError("down"), None])
    timers = Timers()

    supervisor.announce_discovery(TOKEN, schedule=timers)
    timers.fire()

    assert [post[2]["config"]["token"] for post in _posts(calls)] == [TOKEN, TOKEN]


def test_a_rejected_announcement_counts_as_a_failure(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    _install(monkeypatch, post=[requests.HTTPError("400"), None])
    timers = Timers()

    assert supervisor.announce_discovery(TOKEN, schedule=timers) is False
    assert len(timers.scheduled) == 1


def test_a_missing_hostname_falls_back_to_the_slug_based_name(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, info={"data": {"slug": "abc123_ranzenpost"}})

    supervisor.announce_discovery(TOKEN, schedule=Timers())

    assert _posts(calls)[0][2]["config"]["host"] == "abc123-ranzenpost"


def test_an_unreachable_addon_info_still_tries_to_announce_with_the_default_host(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    calls = _install(monkeypatch, info=requests.Timeout("slow"))

    supervisor.announce_discovery(TOKEN, schedule=Timers())

    assert _posts(calls)[0][2]["config"]["host"] == supervisor.DISCOVERY_FALLBACK_HOST


def test_the_real_scheduler_uses_a_daemon_timer(monkeypatch):
    created = []

    class FakeTimer:
        def __init__(self, delay, function, args=()):
            self.delay = delay
            self.function = function
            self.args = args
            self.daemon = False
            created.append(self)

        def start(self):
            pass

    monkeypatch.setattr("threading.Timer", FakeTimer)

    supervisor._schedule_later(60, lambda: None)

    assert created[0].daemon is True
    assert created[0].delay == 60


def test_the_config_declares_the_service_name_the_announcement_uses():
    from pathlib import Path

    config = (Path(__file__).resolve().parents[2] / "iserv_connector" / "config.yaml").read_text(encoding="utf-8")

    assert f"discovery: [{supervisor.DISCOVERY_SERVICE}]" in config


@pytest.mark.parametrize("value,expected", [
    ({"data": {"hostname": "local-ranzenpost"}}, "local-ranzenpost"),
    ({"hostname": "a0d7b954-ranzenpost"}, "a0d7b954-ranzenpost"),
    ({"data": {"slug": "local_ranzenpost"}}, "local-ranzenpost"),
    ({"data": {}}, supervisor.DISCOVERY_FALLBACK_HOST),
    (None, supervisor.DISCOVERY_FALLBACK_HOST),
])
def test_discovery_host_prefers_the_hostname_then_the_slug(value, expected):
    assert supervisor.discovery_host(value) == expected
