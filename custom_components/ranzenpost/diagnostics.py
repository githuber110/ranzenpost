from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import RanzenpostConfigEntry

REDACTED_KEYS = {CONF_TOKEN}
REDACTED_TEXT_KEYS = {
    "name",
    "url_host",
    "class_name",
    "title",
    "sender",
    "child",
    "details",
    "summary",
    "description",
    "location",
    "subject",
    "first_lesson",
    "teacher",
    "room",
    "note",
    "before",
    "after",
}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def _redacted(value: Any) -> Any:
    return async_redact_data(_plain(value), REDACTED_TEXT_KEYS)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), REDACTED_KEYS),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "info": _info_of(data.info) if data else None,
        "schools": {school.id: _school_of(data, school) for school in data.info.schools} if data else {},
        "states": {child_key: _redacted(asdict(state)) for child_key, state in data.states.items()} if data else {},
        "changes": [_redacted(asdict(change)) for change in data.changes] if data else [],
    }


def _info_of(info) -> dict[str, Any]:
    plain = asdict(info)
    plain["schools"] = [
        dict(asdict(school), modules=school.modules.as_dict(), children=[asdict(child) for child in school.children])
        for school in info.schools
    ]
    return _redacted(plain)


def _school_of(data, school) -> dict[str, Any]:
    return {
        "status": school.status,
        "modules": school.modules.as_dict(),
        "children": [child.key for child in school.children],
        "school": _redacted(asdict(data.school(school.id))),
    }
