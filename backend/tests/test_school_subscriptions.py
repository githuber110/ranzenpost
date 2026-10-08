import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import feed, subscriptions
from app.integration_api import IntegrationAccess
from app.server import create_app
from app.store import Store
from app.subscriptions import SubscriptionError, SubscriptionRegistry
from tests.test_calendar_feed import (
    CHILD_ID,
    CHILD_NAME,
    CONNECTION_ID,
    NOW,
    FakeHolidayCalendar,
    _build,
    _day,
    _lesson,
    _snapshot,
    _uids,
)
from tests.test_integration_api import PREFIX, Clock, FakeService, _auth

FAMILY_SCHOOL = "f0e1d2c3"
FAMILY_SCHOOL_NAME = "Lindenhof School"
OTHER_SCHOOL_NAME = "Brookside School"
SCHOOL_EVENT_TITLE = "Autumn fair"
WEBHOOK = re.compile(r"^ranzenpost_[0-9a-f]{32}$")
SCHOOL_PARTS = ["school_holidays", "public_holidays", "school_events"]
LESSON = "Zaubertrank"
CHILD_PARTS = ["timetable", "marks", "absences", "own_entries"]


@pytest.fixture(autouse=True)
def _no_supervisor(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("ISERV_ADDON_VERSION", "2609.02.00")


def _school_event(title=SCHOOL_EVENT_TITLE, start="2026-09-10T18:00:00+02:00"):
    return {
        "uid": f"{title}@school.example",
        "title": title,
        "start": start,
        "end": "2026-09-10T20:00:00+02:00",
        "all_day": False,
        "location": "Hall",
        "calendar": "School",
        "category": "",
        "description": "",
    }


def _family_store(tmp_path, with_child_school=True, calendar=True):
    store = Store(tmp_path / "data")
    if with_child_school:
        store.add_connection(
            "https://school-one.example",
            connection_id=CONNECTION_ID,
            setup_complete=True,
            school_name=OTHER_SCHOOL_NAME,
            holiday_region="DE-NI",
            children=[{"child_id": CHILD_ID.split(":", 1)[1], "name": CHILD_NAME, "class_name": "5A"}],
        )
    store.add_connection(
        "https://lindenhof.example",
        connection_id=FAMILY_SCHOOL,
        setup_complete=True,
        school_name=FAMILY_SCHOOL_NAME,
        holiday_region="DE-NI",
        children=[],
    )
    if calendar:
        store.connection_store(FAMILY_SCHOOL).save_modules({"modules": {"calendar": True}})
    return store


def _with_school_events(store, school_id=FAMILY_SCHOOL, events=None):
    snapshot = store.load_calendar_snapshot()
    snapshot.setdefault("schools", {})[school_id] = {"events": events or [_school_event()], "last_success": 1}
    store.save_calendar_snapshot(snapshot)


def _holidays():
    span = {
        day.isoformat(): _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="p9")
        for day in (date(2026, 10, 12) + timedelta(days=offset) for offset in range(5))
    }
    span["2026-10-03"] = _day(free=True, overrides=True, kind="public", name="Tag der Deutschen Einheit", period_id="u1")
    return FakeHolidayCalendar(days=span)


def test_a_school_subscription_needs_no_child(tmp_path):
    store = _family_store(tmp_path, with_child_school=False)

    view = SubscriptionRegistry(store).create("", ["school_events", "school_holidays"], school_id=FAMILY_SCHOOL)

    assert view["child_key"] == ""
    assert view["school_id"] == FAMILY_SCHOOL
    assert view["components"] == ["school_holidays", "school_events"]
    assert view["label"] == ""
    stored = store.load_calendar_subscriptions()["subscriptions"][0]
    assert (stored["child_key"], stored["school_id"]) == ("", FAMILY_SCHOOL)
    assert len(stored["token"]) >= 43


@pytest.mark.parametrize("part", CHILD_PARTS)
def test_a_school_subscription_refuses_every_child_part(tmp_path, part):
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store)

    with pytest.raises(SubscriptionError) as error:
        registry.create("", ["school_holidays", part], school_id=FAMILY_SCHOOL)

    assert error.value.message_key == subscriptions.ERROR_COMPONENTS
    assert store.load_calendar_subscriptions().get("subscriptions", []) == []


@pytest.mark.parametrize("school", ["nope", CHILD_ID])
def test_a_school_subscription_refuses_an_unknown_school(tmp_path, school):
    registry = SubscriptionRegistry(_family_store(tmp_path))

    with pytest.raises(SubscriptionError) as error:
        registry.create("", ["school_holidays"], school_id=school)

    assert error.value.message_key == subscriptions.ERROR_SCHOOL


def test_changing_a_school_subscription_keeps_to_school_parts(tmp_path):
    registry = SubscriptionRegistry(_family_store(tmp_path))
    view = registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL)

    with pytest.raises(SubscriptionError) as error:
        registry.update(view["id"], components=["timetable"])
    changed = registry.update(view["id"], components=["public_holidays", "school_events"])

    assert error.value.message_key == subscriptions.ERROR_COMPONENTS
    assert changed["components"] == ["public_holidays", "school_events"]
    assert changed["school_id"] == FAMILY_SCHOOL


