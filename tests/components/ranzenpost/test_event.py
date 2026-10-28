from datetime import timedelta
from unittest.mock import patch

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import CoreState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, CHILD_2, fixture, mock_addon, route, setup_entry

ALEX = "event.ranzenpost_alex_timetable_changed"
KIM = "event.ranzenpost_kim_timetable_changed"
FRESH = {
    "child_key": CHILD_1,
    "school_id": "a1b2c3d4",
    "at": "2026-09-02T09:20:00+02:00",
    "kind": "cancellation",
    "summary": "Sport is cancelled",
    "date": "2026-09-03",
    "period": 5,
    "new": True,
}


async def poll_with_changes(hass, aioclient_mock, frozen_now, changes, info=None):
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info, changes=changes)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_event_entities_start_without_a_fired_event(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    for entity_id in (ALEX, KIM):
        state = hass.states.get(entity_id)
        assert state.state == "unknown"
        assert state.attributes["event_types"] == ["substitution", "cancellation", "room_change", "new_lesson"]
    registry = er.async_get(hass)
    entry_id = registry.async_get(ALEX).config_entry_id
    assert registry.async_get(ALEX).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_timetable_changed"
    assert registry.async_get(KIM).unique_id == f"{DOMAIN}_{entry_id}_{CHILD_2}_timetable_changed"


async def test_a_new_change_fires_the_event_for_its_child_only(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])

    fired = hass.states.get(ALEX)
    assert fired.state != "unknown"
    assert fired.attributes["event_type"] == "cancellation"
    assert fired.attributes["child"] == "Alex Sample"
    assert fired.attributes["summary"] == "Sport is cancelled"
    assert fired.attributes["date"] == "2026-09-03"
    assert fired.attributes["period"] == 5
    assert hass.states.get(KIM).state == "unknown"


async def test_the_same_change_is_not_fired_twice(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])
    first = hass.states.get(ALEX)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])
    assert hass.states.get(ALEX).state == first.state

    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])
    assert hass.states.get(ALEX).state == first.state


async def test_a_change_home_assistant_sees_first_fires_although_the_app_no_longer_calls_it_new(
    hass, aioclient_mock, frozen_now
):
    await setup_entry(hass, aioclient_mock)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])
    first = hass.states.get(ALEX)
    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])

    assert first.attributes["event_type"] == "cancellation"
    assert hass.states.get(ALEX).state == first.state


async def test_a_change_from_while_home_assistant_was_away_fires_once_after_the_restart(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, changes=[dict(FRESH, new=False), *fixture("changes")])
    events = async_capture_events(hass, "ranzenpost_event")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    fired = hass.states.get(ALEX)
    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert fired.attributes["event_type"] == "cancellation"
    assert fired.attributes["summary"] == "Sport is cancelled"
    assert [(event.data["type"], event.data["summary"]) for event in events] == [("lesson_cancelled", "Sport is cancelled")]
    assert hass.states.get(KIM).state == "unknown"


async def test_a_manual_refresh_between_two_polls_loses_no_change(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, changes=[FRESH, *fixture("changes")])
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    first = hass.states.get(ALEX)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])

    assert first.attributes["event_type"] == "cancellation"
    assert hass.states.get(ALEX).state == first.state


async def test_a_failed_poll_between_two_good_ones_does_not_repeat_the_event(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])
    first = hass.states.get(ALEX)

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), status=500, json={"error": "boom"})
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ALEX).state == "unavailable"

    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])
    assert hass.states.get(ALEX).state == first.state


async def test_removing_the_entry_forgets_the_changes_it_has_seen(hass, aioclient_mock, frozen_now, hass_storage):
    entry = await setup_entry(hass, aioclient_mock)
    key = f"{DOMAIN}.{entry.entry_id}.changes"
    assert len(hass_storage[key]["data"]["seen"]) == len(fixture("changes"))

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert key not in hass_storage


SECOND = dict(FRESH, kind="substitution", summary="English with Mr Stand-in", period=6)


async def test_two_changes_of_one_poll_are_both_recorded_by_the_event_entity(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    changed = async_capture_events(hass, EVENT_STATE_CHANGED)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, SECOND, *fixture("changes")])

    recorded = [event.data["new_state"] for event in changed if event.data["entity_id"] == ALEX]
    assert sorted(state.attributes["event_type"] for state in recorded) == ["cancellation", "substitution"]


async def test_changes_found_while_home_assistant_starts_fire_once_it_has_started(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, changes=[FRESH, *fixture("changes")])
    events = async_capture_events(hass, "ranzenpost_event")
    hass.set_state(CoreState.not_running)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert events == []
    assert hass.states.get(ALEX).state == "unknown"

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])

    assert [event.data["summary"] for event in events] == ["Sport is cancelled"]
    assert hass.states.get(ALEX).attributes["event_type"] == "cancellation"


async def test_a_poll_that_fails_after_reading_the_changes_keeps_them_new(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    events = async_capture_events(hass, "ranzenpost_event")

    with patch("custom_components.ranzenpost.coordinator.signals_between", side_effect=RuntimeError("boom")):
        await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])
    assert events == []
    await poll_with_changes(hass, aioclient_mock, frozen_now, [FRESH, *fixture("changes")])

    assert [event.data["summary"] for event in events] == ["Sport is cancelled"]
