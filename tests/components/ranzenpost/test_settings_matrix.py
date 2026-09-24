from copy import deepcopy
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ranzenpost.const import DOMAIN

from . import CHILD_1, CHILD_2, SCHOOL, fixture, mock_addon, route, setup_entry

ALEX = "sensor.ranzenpost_alex"
KIM = "sensor.ranzenpost_kim"
SCHOOL_SENSOR = "sensor.ranzenpost_school"
LESSONS = "calendar.ranzenpost_alex_lessons"
EXAMS_KIM = "calendar.ranzenpost_kim_exams"
ABSENCES_KIM = "calendar.ranzenpost_kim_absences"
HOLIDAYS = "calendar.ranzenpost_school_holidays"
TIMETABLE_CHANGED_EVENT = "event.ranzenpost_alex_timetable_changed"
CHANGED_TODAY_BINARY = "binary_sensor.ranzenpost_alex_timetable_changed_today"
LESSONS_WINDOW = "start=2026-09-02T00:00:00%2B02:00&end=2026-09-03T00:00:00%2B02:00"
EXAMS_WINDOW = "start=2026-09-08T00:00:00%2B02:00&end=2026-09-12T00:00:00%2B02:00"
ABSENCES_WINDOW = "start=2026-09-01T00:00:00%2B02:00&end=2026-09-10T00:00:00%2B02:00"
HOLIDAYS_WINDOW = "start=2026-10-01T00:00:00%2B02:00&end=2026-11-01T00:00:00%2B01:00"

ROWS = (
    "period_time",
    "subject_display_name",
    "subject_code",
    "subject_color",
    "teacher_display_name",
    "holiday_region",
    "language",
    "school_short_name",
    "exam_set_and_removed",
    "lesson_cancelled_and_undone",
    "absence_reported_and_deleted",
    "letter_archived",
    "notification_targets_events",
    "calendar_subscription_rotate_delete",
    "passphrase",
    "theme",
    "child_switch",
    "school_filter_chips",
    "navigation",
    "overview_blocks",
    "modules_disabled",
    "school_phone_numbers",
    "calendar_subscription_components",
    "own_entries_home_assistant",
)

EXEMPT = {
    "language": (
        "api.py parses Info.language onto the Info dataclass but no entity, attribute or device in "
        "custom_components/ranzenpost reads Info.language (grep over custom_components/ranzenpost/*.py "
        "finds no reference outside api.py); the setting never reaches HA."
    ),
    "notification_targets_events": (
        "notification target/event selection lives in the add-on's own configuration; no module under "
        "custom_components/ranzenpost reads or exposes it."
    ),
    "calendar_subscription_rotate_delete": (
        "ICS/remote_calendar subscription management is an add-on web server feature; "
        "custom_components/ranzenpost has no calendar-subscription entity."
    ),
    "passphrase": (
        "the add-on passphrase/token is connection config (const.CONF_TOKEN) used to authenticate requests, "
        "not a value surfaced on any entity."
    ),
    "theme": "there is no theme concept in custom_components/ranzenpost.",
    "child_switch": (
        "selecting which children are tracked is a config_entry option (const.CONF_CHILDREN) that changes "
        "which entities exist at all, not a value propagated onto an existing entity; entity existence for "
        "this option is already covered by test_schools.py and test_coordinator.py, not this "
        "state-propagation matrix."
    ),
    "school_filter_chips": (
        "school/module filter chips are a frontend-only concept (custom_components/ranzenpost/frontend); "
        "no entity carries this setting."
    ),
    "navigation": (
        "bottom bar/rail/More sheet order is a frontend-only concept (custom_components/ranzenpost/frontend "
        "reads no navigation order); no entity or attribute in custom_components/ranzenpost carries it."
    ),
    "overview_blocks": (
        "block order/size on the app overview is a frontend-only concept; the Lovelace card keeps its own "
        "independent blocks list (config.blocks) covered by tests/card/settingsMatrix.test.js, not this "
        "coordinator/entity matrix."
    ),
    "school_phone_numbers": "school phone numbers are not read anywhere in custom_components/ranzenpost.",
    "calendar_subscription_components": (
        "same as calendar_subscription_rotate_delete: no HA entity models ICS subscription components."
    ),
}


async def _tick(hass, frozen_now, seconds=61):
    frozen_now.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _lessons_events():
    return fixture("events_lessons")


