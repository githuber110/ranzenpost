from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import async_capture_events, async_fire_time_changed

from custom_components.ranzenpost import async_remove_config_entry_device
from custom_components.ranzenpost.const import DOMAIN
from custom_components.ranzenpost.coordinator import login_issue_id

from . import CHILD_1, CHILD_2, SCHOOL, fixture, mock_addon, route, setup_entry

CHILD_3 = f"{SCHOOL}:child-3"
LESSONS = "calendar.ranzenpost_alex_lessons"
CONNECTION = "sensor.ranzenpost_school_connection"


def info_with_children(*keys):
    info = fixture("info")
    names = {CHILD_1: "Alex Sample", CHILD_2: "Kim Sample", CHILD_3: "Sam Sample"}
    info["schools"][0]["children"] = [{"key": child, "name": names[child], "class_name": "5b"} for child in keys]
    return info


def state_with_timetable_stamp(stamp):
    state = fixture("state_child_1")
    state["timetable_last_updated"] = stamp
    return state


def lessons_calls(aioclient_mock):
    return [
        call
        for call in aioclient_mock.mock_calls
        if "/api/integration/events" in str(call[1]) and "kind=lessons" in str(call[1]) and f"child={CHILD_1}" in str(call[1])
    ]


async def poll(hass, frozen_now):
    frozen_now.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_a_changed_child_set_reloads_the_entry_and_its_entities(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert hass.states.get("sensor.ranzenpost_sam_unread_letters") is None

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_children(CHILD_1, CHILD_2, CHILD_3))
    aioclient_mock.get(route("state", child=CHILD_3), json=fixture("state_child_2"))
    for kind in ("lessons", "exams", "absences"):
        aioclient_mock.get(route("events", child=CHILD_3, kind=kind), json=fixture(f"events_{kind}"))
    await poll(hass, frozen_now)

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_sam_unread_letters").state == "0"
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"


async def test_a_device_of_a_child_the_school_no_longer_lists_may_be_removed(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    registry = dr.async_get(hass)
    school = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    kim = registry.async_get_device(identifiers={(DOMAIN, f"child:{entry.entry_id}:{CHILD_2}")})

    assert await async_remove_config_entry_device(hass, entry, school) is False
    assert await async_remove_config_entry_device(hass, entry, kim) is False

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_children(CHILD_1))
    await poll(hass, frozen_now)

    assert entry.state is ConfigEntryState.LOADED
    assert await async_remove_config_entry_device(hass, entry, kim) is True
    assert await async_remove_config_entry_device(hass, entry, school) is False


async def test_a_new_timetable_stamp_drops_the_cached_events(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    assert len(lessons_calls(aioclient_mock)) == 1

    await poll(hass, frozen_now)
    assert len(lessons_calls(aioclient_mock)) == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("state", child=CHILD_1), json=state_with_timetable_stamp("2026-09-02T09:10:00+02:00"))
    mock_addon(aioclient_mock)
    await poll(hass, frozen_now)
    assert len(lessons_calls(aioclient_mock)) == 1
    assert hass.states.get(LESSONS).state == "on"

    await poll(hass, frozen_now)
    assert len(lessons_calls(aioclient_mock)) == 1


async def test_a_reload_that_fails_is_tried_again_on_the_next_poll(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_children(CHILD_1, CHILD_2, CHILD_3))
    aioclient_mock.get(route("state", child=CHILD_3), json=fixture("state_child_2"))
    for kind in ("lessons", "exams", "absences"):
        aioclient_mock.get(route("events", child=CHILD_3, kind=kind), json=fixture(f"events_{kind}"))

    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=False)) as refused:
        await poll(hass, frozen_now)
    assert refused.call_count == 1
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_sam_unread_letters") is None

    await poll(hass, frozen_now)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ranzenpost_sam_unread_letters").state == "0"


async def test_the_reload_goes_through_the_scheduler_that_cancels_a_pending_retry(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info_with_children(CHILD_1))

    with patch.object(hass.config_entries, "async_schedule_reload", wraps=hass.config_entries.async_schedule_reload) as scheduled:
        await poll(hass, frozen_now)

    assert scheduled.call_args_list == [((entry.entry_id,),)]
    assert entry.state is ConfigEntryState.LOADED


