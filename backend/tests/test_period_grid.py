import random
from datetime import date, timedelta

from app import own_entries, period_grid
from app.iserv.dsa import parse_period_slots
from app.iserv.models import Lesson
from app.mapping import lesson_times

ISERV = {"1": {"start": "07:50", "end": "08:35"}, "2": {"start": "08:40", "end": "09:25"}, "3": {"start": "09:45", "end": "10:30"}}
STARTS_ONLY = {"1": {"start": "08:00", "end": ""}, "2": {"start": "08:50", "end": ""}}


def config_with(iserv=None, times=None, lessons=None, days=None):
    grid = {}
    if iserv is not None:
        grid["iserv"] = iserv
    if lessons is not None:
        grid["lessons"] = lessons
    if days is not None:
        grid["days"] = days
    return {"period_times": dict(times or {}), "period_grid": grid}


def rows_by_number(config):
    return {row["number"]: row for row in period_grid.resolve(config)}


def test_the_iserv_layer_gives_start_and_duration():
    rows = rows_by_number(config_with(ISERV, {"1": "07:50", "2": "08:40", "3": "09:45"}))
    assert [rows[n]["duration"] for n in (1, 2, 3)] == [45, 45, 45]
    assert rows[1]["source"] == period_grid.SOURCE_ISERV
    assert not any(row["own_start"] or row["own_duration"] or row["added"] for row in rows.values())


def test_without_an_end_from_iserv_the_standard_45_minutes_apply():
    rows = rows_by_number(config_with(STARTS_ONLY, {"1": "08:00"}))
    assert rows[1]["duration"] == 45
    assert rows[1]["end"] == 8 * 60 + 45
    assert rows[1]["source"] == period_grid.SOURCE_STANDARD


def test_an_own_duration_and_start_win_over_iserv():
    rows = rows_by_number(config_with(ISERV, {"1": "07:45", "2": "08:40"}, {"2": {"duration": 60}}))
    assert rows[1]["start"] == 7 * 60 + 45 and rows[1]["own_start"] and not rows[1]["own_duration"]
    assert rows[2]["duration"] == 60 and rows[2]["own_duration"] and not rows[2]["own_start"]
    assert rows[2]["iserv_duration"] == 45


def test_an_added_ninth_lesson_is_own_until_iserv_sends_its_own_ninth():
    config = config_with(ISERV, {"1": "07:50", "9": "15:30"}, {"9": {"duration": 50, "added": True}})
    row = rows_by_number(config)[9]
    assert row["added"] and row["source"] == period_grid.SOURCE_OWN and row["duration"] == 50
    later = period_grid.merge_iserv(config, dict(ISERV, **{"9": {"start": "15:20", "end": "16:05"}}))
    taken = rows_by_number(later)[9]
    assert not taken["added"]
    assert taken["start"] == 15 * 60 + 20
    assert taken["duration"] == 50 and taken["own_duration"]
    assert later["period_times"]["9"] == "15:20"


def test_merging_fills_empty_starts_and_keeps_own_ones():
    config = config_with(None, {"1": "07:30"})
    merged = period_grid.merge_iserv(config, ISERV)
    assert merged["period_times"] == {"1": "07:30", "2": "08:40", "3": "09:45"}
    assert merged["period_grid"]["iserv"]["2"] == {"start": "08:40", "end": "09:25"}


def test_new_iserv_times_are_followed_where_nothing_was_changed_by_hand():
    first = period_grid.merge_iserv(config_with(None, {"1": "07:30"}), ISERV)
    moved = dict(ISERV, **{"1": {"start": "08:00", "end": "08:45"}, "2": {"start": "08:50", "end": "09:35"}})
    second = period_grid.merge_iserv(first, moved)
    assert second["period_times"]["1"] == "07:30"
    assert second["period_times"]["2"] == "08:50"


def test_an_empty_iserv_answer_keeps_the_known_layer():
    config = period_grid.merge_iserv(config_with(None, {}), ISERV)
    assert period_grid.merge_iserv(config, {}) is config


def test_seconds_from_iserv_are_accepted_and_dropped():
    merged = period_grid.merge_iserv(config_with(None, {}), {"1": {"start": "07:50:00", "end": "08:35:00"}})
    assert merged["period_grid"]["iserv"]["1"] == {"start": "07:50", "end": "08:35"}
    assert merged["period_times"]["1"] == "07:50"


def test_parse_period_slots_keeps_start_and_end():
    slots = [{"number": 1, "startTime": "07:50", "endTime": "08:35"}, {"number": 2, "startTime": ""}, {"startTime": "09:00"}]
    assert parse_period_slots(slots) == {"1": {"start": "07:50", "end": "08:35"}}


