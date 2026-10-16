import pytest
import requests

from app.iserv.client import IServClient, REGISTRATION_UNCONFIRMED_KEY
from app.iserv.errors import TwoFactorError
from app.iserv_prober import IServProber
from tests.conftest import load_fixture
from tests.test_wizard import CODE, CODE2, VALID_SECRET, make

BASE = "https://school.example"
LIST_URL = BASE + "/iserv/auth/settings/twofactor/"
STALE = "b2b6b8b0-1111-4a2a-9c3c-abcdef123456"
NEW = "0b0c0d0e-0000-4000-8000-000000000001"
OTHER = "c3c3c3c3-2222-4b2b-8d3d-abcdef654321"


def old(*uuids):
    return [{"uuid": uuid, "created": ""} for uuid in uuids]


def remember_uuid(wizard, store, uuid):
    connection_id = wizard.status()["connection_id"]
    secrets = store.base.load_secrets(connection_id)
    secrets["twofactor_uuid"] = uuid
    store.base.save_secrets(connection_id, secrets)


def connected(tmp_path, register, own=STALE):
    wizard, store, prober, clock = make(tmp_path, register=register, begin={"status": "awaiting_confirm", "stale_tokens": 1, "stale_removable": 1})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    if own:
        remember_uuid(wizard, store, own)
    wizard.connect(CODE)
    return wizard, store, prober


def test_the_code_step_knows_whether_old_entries_can_be_removed(tmp_path):
    wizard, _, _, _ = make(tmp_path, begin={"status": "awaiting_confirm", "stale_tokens": 2, "stale_removable": 1})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    state = wizard.connect(CODE)
    assert state["stale_tokens"] == 2
    assert state["stale_removable"] == 1


def test_old_entries_are_offered_after_the_connection_and_removed_with_the_app_key(tmp_path):
    wizard, store, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(STALE)})
    state = wizard.connect(CODE2)
    assert state["step"] == "child"
    assert state["stale_uuids"] == [STALE]
    state = wizard.remove_stale_tokens()
    assert prober.stale_calls == [(VALID_SECRET, [STALE])]
    assert "stale_uuids" not in state
    assert state["stale_removed"] == 1
    assert "error" not in state


def test_the_app_never_removes_its_own_new_entry(tmp_path):
    wizard, store, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(NEW, STALE)})
    wizard.connect(CODE2)
    wizard.remove_stale_tokens()
    assert prober.stale_calls == [(VALID_SECRET, [STALE])]


def test_a_removal_iserv_did_not_finish_keeps_the_offer(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(STALE)})
    wizard.connect(CODE2)
    prober.stale_answer = {"status": "partial", "left": [STALE]}
    state = wizard.remove_stale_tokens()
    assert state["stale_uuids"] == [STALE]
    assert state["error"]["message_key"] == "api.wizard.stale.partial"
    assert state["error"]["message_vars"] == {"count": 1}


def test_a_failed_or_unclear_removal_keeps_the_offer(tmp_path):
    answers = (
        ({"status": "failed", "left": [STALE]}, "api.wizard.stale.failed"),
        ({"status": "uncertain", "left": [STALE]}, "api.wizard.stale.failed"),
        ({"status": "outage"}, "api.wizard.outage"),
    )
    for answer, key in answers:
        wizard, _, prober = connected(tmp_path / answer["status"], {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(STALE)})
        wizard.connect(CODE2)
        prober.stale_answer = answer
        state = wizard.remove_stale_tokens()
        assert state["stale_uuids"] == [STALE]
        assert state["error"]["message_key"] == key


def test_removal_needs_old_entries_and_a_finished_connection(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET})
    assert wizard.remove_stale_tokens()["error"]["code"] == "stale_not_pending"
    state = wizard.connect(CODE2)
    assert "stale_uuids" not in state
    assert wizard.remove_stale_tokens()["error"]["code"] == "stale_not_pending"
    assert prober.stale_calls == []


def test_a_new_sign_in_forgets_the_old_entries(tmp_path):
    wizard, _, _ = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(STALE, OTHER)})
    state = wizard.connect(CODE2)
    assert state["other_tokens"]
    wizard.back()
    wizard.back()
    state = wizard.set_login("parent", "secret")
    assert "stale_uuids" not in state
    assert "other_tokens" not in state


