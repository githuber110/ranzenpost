import pathlib

import pytest
import requests

from app.iserv.client import IServClient, LOGIN_FAILED_MARKER, SESSION_COOKIE, password_outcome
from app.iserv.errors import DataError
from app.iserv.twofactor import ROW_ID_PREFIX

TOKEN_PAGE = (
    "<html><body><table><tbody>"
    f'<tr id="{ROW_ID_PREFIX}uuid-1"><td>Ranzenpost</td></tr>'
    "</tbody></table></body></html>"
)
EMPTY_TOKEN_PAGE = "<html><body><table><tbody></tbody></table></body></html>"
RATE_LIMIT_PAGE = "<html><body><h1>Zu viele Versuche</h1></body></html>"
TWO_FACTOR_PAGE = (
    '<html><body><form action="/iserv/auth/twofactor" method="post">'
    '<input name="otp"><input name="_token" value="t">'
    "</form></body></html>"
)
LOGIN_PAGE = (
    '<html><body><form action="/iserv/login_check" method="post">'
    '<input name="_username" type="text"><input name="_password" type="password">'
    "</form></body></html>"
)
PORTAL_PAGE = "<html><body><h1>Schulportal</h1></body></html>"
FAILED_PAGE = f"<html><body><p>{LOGIN_FAILED_MARKER}</p></body></html>"


class FakeAnswer:
    def __init__(self, status_code=200, text="", url="https://school.example/iserv/"):
        self.status_code = status_code
        self.text = text
        self.url = url


class RecordingSession:
    def __init__(self, pages=None, delete_status=200):
        self.pages = pages or {}
        self.delete_status = delete_status
        self.headers = {}
        self.deleted = []

    def get(self, url, **kwargs):
        for path, page in self.pages.items():
            if path in url:
                return page
        return FakeAnswer(200, "", url)

    def request(self, method, url, **kwargs):
        self.deleted.append(url)
        return FakeAnswer(self.delete_status, "", url)


def _client(session):
    return IServClient("https://school.example", session=session)


def test_a_token_page_the_server_refused_is_never_read_as_an_empty_token_list():
    session = RecordingSession(pages={"twofactor": FakeAnswer(403, RATE_LIMIT_PAGE)})
    with pytest.raises(DataError):
        _client(session).list_totp_token_rows()
    with pytest.raises(DataError):
        _client(session).list_totp_tokens()


def test_a_delete_the_server_refused_is_never_reported_as_a_removal():
    session = RecordingSession(
        pages={"twofactor": FakeAnswer(200, EMPTY_TOKEN_PAGE)}, delete_status=403
    )
    with pytest.raises(DataError):
        _client(session).delete_totp_token("uuid-1", "000000", "csrf")
    assert session.deleted, "the delete was never attempted, so the guard proves nothing"


def test_a_delete_that_worked_is_still_reported_as_a_removal():
    session = RecordingSession(pages={"twofactor": FakeAnswer(200, EMPTY_TOKEN_PAGE)})
    assert _client(session).delete_totp_token("uuid-1", "000000", "csrf") is True


def test_a_token_that_is_still_listed_is_not_reported_as_removed():
    session = RecordingSession(pages={"twofactor": FakeAnswer(200, TOKEN_PAGE)})
    assert _client(session).delete_totp_token("uuid-1", "000000", "csrf") is False


def test_a_password_is_only_called_accepted_on_a_positive_signal():
    assert password_outcome(FakeAnswer(200, TWO_FACTOR_PAGE), set()) is True
    assert password_outcome(FakeAnswer(200, PORTAL_PAGE), {SESSION_COOKIE}) is True


def test_a_wrong_password_is_still_recognised():
    assert password_outcome(FakeAnswer(200, FAILED_PAGE), set()) is False


@pytest.mark.parametrize(
    "answer",
    [
        FakeAnswer(500, "<html><body>Fehler</body></html>"),
        FakeAnswer(429, RATE_LIMIT_PAGE),
        FakeAnswer(200, RATE_LIMIT_PAGE),
        FakeAnswer(200, LOGIN_PAGE),
        FakeAnswer(200, ""),
    ],
)
def test_an_answer_that_proves_nothing_is_reported_as_unknown_not_as_accepted(answer):
    assert password_outcome(answer, set()) is None


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_a_refused_request_is_unknown_even_when_its_body_looks_like_a_signed_in_page(status):
    assert password_outcome(FakeAnswer(status, TWO_FACTOR_PAGE), set()) is None
    assert password_outcome(FakeAnswer(status, PORTAL_PAGE), {SESSION_COOKIE}) is None


