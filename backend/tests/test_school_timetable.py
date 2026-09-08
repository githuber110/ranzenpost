import json
import pathlib
from datetime import date

import pytest

from app.iserv.errors import DataError
from app.iserv.models import Child, Lesson, TimetableWeek
from app.service import TIMETABLE_UNREADABLE_KEY, IServService
from app.store import Store

FIXTURE = json.loads(
    (pathlib.Path(__file__).resolve().parent / "fixtures" / "dsa_current_timetable.json").read_text(encoding="utf-8")
)
ME = {
    "id": 900,
    "displayname": "Muster Jo",
    "roles": ["guardian"],
    "children": [
        {
            "id": 500001,
            "displayname": "Muster Kim",
            "forename": "Kim",
            "surname": "Muster",
            "mainCourse": {"id": 7001, "name": "Klasse 01D", "externalId": "klasse.01d"},
            "courses": [{"id": 7001, "name": "Klasse 01D", "type": "class"}, {"id": 7002, "name": "TEAM 1", "type": "course"}],
        }
    ],
}


class LegacyClient:
    def __init__(self, url):
        self.url = url
        self.base_url = url
        self.session = object()
        self.timetable_calls = []

    def login(self, username, password, code_provider):
        return self

    def is_authenticated(self):
        return True

    def get_children(self):
        return [Child("uuid-old", "Kim Muster")]

    def get_timetable(self, child_id, reference=None):
        self.timetable_calls.append((child_id, reference))
        lesson = Lesson("07.09.2026", 1, 1, "D", "BEI", "R1", "1a")
        return TimetableWeek("07.09.2026", "13.09.2026", "old", [lesson], [lesson], [])


class SchoolApp:
    def __init__(self, me=ME, timetable=FIXTURE, settings=None, me_fails=False):
        self.me = me
        self.timetable = timetable
        self.settings = settings if settings is not None else {
            "timetable_availableForGuardiansAndStudents": True,
            "substitutions_availableForGuardiansAndStudents": False,
        }
        self.me_fails = me_fails
        self.timetable_calls = []
        self.settings_calls = 0

    def me_with_children(self):
        if self.me_fails:
            raise RuntimeError("down")
        return self.me

    def current_timetable(self, reference, course_ids, substitutions=False):
        self.timetable_calls.append((reference, list(course_ids), substitutions))
        return self.timetable

    def school_settings(self):
        self.settings_calls += 1
        return self.settings

    def period_times(self):
        return {"1": "08:00"}

    def sick_note_children(self):
        return []

    def students(self):
        return []


def make(tmp_path, school_app=None, config=None):
    store = Store(tmp_path / "data")
    store.save_config(dict({"school_url": "https://school.example"}, **(config or {})))
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    clients = []

    def factory(url):
        client = LegacyClient(url)
        clients.append(client)
        return client

    service = IServService(store, client_factory=factory)
    app = school_app if school_app is not None else SchoolApp()
    service._dsa = lambda: app
    return service, store, app, clients


def test_children_come_from_the_school_account_with_their_courses(tmp_path):
    service, _, _, _ = make(tmp_path)
    children = service.children()
    assert children == [{
        "child_id": "500001",
        "student_id": 500001,
        "name": "Kim Muster",
        "class_name": "1D",
        "class_full": "Klasse 01D",
        "class_code": "klasse.01d",
        "course_ids": [7001, 7002],
    }]


def test_the_name_reads_forename_first_even_though_the_school_lists_surname_first(tmp_path):
    service, _, _, _ = make(tmp_path)
    assert service.children()[0]["name"] == "Kim Muster"


def test_a_stored_child_under_the_old_id_is_moved_to_the_school_account_id_by_name(tmp_path):
    service, store, _, _ = make(tmp_path, config={"children": [{"child_id": "uuid-old", "name": "Muster Kim", "class_name": "1d"}]})
    service.children()
    stored = store.load_config()["children"]
    assert stored == [{"child_id": "500001", "name": "Muster Kim", "class_name": "1D"}]


def test_a_calendar_subscription_follows_the_child_to_its_new_id(tmp_path):
    service, store, _, _ = make(tmp_path, config={"children": [{"child_id": "uuid-old", "name": "Kim Muster"}]})
    store.save_calendar_subscriptions({"subscriptions": [
        {"id": "sub1", "child_id": "uuid-old", "label": "Kim", "components": ["timetable"], "token": "t", "color": ""},
        {"id": "sub2", "child_id": "uuid-other", "label": "Alex", "components": ["timetable"], "token": "u", "color": ""},
    ]})
    service.children()
    entries = store.load_calendar_subscriptions()["subscriptions"]
    assert [entry["child_id"] for entry in entries] == ["500001", "uuid-other"]


