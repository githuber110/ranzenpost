from collections import namedtuple
from datetime import date

import pytest

from app import integration, modules, timetable_source
from app.iserv.children import CHILD_PAGE_FORBIDDEN_KEY
from app.identifiers import UNKNOWN_CHILD_KEY
from app.iserv import dsa
from app.iserv.errors import DataError
from app.iserv.models import Child
from app.not_configured import ConnectionChangedError
from app.poller import Poller
from app.service import IServService
from app.store import Store
from tests.support import add_school, connection_service
from tests.test_school_timetable import ME, LegacyClient, SchoolApp

Option = namedtuple("Option", "child_id name")
SAME_NAMES = [
    ("KIM MUSTER", "kim muster"),
    ("Muster, Kim", "Kim Muster"),
    ("Anna-Lena Muster", "Muster Anna Lena"),
    ("Jürgen Groß", "GROSS JÜRGEN"),
    ("Özlem Çelik", "çelik özlem"),
    ("Jürgen Muster", "Jürgen Muster"),
]
DIFFERENT_NAMES = [
    ("Kim Mustermann", "Kim Muster"),
    ("कमला शर्मा", "कमल शर्मा"),
]
STORED = [{"child_id": "500001", "name": "Kim Muster", "class_name": "1D"}]
ROBIN = {
    "id": 500002,
    "displayname": "Anders Robin",
    "forename": "Robin",
    "surname": "Anders",
    "mainCourse": {"id": 7003, "name": "Klasse 03A", "externalId": "klasse.03a"},
    "courses": [{"id": 7003, "name": "Klasse 03A", "type": "class"}],
}


class PageClient(LegacyClient):
    listed = (("uuid-old", "Kim Muster"),)
    refused = False

    def get_children(self):
        if self.refused:
            raise DataError("refused", message_key=CHILD_PAGE_FORBIDDEN_KEY)
        return [Child(child_id, name) for child_id, name in self.listed]


class ListingSchoolApp(SchoolApp):
    def __init__(self, students=(), **kwargs):
        super().__init__(**kwargs)
        self.listed_students = list(students)
        self.sick_note_calls = 0

    def sick_note_children(self):
        self.sick_note_calls += 1
        return [dict(student) for student in self.listed_students]


def outage_school(tmp_path, children=STORED, listed=None, refused=False, school_app=None):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example", children=[dict(child) for child in children])
    clients = []

    def factory(url):
        client = PageClient(url)
        if listed is not None:
            client.listed = listed
        client.refused = refused
        clients.append(client)
        return client

    service = connection_service(store, connection_id, factory)
    app = school_app if school_app is not None else SchoolApp(me_fails=True)
    service._dsa = lambda: app
    return service, service.store, app, clients


def stored_ids(store):
    return [entry["child_id"] for entry in store.load_config()["children"]]


def page_reads(clients):
    return [call[0] for client in clients for call in client.timetable_calls]


def test_during_an_outage_the_child_keeps_its_stored_id(tmp_path):
    service, store, _, _ = outage_school(tmp_path)
    children = service.children()
    assert [child["child_id"] for child in children] == ["500001"]
    assert children[0]["name"] == "Kim Muster"
    assert stored_ids(store) == ["500001"]


def test_the_stored_list_does_not_grow_over_repeated_outages(tmp_path):
    service, store, _, _ = outage_school(tmp_path)
    for _ in range(3):
        service.children()
    assert store.load_config()["children"] == STORED


def test_the_timetable_page_is_still_read_with_its_own_id_during_an_outage(tmp_path):
    service, _, _, clients = outage_school(tmp_path)
    service.children()
    result = service.timetable("500001", reference=date(2026, 9, 7))
    assert page_reads(clients) == ["uuid-old"]
    assert result["lessons"], "the timetable fallback must still answer"


