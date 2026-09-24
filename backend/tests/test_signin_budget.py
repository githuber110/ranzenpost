import pytest
from fastapi.testclient import TestClient

from app import integration, lockout, messages
from app.iserv import errors
from app.iserv.client import REFUSAL_KEYS, IServClient
from app.iserv.errors import LoginError, OutageError, REASON_DEFAULT_PASSWORD
from app.iserv_prober import IServProber
from app.lockout import classify_login_response, login_refusal
from app.poller import AUTH_NOTIFY_KEYS, Poller
from app.server import create_app
from app.service import IServService, REPAIR_REFUSAL_KEYS
from app.store import Store
from app.subscriptions import COMPONENT_ABSENCES, COMPONENT_TIMETABLE, SubscriptionRegistry
from app.wizard import Wizard

from tests.support import add_school, connection_service
from tests.test_login_reasons_running import NO_2FA, SCHOOL_ONE, Client, Clock, forced, poll, school
from tests.test_login_refusals import Answer, School, _school
from tests.test_poller_modules import CHILD_ID, NOW_EPOCH, ModularService, _store
from tests.test_wizard import FakeProber, make

LOCK_PAGE = (
    "<html><body><div class='alert'>Anmeldung fehlgeschlagen! Zu viele Fehlversuche, "
    "Ihr Konto ist vorübergehend gesperrt.</div></body></html>"
)
MINUTE = 60
HOUR = 60 * MINUTE


def rate_limited(seconds=3600):
    return OutageError("rate_limited", retry_after=seconds)


class RateLimitedSchool:
    def __init__(self, fixture):
        self.page = fixture("login_page.html")
        self.headers = {}
        self.cookies = []
        self.posts = 0

    def get(self, url, **kwargs):
        return Answer(self.page, url="https://school.example/iserv/")

    def post(self, url, data=None, **kwargs):
        self.posts += 1
        answer = Answer("Too Many Requests", status_code=429)
        answer.headers = {"Retry-After": "600"}
        return answer

    def request(self, method, url, **kwargs):
        return self.post(url) if method.upper() == "POST" else self.get(url)

    def close(self):
        pass


def test_a_stale_health_check_waits_out_the_school_retry_after(tmp_path):
    service, store, connection_id, log = school(tmp_path, lambda: rate_limited())
    poll(service, [])
    slot = integration.school_state(store, connection_id)
    connection = service.connection(connection_id)
    for _ in range(5):
        health = connection.health_status(clock=lambda: slot["last_poll"] + 10 * MINUTE)
    assert len(log) == 1
    assert health == {"status": "outage", "stale": False}


def test_a_read_during_the_backoff_answers_outage_without_a_login(tmp_path):
    service, store, connection_id, log = school(tmp_path, lambda: rate_limited())
    poll(service, [])
    app = TestClient(create_app(service))
    for _ in range(3):
        body = app.get("/api/children", params={"connection": connection_id}).json()
    assert len(log) == 1
    assert body["error"] == "network"
    assert body["message_key"] == "api.outage"


def test_the_live_status_of_the_connection_list_waits_out_the_backoff(tmp_path):
    service, store, connection_id, log = school(tmp_path, lambda: rate_limited())
    poll(service, [])
    for _ in range(3):
        rows = service.summaries(with_status=True)
    assert len(log) == 1
    assert rows[0]["status"] == "outage"


def test_a_manual_retry_honours_the_school_rate_limit(tmp_path):
    service, store, connection_id, log = school(tmp_path, lambda: rate_limited())
    poll(service, [])
    Poller(service).poll_once(connection_id=connection_id)
    assert len(log) == 1


def test_a_manual_retry_still_lifts_a_plain_outage_backoff(tmp_path):
    service, store, connection_id, log = school(tmp_path, lambda: OutageError("status:503"))
    poll(service, [])
    poll(service, [])
    assert integration.outage_backoff_active(store, connection_id, integration.school_state(store, connection_id)["last_poll"])
    Poller(service).poll_once(connection_id=connection_id)
    assert len(log) == 3


def test_the_code_step_under_429_is_an_outage_with_the_school_wait(monkeypatch, fixture):
    school_server = RateLimitedSchool(fixture)
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: school_server)
    result = IServProber().begin_2fa("https://school.example", "u", "p", "123456")
    assert result == {"status": "rate_limited", "retry_after": 600}


