import json
import os
from datetime import timedelta

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.translation import async_get_translations
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.ranzenpost.api import HEADER_INSTALLED, HEADER_INTEGRATION
from custom_components.ranzenpost.config_flow import validate_connection
from custom_components.ranzenpost.const import DOMAIN
from custom_components.ranzenpost.version import FINAL, mismatch_is_severe, parse_version, version_mismatch

from . import ENTRY_DATA, MANIFEST_VERSION, fixture, mock_addon, route, setup_entry

LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
LOADED = parse_version(MANIFEST_VERSION)
NEXT_FEATURE = f"{LOADED[0]}.{LOADED[1] + 1}.0"
NEXT_FIX = f"{LOADED[0]}.{LOADED[1]}.{LOADED[2] + 1}"
PREVIOUS_FEATURE = f"{LOADED[0]}.{LOADED[1] - 1}.0"


def issue(hass, entry, key):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}:{entry.entry_id}")


def restart_issue(hass):
    return ir.async_get(hass).async_get_issue(DOMAIN, "restart_required")


def info_of(version):
    info = fixture("info")
    info["version"] = version
    return info


async def settle(hass):
    await hass.async_block_till_done(wait_background_tasks=True)


async def refresh(hass, aioclient_mock, frozen_now, info=None):
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await settle(hass)


@pytest.fixture
def manifest_on_disk(hass, tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    stamps = iter(range(1_700_000_000, 1_800_000_000, 10))

    def write(version):
        path.write_text(json.dumps({"domain": DOMAIN, "version": version}), encoding="utf-8")
        stamp = next(stamps)
        os.utime(path, (stamp, stamp))

    async def install(version):
        await hass.async_add_executor_job(write, version)

    write(MANIFEST_VERSION)
    monkeypatch.setattr("custom_components.ranzenpost.coordinator.MANIFEST_FILE", path)
    return install


async def test_an_app_a_feature_release_behind_raises_an_error_repair_with_the_update_path(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(PREVIOUS_FEATURE))

    found = issue(hass, entry, "app_update_needed")
    assert found is not None
    assert found.severity == ir.IssueSeverity.ERROR
    assert found.is_fixable is False
    assert found.translation_key == "app_update_needed"
    assert found.translation_placeholders["addon_version"] == PREVIOUS_FEATURE
    assert found.translation_placeholders["integration_version"] == MANIFEST_VERSION
    assert issue(hass, entry, "integration_too_old") is None
    assert issue(hass, entry, "addon_too_old") is None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"

    await refresh(hass, aioclient_mock, frozen_now)

    assert issue(hass, entry, "app_update_needed") is None


def older_on_the_same_line():
    year, line, fix, beta = LOADED
    if beta != FINAL:
        return f"{year}.{line}.{fix}b{beta - 1}" if beta > 0 else (f"{year}.{line}.{fix - 1}" if fix > 0 else None)
    return f"{year}.{line}.{fix}b1"


async def test_an_app_a_fix_release_behind_raises_a_warning_repair(hass, aioclient_mock, frozen_now):
    older_fix = older_on_the_same_line()
    if older_fix is None:
        assert version_mismatch("2609.5.0", "2609.5.1", False) == "app_update_needed"
        assert mismatch_is_severe("app_update_needed", "2609.5.0", "2609.5.1") is False
        return
    entry = await setup_entry(hass, aioclient_mock, info=info_of(older_fix))

    found = issue(hass, entry, "app_update_needed")
    assert found.severity == ir.IssueSeverity.WARNING


async def test_an_app_a_fix_release_ahead_asks_for_the_integration_update(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(NEXT_FIX))

    found = issue(hass, entry, "integration_too_old")
    assert found.severity == ir.IssueSeverity.WARNING
    assert issue(hass, entry, "app_update_needed") is None


async def test_the_version_repair_switches_sides_when_the_other_side_overtakes(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(PREVIOUS_FEATURE))
    assert issue(hass, entry, "app_update_needed") is not None

    await refresh(hass, aioclient_mock, frozen_now, info=info_of(NEXT_FEATURE))

    assert issue(hass, entry, "app_update_needed") is None
    assert issue(hass, entry, "integration_too_old") is not None


async def test_every_version_repair_text_names_the_path_in_every_language(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    expected = {
        "en": ("Settings → Apps", "Check for updates", "Update", "HACS", "Restart Home Assistant"),
        "de": ("Einstellungen → Apps", "Nach Updates suchen", "Aktualisieren", "HACS", "Home Assistant neu starten"),
    }
    for language in LANGUAGES:
        issues = await async_get_translations(hass, language, "issues", {DOMAIN})
        prefix = f"component.{DOMAIN}.issues"
        app = issues[f"{prefix}.app_update_needed.description"]
        too_old = issues[f"{prefix}.addon_too_old.description"]
        integration = issues[f"{prefix}.integration_too_old.description"]
        restart = issues[f"{prefix}.restart_required.fix_flow.step.confirm.description"]
        for text in (app, too_old, integration, restart):
            assert "Ranzenpost" in text, language
        assert "{addon_version}" in app and "{integration_version}" in app, language
        assert "{installed_version}" in restart and "{loaded_version}" in restart, language
        assert "HACS" in integration, language
        assert "add-on" not in (app + too_old + integration + restart).lower(), language
        if language in expected:
            settings, check, update, hacs, restart_label = expected[language]
            assert settings in app and check in app and update in app, language
            assert settings in too_old and check in too_old, language
            assert hacs in integration and restart_label in integration, language
            assert restart_label in restart, language


async def test_an_integration_updated_on_disk_asks_for_a_restart_until_home_assistant_restarts(
    hass, aioclient_mock, frozen_now, manifest_on_disk
):
    entry = await setup_entry(hass, aioclient_mock)
    assert restart_issue(hass) is None

    await manifest_on_disk(NEXT_FEATURE)
    await refresh(hass, aioclient_mock, frozen_now)

    found = restart_issue(hass)
    assert found is not None
    assert found.is_fixable is True
    assert found.severity == ir.IssueSeverity.WARNING
    assert found.translation_placeholders == {"loaded_version": MANIFEST_VERSION, "installed_version": NEXT_FEATURE}
    app = issue(hass, entry, "app_update_needed")
    assert app is not None
    assert app.translation_placeholders["integration_version"] == NEXT_FEATURE

    await manifest_on_disk(MANIFEST_VERSION)
    await refresh(hass, aioclient_mock, frozen_now)

    assert restart_issue(hass) is None
    assert issue(hass, entry, "app_update_needed") is None


async def test_an_integration_updated_on_disk_to_the_app_version_only_asks_for_the_restart(
    hass, aioclient_mock, frozen_now, manifest_on_disk
):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(NEXT_FEATURE))
    assert issue(hass, entry, "integration_too_old") is not None

    await manifest_on_disk(NEXT_FEATURE)
    await refresh(hass, aioclient_mock, frozen_now, info=info_of(NEXT_FEATURE))

    assert restart_issue(hass) is not None
    assert issue(hass, entry, "integration_too_old") is None
    assert issue(hass, entry, "app_update_needed") is None


async def test_the_restart_repair_is_raised_even_while_the_app_is_unreachable(
    hass, aioclient_mock, frozen_now, manifest_on_disk
):
    await setup_entry(hass, aioclient_mock)
    await manifest_on_disk(NEXT_FIX)
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), status=500)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await settle(hass)

    assert restart_issue(hass) is not None