def test_the_timetable_page_finds_its_id_when_asked_before_the_child_list(tmp_path):
    service, store, _, clients = outage_school(tmp_path)
    result = service.timetable("500001", reference=date(2026, 9, 7))
    assert page_reads(clients) == ["uuid-old"]
    assert result["lessons"]
    assert stored_ids(store) == ["500001"]


def test_a_child_the_page_lists_under_its_stored_id_is_read_with_that_id(tmp_path):
    service, store, _, clients = outage_school(tmp_path, children=[{"child_id": "uuid-old", "name": "Kim Muster"}])
    assert [child["child_id"] for child in service.children()] == ["uuid-old"]
    service.timetable("uuid-old", reference=date(2026, 9, 7))
    assert page_reads(clients) == ["uuid-old"]
    assert stored_ids(store) == ["uuid-old"]


def test_a_really_new_child_during_an_outage_is_still_learned(tmp_path):
    listed = (("uuid-old", "Kim Muster"), ("uuid-new", "Robin Anders"))
    service, store, _, _ = outage_school(tmp_path, listed=listed)
    assert [child["child_id"] for child in service.children()] == ["500001", "uuid-new"]
    assert stored_ids(store) == ["500001", "uuid-new"]


def test_after_the_outage_nothing_is_stored_twice(tmp_path):
    listed = (("uuid-old", "Kim Muster"), ("uuid-new", "Robin Anders"))
    service, store, app, _ = outage_school(tmp_path, listed=listed)
    service.children()
    app.me_fails = False
    app.me = dict(ME, children=list(ME["children"]) + [ROBIN])
    assert [child["child_id"] for child in service.children()] == ["500001", "500002"]
    assert stored_ids(store) == ["500001", "500002"]


def test_the_course_filter_of_the_stored_child_still_applies_during_an_outage(tmp_path):
    service, _, _, _ = outage_school(tmp_path)
    service.save_course_filter("500001", [], [], confirmed_empty=True)
    listed = service.children()[0]["child_id"]
    assert service.timetable(listed, reference=date(2026, 9, 7))["courses"]["chosen"] is True


def test_a_refused_page_lists_the_school_app_child_under_its_stored_id(tmp_path):
    app = ListingSchoolApp(students=[{"id": 7777, "name": "Kim Muster", "class_name": "1D"}], me_fails=True)
    service, store, _, _ = outage_school(tmp_path, refused=True, school_app=app)
    children = service.children()
    assert [(child["child_id"], child["student_id"]) for child in children] == [("500001", 7777)]
    assert stored_ids(store) == ["500001"]


def test_without_a_timetable_module_the_fallback_child_keeps_its_stored_id(tmp_path):
    app = ListingSchoolApp(students=[{"id": 7777, "name": "Muster Kim", "class_name": "1D"}], me_fails=True)
    service, store, _, _ = outage_school(tmp_path, school_app=app)
    service.module_available = lambda module: module != modules.TIMETABLE
    children = service.children()
    assert [(child["child_id"], child["student_id"]) for child in children] == [("500001", 7777)]
    assert stored_ids(store) == ["500001"]


def test_two_stored_children_of_the_same_name_are_not_guessed(tmp_path):
    twins = [{"child_id": "500001", "name": "Kim Muster"}, {"child_id": "500009", "name": "Muster Kim"}]
    service, store, _, _ = outage_school(tmp_path, children=twins)
    assert [child["child_id"] for child in service.children()] == ["uuid-old"]
    assert stored_ids(store) == ["500001", "500009", "uuid-old"]


