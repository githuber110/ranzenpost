import logging
import os

from . import messages
from .calendar_listener import DEFAULT_PORT as FEED_PORT

CORE_API = "http://supervisor/core/api"
SUPERVISOR_API = "http://supervisor"
REQUEST_TIMEOUT = 5

logger = logging.getLogger(__name__)

DEFAULT_HOST = "homeassistant.local"
REMOTE_UI_DOMAIN = "nabu.casa"
CONTAINER_PORT_KEY = f"{FEED_PORT}/tcp"

INTERNAL_URL = "internal_url"
EXTERNAL_URL = "external_url"
HOST_SOURCE_INTERNAL = "internal_url"
HOST_SOURCE_EXTERNAL = "external_url"
HOST_SOURCE_FALLBACK = "fallback"

PORT_OPENED_KEY = "api.calendar.port.opened"
PORT_ALREADY_OPEN_KEY = "api.calendar.port.alreadyOpen"
PORT_UNAVAILABLE_KEY = "api.calendar.error.portUnavailable"
PORT_FAILED_KEY = "api.calendar.error.portFailed"
RESTART_ACCEPTED_KEY = "api.calendar.restart.accepted"
RESTART_FAILED_KEY = "api.calendar.error.restartFailed"
RESTART_PATH = "/addons/self/restart"
RESTART_PENDING_KEY = "calendar_restart_pending"
RESTART_DELAY_SECONDS = 0.5

URL_SEPARATORS = ("/", "?", "#")


class AutonomousRestartError(RuntimeError):
    pass


def sanitize_host(value):
    text = str(value or "").strip()
    if not text:
        return ""
    marker = text.find("://")
    if marker != -1:
        text = text[marker + 3 :]
    elif text.startswith("//"):
        text = text[2:]
    for separator in URL_SEPARATORS:
        cut = text.find(separator)
        if cut != -1:
            text = text[:cut]
    if "@" in text:
        text = text.rpartition("@")[2]
    text = text.strip()
    if text.startswith("["):
        closing = text.find("]")
        if closing == -1:
            return ""
        text = text[1:closing]
    elif text.count(":") == 1:
        text = text.partition(":")[0]
    text = text.strip().rstrip(".").strip()
    if not text or "[" in text or "]" in text or " " in text:
        return ""
    return text.lower()


def is_remote_ui_host(host):
    candidate = str(host or "").strip().lower().rstrip(".")
    return candidate == REMOTE_UI_DOMAIN or candidate.endswith(f".{REMOTE_UI_DOMAIN}")


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _token():
    return os.environ.get("SUPERVISOR_TOKEN")


def _unwrap(payload):
    if not isinstance(payload, dict):
        return None
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else payload


def _core_config():
    token = _token()
    if not token:
        return {}
    import requests

    try:
        response = requests.get(
            f"{CORE_API}/config", headers=_headers(token), timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _addon_info():
    token = _token()
    if not token:
        return None
    import requests

    try:
        response = requests.get(
            f"{SUPERVISOR_API}/addons/self/info", headers=_headers(token), timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return None
    return _unwrap(payload)


def host_state():
    config = _core_config()
    for field, source in (
        (INTERNAL_URL, HOST_SOURCE_INTERNAL),
        (EXTERNAL_URL, HOST_SOURCE_EXTERNAL),
    ):
        host = sanitize_host(config.get(field))
        if host and not is_remote_ui_host(host):
            return {"host": host, "host_source": source}
    return {"host": DEFAULT_HOST, "host_source": HOST_SOURCE_FALLBACK}


def resolve_host():
    return host_state()["host"]


def mapped_feed_port(info):
    network = (info or {}).get("network")
    if not isinstance(network, dict):
        return 0
    value = network.get(CONTAINER_PORT_KEY)
    if isinstance(value, bool):
        return 0
    try:
        port = int(value)
    except (TypeError, ValueError):
        return 0
    return port if port > 0 else 0


def feed_port_state(port=FEED_PORT):
    info = _addon_info()
    mapped = mapped_feed_port(info)
    return {
        "supervisor": info is not None,
        "port_open": mapped == int(port),
        "mapped_port": mapped,
    }


def feed_port_open(port=FEED_PORT):
    return mapped_feed_port(_addon_info()) == int(port)


def open_feed_port(port=FEED_PORT, store=None):
    token = _token()
    if not token:
        return messages.result(
            False, PORT_UNAVAILABLE_KEY, port_open=False, restart_required=False
        )
    target = int(port)
    info = _addon_info()
    if info is None:
        return messages.result(
            False, PORT_UNAVAILABLE_KEY, port_open=False, restart_required=False
        )
    if mapped_feed_port(info) == target:
        pending = restart_pending(store)
        return messages.result(
            True, PORT_ALREADY_OPEN_KEY, port_open=True, restart_required=pending
        )
    import requests

    try:
        response = requests.post(
            f"{SUPERVISOR_API}/addons/self/options",
            headers=_headers(token),
            json={"network": {CONTAINER_PORT_KEY: target}},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return messages.result(False, PORT_FAILED_KEY, port_open=False, restart_required=False)
    _write_restart_pending(store, True)
    return messages.result(True, PORT_OPENED_KEY, port_open=True, restart_required=True)


def _post_restart(token):
    import requests

    try:
        requests.post(
            f"{SUPERVISOR_API}{RESTART_PATH}",
            headers=_headers(token),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        logger.warning("the add-on restart call did not come back", exc_info=True)


def _schedule_restart(token):
    import threading

    timer = threading.Timer(RESTART_DELAY_SECONDS, _post_restart, args=(token,))
    timer.daemon = True
    timer.start()


def restart_addon(requested_by_user=False, schedule=None):
    if not requested_by_user:
        raise AutonomousRestartError("the add-on restart needs an explicit user request")
    token = _token()
    if not token:
        return messages.result(False, PORT_UNAVAILABLE_KEY, restarting=False)
    runner = schedule if schedule is not None else _schedule_restart
    try:
        runner(token)
    except Exception:
        logger.warning("the add-on restart could not be scheduled", exc_info=True)
        return messages.result(False, RESTART_FAILED_KEY, restarting=False)
    return messages.result(True, RESTART_ACCEPTED_KEY, restarting=True)


def _write_restart_pending(store, pending):
    if store is None:
        return
    config = store.load_config()
    if bool(config.get(RESTART_PENDING_KEY)) == bool(pending):
        return
    if pending:
        config[RESTART_PENDING_KEY] = True
    else:
        config.pop(RESTART_PENDING_KEY, None)
    store.save_config(config)


def restart_pending(store):
    if store is None:
        return False
    return bool(store.load_config().get(RESTART_PENDING_KEY))


def clear_restart_pending(store):
    _write_restart_pending(store, False)


def calendar_access(port=FEED_PORT, store=None):
    state = dict(host_state())
    state.update(feed_port_state(port))
    state["restart_pending"] = restart_pending(store)
    return state
