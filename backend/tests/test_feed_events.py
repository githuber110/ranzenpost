from datetime import date, datetime

from app import feed
from app.cancellations import CancellationRegistry

from tests.test_calendar_feed import (
    CHILD_ID,
    NOW,
    NOW_EPOCH,
    WEDNESDAY,
    FakeHolidayCalendar,
    _lesson,
    _snapshot,
    _store,
    _subscription,
)


def _gather(store, subscription, calendar=None, now=NOW):
    return feed.gather_events(subscription, store, calendar or FakeHolidayCalendar(), now=now)


def test_gather_events_hands_out_the_same_events_the_ics_feed_renders(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(), _lesson(period=3, subject_code="MA", subject_label="Mathe")]))
    subscription = _subscription(store)

    events = _gather(store, subscription)
    ics = feed.build_feed(subscription, store, FakeHolidayCalendar(), now=NOW)

    assert [event.uid for event in events] == [
        line[4:] for line in ics.replace("\r\n ", "").split("\r\n") if line.startswith("UID:")
    ]
    assert all(isinstance(event, feed.FeedEvent) for event in events)


def test_gather_events_leaves_the_calendar_state_untouched(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    subscription = _subscription(store)

    _gather(store, subscription)

    assert store.load_calendar_state() == {}


def test_a_cancelled_lesson_carries_the_cancelled_flag_and_stays_in_the_list(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot([_lesson(), _lesson(period=3, subject_code="MA", subject_label="Mathe", change_kind="cancelled")])
    )
    subscription = _subscription(store)

    events = [event for event in _gather(store, subscription) if not event.all_day]

    assert [event.cancelled for event in events] == [False, True]
    assert events[1].transparent is True
    assert events[1].start == datetime(2026, 9, 2, 9, 45)


def test_an_own_marker_counts_as_cancelled_too(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    CancellationRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-02", 1)
    subscription = _subscription(store)

    events = [event for event in _gather(store, subscription) if not event.all_day]

    assert events[0].cancelled is True


def test_plain_events_default_to_not_cancelled():
    event = feed.FeedEvent("uid", "s", "d", "", date(2026, 9, 2), date(2026, 9, 3), True, True)

    assert event.cancelled is False


def test_the_cancelled_flag_does_not_move_the_content_hash(tmp_path):
    plain = feed.FeedEvent("uid", "s", "d", "", date(2026, 9, 2), date(2026, 9, 3), True, True)
    flagged = feed.FeedEvent("uid", "s", "d", "", date(2026, 9, 2), date(2026, 9, 3), True, True, cancelled=True)

    assert feed.content_hash(plain) == feed.content_hash(flagged)


def test_change_note_lists_the_before_and_after_of_every_changed_field():
    lesson = _lesson(
        change_kind="changed",
        changed_fields=["teacher", "room"],
        previous={"subject": "", "teacher": "Alt", "room": "R9"},
    )

    note = feed.change_note("de", lesson)

    assert "Alt" in note and "Behrens" in note
    assert "R9" in note and "R1" in note
    assert feed.change_note("de", _lesson()) == ""
