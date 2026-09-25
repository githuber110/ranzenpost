import json
from pathlib import Path

import pytest

from app.iserv.client import IServClient
from app.iserv.errors import DataError, LoginError, PasswordError, TwoFactorError

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://school.example"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeCookie:
    def __init__(self, name):
        self.name = name


class FakeResponse:
    def __init__(self, text="", url="", status_code=200, json_data=None):
        self.text = text
        self.url = url
        self.status_code = status_code
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    def __init__(self, login_failed=False):
        self.headers = {}
        self.cookies = []
        self.login_failed = login_failed
        self.two_factor_data = None
        self.login_data = None

    def get(self, url, timeout=None, params=None):
        if "authentication/redirect" in url:
            self.cookies = [FakeCookie("IServSAT"), FakeCookie("IServSATId"), FakeCookie("IServSession")]
            return FakeResponse(read("portal.html"), f"{BASE}/iserv/")
        if "time-table/data" in url:
            return FakeResponse(url=url, json_data=json.loads(read("timetable_data.json")))
        if "time-table/" in url:
            return FakeResponse(read("timetable_page.html"), url)
        return FakeResponse(read("login_page.html"), f"{BASE}/iserv/auth/login?step1")

    def post(self, url, data=None, timeout=None, allow_redirects=True):
        if "auth/login" in url:
            self.login_data = data
            if self.login_failed:
                return FakeResponse("Anmeldung fehlgeschlagen", url)
            return FakeResponse(read("twofactor_page.html"), f"{BASE}/iserv/auth/twofactor/confirm?step2")
        if "twofactor/confirm" in url:
            self.two_factor_data = data
            return FakeResponse(read("auth_continue.html"), f"{BASE}/iserv/auth/auth?authok")
        return FakeResponse(read("portal.html"), url)


def make_client(**kwargs):
    session = FakeSession(**kwargs)
    return IServClient(BASE, session=session), session


def test_login_completes_full_two_factor_flow():
    client, session = make_client()
    client.login("parent", "secret", lambda: "451884")
    assert client.is_authenticated()
    assert session.login_data["_username"] == "parent"
    assert session.two_factor_data["otp"] == "451884"
    assert session.two_factor_data["_csrf_token"] == "csrf-token-example"


def test_login_remembers_the_login_page_it_was_served():
    client, _ = make_client()
    assert client.login_page == ""
    client.login("parent", "secret", lambda: "451884")
    assert client.login_page == read("login_page.html")


def test_login_raises_on_wrong_credentials():
    client, _ = make_client(login_failed=True)
    with pytest.raises(LoginError):
        client.login("parent", "wrong", lambda: "000000")


def test_get_children_after_login():
    client, _ = make_client()
    client.login("parent", "secret", lambda: "451884")
    children = client.get_children()
    assert [child.name for child in children] == ["Alex Example", "Robin Example"]


def test_get_timetable_after_login():
    client, _ = make_client()
    client.login("parent", "secret", lambda: "451884")
    week = client.get_timetable("11111111-1111-4111-8111-111111111111")
    assert week.last_updated == "22.07.2026 12:25"
    assert len(week.combined) == 2


def test_get_timetable_always_sends_child_id_for_a_two_child_account():
    calls = []

    class RecordingSession(FakeSession):
        def get(self, url, timeout=None, params=None):
            if "time-table/data" in url:
                calls.append(params)
            return super().get(url, timeout=timeout, params=params)

    client = IServClient(BASE, session=RecordingSession())
    client.login("parent", "secret", lambda: "451884")
    children = client.get_children()
    assert len(children) == 2
    for child in children:
        client.get_timetable(child.child_id)
    assert len(calls) == 2
    for params, child in zip(calls, children):
        assert params["childId"] == child.child_id
        assert json.loads(params["filter"])["child"] == child.child_id


def test_get_timetable_reports_a_403_as_area_forbidden_not_a_login_failure():
    from app.iserv.children import CHILD_PAGE_FORBIDDEN_KEY

    class ForbiddenSession(FakeSession):
        def get(self, url, timeout=None, params=None):
            if "time-table/data" in url:
                return FakeResponse("forbidden", url, status_code=403)
            return super().get(url, timeout=timeout, params=params)

    client = IServClient(BASE, session=ForbiddenSession())
    client.login("parent", "secret", lambda: "451884")
    with pytest.raises(DataError) as excinfo:
        client.get_timetable("22222222-2222-4222-8222-222222222222")
    assert excinfo.value.message_key == CHILD_PAGE_FORBIDDEN_KEY
    assert not isinstance(excinfo.value, LoginError)


def test_fetch_or_raise_returns_the_response_on_success():
    client, _ = make_client()
    client.login("parent", "secret", lambda: "451884")
    response = client.fetch_or_raise("/iserv/time-table/")
    assert response.status_code == 200