def test_an_unconfirmed_registration_shows_the_real_state_and_offers_a_check(tmp_path):
    wizard, store, prober = connected(tmp_path, {"status": "unconfirmed"})
    state = wizard.connect(CODE2)
    assert state["step"] == "connect"
    assert state["registration_unconfirmed"] is True
    assert "awaiting_confirm" not in state
    assert state["error"]["message_key"] == "api.twofactor.unconfirmed"
    assert state["attempts"] == 0
    prober.registration_check = {"status": "unconfirmed"}
    assert wizard.check_registration()["registration_unconfirmed"] is True
    prober.registration_check = {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(STALE)}
    state = wizard.check_registration()
    assert state["step"] == "child"
    assert "registration_unconfirmed" not in state
    assert state["stale_uuids"] == [STALE]
    assert store.load_secrets()["totp_secret"] == VALID_SECRET
    assert store.load_secrets()["twofactor_uuid"] == NEW


def test_a_registration_iserv_does_not_list_asks_for_a_fresh_start(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "unconfirmed"})
    wizard.connect(CODE2)
    state = wizard.check_registration()
    assert state["error"]["message_key"] == "api.wizard.registration.missing"
    assert "registration_unconfirmed" not in state
    assert wizard.check_registration()["error"]["code"] == "registration_not_pending"
    begins = prober.begin_calls
    wizard.connect(CODE)
    assert prober.begin_calls == begins + 1


class Cookie:
    def __init__(self, name):
        self.name = name


class Answer:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {}


class TokenSchool:
    def __init__(self, lists, delete_status=200):
        self.headers = {}
        self.cookies = []
        self.lists = list(lists)
        self.delete_status = delete_status
        self.deleted = []
        self.codes = []

    def get(self, url, timeout=None, params=None, **kwargs):
        if "authentication/redirect" in url:
            self.cookies = [Cookie("IServSession")]
            return Answer(load_fixture("portal.html"), BASE + "/iserv/")
        if url == LIST_URL:
            name = self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
            if name is None:
                raise requests.ConnectionError("gone")
            return Answer(load_fixture(name), url)
        return Answer(load_fixture("login_page.html"), BASE + "/iserv/auth/login")

    def post(self, url, data=None, timeout=None, **kwargs):
        if "auth/login" in url:
            return Answer(load_fixture("twofactor_page.html"), BASE + "/iserv/auth/twofactor/confirm")
        if data and data.get("otp"):
            self.codes.append(data["otp"])
        return Answer(load_fixture("auth_continue.html"), BASE + "/iserv/auth/auth")

    def request(self, method, url, data=None, timeout=None, **kwargs):
        self.deleted.append((method, url, dict(data or {})))
        self.codes.append(dict(data or {}).get("delete[code]"))
        return Answer("", url, self.delete_status)


def prober_for(monkeypatch, school):
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=15: IServClient(url, session=school))
    prober = IServProber()
    prober.sleeper = lambda seconds: None
    return prober


def test_the_prober_removes_an_old_entry_with_a_code_from_the_app_key_and_rereads_the_list(monkeypatch):
    school = TokenSchool(["twofactor_list_uuid.html", "twofactor_list_uuid_removed.html"])
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result == {"status": "ok", "left": [], "removed": 1}
    method, url, data = school.deleted[0]
    assert method == "DELETE"
    assert url == BASE + "/iserv/auth/settings/twofactor/delete/" + STALE
    assert data["delete[_token]"] == "csrf-delete-token"
    assert len(data["delete[code]"]) == 6 and data["delete[code]"].isdigit()


def test_the_prober_skips_entries_iserv_no_longer_lists(monkeypatch):
    school = TokenSchool(["twofactor_list_uuid_removed.html"])
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result["status"] == "ok"
    assert school.deleted == []


def test_a_refused_delete_is_reported_with_what_is_left(monkeypatch):
    school = TokenSchool(["twofactor_list_uuid.html"], delete_status=403)
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result == {"status": "failed", "left": [STALE]}
    assert len(school.deleted) == 1


def test_an_unreadable_list_after_the_delete_is_uncertain(monkeypatch):
    school = TokenSchool(["twofactor_list_uuid.html", "twofactor_list_uuid.html", None])
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result == {"status": "uncertain", "left": [STALE]}


def test_an_unrecognised_page_after_the_delete_is_uncertain_and_never_ok(monkeypatch):
    school = TokenSchool(["twofactor_list_uuid.html", "login_page.html"])
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result == {"status": "uncertain", "left": [STALE]}
    assert len(school.deleted) == 1


