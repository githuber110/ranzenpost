import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import cancellations, messages
from app.cancellations import CancellationError, CancellationRegistry
from app.poller import Poller
from app.server import create_app
from app.store import Store

from tests.test_poller import (
    FakeService,
    NotifierRecorder,
    PublisherRecorder,
    _display_lesson,
    _timetable,
)

CHILD_ID = "child-uuid-a"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
NOW = datetime(2026, 9, 2, 6, 0)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
WEDNESDAY_ISO = "2026-09-02"
PERIOD_TIMES = {"1": "08:00", "2": "08:50", "3": "09:45"}

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"
I18N_DIR = Path(__file__).resolve().parents[2] / "frontend" / "i18n"


def _bundle(language):
    return json.loads((I18N_DIR / f"{language}.json").read_text(encoding="utf-8"))


def _store(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["children"] = [{"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"}]
    config["period_times"] = dict(PERIOD_TIMES)
    store.save_config(config)
    return store


def _registry(store):
    return CancellationRegistry(store, clock=lambda: NOW_EPOCH)


def test_a_marker_survives_a_reload_of_the_registry(tmp_path):
    store = _store(tmp_path)
    created = _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3)
    assert created["child_id"] == CHILD_ID
    assert created["period"] == 3
    listed = _registry(store).list(CHILD_ID)["cancellations"]
    assert [entry["id"] for entry in listed] == [created["id"]]


def test_marking_the_same_lesson_twice_returns_the_same_marker(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    first = registry.create(CHILD_ID, WEDNESDAY_ISO, 3)
    second = registry.create(CHILD_ID, WEDNESDAY_ISO, 3)
    assert first["id"] == second["id"]
    assert len(registry.list()["cancellations"]) == 1


def test_a_marker_can_be_taken_back(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    created = registry.create(CHILD_ID, WEDNESDAY_ISO, 3)
    assert registry.delete(created["id"]) == {"deleted": created["id"]}
    assert registry.list()["cancellations"] == []
    with pytest.raises(CancellationError) as caught:
        registry.delete(created["id"])
    assert caught.value.message_key == cancellations.ERROR_NOT_FOUND


def test_an_unknown_child_a_bad_date_and_an_unknown_period_are_refused(tmp_path):
    registry = _registry(_store(tmp_path))
    with pytest.raises(CancellationError) as child:
        registry.create("someone-else", WEDNESDAY_ISO, 3)
    assert child.value.message_key == cancellations.ERROR_CHILD
    with pytest.raises(CancellationError) as date:
        registry.create(CHILD_ID, "2028-01-01", 3)
    assert date.value.message_key == cancellations.ERROR_DATE
    with pytest.raises(CancellationError) as period:
        registry.create(CHILD_ID, WEDNESDAY_ISO, 99)
    assert period.value.message_key == cancellations.ERROR_PERIOD


def test_every_refusal_key_is_translatable(tmp_path):
    bundles = {language: _bundle(language) for language in messages.LANGUAGES}
    for key in (
        cancellations.ERROR_CHILD,
        cancellations.ERROR_DATE,
        cancellations.ERROR_PERIOD,
        cancellations.ERROR_NOT_FOUND,
    ):
        for language in messages.LANGUAGES:
            assert key in bundles[language], f"{key} is missing from frontend/i18n/{language}.json"
            assert bundles[language][key].strip()
            rendered = messages.text_in(language, key)
            assert rendered != key, f"{key} resolves to its own key text in {language}"


class _Service:
    def __init__(self, store):
        self.store = store


def _client(store):
    return TestClient(create_app(_Service(store)))


def test_the_routes_create_list_and_delete_a_marker(tmp_path):
    store = _store(tmp_path)
    client = _client(store)
    created = client.post(
        "/api/cancellations",
        json={"child_id": CHILD_ID, "date": WEDNESDAY_ISO, "period": 3},
    )
    assert created.status_code == 200
    marker = created.json()
    listed = client.get("/api/cancellations", params={"child_id": CHILD_ID}).json()
    assert [entry["id"] for entry in listed["cancellations"]] == [marker["id"]]
    removed = client.delete(f"/api/cancellations/{marker['id']}")
    assert removed.status_code == 200
    assert client.get("/api/cancellations").json()["cancellations"] == []


def test_a_refused_marker_answers_with_a_message_key(tmp_path):
    client = _client(_store(tmp_path))
    answer = client.post(
        "/api/cancellations",
        json={"child_id": "someone-else", "date": WEDNESDAY_ISO, "period": 3},
    )
    assert answer.status_code == 400
    assert answer.json()["message_key"] == cancellations.ERROR_CHILD


def test_an_own_marker_never_touches_the_iserv_data_and_pushes_nothing(tmp_path):
    store = _store(tmp_path)
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables, store=store),
        publisher=publisher,
        notifier=notifier,
        store=store,
    )
    poller.poll_once()
    before = store.load_config()["poll_state"]["c1"]
    publishes = len(publisher.calls)

    config = store.load_config()
    config["children"] = config["children"] + [{"child_id": "c1", "name": "Alice"}]
    store.save_config(config)
    CancellationRegistry(store, clock=lambda: NOW_EPOCH).create("c1", "2026-08-31", 1)

    poller.poll_once()
    after = store.load_config()["poll_state"]["c1"]
    assert after["signature"] == before["signature"]
    assert after["plan_signature"] == before["plan_signature"]
    assert after["changes_signature"] == before["changes_signature"]
    assert notifier.calls == []
    assert len(publisher.calls) == publishes


