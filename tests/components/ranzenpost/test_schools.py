from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost import async_remove_config_entry_device
from custom_components.ranzenpost.const import DOMAIN

from . import (
    CHILD_1,
    CHILD_2,
    PORT,
    SCHOOL,
    SECOND_SCHOOL,
    fixture,
    make_entry,
    mock_addon,
    route,
    school_of,
    setup_entry,
    two_schools_info,
)

OTHER_ALEX = f"{SECOND_SCHOOL}:child-1"
OTHER_ROBIN = f"{SECOND_SCHOOL}:child-9"


async def poll(hass, frozen_now):
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_two_schools_get_one_device_each_and_the_children_hang_below_their_school(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())
    registry = dr.async_get(hass)

    first = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    second = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SECOND_SCHOOL}")})
    assert first.name == "Ranzenpost Sample School"
    assert second.name == "Ranzenpost Other School"
    kim = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_2}")})
    robin = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{OTHER_ROBIN}")})
    assert kim.via_device_id == first.id
    assert robin.via_device_id == second.id
    assert robin.name == "Ranzenpost Robin"
    assert len(dr.async_entries_for_config_entry(registry, entry.entry_id)) == 6


async def test_a_shared_first_name_gets_the_school_in_the_entity_id_and_the_device_name(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())
    registry = dr.async_get(hass)

    assert hass.states.get("sensor.ranzenpost_alex_sample_school_unread_letters").state == "2"
    assert hass.states.get("sensor.ranzenpost_alex_other_school_unread_letters").state == "0"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None
    assert hass.states.get("sensor.ranzenpost_kim_unread_letters").state == "0"
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters").state == "0"
    first_alex = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")})
    other_alex = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{OTHER_ALEX}")})
    assert first_alex.name == "Ranzenpost Alex (Sample School)"
    assert other_alex.name == "Ranzenpost Alex (Other School)"
    entities = er.async_get(hass)
    unique = entities.async_get("sensor.ranzenpost_alex_other_school_unread_letters").unique_id
    assert unique == f"{DOMAIN}_{entry.entry_id}_{OTHER_ALEX}_unread_letters"


async def test_school_entities_exist_per_school_and_follow_their_own_status_and_modules(hass, aioclient_mock, frozen_now):
    info = two_schools_info()
    info["schools"][1]["status"] = "error"
    info["schools"][1]["modules"]["conferences"] = False
    entry = await setup_entry(hass, aioclient_mock, info=info)
    entities = er.async_get(hass)

    assert hass.states.get("sensor.ranzenpost_school_sample_school_connection").state == "ok"
    assert hass.states.get("sensor.ranzenpost_school_other_school_connection").state == "error"
    assert hass.states.get("sensor.ranzenpost_school_sample_school_next_conference") is not None
    assert hass.states.get("sensor.ranzenpost_school_other_school_next_conference") is None
    assert hass.states.get("calendar.ranzenpost_school_sample_school_holidays") is not None
    assert hass.states.get("calendar.ranzenpost_school_other_school_holidays") is not None
    holidays = entities.async_get("calendar.ranzenpost_school_other_school_holidays")
    assert holidays.unique_id == f"{DOMAIN}_{entry.entry_id}_school_{SECOND_SCHOOL}_holidays"
    holiday_calls = [
        str(call[1]) for call in aioclient_mock.mock_calls if "kind=holidays" in str(call[1])
    ]
    assert any(f"school={SECOND_SCHOOL}" in call for call in holiday_calls)
    assert any(f"school={SCHOOL}" in call for call in holiday_calls)


async def test_the_modules_of_one_school_do_not_decide_the_entities_of_the_other(hass, aioclient_mock, frozen_now):
    info = two_schools_info()
    info["schools"][1]["modules"]["timetable"] = False
    info["schools"][1]["modules"]["letters"] = False
    await setup_entry(hass, aioclient_mock, info=info)

    assert hass.states.get("sensor.ranzenpost_kim_current_lesson") is not None
    assert hass.states.get("sensor.ranzenpost_robin_current_lesson") is None
    assert hass.states.get("binary_sensor.ranzenpost_robin_school_day_today") is None
    assert hass.states.get("event.ranzenpost_robin_timetable_changed") is None
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters") is None
    assert hass.states.get("sensor.ranzenpost_robin_unread_posts") is not None
    assert hass.states.get("sensor.ranzenpost_kim_unread_letters") is not None