def _state_child_1():
    return fixture("state_child_1")


def _state_child_2():
    return fixture("state_child_2")


async def _poll_with(hass, aioclient_mock, frozen_now, **overrides):
    aioclient_mock.clear_requests()
    for (kind, child), payload in overrides.pop("events", {}).items():
        aioclient_mock.get(route("events", child=child, kind=kind), json=payload)
    for child, payload in overrides.pop("states", {}).items():
        aioclient_mock.get(route("state", child=child), json=payload)
    if "school" in overrides:
        aioclient_mock.get(route("school", id=SCHOOL), json=overrides.pop("school"))
    if "events_holidays" in overrides:
        aioclient_mock.get(route("events", kind="holidays", school=SCHOOL), json=overrides.pop("events_holidays"))
    mock_addon(aioclient_mock, info=overrides.pop("info", None), changes=overrides.pop("changes", None))
    await _tick(hass, frozen_now)


async def _run_period_time_next_lesson_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    base = hass.states.get(f"{ALEX}_next_lesson")
    assert base.attributes["start"] == "2026-09-02T09:50:00+02:00"
    assert base.attributes["end"] == "2026-09-02T10:35:00+02:00"

    state = _state_child_1()
    state["next_lesson"]["start"] = "2026-09-02T10:05:00+02:00"
    state["next_lesson"]["end"] = "2026-09-02T10:50:00+02:00"
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: state})

    shifted = hass.states.get(f"{ALEX}_next_lesson")
    assert shifted.attributes["start"] == "2026-09-02T10:05:00+02:00"
    assert shifted.attributes["end"] == "2026-09-02T10:50:00+02:00"
    assert shifted.attributes["minutes_until"] == 48


async def _run_period_time_lessons_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert base[0]["start"] == {"dateTime": "2026-09-02T09:00:00+02:00"}

    events = _lessons_events()
    events[0]["start"] = "2026-09-02T09:20:00+02:00"
    events[0]["end"] = "2026-09-02T10:05:00+02:00"
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=events)
    mock_addon(aioclient_mock)

    frozen_now.tick(timedelta(minutes=6))
    shifted = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert shifted[0]["start"] == {"dateTime": "2026-09-02T09:20:00+02:00"}
    assert shifted[0]["end"] == {"dateTime": "2026-09-02T10:05:00+02:00"}


async def _run_subject_display_name_current_lesson_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(f"{ALEX}_current_lesson").state == "Maths"

    state = _state_child_1()
    state["now_lesson"]["subject"] = "Mathematics"
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: state})

    assert hass.states.get(f"{ALEX}_current_lesson").state == "Mathematics"


async def _run_subject_display_name_lessons_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert base[0]["summary"] == "Maths"

    events = _lessons_events()
    events[0]["summary"] = "Mathematics"
    events[0]["subject"] = "Mathematics"
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=events)
    mock_addon(aioclient_mock)

    frozen_now.tick(timedelta(minutes=6))
    changed = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert changed[0]["summary"] == "Mathematics"
    assert changed[0]["subject"] == "Mathematics"


async def _run_subject_code_current_lesson_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(f"{ALEX}_current_lesson").attributes["subject_code"] == "MA"

    state = _state_child_1()
    state["now_lesson"]["subject_code"] = "MTH"
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: state})

    assert hass.states.get(f"{ALEX}_current_lesson").attributes["subject_code"] == "MTH"


async def _run_subject_code_lessons_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert base[0]["subject_code"] == "MA"

    events = _lessons_events()
    events[0]["subject_code"] = "MTH"
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=events)
    mock_addon(aioclient_mock)

    frozen_now.tick(timedelta(minutes=6))
    changed = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert changed[0]["subject_code"] == "MTH"


async def _run_subject_color_lessons_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert base[0]["color"] == "#3366cc"

    events = _lessons_events()
    events[0]["color"] = "#112233"
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=events)
    mock_addon(aioclient_mock)

    frozen_now.tick(timedelta(minutes=6))
    changed = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert changed[0]["color"] == "#112233"


async def _run_teacher_display_name_current_lesson_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(f"{ALEX}_current_lesson").attributes["teacher"] == "Mrs Example"

    state = _state_child_1()
    state["now_lesson"]["teacher"] = "Mx Newcomer"
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: state})

    assert hass.states.get(f"{ALEX}_current_lesson").attributes["teacher"] == "Mx Newcomer"


