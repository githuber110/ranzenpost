import pytest

from app.iserv.errors import DataError
from app.iserv.models import Child
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_service import FakeAbsenceDsa, with_absences

OWN_CHILD = "uuid-own"
OTHER_CHILD = "uuid-other"
UNKNOWN_KEY = "api.child.unknown"


class RecordingClient:
    children = [Child(OWN_CHILD, "Kim")]
    failure = None

    def __init__(self, url):
        self.url = url
        self.base_url = url
        self.session = None
        self.authed = False
        self.timetable_calls = []

    def login(self, username, password, code_provider):
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        if self.failure is not None:
            raise self.failure
        return list(self.children)

    def read_time_table_week(self, child_id, reference=None):
        self.timetable_calls.append(child_id)
        raise AssertionError(f"timetable of {child_id} must not be requested")


def school(tmp_path, client_class, stored_children=None):
    store = Store(tmp_path / "data")
    clients = []

    def factory(url):
        client = client_class(url)
        clients.append(client)
        return client

    connection_id = add_school(store, children=stored_children or [])
    service = IServService(store, client_factory=factory)
    return service, store, connection_id, clients


def requested_timetables(clients):
    return [child_id for client in clients for child_id in client.timetable_calls]


def expect_unknown(call):
    with pytest.raises(DataError) as caught:
        call()
    assert caught.value.message_key == UNKNOWN_KEY


def test_an_id_outside_the_stored_children_is_refused_without_asking_the_school(tmp_path):
    service, _, connection_id, clients = school(tmp_path, RecordingClient, [{"child_id": OWN_CHILD, "name": "Kim"}])
    expect_unknown(lambda: service.timetable(f"{connection_id}:{OTHER_CHILD}"))
    assert requested_timetables(clients) == []


def test_an_unknown_school_is_refused(tmp_path):
    service, _, _, clients = school(tmp_path, RecordingClient)
    expect_unknown(lambda: service.timetable(f"deadbeef:{OWN_CHILD}"))
    assert requested_timetables(clients) == []


def test_without_stored_children_an_id_the_school_does_not_list_is_refused(tmp_path):
    service, store, connection_id, clients = school(tmp_path, RecordingClient)
    expect_unknown(lambda: service.timetable(f"{connection_id}:{OTHER_CHILD}"))
    assert requested_timetables(clients) == []
    assert [child["child_id"] for child in store.connection(connection_id)["children"]] == [OWN_CHILD]


def test_a_school_that_confirms_no_children_allows_no_child(tmp_path):
    class NoChildren(RecordingClient):
        children = []

    service, _, connection_id, clients = school(tmp_path, NoChildren)
    expect_unknown(lambda: service.timetable(f"{connection_id}:{OTHER_CHILD}"))
    assert requested_timetables(clients) == []


def test_an_unreadable_child_list_is_an_error_and_not_an_empty_list(tmp_path):
    class Unreadable(RecordingClient):
        failure = DataError("child list unreadable", message_key="api.data.timetable")

    service, _, connection_id, clients = school(tmp_path, Unreadable)
    with pytest.raises(DataError) as caught:
        service.timetable(f"{connection_id}:{OTHER_CHILD}")
    assert caught.value.message_key != UNKNOWN_KEY
    assert requested_timetables(clients) == []


def test_without_stored_children_a_listed_child_is_allowed(tmp_path):
    class Allowed(RecordingClient):
        def read_time_table_week(self, child_id, reference=None):
            self.timetable_calls.append(child_id)
            raise DataError("stop after the check", message_key="test.reached")

    service, _, connection_id, clients = school(tmp_path, Allowed)
    with pytest.raises(DataError) as caught:
        service.timetable(f"{connection_id}:{OWN_CHILD}")
    assert caught.value.message_key == "test.reached"
    assert requested_timetables(clients) == [OWN_CHILD]


def sick_note(student_id):
    return {"type": "sick", "student_id": student_id, "day_from": "today", "day_till": "today"}


@pytest.mark.parametrize(
    "student_id, message_key",
    [(8, UNKNOWN_KEY), ("8", UNKNOWN_KEY), (None, "api.absence.error.student"), ("", "api.absence.error.student")],
)
def test_an_absence_for_a_student_the_school_does_not_offer_is_not_sent(tmp_path, student_id, message_key):
    dsa = FakeAbsenceDsa()
    service, _ = with_absences(tmp_path, dsa)
    result = service.report_absence(sick_note(student_id))
    assert result["ok"] is False
    assert result["message_key"] == message_key
    assert dsa.sent is None


@pytest.mark.parametrize("student_id", [7, "7"])
def test_an_absence_for_an_offered_student_is_sent(tmp_path, student_id):
    dsa = FakeAbsenceDsa()
    service, _ = with_absences(tmp_path, dsa)
    assert service.report_absence(sick_note(student_id))["ok"] is True
    assert dsa.sent.payload["sickUser"] == 7


def test_an_absence_is_not_sent_when_the_offered_students_cannot_be_read(tmp_path):
    class Unreadable(FakeAbsenceDsa):
        def sick_note_children(self):
            return []

        def sick_note_children_or_raise(self):
            raise DataError("students unreadable", message_key="api.data.absences")

    dsa = Unreadable()
    service, _ = with_absences(tmp_path, dsa)
    with pytest.raises(DataError):
        service.report_absence(sick_note(7))
    assert dsa.sent is None
