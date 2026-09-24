from datetime import timedelta

import pytest
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.device_automation.exceptions import InvalidDeviceAutomationConfig
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_get_device_automations, async_mock_service

from custom_components.ranzenpost.const import CHILD_CONDITIONS, DOMAIN
from custom_components.ranzenpost.device_condition import async_condition_from_config, async_validate_condition_config

from . import CHILD_1, CHILD_2, SCHOOL, fixture, setup_entry

FROZEN_LESSON_END = "2026-09-02T07:46:00+00:00"


def child_device(hass, entry, child_key=CHILD_1):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{child_key}")})


def school_device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})


def condition_of(device_id, kind):
    return {"condition": "device", "domain": DOMAIN, "device_id": device_id, "type": kind}


async def ranzenpost_conditions(hass, device_id):
    listed = await async_get_device_automations(hass, DeviceAutomationType.CONDITION, device_id)
    return [item for item in listed if item["domain"] == DOMAIN]


async def test_child_devices_with_a_timetable_list_both_conditions(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    conditions = await ranzenpost_conditions(hass, child_device(hass, entry).id)
    school = await ranzenpost_conditions(hass, school_device(hass, entry).id)

    assert [item["type"] for item in conditions] == list(CHILD_CONDITIONS)
    assert all(item["condition"] == "device" for item in conditions)
    assert school == []


async def test_a_child_without_the_timetable_module_lists_no_condition(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0]["modules"]["timetable"] = False
    entry = await setup_entry(hass, aioclient_mock, info=info)

    conditions = await ranzenpost_conditions(hass, child_device(hass, entry).id)

    assert conditions == []


async def test_a_condition_on_a_school_device_is_refused(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    with pytest.raises(InvalidDeviceAutomationConfig):
        await async_validate_condition_config(hass, condition_of(school_device(hass, entry).id, "is_school_day"))
    assert await async_validate_condition_config(hass, condition_of(child_device(hass, entry).id, "is_school_day"))


async def test_is_school_day_follows_the_state_of_each_child(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    alex = async_condition_from_config(hass, condition_of(child_device(hass, entry).id, "is_school_day"))
    kim = async_condition_from_config(hass, condition_of(child_device(hass, entry, CHILD_2).id, "is_school_day"))

    assert alex(hass, {}) is True
    assert kim(hass, {}) is False


async def test_lesson_running_is_true_only_while_the_clock_is_inside_a_lesson(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    running = async_condition_from_config(hass, condition_of(child_device(hass, entry).id, "lesson_running"))
    kim = async_condition_from_config(hass, condition_of(child_device(hass, entry, CHILD_2).id, "lesson_running"))

    assert running(hass, {}) is True
    assert kim(hass, {}) is False

    frozen_now.move_to(FROZEN_LESSON_END)
    assert running(hass, {}) is False

    frozen_now.tick(timedelta(minutes=5))
    assert running(hass, {}) is True


async def test_the_condition_is_false_once_the_entry_is_unloaded(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    checker = async_condition_from_config(hass, condition_of(child_device(hass, entry).id, "is_school_day"))
    assert checker(hass, {}) is True

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert checker(hass, {}) is False


async def test_an_automation_uses_the_condition(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {"platform": "event", "event_type": "test_event_alex"},
                    "condition": condition_of(child_device(hass, entry).id, "is_school_day"),
                    "action": {"service": "test.automation", "data": {"value": "alex"}},
                },
                {
                    "trigger": {"platform": "event", "event_type": "test_event_kim"},
                    "condition": condition_of(child_device(hass, entry, CHILD_2).id, "is_school_day"),
                    "action": {"service": "test.automation", "data": {"value": "kim"}},
                },
            ]
        },
    )
    await hass.async_block_till_done()

    hass.bus.async_fire("test_event_alex")
    hass.bus.async_fire("test_event_kim")
    await hass.async_block_till_done()

    assert [call.data["value"] for call in calls] == ["alex"]
