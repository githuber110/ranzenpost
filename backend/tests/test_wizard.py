from app.store import Store
from app.wizard import Wizard

VALID_SECRET = "JBSWY3DPEHPK3PXP"
CODE = "123456"
CODE2 = "654321"


def complete_connect(wizard, first=None, second=None):
    wizard.connect(first or CODE)
    return wizard.connect(second or CODE2)


class Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        return self.value


class FakeProber:
    def __init__(self, url_ok=True, login="twofactor", register=None, begin=None):
        self.url_ok = url_ok
        self.login = login
        self.register = register or {"status": "ok", "secret": VALID_SECRET}
        self.begin = begin or {"status": "awaiting_confirm"}
        self.login_calls = 0
        self.register_calls = 0
        self.begin_calls = 0
        self.verify_calls = 0
        self.verify_totp_result = "ok"

    def probe_url(self, base):
        if self.url_ok:
            return {"ok": True, "host": base}
        return {"ok": False, "error": "url_unreachable", "message": "x"}

    def verify_login(self, url, username, password):
        self.login_calls += 1
        return self.login

    def verify_totp(self, url, username, password, secret):
        self.verify_calls += 1
        return self.verify_totp_result

    def begin_2fa(self, url, username, password, code, name="ISERV-Connector"):
        self.begin_calls += 1
        return self.begin

    def confirm_2fa(self, url, username, password, code, name="ISERV-Connector"):
        self.register_calls += 1
        return self.register

    def register_2fa(self, url, username, password, code, name="ISERV-Connector"):
        started = self.begin_2fa(url, username, password, code, name)
        if started.get("status") != "awaiting_confirm":
            return started
        return self.confirm_2fa(url, username, password, code, name)


def make(tmp_path, clock=None, **kwargs):
    store = Store(tmp_path / "data")
    prober = FakeProber(**kwargs)
    clock = clock or Clock()
    return Wizard(store, prober, now=clock), store, prober, clock


