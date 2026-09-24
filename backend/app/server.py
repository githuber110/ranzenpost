import logging
import threading
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import cancellations, diagnostics, holidays, integration, marks, messages, modules, schoolregion, subscriptions
from .absence_routes import register_routes as register_absence_routes
from .account_routes import register_routes as register_account_routes
from .calendar_routes import register_routes as register_calendar_routes
from .cancellation_routes import register_routes as register_cancellation_routes
from .config_routes import register_routes as register_config_routes
from .connection_routes import register_routes as register_connection_routes
from .iserv.errors import DataError, sign_in_reason_rank
from .letter_routes import register_routes as register_letter_routes
from .mark_routes import register_routes as register_mark_routes
from .period_routes import register_routes as register_period_routes
from .pinboard_routes import register_routes as register_pinboard_routes
from .poller import Poller
from .store import config_for_connection
from .upstream import NETWORK, _binary_upstream_response, read_endpoint, upstream_write_error, write_endpoint
from .wizard_routes import register_routes as register_wizard_routes

logger = logging.getLogger(__name__)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-src blob:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
NOTIFY_TEST_MESSAGE_KEY = "notify.test.message"
NOTIFY_TEST_TITLE_KEY = "notify.test.title"
DEFAULT_LANGUAGE = "system"
MAX_WEEK = 8


def _clamp_week(value):
    try:
        week = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-MAX_WEEK, min(MAX_WEEK, week))


