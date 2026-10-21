import json
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from app import upstream
from app.iserv.errors import LoginError, TwoFactorError
from app.server import create_app
from app.service import NotConfiguredError
from app.store import Store

BUNDLE = json.loads(
    (Path(__file__).resolve().parents[2] / "frontend" / "i18n" / "de.json").read_text(
        encoding="utf-8"
    )
)

UPSTREAM_FAILURES = (
    (NotConfiguredError("not set up"), upstream.NOT_CONFIGURED),
    (LoginError("password changed"), upstream.AUTH_FAILED),
    (TwoFactorError("no stored token"), upstream.AUTH_FAILED),
    (requests.RequestException("boom"), upstream.NETWORK),
)

READ_ENDPOINTS = (
    ("/api/me", "GET", None),
    ("/api/children", "GET", None),
    ("/api/timetable", "GET", None),
    ("/api/timetable/courses", "GET", None),
    ("/api/pinboard", "GET", None),
    ("/api/letters", "GET", None),
    ("/api/letters/detail", "GET", None),
    ("/api/letters/answer", "GET", None),
    ("/api/conferences", "GET", None),
    ("/api/conferences/page", "GET", None),
    ("/api/school-events", "GET", None),
    ("/api/tasks", "GET", None),
    ("/api/news", "GET", None),
    ("/api/tasks/detail", "GET", None),
    ("/api/news/section", "GET", None),
    ("/api/news/section/detail", "GET", None),
    ("/api/forums", "GET", None),
    ("/api/texts", "GET", None),
    ("/api/infodisplay", "GET", None),
    ("/api/whiteboards", "GET", None),
    ("/api/mail", "GET", None),
    ("/api/mail/folders", "GET", None),
    ("/api/mail/messages", "GET", None),
    ("/api/mail/message", "GET", None),
    ("/api/mail/source", "GET", None),
    ("/api/mail/compose", "GET", None),
    ("/api/mail/account", "GET", None),
    ("/api/mail/recipients", "GET", None),
    ("/api/mail/settings", "GET", None),
    ("/api/mail/settings/page", "GET", None),
    ("/api/mail/event", "GET", None),
    ("/api/absences", "GET", None),
    ("/api/absences/older-form", "GET", None),
    ("/api/absences/older-detail", "GET", None),
    ("/api/messenger/rooms", "GET", None),
    ("/api/messenger/room", "GET", None),
    ("/api/messenger/teachers", "GET", None),
    ("/api/messenger/room/teacher/children", "GET", None),
    ("/api/account-modules", "GET", None),
    ("/api/files", "GET", None),
    ("/api/files/search", "GET", None),
    ("/api/addressbook/search", "GET", None),
    ("/api/mailinglists", "GET", None),
    ("/api/mailinglists/detail", "GET", None),
)

