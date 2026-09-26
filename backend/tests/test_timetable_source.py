import logging
from datetime import date

import pytest

from app.iserv.dsa import SCHOOL_APP_EXPIRED_KEY
from app.iserv.errors import DataError, LoginError, TwoFactorError
from app.iserv.timetable import TIMETABLE_SHAPE_KEY
from app.store import Store
from app.timetable_source import MATCH_SECONDS, RECHECK_SECONDS, SOURCE_KEY, matching_option, name_words
from app.iserv.models import Child
from tests.support import add_school, connection_service
from app import modules
from app.service import TIMETABLE_UNREADABLE_KEY
from tests.time_table_school import (
    ABSENT,
    MOVED_WEEK_CHANGES,
    MOVED_WEEK_PLAN,
    SCHOOL_APP_ANSWERS,
    SCHOOL_APP_REFUSES,
    withheld_school,
    BROKEN,
    DATA,
    EMPTY,
    FORBIDDEN,
    ODD,
    OTHER_CHILD,
    PAGE,
    PAGE_FORBIDDEN,
    PAGE_FOREIGN,
    PAGE_LOGIN,
    PAGE_ROOT,
    VACATIONS,
    TimeTableSchool,
    WEEK_PLAN,
    client_factory,
)

WEDNESDAY = date(2026, 9, 9)
CHILD = "500001"
WEEK_PLAN_WITH_TWO_SPORT_COURSES = WEEK_PLAN + ((3, 3, "SP", "OTT", "GYM2"),)
OWN_OPTION = "11111111-1111-4111-8111-111111111111"


class Clock:
    def __init__(self):
        self.now = 1_790_000_000.0

    def __call__(self):
        return self.now


def make(tmp_path, school):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    service = connection_service(store, connection_id, client_factory(school))
    service.clock = Clock()
    return service


def school_app_reads(school):
    return len([params for params in school.paths("/iserv/dieschulapp/api/1.0/current-timetable/") if params.get("filterBy")])


def remembered(service):
    return service.store.load_config().get(SOURCE_KEY)


