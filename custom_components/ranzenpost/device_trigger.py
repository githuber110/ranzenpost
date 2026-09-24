from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA, InvalidDeviceAutomationConfig
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_EVENT, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_TYPE, CHILD_TRIGGERS, DOMAIN, EVENT_RANZENPOST, SCHOOL_TRIGGERS, TRIGGER_MODULES
from .devices import DeviceRef, device_ref_of_id, modules_of_device
from .signals import ATTR_DEVICE_ID

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(CHILD_TRIGGERS + SCHOOL_TRIGGERS)}
)
PLATFORM_DEVICE = "device"


def trigger_types_of(hass: HomeAssistant, ref: DeviceRef) -> tuple[str, ...]:
    if not ref.is_child:
        return SCHOOL_TRIGGERS
    modules = modules_of_device(hass, ref)
    return tuple(kind for kind in CHILD_TRIGGERS if modules.has(TRIGGER_MODULES[kind]))


async def async_validate_trigger_config(hass: HomeAssistant, config: ConfigType) -> ConfigType:
    config = TRIGGER_SCHEMA(config)
    ref = device_ref_of_id(hass, config[CONF_DEVICE_ID])
    if ref is None:
        return config
    allowed = CHILD_TRIGGERS if ref.is_child else SCHOOL_TRIGGERS
    if config[CONF_TYPE] not in allowed:
        raise InvalidDeviceAutomationConfig(f"{config[CONF_TYPE]} is not a trigger of a {ref.kind} device")
    return config


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    ref = device_ref_of_id(hass, device_id)
    if ref is None:
        return []
    return [
        {CONF_PLATFORM: PLATFORM_DEVICE, CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: kind}
        for kind in trigger_types_of(hass, ref)
    ]


async def async_attach_trigger(
    hass: HomeAssistant, config: ConfigType, action: TriggerActionType, trigger_info: TriggerInfo
) -> CALLBACK_TYPE:
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: CONF_EVENT,
            event_trigger.CONF_EVENT_TYPE: EVENT_RANZENPOST,
            event_trigger.CONF_EVENT_DATA: {ATTR_DEVICE_ID: config[CONF_DEVICE_ID], ATTR_TYPE: config[CONF_TYPE]},
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type=PLATFORM_DEVICE
    )
