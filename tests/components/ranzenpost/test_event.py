from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

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


async def test_a_change_that_is_no_longer_new_never_fires(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    await poll_with_changes(hass, aioclient_mock, frozen_now, [dict(FRESH, new=False), *fixture("changes")])

    assert hass.states.get(ALEX).state == "unknown"


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
