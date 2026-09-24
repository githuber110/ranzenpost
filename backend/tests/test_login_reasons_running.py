import pytest
from fastapi.testclient import TestClient

from app import integration, messages, modules
from app.iserv.errors import DataError, LoginError, TwoFactorError, TwoFactorSetupRequired
from app.poller import Poller
from app.server import create_app
from app.service import IServService
from app.sign_in import (
    CODE_STEP_FAILED,
    REFUSAL_WAIT_FIRST_SECONDS,
    SESSION_HOLD_FIRST_SECONDS,
    SESSION_NOT_OPENED,
    SETUP_RETRY_SECONDS,
)
from app.store import Store
from tests.support import add_school, connection_service

SCHOOL_ONE = "https://school-one.example"
NO_2FA = {"username": "parent.one", "password": "secret"}
FORCED = "twofactor_required_setup"


def forced():
    return TwoFactorSetupRequired("setup", message_key="api.login.twofactorSetup")


class Client:
    def __init__(self, url, fail=None, log=None, refusal="", accepts=True, answered=True):
        self.url = url
        self.fail = fail
        self.log = log if log is not None else []
        self.authed = False
        self.username = ""
        self.refusal = refusal
        self.accepts = accepts
        self.answered = answered

    def login(self, username, password, code_provider):
        self.log.append(username)
        failure = self.fail() if callable(self.fail) else self.fail
        if failure is not None:
            raise failure
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        return []

    def accepts_password(self, password):
        return self.accepts


class Clock:
    def __init__(self, value=1_000_000.0):
        self.value = value

    def __call__(self):
        return self.value


def school(tmp_path, fail, secrets=None):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(secrets or NO_2FA), school_name="School One")
    log = []
    service = IServService(store, client_factory=lambda url: Client(url, fail=fail, log=log))
    return service, store, connection_id, log


def poll(service, sent):
    return Poller(service, notifiers={"auth": lambda name, message: sent.append(message) or True}).poll_once()


def test_a_forced_setup_is_its_own_state_with_its_own_message(tmp_path):
    service, store, connection_id, _ = school(tmp_path, forced)
    sent = []
    events = poll(service, sent)
    assert {"connection_id": connection_id, "error": FORCED} in events
    slot = integration.school_state(store, connection_id)
    assert slot["last_error"] == integration.ERROR_AUTH
    assert slot["auth_reason"] == FORCED
    assert sent == [messages.text("api.login.twofactorSetup")]
    [listed] = integration.build_schools(service, store)
    assert listed["status"] == integration.STATUS_AUTH_FAILED
    assert listed["status_reason"] == FORCED


def test_a_forced_setup_is_never_retried_while_nothing_changed(tmp_path):
    service, store, connection_id, log = school(tmp_path, forced)
    sent = []
    for _ in range(4):
        poll(service, sent)
    assert len(log) == 1
    assert len(sent) == 1
    assert integration.school_state(store, connection_id)["auth_reason"] == FORCED


def test_a_forced_setup_is_retried_once_the_setup_stored_a_secret(tmp_path):
    service, store, connection_id, log = school(tmp_path, forced)
    poll(service, [])
    store.save_secrets(connection_id, dict(NO_2FA, totp_secret="JBSWY3DPEHPK3PXP"))
    poll(service, [])
    assert len(log) == 2


def test_a_forced_setup_is_looked_at_again_after_the_long_wait(tmp_path):
    service, store, connection_id, log = school(tmp_path, forced)
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    clock.value += SETUP_RETRY_SECONDS - 1
    poll(service, [])
    assert len(log) == 1
    clock.value += 2
    poll(service, [])
    assert len(log) == 2


