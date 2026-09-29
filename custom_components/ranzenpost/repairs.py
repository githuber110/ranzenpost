from __future__ import annotations

from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .version import RESTART_REQUIRED

HOMEASSISTANT_DOMAIN = "homeassistant"
RESTART_SERVICE = "restart"


class RestartRepairFlow(ConfirmRepairFlow):
    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is None:
            return await super().async_step_confirm()
        await self.hass.services.async_call(HOMEASSISTANT_DOMAIN, RESTART_SERVICE, blocking=False)
        return self.async_create_entry(data={})


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    if issue_id == RESTART_REQUIRED:
        return RestartRepairFlow()
    return ConfirmRepairFlow()