def test_fetch_or_raise_raises_on_a_non_200_response():
    class FailingSession(FakeSession):
        def get(self, url, timeout=None, params=None):
            return FakeResponse("gone", url, status_code=404)

    client = IServClient(BASE, session=FailingSession())
    with pytest.raises(DataError):
        client.fetch_or_raise("/iserv/parentconference/attendee/")


def test_fetch_or_raise_reports_a_server_error_as_an_outage():
    from app.iserv.errors import OutageError

    class FailingSession(FakeSession):
        def get(self, url, timeout=None, params=None):
            return FakeResponse("maintenance", url, status_code=503)

    client = IServClient(BASE, session=FailingSession())
    with pytest.raises(OutageError) as caught:
        client.fetch_or_raise("/iserv/parentconference/attendee/")
    assert caught.value.reason == "status:503"


class SecuritySession:
    def __init__(self, page, post_result, token_list="twofactor_list.html", deleted_list=None):
        self.headers = {}
        self.cookies = []
        self.page = page
        self.post_result = post_result
        self.token_list = token_list
        self.deleted_list = deleted_list
        self.posted = None
        self.posted_url = None
        self.posted_once = False
        self.requested = []
        self.deleted = None
        self.deleted_url = None
        self.deleted_method = None

    def get(self, url, timeout=None, params=None):
        self.requested.append(url)
        if url.endswith("/iserv/auth/settings/twofactor/"):
            if self.deleted is not None and self.deleted_list:
                return FakeResponse(read(self.deleted_list), url)
            listing = self.token_list if self.posted_once else "twofactor_list_empty.html"
            return FakeResponse(read(listing), url)
        return FakeResponse(read(self.page), url)

    def post(self, url, data=None, timeout=None, allow_redirects=True):
        self.posted = data
        self.posted_url = url
        self.posted_once = True
        self.followed = allow_redirects
        return FakeResponse(read(self.post_result), url)

    def request(self, method, url, data=None, timeout=None):
        self.deleted_method = method
        self.deleted = data
        self.deleted_url = url
        return FakeResponse("", url)


def test_register_totp_submits_confirm_form_and_returns_secret():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html")
    client = IServClient(BASE, session=session)
    secret = client.register_totp("ISERV-Connector", "123456")
    assert secret == "JBSWY3DPEHPK3PXP"
    assert session.posted["confirm[name]"] == "ISERV-Connector"
    assert session.posted["confirm[verification]"] == "123456"
    assert session.posted["confirm[_fake_username]"] == ""
    assert session.posted["confirm[_token]"] == "csrf-confirm-token"
    assert len(session.posted["confirm[code]"]) == 6
    assert session.posted["confirm[code]"].isdigit()


def test_register_totp_rejected_raises_with_the_server_message():
    session = SecuritySession("security_2fa_add.html", "security_2fa_rejected.html",
                              token_list="twofactor_list_empty.html")
    client = IServClient(BASE, session=session)
    with pytest.raises(TwoFactorError) as error:
        client.register_totp("ISERV-Connector", "000000")
    assert "2FA-Code" in str(error.value)


def test_register_totp_trusts_the_token_list_over_the_response_text():
    session = SecuritySession("security_2fa_add.html", "security_2fa_rejected.html")
    client = IServClient(BASE, session=session)
    assert client.register_totp("ISERV-Connector", "123456") == "JBSWY3DPEHPK3PXP"


def test_register_totp_fails_when_the_token_never_appears():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html",
                              token_list="twofactor_list_empty.html")
    client = IServClient(BASE, session=session)
    with pytest.raises(TwoFactorError):
        client.register_totp("ISERV-Connector", "123456")


def test_change_password_success():
    session = SecuritySession("security_password.html", "security_password_ok.html")
    client = IServClient(BASE, session=session)
    assert client.change_password("old-pass", "new-pass-123") is True
    assert session.posted["password_change[current]"] == "old-pass"
    assert session.posted["password_change[new][first]"] == "new-pass-123"
    assert session.posted["password_change[new][second]"] == "new-pass-123"
    assert session.posted["password_change[_token]"] == "csrf-password-token"


def test_change_password_rejected_raises():
    session = SecuritySession("security_password.html", "security_password_bad.html")
    client = IServClient(BASE, session=session)
    with pytest.raises(PasswordError):
        client.change_password("wrong", "new-pass-123")


def test_register_totp_reads_the_add_page_and_posts_to_the_htmx_target():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html")
    client = IServClient(BASE, session=session)
    secret = client.register_totp("ISERV-Connector", "123456")
    assert secret == "JBSWY3DPEHPK3PXP"
    assert session.requested[0] == BASE + "/iserv/auth/settings/twofactor/add"
    assert session.posted_url == BASE + "/iserv/auth/settings/twofactor/add/confirm"


def test_url_rejects_an_absolute_path_on_a_foreign_host():
    client = IServClient(BASE, session=SecuritySession("security_2fa_add.html", "security_2fa_added.html"))
    with pytest.raises(DataError):
        client._url("https://evil.example/steal")


