import logging

import pytest
import requests

from app.iserv.client import SESSION_COOKIE, SETUP_OK, SETUP_REJECTED, SETUP_UNCERTAIN, IServClient, SetupOutcome
from app.iserv.errors import TwoFactorError, TwoFactorSetupRequired
from app.iserv.twofactor import (
    SETUP_STEP_ACTIVATE,
    SETUP_STEP_NAME,
    build_setup_payload,
    parse_setup_page,
    setup_shape,
)
from app.iserv_prober import IServProber, setup_uri
from tests.conftest import load_fixture

BASE = "https://school.example"
SETUP_URL = BASE + "/iserv/auth/twofactor/setup"
ADD_URL = BASE + "/iserv/auth/settings/twofactor/add"
LIST_URL = BASE + "/iserv/auth/settings/twofactor/"
CONFIRM_URL = BASE + "/iserv/auth/settings/twofactor/add/confirm"
FIRST_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
PASSWORD = "pass-word-77"
CODE = "246813"


class Answer:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": "text/html; charset=utf-8"}


class Cookie:
    def __init__(self, name):
        self.name = name


class School:
    def __init__(self, landing="twofactor_setup_first.html", landing_url=SETUP_URL, pages=None, answer=None,
                 lists=("twofactor_list_none.html", "twofactor_list_setup_done.html"), post_error=None):
        self.headers = {}
        self.cookies = [Cookie(SESSION_COOKIE)]
        self.landing = landing
        self.landing_url = landing_url
        self.pages = dict(pages or {})
        self.answer = answer
        self.lists = list(lists)
        self.post_error = post_error
        self.gets = []
        self.posts = []
        self.events = []

    def get(self, url, timeout=None, params=None, **kwargs):
        self.gets.append(url)
        self.events.append(("GET", url))
        if url == BASE + "/iserv/":
            return Answer(load_fixture("login_page.html"), BASE + "/iserv/auth/login")
        if url == LIST_URL:
            name = self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
            if name is None:
                raise requests.ConnectionError("list unreachable")
            return Answer(load_fixture(name), url)
        if url in self.pages:
            return Answer(load_fixture(self.pages[url]), url)
        return Answer("<html><body>missing</body></html>", url, 404)

    def post(self, url, data=None, timeout=None, **kwargs):
        self.posts.append((url, dict(data or {})))
        self.events.append(("POST", url))
        if "/auth/login" in url:
            return Answer(load_fixture(self.landing), self.landing_url)
        if self.post_error is not None:
            raise self.post_error
        name, status = self.answer if isinstance(self.answer, tuple) else (self.answer, 200)
        if isinstance(name, dict):
            name = name.get(url, "")
        return Answer(load_fixture(name) if name else "", url, status)


def signed_in(school):
    client = IServClient(BASE, session=school)
    with pytest.raises(TwoFactorSetupRequired):
        client.login("parent.one", PASSWORD, lambda: pytest.fail("no code may be asked"))
    return client


def test_the_forced_setup_page_yields_the_secret_the_link_and_the_form(fixture):
    setup = parse_setup_page(fixture("twofactor_setup_first.html"), SETUP_URL)
    assert setup.step == SETUP_STEP_ACTIVATE
    assert setup.secret == FIRST_SECRET
    assert setup.uri.startswith("otpauth://totp/IServ:parent.one?secret=" + FIRST_SECRET)
    assert "&amp;" not in setup.uri
    assert setup.action == CONFIRM_URL


def test_the_older_setup_fixture_and_the_add_page_are_read_the_same_way(fixture):
    for name, url in (("twofactor_setup_required.html", SETUP_URL), ("security_2fa_add.html", ADD_URL)):
        setup = parse_setup_page(fixture(name), url)
        assert setup is not None and setup.step == SETUP_STEP_ACTIVATE, name
        assert setup.secret


def test_a_key_shown_only_as_text_is_still_found():
    page = (
        '<p class="manual">Schlüssel: <code>GEZD GNBV GY3T QOJQ</code></p>'
        '<form hx-post="/iserv/auth/settings/twofactor/add/confirm"><input name="confirm[code]"></form>'
    )
    setup = parse_setup_page(page, ADD_URL)
    assert setup.secret == "GEZDGNBVGY3TQOJQ"
    assert setup.uri == ""


