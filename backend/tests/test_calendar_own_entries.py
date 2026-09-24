from datetime import date, datetime, timedelta, timezone

from app import feed, subscriptions
from app.subscriptions import COMPONENT_OWN_ENTRIES, COMPONENT_TIMETABLE

CONNECTION_ID = "a1b2c3d4"
CHILD = f"{CONNECTION_ID}:kid"
TODAY = date(2026, 9, 23)
NOW_EPOCH = int(datetime(2026, 9, 23, 6, 0, tzinfo=timezone.utc).timestamp())
MONDAY = date(2026, 9, 21)
BASE = (470, 520, 585, 635, 695, 745, 830, 880)


def clock(minutes):
    return "%02d:%02d" % divmod(minutes, 60)


def german(day):
    return day.strftime("%d.%m.%Y")


def lessons_for(monday, per_day):
    lessons = []
    for index, count in enumerate(per_day):
        day = monday + timedelta(days=index)
        for period in range(1, count + 1):
            start = BASE[period - 1]
            lessons.append({"date": german(day), "day_of_week": index + 1, "period": period, "start_time": clock(start), "end_time": clock(start + 45), "subject_code": "D", "subject_label": "Deutsch", "change_kind": ""})
    return lessons


def snapshot(weeks=1):
    stored = {}
    for offset in range(weeks):
        monday = MONDAY + timedelta(days=7 * offset)
        stored[monday.isoformat()] = {"start_date": monday.isoformat(), "end_date": (monday + timedelta(days=4)).isoformat(), "lessons": lessons_for(monday, [6, 8, 5, 6, 5]), "fetched_at": NOW_EPOCH}
    return {"children": {CHILD: {"weeks": stored, "last_success": NOW_EPOCH}}}


def entry(entry_id, **fields):
    base = {"id": entry_id, "type": "club", "name": "Chess club", "start": "15:30", "duration": 60, "repeat": "weekly", "days": [2], "interval": 1, "date": "", "from": "2026-09-01", "until": "2027-06-30", "holidays": False, "child": "kid"}
    base.update(fields)
    return base


def config(entries):
    return {
        "language": "de",
        "children": [{"child_id": "kid", "name": "Kim Example"}],
        "period_times": {str(n): clock(start) for n, start in enumerate(BASE, 1)},
        "period_grid": {"iserv": {str(n): {"start": clock(start), "end": clock(start + 45)} for n, start in enumerate(BASE, 1)}},
        "own_entries": entries,
    }


def events(entries, components=(COMPONENT_OWN_ENTRIES,), weeks=1, days=None, blocked=False):
    subscription = {"child_key": CHILD, "components": list(components)}
    return [
        event
        for event in feed.build_events(subscription, config(entries), snapshot(weeks), days or {}, blocked, TODAY, NOW_EPOCH)
        if event.kind == COMPONENT_OWN_ENTRIES
    ]


def test_own_entries_reach_the_feed_only_with_their_component():
    entries = [entry("e1")]
    assert events(entries, components=(COMPONENT_TIMETABLE,)) == []
    found = events(entries)
    assert [(event.summary, event.start, event.end) for event in found] == [("Chess club", datetime(2026, 9, 23, 15, 30), datetime(2026, 9, 23, 16, 30))]


def test_pauses_never_reach_the_feed():
    pause = entry("p1", type="pause", name="Lunch", start="13:15", duration=35, repeat="daily", days=[0, 1, 2, 3, 4], child="")
    appointment = entry("a1", type="appointment", name="Parents evening", start="19:00", duration=90, repeat="once", date="2026-09-24", holidays=True)
    assert [event.summary for event in events([pause, appointment])] == ["Parents evening"]


def test_the_feed_stops_where_the_timetable_data_ends():
    daily = entry("d1", repeat="daily", days=[0, 1, 2, 3, 4], start="17:00")
    one_week = events([daily])
    assert max(event.start.date() for event in one_week) == date(2026, 9, 25)
    two_weeks = events([daily], weeks=2)
    assert max(event.start.date() for event in two_weeks) == date(2026, 10, 2)
    assert min(event.start.date() for event in two_weeks) >= feed.lesson_window(TODAY)[0]


def test_a_longer_lesson_in_the_data_shortens_the_entry():
    late = entry("l1", days=[1], start="15:00", duration=60)
    found = events([late])
    assert [(event.start, event.end) for event in found] == [(datetime(2026, 9, 22, 15, 25), datetime(2026, 9, 22, 16, 0))]


def test_holidays_silence_a_series_unless_it_is_ticked():
    day = {"2026-09-23": {"free": True, "overrides_lessons": True}}
    quiet = entry("q1")
    ticked = entry("t1", name="Swim", start="17:00", holidays=True)
    assert [event.summary for event in events([quiet, ticked], days=day)] == ["Swim"]
    assert [event.summary for event in events([quiet, ticked], blocked=True)] == ["Swim"]


def test_the_uid_is_stable_per_entry_and_day():
    first = events([entry("e1")])[0]
    again = events([entry("e1", name="Chess")])[0]
    assert first.uid == again.uid
    assert first.uid.endswith(f"-20260923-own-e1@{feed.UID_DOMAIN}")


def test_new_component_is_known_and_existing_subscriptions_stay_as_they_are():
    assert COMPONENT_OWN_ENTRIES in subscriptions.COMPONENTS
    assert subscriptions.normalize_components([COMPONENT_TIMETABLE]) == [COMPONENT_TIMETABLE]
    assert subscriptions.normalize_components([COMPONENT_OWN_ENTRIES]) == [COMPONENT_OWN_ENTRIES]


def test_a_one_off_break_shortens_a_club_in_the_feed_as_in_the_app():
    club = entry("c1", start="15:30", duration=60)
    snack = entry("b1", type="pause", name="Snack", start="16:00", duration=15, repeat="once", date="2026-09-23", holidays=True)
    found = events([club, snack])
    assert [(event.summary, event.start, event.end) for event in found] == [("Chess club", datetime(2026, 9, 23, 15, 30), datetime(2026, 9, 23, 16, 0))]



def test_on_a_holiday_the_lessons_iserv_still_reports_do_not_cut_a_ticked_entry():
    day = {"2026-09-23": {"free": True, "overrides_lessons": True}}
    morning = entry("m1", name="Riding", start="08:00", duration=60, holidays=True)
    found = events([morning], days=day)
    assert [(event.summary, event.start, event.end) for event in found] == [("Riding", datetime(2026, 9, 23, 8, 0), datetime(2026, 9, 23, 9, 0))]
    assert all(event.start != datetime(2026, 9, 23, 8, 0) for event in events([morning]))
