import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from aiohasupervisor import SupervisorError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.ranzenpost.addon import entry_addon
from custom_components.ranzenpost.const import DOMAIN
from custom_components.ranzenpost.repairs import hacs_update_entity
from custom_components.ranzenpost.version import parse_version

from . import MANIFEST_VERSION, fixture, setup_entry

APP_SLUG = "abc123_ranzenpost"
REPAIRS_MODULE = "custom_components.ranzenpost.repairs"
LOADED = parse_version(MANIFEST_VERSION)
NEXT_FEATURE = f"{LOADED[0]}.{LOADED[1] + 1}.0"
PREVIOUS_FEATURE = f"{LOADED[0]}.{LOADED[1] - 1}.0"


def info_of(version):
    info = fixture("info")
    info["version"] = version
    return info


def issue(hass, entry, key):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}:{entry.entry_id}")


def restart_issue(hass):
    return ir.async_get(hass).async_get_issue(DOMAIN, "restart_required")


async def settle(hass):
    await hass.async_block_till_done(wait_background_tasks=True)


def installed(slug):
    addon = MagicMock()
    addon.slug = slug
    return addon


def app_supervisor(addons=None, update_available=True):
    client = MagicMock()
    client.addons.list = AsyncMock(return_value=addons if addons is not None else [installed(APP_SLUG)])
    info = MagicMock()
    info.update_available = update_available
    info.version = PREVIOUS_FEATURE
    info.version_latest = MANIFEST_VERSION if update_available else PREVIOUS_FEATURE
    client.addons.addon_info = AsyncMock(return_value=info)
    client.store.reload = AsyncMock()
    client.store.update_addon = AsyncMock()
    return client


def on_supervisor(hass, client):
    hass.config.components.add("hassio")
    return patch(f"{REPAIRS_MODULE}.get_supervisor_client", return_value=client)