def test_pages_without_a_setup_form_are_not_taken_for_one(fixture):
    for name in ("login_page.html", "twofactor_page.html", "portal.html", "twofactor_setup_required_notice.html"):
        assert parse_setup_page(fixture(name), SETUP_URL) is None, name


def test_the_name_step_is_recognised_without_a_key(fixture):
    setup = parse_setup_page(fixture("twofactor_setup_name.html"), ADD_URL)
    assert setup.step == SETUP_STEP_NAME
    assert setup.secret == ""


def test_the_payload_fills_the_form_iserv_sent(fixture):
    setup = parse_setup_page(fixture("twofactor_setup_first.html"), SETUP_URL)
    payload = build_setup_payload(setup, "Authenticator", CODE, PASSWORD)
    assert payload == {
        "confirm[name]": "Authenticator",
        "confirm[verification]": PASSWORD,
        "confirm[_fake_username]": "",
        "confirm[code]": CODE,
        "confirm[actions][submit]": "",
        "confirm[_token]": "csrf-first-setup",
    }


def test_the_name_step_payload_chooses_save_and_never_cancel(fixture):
    setup = parse_setup_page(fixture("twofactor_setup_name.html"), ADD_URL)
    payload = build_setup_payload(setup, "Authenticator", "", PASSWORD)
    assert payload["twofactor_add[name]"] == "Authenticator"
    assert "twofactor_add[actions][save]" in payload
    assert "twofactor_add[actions][cancel]" not in payload
    assert payload["twofactor_add[_token]"] == "csrf-name-step"


def test_the_shape_names_fields_but_never_values(fixture):
    page = Answer(fixture("twofactor_setup_first.html"), SETUP_URL)
    shape = setup_shape(page, parse_setup_page(page.text, page.url))
    text = repr(shape)
    assert FIRST_SECRET not in text and "GEZD" not in text
    assert "csrf-first-setup" not in text
    assert "confirm[verification]:password" in shape["forms"][0]["fields"]
    assert shape["secret_found"] is True and shape["otpauth_link"] is True
    assert shape["step"] == SETUP_STEP_ACTIVATE


def test_the_client_reads_the_setup_from_the_landing_page():
    school = School()
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    assert setup.secret == FIRST_SECRET
    assert school.gets == [BASE + "/iserv/", LIST_URL]


def test_the_client_follows_the_setup_link_of_a_notice_page():
    school = School(landing="twofactor_setup_required_notice.html", pages={ADD_URL: "twofactor_setup_first.html"})
    client = signed_in(school)
    assert client.open_twofactor_setup("Authenticator", PASSWORD).secret == FIRST_SECRET
    assert school.gets[-1] == ADD_URL
    assert len(school.posts) == 1


def test_the_client_walks_through_the_name_step_once():
    school = School(
        landing="twofactor_setup_required_notice.html",
        pages={ADD_URL: "twofactor_setup_name.html"},
        answer="twofactor_setup_first.html",
    )
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    assert setup.secret == FIRST_SECRET
    url, data = school.posts[-1]
    assert url == ADD_URL
    assert data["twofactor_add[name]"] == "Authenticator"
    assert len(school.posts) == 2


def test_no_setup_form_is_an_error_with_a_shape_and_without_secrets():
    school = School(landing="twofactor_setup_required_notice.html", pages={ADD_URL: "portal.html"})
    client = signed_in(school)
    with pytest.raises(TwoFactorError) as caught:
        client.open_twofactor_setup("Authenticator", PASSWORD)
    assert caught.value.message_key == "api.wizard.setup.noForm"
    assert caught.value.detail["setup"]["step"] == "none"
    assert PASSWORD not in repr(caught.value.detail)


def test_a_setup_form_that_posts_to_another_host_is_never_used():
    school = School(landing="twofactor_setup_required_notice.html", pages={ADD_URL: "twofactor_setup_first.html"})
    client = signed_in(school)
    foreign = load_fixture("twofactor_setup_first.html").replace(
        'hx-post="/iserv/auth/settings/twofactor/add/confirm"', 'hx-post="https://elsewhere.example/collect"'
    )
    school.get = lambda url, **kwargs: Answer(foreign, url)
    with pytest.raises(TwoFactorError) as caught:
        client.open_twofactor_setup("Authenticator", PASSWORD)
    assert caught.value.message_key == "api.wizard.setup.noForm"
    assert len(school.posts) == 1