WRITE_ENDPOINTS = (
    ("/api/pinboard/seen", "POST", {"tile_ids": ["t1"]}),
    ("/api/letters/seen", "POST", {"keys": ["k1"]}),
    ("/api/letters/archive", "POST", {"letter_id": "l1", "recipient_id": "r1"}),
    ("/api/letters/restore", "POST", {"letter_id": "l1", "recipient_id": "r1"}),
    ("/api/letters/confirm", "POST", {"letter_id": "l1", "recipient_id": "r1"}),
    (
        "/api/letters/reply",
        "POST",
        {"letter_id": "l1", "recipient_id": "r1", "text": "hi", "request_id": "a" * 32, "confirmed": True},
    ),
    (
        "/api/conferences/submit",
        "POST",
        {"page": "a" * 24, "form": 0, "check": "c" * 16, "values": {}, "request_id": "a" * 32, "confirmed": True},
    ),
    ("/api/absences", "POST", {"type": "krankmeldung"}),
    ("/api/forums/read", "POST", {"connection_id": "c1", "confirmed": True}),
    ("/api/absences/delete", "POST", {"id": "a1"}),
    ("/api/absences/older-attachment/delete", "POST", {"id": "older:481", "key": "0" * 16}),
    ("/api/tasks/act", "POST", {"task_id": "1", "action": "confirm", "form": "f1", "confirmed": True}),
    ("/api/password/repair", "POST", {"password": "current-pass"}),
    ("/api/messenger/send", "POST", {"room_id": "!r:school.example", "text": "hi"}),
    ("/api/mail/seen", "POST", {"folder": "INBOX", "uid": "7"}),
    ("/api/mail/flag", "POST", {"folder": "INBOX", "uids": ["7"], "flag": "flagged", "on": True}),
    ("/api/mail/move", "POST", {"folder": "INBOX", "uids": ["7"], "target": "Archive"}),
    ("/api/mail/archive", "POST", {"folder": "INBOX", "uids": ["7"]}),
    ("/api/mail/trash", "POST", {"folder": "INBOX", "uids": ["7"]}),
    ("/api/mail/spam", "POST", {"folder": "INBOX", "uids": ["7"], "confirmed": True}),
    ("/api/files/upload", "POST", {"path": "own", "confirmed": True}),
    ("/api/mailinglists/import", "POST", {"confirmed": True}),
    ("/api/mailinglists/delete", "POST", {"list_id": "41", "confirmed": True}),
    ("/api/mail/folder/create", "POST", {"name": "x"}),
    ("/api/mail/folder/rename", "POST", {"folder": "x", "name": "y"}),
    ("/api/mail/folder/delete", "POST", {"folder": "x", "confirmed": True}),
    ("/api/mail/draft/delete", "POST", {"folder": "Drafts", "uid": "1", "confirmed": True}),
    ("/api/mail/receipt", "POST", {"folder": "INBOX", "uid": "7", "send": False}),
    ("/api/mail/draft", "POST", {"to": []}),
    ("/api/mail/send", "POST", {"to": [], "confirmed": True}),
    ("/api/mail/settings/page", "POST", {"path": "/iserv/mail/settings/vacation", "form": 0, "values": {}, "confirmed": True}),
    ("/api/mail/event", "POST", {"path": "/iserv/calendar/create", "form": 0, "values": {}, "confirmed": True}),
    ("/api/messenger/read", "POST", {"room_id": "!r:school.example", "event_id": "$e1"}),
    (
        "/api/messenger/room/teacher",
        "POST",
        {"teacher": "userid:t1", "child_ids": ["c1"], "add_other_parents": False},
    ),
)

BINARY_ENDPOINTS = (
    "/api/pinboard/attachment/note.pdf",
    "/api/letters/attachment/a1",
    "/api/absences/attachment/note.pdf",
    "/api/absences/sick-note-pdf",
    "/api/absences/older-attachment",
    "/api/absences/older-export",
    "/api/news/file",
    "/api/tasks/file",
    "/api/messenger/media/school-server/media-1",
    "/api/mail/attachment",
    "/api/mail/body",
    "/api/files/file",
)

QUERY = {
    "/api/timetable": {"child": "a1b2c3d4:c1"},
    "/api/timetable/courses": {"child": "a1b2c3d4:c1"},
    "/api/letters/detail": {"letter_id": "l1", "recipient_id": "r1"},
    "/api/letters/answer": {"letter_id": "l1", "recipient_id": "r1"},
    "/api/conferences/page": {"page": "a" * 24},
    "/api/absences/sick-note-pdf": {"id": "42"},
    "/api/absences/older-attachment": {"id": "older:481", "key": "0" * 16},
    "/api/messenger/room": {"id": "!r:school.example"},
    "/api/messenger/teachers": {"query": "Beh"},
    "/api/mail/messages": {"folder": "INBOX"},
    "/api/mail/message": {"folder": "INBOX", "uid": "7"},
    "/api/mail/source": {"folder": "INBOX", "uid": "7"},
    "/api/mail/settings/page": {"path": "/iserv/mail/settings/vacation"},
    "/api/mail/event": {"folder": "INBOX", "uid": "7"},
    "/api/mail/attachment": {"folder": "INBOX", "uid": "7", "part": "1"},
    "/api/mail/body": {"folder": "INBOX", "uid": "7"},
}

