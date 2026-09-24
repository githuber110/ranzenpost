from . import SCENARIO_SATURDAY, fixture, setup_entry

ALEX = "ranzenpost_alex"
KIM = "ranzenpost_kim"
SCHOOL = "ranzenpost_school"
HA_ATTRIBUTES = {
    "friendly_name",
    "device_class",
    "icon",
    "options",
    "event_types",
    "event_type",
    "message",
    "all_day",
    "start_time",
    "end_time",
    "location",
    "description",
    "offset_reached",
    "supported_features",
    "attribution",
}
MODULES = {"timetable": True, "letters": True, "pinboard": True, "absences": True, "conferences": True, "messenger": True}


def extra(hass, entity_id):
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state, {key: value for key, value in state.attributes.items() if key not in HA_ATTRIBUTES}


def with_minutes(lesson, minutes_until, minutes_left):
    return dict(lesson, minutes_until=minutes_until, minutes_left=minutes_left)


def event_attributes(event):
    return {
        "summary": event["summary"],
        "start": event["start"],
        "end": event["end"],
        "subject": event["subject"],
        "subject_code": event["subject_code"],
        "name": event["name"],
        "kind": event["kind"],
    }


async def test_every_entity_on_a_school_morning(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)
    state = fixture("state_child_1")
    school = fixture("school")
    maths, english, art = state["now_lesson"], state["changes_today"][0], state["changes_today"][1]

    assert extra(hass, f"sensor.{ALEX}_current_lesson") == ("Maths", with_minutes(maths, 0, 30))
    assert extra(hass, f"sensor.{ALEX}_next_lesson") == ("English", with_minutes(english, 35, 80))
    assert extra(hass, f"sensor.{ALEX}_school_end_today") == ("2026-09-02T11:05:00+00:00", {"school_day": True})
    assert extra(hass, f"sensor.{ALEX}_next_school_day") == (
        "2026-09-03T06:00:00+00:00",
        {
            "date": "2026-09-03",
            "weekday": "thursday",
            "days_until": 1,
            "end": "2026-09-03T12:25:00+02:00",
            "lessons": 5,
            "first_lesson": "Biology",
        },
    )
    assert extra(hass, f"sensor.{ALEX}_changes_today") == (
        "2",
        {"changes": [with_minutes(english, 35, 80), with_minutes(art, 145, 190)]},
    )
    assert extra(hass, f"sensor.{ALEX}_next_exam") == ("Biology", state["next_exam"])
    assert extra(hass, f"sensor.{ALEX}_exams_upcoming") == ("2", {"exams": state["exams_upcoming"]["items"], "days": 30})
    assert extra(hass, f"sensor.{ALEX}_unread_letters") == (
        "2",
        {
            "letters": [
                {"title": "Field trip", "sender": "Mrs Example", "date": "2026-09-01", "child": "Alex"},
                {"title": "Photo day", "sender": "Head Office", "date": "2026-08-28", "child": "Alex"},
            ]
        },
    )
    assert extra(hass, f"sensor.{ALEX}_unread_posts") == (
        "1",
        {"posts": [{"title": "Lost and found", "sender": "Caretaker", "date": None, "child": ""}]},
    )
    assert extra(hass, f"sensor.{ALEX}_open_absences") == (
        "1",
        {
            "absences": [
                {
                    "kind": "sick",
                    "summary": "Sick note",
                    "start": "2026-09-04",
                    "end": "2026-09-04",
                    "status": "pending",
                    "days_until": 2,
                }
            ]
        },
    )
    assert extra(hass, f"sensor.{ALEX}_next_absence") == ("2026-09-04", state["next_absence"])
    assert extra(hass, f"sensor.{ALEX}_timetable_last_updated") == ("2026-09-01T16:30:00+00:00", {"source": "iserv"})
    assert extra(hass, f"binary_sensor.{ALEX}_school_day_today") == ("on", {})
    assert extra(hass, f"binary_sensor.{ALEX}_timetable_changed_today") == ("on", {})
    assert extra(hass, f"calendar.{ALEX}_lessons") == ("on", event_attributes(fixture("events_lessons")[0]))
    assert extra(hass, f"calendar.{ALEX}_exams") == ("off", event_attributes(fixture("events_exams")[0]))
    assert extra(hass, f"calendar.{ALEX}_absences") == ("off", event_attributes(fixture("events_absences")[0]))
    assert extra(hass, f"event.{ALEX}_timetable_changed") == ("unknown", {})
    assert hass.states.get(f"event.{ALEX}_timetable_changed").attributes["event_types"] == [
        "substitution",
        "cancellation",
        "room_change",
        "new_lesson",
    ]

    assert extra(hass, f"calendar.{SCHOOL}_holidays") == ("off", event_attributes(fixture("events_holidays")[0]))
    assert extra(hass, f"sensor.{SCHOOL}_next_holiday") == (
        "Autumn holidays",
        {"start": "2026-10-12", "end": "2026-10-23", "days_until": 40},
    )
    assert extra(hass, f"sensor.{SCHOOL}_next_conference") == (
        "2026-11-04T23:00:00+00:00",
        {
            "date": "2026-11-05",
            "title": "Parent-teacher conference",
            "details": school["next_conference"]["details"],
            "days_until": 64,
        },
    )
    assert extra(hass, f"sensor.{SCHOOL}_connection") == (
        "ok",
        {
            "last_poll": "2026-09-02T09:00:00+02:00",
            "last_success": "2026-09-02T09:00:00+02:00",
            "version": "2609.02.00",
            "modules": MODULES,
            "modules_disabled": [],
            "feed_port_open": True,
            "ingress_path": "/hassio/ingress/ranzenpost",
        },
    )


