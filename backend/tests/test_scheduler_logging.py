import logging
import threading

import pytest

from app import scheduler
from app.store import Store


class BoomService:
    def is_configured(self):
        raise RuntimeError("boom")


class _StopLoop(Exception):
    pass


def test_poll_cycle_failure_is_logged(caplog, monkeypatch):
    def fake_sleep(_):
        raise _StopLoop

    monkeypatch.setattr(scheduler.time, "sleep", fake_sleep)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    with caplog.at_level(logging.WARNING, logger="app.scheduler"):
        thread = scheduler.start_poller(BoomService(), interval_seconds=0)
        thread.join(timeout=2)
    assert "poll cycle failed" in caplog.text


def test_make_notifier_without_a_target_sends_nothing(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"notify_services": []})

    monkeypatch.setattr(
        scheduler, "notify", lambda *a, **k: pytest.fail("must not push without a target")
    )

    send = scheduler._make_notifier(store)

    assert send("child", "hello") is False


def test_make_notifier_ignores_blank_targets(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"notify_services": ["", None]})

    monkeypatch.setattr(
        scheduler, "notify", lambda *a, **k: pytest.fail("must not push without a target")
    )

    send = scheduler._make_notifier(store)

    assert send("child", "hello") is False


def test_make_notifier_delivers_to_remaining_service_when_one_fails(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"notify_services": ["notify.broken", "notify.works"]})

    sent_to = []

    def fake_notify(message, service=None, title="Ranzenpost"):
        if service == "notify.broken":
            raise RuntimeError("boom")
        sent_to.append(service)
        return True

    monkeypatch.setattr(scheduler, "notify", fake_notify)

    send = scheduler._make_notifier(store)
    result = send("child", "hello")

    assert result is True
    assert sent_to == ["notify.works"]


def test_make_notifier_returns_false_when_all_services_fail(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"notify_services": ["notify.broken"]})

    def fake_notify(message, service=None, title="Ranzenpost"):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler, "notify", fake_notify)

    send = scheduler._make_notifier(store)

    assert send("child", "hello") is False