def test_a_child_subscription_still_needs_a_known_child_and_may_add_school_events(tmp_path):
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store)

    with pytest.raises(SubscriptionError) as error:
        registry.create("", ["school_holidays"])
    view = registry.create(CHILD_ID, ["timetable", "school_events"])

    assert error.value.message_key == subscriptions.ERROR_CHILD
    assert view["components"] == ["timetable", "school_events"]
    assert view["school_id"] == CONNECTION_ID
    assert "school_id" not in store.load_calendar_subscriptions()["subscriptions"][0]


def test_the_school_feed_carries_holidays_and_school_events_without_child_data(tmp_path):
    store = _family_store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(subject_code="ZT", subject_label=LESSON)]))
    _with_school_events(store)
    view = SubscriptionRegistry(store).create("", SCHOOL_PARTS, school_id=FAMILY_SCHOOL)

    ics = _build(store, view, _holidays())

    assert f"X-WR-CALNAME:Ranzenpost – {FAMILY_SCHOOL_NAME}" in ics
    assert f"SUMMARY:{SCHOOL_EVENT_TITLE}" in ics
    assert "SUMMARY:Herbstferien" in ics
    assert "SUMMARY:Tag der Deutschen Einheit" in ics
    assert LESSON not in ics
    for part in CHILD_NAME.split():
        assert part.casefold() not in ics.casefold()
    assert CHILD_ID.split(":", 1)[1] not in ics


def test_a_school_feed_never_shows_child_parts_even_if_stored_by_hand(tmp_path):
    store = _family_store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(subject_code="ZT", subject_label=LESSON)], child_id=""))
    store.save_calendar_subscriptions(
        {
            "subscriptions": [
                {
                    "id": "forged",
                    "child_key": "",
                    "school_id": CONNECTION_ID,
                    "label": "",
                    "components": ["timetable", "marks", "absences", "own_entries", "school_holidays"],
                    "color": "",
                    "token": "z" * 43,
                    "created_at": 1,
                    "rotated_at": 0,
                }
            ]
        }
    )
    entry = SubscriptionRegistry(store).find_by_token("z" * 43)

    ics = _build(store, entry, _holidays())

    assert LESSON not in ics
    assert "SUMMARY:Herbstferien" in ics
    assert f"X-WR-CALNAME:Ranzenpost – {OTHER_SCHOOL_NAME}" in ics


def test_a_school_without_stored_calendar_entries_gets_no_invented_events(tmp_path):
    store = _family_store(tmp_path, calendar=False)
    _with_school_events(store, school_id=CONNECTION_ID)
    view = SubscriptionRegistry(store).create("", ["school_events"], school_id=FAMILY_SCHOOL)

    ics = _build(store, view)

    assert "BEGIN:VEVENT" not in ics


def test_a_child_subscription_shows_the_events_of_the_child_school_only(tmp_path):
    store = _family_store(tmp_path)
    _with_school_events(store, school_id=CONNECTION_ID, events=[_school_event("Sports day")])
    _with_school_events(store, school_id=FAMILY_SCHOOL, events=[_school_event("Lindenhof concert")])
    view = SubscriptionRegistry(store).create(CHILD_ID, ["school_events"])

    ics = _build(store, view)

    assert "SUMMARY:Sports day" in ics
    assert "Lindenhof concert" not in ics


def test_two_school_subscriptions_keep_their_own_holiday_uids_across_a_new_link(tmp_path):
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store)
    first = registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL)
    second = registry.create("", ["school_holidays"], school_id=CONNECTION_ID)

    first_uids = _uids(_build(store, first, _holidays()))
    second_uids = _uids(_build(store, second, _holidays()))
    rotated = registry.rotate(first["id"])

    assert first_uids and second_uids
    assert set(first_uids).isdisjoint(second_uids)
    assert _uids(_build(store, rotated, _holidays())) == first_uids


def test_the_holiday_uids_of_home_assistant_stay_as_they_were(tmp_path):
    events = feed.build_events(
        {"child_key": "", "school_id": FAMILY_SCHOOL, "components": ["school_holidays"]},
        {"language": "de"},
        {},
        _holidays().range_info(date(2026, 8, 17), date(2027, 9, 2))["days"],
        False,
        NOW.date(),
        0,
    )

    assert events
    assert all(event.uid.startswith(feed.child_tag("")) for event in events)


def test_disconnecting_a_school_removes_its_school_subscriptions_only(tmp_path):
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store)
    gone = registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL)
    kept_school = registry.create("", ["school_holidays"], school_id=CONNECTION_ID)
    kept_child = registry.create(CHILD_ID, ["school_holidays"])

    store.remove_connection(FAMILY_SCHOOL)

    remaining = [entry["id"] for entry in registry.list()]
    assert gone["id"] not in remaining
    assert remaining == [kept_school["id"], kept_child["id"]]
    assert registry.find_by_token(gone["token"]) is None


