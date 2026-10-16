from homeassistant.components.device_automation import DeviceAutomationType
from pytest_homeassistant_custom_component.common import async_capture_events, async_get_device_automations

from custom_components.ranzenpost.api import School
from custom_components.ranzenpost.const import DOMAIN
from custom_components.ranzenpost.signals import school_notice_signals

from . import SCHOOL, fixture, route, setup_entry
from .test_school_notices import childless_info, poll, ranzenpost_entities, school_device

FORUMS = "sensor.ranzenpost_school_unread_forum_posts"


async def test_the_forum_sensor_needs_the_confirmed_forum_module(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info())
    assert FORUMS not in ranzenpost_entities(hass)


async def test_the_forum_sensor_counts_unread_posts_and_lists_the_forums(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=childless_info(forums=True))
    entities = ranzenpost_entities(hass)

    assert hass.states.get(FORUMS).state == "4"
    assert hass.states.get(FORUMS).attributes["forums"] == fixture("school")["unread_forum_posts"]["items"]
    assert entities[FORUMS].unique_id == f"ranzenpost_{entry.entry_id}_school_{SCHOOL}_unread_forum_posts"
    assert entities[FORUMS].device_id == school_device(hass, entry).id


async def test_the_school_device_offers_the_forum_trigger(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=childless_info(pinboard=False, forums=True))

    listed = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, school_device(hass, entry).id)

    assert [item["type"] for item in listed if item["domain"] == DOMAIN][-1] == "school_new_forum_post"


async def test_a_forum_with_new_posts_fires_once_from_the_fresh_record(hass, aioclient_mock, frozen_now):
    info = childless_info(forums=True)
    entry = await setup_entry(hass, aioclient_mock, info=info)
    school = school_device(hass, entry)
    events = async_capture_events(hass, "ranzenpost_event")
    grown = fixture("school")
    fresh = dict(grown["unread_forum_posts"]["items"][0], id="4101:ffff000011112222", text="New topic 02.09.2026 10:00", seen=1_791_000_000)
    grown["unread_forum_posts"]["count"] = 6
    grown["unread_forum_posts"]["fresh"] = [fresh]

    await poll(hass, aioclient_mock, frozen_now, info, grown)
    await poll(hass, aioclient_mock, frozen_now, info, grown)

    assert [(event.data["type"], event.data["device_id"], event.data.get("title")) for event in events] == [
        ("school_new_forum_post", school.id, "School yard"),
    ]
    assert hass.states.get(FORUMS).state == "6"


async def test_an_add_on_without_forum_posts_leaves_the_sensor_unknown(hass, aioclient_mock, frozen_now):
    old = fixture("school")
    del old["unread_forum_posts"]
    aioclient_mock.get(route("school", id=SCHOOL), json=old)
    await setup_entry(hass, aioclient_mock, info=childless_info(forums=True))

    assert hass.states.get(FORUMS).state == "unknown"


def test_forum_signals_follow_only_the_fresh_record():
    before = fixture("school")
    after = fixture("school")
    after["unread_forum_posts"]["count"] = 9
    assert school_notice_signals(SCHOOL, School.from_json(before), School.from_json(after)) == []
    after["unread_forum_posts"]["fresh"] = [dict(after["unread_forum_posts"]["items"][0], seen=5)]
    signals = school_notice_signals(SCHOOL, School.from_json(before), School.from_json(after))
    assert [(signal.type, signal.data["title"]) for signal in signals] == [("school_new_forum_post", "School yard")]


TEXTS = "sensor.ranzenpost_school_texts"


async def test_the_text_sensor_needs_the_confirmed_text_module_and_lists_the_texts(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock, info=childless_info())
    assert TEXTS not in ranzenpost_entities(hass)


async def test_the_text_sensor_counts_the_texts_with_owner_and_date(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock, info=childless_info(texts=True))
    entities = ranzenpost_entities(hass)

    assert hass.states.get(TEXTS).state == "2"
    assert hass.states.get(TEXTS).attributes["texts"][0]["sender"] == "Class teacher"
    assert entities[TEXTS].unique_id == f"ranzenpost_{entry.entry_id}_school_{SCHOOL}_texts"
    listed = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, school_device(hass, entry).id)
    assert [item["type"] for item in listed if item["domain"] == DOMAIN][-1] == "school_new_text"


async def test_a_new_shared_text_fires_once_from_the_fresh_record(hass, aioclient_mock, frozen_now):
    info = childless_info(texts=True)
    entry = await setup_entry(hass, aioclient_mock, info=info)
    school = school_device(hass, entry)
    events = async_capture_events(hass, "ranzenpost_event")
    grown = fixture("school")
    shared = {"title": "Reading list", "sender": "Library", "date": "2026-09-02", "child": "", "id": "p3"}
    grown["texts"]["items"].append(shared)
    grown["texts"]["count"] = 3
    grown["texts"]["fresh"] = [dict(shared, seen=1_791_000_000)]

    await poll(hass, aioclient_mock, frozen_now, info, grown)
    await poll(hass, aioclient_mock, frozen_now, info, grown)

    assert [(event.data["type"], event.data["device_id"], event.data.get("title")) for event in events] == [
        ("school_new_text", school.id, "Reading list"),
    ]
    assert hass.states.get(TEXTS).state == "3"