def test_a_recovered_school_drops_the_reason(tmp_path):
    failures = [forced()]
    service, store, connection_id, _ = school(tmp_path, lambda: failures.pop() if failures else None)
    silent = {"modules": {name: False for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(silent)
    poll(service, [])
    store.save_secrets(connection_id, dict(NO_2FA, totp_secret="JBSWY3DPEHPK3PXP"))
    poll(service, [])
    slot = integration.school_state(store, connection_id)
    assert slot["last_poll_ok"] is True
    assert "auth_reason" not in slot
    [listed] = integration.build_schools(service, store)
    assert listed["status_reason"] == ""


def test_a_new_reason_is_announced_even_when_a_wrong_password_was_already_announced(tmp_path):
    failures = [forced(), LoginError("wrong")]
    service, store, connection_id, _ = school(tmp_path, lambda: failures.pop())
    clock = Clock()
    service.connection(connection_id).clock = clock
    sent = []
    poll(service, sent)
    clock.value += REFUSAL_WAIT_FIRST_SECONDS + 1
    poll(service, sent)
    assert sent == [messages.text("notify.auth.badCredentials"), messages.text("api.login.twofactorSetup")]


def test_an_unknown_account_and_a_default_password_carry_their_own_reason(tmp_path):
    for reason, key in (
        ("unknown_account", "api.login.unknownAccount"),
        ("default_password_blocked", "api.login.defaultPassword"),
        ("locked", "api.login.locked"),
    ):
        service, store, connection_id, _ = school(
            tmp_path / reason, LoginError("refused", message_key=key, reason=reason)
        )
        sent = []
        poll(service, sent)
        assert sent == [messages.text(key)]
        assert integration.school_state(store, connection_id)["auth_reason"] == reason
        assert integration.build_schools(service, store)[0]["status_reason"] == reason


def test_a_plain_wrong_password_keeps_the_known_message_and_reason(tmp_path):
    service, store, connection_id, _ = school(tmp_path, LoginError("wrong"))
    sent = []
    poll(service, sent)
    assert sent == [messages.text("notify.auth.badCredentials")]
    assert integration.build_schools(service, store)[0]["status_reason"] == "bad_credentials"


def test_the_health_check_names_the_forced_setup_live_and_from_the_stored_poll(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    live = connection_service(store, connection_id, lambda url: Client(url, fail=forced()))
    assert live.health_status(clock=lambda: 1000.0) == {"status": "auth_failed", "stale": False, "reason": FORCED}
    integration.record_school_poll(store, connection_id, 1000.0, False, integration.ERROR_AUTH, auth_reason=FORCED)
    stored = connection_service(store, connection_id, lambda url: Client(url))
    assert stored.health_status(clock=lambda: 1060.0) == {"status": "auth_failed", "stale": False, "reason": FORCED}


def test_the_health_overview_hands_the_reason_to_the_app(tmp_path):
    service, store, connection_id, _ = school(tmp_path, forced)
    _, rows = service.health_overview(clock=lambda: 1000.0)
    assert rows[0]["reason"] == FORCED


def test_repairing_the_password_names_the_forced_setup_and_keeps_the_old_password(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    service = connection_service(store, connection_id, lambda url: Client(url, refusal=FORCED, accepts=True))
    result = service.repair_password("new-secret")
    assert result["ok"] is False
    assert result["message_key"] == "api.login.twofactorSetup"
    assert store.load_secrets(connection_id)["password"] == "secret"


def test_repairing_the_password_names_an_unknown_account(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    service = connection_service(
        store, connection_id, lambda url: Client(url, refusal="unknown_account", accepts=False)
    )
    result = service.repair_password("new-secret")
    assert result["ok"] is False
    assert result["message_key"] == "api.login.unknownAccount"


def test_repairing_the_password_tells_an_unclear_answer_from_no_answer(tmp_path):
    for answered, key in ((True, "api.repair.unexpected"), (False, "api.repair.unreachable")):
        store = Store(tmp_path / str(answered) / "data")
        connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
        service = connection_service(
            store, connection_id, lambda url: Client(url, accepts=None, answered=answered)
        )
        result = service.repair_password("new-secret")
        assert result["ok"] is False
        assert result["message_key"] == key
        assert store.load_secrets(connection_id)["password"] == "secret"


def test_the_app_health_names_the_forced_setup_of_the_failing_school(tmp_path):
    service, store, connection_id, _ = school(tmp_path, forced)
    health = TestClient(create_app(service)).get("/api/health").json()
    assert health["connection"] == "auth_failed"
    assert health["auth_reason"] == FORCED
    assert health["connections"][0]["reason"] == FORCED


def test_a_read_during_the_forced_setup_answers_with_the_setup_message(tmp_path):
    service, store, connection_id, _ = school(tmp_path, forced)
    body = TestClient(create_app(service)).get("/api/children", params={"connection": connection_id}).json()
    assert body["error"] == "auth_failed"
    assert body["message_key"] == "api.login.twofactorSetup"


def test_a_locked_account_is_not_signed_in_again_on_the_next_poll(tmp_path):
    service, store, connection_id, log = school(
        tmp_path, LoginError("locked", message_key="api.login.locked", reason="locked")
    )
    sent = []
    poll(service, sent)
    poll(service, sent)
    assert log == ["parent.one"]
    assert sent == [messages.text("api.login.locked")]


def test_a_repaired_password_lifts_the_hold_of_a_lock(tmp_path):
    failures = [LoginError("locked", message_key="api.login.locked", reason="locked")]
    service, store, connection_id, log = school(tmp_path, lambda: failures[0] if failures else None)
    sent = []
    poll(service, sent)
    assert "login_hold" in store.load_secrets(connection_id)
    failures.clear()
    assert service.repair_password(connection_id, "secret")["ok"] is True
    assert "login_hold" not in store.load_secrets(connection_id)
    poll(service, sent)
    assert log == ["parent.one", "parent.one"]


def test_the_troubleshooting_report_never_signs_in(tmp_path):
    from app import diagnostics

    service, _, connection_id, log = school(tmp_path, LoginError("wrong"))
    connection = service.connection(connection_id)
    for structure in (False, True):
        diagnostics.school_section(1, connection, structure, None)
    assert log == []


def test_the_report_reads_the_session_the_poller_left_open(tmp_path):
    from app import diagnostics

    service, _, connection_id, log = school(tmp_path, None)
    connection = service.connection(connection_id)
    connection._session()
    signed_in = len(log)
    lines = diagnostics.school_section(1, connection, False, None)[0]
    assert "- Session: not opened" in lines
    client, state = diagnostics._session_of(connection)
    assert state == "ok" and client is connection.signed_in_session()
    assert len(log) == signed_in


def test_the_report_says_when_nobody_is_signed_in(tmp_path):
    from app import diagnostics

    service, _, connection_id, log = school(tmp_path, None)
    assert diagnostics._session_of(service.connection(connection_id)) == (None, "not signed in")
    assert log == []


def expiring(service, connection_id, clock):
    connection = service.connection(connection_id)
    connection.clock = clock
    return connection


def test_a_school_app_that_always_answers_401_signs_in_again_at_most_once_per_window(tmp_path):
    clock = Clock()
    service, _, connection_id, log = school(tmp_path, None)
    connection = expiring(service, connection_id, clock)
    for _ in range(20):
        connection._forget_session(connection._session())
    assert log == ["parent.one"]
    clock.value += 11 * 60
    for _ in range(20):
        connection._forget_session(connection._session())
    assert log == ["parent.one", "parent.one"]
    clock.value += 5 * 60
    for _ in range(20):
        connection._forget_session(connection._session())
    assert log == ["parent.one", "parent.one"]


def test_an_old_session_does_not_drop_a_newer_one(tmp_path):
    clock = Clock()
    service, _, connection_id, log = school(tmp_path, None)
    connection = expiring(service, connection_id, clock)
    old = connection._session()
    connection._client = None
    newer = connection._session()
    clock.value += 60 * 60
    connection._forget_session(old)
    assert connection.signed_in_session() is newer


def test_a_read_that_meets_an_expired_session_says_so():
    from app.iserv.dsa import DieSchulAppClient
    from app.iserv.errors import DataError
    from tests.test_write_certainty import RefusingSession

    client = DieSchulAppClient("https://school.example", RefusingSession(401))
    for read in (client.pinboards_or_raise, client.sick_note_children_or_raise):
        try:
            read()
        except DataError as error:
            assert error.message_key == "api.schoolApp.sessionExpired"
        else:
            raise AssertionError("an expired session must raise")


def test_a_permanent_401_backs_off_until_a_day(tmp_path):
    clock = Clock()
    service, _, connection_id, log = school(tmp_path, None)
    connection = expiring(service, connection_id, clock)
    for _ in range(12):
        session = connection._session()
        clock.value += connection._expiry_window + 1
        connection._forget_session(session)
    assert connection._expiry_window == 24 * 60 * 60
    signed_in = len(log)
    for _ in range(24):
        session = connection._session()
        clock.value += 60 * 60
        connection._forget_session(session)
    assert len(log) <= signed_in + 2


def test_a_session_that_lived_long_before_it_expired_resets_the_window(tmp_path):
    clock = Clock()
    service, _, connection_id, log = school(tmp_path, None)
    connection = expiring(service, connection_id, clock)
    connection._expiry_window = 40 * 60
    connection._session()
    clock.value += 6 * 60 * 60
    connection._forget_session(connection._client)
    assert connection._expiry_window == 10 * 60


def test_a_normal_school_app_answer_resets_the_back_off(tmp_path):
    clock = Clock()
    service, _, connection_id, log = school(tmp_path, None)
    connection = expiring(service, connection_id, clock)
    connection._expiry_window = 24 * 60 * 60
    connection._trust_school_app()
    assert connection._expiry_window == 10 * 60


def test_the_school_app_client_reports_a_normal_answer():
    from app.iserv.dsa import DieSchulAppClient
    from tests.test_write_certainty import RefusingSession

    answered = []
    DieSchulAppClient("https://school.example", RefusingSession(200, []), on_answered=lambda: answered.append(1)).pinboards()
    DieSchulAppClient("https://school.example", RefusingSession(401), on_answered=lambda: answered.append(1)).pinboards()
    assert answered == [1]


def test_a_second_sign_in_path_reuses_the_session_that_was_just_made(tmp_path):
    service, _, connection_id, log = school(tmp_path, None)
    connection = service.connection(connection_id)
    first = connection._session()
    assert connection._login() is first
    assert log == ["parent.one"]


def test_a_new_absence_refused_with_401_names_the_status_not_a_call_to_school():
    from app.absence_service import _absence_failure

    answer = type("Answer", (), {"status_code": 401})()
    result = _absence_failure(answer)
    assert result["message_key"] == "api.absence.upstream.statusSubmit"


def session_never_opened():
    return TwoFactorError(
        "session was not established", message_key="api.login.session", detail={"login_stage": "session"}
    )


def test_a_session_that_never_opened_holds_the_sign_in_briefly_and_names_no_lock(tmp_path):
    service, store, connection_id, log = school(tmp_path, session_never_opened)
    clock = Clock()
    service.connection(connection_id).clock = clock
    sent = []
    poll(service, sent)
    assert log == ["parent.one"]
    hold = store.load_secrets(connection_id)["login_hold"]
    assert hold["reason"] == SESSION_NOT_OPENED
    assert hold["wait"] == SESSION_HOLD_FIRST_SECONDS
    assert sent == []
    assert "locked" not in str(integration.school_state(store, connection_id))
    clock.value += SESSION_HOLD_FIRST_SECONDS - 1
    poll(service, sent)
    assert log == ["parent.one"]
    clock.value += 2
    poll(service, sent)
    assert log == ["parent.one"] * 2
    assert store.load_secrets(connection_id)["login_hold"]["wait"] == SESSION_HOLD_FIRST_SECONDS * 2


def test_the_hold_after_a_session_that_never_opened_grows_only_up_to_its_low_cap(tmp_path):
    service, store, connection_id, log = school(tmp_path, session_never_opened)
    clock = Clock()
    service.connection(connection_id).clock = clock
    gaps = []
    started = clock.value
    for _ in range(8):
        before = len(log)
        while len(log) == before:
            clock.value += 60
            poll(service, [])
        gaps.append(clock.value - started)
        started = clock.value
    assert gaps[1:] == [300, 600, 1200, 2400, 3600, 3600, 3600]


def test_the_health_check_names_a_session_that_never_opened_and_waits_out_its_hold(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    log = []
    live = connection_service(store, connection_id, lambda url: Client(url, fail=session_never_opened, log=log))
    live.clock = lambda: 1000.0
    expected = {"status": "auth_failed", "stale": False, "reason": SESSION_NOT_OPENED}
    assert live.health_status(clock=lambda: 1000.0) == expected
    assert live.health_status(clock=lambda: 1000.0) == expected
    assert log == ["parent.one"]


def refused_code():
    return TwoFactorError(
        "session was not established", message_key="api.login.twofactor", detail={"login_stage": "two_factor"}
    )


def no_session_after_the_code():
    return TwoFactorError(
        "session was not established", message_key="api.login.session", detail={"login_stage": "two_factor"}
    )


def active_hold(store, connection_id, now):
    from app.sign_in import _login_hold_of, _sign_in_fingerprint

    secrets = store.load_secrets(connection_id)
    return _login_hold_of(secrets, _sign_in_fingerprint(secrets), now)


def test_a_refused_code_holds_the_sign_in_from_the_second_failure_and_the_poll_names_the_code(tmp_path):
    service, store, connection_id, log = school(tmp_path, refused_code)
    clock = Clock()
    service.connection(connection_id).clock = clock
    sent, notifiers = pushes()
    first = Poller(service, notifiers=notifiers).poll_once()
    held = Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"] * 2
    assert [event["error"] for event in first] == [event["error"] for event in held] == [CODE_STEP_FAILED]
    slot = integration.school_state(store, connection_id)
    assert (slot["last_error"], slot["auth_reason"]) == (integration.ERROR_AUTH, CODE_STEP_FAILED)
    assert sent == []
    assert hold_of(store, connection_id)["wait"] == SESSION_HOLD_FIRST_SECONDS
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"] * 3
    assert hold_of(store, connection_id)["wait"] == SESSION_HOLD_FIRST_SECONDS * 2


def test_one_refused_code_right_after_the_setup_leaves_the_next_sign_in_free(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    log = []
    fail = failing_in_turn(refused_code)
    live = connection_service(store, connection_id, lambda url: Client(url, fail=fail, log=log))
    live.clock = lambda: 1000.0
    assert live.children() == []
    assert log == ["parent.one"] * 2
    assert "login_hold" not in store.load_secrets(connection_id)


def test_two_refused_codes_in_a_row_hold_the_next_sign_in(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    log = []
    fail = failing_in_turn(refused_code, refused_code)
    live = connection_service(store, connection_id, lambda url: Client(url, fail=fail, log=log))
    live.clock = lambda: 1000.0
    for _ in range(2):
        with pytest.raises(TwoFactorError):
            live.children()
    assert log == ["parent.one"] * 2
    assert active_hold(store, connection_id, 1000.0)["wait"] == SESSION_HOLD_FIRST_SECONDS


def test_only_code_failures_in_a_row_count_towards_the_hold(tmp_path):
    for name, between in (
        ("success", lambda live, store, connection_id: live._login()),
        ("setup", lambda live, store, connection_id: store.save_secrets(connection_id, dict(NO_2FA))),
    ):
        store = Store(tmp_path / name)
        connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
        fail = failing_in_turn(refused_code, lambda: None, refused_code) if name == "success" else refused_code
        live = connection_service(store, connection_id, lambda url: Client(url, fail=fail))
        live.clock = lambda: 1000.0
        with pytest.raises(TwoFactorError):
            live._login()
        between(live, store, connection_id)
        live._client = None
        with pytest.raises(TwoFactorError):
            live._login()
        assert active_hold(store, connection_id, 1000.0) is None, name


def test_a_held_code_failure_repeats_the_words_of_the_first_one(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    log = []
    live = connection_service(store, connection_id, lambda url: Client(url, fail=refused_code, log=log))
    seen = []
    for _ in range(3):
        try:
            live._login()
        except TwoFactorError as error:
            seen.append((error.message_key, error.detail["login_stage"]))
    assert seen == [("api.login.twofactor", "two_factor")] * 3
    assert log == ["parent.one"] * 2


def test_no_session_after_the_code_is_named_and_held_as_a_session_that_never_opened(tmp_path):
    service, store, connection_id, log = school(tmp_path, no_session_after_the_code)
    sent, notifiers = pushes()
    polls = [Poller(service, notifiers=notifiers).poll_once() for _ in range(3)]
    assert log == ["parent.one"] * 2
    for events in polls:
        assert {"connection_id": connection_id, "error": SESSION_NOT_OPENED} in events
    assert hold_of(store, connection_id)["reason"] == SESSION_NOT_OPENED
    assert integration.school_state(store, connection_id)["auth_reason"] == SESSION_NOT_OPENED
    assert sent == []


def test_a_code_failure_after_a_lock_never_shortens_the_lock(tmp_path):
    service, store, connection_id, log = school(tmp_path, failing_in_turn(locked, refused_code, refused_code))
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    clock.value += REFUSAL_WAIT_FIRST_SECONDS + 1
    poll(service, [])
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    poll(service, [])
    assert len(log) == 3


def test_a_sign_in_that_works_after_a_code_hold_lifts_it(tmp_path):
    service, store, connection_id, log = school(tmp_path, failing_in_turn(refused_code, refused_code))
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    poll(service, [])
    assert "until" in hold_of(store, connection_id)
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    poll(service, [])
    assert "login_hold" not in store.load_secrets(connection_id)
    assert len(log) == 3


def test_new_credentials_sign_in_at_once_despite_a_code_hold_of_the_old_ones(tmp_path):
    service, store, connection_id, log = school(tmp_path, refused_code)
    poll(service, [])
    poll(service, [])
    hold = hold_of(store, connection_id)
    assert "until" in hold and len(log) == 2
    store.save_secrets(connection_id, dict(NO_2FA, password="other-secret", login_hold=hold))
    poll(service, [])
    assert len(log) == 3


def test_a_lock_keeps_its_long_hold(tmp_path):
    service, store, connection_id, _ = school(
        tmp_path, LoginError("locked", message_key="api.login.locked", reason="locked")
    )
    poll(service, [])
    hold = store.load_secrets(connection_id)["login_hold"]
    assert hold["reason"] == "locked"
    assert hold["wait"] == REFUSAL_WAIT_FIRST_SECONDS


def test_a_sign_in_that_works_after_the_hold_lifts_it(tmp_path):
    failures = [session_never_opened()]
    service, store, connection_id, log = school(tmp_path, lambda: failures.pop() if failures else None)
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    assert "login_hold" in store.load_secrets(connection_id)
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    poll(service, [])
    assert "login_hold" not in store.load_secrets(connection_id)
    assert len(log) == 2


def test_a_repaired_password_lifts_the_hold_of_a_session_that_never_opened(tmp_path):
    failures = [session_never_opened()]
    service, store, connection_id, log = school(tmp_path, lambda: failures[0] if failures else None)
    poll(service, [])
    assert "login_hold" in store.load_secrets(connection_id)
    failures.clear()
    assert service.repair_password(connection_id, "secret")["ok"] is True
    assert "login_hold" not in store.load_secrets(connection_id)


def test_a_bare_forbidden_answer_from_the_real_client_holds_as_a_session_that_never_opened(tmp_path, fixture):
    from app.iserv.client import IServClient
    from tests.test_login_refusals import BARE_FORBIDDEN, Answer, School as ForbiddingSchool

    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    schools = []

    def client(url):
        schools.append(ForbiddingSchool(Answer(fixture("login_page.html")), Answer(BARE_FORBIDDEN, status_code=403)))
        return IServClient("https://school.example", session=schools[-1])

    live = connection_service(store, connection_id, client)
    assert live.health_status(clock=lambda: 1000.0)["reason"] == SESSION_NOT_OPENED
    assert live.health_status(clock=lambda: 1000.0)["reason"] == SESSION_NOT_OPENED
    assert store.load_secrets(connection_id)["login_hold"]["reason"] == SESSION_NOT_OPENED
    assert sum(school.posts for school in schools) == 1


class AnnouncingLock:
    def __init__(self, inner, watched, blocked):
        self.inner = inner
        self.watched = watched
        self.blocked = blocked

    def acquire(self, blocking=True, timeout=-1):
        if self.inner.acquire(blocking=False):
            return True
        if self.watched():
            self.blocked.set()
        return self.inner.acquire(blocking, timeout)

    def release(self):
        self.inner.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def test_a_password_repaired_while_a_failed_sign_in_writes_its_hold_is_never_undone(tmp_path):
    import threading

    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    armed = threading.Event()
    repair_blocked_or_done = threading.Event()

    def fail():
        armed.set()
        return session_never_opened()

    live = connection_service(store, connection_id, lambda url: Client(url, fail=fail))
    repairer = connection_service(store, connection_id, lambda url: Client(url, accepts=True))
    results = []

    def repair():
        try:
            results.append(repairer.repair_password("new-secret"))
        finally:
            repair_blocked_or_done.set()

    worker = threading.Thread(target=repair)
    store.lock = AnnouncingLock(store.lock, lambda: threading.current_thread() is worker, repair_blocked_or_done)
    original_load = live.store.load_secrets

    def load_while_a_repair_lands():
        secrets = original_load()
        if armed.is_set():
            armed.clear()
            worker.start()
            assert repair_blocked_or_done.wait(timeout=30)
        return secrets

    live.store.load_secrets = load_while_a_repair_lands
    live.check_connection()
    worker.join(timeout=30)
    assert not worker.is_alive()
    assert [result["ok"] for result in results] == [True]
    saved = store.load_secrets(connection_id)
    assert saved["password"] == "new-secret"
    assert "login_hold" not in saved


def test_a_password_stored_during_a_sign_in_with_the_old_one_drops_that_session(tmp_path):
    import threading

    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    signing_in = threading.Event()
    finish = threading.Event()
    repair_blocked_or_done = threading.Event()

    def slow():
        signing_in.set()
        assert finish.wait(timeout=30)

    live = connection_service(store, connection_id, lambda url: Client(url, fail=slow))
    results = []

    def repair():
        try:
            results.append(live.repair_password("new-secret"))
        finally:
            repair_blocked_or_done.set()

    worker = threading.Thread(target=repair)
    live._session_lock = AnnouncingLock(
        live._session_lock, lambda: threading.current_thread() is worker, repair_blocked_or_done
    )
    signer = threading.Thread(target=live._login)
    signer.start()
    assert signing_in.wait(timeout=30)
    worker.start()
    assert repair_blocked_or_done.wait(timeout=30)
    finish.set()
    signer.join(timeout=30)
    worker.join(timeout=30)
    assert not signer.is_alive() and not worker.is_alive()
    assert [result["ok"] for result in results] == [True]
    assert store.load_secrets(connection_id)["password"] == "new-secret"
    assert live.signed_in_session() is None


def test_a_late_success_with_old_credentials_keeps_the_hold_of_the_new_ones(tmp_path):
    from app.sign_in import _sign_in_fingerprint

    store = Store(tmp_path / "data")
    current = dict(NO_2FA, password="new-secret")
    connection_id = add_school(store, SCHOOL_ONE, secrets=current)
    live = connection_service(store, connection_id, lambda url: Client(url))
    newer = {"fingerprint": _sign_in_fingerprint(current), "reason": SESSION_NOT_OPENED, "until": 9e9, "wait": 300}
    stale = dict(newer, fingerprint="gone")
    for hold, kept in ((newer, True), (stale, False)):
        store.save_secrets(connection_id, dict(current, login_hold=hold))
        live._release_login_hold(_sign_in_fingerprint(NO_2FA))
        assert ("login_hold" in store.load_secrets(connection_id)) is kept


def failing_in_turn(*failures):
    queue = list(failures)
    return lambda: queue.pop(0)() if queue else None


def locked():
    return LoginError("locked", message_key="api.login.locked", reason="locked")


def hold_of(store, connection_id):
    return store.load_secrets(connection_id)["login_hold"]


def test_a_session_failure_after_a_lock_never_shortens_the_lock(tmp_path):
    service, store, connection_id, log = school(tmp_path, failing_in_turn(locked, session_never_opened))
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    clock.value += REFUSAL_WAIT_FIRST_SECONDS + 1
    poll(service, [])
    assert hold_of(store, connection_id)["reason"] == SESSION_NOT_OPENED
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    poll(service, [])
    assert len(log) == 2
    clock.value += REFUSAL_WAIT_FIRST_SECONDS
    poll(service, [])
    assert len(log) == 3


def test_a_lock_after_a_session_hold_keeps_growing_as_if_nothing_came_between(tmp_path):
    service, store, connection_id, _ = school(tmp_path, failing_in_turn(locked, session_never_opened, locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    for _ in range(3):
        poll(service, [])
        clock.value += hold_of(store, connection_id)["wait"] + 1
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS * 2


def test_a_lock_after_a_session_hold_starts_at_the_lock_wait(tmp_path):
    service, store, connection_id, _ = school(tmp_path, failing_in_turn(session_never_opened, locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    poll(service, [])
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    poll(service, [])
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS


def test_a_corrupt_stored_wait_never_replaces_the_sign_in_error(tmp_path):
    from app.sign_in import _sign_in_fingerprint

    for failure, reason, first in (
        (session_never_opened, SESSION_NOT_OPENED, SESSION_HOLD_FIRST_SECONDS),
        (locked, "locked", REFUSAL_WAIT_FIRST_SECONDS),
    ):
        for corrupt in ("soon", None, float("inf"), [1]):
            data = tmp_path / f"{reason}-{corrupt!r}"
            store = Store(data)
            secrets = dict(NO_2FA)
            stored = {"fingerprint": _sign_in_fingerprint(secrets), "reason": reason, "until": 0, "wait": corrupt}
            stored.update(session_wait=corrupt, refusal_wait=corrupt)
            connection_id = add_school(store, SCHOOL_ONE, secrets=dict(secrets, login_hold=stored))
            live = connection_service(store, connection_id, lambda url: Client(url, fail=failure))
            assert live.check_connection() == "auth_failed"
            assert hold_of(store, connection_id)["wait"] == first


def test_new_credentials_sign_in_at_once_despite_a_session_hold_of_the_old_ones(tmp_path):
    service, store, connection_id, log = school(tmp_path, session_never_opened)
    poll(service, [])
    hold = hold_of(store, connection_id)
    store.save_secrets(connection_id, dict(NO_2FA, password="other-secret", login_hold=hold))
    poll(service, [])
    assert len(log) == 2


def test_a_session_hold_after_an_oversized_lock_level_stays_at_the_lock_cap(tmp_path):
    from app.sign_in import REFUSAL_WAIT_CAP_SECONDS, _sign_in_fingerprint

    store = Store(tmp_path / "data")
    oversized = {"fingerprint": _sign_in_fingerprint(NO_2FA), "reason": "locked", "until": 1000.0, "wait": 10**9}
    oversized["refused_at"] = 1000.0
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA, login_hold=oversized))
    live = connection_service(store, connection_id, lambda url: Client(url, fail=session_never_opened))
    live.clock = lambda: 1060.0
    live.check_connection()
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_CAP_SECONDS
    assert hold_of(store, connection_id)["refusal_wait"] == REFUSAL_WAIT_CAP_SECONDS


DAY = 24 * 60 * 60


def locked_then(*later):
    return failing_in_turn(locked, *later)


def poll_at(service, clock, seconds_after_start, started):
    clock.value = started + seconds_after_start
    poll(service, [])


def test_a_new_lock_within_a_day_doubles_the_wait(tmp_path):
    service, store, connection_id, _ = school(tmp_path, locked_then(locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    started = clock.value
    poll(service, [])
    poll_at(service, clock, DAY - 60, started)
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS * 2


def test_a_lock_after_a_day_without_a_new_lock_starts_again_at_the_first_wait(tmp_path):
    service, store, connection_id, _ = school(tmp_path, locked_then(locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    started = clock.value
    poll(service, [])
    poll_at(service, clock, DAY + 60, started)
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS


def test_a_session_hold_a_day_after_the_last_lock_carries_no_lock_level(tmp_path):
    service, store, connection_id, _ = school(tmp_path, locked_then(session_never_opened))
    clock = Clock()
    service.connection(connection_id).clock = clock
    started = clock.value
    poll(service, [])
    poll_at(service, clock, DAY + 60, started)
    hold = hold_of(store, connection_id)
    assert hold["reason"] == SESSION_NOT_OPENED
    assert hold["wait"] == SESSION_HOLD_FIRST_SECONDS
    assert "refusal_wait" not in hold


def test_the_lock_level_carried_through_session_holds_still_ends_a_day_after_the_lock(tmp_path):
    service, store, connection_id, _ = school(tmp_path, locked_then(session_never_opened, session_never_opened, locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    started = clock.value
    poll(service, [])
    poll_at(service, clock, 2 * REFUSAL_WAIT_FIRST_SECONDS, started)
    assert hold_of(store, connection_id)["refusal_wait"] == REFUSAL_WAIT_FIRST_SECONDS
    poll_at(service, clock, DAY + 60, started)
    assert "refusal_wait" not in hold_of(store, connection_id)
    poll_at(service, clock, DAY + 2 * 60 * 60, started)
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS


def test_a_lock_after_a_session_hold_within_a_day_of_the_last_lock_still_doubles(tmp_path):
    service, store, connection_id, _ = school(tmp_path, locked_then(session_never_opened, locked))
    clock = Clock()
    service.connection(connection_id).clock = clock
    started = clock.value
    poll(service, [])
    poll_at(service, clock, 2 * REFUSAL_WAIT_FIRST_SECONDS, started)
    poll_at(service, clock, DAY - 60, started)
    assert hold_of(store, connection_id)["reason"] == "locked"
    assert hold_of(store, connection_id)["wait"] == REFUSAL_WAIT_FIRST_SECONDS * 2


def test_an_old_stored_hold_without_a_lock_time_decays_by_its_own_start(tmp_path):
    from app.sign_in import _sign_in_fingerprint

    now = 1_000_000.0
    fingerprint = _sign_in_fingerprint(NO_2FA)
    cases = (
        ({"reason": "locked", "wait": 3600, "until": now - 60}, locked, "locked", 7200),
        ({"reason": "locked", "wait": 3600, "until": now - DAY}, locked, "locked", REFUSAL_WAIT_FIRST_SECONDS),
        (
            {"reason": SESSION_NOT_OPENED, "wait": 3600, "session_wait": 300, "refusal_wait": 3600, "until": now - 60},
            locked,
            "locked",
            7200,
        ),
        (
            {"reason": SESSION_NOT_OPENED, "wait": 3600, "session_wait": 300, "refusal_wait": 3600, "until": now - DAY},
            locked,
            "locked",
            REFUSAL_WAIT_FIRST_SECONDS,
        ),
    )
    for index, (stored, failure, reason, wait) in enumerate(cases):
        store = Store(tmp_path / f"old-{index}")
        stored = dict(stored, fingerprint=fingerprint)
        connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA, login_hold=stored))
        live = connection_service(store, connection_id, lambda url: Client(url, fail=failure))
        live.clock = lambda: now
        live.check_connection()
        assert (hold_of(store, connection_id)["reason"], hold_of(store, connection_id)["wait"]) == (reason, wait)


def pushes():
    sent = []
    return sent, {
        event: (lambda event: lambda name, message: sent.append((event, message)) or True)(event)
        for event in ("auth", "outage")
    }


def test_a_poll_that_meets_a_session_that_never_opened_records_a_sign_in_problem_and_pushes_nothing(tmp_path):
    service, store, connection_id, log = school(tmp_path, session_never_opened)
    sent, notifiers = pushes()
    first = Poller(service, notifiers=notifiers).poll_once()
    held = Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"]
    for events in (first, held):
        assert {"connection_id": connection_id, "error": SESSION_NOT_OPENED} in events
    slot = integration.school_state(store, connection_id)
    assert slot["last_error"] == integration.ERROR_AUTH
    assert slot["auth_reason"] == SESSION_NOT_OPENED
    assert sent == []
    expected = {"status": "auth_failed", "stale": False, "reason": SESSION_NOT_OPENED}
    assert service.connection(connection_id).health_status() == expected
    health = TestClient(create_app(service)).get("/api/health").json()
    assert (health["connection"], health["auth_reason"]) == ("auth_failed", SESSION_NOT_OPENED)


def test_a_session_that_never_opened_during_the_module_check_is_still_a_sign_in_problem(tmp_path):
    service, store, connection_id, _ = school(tmp_path, session_never_opened)
    silent = {"modules": {name: False for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(silent)
    sent, notifiers = pushes()
    Poller(service, notifiers=notifiers).poll_once()
    slot = integration.school_state(store, connection_id)
    assert slot["last_poll_ok"] is False
    assert slot["auth_reason"] == SESSION_NOT_OPENED
    assert sent == []


def test_home_assistant_sees_a_session_that_never_opened_as_an_error_without_a_login_reason(tmp_path):
    from tests.test_integration_contract import assert_matches

    service, store, connection_id, _ = school(tmp_path, session_never_opened)
    poll(service, [])
    [listed] = integration.build_schools(service, store)
    assert listed["status"] == integration.STATUS_ERROR
    assert listed["status_reason"] == ""
    assert_matches("#/$defs/schoolInfo", listed)


def test_a_wrong_password_after_a_session_that_never_opened_is_still_announced(tmp_path):
    wrong = LoginError("refused", message_key="api.login.failed", reason="bad_credentials")
    service, store, connection_id, _ = school(tmp_path, failing_in_turn(session_never_opened, lambda: wrong))
    clock = Clock()
    service.connection(connection_id).clock = clock
    sent, notifiers = pushes()
    Poller(service, notifiers=notifiers).poll_once()
    clock.value += SESSION_HOLD_FIRST_SECONDS + 1
    Poller(service, notifiers=notifiers).poll_once()
    assert [event for event, _ in sent] == ["auth"]
    [listed] = integration.build_schools(service, store)
    assert (listed["status"], listed["status_reason"]) == (integration.STATUS_AUTH_FAILED, "bad_credentials")


def stored_hold_case(tmp_path, name, stored, failure, now):
    from app.sign_in import _sign_in_fingerprint

    store = Store(tmp_path / name)
    stored = dict(stored, fingerprint=_sign_in_fingerprint(NO_2FA))
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA, login_hold=stored))
    live = connection_service(store, connection_id, lambda url: Client(url, fail=failure))
    live.clock = lambda: now
    assert live.check_connection() == "auth_failed"
    return hold_of(store, connection_id)


def test_huge_stored_numbers_never_break_the_hold(tmp_path):
    now = 1_000_000.0
    huge = 10**400
    cases = (
        {"reason": "locked", "wait": huge, "until": now - 60},
        {"reason": "locked", "wait": 1800, "until": huge},
        {"reason": "locked", "wait": 1800, "until": now + 10 * DAY},
        {"reason": "locked", "wait": 1800, "until": float("nan")},
        {"reason": "locked", "wait": 1800, "until": now - 60, "refused_at": huge},
        {"reason": "locked", "wait": huge, "until": huge, "refused_at": huge},
        {"reason": SESSION_NOT_OPENED, "wait": huge, "session_wait": huge, "refusal_wait": huge, "until": now - 60},
        {"reason": SESSION_NOT_OPENED, "wait": 300, "refusal_wait": 1800, "until": now - 60, "refused_at": -huge},
    )
    for index, stored in enumerate(cases):
        for failure, reason in ((locked, "locked"), (session_never_opened, SESSION_NOT_OPENED)):
            hold = stored_hold_case(tmp_path, f"huge-{index}-{reason}", stored, failure, now)
            assert hold["reason"] == reason
            assert 0 < hold["wait"] <= 12 * 60 * 60
            assert now < hold["until"] <= now + 12 * 60 * 60


def test_a_corrupt_lock_time_falls_back_to_the_start_of_the_stored_hold(tmp_path):
    now = 1_000_000.0
    for index, corrupt in enumerate(("soon", None, [1], float("inf"), float("nan"), True, 10**400)):
        kept = {"reason": "locked", "wait": 3600, "until": now - 60, "refused_at": corrupt}
        assert stored_hold_case(tmp_path, f"kept-{index}", kept, locked, now)["wait"] == 7200
        old = dict(kept, until=now - DAY)
        assert stored_hold_case(tmp_path, f"old-{index}", old, locked, now)["wait"] == REFUSAL_WAIT_FIRST_SECONDS


def test_the_lock_level_resets_exactly_a_day_after_the_lock(tmp_path):
    now = 1_000_000.0
    for name, refused_at, wait in (
        ("day", now - DAY, REFUSAL_WAIT_FIRST_SECONDS),
        ("just-under", now - DAY + 1, REFUSAL_WAIT_FIRST_SECONDS * 4),
    ):
        stored = {"reason": "locked", "wait": REFUSAL_WAIT_FIRST_SECONDS * 2, "until": now - 60, "refused_at": refused_at}
        assert stored_hold_case(tmp_path, name, stored, locked, now)["wait"] == wait


SCHOOL_TWO = "https://school-two.example"


def two_failing_schools(tmp_path):
    import time

    store = Store(tmp_path / "data")
    first = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    second = add_school(store, SCHOOL_TWO, secrets=dict(NO_2FA, username="parent.two"), school_name="School Two")
    now = time.time()
    integration.record_school_poll(store, first, now, False, integration.ERROR_AUTH, auth_reason=SESSION_NOT_OPENED)
    integration.record_school_poll(store, second, now, False, integration.ERROR_AUTH, auth_reason="bad_credentials")
    service = IServService(store, client_factory=lambda url: Client(url))
    return service, store, first, second


def test_the_app_health_prefers_a_school_that_needs_a_new_password_over_a_missing_session(tmp_path):
    service, _, _, second = two_failing_schools(tmp_path)
    health = TestClient(create_app(service)).get("/api/health").json()
    assert health["connection"] == "auth_failed"
    assert (health["connection_id"], health["auth_reason"], health["username"]) == (second, "bad_credentials", "parent.two")


def test_the_app_health_names_a_missing_session_when_no_school_needs_more(tmp_path):
    service, store, first, second = two_failing_schools(tmp_path)
    import time

    integration.record_school_poll(store, second, time.time(), False, integration.ERROR_AUTH, auth_reason=SESSION_NOT_OPENED)
    health = TestClient(create_app(service)).get("/api/health").json()
    assert (health["connection_id"], health["auth_reason"]) == (first, SESSION_NOT_OPENED)


def test_a_retry_names_the_reason_of_a_failed_sign_in(tmp_path):
    service, store, connection_id, _ = school(tmp_path, session_never_opened)
    answer = TestClient(create_app(service)).post(f"/api/connections/{connection_id}/retry").json()
    assert answer["ok"] is True
    assert (answer["status"], answer["reason"]) == ("auth_failed", SESSION_NOT_OPENED)


def test_a_retry_that_signs_in_names_no_reason(tmp_path):
    service, store, connection_id, _ = school(tmp_path, None)
    silent = {"modules": {name: False for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(silent)
    answer = TestClient(create_app(service)).post(f"/api/connections/{connection_id}/retry").json()
    assert (answer["status"], answer["reason"]) == ("ok", "")


def test_only_a_sign_in_problem_escapes_the_module_check(tmp_path):
    service, _, connection_id, _ = school(tmp_path, None)
    connection = service.connection(connection_id)
    poller = Poller(service)
    for failure in (DataError("odd page"), ValueError("broken")):
        def refresh(failure=failure):
            raise failure

        connection.refresh_modules = refresh
        assert poller._registry(connection) == modules.registry_of(connection)
    for failure in (session_never_opened, refused_code, no_session_after_the_code):
        connection.refresh_modules = lambda failure=failure: (_ for _ in ()).throw(failure())
        with pytest.raises(TwoFactorError):
            poller._registry(connection)


def test_a_code_refused_during_the_module_check_is_a_sign_in_problem_after_one_attempt(tmp_path):
    service, store, connection_id, log = school(tmp_path, refused_code)
    silent = {"modules": {name: False for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(silent)
    sent, notifiers = pushes()
    events = Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"]
    assert {"connection_id": connection_id, "error": CODE_STEP_FAILED} in events
    slot = integration.school_state(store, connection_id)
    assert (slot["last_poll_ok"], slot["auth_reason"]) == (False, CODE_STEP_FAILED)
    assert sent == []


def test_iserv_answering_after_a_long_outage_without_a_session_says_it_is_back_but_sends_no_sign_in_push(tmp_path):
    service, store, connection_id, _ = school(tmp_path, session_never_opened)
    integration.note_outage(store, connection_id, 1000, "timeout", 1800)
    integration.mark_outage_notified(store, connection_id)
    sent, notifiers = pushes()
    Poller(service, notifiers=notifiers).poll_once(connection_id=connection_id)
    assert [event for event, _ in sent] == ["outage"]
    assert sent[0][1] == messages.text_in(None, "notify.outage.back", {"school": "School One"})
    slot = integration.school_state(store, connection_id)
    assert integration.OUTAGE_SINCE not in slot
    assert slot["auth_reason"] == SESSION_NOT_OPENED


def test_no_sign_in_hold_is_ever_longer_than_the_bound_that_drops_broken_holds():
    from app import sign_in

    for wait in (sign_in.SETUP_RETRY_SECONDS, sign_in.SESSION_HOLD_CAP_SECONDS, sign_in.REFUSAL_WAIT_FIRST_SECONDS):
        assert wait <= sign_in.REFUSAL_WAIT_CAP_SECONDS


class ExpiringClient(Client):
    def get_children(self):
        self.authed = False
        return []


def test_a_session_that_never_opens_again_partway_through_a_poll_is_a_sign_in_problem(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    log = []
    fail = failing_in_turn(lambda: None, session_never_opened)
    service = IServService(store, client_factory=lambda url: ExpiringClient(url, fail=fail, log=log))
    sent, notifiers = pushes()
    events = Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"] * 2
    assert {"connection_id": connection_id, "error": SESSION_NOT_OPENED} in events
    slot = integration.school_state(store, connection_id)
    assert (slot["last_error"], slot["auth_reason"]) == (integration.ERROR_AUTH, SESSION_NOT_OPENED)
    assert sent == []


def refused_after(successes):
    attempts = []

    def fail():
        attempts.append(1)
        return refused_code() if len(attempts) > successes else None

    return fail


def test_a_code_refused_again_partway_through_a_poll_is_a_sign_in_problem_like_at_the_start(tmp_path, caplog):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    log = []
    fail = refused_after(1)
    service = IServService(store, client_factory=lambda url: ExpiringClient(url, fail=fail, log=log))
    sent, notifiers = pushes()
    with caplog.at_level("WARNING", logger="app.poller"):
        events = Poller(service, notifiers=notifiers).poll_once()
    assert len(log) > 1
    assert {"connection_id": connection_id, "error": CODE_STEP_FAILED} in events
    slot = integration.school_state(store, connection_id)
    assert (slot["last_error"], slot["auth_reason"]) == (integration.ERROR_AUTH, CODE_STEP_FAILED)
    assert sent == []
    assert "sign-in code refused" in caplog.text


def test_a_module_that_fails_while_the_session_holds_is_still_reported_as_before(tmp_path):
    service, store, connection_id, log = school(tmp_path, None)
    events = poll(service, [])
    assert log == ["parent.one"]
    assert any(event.get("module") and event.get("error") for event in events)
    assert integration.school_state(store, connection_id)["last_error"] == integration.ERROR_NETWORK


def refused_codes_apart(tmp_path, gap):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    clock = Clock()
    live = connection_service(store, connection_id, lambda url: Client(url, fail=refused_code))
    live.clock = clock
    for step in (0, gap):
        clock.value += step
        with pytest.raises(TwoFactorError):
            live._login()
    return live, store, connection_id, clock


def test_a_refused_code_a_day_after_the_last_one_starts_counting_again(tmp_path):
    _, store, connection_id, clock = refused_codes_apart(tmp_path, DAY)
    assert active_hold(store, connection_id, clock.value) is None
    assert hold_of(store, connection_id)["code_failures"] == 1


def test_refused_codes_within_a_day_keep_counting_through_the_hold(tmp_path):
    live, store, connection_id, clock = refused_codes_apart(tmp_path, DAY - 1)
    assert active_hold(store, connection_id, clock.value)["wait"] == SESSION_HOLD_FIRST_SECONDS
    clock.value += SESSION_HOLD_FIRST_SECONDS
    with pytest.raises(TwoFactorError):
        live._login()
    assert active_hold(store, connection_id, clock.value)["wait"] == SESSION_HOLD_FIRST_SECONDS * 2


def test_a_stored_code_failure_without_a_usable_time_is_not_counted(tmp_path):
    now = 1_000_000.0
    stamps = ("soon", None, [1], True, float("inf"), float("nan"), 10**400, now + 60, now - DAY)
    for index, stamp in enumerate(stamps):
        stored = {"code_failures": 1, "code_failed_at": stamp}
        hold = stored_hold_case(tmp_path, f"stamp-{index}", stored, refused_code, now)
        assert "until" not in hold, stamp
        assert (hold["code_failures"], hold["code_failed_at"]) == (1, now), stamp
    legacy = stored_hold_case(tmp_path, "legacy", {"code_failures": 1}, refused_code, now)
    assert "until" not in legacy
    counted = stored_hold_case(tmp_path, "counted", {"code_failures": 1, "code_failed_at": now - 60}, refused_code, now)
    assert counted["wait"] == SESSION_HOLD_FIRST_SECONDS
    assert counted["code_failed_at"] == now


class CodeAskingClient(Client):
    def login(self, username, password, code_provider):
        self.log.append(username)
        code_provider()
        self.authed = True
        return self


def test_a_code_prompt_without_a_stored_key_holds_like_a_forced_setup_until_the_setup_stores_one(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    log = []
    service = IServService(store, client_factory=lambda url: CodeAskingClient(url, log=log))
    sent, notifiers = pushes()
    first = Poller(service, notifiers=notifiers).poll_once()
    held = Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"]
    for events in (first, held):
        assert {"connection_id": connection_id, "error": FORCED} in events
    hold = hold_of(store, connection_id)
    assert (hold["reason"], hold["wait"]) == (FORCED, SETUP_RETRY_SECONDS)
    assert [message for _, message in sent] == [messages.text("api.login.twofactorSetup")]
    with pytest.raises(TwoFactorSetupRequired) as raised:
        service.connection(connection_id)._login()
    assert raised.value.message_key == "api.login.twofactorSetup"
    assert log == ["parent.one"]
    store.save_secrets(connection_id, dict(NO_2FA, totp_secret="JBSWY3DPEHPK3PXP", login_hold=hold))
    Poller(service, notifiers=notifiers).poll_once()
    assert log == ["parent.one"] * 2
    assert "login_hold" not in store.load_secrets(connection_id)


def test_the_health_check_names_a_refused_code_as_a_code_problem_and_not_a_wrong_password(tmp_path):
    for name, failure, reason in (
        ("code", refused_code, "code_step_failed"),
        ("session", no_session_after_the_code, SESSION_NOT_OPENED),
    ):
        store = Store(tmp_path / name)
        connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
        log = []
        service = IServService(store, client_factory=lambda url: Client(url, fail=failure, log=log))
        live = service.connection(connection_id)
        live.clock = lambda: 1000.0
        expected = {"status": "auth_failed", "stale": False, "reason": reason}
        for _ in range(3):
            assert live.health_status(clock=lambda: 1000.0) == expected, name
        assert log == ["parent.one"] * 2, name
        health = TestClient(create_app(service)).get("/api/health").json()
        assert (health["connection"], health["auth_reason"]) == ("auth_failed", reason), name


def test_a_failed_check_never_drops_a_session_another_request_opened_meanwhile(tmp_path):
    import threading

    import requests

    from app.iserv.errors import OutageError

    checks = (
        ("connection", lambda live: live.check_connection()),
        ("health", lambda live: live.health_status(clock=lambda: 1000.0)),
    )
    failures = (
        ("code", lambda: TwoFactorError("odd")),
        ("outage", lambda: OutageError("unexpected")),
        ("timeout", lambda: requests.Timeout("slow")),
        ("network", lambda: requests.ConnectionError("down")),
    )
    for check_name, check in checks:
        for failure_name, failure in failures:
            name = f"{check_name}-{failure_name}"
            store = Store(tmp_path / name)
            connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
            fail = failing_in_turn(failure)
            live = connection_service(store, connection_id, lambda url, fail=fail: Client(url, fail=fail))
            live.clock = lambda: 1000.0
            opener_blocked_or_done = threading.Event()
            original = live._login

            def open_session():
                try:
                    original()
                finally:
                    opener_blocked_or_done.set()

            opener = threading.Thread(target=open_session)
            live._session_lock = AnnouncingLock(
                live._session_lock, lambda: threading.current_thread() is opener, opener_blocked_or_done
            )

            def failing_while_another_request_signs_in(timeout=None):
                try:
                    return original(timeout)
                except Exception:
                    opener.start()
                    assert opener_blocked_or_done.wait(timeout=30)
                    raise

            live._login = failing_while_another_request_signs_in
            check(live)
            opener.join(timeout=30)
            assert not opener.is_alive(), name
            assert live.signed_in_session() is not None, name


def test_removing_the_school_during_a_sign_in_leaves_no_session_behind(tmp_path):
    import threading

    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    signing_in = threading.Event()
    finish = threading.Event()
    clear_blocked_or_done = threading.Event()

    def slow():
        signing_in.set()
        assert finish.wait(timeout=30)

    live = connection_service(store, connection_id, lambda url: Client(url, fail=slow))

    def clear():
        try:
            live._clear_local_data()
        finally:
            clear_blocked_or_done.set()

    worker = threading.Thread(target=clear)
    live._session_lock = AnnouncingLock(
        live._session_lock, lambda: threading.current_thread() is worker, clear_blocked_or_done
    )
    signer = threading.Thread(target=live._login)
    signer.start()
    assert signing_in.wait(timeout=30)
    worker.start()
    assert clear_blocked_or_done.wait(timeout=30)
    finish.set()
    signer.join(timeout=30)
    worker.join(timeout=30)
    assert not signer.is_alive() and not worker.is_alive()
    assert live.signed_in_session() is None
    assert connection_id not in [entry["id"] for entry in store.connections()]


def test_the_poll_log_names_the_missing_session_that_stopped_a_module(tmp_path, caplog):
    from app.poller import SESSION_FAILURE_KIND

    store = Store(tmp_path / "data")
    add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    fail = failing_in_turn(lambda: None, session_never_opened)
    service = IServService(store, client_factory=lambda url: ExpiringClient(url, fail=fail))
    with caplog.at_level("WARNING", logger="app.poller"):
        Poller(service, notifiers=pushes()[1]).poll_once()
    assert f"sign-in opened no session: {SESSION_FAILURE_KIND}" in caplog.text


def test_a_refused_code_reaches_home_assistant_as_an_error_without_a_repair_and_the_retry_names_it(tmp_path):
    from tests.test_integration_contract import assert_matches

    service, store, connection_id, _ = school(tmp_path, refused_code)
    sent, notifiers = pushes()
    Poller(service, notifiers=notifiers).poll_once()
    assert sent == []
    [listed] = integration.build_schools(service, store)
    assert (listed["status"], listed["status_reason"]) == (integration.STATUS_ERROR, "")
    assert_matches("#/$defs/schoolInfo", listed)
    expected = {"status": "auth_failed", "stale": False, "reason": CODE_STEP_FAILED}
    assert service.connection(connection_id).health_status() == expected
    answer = TestClient(create_app(service)).post(f"/api/connections/{connection_id}/retry").json()
    assert (answer["ok"], answer["status"], answer["reason"]) == (True, "auth_failed", CODE_STEP_FAILED)
    assert sent == []


def test_a_password_only_school_never_gets_a_code_hold_or_a_code_reason(tmp_path, fixture):
    from app.iserv.client import IServClient
    from tests.test_login_refusals import BARE_FORBIDDEN, Answer, School as ForbiddingSchool

    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA))
    schools = []

    def client(url):
        schools.append(ForbiddingSchool(Answer(fixture("login_page.html")), Answer(BARE_FORBIDDEN, status_code=403)))
        return IServClient("https://school.example", session=schools[-1])

    live = connection_service(store, connection_id, client)
    clock = Clock()
    live.clock = clock
    for _ in range(4):
        assert live.health_status(clock=clock)["reason"] == SESSION_NOT_OPENED
        hold = hold_of(store, connection_id)
        assert hold["reason"] == SESSION_NOT_OPENED
        assert "code_failures" not in hold and "code_failed_at" not in hold
        clock.value = hold["until"] + 1
    assert sum(school.posts for school in schools) == 4


def test_the_messenger_never_signs_in_again_under_a_code_hold_or_a_missing_key_hold(tmp_path):
    for name, secrets, factory, key in (
        ("code", NO_2FA, lambda log: lambda url: Client(url, fail=refused_code, log=log), "api.login.twofactor"),
        ("key", NO_2FA, lambda log: lambda url: CodeAskingClient(url, log=log), "api.login.twofactorSetup"),
    ):
        store = Store(tmp_path / name)
        connection_id = add_school(store, SCHOOL_ONE, secrets=dict(secrets), school_name="School One")
        log = []
        service = IServService(store, client_factory=factory(log))
        for _ in range(2):
            Poller(service, notifiers=pushes()[1]).poll_once()
        signed_in = len(log)
        assert "until" in hold_of(store, connection_id), name
        app = TestClient(create_app(service))
        for path in ("/api/messenger/rooms", f"/api/messenger/teachers?query=ab&connection={connection_id}"):
            answer = app.get(path).json()
            assert (answer["error"], answer["message_key"]) == ("auth_failed", key), (name, path)
        assert len(log) == signed_in, name


def test_the_app_health_prefers_a_password_problem_then_a_refused_code_then_a_missing_session(tmp_path):
    import time

    for name, first_reason, second_reason, wanted in (
        ("password", CODE_STEP_FAILED, "bad_credentials", "second"),
        ("password-first", "unknown_account", CODE_STEP_FAILED, "first"),
        ("code", SESSION_NOT_OPENED, CODE_STEP_FAILED, "second"),
        ("code-first", CODE_STEP_FAILED, SESSION_NOT_OPENED, "first"),
    ):
        store = Store(tmp_path / name)
        first = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
        second = add_school(store, SCHOOL_TWO, secrets=dict(NO_2FA, username="parent.two"), school_name="School Two")
        now = time.time()
        integration.record_school_poll(store, first, now, False, integration.ERROR_AUTH, auth_reason=first_reason)
        integration.record_school_poll(store, second, now, False, integration.ERROR_AUTH, auth_reason=second_reason)
        service = IServService(store, client_factory=lambda url: Client(url))
        health = TestClient(create_app(service)).get("/api/health").json()
        expected = (first, first_reason) if wanted == "first" else (second, second_reason)
        assert (health["connection_id"], health["auth_reason"]) == expected, name


def test_the_app_ranks_the_late_sign_in_reasons_exactly_like_the_backend():
    import re
    from pathlib import Path

    from app.iserv.errors import LATE_SIGN_IN_REASONS, sign_in_reason_rank

    source = (Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.js").read_text(encoding="utf-8")
    constants = dict(re.findall(r'export const (REASON_\w+) = "([^"]+)";', source))
    [listed] = re.findall(r"const LATE_LOGIN_REASONS = Object\.freeze\(\[([^\]]*)\]\);", source)
    ranked = tuple(constants[name.strip()] for name in listed.split(",") if name.strip())
    assert ranked == LATE_SIGN_IN_REASONS
    assert [sign_in_reason_rank(reason) for reason in ranked] == list(range(1, len(ranked) + 1))


def refused_codes_through_their_holds(tmp_path, times, fail=refused_code, name="data"):
    store = Store(tmp_path / name)
    connection_id = add_school(store, SCHOOL_ONE, secrets=dict(NO_2FA), school_name="School One")
    registry = {"modules": {name: True for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(registry)
    log = []
    service = IServService(store, client_factory=lambda url: Client(url, fail=fail, log=log))
    clock = Clock()
    service.connection(connection_id).clock = clock
    sent, notifiers = pushes()
    poller = Poller(service, notifiers=notifiers)
    for _ in range(times):
        refuse_once_more(poller, store, connection_id, clock)
    return service, store, connection_id, log, clock, sent, poller


def refuse_once_more(poller, store, connection_id, clock):
    record = store.load_secrets(connection_id).get("login_hold") or {}
    if "until" in record:
        clock.value = max(clock.value, record["until"] + 1)
    poller.poll_once()


def repair_needed(service, connection_id):
    return service.connection(connection_id).code_refusal_needs_setup()


def test_the_third_held_code_refusal_in_a_row_asks_for_a_new_setup(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 3)
    assert len(log) == 3
    assert hold_of(store, connection_id)["code_holds"] == 2
    assert not repair_needed(service, connection_id)
    assert sent == []
    refuse_once_more(poller, store, connection_id, clock)
    assert len(log) == 4
    assert repair_needed(service, connection_id)
    assert sent == [("auth", messages.text("api.login.twofactor"))]


def test_a_code_refusal_that_asks_for_a_new_setup_pushes_once_and_then_stays_quiet(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 4)
    for _ in range(3):
        poller.poll_once()
        refuse_once_more(poller, store, connection_id, clock)
    assert len(log) == 7
    assert repair_needed(service, connection_id)
    assert sent == [("auth", messages.text("api.login.twofactor"))]


def test_home_assistant_gets_one_repair_for_a_code_refusal_that_asks_for_a_new_setup(tmp_path):
    from tests.test_integration_contract import assert_matches

    service, store, connection_id, *_ = refused_codes_through_their_holds(tmp_path, 3)
    [listed] = integration.build_schools(service, store)
    assert (listed["status"], listed["status_reason"]) == (integration.STATUS_ERROR, "")
    service, store, connection_id, *_, poller = refused_codes_through_their_holds(tmp_path, 4, name="announced")
    poller.poll_once()
    [listed] = integration.build_schools(service, store)
    assert (listed["status"], listed["status_reason"]) == (integration.STATUS_AUTH_FAILED, CODE_STEP_FAILED)
    assert_matches("#/$defs/schoolInfo", listed)
    expected = {"status": "auth_failed", "stale": False, "reason": CODE_STEP_FAILED}
    assert service.connection(connection_id).health_status() == expected


def test_new_credentials_end_the_repair_at_once_and_start_counting_again(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 4)
    store.save_secrets(connection_id, dict(NO_2FA, totp_secret="JBSWY3DPEHPK3PXP"))
    assert not repair_needed(service, connection_id)
    [listed] = integration.build_schools(service, store)
    assert listed["status"] == integration.STATUS_ERROR
    for _ in range(3):
        refuse_once_more(poller, store, connection_id, clock)
    assert not repair_needed(service, connection_id)
    assert len(sent) == 1
    refuse_once_more(poller, store, connection_id, clock)
    assert repair_needed(service, connection_id)
    assert len(sent) == 2


def test_a_sign_in_that_works_ends_the_repair_and_a_fresh_one_pushes_once_again(tmp_path):
    turns = [refused_code] * 4 + [lambda: None] + [refused_code] * 4
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(
        tmp_path, 4, fail=lambda: turns.pop(0)() if turns else refused_code()
    )
    assert repair_needed(service, connection_id)
    refuse_once_more(poller, store, connection_id, clock)
    assert "login_hold" not in store.load_secrets(connection_id)
    assert not repair_needed(service, connection_id)
    assert integration.build_schools(service, store)[0]["status"] != integration.STATUS_AUTH_FAILED
    service.connection(connection_id)._client = None
    for _ in range(4):
        refuse_once_more(poller, store, connection_id, clock)
    assert repair_needed(service, connection_id)
    assert sent == [("auth", messages.text("api.login.twofactor"))] * 2


def test_only_code_refusals_in_a_row_count_towards_the_repair(tmp_path):
    kinds = [refused_code, refused_code, refused_code, session_never_opened, refused_code, refused_code, refused_code]
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(
        tmp_path, len(kinds), fail=lambda: kinds.pop(0)() if kinds else refused_code()
    )
    assert hold_of(store, connection_id)["code_holds"] == 2
    assert not repair_needed(service, connection_id)
    refuse_once_more(poller, store, connection_id, clock)
    assert repair_needed(service, connection_id)


def test_the_count_towards_a_repair_ends_a_day_after_the_last_code_refusal(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 3)
    clock.value = hold_of(store, connection_id)["code_failed_at"] + DAY
    refuse_once_more(poller, store, connection_id, clock)
    record = hold_of(store, connection_id)
    assert (record["code_failures"], "code_holds" in record) == (1, False)
    assert not repair_needed(service, connection_id)


def test_a_repair_that_was_asked_for_stands_until_a_setup_new_credentials_or_a_working_sign_in(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 4)
    clock.value = hold_of(store, connection_id)["code_failed_at"] + 3 * DAY
    assert repair_needed(service, connection_id)
    refuse_once_more(poller, store, connection_id, clock)
    assert repair_needed(service, connection_id)
    assert len(sent) == 1


def test_a_session_that_never_opened_between_code_refusals_neither_repeats_the_push_nor_drops_the_repair(tmp_path):
    turns = [refused_code] * 4 + [session_never_opened] + [refused_code] * 4
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(
        tmp_path, 4, fail=lambda: turns.pop(0)() if turns else refused_code()
    )
    wanted = (integration.STATUS_AUTH_FAILED, CODE_STEP_FAILED)
    refuse_once_more(poller, store, connection_id, clock)
    assert integration.school_state(store, connection_id)["auth_reason"] == SESSION_NOT_OPENED
    [listed] = integration.build_schools(service, store)
    assert (listed["status"], listed["status_reason"]) == wanted
    for _ in range(4):
        refuse_once_more(poller, store, connection_id, clock)
        [listed] = integration.build_schools(service, store)
        assert (listed["status"], listed["status_reason"]) == wanted
    assert len(log) == 9
    assert sent == [("auth", messages.text("api.login.twofactor"))]


def test_a_failed_repair_push_is_tried_again_on_the_next_refused_poll_and_then_kept(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 3)
    answers = [False, True]
    tried = []
    poller.notifiers["auth"] = lambda name, message: tried.append(message) or (answers.pop(0) if answers else True)
    refuse_once_more(poller, store, connection_id, clock)
    assert len(tried) == 1
    poller.poll_once()
    assert len(tried) == 2
    for _ in range(2):
        poller.poll_once()
        refuse_once_more(poller, store, connection_id, clock)
    assert len(tried) == 2


def test_a_poll_that_passes_its_start_without_a_sign_in_keeps_the_repair_and_its_single_push(tmp_path):
    service, store, connection_id, log, clock, sent, poller = refused_codes_through_their_holds(tmp_path, 4)
    silent = {"modules": {name: False for name in modules.MODULES}, "checked_at": 1}
    store.connection_store(connection_id).save_modules(silent)
    connection = service.connection(connection_id)
    connection.refresh_modules = lambda: (_ for _ in ()).throw(DataError("odd page"))
    poller.poll_once()
    assert repair_needed(service, connection_id)
    assert integration.build_schools(service, store)[0]["status"] == integration.STATUS_AUTH_FAILED
    del connection.refresh_modules
    refuse_once_more(poller, store, connection_id, clock)
    assert len(sent) == 1
