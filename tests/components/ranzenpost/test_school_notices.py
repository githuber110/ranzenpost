from datetime import timedelta

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.ranzenpost.api import School
from custom_components.ranzenpost.const import DOMAIN
from custom_components.ranzenpost.signals import Signal, school_notice_signals

from . import CHILD_1, CHILD_2, SCHOOL, fixture, mock_addon, route, setup_entry

LETTERS = "sensor.ranzenpost_school_unread_letters"
POSTS = "sensor.ranzenpost_school_unread_posts"
SCHOOL_DEVICE = "ranzenpost_school"
CHILD_SENSOR_KEYS = (
    "current_lesson",
    "next_lesson",
    "school_end_today",
    "next_school_day",
    "changes_today",
    "next_exam",
    "exams_upcoming",
    "unread_letters",
    "unread_posts",
    "open_absences",
    "next_absence",
    "timetable_last_updated",
)


def childless_info(**modules):
    info = fixture("info")
    info["schools"][0]["children"] = []
    info["schools"][0]["modules"].update(modules)
    return info


def school_payload(letters=None, posts=None):
    school = fixture("school")
    if letters is not None:
        school["unread_letters"] = letters
    if posts is not None:
        school["unread_posts"] = posts
    return school


def school_device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})


def ranzenpost_entities(hass):
    return {entry.entity_id: entry for entry in er.async_get(hass).entities.values() if entry.platform == DOMAIN}


async def poll(hass, aioclient_mock, frozen_now, info, school):
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("school", id=SCHOOL), json=school)
    mock_addon(aioclient_mock, info=info)
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_a_school_without_children_gets_its_unread_letters_and_posts(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=childless_info())
    entities = ranzenpost_entities(hass)
    letters = fixture("school")["unread_letters"]

    assert hass.states.get(LETTERS).state == str(letters["count"])
    assert hass.states.get(LETTERS).attributes["letters"] == letters["items"]
    assert hass.states.get(POSTS).state == "1"
    assert hass.states.get(POSTS).attributes["posts"][0]["title"] == "Lost and found"
    assert entities[LETTERS].unique_id == f"ranzenpost_{entry.entry_id}_school_{SCHOOL}_unread_letters"
    assert entities[POSTS].unique_id == f"ranzenpost_{entry.entry_id}_school_{SCHOOL}_unread_posts"
    assert entities[LETTERS].device_id == school_device(hass, entry).id
    assert not [entity_id for entity_id in entities if entity_id.startswith("sensor.ranzenpost_alex")]


async def test_a_school_without_children_says_so_on_its_connection_and_raises_no_repair(
    hass, aioclient_mock, frozen_now
):
    await setup_entry(hass, aioclient_mock, info=childless_info())

    assert hass.states.get(f"sensor.{SCHOOL_DEVICE}_connection").attributes["profiles"] == 0
    assert [issue for (domain, _key), issue in ir.async_get(hass).issues.items() if domain == DOMAIN] == []


async def test_the_school_notice_sensors_follow_the_modules_of_the_school(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info(letters=False))
    entities = ranzenpost_entities(hass)

    assert LETTERS not in entities
    assert POSTS in entities


async def test_an_add_on_without_school_notices_leaves_the_sensors_unknown(hass, aioclient_mock, frozen_now):
    old = fixture("school")
    del old["unread_letters"]
    del old["unread_posts"]
    aioclient_mock.get(route("school", id=SCHOOL), json=old)

    await setup_entry(hass, aioclient_mock, info=childless_info())

    assert hass.states.get(LETTERS).state == "unknown"
    assert hass.states.get(LETTERS).attributes.get("letters") is None


async def test_a_school_device_without_children_offers_the_notice_triggers_of_its_modules(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock, info=childless_info(pinboard=False))

    listed = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, school_device(hass, entry).id)

    assert [item["type"] for item in listed if item["domain"] == DOMAIN] == [
        "school_unreachable",
        "school_reachable",
        "login_needed",
        "school_new_letter",
    ]


