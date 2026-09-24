from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import State
from .const import KEY_SCHOOL_DAY_TODAY, KEY_TIMETABLE_CHANGED_TODAY, MODULE_TIMETABLE
from .coordinator import RanzenpostConfigEntry, RanzenpostCoordinator, selected_children
from .entity import RanzenpostChildEntity


@dataclass(frozen=True, kw_only=True)
class ChildBinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[State], bool]


CHILD_BINARY_SENSORS: tuple[ChildBinarySensorDescription, ...] = (
    ChildBinarySensorDescription(key=KEY_SCHOOL_DAY_TODAY, is_on_fn=lambda state: state.school_day_today),
    ChildBinarySensorDescription(
        key=KEY_TIMETABLE_CHANGED_TODAY, is_on_fn=lambda state: state.timetable_changed_today
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RanzenpostConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    info = coordinator.data.info
    async_add_entities(
        RanzenpostChildBinarySensor(coordinator, child, description)
        for child in selected_children(info, entry)
        if info.modules_of(child).has(MODULE_TIMETABLE)
        for description in CHILD_BINARY_SENSORS
    )


class RanzenpostChildBinarySensor(RanzenpostChildEntity, BinarySensorEntity):
    entity_description: ChildBinarySensorDescription

    def __init__(
        self, coordinator: RanzenpostCoordinator, child, description: ChildBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, BINARY_SENSOR_DOMAIN, child, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        state = self.state_of_child
        return self.entity_description.is_on_fn(state) if state else None
