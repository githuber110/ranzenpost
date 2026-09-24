import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app import integration, integration_api
from app.cancellations import CancellationRegistry
from app.marks import MarkRegistry

from tests.test_calendar_feed import FakeHolidayCalendar, _day
from tests.test_integration_state import SATURDAY_EPOCH, _saturday_snapshot
from tests.test_integration_api import (
    CHILD_ID,
    CHILD_QUERY,
    NOW_EPOCH,
    PREFIX,
    SCHOOL,
    SECOND_CHILD_ID,
    Clock,
    FakeService,
    _app,
    _auth,
    _store,
    _today_snapshot,
)

CONTRACT = Path(__file__).resolve().parents[2] / "custom_components" / "ranzenpost" / "contract.json"
ROUTES = ("/api/integration/info", "/api/integration/state", "/api/integration/events", "/api/integration/school", "/api/integration/changes")


def contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def validator_for(reference):
    document = contract()
    schema = {"$ref": reference, "$defs": document["$defs"]}
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def errors_of(reference, payload):
    return [error.message for error in validator_for(reference).iter_errors(payload)]


def assert_matches(reference, payload):
    assert errors_of(reference, payload) == [], json.dumps(payload, ensure_ascii=False)[:400]


def test_the_contract_is_a_valid_draft_2020_12_schema():
    document = contract()

    Draft202012Validator.check_schema(document)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_the_contract_names_exactly_the_routes_the_app_serves(tmp_path):
    document = contract()
    client, _, _ = _app(tmp_path)
    served = {
        getattr(route, "path", "")
        for route in client.app.routes
        if getattr(route, "path", "").startswith(integration_api.PREFIX + "/")
    }

    assert set(document["routes"]) == served == set(ROUTES) == set(integration_api.ROUTES)
    for route in ROUTES:
        assert document["routes"][route]["$ref"].startswith("#/$defs/")


def test_the_contract_lists_the_query_parameters_the_routes_read():
    document = contract()

    assert document["routes"]["/api/integration/state"]["query"] == ["child"]
    assert document["routes"]["/api/integration/events"]["query"] == ["child", "kind", "start", "end", "school", "purpose"]
    assert document["routes"]["/api/integration/school"]["query"] == ["id"]
    assert document["$defs"]["eventKind"]["enum"] == sorted(integration.EVENT_COMPONENTS, key=list(integration.EVENT_COMPONENTS).index)
    assert document["$defs"]["purpose"]["enum"] == list(integration.PURPOSES)
    assert integration_api.ERROR_BAD_PURPOSE in document["$defs"]["error"]["properties"]["error"]["enum"]


def test_the_contract_and_the_backend_agree_on_the_change_kinds():
    assert contract()["$defs"]["change"]["properties"]["kind"]["enum"] == list(integration.CHANGE_KINDS)
    assert contract()["$defs"]["changeKind"]["enum"] == list(integration.CHANGE_KINDS)
    assert contract()["$defs"]["changes"]["maxItems"] == integration.MAX_CHANGES


def test_the_contract_and_the_backend_agree_on_the_state_limits():
    document = contract()
    assert document["$defs"]["weekday"]["enum"] == list(integration.WEEKDAYS)
    assert document["$defs"]["notices"]["properties"]["items"]["maxItems"] == integration.MAX_NOTICES
    assert document["$defs"]["state"]["properties"]["exams_upcoming"]["properties"]["days"]["const"] == integration.EXAM_DAYS_AHEAD
    assert set(document["$defs"]["changedFields"]["properties"]) == set(integration.CHANGE_FIELDS)
    assert document["$defs"]["state"]["properties"]["timetable_last_updated_source"]["enum"] == [
        integration.STAMP_SOURCE_ISERV,
        integration.STAMP_SOURCE_APP,
        "",
    ]


