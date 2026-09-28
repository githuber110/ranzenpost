from fastapi import Body
from fastapi.responses import JSONResponse

from . import messages
from .hanotify import notify_service_list
from .store import GLOBAL_SETTING_KEYS, edit_config, normalize_layout

CONFIG_ALLOWED_KEYS = set(GLOBAL_SETTING_KEYS)


def register_routes(app, service):
    @app.get("/api/config")
    def get_config():
        return service.store.load_config()

    @app.post("/api/config")
    def set_config(config: dict = Body(...)):
        unknown_keys = sorted(key for key in config if key not in CONFIG_ALLOWED_KEYS)
        if unknown_keys:
            body = {"error": "unknown_keys", "keys": unknown_keys}
            body.update(messages.payload("api.config.unknownKeys", {"keys": ", ".join(unknown_keys)}))
            return JSONResponse(status_code=400, content=body)
        if "notify_services" in config:
            config["notify_services"] = notify_service_list(config["notify_services"])

        def change(current):
            current.update(config)
            current.update(normalize_layout(current))

        edit_config(service.store, change)
        return {"saved": True}
