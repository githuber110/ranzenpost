from homeassistant.helpers import entity_registry as er

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, setup_entry

ALEX = "binary_sensor.ranzenpost_alex"
KIM = "binary_sensor.ranzenpost_kim"


async def test_binary_sensors_follow_the_child_state(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    assert hass.states.get(f"{ALEX}_school_day_today").state == "on"
    assert hass.states.get(f"{ALEX}_timetable_changed_today").state == "on"
    assert hass.states.get(f"{KIM}_school_day_today").state == "off"
    assert hass.states.get(f"{KIM}_timetable_changed_today").state == "off"
    assert len(hass.states.async_entity_ids("binary_sensor")) == 4


async def test_binary_sensor_unique_ids_follow_the_scheme(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    registry = er.async_get(hass)

    entry_id = registry.async_get(f"{ALEX}_school_day_today").config_entry_id
    assert registry.async_get(f"{ALEX}_school_day_today").unique_id == f"{DOMAIN}_{entry_id}_{CHILD_1}_school_day_today"
    assert (
        registry.async_get(f"{ALEX}_timetable_changed_today").unique_id
        == f"{DOMAIN}_{entry_id}_{CHILD_1}_timetable_changed_today"
    )
