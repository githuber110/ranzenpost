from __future__ import annotations

import re

from .const import MIN_ADDON_VERSION

VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:b(\d{1,3}))?$")
FINAL = 10**6
ADDON_TOO_OLD = "addon_too_old"
INTEGRATION_TOO_OLD = "integration_too_old"

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
    if integration is not None and release_line(addon) > release_line(integration):
        return INTEGRATION_TOO_OLD
    return None