def lesson(period, start, end, day="02.09.2026"):
    return Lesson(date=day, day_of_week=3, period=period, subject="D", teacher="T", room="R", class_name="5a", start_time=start, end_time=end)


def test_an_own_duration_moves_the_end_the_lesson_shows():
    config = config_with(ISERV, {"1": "07:50"}, {"1": {"duration": 60}})
    assert lesson_times(lesson(1, "07:50", "08:35"), config) == ("07:50", "08:50")


def test_an_own_start_keeps_the_school_duration_of_a_double_lesson():
    config = config_with(None, {"1": "07:40"})
    assert lesson_times(lesson(1, "08:00", "09:30"), config) == ("07:40", "09:10")


def test_no_lesson_end_crosses_midnight():
    config = config_with(None, {"1": "23:40"}, {"1": {"duration": 30}})
    assert lesson_times(lesson(1, "", ""), config) == ("23:40", "")


def test_regular_periods_skip_added_lessons_but_keep_cancelled_ones():
    lessons = [
        {"date": "07.09.2026", "period": 1, "change_kind": ""},
        {"date": "07.09.2026", "period": 2, "change_kind": "cancelled"},
        {"date": "07.09.2026", "period": 7, "change_kind": "added"},
        {"date": "08.09.2026", "period": 3, "change_kind": "added"},
    ]
    assert period_grid.regular_periods(lessons) == {0: [1, 2], 1: []}


def test_the_profile_only_changes_weekdays_that_were_seen():
    config = config_with(ISERV, {}, days={"c1": {"0": [1, 2, 3], "4": [1, 2]}})
    merged = period_grid.merge_profile(config, "c1", [{"date": "07.09.2026", "period": 1, "change_kind": ""}])
    assert period_grid.profiles(merged)["c1"] == {0: [1], 4: [1, 2]}
    assert period_grid.merge_profile(config, "c1", []) is config


def week_lessons(monday, plan):
    lessons = []
    for weekday, numbers in plan.items():
        day = monday + timedelta(days=weekday)
        for number in numbers:
            lessons.append({"date": day.strftime("%d.%m.%Y"), "period": number, "change_kind": ""})
    return lessons


FIRST_MONDAY = date(2026, 9, 7)


def test_a_weekday_free_in_three_read_weeks_stops_limiting():
    config = config_with(ISERV, {}, days={"c1": {"0": [1, 2, 3], "2": [1, 2]}})
    first = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY, {0: [1], 1: [2]}))
    assert period_grid.profiles(first)["c1"][2] == [1, 2]
    again = period_grid.merge_profile(first, "c1", week_lessons(FIRST_MONDAY, {0: [1], 1: [2]}))
    second = period_grid.merge_profile(again, "c1", week_lessons(FIRST_MONDAY + timedelta(days=7), {0: [1], 1: [2]}))
    assert period_grid.profiles(second)["c1"][2] == [1, 2]
    third = period_grid.merge_profile(second, "c1", week_lessons(FIRST_MONDAY + timedelta(days=14), {0: [1], 1: [2]}))
    assert period_grid.profiles(third)["c1"] == {0: [1], 1: [2], 2: [], 3: [], 4: []}


def test_a_holiday_on_the_same_weekday_twice_keeps_the_lessons():
    config = config_with(ISERV, {}, days={"c1": {"2": [1, 2]}})
    before = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY, {0: [1], 1: [2]}))
    after = period_grid.merge_profile(before, "c1", week_lessons(FIRST_MONDAY + timedelta(days=21), {3: [1], 4: [2]}))
    assert period_grid.profiles(after)["c1"][2] == [1, 2]


def test_broken_stored_marks_do_not_break_learning():
    config = config_with(ISERV, {}, days={"c1": {"2": [1, 2]}})
    config["period_grid"]["seen"] = {"c1": {"2": {"empty": 7}, "3": "x"}, "c2": []}
    merged = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY, {0: [1]}))
    assert merged["period_grid"]["seen"]["c1"]["2"] == {"empty": [FIRST_MONDAY.isoformat()]}


def test_lessons_coming_back_restore_the_weekday_and_reset_the_count():
    config = config_with(ISERV, {}, days={"c1": {"2": [1, 2]}})
    first = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY, {0: [1]}))
    back = period_grid.merge_profile(first, "c1", week_lessons(FIRST_MONDAY + timedelta(days=7), {0: [1], 2: [3]}))
    later = period_grid.merge_profile(back, "c1", week_lessons(FIRST_MONDAY + timedelta(days=14), {0: [1]}))
    assert period_grid.profiles(later)["c1"][2] == [3]


