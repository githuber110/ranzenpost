import pytest
import requests

from app.iserv.client import IServClient, LOGIN_FAILED_MARKER, SESSION_COOKIE
from app.iserv.errors import LoginError, OutageError, TwoFactorError, transport_outage
from app.iserv_prober import IServProber

LOGIN_PAGE = (
    '<html><body><form action="/iserv/login_check" method="post">'
    '<input name="_username" type="text"><input name="_password" type="password">'
    "</form></body></html>"
)
TWO_FACTOR_PAGE = (
    '<html><body><form action="/iserv/auth/twofactor" method="post">'
    '<input name="otp"><input name="_token" value="t">'
    "</form></body></html>"
)
FAILED_PAGE = f"<html><body><p>{LOGIN_FAILED_MARKER}</p></body></html>"
MAINTENANCE_PAGE = "<html><body><h1>Wartungsarbeiten</h1><p>IServ ist in Kürze wieder da.</p></body></html>"
BLANK_PAGE = "<html><body><h1>Willkommen</h1></body></html>"
PORTAL_PAGE = "<html><body><h1>Schulportal</h1></body></html>"


class FakeAnswer:
    def __init__(self, status_code=200, text="", url="https://school.example/iserv/", headers=None):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = headers or {}


class FakeCookie:
    def __init__(self, name):
        self.name = name


class ScriptedSession:
    def __init__(self, page, answer=None, second=None, signs_in=False):
        self.page = page
        self.answer = answer
        self.second = second
        self.signs_in = signs_in
        self.headers = {}
        self.cookies = []
        self.posts = 0

    def get(self, url, **kwargs):
        if isinstance(self.page, Exception):
            raise self.page
        return self.page

    def post(self, url, **kwargs):
        self.posts += 1
        chosen = self.answer if self.posts == 1 else self.second
        if isinstance(chosen, Exception):
            raise chosen
        if self.signs_in and self.posts == (2 if self.second is not None else 1):
            self.cookies = [FakeCookie(SESSION_COOKIE)]
        return chosen


def _login(session, code="123456"):
    return IServClient("https://school.example", session=session).login("parent", "secret", lambda: code)


def _dns_failure():
    inner = ConnectionError("HTTPSConnectionPool(host='school.example', port=443): Max retries exceeded with url: /iserv/ (Caused by NameResolutionError(\"<urllib3.connection.HTTPSConnection object>: Failed to resolve 'school.example' ([Errno 11001] getaddrinfo failed)\"))")
    return requests.ConnectionError(str(inner))


def _refused_failure():
    return requests.ConnectionError(
        "HTTPSConnectionPool(host='school.example', port=443): Max retries exceeded with url: /iserv/ "
        "(Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object>: Failed to establish a new "
        "connection: [WinError 10061] No connection could be made because the target machine actively refused it'))"
    )


@pytest.mark.parametrize(
    "failure,reason",
    [
        (requests.ConnectTimeout("connect timed out"), "timeout"),
        (requests.ReadTimeout("read timed out"), "timeout"),
        (_dns_failure(), "dns"),
        (_refused_failure(), "refused"),
        (requests.ConnectionError("Connection reset by peer"), "connection"),
    ],
)
def test_a_transport_failure_while_fetching_the_login_page_is_an_outage(failure, reason):
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(failure))
    assert caught.value.reason == reason
    assert not isinstance(caught.value, LoginError)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_server_error_on_the_login_page_is_an_outage_with_its_status(status):
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(status, MAINTENANCE_PAGE)))
    assert caught.value.reason == f"status:{status}"


def test_a_429_on_the_login_page_is_an_outage_that_honours_retry_after_seconds():
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(429, "slow down", headers={"Retry-After": "120"})))
    assert caught.value.reason == "rate_limited"
    assert caught.value.retry_after == 120
    assert not isinstance(caught.value, LoginError)


def test_a_429_while_posting_credentials_is_an_outage_not_bad_credentials():
    session = ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(429, "slow down"))
    with pytest.raises(OutageError) as caught:
        _login(session)
    assert caught.value.reason == "rate_limited"
    assert caught.value.retry_after is None
    assert not isinstance(caught.value, LoginError)


def test_a_429_retry_after_as_an_http_date_is_converted_to_seconds_and_capped(monkeypatch):
    from datetime import datetime, timezone

    import app.iserv.errors as errors_module

    fixed_now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(errors_module, "datetime", FixedDatetime)
    future = "Wed, 23 Sep 2026 12:05:00 GMT"
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(429, "slow down", headers={"Retry-After": future})))
    assert caught.value.retry_after == 300


