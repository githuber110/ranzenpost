from app.iserv.models import Lesson
from app.mapping import configured_time, lesson_times, to_display

SCHOOL_START = "08:00"
SCHOOL_END = "08:45"
OWN_START = "07:40"


def lesson(period=1, start=SCHOOL_START, end=SCHOOL_END):
    return Lesson(
        date="07.09.2026",
        day_of_week=1,
        period=period,
        subject="D",
        teacher="BEI",
        room="R1",
        class_name="3b",
        start_time=start,
        end_time=end,
    )


def test_a_time_the_parent_entered_beats_the_one_the_school_sends():
    config = {"period_times": {"1": OWN_START}}
    assert lesson_times(lesson(), config) == (OWN_START, "08:25")


def test_the_school_time_still_fills_a_period_the_parent_left_empty():
    config = {"period_times": {"1": "", "2": "09:00"}}
    assert lesson_times(lesson(), config) == (SCHOOL_START, SCHOOL_END)


def test_an_agreeing_setting_keeps_the_end_the_school_named():
    config = {"period_times": {"1": SCHOOL_START}}
    assert lesson_times(lesson(), config) == (SCHOOL_START, SCHOOL_END)


def test_a_nonsense_setting_is_ignored_rather_than_shown():
    for broken in ("acht uhr", "25:00", "8:6", "08.00", "  ", "08:00:00"):
        config = {"period_times": {"1": broken}}
        assert lesson_times(lesson(), config) == (SCHOOL_START, SCHOOL_END), broken
        assert configured_time(config, 1) == ""


def test_a_short_form_hour_is_accepted():
    config = {"period_times": {"1": "7:40"}}
    assert lesson_times(lesson(), config) == ("7:40", "08:25")


def test_a_late_lesson_never_wraps_past_midnight():
    config = {"period_times": {"1": "23:30"}}
    start, end = lesson_times(lesson(), config)
    assert start == "23:30"
    assert end == ""


def test_the_displayed_lesson_carries_the_entered_time():
    config = {"period_times": {"1": OWN_START}, "subjects": {}, "teachers": {}}
    shown = to_display(lesson(), config)
    assert shown["start_time"] == OWN_START
    assert shown["end_time"] == "08:25"


def test_a_lesson_the_school_gave_no_time_for_still_takes_the_setting():
    config = {"period_times": {"3": "10:15"}, "subjects": {}, "teachers": {}}
    shown = to_display(lesson(period=3, start="", end=""), config)
    assert shown["start_time"] == "10:15"
    assert shown["end_time"] == "11:00"
