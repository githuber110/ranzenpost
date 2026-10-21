from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import voluptuous as vol
from aiohasupervisor import SupervisorError
from homeassistant import data_entry_flow
from homeassistant.components.hassio import get_supervisor_client
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.hassio import is_hassio

from .addon import entry_addon
from .const import ADDON_REPOSITORY, BRAND, CONF_HOST, DOMAIN, ISSUE_ENTRY
from .version import ADDON_TOO_OLD, APP_UPDATE_NEEDED, INTEGRATION_TOO_OLD, RESTART_REQUIRED

_LOGGER = logging.getLogger(__name__)

HOMEASSISTANT_DOMAIN = "homeassistant"
RESTART_SERVICE = "restart"
HACS_DOMAIN = "hacs"
UPDATE_DOMAIN = "update"
INSTALL_SERVICE = "install"
STEP_CONFIRM = "confirm"
STEP_UPDATE_APP = "update_app"
STEP_INSTALL_INTEGRATION = "install_integration"
STEP_UPDATED = "updated"
STEP_NO_NEWER_VERSION = "no_newer_version"
STEP_UPDATE_FAILED = "update_failed"
ABORT_NO_SUPERVISOR = "no_supervisor"
ABORT_NO_ADDON = "no_addon"
ABORT_NO_HACS = "no_hacs"
ABORT_NO_NEWER_VERSION = "no_newer_version"
ABORT_UPDATE_FAILED = "update_failed"
REPOSITORY_URL = re.compile(rf"^{re.escape(ADDON_REPOSITORY.lower())}(/|$)")
HACS_NAMES = {BRAND.lower(), f"{BRAND.lower()} update"}
HACS_PICTURE = f"/_/{DOMAIN}/"
RUNNING_UPDATES = f"{DOMAIN}_running_updates"


class NoNewerVersion(Exception):
    pass


class RestartRepairFlow(ConfirmRepairFlow):
    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is None:
            return await super().async_step_confirm()
        await self.hass.services.async_call(HOMEASSISTANT_DOMAIN, RESTART_SERVICE, blocking=False)
        return self.async_create_entry(data={})


async def _shielded(task: asyncio.Task) -> None:
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        return


