STATUS_OK = "ok"
STATUS_ERROR = "error"

DISCOVERY_PREFIX = "homeassistant"
STATE_KEY = "state"


def _cid(child):
    return child["child_id"] if isinstance(child, dict) else child.child_id


def _cname(child):
    return child.get("name") if isinstance(child, dict) else child.name


def _unique_id(app_slug, child_id, key):
    return f"{app_slug}_{child_id}_{key}"


def _config_topic(component, app_slug, child_id, key):
    return f"{DISCOVERY_PREFIX}/{component}/{_unique_id(app_slug, child_id, key)}/config"


def _device_block(app_slug, child):
    return {
        "identifiers": [f"{app_slug}{_cid(child)}"],
        "name": f"IServ {_cname(child)}",
        "manufacturer": "Ranzenpost",
    }


def state_topic(app_slug, child_id, key):
    return f"{app_slug}/{child_id}/{key}"


def state_payload(last_updated, has_changes, error=None):
    return {
        "last_updated": last_updated,
        "status": STATUS_ERROR if error else STATUS_OK,
        "has_changes": "ON" if has_changes else "OFF",
    }


def discovery_configs(app_slug, child):
    device = _device_block(app_slug, child)
    topic = state_topic(app_slug, _cid(child), STATE_KEY)

    return [
        {
            "topic": _config_topic("sensor", app_slug, _cid(child), "last_updated"),
            "payload": {
                "unique_id": _unique_id(app_slug, _cid(child), "last_updated"),
                "name": "Last Updated",
                "state_topic": topic,
                "value_template": "{{ value_json.last_updated }}",
                "device_class": "text",
                "device": device,
            },
        },
        {
            "topic": _config_topic("sensor", app_slug, _cid(child), "status"),
            "payload": {
                "unique_id": _unique_id(app_slug, _cid(child), "status"),
                "name": "Status",
                "state_topic": topic,
                "value_template": "{{ value_json.status }}",
                "device": device,
            },
        },
        {
            "topic": _config_topic("binary_sensor", app_slug, _cid(child), "has_changes"),
            "payload": {
                "unique_id": _unique_id(app_slug, _cid(child), "has_changes"),
                "name": "Has Changes",
                "state_topic": topic,
                "value_template": "{{ value_json.has_changes }}",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": device,
            },
        },
    ]
