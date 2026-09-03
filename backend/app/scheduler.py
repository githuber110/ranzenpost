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
        services = config.get("notify_services") or [None]
        sent_any = False
        for service in services:
            try:
                if notify(message, service=service):
                    sent_any = True
            except Exception:
                logger.warning("notify to %s failed", service, exc_info=True)
        return sent_any

    return send


def _build_publisher():
    if not os.environ.get("ISERV_MQTT_HOST"):
        return None
    try:
        from .mqtt_publisher import MqttPublisher, connect_from_env

        return MqttPublisher(connect_from_env())
    except Exception:
        return None


def start_poller(service, interval_seconds=1800, registry=None, holiday_calendar=None):
    def loop():
        publisher = None
        discovered = False
        while True:
            try:
                if service.is_configured():
                    if publisher is None:
                        publisher = _build_publisher()
                    if publisher is not None and not discovered:
                        try:
                            publisher.publish_discovery(service.children())
                            discovered = True
                        except Exception:
                            logger.warning("MQTT discovery publish failed", exc_info=True)
                    Poller(
                        service,
                        publisher=publisher,
                        notifier=_make_notifier(service.store),
                        notifiers={
                            event: _make_notifier(service.store, event)
                            for event in ("timetable", "letters", "pinboard", "conferences", "auth")
                        },
                        registry=registry,
                        holiday_calendar=holiday_calendar,
                    ).poll_once()
            except Exception:
                logger.warning("poll cycle failed", exc_info=True)
            time.sleep(interval_seconds)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
