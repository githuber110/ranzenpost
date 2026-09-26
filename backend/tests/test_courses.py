import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app import courses
from app.iserv.models import Child
from app.iserv.timetable import parse_timetable, week_bounds
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.conftest import load_fixture
from tests.support import add_school

CHILD_ID = "uuid-1"
MONDAY = "31.08.2026"
TUESDAY = "01.09.2026"
ELECTIVES = ["E1|CCC", "E2|DDD", "F1|EEE", "L1|FFF", "SP|GGG", "SP|HHH"]
FIXTURE_MONDAY = date(2026, 8, 31)
WEEK = date(2026, 9, 1)
DATE_FORMAT = "%d.%m.%Y"


def shifted(value, days):
    return (datetime.strptime(value, DATE_FORMAT) + timedelta(days=days)).strftime(DATE_FORMAT)


def week_payload(name, reference):
    payload = json.loads(load_fixture(name))
    days = (week_bounds(reference or date.today())[0] - FIXTURE_MONDAY).days
    for bucket in (payload["data"]["timetable"], payload["plain-timetable"], payload["plain-changes"]):
        for entry in bucket:
            entry["date"] = shifted(entry["date"], days)
    return payload


class ParallelClient:
    fixture_name = "timetable_parallel_courses.json"

    def __init__(self, url):
        self.url = url
        self.base_url = url
        self.session = None
        self.authed = False
        self.references = []

    def login(self, username, password, code_provider):
        assert code_provider()
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        return [Child(CHILD_ID, "Kim")]

    def read_time_table_week(self, child_id, reference=None):
        self.references.append(reference)
        return parse_timetable(week_payload(self.fixture_name, reference))


class SingleLessonClient(ParallelClient):
    fixture_name = "timetable_data.json"


def service_for(tmp_path, client_class=ParallelClient):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[{"child_id": CHILD_ID, "name": "Kim"}])
    service = IServService(store, client_factory=lambda url: client_class(url))
    return service, store, f"{connection_id}:{CHILD_ID}"


def lessons_at(result, day, period):
    return [lesson for lesson in result["lessons"] if lesson["date"] == day and lesson["period"] == period]


def pairs(lessons):
    return sorted((lesson["subject_code"], lesson["teacher_code"]) for lesson in lessons)


def display(date_value, period, key, **extra):
    subject, teacher = courses.split_course_key(key)
    entry = {
        "date": date_value,
        "day_of_week": 1,
        "period": period,
        "subject_key": subject,
        "subject_code": subject,
        "teacher_code": teacher,
        "room": "R1",
        "change_kind": "",
        "course_key": key,
    }
    entry.update(extra)
    return entry


def test_course_key_round_trips_and_keeps_a_separator_in_the_subject():
    assert courses.course_key("E1", "CCC") == "E1|CCC"
    assert courses.split_course_key("E1|CCC") == ("E1", "CCC")
    assert courses.split_course_key("A|B|CCC") == ("A|B", "CCC")


def test_parallel_keys_ignore_single_lesson_periods():
    lessons = [display(MONDAY, 1, "D|AAA"), display(MONDAY, 2, "E1|CCC"), display(MONDAY, 2, "E2|DDD")]
    assert courses.parallel_keys(lessons) == {"E1|CCC", "E2|DDD"}


def test_a_duplicated_lesson_is_not_a_parallel_course():
    lessons = [display(MONDAY, 1, "D|AAA"), display(MONDAY, 1, "D|AAA")]
    assert courses.parallel_keys(lessons) == set()


def test_filter_shows_chosen_and_unknown_courses_only():
    active = courses.normalize_filter({"chosen": ["E1|CCC"], "known": ["E1|CCC", "E2|DDD"]})
    assert courses.shows(display(MONDAY, 2, "E1|CCC"), active)
    assert not courses.shows(display(MONDAY, 2, "E2|DDD"), active)
    assert courses.shows(display(MONDAY, 2, "NEW|QQQ"), active)
    assert courses.shows(display(MONDAY, 1, "D|AAA"), active)
    assert courses.shows(display(MONDAY, 2, "E2|DDD"), None)