async def _run_holiday_region_next_holiday_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    base = hass.states.get(f"{SCHOOL_SENSOR}_next_holiday")
    assert base.state == "Autumn holidays"
    assert base.attributes["start"] == "2026-10-12"

    school = fixture("school")
    school["next_holiday"] = {"name": "Winter holidays", "start": "2026-12-21", "end": "2027-01-06", "days_until": 110}
    await _poll_with(hass, aioclient_mock, frozen_now, school=school)

    changed = hass.states.get(f"{SCHOOL_SENSOR}_next_holiday")
    assert changed.state == "Winter holidays"
    assert changed.attributes["start"] == "2026-12-21"
    assert changed.attributes["end"] == "2027-01-06"
    assert changed.attributes["days_until"] == 110


async def _run_holiday_region_holidays_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{HOLIDAYS}?{HOLIDAYS_WINDOW}")).json()
    assert base[0]["summary"] == "Autumn holidays"

    events = fixture("events_holidays")
    events[0]["summary"] = "Autumn break"
    events[0]["start"] = "2026-10-19"
    events[0]["end"] = "2026-10-31"
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", kind="holidays", school=SCHOOL), json=events)
    mock_addon(aioclient_mock)

    frozen_now.tick(timedelta(minutes=6))
    changed = await (await client.get(f"/api/calendars/{HOLIDAYS}?{HOLIDAYS_WINDOW}")).json()
    assert changed[0]["summary"] == "Autumn break"
    assert changed[0]["start"] == {"date": "2026-10-19"}


async def _run_school_short_name_device_name(hass, aioclient_mock, frozen_now, hass_client):
    entry = await setup_entry(hass, aioclient_mock)
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert device is not None
    assert device.name == "Ranzenpost Sample School"

    info = fixture("info")
    info["schools"][0]["name"] = "Renamed School"
    await _poll_with(hass, aioclient_mock, frozen_now, info=info)

    device = registry.async_get_device(identifiers={(DOMAIN, f"school:{entry.entry_id}:{SCHOOL}")})
    assert device.name == "Ranzenpost Renamed School"


def _exam_payload():
    return {
        "date": "2026-09-10",
        "weekday": "thursday",
        "days_until": 8,
        "period": 2,
        "subject": "Chemistry",
        "subject_code": "CH",
        "name": "Unit test",
        "start": "2026-09-10T09:50:00+02:00",
        "end": "2026-09-10T10:35:00+02:00",
        "teacher": "Dr Flask",
        "room": "R110",
    }


def _exam_event():
    return {
        "uid": "exam-20260910-p2@sample",
        "summary": "Exam: Chemistry",
        "description": "Unit test",
        "location": "R110",
        "start": "2026-09-10T09:50:00+02:00",
        "end": "2026-09-10T10:35:00+02:00",
        "all_day": False,
        "cancelled": False,
        "color": "#cc3333",
        "subject_code": "CH",
        "subject": "Chemistry",
        "name": "Unit test",
        "kind": "",
    }


async def _set_kim_baseline(hass, aioclient_mock, frozen_now):
    await _poll_with(
        hass,
        aioclient_mock,
        frozen_now,
        states={CHILD_2: _state_child_2()},
        events={("exams", CHILD_2): []},
    )


async def _run_exam_set_and_removed_next_exam_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_next_exam").state == "none"

    set_state = _state_child_2()
    exam = _exam_payload()
    set_state["next_exam"] = exam
    set_state["exams_upcoming"] = {"count": 1, "items": [exam], "days": 30}
    await _poll_with(
        hass, aioclient_mock, frozen_now, states={CHILD_2: set_state}, events={("exams", CHILD_2): [_exam_event()]}
    )
    assert hass.states.get(f"{KIM}_next_exam").state == "Chemistry"

    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_next_exam").state == "none"


async def _run_exam_set_and_removed_exams_upcoming_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_exams_upcoming").state == "0"

    set_state = _state_child_2()
    exam = _exam_payload()
    set_state["next_exam"] = exam
    set_state["exams_upcoming"] = {"count": 1, "items": [exam], "days": 30}
    await _poll_with(
        hass, aioclient_mock, frozen_now, states={CHILD_2: set_state}, events={("exams", CHILD_2): [_exam_event()]}
    )
    assert hass.states.get(f"{KIM}_exams_upcoming").state == "1"

    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_exams_upcoming").state == "0"


