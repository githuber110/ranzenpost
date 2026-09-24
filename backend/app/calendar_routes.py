import os

from fastapi import Body
from fastapi.responses import JSONResponse

from . import messages, subscriptions
from .calendar_listener import DEFAULT_PORT as CALENDAR_PORT


def register_routes(app, service, subscription_registry, warm):
    def _warm_after(entry):
        wanted = (subscriptions.COMPONENT_TIMETABLE, subscriptions.COMPONENT_MARKS, subscriptions.COMPONENT_OWN_ENTRIES)
        if any(name in (entry.get("components") or []) for name in wanted):
            warm(entry.get("child_key", ""))
        return entry

    def _subscription_error(error):
        return JSONResponse(status_code=400, content=messages.result(False, error.message_key))

    @app.get("/api/calendar/subscriptions")
    def calendar_subscriptions():
        from .supervisor import calendar_access

        body = {
            "subscriptions": subscription_registry.list(),
            "components": list(subscriptions.COMPONENTS),
            "holiday_regions": {
                entry["id"]: entry.get("holiday_region") or "" for entry in service.store.connections()
            },
            "path_template": "/calendar/{token}.ics",
            "port": int(os.environ.get("ISERV_CALENDAR_PORT", str(CALENDAR_PORT))),
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
        try:
            return _warm_after(
                subscription_registry.create(
                    body.get("child_key", ""),
                    body.get("components"),
                    body.get("label", ""),
                    body.get("color", ""),
                )
            )
        except subscriptions.SubscriptionError as error:
            return _subscription_error(error)

    @app.post("/api/calendar/subscriptions/{subscription_id}")
    def update_calendar_subscription(subscription_id: str, body: dict = Body(...)):
        try:
            updated = subscription_registry.update(
                subscription_id,
                components=body.get("components"),
                label=body.get("label"),
                color=body.get("color"),
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