def test_a_new_token_in_the_list_is_success():
    school = School(answer="twofactor_setup_first_rejected.html")
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    outcome = client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD)
    assert outcome.status == SETUP_OK
    url, data = school.posts[-1]
    assert url == CONFIRM_URL
    assert data["confirm[code]"] == CODE
    assert data["confirm[verification]"] == PASSWORD


def test_a_wrong_code_is_rejected_and_keeps_the_fresh_form():
    school = School(answer="twofactor_setup_first_rejected.html", lists=("twofactor_list_none.html",))
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    outcome = client.confirm_twofactor_setup(setup, "Authenticator", "000000", PASSWORD)
    assert outcome.status == SETUP_REJECTED
    assert outcome.setup.secret == FIRST_SECRET
    assert outcome.setup.fields["confirm[_token]"] == "csrf-first-setup-again"
    assert len([post for post in school.posts if post[0] == CONFIRM_URL]) == 1


def test_an_unclear_answer_is_uncertain_and_never_sent_twice():
    for answer, lists in (
        ("portal.html", ("twofactor_list_none.html",)),
        ("twofactor_setup_first_rejected.html", ("twofactor_list_none.html", None)),
        (("twofactor_setup_first.html", 502), ("twofactor_list_none.html",)),
    ):
        school = School(answer=answer, lists=lists)
        client = signed_in(school)
        setup = client.open_twofactor_setup("Authenticator", PASSWORD)
        outcome = client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD)
        assert outcome.status == SETUP_UNCERTAIN, answer
        assert len([post for post in school.posts if post[0] == CONFIRM_URL]) == 1


def test_a_request_lost_on_the_way_is_uncertain_and_not_repeated():
    school = School(post_error=requests.ConnectionError("reset"))
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    school.post_error = requests.ConnectionError("reset")
    assert client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD).status == SETUP_UNCERTAIN
    assert len([post for post in school.posts if post[0] == CONFIRM_URL]) == 1


def test_the_key_password_and_code_never_reach_the_log(caplog):
    caplog.set_level(logging.DEBUG)
    school = School(
        landing="twofactor_setup_required_notice.html",
        pages={ADD_URL: "twofactor_setup_name.html"},
        answer={ADD_URL: "twofactor_setup_first.html", CONFIRM_URL: "twofactor_setup_first_rejected.html"},
        lists=("twofactor_list_none.html",),
    )
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "two-factor setup page" in logged and "two-factor setup answer" in logged
    assert "confirm[code]:code" in logged
    for value in (FIRST_SECRET, "GEZD GNBV", PASSWORD, CODE, "csrf-first-setup", "csrf-name-step"):
        assert value not in logged


class ProberClient:
    script = {}

    def __init__(self, url, timeout=15):
        self.url = url
        self.login_result = self.script.get("login")
        self.setup = parse_setup_page(load_fixture("twofactor_setup_first.html"), SETUP_URL)
        self.outcomes = list(self.script.get("outcomes", []))
        self.confirmed = []

    def login(self, username, password, code_provider):
        result = self.login_result
        if result == "code":
            code_provider()
        if isinstance(result, Exception):
            raise result
        return self

    def open_twofactor_setup(self, name, password):
        return self.setup

    def confirm_twofactor_setup(self, setup, name, code, password):
        self.confirmed.append(code)
        return self.outcomes.pop(0)


def prober_with(monkeypatch, **script):
    script.setdefault("login", TwoFactorSetupRequired("setup"))
    ProberClient.script = script
    monkeypatch.setattr("app.iserv_prober.IServClient", ProberClient)
    return IServProber()


def test_the_prober_names_why_no_setup_is_needed(monkeypatch):
    assert prober_with(monkeypatch, login=None).begin_setup(BASE, "u", "p") == {"status": "no_2fa"}
    assert prober_with(monkeypatch, login="code").begin_setup(BASE, "u", "p") == {"status": "twofactor"}


def test_the_prober_keeps_the_key_in_memory_until_the_setup_ends(monkeypatch):
    prober = prober_with(monkeypatch, outcomes=[SetupOutcome(SETUP_OK, None)])
    assert prober.begin_setup(BASE, "u", "p") == {"status": "awaiting_setup_code"}
    key = prober.setup_key(BASE, "u")
    assert key["secret"] == FIRST_SECRET
    assert key["uri"].startswith("otpauth://")
    assert prober.setup_key(BASE, "someone.else") is None
    assert prober.confirm_setup(BASE, "u", "p", CODE) == {"status": "ok"}
    assert prober.setup_key(BASE, "u") is None
    assert prober.confirm_setup(BASE, "u", "p", CODE) == {"status": "expired"}