async def test_a_school_outage_the_addon_absorbed_keeps_the_entities_and_asks_for_nothing(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"
    assert hass.states.get(CONNECTION).state == "ok"

    info = fixture("info")
    info["schools"][0]["status"] = "unreachable"
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info)
    await poll(hass, frozen_now)

    connection = hass.states.get(CONNECTION)
    assert connection.state == "unreachable"
    assert "unreachable" in connection.attributes["options"]
    assert hass.states.get("sensor.ranzenpost_alex_unread_letters").state == "2"
    assert hass.states.get(LESSONS).state != "unavailable"
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    issue_registry = ir.async_get(hass)
    assert [issue for issue in issue_registry.issues if issue[0] == DOMAIN] == []
    assert entry.state is ConfigEntryState.LOADED


async def test_a_failed_login_raises_a_repair_issue_that_clears_on_recovery(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    issue_registry = ir.async_get(hass)
    issue_id = login_issue_id(entry.entry_id, SCHOOL)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None

    info = fixture("info")
    info["schools"][0]["status"] = "auth_failed"
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info)
    await poll(hass, frozen_now)

    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_key == "login_needed"
    assert issue.translation_placeholders == {"school": "Sample School"}

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    await poll(hass, frozen_now)

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_a_school_in_error_raises_no_login_repair_issue_and_no_login_trigger(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    issue_registry = ir.async_get(hass)
    issue_id = login_issue_id(entry.entry_id, SCHOOL)
    events = async_capture_events(hass, "ranzenpost_event")

    async def school_status(status, reason=""):
        info = fixture("info")
        info["schools"][0]["status"] = status
        info["schools"][0]["status_reason"] = reason
        aioclient_mock.clear_requests()
        mock_addon(aioclient_mock, info=info)
        await poll(hass, frozen_now)

    def login_triggers():
        return [event for event in events if event.data.get("type") == "login_needed"]

    await school_status("error")
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    assert not [issue for issue in issue_registry.issues.values() if issue.domain == DOMAIN]
    assert login_triggers() == []

    await school_status("auth_failed", "bad_credentials")
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None
    assert len(login_triggers()) == 1

    await school_status("error")
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    assert len(login_triggers()) == 1


async def test_the_login_repair_issue_names_why_iserv_refused(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    issue_registry = ir.async_get(hass)
    issue_id = login_issue_id(entry.entry_id, SCHOOL)

    for reason, key in (
        ("twofactor_required_setup", "login_twofactor_setup"),
        ("unknown_account", "login_unknown_account"),
        ("default_password_blocked", "login_default_password"),
        ("code_step_failed", "login_code_refused"),
        ("bad_credentials", "login_needed"),
        ("", "login_needed"),
    ):
        info = fixture("info")
        info["schools"][0]["status"] = "auth_failed"
        info["schools"][0]["status_reason"] = reason
        aioclient_mock.clear_requests()
        mock_addon(aioclient_mock, info=info)
        await poll(hass, frozen_now)

        issue = issue_registry.async_get_issue(DOMAIN, issue_id)
        assert issue is not None
        assert issue.translation_key == key
        assert issue.translation_placeholders == {"school": "Sample School"}

    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock)
    await poll(hass, frozen_now)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_the_two_factor_repair_issue_tells_to_finish_the_setup_in_ranzenpost(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    translations = await async_get_translations(hass, "en", "issues", {DOMAIN})
    description = translations[f"component.{DOMAIN}.issues.login_twofactor_setup.description"]
    assert "two-factor" in description
    assert "finish the setup" in description


async def test_the_code_repair_issue_tells_to_set_up_the_school_again(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    translations = await async_get_translations(hass, "en", "issues", {DOMAIN})
    description = translations[f"component.{DOMAIN}.issues.login_code_refused.description"]
    assert "confirmation code" in description
    assert "set up the school from scratch" in description


async def test_an_outage_never_raises_the_login_repair_issue(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    issue_registry = ir.async_get(hass)
    issue_id = login_issue_id(entry.entry_id, SCHOOL)

    info = fixture("info")
    info["schools"][0]["status"] = "unreachable"
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info)
    await poll(hass, frozen_now)

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_removing_the_entry_deletes_its_login_repair_issue(hass, aioclient_mock, frozen_now):
    entry = await setup_entry(hass, aioclient_mock)
    issue_registry = ir.async_get(hass)
    issue_id = login_issue_id(entry.entry_id, SCHOOL)

    info = fixture("info")
    info["schools"][0]["status"] = "auth_failed"
    aioclient_mock.clear_requests()
    mock_addon(aioclient_mock, info=info)
    await poll(hass, frozen_now)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
