from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .api import Child, Modules
from .const import DOMAIN, MODULES

DEVICE_SCHOOL = "school"
DEVICE_CHILD = "child"
IDENTIFIER_SEPARATOR = ":"


def school_identifier(entry_id: str, school_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{DEVICE_SCHOOL}{IDENTIFIER_SEPARATOR}{entry_id}{IDENTIFIER_SEPARATOR}{school_id}")


def child_key_identifier(entry_id: str, child_key: str) -> tuple[str, str]:
    return (DOMAIN, f"{DEVICE_CHILD}{IDENTIFIER_SEPARATOR}{entry_id}{IDENTIFIER_SEPARATOR}{child_key}")


def child_identifier(entry_id: str, child: Child) -> tuple[str, str]:
    return child_key_identifier(entry_id, child.key)


@dataclass(frozen=True)
class DeviceRef:
    kind: str
    entry_id: str
    key: str

    @property
    def is_child(self) -> bool:
        return self.kind == DEVICE_CHILD


def device_ref(device: dr.DeviceEntry | None) -> DeviceRef | None:
    if device is None:
        return None
    for domain, identifier in device.identifiers:
        if domain != DOMAIN:
            continue
        kind, _, rest = identifier.partition(IDENTIFIER_SEPARATOR)
        entry_id, separator, key = rest.partition(IDENTIFIER_SEPARATOR)
        if kind in (DEVICE_SCHOOL, DEVICE_CHILD) and separator and key:
            return DeviceRef(kind, entry_id, key)
    return None


@callback
def device_ref_of_id(hass: HomeAssistant, device_id: str) -> DeviceRef | None:
    return device_ref(dr.async_get(hass).async_get(device_id))


@callback
def data_of_device(hass: HomeAssistant, ref: DeviceRef):
    entry = hass.config_entries.async_get_entry(ref.entry_id)
    coordinator = getattr(entry, "runtime_data", None)
    return getattr(coordinator, "data", None)


@callback
def device_id_of(hass: HomeAssistant, identifier: tuple[str, str]) -> str | None:
    device = dr.async_get(hass).async_get_device(identifiers={identifier})
    return device.id if device else None


@callback
def modules_of_device(hass: HomeAssistant, ref: DeviceRef) -> Modules:
    data = data_of_device(hass, ref)
    child = next((child for child in data.info.children if child.key == ref.key), None) if data else None
    return data.info.modules_of(child) if child else Modules(frozenset(MODULES))
