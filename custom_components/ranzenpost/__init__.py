from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.loader import async_get_integration

from .api import Info, school_of_key
from .card import async_register_card, async_remove_card
from .const import (
    BRAND,
    CONF_CHILDREN,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    ENTRY_VERSION,
    KEY_MODULES,
    LEGACY_UNIQUE_ID,
    OPT_IN_CALENDAR_KINDS,
    unique_id_of,
)
from .coordinator import (
    ENTRY_ISSUE_KEYS,
    RanzenpostConfigEntry,
    RanzenpostCoordinator,
    child_option_keys,
    entry_issue_id,
    login_issue_id,
)
from .entity import child_identifier, child_unique_id, panel_url, school_device_info, school_identifier, school_unique_id
from .signals import async_fire_signals
from .websocket import async_register_websocket

PLATFORMS = (Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.EVENT, Platform.SENSOR)
LEGACY_SCHOOL_PREFIX = "school:"
LEGACY_CHILD_PREFIX = "child:"
LEGACY_SCHOOL_UNIQUE_PREFIX = f"{DOMAIN}_school_"
KNOWN_SCHOOLS_KEY = "known_schools"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _known_schools(hass: HomeAssistant) -> dict[str, tuple[str, ...]]:
    return hass.data.setdefault(DOMAIN, {}).setdefault(KNOWN_SCHOOLS_KEY, {})


