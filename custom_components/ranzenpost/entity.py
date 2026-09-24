from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .api import Child, Info, SchoolInfo, State
from .const import BRAND, DOMAIN
from .coordinator import RanzenpostCoordinator
from .devices import child_identifier, school_identifier

MODEL_SCHOOL = "IServ school server"
MODEL_CHILD = "IServ account"
PANEL_SCHEME = "homeassistant:/"


def panel_url(ingress_path: str) -> str | None:
    return f"{PANEL_SCHEME}{ingress_path}" if ingress_path.startswith("/") else None


def school_slug(school: SchoolInfo | None) -> str:
    return slugify(school.label) if school else ""


def first_name_is_shared(info: Info, child: Child) -> bool:
    wanted = slugify(child.first_name)
    return any(
        other.key != child.key and other.school_id != child.school_id and slugify(other.first_name) == wanted
        for other in info.children
    )


def child_slug(info: Info, child: Child) -> str:
    name = slugify(child.first_name)
    if first_name_is_shared(info, child):
        return f"{name}_{school_slug(info.school_of(child))}"
    return name


def child_entity_id(platform: str, info: Info, child: Child, key: str) -> str:
    return f"{platform}.{DOMAIN}_{child_slug(info, child)}_{key}"


def school_entity_id(platform: str, info: Info, school: SchoolInfo, key: str) -> str:
    if info.many_schools:
        return f"{platform}.{DOMAIN}_school_{school_slug(school)}_{key}"
    return f"{platform}.{DOMAIN}_school_{key}"


def child_unique_id(entry_id: str, child: Child, key: str) -> str:
    return f"{DOMAIN}_{entry_id}_{child.key}_{key}"


def school_unique_id(entry_id: str, school_id: str, key: str) -> str:
    return f"{DOMAIN}_{entry_id}_school_{school_id}_{key}"


def school_device_info(entry_id: str, school: SchoolInfo, info: Info) -> DeviceInfo:
    return DeviceInfo(
        identifiers={school_identifier(entry_id, school.id)},
        name=f"{BRAND} {school.label}".strip(),
        manufacturer=BRAND,
        model=MODEL_SCHOOL,
        sw_version=info.version or None,
        configuration_url=panel_url(info.ingress_path),
    )


def child_device_info(entry_id: str, info: Info, child: Child) -> DeviceInfo:
    school = info.school_of(child)
    shown = f"{child.first_name} ({school.label})" if school and first_name_is_shared(info, child) else child.first_name
    return DeviceInfo(
        identifiers={child_identifier(entry_id, child)},
        name=f"{BRAND} {shown}",
        manufacturer=BRAND,
        model=MODEL_CHILD,
        via_device=school_identifier(entry_id, child.school_id),
        configuration_url=panel_url(info.ingress_path),
    )


class RanzenpostSchoolEntity(CoordinatorEntity[RanzenpostCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RanzenpostCoordinator, platform: str, school: SchoolInfo, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        self.school_id = school.id
        entry_id = coordinator.config_entry.entry_id
        self.entity_id = school_entity_id(platform, coordinator.data.info, school, key)
        self._attr_translation_key = key
        self._attr_unique_id = school_unique_id(entry_id, school.id, key)
        self._attr_device_info = school_device_info(entry_id, school, coordinator.data.info)

    @property
    def info(self) -> Info:
        return self.coordinator.data.info

    @property
    def school_info(self) -> SchoolInfo | None:
        return self.info.school(self.school_id)

    @property
    def available(self) -> bool:
        return super().available and self.school_info is not None


class RanzenpostChildEntity(CoordinatorEntity[RanzenpostCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RanzenpostCoordinator, platform: str, child: Child, key: str) -> None:
        super().__init__(coordinator)
        self.child = child
        self.key = key
        entry_id = coordinator.config_entry.entry_id
        self.entity_id = child_entity_id(platform, coordinator.data.info, child, key)
        self._attr_translation_key = key
        self._attr_unique_id = child_unique_id(entry_id, child, key)
        self._attr_device_info = child_device_info(entry_id, coordinator.data.info, child)

    @property
    def available(self) -> bool:
        return super().available and self.child.key in self.coordinator.data.states

    @property
    def state_of_child(self) -> State | None:
        return self.coordinator.data.states.get(self.child.key)