def test_an_unrecognised_page_before_the_delete_sends_nothing(monkeypatch):
    school = TokenSchool(["login_page.html"])
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result == {"status": "uncertain", "left": [STALE]}
    assert school.deleted == []


class PendingClient:
    def __init__(self, rows):
        self.rows = rows

    def read_token_list(self):
        if self.rows is None:
            raise TwoFactorError("unreadable")
        return self.rows


class Registration:
    secret = VALID_SECRET


def pending_prober(rows, existing=(STALE,)):
    prober = IServProber()
    prober._pending = {
        "client": PendingClient(rows),
        "registration": Registration(),
        "url": BASE,
        "username": "u",
        "existing_uuids": set(existing),
        "old_tokens": [{"uuid": STALE, "created": "2026-09-01"}],
        "unconfirmed": True,
    }
    return prober


def test_checking_an_unconfirmed_registration_reads_the_token_list():
    listed = [{"name": "ISERV-Connector", "uuid": STALE}, {"name": "ISERV-Connector", "uuid": NEW}]
    result = pending_prober(listed).check_registration(BASE, "u")
    assert result == {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": [{"uuid": STALE, "created": "2026-09-01"}]}
    assert pending_prober([{"name": "ISERV-Connector", "uuid": STALE}]).check_registration(BASE, "u") == {"status": "missing"}
    assert pending_prober(None).check_registration(BASE, "u") == {"status": "unconfirmed"}
    assert IServProber().check_registration(BASE, "u") == {"status": "expired"}


def test_an_unconfirmed_registration_keeps_the_pending_setup(monkeypatch):
    prober = IServProber()

    class Unconfirmed:
        def confirm_totp_registration(self, registration, name, code, at=None):
            raise TwoFactorError("unclear", message_key=REGISTRATION_UNCONFIRMED_KEY)

    prober._pending = {"client": Unconfirmed(), "registration": Registration(), "url": BASE, "username": "u"}
    assert prober.confirm_2fa(BASE, "u", "p", CODE2) == {"status": "unconfirmed"}
    assert prober._pending["unconfirmed"] is True


def test_begin_counts_the_removable_old_entries(monkeypatch):
    from tests.test_client import SecuritySession

    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html", token_list="twofactor_list_uuid.html")
    session.posted_once = True
    client = IServClient(BASE, session=session)
    client.login = lambda username, password, provider: client
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=15: client)
    result = IServProber().begin_2fa(BASE, "u", "p", CODE)
    assert result == {"status": "awaiting_confirm", "stale_tokens": 1, "stale_removable": 1}


@pytest.mark.parametrize("code", ["login", "list"])
def test_nothing_is_deleted_without_a_session_or_a_list(monkeypatch, code):
    school = TokenSchool([None] if code == "list" else ["twofactor_list_uuid.html"])
    if code == "login":
        school.post = lambda url, data=None, **kwargs: Answer(load_fixture("login_refused_password.html"), url)
    result = prober_for(monkeypatch, school).remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE])
    assert result["left"] == [STALE]
    assert result["status"] != "ok"
    assert school.deleted == []


class UnreadableFirstClient:
    def __init__(self, lists):
        self.lists = list(lists)

    def login(self, username, password, provider):
        return self

    def start_totp_registration(self):
        return Registration()

    def read_token_list(self):
        rows = self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
        if rows is None:
            raise TwoFactorError("unreadable")
        return list(rows)

    def confirm_totp_registration(self, registration, name, code, at=None):
        raise TwoFactorError("unclear", message_key=REGISTRATION_UNCONFIRMED_KEY)


@pytest.mark.parametrize("later, expected", [
    ([{"name": "ISERV-Connector", "uuid": STALE}], "unconfirmed"),
    ([{"name": "Authenticator", "uuid": NEW}], "missing"),
])
def test_an_unreadable_list_at_the_start_never_turns_an_old_entry_into_the_new_one(monkeypatch, later, expected):
    client = UnreadableFirstClient([None, later])
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=15: client)
    prober = IServProber()
    assert prober.begin_2fa(BASE, "u", "p", CODE)["status"] == "awaiting_confirm"
    client.lists = [later]
    assert prober.confirm_2fa(BASE, "u", "p", CODE2) == {"status": "unconfirmed"}
    assert prober.check_registration(BASE, "u") == {"status": expected}


