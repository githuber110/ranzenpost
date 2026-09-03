from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import feed, feed_ics, holidays, marks, messages, subscriptions
from app.iserv.absences import berlin_offset
from app.marks import MarkRegistry
from app.store import Store
from app.subscriptions import SubscriptionRegistry, SubscriptionError

CHILD_ID = "child-uuid-a"
SECOND_CHILD_ID = "child-uuid-b"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
SECOND_CHILD_NAME = "Kraakebolle Nebelkrähe"
NOW = datetime(2026, 9, 2, 6, 0)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
MONDAY = "31.08.2026"
WEDNESDAY = "02.09.2026"


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
        self.calls = 0

    def range_info(self, start, end, config=None):
        self.calls += 1
        filled = {}
        day = start
        while day <= end:
            filled[day.isoformat()] = self.days.get(day.isoformat(), _day())
            day += timedelta(days=1)
        return {"status": self.status, "stale": False, "days": filled, "periods": []}


def _lesson(
    day=WEDNESDAY,
    period=1,
    subject_code="D",
    subject_label="Deutsch",
    teacher_code="BEH",
    teacher_label="Behrens",
    room="R1",
    start_time="08:00",
    change_kind="",
    changed_fields=None,
    previous=None,
    color="#0e6b70",
    is_class_teacher=False,
):
    return {
        "date": day,
        "day_of_week": 3,
        "period": period,
        "start_time": start_time,
        "subject_code": subject_code,
        "subject_label": subject_label,
        "color": color,
        "teacher_code": teacher_code,
        "teacher_label": teacher_label,
        "is_class_teacher": is_class_teacher,
        "room": room,
        "change_kind": change_kind,
        "changed_fields": list(changed_fields or []),
        "previous": previous or {"subject": "", "teacher": "", "room": ""},
    }


def _snapshot(lessons, child_id=CHILD_ID, last_success=NOW_EPOCH, week=MONDAY):
    return {
        "children": {
            child_id: {
                "weeks": {
                    week: {
                        "start_date": week,
                        "end_date": "06.09.2026",
                        "lessons": lessons,
                    }
                },
                "last_success": last_success,
            }
        }
    }


def _store(tmp_path, language="de", region="DE-NI", children=None, subjects=None):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["language"] = language
    config["holiday_region"] = region
    config["children"] = children or [
        {"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"},
        {"child_id": SECOND_CHILD_ID, "name": SECOND_CHILD_NAME, "class_name": "7B"},
    ]
    config["subjects"] = subjects or {"D": {"label": "Deutsch", "color": "#0e6b70"}}
    config["period_times"] = {"1": "08:00", "3": "09:45", "4": "10:30"}
    store.save_config(config)
    return store


def _subscription(store, components=("timetable",), label="5A", child_id=CHILD_ID, color=""):
    return SubscriptionRegistry(store).create(child_id, list(components), label, color)


def _unfold(text):
    return text.replace("\r\n ", "")


def _build(store, subscription, calendar=None, now=NOW):
    return _unfold(feed.build_feed(subscription, store, calendar or FakeHolidayCalendar(), now=now))


def _uids(ics):
    return [line[4:] for line in ics.split("\r\n") if line.startswith("UID:")]


def test_the_child_name_never_reaches_the_feed_or_its_address(tmp_path):
    store = _store(tmp_path)
    snapshot = _snapshot([_lesson()])
    snapshot["children"][CHILD_ID]["absences"] = [
        {
            "id": 41,
            "kind": "leave",
            "label_key": "absence.entry.kind.leave",
            "target_key": "",
            "status": "accepted",
            "from_date": "2026-09-02",
            "till_date": "2026-09-02",
            "from_period": 3,
            "till_period": 4,
            "subject": f"Antrag {CHILD_NAME.split()[0]}",
            "comment": CHILD_NAME,
        }
    ]
    store.save_calendar_snapshot(snapshot)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-02", 3, "D", "Diktat")
    subscription = _subscription(store, subscriptions.COMPONENTS)

    ics = _build(store, subscription)

    assert "BEGIN:VEVENT" in ics
    haystack = (ics + subscription["token"] + subscription["path"] + subscription["label"]).casefold()
    for part in CHILD_NAME.split():
        assert part.casefold() not in haystack
    assert CHILD_ID not in ics


def test_a_label_carrying_the_child_name_is_refused(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)

    with pytest.raises(SubscriptionError) as error:
        registry.create(CHILD_ID, ["timetable"], "Kalender Zwiebelfisch")

    assert error.value.message_key == subscriptions.ERROR_LABEL_NAME
    assert registry.list() == []


