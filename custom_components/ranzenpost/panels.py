from __future__ import annotations

from typing import Any

LEGACY_PANEL = "hassio"
LEGACY_PANEL_PREFIX = "/hassio/ingress/"
APP_PANEL = "app"
APP_PANEL_PREFIX = "/app/"
PANELS_KEY = "frontend_panels"


def app_panel_path(panels: Any, ingress_path: str) -> str:
    if not ingress_path.startswith(LEGACY_PANEL_PREFIX):
        return ingress_path
    names = panels if isinstance(panels, dict) else {}
    if APP_PANEL in names and LEGACY_PANEL not in names:
        return APP_PANEL_PREFIX + ingress_path[len(LEGACY_PANEL_PREFIX):]
    return ingress_path
