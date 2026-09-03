from app.iserv.models import Child
from app.mqtt_bridge import discovery_configs, state_payload, state_topic


def child(child_id="7a", name="Alex"):
    return Child(child_id=child_id, name=name)


def test_topic_schema_matches_ha_discovery_convention():
    entries = discovery_configs("iserv_connector", child())
    for entry in entries:
        assert entry["topic"].startswith("homeassistant/")
        assert entry["topic"].endswith("/config")
    components = [entry["topic"].split("/")[1] for entry in entries]
    assert components == ["sensor", "sensor", "binary_sensor"]


def test_unique_id_distinct_per_child_and_key():
    entries_a = discovery_configs("iserv_connector", child("7a", "Alex"))
    entries_b = discovery_configs("iserv_connector", child("9b", "Robin"))
    ids = [entry["payload"]["unique_id"] for entry in entries_a + entries_b]
    assert len(ids) == len(set(ids))


def test_device_block_shared_across_entities_of_same_child():
    entries = discovery_configs("iserv_connector", child("7a", "Alex"))
    devices = [entry["payload"]["device"] for entry in entries]
    assert all(device == devices[0] for device in devices)
    assert devices[0]["identifiers"] == ["iserv_connector7a"]
    assert devices[0]["name"] == "IServ Alex"
    assert devices[0]["manufacturer"] == "Ranzenpost"


def test_has_changes_binary_payload_on_off():
    on_payload = state_payload(last_updated="31.08.2026 07:30", has_changes=True, error=None)
    off_payload = state_payload(last_updated="31.08.2026 07:30", has_changes=False, error=None)
    assert on_payload["has_changes"] == "ON"
    assert off_payload["has_changes"] == "OFF"


def test_state_topic_matches_discovery_state_topics():
    entries = discovery_configs("iserv_connector", child("7a", "Alex"))
    expected = state_topic("iserv_connector", "7a", "state")
    assert all(entry["payload"]["state_topic"] == expected for entry in entries)


def test_status_reflects_error_flag():
    ok_payload = state_payload(last_updated="31.08.2026 07:30", has_changes=False, error=None)
    error_payload = state_payload(last_updated="31.08.2026 07:30", has_changes=False, error="login failed")
    assert ok_payload["status"] == "ok"
    assert error_payload["status"] == "error"


def test_value_templates_reference_matching_json_keys():
    entries = discovery_configs("iserv_connector", child("7a", "Alex"))
    by_unique_id = {entry["payload"]["unique_id"]: entry["payload"] for entry in entries}
    assert "value_json.last_updated" in by_unique_id["iserv_connector_7a_last_updated"]["value_template"]
    assert "value_json.status" in by_unique_id["iserv_connector_7a_status"]["value_template"]
    assert "value_json.has_changes" in by_unique_id["iserv_connector_7a_has_changes"]["value_template"]
