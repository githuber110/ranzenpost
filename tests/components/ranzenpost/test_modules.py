import json
import pathlib
import re
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.const import CONNECTION_STATES, DOMAIN

from . import CHILD_1, fixture, make_entry, mock_addon

INTEGRATION = pathlib.Path(__file__).resolve().parents[3] / "custom_components" / "ranzenpost"
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
ALL_MODULES = ("timetable", "letters", "pinboard", "absences", "conferences", "messenger")


def info_with(**flags):
    info = fixture("info")
    info["schools"][0]["modules"] = {name: flags.get(name, True) for name in ALL_MODULES}
    return info


def state_without(*fields):
    state = fixture("state_child_1")
    for field in fields:
        state.pop(field, None)
    return state


def ranzenpost_entities(hass):
    registry = er.async_get(hass)
    return sorted(entry.entity_id for entry in registry.entities.values() if entry.platform == DOMAIN)


async def setup_with(hass, aioclient_mock, info, states=None):
    mock_addon(aioclient_mock, info=info)
    if states is not None:
        aioclient_mock.clear_requests()
        mock_addon(aioclient_mock, info=info)
        for child, state in states.items():
            aioclient_mock.get(f"http://addon-host:8099/api/integration/state?child={child}", json=state)
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_every_module_creates_every_entity(hass, aioclient_mock, frozen_now):
    await setup_with(hass, aioclient_mock, info_with())
    entities = ranzenpost_entities(hass)
    assert "calendar.ranzenpost_alex_lessons" in entities
    assert "calendar.ranzenpost_alex_exams" in entities
    assert "calendar.ranzenpost_alex_absences" in entities
    assert "sensor.ranzenpost_alex_unread_letters" in entities
    assert "sensor.ranzenpost_alex_unread_posts" in entities
    assert "sensor.ranzenpost_alex_open_absences" in entities
    assert "sensor.ranzenpost_alex_next_absence" in entities
    assert "sensor.ranzenpost_school_next_conference" in entities
    assert "event.ranzenpost_alex_timetable_changed" in entities


async def test_a_reduced_subset_creates_only_the_entities_of_its_modules(hass, aioclient_mock, frozen_now):
    await setup_with(hass, aioclient_mock, info_with(letters=False, absences=False, conferences=False))
    entities = ranzenpost_entities(hass)
    assert "sensor.ranzenpost_alex_unread_letters" not in entities
    assert "sensor.ranzenpost_alex_open_absences" not in entities
    assert "sensor.ranzenpost_alex_next_absence" not in entities
    assert "calendar.ranzenpost_alex_absences" not in entities
    assert "sensor.ranzenpost_school_next_conference" not in entities
    assert "sensor.ranzenpost_alex_unread_posts" in entities
    assert "calendar.ranzenpost_alex_lessons" in entities
    assert "calendar.ranzenpost_alex_exams" in entities
    assert "sensor.ranzenpost_alex_current_lesson" in entities
    assert "binary_sensor.ranzenpost_alex_school_day_today" in entities
    assert "event.ranzenpost_alex_timetable_changed" in entities
    assert "sensor.ranzenpost_school_connection" in entities
    assert "sensor.ranzenpost_school_next_holiday" in entities
    assert "calendar.ranzenpost_school_holidays" in entities


async def test_without_the_timetable_no_lesson_entity_exists(hass, aioclient_mock, frozen_now):
    await setup_with(hass, aioclient_mock, info_with(timetable=False))
    entities = ranzenpost_entities(hass)
    for key in (
        "calendar.ranzenpost_alex_lessons",
        "calendar.ranzenpost_alex_exams",
        "sensor.ranzenpost_alex_current_lesson",
        "sensor.ranzenpost_alex_next_lesson",
        "sensor.ranzenpost_alex_school_end_today",
        "sensor.ranzenpost_alex_next_school_day",
        "sensor.ranzenpost_alex_changes_today",
        "sensor.ranzenpost_alex_next_exam",
        "sensor.ranzenpost_alex_exams_upcoming",
        "sensor.ranzenpost_alex_timetable_last_updated",
        "binary_sensor.ranzenpost_alex_school_day_today",
        "binary_sensor.ranzenpost_alex_timetable_changed_today",
        "event.ranzenpost_alex_timetable_changed",
    ):
        assert key not in entities, key
    assert "sensor.ranzenpost_alex_unread_letters" in entities
    assert "calendar.ranzenpost_alex_absences" in entities
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_the_empty_set_sets_up_with_the_school_device_and_the_connection_sensor(hass, aioclient_mock, frozen_now):
    entry = await setup_with(hass, aioclient_mock, info_with(**{name: False for name in ALL_MODULES}))
    assert entry.state is ConfigEntryState.LOADED
    entities = ranzenpost_entities(hass)
    assert entities == [
        "calendar.ranzenpost_school_holidays",
        "sensor.ranzenpost_school_connection",
        "sensor.ranzenpost_school_next_holiday",
    ]
    assert hass.states.get("sensor.ranzenpost_school_connection").state == "ok"
    devices = dr.async_get(hass)
    assert devices.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:a1b2c3d4")}) is not None
    assert devices.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_1}")}) is None


