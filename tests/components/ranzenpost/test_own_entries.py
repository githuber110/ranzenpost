from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, fixture, mock_addon, setup_entry

OWN = "calendar.ranzenpost_alex_own_entries"


def info_sharing(shared):
    info = fixture("info")
    info["schools"][0]["own_entries"] = shared
    return info


def own_calls(aioclient_mock):
    return [call for call in aioclient_mock.mock_calls if "kind=own_entries" in str(call[1])]


async def test_without_the_setting_there_is_no_own_entries_calendar_and_no_request(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(OWN) is None
    assert er.async_get(hass).async_get(OWN) is None
    assert own_calls(aioclient_mock) == []


async def test_with_the_setting_each_child_gets_an_own_entries_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock, info=info_sharing(True))
    registry = er.async_get(hass)
    entry_id = registry.async_get(OWN).config_entry_id
    assert registry.async_get(OWN).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_own_entries"
    assert registry.async_get(OWN).translation_key == "own_entries"
    assert hass.states.get("calendar.ranzenpost_kim_own_entries") is not None
    state = hass.states.get(OWN)
    assert state.state == "off"
    assert state.attributes["message"] == "Chess club"
    assert state.attributes["kind"] == "own_entries"
    client = await hass_client()
    events = await (await client.get(f"/api/calendars/{OWN}?start=2026-09-02T00:00:00%2B02:00&end=2026-09-04T00:00:00%2B02:00")).json()
    assert [(event["summary"], event["start"]) for event in events] == [
        ("Chess club", {"dateTime": "2026-09-02T15:00:00+02:00"}),
        ("Dentist", {"dateTime": "2026-09-03T16:00:00+02:00"}),
    ]


async def test_switching_the_setting_reloads_and_adds_or_forgets_the_calendar(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert er.async_get(hass).async_get(OWN) is None
    for shared, present in ((True, True), (False, False)):
        aioclient_mock.clear_requests()
        mock_addon(aioclient_mock, info=info_sharing(shared))
        frozen_now.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert (er.async_get(hass).async_get(OWN) is not None) == present
        assert (hass.states.get(OWN) is not None) == present


async def test_an_addon_without_the_flag_counts_as_switched_off(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    del info["schools"][0]["own_entries"]
    await setup_entry(hass, aioclient_mock, info=info)
    assert hass.states.get(OWN) is None