def test_vacation_days_do_not_count_as_free_weekdays():
    config = config_with(ISERV, {}, days={"c1": {"2": [1, 2]}})
    vacation = [{"name": "Break", "start_date": "2026-09-09", "end_date": "2026-09-09"}]
    later = [{"name": "Break", "start_date": "2026-09-16", "end_date": "2026-09-16"}]
    first = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY, {0: [1]}), vacation)
    second = period_grid.merge_profile(first, "c1", week_lessons(FIRST_MONDAY + timedelta(days=7), {0: [1]}), later)
    assert period_grid.profiles(second)["c1"][2] == [1, 2]


def test_a_free_weekday_lets_an_entry_through_that_old_lessons_blocked():
    rows = period_grid.resolve(config_with(ISERV, {"1": "07:50", "2": "08:40", "3": "09:45"}))
    config = config_with(ISERV, {"1": "07:50", "2": "08:40", "3": "09:45"}, days={"c1": {"2": [1, 2, 3]}})
    entry = {"id": "e1", "type": "club", "start": "08:00", "duration": 30, "repeat": "weekly", "days": [2], "from": "2026-09-01", "until": "2026-12-01", "child": "c1"}
    assert own_entries.entry_status(entry, rows, period_grid.profiles(config), ["c1"])["state"] == own_entries.STATE_HIDDEN
    for offset in (0, 7, 14):
        config = period_grid.merge_profile(config, "c1", week_lessons(FIRST_MONDAY + timedelta(days=offset), {0: [1]}))
    assert own_entries.entry_status(entry, rows, period_grid.profiles(config), ["c1"])["state"] == own_entries.STATE_OK


def test_profile_learning_matches_a_simple_model_over_random_weeks():
    rng = random.Random(344)
    for _ in range(200):
        config = config_with(ISERV, {})
        numbers = {}
        empty = {}
        monday = FIRST_MONDAY
        for _ in range(rng.randint(1, 8)):
            monday += timedelta(days=7 * rng.choice([0, 1, 1, 1, 2]))
            plan = {weekday: sorted(rng.sample([1, 2, 3], rng.randint(1, 3))) for weekday in range(5) if rng.random() < 0.6}
            off = {weekday for weekday in range(5) if weekday not in plan and rng.random() < 0.15}
            vacations = [{"name": "Off", "start_date": (monday + timedelta(days=day)).isoformat(), "end_date": (monday + timedelta(days=day)).isoformat()} for day in off]
            config = period_grid.merge_profile(config, "c1", week_lessons(monday, plan), vacations)
            if not plan:
                continue
            for weekday in range(5):
                if weekday in plan:
                    numbers[weekday] = plan[weekday]
                    empty[weekday] = set()
                elif weekday not in off:
                    empty.setdefault(weekday, set()).add(monday)
                    if len(empty[weekday]) >= period_grid.FREE_AFTER_WEEKS:
                        numbers[weekday] = []
            learned = period_grid.profiles(config).get("c1", {})
            assert {day: value for day, value in learned.items()} == numbers
            for weekday in plan:
                assert learned[weekday] == plan[weekday]


def test_resolved_rows_never_end_after_midnight_and_stay_sorted():
    rng = random.Random(344)
    for _ in range(300):
        iserv = {}
        times = {}
        lessons = {}
        for number in range(1, rng.randint(1, 11)):
            start = rng.randint(0, 23 * 60 + 59)
            if rng.random() < 0.7:
                end = start + rng.choice([0, 30, 45, 90]) if rng.random() < 0.6 else None
                iserv[str(number)] = {"start": period_grid.clock_of(start), "end": period_grid.clock_of(end) if end and end < 1440 else ""}
            if rng.random() < 0.5:
                times[str(number)] = period_grid.clock_of(rng.randint(0, 1439))
            if rng.random() < 0.3:
                lessons[str(number)] = {"duration": rng.randint(1, 300), "added": rng.random() < 0.3}
        rows = period_grid.resolve(config_with(iserv, times, lessons))
        assert [row["number"] for row in rows] == sorted(row["number"] for row in rows)
        for row in rows:
            assert 0 <= row["start"] < 1440
            assert row["start"] < row["end"] <= 1440
            assert row["duration"] > 0
            if row["added"]:
                assert str(row["number"]) not in iserv and row["source"] == period_grid.SOURCE_OWN
            elif str(row["number"]) not in iserv:
                assert row["source"] == period_grid.SOURCE_SAVED
