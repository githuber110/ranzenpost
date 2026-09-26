import pytest

from app.iserv.children import CHILD_PAGE_MESSAGE_KEY
from app.iserv.errors import DataError
from app.store import Store
from app.wizard import Wizard
from tests.support import add_school, connection_service
from tests.test_children_fallback import SCHOOL_APP_CHILDREN, RefusingClient, SchoolApp
from tests.test_wizard import FakeProber, WizardStore, complete_connect, offer

NO_TIMETABLE = {"timetable_availableForGuardiansAndStudents": False}


class CountingSchoolApp(SchoolApp):
    def __init__(self, children=None, fail=False):
        super().__init__(children, fail)
        self.settings = dict(NO_TIMETABLE)
        self.reads = 0

    def sick_note_children_or_raise(self):
        self.reads += 1
        if self.fail:
            raise DataError("school app unreadable", message_key="api.data.absences")
        return list(self._children)


class LetterPages(RefusingClient):
    status = 200

    def fetch(self, path, params=None):
        page = type("Page", (), {})()
        page.status_code = self.status
        page.text = "<html><body></body></html>"
        page.url = f"https://school.example/{path}"
        return page


class BrokenLetterPages(LetterPages):
    status = 500


def school_without_timetable(tmp_path, school_app, client=LetterPages):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    service = connection_service(store, connection_id, lambda url: client(url))
    service._dsa = lambda: school_app
    return service, store, connection_id


def test_an_unreadable_child_list_without_a_timetable_is_an_error(tmp_path):
    service, _, _ = school_without_timetable(tmp_path, CountingSchoolApp(fail=True), BrokenLetterPages)
    with pytest.raises(DataError):
        service.children()


def test_a_readable_but_empty_child_list_without_a_timetable_stays_empty(tmp_path):
    service, _, _ = school_without_timetable(tmp_path, CountingSchoolApp([]))
    assert service.children() == []


def test_the_school_app_list_still_names_the_children_without_a_timetable(tmp_path):
    service, _, _ = school_without_timetable(tmp_path, CountingSchoolApp(SCHOOL_APP_CHILDREN))
    assert [child["name"] for child in service.children()] == ["Mia Muster", "Ben Muster"]


def test_unknown_ids_do_not_ask_the_school_again_and_again(tmp_path):
    school_app = CountingSchoolApp([])
    service, _, _ = school_without_timetable(tmp_path, school_app)
    for attempt in range(5):
        with pytest.raises(DataError):
            service.authorized_child(f"made-up-{attempt}")
    assert school_app.reads == 1


def test_a_child_named_only_in_letters_gets_no_timetable_request(tmp_path):
    service, _, _ = school_without_timetable(tmp_path, CountingSchoolApp(SCHOOL_APP_CHILDREN))
    service._session = lambda: pytest.fail("no timetable request for a letters child")
    with pytest.raises(DataError) as caught:
        service._timetable_payload("letters:kim-muster")
    assert caught.value.message_key == "api.child.unknown"


def test_the_unreadable_error_names_the_child_list(tmp_path):
    class Broken(CountingSchoolApp):
        def sick_note_children_or_raise(self):
            raise RuntimeError("school app down")

    service, _, _ = school_without_timetable(tmp_path, Broken(), BrokenLetterPages)
    with pytest.raises(DataError) as caught:
        service.children()
    assert caught.value.message_key == CHILD_PAGE_MESSAGE_KEY


def wizard_with_child(tmp_path, username="parent", host="school-one.example"):
    store = Store(tmp_path / "data")
    prober = FakeProber()
    wizard = Wizard(store, prober)
    flat = WizardStore(store, wizard)
    wizard.set_url(host)
    wizard.set_login(username, "s")
    complete_connect(wizard)
    offer(flat, "uuid-1")
    wizard.select_child("uuid-1", "Bella", "2b")
    flat.edit_config(lambda config: config.update(course_filters={"uuid-1": {"chosen": ["E1|A"], "known": ["E1|A"]}}))
    return wizard, flat


def rerun(wizard, username, host):
    wizard.reset(wizard.status()["connection_id"])
    wizard.set_url(host)
    wizard.set_login(username, "s")