def test_a_stored_child_that_matches_no_current_child_is_left_alone(tmp_path):
    service, store, _, _ = make(tmp_path, config={"children": [{"child_id": "uuid-other", "name": "Alex Anders"}]})
    service.children()
    stored = store.load_config()["children"]
    assert stored[0] == {"child_id": "uuid-other", "name": "Alex Anders"}
    assert [child["child_id"] for child in stored[1:]] == ["500001"], "the listed child must become known too"


def test_when_the_school_account_cannot_be_read_the_old_way_still_works(tmp_path):
    service, _, _, clients = make(tmp_path, school_app=SchoolApp(me_fails=True))
    children = service.children()
    assert [child["child_id"] for child in children] == ["uuid-old"]


def test_the_timetable_is_read_from_the_school_app_with_the_childs_courses(tmp_path):
    service, _, app, clients = make(tmp_path)
    result = service.timetable("500001", reference=date(2026, 9, 9))
    assert app.timetable_calls == [(date(2026, 9, 9), [7001, 7002], False)]
    assert all(client.timetable_calls == [] for client in clients), "the old timetable page was consulted"
    assert result["start_date"] == "07.09.2026"
    assert result["end_date"] == "13.09.2026"
    assert len(result["lessons"]) == 4


def test_the_week_offset_moves_the_requested_date(tmp_path):
    service, _, app, _ = make(tmp_path)
    service.timetable("500001", reference=date(2026, 9, 9), week_offset=1)
    assert app.timetable_calls[0][0] == date(2026, 9, 16)


def test_every_lesson_keeps_the_old_contract_and_gains_the_new_fields(tmp_path):
    service, _, _, _ = make(tmp_path)
    lesson = service.timetable("500001", reference=date(2026, 9, 7))["lessons"][0]
    for key in ("date", "day_of_week", "period", "subject_code", "subject_label", "color", "teacher_code", "teacher_label", "room", "change_kind", "start_time"):
        assert key in lesson
    assert lesson["subject_code"] == "D"
    assert lesson["subject_label"] == "Deutsch"
    assert lesson["color"] == "#0f3beb"
    assert lesson["teacher_label"] == "Katrin Beispiel"
    assert lesson["teacher_surname"] == "Beispiel"
    assert lesson["start_time"] == "08:00"
    assert lesson["end_time"] == "08:45"
    assert lesson["change_kind"] == ""


def test_a_colour_the_user_chose_is_not_overwritten_by_the_school_colour(tmp_path):
    service, _, _, _ = make(tmp_path, config={"subjects": {"D": {"label": "Deutsch", "color": "#123456", "color_source": "user"}}})
    lesson = service.timetable("500001", reference=date(2026, 9, 7))["lessons"][0]
    assert lesson["color"] == "#123456"


def test_the_answer_says_whether_the_school_releases_substitutions(tmp_path):
    service, _, _, _ = make(tmp_path)
    assert service.timetable("500001", reference=date(2026, 9, 7))["substitutions_released"] is False


def test_substitutions_are_only_requested_when_the_school_releases_them(tmp_path):
    app = SchoolApp(settings={"timetable_availableForGuardiansAndStudents": True, "substitutions_availableForGuardiansAndStudents": True})
    service, _, _, _ = make(tmp_path, school_app=app)
    service.timetable("500001", reference=date(2026, 9, 7))
    assert app.timetable_calls[0][2] is True


def test_vacations_travel_with_the_answer(tmp_path):
    service, _, _, _ = make(tmp_path)
    assert service.timetable("500001", reference=date(2026, 9, 7))["vacations"] == [
        {"name": "Herbstferien", "start_date": "2026-10-17", "end_date": "2026-10-31"}
    ]


def test_an_unreadable_timetable_is_a_failure_not_an_empty_week(tmp_path):
    service, _, _, _ = make(tmp_path, school_app=SchoolApp(timetable=None))
    with pytest.raises(DataError) as caught:
        service.timetable("500001", reference=date(2026, 9, 7))
    assert caught.value.message_key == TIMETABLE_UNREADABLE_KEY


def test_a_child_the_school_account_does_not_know_falls_back_to_the_old_timetable(tmp_path):
    service, _, app, clients = make(tmp_path)
    service.timetable("uuid-old", reference=date(2026, 9, 7))
    assert app.timetable_calls == []
    assert clients[0].timetable_calls[0][0] == "uuid-old"


def test_the_school_settings_are_not_fetched_again_for_every_week(tmp_path):
    service, _, app, _ = make(tmp_path)
    for offset in (0, 1, 2):
        service.timetable("500001", reference=date(2026, 9, 7), week_offset=offset)
    assert app.settings_calls == 1


def test_no_change_is_invented_when_the_school_delivers_no_substitutions(tmp_path):
    service, _, _, _ = make(tmp_path)
    result = service.timetable("500001", reference=date(2026, 9, 7))
    assert result["change_count"] == 0
    assert all(lesson["change_kind"] == "" for lesson in result["lessons"])
