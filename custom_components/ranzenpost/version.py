from __future__ import annotations

import re

from .const import MIN_ADDON_VERSION

VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:b(\d{1,3}))?$")
FINAL = 10**6
ADDON_TOO_OLD = "addon_too_old"
APP_UPDATE_NEEDED = "app_update_needed"
INTEGRATION_TOO_OLD = "integration_too_old"
RESTART_REQUIRED = "restart_required"

type Version = tuple[int, int, int, int]


def parse_version(text: str) -> Version | None:
    match = VERSION_PATTERN.match(str(text or ""))
    if match is None:
        return None
    beta = match.group(4)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), FINAL if beta is None else int(beta))


def release_line(version: Version) -> tuple[int, int]:
    return (version[0], version[1])


def version_mismatch(addon_version: str, integration_version: str, legacy: bool) -> str | None:
    if legacy:
        return ADDON_TOO_OLD
    addon = parse_version(addon_version)
    if addon is None:
        return None
    if addon < parse_version(MIN_ADDON_VERSION):
        return ADDON_TOO_OLD
    integration = parse_version(integration_version)
    if integration is None or integration == addon:
        return None
    return INTEGRATION_TOO_OLD if addon > integration else APP_UPDATE_NEEDED


def mismatch_is_severe(mismatch: str | None, addon_version: str, integration_version: str) -> bool:
    if mismatch == ADDON_TOO_OLD:
        return True
    if mismatch != APP_UPDATE_NEEDED:
        return False
    addon = parse_version(addon_version)
    integration = parse_version(integration_version)
    return addon is not None and integration is not None and release_line(addon) < release_line(integration)


def newer_version(loaded: str, installed: str) -> str:
    current = parse_version(loaded)
    candidate = parse_version(installed)
    if candidate is None or (current is not None and candidate <= current):
        return loaded
    return installed


def restart_pending(loaded: str, installed: str) -> bool:
    current = parse_version(loaded)
    candidate = parse_version(installed)
    return current is not None and candidate is not None and candidate > current