def test_a_label_carrying_the_child_name_is_refused_on_update(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    with pytest.raises(SubscriptionError):
        registry.update(created["id"], label="quastenflosser")


def test_the_label_defaults_to_the_class_name(tmp_path):
    store = _store(tmp_path)

    created = SubscriptionRegistry(store).create(CHILD_ID, ["timetable"], "")

    assert created["label"] == "5A"


def test_at_least_one_component_is_required(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)

    for invalid in ([], None, ["nonsense"], ["timetable", "nonsense"]):
        with pytest.raises(SubscriptionError) as error:
            registry.create(CHILD_ID, invalid, "5A")
        assert error.value.message_key == subscriptions.ERROR_COMPONENTS


def test_every_single_component_on_its_own_is_accepted(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)

    for name in subscriptions.COMPONENTS:
        created = registry.create(CHILD_ID, [name], "5A")
        assert created["components"] == [name]


def test_the_timetable_component_needs_a_holiday_region(tmp_path):
    store = _store(tmp_path, region="")

    with pytest.raises(SubscriptionError) as error:
        SubscriptionRegistry(store).create(CHILD_ID, ["timetable"], "5A")

    assert error.value.message_key == subscriptions.ERROR_REGION


def test_changing_the_selection_keeps_the_token(tmp_path):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    updated = registry.update(created["id"], components=["timetable", "public_holidays"])

    assert updated["token"] == created["token"]
    assert updated["components"] == ["timetable", "public_holidays"]


def test_the_summary_names_period_subject_and_teacher(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store))

    assert "SUMMARY:1. Stunde Deutsch (Behrens)" in ics


def test_a_lesson_without_a_teacher_keeps_the_summary_clean(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(teacher_code="", teacher_label="")]))

    ics = _build(store, _subscription(store))

    assert "SUMMARY:1. Stunde Deutsch" in ics
    assert "()" not in ics


def test_a_lesson_lasts_exactly_forty_five_minutes(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(start_time="08:00")]))

    ics = _build(store, _subscription(store))

    assert "DTSTART;TZID=Europe/Berlin:20260902T080000" in ics
    assert "DTEND;TZID=Europe/Berlin:20260902T084500" in ics


def test_a_double_lesson_stays_two_events(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot([_lesson(period=3, start_time="09:45"), _lesson(period=4, start_time="10:30")])
    )

    ics = _build(store, _subscription(store))

    assert ics.count("BEGIN:VEVENT") == 2
    assert "DTEND;TZID=Europe/Berlin:20260902T103000" in ics
    assert "DTSTART;TZID=Europe/Berlin:20260902T103000" in ics


def test_the_details_carry_everything_the_app_shows(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot(
            [
                _lesson(
                    change_kind="changed",
                    changed_fields=["room"],
                    previous={"subject": "", "teacher": "", "room": "R1"},
                    room="R2",
                    is_class_teacher=True,
                )
            ]
        )
    )

    ics = _build(store, _subscription(store))
    description = next(line for line in ics.split("\r\n") if line.startswith("DESCRIPTION:"))

    for fragment in (
        "Datum: 02.09.2026",
        "Uhrzeit: 08:00 – 08:45 Uhr",
        "Stunde: 1. Stunde",
        "Fach: Deutsch",
        "Lehrkraft: Behrens",
        "Raum: R2",
        "Rolle: Klassenlehrkraft",
        "Status: Diese Stunde wird vertreten.",
        "Raum: R1 → R2",
    ):
        assert fragment in description
    assert "LOCATION:R2" in ics


def test_a_double_booking_is_named_in_the_details(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot([_lesson(), _lesson(subject_code="E", subject_label="Englisch", room="R9")])
    )

    ics = _build(store, _subscription(store))

    assert ics.count("BEGIN:VEVENT") == 2
    assert "Doppelbelegung: 2" in ics


def test_a_cancelled_lesson_stays_visible_and_is_marked(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(change_kind="cancelled")]))

    ics = _build(store, _subscription(store))

    assert "SUMMARY:Entfällt · 1. Stunde Deutsch (Behrens)" in ics
    assert "TRANSP:TRANSPARENT" in ics
    assert "Diese Stunde entfällt." in ics


def test_no_status_cancelled_is_emitted_because_clients_hide_it(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(change_kind="cancelled")]))

    ics = _build(store, _subscription(store))

    assert "STATUS:CANCELLED" not in ics


def test_an_added_lesson_is_marked(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(change_kind="added")]))

    assert "SUMMARY:Zusätzlich · 1. Stunde Deutsch (Behrens)" in _build(
        store, _subscription(store)
    )