def test_a_429_on_the_login_post_is_rate_limiting_not_a_lock(monkeypatch, fixture):
    school_server = RateLimitedSchool(fixture)
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: school_server)
    prober = IServProber()
    assert prober.verify_login("https://school.example", "u", "p") == "rate_limited"
    assert prober.retry_after == 600


def test_the_wizard_code_step_pauses_for_the_school_wait_under_429(tmp_path):
    wizard, _, prober, clock = make(tmp_path, begin={"status": "rate_limited", "retry_after": 600})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(20):
        state = wizard.connect("123456")
    assert prober.begin_calls == 1
    assert state["retry_in"] == 600
    assert state["error"]["message_key"] == "api.wizard.pausedRateLimited"
    clock.value += 601
    wizard.connect("123456")
    assert prober.begin_calls == 2


def test_the_wizard_login_step_pauses_for_the_school_wait_under_429(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="rate_limited")
    prober.retry_after = 120
    wizard.set_url("myschool.example")
    for _ in range(5):
        state = wizard.set_login("p", "s")
    assert prober.login_calls == 1
    assert state["retry_in"] == 120
    assert state["error"]["message_key"] == "api.wizard.pausedRateLimited"


def test_a_rate_limit_without_a_wait_still_pauses_the_wizard(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="rate_limited")
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.set_login("p", "s")
    assert prober.login_calls == 1
    assert state["retry_in"] == 300


def test_a_captcha_pauses_the_wizard_like_a_lock_and_keeps_its_explanation(tmp_path):
    wizard, _, prober, clock = make(tmp_path, login="captcha")
    wizard.set_url("myschool.example")
    first = wizard.set_login("p", "x")
    assert first["error"]["code"] == "captcha"
    assert first["error"]["message_key"] == "api.lockout.captcha"
    assert first["retry_in"] == 300
    for _ in range(3):
        state = wizard.set_login("p", "x")
    assert prober.login_calls == 1
    assert state["error"]["message_key"] == "api.lockout.captcha"
    clock.value += 301
    wizard.set_login("p", "x")
    assert prober.login_calls == 2


def test_a_lock_page_that_also_says_failed_reads_as_a_lock():
    assert login_refusal(LOCK_PAGE) is None
    assert classify_login_response(LOCK_PAGE) == "locked"


def test_the_wizard_probe_reads_a_lock_page_with_the_failed_wording_as_a_lock(monkeypatch, fixture):
    server = School(Answer(fixture("login_page.html")), Answer(LOCK_PAGE))
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: server)
    assert IServProber().verify_login("https://school.example", "u", "p") == "locked"


def test_the_wizard_probe_reads_a_bare_forbidden_page_as_unknown_and_not_as_a_lock(monkeypatch, fixture):
    refused = "<html><head><title>Zugriff verweigert</title></head><body></body></html>"
    server = School(Answer(fixture("login_page.html")), Answer(refused, status_code=403))
    monkeypatch.setattr("app.iserv_prober.requests.Session", lambda: server)
    assert IServProber().verify_login("https://school.example", "u", "p") == "unknown"


def test_the_default_password_page_stays_first_although_it_says_gesperrt(fixture):
    page = fixture("login_refused_default_password.html")
    assert "gesperrt" in page.lower()
    assert login_refusal(page) == lockout.DEFAULT_PASSWORD_BLOCKED
    assert classify_login_response(page) == lockout.DEFAULT_PASSWORD_BLOCKED


def test_a_code_prompt_that_says_um_fortzufahren_is_a_normal_code_prompt(monkeypatch, fixture):
    page = fixture("twofactor_page.html").replace(
        "<body>", "<body><p>Bitte geben Sie den Code der Zwei-Faktor-Authentifizierung ein, um fortzufahren.</p>"
    )
    server = School(Answer(fixture("login_page.html")), Answer(page, url="https://school.example/iserv/auth/twofactor"))
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: server)
    client = IServClient("https://school.example", session=School(None, None))
    client.username = "parent.one"
    assert client.accepts_password("right") is True
    assert client.refusal == ""


