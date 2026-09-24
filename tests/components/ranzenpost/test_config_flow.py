import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiohasupervisor import SupervisorError
from aiohasupervisor.models import AddonState, Discovery
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from custom_components.ranzenpost.const import (
    ADDON_REPOSITORY,
    CONF_CHILDREN,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DOMAIN,
)

from . import (
    CHILD_1,
    CHILD_2,
    ENTRY_DATA,
    HOST,
    NEW_TOKEN,
    PORT,
    TOKEN,
    UNIQUE_ID,
    fixture,
    make_entry,
    make_legacy_entry,
    mock_addon,
    route,
    setup_entry,
    two_schools_info,
)

ADDON_SLUG = "abc123_ranzenpost"
ADDON_NAME = "Ranzenpost (IServ)"
ADDON_HOSTNAME = "abc123-ranzenpost"
FLOW_MODULE = "custom_components.ranzenpost.config_flow"


def discovery_message(token=TOKEN) -> Discovery:
    return Discovery(
        addon=ADDON_SLUG,
        service="ranzenpost",
        uuid=uuid4(),
        config={CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: token},
    )


def service_info(token=TOKEN, slug=ADDON_SLUG) -> HassioServiceInfo:
    return HassioServiceInfo(
        config={CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: token},
        name=ADDON_NAME,
        slug=slug,
        uuid=uuid4().hex,
    )


def supervisor_mock(*, installed: bool, running: bool, discoveries=None) -> MagicMock:
    client = MagicMock()
    client.discovery.list = AsyncMock(side_effect=discoveries if discoveries is not None else [[]] * 20)
    client.store.repositories_list = AsyncMock(return_value=[])
    client.store.add_repository = AsyncMock()
    client.store.reload = AsyncMock()
    addon = MagicMock()
    addon.slug = ADDON_SLUG
    addon.name = ADDON_NAME
    addon.url = ADDON_REPOSITORY
    addon.installed = installed
    client.store.addons_list = AsyncMock(return_value=[addon])
    client.store.install_addon = AsyncMock()
    info = MagicMock()
    info.name = ADDON_NAME
    info.hostname = ADDON_HOSTNAME
    info.state = AddonState.STARTED if running else AddonState.STOPPED
    client.addons.addon_info = AsyncMock(return_value=info)
    client.addons.start_addon = AsyncMock()
    return client


@pytest.fixture
def mock_setup():
    with patch("custom_components.ranzenpost.async_setup_entry", return_value=True) as setup:
        yield setup


@pytest.fixture
def fast_discovery():
    with patch(f"{FLOW_MODULE}.DISCOVERY_POLL_SECONDS", 0), patch(f"{FLOW_MODULE}.DISCOVERY_WAIT_SECONDS", 0):
        yield


def with_hassio(hass, client):
    hass.config.components.add("hassio")
    return patch(f"{FLOW_MODULE}.get_supervisor_client", return_value=client)


async def settled(hass, result):
    while result["type"] is FlowResultType.SHOW_PROGRESS:
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
    return result