async def test_a_new_school_letter_fires_once_on_the_school_device(hass, aioclient_mock, frozen_now):
    info = childless_info()
    entry = await setup_entry(hass, aioclient_mock, info=info)
    school = school_device(hass, entry)
    events = async_capture_events(hass, "ranzenpost_event")
    calls = async_mock_service(hass, "test", "automation")
    trigger = {"platform": "device", "domain": DOMAIN, "device_id": school.id, "type": "school_new_letter"}
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": trigger,
                    "action": {"service": "test.automation", "data_template": {"value": "{{ trigger.event.data.title }}"}},
                }
            ]
        },
    )
    await hass.async_block_till_done()
    letters = fixture("school")["unread_letters"]
    grown = {
        "count": letters["count"] + 1,
        "items": [*letters["items"], {"title": "Trip money", "sender": "Office", "date": "2026-09-02", "child": ""}],
    }

    await poll(hass, aioclient_mock, frozen_now, info, school_payload(letters=grown))
    await poll(hass, aioclient_mock, frozen_now, info, school_payload(letters=grown))

    assert [call.data["value"] for call in calls] == ["Trip money"]
    assert [(event.data["type"], event.data["device_id"], event.data["child_key"]) for event in events] == [
        ("school_new_letter", school.id, "")
    ]
    assert hass.states.get(LETTERS).state == "3"


async def test_upgrading_the_add_on_fires_nothing_for_letters_that_were_already_there(
    hass, aioclient_mock, frozen_now
):
    info = childless_info()
    old = fixture("school")
    del old["unread_letters"]
    del old["unread_posts"]
    aioclient_mock.get(route("school", id=SCHOOL), json=old)
    await setup_entry(hass, aioclient_mock, info=info)
    events = async_capture_events(hass, "ranzenpost_event")

    await poll(hass, aioclient_mock, frozen_now, info, fixture("school"))

    assert events == []
    assert hass.states.get(LETTERS).state == "2"


async def test_children_keep_their_entities_and_the_new_school_letter_does_not_reach_their_triggers(
    hass, aioclient_mock, frozen_now
):
    entry = await setup_entry(hass, aioclient_mock)
    entities = ranzenpost_entities(hass)
    events = async_capture_events(hass, "ranzenpost_event")
    letters = fixture("school")["unread_letters"]
    grown = {"count": 3, "items": [*letters["items"], {"title": "Trip money", "sender": "", "date": "", "child": ""}]}

    for slug, key in (("alex", CHILD_1), ("kim", CHILD_2)):
        for name in CHILD_SENSOR_KEYS:
            entity = entities[f"sensor.ranzenpost_{slug}_{name}"]
            assert entity.unique_id == f"ranzenpost_{entry.entry_id}_{key}_{name}"
    for name in ("next_holiday", "next_free_day", "next_conference", "connection"):
        entity = entities[f"sensor.ranzenpost_school_{name}"]
        assert entity.unique_id == f"ranzenpost_{entry.entry_id}_school_{SCHOOL}_{name}"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"

    await poll(hass, aioclient_mock, frozen_now, fixture("info"), school_payload(letters=grown))

    assert [event.data["type"] for event in events] == ["school_new_letter"]
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


def test_school_notice_signals_need_both_payloads_to_know_the_notices():
    known = School.from_json(fixture("school"))
    unknown = School.from_json({key: value for key, value in fixture("school").items() if not key.startswith("unread")})
    grown_json = fixture("school")
    grown_json["unread_posts"]["items"].append({"title": "Bake sale", "sender": "Club", "date": "", "child": ""})
    grown_json["unread_posts"]["count"] += 1
    grown = School.from_json(grown_json)

    assert school_notice_signals(SCHOOL, unknown, grown) == []
    assert school_notice_signals(SCHOOL, known, known) == []
    assert school_notice_signals(SCHOOL, known, grown) == [
        Signal("school_new_noticeboard_post", SCHOOL, "", {"title": "Bake sale", "sender": "Club", "date": None})
    ]
