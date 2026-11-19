from datetime import date

import pytest

from fastapi.testclient import TestClient

from app.refusals import REFUSAL_SECONDS
from app.server import create_app
from app.service import IServService
from app.store import Store, edit_config, normalize_connection
from app.timetable_source import BOTH_KEY, CHOICE_KEY, RECHECK_SECONDS
from tests.support import add_school, connection_service
from app.iserv.errors import OutageError
from app.poller import Poller
from tests.time_table_school import (
    ABSENT,
    BROKEN,
    DATA,
    EMPTY,
    LESSONS,
    MOVED_WEEK_PLAN,
    PAGE,
    SCHOOL_APP_REGULAR,
    SCHOOL_APP_SUBSTITUTED,
    TimeTableSchool,
    client_factory,
    moved_week_changes,
)

MONDAY_AFTER = date(2026, 10, 5)
CHILD = "500001"


class Clock:
    def __init__(self):
        self.now = 1_790_000_000.0

    def __call__(self):
        return self.now


def both_modules(**overrides):
    fields = dict(
        school_week=(SCHOOL_APP_REGULAR, SCHOOL_APP_REGULAR),
        slots=True,
        plan=MOVED_WEEK_PLAN,
        changes=moved_week_changes,
    )
    fields.update(overrides)
    return TimeTableSchool(**fields)


def make(tmp_path, school):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    service = connection_service(store, connection_id, client_factory(school))
    service.clock = Clock()
    return service


def choose(service, value):
    edit_config(service.store, lambda current: current.update({CHOICE_KEY: value}))


def test_the_new_plan_stays_the_source_and_both_plans_report_their_changes(tmp_path):
    school = both_modules()
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "school-app"
    assert result["source_choice"] == "school-app"
    assert result["source_choice_missing"] is False
    assert result["sources"]["school-app"]["changes"] == 0
    assert result["sources"]["time-table"]["changes"] > 0
    assert len(result["lessons"]) == len(SCHOOL_APP_REGULAR)


def test_choosing_the_old_plan_shows_its_lessons_and_changes_every_week(tmp_path):
    school = both_modules()
    service = make(tmp_path, school)
    choose(service, "time-table")
    for week_offset in (0, 1):
        result = service.timetable(CHILD, reference=MONDAY_AFTER, week_offset=week_offset)
        assert result["source"] == "time-table"
        assert result["source_choice"] == "time-table"
        assert result["source_choice_missing"] is False
        assert result["change_count"] > 0
    assert result["sources"]["school-app"]["changes"] == 0


def test_the_old_plan_stays_chosen_while_the_new_plan_also_has_changes(tmp_path):
    school = both_modules(school_week=(SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED))
    service = make(tmp_path, school)
    choose(service, "time-table")
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "time-table"
    assert result["sources"]["school-app"]["changes"] > 0


def test_a_chosen_old_plan_that_is_gone_shows_the_new_plan_and_says_so(tmp_path):
    school = both_modules(time_table=ABSENT)
    service = make(tmp_path, school)
    choose(service, "time-table")
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "school-app"
    assert result["source_choice"] == "time-table"
    assert result["source_choice_missing"] is True
    assert len(result["lessons"]) == len(SCHOOL_APP_REGULAR)
    assert service.store.load_config()[CHOICE_KEY] == "time-table"


def test_the_old_plan_is_compared_at_most_once_an_hour(tmp_path):
    school = both_modules()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=MONDAY_AFTER)
    service.clock.now += 60
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert len(school.paths(DATA)) == 1
    assert result["sources"]["time-table"]["changes"] > 0
    service.clock.now += RECHECK_SECONDS
    service.timetable(CHILD, reference=MONDAY_AFTER)
    assert len(school.paths(DATA)) == 2


def test_only_the_current_week_is_compared(tmp_path):
    school = both_modules()
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=MONDAY_AFTER, week_offset=1)
    assert result["sources"] is None
    assert school.paths(DATA) == []


def test_a_school_without_the_old_plan_is_asked_for_it_once_a_day(tmp_path):
    school = both_modules(time_table=ABSENT)
    service = make(tmp_path, school)
    for _ in range(3):
        result = service.timetable(CHILD, reference=MONDAY_AFTER)
        service.clock.now += RECHECK_SECONDS
    assert result["sources"] is None
    assert len(school.paths(PAGE)) == 1
    service.clock.now += REFUSAL_SECONDS
    service.timetable(CHILD, reference=MONDAY_AFTER)
    assert len(school.paths(PAGE)) == 2


def test_an_unknown_stored_choice_means_the_new_plan():
    assert normalize_connection({"timetable_choice": "elsewhere"})["timetable_choice"] == ""
    assert normalize_connection({"timetable_choice": "time-table"})["timetable_choice"] == "time-table"


class Holidays:
    def range_info(self, start, end, config=None, partial=False):
        return {"status": "ok", "days": {}, "periods": []}