def _filled(tmp_path, calendar=None):
    client, store, access = _app(tmp_path, calendar=calendar)
    _today_snapshot(store)
    CancellationRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-02", 3)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-03", 2, "D", "Diktat")
    integration.record_poll(
        store,
        NOW_EPOCH - 60,
        True,
        changes=[
            {
                "child_key": CHILD_ID,
                "school_id": SCHOOL,
                "at": "2026-09-02T08:00:00+02:00",
                "kind": "cancellation",
                "summary": "Ausfall: 4. Sport (Klein)",
                "date": "2026-09-02",
                "period": 4,
                "new": True,
            }
        ],
    )
    integration.record_school_poll(
        store,
        SCHOOL,
        NOW_EPOCH - 60,
        True,
        letters=["Wandertag"],
        posts=["Mensa"],
        conferences=[["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"]],
        school_name="Testschule",
    )
    return client, store


def test_info_matches_the_contract_filled_and_empty(tmp_path):
    client, store = _filled(tmp_path)
    assert_matches("#/$defs/info", client.get(PREFIX + "/info", headers=_auth(store)).json())

    bare_store = _store(tmp_path / "bare")
    client, _, _ = _app(tmp_path, store=bare_store, service=FakeService(bare_store, configured=False))
    assert_matches("#/$defs/info", client.get(PREFIX + "/info", headers=_auth(bare_store)).json())


def test_state_matches_the_contract_filled_and_empty(tmp_path):
    client, store = _filled(tmp_path)
    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    assert body["now_lesson"] is not None
    assert body["changes_today"]
    assert body["open_absences"]["items"]
    assert_matches("#/$defs/state", body)

    empty = client.get(PREFIX + f"/state?child={SECOND_CHILD_ID}", headers=_auth(store)).json()
    assert empty["now_lesson"] is None
    assert_matches("#/$defs/state", empty)


def test_state_on_a_saturday_night_matches_the_contract(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(SATURDAY_EPOCH))
    _saturday_snapshot(store)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"] is None
    assert body["next_lesson"]["weekday"] == "monday"
    assert body["next_school_day"]["days_until"] == 2
    assert body["next_exam"]["name"] == "Klassenarbeit"
    assert body["unread_letters"]["items"][0]["child"]
    assert_matches("#/$defs/state", body)


def test_state_at_night_matches_the_contract(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(NOW_EPOCH + 16 * 60 * 60))
    _today_snapshot(store)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"] is None
    assert body["next_lesson"]["start"].startswith("2026-09-03")
    assert_matches("#/$defs/state", body)


@pytest.mark.parametrize("kind", ["lessons", "exams", "absences"])
def test_child_events_match_the_contract(tmp_path, kind):
    client, store = _filled(tmp_path)

    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind={kind}", headers=_auth(store)).json()

    assert body, kind
    assert_matches("#/$defs/events", body)


def test_holiday_events_match_the_contract(tmp_path):
    calendar = FakeHolidayCalendar(
        days={
            "2026-10-05": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1"),
            "2026-10-03": _day(free=True, overrides=True, kind="public", name="Tag der Deutschen Einheit"),
        }
    )
    client, store = _filled(tmp_path, calendar=calendar)

    body = client.get(PREFIX + f"/events?kind=holidays&school={SCHOOL}&start=2026-10-01&end=2026-10-31", headers=_auth(store)).json()

    assert len(body) == 2
    assert_matches("#/$defs/events", body)


def test_lesson_events_mix_timed_and_all_day_entries_and_still_match(tmp_path):
    calendar = FakeHolidayCalendar(days={"2026-09-04": _day(free=True, overrides=True, kind="public", name="Frei")})
    client, store = _filled(tmp_path, calendar=calendar)
    store.save_calendar_snapshot({"children": {CHILD_ID: {"weeks": {"31.08.2026": {"start_date": "31.08.2026", "end_date": "06.09.2026", "lessons": [{"date": "02.09.2026", "period": 1, "subject_code": "D", "subject_label": "Deutsch", "teacher_code": "BEH", "teacher_label": "Behrens", "room": "R1", "change_kind": "", "changed_fields": [], "previous": {}, "start_time": ""}]}}, "last_success": 0}}})
    store.update_connection(SCHOOL, period_times={})

    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons", headers=_auth(store)).json()

    assert any(event["all_day"] for event in body)
    assert_matches("#/$defs/events", body)


