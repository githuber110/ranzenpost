import json
import pathlib
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.const import CONF_CHILDREN, CONF_SCAN_INTERVAL, DOMAIN, MIN_ADDON_VERSION

from . import CHILD_1, CHILD_2, HOST, PORT, SCHOOL, fixture, make_entry, make_legacy_entry, mock_addon, route, setup_entry

MANIFEST = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost" / "manifest.json"
MANIFEST_VERSION = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def version_issue(hass, entry, key):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}:{entry.entry_id}")


async def test_setup_creates_the_school_and_child_devices(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    registry = dr.async_get(hass)

    assert entry.state is ConfigEntryState.LOADED
    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert registry.async_get_device(identifiers={(DOMAIN, "school:school.example")}) is None
    assert registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}")}) is None
    child = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")})
    other = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_2}")})
    assert school.name == "Ranzenpost Sample School"
    assert school.sw_version == "2609.02.00"
    assert child.name == "Ranzenpost Alex"
    assert child.via_device_id == school.id
    assert other.name == "Ranzenpost Kim"
    assert school.configuration_url == "homeassistant://hassio/ingress/ranzenpost"
    assert child.configuration_url == "homeassistant://hassio/ingress/ranzenpost"
    assert other.configuration_url == "homeassistant://hassio/ingress/ranzenpost"


async def test_devices_get_the_panel_link_once_the_addon_reports_its_ingress_path(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["ingress_path"] = ""
    entry = await setup_entry(hass, aioclient_mock, info=info)
    registry = dr.async_get(hass)
    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    child = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")})
    assert school.configuration_url is None
    assert child.configuration_url is None

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    child = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")})
    assert school.configuration_url == "homeassistant://hassio/ingress/ranzenpost"
    assert child.configuration_url == "homeassistant://hassio/ingress/ranzenpost"


def test_the_panel_url_is_built_only_from_an_absolute_ingress_path():
    from custom_components.ranzenpost.entity import panel_url

    assert panel_url("/hassio/ingress/ranzenpost") == "homeassistant://hassio/ingress/ranzenpost"
    assert panel_url("/hassio/ingress/abc123_ranzenpost") == "homeassistant://hassio/ingress/abc123_ranzenpost"
    assert panel_url("") is None
    assert panel_url("ranzenpost") is None


async def test_setup_moves_a_school_device_keyed_by_the_host_onto_the_school_id(hass, aioclient_mock, frozen_now):
    mock_addon(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    legacy = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "school:school.example")}, name="Ranzenpost Sample School"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert school.id == legacy.id
    assert registry.async_get_device(identifiers={(DOMAIN, "school:school.example")}) is None
    assert len(dr.async_entries_for_config_entry(registry, entry.entry_id)) == 3


async def test_setup_moves_the_single_school_devices_of_the_previous_release_onto_the_new_keys(hass, aioclient_mock, frozen_now):
    mock_addon(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    old_school = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"school:{entry.entry_id}")}, name="Ranzenpost Sample School"
    )
    old_child = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "child:child-1")}, name="Ranzenpost Alex"
    )
    entities = er.async_get(hass)
    old_sensor = entities.async_get_or_create(
        "sensor", DOMAIN, "ranzenpost_child-1_unread_letters", config_entry=entry, suggested_object_id="ranzenpost_alex_unread_letters"
    )
    old_holidays = entities.async_get_or_create(
        "calendar", DOMAIN, "ranzenpost_school_holidays", config_entry=entry, suggested_object_id="ranzenpost_school_holidays"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    child = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")})
    assert school.id == old_school.id
    assert child.id == old_child.id
    assert len(dr.async_entries_for_config_entry(registry, entry.entry_id)) == 3
    assert entities.async_get(old_sensor.entity_id).unique_id == f"{DOMAIN}_{entry.entry_id}_{CHILD_1}_unread_letters"
    assert entities.async_get(old_holidays.entity_id).unique_id == f"{DOMAIN}_{entry.entry_id}_school_{SCHOOL}_holidays"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"
    assert len(hass.states.async_entity_ids("calendar")) == 7


async def test_unload_removes_the_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("sensor.ranzenpost_alex_current_lesson").state == "unavailable"


async def test_setup_retries_when_the_addon_is_unreachable(hass, aioclient_mock):
    aioclient_mock.get(route("info"), exc=OSError("down"))
    entry = make_entry()
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_starts_reauth_when_the_token_is_rejected(hass, aioclient_mock):
    aioclient_mock.get(route("info"), status=401, json={"error": "unauthorized"})
    entry = make_entry()
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_entities_go_unavailable_and_recover_with_the_addon(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), status=500, json={"error": "boom"})
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "unavailable"

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_a_rejected_token_during_polling_starts_reauth(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), status=401, json={"error": "unauthorized"})
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "unavailable"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_options_limit_the_children_and_the_interval(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, options={CONF_CHILDREN: [CHILD_2], CONF_SCAN_INTERVAL: 300})

    assert hass.states.get("sensor.ranzenpost_kim_unread_letters") is not None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None
    state_calls = [call for call in aioclient_mock.mock_calls if str(call[1]).endswith(f"state?child={CHILD_1}")]
    assert state_calls == []

    calls_before = len(aioclient_mock.mock_calls)
    frozen_now.tick(timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) == calls_before

    frozen_now.tick(timedelta(seconds=200))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(aioclient_mock.mock_calls) > calls_before


async def test_an_unconfigured_addon_still_sets_up_the_school_device(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0].update(status="unconfigured", children=[], name="", url_host="")
    info["last_poll"] = None
    mock_addon(aioclient_mock, info=info)
    entry = make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert school is not None
    assert school.name == f"Ranzenpost {SCHOOL}"
    assert hass.states.get("sensor.ranzenpost_school_connection").state == "unconfigured"