async def test_hassio_discovery_creates_the_entry_after_confirmation(hass, aioclient_mock, mock_setup):
    aioclient_mock.get(route("info"), json=fixture("info"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"
    assert result["description_placeholders"] == {"addon": ADDON_NAME}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Ranzenpost ({HOST})"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == UNIQUE_ID
    assert mock_setup.call_count == 1


async def test_hassio_discovery_shows_errors_until_the_addon_answers(hass, aioclient_mock, mock_setup):
    aioclient_mock.get(route("info"), status=401, json={"error": "unauthorized"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), exc=OSError("down"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), json=fixture("info"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_hassio_discovery_ignores_a_foreign_addon(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info(slug="core_mosquitto")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_ranzenpost_addon"


async def test_a_second_discovery_with_a_new_token_updates_and_reloads_the_entry(hass, mock_setup):
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert mock_setup.call_count == 1

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info(token=NEW_TOKEN)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_TOKEN] == NEW_TOKEN
    assert mock_setup.call_count == 2


async def test_a_discovery_with_a_new_token_revives_an_entry_that_failed_with_a_stale_token(
    hass, aioclient_mock, frozen_now
):
    aioclient_mock.get(route("info"), status=401, json={"error": "unauthorized"})
    entry = make_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert len(hass.config_entries.flow.async_progress_by_handler(DOMAIN)) == 1

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info(token=NEW_TOKEN)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_TOKEN] == NEW_TOKEN
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_a_second_discovery_with_the_same_token_leaves_the_entry_alone(hass, mock_setup):
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info()
    )
    await hass.async_block_till_done()

    assert result["reason"] == "already_configured"
    assert mock_setup.call_count == 1


async def test_a_discovery_adopts_the_entry_of_the_previous_release_instead_of_offering_a_duplicate(hass, mock_setup):
    entry = make_legacy_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info(token=NEW_TOKEN)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == UNIQUE_ID
    assert entry.data[CONF_TOKEN] == NEW_TOKEN
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_discovery_from_a_new_host_adopts_the_only_entry_of_the_previous_release(hass, mock_setup):
    entry = make_legacy_entry(host="old-host")
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info()
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == UNIQUE_ID
    assert entry.data[CONF_HOST] == HOST
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_discovery_from_a_new_host_leaves_a_legacy_entry_alone_when_another_entry_exists(
    hass, aioclient_mock, mock_setup
):
    legacy = make_legacy_entry(host="old-host")
    legacy.add_to_hass(hass)
    make_entry(host="second-host").add_to_hass(hass)
    aioclient_mock.get(route("info"), json=fixture("info"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_HASSIO}, data=service_info()
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert legacy.unique_id != UNIQUE_ID
    assert len(hass.config_entries.async_entries(DOMAIN)) == 3


async def test_the_manual_form_recognises_the_entry_of_the_previous_release(hass):
    entry = make_legacy_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == UNIQUE_ID
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_user_flow_without_supervisor_validates_the_manual_form(hass, aioclient_mock, mock_setup):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    aioclient_mock.get(route("info"), exc=OSError("down"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), status=403, json={"error": "forbidden"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), json=fixture("info"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA


async def test_the_created_entry_tells_the_user_to_sign_in_through_the_sidebar(hass, aioclient_mock, mock_setup):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    aioclient_mock.get(route("info"), json=fixture("info"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    translations = await async_get_translations(hass, "en", "config", {DOMAIN})

    assert translations[f"component.{DOMAIN}.config.create_entry.default"] == (
        "Done. Open Ranzenpost in the sidebar and sign in to your school. Devices and entities appear on their own."
    )


async def test_manual_flow_aborts_when_the_same_host_and_port_are_already_configured(hass):
    make_entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_a_second_addon_host_gets_its_own_entry(hass, aioclient_mock, mock_setup):
    make_entry().add_to_hass(hass)
    other = {CONF_HOST: "second-host", CONF_PORT: PORT, CONF_TOKEN: NEW_TOKEN}
    aioclient_mock.get(route("info", "http://second-host:8099"), json=fixture("info"))

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], other)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "second-host:8099"
    assert result["title"] == "Ranzenpost (second-host)"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_user_flow_with_supervisor_uses_an_existing_discovery(hass, aioclient_mock, mock_setup):
    aioclient_mock.get(route("info"), json=fixture("info"))
    client = supervisor_mock(installed=True, running=True, discoveries=[[discovery_message()]])

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "hassio_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    client.store.install_addon.assert_not_called()


async def test_user_flow_installs_starts_and_waits_for_the_addon(hass, aioclient_mock, mock_setup, fast_discovery):
    aioclient_mock.get(route("info"), json=fixture("info"))
    client = supervisor_mock(installed=False, running=False, discoveries=[[], [discovery_message()]])
    gate = asyncio.Event()

    async def slow_install(slug):
        await gate.wait()

    client.store.install_addon = AsyncMock(side_effect=slow_install)

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "install_addon"
        assert result["description_placeholders"] == {"repository": ADDON_REPOSITORY}

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["progress_action"] == "install_addon"
        gate.set()

        result = await settled(hass, result)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "hassio_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    client.store.add_repository.assert_awaited_once()
    assert client.store.add_repository.await_args.args[0].repository == ADDON_REPOSITORY
    client.store.install_addon.assert_awaited_once_with(ADDON_SLUG)
    client.addons.start_addon.assert_awaited_once_with(ADDON_SLUG)


async def test_user_flow_skips_the_repository_when_it_is_already_added(hass, aioclient_mock, mock_setup, fast_discovery):
    aioclient_mock.get(route("info"), json=fixture("info"))
    client = supervisor_mock(installed=False, running=False, discoveries=[[], [discovery_message()]])
    repository = MagicMock()
    repository.source = ADDON_REPOSITORY.upper()
    client.store.repositories_list = AsyncMock(return_value=[repository])

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await settled(hass, await hass.config_entries.flow.async_configure(result["flow_id"], {}))

    assert result["step_id"] == "hassio_confirm"
    client.store.add_repository.assert_not_called()
    client.store.install_addon.assert_awaited_once_with(ADDON_SLUG)


async def test_user_flow_aborts_when_the_install_fails(hass, mock_setup, fast_discovery):
    client = supervisor_mock(installed=False, running=False)
    client.store.install_addon = AsyncMock(side_effect=SupervisorError("no space"))

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await settled(hass, await hass.config_entries.flow.async_configure(result["flow_id"], {}))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "addon_install_failed"
    client.addons.start_addon.assert_not_called()


async def test_user_flow_aborts_when_the_addon_does_not_start(hass, mock_setup, fast_discovery):
    client = supervisor_mock(installed=True, running=False)
    gate = asyncio.Event()

    async def slow_start(slug):
        await gate.wait()
        raise SupervisorError("crash")

    client.addons.start_addon = AsyncMock(side_effect=slow_start)

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["progress_action"] == "start_addon"
        gate.set()
        result = await settled(hass, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "addon_start_failed"
    client.store.install_addon.assert_not_called()


async def test_user_flow_offers_the_manual_form_when_no_discovery_arrives(hass, aioclient_mock, mock_setup, fast_discovery):
    aioclient_mock.get(route("info"), json=fixture("info"))
    client = supervisor_mock(installed=True, running=True)
    gate = asyncio.Event()

    calls = []

    async def slow_list():
        calls.append(True)
        if len(calls) > 1:
            await gate.wait()
        return []

    client.discovery.list = AsyncMock(side_effect=slow_list)

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["progress_action"] == "wait_discovery"
        gate.set()

        result = await settled(hass, result)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "addon_no_discovery"
        assert result["description_placeholders"] == {"addon": ADDON_NAME}
        defaults = {key.schema: key.default() for key in result["data_schema"].schema if key.default is not None}
        assert defaults[CONF_HOST] == ADDON_HOSTNAME
        assert defaults[CONF_PORT] == PORT

        result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(ENTRY_DATA))
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    client.store.install_addon.assert_not_called()
    client.addons.start_addon.assert_not_called()


async def test_user_flow_falls_back_to_manual_when_the_supervisor_fails(hass, mock_setup):
    client = supervisor_mock(installed=True, running=True)
    client.discovery.list = AsyncMock(side_effect=SupervisorError("offline"))

    with with_hassio(hass, client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_reauth_replaces_the_token_after_validation(hass, aioclient_mock, mock_setup):
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"][CONF_HOST] == HOST

    aioclient_mock.get(route("info"), status=401, json={"error": "unauthorized"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: NEW_TOKEN})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("info"), json=fixture("info"))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: NEW_TOKEN})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == NEW_TOKEN
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == f"Bearer {NEW_TOKEN}"
    assert mock_setup.call_count == 2


async def test_options_flow_stores_interval_and_children_and_reloads(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    fields = {key.schema: value for key, value in result["data_schema"].schema.items()}
    options = fields[CONF_CHILDREN].config["options"]
    assert [option["value"] for option in options] == [CHILD_1, CHILD_2]
    assert [option["label"] for option in options] == ["Alex Sample (5b)", "Kim Sample (8a)"]

    with patch("custom_components.ranzenpost.async_setup_entry", return_value=True) as setup:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 45, CONF_CHILDREN: [CHILD_2]}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 45, CONF_CHILDREN: [CHILD_2]}
    assert setup.call_count == 1


async def test_options_flow_names_the_school_next_to_the_first_name_when_there_are_two(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())

    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = {key.schema: value for key, value in result["data_schema"].schema.items()}
    options = fields[CONF_CHILDREN].config["options"]

    assert [option["value"] for option in options] == [CHILD_1, CHILD_2, "b2c3d4e5:child-1", "b2c3d4e5:child-9"]
    assert [option["label"] for option in options] == [
        "Alex (Sample School)",
        "Kim (Sample School)",
        "Alex (Other School)",
        "Robin (Other School)",
    ]


async def test_options_flow_rejects_an_interval_below_the_minimum(hass, aioclient_mock):
    entry = await setup_entry(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(Exception):
        await hass.config_entries.options.async_configure(result["flow_id"], {CONF_SCAN_INTERVAL: 5, CONF_CHILDREN: []})