def test_the_prober_keeps_a_rejected_setup_open_and_names_a_new_key(monkeypatch):
    fresh = parse_setup_page(load_fixture("twofactor_setup_first.html"), SETUP_URL)
    other = parse_setup_page(load_fixture("security_2fa_add.html"), ADD_URL)
    prober = prober_with(monkeypatch, outcomes=[SetupOutcome(SETUP_REJECTED, fresh), SetupOutcome(SETUP_REJECTED, other)])
    prober.begin_setup(BASE, "u", "p")
    assert prober.confirm_setup(BASE, "u", "p", "000000") == {"status": "rejected", "key_changed": False}
    assert prober.confirm_setup(BASE, "u", "p", "000000") == {"status": "rejected", "key_changed": True}
    assert prober.setup_key(BASE, "u")["secret"] == other.secret


def test_an_uncertain_setup_drops_the_key(monkeypatch):
    prober = prober_with(monkeypatch, outcomes=[SetupOutcome(SETUP_UNCERTAIN, None)])
    prober.begin_setup(BASE, "u", "p")
    assert prober.confirm_setup(BASE, "u", "p", CODE) == {"status": "uncertain"}
    assert prober.setup_key(BASE, "u") is None


def test_a_link_is_built_when_iserv_shows_only_the_key():
    uri = setup_uri("GEZDGNBVGY3TQOJQ", "", "parent one")
    assert uri == "otpauth://totp/IServ:parent%20one?secret=GEZDGNBVGY3TQOJQ&issuer=IServ"


def test_only_setup_links_on_the_school_host_below_iserv_are_followed():
    page = Answer(
        '<a href="/iserv/auth/twofactor/setup">a</a>'
        '<a href="/twofactor/setup">b</a>'
        '<a href="/portal/twofactor/start">c</a>'
        '<a href="https://elsewhere.example/iserv/twofactor/add">d</a>'
        '<a href="http://school.example/iserv/auth/twofactor/other">e</a>',
        BASE + "/iserv/",
    )
    client = IServClient(BASE, session=School())
    assert client._setup_targets(page) == [SETUP_URL, ADD_URL]


def test_a_code_form_outside_the_two_factor_pages_is_not_a_setup(fixture):
    page = fixture("twofactor_setup_first.html").replace(
        'hx-post="/iserv/auth/settings/twofactor/add/confirm"', 'hx-post="/iserv/profile/save"'
    )
    assert parse_setup_page(page, SETUP_URL) is None


def test_the_shape_reports_form_actions_as_link_shapes(fixture):
    action = "/iserv/auth/settings/twofactor/add/confirm/b2b6b8b0-1111-4a2a-9c3c-abcdef123456"
    page = Answer(fixture("twofactor_setup_first.html").replace("/iserv/auth/settings/twofactor/add/confirm", action), SETUP_URL)
    shape = setup_shape(page)
    assert "b2b6b8b0" not in repr(shape)
    assert shape["forms"][0]["action"] == "/iserv/auth/settings/<seg>/add/confirm/<uuid>"


def test_an_unreadable_list_before_the_setup_never_counts_as_success():
    school = School(answer="portal.html", lists=(None, "twofactor_list_setup_done.html"))
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    assert client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD).status == SETUP_UNCERTAIN


class SetupEverywhere(School):
    def get(self, url, timeout=None, params=None, **kwargs):
        if url == LIST_URL:
            self.gets.append(url)
            self.events.append(("GET", url))
            return Answer(load_fixture("twofactor_setup_first.html").replace("csrf-first-setup", "csrf-from-list"), SETUP_URL)
        return super().get(url, timeout=timeout, params=params, **kwargs)


def test_nothing_is_read_between_showing_the_key_and_posting_the_code():
    school = SetupEverywhere(answer="twofactor_setup_first_rejected.html")
    client = signed_in(school)
    setup = client.open_twofactor_setup("Authenticator", PASSWORD)
    assert setup.fields["confirm[_token]"] == "csrf-from-list"
    shown = len(school.events)
    outcome = client.confirm_twofactor_setup(setup, "Authenticator", CODE, PASSWORD)
    assert school.events[shown] == ("POST", CONFIRM_URL)
    assert outcome.status == SETUP_UNCERTAIN
