import inspect

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.iserv.errors import DataError
from app.server import create_app
from app.service import SCHOOL_REQUIRED_KEY, UNKNOWN_CONNECTION_KEY, IServService, SchoolRequiredError
from app.store import Store
from tests.support import SCHOOL_ONE, SCHOOL_TWO, add_school

ALL_SCHOOL_METHODS = {
    "children": "without a school it lists every school on purpose",
    "connection": "accessor by id, no fallback",
}
PLACEHOLDERS = {
    "payload": {},
    "child_ids": [],
    "add_other_parents": False,
    "attachments": None,
    "before": None,
    "confirmed": False,
    "text": "text",
}
ALL_SCHOOL_ROUTES = {
    ("GET", "/api/health"): "names the failing school, asks every school",
    ("GET", "/api/children"): "lists every school without a school",
    ("GET", "/api/modules"): "merges every school without a school",
    ("POST", "/api/wizard/reset"): "targets the wizard session, not a signed-in school",
}
SCHOOL_ROUTES = {
    ("GET", "/api/me"): {},
    ("GET", "/api/absences"): {},
    ("GET", "/api/absences/sick-note-pdf"): {"params": {"id": "7"}},
    ("GET", "/api/absences/attachment/{filename}"): {"path": "/api/absences/attachment/file.pdf"},
    ("GET", "/api/holidays"): {},
    ("GET", "/api/holidays/region-suggestion"): {},
    ("GET", "/api/messenger/room"): {"params": {"id": "!room:school.example"}},
    ("GET", "/api/messenger/teachers"): {"params": {"query": "Beh"}},
    ("GET", "/api/messenger/room/teacher/children"): {},
    ("GET", "/api/messenger/media/{server_name}/{media_id}"): {"path": "/api/messenger/media/school.example/abc"},
    ("GET", "/api/letters/detail"): {"params": {"letter_id": "1", "recipient_id": "2"}},
    ("GET", "/api/letters/attachment/{attachment_id}"): {"path": "/api/letters/attachment/1"},
    ("GET", "/api/pinboard/attachment/{filename}"): {"path": "/api/pinboard/attachment/file.pdf"},
    ("POST", "/api/modules/recheck"): {"json": {}},
    ("POST", "/api/password"): {"json": {"current": "old-secret", "new": "new-secret"}},
    ("POST", "/api/password/repair"): {"json": {"password": "secret"}},
    ("POST", "/api/account/disconnect"): {"json": {}},
    ("POST", "/api/absences"): {"json": {"type": "sick"}},
    ("POST", "/api/absences/delete"): {"json": {"type": "sick", "id": "1"}},
    ("POST", "/api/messenger/send"): {"json": {"room_id": "!room:school.example", "text": "Hallo"}},
    ("POST", "/api/messenger/read"): {"json": {"room_id": "!room:school.example", "event_id": "$e"}},
    ("POST", "/api/messenger/room/teacher"): {"json": {"teacher": "userid:1", "child_ids": ["c1"]}},
    ("POST", "/api/letters/confirm"): {"json": {"letter_id": "1", "recipient_id": "2"}},
    ("POST", "/api/letters/reply"): {"json": {"letter_id": "1", "recipient_id": "2", "text": "Ja", "request_id": "r1"}},
    ("POST", "/api/letters/archive"): {"json": {"letter_id": "1", "recipient_id": "2"}},
    ("POST", "/api/letters/restore"): {"json": {"letter_id": "1", "recipient_id": "2"}},
}
REFUSALS = {SCHOOL_REQUIRED_KEY, UNKNOWN_CONNECTION_KEY}


def untouchable(url):
    raise AssertionError(f"a school was contacted without being named: {url}")


def two_schools(tmp_path, factory=untouchable):
    store = Store(tmp_path / "data")
    first = add_school(store, SCHOOL_ONE)
    second = add_school(store, SCHOOL_TWO)
    return IServService(store, client_factory=factory), first, second


def school_methods():
    found = {}
    for name, member in inspect.getmembers(IServService, inspect.isfunction):
        if name.startswith("_"):
            continue
        parameters = inspect.signature(member).parameters
        if "connection_id" in parameters:
            found[name] = parameters
    return found


def placeholder_arguments(parameters):
    values = {}
    for name, parameter in parameters.items():
        if name in ("self", "connection_id"):
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        values[name] = PLACEHOLDERS.get(name, "x")
    return values


def test_the_guard_knows_every_method_that_takes_a_school():
    methods = school_methods()
    assert set(ALL_SCHOOL_METHODS) <= set(methods)
    assert "pick_school" in methods
    assert len(methods) >= 25


@pytest.mark.parametrize("name", sorted(set(school_methods()) - set(ALL_SCHOOL_METHODS)))
def test_no_school_method_falls_back_to_the_first_school_when_two_are_set_up(tmp_path, name):
    service, _, _ = two_schools(tmp_path)
    method = getattr(service, name)
    with pytest.raises(DataError) as caught:
        method(connection_id=None, **placeholder_arguments(school_methods()[name]))
    assert caught.value.message_key in REFUSALS


def test_without_a_school_two_schools_ask_for_one(tmp_path):
    service, _, _ = two_schools(tmp_path)
    with pytest.raises(SchoolRequiredError) as caught:
        service.pick_school(None)
    assert caught.value.message_key == SCHOOL_REQUIRED_KEY