def test_happy_path_with_2fa(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    assert wizard.set_url("myschool.example")["step"] == "login"
    assert wizard.status()["school_url"] == "https://myschool.example"
    state = wizard.set_login("parent", "secret")
    assert state["step"] == "connect"
    assert state["has_2fa"] is True
    assert store.load_secrets()["username"] == "parent"
    first = wizard.connect(CODE)
    assert first.get("awaiting_confirm") is True
    assert first["step"] == "connect"
    state = wizard.connect(CODE2)
    assert state["step"] == "child"
    assert state["verified_2fa"] is True
    assert store.load_secrets()["totp_secret"] == VALID_SECRET


def test_no_2fa_account_skips_connect(tmp_path):
    wizard, store, prober, _ = make(tmp_path, login="no_2fa")
    wizard.set_url("myschool.example")
    state = wizard.set_login("parent", "secret")
    assert state["step"] == "child"
    assert state["has_2fa"] is False
    assert state["verified_2fa"] is True
    assert prober.register_calls == 0
    assert not store.load_secrets().get("totp_secret")


def test_connect_invalid_code_never_hits_network(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect("12ab")
    assert state["error"]["code"] == "code_invalid"
    assert prober.register_calls == 0


def test_connect_rejected_reports_code_error(tmp_path):
    wizard, _, _, _ = make(tmp_path, register={"status": "code_rejected"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state["error"]["code"] == "code_rejected"
    assert state["step"] == "connect"


def test_connect_rate_limit_pauses_after_three_failures(tmp_path):
    wizard, _, prober, _ = make(tmp_path, register={"status": "code_rejected"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(2):
        wizard.connect(CODE)
        wizard.connect(CODE2)
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state.get("paused_until") is not None
    calls = prober.register_calls
    wizard.connect(CODE)
    assert prober.register_calls == calls


def test_idempotent_connect_skips_when_verified(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    complete_connect(wizard)
    prober.register_calls = 0
    state = wizard.connect(CODE)
    assert state["step"] == "child"
    assert prober.register_calls == 0


def test_login_rate_limit_pauses(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="bad_credentials")
    wizard.set_url("myschool.example")
    wizard.set_login("p", "x")
    wizard.set_login("p", "x")
    state = wizard.set_login("p", "x")
    assert state.get("paused_until") is not None
    assert state["error"]["code"] == "paused"
    calls = prober.login_calls
    wizard.set_login("p", "x")
    assert prober.login_calls == calls


def test_login_rate_limit_also_pauses_on_locked(tmp_path):
    wizard, _, _, _ = make(tmp_path, login="locked")
    wizard.set_url("myschool.example")
    wizard.set_login("p", "x")
    wizard.set_login("p", "x")
    state = wizard.set_login("p", "x")
    assert state.get("paused_until") is not None


def test_pause_auto_releases_after_cooldown(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = make(tmp_path, clock=clock, login="bad_credentials")
    wizard.set_url("myschool.example")
    for _ in range(3):
        wizard.set_login("p", "x")
    paused_calls = prober.login_calls
    clock.value = 5000
    wizard.set_login("p", "x")
    assert prober.login_calls > paused_calls


def test_new_login_resets_verification(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    state = wizard.set_login("other", "s")
    assert state["verified_2fa"] is False
    assert not store.load_secrets().get("totp_secret")


def test_reset_clears_wizard_and_secrets(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    state = wizard.reset()
    assert state["step"] == "url"
    assert "school_url" not in state
    secrets = store.load_secrets()
    assert not secrets.get("username")
    assert not secrets.get("password")
    assert not secrets.get("totp_secret")


def test_connect_stores_the_captured_twofactor_uuid(tmp_path):
    wizard, store, _, _ = make(tmp_path, register={"status": "ok", "secret": VALID_SECRET, "uuid": "row-uuid-1"})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    assert store.load_secrets()["twofactor_uuid"] == "row-uuid-1"


def test_connect_without_a_captured_uuid_leaves_it_unset(tmp_path):
    wizard, store, _, _ = make(tmp_path, register={"status": "ok", "secret": VALID_SECRET})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    assert "twofactor_uuid" not in store.load_secrets()


def test_reset_also_clears_the_twofactor_uuid(tmp_path):
    wizard, store, _, _ = make(tmp_path, register={"status": "ok", "secret": VALID_SECRET, "uuid": "row-uuid-1"})
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    wizard.reset()
    assert "twofactor_uuid" not in store.load_secrets()


def test_back_from_connect_returns_to_login(tmp_path):
    wizard, _, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    state = wizard.back()
    assert state["step"] == "login"


def test_back_from_child_skips_connect_when_no_2fa(tmp_path):
    wizard, _, _, _ = make(tmp_path, login="no_2fa")
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    state = wizard.back()
    assert state["step"] == "login"


def test_select_child_persists_to_config(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    state = wizard.select_child("uuid-1", "Bella", "2b")
    assert state["step"] == "done"
    children = store.load_config()["children"]
    assert children == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]


def test_skip_child_finishes_setup_with_no_children(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    state = wizard.skip_child()
    assert state["step"] == "done"
    assert "selected_child" not in state
    assert store.load_config().get("children", []) == []


def test_url_invalid_reports_error(tmp_path):
    wizard, _, _, _ = make(tmp_path)
    assert wizard.set_url("notahost")["error"]["code"] == "url_invalid"


def test_connect_asks_for_a_second_code(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    first = wizard.connect(CODE)
    assert first["awaiting_confirm"] is True
    assert prober.begin_calls == 1
    assert prober.register_calls == 0
    same = wizard.connect(CODE)
    assert same["error"]["code"] == "same_code"
    assert prober.register_calls == 0
    done = wizard.connect(CODE2)
    assert done["step"] == "child"
    assert prober.register_calls == 1


def test_connect_reports_missing_registration_form(tmp_path):
    wizard, _, _, _ = make(tmp_path, begin={"status": "no_form"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect(CODE)
    assert state["error"]["code"] == "no_form"


def test_expired_pending_registration_restarts(tmp_path):
    wizard, _, prober, _ = make(tmp_path, register={"status": "expired"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state["error"]["code"] == "expired"
    assert not state.get("awaiting_confirm")


def test_back_clears_pending_registration(tmp_path):
    wizard, _, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    state = wizard.back()
    assert not state.get("awaiting_confirm")
    assert not state.get("last_code")


def test_rejected_registration_restarts_the_pairing(tmp_path):
    wizard, _, _, _ = make(tmp_path, register={"status": "code_rejected", "message": "Bitte geben Sie einen gültigen 2FA-Code ein."})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state["error"]["code"] == "code_rejected"
    assert "IServ meldet" in state["error"]["message"]
    assert not state.get("awaiting_confirm")


def test_restarting_the_pairing_does_not_reset_the_attempt_counter(tmp_path):
    wizard, _, _, _ = make(tmp_path, register={"status": "code_rejected"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    first = wizard.connect(CODE2)
    assert first["attempts"] == 1
    wizard.connect(CODE)
    second = wizard.connect(CODE2)
    assert second["attempts"] == 2


def test_existing_working_secret_is_reused_without_creating_a_new_token(tmp_path):
    wizard, store, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    prober.begin_calls = 0
    prober.register_calls = 0
    state = wizard.connect(CODE)
    assert state["step"] == "child"
    assert state["reused_secret"] is True
    assert prober.begin_calls == 0
    assert prober.register_calls == 0


def test_a_stored_secret_that_no_longer_works_leads_to_a_new_token(tmp_path):
    wizard, store, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    prober.verify_totp_result = "bad_code"
    prober.begin_calls = 0
    state = wizard.connect(CODE)
    assert prober.begin_calls == 1
    assert state.get("awaiting_confirm") is True


def test_stale_token_count_is_reported_to_the_user(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    prober.begin = {"status": "awaiting_confirm", "stale_tokens": 2}
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect(CODE)
    assert state["stale_tokens"] == 2
    done = wizard.connect(CODE2)
    assert done["step"] == "child"
    assert "stale_tokens" not in done


def test_a_created_token_is_kept_even_when_the_check_login_fails(tmp_path):
    wizard, store, _, _ = make(tmp_path, register={"status": "ok_unverified", "secret": VALID_SECRET, "reason": "login_refused"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    wizard.connect(CODE)
    state = wizard.connect(CODE2)
    assert state["step"] == "child"
    assert store.load_secrets()["totp_secret"] == VALID_SECRET
    assert state["unverified_reason"] == "login_refused"


def test_school_url_is_written_into_the_config_not_only_the_wizard_state(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    assert store.load_config()["school_url"] == "https://myschool.example"


def test_school_url_is_synced_on_every_save_not_just_the_url_step(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    config = store.load_config()
    config["school_url"] = ""
    store.save_config(config)
    wizard.set_login("parent", "s")
    assert store.load_config()["school_url"] == "https://myschool.example"
