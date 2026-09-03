from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import atomic_write, feed, holidays, marks, messages, subscriptions
from app.marks import MarkError, MarkRegistry
from app.poller import Poller
from app.server import create_app
from app.store import Store
from app.subscriptions import SubscriptionRegistry

CHILD_ID = "child-uuid-a"
SECOND_CHILD_ID = "child-uuid-b"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
SECOND_CHILD_NAME = "Kraakebolle Nebelkrähe"
STUDENT_ID = 4711
NOW = datetime(2026, 9, 2, 6, 0)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
MONDAY = "31.08.2026"
WEDNESDAY = "02.09.2026"
WEDNESDAY_ISO = "2026-09-02"
PERIOD_TIMES = {"1": "08:00", "2": "08:50", "3": "09:45", "4": "10:30", "5": "11:30"}


def _day(free=False, overrides=False, kind="", name="", name_key="", period_id=""):
    return {
        "free": free,
        "overrides_lessons": overrides,
        "weekend": False,
        "kind": kind,
        "type": "",
        "name": name,
        "name_key": name_key,
        "period_id": period_id,
    }


class FakeHolidayCalendar:
    def __init__(self, status=holidays.STATUS_OK, days=None):
        self.status = status
        self.days = dict(days or {})

    def range_info(self, start, end, config=None):
        filled = {}
        day = start
        while day <= end:
            filled[day.isoformat()] = self.days.get(day.isoformat(), _day())
            day += timedelta(days=1)
        return {"status": self.status, "stale": False, "days": filled, "periods": []}


def _lesson(period=3, subject_code="MA", subject_label="Mathe", change_kind="", room="R204"):
    return {
        "date": WEDNESDAY,
        "day_of_week": 3,
        "period": period,
        "start_time": PERIOD_TIMES[str(period)],
        "subject_code": subject_code,
        "subject_label": subject_label,
        "color": "#2486ed",
        "teacher_code": "KLU",
        "teacher_label": "Kluge",
        "is_class_teacher": False,
        "room": room,
        "change_kind": change_kind,
        "changed_fields": [],
        "previous": {"subject": "", "teacher": "", "room": ""},
    }


def _snapshot(lessons, fetched_at=NOW_EPOCH, child_id=CHILD_ID, absences=None):
    child = {
        "weeks": {
            MONDAY: {
                "start_date": MONDAY,
                "end_date": "06.09.2026",
                "lessons": lessons,
                "fetched_at": fetched_at,
            }
        },
        "last_success": NOW_EPOCH,
    }
    if absences is not None:
        child["absences"] = absences
        child["absences_fetched_at"] = NOW_EPOCH
    return {"children": {child_id: child}}


def _store(tmp_path, language="de"):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["language"] = language
    config["holiday_region"] = "DE-NI"
    config["children"] = [
        {"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"},
        {"child_id": SECOND_CHILD_ID, "name": SECOND_CHILD_NAME, "class_name": "7B"},
    ]
    config["subjects"] = {
        "MA": {"label": "Mathe", "color": "#2486ed"},
        "D": {"label": "Deutsch", "color": "#0e6b70"},
    }
    config["period_times"] = dict(PERIOD_TIMES)
    store.save_config(config)
    return store


def _registry(store):
    return MarkRegistry(store, clock=lambda: NOW_EPOCH)


def _subscription(store, components=("marks",), child_id=CHILD_ID):
    return SubscriptionRegistry(store).create(child_id, list(components), "5A")


def _build(store, subscription, calendar=None, now=NOW):
    body = feed.build_feed(subscription, store, calendar or FakeHolidayCalendar(), now=now)
    return body.replace("\r\n ", "")


def _absence(
    entry_id=41,
    kind="leave",
    label_key="absence.entry.kind.leave",
    target_key="",
    status="accepted",
    from_date=WEDNESDAY_ISO,
    till_date=WEDNESDAY_ISO,
    from_period=3,
    till_period=4,
    subject="Zahnarzt",
    comment="",
):
    return {
        "id": entry_id,
        "kind": kind,
        "target": "",
        "label_key": label_key,
        "target_key": target_key,
        "status": status,
        "from_date": from_date,
        "till_date": till_date,
        "from_period": from_period,
        "till_period": till_period,
        "subject": subject,
        "comment": comment,
    }