def test_removal_waits_out_a_rate_limit_and_respects_the_pause(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(STALE)})
    wizard.connect(CODE2)
    prober.stale_answer = {"status": "rate_limited", "retry_after": 120, "left": [STALE]}
    state = wizard.remove_stale_tokens()
    assert state["error"]["code"] == "paused"
    assert state["retry_in"] == 120
    assert state["stale_uuids"] == [STALE]
    state = wizard.remove_stale_tokens()
    assert state["error"]["code"] == "paused"
    assert len(prober.stale_calls) == 1


@pytest.mark.parametrize("refusal, code, attempts", [
    ("bad_credentials", "bad_credentials", 1),
    ("locked", "paused", 1),
    ("unknown_account", "unknown_account", 1),
])
def test_a_refused_sign_in_during_removal_counts_like_any_sign_in(tmp_path, refusal, code, attempts):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(STALE)})
    wizard.connect(CODE2)
    prober.stale_answer = {"status": refusal, "left": [STALE]}
    state = wizard.remove_stale_tokens()
    assert state["error"]["code"] == code
    assert state["attempts"] == attempts
    assert state["stale_uuids"] == [STALE]


def test_begin_reads_the_token_list_only_once(monkeypatch):
    from tests.test_client import SecuritySession

    session = SecuritySession("security_2fa_add.html", "security_2fa_added.html", token_list="twofactor_list_uuid.html")
    session.posted_once = True
    client = IServClient(BASE, session=session)
    client.login = lambda username, password, provider: client
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=15: client)
    IServProber().begin_2fa(BASE, "u", "p", CODE)
    assert session.requested.count(LIST_URL) == 1


class FakeTime:
    def __init__(self, now):
        self.now = now
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Registering:
    def confirm_totp_registration(self, registration, name, code, at=None):
        return registration.secret

    def read_token_list(self):
        return []


def test_removal_never_reuses_a_code_the_registration_or_an_earlier_step_used(monkeypatch):
    import time

    from app.iserv.totp import generate_code

    other = "c3c3c3c3-2222-4b2b-8d3d-abcdef654321"
    school = TokenSchool(["twofactor_list_uuid.html"])
    prober = prober_for(monkeypatch, school)
    clock = FakeTime(time.time())
    prober.clock = clock
    prober.sleeper = clock.sleep
    prober._pending = {"client": Registering(), "registration": Registration(), "url": BASE, "username": "u", "existing_uuids": set()}
    activation = generate_code(VALID_SECRET, at=clock.now)
    assert prober.confirm_2fa(BASE, "u", "p", CODE2)["status"] == "ok"
    prober.remove_stale_tokens(BASE, "u", "p", VALID_SECRET, [STALE, other])
    assert activation not in school.codes
    assert len(school.codes) == 2
    assert len(set(school.codes)) == len(school.codes)
    assert len(clock.slept) == 2


def test_two_removals_never_run_at_the_same_time(monkeypatch):
    import threading
    import time

    class SlowSchool(TokenSchool):
        def __init__(self):
            super().__init__(["twofactor_list_uuid.html"])
            self.inside = threading.Event()
            self.release = threading.Event()
            self.deleting = False
            self.overlap = False

        def get(self, url, timeout=None, params=None, **kwargs):
            self.overlap = self.overlap or self.deleting
            return super().get(url, timeout=timeout, params=params, **kwargs)

        def post(self, url, data=None, timeout=None, **kwargs):
            self.overlap = self.overlap or self.deleting
            return super().post(url, data=data, timeout=timeout, **kwargs)

        def request(self, method, url, data=None, timeout=None, **kwargs):
            self.deleting = True
            self.inside.set()
            self.release.wait(5)
            self.deleting = False
            return super().request(method, url, data=data, timeout=timeout, **kwargs)

    school = SlowSchool()
    prober = prober_for(monkeypatch, school)
    first = threading.Thread(target=prober.remove_stale_tokens, args=(BASE, "u", "p", VALID_SECRET, [STALE]))
    second = threading.Thread(target=prober.remove_stale_tokens, args=(BASE, "u", "p", VALID_SECRET, [STALE]))
    first.start()
    assert school.inside.wait(5)
    second.start()
    time.sleep(0.3)
    school.release.set()
    first.join(10)
    second.join(10)
    assert not school.overlap


def test_only_the_entry_this_connection_stored_is_removed_with_one_click(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(STALE, OTHER)})
    state = wizard.connect(CODE2)
    assert state["stale_uuids"] == [STALE]
    assert state["other_tokens"] == [{"uuid": OTHER, "name": "ISERV-Connector", "created": ""}]
    wizard.remove_stale_tokens()
    assert prober.stale_calls == [(VALID_SECRET, [STALE])]