def test_a_named_school_is_used_even_when_it_is_the_second(tmp_path):
    service, _, second = two_schools(tmp_path)
    assert service.pick_school(second).id == second


def test_a_single_school_stays_implicit(tmp_path):
    store = Store(tmp_path / "data")
    only = add_school(store, SCHOOL_ONE)
    service = IServService(store, client_factory=untouchable)
    assert service.pick_school(None).id == only
    assert service.pick_school("").id == only


def test_a_school_still_being_set_up_does_not_make_the_first_school_ambiguous(tmp_path):
    store = Store(tmp_path / "data")
    only = add_school(store, SCHOOL_ONE)
    add_school(store, SCHOOL_TWO, complete=False)
    service = IServService(store, client_factory=untouchable)
    assert service.pick_school(None).id == only


def endpoint_source(endpoint):
    parts = [inspect.getsource(endpoint)]
    for helper in inspect.getclosurevars(endpoint).nonlocals.values():
        if inspect.isfunction(helper):
            parts.append(inspect.getsource(helper))
    return "\n".join(parts)


def school_route_keys(app):
    found = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path_names = {param.name for param in route.dependant.path_params}
        query_names = {param.name for param in route.dependant.query_params}
        source = endpoint_source(route.endpoint)
        if "connection_id" in path_names:
            continue
        if "connection" in query_names or "connection_id" in source:
            for method in route.methods:
                found.add((method, route.path))
    return found


def app_of(service):
    return create_app(service, region_suggester=None)


def test_the_guard_knows_every_route_that_takes_a_school(tmp_path):
    service, _, _ = two_schools(tmp_path)
    found = school_route_keys(app_of(service))
    assert found - set(ALL_SCHOOL_ROUTES) == set(SCHOOL_ROUTES)


def call(client, key, extra=None):
    method, path = key
    spec = dict(SCHOOL_ROUTES[key])
    url = spec.pop("path", path)
    params = dict(spec.pop("params", {}), **(extra or {}).get("params", {}))
    if method == "GET":
        return client.get(url, params=params)
    body = dict(spec.pop("json", {}), **(extra or {}).get("json", {}))
    return client.post(url, params=params, json=body)


@pytest.mark.parametrize("key", sorted(SCHOOL_ROUTES), ids=lambda key: f"{key[0]} {key[1]}")
def test_no_school_route_falls_back_to_the_first_school_when_two_are_set_up(tmp_path, key):
    service, _, _ = two_schools(tmp_path)
    response = call(TestClient(app_of(service), raise_server_exceptions=True), key)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = response.json()
        assert body.get("message_key") in REFUSALS, body
        if body["message_key"] == SCHOOL_REQUIRED_KEY:
            assert body.get("error") == "school_required", body
    else:
        assert response.status_code == 400, response.text


def test_sick_note_pdf_without_a_school_answers_school_required(tmp_path):
    service, _, _ = two_schools(tmp_path)
    response = call(TestClient(app_of(service), raise_server_exceptions=True), ("GET", "/api/absences/sick-note-pdf"))
    assert (response.status_code, response.text) == (400, "school required")


FIXTURE_GUARD_SCRIPT = """
import inspect, json
from app.iserv.errors import DataError
from app.store import Store
from tests import e2e_fixture_app as fixture
from tests.test_school_scope import PLACEHOLDERS

ACCESSORS = {"connection", "known_connection", "pick_school", "children", "_raw_children", "_course_config"}
outcome = {}
token = fixture.SCHOOLS.set("2")
for owner in (fixture.FixtureService, fixture.MatrixService):
    service = owner(Store(fixture.E2E_DATA_DIR / owner.__name__))
    for name, member in inspect.getmembers(owner, inspect.isfunction):
        parameters = inspect.signature(member).parameters
        if "connection_id" not in parameters or name in ACCESSORS:
            continue
        values = {
            key: PLACEHOLDERS.get(key, "x")
            for key, parameter in parameters.items()
            if key not in ("self", "connection_id") and parameter.default is inspect.Parameter.empty
        }
        try:
            getattr(service, name)(connection_id=None, **values)
            outcome[owner.__name__ + "." + name] = "answered"
        except DataError as error:
            outcome[owner.__name__ + "." + name] = error.message_key
fixture.SCHOOLS.reset(token)
print(json.dumps(outcome))
"""


def test_the_e2e_fixture_refuses_school_actions_without_a_school_like_the_service(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    run = subprocess.run(
        [sys.executable, "-c", FIXTURE_GUARD_SCRIPT],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, ISERV_E2E_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    outcome = json.loads(run.stdout.strip().splitlines()[-1])
    for name in ("sick_note_pdf", "delete_absence", "messenger_send", "messenger_media", "recheck_modules"):
        assert f"FixtureService.{name}" in outcome
    assert {name: key for name, key in outcome.items() if key not in REFUSALS} == {}


def test_the_frontend_route_guard_watches_every_school_route():
    import re
    from pathlib import Path

    guard = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "schoolRoutes.test.js"
    listed = set(re.findall(r'^\s+"(api/[^"]+)",$', guard.read_text(encoding="utf-8"), re.MULTILINE))
    wanted = {path.lstrip("/").split("/{")[0] for _, path in SCHOOL_ROUTES}
    assert wanted == listed
