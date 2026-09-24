import json
import logging
import pathlib

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.setup import async_setup_component

from custom_components.ranzenpost.card import CARD_URL_PATH, DATA_CARD_REGISTERED, card_resource_url

from . import setup_entry

MANIFEST = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost" / "manifest.json"
VERSION = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
CARD_URL = card_resource_url(VERSION)


def resource_urls(hass):
    return [item["url"] for item in hass.data[LOVELACE_DATA].resources.async_items()]


async def test_the_card_url_carries_the_manifest_version():
    assert CARD_URL == f"/ranzenpost/ranzenpost-card.js?v={VERSION}"
    assert CARD_URL_PATH == "/ranzenpost/ranzenpost-card.js"


async def test_storage_mode_creates_the_resource_once(hass, aioclient_mock, frozen_now, hass_storage):
    assert await async_setup_component(hass, "lovelace", {})
    entry = await setup_entry(hass, aioclient_mock)

    assert resource_urls(hass) == [CARD_URL]
    item = hass.data[LOVELACE_DATA].resources.async_items()[0]
    assert item["type"] == "module"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert resource_urls(hass) == [CARD_URL]


async def test_storage_mode_replaces_a_resource_of_an_older_version(hass, aioclient_mock, frozen_now, hass_storage):
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_load()
    resources.loaded = True
    await resources.async_create_item({"res_type": "module", "url": card_resource_url("2609.01.30")})
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})

    await setup_entry(hass, aioclient_mock)

    assert sorted(resource_urls(hass)) == sorted([CARD_URL, "/local/other-card.js"])


async def test_the_card_file_is_served(hass, aioclient_mock, frozen_now, hass_storage, hass_client):
    assert await async_setup_component(hass, "lovelace", {})
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()

    response = await client.get(CARD_URL_PATH)

    assert response.status == 200
    body = await response.text()
    assert "customElements.define(" in body
    assert '"ranzenpost-card"' in body


async def test_yaml_mode_logs_how_to_add_the_resource(hass, aioclient_mock, frozen_now, caplog):
    assert await async_setup_component(hass, "lovelace", {"lovelace": {"mode": "yaml"}})
    caplog.set_level(logging.INFO)

    entry = await setup_entry(hass, aioclient_mock)

    assert entry.state.value == "loaded"
    hints = [record for record in caplog.records if CARD_URL in record.getMessage()]
    assert len(hints) == 1
    assert "module" in hints[0].getMessage()


async def test_a_failed_card_registration_is_logged_and_retried_on_the_next_setup(
    hass, aioclient_mock, frozen_now, hass_storage, caplog, monkeypatch
):
    assert await async_setup_component(hass, "lovelace", {})
    attempts = []

    async def broken(*args, **kwargs):
        attempts.append(args)
        raise OSError("resources unavailable")

    monkeypatch.setattr(hass.http, "async_register_static_paths", broken)
    entry = await setup_entry(hass, aioclient_mock)

    assert entry.state.value == "loaded"
    assert len(attempts) == 1
    assert DATA_CARD_REGISTERED not in hass.data
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING and "card" in record.getMessage()]
    assert len(warnings) == 1
    assert resource_urls(hass) == []

    monkeypatch.undo()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DATA_CARD_REGISTERED] is True
    assert resource_urls(hass) == [CARD_URL]


async def test_removing_the_entry_deletes_only_the_card_resource(hass, aioclient_mock, frozen_now, hass_storage):
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_load()
    resources.loaded = True
    await resources.async_create_item({"res_type": "module", "url": card_resource_url("2609.01.30")})
    await resources.async_create_item({"res_type": "module", "url": "/local/other-card.js"})
    entry = await setup_entry(hass, aioclient_mock)
    assert CARD_URL in resource_urls(hass)

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert resource_urls(hass) == ["/local/other-card.js"]


async def test_removing_the_entry_survives_yaml_mode_and_a_missing_lovelace(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert await async_setup_component(hass, "lovelace", {"lovelace": {"mode": "yaml"}})
    entry = await setup_entry(hass, aioclient_mock)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries("ranzenpost") == []


async def test_setup_survives_without_lovelace(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)

    assert entry.state.value == "loaded"
    assert LOVELACE_DATA not in hass.data