async def test_a_child_without_data_reads_none_zero_and_empty_lists(hass, aioclient_mock, frozen_now):
    await setup_entry(hass, aioclient_mock)

    assert extra(hass, f"sensor.{KIM}_current_lesson") == ("none", {})
    assert extra(hass, f"sensor.{KIM}_next_lesson") == ("none", {})
    assert extra(hass, f"sensor.{KIM}_school_end_today") == ("unknown", {"school_day": False})
    assert extra(hass, f"sensor.{KIM}_next_school_day") == ("unknown", {})
    assert extra(hass, f"sensor.{KIM}_changes_today") == ("0", {"changes": []})
    assert extra(hass, f"sensor.{KIM}_next_exam") == ("none", {})
    assert extra(hass, f"sensor.{KIM}_exams_upcoming") == ("0", {"exams": [], "days": 30})
    assert extra(hass, f"sensor.{KIM}_unread_letters") == ("0", {"letters": []})
    assert extra(hass, f"sensor.{KIM}_unread_posts") == ("0", {"posts": []})
    assert extra(hass, f"sensor.{KIM}_open_absences") == ("0", {"absences": []})
    assert extra(hass, f"sensor.{KIM}_next_absence") == ("none", {})
    assert extra(hass, f"sensor.{KIM}_timetable_last_updated") == ("unknown", {"source": ""})
    assert extra(hass, f"binary_sensor.{KIM}_school_day_today") == ("off", {})
    assert extra(hass, f"binary_sensor.{KIM}_timetable_changed_today") == ("off", {})