class FlakyModules(ModularService):
    def __init__(self, store):
        super().__init__(store, {})
        self.letter_ids = ["a"]
        self.pin_fail = False
        self.week_fail = False

    def letters(self, tab="current"):
        self.calls.append("letters")
        return {"letters": [{"letter_id": i, "recipient_id": "r", "title": "T", "unread": True} for i in self.letter_ids]}

    def pinboard(self):
        if self.pin_fail:
            raise rate_limited(600)
        return super().pinboard()

    def timetable(self, child_id, week_offset=0):
        if self.week_fail and week_offset:
            raise rate_limited(600)
        return super().timetable(child_id, week_offset)


def _module_poller(tmp_path):
    store = _store(tmp_path)
    service = FlakyModules(store)
    sent = []
    clock = {"now": NOW_EPOCH}
    subscriptions = SubscriptionRegistry(store)
    subscriptions.create(CHILD_ID, [COMPONENT_TIMETABLE, COMPONENT_ABSENCES], "", "")
    poller = Poller(
        service,
        store=store,
        registry=subscriptions,
        clock=lambda: clock["now"],
        notifiers={"letters": lambda name, text: sent.append(text) or True},
    )
    return store, service, poller, clock, sent


def test_a_429_in_the_middle_of_a_poll_never_repeats_a_push(tmp_path):
    store, service, poller, clock, sent = _module_poller(tmp_path)
    poller.poll_once()
    service.letter_ids = ["a", "b"]
    service.pin_fail = True
    poller.poll_once()
    assert len(sent) == 1
    clock["now"] += 700
    poller.poll_once()
    assert len(sent) == 1


def test_a_429_on_a_later_timetable_week_ends_the_poll_as_an_outage(tmp_path):
    store, service, poller, clock, sent = _module_poller(tmp_path)
    service.week_fail = True
    poller.poll_once()
    slot = integration.school_state(store, service.id)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_REASON] == "rate_limited"


def _refused():
    return LoginError("refused", message_key="api.login.defaultPassword", reason=REASON_DEFAULT_PASSWORD)


