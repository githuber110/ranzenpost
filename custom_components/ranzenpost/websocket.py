from __future__ import annotations

from datetime import date, datetime
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import Child, Event, RanzenpostError
from .const import CALENDAR_MODULES, DOMAIN, KIND_OWN_ENTRIES, OWN_ENTRIES_MAX_DAYS, PURPOSE_CARD, WS_OWN_ENTRIES
from .coordinator import RanzenpostCoordinator, selected_children
from .devices import device_ref

ERROR_BAD_RANGE = "bad_range"
ERROR_UNAVAILABLE = "unavailable"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_own_entries)


@callback
def child_of_device(hass: HomeAssistant, device_id: str) -> tuple[RanzenpostCoordinator, Child] | None:
    device = dr.async_get(hass).async_get(device_id)
    ref = device_ref(device)
    if device is None or ref is None or not ref.is_child or ref.entry_id not in device.config_entries:
        return None
    entry = hass.config_entries.async_get_entry(ref.entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    coordinator = entry.runtime_data
    if coordinator is None or coordinator.data is None:
        return None
    child = next((child for child in selected_children(coordinator.data.info, entry) if child.key == ref.key), None)
    if child is None:
        return None
    return coordinator, child


def event_payload(event: Event) -> dict[str, Any]:
    return {
        "uid": event.uid,
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": {"dateTime": event.start.isoformat()},
        "end": {"dateTime": event.end.isoformat()},
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_OWN_ENTRIES,
        vol.Required("device_id"): str,
        vol.Required("start"): cv.date,
        vol.Required("end"): cv.date,
    }
)
@websocket_api.async_response
async def ws_own_entries(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    start: date = msg["start"]
    end: date = msg["end"]
    if end < start or (end - start).days > OWN_ENTRIES_MAX_DAYS:
        connection.send_error(
            msg["id"], ERROR_BAD_RANGE, f"the range must run forward and span at most {OWN_ENTRIES_MAX_DAYS} days"
        )
        return
    found = child_of_device(hass, msg["device_id"])
    if found is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "no Ranzenpost child with this device")
        return
    coordinator, child = found
    if not coordinator.data.info.modules_of(child).has(CALENDAR_MODULES[KIND_OWN_ENTRIES]):
        connection.send_result(msg["id"], [])
        return
    try:
        events = await coordinator.events.events(child.key, KIND_OWN_ENTRIES, start, end, purpose=PURPOSE_CARD)
    except RanzenpostError:
        connection.send_error(msg["id"], ERROR_UNAVAILABLE, "the add-on could not be read")
        return
    own = [event for event in events if event.kind == KIND_OWN_ENTRIES and isinstance(event.start, datetime)]
    connection.send_result(msg["id"], [event_payload(event) for event in own])
