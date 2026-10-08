import os

from fastapi import Body
from fastapi.responses import JSONResponse

from . import messages, modules, subscriptions
from .calendar_listener import DEFAULT_PORT as CALENDAR_PORT


def school_calendar_ready(store, connection_id):
    scoped = getattr(store, "connection_store", None)
    if not callable(scoped):
        return False
    stored = scoped(connection_id).load_modules()
    return bool(stored) and modules.available(stored, modules.CALENDAR)


def register_routes(app, service, subscription_registry, warm, integration_seen):
    def _warm_after(entry):
        wanted = (subscriptions.COMPONENT_TIMETABLE, subscriptions.COMPONENT_MARKS, subscriptions.COMPONENT_OWN_ENTRIES)
        if any(name in (entry.get("components") or []) for name in wanted):
            warm(entry.get("child_key", ""))
        return entry

    def _internet():
        return subscriptions.internet_access(
            subscription_registry.outside_access, integration_seen(), int(subscription_registry.clock()), subscription_registry.started
        )

    def _internet_refused(subscription_id=""):
        access = _internet()
        if access == subscriptions.INTERNET_READY:
            return None
        current = next((view for view in subscription_registry.list() if view.get("id") == subscription_id), None)
        if current is not None and current.get("online"):
            return None
        return _subscription_error(subscriptions.SubscriptionError(subscriptions.INTERNET_REFUSALS[access]))

    def _subscription_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/calendar/subscriptions")
    def calendar_subscriptions():
        from .supervisor import calendar_access

        seen = integration_seen()
        now = int(subscription_registry.clock())
        body = {
            "subscriptions": [
                subscriptions.settle_online_state(view, seen, now) for view in subscription_registry.list()
            ],
            "components": list(subscriptions.COMPONENTS),
            "holiday_regions": {
                entry["id"]: entry.get("holiday_region") or "" for entry in service.store.connections()
            },
            "school_events": {
                entry["id"]: school_calendar_ready(service.store, entry["id"]) for entry in service.store.connections()
            },
            "path_template": "/calendar/{token}.ics",
            "port": int(os.environ.get("ISERV_CALENDAR_PORT", str(CALENDAR_PORT))),
            "internet": _internet(),
        }
        body.update(calendar_access(store=service.store))
        return body

    @app.post("/api/calendar/port")
    def open_calendar_port():
        from .supervisor import open_feed_port

        return open_feed_port(store=service.store)

    @app.post("/api/calendar/restart")
    def restart_calendar_addon():
        from .supervisor import restart_addon

        return restart_addon(requested_by_user=True)

    @app.post("/api/calendar/subscriptions")
    def create_calendar_subscription(body: dict = Body(...)):
        refused = _internet_refused() if body.get("online") is True else None
        if refused is not None:
            return refused
        try:
            return _warm_after(
                subscription_registry.create(
                    body.get("child_key", ""),
                    body.get("components"),
                    body.get("label", ""),
                    body.get("color", ""),
                    online=body.get("online") is True,
                    school_id=body.get("school_id", ""),
                )
            )
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.post("/api/calendar/subscriptions/{subscription_id}")
    def update_calendar_subscription(subscription_id: str, body: dict = Body(...)):
        refused = _internet_refused(subscription_id) if body.get("online") is True else None
        if refused is not None:
            return refused
        try:
            updated = subscription_registry.update(
                subscription_id,
                components=body.get("components"),
                label=body.get("label"),
                color=body.get("color"),
                online=body.get("online") if isinstance(body.get("online"), bool) else None,
            )
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)
        return _warm_after(updated) if body.get("components") is not None else updated

    @app.post("/api/calendar/subscriptions/{subscription_id}/rotate")
    def rotate_calendar_subscription(subscription_id: str):
        try:
            return subscription_registry.rotate(subscription_id)
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.delete("/api/calendar/subscriptions/{subscription_id}")
    def revoke_calendar_subscription(subscription_id: str):
        try:
            return subscription_registry.revoke(subscription_id)
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)