def test_a_refused_password_is_not_tried_again_by_polls_or_health_checks(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    sent = []
    for _ in range(3):
        poll(service, sent)
    connection = service.connection(connection_id)
    last = integration.school_state(store, connection_id)["last_poll"]
    for _ in range(5):
        health = connection.health_status(clock=lambda: last + 10 * MINUTE)
    assert len(log) == 1
    assert len(sent) == 1
    assert health == {"status": "auth_failed", "stale": False, "reason": REASON_DEFAULT_PASSWORD}


def test_a_read_during_the_refusal_wait_names_the_reason_without_a_login(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    poll(service, [])
    body = TestClient(create_app(service)).get("/api/children", params={"connection": connection_id}).json()
    assert len(log) == 1
    assert body["error"] == "auth_failed"
    assert body["message_key"] == "api.login.defaultPassword"


def test_the_refusal_wait_grows_from_half_an_hour_to_twelve_hours(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    expected = 30 * MINUTE
    logins = 1
    while expected <= 12 * HOUR:
        clock.value += expected - 1
        poll(service, [])
        assert len(log) == logins
        clock.value += 2
        poll(service, [])
        logins += 1
        assert len(log) == logins
        if expected == 12 * HOUR:
            break
        expected = min(expected * 2, 12 * HOUR)


def test_a_new_password_ends_the_refusal_wait_at_once(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    poll(service, [])
    secrets = store.load_secrets(connection_id)
    secrets["password"] = "changed"
    store.save_secrets(connection_id, secrets)
    poll(service, [])
    assert len(log) == 2


def test_the_refusal_wait_survives_a_restart_and_keeps_no_password(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    poll(service, [])
    restarted = IServService(store, client_factory=lambda url: Client(url, fail=_refused, log=log))
    poll(restarted, [])
    assert len(log) == 1
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"secret" not in path.read_bytes()


def test_the_forced_setup_wait_survives_a_restart(tmp_path):
    service, store, connection_id, log = school(tmp_path, forced)
    poll(service, [])
    restarted = IServService(store, client_factory=lambda url: Client(url, fail=forced, log=log))
    poll(restarted, [])
    assert len(log) == 1


def test_a_finished_wizard_with_the_same_password_ends_the_refusal_wait(tmp_path):
    service, store, connection_id, log = school(tmp_path, _refused)
    poll(service, [])
    wizard = Wizard(store, FakeProber(login="no_2fa"))
    wizard.reset(connection_id)
    wizard.set_url(SCHOOL_ONE)
    wizard.set_login(NO_2FA["username"], NO_2FA["password"])
    wizard.skip_child()
    poll(service, [])
    assert len(log) == 2


class RefusingClient(Client):
    checks = 0

    def accepts_password(self, password):
        RefusingClient.checks += 1
        return False


def test_repairing_the_password_pauses_after_three_refusals(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    RefusingClient.checks = 0
    service = connection_service(store, connection_id, lambda url: RefusingClient(url))
    clock = Clock()
    service.clock = clock
    results = [service.repair_password("wrong") for _ in range(6)]
    assert RefusingClient.checks == 3
    assert results[2]["message_key"] == "api.wizard.pausedCredentials"
    assert results[5]["ok"] is False
    assert results[5]["retry_in"] == 30
    clock.value += 31
    service.repair_password("wrong")
    assert RefusingClient.checks == 4


def test_repairing_the_password_waits_out_the_school_rate_limit(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    RefusingClient.checks = 0
    service = connection_service(store, connection_id, lambda url: RefusingClient(url))
    clock = Clock(NOW_EPOCH)
    service.clock = clock
    integration.note_outage(store, connection_id, NOW_EPOCH, "rate_limited", 1800, retry_after=600)
    result = service.repair_password("new")
    assert RefusingClient.checks == 0
    assert result["message_key"] == "api.wizard.pausedRateLimited"
    assert result["retry_in"] == 600


def test_the_wizard_pause_is_checked_before_a_stored_code_secret_is_tried(tmp_path):
    wizard, store, prober, _ = make(tmp_path, login="twofactor", begin={"status": "bad_code"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(3):
        wizard.connect("123456")
    state = wizard.status()
    assert state["retry_in"] > 0
    secrets = store.load_secrets()
    secrets["totp_secret"] = "JBSWY3DPEHPK3PXP"
    store.base.save_secrets(state["connection_id"], secrets)
    wizard.connect("123456")
    assert prober.verify_calls == 0


@pytest.mark.parametrize(
    "name,status",
    [
        ("login_refused_unknown_account.html", "unknown_account"),
        ("login_refused_default_password.html", "default_password_blocked"),
        ("login_refused_password.html", "bad_credentials"),
    ],
)
def test_the_code_step_names_each_refusal(monkeypatch, fixture, name, status):
    monkeypatch.setattr("app.iserv.client.requests.Session", lambda: _school(fixture, name))
    assert IServProber().begin_2fa("https://school.example", "u", "p", "123456") == {"status": status}


def test_the_wizard_names_a_default_password_in_the_code_step_without_counting_it(tmp_path):
    wizard, _, prober, _ = make(tmp_path, begin={"status": "default_password_blocked"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect("123456")
    assert state["error"]["message_key"] == "api.lockout.defaultPassword"
    assert state["attempts"] == 0


def test_the_wizard_names_an_unknown_account_in_the_code_step(tmp_path):
    wizard, _, prober, _ = make(tmp_path, begin={"status": "unknown_account"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect("123456")
    assert state["error"]["message_key"] == "api.lockout.unknownAccount"
    assert state["attempts"] == 1


def test_the_refusal_names_are_bound_between_the_page_reader_and_the_sign_in_errors():
    assert lockout.BAD_CREDENTIALS == errors.REASON_BAD_CREDENTIALS
    assert lockout.UNKNOWN_ACCOUNT == errors.REASON_UNKNOWN_ACCOUNT
    assert lockout.DEFAULT_PASSWORD_BLOCKED == errors.REASON_DEFAULT_PASSWORD
    assert lockout.TWOFACTOR_REQUIRED_SETUP == errors.REASON_TWOFACTOR_SETUP
    assert lockout.LOCKED == errors.REASON_LOCKED
    refusals = {lockout.BAD_CREDENTIALS, lockout.UNKNOWN_ACCOUNT, lockout.DEFAULT_PASSWORD_BLOCKED, lockout.LOCKED}
    assert refusals == set(REFUSAL_KEYS)
    assert set(errors.LOGIN_REASONS) == set(AUTH_NOTIFY_KEYS)
    assert set(errors.LOGIN_REASONS) <= set(REPAIR_REFUSAL_KEYS)
    for key in list(REFUSAL_KEYS.values()) + list(REPAIR_REFUSAL_KEYS.values()) + list(AUTH_NOTIFY_KEYS.values()):
        assert messages.BASE_MESSAGES.get(key)