async def start_fix(hass, hass_client, issue_id):
    assert await async_setup_component(hass, "repairs", {})
    client = await hass_client()
    started = await client.post("/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id})
    return client, await started.json()


async def confirm_fix(hass, client, flow):
    result = await (await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")).json()
    while result["type"] in ("progress", "progress_done"):
        await settle(hass)
        result = await (await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")).json()
    return result


async def app_behind(hass, aioclient_mock, version=PREVIOUS_FEATURE, key="app_update_needed"):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(version))
    found = issue(hass, entry, key)
    assert found is not None
    assert found.is_fixable is True
    return entry, f"{key}:{entry.entry_id}"


async def test_one_click_updates_the_app_through_the_supervisor(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor()

    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        assert flow["type"] == "form"
        assert flow["step_id"] == "confirm"
        assert flow["description_placeholders"]["addon_version"] == PREVIOUS_FEATURE
        assert flow["description_placeholders"]["integration_version"] == MANIFEST_VERSION
        supervisor.store.update_addon.assert_not_called()
        result = await confirm_fix(hass, client, flow)

    assert result["type"] == "create_entry"
    supervisor.store.reload.assert_awaited_once()
    supervisor.store.update_addon.assert_awaited_once_with(APP_SLUG)
    assert issue(hass, entry, "app_update_needed") is None


async def test_an_app_too_old_for_the_integration_offers_the_same_one_click_update(
    hass, aioclient_mock, frozen_now, hass_client
):
    _, issue_id = await app_behind(hass, aioclient_mock, version="2609.1.0", key="addon_too_old")
    supervisor = app_supervisor()

    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        assert flow["description_placeholders"]["required_version"]
        result = await confirm_fix(hass, client, flow)

    assert result["type"] == "create_entry"
    supervisor.store.update_addon.assert_awaited_once_with(APP_SLUG)


async def test_the_app_update_picks_the_app_whose_host_the_entry_uses(hass):
    two = app_supervisor(addons=[installed("local_ranzenpost"), installed(APP_SLUG), installed("core_mosquitto")])
    assert (await entry_addon(two, "abc123-ranzenpost")).slug == APP_SLUG
    assert (await entry_addon(two, "local-ranzenpost")).slug == "local_ranzenpost"
    assert await entry_addon(two, "192.168.1.5") is None
    one = app_supervisor(addons=[installed("local_ranzenpost"), installed("core_mosquitto")])
    assert (await entry_addon(one, "192.168.1.5")).slug == "local_ranzenpost"
    assert await entry_addon(app_supervisor(addons=[]), "abc123-ranzenpost") is None


async def test_the_app_update_stops_without_a_supervisor(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await app_behind(hass, aioclient_mock)

    _, flow = await start_fix(hass, hass_client, issue_id)

    assert flow["type"] == "abort"
    assert flow["reason"] == "no_supervisor"
    assert issue(hass, entry, "app_update_needed") is not None


async def test_the_app_update_stops_when_no_ranzenpost_app_is_installed(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor(addons=[installed("core_mosquitto")])

    with on_supervisor(hass, supervisor):
        _, flow = await start_fix(hass, hass_client, issue_id)

    assert flow["type"] == "abort"
    assert flow["reason"] == "no_addon"
    supervisor.store.update_addon.assert_not_called()
    assert issue(hass, entry, "app_update_needed") is not None


async def test_the_app_update_says_so_when_the_store_has_no_newer_version(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor(update_available=False)

    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        result = await confirm_fix(hass, client, flow)

    assert result["type"] == "abort"
    assert result["reason"] == "no_newer_version"
    supervisor.store.reload.assert_awaited_once()
    supervisor.store.update_addon.assert_not_called()
    assert issue(hass, entry, "app_update_needed") is not None


async def test_a_failed_app_update_is_never_reported_as_done(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor()
    supervisor.store.update_addon = AsyncMock(side_effect=SupervisorError("pull failed"))

    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        result = await confirm_fix(hass, client, flow)

    assert result["type"] == "abort"
    assert result["reason"] == "update_failed"
    assert issue(hass, entry, "app_update_needed") is not None


async def test_a_supervisor_that_cannot_list_the_apps_ends_the_app_update(hass, aioclient_mock, frozen_now, hass_client):
    _, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor()
    supervisor.addons.list = AsyncMock(side_effect=SupervisorError("offline"))

    with on_supervisor(hass, supervisor):
        _, flow = await start_fix(hass, hass_client, issue_id)

    assert flow["type"] == "abort"
    assert flow["reason"] == "update_failed"


def hacs_entity(hass, unique_id, object_id, state="on", **attributes):
    entry = er.async_get(hass).async_get_or_create("update", "hacs", unique_id, suggested_object_id=object_id)
    hass.states.async_set(entry.entity_id, state, attributes)
    return entry.entity_id


def ranzenpost_hacs_entity(hass, state="on"):
    hacs_entity(
        hass,
        "998877",
        "other_update",
        release_url="https://github.com/someone/other/releases/1.2.0",
        friendly_name="Other update",
    )
    return hacs_entity(
        hass,
        "112233",
        "ranzenpost_update",
        state=state,
        release_url=f"https://github.com/githuber110/ranzenpost/release/{NEXT_FEATURE}",
        friendly_name="Ranzenpost update",
        installed_version=MANIFEST_VERSION,
        latest_version=NEXT_FEATURE,
    )


async def integration_behind(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock, info=info_of(NEXT_FEATURE))
    found = issue(hass, entry, "integration_too_old")
    assert found is not None
    assert found.is_fixable is True
    return entry, f"integration_too_old:{entry.entry_id}"


async def test_one_click_installs_the_integration_through_hacs_and_then_asks_for_the_restart(
    hass, aioclient_mock, frozen_now, hass_client, manifest_on_disk
):
    _, issue_id = await integration_behind(hass, aioclient_mock)
    entity_id = ranzenpost_hacs_entity(hass)
    installs = []

    async def install(call):
        installs.append(call.data["entity_id"])
        await manifest_on_disk(NEXT_FEATURE)

    hass.services.async_register("update", "install", install)

    client, flow = await start_fix(hass, hass_client, issue_id)
    assert flow["step_id"] == "confirm"
    assert flow["description_placeholders"]["addon_version"] == NEXT_FEATURE
    assert installs == []
    result = await confirm_fix(hass, client, flow)
    await settle(hass)

    assert result["type"] == "create_entry"
    assert installs == [entity_id]
    found = restart_issue(hass)
    assert found is not None
    assert found.translation_placeholders["installed_version"] == NEXT_FEATURE


async def test_the_integration_update_finds_the_hacs_entity_by_name_when_hacs_names_no_release(hass):
    assert hacs_update_entity(hass) is None
    named = hacs_entity(hass, "1", "ranzenpost", title="Ranzenpost")
    hacs_entity(hass, "2", "other", title="Other")
    assert hacs_update_entity(hass) == named
    hacs_entity(hass, "3", "ranzenpost_copy", friendly_name="Ranzenpost update")
    assert hacs_update_entity(hass) is None
    pointed = hacs_entity(hass, "4", "pointed", release_url="https://github.com/githuber110/ranzenpost/releases/x")
    hacs_entity(hass, "5", "card", release_url="https://github.com/githuber110/ranzenpost-card/releases/x")
    assert hacs_update_entity(hass) == pointed


async def test_the_integration_update_stops_without_hacs(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await integration_behind(hass, aioclient_mock)
    hacs_entity(hass, "998877", "other_update", release_url="https://github.com/someone/other/releases/1.2.0")

    _, flow = await start_fix(hass, hass_client, issue_id)

    assert flow["type"] == "abort"
    assert flow["reason"] == "no_hacs"
    assert issue(hass, entry, "integration_too_old") is not None


async def test_the_integration_update_says_so_when_hacs_has_no_newer_version(
    hass, aioclient_mock, frozen_now, hass_client
):
    _, issue_id = await integration_behind(hass, aioclient_mock)
    ranzenpost_hacs_entity(hass, state="off")
    installs = async_mock_service(hass, "update", "install")

    _, flow = await start_fix(hass, hass_client, issue_id)

    assert flow["type"] == "abort"
    assert flow["reason"] == "no_newer_version"
    assert installs == []


async def test_a_failed_hacs_install_is_never_reported_as_done(hass, aioclient_mock, frozen_now, hass_client):
    entry, issue_id = await integration_behind(hass, aioclient_mock)
    ranzenpost_hacs_entity(hass)

    async def install(call):
        raise HomeAssistantError("download failed")

    hass.services.async_register("update", "install", install)

    client, flow = await start_fix(hass, hass_client, issue_id)
    result = await confirm_fix(hass, client, flow)

    assert result["type"] == "abort"
    assert result["reason"] == "update_failed"
    assert issue(hass, entry, "integration_too_old") is not None
    assert restart_issue(hass) is None


async def test_closing_the_dialog_does_not_cut_the_running_app_update(hass, aioclient_mock, frozen_now, hass_client):
    _, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor()
    release = asyncio.Event()
    finished = []

    async def slow_update(slug):
        await release.wait()
        finished.append(slug)

    supervisor.store.update_addon = AsyncMock(side_effect=slow_update)
    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        result = await (await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}")).json()
        assert result["type"] == "progress"
        await client.delete(f"/api/repairs/issues/fix/{flow['flow_id']}")
        await hass.async_block_till_done()
        release.set()
        await settle(hass)

    assert finished == [APP_SLUG]


async def test_a_slow_store_reload_does_not_stop_the_app_update(hass, aioclient_mock, frozen_now, hass_client):
    _, issue_id = await app_behind(hass, aioclient_mock)
    supervisor = app_supervisor()
    supervisor.store.reload = AsyncMock(side_effect=SupervisorError("timeout"))

    with on_supervisor(hass, supervisor):
        client, flow = await start_fix(hass, hass_client, issue_id)
        result = await confirm_fix(hass, client, flow)

    assert result["type"] == "create_entry"
    supervisor.store.update_addon.assert_awaited_once_with(APP_SLUG)


async def test_the_version_repair_survives_a_restart_with_its_versions(hass, aioclient_mock, frozen_now):
    entry, _ = await app_behind(hass, aioclient_mock)
    assert issue(hass, entry, "app_update_needed").is_persistent is True
