from __future__ import annotations

from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Change, Child
from .const import ATTR_CHILD, ATTR_DATE, ATTR_PERIOD, ATTR_SUMMARY, CHANGE_KINDS, KEY_TIMETABLE_CHANGED, MODULE_TIMETABLE
from .coordinator import RanzenpostConfigEntry, RanzenpostCoordinator, RanzenpostData, selected_children
from .entity import RanzenpostChildEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RanzenpostConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    info = coordinator.data.info
    async_add_entities(
        RanzenpostTimetableEvent(coordinator, child)
        for child in selected_children(info, entry)
        if info.modules_of(child).has(MODULE_TIMETABLE)
    )


class RanzenpostTimetableEvent(RanzenpostChildEntity, EventEntity):
    _attr_event_types = list(CHANGE_KINDS)

    def __init__(self, coordinator: RanzenpostCoordinator, child: Child) -> None:
        super().__init__(coordinator, EVENT_DOMAIN, child, KEY_TIMETABLE_CHANGED)
        self._announced: RanzenpostData | None = coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not self._announced:
            self._announced = data
            for change in data.new_changes:
                if change.child_key == self.child.key and change.kind in CHANGE_KINDS:
                    self._trigger_event(change.kind, self._attributes_of(change))
        super()._handle_coordinator_update()

    def _attributes_of(self, change: Change) -> dict[str, object]:
        return {
            ATTR_CHILD: self.child.name,
            ATTR_SUMMARY: change.summary,
            ATTR_DATE: change.date.isoformat() if change.date else None,
            ATTR_PERIOD: change.period,
        }