def test_an_empty_school_app_without_slots_falls_back_to_the_time_table_module(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert result["no_lessons"] is False
    assert len(result["lessons"]) == len(WEEK_PLAN)
    assert {lesson["subject_code"] for lesson in result["lessons"]} == {"D", "MA", "EN", "SP", "KU"}
    asked = school.paths(DATA)[-1]
    assert asked["childId"] == OWN_OPTION
    assert '"startDate":"07.09.2026"' in asked["filter"]
    assert '"child":"%s"' % OWN_OPTION in asked["filter"]


def test_a_room_change_of_the_time_table_module_reaches_the_week(tmp_path):
    record = {
        "date": "07.09.2026",
        "period": 1,
        "periodStart": 1,
        "periodEnd": 1,
        "origSubject": "D",
        "substitutionSubject": "D",
        "origTeacher": "KLE",
        "substitutionTeacher": "KLE",
        "origRoom": "R101",
        "substitutionRoom": "R305",
        "origClass": ["5A"],
        "substitutionClass": ["5A"],
        "text": "",
        "change_types": [],
    }
    service = make(tmp_path, TimeTableSchool(changes=[record]))
    lesson = next(item for item in service.timetable(CHILD, reference=WEDNESDAY)["lessons"] if item["date"] == "07.09.2026" and item["period"] == 1)
    assert lesson["room"] == "R305"
    assert lesson["change_kind"] == "changed"
    assert lesson["changed_fields"] == ["room"]
    assert lesson["previous"]["room"] == "R101"


def test_the_week_answer_lists_only_the_time_table_changes_that_reached_a_lesson(tmp_path):
    shown = {
        "date": "07.09.2026",
        "period": 1,
        "periodStart": 1,
        "periodEnd": 1,
        "origSubject": "D",
        "substitutionSubject": "D",
        "origTeacher": "KLE",
        "substitutionTeacher": "KLE",
        "origRoom": "R101",
        "substitutionRoom": "R305",
        "origClass": ["5A"],
        "substitutionClass": ["5A"],
        "text": "",
        "change_types": [],
    }
    elsewhere = dict(shown, origClass=["6B"], substitutionClass=["6B"])
    service = make(tmp_path, TimeTableSchool(changes=[shown, elsewhere]))
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert [(item["date"], item["period"], item["subject"], item["room"], item["kind"]) for item in result["changes"]] == [
        ("07.09.2026", 1, "D", "R305", "changed"),
    ]
    assert result["changes_format"] == "lessons"


def test_the_school_remembers_the_time_table_source(tmp_path):
    service = make(tmp_path, TimeTableSchool())
    service.timetable(CHILD, reference=WEDNESDAY)
    assert remembered(service) == "time-table"


def test_a_remembered_source_skips_the_school_app_until_the_recheck_is_due(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    asked = school_app_reads(school)
    service.timetable(CHILD, reference=WEDNESDAY, week_offset=1)
    assert school_app_reads(school) == asked
    service.clock.now += RECHECK_SECONDS
    service.timetable(CHILD, reference=WEDNESDAY)
    assert school_app_reads(school) == asked + 1


def test_a_restart_keeps_the_remembered_source(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    asked = school_app_reads(school)
    again = connection_service(Store(tmp_path / "data"), service.id, client_factory(school))
    again.clock = Clock()
    result = again.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert school_app_reads(school) == asked + 1
    again.timetable(CHILD, reference=WEDNESDAY, week_offset=1)
    assert school_app_reads(school) == asked + 1


def test_the_child_page_is_read_once_for_several_weeks(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    for offset in (0, 1, 2):
        service.timetable(CHILD, reference=WEDNESDAY, week_offset=offset)
    assert len(school.paths(PAGE)) == 1


def test_the_school_app_takes_over_again_once_it_lists_lessons(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    school.school_lessons = True
    service.clock.now += RECHECK_SECONDS
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "school-app"
    assert [lesson["subject_code"] for lesson in result["lessons"]] == ["D"]
    assert remembered(service) == ""


def test_the_school_app_takes_over_again_once_slots_appear(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    school.slots = True
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "school-app"
    assert result["no_lessons"] is True
    assert remembered(service) == ""


def test_a_school_that_keeps_its_plan_in_the_school_app_never_asks_the_old_module(tmp_path):
    school = TimeTableSchool(school_lessons=True)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "school-app"
    assert school.paths(PAGE) == []
    assert school.paths(DATA) == []


def test_an_empty_week_with_slots_is_honestly_empty_without_the_old_module(tmp_path):
    school = TimeTableSchool(slots=True)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["lessons"] == []
    assert result["no_lessons"] is True
    assert result["source"] == "school-app"
    assert school.paths(PAGE) == []


def test_both_sources_without_lessons_give_an_explicit_empty_week(tmp_path):
    school = TimeTableSchool(time_table=EMPTY)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["lessons"] == []
    assert result["no_lessons"] is True
    assert remembered(service) in (None, "")
    assert len(school.paths(DATA)) == 1


def test_a_missing_time_table_module_leaves_the_empty_school_app_week(tmp_path):
    school = TimeTableSchool(time_table=ABSENT)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["no_lessons"] is True
    assert school.paths(DATA) == []


def test_a_refusal_of_the_time_table_data_is_an_error_but_no_sign_in_failure(tmp_path):
    service = make(tmp_path, TimeTableSchool(time_table=FORBIDDEN))
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert not isinstance(caught.value, (LoginError, TwoFactorError))
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY
    assert caught.value.detail["source"] == "time-table"
    assert caught.value.detail["status"] == 403
    assert remembered(service) in (None, "")


def test_an_answer_in_an_unknown_shape_is_an_error_with_a_diagnosis(tmp_path):
    service = make(tmp_path, TimeTableSchool(time_table=ODD))
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY
    assert caught.value.detail["source"] == "time-table"
    assert "rows: array len 1 of object" in caught.value.detail["shape"]


def test_a_server_error_of_the_time_table_data_is_a_data_error_not_an_outage(tmp_path):
    service = make(tmp_path, TimeTableSchool(time_table=BROKEN))
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY
    assert caught.value.detail["status"] == 500


def test_a_child_page_that_lists_only_other_children_is_never_read(tmp_path):
    school = TimeTableSchool(options=(OTHER_CHILD, ("44444444-4444-4444-8444-444444444444", "Sam Anders")))
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.detail["options"] == 2
    assert school.paths(DATA) == []


def test_the_matching_option_is_chosen_among_siblings(tmp_path):
    school = TimeTableSchool(options=(OTHER_CHILD, (OWN_OPTION, "Muster, Kim (5A)")))
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    assert school.paths(DATA)[-1]["childId"] == OWN_OPTION


def test_a_page_without_a_child_select_is_read_without_a_child_for_a_single_child(tmp_path):
    school = TimeTableSchool(options=None)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert len(result["lessons"]) == len(WEEK_PLAN)
    asked = school.paths(DATA)[-1]
    assert "childId" not in asked
    assert '"child"' not in asked["filter"]


def test_a_page_without_a_child_select_is_not_read_for_two_listed_children(tmp_path):
    sibling = {"id": 500002, "forename": "Sam", "surname": "Muster", "courses": [{"id": 7002}]}
    school = TimeTableSchool(options=None, extra_children=[sibling])
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.detail == {"source": "time-table", "child_select": False, "options": 0, "listed_children": 2}
    assert school.paths(DATA) == []


def test_a_child_the_school_account_does_not_list_is_refused():
    options = [Child("a", "Robin Anders")]
    assert matching_option(options, CHILD, "Kim Muster", 2) is None
    assert matching_option(options, CHILD, "Kim Muster", 1) is None
    assert matching_option([Child("a", "Kim Muster"), Child("b", "Kim Muster")], CHILD, "Kim Muster", 2) is None


def test_one_option_for_one_listed_child_needs_agreeing_names_or_a_missing_name():
    assert matching_option([Child("a", "Muster, Kimberly")], CHILD, "Kim Muster", 1).child_id == "a"
    assert matching_option([Child("a", "Muster, Sam")], CHILD, "Kim Muster", 1) is None
    assert matching_option([Child("a", "MUSTER, kim")], CHILD, "Kim Muster", 1).child_id == "a"
    assert matching_option([Child("a", "Robin Anders")], CHILD, "", 1).child_id == "a"
    assert matching_option([Child("a", "Muster, Kimberly")], CHILD, "Kim Muster", 2) is None


def test_an_id_match_with_a_contradicting_name_is_not_accepted():
    assert matching_option([Child(CHILD, "Robin Anders")], CHILD, "Kim Muster", 1) is None
    assert matching_option([Child(CHILD, "Robin Anders")], CHILD, "Kim Muster", 2) is None
    assert matching_option([Child(CHILD, "Muster, Kim")], CHILD, "Kim Muster", 2).child_id == CHILD
    assert matching_option([Child(CHILD, "Other Name")], CHILD, "", 2).child_id == CHILD
    assert matching_option([Child(CHILD, "Muster, Sam")], CHILD, "Kim Muster", 1) is None
    assert matching_option([Child(CHILD, "Muster, Kimberly")], CHILD, "Kim Muster", 2).child_id == CHILD


def test_a_sibling_with_the_same_surname_never_delivers_its_lessons(tmp_path):
    school = TimeTableSchool(options=(("55555555-5555-4555-8555-555555555555", "Muster, Sam"),))
    service = make(tmp_path, school)
    with pytest.raises(DataError):
        service.timetable(CHILD, reference=WEDNESDAY)
    assert school.paths(DATA) == []


def test_a_single_option_of_another_child_never_delivers_its_lessons(tmp_path):
    school = TimeTableSchool(options=(OTHER_CHILD,))
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.detail == {"source": "time-table", "child_select": True, "options": 1, "listed_children": 1}
    assert school.paths(DATA) == []
    assert remembered(service) in (None, "")


def test_names_compare_as_words_in_any_order():
    assert name_words("Muster, Kim") == name_words("Kim Muster")
    assert name_words("") == frozenset()


def test_the_course_filter_still_applies_to_a_week_from_the_old_module(tmp_path):
    from app.store import edit_config

    service = make(tmp_path, TimeTableSchool())
    chosen = {CHILD: {"chosen": ["D|KLE"], "known": ["D|KLE", "MA|BRA"]}}
    edit_config(service.store, lambda config: config.update(course_filters=chosen))
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["courses"]["chosen"] is True
    assert result["courses"]["hidden"] == 2
    assert "MA" not in {lesson["subject_code"] for lesson in result["lessons"]}
    assert len(result["lessons"]) == len(WEEK_PLAN) - 2


def test_a_login_page_instead_of_the_time_table_is_a_session_problem_not_an_empty_week(tmp_path):
    school = TimeTableSchool(page=PAGE_LOGIN)
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == SCHOOL_APP_EXPIRED_KEY
    assert not isinstance(caught.value, (LoginError, TwoFactorError))
    with pytest.raises(DataError):
        service.timetable(CHILD, reference=WEDNESDAY)
    assert len(school.paths(PAGE)) == 2


def test_a_remembered_source_survives_a_login_page_and_is_read_again_once_signed_in(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    service.clock.now += MATCH_SECONDS + 1
    school.page = PAGE_LOGIN
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == SCHOOL_APP_EXPIRED_KEY
    assert remembered(service) == "time-table"
    school.page = "shown"
    service.clock.now += 60
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert len(result["lessons"]) == len(WEEK_PLAN)


def test_a_cached_failure_is_raised_as_a_fresh_error(tmp_path):
    service = make(tmp_path, TimeTableSchool(options=(OTHER_CHILD,)))
    errors = []
    for _ in range(2):
        with pytest.raises(DataError) as caught:
            service.timetable(CHILD, reference=WEDNESDAY)
        errors.append(caught.value)
    assert errors[0] is not errors[1]
    assert errors[0].detail == errors[1].detail
    assert errors[0].message_key == errors[1].message_key


@pytest.mark.parametrize("page", [PAGE_FORBIDDEN, PAGE_ROOT])
def test_a_time_table_page_the_account_does_not_get_counts_as_absent(tmp_path, page):
    school = TimeTableSchool(page=page)
    service = make(tmp_path, school)
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["no_lessons"] is True
    assert result["source"] == "school-app"
    assert school.paths(DATA) == []


def test_an_absent_module_is_not_asked_again_on_every_poll(tmp_path, caplog):
    school = TimeTableSchool(page=PAGE_FORBIDDEN)
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        for offset in (0, 1, 0):
            assert service.timetable(CHILD, reference=WEDNESDAY, week_offset=offset)["no_lessons"] is True
    assert len(school.paths(PAGE)) == 1
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    service.clock.now += MATCH_SECONDS + 1
    service.timetable(CHILD, reference=WEDNESDAY)
    assert len(school.paths(PAGE)) == 2


def test_a_page_at_the_right_address_that_is_no_time_table_is_an_error(tmp_path):
    school = TimeTableSchool(page=PAGE_FOREIGN)
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == TIMETABLE_SHAPE_KEY
    assert school.paths(DATA) == []


def test_a_failed_match_is_kept_for_a_while_and_logged_once(tmp_path, caplog):
    school = TimeTableSchool(options=(OTHER_CHILD,))
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        for _ in range(3):
            with pytest.raises(DataError):
                service.timetable(CHILD, reference=WEDNESDAY)
    assert len(school.paths(PAGE)) == 1
    assert len([record for record in caplog.records if record.levelno >= logging.WARNING]) == 1
    service.clock.now += MATCH_SECONDS + 1
    school.options = ((OWN_OPTION, "Muster, Kim"),)
    assert service.timetable(CHILD, reference=WEDNESDAY)["source"] == "time-table"


def test_every_read_carries_the_school_vacations(tmp_path):
    school = TimeTableSchool(vacations=VACATIONS)
    service = make(tmp_path, school)
    first = service.timetable(CHILD, reference=WEDNESDAY)
    second = service.timetable(CHILD, reference=WEDNESDAY, week_offset=1)
    expected = [{"name": "Herbstferien", "start_date": "2026-10-17", "end_date": "2026-10-31"}]
    assert first["source"] == second["source"] == "time-table"
    assert first["vacations"] == expected
    assert second["vacations"] == expected


def test_a_read_that_outlives_an_account_switch_does_not_store_its_source(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)

    def switch():
        entry = service.store.load_config()
        edit_config_switch(service, int(entry.get("login_revision") or 0) + 1)

    school.on_data = switch
    service.timetable(CHILD, reference=WEDNESDAY)
    assert remembered(service) in (None, "")


def edit_config_switch(service, revision):
    from app.store import edit_config

    edit_config(service.store, lambda config: config.update(login_revision=revision))


def test_the_diagnosis_logged_for_a_refusal_carries_no_page_title(tmp_path, caplog):
    service = make(tmp_path, TimeTableSchool(time_table=FORBIDDEN))
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        with pytest.raises(DataError):
            service.timetable(CHILD, reference=WEDNESDAY)
    assert "Riverside" not in caplog.text
    assert "Zugriff" not in caplog.text


PRIVATE = ("Kim", "Muster", CHILD, OWN_OPTION, "Robin", "Anders", "7001", "R101", "KLE")


def source_lines(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "app.timetable_source"]


def assert_private_free(lines):
    for line in lines:
        for value in PRIVATE:
            assert value not in line, (value, line)


def test_the_fallback_leaves_one_log_line_per_step_without_names_or_ids(tmp_path, caplog):
    service = make(tmp_path, TimeTableSchool())
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        service.timetable(CHILD, reference=WEDNESDAY)
    lines = source_lines(caplog)
    school = "school#%s " % service.id
    assert school + "school app timetable empty (entries 0, slots 0), trying the time-table module" in lines
    assert school + "time-table child select: present, options 1, listed children 1, matched yes" in lines
    assert school + "time-table data answered 200 application/json, lessons 6 for the week of 07.09.2026" in lines
    assert school + "timetable source: time-table (the school app lists no lessons and no slots)" in lines
    assert school + "timetable source time-table chosen for the week of 07.09.2026" in lines
    assert_private_free(lines)


def test_a_repeated_poll_does_not_repeat_the_same_line(tmp_path, caplog):
    service = make(tmp_path, TimeTableSchool(time_table=EMPTY))
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        for _ in range(3):
            service.timetable(CHILD, reference=WEDNESDAY)
    lines = source_lines(caplog)
    assert len([line for line in lines if "trying the time-table module" in line]) == 1
    assert len([line for line in lines if "lists no lessons either, the week of 07.09.2026 has no lessons" in line]) == 1


def test_an_honest_empty_week_with_slots_is_logged(tmp_path, caplog):
    service = make(tmp_path, TimeTableSchool(slots=True))
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        service.timetable(CHILD, reference=WEDNESDAY)
    assert "school#%s school app timetable empty (entries 0, slots 1) for the week of 07.09.2026, no lessons that week" % service.id in source_lines(caplog)


@pytest.mark.parametrize("answer, key, fragment", [
    (FORBIDDEN, TIMETABLE_SHAPE_KEY, '"status": 403'),
    (BROKEN, TIMETABLE_SHAPE_KEY, '"status": 500'),
    (ODD, TIMETABLE_SHAPE_KEY, '"shape": ["(root): object keys 1", "rows: array len 1 of object"'),
])
def test_a_refused_or_unknown_answer_is_logged_with_its_diagnosis(tmp_path, caplog, answer, key, fragment):
    service = make(tmp_path, TimeTableSchool(time_table=answer))
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        with pytest.raises(DataError):
            service.timetable(CHILD, reference=WEDNESDAY)
    failures = [line for line in source_lines(caplog) if "time-table module unreadable" in line]
    assert len(failures) == 1
    assert "(%s)" % key in failures[0]
    assert fragment in failures[0]
    assert_private_free(source_lines(caplog))


def test_an_unmatched_child_select_is_logged_without_names(tmp_path, caplog):
    school = TimeTableSchool(options=(OTHER_CHILD, ("44444444-4444-4444-8444-444444444444", "Sam Anders")))
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        with pytest.raises(DataError):
            service.timetable(CHILD, reference=WEDNESDAY)
    lines = source_lines(caplog)
    assert "school#%s time-table child select: present, options 2, listed children 1, matched no" % service.id in lines
    assert any('"options": 2' in line and "unreadable" in line for line in lines)
    assert_private_free(lines)


def test_a_restart_names_the_remembered_source_once(tmp_path, caplog):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    again = connection_service(Store(tmp_path / "data"), service.id, client_factory(school))
    again.clock = Clock()
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        again.timetable(CHILD, reference=WEDNESDAY)
        again.timetable(CHILD, reference=WEDNESDAY, week_offset=1)
    lines = [line for line in source_lines(caplog) if "remembered" in line]
    assert lines == ["school#%s timetable source time-table remembered, the school app is asked again every 3600 s" % service.id]


def test_the_connection_counts_the_children_its_school_account_lists(tmp_path):
    sibling = {"id": 500002, "forename": "Sam", "surname": "Muster", "courses": [{"id": 7002}]}
    assert make(tmp_path / "one", TimeTableSchool()).listed_child_count() == 1
    assert make(tmp_path / "two", TimeTableSchool(extra_children=[sibling])).listed_child_count() == 2


def test_counting_the_listed_children_reuses_a_fresh_list(tmp_path):
    school = TimeTableSchool()
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    asked = len(school.paths("/iserv/dieschulapp/api/1.0/users/me"))
    assert service.listed_child_count() == 1
    assert len(school.paths("/iserv/dieschulapp/api/1.0/users/me")) == asked


def current_timetable_reads(school):
    return len(school.paths("/iserv/dieschulapp/api/1.0/current-timetable/"))


def source_changes(caplog):
    return [line for line in source_lines(caplog) if "timetable source:" in line]


def test_a_school_app_that_refuses_the_timetable_hands_the_week_to_the_time_table_module(tmp_path, caplog):
    school = TimeTableSchool(school_app=SCHOOL_APP_REFUSES, slots=True)
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert len(result["lessons"]) == len(WEEK_PLAN)
    assert remembered(service) == "time-table"
    school_line = "school#%s " % service.id
    assert school_line + "school app refuses the timetable (403), trying the time-table module" in source_lines(caplog)
    assert source_changes(caplog) == [school_line + "timetable source: time-table (the school app refuses the timetable)"]
    assert_private_free(source_lines(caplog))


def test_a_school_app_timetable_that_is_not_released_is_never_asked(tmp_path, caplog):
    school = TimeTableSchool(released=False, school_lessons=True, slots=True)
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert len(result["lessons"]) == len(WEEK_PLAN)
    assert school_app_reads(school) == 0
    assert remembered(service) == "time-table"
    school_line = "school#%s " % service.id
    assert school_line + "school app does not release the timetable, trying the time-table module" in source_lines(caplog)
    assert source_changes(caplog) == [school_line + "timetable source: time-table (the school app does not release the timetable)"]


def test_a_refusing_school_app_is_asked_again_only_when_the_recheck_is_due(tmp_path, caplog):
    school = TimeTableSchool(school_app=SCHOOL_APP_REFUSES, slots=True)
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        service.timetable(CHILD, reference=WEDNESDAY)
        asked = current_timetable_reads(school)
        for offset in (1, 0, 1):
            assert service.timetable(CHILD, reference=WEDNESDAY, week_offset=offset)["source"] == "time-table"
        assert current_timetable_reads(school) == asked
        service.clock.now += RECHECK_SECONDS
        assert service.timetable(CHILD, reference=WEDNESDAY)["source"] == "time-table"
    assert current_timetable_reads(school) == asked + 1
    assert remembered(service) == "time-table"
    assert len(source_changes(caplog)) == 1


def test_a_restart_with_a_refusing_school_app_keeps_the_source_without_switching_back(tmp_path, caplog):
    school = TimeTableSchool(school_app=SCHOOL_APP_REFUSES, slots=True)
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    again = connection_service(Store(tmp_path / "data"), service.id, client_factory(school))
    again.clock = Clock()
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        assert again.timetable(CHILD, reference=WEDNESDAY)["source"] == "time-table"
        assert again.timetable(CHILD, reference=WEDNESDAY, week_offset=1)["source"] == "time-table"
    assert remembered(again) == "time-table"
    assert source_changes(caplog) == []


def test_the_school_app_takes_over_again_once_it_stops_refusing(tmp_path):
    school = TimeTableSchool(school_app=SCHOOL_APP_REFUSES, slots=True)
    service = make(tmp_path, school)
    service.timetable(CHILD, reference=WEDNESDAY)
    school.school_app = SCHOOL_APP_ANSWERS
    school.school_lessons = True
    service.clock.now += RECHECK_SECONDS
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "school-app"
    assert [lesson["subject_code"] for lesson in result["lessons"]] == ["D"]
    assert remembered(service) == ""


def test_a_refusing_school_app_without_a_time_table_module_stays_an_error(tmp_path):
    school = TimeTableSchool(school_app=SCHOOL_APP_REFUSES, slots=True, time_table=ABSENT)
    service = make(tmp_path, school)
    with pytest.raises(DataError) as caught:
        service.timetable(CHILD, reference=WEDNESDAY)
    assert caught.value.message_key == TIMETABLE_UNREADABLE_KEY
    assert caught.value.detail["status"] == 403
    assert remembered(service) in (None, "")


def test_the_withheld_school_keeps_its_timetable_and_shows_the_changes(tmp_path, caplog):
    school = withheld_school()
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO):
        assert service.check_connection() == "ok"
        assert service.modules()["modules"][modules.TIMETABLE] is True
        assert service.timetable_available() is True
        result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    assert result["no_lessons"] is False
    assert len(result["lessons"]) == len(MOVED_WEEK_PLAN) == 41
    assert {lesson["teacher_code"] for lesson in result["lessons"]} == {""}
    assert school_app_reads(school) == 0
    changed = {(lesson["date"], lesson["period"]): lesson for lesson in result["lessons"] if lesson["change_kind"]}
    assert sorted((key, lesson["subject_code"], lesson["change_kind"], lesson["changed_fields"]) for key, lesson in changed.items()) == [
        (("07.09.2026", 4), "M", "changed", ["subject", "room"]),
        (("08.09.2026", 2), "Eth", "changed", ["class"]),
        (("08.09.2026", 6), "L", "cancelled", []),
        (("09.09.2026", 3), "Bio", "changed", []),
        (("10.09.2026", 5), "L", "changed", ["subject"]),
        (("11.09.2026", 4), "Eth", "changed", ["class"]),
        (("11.09.2026", 6), "M", "cancelled", []),
    ]
    assert changed[("07.09.2026", 4)]["previous"]["subject"] == "Mu"
    assert changed[("10.09.2026", 5)]["previous"]["subject"] == "E"
    assert result["change_count"] == len(changed) == len(result["changes"]) == len(MOVED_WEEK_CHANGES) == 7


def test_the_moved_week_shows_both_moves_the_note_and_the_hidden_substitutes(tmp_path):
    result = make(tmp_path, withheld_school()).timetable(CHILD, reference=WEDNESDAY)
    slots = {(lesson["date"], lesson["period"], lesson["subject_code"]): lesson for lesson in result["lessons"]}
    assert slots[("08.09.2026", 6, "L")]["moved_to"] == {"date": "10.09.2026", "period": 5, "period_end": 5}
    assert slots[("10.09.2026", 5, "L")]["moved_from"] == {"date": "08.09.2026", "period": 6, "period_end": 6}
    assert slots[("11.09.2026", 6, "M")]["moved_to"] == {"date": "07.09.2026", "period": 4, "period_end": 4}
    assert slots[("07.09.2026", 4, "M")]["moved_from"] == {"date": "11.09.2026", "period": 6, "period_end": 6}
    assert slots[("08.09.2026", 6, "L")]["change_note"] == "Material mitbringen"
    for key in (("08.09.2026", 2, "Eth"), ("09.09.2026", 3, "Bio"), ("11.09.2026", 4, "Eth")):
        assert slots[key]["teacher_hidden"] is True
        assert slots[key]["no_details"] is False
        assert slots[key]["teacher_code"] == ""
        assert slots[key]["moved_from"] is None
    assert slots[("08.09.2026", 2, "Eth")]["classes"] == "5A, 5B, 5C"
    assert slots[("08.09.2026", 2, "Eth")]["previous"]["class"] == "5A"
    assert sum(1 for item in result["changes"] if item["moved"]) == 4
    unchanged = [lesson for lesson in result["lessons"] if not lesson["change_kind"]]
    assert all(lesson["moved_to"] is None and lesson["change_note"] == "" for lesson in unchanged)


def test_the_withheld_school_logs_no_warning_and_keeps_the_module(tmp_path, caplog):
    school = withheld_school()
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO):
        service.check_connection()
        service.timetable(CHILD, reference=WEDNESDAY)
    assert [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING] == []
    assert "missing: timetable" not in caplog.text


def test_a_registry_stored_by_the_old_rule_is_corrected_at_the_next_sign_in(tmp_path):
    school = withheld_school()
    service = make(tmp_path, school)
    old = modules.default_registry()
    old["modules"][modules.TIMETABLE] = False
    old["modules"][modules.CONFERENCES] = False
    old["checked_at"] = 1_790_000_000
    old["probes"] = {modules.TIMETABLE: {
        "path": "/iserv/time-table/", "status": 200, "content_type": "text/html",
        "length": 28690, "final_path": "/iserv/time-table/", "verdict": modules.AVAILABLE,
    }}
    service.store.save_modules(old)
    assert service.timetable_available() is False
    assert service.check_connection() == "ok"
    assert service.timetable_available() is True
    assert service.timetable(CHILD, reference=WEDNESDAY)["source"] == "time-table"


def test_a_fresh_install_with_the_release_off_offers_the_timetable_before_and_after_the_probe(tmp_path):
    school = withheld_school()
    service = make(tmp_path, school)
    assert service.stored_modules()["checked_at"] == 0
    assert service.timetable_available() is True
    assert service.check_connection() == "ok"
    assert service.stored_modules()["checked_at"] > 0
    assert service.timetable_available() is True


def child_list_without_the_page(school, service, courses_known=False):
    assert service.check_connection() == "ok"
    if courses_known:
        assert service.listed_child_count() == 1
    school.me_failures = 1
    assert [child["child_id"] for child in service.children()] == [CHILD]
    assert service._timetable_page_denied is True


def test_a_page_that_refuses_the_child_list_leaves_a_timetable_the_school_app_serves(tmp_path):
    school = TimeTableSchool(options=None, school_lessons=True, sick_notes=True)
    service = make(tmp_path, school)
    child_list_without_the_page(school, service, courses_known=True)
    assert service.stored_modules()["probes"][modules.TIMETABLE]["path"].startswith(modules.DSA_API)
    assert service.timetable_available() is True
    result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "school-app"
    assert [lesson["subject_code"] for lesson in result["lessons"]] == ["D"]


def test_a_page_that_refuses_the_child_list_hides_a_timetable_only_the_page_serves(tmp_path):
    school = TimeTableSchool(options=None, school_app=SCHOOL_APP_REFUSES, sick_notes=True)
    service = make(tmp_path, school)
    child_list_without_the_page(school, service)
    assert service.stored_modules()["probes"][modules.TIMETABLE]["path"] == PAGE
    assert service.timetable_available() is False


def test_a_child_without_course_ids_reads_the_time_table_week_with_its_changes(tmp_path, caplog):
    record = {
        "date": "07.09.2026", "period": 1, "periodStart": 1, "periodEnd": 1,
        "origSubject": "D", "substitutionSubject": "D", "origTeacher": None, "substitutionTeacher": None,
        "origRoom": "R101", "substitutionRoom": "R305", "origClass": ["5A"], "substitutionClass": ["5A"],
        "text": "", "change_types": ["1", "4"],
    }
    school = TimeTableSchool(me_courses=False, released=False, school_app=SCHOOL_APP_REFUSES, changes=[record])
    service = make(tmp_path, school)
    with caplog.at_level(logging.INFO, logger="app.timetable_source"):
        result = service.timetable(CHILD, reference=WEDNESDAY)
    assert result["source"] == "time-table"
    lesson = next(item for item in result["lessons"] if item["date"] == "07.09.2026" and item["period"] == 1)
    assert (lesson["room"], lesson["change_kind"], lesson["changed_fields"]) == ("R305", "changed", ["room"])
    assert [(item["date"], item["period"], item["room"]) for item in result["changes"]] == [("07.09.2026", 1, "R305")]
    assert school_app_reads(school) == 0
    assert "school#%s time-table data answered 200 application/json, lessons 6 for the week of 07.09.2026" % service.id in source_lines(caplog)


def test_a_refused_child_list_hides_the_timetable_when_no_known_child_has_course_ids(tmp_path):
    school = TimeTableSchool(options=None, school_lessons=True, sick_notes=True)
    service = make(tmp_path, school)
    child_list_without_the_page(school, service)
    assert modules.school_app_timetable_served(service.stored_modules()) is True
    assert service._child_service.course_ids_known() is False
    assert service.timetable_available() is False


def test_a_moved_week_with_named_teachers_shows_no_replaced_teacher_at_a_changed_lesson(tmp_path):
    plan = tuple((day, period, subject, "T-" + subject, room) for day, period, subject, _teacher, room in MOVED_WEEK_PLAN)
    result = make(tmp_path, withheld_school(plan=plan)).timetable(CHILD, reference=WEDNESDAY)
    slots = {(lesson["date"], lesson["period"], lesson["subject_code"]): lesson for lesson in result["lessons"]}
    for key, regular in ((("07.09.2026", 4, "M"), "T-Mu"), (("10.09.2026", 5, "L"), "T-E"), (("09.09.2026", 3, "Bio"), "T-Bio")):
        lesson = slots[key]
        assert lesson["teacher_code"] == "", key
        assert lesson["teacher_hidden"] is True, key
        assert "teacher" in lesson["changed_fields"], key
        assert lesson["previous"]["teacher"] == regular, key
    assert slots[("08.09.2026", 6, "L")]["teacher_code"] == "T-L"
    assert slots[("07.09.2026", 1, "BK")]["teacher_code"] == "T-BK"


def test_a_hidden_teacher_change_of_an_unchosen_same_subject_course_is_neither_listed_nor_counted(tmp_path):
    plan = WEEK_PLAN_WITH_TWO_SPORT_COURSES
    record = {
        "date": "09.09.2026", "period": 3, "periodStart": 3, "periodEnd": 3,
        "origSubject": "SP", "substitutionSubject": "SP", "origTeacher": "OTT", "substitutionTeacher": None,
        "origRoom": "GYM2", "substitutionRoom": "GYM2", "origClass": ["5A"], "substitutionClass": ["5A"],
        "text": "", "change_types": ["2"],
    }
    service = make(tmp_path, TimeTableSchool(plan=plan, changes=[record]))
    full = service.timetable(CHILD, reference=WEDNESDAY)
    assert full["change_count"] == len(full["changes"]) == 1
    service.save_course_filter(CHILD, ["SP|FUC"], ["SP|FUC", "SP|OTT"])
    shown = service.timetable(CHILD, reference=WEDNESDAY)
    marked = [lesson for lesson in shown["lessons"] if lesson["change_kind"]]
    assert shown["change_count"] == len(marked) == len(shown["changes"]) == 0
    service.save_course_filter(CHILD, ["SP|OTT"], ["SP|FUC", "SP|OTT"])
    other = service.timetable(CHILD, reference=WEDNESDAY)
    assert other["change_count"] == len(other["changes"]) == 1
