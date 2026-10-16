from datetime import date, datetime, timezone

import pytest

from app import berlin, holidays

SWITCHES = [
    (2025, datetime(2025, 3, 30, 1, 0), datetime(2025, 10, 26, 1, 0)),
    (2026, datetime(2026, 3, 29, 1, 0), datetime(2026, 10, 25, 1, 0)),
    (2027, datetime(2027, 3, 28, 1, 0), datetime(2027, 10, 31, 1, 0)),
]


def utc_epoch(moment):
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


@pytest.mark.parametrize("year, spring, autumn", SWITCHES)
def test_the_local_time_jumps_exactly_at_the_switch_instants(year, spring, autumn):
    from datetime import timedelta

    one = timedelta(minutes=1)
    assert berlin.local_from_utc(spring - timedelta(hours=2)) == (spring - timedelta(hours=2)) + timedelta(hours=1)
    assert berlin.local_from_utc(spring) == spring + timedelta(hours=2)
    assert berlin.local_from_utc(autumn - one) == (autumn - one) + timedelta(hours=2)
    assert berlin.local_from_utc(autumn) == autumn + timedelta(hours=1)


@pytest.mark.parametrize("year, spring, autumn", SWITCHES)
def test_the_hour_before_each_switch_keeps_its_old_offset(year, spring, autumn):
    from datetime import timedelta

    half = timedelta(minutes=30)
    assert berlin.local_from_utc(spring - half) == spring - half + timedelta(hours=1)
    assert berlin.local_from_utc(spring - timedelta(hours=1)) == spring
    assert berlin.local_from_utc(autumn - half) == autumn - half + timedelta(hours=2)
    assert berlin.local_from_utc(autumn + half) == autumn + half + timedelta(hours=1)


@pytest.mark.parametrize("year, spring, autumn", SWITCHES)
def test_the_offset_follows_the_wall_clock_on_the_switch_days(year, spring, autumn):
    assert berlin.offset(datetime(year, 1, 15, 12, 0)) == 1
    assert berlin.offset(datetime(spring.year, spring.month, spring.day, 1, 59)) == 1
    assert berlin.offset(datetime(spring.year, spring.month, spring.day, 2, 0)) == 2
    assert berlin.offset(datetime(autumn.year, autumn.month, autumn.day, 2, 59)) == 2
    assert berlin.offset(datetime(autumn.year, autumn.month, autumn.day, 3, 0)) == 1
    assert berlin.offset(datetime(year, 7, 15, 12, 0)) == 2


@pytest.mark.parametrize(
    "utc, local_day",
    [
        (datetime(2026, 3, 28, 22, 59), date(2026, 3, 28)),
        (datetime(2026, 3, 28, 23, 0), date(2026, 3, 29)),
        (datetime(2026, 3, 29, 21, 59), date(2026, 3, 29)),
        (datetime(2026, 3, 29, 22, 0), date(2026, 3, 30)),
        (datetime(2026, 10, 24, 21, 59), date(2026, 10, 24)),
        (datetime(2026, 10, 24, 22, 0), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 22, 59), date(2026, 10, 25)),
        (datetime(2026, 10, 25, 23, 0), date(2026, 10, 26)),
        (datetime(2026, 12, 31, 23, 0), date(2027, 1, 1)),
    ],
)
def test_the_local_day_changes_at_local_midnight_around_the_switches(utc, local_day):
    assert berlin.date_from_utc(utc) == local_day
    assert berlin.today(utc) == local_day
    assert holidays.berlin_today(utc) == local_day
    assert berlin.local_from_epoch(utc_epoch(utc)).date() == local_day


def test_the_epoch_is_converted_like_the_naive_utc_time():
    moment = datetime(2026, 12, 1, 17, 0)
    assert berlin.local_from_epoch(utc_epoch(moment)) == datetime(2026, 12, 1, 18, 0)
    moment = datetime(2026, 7, 1, 17, 0)
    assert berlin.local_from_epoch(utc_epoch(moment)) == datetime(2026, 7, 1, 19, 0)


@pytest.mark.parametrize(
    "utc, stamp",
    [
        (datetime(2026, 10, 25, 0, 30), "2026-10-25T02:30:00+02:00"),
        (datetime(2026, 10, 25, 1, 30), "2026-10-25T02:30:00+01:00"),
        (datetime(2026, 3, 29, 0, 30), "2026-03-29T01:30:00+01:00"),
        (datetime(2026, 3, 29, 1, 30), "2026-03-29T03:30:00+02:00"),
    ],
)
def test_a_stamp_carries_the_offset_of_its_instant_even_in_the_repeated_hour(utc, stamp):
    from app import diagnostics, integration

    epoch = utc_epoch(utc)
    assert berlin.iso_from_epoch(epoch) == stamp
    assert integration.berlin_iso(epoch) == stamp
    assert diagnostics._stamp(epoch) == stamp
    assert datetime.fromisoformat(stamp).timestamp() == epoch
