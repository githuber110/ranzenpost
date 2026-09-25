import logging
from pathlib import Path

import pytest
import requests

from app import modules
from app.iserv.children import CHILD_PAGE_FORBIDDEN_KEY
from app.iserv.errors import DataError, OutageError
from app.iserv.models import Child
from app.service import IServService
from app.store import Store
from tests.support import add_school, connection_service

START_PAGE = """
<html><body>
<a href="/iserv/time-table/">Stundenplan</a>
<a href="/iserv/parentletter/parent/index">Elternbriefe</a>
<a href="/iserv/mail/">E-Mail</a>
<footer>IServ 3.9.1</footer>
</body></html>
"""

FIXTURES = Path(__file__).parent / "fixtures"
MESSENGER_PAGE = (FIXTURES / "messenger_page.html").read_text(encoding="utf-8")
MESSENGER_PAGE_WITHOUT_CREDENTIALS = (FIXTURES / "messenger_page_without_credentials.html").read_text(encoding="utf-8")
TIMETABLE_PATHS = (modules.DSA_TIMETABLE_PATH, modules.PROBES[modules.TIMETABLE][0])

SCHOOL_APP_CHILDREN = [
    {"id": 99, "name": "Mia Muster", "class_name": "2b", "class_full": "Klasse 02B", "class_code": "klasse.02b"},
]


MESSENGER_PAGE_WITHOUT_DATA = "<html><body><div id='app'></div></body></html>"
AUTHENTICATE_PATHS = ("/iserv/messenger/authenticate", "/messenger/authenticate")
AUTHENTICATE_ANSWER = {
    "messenger_authentication": {
        "access_token": "tok-x",
        "device_id": "dev-x",
        "home_server": "srv-x",
        "user_id": "@me:srv-x",
        "iserv_token": "it-x",
        "iserv_cryptkey": "ck-x",
    }
}


