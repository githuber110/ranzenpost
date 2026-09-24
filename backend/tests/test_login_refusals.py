import pytest

from app.iserv.client import SESSION_COOKIE, IServClient
from app.iserv.errors import (
    REASON_BAD_CREDENTIALS,
    REASON_DEFAULT_PASSWORD,
    REASON_LOCKED,
    REASON_TWOFACTOR_SETUP,
    REASON_UNKNOWN_ACCOUNT,
    LoginError,
    TwoFactorSetupRequired,
    login_reason,
)
from app.iserv.twofactor import setup_required
from app.iserv_prober import IServProber
from app.lockout import (
    DEFAULT_PASSWORD_BLOCKED,
    TWOFACTOR_REQUIRED_SETUP,
    UNKNOWN_ACCOUNT,
    classify_login_response,
    human_message,
    login_refusal,
)

SETUP_URL = "https://school.example/iserv/auth/twofactor/setup"
PORTAL_URL = "https://school.example/iserv/"


class Answer:
    def __init__(self, text, url=PORTAL_URL, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {}


class Cookie:
    def __init__(self, name):
        self.name = name


class School:
    def __init__(self, login_page, answer, signs_in=False):
        self.login_page = login_page
        self.answer = answer
        self.signs_in = signs_in
        self.headers = {}
        self.cookies = []
        self.posts = 0

    def get(self, url, **kwargs):
        return self.login_page

    def post(self, url, data=None, **kwargs):
        self.posts += 1
        if self.signs_in:
            self.cookies = [Cookie(SESSION_COOKIE)]
        return self.answer

    def request(self, method, url, **kwargs):
        return Answer("", url)

    def close(self):
        pass


def _school(fixture, answer_name, url=PORTAL_URL, signs_in=False):
    return School(Answer(fixture("login_page.html")), Answer(fixture(answer_name), url), signs_in)


def _probe(monkeypatch, school):
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: school)
    return IServProber().verify_login("https://school.example", "parent.one", "secret")


def _login(school):
    client = IServClient("https://school.example", session=school)
    client.login("parent.one", "secret", lambda: "123456")
    return client


@pytest.mark.parametrize(
    "name,kind",
    [
        ("login_refused_password.html", "bad_credentials"),
        ("login_refused_unknown_account.html", UNKNOWN_ACCOUNT),
        ("login_refused_default_password.html", DEFAULT_PASSWORD_BLOCKED),
        ("login_page.html", None),
        ("portal.html", None),
    ],
)
def test_each_official_refusal_text_has_its_own_kind(fixture, name, kind):
    assert login_refusal(fixture(name)) == kind


def test_the_default_password_page_is_never_mistaken_for_a_lock_or_an_expired_password(fixture):
    html = fixture("login_refused_default_password.html")
    assert "gesperrt" in html and "Passwort im Schulnetz" in html
    assert classify_login_response(html) == DEFAULT_PASSWORD_BLOCKED


def test_an_unknown_account_is_classified_before_the_generic_failure(fixture):
    html = fixture("login_refused_unknown_account.html") + "<p>Anmeldung fehlgeschlagen!</p>"
    assert login_refusal(html) == UNKNOWN_ACCOUNT


def test_every_new_kind_has_its_own_actionable_message():
    kinds = ("locked", "captcha", "password_expired", "normal", UNKNOWN_ACCOUNT, DEFAULT_PASSWORD_BLOCKED)
    texts = {kind: human_message(kind) for kind in kinds}
    assert len(set(texts.values())) == len(kinds)
    assert "Schulnetz" in texts[DEFAULT_PASSWORD_BLOCKED]


@pytest.mark.parametrize(
    "name,authenticated,expected",
    [
        ("twofactor_setup_required.html", True, True),
        ("twofactor_setup_required.html", False, True),
        ("twofactor_setup_required_notice.html", False, True),
        ("twofactor_setup_required_notice.html", True, True),
        ("portal_twofactor_grace_notice.html", True, False),
        ("portal_twofactor_grace_notice.html", False, False),
        ("twofactor_page.html", False, False),
        ("portal.html", True, False),
        ("login_page.html", False, False),
    ],
)
def test_the_forced_setup_page_is_told_apart_from_the_code_prompt_and_a_grace_notice(
    fixture, name, authenticated, expected
):
    assert setup_required(fixture(name), SETUP_URL, authenticated) is expected


@pytest.mark.parametrize(
    "name,outcome",
    [
        ("login_refused_password.html", "bad_credentials"),
        ("login_refused_unknown_account.html", UNKNOWN_ACCOUNT),
        ("login_refused_default_password.html", DEFAULT_PASSWORD_BLOCKED),
        ("twofactor_page.html", "twofactor"),
    ],
)
def test_the_wizard_probe_names_each_refusal(monkeypatch, fixture, name, outcome):
    assert _probe(monkeypatch, _school(fixture, name)) == outcome


def test_the_wizard_probe_sees_the_forced_setup_even_when_a_session_was_opened(monkeypatch, fixture):
    school = _school(fixture, "twofactor_setup_required.html", SETUP_URL, signs_in=True)
    assert _probe(monkeypatch, school) == TWOFACTOR_REQUIRED_SETUP


def test_the_wizard_probe_sees_a_forced_setup_notice_without_a_session(monkeypatch, fixture):
    school = _school(fixture, "twofactor_setup_required_notice.html", SETUP_URL)
    assert _probe(monkeypatch, school) == TWOFACTOR_REQUIRED_SETUP


def test_a_grace_period_notice_keeps_a_working_login_working(monkeypatch, fixture):
    school = _school(fixture, "portal_twofactor_grace_notice.html", signs_in=True)
    assert _probe(monkeypatch, school) == "no_2fa"