async def test_the_school_device_is_renamed_once_its_school_name_becomes_known(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0].update(name="")
    entry = await setup_entry(hass, aioclient_mock, info=info)
    registry = dr.async_get(hass)
    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert school.name == "Ranzenpost school.example"

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert school.name == "Ranzenpost Sample School"


async def test_an_addon_without_any_school_sets_up_without_devices_and_hints_at_the_sidebar(
    hass, aioclient_mock, frozen_now
):
    info = fixture("info")
    info["schools"] = []
    info["last_poll"] = None
    mock_addon(aioclient_mock, info=info)
    entry = make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id) == []
    assert hass.states.async_entity_ids("sensor") == []
    issue = version_issue(hass, entry, "no_school_yet")
    assert issue.is_fixable is False
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.learn_more_url == "/hassio/ingress/ranzenpost"
    assert issue.translation_placeholders is None


async def test_the_no_school_hint_disappears_with_the_first_school(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"] = []
    info["ingress_path"] = ""
    entry = await setup_entry(hass, aioclient_mock, info=info)
    assert version_issue(hass, entry, "no_school_yet").learn_more_url is None

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert version_issue(hass, entry, "no_school_yet") is None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_removing_the_entry_deletes_the_no_school_hint(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"] = []
    entry = await setup_entry(hass, aioclient_mock, info=info)
    assert version_issue(hass, entry, "no_school_yet") is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert version_issue(hass, entry, "no_school_yet") is None


async def test_setup_moves_the_entry_of_the_previous_release_onto_the_host_and_port_unique_id(
    hass, aioclient_mock, frozen_now
):
    mock_addon(aioclient_mock)
    entry = make_legacy_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.unique_id == f"{HOST}:{PORT}"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_the_migration_keeps_the_legacy_unique_id_when_the_new_one_is_already_taken(
    hass, aioclient_mock, frozen_now
):
    mock_addon(aioclient_mock)
    make_entry().add_to_hass(hass)
    entry = make_legacy_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert entry.unique_id == DOMAIN


async def test_children_chosen_by_their_raw_id_before_the_upgrade_still_get_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, options={CONF_CHILDREN: ["child-2"], CONF_SCAN_INTERVAL: 300})

    assert hass.states.get("sensor.ranzenpost_kim_unread_letters") is not None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None
    assert entry.options[CONF_CHILDREN] == [CHILD_2]
    assert entry.options[CONF_SCAN_INTERVAL] == 300


def test_selected_children_match_the_key_or_the_raw_id():
    from custom_components.ranzenpost.api import Info
    from custom_components.ranzenpost.coordinator import selected_children

    info = Info.from_json(fixture("info"))
    assert [child.key for child in selected_children(info, make_entry({CONF_CHILDREN: [CHILD_1]}))] == [CHILD_1]
    assert [child.key for child in selected_children(info, make_entry({CONF_CHILDREN: ["child-2"]}))] == [CHILD_2]
    assert [child.key for child in selected_children(info, make_entry({CONF_CHILDREN: ["nobody"]}))] == []
    assert len(selected_children(info, make_entry({}))) == 2


def test_an_info_answer_without_a_schools_list_is_recognised_as_the_previous_release():
    from custom_components.ranzenpost.api import Info

    assert Info.from_json({"version": "2608.03.00", "language": "de"}).legacy is True
    assert Info.from_json({"version": "2609.02.00", "schools": []}).legacy is False
    assert Info.from_json(fixture("info")).legacy is False


async def test_an_addon_of_the_previous_release_sets_up_with_a_repair_that_asks_for_an_update(
    hass, aioclient_mock, frozen_now, caplog
):
    info = fixture("info")
    del info["schools"]
    info["version"] = "2608.03.00"
    mock_addon(aioclient_mock, info=info)
    entry = make_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_entity_ids("sensor") == []
    issue = version_issue(hass, entry, "addon_too_old")
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.is_fixable is False
    assert issue.translation_placeholders == {
        "addon_version": "2608.03.00",
        "integration_version": MANIFEST_VERSION,
        "required_version": MIN_ADDON_VERSION,
    }
    assert version_issue(hass, entry, "integration_too_old") is None
    assert version_issue(hass, entry, "no_school_yet") is None
    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert [line for line in warnings if "2608.03.00" in line and "update" in line] != []


async def test_the_addon_too_old_repair_clears_once_the_addon_is_updated(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["version"] = "2609.01.30"
    entry = await setup_entry(hass, aioclient_mock, info=info)
    assert version_issue(hass, entry, "addon_too_old") is not None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert version_issue(hass, entry, "addon_too_old") is None


async def test_an_addon_a_public_release_ahead_raises_a_warning_repair_for_the_integration(
    hass, aioclient_mock, frozen_now
):
    info = fixture("info")
    info["version"] = "2701.01.00"
    entry = await setup_entry(hass, aioclient_mock, info=info)

    assert entry.state is ConfigEntryState.LOADED
    issue = version_issue(hass, entry, "integration_too_old")
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["addon_version"] == "2701.01.00"
    assert issue.translation_placeholders["integration_version"] == MANIFEST_VERSION
    assert version_issue(hass, entry, "addon_too_old") is None
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_matching_versions_raise_no_version_repair(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    assert version_issue(hass, entry, "addon_too_old") is None
    assert version_issue(hass, entry, "integration_too_old") is None


async def test_removing_the_entry_deletes_its_version_repair(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["version"] = "2701.01.00"
    entry = await setup_entry(hass, aioclient_mock, info=info)
    assert version_issue(hass, entry, "integration_too_old") is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert version_issue(hass, entry, "integration_too_old") is None
