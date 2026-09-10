import time
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


def test_a_single_child_can_be_refreshed_without_a_full_poll(tmp_path):
    store = _store(tmp_path)
    service = FakeService(store)
    holiday_calendar = CountingHolidays()

    done = Poller(service, store=store, holiday_calendar=holiday_calendar, clock=lambda: NOW_EPOCH).refresh_child(CHILD_ID)

    assert done is True
    assert sorted(offset for _, offset in service.calls) == [0, 1, 2, 3]
    child = store.load_calendar_snapshot()["children"][CHILD_ID]
    assert sorted(child["weeks"]) == ["07.09.2026", "14.09.2026", "21.09.2026", "31.08.2026"]
    assert child["last_success"] == NOW_EPOCH
    assert holiday_calendar.calls == 1


def test_a_refresh_that_fails_leaves_the_snapshot_untouched_and_says_so(tmp_path):
    store = _store(tmp_path)
    service = FakeService(store)
    service.timetable = lambda child_id, week_offset=0: (_ for _ in ()).throw(RuntimeError("down"))

    done = Poller(service, store=store, clock=lambda: NOW_EPOCH).refresh_child(CHILD_ID)

    assert done is False
    assert store.load_calendar_snapshot() == {}


def _api_with_warmer(tmp_path, warmer):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    service = FakeService(store)
    client = TestClient(
        create_app(service, registry=registry, calendar_warmer=warmer), raise_server_exceptions=False
    )
    return client, store, registry, service


def test_creating_a_subscription_asks_for_the_child_to_be_fetched_right_away(tmp_path):
    warmed = []
    client, _, _, _ = _api_with_warmer(tmp_path, warmed.append)

    response = client.post(
        "/api/calendar/subscriptions",
        json={"child_id": CHILD_ID, "components": ["timetable", "school_holidays"], "label": "5A"},
    )

    assert response.status_code == 200
    assert warmed == [CHILD_ID]


def test_ticking_the_timetable_on_an_existing_subscription_fetches_the_child_too(tmp_path):
    warmed = []
    client, _, registry, _ = _api_with_warmer(tmp_path, warmed.append)
    created = registry.create(CHILD_ID, ["school_holidays"], "5A")

    client.post(
        f"/api/calendar/subscriptions/{created['id']}",
        json={"components": ["school_holidays", "timetable"]},
    )

    assert warmed == [CHILD_ID]


def test_a_subscription_without_lessons_or_marks_fetches_nothing(tmp_path):
    warmed = []
    client, _, _, _ = _api_with_warmer(tmp_path, warmed.append)

    client.post(
        "/api/calendar/subscriptions",
        json={"child_id": CHILD_ID, "components": ["school_holidays", "public_holidays"], "label": "5A"},
    )

    assert warmed == []


def test_the_first_feed_request_after_subscribing_already_carries_the_lessons(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    service = FakeService(store)
    client = TestClient(create_app(service, registry=registry), raise_server_exceptions=False)

    created = client.post(
        "/api/calendar/subscriptions",
        json={"child_id": CHILD_ID, "components": ["timetable"], "label": "5A"},
    ).json()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not store.load_calendar_snapshot():
        time.sleep(0.05)

    ics = feed.build_feed(
        registry.find_by_token(created["token"]),
        store,
        CountingHolidays(),
        now=datetime(2026, 9, 2, 6, 0),
    )

    assert "DTSTART;TZID=Europe/Berlin:20260902T080000" in ics
    assert "calendar.notice.noData" not in ics
    assert "noch keine Daten" not in ics


def _feed_client(tmp_path):
    from app.calendar_server import create_calendar_app

    store = _store(tmp_path)
    registry = SubscriptionRegistry(store, clock=lambda: NOW_EPOCH)
    subscription = registry.create(CHILD_ID, ["school_holidays"], "5A")
    app = create_calendar_app(store, registry, holiday_calendar=CountingHolidays(), builder=lambda *_: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    return TestClient(app, raise_server_exceptions=False), registry, subscription


def test_a_fresh_subscription_reports_that_nobody_fetched_it_yet(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store, clock=lambda: NOW_EPOCH)

    created = registry.create(CHILD_ID, ["timetable"], "5A")

    assert created["last_fetched_at"] == 0
    assert registry.list()[0]["last_fetched_at"] == 0


def test_a_calendar_app_fetching_the_feed_is_written_down(tmp_path):
    client, registry, subscription = _feed_client(tmp_path)

    response = client.get(f"/calendar/{subscription['token']}.ics")

    assert response.status_code == 200
    assert registry.list()[0]["last_fetched_at"] == NOW_EPOCH


def test_an_unchanged_feed_still_counts_as_a_fetch(tmp_path):
    client, registry, subscription = _feed_client(tmp_path)
    first = client.get(f"/calendar/{subscription['token']}.ics")

    registry.clock = lambda: NOW_EPOCH + 3600
    again = client.get(
        f"/calendar/{subscription['token']}.ics",
        headers={"if-none-match": first.headers["etag"]},
    )

    assert again.status_code == 304
    assert registry.list()[0]["last_fetched_at"] == NOW_EPOCH + 3600


def test_a_rejected_token_writes_nothing_down(tmp_path):
    client, registry, _ = _feed_client(tmp_path)

    assert client.get("/calendar/nonsense.ics").status_code == 404
    assert registry.list()[0]["last_fetched_at"] == 0


def test_the_feed_still_answers_when_the_fetch_note_cannot_be_stored(tmp_path):
    client, registry, subscription = _feed_client(tmp_path)

    def refuse(_subscription_id):
        raise OSError("read-only")

    registry.note_fetch = refuse

    assert client.get(f"/calendar/{subscription['token']}.ics").status_code == 200


def test_noting_a_fetch_for_an_unknown_subscription_changes_nothing(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store, clock=lambda: NOW_EPOCH)
    registry.create(CHILD_ID, ["timetable"], "5A")

    registry.note_fetch("does-not-exist")

    assert registry.list()[0]["last_fetched_at"] == 0