def test_the_poller_never_learns_about_own_markers_at_all():
    source = (BACKEND_APP / "poller.py").read_text(encoding="utf-8")
    assert "cancellations" not in source, (
        "the poller decides what gets pushed - it must not see a marker that only this app knows"
    )
    service = (BACKEND_APP / "service.py").read_text(encoding="utf-8")
    assert "load_cancellations" not in service


def test_the_calendar_feed_shows_an_own_marker_the_way_it_shows_a_school_cancellation(tmp_path):
    from app import feed, holidays

    day = holidays.parse_day(WEDNESDAY_ISO)
    lesson = {
        "date": WEDNESDAY_ISO,
        "period": 3,
        "start_time": "09:45",
        "subject_code": "MA",
        "subject_label": "Mathe",
        "teacher_label": "Kluge",
        "room": "R204",
        "change_kind": "",
    }
    collected = {("id", 3, "a"): (day, lesson)}
    plain = feed.timetable_events("de", "c1", collected, {}, False, {}, ())
    dropped = feed.timetable_events("de", "c1", collected, {}, False, {}, {(day, 3)})
    assert plain[0].transparent is False
    assert dropped[0].transparent is True
    assert dropped[0].summary != plain[0].summary
    assert messages.text_in("de", "calendar.cancellation.notice") in dropped[0].description


def test_the_feed_only_drops_the_child_and_slot_that_was_marked():
    from app import feed, holidays

    day = holidays.parse_day(WEDNESDAY_ISO)
    entries = [
        {"child_id": CHILD_ID, "date": WEDNESDAY_ISO, "period": 3},
        {"child_id": "other-child", "date": WEDNESDAY_ISO, "period": 4},
        {"child_id": CHILD_ID, "date": "not-a-date", "period": 5},
    ]
    assert feed.dropped_slots(entries, CHILD_ID) == {(day, 3)}
    assert feed.dropped_slots(entries, "other-child") == {(day, 4)}
    assert feed.dropped_slots([], CHILD_ID) == set()


def test_a_cancellation_stored_through_the_real_registry_reaches_the_built_feed(tmp_path):
    from app import feed, feed_ics
    from app.subscriptions import SubscriptionRegistry
    from tests.test_calendar_feed import FakeHolidayCalendar, _lesson, _snapshot, _unfold

    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(period=3, start_time="09:45")]))
    subscription = SubscriptionRegistry(store).create(
        CHILD_ID, ["timetable"], "5A", "", require_region=False
    )
    notice = feed_ics.escape_text(messages.text_in("de", "calendar.cancellation.notice"))

    before = _unfold(feed.build_feed(subscription, store, FakeHolidayCalendar(), now=NOW))
    assert "TRANSP:TRANSPARENT" not in before
    assert notice not in before

    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3)

    after = _unfold(feed.build_feed(subscription, store, FakeHolidayCalendar(), now=NOW))
    assert "TRANSP:TRANSPARENT" in after
    assert notice in after
