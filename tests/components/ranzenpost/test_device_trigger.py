import json
import pathlib
from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.device_automation.exceptions import InvalidDeviceAutomationConfig
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.ranzenpost.const import CHILD_TRIGGERS, DOMAIN, SCHOOL_TRIGGERS
from custom_components.ranzenpost.device_trigger import async_validate_trigger_config

from . import CHILD_1, CHILD_2, SCHOOL, fixture, mock_addon, setup_entry

INTEGRATION = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost"
FRESH_CANCELLATION = {
    "child_key": CHILD_1,
    "school_id": SCHOOL,
    "at": "2026-09-02T09:20:00+02:00",
    "kind": "cancellation",
    "summary": "Sport is cancelled",
    "date": "2026-09-03",
    "period": 5,
    "new": True,
}


def child_device(hass, entry, child_key=CHILD_1):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{child_key}")})


def school_device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})


def trigger_of(device_id, kind):
    return {"platform": "device", "domain": DOMAIN, "device_id": device_id, "type": kind}


async def ranzenpost_triggers(hass, device_id):
    listed = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device_id)
    return [item for item in listed if item["domain"] == DOMAIN]


async def poll(hass, aioclient_mock, frozen_now, info=None, changes=None, states=None):
    aioclient_mock.clear_requests()
    for child_key, state in (states or {}).items():
        aioclient_mock.get(f"http://addon-host:8099/api/integration/state?child={child_key}", json=state)
    mock_addon(aioclient_mock, info=info, changes=changes)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def automations_with(hass, *pairs):
    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {"trigger": trigger, "action": {"service": "test.automation", "data_template": {"value": template}}}
                for trigger, template in pairs
            ]
        },
    )
    await hass.async_block_till_done()
    return calls


async def test_child_devices_list_the_child_triggers_and_school_devices_the_school_triggers(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock)
    child = child_device(hass, entry)
    school = school_device(hass, entry)

    child_triggers = await ranzenpost_triggers(hass, child.id)
    school_triggers = await ranzenpost_triggers(hass, school.id)
    every_child_trigger = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, child.id)

    assert [item["type"] for item in child_triggers] == list(CHILD_TRIGGERS)
    assert [item["type"] for item in school_triggers] == list(SCHOOL_TRIGGERS)
    assert all(item["device_id"] == child.id and item["platform"] == "device" for item in child_triggers)
    assert {item["domain"] for item in every_child_trigger} == {DOMAIN, "binary_sensor"}


async def test_a_child_without_the_letters_module_has_no_new_letter_trigger(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0]["modules"]["letters"] = False
    info["schools"][0]["modules"]["pinboard"] = False
    entry = await setup_entry(hass, aioclient_mock, info=info)

    triggers = await ranzenpost_triggers(hass, child_device(hass, entry).id)

    assert [item["type"] for item in triggers] == [
        "timetable_changed",
        "lesson_cancelled",
        "substitution",
        "absence_status_changed",
    ]


async def test_a_school_trigger_on_a_child_device_is_refused(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    with pytest.raises(InvalidDeviceAutomationConfig):
        await async_validate_trigger_config(hass, trigger_of(child_device(hass, entry).id, "school_unreachable"))
    with pytest.raises(InvalidDeviceAutomationConfig):
        await async_validate_trigger_config(hass, trigger_of(school_device(hass, entry).id, "new_letter"))
    with pytest.raises(vol.Invalid):
        await async_validate_trigger_config(hass, trigger_of(child_device(hass, entry).id, "no_such_trigger"))
    assert await async_validate_trigger_config(hass, trigger_of(child_device(hass, entry).id, "new_letter"))


async def test_a_cancelled_lesson_fires_the_trigger_of_its_child_only(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    alex = child_device(hass, entry)
    kim = child_device(hass, entry, CHILD_2)
    calls = await automations_with(
        hass,
        (trigger_of(alex.id, "lesson_cancelled"), "{{ trigger.event.data.summary }}"),
        (trigger_of(kim.id, "lesson_cancelled"), "kim"),
    )

    await poll(hass, aioclient_mock, frozen_now, changes=[FRESH_CANCELLATION, *fixture("changes")])

    assert [call.data["value"] for call in calls] == ["Sport is cancelled"]


async def test_a_new_letter_fires_with_its_title_and_the_same_letter_never_fires_twice(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock)
    calls = await automations_with(
        hass, (trigger_of(child_device(hass, entry).id, "new_letter"), "{{ trigger.event.data.title }}")
    )
    grown = fixture("state_child_1")
    grown["unread_letters"]["count"] += 1
    grown["unread_letters"]["items"].append(
        {"title": "Trip money", "sender": "Mrs Example", "date": "2026-09-02", "child": "Alex"}
    )

    await poll(hass, aioclient_mock, frozen_now, states={CHILD_1: grown})
    await poll(hass, aioclient_mock, frozen_now, states={CHILD_1: grown})

    assert [call.data["value"] for call in calls] == ["Trip money"]


async def test_the_school_triggers_fire_on_status_transitions(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    school = school_device(hass, entry)
    events = async_capture_events(hass, "ranzenpost_event")
    calls = await automations_with(
        hass,
        (trigger_of(school.id, "school_unreachable"), "down"),
        (trigger_of(school.id, "school_reachable"), "up"),
        (trigger_of(school.id, "login_needed"), "login"),
    )

    offline = fixture("info")
    offline["schools"][0]["status"] = "unreachable"
    await poll(hass, aioclient_mock, frozen_now, info=offline)
    await poll(hass, aioclient_mock, frozen_now, info=offline)
    await poll(hass, aioclient_mock, frozen_now)
    failed = fixture("info")
    failed["schools"][0]["status"] = "auth_failed"
    await poll(hass, aioclient_mock, frozen_now, info=failed)

    assert [call.data["value"] for call in calls] == ["down", "up", "login"]
    assert [(event.data["type"], event.data["device_id"], event.data["status"]) for event in events] == [
        ("school_unreachable", school.id, "unreachable"),
        ("school_reachable", school.id, "ok"),
        ("login_needed", school.id, "auth_failed"),
    ]


async def test_a_restart_fires_nothing_for_changes_that_were_already_known(hass, aioclient_mock, frozen_now):
    mock_addon(aioclient_mock, changes=[FRESH_CANCELLATION, *fixture("changes")])
    events = async_capture_events(hass, "ranzenpost_event")
    await setup_entry(hass, aioclient_mock)

    await poll(hass, aioclient_mock, frozen_now, changes=[FRESH_CANCELLATION, *fixture("changes")])

    assert events == []


def test_every_trigger_and_condition_has_a_translated_name():
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))["device_automation"]
    assert set(strings["trigger_type"]) == set(CHILD_TRIGGERS) | set(SCHOOL_TRIGGERS)
    assert set(strings["condition_type"]) == {"is_school_day", "lesson_running"}
    assert all(value.strip() for value in strings["trigger_type"].values())
    assert all(value.strip() for value in strings["condition_type"].values())