@pytest.mark.parametrize(
    "username, host",
    [("someone.else", "school-one.example"), ("parent", "school-two.example")],
    ids=["other-account", "other-school"],
)
def test_signing_in_with_another_account_or_school_forgets_the_old_children(tmp_path, username, host):
    wizard, flat = wizard_with_child(tmp_path)
    rerun(wizard, username, host)
    config = flat.load_config()
    assert config["children"] == []
    assert config["course_filters"] == {}


@pytest.mark.parametrize("username", ["parent", " Parent "], ids=["same", "same-other-spelling"])
def test_signing_in_again_with_the_same_account_keeps_the_children(tmp_path, username):
    wizard, flat = wizard_with_child(tmp_path)
    rerun(wizard, username, "school-one.example")
    config = flat.load_config()
    assert [child["child_id"] for child in config["children"]] == ["uuid-1"]
    assert "uuid-1" in config["course_filters"]


def test_an_old_install_without_fingerprint_still_notices_another_account(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    secrets = flat.base.load_secrets(flat.load_config()["connection_id"])
    secrets.pop("account_fingerprint", None)
    secrets.pop("school_identity", None)
    flat.base.save_secrets(flat.load_config()["connection_id"], secrets)
    rerun(wizard, "someone.else", "school-one.example")
    assert flat.load_config()["children"] == []


def test_a_default_port_is_the_same_school(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    rerun(wizard, "parent", "school-one.example:443")
    assert [child["child_id"] for child in flat.load_config()["children"]] == ["uuid-1"]


def test_a_mistyped_school_that_is_corrected_before_sign_in_keeps_the_children(tmp_path):
    wizard, flat = wizard_with_child(tmp_path)
    wizard.reset(wizard.status()["connection_id"])
    wizard.set_url("school-two.example")
    wizard.back()
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    assert [child["child_id"] for child in flat.load_config()["children"]] == ["uuid-1"]


def test_a_new_sign_in_gives_the_service_a_fresh_connection(tmp_path):
    from app.service import IServService

    wizard, flat = wizard_with_child(tmp_path)
    connection_id = flat.load_config()["connection_id"]
    service = IServService(flat.base)
    before = service.connection(connection_id)
    before._child_service._listed_ids = (before.clock(), {"old-child"})
    assert service.connection(connection_id) is before
    rerun(wizard, "someone.else", "school-one.example")
    after = service.connection(connection_id)
    assert after is not before
    assert after._child_service._listed_ids[1] == set()


def test_a_sign_in_error_passes_through_the_child_list(tmp_path):
    from app.iserv.errors import LoginError

    class Refusing(CountingSchoolApp):
        def sick_note_children_or_raise(self):
            raise LoginError("refused", reason="bad_credentials")

    service, _, _ = school_without_timetable(tmp_path, Refusing())
    with pytest.raises(LoginError):
        service.children()


def test_empty_letters_do_not_confirm_no_children_when_the_school_app_failed(tmp_path):
    service, _, _ = school_without_timetable(tmp_path, CountingSchoolApp(fail=True))
    with pytest.raises(DataError):
        service.children()


@pytest.mark.parametrize("sent", [42, "42", " 042 "])
def test_a_listed_absence_is_found_whatever_the_id_spelling(tmp_path, sent):
    from tests.test_service import FakeAbsenceDsa, with_absences

    dsa = FakeAbsenceDsa(status=204)
    dsa._requests["user-requests-to-school/student-absences/"] = [{"id": "42"}]
    service, _ = with_absences(tmp_path, dsa)
    assert service.delete_absence({"type": "leave", "id": sent})["ok"] is True


def test_the_poll_of_a_school_without_timetable_goes_on_when_the_child_list_fails(tmp_path):
    from app.poller import Poller

    class Service:
        id = "s1"

        def __init__(self):
            self.store = None

        def children(self):
            raise DataError("unreadable", message_key=CHILD_PAGE_MESSAGE_KEY)

        def stored_children(self):
            return [{"child_id": "c1", "name": "Kim"}]

    poller = Poller(Service())
    children, event = poller._children_for_poll(Service(), "s1")
    assert children == [{"child_id": "c1", "name": "Kim"}]
    assert event["module"] == "children" and event["error"]