def test_normalize_filter_rejects_broken_input_and_folds_chosen_into_known():
    assert courses.normalize_filter(None) is None
    assert courses.normalize_filter({"chosen": "E1|CCC", "known": []}) is None
    cleaned = courses.normalize_filter({"chosen": ["E1|CCC", "E1|CCC", 7, "", "nokey"], "known": ["E2|DDD"]})
    assert cleaned == {"chosen": ["E1|CCC"], "known": ["E1|CCC", "E2|DDD"]}
    capped = courses.normalize_filter(
        {"chosen": [], "known": [f"S{index}|T" for index in range(courses.MAX_KEYS + 50)], courses.CONFIRMED_EMPTY_KEY: True}
    )
    assert len(capped["known"]) == courses.MAX_KEYS


def test_regular_course_key_follows_the_regular_teacher_of_a_substitution():
    lesson = type("L", (), {"subject": "E2", "teacher": "ZZZ"})()
    change = {"kind": "changed", "fields": ["teacher"], "previous": {"subject": "E2", "teacher": "DDD", "room": "R202"}}
    assert courses.regular_course_key(lesson, change) == "E2|DDD"
    assert courses.regular_course_key(lesson, {"kind": "added", "previous": {"subject": "", "teacher": ""}}) == "E2|ZZZ"
    assert courses.regular_course_key(lesson) == "E2|ZZZ"


def test_visible_changes_drop_only_changes_of_hidden_courses():
    visible = [display(TUESDAY, 1, "E1|CCC", subject_key="E1")]
    hidden = [display(TUESDAY, 1, "E2|DDD", subject_key="E2")]
    changes = [
        {"date": TUESDAY, "period": 1, "subject": "E2", "type": "Vertretung"},
        {"date": TUESDAY, "period": 1, "subject": "E1", "type": "Vertretung"},
        {"date": TUESDAY, "period": 2, "subject": "E2", "type": "Entfall"},
        "broken",
    ]
    kept = courses.visible_changes(changes, visible, hidden)
    assert kept == changes[1:]


def test_visible_changes_tell_parallel_groups_of_one_subject_apart_by_teacher():
    visible = [display(TUESDAY, 2, "SP|GGG", subject_key="SP", teacher_code="GGG")]
    hidden = [display(TUESDAY, 2, "SP|HHH", subject_key="SP", teacher_code="HHH")]
    changes = [
        {"date": TUESDAY, "period": 2, "subject": "SP", "teacher": "HHH", "type": "Entfall"},
        {"date": TUESDAY, "period": 2, "subject": "SP", "teacher": "GGG", "type": "Vertretung"},
    ]
    assert courses.visible_changes(changes, visible, hidden) == changes[1:]


def test_catalogue_groups_by_named_subject_or_code_stem():
    lessons = [display(MONDAY, 3, key) for key in ELECTIVES]
    config = {"subjects": {"F1": {"label": "Franzoesisch"}, "E1": {"label": "E1"}}}
    listed = courses.catalogue(lessons, None, config)
    assert listed["chosen"] is False
    groups = {entry["key"]: entry["group"] for entry in listed["courses"]}
    assert groups == {"E1|CCC": "E", "E2|DDD": "E", "F1|EEE": "Franzoesisch", "L1|FFF": "L", "SP|GGG": "SP", "SP|HHH": "SP"}
    assert all(entry["chosen"] is True and entry["new"] is False for entry in listed["courses"])


def test_catalogue_marks_new_courses_as_shown_and_keeps_known_ones_out_of_this_week():
    lessons = [display(MONDAY, 3, key) for key in ("E1|CCC", "E2|DDD", "X1|NEW")]
    active = courses.normalize_filter({"chosen": ["E1|CCC", "OLD|GONE"], "known": ["E1|CCC", "E2|DDD", "OLD|GONE"]})
    listed = {entry["key"]: entry for entry in courses.catalogue(lessons, active, {})["courses"]}
    assert set(listed) == {"E1|CCC", "E2|DDD", "X1|NEW", "OLD|GONE"}
    assert listed["E1|CCC"]["chosen"] is True and listed["E1|CCC"]["new"] is False
    assert listed["E2|DDD"]["chosen"] is False
    assert listed["X1|NEW"]["chosen"] is True and listed["X1|NEW"]["new"] is True
    assert listed["OLD|GONE"]["count"] == 0 and listed["OLD|GONE"]["chosen"] is True


