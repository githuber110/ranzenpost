import json
import pathlib

from homeassistant import loader
from homeassistant.loader import Manifest, async_get_integration

INTEGRATION = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost"
HACS = INTEGRATION.parents[1] / "hacs.json"
REQUIRED_KEYS = ("domain", "name", "version", "codeowners", "documentation", "iot_class")
IOT_CLASSES = ("assumed_state", "cloud_polling", "cloud_push", "local_polling", "local_push", "calculated")
INTEGRATION_TYPES = ("device", "entity", "hardware", "helper", "hub", "service", "system", "virtual")


def manifest():
    return json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_uses_only_keys_the_loader_knows():
    known = set(Manifest.__annotations__)
    assert set(manifest()) <= known, set(manifest()) - known


def test_manifest_carries_every_key_hassfest_requires_of_a_custom_integration():
    data = manifest()
    for key in REQUIRED_KEYS:
        assert data.get(key), key
    assert data["iot_class"] in IOT_CLASSES
    assert data["integration_type"] in INTEGRATION_TYPES
    assert data["config_flow"] is True
    assert all(owner.startswith("@") for owner in data["codeowners"])
    assert data["documentation"].startswith("https://")
    assert data["issue_tracker"].startswith("https://")
    assert isinstance(data["requirements"], list)
    assert isinstance(data["dependencies"], list)
    assert isinstance(data["after_dependencies"], list)


async def test_the_loader_accepts_the_integration_with_its_platforms(hass):
    integration = await async_get_integration(hass, "ranzenpost")
    assert integration.domain == "ranzenpost"
    assert integration.version is not None
    assert str(integration.version) == manifest()["version"]
    assert integration.config_flow is True
    assert integration.iot_class == "local_polling"
    assert integration.integration_type == "hub"
    assert integration.dependencies == ["http"]
    assert integration.after_dependencies == ["hassio", "lovelace"]
    assert integration.requirements == []
    platforms = ("binary_sensor", "calendar", "event", "sensor", "config_flow", "diagnostics")
    assert integration.platforms_exists(platforms) == list(platforms)
    for platform in platforms:
        await integration.async_get_platform(platform)
    assert loader.async_get_loaded_integration(hass, "ranzenpost") is integration


def test_hacs_json_names_the_integration_and_a_minimum_core_version():
    data = json.loads(HACS.read_text(encoding="utf-8"))
    assert data["name"] == "Ranzenpost"
    assert data["homeassistant"]
    assert set(data) <= {"name", "render_readme", "homeassistant", "hacs", "content_in_root", "zip_release", "filename", "country", "hide_default_branch", "persistent_directory"}
