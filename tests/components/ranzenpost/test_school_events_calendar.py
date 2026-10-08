from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.api import Modules
from custom_components.ranzenpost.const import DOMAIN

from . import SCHOOL, SECOND_SCHOOL, fixture, mock_addon, setup_entry, two_schools_info

SCHOOL_EVENTS = "calendar.ranzenpost_school_school_events"
HOLIDAYS = "calendar.ranzenpost_school_holidays"


def info_with_calendar(available=True, disabled=False):
    info = fixture("info")
    info["schools"][0]["modules"]["calendar"] = available
    info["schools"][0]["disabled"]["calendar"] = disabled
    return info


def registry_snapshot(hass):
    registry = er.async_get(hass)
    return {
        entry.entity_id: (entry.unique_id, entry.device_id, entry.translation_key)
        for entry in registry.entities.values()
        if entry.platform == DOMAIN
    }


def school_events_calls(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if "kind=school_events" in str(call[1])]


async def test_without_the_calendar_module_no_school_events_calendar_exists(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(SCHOOL_EVENTS) is None
    assert school_events_calls(aioclient_mock) == []


async def test_an_addon_without_the_calendar_flag_creates_no_school_events_calendar(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0]["modules"].pop("calendar")
    info["schools"][0]["disabled"].pop("calendar")
    await setup_entry(hass, aioclient_mock, info=info)
    assert hass.states.get(SCHOOL_EVENTS) is None


async def test_a_switched_off_calendar_creates_no_school_events_calendar(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=info_with_calendar(disabled=True))
    assert hass.states.get(SCHOOL_EVENTS) is None


def test_the_calendar_module_counts_only_when_the_addon_confirms_it():
    assert not Modules.from_json({}).has("calendar")
    assert not Modules.from_json({"calendar": None}).has("calendar")
    assert Modules.from_json({"calendar": True}).has("calendar")
    assert not Modules.from_json({"calendar": True}, {"calendar": True}).has("calendar")
    assert Modules.from_json({}).has("timetable")
    assert Modules.from_json({"timetable": None}).has("timetable")


async def test_the_school_events_calendar_gets_its_own_unique_id_and_keeps_every_other_entity(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock)
    before = registry_snapshot(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_calendar())
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    after = registry_snapshot(hass)

    assert set(after) - set(before) == {SCHOOL_EVENTS}
    assert {key: value for key, value in after.items() if key in before} == before
    unique_id = f"{DOMAIN}_{entry.entry_id}_school_{SCHOOL}_school_events"
    assert after[SCHOOL_EVENTS][0] == unique_id
    assert after[SCHOOL_EVENTS][1] == after[HOLIDAYS][1]
    assert after[SCHOOL_EVENTS][2] == "school_events"
    assert unique_id not in {value[0] for value in before.values()}
    assert hass.states.get(SCHOOL_EVENTS).attributes["friendly_name"] == "Ranzenpost Sample School School events"


async def test_the_school_events_calendar_shows_the_next_event_from_the_addon(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=info_with_calendar())
    state = hass.states.get(SCHOOL_EVENTS)
    assert state.state == "off"
    assert state.attributes["message"] == "Parents evening"
    assert state.attributes["location"] == "Hall"
    assert state.attributes["start_time"] == "2026-09-04 18:00:00"
    assert state.attributes["kind"] == "school_event"
    assert any(f"school={SCHOOL}" in str(call[1]) for call in school_events_calls(aioclient_mock))


async def test_get_events_serves_timed_and_all_day_school_events(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock, info=info_with_calendar())
    client = await hass_client()

    response = await client.get(
        f"/api/calendars/{SCHOOL_EVENTS}?start=2026-09-01T00:00:00%2B02:00&end=2026-09-30T00:00:00%2B02:00"
    )
    events = await response.json()

    assert [event["summary"] for event in events] == ["Parents evening", "Sports day"]
    assert events[0]["start"] == {"dateTime": "2026-09-04T18:00:00+02:00"}
    assert events[0]["location"] == "Hall"
    assert events[1]["start"] == {"date": "2026-09-10"}
    assert events[1]["end"] == {"date": "2026-09-11"}
    assert [event["kind"] for event in events] == ["school_event", "school_event"]


async def test_every_school_with_the_calendar_gets_its_own_school_events_calendar(hass, aioclient_mock, frozen_now):
    info = two_schools_info()
    info["schools"][0]["modules"]["calendar"] = True
    entry = await setup_entry(hass, aioclient_mock, info=info)
    registry = er.async_get(hass)
    first = registry.async_get("calendar.ranzenpost_school_sample_school_school_events")
    assert first.unique_id == f"{DOMAIN}_{entry.entry_id}_school_{SCHOOL}_school_events"
    assert registry.async_get_entity_id("calendar", DOMAIN, f"{DOMAIN}_{entry.entry_id}_school_{SECOND_SCHOOL}_school_events") is None
    assert hass.states.get("calendar.ranzenpost_school_other_school_holidays") is not None


async def test_switching_the_calendar_off_later_forgets_the_school_events_calendar(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=info_with_calendar())
    assert hass.states.get(SCHOOL_EVENTS) is not None

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_calendar(disabled=True))
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert er.async_get(hass).async_get(SCHOOL_EVENTS) is None
    assert hass.states.get(HOLIDAYS) is not None