def test_a_substitution_keeps_the_uid_of_the_plain_lesson(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    subscription = _subscription(store)
    before = _uids(_build(store, subscription))

    store.save_calendar_snapshot(
        _snapshot([_lesson(subject_code="MA", subject_label="Mathe", change_kind="changed")])
    )
    after = _uids(_build(store, subscription))

    assert before == after


def test_two_children_never_share_a_uid(tmp_path):
    store = _store(tmp_path)
    snapshot = _snapshot([_lesson()])
    snapshot["children"][SECOND_CHILD_ID] = snapshot["children"][CHILD_ID]
    store.save_calendar_snapshot(snapshot)
    first = _subscription(store)
    second = _subscription(store, label="7B", child_id=SECOND_CHILD_ID)

    assert _uids(_build(store, first)) != _uids(_build(store, second))


def test_two_childrens_school_holidays_never_share_a_uid(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    calendar = FakeHolidayCalendar(
        days={"2026-10-03": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="u1")}
    )
    first = _subscription(store, ("school_holidays",))
    second = _subscription(store, ("school_holidays",), label="7B", child_id=SECOND_CHILD_ID)

    first_uids = _uids(_build(store, first, calendar))
    second_uids = _uids(_build(store, second, calendar))
    assert first_uids
    assert not set(first_uids) & set(second_uids)


def test_parallel_courses_get_stable_distinct_uids(tmp_path):
    store = _store(tmp_path)
    lessons = [_lesson(), _lesson(subject_code="E", subject_label="Englisch", room="R9")]
    store.save_calendar_snapshot(_snapshot(lessons))
    subscription = _subscription(store)

    first = _uids(_build(store, subscription))
    store.save_calendar_snapshot(_snapshot(list(reversed(lessons))))
    second = _uids(_build(store, subscription))

    assert len(set(first)) == 2
    assert first == second


def test_sequence_rises_only_when_the_content_changes(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    subscription = _subscription(store)

    first = _build(store, subscription)
    again = _build(store, subscription, now=NOW + timedelta(hours=3))
    assert "SEQUENCE:0" in first
    assert first == again

    store.save_calendar_snapshot(_snapshot([_lesson(room="R7")]))
    changed = _build(store, subscription, now=NOW + timedelta(hours=4))
    assert "SEQUENCE:1" in changed
    assert "LAST-MODIFIED:20260902T100000Z" in changed


def test_a_holiday_week_removes_every_lesson_iserv_still_reports(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot([_lesson(period=number, start_time="08:00") for number in range(1, 9)])
    )
    calendar = FakeHolidayCalendar(
        days={
            "2026-09-02": _day(
                free=True, overrides=True, kind="school", name_key="holidays.period.summer", period_id="p1"
            )
        }
    )

    ics = _build(store, _subscription(store), calendar)

    assert "BEGIN:VEVENT" not in ics


def test_a_group_holiday_leaves_the_lessons_alone(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    calendar = FakeHolidayCalendar(
        days={"2026-09-02": _day(free=True, overrides=False, kind="school", name="Jahrgang 5 frei")}
    )

    ics = _build(store, _subscription(store), calendar)

    assert "SUMMARY:1. Stunde Deutsch (Behrens)" in ics


def test_nothing_is_claimed_free_when_overrides_lessons_is_false(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    calendar = FakeHolidayCalendar(
        days={"2026-09-02": _day(free=True, overrides=False, kind="school", name="Jahrgang 5 frei")}
    )

    ics = _build(store, _subscription(store, ("school_holidays",)), calendar)

    assert "BEGIN:VEVENT" not in ics


def test_school_holidays_become_one_all_day_event_per_span(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    span = {
        day.isoformat(): _day(
            free=True, overrides=True, kind="school", name_key="holidays.period.autumn", period_id="p9"
        )
        for day in (date(2026, 10, 12) + timedelta(days=offset) for offset in range(5))
    }

    ics = _build(store, _subscription(store, ("school_holidays",)), FakeHolidayCalendar(days=span))

    assert ics.count("BEGIN:VEVENT") == 1
    assert "DTSTART;VALUE=DATE:20261012" in ics
    assert "DTEND;VALUE=DATE:20261017" in ics
    assert "SUMMARY:Herbstferien" in ics


def test_public_holidays_become_one_all_day_event_per_day(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    days = {
        "2026-10-03": _day(free=True, overrides=True, kind="public", name="Tag der Deutschen Einheit", period_id="u1"),
        "2026-12-25": _day(free=True, overrides=True, kind="public", name="Erster Weihnachtstag", period_id="u2"),
    }

    ics = _build(store, _subscription(store, ("public_holidays",)), FakeHolidayCalendar(days=days))

    assert ics.count("BEGIN:VEVENT") == 2
    assert "SUMMARY:Tag der Deutschen Einheit" in ics
    assert "DTSTART;VALUE=DATE:20261003" in ics
    assert "DTEND;VALUE=DATE:20261004" in ics


def test_the_two_holiday_components_stay_apart(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    days = {
        "2026-10-03": _day(free=True, overrides=True, kind="public", name="Tag der Deutschen Einheit", period_id="u1"),
        "2026-10-12": _day(free=True, overrides=True, kind="school", name_key="holidays.period.autumn", period_id="p9"),
    }
    calendar = FakeHolidayCalendar(days=days)

    school_only = _build(store, _subscription(store, ("school_holidays",)), calendar)
    public_only = _build(store, _subscription(store, ("public_holidays",)), calendar)

    assert "Herbstferien" in school_only and "Tag der Deutschen Einheit" not in school_only
    assert "Tag der Deutschen Einheit" in public_only and "Herbstferien" not in public_only


def test_an_unknown_holiday_status_drops_the_lessons_and_says_so(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))
    calendar = FakeHolidayCalendar(status=holidays.STATUS_UNKNOWN)

    ics = _build(store, _subscription(store), calendar)

    assert "SUMMARY:1. Stunde Deutsch (Behrens)" not in ics
    assert "Ferienabgleich nicht möglich" in ics


def test_an_old_snapshot_produces_a_visible_notice(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()], last_success=NOW_EPOCH - 30 * 60 * 60))

    ics = _build(store, _subscription(store))

    assert "Ranzenpost: keine neuen Daten" in ics
    assert "SUMMARY:1. Stunde Deutsch (Behrens)" in ics


def test_a_missing_snapshot_says_so_instead_of_looking_empty(tmp_path):
    store = _store(tmp_path)

    ics = _build(store, _subscription(store))

    assert "Ranzenpost: noch keine Daten" in ics


def test_a_lesson_without_a_start_time_is_not_dropped_silently(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(period=11, start_time="")]))

    ics = _build(store, _subscription(store))

    assert "SUMMARY:Stunden ohne Uhrzeit" in ics
    assert "11. Stunde Deutsch (Behrens)" in ics
    assert "DTSTART;VALUE=DATE:20260902" in ics


def test_local_time_stays_the_same_across_the_daylight_saving_boundary(tmp_path):
    store = _store(tmp_path)
    winter = _lesson(day="14.01.2027", start_time="08:00")
    summer = _lesson(day="17.06.2027", start_time="08:00")
    snapshot = {
        "children": {
            CHILD_ID: {
                "weeks": {
                    "11.01.2027": {"start_date": "11.01.2027", "end_date": "17.01.2027", "lessons": [winter]},
                    "14.06.2027": {"start_date": "14.06.2027", "end_date": "20.06.2027", "lessons": [summer]},
                },
                "last_success": int(datetime(2027, 1, 14, 6, 0).replace(tzinfo=timezone.utc).timestamp()),
            }
        }
    }
    store.save_calendar_snapshot(snapshot)

    ics = _build(store, _subscription(store), now=datetime(2027, 1, 14, 6, 0))
    assert "DTSTART;TZID=Europe/Berlin:20270114T080000" in ics
    assert berlin_offset(datetime(2027, 1, 14, 7, 0)) == 1

    ics = _build(store, _subscription(store), now=datetime(2027, 6, 17, 6, 0))
    assert "DTSTART;TZID=Europe/Berlin:20270617T080000" in ics
    assert berlin_offset(datetime(2027, 6, 17, 6, 0)) == 2


def test_the_timezone_block_carries_the_daylight_saving_rules(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store))

    assert ics.count("BEGIN:VTIMEZONE") == 1
    assert "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU" in ics
    assert "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU" in ics
    assert "TZOFFSETTO:+0200" in ics
    assert "TZOFFSETTO:+0100" in ics


def test_all_day_events_never_carry_a_timezone(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    days = {"2026-10-03": _day(free=True, overrides=True, kind="public", name="Feiertag", period_id="u1")}

    ics = _build(store, _subscription(store, ("public_holidays",)), FakeHolidayCalendar(days=days))

    assert "DTSTART;VALUE=DATE:20261003" in ics
    assert "TZID=Europe/Berlin:2026100" not in ics


def test_the_calendar_carries_the_subscription_label_and_no_name(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store, label="5A"))

    assert "X-WR-CALNAME:5A" in ics
    assert "NAME:5A" in ics


def test_an_empty_label_falls_back_to_a_translated_name(tmp_path):
    store = _store(tmp_path, children=[{"child_id": CHILD_ID, "name": CHILD_NAME}])
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store, label=""))

    assert "X-WR-CALNAME:Schulkalender" in ics