def test_a_maintenance_page_without_a_login_form_is_an_outage():
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(200, MAINTENANCE_PAGE)))
    assert caught.value.reason == "maintenance_page"


def test_an_unexpected_page_without_a_login_form_is_an_outage_not_a_login_failure():
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(200, BLANK_PAGE)))
    assert caught.value.reason == "unexpected"


def test_a_transport_failure_while_posting_the_credentials_is_an_outage():
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(200, LOGIN_PAGE), requests.ReadTimeout("read timed out")))
    assert caught.value.reason == "timeout"


def test_a_server_error_while_posting_the_credentials_is_an_outage():
    with pytest.raises(OutageError) as caught:
        _login(ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(503, MAINTENANCE_PAGE)))
    assert caught.value.reason == "status:503"


def test_a_login_form_that_rejects_the_credentials_stays_a_login_failure():
    with pytest.raises(LoginError):
        _login(ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, FAILED_PAGE)))


def test_a_login_form_that_accepts_the_credentials_signs_in():
    session = ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, PORTAL_PAGE), signs_in=True)
    assert _login(session).is_authenticated()


def test_a_wrong_second_factor_stays_a_two_factor_failure():
    session = ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, TWO_FACTOR_PAGE), FakeAnswer(200, TWO_FACTOR_PAGE))
    with pytest.raises(TwoFactorError):
        _login(session)


def test_a_server_error_after_the_second_factor_is_an_outage_not_a_wrong_code():
    session = ScriptedSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, TWO_FACTOR_PAGE), FakeAnswer(502, ""))
    with pytest.raises(OutageError) as caught:
        _login(session)
    assert caught.value.reason == "status:502"


def test_an_outage_still_counts_as_a_request_failure_for_handlers_that_only_know_network():
    assert issubclass(OutageError, requests.RequestException)
    assert not issubclass(OutageError, LoginError)
    assert not issubclass(OutageError, TwoFactorError)
    error = transport_outage(requests.ConnectTimeout("x"))
    assert error.reason == "timeout"
    assert error.message_key
    assert str(error)


def test_the_message_of_an_outage_never_carries_the_school_host(monkeypatch):
    error = transport_outage(_dns_failure())
    assert "school.example" not in str(error)
    assert "school.example" not in str(error.detail)


class ProberSession(ScriptedSession):
    pass


def _prober_with(monkeypatch, session):
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: session)
    return IServProber()


def test_the_wizard_probe_reports_an_outage_instead_of_an_unknown_answer(monkeypatch):
    prober = _prober_with(monkeypatch, ProberSession(FakeAnswer(503, MAINTENANCE_PAGE)))
    assert prober.verify_login("https://school.example", "parent", "secret") == "outage"


def test_the_wizard_probe_reports_a_dead_host_as_an_outage(monkeypatch):
    prober = _prober_with(monkeypatch, ProberSession(requests.ConnectTimeout("x")))
    assert prober.verify_login("https://school.example", "parent", "secret") == "outage"


def test_the_wizard_probe_still_tells_bad_credentials_apart(monkeypatch):
    prober = _prober_with(monkeypatch, ProberSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, FAILED_PAGE)))
    assert prober.verify_login("https://school.example", "parent", "secret") == "bad_credentials"


def test_the_wizard_probe_still_recognises_the_second_factor_form(monkeypatch):
    prober = _prober_with(monkeypatch, ProberSession(FakeAnswer(200, LOGIN_PAGE), FakeAnswer(200, TWO_FACTOR_PAGE)))
    assert prober.verify_login("https://school.example", "parent", "secret") == "twofactor"


class PageSession:
    def __init__(self, answer):
        self.answer = answer
        self.headers = {}
        self.cookies = []

    def get(self, url, **kwargs):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_server_error_on_a_data_page_of_a_signed_in_session_is_an_outage(status):
    from app.iserv.errors import DataError

    client = IServClient("https://school.example", session=PageSession(FakeAnswer(status, MAINTENANCE_PAGE)))
    with pytest.raises(OutageError) as caught:
        client.get_children()
    assert caught.value.reason == f"status:{status}"
    with pytest.raises(OutageError):
        client.fetch_or_raise("/iserv/auth/settings/twofactor/")
    assert not isinstance(caught.value, DataError)


def test_a_refused_data_page_stays_a_data_error_not_an_outage():
    from app.iserv.errors import DataError

    client = IServClient("https://school.example", session=PageSession(FakeAnswer(403, BLANK_PAGE)))
    with pytest.raises(DataError) as caught:
        client.get_children()
    assert not isinstance(caught.value, OutageError)
