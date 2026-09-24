import time

from fastapi import Body
from fastapi.responses import JSONResponse

from . import integration, messages, modules
from .iserv.errors import DataError
from .poller import school_lock
from .scheduler import make_poller, poll_interval_from_env
from .store import CONNECTION_SETTING_KEYS, edit_config
from .upstream import NETWORK, read_endpoint, upstream_error, upstream_write_error, write_endpoint

CONNECTION_ALLOWED_KEYS = set(CONNECTION_SETTING_KEYS)
CONNECTION_VIEW_KEYS = (
    "school_url",
    "school_name",
    "label",
    "short_name",
    "created_at",
    "setup_complete",
    "children",
    "subjects",
    "teachers",
    "period_times",
    "phones",
    "holiday_region",
    "own_entries_ha",
)
BOOLEAN_CONNECTION_KEYS = ("own_entries_ha",)


def _sanitize_phones(phones):
    if not isinstance(phones, list):
        return None
    cleaned = []
    for entry in phones:
        label = str(entry.get("label", "")).strip() if isinstance(entry, dict) else ""
        number = str(entry.get("number", "")).strip() if isinstance(entry, dict) else ""
        if not label and not number:
            continue
        if not label or not number:
            return None
        cleaned.append(entry)
    return cleaned


SHORT_NAME_MAX_LENGTH = 30

RETRY_INTERVAL_SECONDS = 60
RETRY_WAIT_SECONDS = 180
RETRY_TOO_SOON_KEY = "api.retry.tooSoon"
RETRY_DONE_KEY = "api.retry.done"


def register_routes(app, service, wizard, subscription_registry, holiday_source, retry_stamps, retry_lock):
    def _connection_view(connection_id):
        connection = service.known_connection(connection_id)
        config = connection.store.load_config()
        view = {key: config.get(key) for key in CONNECTION_VIEW_KEYS}
        view["id"] = connection.id
        view["name"] = connection.display_name()
        view["username"] = connection.store.load_secrets().get("username", "")
        view["modules"] = modules.registry_of(connection)
        view["children"] = [
            dict(child, key=connection.child_key(str(child.get("child_id") or "")), connection_id=connection.id)
            for child in config.get("children") or []
        ]
        return view

    @app.post("/api/connections/{connection_id}/retry")
    def retry_connection(connection_id: str):
        try:
            connection = service.known_connection(connection_id)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_error(NETWORK, error))
        now = time.time()
        with retry_lock:
            last = retry_stamps.get(connection.id, 0.0)
            if now - last < RETRY_INTERVAL_SECONDS:
                return messages.result(False, RETRY_TOO_SOON_KEY, error="rate_limited")
            retry_stamps[connection.id] = now
        running = school_lock(service.store, connection.id)
        if running.acquire(blocking=False):
            running.release()
            make_poller(
                service, poll_interval_from_env(), registry=subscription_registry, holiday_calendar=holiday_source
            ).poll_once(connection_id=connection.id)
        elif running.acquire(timeout=RETRY_WAIT_SECONDS):
            running.release()
        row = next((entry for entry in service.summaries(with_status=True) if entry["id"] == connection.id), {})
        status = row.get("status", "")
        slot = integration.school_state(service.store, connection.id)
        reason = str(slot.get(integration.AUTH_REASON) or "") if status == integration.ERROR_AUTH else ""
        return messages.result(
            True, RETRY_DONE_KEY, status=status, reason=reason, **integration.outage_view(service.store, connection.id)
        )

    @app.get("/api/connections")
    def list_connections():
        return {"connections": service.summaries()}

    @app.get("/api/connections/{connection_id}")
    def connection_view(connection_id: str):
        return read_endpoint(lambda: _connection_view(connection_id))

    @app.post("/api/connections/{connection_id}")
    def set_connection(connection_id: str, config: dict = Body(...)):
        unknown_keys = sorted(key for key in config if key not in CONNECTION_ALLOWED_KEYS)
        if unknown_keys:
            body = {"error": "unknown_keys", "keys": unknown_keys}
            body.update(messages.payload("api.config.unknownKeys", {"keys": ", ".join(unknown_keys)}))
            return JSONResponse(status_code=400, content=body)
        wrong = sorted(key for key in BOOLEAN_CONNECTION_KEYS if key in config and not isinstance(config[key], bool))
        if wrong:
            body = {"error": "invalid_value", "keys": wrong}
            body.update(messages.payload("api.config.invalidValue", {"keys": ", ".join(wrong)}))
            return JSONResponse(status_code=400, content=body)
        if "phones" in config:
            cleaned_phones = _sanitize_phones(config["phones"])
            if cleaned_phones is None:
                return JSONResponse(status_code=400, content={"error": "invalid_phones"})
            config = dict(config)
            config["phones"] = cleaned_phones
        if "label" in config:
            config = dict(config)
            config["label"] = " ".join(str(config["label"] or "").split())[:60]
        if "short_name" in config:
            config = dict(config)
            config["short_name"] = " ".join(str(config["short_name"] or "").split())[:SHORT_NAME_MAX_LENGTH]
        try:
            connection = service.known_connection(connection_id)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_error(NETWORK, error))
        edit_config(connection.store, lambda current: current.update(config))
        return {"saved": True}

    @app.post("/api/connections/{connection_id}/disconnect")
    def disconnect_connection(connection_id: str):
        try:
            result = service.disconnect(connection_id)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_write_error(NETWORK, error))
        if wizard is not None and not service.store.connections():
            wizard.reset()
        return result

    @app.post("/api/connections/{connection_id}/modules/recheck")
    def recheck_connection_modules(connection_id: str):
        return write_endpoint(lambda: service.recheck_modules(connection_id))

    @app.get("/api/connections/{connection_id}/modules")
    def connection_modules(connection_id: str):
        return read_endpoint(lambda: service.modules_of(connection_id))
