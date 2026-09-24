from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import CONF_RESOURCE_TYPE_WS, LOVELACE_DATA, MODE_STORAGE
from homeassistant.const import CONF_ID, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "frontend" / "ranzenpost-card.js"
CARD_URL_PATH = f"/{DOMAIN}/ranzenpost-card.js"
RESOURCE_TYPE = "module"
DATA_CARD_REGISTERED = f"{DOMAIN}_card_registered"
DATA_CARD_SERVED = f"{DOMAIN}_card_served"


def card_resource_url(version: str) -> str:
    return f"{CARD_URL_PATH}?v={version}"


async def async_register_card(hass: HomeAssistant) -> None:
    if hass.data.get(DATA_CARD_REGISTERED):
        return
    try:
        await _register_card(hass)
    except Exception:
        _LOGGER.warning("the Ranzenpost card could not be registered, the next setup tries again", exc_info=True)
        return
    hass.data[DATA_CARD_REGISTERED] = True


async def _register_card(hass: HomeAssistant) -> None:
    if not hass.data.get(DATA_CARD_SERVED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, str(CARD_FILE), cache_headers=False)]
        )
        hass.data[DATA_CARD_SERVED] = True
    integration = await async_get_integration(hass, DOMAIN)
    url = card_resource_url(str(integration.version))
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        _LOGGER.debug("lovelace is not loaded, the card resource %s was not registered", url)
        return
    resources = _storage_resources(hass)
    if resources is None:
        _LOGGER.warning(
            "Lovelace manages its resources in YAML; add the Ranzenpost card yourself: url: %s, type: %s",
            url,
            RESOURCE_TYPE,
        )
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    ours = [item for item in resources.async_items() if str(item.get(CONF_URL, "")).split("?")[0] == CARD_URL_PATH]
    if any(item[CONF_URL] == url for item in ours):
        return
    if ours:
        await resources.async_update_item(ours[0][CONF_ID], {CONF_URL: url})
        _LOGGER.info("the Ranzenpost card resource now points at %s", url)
        return
    await resources.async_create_item({CONF_RESOURCE_TYPE_WS: RESOURCE_TYPE, CONF_URL: url})
    _LOGGER.info("the Ranzenpost card resource %s was added to the dashboard resources", url)


def _storage_resources(hass: HomeAssistant):
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        return None
    mode = getattr(lovelace, "resource_mode", None) or getattr(lovelace, "mode", None)
    if mode != MODE_STORAGE:
        return None
    return lovelace.resources


async def async_remove_card(hass: HomeAssistant) -> None:
    hass.data.pop(DATA_CARD_REGISTERED, None)
    resources = _storage_resources(hass)
    if resources is None:
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    ours = [item for item in resources.async_items() if str(item.get(CONF_URL, "")).split("?")[0] == CARD_URL_PATH]
    for item in ours:
        await resources.async_delete_item(item[CONF_ID])
        _LOGGER.info("the Ranzenpost card resource %s was removed from the dashboard resources", item[CONF_URL])