@callback
def _remember_schools(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    _known_schools(hass)[entry.entry_id] = tuple(school.id for school in info.schools)


def _school_of_unique_id(entry_id: str, unique_id: str) -> str:
    prefix = f"{DOMAIN}_{entry_id}_"
    if not unique_id.startswith(prefix):
        return ""
    rest = unique_id[len(prefix):]
    if rest.startswith("school_"):
        return rest[len("school_"):].split("_", 1)[0]
    return school_of_key(rest)


@callback
def forget_entities_of_missing_modules(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        school = info.school(_school_of_unique_id(entry.entry_id, entity.unique_id))
        if school is None:
            continue
        stale = tuple(f"_{key}" for key, module in KEY_MODULES.items() if not school.modules.has(module))
        if not school.own_entries:
            stale += tuple(f"_{key}" for key in OPT_IN_CALENDAR_KINDS)
        if stale and entity.unique_id.endswith(stale):
            registry.async_remove(entity.entity_id)


@callback
def migrate_legacy_devices(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    if not info.schools:
        return
    registry = dr.async_get(hass)
    first = info.schools[0]
    for legacy_id in (f"{LEGACY_SCHOOL_PREFIX}{entry.entry_id}", f"{LEGACY_SCHOOL_PREFIX}{first.url_host}"):
        legacy = registry.async_get_device(identifiers={(DOMAIN, legacy_id)})
        if legacy is None or entry.entry_id not in legacy.config_entries:
            continue
        if registry.async_get_device(identifiers={school_identifier(entry.entry_id, first.id)}) is None:
            registry.async_update_device(legacy.id, new_identifiers={school_identifier(entry.entry_id, first.id)})
    if len(info.schools) != 1:
        return
    for child in first.children:
        legacy = registry.async_get_device(identifiers={(DOMAIN, f"{LEGACY_CHILD_PREFIX}{child.raw_id}")})
        if legacy is None or entry.entry_id not in legacy.config_entries:
            continue
        if registry.async_get_device(identifiers={child_identifier(entry.entry_id, child)}) is None:
            registry.async_update_device(legacy.id, new_identifiers={child_identifier(entry.entry_id, child)})


@callback
def migrate_legacy_unique_ids(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    if len(info.schools) != 1:
        return
    school = info.schools[0]
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = entity.unique_id
        if unique_id.startswith(f"{DOMAIN}_{entry.entry_id}_"):
            continue
        wanted = ""
        if unique_id.startswith(LEGACY_SCHOOL_UNIQUE_PREFIX):
            wanted = school_unique_id(entry.entry_id, school.id, unique_id[len(LEGACY_SCHOOL_UNIQUE_PREFIX):])
        else:
            for child in school.children:
                prefix = f"{DOMAIN}_{child.raw_id}_"
                if unique_id.startswith(prefix):
                    wanted = child_unique_id(entry.entry_id, child, unique_id[len(prefix):])
                    break
        if wanted and registry.async_get_entity_id(entity.domain, DOMAIN, wanted) is None:
            registry.async_update_entity(entity.entity_id, new_unique_id=wanted)


@callback
def sync_device_names_and_links(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    registry = dr.async_get(hass)
    link = panel_url(info.ingress_path)
    for school in info.schools:
        device = registry.async_get_device(identifiers={school_identifier(entry.entry_id, school.id)})
        if device is None:
            continue
        wanted = f"{BRAND} {school.label}".strip()
        changes = {}
        if device.name_by_user is None and device.name != wanted:
            changes["name"] = wanted
        if device.configuration_url != link:
            changes["configuration_url"] = link
        if changes:
            registry.async_update_device(device.id, **changes)
    for child in info.children:
        device = registry.async_get_device(identifiers={child_identifier(entry.entry_id, child)})
        if device is not None and device.configuration_url != link:
            registry.async_update_device(device.id, configuration_url=link)


@callback
def rewrite_child_options(hass: HomeAssistant, entry: RanzenpostConfigEntry, info: Info) -> None:
    chosen = [str(item) for item in entry.options.get(CONF_CHILDREN) or []]
    keys = child_option_keys(info, chosen)
    if keys != chosen:
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_CHILDREN: keys})


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_register_websocket(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> bool:
    if entry.version > ENTRY_VERSION:
        return False
    wanted = unique_id_of(entry.data.get(CONF_HOST, ""), entry.data.get(CONF_PORT, 0))
    unique_id = entry.unique_id
    if unique_id in (None, LEGACY_UNIQUE_ID):
        taken = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, wanted)
        if taken is None or taken.entry_id == entry.entry_id:
            unique_id = wanted
    hass.config_entries.async_update_entry(entry, unique_id=unique_id, version=ENTRY_VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> bool:
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = RanzenpostCoordinator(hass, entry, integration_version=str(integration.version or ""))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    info = coordinator.data.info
    rewrite_child_options(hass, entry, info)
    migrate_legacy_devices(hass, entry, info)
    migrate_legacy_unique_ids(hass, entry, info)
    registry = dr.async_get(hass)
    for school in info.schools:
        registry.async_get_or_create(
            config_entry_id=entry.entry_id, **school_device_info(entry.entry_id, school, info)
        )
    forget_entities_of_missing_modules(hass, entry, info)
    _remember_schools(hass, entry, info)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_card(hass)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    announced = coordinator.data

    @callback
    def _on_coordinator_update() -> None:
        nonlocal announced
        data = coordinator.data
        sync_device_names_and_links(hass, entry, data.info)
        _remember_schools(hass, entry, data.info)
        if data is not announced:
            announced = data
            async_fire_signals(hass, entry.entry_id, data.signals)

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: RanzenpostConfigEntry, device: dr.DeviceEntry
) -> bool:
    info = entry.runtime_data.data.info
    current = {school_identifier(entry.entry_id, school.id) for school in info.schools}
    current.update(child_identifier(entry.entry_id, child) for child in info.children)
    return not (device.identifiers & current)


async def async_remove_entry(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> None:
    await async_remove_card(hass)
    for school_id in _known_schools(hass).pop(entry.entry_id, ()):
        ir.async_delete_issue(hass, DOMAIN, login_issue_id(entry.entry_id, school_id))
    for key in ENTRY_ISSUE_KEYS:
        ir.async_delete_issue(hass, DOMAIN, entry_issue_id(key, entry.entry_id))


async def _async_options_updated(hass: HomeAssistant, entry: RanzenpostConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