def test_unfiltered_timetable_keeps_every_parallel_lesson(tmp_path):
    service, _, key = service_for(tmp_path)
    result = service.timetable(key, reference=date(2026, 9, 1))
    assert len(lessons_at(result, MONDAY, 3)) == 6
    assert len(lessons_at(result, MONDAY, 5)) == 3
    assert pairs(lessons_at(result, TUESDAY, 2)) == [("SP", "GGG"), ("SP", "HHH")]
    cancelled = next(lesson for lesson in lessons_at(result, TUESDAY, 2) if lesson["teacher_code"] == "HHH")
    assert cancelled["change_kind"] == "cancelled"
    substituted = next(lesson for lesson in lessons_at(result, TUESDAY, 1) if lesson["subject_code"] == "E2")
    assert substituted["change_kind"] == "changed" and substituted["teacher_code"] == "ZZZ"
    assert substituted["course_key"] == "E2|DDD"
    assert result["courses"] == {"parallel": 9, "chosen": False, "hidden": 0, "new": 0, "signature": ""}
    assert result["change_count"] == 2
    assert len(result["changes"]) == 2


def test_filtered_timetable_shows_only_the_chosen_courses(tmp_path):
    service, store, key = service_for(tmp_path)
    catalogue = service.timetable_courses(key, reference=date(2026, 9, 1))
    known = [entry["key"] for entry in catalogue["courses"]]
    assert len(known) == 9
    saved = service.save_course_filter(key, ["E2|DDD", "SP|GGG", "REV|III"], known)
    assert saved["ok"] is True and saved["message_key"] == "api.courses.saved"
    result = service.timetable(key, reference=date(2026, 9, 1))
    assert pairs(lessons_at(result, MONDAY, 3)) == [("E2", "DDD"), ("SP", "GGG")]
    assert pairs(lessons_at(result, MONDAY, 5)) == [("REV", "III")]
    assert pairs(lessons_at(result, TUESDAY, 1)) == [("E2", "ZZZ")]
    assert pairs(lessons_at(result, TUESDAY, 2)) == [("SP", "GGG")]
    assert pairs(lessons_at(result, MONDAY, 1)) == [("D", "AAA")]
    assert result["courses"]["chosen"] is True
    assert result["courses"]["hidden"] == 4 * 2 + 2 + 3 + 1
    assert result["change_count"] == 1
    assert [entry["subject"] for entry in result["changes"]] == ["E2"]


def test_a_period_without_chosen_courses_stays_empty(tmp_path):
    service, _, key = service_for(tmp_path)
    known = [entry["key"] for entry in service.timetable_courses(key, reference=WEEK)["courses"]]
    service.save_course_filter(key, ["E1|CCC"], known)
    result = service.timetable(key, reference=WEEK)
    assert lessons_at(result, MONDAY, 5) == []
    assert lessons_at(result, TUESDAY, 2) == []


def test_resetting_the_filter_shows_everything_again(tmp_path):
    service, store, key = service_for(tmp_path)
    service.save_course_filter(key, ["E1|CCC"], ELECTIVES)
    reset = service.save_course_filter(key, None, None)
    assert reset["message_key"] == "api.courses.reset"
    assert store.connection(key.split(":")[0])["course_filters"] == {}
    assert len(lessons_at(service.timetable(key, reference=WEEK), MONDAY, 3)) == 6


def test_single_lesson_plan_is_untouched_by_the_filter(tmp_path):
    service, _, key = service_for(tmp_path, SingleLessonClient)
    before = service.timetable(key)
    assert before["courses"]["parallel"] == 0
    catalogue = service.timetable_courses(key)
    assert catalogue == {"courses": [], "chosen": False}
    service.save_course_filter(key, [], [])
    after = service.timetable(key)
    assert after["lessons"] == before["lessons"]
    assert after["change_count"] == before["change_count"]


def test_course_filter_is_stored_per_child_and_rejects_foreign_children(tmp_path):
    service, store, key = service_for(tmp_path)
    connection_id = key.split(":")[0]
    service.save_course_filter(key, ["E1|CCC"], ELECTIVES)
    assert store.connection(connection_id)["course_filters"] == {
        CHILD_ID: {"chosen": ["E1|CCC"], "known": sorted(ELECTIVES)}
    }
    try:
        service.save_course_filter(f"{connection_id}:someone-else", ["E1|CCC"], ELECTIVES)
    except Exception as error:
        assert getattr(error, "message_key", "") == "api.child.unknown"
    else:
        raise AssertionError("a foreign child must be rejected")