def test_the_calendar_skeleton_is_complete(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store))

    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert ics.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "METHOD:PUBLISH" in ics
    assert "PRODID:" in ics
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in ics
    assert "X-PUBLISHED-TTL:PT1H" in ics
    assert "X-WR-TIMEZONE:Europe/Berlin" in ics
    assert ics.count("\n") == ics.count("\r\n")


def test_text_fields_are_escaped(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(
        _snapshot([_lesson(subject_label="Mathe, Kurs; A\\B", room="Raum; 101")])
    )

    ics = _build(store, _subscription(store))

    assert "Mathe\\, Kurs\\; A\\\\B" in ics
    assert "LOCATION:Raum\\; 101" in ics


def test_long_lines_are_folded_at_seventy_five_octets():
    folded = feed_ics.fold_line("DESCRIPTION:" + "a" * 200)
    for piece in folded.split("\r\n"):
        assert len(piece.encode("utf-8")) <= 75
    assert "\r\n " in folded


def test_folding_never_splits_a_multibyte_character():
    folded = feed_ics.fold_line("SUMMARY:" + "ä" * 120)
    for piece in folded.split("\r\n"):
        piece.encode("utf-8").decode("utf-8")
        assert len(piece.encode("utf-8")) <= 75


def test_the_feed_speaks_the_language_the_app_is_set_to(tmp_path):
    store = _store(tmp_path, language="en")
    store.save_calendar_snapshot(_snapshot([_lesson(change_kind="cancelled")]))

    ics = _build(store, _subscription(store))

    assert "Lesson 1 Deutsch (Behrens)" in ics
    assert "Date: 02.09.2026" in ics
    assert "Datum:" not in ics


def test_no_german_calendar_text_is_wired_into_the_backend_code():
    source = "".join(
        Path(module.__file__).read_text(encoding="utf-8") for module in (feed, feed_ics, marks)
    )
    for word in ("Stunde", "Entfällt", "Datum", "Uhrzeit", "Ferien", "Lehrkraft", "Prüfung"):
        assert word not in source


def test_every_calendar_key_exists_in_every_bundle():
    keys = [key for key in messages.BASE_MESSAGES if key.startswith("calendar.") or key.startswith("api.calendar.")]
    assert keys
    for language in messages.LANGUAGES:
        bundle = messages.bundle(language)
        assert [key for key in keys if key not in bundle] == []


def test_the_whole_calendar_carries_a_colour(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store))

    assert "COLOR:teal" in ics
    assert "X-APPLE-CALENDAR-COLOR:#0E6B70FF" in ics


