import hashlib
import json

import fastapi
import pydantic
from fastapi.routing import APIRoute

from app.server import create_app
from app.store import Store

from tests.test_server import FakeService, FakeWizard

OPENAPI_SHA256 = "0e61639867e6b14dfabb27a9bea6cce3975030c343d05d80e9e12a5cd9b710f9"

API_ROUTES = [
    (["GET"], "/api/integration/info", "info"),
    (["GET"], "/api/integration/state", "state"),
    (["GET"], "/api/integration/events", "events"),
    (["GET"], "/api/integration/school", "school"),
    (["GET"], "/api/integration/changes", "changes"),
    (["GET"], "/api/integration-status", "integration_status"),
    (["POST"], "/api/integration-status/rotate", "rotate_integration_token"),
    (["GET"], "/api/health", "health"),
    (["POST"], "/api/connections/{connection_id}/retry", "retry_connection"),
    (["GET"], "/api/connections", "list_connections"),
    (["GET"], "/api/connections/{connection_id}", "connection_view"),
    (["POST"], "/api/connections/{connection_id}", "set_connection"),
    (["POST"], "/api/connections/{connection_id}/disconnect", "disconnect_connection"),
    (["POST"], "/api/connections/{connection_id}/modules/recheck", "recheck_connection_modules"),
    (["GET"], "/api/connections/{connection_id}/modules", "connection_modules"),
    (["GET"], "/api/wizard", "wizard_status"),
    (["POST"], "/api/wizard/url", "wizard_url"),
    (["POST"], "/api/wizard/login", "wizard_login"),
    (["POST"], "/api/wizard/connect", "wizard_connect"),
    (["POST"], "/api/wizard/child", "wizard_child"),
    (["POST"], "/api/wizard/skip-child", "wizard_skip_child"),
    (["POST"], "/api/wizard/back", "wizard_back"),
    (["POST"], "/api/wizard/reset", "wizard_reset"),
    (["POST"], "/api/wizard/start", "wizard_start"),
    (["POST"], "/api/wizard/cancel", "wizard_cancel"),
    (["GET"], "/api/modules", "module_registry"),
    (["POST"], "/api/modules/recheck", "recheck_modules"),
    (["GET"], "/api/diagnostics", "diagnostics_report"),
    (["GET"], "/api/diagnostics/report.zip", "diagnostics_bundle"),
    (["GET"], "/api/timetable-availability", "timetable_availability"),
    (["GET"], "/api/config", "get_config"),
    (["POST"], "/api/config", "set_config"),
    (["POST"], "/api/password", "change_password"),
    (["POST"], "/api/password/repair", "repair_password"),
    (["POST"], "/api/account/disconnect", "disconnect_account"),
    (["GET"], "/api/notify-services", "notify_services"),
    (["GET"], "/api/me", "me"),
    (["GET"], "/api/children", "children"),
    (["GET"], "/api/timetable", "timetable"),
    (["GET"], "/api/timetable/courses", "timetable_courses"),
    (["POST"], "/api/timetable/courses", "save_timetable_courses"),
    (["GET"], "/api/holidays/regions", "holiday_regions"),
    (["GET"], "/api/holidays/region-suggestion", "holiday_region_suggestion"),
    (["GET"], "/api/holidays", "holiday_range"),
    (["GET"], "/api/pinboard", "pinboard"),
    (["POST"], "/api/pinboard/seen", "pinboard_seen"),
    (["GET"], "/api/pinboard/attachment/{filename}", "pinboard_attachment"),
    (["GET"], "/api/letters", "letters"),
    (["POST"], "/api/letters/seen", "letters_seen"),
    (["GET"], "/api/letters/detail", "letter_detail"),
    (["POST"], "/api/letters/archive", "letters_archive"),
    (["POST"], "/api/letters/restore", "letters_restore"),
    (["POST"], "/api/letters/confirm", "letters_confirm"),
    (["GET"], "/api/letters/attachment/{attachment_id}", "letters_attachment"),
    (["GET"], "/api/conferences", "conferences"),
    (["GET"], "/api/absences", "absences"),
    (["POST"], "/api/absences", "report_absence"),
    (["POST"], "/api/absences/delete", "delete_absence"),
    (["GET"], "/api/absences/attachment/{filename}", "absence_attachment"),
    (["GET"], "/api/absences/sick-note-pdf", "sick_note_pdf"),
    (["POST"], "/api/notify-test", "notify_test"),
    (["GET"], "/api/calendar/subscriptions", "calendar_subscriptions"),
    (["POST"], "/api/calendar/port", "open_calendar_port"),
    (["POST"], "/api/calendar/restart", "restart_calendar_addon"),
    (["POST"], "/api/calendar/subscriptions", "create_calendar_subscription"),
    (["POST"], "/api/calendar/subscriptions/{subscription_id}", "update_calendar_subscription"),
    (["POST"], "/api/calendar/subscriptions/{subscription_id}/rotate", "rotate_calendar_subscription"),
    (["DELETE"], "/api/calendar/subscriptions/{subscription_id}", "revoke_calendar_subscription"),
    (["GET"], "/api/marks", "list_marks"),
    (["POST"], "/api/marks", "create_mark"),
    (["POST"], "/api/marks/{mark_id}", "update_mark"),
    (["DELETE"], "/api/marks/{mark_id}", "delete_mark"),
    (["GET"], "/api/connections/{connection_id}/periods", "period_grid_view"),
    (["POST"], "/api/connections/{connection_id}/periods/lessons", "add_period_lesson"),
    (["POST"], "/api/connections/{connection_id}/periods/lessons/{number}", "set_period_lesson"),
    (["POST"], "/api/connections/{connection_id}/periods/lessons/{number}/reset", "reset_period_lesson"),
    (["DELETE"], "/api/connections/{connection_id}/periods/lessons/{number}", "remove_period_lesson"),
    (["POST"], "/api/connections/{connection_id}/periods/reset", "reset_period_grid"),
    (["POST"], "/api/connections/{connection_id}/own-entries", "create_own_entry"),
    (["POST"], "/api/connections/{connection_id}/own-entries/rollover", "roll_own_entries"),
    (["POST"], "/api/connections/{connection_id}/own-entries/{entry_id}", "update_own_entry"),
    (["DELETE"], "/api/connections/{connection_id}/own-entries/{entry_id}", "delete_own_entry"),
    (["GET"], "/api/cancellations", "list_cancellations"),
    (["POST"], "/api/cancellations", "create_cancellation"),
    (["DELETE"], "/api/cancellations/{cancellation_id}", "delete_cancellation"),
    (["GET"], "/api/messenger/rooms", "messenger_rooms"),
    (["GET"], "/api/messenger/room", "messenger_room"),
    (["POST"], "/api/messenger/send", "messenger_send"),
    (["POST"], "/api/messenger/read", "messenger_read"),
    (["GET"], "/api/messenger/teachers", "messenger_teachers"),
    (["GET"], "/api/messenger/room/teacher/children", "messenger_teacher_room_children"),
    (["POST"], "/api/messenger/room/teacher", "messenger_teacher_room"),
    (["GET"], "/api/messenger/media/{server_name}/{media_id}", "messenger_media"),
]