def test_the_choice_is_saved_and_shown_for_the_school_and_rejects_other_values(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    client = TestClient(create_app(IServService(store), holiday_calendar=Holidays(), calendar_warmer=lambda child: None))
    refused = client.post(f"/api/connections/{connection_id}", json={"timetable_choice": "elsewhere"})
    assert refused.status_code == 400
    saved = client.post(f"/api/connections/{connection_id}", json={"timetable_choice": "time-table"})
    assert saved.json() == {"saved": True}
    assert client.get(f"/api/connections/{connection_id}").json()["timetable_choice"] == "time-table"


def test_a_chosen_old_plan_is_shown_while_the_new_plan_lists_no_lessons(tmp_path):
    school = both_modules(school_week=((), ()))
    service = make(tmp_path, school)
    choose(service, "time-table")
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "time-table"
    assert result["source_choice_missing"] is False
    assert len(result["lessons"]) > 0


def test_an_empty_week_of_the_chosen_old_plan_stays_an_empty_old_week(tmp_path):
    school = both_modules(time_table=EMPTY)
    service = make(tmp_path, school)
    choose(service, "time-table")
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "time-table"
    assert result["source_choice_missing"] is False
    assert result["no_lessons"] is True


def test_a_broken_chosen_old_plan_shows_the_new_plan_and_says_so(tmp_path):
    school = both_modules(time_table=BROKEN)
    service = make(tmp_path, school)
    choose(service, "time-table")
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "school-app"
    assert result["source_choice_missing"] is True
    assert result["source_choice_failure"] == "not readable"


def test_an_unreachable_chosen_old_plan_is_an_outage_of_the_school(tmp_path):
    school = both_modules(on_data=outage)
    service = make(tmp_path, school)
    choose(service, "time-table")
    with pytest.raises(OutageError):
        service.timetable(CHILD, reference=MONDAY_AFTER)


def test_a_compared_old_plan_that_is_unreachable_leaves_the_new_plan_alone(tmp_path):
    school = both_modules(on_data=outage)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["source"] == "school-app"
    assert result["sources"] is None


def outage():
    raise OutageError("the old module timed out")


def test_a_passing_error_of_the_old_plan_does_not_pause_the_comparison_for_a_day(tmp_path):
    school = both_modules(time_table=BROKEN)
    service = make(tmp_path, school)
    assert service.timetable(CHILD, reference=MONDAY_AFTER)["sources"] is None
    school.time_table = LESSONS
    service.clock.now += RECHECK_SECONDS
    assert service.timetable(CHILD, reference=MONDAY_AFTER)["sources"]["time-table"]["changes"] > 0


def test_an_unread_regular_plan_makes_the_new_plan_count_unknown_not_zero(tmp_path):
    school = both_modules(school_week=(None, SCHOOL_APP_REGULAR))
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=MONDAY_AFTER)
    assert result["sources"]["school-app"]["changes"] is None


def test_the_school_remembers_whether_it_has_both_plans(tmp_path):
    school = both_modules()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=MONDAY_AFTER)
    assert service.store.load_config()[BOTH_KEY] is True
    school.time_table = ABSENT
    service.clock.now += REFUSAL_SECONDS
    service.timetable(CHILD, reference=MONDAY_AFTER)
    assert service.store.load_config()[BOTH_KEY] is False


def polling(tmp_path, school):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example", children=[{"child_id": CHILD, "name": "Kim Muster"}])
    service = IServService(store, client_factory=client_factory(school))
    connection = service.connection(connection_id)
    clock = Clock()
    connection.clock = clock
    edit_config(connection.store, lambda current: current.update({CHOICE_KEY: "time-table"}))
    poller = Poller(service, notifier=lambda name, message: True, store=store, clock=clock)
    return store, connection_id, clock, poller


def test_a_poll_without_the_chosen_old_module_carries_on_with_the_new_plan(tmp_path):
    school = both_modules()
    store, connection_id, clock, poller = polling(tmp_path, school)
    poller.poll_once()
    school.time_table = ABSENT
    for _ in range(2):
        clock.now += 3 * 3600
        poller.poll_once()
    states = store.connection(connection_id)["poll_state"]
    assert states and all(entry.get("timetable_source") == "school-app" for entry in states.values())


def test_a_poll_that_cannot_read_the_chosen_old_plan_keeps_the_last_state(tmp_path):
    school = both_modules()
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example", children=[{"child_id": CHILD, "name": "Kim Muster"}])
    service = IServService(store, client_factory=client_factory(school))
    connection = service.connection(connection_id)
    clock = Clock()
    connection.clock = clock
    edit_config(connection.store, lambda current: current.update({CHOICE_KEY: "time-table"}))
    poller = Poller(service, notifier=lambda name, message: True, store=store, clock=clock)
    poller.poll_once()
    before = store.connection(connection_id)["poll_state"]
    assert before and all(entry.get("timetable_source") == "time-table" for entry in before.values())
    school.time_table = BROKEN
    clock.now += 3 * 3600
    poller.poll_once()
    assert store.connection(connection_id)["poll_state"] == before
