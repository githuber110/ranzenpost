from . import fixture, setup_entry
from .test_school_notices import poll, ranzenpost_entities


def info_with_mail(mail):
    info = fixture("info")
    for school in info["schools"]:
        school["mail"] = mail
    return info


def mail_entity(hass):
    return next((entity_id for entity_id in ranzenpost_entities(hass) if entity_id.endswith("unread_mail") or "e_mail" in entity_id), None)


async def test_a_school_with_mail_gets_its_unread_mail_count(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock, info=info_with_mail(True))
    entity_id = mail_entity(hass)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "2"
    assert ranzenpost_entities(hass)[entity_id].unique_id.endswith("_unread_mail")


async def test_a_school_without_mail_gets_no_mail_sensor(hass, aioclient_mock):
    await setup_entry(hass, aioclient_mock, info=info_with_mail(False))
    assert mail_entity(hass) is None


async def test_an_unknown_mail_count_is_unknown_and_not_zero(hass, aioclient_mock, frozen_now):
    info = info_with_mail(True)
    await setup_entry(hass, aioclient_mock, info=info)
    school = fixture("school")
    school["unread_mail"] = None
    await poll(hass, aioclient_mock, frozen_now, info, school)
    assert hass.states.get(mail_entity(hass)).state == "unknown"


async def test_mail_appearing_in_the_menu_reloads_and_adds_the_sensor(hass, aioclient_mock, frozen_now):
    from datetime import timedelta

    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    from . import mock_addon

    entry = await setup_entry(hass, aioclient_mock, info=info_with_mail(False))
    assert mail_entity(hass) is None
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_mail(True))
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert mail_entity(hass) is not None