class UpdateRepairFlow(RepairsFlow):
    progress_step = ""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._waiter: asyncio.Task | None = None

    def _placeholders(self) -> dict[str, str]:
        issue = ir.async_get(self.hass).async_get_issue(DOMAIN, self.issue_id)
        return dict(issue.translation_placeholders or {}) if issue is not None else {}

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id=STEP_CONFIRM, data_schema=vol.Schema({}), description_placeholders=self._placeholders()
            )
        return await self._progress()

    def _running_update(self) -> asyncio.Task:
        running = self.hass.data.setdefault(RUNNING_UPDATES, {})
        task = running.get(self.issue_id)
        if task is None or task.done():
            task = self.hass.async_create_background_task(self._async_update(), f"{DOMAIN} {self.issue_id}")
            running[self.issue_id] = task
        return task

    async def _progress(self) -> data_entry_flow.FlowResult:
        if not self._task:
            self._task = self._running_update()
            self._waiter = self.hass.async_create_task(_shielded(self._task))
        if not self._task.done():
            return self.async_show_progress(
                step_id=self.progress_step, progress_action=self.progress_step, progress_task=self._waiter
            )
        try:
            self._task.result()
        except NoNewerVersion as err:
            _LOGGER.warning("no newer Ranzenpost version is offered yet: %s", err)
            return self.async_show_progress_done(next_step_id=STEP_NO_NEWER_VERSION)
        except (SupervisorError, HomeAssistantError) as err:
            _LOGGER.error("the Ranzenpost update failed: %s", err)
            return self.async_show_progress_done(next_step_id=STEP_UPDATE_FAILED)
        except Exception:
            _LOGGER.exception("the Ranzenpost update failed in an unexpected way")
            return self.async_show_progress_done(next_step_id=STEP_UPDATE_FAILED)
        finally:
            self._task = None
            self._waiter = None
        return self.async_show_progress_done(next_step_id=STEP_UPDATED)

    async def _async_update(self) -> None:
        raise NotImplementedError

    async def async_step_updated(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return self.async_create_entry(data={})

    async def async_step_no_newer_version(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return self.async_abort(reason=ABORT_NO_NEWER_VERSION)

    async def async_step_update_failed(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return self.async_abort(reason=ABORT_UPDATE_FAILED)


class AppUpdateRepairFlow(UpdateRepairFlow):
    progress_step = STEP_UPDATE_APP

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self._entry_id = entry_id
        self._slug = ""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if not is_hassio(self.hass):
            return self.async_abort(reason=ABORT_NO_SUPERVISOR)
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        host = entry.data.get(CONF_HOST, "") if entry is not None else ""
        try:
            addon = await entry_addon(get_supervisor_client(self.hass), host)
        except SupervisorError as err:
            _LOGGER.error("the supervisor could not list the apps: %s", err)
            return self.async_abort(reason=ABORT_UPDATE_FAILED)
        if addon is None:
            return self.async_abort(reason=ABORT_NO_ADDON)
        self._slug = addon.slug
        return await self.async_step_confirm()

    async def async_step_update_app(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        return await self._progress()

    async def _async_update(self) -> None:
        client = get_supervisor_client(self.hass)
        try:
            await client.store.reload()
        except SupervisorError as err:
            _LOGGER.warning("the supervisor could not reload the app store, the update uses its last list: %s", err)
        info = await client.addons.addon_info(self._slug)
        if not info.update_available:
            raise NoNewerVersion(f"{self._slug} {info.version} is the newest in the store")
        await client.store.update_addon(self._slug)
        _LOGGER.info("the supervisor updated %s from %s to %s", self._slug, info.version, info.version_latest)


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


def hacs_update_entity(hass: HomeAssistant) -> str | None:
    scored = [
        (hacs_match(hass.states.get(entry.entity_id)), entry.entity_id)
        for entry in er.async_get(hass).entities.values()
        if entry.platform == HACS_DOMAIN and entry.domain == UPDATE_DOMAIN
    ]
    best = max((score for score, _ in scored), default=0)
    found = [entity_id for score, entity_id in scored if score == best]
    return found[0] if best and len(found) == 1 else None


class IntegrationUpdateRepairFlow(UpdateRepairFlow):
    progress_step = STEP_INSTALL_INTEGRATION

    def __init__(self) -> None:
        super().__init__()
        self._entity_id = ""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        entity_id = hacs_update_entity(self.hass)
        if entity_id is None:
            return self.async_abort(reason=ABORT_NO_HACS)
        state = self.hass.states.get(entity_id)
        if state is None or state.state != STATE_ON:
            return self.async_abort(reason=ABORT_NO_NEWER_VERSION)
        self._entity_id = entity_id
        return await self.async_step_confirm()

    async def async_step_install_integration(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self._progress()

    async def _async_update(self) -> None:
        await self.hass.services.async_call(
            UPDATE_DOMAIN, INSTALL_SERVICE, {"entity_id": self._entity_id}, blocking=True
        )
        _LOGGER.info("HACS installed the Ranzenpost integration update through %s", self._entity_id)
        for entry in self.hass.config_entries.async_loaded_entries(DOMAIN):
            entry.runtime_data.schedule_manifest_check()


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    if issue_id == RESTART_REQUIRED:
        return RestartRepairFlow()
    key, _, entry_id = issue_id.partition(":")
    if key in (APP_UPDATE_NEEDED, ADDON_TOO_OLD):
        return AppUpdateRepairFlow(str((data or {}).get(ISSUE_ENTRY) or entry_id))
    if key == INTEGRATION_TOO_OLD:
        return IntegrationUpdateRepairFlow()
    return ConfirmRepairFlow()