def test_url_allows_an_absolute_path_on_the_same_origin():
    client = IServClient(BASE, session=SecuritySession("security_2fa_add.html", "security_2fa_added.html"))
    assert client._url(BASE + "/iserv/x") == BASE + "/iserv/x"


def test_list_totp_token_rows_returns_name_and_uuid():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html", token_list="twofactor_list_uuid.html")
    session.posted_once = True
    client = IServClient(BASE, session=session)
    rows = client.list_totp_token_rows()
    assert rows == [{"name": "ISERV-Connector", "uuid": "b2b6b8b0-1111-4a2a-9c3c-abcdef123456"}]


def test_delete_totp_token_sends_the_exact_form_shape_to_the_delete_path():
    session = SecuritySession(
        "security_2fa_add.html", "security_2fa_added.html",
        token_list="twofactor_list_uuid.html", deleted_list="twofactor_list_uuid_removed.html",
    )
    session.posted_once = True
    client = IServClient(BASE, session=session)
    removed = client.delete_totp_token("b2b6b8b0-1111-4a2a-9c3c-abcdef123456", "654321", "csrf-delete-token")
    assert removed is True
    assert session.deleted_method == "DELETE"
    assert session.deleted_url == BASE + "/iserv/auth/settings/twofactor/delete/b2b6b8b0-1111-4a2a-9c3c-abcdef123456"
    assert session.deleted == {"delete[code]": "654321", "delete[_token]": "csrf-delete-token"}


def test_delete_totp_token_reports_false_when_the_row_is_still_present():
    session = SecuritySession(
        "security_2fa_add.html", "security_2fa_added.html",
        token_list="twofactor_list_uuid.html", deleted_list="twofactor_list_uuid.html",
    )
    session.posted_once = True
    client = IServClient(BASE, session=session)
    removed = client.delete_totp_token("b2b6b8b0-1111-4a2a-9c3c-abcdef123456", "654321", "csrf-delete-token")
    assert removed is False


def test_post_absolute_rejects_a_foreign_host():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html")
    client = IServClient(BASE, session=session)
    with pytest.raises(DataError):
        client.post_absolute("https://evil.example/steal", data={})
    assert session.posted_url is None


def test_post_absolute_posts_on_the_same_origin():
    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html")
    client = IServClient(BASE, session=session)
    client.post_absolute(BASE + "/iserv/x", data={"a": "b"})
    assert session.posted_url == BASE + "/iserv/x"



def test_the_time_table_page_counts_as_absent_when_the_account_does_not_get_it():
    class PageSession(FakeSession):
        answer = (404, "/iserv/time-table/", "")

        def get(self, url, timeout=None, params=None):
            if url.endswith("/iserv/time-table/"):
                status, path, text = self.answer
                return FakeResponse(text, BASE + path, status_code=status)
            return super().get(url, timeout=timeout, params=params)

    session = PageSession()
    client = IServClient(BASE, session=session)
    cases = {
        (404, "/iserv/time-table/", ""): "status 404",
        (403, "/iserv/time-table/", "<h1>Riverside Primary</h1>"): "status 403",
        (200, "/iserv/", "<nav></nav>"): "redirect",
    }
    for answer, reason in cases.items():
        session.answer = answer
        page = client.read_time_table_page()
        assert page.absent == reason, answer
        assert page.children == []
    for answer in (
        (401, "/iserv/time-table/", ""),
        (200, "/iserv/auth/login", "<form><input name='_password'></form>"),
        (200, "/iserv/time-table/", "<form><input name='_password'></form>"),
    ):
        session.answer = answer
        with pytest.raises(DataError) as expired:
            client.read_time_table_page()
        assert expired.value.message_key == "api.schoolApp.sessionExpired", answer
    session.answer = (200, "/iserv/time-table/", "<p>Wartung</p>")
    with pytest.raises(DataError) as excinfo:
        client.read_time_table_page()
    assert excinfo.value.detail["recognised"] is False


def test_the_time_table_page_lists_its_child_options():
    client, _ = make_client()
    client.login("parent", "secret", lambda: "451884")
    page = client.read_time_table_page()
    assert page.absent == ""
    assert page.select is True
    assert [child.name for child in page.children] == ["Alex Example", "Robin Example"]


def test_a_time_table_answer_that_is_no_object_is_a_shape_error():
    from app.iserv.timetable import TIMETABLE_SHAPE_KEY, parse_time_table

    with pytest.raises(DataError) as excinfo:
        parse_time_table([{"x": 1}])
    assert excinfo.value.message_key == TIMETABLE_SHAPE_KEY
    assert excinfo.value.detail["shape"][0] == "(root): array len 1 of object"


def test_a_time_table_week_without_a_child_leaves_the_child_out_of_the_query():
    from datetime import date

    from app.iserv.timetable import data_params

    params = data_params("", date(2026, 9, 9))
    assert params == {"filter": '{"startDate":"07.09.2026","endDate":"13.09.2026","classes":[],"teachers":[],"rooms":[]}'}