PLACEHOLDER_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ranzenpost (IServ)</title></head>
<body style="font-family:system-ui;margin:0;display:grid;place-items:center;height:100vh;background:#f3f4f8;color:#14161c">
<div style="text-align:center;max-width:340px;padding:24px">
<h1 style="font-size:20px">Ranzenpost</h1>
<p style="color:#6b7280">Der Dienst läuft.</p>
</div></body></html>"""


def create_app(
    service,
    wizard=None,
    frontend_dir=None,
    holiday_calendar=None,
    registry=None,
    region_suggester=None,
    mark_registry=None,
    calendar_warmer=None,
    integration_access=None,
):
    app = FastAPI(title="Ranzenpost")
    from .integration_api import IntegrationAccess, register_integration_routes, register_status_routes
    from .supervisor import clear_restart_pending

    clear_restart_pending(service.store)
    holiday_source = holiday_calendar or holidays.HolidayCalendar(service.store)
    region_source = region_suggester or schoolregion.RegionSuggester(service)
    subscription_registry = registry or subscriptions.SubscriptionRegistry(service.store)
    marks_registry = mark_registry or marks.MarkRegistry(service.store)
    cancellation_registry = cancellations.CancellationRegistry(service.store)

    def warm_calendar(child_id):
        def run():
            try:
                Poller(
                    service, registry=subscription_registry, holiday_calendar=holiday_source
                ).refresh_child(child_id)
            except Exception:
                logger.warning("calendar warm-up for a child failed", exc_info=True)

        threading.Thread(target=run, daemon=True).start()

    warm = calendar_warmer or warm_calendar
    access = integration_access or IntegrationAccess(service.store)
    register_integration_routes(app, service, service.store, holiday_source, access, warm=warm)
    register_status_routes(app, access)
    app.state.integration_access = access

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def _connection_config(connection_id):
        if connection_id:
            service.known_connection(connection_id)
        else:
            connection_id = service.first_connection().id
        return config_for_connection(service.store, connection_id)

    @app.get("/api/health")
    def health():
        overall, rows = service.health_overview()
        matching = [row for row in rows if row["status"] == overall]
        failing = min(
            matching,
            key=lambda row: sign_in_reason_rank(row.get("reason")),
            default=rows[0] if rows else {},
        )
        return {
            "status": "ok",
            "configured": service.is_configured(),
            "connection": overall,
            "username": failing.get("username", ""),
            "connection_id": failing.get("id", ""),
            "auth_reason": failing.get("reason", ""),
            "language": service.store.load_config().get("language") or DEFAULT_LANGUAGE,
            "modules": modules.registry_of(service),
            "version": integration.addon_version(),
            "connections": [
                dict(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "short_name": row.get("short_name", ""),
                        "status": row["status"],
                        "reason": row.get("reason", ""),
                        "stale": row.get("stale", False),
                        "username": row["username"],
                        "setup_complete": row["setup_complete"],
                        "children": len(row["children"]),
                    },
                    **integration.outage_view(service.store, row["id"]),
                )
                for row in rows
            ],
        }

    retry_stamps = {}
    retry_lock = threading.Lock()

    register_connection_routes(app, service, wizard, subscription_registry, holiday_source, retry_stamps, retry_lock)

    if wizard is not None:
        register_wizard_routes(app, wizard)

    @app.get("/api/modules")
    def module_registry(connection: str = ""):
        if connection:
            return read_endpoint(lambda: service.modules_of(connection))
        return modules.registry_of(service)

    @app.post("/api/modules/recheck")
    def recheck_modules(body: dict = Body(default=None)):
        connection_id = (body or {}).get("connection_id") or None
        return write_endpoint(lambda: service.recheck_modules(connection_id))

    report_cache = diagnostics.ReportCache()

    def structure_wanted(structure):
        return str(structure).strip().lower() not in ("0", "false", "no", "")

    @app.get("/api/diagnostics")
    def diagnostics_report(structure: str = "1", module: str = ""):
        return {
            "report": report_cache.build(service, structure=structure_wanted(structure), module=module),
            "segments": diagnostics.report_segments(service),
            "facts": diagnostics.report_facts(service),
        }

    @app.get("/api/diagnostics/report.zip")
    def diagnostics_bundle(structure: str = "1", module: str = ""):
        content = report_cache.bundle(service, structure=structure_wanted(structure), module=module)
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="%s"' % diagnostics.BUNDLE_NAME},
        )

    @app.get("/api/timetable-availability")
    def timetable_availability():
        return {"available": modules.available(modules.registry_of(service), modules.TIMETABLE)}

    register_config_routes(app, service)

    register_account_routes(app, service, wizard)

    @app.get("/api/notify-services")
    def notify_services():
        from .haservices import list_notify_services

        return list_notify_services()

    @app.get("/api/me")
    def me(connection: str = ""):
        return read_endpoint(lambda: service.me(connection or None))

    @app.get("/api/children")
    def children(connection: str = ""):
        return read_endpoint(lambda: service.children(connection or None))

    @app.get("/api/timetable")
    def timetable(child: str, week: int = 0):
        return read_endpoint(lambda: service.timetable(child, week_offset=_clamp_week(week)))

    @app.get("/api/timetable/courses")
    def timetable_courses(child: str):
        return read_endpoint(lambda: service.timetable_courses(child))

    @app.post("/api/timetable/courses")
    def save_timetable_courses(body: dict = Body(...)):
        child = str(body.get("child") or "")
        chosen = body.get("chosen")
        known = body.get("known")
        if chosen is not None and (not isinstance(chosen, list) or not isinstance(known, list)):
            return JSONResponse(status_code=400, content=messages.result(False, "api.courses.invalid", error="invalid"))
        if chosen == [] and known and body.get("confirm_empty") is not True:
            return JSONResponse(status_code=400, content=messages.result(False, "api.courses.emptyUnconfirmed", error="unconfirmed"))
        try:
            result = service.save_course_filter(child, chosen, known, body.get("confirm_empty") is True)
        except DataError as error:
            return JSONResponse(status_code=404, content=upstream_write_error(NETWORK, error))
        warm(child)
        return result

    @app.get("/api/holidays/regions")
    def holiday_regions():
        return {"regions": holidays.region_options()}

    @app.get("/api/holidays/region-suggestion")
    def holiday_region_suggestion(connection: str = ""):
        return region_source.suggest(connection or None)

    @app.get("/api/holidays")
    def holiday_range(week: int = 0, start: str = "", end: str = "", connection: str = ""):
        first = holidays.parse_day(start)
        last = holidays.parse_day(end)
        if first is None or last is None:
            first, last = holidays.week_range(_clamp_week(week))
        if last < first:
            first, last = last, first
        if (last - first).days > holidays.MAX_SPAN_DAYS:
            return JSONResponse(
                status_code=400, content=messages.payload("api.holidays.error.range")
            )
        return read_endpoint(lambda: holiday_source.range_info(first, last, _connection_config(connection)))

    register_pinboard_routes(app, service)

    register_letter_routes(app, service)

    @app.get("/api/conferences")
    def conferences():
        return read_endpoint(service.conferences)

    register_absence_routes(app, service)

    @app.post("/api/notify-test")
    def notify_test(body: dict = Body(...)):
        from .hanotify import notify

        try:
            language = messages.normalize_language(body.get("language"))
            sent = notify(
                messages.text_in(language, NOTIFY_TEST_MESSAGE_KEY),
                service=body.get("service") or None,
                title=messages.text_in(language, NOTIFY_TEST_TITLE_KEY),
            )
        except Exception:
            sent = False
        if not sent:
            return messages.result(False, "api.notify.failed")
        return messages.result(True, "api.notify.sent")

    register_calendar_routes(app, service, subscription_registry, warm)

    register_mark_routes(app, marks_registry)

    register_period_routes(app, service, holiday_source)

    register_cancellation_routes(app, cancellation_registry)

    from .messenger_routes import register_routes as register_messenger_routes

    register_messenger_routes(app, service, read_endpoint, write_endpoint, _binary_upstream_response)

    if frontend_dir and Path(frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        @app.get("/", response_class=HTMLResponse)
        def index():
            return PLACEHOLDER_HTML

    return app
