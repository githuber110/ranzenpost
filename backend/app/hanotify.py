import os
import re
from urllib.parse import quote

DEFAULT_SERVICE = "persistent_notification.create"

SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def is_valid_service_format(service):
    return bool(service) and bool(SERVICE_PATTERN.match(service))


def notify(message, service=None, title="Ranzenpost"):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False
    target = (service or DEFAULT_SERVICE).strip()
    if not is_valid_service_format(target):
        return False
    if target != DEFAULT_SERVICE:
        from .haservices import allowed_service_ids, list_notify_services

        allowlist = list_notify_services()
        if allowlist.get("supervisor") and target not in allowed_service_ids(allowlist):
            return False
    domain, _, name = target.partition(".")
    import requests

    try:
        requests.post(
            f"http://supervisor/core/api/services/{quote(domain, safe='')}/{quote(name, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message, "title": title},
            timeout=10,
        )
    except requests.RequestException:
        return False
    return True