def test_entries_this_connection_never_stored_are_only_listed(tmp_path):
    register = {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": [{"uuid": STALE, "created": "2026-09-01"}]}
    wizard, _, prober = connected(tmp_path, register, own=None)
    state = wizard.connect(CODE2)
    assert "stale_uuids" not in state
    assert state["other_tokens"] == [{"uuid": STALE, "name": "ISERV-Connector", "created": "2026-09-01"}]
    assert wizard.remove_stale_tokens()["error"]["code"] == "stale_not_pending"
    assert prober.stale_calls == []


def test_another_entry_is_removed_only_one_at_a_time_after_a_confirmation(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(OTHER, NEW)}, own=None)
    wizard.connect(CODE2)
    for uuid, confirmed in ((OTHER, None), (OTHER, "yes"), (NEW, True), (STALE, True), (123, True)):
        assert wizard.remove_other_token(uuid, confirmed)["error"]["code"] == "stale_not_pending"
    assert prober.stale_calls == []
    state = wizard.remove_other_token(OTHER, True)
    assert prober.stale_calls == [(VALID_SECRET, [OTHER])]
    assert "other_tokens" not in state
    assert state["stale_removed"] == 1
    assert "error" not in state


def test_a_failed_removal_of_another_entry_keeps_it_listed(tmp_path):
    wizard, _, prober = connected(tmp_path, {"status": "ok", "secret": VALID_SECRET, "old_tokens": old(OTHER)}, own=None)
    wizard.connect(CODE2)
    prober.stale_answer = {"status": "failed", "left": [OTHER]}
    state = wizard.remove_other_token(OTHER, True)
    assert [token["uuid"] for token in state["other_tokens"]] == [OTHER]
    assert state["error"]["message_key"] == "api.wizard.stale.failed"
    prober.stale_answer = {"status": "locked", "left": [OTHER]}
    assert wizard.remove_other_token(OTHER, True)["error"]["code"] == "paused"


def test_the_entry_of_this_connection_is_still_known_after_a_fresh_setup(tmp_path):
    wizard, store, prober, _ = make(tmp_path, register={"status": "ok", "secret": VALID_SECRET, "uuid": STALE})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    wizard.connect(CODE)
    wizard.connect(CODE2)
    connection_id = wizard.status()["connection_id"]
    assert store.load_secrets()["twofactor_uuid"] == STALE
    wizard.skip_child()
    wizard.reset(connection_id)
    assert "twofactor_uuid" not in store.load_secrets()
    prober.register = {"status": "ok", "secret": VALID_SECRET, "uuid": NEW, "old_tokens": old(STALE, OTHER)}
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state["stale_uuids"] == [STALE]
    assert [token["uuid"] for token in state["other_tokens"]] == [OTHER]
    assert store.load_secrets()["twofactor_uuid"] == NEW
    assert "previous_twofactor_uuid" not in store.load_secrets()


def test_another_account_forgets_the_entry_of_the_earlier_one(tmp_path):
    wizard, store, prober, _ = make(tmp_path, register={"status": "ok", "secret": VALID_SECRET, "uuid": STALE})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    wizard.connect(CODE)
    wizard.connect(CODE2)
    connection_id = wizard.status()["connection_id"]
    wizard.skip_child()
    wizard.reset(connection_id)
    wizard.set_url("myschool.example")
    wizard.set_login("someone.else", "secret")
    assert "previous_twofactor_uuid" not in store.load_secrets()


def test_the_prober_reports_old_entries_with_their_dates(monkeypatch):
    rows = [
        {"name": "ISERV-Connector", "uuid": STALE, "created": "2026-09-01"},
        {"name": "ISERV-Connector", "uuid": "", "created": ""},
        {"name": "Authenticator", "uuid": OTHER, "created": ""},
    ]
    client = UnreadableFirstClient([rows])
    monkeypatch.setattr("app.iserv_prober.IServClient", lambda url, timeout=15: client)
    prober = IServProber()
    assert prober.begin_2fa(BASE, "u", "p", CODE) == {"status": "awaiting_confirm", "stale_tokens": 2, "stale_removable": 1}
    assert prober._pending["old_tokens"] == [{"uuid": STALE, "created": "2026-09-01"}]