async def test_every_entity_on_a_saturday_night(hass, aioclient_mock, frozen_saturday):
    await setup_entry(hass, aioclient_mock, scenario=SCENARIO_SATURDAY)
    state = fixture("state_child_1", SCENARIO_SATURDAY)
    monday = 2 * 24 * 60 + 4 * 60

    assert extra(hass, f"sensor.{ALEX}_current_lesson") == ("none", {})
    assert extra(hass, f"sensor.{ALEX}_next_lesson") == ("Maths", with_minutes(state["next_lesson"], monday + 10, monday + 55))
    assert extra(hass, f"sensor.{ALEX}_school_end_today") == ("unknown", {"school_day": False})
    assert extra(hass, f"sensor.{ALEX}_next_school_day") == (
        "2026-09-07T06:00:00+00:00",
        {
            "date": "2026-09-07",
            "weekday": "monday",
            "days_until": 2,
            "end": "2026-09-07T12:25:00+02:00",
            "lessons": 5,
            "first_lesson": "Maths",
        },
    )
    assert extra(hass, f"sensor.{ALEX}_changes_today") == ("0", {"changes": []})
    assert extra(hass, f"sensor.{ALEX}_next_exam") == (
        "Biology",
        {
            "date": "2026-09-09",
            "weekday": "wednesday",
            "days_until": 4,
            "period": 2,
            "subject": "Biology",
            "subject_code": "BI",
            "name": "Chapter 3",
            "start": "2026-09-09T08:50:00+02:00",
            "end": "2026-09-09T09:35:00+02:00",
            "teacher": "Dr Leaf",
            "room": "R404",
        },
    )
    assert extra(hass, f"sensor.{ALEX}_exams_upcoming") == ("1", {"exams": [state["next_exam"]], "days": 30})
    assert extra(hass, f"sensor.{ALEX}_unread_letters") == (
        "1",
        {"letters": [{"title": "Field trip", "sender": "Mrs Example", "date": "2026-09-04", "child": "Alex"}]},
    )
    assert extra(hass, f"sensor.{ALEX}_unread_posts") == ("0", {"posts": []})
    assert extra(hass, f"sensor.{ALEX}_open_absences") == ("0", {"absences": []})
    assert extra(hass, f"sensor.{ALEX}_next_absence") == ("none", {})
    assert extra(hass, f"sensor.{ALEX}_timetable_last_updated") == ("2026-09-04T14:05:00+00:00", {"source": "app"})
    assert extra(hass, f"binary_sensor.{ALEX}_school_day_today") == ("off", {})
    assert extra(hass, f"binary_sensor.{ALEX}_timetable_changed_today") == ("off", {})
    assert extra(hass, f"calendar.{ALEX}_lessons") == (
        "off",
        event_attributes(fixture("events_lessons", SCENARIO_SATURDAY)[0]),
    )
    assert extra(hass, f"calendar.{ALEX}_exams") == ("off", event_attributes(fixture("events_exams", SCENARIO_SATURDAY)[0]))
    assert extra(hass, f"calendar.{ALEX}_absences") == ("off", {})
    assert extra(hass, f"event.{ALEX}_timetable_changed") == ("unknown", {})

    assert extra(hass, f"sensor.{SCHOOL}_next_holiday") == (
        "Autumn holidays",
        {"start": "2026-10-12", "end": "2026-10-23", "days_until": 37},
    )
    assert extra(hass, f"sensor.{SCHOOL}_next_conference")[1]["days_until"] == 61
    assert extra(hass, f"sensor.{SCHOOL}_connection") == (
        "ok",
        {
            "last_poll": "2026-09-05T03:49:00+02:00",
            "last_success": "2026-09-05T03:49:00+02:00",
            "version": "2609.02.00",
            "modules": MODULES,
            "modules_disabled": [],
            "feed_port_open": True,
            "ingress_path": "/hassio/ingress/ranzenpost",
        },
    )


async def test_the_entity_set_is_complete_in_both_scenarios(hass, aioclient_mock, frozen_saturday):
    await setup_entry(hass, aioclient_mock, scenario=SCENARIO_SATURDAY)
    child_keys = {
        "sensor": (
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
        ),
        "binary_sensor": ("school_day_today", "timetable_changed_today"),
        "calendar": ("lessons", "exams", "absences"),
        "event": ("timetable_changed",),
    }
    school_keys = {"sensor": ("next_holiday", "next_conference", "connection"), "calendar": ("holidays",)}
    expected = {
        f"{platform}.{child}_{key}" for child in (ALEX, KIM) for platform, keys in child_keys.items() for key in keys
    } | {f"{platform}.{SCHOOL}_{key}" for platform, keys in school_keys.items() for key in keys}

    assert set(hass.states.async_entity_ids()) == expected
    assert "sensor.ranzenpost_alex_school_start_tomorrow" not in expected