def test_moving_a_child_leaves_school_subscriptions_alone(tmp_path):
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store)
    school = registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL)

    assert registry.move_child(CHILD_ID, f"{CONNECTION_ID}:child-uuid-z") == 0
    assert registry.list()[0]["child_key"] == ""
    assert registry.list()[0]["school_id"] == FAMILY_SCHOOL
    assert school["id"] not in registry.children_with_component("school_holidays")


def _app(tmp_path):
    clock = Clock()
    store = _family_store(tmp_path)
    registry = SubscriptionRegistry(store, clock=clock)
    access = IntegrationAccess(store, clock=clock, announce=lambda token: None)
    app = create_app(
        FakeService(store),
        holiday_calendar=_holidays(),
        registry=registry,
        integration_access=access,
        calendar_warmer=lambda child_id: None,
    )
    return TestClient(app, raise_server_exceptions=False), store, registry


def test_the_api_creates_a_school_subscription_from_a_school_id(tmp_path):
    client, _, registry = _app(tmp_path)

    response = client.post(
        "/api/calendar/subscriptions", json={"school_id": FAMILY_SCHOOL, "components": SCHOOL_PARTS}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["child_key"], body["school_id"], body["components"]) == ("", FAMILY_SCHOOL, SCHOOL_PARTS)
    assert [entry["id"] for entry in registry.list()] == [body["id"]]


@pytest.mark.parametrize(
    "body, key",
    [
        ({"school_id": "nope", "components": ["school_holidays"]}, "api.calendar.error.school"),
        ({"school_id": FAMILY_SCHOOL, "components": ["timetable"]}, "api.calendar.error.components"),
        ({"school_id": FAMILY_SCHOOL, "components": []}, "api.calendar.error.components"),
        ({"components": ["school_holidays"]}, "api.calendar.error.child"),
    ],
)
def test_the_api_refuses_a_school_subscription_it_cannot_serve(tmp_path, body, key):
    client, _, registry = _app(tmp_path)

    response = client.post("/api/calendar/subscriptions", json=body)

    assert response.status_code == 400
    assert response.json()["message_key"] == key
    assert registry.list() == []


def test_the_listing_says_which_school_offers_school_events(tmp_path):
    client, _, _ = _app(tmp_path)

    body = client.get("/api/calendar/subscriptions").json()

    assert body["school_events"] == {CONNECTION_ID: False, FAMILY_SCHOOL: True}
    assert "school_events" in body["components"]


def test_a_school_subscription_works_through_home_assistant(tmp_path):
    client, store, registry = _app(tmp_path)
    view = registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL, online=True)

    feeds = client.get(PREFIX + "/info", headers=_auth(store)).json()["online_feeds"]
    webhook = next(item["webhook_id"] for item in feeds if item["id"] == view["id"])
    answer = client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": webhook}, headers=_auth(store))
    renewed = registry.rotate(view["id"])
    new_webhook = next(item["webhook_id"] for item in registry.online_feeds() if item["id"] == view["id"])
    stale = client.get(PREFIX + "/feed", params={"id": view["id"], "webhook": webhook}, headers=_auth(store))

    assert WEBHOOK.match(webhook) and WEBHOOK.match(new_webhook) and new_webhook != webhook
    assert answer.status_code == 200
    assert "SUMMARY:Herbstferien" in answer.json()["calendar"].replace("\r\n ", "")
    assert f"Ranzenpost – {FAMILY_SCHOOL_NAME}" in answer.json()["calendar"].replace("\r\n ", "")
    assert renewed["token"] != view["token"]
    assert stale.status_code == 404

    assert client.delete(f"/api/calendar/subscriptions/{view['id']}").status_code == 200
    assert registry.online_feeds() == []


def test_a_school_still_in_its_setup_gets_no_subscription(tmp_path):
    store = _family_store(tmp_path, with_child_school=False)
    store.add_connection("https://pending.example", connection_id="pending01", setup_complete=False, children=[])

    with pytest.raises(SubscriptionError) as error:
        SubscriptionRegistry(store).create("", ["school_holidays"], school_id="pending01")

    assert error.value.message_key == subscriptions.ERROR_SCHOOL
    assert store.load_calendar_subscriptions().get("subscriptions", []) == []


def test_a_school_removed_before_the_write_gets_no_orphan_subscription(tmp_path):
    store = _family_store(tmp_path, with_child_school=False)
    registry = SubscriptionRegistry(store)
    original = registry._store_new

    def store_after_disconnect(*args, **kwargs):
        store.remove_connection(FAMILY_SCHOOL)
        return original(*args, **kwargs)

    registry._store_new = store_after_disconnect
    with pytest.raises(SubscriptionError):
        registry.create("", ["school_holidays"], school_id=FAMILY_SCHOOL)
    assert store.load_calendar_subscriptions().get("subscriptions", []) == []
