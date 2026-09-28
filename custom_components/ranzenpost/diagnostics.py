from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CHILDREN, CONF_TOKEN
from .coordinator import RanzenpostConfigEntry

REDACTED_KEYS = {CONF_TOKEN}
CHILD_ALIAS_PREFIX = "child-"
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


def _child_aliases(data) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for index, child in enumerate(data.info.children if data else (), start=1):
        aliases.setdefault(child.key, f"{CHILD_ALIAS_PREFIX}{index}")
        aliases.setdefault(child.raw_id, aliases[child.key])
    return aliases


def _alias(aliases: dict[str, str], key: Any) -> str:
    text = str(key)
    if text not in aliases:
        aliases[text] = f"{CHILD_ALIAS_PREFIX}{len(set(aliases.values())) + 1}"
    return aliases[text]


def _options_of(options, aliases: dict[str, str]) -> dict[str, Any]:
    plain = dict(options)
    chosen = plain.get(CONF_CHILDREN)
    if isinstance(chosen, (list, tuple)):
        plain[CONF_CHILDREN] = [_alias(aliases, item) for item in chosen]
    return plain


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    aliases = _child_aliases(data)
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), REDACTED_KEYS),
            "options": _options_of(entry.options, aliases),
        },
        "last_update_success": coordinator.last_update_success,
        "info": _info_of(data.info, aliases) if data else None,
        "schools": {school.id: _school_of(data, school, aliases) for school in data.info.schools} if data else {},
        "states": {_alias(aliases, key): _redacted(asdict(state)) for key, state in data.states.items()} if data else {},
        "changes": [_change_of(change, aliases) for change in data.changes] if data else [],
    }


def _change_of(change, aliases: dict[str, str]) -> dict[str, Any]:
    return _redacted(dict(asdict(change), child_key=_alias(aliases, change.child_key)))


def _info_of(info, aliases: dict[str, str]) -> dict[str, Any]:
    plain = asdict(info)
    plain["schools"] = [
        dict(
            asdict(school),
            modules=school.modules.as_dict(),
            children=[dict(asdict(child), key=_alias(aliases, child.key)) for child in school.children],
        )
        for school in info.schools
    ]
    return _redacted(plain)


def _school_of(data, school, aliases: dict[str, str]) -> dict[str, Any]:
    return {
        "status": school.status,
        "modules": school.modules.as_dict(),
        "children": [_alias(aliases, child.key) for child in school.children],
        "school": _redacted(asdict(data.school(school.id))),
    }
