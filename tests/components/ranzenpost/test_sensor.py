from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, CHILD_2, SCHOOL, setup_entry

ALEX = "sensor.ranzenpost_alex"
KIM = "sensor.ranzenpost_kim"
SCHOOL_ID = SCHOOL
SCHOOL = "sensor.ranzenpost_school"


async def test_lesson_sensors_expose_subject_and_details(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    current = hass.states.get(f"{ALEX}_current_lesson")
    assert current.state == "Maths"
    assert current.attributes["teacher"] == "Mrs Example"
    assert current.attributes["room"] == "R101"
    assert current.attributes["start"] == "2026-09-02T09:00:00+02:00"
    assert current.attributes["end"] == "2026-09-02T09:45:00+02:00"
    assert current.attributes["substitution"] is False
    assert current.attributes["cancelled"] is False
    assert current.attributes["note"] == ""

    upcoming = hass.states.get(f"{ALEX}_next_lesson")
    assert upcoming.state == "English"
    assert upcoming.attributes["substitution"] is True
    assert upcoming.attributes["kind"] == "substitution"
    assert upcoming.attributes["period"] == 2
    assert upcoming.attributes["weekday"] == "wednesday"
    assert upcoming.attributes["minutes_until"] == 35
    assert upcoming.attributes["minutes_left"] == 80
    assert current.attributes["minutes_until"] == 0
    assert current.attributes["minutes_left"] == 30


async def test_lesson_sensors_read_none_without_a_lesson(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    assert hass.states.get(f"{KIM}_current_lesson").state == "none"
    assert hass.states.get(f"{KIM}_next_lesson").state == "none"
    assert "minutes_until" not in hass.states.get(f"{KIM}_next_lesson").attributes


async def test_timestamp_sensors_carry_the_device_class(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    end = hass.states.get(f"{ALEX}_school_end_today")
    assert end.state == "2026-09-02T11:05:00+00:00"
    assert end.attributes["device_class"] == "timestamp"
    assert hass.states.get(f"{ALEX}_next_school_day").state == "2026-09-03T06:00:00+00:00"
    assert hass.states.get(f"{ALEX}_next_school_day").attributes["device_class"] == "timestamp"
    assert hass.states.get(f"{KIM}_next_school_day").state == "unknown"
    assert hass.states.get(f"{ALEX}_timetable_last_updated").state == "2026-09-01T16:30:00+00:00"
    assert hass.states.get(f"{KIM}_school_end_today").state == "unknown"
    assert hass.states.get(f"{KIM}_timetable_last_updated").state == "unknown"
    for entity_id in (f"{ALEX}_school_end_today", f"{ALEX}_timetable_last_updated", f"{SCHOOL}_next_conference"):
        assert "state_class" not in hass.states.get(entity_id).attributes


async def test_counting_sensors_carry_their_lists(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    changes = hass.states.get(f"{ALEX}_changes_today")
    assert changes.state == "2"
    assert [item["subject"] for item in changes.attributes["changes"]] == ["English", "Art"]
    assert changes.attributes["changes"][1]["cancelled"] is True

    letters = hass.states.get(f"{ALEX}_unread_letters")
    assert letters.state == "2"
    assert [item["title"] for item in letters.attributes["letters"]] == ["Field trip", "Photo day"]
    posts = hass.states.get(f"{ALEX}_unread_posts")
    assert posts.state == "1"
    assert [item["title"] for item in posts.attributes["posts"]] == ["Lost and found"]

    absences = hass.states.get(f"{ALEX}_open_absences")
    assert absences.state == "1"
    assert absences.attributes["absences"] == [
        {
            "kind": "sick",
            "summary": "Sick note",
            "start": "2026-09-04",
            "end": "2026-09-04",
            "status": "pending",
            "days_until": 2,
        }
    ]
    assert hass.states.get(f"{KIM}_open_absences").state == "0"

    exams = hass.states.get(f"{ALEX}_exams_upcoming")
    assert exams.state == "2"
    assert [item["subject"] for item in exams.attributes["exams"]] == ["Biology", "Maths"]
    assert hass.states.get(f"{ALEX}_next_exam").state == "Biology"
    assert hass.states.get(f"{ALEX}_next_exam").attributes["name"] == "Chapter 3"
    assert hass.states.get(f"{KIM}_next_exam").state == "none"


async def test_school_sensors_describe_holiday_conference_and_connection(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    holiday = hass.states.get(f"{SCHOOL}_next_holiday")
    assert holiday.state == "Autumn holidays"
    assert holiday.attributes["start"] == "2026-10-12"
    assert holiday.attributes["end"] == "2026-10-23"

    conference = hass.states.get(f"{SCHOOL}_next_conference")
    assert conference.state == "2026-11-04T23:00:00+00:00"
    assert conference.attributes["title"] == "Parent-teacher conference"
    assert conference.attributes["device_class"] == "timestamp"

    connection = hass.states.get(f"{SCHOOL}_connection")
    assert connection.state == "ok"
    assert connection.attributes["options"] == ["ok", "error", "unconfigured", "unreachable", "auth_failed"]
    assert connection.attributes["last_poll"] == "2026-09-02T09:00:00+02:00"
    assert connection.attributes["version"] == "2609.02.00"
    assert connection.attributes["feed_port_open"] is True


async def test_unique_ids_and_diagnostic_category_follow_the_scheme(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    registry = er.async_get(hass)

    entry_id = registry.async_get(f"{ALEX}_current_lesson").config_entry_id
    assert registry.async_get(f"{ALEX}_current_lesson").unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_current_lesson"
    assert registry.async_get(f"{KIM}_unread_posts").unique_id == f"{DOMAIN}_{entry_id}_{CHILD_2}_unread_posts"
    assert registry.async_get(f"{SCHOOL}_connection").unique_id == f"{DOMAIN}_{entry_id}_school_{SCHOOL_ID}_connection"
    assert registry.async_get(f"{SCHOOL}_connection").entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(f"{ALEX}_timetable_last_updated").entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(f"{ALEX}_unread_letters").entity_category is None


async def test_every_child_gets_the_full_sensor_set(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    keys = (
        "current_lesson",
        "next_lesson",
        "school_end_today",
        "next_school_day",
        "changes_today",
        "next_exam",
        "exams_upcoming",
        "unread_letters",
        "unread_posts",
        "open_absences",
        "next_absence",
        "timetable_last_updated",
    )
    for prefix in (ALEX, KIM):
        for key in keys:
            assert hass.states.get(f"{prefix}_{key}") is not None, key
    for key in ("next_holiday", "next_conference", "connection"):
        assert hass.states.get(f"{SCHOOL}_{key}") is not None, key
    assert len(hass.states.async_entity_ids("sensor")) == 2 * len(keys) + 3


async def test_next_absence_sensor_reads_the_earliest_open_absence(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    absence = hass.states.get(f"{ALEX}_next_absence")
    assert absence.state == "2026-09-04"
    assert absence.attributes["kind"] == "sick"
    assert absence.attributes["summary"] == "Sick note"
    assert absence.attributes["start"] == "2026-09-04"
    assert absence.attributes["end"] == "2026-09-04"
    assert absence.attributes["status"] == "pending"
    assert absence.attributes["days_until"] == 2

    assert hass.states.get(f"{KIM}_next_absence").state == "none"
    assert hass.states.get(f"{KIM}_next_absence").attributes.get("days_until") is None