async def _run_exam_set_and_removed_exams_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{EXAMS_KIM}?{EXAMS_WINDOW}")).json()
    assert base == []

    set_state = _state_child_2()
    exam = _exam_payload()
    set_state["next_exam"] = exam
    set_state["exams_upcoming"] = {"count": 1, "items": [exam], "days": 30}
    await _poll_with(
        hass, aioclient_mock, frozen_now, states={CHILD_2: set_state}, events={("exams", CHILD_2): [_exam_event()]}
    )
    frozen_now.tick(timedelta(minutes=6))
    appeared = await (await client.get(f"/api/calendars/{EXAMS_KIM}?{EXAMS_WINDOW}")).json()
    assert [event["summary"] for event in appeared] == ["Exam: Chemistry"]

    await _set_kim_baseline(hass, aioclient_mock, frozen_now)
    frozen_now.tick(timedelta(minutes=6))
    gone = await (await client.get(f"/api/calendars/{EXAMS_KIM}?{EXAMS_WINDOW}")).json()
    assert gone == []


def _no_changes_state():
    state = _state_child_1()
    state["changes_today"] = []
    state["timetable_changed_today"] = False
    return state


def _cancelled_state():
    state = _no_changes_state()
    now_lesson = deepcopy(state["now_lesson"])
    now_lesson["cancelled"] = True
    now_lesson["kind"] = "cancellation"
    state["now_lesson"] = now_lesson
    state["changes_today"] = [deepcopy(now_lesson)]
    state["timetable_changed_today"] = True
    return state


async def _run_lesson_cancelled_and_undone_current_lesson_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(f"{ALEX}_current_lesson").attributes["cancelled"] is False

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _cancelled_state()})
    assert hass.states.get(f"{ALEX}_current_lesson").attributes["cancelled"] is True

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(f"{ALEX}_current_lesson").attributes["cancelled"] is False


async def _run_lesson_cancelled_and_undone_changes_today_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(f"{ALEX}_changes_today").state == "0"

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _cancelled_state()})
    assert hass.states.get(f"{ALEX}_changes_today").state == "1"

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(f"{ALEX}_changes_today").state == "0"


async def _run_lesson_cancelled_and_undone_changed_today_binary_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(CHANGED_TODAY_BINARY).state == "off"

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _cancelled_state()})
    assert hass.states.get(CHANGED_TODAY_BINARY).state == "on"

    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: _no_changes_state()})
    assert hass.states.get(CHANGED_TODAY_BINARY).state == "off"


async def _run_lesson_cancelled_and_undone_lessons_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert base[0]["cancelled"] is False

    events = _lessons_events()
    events[0]["cancelled"] = True
    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=events)
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(minutes=6))
    cancelled = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert cancelled[0]["cancelled"] is True

    aioclient_mock.clear_requests()
    aioclient_mock.get(route("events", child=CHILD_1, kind="lessons"), json=_lessons_events())
    mock_addon(aioclient_mock)
    frozen_now.tick(timedelta(minutes=6))
    undone = await (await client.get(f"/api/calendars/{LESSONS}?{LESSONS_WINDOW}")).json()
    assert undone[0]["cancelled"] is False


