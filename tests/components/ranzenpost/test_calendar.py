from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, SCHOOL, setup_entry

LESSONS = "calendar.ranzenpost_alex_lessons"
EXAMS = "calendar.ranzenpost_alex_exams"
ABSENCES = "calendar.ranzenpost_alex_absences"
HOLIDAYS = "calendar.ranzenpost_school_holidays"
WINDOW = "start=2026-09-02T00:00:00%2B02:00&end=2026-09-03T00:00:00%2B02:00"


def events_calls(aioclient_mock, kind, child=None, window=""):
    return [
        call
        for call in aioclient_mock.mock_calls
        if "/api/integration/events" in str(call[1])
        and f"kind={kind}" in str(call[1])
        and (child is None or f"child={child}" in str(call[1]))
        and window in str(call[1])
    ]


async def test_every_calendar_exists_with_its_unique_id(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    registry = er.async_get(hass)

    entry_id = registry.async_get(LESSONS).config_entry_id
    assert registry.async_get(LESSONS).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_lessons"
    assert registry.async_get(EXAMS).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_exams"
    assert registry.async_get(ABSENCES).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_absences"
    assert registry.async_get(HOLIDAYS).unique_id == f"{DOMAIN}_{entry_id}_school_{SCHOOL}_holidays"
    assert len(hass.states.async_entity_ids("calendar")) == 7


async def test_the_lessons_calendar_is_on_during_the_current_lesson(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    state = hass.states.get(LESSONS)
    assert state.state == "on"
    assert state.attributes["message"] == "Maths"
    assert state.attributes["location"] == "R101"
    assert state.attributes["start_time"] == "2026-09-02 09:00:00"
    assert state.attributes["end_time"] == "2026-09-02 09:45:00"


async def test_the_next_event_skips_cancelled_lessons(hass, aioclient_mock, frozen_now):
    frozen_now.move_to("2026-09-02T08:00:00+00:00")
    await setup_entry(hass, aioclient_mock)

    state = hass.states.get(LESSONS)
    assert state.state == "off"
    assert state.attributes["message"] == "Biology"


async def test_all_day_calendars_expose_their_next_event(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    absences = hass.states.get(ABSENCES)
    assert absences.state == "off"
    assert absences.attributes["message"] == "Sick note"
    assert absences.attributes["all_day"] is True
    holidays = hass.states.get(HOLIDAYS)
    assert holidays.attributes["message"] == "Autumn holidays"
    assert holidays.attributes["start_time"] == "2026-10-12 00:00:00"
    assert holidays.attributes["end_time"] == "2026-10-24 00:00:00"
    exams = hass.states.get(EXAMS)
    assert exams.attributes["message"] == "Exam: Biology"
    assert exams.attributes["name"] == "Chapter 3"
    assert exams.attributes["start"] == "2026-09-03T08:00:00+02:00"
    assert absences.attributes["kind"] == "sick"
    assert absences.attributes["start"] == "2026-09-04"
    assert holidays.attributes["summary"] == "Autumn holidays"


async def test_get_events_keeps_cancelled_lessons_with_the_addon_summary(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()

    response = await client.get(f"/api/calendars/{LESSONS}?{WINDOW}")
    assert response.status == 200
    events = await response.json()

    assert [event["summary"] for event in events] == ["Maths", "Cancelled: Art"]
    assert events[1]["description"] == "Ms Brush, R303\nThis lesson is cancelled"
    assert events[1]["location"] == "R303"
    assert events[1]["uid"] == "lesson-20260902-p4@sample"
    assert events[0]["start"] == {"dateTime": "2026-09-02T09:00:00+02:00"}
    assert events[0]["end"] == {"dateTime": "2026-09-02T09:45:00+02:00"}
    assert [event["color"] for event in events] == ["#3366cc", ""]
    assert [event["cancelled"] for event in events] == [False, True]
    calls = events_calls(aioclient_mock, "lessons", CHILD_1)
    assert "start=2026-09-02&end=2026-09-03" in str(calls[-1][1])


async def test_get_events_serves_all_day_events_with_exclusive_end(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()

    response = await client.get(
        f"/api/calendars/{HOLIDAYS}?start=2026-10-01T00:00:00%2B02:00&end=2026-11-01T00:00:00%2B01:00"
    )
    events = await response.json()

    assert events == [
        {
            "summary": "Autumn holidays",
            "description": None,
            "location": None,
            "uid": "holiday-20261012@sample",
            "recurrence_id": None,
            "rrule": None,
            "start": {"date": "2026-10-12"},
            "end": {"date": "2026-10-24"},
            "color": "",
            "cancelled": False,
            "subject_code": "",
            "subject": "",
            "name": "",
            "kind": "",
        }
    ]


async def test_lesson_and_exam_events_carry_the_subject_code_and_name(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()

    lessons = await (await client.get(f"/api/calendars/{LESSONS}?start=2026-09-02T00:00:00%2B02:00&end=2026-09-04T00:00:00%2B02:00")).json()
    exams = await (await client.get(f"/api/calendars/{EXAMS}?start=2026-09-02T00:00:00%2B02:00&end=2026-09-04T00:00:00%2B02:00")).json()

    assert [(event["subject_code"], event["subject"]) for event in lessons] == [("MA", "Maths"), ("AR", "Art"), ("BI", "Biology")]
    assert [(event["subject_code"], event["subject"]) for event in exams] == [("BI", "Biology")]


async def test_get_events_caches_a_window_for_five_minutes(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    window = "start=2026-09-02&end=2026-09-03"
    assert events_calls(aioclient_mock, "lessons", CHILD_1, window) == []

    await client.get(f"/api/calendars/{LESSONS}?{WINDOW}")
    await client.get(f"/api/calendars/{LESSONS}?{WINDOW}")
    assert len(events_calls(aioclient_mock, "lessons", CHILD_1, window)) == 1

    frozen_now.tick(timedelta(minutes=5, seconds=1))
    await client.get(f"/api/calendars/{LESSONS}?{WINDOW}")
    assert len(events_calls(aioclient_mock, "lessons", CHILD_1, window)) == 2


async def test_the_upcoming_window_is_refreshed_through_the_cache(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    assert len(events_calls(aioclient_mock, "lessons", CHILD_1)) == 1

    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(events_calls(aioclient_mock, "lessons", CHILD_1)) == 1

    frozen_now.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(events_calls(aioclient_mock, "lessons", CHILD_1)) == 2
    assert hass.states.get(LESSONS).state == "on"