COVERED_ROUTES = {
    "/api/me",
    "/api/children",
    "/api/timetable",
    "/api/timetable/courses",
    "/api/pinboard",
    "/api/letters",
    "/api/letters/detail",
    "/api/letters/answer",
    "/api/conferences",
    "/api/conferences/page",
    "/api/conferences/submit",
    "/api/school-events",
    "/api/tasks",
    "/api/news",
    "/api/news/file",
    "/api/news/section",
    "/api/news/section/detail",
    "/api/tasks/detail",
    "/api/tasks/file",
    "/api/tasks/act",
    "/api/forums",
    "/api/forums/read",
    "/api/texts",
    "/api/infodisplay",
    "/api/whiteboards",
    "/api/mail",
    "/api/mail/folders",
    "/api/mail/messages",
    "/api/mail/message",
    "/api/mail/seen",
    "/api/mail/attachment",
    "/api/mail/body",
    "/api/mail/source",
    "/api/mail/compose",
    "/api/mail/flag",
    "/api/mail/move",
    "/api/mail/archive",
    "/api/mail/trash",
    "/api/mail/folder/create",
    "/api/mail/folder/rename",
    "/api/mail/folder/delete",
    "/api/mail/draft/delete",
    "/api/mail/receipt",
    "/api/mail/draft",
    "/api/mail/send",
    "/api/mail/account",
    "/api/mail/recipients",
    "/api/mail/settings",
    "/api/mail/settings/page",
    "/api/mail/event",
    "/api/mail/spam",
    "/api/account-modules",
    "/api/files",
    "/api/files/search",
    "/api/files/file",
    "/api/files/upload",
    "/api/addressbook/search",
    "/api/mailinglists",
    "/api/mailinglists/detail",
    "/api/mailinglists/import",
    "/api/mailinglists/delete",

    "/api/absences",
    "/api/pinboard/seen",
    "/api/letters/seen",
    "/api/letters/archive",
    "/api/letters/restore",
    "/api/letters/confirm",
    "/api/letters/reply",
    "/api/absences/delete",
    "/api/absences/older-form",
    "/api/absences/older-detail",
    "/api/absences/older-attachment",
    "/api/absences/older-attachment/delete",
    "/api/absences/older-export",
    "/api/password/repair",
    "/api/pinboard/attachment/{filename}",
    "/api/letters/attachment/{attachment_id}",
    "/api/absences/attachment/{filename}",
    "/api/absences/sick-note-pdf",
    "/api/messenger/rooms",
    "/api/messenger/room",
    "/api/messenger/send",
    "/api/messenger/media/{server_name}/{media_id}",
    "/api/messenger/read",
    "/api/messenger/teachers",
    "/api/messenger/room/teacher",
    "/api/messenger/room/teacher/children",
}

