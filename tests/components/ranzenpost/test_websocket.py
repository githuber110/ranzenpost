from datetime import timedelta

from homeassistant.helpers import device_registry as dr

from custom_components.ranzenpost.const import CONF_CHILDREN, CONF_SCAN_INTERVAL, DOMAIN

from . import CHILD_1, CHILD_2, SCHOOL, fixture, mock_addon, route, setup_entry
from .test_modules import info_with

WS_TYPE = f"{DOMAIN}/own_entries"
WEEK = {"start": "2026-09-01", "end": "2026-09-05"}


def child_device(hass, entry, child_key):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{child_key}")})


def school_device(hass, entry):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})


def own_calls(aioclient_mock):
    return [str(call[1]) for call in aioclient_mock.mock_calls if "kind=own_entries" in str(call[1])]


async def ask(hass_ws_client, device_id, **range_):
    client = await hass_ws_client()
    await client.send_json_auto_id({"type": WS_TYPE, "device_id": device_id, **(range_ or WEEK)})
    return await client.receive_json()


async def test_the_card_reads_clubs_and_appointments_while_the_calendar_setting_is_off(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    assert own_calls(aioclient_mock) == []
    reply = await ask(hass_ws_client, child_device(hass, entry, CHILD_1).id)
    assert reply["success"] is True
    assert [(event["summary"], event["start"], event["end"]) for event in reply["result"]] == [
        ("Chess club", {"dateTime": "2026-09-02T15:00:00+02:00"}, {"dateTime": "2026-09-02T16:00:00+02:00"}),
        ("Dentist", {"dateTime": "2026-09-03T16:00:00+02:00"}, {"dateTime": "2026-09-03T16:30:00+02:00"}),
    ]
    assert reply["result"][0]["uid"] == "own-20260902-e1@sample"
    calls = own_calls(aioclient_mock)
    assert len(calls) == 1
    assert "child-1" in calls[0]
    assert "purpose=card" in calls[0]
    assert "start=2026-09-01" in calls[0] and "end=2026-09-05" in calls[0]
    assert hass.states.get("calendar.ranzenpost_alex_own_entries") is None


async def test_the_card_answer_is_cached_like_the_calendars(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    device_id = child_device(hass, entry, CHILD_1).id
    await ask(hass_ws_client, device_id)
    await ask(hass_ws_client, device_id)
    assert len(own_calls(aioclient_mock)) == 1


async def test_expired_answers_leave_the_cache(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    device_id = child_device(hass, entry, CHILD_1).id
    own = lambda: sorted((key[3].isoformat(), key[4].isoformat()) for key in entry.runtime_data.events._entries if key[2] == "own_entries")
    for day in range(1, 8):
        await ask(hass_ws_client, device_id, start=f"2026-09-0{day}", end=f"2026-09-0{day}")
    assert len(own()) == 7
    frozen_now.tick(timedelta(minutes=6))
    await ask(hass_ws_client, device_id)
    assert own() == [("2026-09-01", "2026-09-05")]


async def test_a_left_over_child_device_and_an_unloaded_entry_are_not_found(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    ghost = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"child:{entry.entry_id}:{SCHOOL}:gone")}
    )
    reply = await ask(hass_ws_client, ghost.id)
    assert reply["success"] is False
    assert reply["error"]["code"] == "not_found"
    device_id = child_device(hass, entry, CHILD_1).id
    assert await hass.config_entries.async_unload(entry.entry_id)
    reply = await ask(hass_ws_client, device_id)
    assert reply["success"] is False
    assert reply["error"]["code"] == "not_found"
    assert own_calls(aioclient_mock) == []


async def test_devices_that_are_no_selected_child_are_not_found(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock, options={CONF_CHILDREN: [CHILD_2], CONF_SCAN_INTERVAL: 300})
    assert child_device(hass, entry, CHILD_1) is None
    for device_id in (school_device(hass, entry).id, "no-such-device"):
        reply = await ask(hass_ws_client, device_id)
        assert reply["success"] is False
        assert reply["error"]["code"] == "not_found"
    assert own_calls(aioclient_mock) == []


async def test_a_range_backwards_or_over_a_month_is_refused(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    device_id = child_device(hass, entry, CHILD_1).id
    for start, end in (("2026-09-05", "2026-09-01"), ("2026-09-01", "2026-10-03")):
        reply = await ask(hass_ws_client, device_id, start=start, end=end)
        assert reply["success"] is False
        assert reply["error"]["code"] == "bad_range"
    reply = await ask(hass_ws_client, device_id, start="2026-09-01", end="2026-10-02")
    assert reply["success"] is True
    assert own_calls(aioclient_mock) and all("purpose=card" in call for call in own_calls(aioclient_mock))


async def test_without_the_timetable_module_the_card_gets_nothing_and_asks_nobody(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock, info=info_with(timetable=False))
    reply = await ask(hass_ws_client, child_device(hass, entry, CHILD_1).id)
    assert reply["success"] is True
    assert reply["result"] == []
    assert own_calls(aioclient_mock) == []


async def test_an_unreachable_addon_is_an_error_and_not_an_empty_day(hass, aioclient_mock, frozen_now, hass_ws_client):
    entry = await setup_entry(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="own_entries", purpose="card"), status=500)
    mock_addon(aioclient_mock, info=fixture("info"))
    reply = await ask(hass_ws_client, child_device(hass, entry, CHILD_1).id)
    assert reply["success"] is False
    assert reply["error"]["code"] == "unavailable"
    assert "addon-host" not in reply["error"]["message"]