def test_school_matches_the_contract_filled_and_empty(tmp_path):
    calendar = FakeHolidayCalendar(days={"2026-10-05": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1")})
    client, store = _filled(tmp_path, calendar=calendar)
    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()
    assert body["next_holiday"] and body["next_conference"]
    assert_matches("#/$defs/school", body)

    client, store, _ = _app(tmp_path / "empty")
    assert_matches("#/$defs/school", client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json())


def test_info_with_two_schools_matches_the_contract(tmp_path):
    store = _store(tmp_path, schools=2)
    client, _, _ = _app(tmp_path, store=store)
    body = client.get(PREFIX + "/info", headers=_auth(store)).json()
    assert len(body["schools"]) == 2
    assert_matches("#/$defs/info", body)


def test_lesson_and_exam_events_carry_the_subject_fields(tmp_path):
    client, store = _filled(tmp_path)
    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-02&end=2026-09-02", headers=_auth(store)).json()
    exams = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=exams", headers=_auth(store)).json()
    timed = [event for event in lessons if not event["all_day"]]
    assert [event["subject_code"] for event in timed] == ["D", "EN", "MA", "SP"]
    assert timed[0]["subject"] == "Deutsch"
    assert exams[0]["subject_code"] == "D"
    assert exams[0]["subject"] == "Deutsch"
    holidays_body = client.get(PREFIX + f"/events?kind=holidays&school={SCHOOL}", headers=_auth(store)).json()
    assert all(event["subject_code"] == "" and event["subject"] == "" for event in holidays_body)


def test_changes_match_the_contract(tmp_path):
    client, store = _filled(tmp_path)

    body = client.get(PREFIX + "/changes", headers=_auth(store)).json()

    assert body
    assert_matches("#/$defs/changes", body)


def test_every_refusal_matches_the_error_shape(tmp_path):
    client, store, _ = _app(tmp_path)
    responses = [
        client.get(PREFIX + "/info"),
        client.get(PREFIX + "/info", headers={"Authorization": "Bearer " + "x" * 43}),
        client.get(PREFIX + "/info", headers=dict(_auth(store), **{"X-Ingress-Path": "/x"})),
        client.get(PREFIX + "/state?child=nobody", headers=_auth(store)),
        client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=nothing", headers=_auth(store)),
        client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=bad", headers=_auth(store)),
    ]

    for response in responses:
        assert response.status_code in (400, 401, 403, 404)
        assert_matches("#/$defs/error", response.json())


def test_the_contract_still_catches_a_planted_deviation():
    good = {"count": 0, "items": []}
    notice = {"title": "t", "sender": "", "date": "", "child": ""}
    assert errors_of("#/$defs/notices", good) == []
    assert errors_of("#/$defs/notices", {"count": "0", "items": []})
    assert errors_of("#/$defs/notices", {"count": 0})
    assert errors_of("#/$defs/notices", {"count": 0, "items": [], "extra": 1})
    assert errors_of("#/$defs/notices", {"count": 0, "items": [dict(notice, date="1.9.2026")]})
    assert errors_of("#/$defs/notices", {"count": 11, "items": [notice] * 11})
    assert errors_of("#/$defs/lesson", {"date": "2026-09-02", "weekday": "Wednesday"})
    assert errors_of("#/$defs/datetime", "2026-09-02T08:00:00Z")
    assert errors_of("#/$defs/datetime", "2026-09-02T08:00:00+02:00") == []
    assert errors_of("#/$defs/event", {"uid": "u", "summary": "", "description": "", "location": "", "start": "2026-09-02", "end": "2026-09-03", "all_day": False, "cancelled": False, "color": ""})


OWN_ENTRIES = [
    {"id": "a1", "type": "appointment", "name": "Dentist", "start": "16:00", "duration": 30, "repeat": "once", "days": [], "interval": 1, "date": "2026-09-02", "from": "", "until": "", "holidays": True, "child": CHILD_ID.split(":", 1)[1]},
    {"id": "p1", "type": "pause", "name": "Snack", "start": "17:00", "duration": 15, "repeat": "once", "days": [], "interval": 1, "date": "2026-09-02", "from": "", "until": "", "holidays": True, "child": ""},
]


@pytest.mark.parametrize("shared", [False, True])
def test_own_entries_reach_home_assistant_only_with_the_setting(tmp_path, shared):
    client, store = _filled(tmp_path)
    store.update_connection(SCHOOL, own_entries=OWN_ENTRIES, own_entries_ha=shared)
    info = client.get(PREFIX + "/info", headers=_auth(store)).json()
    assert info["schools"][0]["own_entries"] is shared
    assert_matches("#/$defs/info", info)
    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=own_entries&start=2026-09-01&end=2026-09-05", headers=_auth(store)).json()
    assert_matches("#/$defs/events", body)
    if not shared:
        assert body == []
        return
    assert [(event["summary"], event["start"], event["end"], event["kind"]) for event in body] == [
        ("Dentist", "2026-09-02T16:00:00+02:00", "2026-09-02T16:30:00+02:00", "own_entries")
    ]
    lessons = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons", headers=_auth(store)).json()
    assert all(event["kind"] != "own_entries" for event in lessons)


def test_own_entries_of_another_school_never_ride_along_with_the_school_parameter(tmp_path):
    client, store = _filled(tmp_path)
    store.update_connection(SCHOOL, own_entries=[], own_entries_ha=True)
    other = store.add_connection("https://other.example.test/iserv", connection_id="e5f6a7b8", setup_complete=True, own_entries=[dict(OWN_ENTRIES[0], child="")])
    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=own_entries&start=2026-09-01&end=2026-09-05&school={other['id']}", headers=_auth(store)).json()
    assert body == []


@pytest.mark.parametrize("shared", [False, True])
def test_the_card_gets_clubs_and_appointments_whatever_the_setting(tmp_path, shared):
    client, store = _filled(tmp_path)
    store.update_connection(SCHOOL, own_entries=OWN_ENTRIES, own_entries_ha=shared)
    query = f"/events?{CHILD_QUERY}&kind=own_entries&start=2026-09-01&end=2026-09-05"
    card = client.get(PREFIX + query + "&purpose=card", headers=_auth(store)).json()
    assert_matches("#/$defs/events", card)
    assert [(event["summary"], event["start"], event["kind"]) for event in card] == [("Dentist", "2026-09-02T16:00:00+02:00", "own_entries")]
    calendar = client.get(PREFIX + query + "&purpose=calendar", headers=_auth(store)).json()
    assert calendar == (card if shared else [])
    assert client.get(PREFIX + query, headers=_auth(store)).json() == calendar


def test_the_card_purpose_keeps_every_guard_of_the_events_route(tmp_path):
    client, store = _filled(tmp_path)
    store.update_connection(SCHOOL, own_entries=OWN_ENTRIES)
    other = store.add_connection("https://other.example.test/iserv", connection_id="e5f6a7b8", setup_complete=True, own_entries=[dict(OWN_ENTRIES[0], child="", name="Other school")])
    query = "/events?kind=own_entries&start=2026-09-01&end=2026-09-05&purpose=card"
    assert client.get(PREFIX + query + f"&{CHILD_QUERY}").status_code == 401
    assert client.get(PREFIX + query + f"&{CHILD_QUERY}", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ingress = client.get(PREFIX + query + f"&{CHILD_QUERY}", headers={**_auth(store), "X-Ingress-Path": "/api/hassio_ingress/x"})
    assert ingress.status_code == 403
    for child in ("", f"{SCHOOL}:nobody", f"{other['id']}:child-uuid-a", "child-uuid-a"):
        refused = client.get(PREFIX + query + f"&child={child}", headers=_auth(store))
        assert refused.status_code == 404, child
        assert_matches("#/$defs/error", refused.json())
    body = client.get(PREFIX + query + f"&{CHILD_QUERY}&school={other['id']}", headers=_auth(store)).json()
    assert [event["summary"] for event in body] == ["Dentist"]
    wrong = client.get(PREFIX + query.replace("purpose=card", "purpose=automation") + f"&{CHILD_QUERY}", headers=_auth(store))
    assert wrong.status_code == 400 and wrong.json()["error"] == "bad_purpose"
    assert_matches("#/$defs/error", wrong.json())
