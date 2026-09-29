import re

VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:b(\d{1,3}))?$")
FINAL = 10**6
MAX_LENGTH = 32
UPDATE_APP = "app"
UPDATE_INTEGRATION = "integration"
UPDATE_RESTART = "restart"


def parse_version(text):
    match = VERSION_PATTERN.match(str(text or "").strip())
    if match is None:
        return None
    beta = match.group(4)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), FINAL if beta is None else int(beta))


def clean_version(text):
    value = str(text or "").strip()
    if len(value) > MAX_LENGTH or parse_version(value) is None:
        return ""
    return value


def pending_updates(app_version, loaded_version, installed_version="", unversioned=False):
    app = parse_version(app_version)
    if unversioned:
        return [UPDATE_INTEGRATION] if app is not None else []
    loaded = parse_version(loaded_version)
    if app is None or loaded is None:
        return []
    installed = parse_version(installed_version)
    restart = installed is not None and installed > loaded
    target = installed if restart else loaded
    steps = []
    if app < target:
        steps.append(UPDATE_APP)
    if app > target:
        steps.append(UPDATE_INTEGRATION)
    if restart:
        steps.append(UPDATE_RESTART)
    return steps