async def _run_lesson_cancelled_and_undone_timetable_changed_event(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    assert hass.states.get(TIMETABLE_CHANGED_EVENT).state == "unknown"

    fresh_cancellation = {
        "child_key": CHILD_1,
        "school_id": SCHOOL,
        "at": "2026-09-02T09:20:00+02:00",
        "kind": "cancellation",
        "summary": "Sport is cancelled",
        "date": "2026-09-03",
        "period": 5,
        "new": True,
    }
    await _poll_with(hass, aioclient_mock, frozen_now, changes=[fresh_cancellation, *fixture("changes")])
    fired = hass.states.get(TIMETABLE_CHANGED_EVENT)
    assert fired.state != "unknown"
    assert fired.attributes["event_type"] == "cancellation"
    assert fired.attributes["summary"] == "Sport is cancelled"

    await _poll_with(
        hass, aioclient_mock, frozen_now, changes=[dict(fresh_cancellation, new=False), *fixture("changes")]
    )
    assert hass.states.get(TIMETABLE_CHANGED_EVENT).state == fired.state


def _absence_payload():
    return {"kind": "sick", "summary": "Fever", "start": "2026-09-09", "end": "2026-09-11", "status": "pending"}


def _absence_event():
    return {
        "uid": "absence-20260909@sample",
        "summary": "Fever",
        "description": "Reported by a parent",
        "location": "",
        "start": "2026-09-09",
        "end": "2026-09-12",
        "all_day": True,
        "cancelled": False,
        "color": "",
        "subject_code": "",
        "subject": "",
        "name": "",
        "kind": "sick",
    }


async def _set_kim_absences_baseline(hass, aioclient_mock, frozen_now):
    await _poll_with(
        hass, aioclient_mock, frozen_now, states={CHILD_2: _state_child_2()}, events={("absences", CHILD_2): []}
    )


async def _run_absence_reported_and_deleted_open_absences_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _set_kim_absences_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_open_absences").state == "0"
    assert hass.states.get(f"{KIM}_open_absences").attributes["absences"] == []

    reported_state = _state_child_2()
    reported_state["open_absences"] = {"count": 1, "items": [_absence_payload()]}
    await _poll_with(
        hass,
        aioclient_mock,
        frozen_now,
        states={CHILD_2: reported_state},
        events={("absences", CHILD_2): [_absence_event()]},
    )
    reported = hass.states.get(f"{KIM}_open_absences")
    assert reported.state == "1"
    assert reported.attributes["absences"][0]["summary"] == "Fever"

    await _set_kim_absences_baseline(hass, aioclient_mock, frozen_now)
    assert hass.states.get(f"{KIM}_open_absences").state == "0"


async def _run_absence_reported_and_deleted_absences_calendar(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    await _set_kim_absences_baseline(hass, aioclient_mock, frozen_now)
    client = await hass_client()
    base = await (await client.get(f"/api/calendars/{ABSENCES_KIM}?{ABSENCES_WINDOW}")).json()
    assert base == []

    reported_state = _state_child_2()
    reported_state["open_absences"] = {"count": 1, "items": [_absence_payload()]}
    await _poll_with(
        hass,
        aioclient_mock,
        frozen_now,
        states={CHILD_2: reported_state},
        events={("absences", CHILD_2): [_absence_event()]},
    )
    frozen_now.tick(timedelta(minutes=6))
    appeared = await (await client.get(f"/api/calendars/{ABSENCES_KIM}?{ABSENCES_WINDOW}")).json()
    assert [event["summary"] for event in appeared] == ["Fever"]

    await _set_kim_absences_baseline(hass, aioclient_mock, frozen_now)
    frozen_now.tick(timedelta(minutes=6))
    gone = await (await client.get(f"/api/calendars/{ABSENCES_KIM}?{ABSENCES_WINDOW}")).json()
    assert gone == []


async def _run_letter_archived_unread_letters_sensor(hass, aioclient_mock, frozen_now, hass_client):
    await setup_entry(hass, aioclient_mock)
    base = hass.states.get(f"{ALEX}_unread_letters")
    assert base.state == "2"
    assert len(base.attributes["letters"]) == 2

    state = _state_child_1()
    state["unread_letters"] = {"count": 1, "items": [state["unread_letters"]["items"][1]]}
    await _poll_with(hass, aioclient_mock, frozen_now, states={CHILD_1: state})

    archived = hass.states.get(f"{ALEX}_unread_letters")
    assert archived.state == "1"
    assert archived.attributes["letters"] == [
        {"title": "Photo day", "sender": "Head Office", "date": "2026-08-28", "child": "Alex"}
    ]


def _ranzenpost_entities(hass):
    registry = er.async_get(hass)
    return sorted(entry.entity_id for entry in registry.entities.values() if entry.platform == DOMAIN)


async def _run_modules_disabled_entity_removed(hass, aioclient_mock, frozen_now, hass_client):
    entry = await setup_entry(hass, aioclient_mock)
    assert "sensor.ranzenpost_alex_unread_letters" in _ranzenpost_entities(hass)

    disabled_info = fixture("info")
    disabled_info["schools"][0]["disabled"] = {"letters": True}
    await _poll_with(hass, aioclient_mock, frozen_now, info=disabled_info)

    assert entry.state is ConfigEntryState.LOADED
    assert "sensor.ranzenpost_alex_unread_letters" not in _ranzenpost_entities(hass)
    assert "sensor.ranzenpost_alex_unread_posts" in _ranzenpost_entities(hass)


async def _run_own_entries_home_assistant_calendar(hass, aioclient_mock, frozen_now, hass_client):
    entry = await setup_entry(hass, aioclient_mock)
    own = "calendar.ranzenpost_alex_own_entries"
    assert own not in _ranzenpost_entities(hass)

    shared = fixture("info")
    shared["schools"][0]["own_entries"] = True
    await _poll_with(hass, aioclient_mock, frozen_now, info=shared)

    assert entry.state is ConfigEntryState.LOADED
    assert own in _ranzenpost_entities(hass)
    client = await hass_client()
    events = await (await client.get(f"/api/calendars/{own}?{LESSONS_WINDOW}")).json()
    assert [event["summary"] for event in events] == ["Chess club"]


CASES = (
    ("period_time-next_lesson_sensor", _run_period_time_next_lesson_sensor),
    ("period_time-lessons_calendar", _run_period_time_lessons_calendar),
    ("subject_display_name-current_lesson_sensor", _run_subject_display_name_current_lesson_sensor),
    ("subject_display_name-lessons_calendar", _run_subject_display_name_lessons_calendar),
    ("subject_code-current_lesson_sensor", _run_subject_code_current_lesson_sensor),
    ("subject_code-lessons_calendar", _run_subject_code_lessons_calendar),
    ("subject_color-lessons_calendar", _run_subject_color_lessons_calendar),
    ("teacher_display_name-current_lesson_sensor", _run_teacher_display_name_current_lesson_sensor),
    ("holiday_region-next_holiday_sensor", _run_holiday_region_next_holiday_sensor),
    ("holiday_region-holidays_calendar", _run_holiday_region_holidays_calendar),
    ("school_short_name-device_name", _run_school_short_name_device_name),
    ("exam_set_and_removed-next_exam_sensor", _run_exam_set_and_removed_next_exam_sensor),
    ("exam_set_and_removed-exams_upcoming_sensor", _run_exam_set_and_removed_exams_upcoming_sensor),
    ("exam_set_and_removed-exams_calendar", _run_exam_set_and_removed_exams_calendar),
    ("lesson_cancelled_and_undone-current_lesson_sensor", _run_lesson_cancelled_and_undone_current_lesson_sensor),
    ("lesson_cancelled_and_undone-changes_today_sensor", _run_lesson_cancelled_and_undone_changes_today_sensor),
    (
        "lesson_cancelled_and_undone-changed_today_binary_sensor",
        _run_lesson_cancelled_and_undone_changed_today_binary_sensor,
    ),
    ("lesson_cancelled_and_undone-lessons_calendar", _run_lesson_cancelled_and_undone_lessons_calendar),
    (
        "lesson_cancelled_and_undone-timetable_changed_event",
        _run_lesson_cancelled_and_undone_timetable_changed_event,
    ),
    ("absence_reported_and_deleted-open_absences_sensor", _run_absence_reported_and_deleted_open_absences_sensor),
    ("absence_reported_and_deleted-absences_calendar", _run_absence_reported_and_deleted_absences_calendar),
    ("letter_archived-unread_letters_sensor", _run_letter_archived_unread_letters_sensor),
    ("modules_disabled-entity_removed", _run_modules_disabled_entity_removed),
    ("own_entries_home_assistant-own_entries_calendar", _run_own_entries_home_assistant_calendar),
)


@pytest.mark.parametrize("run", [case for _, case in CASES], ids=[case_id for case_id, _ in CASES])
async def test_a_settings_or_action_change_arrives_on_its_ha_surface(hass, aioclient_mock, frozen_now, hass_client, run):
    await run(hass, aioclient_mock, frozen_now, hass_client)


def test_every_row_is_covered_or_exempt():
    covered = {case_id.split("-", 1)[0] for case_id, _ in CASES}
    for row in ROWS:
        assert row in covered or row in EXEMPT, f"row {row!r} is neither parametrised nor exempt"
    for row in EXEMPT:
        assert row in ROWS, f"exempt row {row!r} is not listed in ROWS"
