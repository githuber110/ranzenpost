import pytest

from app.iserv.children import CHILD_PAGE_FORBIDDEN_KEY, CHILD_PAGE_MESSAGE_KEY
from app.iserv.errors import DataError
from app.iserv.models import Child
from app.service import IServService
from app.store import Store

SCHOOL_APP_CHILDREN = [
    {"id": 99, "name": "Mia Muster", "class_name": "2b", "class_full": "Klasse 02B", "class_code": "klasse.02b"},
    {"id": 100, "name": "Ben Muster", "class_name": "4a", "class_full": "Klasse 04A", "class_code": "klasse.04a"},
]


class RefusingClient:
    def __init__(self, url, message_key=CHILD_PAGE_FORBIDDEN_KEY):
        self.url = url
        self.message_key = message_key
        self.base_url = url
        self.session = object()

    def login(self, username, password, code_provider):
        return self

    def is_authenticated(self):
        return True

    def get_children(self):
        raise DataError("child list page was not readable", message_key=self.message_key, detail={"status": 403})


class WorkingClient(RefusingClient):
    def get_children(self):
        return [Child("uuid-1", "Mia Muster")]


class SchoolApp:
    def __init__(self, children=None, fail=False):
        self._children = children if children is not None else []
        self.fail = fail
        self.settings = {"timetable_availableForGuardiansAndStudents": True}

    def sick_note_children(self):
        if self.fail:
            raise RuntimeError("school app down")
        return list(self._children)

    def students(self):
        return list(self._children)

    def school_settings(self):
        return self.settings


def make(tmp_path, client_class=RefusingClient, school_app=None, **client_kwargs):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    service = IServService(store, client_factory=lambda url: client_class(url, **client_kwargs))
    service._dsa = lambda: school_app if school_app is not None else SchoolApp()
    return service


def test_a_refused_timetable_page_no_longer_costs_the_family_its_children(tmp_path):
    service = make(tmp_path, school_app=SchoolApp(SCHOOL_APP_CHILDREN))
    children = service.children()
    assert [child["name"] for child in children] == ["Mia Muster", "Ben Muster"]
    assert children[0] == {
        "child_id": "99",
        "name": "Mia Muster",
        "class_name": "2b",
        "student_id": 99,
        "class_full": "Klasse 02B",
        "class_code": "klasse.02b",
    }


def test_the_fallback_carries_every_field_the_old_list_carried_and_more(tmp_path):
    service = make(tmp_path, school_app=SchoolApp(SCHOOL_APP_CHILDREN))
    child = service.children()[0]
    assert set(child) >= {"child_id", "name", "class_name", "student_id", "class_full", "class_code"}
    assert child["class_name"] and child["class_code"] and child["student_id"] is not None


def test_children_read_the_old_way_still_come_from_the_timetable_page(tmp_path):
    service = make(tmp_path, client_class=WorkingClient, school_app=SchoolApp(SCHOOL_APP_CHILDREN))
    children = service.children()
    assert [child["child_id"] for child in children] == ["uuid-1"]
    assert service.timetable_available() is True


def test_while_the_timetable_page_is_refused_the_timetable_is_reported_unavailable(tmp_path):
    service = make(tmp_path, school_app=SchoolApp(SCHOOL_APP_CHILDREN))
    service.children()
    assert service.timetable_available() is False


def test_a_later_working_read_lifts_the_unavailable_mark_again(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"})
    clients = [RefusingClient("https://school.example"), WorkingClient("https://school.example")]
    service = IServService(store, client_factory=lambda url: clients.pop(0))
    service._dsa = lambda: SchoolApp(SCHOOL_APP_CHILDREN)
    service.children()
    assert service.timetable_available() is False
    service._client = None
    service.children()
    assert service.timetable_available() is True


def test_an_empty_school_app_list_does_not_turn_a_refusal_into_no_children(tmp_path):
    service = make(tmp_path, school_app=SchoolApp([]))
    with pytest.raises(DataError) as caught:
        service.children()
    assert caught.value.message_key == CHILD_PAGE_FORBIDDEN_KEY


def test_a_broken_school_app_keeps_the_original_refusal_as_the_reason(tmp_path):
    service = make(tmp_path, school_app=SchoolApp(fail=True))
    with pytest.raises(DataError) as caught:
        service.children()
    assert caught.value.message_key == CHILD_PAGE_FORBIDDEN_KEY


@pytest.mark.parametrize("key", [CHILD_PAGE_FORBIDDEN_KEY, CHILD_PAGE_MESSAGE_KEY])
def test_both_child_page_failures_take_the_fallback(tmp_path, key):
    service = make(tmp_path, school_app=SchoolApp(SCHOOL_APP_CHILDREN), message_key=key)
    assert [child["child_id"] for child in service.children()] == ["99", "100"]


def test_an_unrelated_data_error_is_not_swallowed_by_the_fallback(tmp_path):
    service = make(tmp_path, school_app=SchoolApp(SCHOOL_APP_CHILDREN), message_key="api.something.else")
    with pytest.raises(DataError) as caught:
        service.children()
    assert caught.value.message_key == "api.something.else"


def test_a_school_app_entry_without_an_id_or_name_is_left_out(tmp_path):
    ragged = SCHOOL_APP_CHILDREN + [{"id": None, "name": "Geist"}, {"id": 7, "name": ""}]
    service = make(tmp_path, school_app=SchoolApp(ragged))
    assert [child["child_id"] for child in service.children()] == ["99", "100"]
