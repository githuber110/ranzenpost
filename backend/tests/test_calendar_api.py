from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import feed, holidays
from app.poller import Poller
from app.server import create_app
from app.store import Store
from app.subscriptions import SubscriptionRegistry

CHILD_ID = "child-uuid-a"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
NOW_EPOCH = int(datetime(2026, 9, 2, 6, 0).replace(tzinfo=timezone.utc).timestamp())


class FakeService:
    def __init__(self, store):
        self.store = store
        self.calls = []

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def children(self):
        return [{"child_id": CHILD_ID, "name": CHILD_NAME}]

    def timetable(self, child_id, week_offset=0):
        self.calls.append((child_id, week_offset))
        start = ["31.08.2026", "07.09.2026", "14.09.2026", "21.09.2026"][week_offset]
        return {
            "last_updated": "02.09.2026 06:00",
            "start_date": start,
            "end_date": start,
            "lessons": [
                {
                    "date": "02.09.2026",
                    "day_of_week": 3,
                    "period": 1,
                    "start_time": "08:00",
                    "subject_code": "D",
                    "subject_label": "Deutsch",
                    "color": "#0e6b70",
                    "teacher_code": "BEH",
                    "teacher_label": "Behrens",
                    "is_class_teacher": False,
                    "room": "R1",
                    "change_kind": "",
                    "changed_fields": [],
                    "previous": {"subject": "", "teacher": "", "room": ""},
                }
            ],
            "changes": [],
        }


class CountingHolidays:
    def __init__(self):
        self.calls = 0

    def range_info(self, start, end, config=None):
        self.calls += 1
        return {"status": holidays.STATUS_OK, "stale": False, "days": {}, "periods": []}


def _store(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["holiday_region"] = "DE-NI"
    config["children"] = [{"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"}]
    store.save_config(config)
    return store


def _api(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    client = TestClient(create_app(FakeService(store), registry=registry), raise_server_exceptions=False)
    return client, store, registry


def test_the_api_creates_lists_updates_rotates_and_revokes(tmp_path):
    client, store, registry = _api(tmp_path)

    created = client.post(
        "/api/calendar/subscriptions",
        json={"child_id": CHILD_ID, "components": ["timetable", "school_holidays"], "label": "5A"},
    ).json()
    assert created["label"] == "5A"
    assert created["path"] == f"/calendar/{created['token']}.ics"

    listing = client.get("/api/calendar/subscriptions").json()
    assert [entry["id"] for entry in listing["subscriptions"]] == [created["id"]]
    assert listing["path_template"] == "/calendar/{token}.ics"
    assert listing["port"] == 8100
    assert listing["components"] == [
        "timetable",
        "school_holidays",
        "public_holidays",
        "marks",
        "absences",
    ]

    updated = client.post(
        f"/api/calendar/subscriptions/{created['id']}", json={"components": ["public_holidays"]}
    ).json()
    assert updated["components"] == ["public_holidays"]
    assert updated["token"] == created["token"]

    rotated = client.post(f"/api/calendar/subscriptions/{created['id']}/rotate").json()
    assert rotated["token"] != created["token"]

    assert client.delete(f"/api/calendar/subscriptions/{created['id']}").status_code == 200
    assert client.get("/api/calendar/subscriptions").json()["subscriptions"] == []


def test_the_api_refuses_an_empty_selection_with_a_message_key(tmp_path):
    client, _, _ = _api(tmp_path)

    response = client.post(
        "/api/calendar/subscriptions", json={"child_id": CHILD_ID, "components": []}
    )

    assert response.status_code == 400
    assert response.json()["message_key"] == "api.calendar.error.components"
    assert response.json()["ok"] is False


def test_the_api_refuses_a_label_that_carries_the_child_name(tmp_path):
    client, _, _ = _api(tmp_path)

    response = client.post(
        "/api/calendar/subscriptions",
        json={"child_id": CHILD_ID, "components": ["timetable"], "label": "Quastenflosser"},
    )

    assert response.status_code == 400
    assert response.json()["message_key"] == "api.calendar.error.labelName"


def test_the_api_refuses_an_unknown_child(tmp_path):
    client, _, _ = _api(tmp_path)

    response = client.post(
        "/api/calendar/subscriptions", json={"child_id": "nope", "components": ["timetable"]}
    )

    assert response.json()["message_key"] == "api.calendar.error.child"


def test_the_api_refuses_a_rotate_for_an_unknown_subscription(tmp_path):
    client, _, _ = _api(tmp_path)

    response = client.post("/api/calendar/subscriptions/deadbeef/rotate")

    assert response.status_code == 400
    assert response.json()["message_key"] == "api.calendar.error.notFound"


def test_tokens_never_travel_through_the_plain_config_endpoint(tmp_path):
    client, store, registry = _api(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    config = client.get("/api/config").json()

    assert created["token"] not in str(config)


def test_the_poller_snapshots_four_weeks_for_a_subscribed_child(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    registry.create(CHILD_ID, ["timetable"], "5A")
    service = FakeService(store)
    holiday_calendar = CountingHolidays()

    Poller(
        service,
        store=store,
        registry=registry,
        holiday_calendar=holiday_calendar,
        clock=lambda: NOW_EPOCH,
    ).poll_once()

    assert sorted(offset for _, offset in service.calls) == [0, 1, 2, 3]
    weeks = store.load_calendar_snapshot()["children"][CHILD_ID]["weeks"]
    assert sorted(weeks) == ["07.09.2026", "14.09.2026", "21.09.2026", "31.08.2026"]
    assert store.load_calendar_snapshot()["children"][CHILD_ID]["last_success"] > 0
    assert holiday_calendar.calls == 1


def test_the_poller_leaves_iserv_alone_when_nobody_subscribed(tmp_path):
    store = _store(tmp_path)
    service = FakeService(store)

    Poller(service, store=store, registry=SubscriptionRegistry(store)).poll_once()

    assert service.calls == [(CHILD_ID, 0)]
    assert store.load_calendar_snapshot() == {}


def test_the_poller_drops_weeks_that_left_the_window(tmp_path):
    store = _store(tmp_path)
    poller = Poller(FakeService(store), store=store, clock=lambda: NOW_EPOCH)
    window = feed.lesson_window(poller._today())
    stale = (window[0] - timedelta(days=90)).strftime("%d.%m.%Y")
    fresh = window[0].strftime("%d.%m.%Y")

    kept = poller._prune_weeks({stale: {}, fresh: {}})

    assert sorted(kept) == [fresh]
