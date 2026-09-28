from app import integration, messages
from app.poller import TIMETABLE_MOVED_KEY, TIMETABLE_PLAN_KEY, Poller
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.time_table_school import (
    EMPTY,
    Answer,
    SCHOOL_APP_REGULAR,
    SCHOOL_APP_SUBSTITUTED,
    TimeTableSchool,
    client_factory,
)

NOW_EPOCH = 1_788_969_600.0


class Clock:
    def __init__(self):
        self.now = NOW_EPOCH

    def __call__(self):
        return self.now


class Notifier:
    def __init__(self):
        self.calls = []

    def __call__(self, name, message):
        self.calls.append(message)
        return True


def school_parts(tmp_path, school_class=TimeTableSchool):
    school = school_class(school_week=(SCHOOL_APP_REGULAR, SCHOOL_APP_REGULAR), slots=True, time_table=EMPTY)
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    service = IServService(store, client_factory=client_factory(school))
    connection = service.connection(connection_id)
    clock = Clock()
    connection.clock = clock
    notifier = Notifier()
    poller = Poller(service, notifier=notifier, store=store, clock=clock)
    return school, clock, notifier, poller, connection


def school_setup(tmp_path):
    return school_parts(tmp_path)[:4]


def later(clock, school, week):
    clock.now += 3 * 3600
    school.school_week = week


def test_a_school_app_substitution_sends_one_change_push_and_no_plan_push(tmp_path):
    school, clock, notifier, poller = school_setup(tmp_path)
    poller.poll_once()
    assert notifier.calls == []
    later(clock, school, (SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED))
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert messages.text_count("de", TIMETABLE_MOVED_KEY, 4, {"name": "Kim"}) in notifier.calls[0]
    assert messages.text_in("de", TIMETABLE_PLAN_KEY, {"name": "Kim"}) not in notifier.calls[0]
    later(clock, school, (SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED))
    poller.poll_once()
    assert len(notifier.calls) == 1


def test_a_regular_plan_that_fails_for_one_poll_sends_no_withdrawn_push(tmp_path):
    school, clock, notifier, poller = school_setup(tmp_path)
    poller.poll_once()
    later(clock, school, (SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED))
    poller.poll_once()
    assert len(notifier.calls) == 1
    later(clock, school, (None, SCHOOL_APP_SUBSTITUTED))
    poller.poll_once()
    later(clock, school, (SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED))
    poller.poll_once()
    assert len(notifier.calls) == 1


def test_a_regular_plan_edited_inside_the_cache_time_is_read_again_and_marks_nothing(tmp_path):
    school, clock, notifier, poller, connection = school_parts(tmp_path)
    poller.poll_once()
    edited = tuple(row[:4] + ("XYZ",) + row[5:] if row[0] == 92009 else row for row in SCHOOL_APP_REGULAR)
    school.school_week = (edited, edited)
    clock.now += 3600
    poller.poll_once()
    shown = connection.timetable("500001")
    assert [lesson["change_kind"] for lesson in shown["lessons"] if lesson["change_kind"]] == []
    clock.now += 3600
    poller.poll_once()
    assert all(messages.text_in("de", TIMETABLE_PLAN_KEY, {"name": "Kim"}) in call for call in notifier.calls)
    assert len(notifier.calls) <= 1


class RateLimitedRegularSchool(TimeTableSchool):
    def _school_app(self, url, rest, params=None):
        if rest.startswith("current-timetable") and (params or {}).get("substitutions") == "false":
            return Answer(url, 429, "", payload=None)
        return super()._school_app(url, rest, params)


def test_a_rate_limited_regular_plan_makes_the_poll_back_off(tmp_path):
    _, _, notifier, poller, connection = school_parts(tmp_path, RateLimitedRegularSchool)
    poller.poll_once()
    assert integration.outage_rate_limited(poller.store, connection.id)
    assert notifier.calls == []
