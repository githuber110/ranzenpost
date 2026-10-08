from datetime import date

import pytest

from app.iserv.school_calendar import (
    CalendarShapeError,
    events_params,
    parse_event,
    parse_events,
    parse_sources,
)

TIMED = {
    "id": "a1",
    "uid": "event-1@school.example",
    "hash": "h1",
    "title": "Parents evening 5a",
    "description": "Room 12, please come on time",
    "category": "Meeting",
    "start": "2026-10-12T19:00:00+02:00",
    "end": "2026-10-12T20:30:00+02:00",
    "allDay": False,
    "calendarId": "/group.parents-5a/calendar",
    "calendarName": "Parents 5a",
    "location": "School hall",
}
ALL_DAY = {
    "uid": "event-2@school.example",
    "title": "Sports day",
    "start": "2026-10-15T00:00:00+02:00",
    "end": "2026-10-16T00:00:00+02:00",
    "allDay": True,
    "calendarName": "School",
}


def test_a_timed_event_keeps_its_times_with_offset_and_its_calendar():
    event = parse_event(TIMED)
    assert event == {
        "uid": "event-1@school.example",
        "title": "Parents evening 5a",
        "start": "2026-10-12T19:00:00+02:00",
        "end": "2026-10-12T20:30:00+02:00",
        "all_day": False,
        "location": "School hall",
        "calendar": "Parents 5a",
        "category": "Meeting",
        "description": "Room 12, please come on time",
    }


def test_an_all_day_event_becomes_dates_with_an_exclusive_end():
    event = parse_event(ALL_DAY)
    assert (event["start"], event["end"], event["all_day"]) == ("2026-10-15", "2026-10-16", True)


@pytest.mark.parametrize("end", [None, "2026-10-15T00:00:00+02:00", "2026-10-15T23:59:59+02:00", "garbage"])
def test_an_all_day_event_lasts_at_least_its_own_day(end):
    event = parse_event(dict(ALL_DAY, end=end))
    assert (event["start"], event["end"]) == ("2026-10-15", "2026-10-16")


def test_a_multi_day_all_day_event_keeps_its_span():
    event = parse_event(dict(ALL_DAY, start="2026-10-19", end="2026-10-24"))
    assert (event["start"], event["end"]) == ("2026-10-19", "2026-10-24")


def test_a_timed_event_without_a_usable_end_ends_at_its_start():
    event = parse_event(dict(TIMED, end="2026-10-12T18:00:00+02:00"))
    assert event["end"] == event["start"]


@pytest.mark.parametrize(
    "item",
    [
        None,
        "text",
        dict(TIMED, title=""),
        dict(TIMED, title=None),
        dict(TIMED, start=None),
        dict(TIMED, start="not a date"),
        dict(TIMED, start=42),
    ],
)
def test_entries_without_a_title_or_a_start_are_left_out(item):
    assert parse_event(item) is None


def test_html_in_a_description_becomes_plain_lines():
    event = parse_event(dict(TIMED, description="<p>Bring <b>shoes</b></p><p>and a drink</p>"))
    assert event["description"] == "Bring\nshoes\nand a drink"


def test_long_texts_are_cut_and_whitespace_is_squeezed():
    event = parse_event(dict(TIMED, title="  A  " + "x" * 500, location="a\n\tb"))
    assert len(event["title"]) == 200
    assert event["title"].startswith("A x")
    assert event["location"] == "a b"


def test_an_event_without_ids_gets_a_stable_fallback_uid():
    item = {key: value for key, value in TIMED.items() if key not in ("id", "uid", "hash")}
    assert parse_event(item)["uid"] == parse_event(dict(item))["uid"]


def test_the_feed_answer_per_calendar_is_flattened_sorted_and_deduplicated():
    payload = {
        "/group.parents-5a/calendar": [TIMED, ALL_DAY],
        "/+public/calendar": [dict(TIMED), dict(TIMED, uid="event-3", title="Concert", start="2026-10-01T18:00:00+02:00")],
    }
    events = parse_events(payload)
    assert [event["title"] for event in events] == ["Concert", "Parents evening 5a", "Sports day"]


def test_the_upcoming_answer_with_an_events_list_is_read_too():
    assert [event["title"] for event in parse_events({"events": [ALL_DAY], "errors": []})] == ["Sports day"]


def test_an_empty_answer_is_an_empty_list():
    assert parse_events({}) == []
    assert parse_events([]) == []


@pytest.mark.parametrize("payload", [None, "text", 3])
def test_an_unknown_shape_is_an_error_and_not_an_empty_calendar(payload):
    with pytest.raises(CalendarShapeError):
        parse_events(payload)


def test_calendar_sources_keep_id_label_type_and_subscription():
    payload = [
        {"label": "Personal", "id": "/f.parent/home", "subscription": False, "color": "#000", "type": "cal"},
        {"label": "Holidays", "id": "holiday", "subscription": False, "type": "plugin"},
        {"label": "no id"},
        "junk",
    ]
    assert parse_sources(payload) == [
        {"id": "/f.parent/home", "label": "Personal", "type": "cal", "subscription": False},
        {"id": "holiday", "label": "Holidays", "type": "plugin", "subscription": False},
    ]
    with pytest.raises(CalendarShapeError):
        parse_sources({"label": "x"})


def test_the_window_is_sent_as_iso_days():
    assert events_params(date(2026, 10, 1), date(2026, 12, 31)) == {"start": "2026-10-01", "end": "2026-12-31"}


def test_an_error_object_is_not_an_empty_calendar():
    with pytest.raises(CalendarShapeError):
        parse_events({"error": "denied"})


def test_a_start_with_offset_and_an_end_without_one_still_reads():
    event = parse_event(dict(TIMED, end="2026-10-12T20:30:00"))
    assert event["end"] == "2026-10-12T20:30:00+02:00"


def test_an_all_day_event_given_in_utc_keeps_its_berlin_date():
    event = parse_event(dict(ALL_DAY, start="2026-10-14T22:00:00Z", end="2026-10-15T22:00:00Z"))
    assert (event["start"], event["end"]) == ("2026-10-15", "2026-10-16")
    winter = parse_event(dict(ALL_DAY, start="2026-12-14T23:00:00Z", end="2026-12-15T23:00:00Z"))
    assert (winter["start"], winter["end"]) == ("2026-12-15", "2026-12-16")


def test_the_personal_calendar_of_the_account_is_not_a_school_event():
    payload = {"/f.parent/home": [dict(TIMED, uid="private", title="Dentist")], "/group.parents-5a/calendar": [TIMED]}
    assert [event["title"] for event in parse_events(payload)] == ["Parents evening 5a"]
    listed = {"events": [dict(TIMED, uid="private", title="Dentist", calendarId="/f.parent/home/"), TIMED], "errors": []}
    assert [event["title"] for event in parse_events(listed)] == ["Parents evening 5a"]
