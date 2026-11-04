from __future__ import annotations

import re

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import ADDON_REPOSITORY, BRAND, DOMAIN

HACS_DOMAIN = "hacs"
UPDATE_DOMAIN = "update"
REPOSITORY_URL = re.compile(rf"^{re.escape(ADDON_REPOSITORY.lower())}(/|$)")
HACS_NAMES = {BRAND.lower(), f"{BRAND.lower()} update"}
HACS_PICTURE = f"/_/{DOMAIN}/"
NOT_LOADED = (None, STATE_UNAVAILABLE, STATE_UNKNOWN)


def hacs_match(state: State | None) -> int:
    if state is None:
        return 0
    attributes = state.attributes
    if REPOSITORY_URL.match(str(attributes.get("release_url") or "").lower()):
        return 2
    names = {str(attributes.get(key) or "").strip().lower() for key in ("title", "friendly_name")}
    if names & HACS_NAMES or HACS_PICTURE in str(attributes.get("entity_picture") or "").lower():
        return 1
    return 0


def _hacs_update_entries(hass: HomeAssistant) -> list[er.RegistryEntry]:
    return [
        entry
        for entry in er.async_get(hass).entities.values()
        if entry.platform == HACS_DOMAIN and entry.domain == UPDATE_DOMAIN
    ]


def hacs_update_entity(hass: HomeAssistant) -> str | None:
    scored = [(hacs_match(hass.states.get(entry.entity_id)), entry.entity_id) for entry in _hacs_update_entries(hass)]
    best = max((score for score, _ in scored), default=0)
    found = [entity_id for score, entity_id in scored if score == best]
    return found[0] if best and len(found) == 1 else None


def _state_value(hass: HomeAssistant, entity_id: str) -> str | None:
    state = hass.states.get(entity_id)
    return state.state if state is not None else None


def waiting_for_hacs(hass: HomeAssistant) -> bool:
    enabled = [entry.entity_id for entry in _hacs_update_entries(hass) if not entry.disabled]
    if enabled and all(_state_value(hass, entity_id) in NOT_LOADED for entity_id in enabled):
        return True
    entity_id = hacs_update_entity(hass)
    return entity_id is not None and _state_value(hass, entity_id) != STATE_ON
