import pathlib
import re

import pytest

from app import supervisor

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
GUARD_FILE = APP / "supervisor.py"
ROUTE_FILE = APP / "server.py"

RESTART_PATTERN = re.compile(r"addons/self/restart")
SANCTION_CALL = "restart_addon(requested_by_user=True)"
ROUTE_PATH = '"/api/calendar/restart"'

RESTART_SYMBOL = "restart_addon"
ALLOWED_MODULES = {
    pathlib.Path("supervisor.py"),
    pathlib.Path("server.py"),
}


def test_only_the_supervisor_guard_names_the_restart_endpoint():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path == GUARD_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        for match in RESTART_PATTERN.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(APP)}:{line_no}")
    assert offenders == []


def test_no_module_outside_the_allowlist_can_reach_the_restart_at_all():
    offenders = []
    scanned = 0
    for path in sorted(APP.rglob("*.py")):
        scanned += 1
        relative = path.relative_to(APP)
        if relative in ALLOWED_MODULES:
            continue
        if RESTART_SYMBOL in path.read_text(encoding="utf-8"):
            offenders.append(str(relative))
    assert offenders == [], f"{RESTART_SYMBOL} may only live in {sorted(str(p) for p in ALLOWED_MODULES)}"
    assert scanned > len(ALLOWED_MODULES), "the sweep must cover the whole app package"


def test_the_allowlist_names_only_modules_that_actually_exist_and_use_it():
    for relative in ALLOWED_MODULES:
        path = APP / relative
        assert path.is_file(), f"{relative} is on the allowlist but does not exist"
        assert RESTART_SYMBOL in path.read_text(encoding="utf-8"), (
            f"{relative} is on the allowlist without using {RESTART_SYMBOL}"
        )


def test_the_sweep_would_catch_a_new_module_reaching_for_the_restart(tmp_path, monkeypatch):
    planted = APP / "zz_restart_tripwire_probe.py"
    planted.write_text("from .supervisor import restart_addon\n", encoding="utf-8")
    try:
        offenders = [
            str(path.relative_to(APP))
            for path in sorted(APP.rglob("*.py"))
            if path.relative_to(APP) not in ALLOWED_MODULES
            and RESTART_SYMBOL in path.read_text(encoding="utf-8")
        ]
        assert offenders == ["zz_restart_tripwire_probe.py"]
    finally:
        planted.unlink()


def test_exactly_one_sanctioned_caller_exists_and_it_is_the_user_route():
    text = ROUTE_FILE.read_text(encoding="utf-8")
    assert text.count("restart_addon") == 2
    assert text.count(SANCTION_CALL) == 1
    assert ROUTE_PATH in text
    sanction_at = text.index(SANCTION_CALL)
    route_at = text.index(ROUTE_PATH)
    assert route_at < sanction_at
    assert text.count(SANCTION_CALL) == text.count("requested_by_user=True")


def test_an_unsanctioned_restart_raises_instead_of_restarting(monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(a))
    with pytest.raises(supervisor.AutonomousRestartError):
        supervisor.restart_addon()
    with pytest.raises(supervisor.AutonomousRestartError):
        supervisor.restart_addon(requested_by_user=False)
    assert calls == []


def test_the_sanctioned_restart_answers_before_it_touches_the_supervisor(monkeypatch):
    order = []
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")

    def schedule(token):
        order.append(("scheduled", token))

    result = supervisor.restart_addon(requested_by_user=True, schedule=schedule)
    order.append(("answered", result["ok"]))

    assert order == [("scheduled", "token"), ("answered", True)]
    assert result["restarting"] is True
    assert result["message_key"] == supervisor.RESTART_ACCEPTED_KEY


def test_the_restart_call_survives_the_container_dying_under_it(monkeypatch):
    import requests

    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    posted = []

    def dying_post(url, headers=None, timeout=None):
        posted.append(url)
        raise requests.ConnectionError("container went away mid-call")

    monkeypatch.setattr("requests.post", dying_post)

    supervisor._post_restart("token")

    assert posted == ["http://supervisor/addons/self/restart"]


def test_the_user_gets_a_success_even_though_the_call_will_die(monkeypatch):
    import requests

    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")

    def dying_post(url, headers=None, timeout=None):
        raise requests.ConnectionError("container went away mid-call")

    monkeypatch.setattr("requests.post", dying_post)

    result = supervisor.restart_addon(requested_by_user=True, schedule=supervisor._post_restart)

    assert result["ok"] is True
    assert result["restarting"] is True
    assert result["message_key"] == supervisor.RESTART_ACCEPTED_KEY


def test_a_timeout_on_the_restart_call_is_still_not_a_user_facing_failure(monkeypatch):
    import requests

    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")

    def timing_out_post(url, headers=None, timeout=None):
        raise requests.Timeout("no answer, the add-on is already going down")

    monkeypatch.setattr("requests.post", timing_out_post)

    result = supervisor.restart_addon(requested_by_user=True, schedule=supervisor._post_restart)

    assert result["ok"] is True
    assert result["restarting"] is True


def test_the_real_scheduler_hands_the_call_to_a_daemon_thread(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    started = []

    class FakeTimer:
        def __init__(self, delay, target, args=None):
            self.delay = delay
            self.target = target
            self.args = args or ()
            self.daemon = False

        def start(self):
            started.append((self.delay, self.args, self.daemon))

    import threading

    monkeypatch.setattr(threading, "Timer", FakeTimer)

    supervisor._schedule_restart("token")

    assert started == [(supervisor.RESTART_DELAY_SECONDS, ("token",), True)]


def test_a_restart_without_a_token_is_reported_honestly(monkeypatch):
    calls = []
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(a))

    result = supervisor.restart_addon(requested_by_user=True)

    assert calls == []
    assert result["ok"] is False
    assert result["restarting"] is False
    assert result["message_key"] == supervisor.PORT_UNAVAILABLE_KEY


def test_a_restart_that_cannot_even_be_scheduled_is_reported_honestly(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")

    def refusing_schedule(token):
        raise RuntimeError("cannot start a thread")

    result = supervisor.restart_addon(requested_by_user=True, schedule=refusing_schedule)

    assert result["ok"] is False
    assert result["restarting"] is False
    assert result["message_key"] == supervisor.RESTART_FAILED_KEY