ROUTES_WITHOUT_UPSTREAM_CALLS = {
    "/api/health": "reports the connection state itself, including auth_failed",
    "/api/config": "local store only",
    "/api/timetable-availability": "alias of the stored module registry, never reaches IServ",
    "/api/modules": "stored module registry, never reaches IServ",
    "/api/modules/recheck": "goes through write_endpoint, refusals carry their own message keys",
    "/api/diagnostics": "builds the report itself, a school that cannot log in becomes a line in the report",
    "/api/diagnostics/report.zip": "packs the same self-built report, a failing school is a line in it",
    "/api/holidays": "local calendar",
    "/api/holidays/regions": "static table",
    "/api/holidays/region-suggestion": "own suggestion vocabulary, never raises",
    "/api/notify-services": "Home Assistant, not IServ",
    "/api/notify-test": "Home Assistant, not IServ",
    "/api/account/disconnect": "service.disconnect classifies its own outcome",
    "/api/password": "richer vocabulary, already separates auth_failed from rejected",
    "/api/connections/{connection_id}/periods": "lesson grid and own entries from the local store, holidays from the local calendar",
    "/api/connections/{connection_id}/periods/lessons": "edits the stored lesson grid only",
    "/api/connections/{connection_id}/periods/lessons/{number}": "edits the stored lesson grid only",
    "/api/connections/{connection_id}/periods/lessons/{number}/reset": "edits the stored lesson grid only",
    "/api/connections/{connection_id}/periods/reset": "edits the stored lesson grid only",
    "/api/connections/{connection_id}/own-entries": "own entries live in the local store only",
    "/api/connections/{connection_id}/own-entries/rollover": "own entries live in the local store only",
    "/api/connections/{connection_id}/own-entries/{entry_id}": "own entries live in the local store only",
    "/api/calendar/subscriptions": "local subscription registry",
    "/api/calendar/subscriptions/{subscription_id}": "local subscription registry",
    "/api/calendar/subscriptions/{subscription_id}/rotate": "local subscription registry",
    "/api/calendar/port": "Home Assistant Supervisor, not IServ",
    "/api/calendar/restart": "Home Assistant Supervisor, not IServ",
    "/api/marks": "local mark registry",
    "/api/marks/{mark_id}": "local mark registry",
    "/api/cancellations": "local cancellation registry",
    "/api/cancellations/{cancellation_id}": "local cancellation registry",
    "/api/integration/info": "local store and Supervisor only, own 401/403/429 vocabulary",
    "/api/integration/state": "local snapshot only, own 401/403/429 vocabulary",
    "/api/integration/events": "local snapshot only, own 401/403/429 vocabulary",
    "/api/integration/school": "local snapshot only, own 401/403/429 vocabulary",
    "/api/integration/changes": "local snapshot only, own 401/403/429 vocabulary",
    "/api/integration/feed": "local snapshot and subscription registry only, own 401/403/404/429 vocabulary",
    "/api/integration/feeds": "local subscription registry only, own 400/401/403/429 vocabulary",
    "/api/integration-status": "local token file, never reaches IServ",
    "/api/integration-status/rotate": "local token file and Supervisor, never reaches IServ",
    "/api/wizard": "wizard state machine with its own error object",
    "/api/wizard/url": "wizard state machine with its own error object",
    "/api/wizard/login": "wizard state machine with its own error object",
    "/api/wizard/connect": "wizard state machine with its own error object",
    "/api/wizard/child": "wizard state machine with its own error object",
    "/api/wizard/skip-child": "wizard state machine with its own error object",
    "/api/wizard/back": "wizard state machine with its own error object",
    "/api/wizard/reset": "wizard state machine with its own error object",
    "/api/wizard/start": "wizard state machine with its own error object",
    "/api/wizard/cancel": "wizard state machine with its own error object",
    "/api/wizard/twofactor/start": "wizard state machine with its own error object",
    "/api/wizard/twofactor/confirm": "wizard state machine with its own error object",
    "/api/wizard/twofactor/check": "wizard state machine with its own error object",
    "/api/wizard/registration/check": "wizard state machine with its own error object",
    "/api/wizard/stale-tokens/remove": "wizard state machine with its own error object",
    "/api/wizard/other-tokens/remove": "wizard state machine with its own error object",
    "/api/connections": "local store only",
    "/api/connections/{connection_id}": "local store only, unknown ids answer through read_endpoint",
    "/api/connections/{connection_id}/disconnect": "service.disconnect classifies its own outcome",
    "/api/connections/{connection_id}/modules": "stored module registry, never reaches IServ",
    "/api/connections/{connection_id}/modules/recheck": "goes through write_endpoint, refusals carry their own message keys",
    "/api/connections/{connection_id}/retry": "runs one poll whose outcome the poller classifies itself, answers with the school status",
}


