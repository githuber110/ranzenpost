from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohasupervisor import SupervisorError
from aiohasupervisor.models import AddonState as SupervisorAddonState
from aiohasupervisor.models import StoreAddRepository
from homeassistant.components.hassio import get_supervisor_client
from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.hassio import is_hassio
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import AuthError, Child, ConnectionError, Info, RanzenpostApi
from .const import (
    ADDON_REPOSITORY,
    ADDON_SLUG,
    BRAND,
    CONF_CHILDREN,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DISCOVERY_POLL_SECONDS,
    DISCOVERY_SERVICE,
    DISCOVERY_WAIT_SECONDS,
    DOMAIN,
    ENTRY_VERSION,
    LEGACY_UNIQUE_ID,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    unique_id_of,
)
from .coordinator import api_for_entry

_LOGGER = logging.getLogger(__name__)

STEP_HASSIO_CONFIRM = "hassio_confirm"
STEP_INSTALL_ADDON = "install_addon"
STEP_START_ADDON = "start_addon"
STEP_WAIT_DISCOVERY = "wait_discovery"
STEP_ADDON_NO_DISCOVERY = "addon_no_discovery"
STEP_MANUAL = "manual"
STEP_REAUTH_CONFIRM = "reauth_confirm"
STEP_FINISH_ADDON = "finish_addon"
STEP_INSTALL_FAILED = "install_failed"
STEP_START_FAILED = "start_failed"
ABORT_INSTALL_FAILED = "addon_install_failed"
ABORT_START_FAILED = "addon_start_failed"
ABORT_WRONG_ADDON = "not_ranzenpost_addon"
ABORT_ALREADY_CONFIGURED = "already_configured"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"
PLACEHOLDER_ADDON = "addon"
PLACEHOLDER_REPOSITORY = "repository"


class AddonNotFound(Exception):
    pass


class DiscoveryTimeout(Exception):
    pass


def manual_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
        }
    )


def token_schema() -> vol.Schema:
    return vol.Schema({vol.Required(CONF_TOKEN): str})


def child_option_label(info: Info | None, child: Child) -> str:
    school = info.school_of(child) if info else None
    if info is not None and info.many_schools and school is not None:
        return f"{child.first_name} ({school.label})"
    return f"{child.name} ({child.class_name})" if child.class_name else child.name


def options_schema(options: Mapping[str, Any], info: Info | None) -> vol.Schema:
    children = info.children if info else ()
    choices = [SelectOptionDict(value=child.key, label=child_option_label(info, child)) for child in children]
    known = {child.key for child in children}
    chosen = [child_key for child_key in options.get(CONF_CHILDREN) or [] if child_key in known]
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Coerce(int),
                vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
            ),
            vol.Optional(CONF_CHILDREN, default=chosen): SelectSelector(
                SelectSelectorConfig(options=choices, multiple=True, mode=SelectSelectorMode.LIST)
            ),
        }
    )


def is_ranzenpost_addon(slug: str) -> bool:
    return slug == ADDON_SLUG or slug.endswith(f"_{ADDON_SLUG}")


async def validate_connection(hass: HomeAssistant, data: Mapping[str, Any]) -> Info:
    api = RanzenpostApi(async_get_clientsession(hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN])
    return await api.info()


def _entry_data(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        CONF_HOST: str(config[CONF_HOST]),
        CONF_PORT: int(config[CONF_PORT]),
        CONF_TOKEN: str(config[CONF_TOKEN]),
    }


class RanzenpostConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = ENTRY_VERSION

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._addon_slug: str | None = None
        self._addon_name: str = BRAND
        self._addon_host: str = ""
        self._install_task: asyncio.Task | None = None
        self._start_task: asyncio.Task | None = None
        self._discovery_task: asyncio.Task | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RanzenpostOptionsFlow:
        return RanzenpostOptionsFlow()

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        if not is_ranzenpost_addon(discovery_info.slug):
            return self.async_abort(reason=ABORT_WRONG_ADDON)
        self._data = _entry_data(discovery_info.config)
        self._addon_name = discovery_info.name or BRAND
        await self.async_set_unique_id(unique_id_of(self._data[CONF_HOST], self._data[CONF_PORT]))
        self._adopt_legacy_entry()
        failed = self._entry_failed_with_another_token()
        if failed is not None:
            return self.async_update_reload_and_abort(failed, data_updates=self._data, reason=ABORT_ALREADY_CONFIGURED)
        self._abort_if_unique_id_configured(updates=self._data)
        return await self.async_step_hassio_confirm()

    def _entry_failed_with_another_token(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, self.unique_id)
        if entry is None or entry.state is not ConfigEntryState.SETUP_ERROR:
            return None
        if entry.data.get(CONF_TOKEN) == self._data[CONF_TOKEN]:
            return None
        return entry

    def _adopt_legacy_entry(self) -> None:
        legacy = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, LEGACY_UNIQUE_ID)
        if legacy is None:
            return
        same_host = unique_id_of(legacy.data.get(CONF_HOST, ""), legacy.data.get(CONF_PORT, 0)) == self.unique_id
        alone = len(self.hass.config_entries.async_entries(DOMAIN)) == 1
        if not (same_host or alone):
            return
        self.hass.config_entries.async_update_entry(legacy, unique_id=self.unique_id)
        _LOGGER.info("the Ranzenpost entry of the previous release now belongs to %s", self.unique_id)

    async def _claim(self, data: Mapping[str, Any]) -> None:
        await self.async_set_unique_id(unique_id_of(data[CONF_HOST], data[CONF_PORT]))
        self._adopt_legacy_entry()
        self._abort_if_unique_id_configured()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._try_connection(self._data)
            if not errors:
                return self._create_entry()
        return self.async_show_form(
            step_id=STEP_HASSIO_CONFIRM,
            errors=errors,
            description_placeholders={PLACEHOLDER_ADDON: self._addon_name},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not is_hassio(self.hass):
            return await self.async_step_manual()
        return await self.async_step_on_supervisor()

    async def async_step_on_supervisor(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        client = get_supervisor_client(self.hass)
        try:
            message = await self._discovery_message(client)
            if message is not None:
                self._data = _entry_data(message.config)
                await self._claim(self._data)
                await self._remember_addon(client, message.addon)
                return await self.async_step_hassio_confirm()
            addon = await self._find_store_addon(client)
            if addon is None or not addon.installed:
                return await self.async_step_install_addon()
            running = await self._remember_addon(client, addon.slug)
        except SupervisorError as err:
            _LOGGER.warning("the supervisor could not be asked about the add-on: %s", err)
            return await self.async_step_manual()
        if not running:
            return await self.async_step_start_addon()
        return await self.async_step_wait_discovery()

    async def async_step_install_addon(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._install_task and user_input is None:
            return self.async_show_form(
                step_id=STEP_INSTALL_ADDON,
                description_placeholders={PLACEHOLDER_REPOSITORY: ADDON_REPOSITORY},
            )
        if not self._install_task:
            self._install_task = self.hass.async_create_task(self._async_install_addon())
        if not self._install_task.done():
            return self.async_show_progress(
                step_id=STEP_INSTALL_ADDON,
                progress_action=STEP_INSTALL_ADDON,
                progress_task=self._install_task,
                description_placeholders={PLACEHOLDER_REPOSITORY: ADDON_REPOSITORY},
            )
        try:
            await self._install_task
        except (SupervisorError, AddonNotFound) as err:
            _LOGGER.error("the add-on could not be installed: %s", err)
            return self.async_show_progress_done(next_step_id=STEP_INSTALL_FAILED)
        finally:
            self._install_task = None
        return self.async_show_progress_done(next_step_id=STEP_START_ADDON)

    async def async_step_install_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason=ABORT_INSTALL_FAILED)

    async def async_step_start_addon(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._start_task:
            self._start_task = self.hass.async_create_task(self._async_start_addon())
        if not self._start_task.done():
            return self.async_show_progress(
                step_id=STEP_START_ADDON,
                progress_action=STEP_START_ADDON,
                progress_task=self._start_task,
            )
        try:
            await self._start_task
        except SupervisorError as err:
            _LOGGER.error("the add-on could not be started: %s", err)
            return self.async_show_progress_done(next_step_id=STEP_START_FAILED)
        finally:
            self._start_task = None
        return self.async_show_progress_done(next_step_id=STEP_WAIT_DISCOVERY)

    async def async_step_start_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason=ABORT_START_FAILED)

    async def async_step_wait_discovery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._discovery_task:
            self._discovery_task = self.hass.async_create_task(self._async_wait_for_discovery())
        if not self._discovery_task.done():
            return self.async_show_progress(
                step_id=STEP_WAIT_DISCOVERY,
                progress_action=STEP_WAIT_DISCOVERY,
                progress_task=self._discovery_task,
            )
        try:
            config = await self._discovery_task
        except (SupervisorError, DiscoveryTimeout) as err:
            _LOGGER.warning("the add-on did not announce itself: %s", err)
            return self.async_show_progress_done(next_step_id=STEP_ADDON_NO_DISCOVERY)
        finally:
            self._discovery_task = None
        self._data = _entry_data(config)
        return self.async_show_progress_done(next_step_id=STEP_FINISH_ADDON)

    async def async_step_finish_addon(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self._claim(self._data)
        return await self.async_step_hassio_confirm()

    async def async_step_addon_no_discovery(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self._claim(_entry_data(user_input))
            errors = await self._try_connection(user_input)
            if not errors:
                self._data = _entry_data(user_input)
                return self._create_entry()
        defaults = dict(user_input or {})
        if not defaults.get(CONF_HOST) and self._addon_host:
            defaults[CONF_HOST] = self._addon_host
        return self.async_show_form(
            step_id=STEP_ADDON_NO_DISCOVERY,
            data_schema=manual_schema(defaults),
            errors=errors,
            description_placeholders={PLACEHOLDER_ADDON: self._addon_name},
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self._claim(_entry_data(user_input))
            errors = await self._try_connection(user_input)
            if not errors:
                self._data = _entry_data(user_input)
                return self._create_entry()
        return self.async_show_form(
            step_id=STEP_MANUAL, data_schema=manual_schema(user_input or {}), errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            candidate = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            errors = await self._try_connection(candidate)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]})
        return self.async_show_form(
            step_id=STEP_REAUTH_CONFIRM,
            data_schema=token_schema(),
            errors=errors,
            description_placeholders={CONF_HOST: entry.data[CONF_HOST]},
        )

    def _create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(title=f"{BRAND} ({self._data[CONF_HOST]})", data=self._data)

    async def _try_connection(self, data: Mapping[str, Any]) -> dict[str, str]:
        try:
            await validate_connection(self.hass, data)
        except AuthError:
            return {"base": ERROR_INVALID_AUTH}
        except ConnectionError:
            return {"base": ERROR_CANNOT_CONNECT}
        except Exception:
            _LOGGER.exception("the add-on answered in an unexpected way")
            return {"base": ERROR_UNKNOWN}
        return {}

    async def _discovery_message(self, client):
        for message in await client.discovery.list():
            if message.service == DISCOVERY_SERVICE and is_ranzenpost_addon(message.addon):
                return message
        return None

    async def _find_store_addon(self, client):
        for addon in await client.store.addons_list():
            if is_ranzenpost_addon(addon.slug) and addon.url and ADDON_REPOSITORY.lower() in addon.url.lower():
                return addon
        for addon in await client.store.addons_list():
            if is_ranzenpost_addon(addon.slug):
                return addon
        return None

    async def _async_install_addon(self) -> None:
        client = get_supervisor_client(self.hass)
        repositories = await client.store.repositories_list()
        if not any(ADDON_REPOSITORY.lower() == (repo.source or "").lower() for repo in repositories):
            await client.store.add_repository(StoreAddRepository(repository=ADDON_REPOSITORY))
        await client.store.reload()
        addon = await self._find_store_addon(client)
        if addon is None:
            raise AddonNotFound(ADDON_REPOSITORY)
        if not addon.installed:
            await client.store.install_addon(addon.slug)
        await self._remember_addon(client, addon.slug)

    async def _remember_addon(self, client, slug: str) -> bool:
        info = await client.addons.addon_info(slug)
        self._addon_slug = slug
        self._addon_name = info.name or BRAND
        self._addon_host = info.hostname or ""
        return info.state == SupervisorAddonState.STARTED

    async def _async_start_addon(self) -> None:
        client = get_supervisor_client(self.hass)
        await client.addons.start_addon(self._addon_slug)

    async def _async_wait_for_discovery(self) -> Mapping[str, Any]:
        client = get_supervisor_client(self.hass)
        waited = 0
        while True:
            message = await self._discovery_message(client)
            if message is not None:
                return message.config
            if waited >= DISCOVERY_WAIT_SECONDS:
                raise DiscoveryTimeout(f"no discovery within {DISCOVERY_WAIT_SECONDS} seconds")
            await asyncio.sleep(DISCOVERY_POLL_SECONDS)
            waited += DISCOVERY_POLL_SECONDS


class RanzenpostOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema(self.config_entry.options, await self._info()),
        )

    async def _info(self) -> Info | None:
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is not None and coordinator.data is not None:
            return coordinator.data.info
        try:
            return await api_for_entry(self.hass, self.config_entry).info()
        except Exception:
            return None