def test_a_chosen_calendar_colour_wins(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    ics = _build(store, _subscription(store, color="#b4602a"))

    assert "X-APPLE-CALENDAR-COLOR:#B4602AFF" in ics


def test_the_subject_colour_is_read_from_the_configuration_at_request_time(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson(color="#0e6b70")]))
    subscription = _subscription(store)
    assert _build(store, subscription).count("COLOR:teal") == 2

    config = store.load_config()
    config["subjects"] = {"D": {"label": "Deutsch", "color": "#c71585"}}
    store.save_config(config)

    later = _build(store, subscription, now=NOW + timedelta(hours=2))
    assert "COLOR:mediumvioletred" in later
    assert later.count("COLOR:teal") == 1


def test_every_event_carries_the_subject_as_a_category(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([_lesson()]))

    assert "CATEGORIES:Deutsch" in _build(store, _subscription(store))


def test_only_css3_colour_names_are_emitted():
    assert feed_ics.nearest_color_name("#0e6b70") in feed_ics.CSS3_COLORS
    assert feed_ics.nearest_color_name("not a colour") == ""
    assert feed_ics.nearest_color_name("") == ""


def test_holiday_events_never_carry_a_colour_or_category(tmp_path):
    store = _store(tmp_path)
    store.save_calendar_snapshot(_snapshot([]))
    days = {"2026-10-03": _day(free=True, overrides=True, kind="public", name="Feiertag", period_id="u1")}

    ics = _build(store, _subscription(store, ("public_holidays",)), FakeHolidayCalendar(days=days))

    assert "CATEGORIES:" not in ics
