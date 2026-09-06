import pytest

from app.iserv.client import (
    LOGIN_CREDENTIALS_KEY,
    LOGIN_FAILED_MARKER,
    LOGIN_SESSION_KEY,
    LOGIN_TWOFACTOR_KEY,
    REGISTRATION_UNCONFIRMED_KEY,
    SESSION_COOKIE,
    IServClient,
)
from app.iserv.errors import LoginError, TwoFactorError
from app.iserv.twofactor import ROW_ID_PREFIX, TwoFactorRegistration

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
PORTAL_PAGE = "<html><body><h1>Schulportal</h1></body></html>"
FAILED_PAGE = f"<html><body><p>{LOGIN_FAILED_MARKER}</p></body></html>"
REFUSED_PAGE = "<html><head><title>Zugriff verweigert</title></head><body></body></html>"


def token_page(*names):
    rows = "".join(
        f'<tr id="{ROW_ID_PREFIX}u{index}"><td>{name}</td></tr>'
        for index, name in enumerate(names)
    )
    return f"<html><body><table><tbody>{rows}</tbody></table></body></html>"


class FakeAnswer:
    def __init__(self, status_code=200, text="", url="https://school.example/iserv/"):
        self.status_code = status_code
        self.text = text
        self.url = url
        self.headers = {}


class Cookie:
    def __init__(self, name):
        self.name = name


class Server:
    def __init__(self, pages, post_answers, cookie_after=None, pages_after=None):
        self.pages = pages
        self.pages_after = pages_after or {}
        self.post_answers = list(post_answers)
        self.cookie_after = cookie_after
        self.headers = {}
        self.cookies = []
        self.posts = 0

    def get(self, url, **kwargs):
        source = self.pages_after if self.posts and self.pages_after else self.pages
        for fragment, page in source.items():
            if fragment in url:
                return page
        return FakeAnswer(200, "", url)

    def post(self, url, data=None, **kwargs):
        self.posts += 1
        if self.cookie_after is not None and self.posts >= self.cookie_after:
            self.cookies = [Cookie(SESSION_COOKIE)]
        return self.post_answers.pop(0) if self.post_answers else FakeAnswer(200, PORTAL_PAGE, url)

    def request(self, method, url, **kwargs):
        return FakeAnswer(200, "", url)


def _client(server):
    return IServClient("https://school.example", session=server)


def test_a_refused_password_names_the_credentials_stage():
    server = Server({"/iserv/": FakeAnswer(200, LOGIN_PAGE)}, [FakeAnswer(200, FAILED_PAGE)])
    with pytest.raises(LoginError) as caught:
        _client(server).login("parent", "wrong", lambda: "000000")
    assert caught.value.message_key == LOGIN_CREDENTIALS_KEY
    assert caught.value.detail["login_stage"] == "credentials"
    assert caught.value.detail["two_factor_offered"] is False


def test_a_refused_code_is_told_apart_from_a_session_that_never_opened():
    server = Server(
        {"/iserv/": FakeAnswer(200, LOGIN_PAGE)},
        [FakeAnswer(200, TWO_FACTOR_PAGE), FakeAnswer(200, TWO_FACTOR_PAGE)],
    )
    with pytest.raises(TwoFactorError) as caught:
        _client(server).login("parent", "right", lambda: "000000")
    assert caught.value.message_key == LOGIN_TWOFACTOR_KEY
    assert caught.value.detail["two_factor_offered"] is True
    assert caught.value.detail["two_factor_again"] is True


def test_a_login_that_ends_nowhere_says_the_session_never_opened():
    server = Server(
        {"/iserv/": FakeAnswer(200, LOGIN_PAGE)},
        [FakeAnswer(403, REFUSED_PAGE)],
    )
    with pytest.raises(TwoFactorError) as caught:
        _client(server).login("parent", "right", lambda: "000000")
    assert caught.value.message_key == LOGIN_SESSION_KEY
    assert caught.value.detail["login_stage"] == "session"
    assert caught.value.detail["refusal"] == "Zugriff verweigert"


def test_a_login_that_works_still_works():
    server = Server(
        {"/iserv/": FakeAnswer(200, LOGIN_PAGE)},
        [FakeAnswer(200, TWO_FACTOR_PAGE), FakeAnswer(200, PORTAL_PAGE)],
        cookie_after=2,
    )
    assert _client(server).login("parent", "right", lambda: "000000") is not None


REGISTRATION = TwoFactorRegistration(
    action="/iserv/auth/settings/twofactor/add",
    secret="JBSWY3DPEHPK3PXP",
    token="csrf",
    fields={},
)


def _registering(list_page, confirm_answer, list_after=None):
    server = Server(
        {"twofactor": list_page},
        [confirm_answer],
        pages_after={"twofactor": list_after} if list_after else None,
    )
    return _client(server)


def test_a_registration_the_server_confirmed_is_accepted():
    client = _registering(
        FakeAnswer(200, token_page()),
        FakeAnswer(200, "<html><body>weiter</body></html>"),
        list_after=FakeAnswer(200, token_page("Ranzenpost")),
    )
    assert client.confirm_totp_registration(REGISTRATION, "Ranzenpost", "000000") == REGISTRATION.secret


def test_a_registration_the_list_does_not_show_afterwards_is_refused():
    client = _registering(
        FakeAnswer(200, token_page()),
        FakeAnswer(200, "<html><body>weiter</body></html>"),
        list_after=FakeAnswer(200, token_page()),
    )
    with pytest.raises(TwoFactorError) as caught:
        client.confirm_totp_registration(REGISTRATION, "Ranzenpost", "000000")
    assert caught.value.message_key == REGISTRATION_UNCONFIRMED_KEY


def test_a_registration_nobody_confirmed_is_refused_instead_of_stored():
    client = _registering(FakeAnswer(403, REFUSED_PAGE), FakeAnswer(200, "<html><body>weiter</body></html>"))
    with pytest.raises(TwoFactorError) as caught:
        client.confirm_totp_registration(REGISTRATION, "Ranzenpost", "000000")
    assert caught.value.message_key == REGISTRATION_UNCONFIRMED_KEY
    assert caught.value.detail["token_listed"] is False


def test_a_registration_the_answer_lists_counts_even_when_the_list_page_is_refused():
    client = _registering(FakeAnswer(403, REFUSED_PAGE), FakeAnswer(200, token_page("Ranzenpost")))
    assert client.confirm_totp_registration(REGISTRATION, "Ranzenpost", "000000") == REGISTRATION.secret


def test_a_rejected_code_keeps_its_own_wording():
    client = _registering(
        FakeAnswer(403, REFUSED_PAGE),
        FakeAnswer(200, "<html><body><p>Ungültiger Code</p></body></html>"),
    )
    with pytest.raises(TwoFactorError) as caught:
        client.confirm_totp_registration(REGISTRATION, "Ranzenpost", "000000")
    assert caught.value.message_key != REGISTRATION_UNCONFIRMED_KEY