def test_the_poller_keeps_the_stored_child_key_through_an_outage(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example", children=[dict(child) for child in STORED])
    store.connection_store(connection_id).save_modules(
        {"modules": {name: name == modules.TIMETABLE for name in modules.MODULES}, "checked_at": 1}
    )
    service = IServService(store, client_factory=PageClient)
    app = SchoolApp()
    service.connection(connection_id)._dsa = lambda: app
    sent = []
    poller = Poller(service, notifier=lambda name, message: sent.append(message) or True, store=store)
    poller.poll_once()
    app.me_fails = True
    service.connection(connection_id)._child_service._children_cache = (0.0, {})
    poller.poll_once()
    config = store.connection_store(connection_id).load_config()
    assert [key for key in config["poll_state"] if key.startswith(connection_id + ":")] == [f"{connection_id}:500001"]
    assert stored_ids(store.connection_store(connection_id)) == ["500001"]
    assert [child["key"] for child in integration.children_of(store.connection(connection_id))] == [f"{connection_id}:500001"]
    assert sent == []


def test_a_failed_child_list_is_asked_once_for_the_timetable_page(tmp_path):
    app = ListingSchoolApp(me_fails=True)
    service, _, _, clients = outage_school(tmp_path, refused=True, school_app=app)
    for _ in range(2):
        service.timetable("500001", reference=date(2026, 9, 7))
    assert page_reads(clients) == ["500001", "500001"]
    assert app.sick_note_calls == 1


def test_after_the_outage_the_page_id_is_forgotten(tmp_path):
    service, _, app, _ = outage_school(tmp_path)
    service.children()
    assert service._child_service.timetable_page_id("500001") == "uuid-old"
    app.me_fails = False
    service.children()
    assert service._child_service.timetable_page_id("500001") == "500001"


def test_the_page_id_of_a_child_is_refused_during_an_outage(tmp_path):
    service, _, _, _ = outage_school(tmp_path)
    service.children()
    assert service.authorized_child("500001") == "500001"
    with pytest.raises(DataError) as caught:
        service.authorized_child("uuid-old")
    assert caught.value.message_key == UNKNOWN_CHILD_KEY


def test_a_retired_child_list_forgets_the_page_id(tmp_path):
    service, _, _, _ = outage_school(tmp_path)
    child_service = service._child_service
    service.children()
    child_service.retire()
    assert child_service.timetable_page_id("500001") == "500001"
    with pytest.raises(ConnectionChangedError):
        child_service.children()
    assert child_service.timetable_page_id("500001") == "500001"


def absence_owner(stored, listed):
    owners = Poller(None)._student_owners("s1", [{"child_id": "c1", "name": stored}], {"children": [{"id": 42, "name": listed}]})
    return owners.get(42)


@pytest.mark.parametrize(("stored", "listed"), SAME_NAMES)
def test_every_child_matcher_agrees_on_the_same_name(stored, listed):
    assert dsa.name_words(stored) == timetable_source.name_words(stored)
    assert dsa.student_for_name([{"name": stored}], listed) is not None
    assert timetable_source.matching_option([Option("x", stored)], "other", listed, 2) is not None
    assert absence_owner(stored, listed) == "s1:c1"


@pytest.mark.parametrize(("stored", "listed"), DIFFERENT_NAMES)
def test_no_child_matcher_takes_a_different_name_for_the_same(stored, listed):
    assert dsa.name_words(stored) != dsa.name_words(listed)
    assert dsa.student_for_name([{"name": stored}], listed) is None
    assert timetable_source.matching_option([Option("x", stored)], "other", listed, 2) is None
    assert absence_owner(stored, listed) is None


def test_a_name_keeps_its_combining_marks_and_splits_only_between_words():
    assert dsa.name_words("कमला शर्मा") == frozenset(
        {"कमला", "शर्मा"}
    )
    assert dsa.name_words("Jürgen-Anna, O'Neil") == frozenset({"jürgen", "anna", "o", "neil"})


def test_a_known_student_id_wins_over_the_name_for_absences():
    children = [{"child_id": "c1", "name": "Kim Muster", "student_id": 7}, {"child_id": "c2", "name": "Robin Anders"}]
    overview = {"children": [{"id": 7, "name": "Robin Anders"}, {"id": 8, "name": "Anders, Robin"}]}
    assert Poller(None)._student_owners("s1", children, overview) == {7: "s1:c1", 8: "s1:c2"}


def test_a_hyphenated_page_name_keeps_the_stored_id_during_an_outage(tmp_path):
    stored = [{"child_id": "500001", "name": "Muster Anna Lena"}]
    service, store, _, _ = outage_school(tmp_path, children=stored, listed=(("uuid-old", "Anna-Lena Muster"),))
    assert [child["child_id"] for child in service.children()] == ["500001"]
    assert stored_ids(store) == ["500001"]


class RosterSchoolApp(SchoolApp):
    def __init__(self, roster=(), **kwargs):
        super().__init__(**kwargs)
        self.roster = list(roster)

    def students(self):
        return [dict(student) for student in self.roster]


TWINS_ROSTER = [
    {"id": 1, "name": "Kim Muster", "class_name": "1A"},
    {"id": 2, "name": "Muster Kim", "class_name": "2B"},
]
TWIN = {"id": 500009, "displayname": "Kim Muster", "forename": "Muster", "surname": "Kim", "courses": []}


def test_two_candidates_of_the_same_name_are_never_guessed():
    assert dsa.student_for_name(TWINS_ROSTER, "Kim Muster") is None
    assert dsa.class_for_name(TWINS_ROSTER, "Kim Muster") == ""


def test_the_class_lookup_does_not_guess_between_two_students_of_the_same_name(tmp_path):
    app = RosterSchoolApp(roster=TWINS_ROSTER, me_fails=True)
    service, _, _, _ = outage_school(tmp_path, children=[], school_app=app)
    child = service.children()[0]
    assert (child["child_id"], child["class_name"], child["student_id"]) == ("uuid-old", "", None)


def test_the_migration_does_not_guess_between_two_account_children_of_the_same_name(tmp_path):
    app = SchoolApp(me=dict(ME, children=list(ME["children"]) + [TWIN]))
    service, store, _, _ = outage_school(tmp_path, children=[{"child_id": "uuid-old", "name": "Kim Muster"}], school_app=app)
    service.children()
    assert stored_ids(store) == ["uuid-old", "500001", "500009"]


def test_the_absence_owner_is_not_guessed_between_two_children_of_the_same_name():
    children = [{"child_id": "c1", "name": "Kim Muster"}, {"child_id": "c2", "name": "Muster Kim"}]
    owners = Poller(None)._student_owners("s1", children, {"children": [{"id": 42, "name": "Kim Muster"}]})
    assert owners == {}


SPELLINGS = [
    ("Anna-Lena Groß", "Gross Anna Lena", {"forename": "Anna Lena", "surname": "Gross"}),
    ("Weiss, Jörg", "Jörg Weiß", {"forename": "Jörg", "surname": "Weiß"}),
]


@pytest.mark.parametrize(("page_name", "roster_name", "account_name"), SPELLINGS)
def test_the_class_lookup_finds_a_student_spelled_differently(tmp_path, page_name, roster_name, account_name):
    app = RosterSchoolApp(roster=[{"id": 9, "name": roster_name, "class_name": "3C"}], me_fails=True)
    service, _, _, _ = outage_school(tmp_path, children=[], listed=(("uuid-a", page_name),), school_app=app)
    child = service.children()[0]
    assert (child["child_id"], child["class_name"], child["student_id"]) == ("uuid-a", "3C", 9)


@pytest.mark.parametrize(("page_name", "roster_name", "account_name"), SPELLINGS)
def test_a_stored_child_spelled_differently_moves_to_the_school_account_id(tmp_path, page_name, roster_name, account_name):
    entry = dict(
        account_name,
        id=500003,
        mainCourse={"id": 7005, "name": "Klasse 03C", "externalId": "klasse.03c"},
        courses=[{"id": 7005, "name": "Klasse 03C", "type": "class"}],
    )
    app = SchoolApp(me=dict(ME, children=[entry]))
    service, store, _, _ = outage_school(tmp_path, children=[{"child_id": "uuid-old", "name": page_name}], school_app=app)
    service.children()
    assert store.load_config()["children"] == [{"child_id": "500003", "name": page_name, "class_name": "3C"}]