def full_app(tmp_path):
    return create_app(FakeService(Store(tmp_path / "data")), wizard=FakeWizard())


def api_routes(app):
    return [
        (sorted(route.methods), route.path, route.name)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api")
    ]


def openapi_sha256(app):
    document = json.dumps(app.openapi(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def test_the_app_serves_exactly_the_known_api_routes_in_order(tmp_path):
    assert api_routes(full_app(tmp_path)) == API_ROUTES


def test_the_openapi_document_is_unchanged(tmp_path):
    actual = openapi_sha256(full_app(tmp_path))
    assert actual == OPENAPI_SHA256, (
        f"the public API description changed: {actual} "
        f"(fastapi {fastapi.__version__}, pydantic {pydantic.VERSION}); "
        "a pure code move must not change it, a deliberate API change or a library upgrade updates OPENAPI_SHA256"
    )


def test_the_openapi_fingerprint_is_stable_between_two_builds(tmp_path):
    assert openapi_sha256(full_app(tmp_path / "one")) == openapi_sha256(full_app(tmp_path / "two"))


def test_the_route_snapshot_notices_a_renamed_endpoint(tmp_path):
    app = full_app(tmp_path)
    route = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == "/api/health")
    route.name = "renamed"
    assert api_routes(app) != API_ROUTES