CONTINUE_PAGE = (pathlib.Path(__file__).resolve().parent / "fixtures" / "auth_continue.html").read_text(
    encoding="utf-8"
)


class FakeCookie:
    def __init__(self, name):
        self.name = name


class ProbeSession:
    def __init__(self, login_page, answer, after_redirect=None, cookie_after_redirect=True):
        self.login_page = login_page
        self.answer = answer
        self.after_redirect = after_redirect
        self.cookie_after_redirect = cookie_after_redirect
        self.headers = {}
        self.cookies = []
        self.visited = []

    def get(self, url, **kwargs):
        self.visited.append(url)
        if len(self.visited) == 1:
            return self.login_page
        if self.cookie_after_redirect:
            self.cookies = [FakeCookie(SESSION_COOKIE)]
        return self.after_redirect or FakeAnswer(200, PORTAL_PAGE, url)

    def post(self, url, **kwargs):
        return self.answer

    def close(self):
        pass


def _probing_client(probe):
    client = _client(RecordingSession())
    client.username = "parent"
    client._probe_session = lambda: probe
    return client


def test_a_correct_password_without_two_factor_is_recognised_through_the_continue_page():
    probe = ProbeSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, CONTINUE_PAGE))
    assert _probing_client(probe).accepts_password("secret") is True
    assert len(probe.visited) > 1, "the continue page was never followed"


def test_a_continue_page_that_never_signs_the_probe_in_stays_unknown():
    probe = ProbeSession(
        FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, CONTINUE_PAGE), cookie_after_redirect=False
    )
    assert _probing_client(probe).accepts_password("secret") is None


def test_a_wrong_password_is_still_recognised_through_the_probe():
    probe = ProbeSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, FAILED_PAGE))
    assert _probing_client(probe).accepts_password("secret") is False


def test_the_probe_never_reports_a_password_as_accepted_after_a_network_failure():
    class Dead:
        headers = {}
        cookies = []

        def get(self, url, **kwargs):
            raise requests.ConnectionError("down")

        def post(self, url, **kwargs):
            raise requests.ConnectionError("down")

        def close(self):
            pass

    client = _client(RecordingSession())
    client.username = "parent"
    client._probe_session = lambda: Dead()
    assert client.accepts_password("secret") is None


REJECT_HTML = "<html><body><ul><li>Das Passwort ist zu kurz.</li></ul></body></html>"


def _client_with_probe(outcomes):
    client = _client(RecordingSession())
    client.username = "parent"
    client.sleeper = lambda seconds: None
    client.accepts_password = lambda password: outcomes.get(password)
    return client


def test_a_password_change_the_server_refused_is_never_stored_as_probably_done():
    from app.iserv.client import PASSWORD_UNVERIFIED
    from app.iserv.errors import PasswordError

    client = _client_with_probe({"new": False, "old": None})
    with pytest.raises(PasswordError) as caught:
        client._verify_password_change("old", "new", REJECT_HTML)
    assert str(caught.value) != PASSWORD_UNVERIFIED, (
        "the service stores the new password on exactly this message, so a refused change would "
        "overwrite the working one"
    )


def test_a_password_change_that_worked_is_still_reported_as_done():
    client = _client_with_probe({"new": True, "old": None})
    assert client._verify_password_change("old", "new", REJECT_HTML) is True


def test_an_unreadable_token_page_does_not_abort_the_two_factor_registration():
    from app.iserv.twofactor import TwoFactorRegistration

    class Refusing(RecordingSession):
        def post(self, url, **kwargs):
            return FakeAnswer(200, "<html><body>ok</body></html>", url)

    session = Refusing(pages={"twofactor": FakeAnswer(500, "<html><body>Fehler</body></html>")})
    client = _client(session)
    registration = TwoFactorRegistration(
        action="/iserv/auth/settings/twofactor/add",
        secret="JBSWY3DPEHPK3PXP",
        token="csrf",
        fields={},
    )
    assert client.confirm_totp_registration(registration, "Ranzenpost", "000000") == registration.secret