class Response:
    def __init__(self, status_code, url, text="", json_data=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.json_data = json_data

    def json(self):
        if self.json_data is None:
            raise ValueError("no json")
        return self.json_data


class ProbeClient:
    def __init__(
        self,
        url,
        missing=(),
        failing=(),
        start_page=START_PAGE,
        start_status=200,
        messenger_page=MESSENGER_PAGE,
        authenticate=None,
    ):
        self.base_url = url.rstrip("/")
        self.session = object()
        self.missing = set(missing)
        self.failing = set(failing)
        self.start_page = start_page
        self.start_status = start_status
        self.messenger_page = messenger_page
        self.authenticate = authenticate
        self.authed = False
        self.calls = []

    def login(self, username, password, code_provider):
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def fetch(self, path, params=None):
        self.calls.append(path)
        if path in self.failing:
            raise requests.ConnectionError("down")
        if path == "/iserv/":
            return Response(self.start_status, self.base_url + path, self.start_page)
        if path in self.missing:
            return Response(403, self.base_url + path)
        if path == modules.PROBES[modules.MESSENGER][0]:
            return Response(200, self.base_url + path, self.messenger_page)
        if path in AUTHENTICATE_PATHS:
            if isinstance(self.authenticate, Exception):
                raise self.authenticate
            if self.authenticate is None:
                return Response(404, self.base_url + path)
            return Response(200, self.base_url + path, json_data=self.authenticate)
        return Response(200, self.base_url + path)

    def get_children(self):
        self.calls.append("/iserv/time-table/")
        if set(TIMETABLE_PATHS) <= self.missing:
            raise DataError("refused", message_key=CHILD_PAGE_FORBIDDEN_KEY, detail={"status": 403})
        return [Child("uuid-1", "Mia Muster")]


class SchoolApp:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else {}

    def sick_note_children(self):
        return list(SCHOOL_APP_CHILDREN)

    def sick_note_children_or_raise(self):
        return self.sick_note_children()

    def students(self):
        return list(SCHOOL_APP_CHILDREN)

    def school_settings(self):
        return self.settings

    def me_with_children(self):
        return None


def make(tmp_path, **client_kwargs):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    holder = {}

    def factory(url):
        holder["client"] = ProbeClient(url, **client_kwargs)
        return holder["client"]

    service = connection_service(store, connection_id, factory)
    service._dsa = lambda: SchoolApp()
    return service, service.store, holder


def test_the_registry_defaults_to_everything_before_any_login(tmp_path):
    service, _, _ = make(tmp_path)
    assert service.modules() == modules.default_registry()
    assert service.timetable_available() is True


def test_a_login_detects_the_modules_and_stores_them(tmp_path, caplog):
    service, store, holder = make(tmp_path, missing=[modules.PROBES[modules.ABSENCES][0]])
    with caplog.at_level(logging.INFO, logger="app.service"):
        service.check_connection()
    registry = service.modules()
    assert registry["modules"][modules.ABSENCES] is False
    assert registry["modules"][modules.LETTERS] is True
    assert registry["unsupported"] == [{"segment": "mail", "slug": "mail", "label": "E-Mail", "name": "E-Mail"}]
    assert registry["unknown"] == []
    assert registry["iserv_version"] == "3.9.1"
    assert store.load_modules()["modules"] == registry["modules"]
    lines = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
    assert lines == [
        f"school#{service.id} modules available: timetable, letters, pinboard, conferences, messenger; "
        "missing: absences; not supported: 1 (mail); unknown: 0"
    ]
    assert holder["client"].calls.count("/iserv/") == 1


def test_the_login_page_names_the_version_when_the_start_page_does_not(tmp_path):
    service, _, holder = make(tmp_path, start_page="<html><body><a href='/iserv/mail/'>Mail</a></body></html>")
    service.check_connection()
    assert service.modules()["iserv_version"] == ""
    holder["client"].login_page = "<html><body><footer>IServ 3.7.4</footer></body></html>"
    service.refresh_modules()
    assert service.modules()["iserv_version"] == "3.7.4"


def test_an_unchanged_registry_is_not_logged_again(tmp_path, caplog):
    service, _, _ = make(tmp_path)
    with caplog.at_level(logging.INFO, logger="app.service"):
        service.check_connection()
        service.refresh_modules()
        service.refresh_modules()
    lines = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
    assert len(lines) == 1


def test_every_refresh_reads_the_start_page_and_probes_every_module(tmp_path):
    service, _, holder = make(tmp_path)
    service.check_connection()
    probes = len(holder["client"].calls)
    assert probes == 1 + len(modules.MODULES)
    service.refresh_modules()
    assert len(holder["client"].calls) == 2 * probes


def test_a_refresh_without_a_session_logs_in_and_detects_only_once(tmp_path):
    service, _, holder = make(tmp_path)
    service.refresh_modules()
    assert holder["client"].calls.count("/iserv/") == 1


def test_a_module_that_appears_later_is_picked_up_by_the_next_refresh_with_one_log_line_per_change(tmp_path, caplog):
    service, _, holder = make(tmp_path, missing=[modules.PROBES[modules.LETTERS][0]])
    with caplog.at_level(logging.INFO, logger="app.service"):
        service.check_connection()
        assert service.modules()["modules"][modules.LETTERS] is False
        service.refresh_modules()
        holder["client"].missing.clear()
        service.refresh_modules()
        assert service.modules()["modules"][modules.LETTERS] is True
        service.refresh_modules()
    prefix = f"school#{service.id} "
    lines = [record.getMessage()[len(prefix):] for record in caplog.records if record.getMessage().startswith(prefix + "modules available")]
    assert lines == [
        "modules available: timetable, pinboard, absences, conferences, messenger; missing: letters; "
        "not supported: 1 (mail); unknown: 0",
        "modules available: timetable, letters, pinboard, absences, conferences, messenger; missing: none; "
        "not supported: 1 (mail); unknown: 0",
    ]


def test_a_manual_recheck_is_rate_limited_to_once_a_minute(tmp_path):
    service, _, holder = make(tmp_path, missing=[modules.PROBES[modules.LETTERS][0]])
    service.check_connection()
    moment = [1000.0]
    first = service.recheck_modules(clock=lambda: moment[0])
    assert first["ok"] is True
    assert first["message_key"] == "api.modules.rechecked"
    assert first["modules"]["modules"][modules.LETTERS] is False
    holder["client"].missing.clear()
    moment[0] += 30
    second = service.recheck_modules(clock=lambda: moment[0])
    assert second["ok"] is False
    assert second["error"] == "rate_limited"
    assert second["message_key"] == "api.modules.tooSoon"
    assert second["modules"]["modules"][modules.LETTERS] is False
    moment[0] += 31
    third = service.recheck_modules(clock=lambda: moment[0])
    assert third["ok"] is True
    assert third["modules"]["modules"][modules.LETTERS] is True


def test_a_network_failure_keeps_the_stored_registry(tmp_path):
    service, store, _ = make(tmp_path, missing=[modules.PROBES[modules.LETTERS][0]])
    service.check_connection()
    assert service.modules()["modules"][modules.LETTERS] is False
    service._sign_in.drop_session()
    service.client_factory = lambda url: ProbeClient(url, failing=[path for path, _ in modules.PROBES.values()])
    service.check_connection()
    service.refresh_modules()
    assert service.modules()["modules"][modules.LETTERS] is False
    assert service.modules()["modules"][modules.TIMETABLE] is True


def test_a_5xx_start_page_keeps_the_stored_registry_instead_of_emptying_it(tmp_path):
    service, store, _ = make(tmp_path, missing=[modules.PROBES[modules.LETTERS][0]])
    service.check_connection()
    before = store.load_modules()
    assert before["modules"][modules.LETTERS] is False
    assert before["modules"][modules.TIMETABLE] is True

    service._client.start_status = 500
    with pytest.raises(OutageError):
        service.refresh_modules()
    assert store.load_modules() == before

    service._client.start_status = 200
    service._client.failing = {"/iserv/"}
    with pytest.raises(OutageError):
        service.refresh_modules()
    assert store.load_modules() == before


def test_a_detection_that_blows_up_keeps_the_stored_registry(tmp_path, caplog):
    service, store, _ = make(tmp_path, missing=[modules.PROBES[modules.LETTERS][0]])
    service.check_connection()
    before = store.load_modules()
    assert before["modules"][modules.LETTERS] is False

    def broken(client):
        raise RuntimeError("parser exploded")

    service._probe_modules = broken
    service._sign_in.drop_session()
    with caplog.at_level(logging.DEBUG, logger="app.service"):
        assert service.check_connection() == "ok"
    assert store.load_modules() == before
    assert service.modules()["modules"][modules.LETTERS] is False
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
    with pytest.raises(RuntimeError):
        service.refresh_modules()
    assert store.load_modules() == before


def test_the_timetable_flag_also_honours_the_school_setting(tmp_path):
    service, _, _ = make(tmp_path)
    service._dsa = lambda: SchoolApp({"timetable_availableForGuardiansAndStudents": False})
    service.check_connection()
    assert service.modules()["modules"][modules.TIMETABLE] is False
    assert service.timetable_available() is False


def test_a_timetable_served_only_by_the_school_app_stays_available(tmp_path):
    service, _, _ = make(tmp_path, missing=[modules.PROBES[modules.TIMETABLE][0]])
    service.check_connection()
    assert service.modules()["modules"][modules.TIMETABLE] is True
    assert service.timetable_available() is True
    withheld, _, _ = make(tmp_path / "other", missing=[modules.PROBES[modules.TIMETABLE][0]])
    withheld._dsa = lambda: SchoolApp({"timetable_availableForGuardiansAndStudents": False})
    withheld.check_connection()
    assert withheld.timetable_available() is False


def test_a_missing_timetable_sends_the_child_list_straight_to_the_school_app(tmp_path, caplog):
    service, _, holder = make(tmp_path, missing=TIMETABLE_PATHS)
    service.check_connection()
    holder["client"].calls.clear()
    with caplog.at_level(logging.WARNING):
        children = service.children()
    assert [child["child_id"] for child in children] == ["99"]
    assert "/iserv/time-table/" not in holder["client"].calls
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_a_login_without_a_fetching_client_still_succeeds(tmp_path):
    class Plain:
        def __init__(self, url):
            self.authed = False

        def login(self, username, password, code_provider):
            self.authed = True
            return self

        def is_authenticated(self):
            return self.authed

    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    service = connection_service(store, connection_id, Plain)
    assert service.check_connection() == "ok"
    assert service.modules() == modules.default_registry()


def test_the_registry_survives_a_restart_through_the_store(tmp_path):
    service, store, _ = make(tmp_path, missing=[modules.PROBES[modules.MESSENGER][0]])
    service.check_connection()
    again = connection_service(store.base, service.id, lambda url: ProbeClient(url))
    assert again.modules()["modules"][modules.MESSENGER] is False


LETTERS_INDEX = (FIXTURES / "letters_index.html").read_text(encoding="utf-8")


class LettersOnlyClient(ProbeClient):
    def fetch(self, path, params=None):
        self.calls.append(path)
        if path == "/iserv/":
            return Response(200, self.base_url + path, self.start_page)
        if path.startswith("/iserv/parentletter/parent/index"):
            return Response(200, self.base_url + path, LETTERS_INDEX)
        if path.startswith("/iserv/parentletter/"):
            return Response(200, self.base_url + path, "<html><body></body></html>")
        return Response(403, self.base_url + path)


class BareSchoolApp(SchoolApp):
    def sick_note_children(self):
        raise AssertionError("the school app must not be asked without the absences module")

    def sick_note_children_or_raise(self):
        return self.sick_note_children()

    def me_with_children(self):
        return None


def make_letters_only(tmp_path, client_class=LettersOnlyClient):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school.example")
    holder = {}

    def factory(url):
        holder["client"] = client_class(url)
        return holder["client"]

    service = connection_service(store, connection_id, factory)
    service._dsa = lambda: BareSchoolApp()
    return service, service.store, holder


def test_without_a_timetable_the_letter_pages_name_the_children(tmp_path, caplog):
    service, store, holder = make_letters_only(tmp_path)
    with caplog.at_level(logging.INFO, logger="app.service"):
        service.check_connection()
        children = service.children()
    assert service.modules()["modules"] == {
        modules.TIMETABLE: False,
        modules.LETTERS: True,
        modules.PINBOARD: False,
        modules.ABSENCES: False,
        modules.CONFERENCES: False,
        modules.MESSENGER: False,
    }
    assert [child["name"] for child in children] == ["Alex Example", "Robin Example"]
    assert children[0]["child_id"] == "letters:alex-example"
    assert children[0]["student_id"] is None
    assert "/iserv/time-table/" not in holder["client"].calls[holder["client"].calls.index("/iserv/parentletter/parent/index"):]
    assert [child["child_id"] for child in store.load_config()["children"]] == ["letters:alex-example", "letters:robin-example"]
    prefix = f"school#{service.id} "
    module_lines = [record.getMessage()[len(prefix):] for record in caplog.records if record.getMessage().startswith(prefix + "modules available")]
    assert module_lines == [
        "modules available: letters; missing: timetable, pinboard, absences, conferences, messenger; "
        "not supported: 1 (mail); unknown: 0"
    ]
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


class NothingClient(ProbeClient):
    def fetch(self, path, params=None):
        self.calls.append(path)
        if path == "/iserv/":
            return Response(200, self.base_url + path, "<html><body><a href='/iserv/mail/'>Mail</a></body></html>")
        return Response(404, self.base_url + path)


def test_without_any_module_the_child_list_is_simply_empty(tmp_path, caplog):
    service, _, holder = make_letters_only(tmp_path, NothingClient)
    with caplog.at_level(logging.DEBUG):
        service.check_connection()
        assert service.children() == []
        assert service.children() == []
    assert service.modules()["modules"] == {name: False for name in modules.MODULES}
    assert "/iserv/time-table/" not in holder["client"].calls[len(modules.MODULES) + 1:]
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
    prefix = f"school#{service.id} modules available"
    module_lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith(prefix)]
    assert len(module_lines) == 1


def test_letters_child_ids_are_stable_slugs():
    from app.child_service import letters_child_id

    assert letters_child_id("  Alex   Example ") == "letters:alex-example"
    assert letters_child_id("Zoë O'Neil") == "letters:zoë-o-neil"
    assert letters_child_id("Alex Example") == letters_child_id("alex example")
