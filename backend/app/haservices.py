import os

CORE_API = "http://supervisor/core/api"
NOTIFY_DOMAIN = "notify"
MOBILE_APP_PREFIX = "mobile_app_"
PERSISTENT_SERVICE_NAME = "persistent_notification"
GROUP_SERVICE_NAME = "notify"
CATEGORY_MOBILE = "mobile"
CATEGORY_PERSISTENT = "persistent"
CATEGORY_GROUP = "group"
CATEGORY_OTHER = "other"
SOURCE_ENTITY = "entity"
SOURCE_DEVICE_TRACKER = "device_tracker"
NAME_DOMAINS = (NOTIFY_DOMAIN, SOURCE_DEVICE_TRACKER)
REQUEST_TIMEOUT = 10


def parse_notify_services(services_json):
    result = []
    for entry in services_json or []:
        if not isinstance(entry, dict) or entry.get("domain") != NOTIFY_DOMAIN:
            continue
        services = entry.get("services")
        if not isinstance(services, (dict, list, tuple)):
            continue
        for name in services:
            if isinstance(name, str) and name:
                result.append(f"{NOTIFY_DOMAIN}.{name}")
    return sorted(set(result))


def service_category(service):
    name = str(service or "").partition(".")[2]
    if name.startswith(MOBILE_APP_PREFIX) and len(name) > len(MOBILE_APP_PREFIX):
        return CATEGORY_MOBILE
    if name == PERSISTENT_SERVICE_NAME:
        return CATEGORY_PERSISTENT
    if name == GROUP_SERVICE_NAME:
        return CATEGORY_GROUP
    return CATEGORY_OTHER


def parse_entity_names(states_json):
    result = {}
    for entry in states_json or []:
        if not isinstance(entry, dict):
            continue
        entity_id = entry.get("entity_id")
        attributes = entry.get("attributes")
        if not isinstance(entity_id, str) or not isinstance(attributes, dict):
            continue
        name = attributes.get("friendly_name")
        if not isinstance(name, str) or not name.strip():
            continue
        result[entity_id] = name.strip()
    return result


def resolve_service_name(service, entity_names):
    names = entity_names or {}
    direct = names.get(service)
    if direct:
        return direct, SOURCE_ENTITY
    local = str(service or "").partition(".")[2]
    if not local.startswith(MOBILE_APP_PREFIX):
        return None, None
    slug = local[len(MOBILE_APP_PREFIX):]
    if not slug:
        return None, None
    for domain in NAME_DOMAINS:
        candidate = names.get(f"{domain}.{slug}")
        if candidate:
            return candidate, SOURCE_ENTITY if domain == NOTIFY_DOMAIN else SOURCE_DEVICE_TRACKER
    return None, None


def describe_notify_services(services_json, entity_names=None):
    described = []
    for service in parse_notify_services(services_json):
        name, source = resolve_service_name(service, entity_names)
        described.append(
            {
                "service": service,
                "name": name,
                "name_source": source,
                "category": service_category(service),
            }
        )
    return described


def allowed_service_ids(payload):
    entries = (payload or {}).get("services") or []
    result = []
    for entry in entries:
        if isinstance(entry, str):
            result.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("service"), str):
            result.append(entry["service"])
    return result


def _fetch_json(path, headers):
    import requests

    response = requests.get(f"{CORE_API}{path}", headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _fetch_entity_names(headers):
    import requests

    try:
        return parse_entity_names(_fetch_json("/states", headers))
    except (requests.RequestException, ValueError, TypeError):
        return {}


def list_notify_services():
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return {"supervisor": False, "services": []}
    import requests

    headers = {"Authorization": f"Bearer {token}"}
    try:
        catalog = _fetch_json("/services", headers)
    except (requests.RequestException, ValueError):
        return {"supervisor": False, "services": []}
    services = parse_notify_services(catalog)
    entity_names = _fetch_entity_names(headers) if services else {}
    return {"supervisor": True, "services": describe_notify_services(catalog, entity_names)}
