from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.const import CONF_CONDITION, CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.condition import ConditionCheckerType
from homeassistant.helpers.typing import ConfigType, TemplateVarsType
from homeassistant.util import dt as dt_util

from .api import Lesson, State
from .const import CHILD_CONDITIONS, CONDITION_SCHOOL_DAY, DOMAIN, MODULE_TIMETABLE
from .devices import DeviceRef, data_of_device, device_ref_of_id, modules_of_device

CONDITION_SCHEMA = cv.DEVICE_CONDITION_BASE_SCHEMA.extend({vol.Required(CONF_TYPE): vol.In(CHILD_CONDITIONS)})
CONDITION_DEVICE = "device"


def child_state_of(hass: HomeAssistant, ref: DeviceRef | None) -> State | None:
    if ref is None or not ref.is_child:
        return None
    data = data_of_device(hass, ref)
    return data.states.get(ref.key) if data else None


def lesson_covers(lesson: Lesson | None, now) -> bool:
    return bool(lesson and lesson.start and lesson.end and lesson.start <= now < lesson.end)


def lesson_running(state: State) -> bool:
    now = dt_util.now()
    return lesson_covers(state.now_lesson, now) or lesson_covers(state.next_lesson, now)


async def async_validate_condition_config(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    config = CONDITION_SCHEMA(config)
    ref = device_ref_of_id(hass, config[CONF_DEVICE_ID])
    if ref is not None and not ref.is_child:
        raise InvalidDeviceAutomationConfig(f"{config[CONF_TYPE]} is not a condition of a {ref.kind} device")
    return config


async def async_get_conditions(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    ref = device_ref_of_id(hass, device_id)
    if ref is None or not ref.is_child or not modules_of_device(hass, ref).has(MODULE_TIMETABLE):
        return []
    return [
        {CONF_CONDITION: CONDITION_DEVICE, CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: kind}
        for kind in CHILD_CONDITIONS
    ]


@callback
def async_condition_from_config(hass: HomeAssistant, config: ConfigType) -> ConditionCheckerType:
    device_id = config[CONF_DEVICE_ID]
    kind = config[CONF_TYPE]

    @callback
    def test_condition(hass: HomeAssistant, variables: TemplateVarsType) -> bool:
        state = child_state_of(hass, device_ref_of_id(hass, device_id))
        if state is None:
            return False
        if kind == CONDITION_SCHOOL_DAY:
            return state.school_day_today
        return lesson_running(state)

    return test_condition
