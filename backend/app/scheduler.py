import logging
import os
import threading
import time

from .hanotify import notify
from .poller import Poller

logger = logging.getLogger(__name__)


def _make_notifier(store, event="timetable"):
    def send(name, message):
        config = store.load_config()
        if not config.get("notify_events", {}).get(event, True):
            return False
        services = [value for value in (config.get("notify_services") or []) if value]
        if not services:
            logger.info("no notification target configured, %s push skipped", event)
            return False
        sent_any = False
        for service in services:
            try:
                if notify(message, service=service):
                    sent_any = True
            except Exception:
                logger.warning("notify to %s failed", service, exc_info=True)
        return sent_any

    return send


NOTIFY_EVENTS = ("timetable", "letters", "pinboard", "conferences", "auth", "messenger", "outage")
DEFAULT_INTERVAL_SECONDS = 1800
INTERVAL_ENV = "ISERV_POLL_INTERVAL"


def poll_interval_from_env():
    try:
        return max(60, int(os.environ.get(INTERVAL_ENV, DEFAULT_INTERVAL_SECONDS)))
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


def notifiers_for(store):
    return {event: _make_notifier(store, event) for event in NOTIFY_EVENTS}


def make_poller(service, interval_seconds=1800, registry=None, holiday_calendar=None):
    return Poller(
        service,
        notifier=_make_notifier(service.store),
        notifiers=notifiers_for(service.store),
        registry=registry,
        holiday_calendar=holiday_calendar,
        poll_interval=interval_seconds,
    )


def start_poller(service, interval_seconds=1800, registry=None, holiday_calendar=None):
    def loop():
        while True:
            try:
                if service.is_configured():
                    make_poller(service, interval_seconds, registry, holiday_calendar).poll_once()
            except Exception:
                logger.warning("poll cycle failed", exc_info=True)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