class RaisingService:
    def __init__(self, store, error):
        self.store = store
        self.error = error

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            raise self.error

        return call


class StubWizard:
    def status(self):
        return {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args, **kwargs):
            return {}

        return call


def _client(tmp_path, error):
    store = Store(tmp_path / "data")
    return TestClient(create_app(RaisingService(store, error), wizard=StubWizard()))


def _call(api, path, method, body):
    if method == "GET":
        return api.get(path, params=QUERY.get(path))
    return api.post(path, params=QUERY.get(path), json=body)


def _assert_uniform(body, expected_code):
    assert body["error"] == expected_code
    assert body["message_key"] == upstream.UPSTREAM_ERROR_MESSAGE_KEYS[expected_code]
    assert body["message"] == BUNDLE[body["message_key"]]


@pytest.mark.parametrize("path,method,body", READ_ENDPOINTS)
@pytest.mark.parametrize("error,expected_code", UPSTREAM_FAILURES)
def test_every_read_endpoint_answers_upstream_failure_in_one_shape(
    tmp_path, path, method, body, error, expected_code
):
    response = _call(_client(tmp_path, error), path, method, body)
    assert response.status_code == 200, f"{path} turned {error!r} into an HTTP error"
    _assert_uniform(response.json(), expected_code)


@pytest.mark.parametrize("path,method,body", WRITE_ENDPOINTS)
@pytest.mark.parametrize("error,expected_code", UPSTREAM_FAILURES)
def test_every_write_endpoint_answers_upstream_failure_in_one_shape(
    tmp_path, path, method, body, error, expected_code
):
    response = _call(_client(tmp_path, error), path, method, body)
    assert response.status_code == 200, f"{path} turned {error!r} into an HTTP error"
    payload = response.json()
    assert payload["ok"] is False
    _assert_uniform(payload, expected_code)


@pytest.mark.parametrize("path", BINARY_ENDPOINTS)
@pytest.mark.parametrize("error,expected_code", UPSTREAM_FAILURES)
def test_every_binary_endpoint_separates_auth_from_network(tmp_path, path, error, expected_code):
    response = _call(_client(tmp_path, error), path, "GET", None)
    expected_body, expected_status = upstream.BINARY_UPSTREAM_RESPONSES[expected_code]
    assert response.status_code == expected_status, f"{path} answered {response.text!r}"
    assert response.text == expected_body


def test_auth_failure_is_distinguishable_from_a_network_failure(tmp_path):
    auth = _call(_client(tmp_path, LoginError("x")), "/api/letters", "GET", None).json()
    network = _call(
        _client(tmp_path, requests.RequestException("x")), "/api/letters", "GET", None
    ).json()
    assert auth["error"] != network["error"]
    assert auth["message"] != network["message"]


def test_the_error_shape_stays_backward_compatible(tmp_path):
    body = _call(
        _client(tmp_path, NotConfiguredError("x")), "/api/pinboard", "GET", None
    ).json()
    assert body["error"] == "not_configured"
    assert set(body) == {"error", "message_key", "message"}


def test_every_upstream_message_key_resolves_in_the_base_bundle():
    for key in upstream.UPSTREAM_ERROR_MESSAGE_KEYS.values():
        assert key in BUNDLE, f"{key} is not in frontend/i18n/de.json"
        assert BUNDLE[key].strip()


def test_no_api_route_escapes_the_upstream_error_decision(tmp_path):
    store = Store(tmp_path / "data")
    app = create_app(RaisingService(store, LoginError("x")), wizard=StubWizard())
    declared = {
        route.path for route in app.routes if getattr(route, "path", "").startswith("/api/")
    }
    known = COVERED_ROUTES | set(ROUTES_WITHOUT_UPSTREAM_CALLS)
    assert declared - known == set(), (
        "a new /api route must either answer upstream failures through "
        "read_endpoint/write_endpoint or be listed with a reason"
    )
    assert known - declared == set(), "this list names routes the app no longer serves"