def test_course_filter_follows_a_moved_child_id():
    config = {"course_filters": {"old": {"chosen": ["E1|CCC"], "known": ["E1|CCC"]}}}
    moved = courses.moved_filter(config, "old", "new")
    assert moved["course_filters"] == {"new": {"chosen": ["E1|CCC"], "known": ["E1|CCC"]}}
    assert courses.moved_filter(config, "absent", "new") is None


def test_course_api_lists_saves_and_resets(tmp_path):
    service, _, key = service_for(tmp_path)
    warmed = []
    client = TestClient(create_app(service, calendar_warmer=warmed.append))
    listed = client.get("/api/timetable/courses", params={"child": key})
    assert listed.status_code == 200
    assert len(listed.json()["courses"]) == 9
    saved = client.post("/api/timetable/courses", json={"child": key, "chosen": ["E1|CCC"], "known": ELECTIVES})
    assert saved.status_code == 200 and saved.json()["message_key"] == "api.courses.saved"
    assert warmed == [key]
    shown = client.get("/api/timetable", params={"child": key}).json()
    assert pairs([lesson for lesson in shown["lessons"] if lesson["day_of_week"] == 1 and lesson["period"] == 3]) == [("E1", "CCC")]
    broken = client.post("/api/timetable/courses", json={"child": key, "chosen": "E1|CCC", "known": []})
    assert broken.status_code == 400 and broken.json()["message_key"] == "api.courses.invalid"
    foreign = client.post("/api/timetable/courses", json={"child": "nope:child", "chosen": [], "known": []})
    assert foreign.status_code == 404
    reset = client.post("/api/timetable/courses", json={"child": key, "chosen": None})
    assert reset.json()["message_key"] == "api.courses.reset"


def test_first_course_list_ticks_every_course_including_team_teaching(tmp_path):
    service, _, key = service_for(tmp_path)
    listed = service.timetable_courses(key, reference=date(2026, 9, 1))
    assert listed["chosen"] is False
    assert listed["courses"]
    assert all(entry["chosen"] is True for entry in listed["courses"])


def test_an_empty_course_choice_needs_an_explicit_confirmation(tmp_path):
    service, store, key = service_for(tmp_path)
    client = TestClient(create_app(service, calendar_warmer=lambda child: None))
    refused = client.post("/api/timetable/courses", json={"child": key, "chosen": [], "known": ELECTIVES})
    assert refused.status_code == 400
    assert refused.json()["message_key"] == "api.courses.emptyUnconfirmed"
    assert courses.filter_of(service.resolve(key)[0].store.load_config(), CHILD_ID) is None
    confirmed = client.post("/api/timetable/courses", json={"child": key, "chosen": [], "known": ELECTIVES, "confirm_empty": True})
    assert confirmed.status_code == 200
    assert confirmed.json()["message_key"] == "api.courses.saved"
    assert courses.filter_of(service.resolve(key)[0].store.load_config(), CHILD_ID) == {
        "chosen": [],
        "known": sorted(ELECTIVES),
        courses.CONFIRMED_EMPTY_KEY: True,
    }


def test_an_empty_choice_saved_before_it_needed_a_confirmation_counts_as_no_choice():
    stored = {"course_filters": {"c1": {"chosen": [], "known": ["E1|CCC", "E2|DDD"]}}}
    assert courses.filter_of(stored, "c1") is None


def test_a_confirmed_empty_choice_stays_and_hides_every_known_course():
    stored = courses.with_filter({}, "c1", {"chosen": [], "known": ["E1|CCC"], courses.CONFIRMED_EMPTY_KEY: True})
    active = courses.filter_of(stored, "c1")
    assert active == {"chosen": [], "known": ["E1|CCC"], courses.CONFIRMED_EMPTY_KEY: True}
    assert courses.shows({"course_key": "E1|CCC"}, active) is False


def test_the_api_keeps_the_confirmation_of_an_empty_choice(tmp_path):
    service, store, key = service_for(tmp_path)
    client = TestClient(create_app(service))
    body = {"child": key, "chosen": [], "known": ELECTIVES, "confirm_empty": True}
    assert client.post("/api/timetable/courses", json=body).json()["ok"] is True
    stored = store.connection(key.split(":")[0])["course_filters"][CHILD_ID]
    assert stored[courses.CONFIRMED_EMPTY_KEY] is True