@pytest.mark.parametrize(
    "name,reason,key",
    [
        ("login_refused_password.html", REASON_BAD_CREDENTIALS, "api.login.credentials"),
        ("login_refused_unknown_account.html", REASON_UNKNOWN_ACCOUNT, "api.login.unknownAccount"),
        ("login_refused_default_password.html", REASON_DEFAULT_PASSWORD, "api.login.defaultPassword"),
        ("login_refused_locked.html", REASON_LOCKED, "api.login.locked"),
    ],
)
def test_a_running_connection_names_each_refusal(fixture, name, reason, key):
    with pytest.raises(LoginError) as caught:
        _login(_school(fixture, name))
    assert caught.value.reason == reason
    assert login_reason(caught.value) == reason
    assert caught.value.message_key == key
    assert caught.value.detail["login_stage"] == "credentials"


def test_a_running_connection_reports_the_forced_setup_as_its_own_login_error(fixture):
    school = _school(fixture, "twofactor_setup_required.html", SETUP_URL, signs_in=True)
    client = IServClient("https://school.example", session=school)
    with pytest.raises(TwoFactorSetupRequired) as caught:
        client.login("parent.one", "secret", lambda: pytest.fail("no code may be asked"))
    assert isinstance(caught.value, LoginError)
    assert caught.value.reason == REASON_TWOFACTOR_SETUP
    assert caught.value.message_key == "api.login.twofactorSetup"
    assert "otpauth://" in client.landing_page.text


def test_a_grace_period_notice_does_not_stop_a_running_connection(fixture):
    client = _login(_school(fixture, "portal_twofactor_grace_notice.html", signs_in=True))
    assert client.is_authenticated()


def test_a_login_error_without_a_named_reason_is_a_credentials_problem():
    assert login_reason(LoginError("x")) == REASON_BAD_CREDENTIALS
    assert login_reason(ValueError("x")) == ""


@pytest.mark.parametrize(
    "name,refusal",
    [
        ("login_refused_unknown_account.html", REASON_UNKNOWN_ACCOUNT),
        ("login_refused_default_password.html", REASON_DEFAULT_PASSWORD),
        ("login_refused_password.html", REASON_BAD_CREDENTIALS),
    ],
)
def test_a_password_check_remembers_why_iserv_refused(monkeypatch, fixture, name, refusal):
    school = _school(fixture, name)
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: school)
    client = IServClient("https://school.example", session=School(None, None))
    client.username = "parent.one"
    assert client.accepts_password("secret") is False
    assert client.refusal == refusal


def test_a_password_check_that_lands_on_the_forced_setup_names_it(monkeypatch, fixture):
    school = _school(fixture, "twofactor_setup_required.html", SETUP_URL, signs_in=True)
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: school)
    client = IServClient("https://school.example", session=School(None, None))
    client.username = "parent.one"
    assert client.accepts_password("secret") is True
    assert client.refusal == REASON_TWOFACTOR_SETUP


def test_a_portal_that_mentions_a_closure_is_not_a_locked_account(fixture):
    page = fixture("portal.html").replace("</body>", "<p>Die Turnhalle ist bis Freitag gesperrt.</p></body>")
    school = School(Answer(fixture("login_page.html")), Answer(page, PORTAL_URL), signs_in=True)
    client = _login(school)
    assert client.is_authenticated()


def test_a_code_prompt_that_mentions_a_lock_is_not_a_locked_account(fixture):
    page = fixture("twofactor_page.html").replace("</body>", "<p>Nach drei falschen Codes wird das Konto gesperrt.</p></body>")
    school = School(Answer(fixture("login_page.html")), Answer(page, PORTAL_URL))
    client = IServClient("https://school.example", session=school)
    with pytest.raises(Exception) as caught:
        client.login("parent.one", "secret", lambda: "123456")
    assert getattr(caught.value, "reason", "") != REASON_LOCKED


BARE_FORBIDDEN = "<html><head><title>Zugriff verweigert</title></head><body></body></html>"
LOCKED_FORBIDDEN = (
    "<html><head><title>Zugriff verweigert</title></head>"
    "<body><p>Zu viele Fehlversuche, Ihr Konto ist vorübergehend gesperrt.</p></body></html>"
)


def _verdict_of_login(school):
    try:
        IServClient("https://school.example", session=school).login("parent.one", "secret", lambda: "123456")
    except Exception as error:
        return getattr(error, "reason", "") or type(error).__name__
    return "signed_in"


def _verdict_of_password_check(school):
    client = IServClient("https://school.example", session=School(None, None))
    client.username = "parent.one"
    accepted = client.accepts_password("secret")
    return client.refusal or str(accepted)


def _verdict_of_wizard_probe(school):
    return IServProber().verify_login("https://school.example", "parent.one", "secret")


def _verdict_of_stored_secret_check(school):
    return IServProber().verify_totp("https://school.example", "parent.one", "secret", "JBSWY3DPEHPK3PXP")


@pytest.mark.parametrize(
    "verdict_of",
    [_verdict_of_login, _verdict_of_password_check, _verdict_of_wizard_probe, _verdict_of_stored_secret_check],
)
@pytest.mark.parametrize(
    "page,locked", [(BARE_FORBIDDEN, False), (LOCKED_FORBIDDEN, True)], ids=["bare", "lock_wording"]
)
def test_every_sign_in_path_reaches_the_same_lock_verdict(monkeypatch, fixture, verdict_of, page, locked):
    school = School(Answer(fixture("login_page.html")), Answer(page, status_code=403))
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: school)
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: school)
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=None: IServClient(url, session=school))
    verdict = verdict_of(school)
    assert (verdict == REASON_LOCKED) is locked, verdict