def test_a_mark_survives_the_round_trip_through_the_atomic_store(tmp_path):
    store = _store(tmp_path)

    created = _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    reopened = Store(tmp_path / "data")
    stored = marks.entries_of(reopened.load_marks())
    assert [entry["id"] for entry in stored] == [created["id"]]
    assert stored[0]["date"] == WEDNESDAY_ISO
    assert stored[0]["period"] == 3
    assert stored[0]["subject_code"] == "MA"
    assert stored[0]["name"] == "Diktat"
    assert stored[0]["created_at"] == NOW_EPOCH
    assert sorted(path.name for path in reopened.dir.glob(f"*{atomic_write.TEMP_SUFFIX}")) == []


def test_an_interrupted_write_leaves_the_previous_marks_untouched(tmp_path, monkeypatch):
    store = _store(tmp_path)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    before = store.marks_path.read_bytes()

    def _boom(*args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(atomic_write.os, "replace", _boom)
    with pytest.raises(OSError):
        registry.create(CHILD_ID, WEDNESDAY_ISO, 4, "MA", "Test")

    assert store.marks_path.read_bytes() == before
    assert len(marks.entries_of(store.load_marks())) == 1


def test_a_name_carrying_the_child_name_is_refused(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(MarkError) as error:
        _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Arbeit Quastenflosser")

    assert error.value.message_key == marks.ERROR_NAME
    assert marks.entries_of(store.load_marks()) == []


def test_the_name_check_is_the_one_the_calendar_label_already_uses(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    created = registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    assert subscriptions.label_carries_child_name("Arbeit Quastenflosser", store.load_config())
    with pytest.raises(MarkError) as error:
        registry.update(created["id"], name="zwiebelfisch")
    assert error.value.message_key == marks.ERROR_NAME
    assert marks.entries_of(store.load_marks())[0]["name"] == "Diktat"


def test_the_same_slot_is_refused_twice_but_stays_free_for_the_sibling(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    with pytest.raises(MarkError) as error:
        registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "D", "Zweites")
    assert error.value.message_key == marks.ERROR_DUPLICATE

    sibling = registry.create(SECOND_CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Test")
    assert sibling["child_id"] == SECOND_CHILD_ID
    assert len(marks.entries_of(store.load_marks())) == 2


def test_re_anchoring_onto_a_taken_slot_is_refused_but_onto_a_free_one_keeps_the_identity(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    first = registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    registry.create(CHILD_ID, WEDNESDAY_ISO, 4, "D", "Test")

    with pytest.raises(MarkError) as error:
        registry.update(first["id"], period=4)
    assert error.value.message_key == marks.ERROR_DUPLICATE

    moved = registry.update(first["id"], period=5)
    assert moved["id"] == first["id"]
    assert moved["period"] == 5


def test_a_date_outside_the_eight_week_window_is_refused(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    start, end = marks.window(holidays.berlin_today(NOW))

    assert registry.create(CHILD_ID, start.isoformat(), 3, "MA")["date"] == start.isoformat()
    with pytest.raises(MarkError) as error:
        registry.create(CHILD_ID, (start - timedelta(days=1)).isoformat(), 3, "MA")
    assert error.value.message_key == marks.ERROR_DATE
    with pytest.raises(MarkError):
        registry.create(CHILD_ID, (end + timedelta(days=1)).isoformat(), 3, "MA")


def test_a_period_the_school_does_not_know_is_refused(tmp_path):
    store = _store(tmp_path)

    for invalid in (0, 9, "abc", None, True):
        with pytest.raises(MarkError) as error:
            _registry(store).create(CHILD_ID, WEDNESDAY_ISO, invalid, "MA")
        assert error.value.message_key == marks.ERROR_PERIOD


def test_an_unknown_child_and_a_missing_subject_are_refused(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(MarkError) as unknown:
        _registry(store).create("nope", WEDNESDAY_ISO, 3, "MA")
    assert unknown.value.message_key == marks.ERROR_CHILD

    with pytest.raises(MarkError) as missing:
        _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "")
    assert missing.value.message_key == marks.ERROR_SUBJECT


def _state(store, lessons, fetched_at=NOW_EPOCH, subject_code="MA", period=3):
    store.save_calendar_snapshot(_snapshot(lessons, fetched_at=fetched_at))
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, period, subject_code, "Diktat")
    return registry.list(CHILD_ID)["marks"][0]["state"]


def test_a_lesson_that_still_sits_where_it_was_reads_as_confirmed(tmp_path):
    assert _state(_store(tmp_path), [_lesson()]) == marks.STATE_CONFIRMED


def test_a_substitution_keeps_the_mark_and_says_so(tmp_path):
    assert _state(_store(tmp_path), [_lesson(change_kind="changed", room="R9")]) == (
        marks.STATE_SUBSTITUTED
    )


def test_another_subject_in_the_slot_reads_as_foreign(tmp_path):
    assert _state(_store(tmp_path), [_lesson(subject_code="D", subject_label="Deutsch")]) == (
        marks.STATE_FOREIGN
    )


def test_a_cancelled_lesson_reads_as_cancelled(tmp_path):
    assert _state(_store(tmp_path), [_lesson(change_kind="cancelled")]) == marks.STATE_CANCELLED


def test_a_cancellation_wins_over_a_second_lesson_of_the_same_subject_in_the_slot(tmp_path):
    lessons = [_lesson(change_kind="cancelled"), _lesson(subject_code="D", subject_label="Deutsch")]

    assert _state(_store(tmp_path), lessons) == marks.STATE_CANCELLED


def test_an_empty_slot_in_a_fresh_week_reads_as_orphaned(tmp_path):
    assert _state(_store(tmp_path), [_lesson(period=1)]) == marks.STATE_ORPHANED


def test_a_stale_week_reads_as_unknown_and_never_as_orphaned(tmp_path):
    stale = NOW_EPOCH - marks.FRESH_AFTER_SECONDS - 60

    assert _state(_store(tmp_path), [_lesson(period=1)], fetched_at=stale) == marks.STATE_UNKNOWN


def test_a_week_without_a_fetch_stamp_reads_as_unknown(tmp_path):
    store = _store(tmp_path)
    snapshot = _snapshot([_lesson(period=1)])
    del snapshot["children"][CHILD_ID]["weeks"][MONDAY]["fetched_at"]
    store.save_calendar_snapshot(snapshot)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    assert registry.list(CHILD_ID)["marks"][0]["state"] == marks.STATE_UNKNOWN


def test_a_missing_week_reads_as_unknown(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    assert registry.list(CHILD_ID)["marks"][0]["state"] == marks.STATE_UNKNOWN


def test_dropping_the_freshness_rule_would_turn_a_stale_week_into_a_false_orphan(tmp_path, monkeypatch):
    store = _store(tmp_path)
    stale = NOW_EPOCH - marks.FRESH_AFTER_SECONDS - 60
    store.save_calendar_snapshot(_snapshot([_lesson(period=1)], fetched_at=stale))
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    assert registry.list(CHILD_ID)["marks"][0]["state"] == marks.STATE_UNKNOWN

    monkeypatch.setattr(marks, "is_fresh", lambda week, now_epoch: True)

    assert registry.list(CHILD_ID)["marks"][0]["state"] == marks.STATE_ORPHANED


def test_the_state_set_is_exactly_the_six_the_analysis_names():
    assert set(marks.STATES) == {
        "confirmed",
        "substituted",
        "foreign",
        "cancelled",
        "orphaned",
        "unknown",
    }


def test_the_listing_stays_inside_the_eight_week_window_and_names_it(tmp_path):
    store = _store(tmp_path)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    start, end = marks.window(holidays.berlin_today(NOW))
    stored = marks.entries_of(store.load_marks())
    stored.append(dict(stored[0], id="far", date=(end + timedelta(days=30)).isoformat()))
    store.save_marks({"marks": stored})

    listing = registry.list(CHILD_ID)

    assert [entry["id"] for entry in listing["marks"]] != []
    assert "far" not in [entry["id"] for entry in listing["marks"]]
    assert listing["window"] == {"start": start.isoformat(), "end": end.isoformat()}


def test_the_mark_reaches_the_feed_at_the_time_the_period_table_gives(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    ics = _build(store, _subscription(store))

    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in ics
    assert "DTEND;TZID=Europe/Berlin:20260902T103000" in ics
    assert "CATEGORIES:Mathe" in ics
    assert "LOCATION:R204" in ics
    assert "TRANSP:OPAQUE" in ics


def test_the_feed_time_ignores_the_lesson_and_follows_the_period_table(tmp_path):
    store = _store(tmp_path)
    moved = _lesson()
    moved["start_time"] = "23:00"
    store.save_calendar_snapshot(_snapshot([moved]))
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    ics = _build(store, _subscription(store))

    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in ics
    assert "T230000" not in ics


def test_the_mark_keeps_its_shape_and_uid_when_the_week_leaves_the_snapshot(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    created = _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    subscription = _subscription(store)
    first = _build(store, subscription)

    store.save_calendar_snapshot({})
    second = _build(store, subscription, now=NOW + timedelta(hours=2))

    assert f"UID:mark-{created['id']}@ranzenpost.local" in first
    assert f"UID:mark-{created['id']}@ranzenpost.local" in second
    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in second


def test_re_anchoring_moves_the_event_without_changing_the_uid(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    registry = _registry(store)
    created = registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    subscription = _subscription(store)
    _build(store, subscription)

    registry.update(created["id"], period=5)
    later = _build(store, subscription, now=NOW + timedelta(hours=2))

    assert f"UID:mark-{created['id']}@ranzenpost.local" in later
    assert "DTSTART;TZID=Europe/Berlin:20260902T113000" in later
    assert "SEQUENCE:1" in later


def test_a_mark_beyond_the_lesson_window_still_reaches_the_feed(tmp_path):
    store = _store(tmp_path)
    far = (holidays.berlin_today(NOW) + timedelta(days=42)).isoformat()
    _registry(store).create(CHILD_ID, far, 3, "MA", "Klausur")

    ics = _build(store, _subscription(store))

    assert far.replace("-", "") in ics


def test_a_mark_outlives_a_holiday_day_and_a_broken_holiday_source(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    subscription = _subscription(store, ("timetable", "marks"))
    blocked = FakeHolidayCalendar(status=holidays.STATUS_UNKNOWN)
    holiday_day = FakeHolidayCalendar(
        days={
            WEDNESDAY_ISO: _day(
                free=True, overrides=True, kind="school", name_key="holidays.period.autumn", period_id="p9"
            )
        }
    )

    while_blocked = _build(store, subscription, blocked)
    while_free = _build(store, subscription, holiday_day, now=NOW + timedelta(hours=2))

    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in while_blocked
    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in while_free
    assert "SUMMARY:3. Stunde Mathe (Kluge)" not in while_free


def test_no_untranslated_message_key_ever_leaks_into_the_feed(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()], absences=[_absence()]))
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    registry.create(CHILD_ID, WEDNESDAY_ISO, 4, "MA", "")

    ics = _build(store, _subscription(store, ("marks", "absences")))

    for fragment in ("calendar.mark", "absence.entry", "absence.fact", "timetable.field"):
        assert fragment not in ics


def test_a_mark_without_its_bundle_key_still_names_the_subject_and_the_period(tmp_path, monkeypatch):
    monkeypatch.delitem(messages.BASE_MESSAGES, feed.MARK_SUMMARY_KEY, raising=False)
    monkeypatch.delitem(messages.BASE_MESSAGES, feed.MARK_SUMMARY_NAMED_KEY, raising=False)
    store = _store(tmp_path)
    registry = _registry(store)
    registry.create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    registry.create(CHILD_ID, WEDNESDAY_ISO, 4, "MA", "")

    ics = _build(store, _subscription(store))

    assert "SUMMARY:Diktat · 3. Stunde Mathe" in ics
    assert f"SUMMARY:{feed.MARK_FALLBACK_PREFIX} · 4. Stunde Mathe" in ics


def test_the_feed_uses_the_target_keys_as_soon_as_the_bundles_carry_them(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "")
    monkeypatch.setitem(
        messages.BASE_MESSAGES, feed.MARK_SUMMARY_KEY, "Probe: {subject} ({period})"
    )
    monkeypatch.setitem(messages.BASE_MESSAGES, feed.MARK_NOTICE_KEY, "Only in this app.")

    ics = _build(store, _subscription(store))

    assert "SUMMARY:Probe: Mathe (3)" in ics
    assert "Only in this app." in ics


def test_the_named_target_key_wins_when_a_free_name_is_set(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    monkeypatch.setitem(
        messages.BASE_MESSAGES, feed.MARK_SUMMARY_NAMED_KEY, "Probe: {name} - {subject}"
    )

    assert "SUMMARY:Probe: Diktat - Mathe" in _build(store, _subscription(store))


def test_a_mark_of_another_child_never_lands_in_this_feed(tmp_path):
    store = _store(tmp_path)
    _registry(store).create(SECOND_CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    ics = _build(store, _subscription(store))

    assert "BEGIN:VEVENT" not in ics


def test_the_marks_component_alone_never_pulls_in_the_lessons(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")

    ics = _build(store, _subscription(store))

    assert ics.count("BEGIN:VEVENT") == 1


def test_an_approved_leave_becomes_a_timed_event(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([], absences=[_absence()]))

    ics = _build(store, _subscription(store, ("absences",)))

    assert "SUMMARY:Beurlaubungsantrag" in ics
    assert "DTSTART;TZID=Europe/Berlin:20260902T094500" in ics
    assert "DTEND;TZID=Europe/Berlin:20260902T111500" in ics
    assert "Status: Genehmigt" in ics
    assert "Zahnarzt" in ics


def test_a_sick_note_becomes_an_all_day_span(tmp_path):
    store = _store(tmp_path)
    entry = _absence(
        entry_id=7,
        kind="sick",
        label_key="absence.entry.kind.sick",
        status="",
        from_date="2026-09-02",
        till_date="2026-09-04",
        from_period=None,
        till_period=None,
        subject="",
    )
    store.save_calendar_snapshot(_snapshot([], absences=[entry]))

    ics = _build(store, _subscription(store, ("absences",)))

    assert "SUMMARY:Krankmeldung" in ics
    assert "DTSTART;VALUE=DATE:20260902" in ics
    assert "DTEND;VALUE=DATE:20260905" in ics
    assert "TRANSP:TRANSPARENT" in ics


def test_a_deregistration_names_what_it_is_about(tmp_path):
    store = _store(tmp_path)
    entry = _absence(
        entry_id=9,
        kind="deregister",
        label_key="absence.entry.kind.deregister",
        target_key="absence.target.bus",
        from_period=None,
        till_period=None,
        subject="",
    )
    store.save_calendar_snapshot(_snapshot([], absences=[entry]))

    assert "SUMMARY:Abmeldung · Bus" in _build(store, _subscription(store, ("absences",)))


def test_an_open_or_rejected_request_never_reaches_the_feed(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot(
            [],
            absences=[
                _absence(entry_id=1, status="open"),
                _absence(entry_id=2, status="rejected"),
            ],
        )
    )

    assert "BEGIN:VEVENT" not in _build(store, _subscription(store, ("absences",)))


def test_the_absence_component_is_independent_of_the_holiday_source(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([], absences=[_absence()]))

    ics = _build(
        store,
        _subscription(store, ("absences",)),
        FakeHolidayCalendar(status=holidays.STATUS_UNKNOWN),
    )

    assert "SUMMARY:Beurlaubungsantrag" in ics


def test_the_new_components_are_accepted_and_nonsense_is_still_refused(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)

    for name in (subscriptions.COMPONENT_MARKS, subscriptions.COMPONENT_ABSENCES):
        assert registry.create(CHILD_ID, [name], "5A")["components"] == [name]

    with pytest.raises(subscriptions.SubscriptionError) as error:
        registry.create(CHILD_ID, ["marks", "nonsense"], "5A")
    assert error.value.message_key == subscriptions.ERROR_COMPONENTS


def test_the_new_components_need_no_holiday_region(tmp_path):
    store = _store(tmp_path)
    config = store.load_config()
    config["holiday_region"] = ""
    store.save_config(config)

    created = SubscriptionRegistry(store).create(CHILD_ID, ["marks", "absences"], "5A")

    assert created["components"] == ["marks", "absences"]


def test_an_existing_subscription_keeps_working_and_can_gain_the_new_parts(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    updated = registry.update(created["id"], components=["timetable", "marks", "absences"])

    assert updated["token"] == created["token"]
    assert updated["components"] == ["timetable", "marks", "absences"]


class FakeService:
    def __init__(self, store, overview=None):
        self.store = store
        self.overview = overview
        self.calls = []

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"

    def children(self):
        return [
            {"child_id": CHILD_ID, "name": CHILD_NAME, "student_id": STUDENT_ID},
            {"child_id": SECOND_CHILD_ID, "name": SECOND_CHILD_NAME, "student_id": None},
        ]

    def timetable(self, child_id, week_offset=0):
        self.calls.append((child_id, week_offset))
        start = ["31.08.2026", "07.09.2026", "14.09.2026", "21.09.2026"][week_offset]
        return {
            "last_updated": "02.09.2026 06:00",
            "start_date": start,
            "end_date": start,
            "lessons": [_lesson()] if week_offset == 0 else [],
            "changes": [],
        }

    def absences_overview(self):
        if self.overview is None:
            raise RuntimeError("no absences")
        return self.overview


def _poller(store, service, registry):
    return Poller(service, store=store, registry=registry, clock=lambda: NOW_EPOCH)


def test_the_poller_snapshots_the_weeks_a_marked_child_needs_without_a_subscription(tmp_path):
    store = _store(tmp_path)
    _registry(store).create(CHILD_ID, WEDNESDAY_ISO, 3, "MA", "Diktat")
    service = FakeService(store)

    _poller(store, service, SubscriptionRegistry(store)).poll_once()

    weeks = store.load_calendar_snapshot()["children"][CHILD_ID]["weeks"]
    assert MONDAY in weeks
    assert weeks[MONDAY]["fetched_at"] == NOW_EPOCH
    assert _registry(store).list(CHILD_ID)["marks"][0]["state"] == marks.STATE_CONFIRMED


def test_the_poller_carries_the_absences_into_the_snapshot_for_the_right_child(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    registry.create(CHILD_ID, ["absences"], "5A")
    overview = {
        "children": [{"id": STUDENT_ID, "name": CHILD_NAME}],
        "entries": [dict(_absence(), student_id=STUDENT_ID)],
    }

    _poller(store, FakeService(store, overview), registry).poll_once()

    stored = store.load_calendar_snapshot()["children"][CHILD_ID]["absences"]
    assert [entry["id"] for entry in stored] == [41]
    assert stored[0]["status"] == "accepted"
    assert "student_id" not in stored[0]
    assert "technical" not in stored[0]


def test_the_snapshot_absence_carries_no_name_and_no_free_person_field(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    registry.create(CHILD_ID, ["absences"], "5A")
    overview = {
        "children": [{"id": STUDENT_ID, "name": CHILD_NAME}],
        "entries": [
            dict(
                _absence(),
                student_id=STUDENT_ID,
                label="Beurlaubungsantrag",
                technical={"author": "Elternteil"},
                answer="ok",
            )
        ],
    }

    _poller(store, FakeService(store, overview), registry).poll_once()

    stored = store.load_calendar_snapshot()["children"][CHILD_ID]["absences"][0]
    assert set(stored) == set(
        (
            "id",
            "kind",
            "target",
            "label_key",
            "target_key",
            "status",
            "from_date",
            "till_date",
            "from_period",
            "till_period",
            "subject",
            "comment",
        )
    )


def test_the_poller_asks_for_no_absences_when_nobody_subscribed_to_them(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    registry.create(CHILD_ID, ["timetable"], "5A")
    overview = {"children": [], "entries": [dict(_absence(), student_id=STUDENT_ID)]}

    _poller(store, FakeService(store, overview), registry).poll_once()

    assert "absences" not in store.load_calendar_snapshot()["children"][CHILD_ID]


def _api(tmp_path):
    store = _store(tmp_path)
    service = FakeService(store)
    client = TestClient(
        create_app(
            service,
            registry=SubscriptionRegistry(store),
            mark_registry=_registry(store),
        ),
        raise_server_exceptions=False,
    )
    return client, store, service


def test_the_api_creates_lists_updates_and_deletes_a_mark(tmp_path):
    client, store, _ = _api(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    created = client.post(
        "/api/marks",
        json={
            "child_id": CHILD_ID,
            "date": WEDNESDAY_ISO,
            "period": 3,
            "subject_code": "MA",
            "name": "Diktat",
        },
    ).json()
    assert created["state"] == marks.STATE_CONFIRMED

    listing = client.get("/api/marks", params={"child_id": CHILD_ID}).json()
    assert [entry["id"] for entry in listing["marks"]] == [created["id"]]
    assert listing["window"]["start"] < listing["window"]["end"]

    renamed = client.post(f"/api/marks/{created['id']}", json={"name": "Diktat 4"}).json()
    assert renamed["name"] == "Diktat 4"
    assert renamed["id"] == created["id"]

    assert client.delete(f"/api/marks/{created['id']}").json() == {"deleted": created["id"]}
    assert client.get("/api/marks").json()["marks"] == []


def test_the_api_answers_every_refusal_with_a_message_key(tmp_path):
    client, _, _ = _api(tmp_path)
    base = {"child_id": CHILD_ID, "date": WEDNESDAY_ISO, "period": 3, "subject_code": "MA"}

    for payload, key in (
        (dict(base, child_id="nope"), marks.ERROR_CHILD),
        (dict(base, date="2001-01-01"), marks.ERROR_DATE),
        (dict(base, period=99), marks.ERROR_PERIOD),
        (dict(base, subject_code=""), marks.ERROR_SUBJECT),
        (dict(base, name="Quastenflosser"), marks.ERROR_NAME),
        (dict(base, name="x" * 61), marks.ERROR_NAME_LENGTH),
    ):
        response = client.post("/api/marks", json=payload)
        assert response.status_code == 400
        assert response.json()["message_key"] == key
        assert response.json()["ok"] is False

    missing = client.post("/api/marks/deadbeef", json={"name": "x"})
    assert missing.status_code == 400
    assert missing.json()["message_key"] == marks.ERROR_NOT_FOUND
    assert client.delete("/api/marks/deadbeef").json()["message_key"] == marks.ERROR_NOT_FOUND


def test_the_mark_endpoints_never_speak_to_iserv(tmp_path):
    client, store, service = _api(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    created = client.post(
        "/api/marks",
        json={"child_id": CHILD_ID, "date": WEDNESDAY_ISO, "period": 3, "subject_code": "MA"},
    ).json()
    client.get("/api/marks")
    client.post(f"/api/marks/{created['id']}", json={"name": "Test"})
    client.delete(f"/api/marks/{created['id']}")

    assert service.calls == []
