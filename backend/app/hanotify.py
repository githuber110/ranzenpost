import os
import re
from urllib.parse import quote

SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


NOTIFY_DOMAIN = "notify"


def is_valid_service_format(service):
    return bool(service) and bool(SERVICE_PATTERN.match(service))


def is_notify_service(service):
    return is_valid_service_format(service) and service.partition(".")[0] == NOTIFY_DOMAIN


def notify_service_list(values):
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        target = value.strip() if isinstance(value, str) else ""
        if is_notify_service(target) and target not in result:
            result.append(target)
    return result


def notify(message, service=None, title="Ranzenpost"):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False
    target = str(service or "").strip()
    if not is_notify_service(target):
        return False
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