async def test_a_removed_school_reloads_the_entry_and_frees_its_devices(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())
    registry = dr.async_get(hass)
    second = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SECOND_SCHOOL}")})
    robin = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{OTHER_ROBIN}")})
    assert await async_remove_config_entry_device(hass, entry, second) is False
    assert await async_remove_config_entry_device(hass, entry, robin) is False

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    await poll(hass, frozen_now)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters").state == "unavailable"
    assert hass.states.get("sensor.ranzenpost_school_other_school_connection").state == "unavailable"
    assert hass.states.get("sensor.ranzenpost_alex_sample_school_unread_letters").state == "2"
    assert await async_remove_config_entry_device(hass, entry, second) is True
    assert await async_remove_config_entry_device(hass, entry, robin) is True


async def test_an_added_school_reloads_the_entry_and_creates_its_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters") is None

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=two_schools_info())
    await poll(hass, frozen_now)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters").state == "0"
    assert hass.states.get("sensor.ranzenpost_school_other_school_connection").state == "ok"


async def test_the_change_event_fires_only_for_the_child_of_the_named_school(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())
    change = {
        "child_key": OTHER_ALEX,
        "school_id": SECOND_SCHOOL,
        "at": "2026-09-02T09:20:00+02:00",
        "kind": "cancellation",
        "summary": "Sport is cancelled",
        "date": "2026-09-02",
        "period": 5,
        "new": True,
    }
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=two_schools_info(), changes=[change])
    await poll(hass, frozen_now)

    other = hass.states.get("event.ranzenpost_alex_other_school_timetable_changed")
    first = hass.states.get("event.ranzenpost_alex_sample_school_timetable_changed")
    assert other.attributes["event_type"] == "cancellation"
    assert other.attributes["child"] == "Alex Other"
    assert first.attributes["event_type"] is None


async def test_two_addon_hosts_live_side_by_side_as_two_entries(hass, aioclient_mock, frozen_now):
    first = await setup_entry(hass, aioclient_mock)
    other_base = "http://second-host:8099"
    other_info = fixture("info")
    other_info["schools"] = [school_of(SECOND_SCHOOL, "Other School", "other.example", [("child-9", "Robin Other", "1c")])]
    mock_addon(aioclient_mock, info=other_info, base_url=other_base)
    second = make_entry(host="second-host", port=PORT)
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    assert first.state is ConfigEntryState.LOADED
    assert second.state is ConfigEntryState.LOADED
    registry = dr.async_get(hass)
    assert len(dr.async_entries_for_config_entry(registry, first.entry_id)) == 3
    assert len(dr.async_entries_for_config_entry(registry, second.entry_id)) == 2
    assert registry.async_get_device(identifiers={(DOMAIN, f"school:{second.entry_id}:{SECOND_SCHOOL}")}) is not None
    assert hass.states.get("sensor.ranzenpost_robin_unread_letters").state == "0"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"
    entities = er.async_get(hass)
    unique_ids = {entity.unique_id for entity in entities.entities.values() if entity.platform == DOMAIN}
    assert len(unique_ids) == len([entity for entity in entities.entities.values() if entity.platform == DOMAIN])
    assert any(unique.startswith(f"{DOMAIN}_{second.entry_id}_school_") for unique in unique_ids)


async def test_the_diagnostics_list_every_school(hass, aioclient_mock, frozen_now):
    from custom_components.ranzenpost.diagnostics import async_get_config_entry_diagnostics

    entry = await setup_entry(hass, aioclient_mock, info=two_schools_info())
    result = await async_get_config_entry_diagnostics(hass, entry)

    assert set(result["schools"]) == {SCHOOL, SECOND_SCHOOL}
    assert result["schools"][SECOND_SCHOOL]["children"] == [OTHER_ALEX, OTHER_ROBIN]
    assert set(result["states"]) == {CHILD_1, CHILD_2, OTHER_ALEX, OTHER_ROBIN}
    assert "Other School" not in str(result)