async def test_an_unreadable_manifest_raises_no_restart_repair(hass, aioclient_mock, frozen_now, tmp_path, monkeypatch):
    monkeypatch.setattr("custom_components.ranzenpost.coordinator.MANIFEST_FILE", tmp_path / "missing.json")
    await setup_entry(hass, aioclient_mock)

    assert restart_issue(hass) is None


async def test_confirming_the_restart_repair_restarts_home_assistant(
    hass, aioclient_mock, frozen_now, manifest_on_disk, hass_client
):
    restarts = async_mock_service(hass, "homeassistant", "restart")
    await manifest_on_disk(NEXT_FIX)
    await setup_entry(hass, aioclient_mock)
    await settle(hass)
    assert restart_issue(hass) is not None
    assert await async_setup_component(hass, "repairs", {})
    client = await hass_client()

    started = await client.post("/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": "restart_required"})
    flow = await started.json()
    assert flow["step_id"] == "confirm"
    assert flow["description_placeholders"] == {"loaded_version": MANIFEST_VERSION, "installed_version": NEXT_FIX}
    assert restarts == []

    confirmed = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")
    assert (await confirmed.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    assert len(restarts) == 1


async def test_removing_the_last_entry_clears_the_restart_repair(hass, aioclient_mock, frozen_now, manifest_on_disk):
    await manifest_on_disk(NEXT_FIX)
    entry = await setup_entry(hass, aioclient_mock)
    await settle(hass)
    assert restart_issue(hass) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert restart_issue(hass) is None


async def test_every_call_to_the_app_names_the_integration_version(
    hass, aioclient_mock, frozen_now, manifest_on_disk
):
    await setup_entry(hass, aioclient_mock)
    calls = [call for call in aioclient_mock.mock_calls if "/api/integration/" in str(call[1])]
    assert calls
    for call in calls:
        headers = call[3] or {}
        assert headers.get(HEADER_INTEGRATION) == MANIFEST_VERSION
        assert HEADER_INSTALLED not in headers
        assert headers.get("Authorization", "").startswith("Bearer ")

    await manifest_on_disk(NEXT_FIX)
    await refresh(hass, aioclient_mock, frozen_now)
    await refresh(hass, aioclient_mock, frozen_now)

    calls = [call for call in aioclient_mock.mock_calls if "/api/integration/" in str(call[1])]
    assert calls
    for call in calls:
        assert call[3].get(HEADER_INTEGRATION) == MANIFEST_VERSION
        assert call[3].get(HEADER_INSTALLED) == NEXT_FIX


async def test_the_connection_sensor_names_the_loaded_integration_version(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    connection = next(state for state in hass.states.async_all("sensor") if state.entity_id.endswith("_connection"))
    assert connection.attributes["integration_version"] == MANIFEST_VERSION


async def test_the_setup_check_names_the_integration_version_too(hass, aioclient_mock):
    aioclient_mock.get(route("info"), json=fixture("info"))

    await validate_connection(hass, ENTRY_DATA)

    headers = aioclient_mock.mock_calls[-1][3]
    assert headers.get(HEADER_INTEGRATION) == MANIFEST_VERSION