async def test_the_coordinator_survives_a_state_without_the_fields_of_missing_modules(hass, aioclient_mock, frozen_now):
    info = info_with(letters=False, pinboard=False, absences=False)
    states = {
        CHILD_1: state_without("unread_letters", "unread_posts", "open_absences"),
        "a1b2c3d4:child-2": fixture("state_child_2"),
    }
    entry = await setup_with(hass, aioclient_mock, info, states)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_alex_current_lesson").state == "Maths"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None


async def test_an_info_without_a_module_registry_creates_everything(hass, aioclient_mock, frozen_now):
    info = fixture("info")
    info["schools"][0].pop("modules")
    await setup_with(hass, aioclient_mock, info)
    assert "sensor.ranzenpost_alex_unread_letters" in ranzenpost_entities(hass)
    assert "calendar.ranzenpost_alex_absences" in ranzenpost_entities(hass)


def test_translation_placeholders_match_strings_json_in_both_directions():
    def flatten(node, prefix=""):
        flat = {}
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flat.update(flatten(value, path))
            else:
                flat[path] = str(value)
        return flat

    base = flatten(json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8")))
    for path in sorted((INTEGRATION / "translations").glob("*.json")):
        translated = flatten(json.loads(path.read_text(encoding="utf-8")))
        assert set(translated) == set(base), path.name
        for key, value in translated.items():
            assert set(PLACEHOLDER.findall(value)) == set(PLACEHOLDER.findall(base[key])), f"{path.name}: {key}"


def test_every_connection_state_has_a_translated_name_in_every_language():
    paths = [INTEGRATION / "strings.json", *sorted((INTEGRATION / "translations").glob("*.json"))]
    for path in paths:
        states = json.loads(path.read_text(encoding="utf-8"))["entity"]["sensor"]["connection"]["state"]
        assert set(states) == set(CONNECTION_STATES), path.name
        assert all(value.strip() for value in states.values()), path.name


async def test_a_changed_module_set_reloads_the_entry_and_its_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_with(hass, aioclient_mock, info_with())
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with(letters=False))
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None
    assert hass.states.get("sensor.ranzenpost_alex_unread_posts").state == "1"

    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters") is None


def info_disabled(*names):
    info = fixture("info")
    info["schools"][0]["disabled"] = {name: name in names for name in ALL_MODULES}
    return info


async def test_a_module_the_user_switched_off_creates_no_entities_although_iserv_offers_it(hass, aioclient_mock, frozen_now):
    await setup_with(hass, aioclient_mock, info_disabled("letters", "conferences"))
    entities = ranzenpost_entities(hass)
    assert "sensor.ranzenpost_alex_unread_letters" not in entities
    assert "sensor.ranzenpost_school_next_conference" not in entities
    assert "sensor.ranzenpost_alex_unread_posts" in entities
    assert "calendar.ranzenpost_alex_lessons" in entities
    connection = hass.states.get("sensor.ranzenpost_school_connection")
    assert connection.attributes["modules"]["letters"] is False
    assert connection.attributes["modules"]["pinboard"] is True
    assert connection.attributes["modules_disabled"] == ["conferences", "letters"]
    assert connection.attributes["ingress_path"] == "/hassio/ingress/ranzenpost"


async def test_switching_a_module_off_later_forgets_its_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_with(hass, aioclient_mock, info_with())
    assert "sensor.ranzenpost_alex_unread_letters" in ranzenpost_entities(hass)
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_disabled("letters"))
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert "sensor.ranzenpost_alex_unread_letters" not in ranzenpost_entities(hass)
    assert "sensor.ranzenpost_alex_unread_posts" in ranzenpost_entities(hass)
