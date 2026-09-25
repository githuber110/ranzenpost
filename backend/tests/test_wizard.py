import pytest

from app.store import Store
from app.wizard import ACCOUNT_KEY, SCHOOL_KEY, Wizard

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


class WizardStore:
    def __init__(self, store, wizard):
        self.base = store
        self.wizard = wizard

    def _id(self):
        return self.wizard.status().get("connection_id", "")

    def load_secrets(self):
        return self.base.load_secrets(self._id())

    def load_config(self):
        return self.base.connection_store(self._id()).load_config()

    def save_config(self, config):
        self.base.connection_store(self._id()).save_config(config)

    def edit_config(self, change):
        return self.base.connection_store(self._id()).edit_config(change)

    def __getattr__(self, name):
        return getattr(self.base, name)


def without_fingerprint(secrets):
    return {key: value for key, value in secrets.items() if key not in (ACCOUNT_KEY, SCHOOL_KEY)}


def offer(store, *child_ids):
    def change(flat):
        known = {child.get("child_id") for child in flat["children"]}
        flat["children"] = flat["children"] + [{"child_id": child_id} for child_id in child_ids if child_id not in known]

    store.edit_config(change)


def choose(wizard, store, child_id, name="", class_name=""):
    offer(store, child_id)
    return wizard.select_child(child_id, name, class_name)


def make(tmp_path, clock=None, **kwargs):
    store = Store(tmp_path / "data")
    prober = FakeProber(**kwargs)
    clock = clock or Clock()
    wizard = Wizard(store, prober, now=clock)
    return wizard, WizardStore(store, wizard), prober, clock


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
    assert "retry_in" in state
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
    assert "retry_in" in state
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
    assert "retry_in" in state


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
    connection_id = wizard.status()["connection_id"]
    state = wizard.reset()
    assert state["step"] == "url"
    assert "school_url" not in state
    assert "connection_id" not in state
    secrets = store.base.load_secrets(connection_id)
    assert not secrets.get("username")
    assert not secrets.get("password")
    assert not secrets.get("totp_secret")
    assert store.base.connection(connection_id) is None


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
    connection_id = wizard.status()["connection_id"]
    wizard.reset()
    assert "twofactor_uuid" not in store.base.load_secrets(connection_id)


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
    state = choose(wizard, store, "uuid-1", "Bella", "2b")
    assert state["step"] == "done"
    children = store.load_config()["children"]
    assert children == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]
    assert store.load_config()["setup_complete"] is True


def test_a_child_the_school_did_not_offer_is_not_stored(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    offer(store, "uuid-1")
    state = wizard.select_child("uuid-foreign", "Mallory", "9z")
    assert state["error"]["code"] == "child_unknown"
    assert state["step"] == "child"
    assert [child["child_id"] for child in store.load_config()["children"]] == ["uuid-1"]


def test_going_back_from_the_phones_step_can_pick_another_offered_child(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    offer(store, "uuid-1", "uuid-2")
    wizard.select_child("uuid-1", "Bella", "2b")
    state = wizard.select_child("uuid-2", "Tom", "4c")
    assert state["step"] == "done"
    assert "error" not in state
    assert state["selected_child"] == "uuid-2"


def test_a_child_the_school_did_not_offer_is_refused_after_the_setup_too(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    choose(wizard, store, "uuid-1", "Bella", "2b")
    state = wizard.select_child("uuid-foreign", "Mallory", "9z")
    assert state["error"]["code"] == "child_unknown"
    assert [child["child_id"] for child in store.load_config()["children"]] == ["uuid-1"]


@pytest.mark.parametrize("sent", [" uuid-1 ", "uuid-1	"])
def test_a_padded_child_id_is_stored_as_the_school_listed_it(tmp_path, sent):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    offer(store, "uuid-1")
    wizard.select_child(sent, "Bella", "2b")
    assert [child["child_id"] for child in store.load_config()["children"]] == ["uuid-1"]


@pytest.mark.parametrize("step", ["url", "login"])
def test_a_child_is_refused_before_the_child_step(tmp_path, step):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    if step == "login":
        wizard.set_login("parent", "s")
        wizard.back()
    offer(store, "uuid-1")
    state = wizard.select_child("uuid-1", "Bella", "2b")
    assert state["error"]["code"] == "child_unknown"


def test_skip_child_finishes_setup_with_no_children(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    state = wizard.skip_child()
    assert state["step"] == "done"
    assert "selected_child" not in state
    assert store.load_config().get("children", []) == []
    assert store.load_config()["setup_complete"] is True


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


def test_a_stored_secret_check_without_a_session_still_leads_to_a_new_token(tmp_path):
    wizard, store, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    prober.verify_totp_result = "unknown"
    prober.begin_calls = 0
    state = wizard.connect(CODE)
    assert prober.begin_calls == 1
    assert state.get("awaiting_confirm") is True
    assert "error" not in state


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
    state = wizard.set_url("myschool.example")
    assert len(state["connection_id"]) == 8
    assert store.load_config()["school_url"] == "https://myschool.example"
    assert store.load_config()["setup_complete"] is False
    assert [entry["id"] for entry in store.base.connections()] == [state["connection_id"]]


def test_the_first_setup_is_not_marked_as_an_addition(tmp_path):
    wizard, _, _, _ = make(tmp_path)
    assert wizard.status()["additional"] is False
    assert wizard.set_url("myschool.example")["additional"] is False


def test_adding_another_school_runs_the_wizard_for_a_second_connection(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    choose(wizard, store, "uuid-1", "Bella", "2b")
    first = wizard.status()["connection_id"]

    started = wizard.start_new()
    assert started["step"] == "url"
    assert "connection_id" not in started
    assert started["additional"] is True
    second_state = wizard.set_url("school-two.example")
    second = second_state["connection_id"]
    assert second != first
    assert second_state["additional"] is True
    wizard.set_login("other", "s")
    complete_connect(wizard)
    choose(wizard, store, "uuid-9", "Bella", "1a")

    entries = store.base.connections()
    assert [entry["id"] for entry in entries] == [first, second]
    assert entries[0]["school_url"] == "https://school-one.example"
    assert entries[1]["school_url"] == "https://school-two.example"
    assert entries[1]["setup_complete"] is True
    assert store.base.load_secrets(first)["username"] == "parent"
    assert store.base.load_secrets(second)["username"] == "other"
    assert entries[0]["children"] == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]
    assert entries[1]["children"] == [{"child_id": "uuid-9", "name": "Bella", "class_name": "1a"}]


def test_the_same_school_url_may_be_connected_twice(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    wizard.skip_child()
    wizard.start_new()
    wizard.set_url("school-one.example")
    wizard.set_login("other-parent", "s")
    complete_connect(wizard)
    wizard.skip_child()
    entries = store.base.connections()
    assert len(entries) == 2
    assert {entry["school_url"] for entry in entries} == {"https://school-one.example"}


def test_cancelling_an_addition_removes_the_half_connection(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    wizard.skip_child()
    first = wizard.status()["connection_id"]
    wizard.start_new()
    second = wizard.set_url("school-two.example")["connection_id"]
    wizard.set_login("other", "s")

    state = wizard.cancel()

    assert state["step"] == "done"
    assert [entry["id"] for entry in store.base.connections()] == [first]
    assert store.base.load_secrets(second) == {}
    assert not store.base.secrets_path_for(second).exists()


def test_starting_again_resumes_a_pending_addition(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    wizard.skip_child()
    wizard.start_new()
    second = wizard.set_url("school-two.example")["connection_id"]
    wizard.set_login("other", "s")

    resumed = wizard.start_new()

    assert resumed["connection_id"] == second
    assert resumed["step"] == "connect"
    assert len(store.base.connections()) == 2


def test_cancelling_the_very_first_setup_starts_from_the_url_again(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    state = wizard.cancel()
    assert state["step"] == "url"
    assert store.base.connections() == []


def test_a_reset_of_a_finished_connection_keeps_its_settings_and_forgets_the_login(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    choose(wizard, store, "uuid-1", "Bella", "2b")
    connection_id = wizard.status()["connection_id"]
    store.base.update_connection(connection_id, holiday_region="DE-NI")

    state = wizard.reset(connection_id)

    assert state["step"] == "url"
    assert state["connection_id"] == connection_id
    entry = store.base.connection(connection_id)
    assert entry["setup_complete"] is False
    assert entry["holiday_region"] == "DE-NI"
    assert entry["children"] == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]
    assert without_fingerprint(store.base.load_secrets(connection_id)) == {}
    wizard.set_url("school-one.example")
    assert wizard.status()["connection_id"] == connection_id
    assert len(store.base.connections()) == 1


def test_school_url_is_synced_on_every_save_not_just_the_url_step(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    config = store.load_config()
    config["school_url"] = ""
    store.save_config(config)
    wizard.set_login("parent", "s")
    assert store.load_config()["school_url"] == "https://myschool.example"


def finished_connection(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    choose(wizard, store, "uuid-1", "Bella", "2b")
    connection_id = wizard.status()["connection_id"]
    store.base.save_calendar_subscriptions({"subscriptions": [{"child_key": f"{connection_id}:uuid-1", "token": "t"}]})
    store.base.save_marks({"marks": [{"id": "m1", "child_key": f"{connection_id}:uuid-1"}]})
    store.base.save_seen({connection_id: {"letters": ["l1"]}})
    store.base.connection_store(connection_id).save_integration_state({"last_poll": 5})
    return wizard, store, connection_id


def test_restarting_the_wizard_after_a_reconnect_keeps_the_connection_and_its_data(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    wizard.reset(connection_id)

    state = wizard.reset()

    assert state["step"] == "url"
    assert state["connection_id"] == connection_id
    entry = store.base.connection(connection_id)
    assert entry is not None
    assert entry["setup_complete"] is False
    assert entry["children"] == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]
    assert store.base.load_calendar_subscriptions()["subscriptions"][0]["child_key"] == f"{connection_id}:uuid-1"
    assert store.base.load_marks()["marks"][0]["id"] == "m1"
    assert store.base.load_seen() == {connection_id: {"letters": ["l1"]}}
    assert store.base.connection_store(connection_id).load_integration_state() == {"last_poll": 5}
    assert without_fingerprint(store.base.load_secrets(connection_id)) == {}
    assert len(store.base.connections()) == 1


def test_cancelling_the_wizard_after_a_reconnect_keeps_the_connection(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    wizard.reset(connection_id)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")

    state = wizard.cancel()

    assert state["step"] == "url"
    entry = store.base.connection(connection_id)
    assert entry is not None
    assert entry["setup_complete"] is False
    assert entry["children"] == [{"child_id": "uuid-1", "name": "Bella", "class_name": "2b"}]
    assert store.base.load_marks()["marks"][0]["id"] == "m1"
    assert without_fingerprint(store.base.load_secrets(connection_id)) == {}


def test_a_connection_the_wizard_created_itself_is_still_removed_on_restart(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("school-one.example")
    state = wizard.set_login("parent", "s")
    connection_id = state["connection_id"]
    assert state["created_connection"] is True

    wizard.reset()

    assert store.base.connection(connection_id) is None
    assert wizard.status().get("connection_id") is None


def test_cancelling_after_a_finished_setup_leaves_the_login_untouched(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)

    state = wizard.cancel()

    assert state["step"] == "done"
    assert store.base.connection(connection_id)["setup_complete"] is True
    assert store.base.load_secrets(connection_id)["username"] == "parent"


def test_an_iserv_outage_during_setup_is_named_and_burns_no_attempt(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="outage")
    wizard.set_url("myschool.example")
    wizard.set_login("p", "x")
    wizard.set_login("p", "x")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "outage"
    assert state["error"]["message_key"] == "api.wizard.outage"
    assert "retry_in" not in state
    assert not state.get("attempts")
    assert prober.login_calls == 3


def pause_with_bad_password(tmp_path, clock):
    wizard, store, prober, _ = make(tmp_path, clock=clock, login="bad_credentials")
    wizard.set_url("myschool.example")
    for _ in range(3):
        state = wizard.set_login("p", "x")
    return wizard, store, prober, state


def test_an_expired_pause_leaves_no_paused_error_behind(tmp_path):
    clock = Clock(1000)
    wizard, _, _, state = pause_with_bad_password(tmp_path, clock)
    assert state["error"]["code"] == "paused"
    clock.value = 1000 + 31
    state = wizard.status()
    assert "error" not in state
    assert "retry_in" not in state
    assert state["attempts"] == 3
    assert state["step"] == "login"


def test_a_pause_reports_the_seconds_left_and_the_reason(tmp_path):
    clock = Clock(1000)
    wizard, _, _, state = pause_with_bad_password(tmp_path, clock)
    assert state["retry_in"] == 30
    assert state["error"]["message_key"] == "api.wizard.pausedCredentials"
    clock.value = 1000 + 17.5
    assert wizard.status()["retry_in"] == 13
    clock.value = 1000 + 31
    assert "retry_in" not in wizard.status()


def test_the_wait_grows_gently_with_each_further_failure_and_stays_short(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, state = pause_with_bad_password(tmp_path, clock)
    waits = [state["retry_in"]]
    for _ in range(5):
        clock.value += waits[-1] + 1
        waits.append(wizard.set_login("p", "x")["retry_in"])
    assert waits == [30, 60, 120, 240, 300, 300]
    assert prober.login_calls == 8


def test_the_first_two_failures_never_wait(tmp_path):
    wizard, _, _, _ = make(tmp_path, login="bad_credentials")
    wizard.set_url("myschool.example")
    for _ in range(2):
        state = wizard.set_login("p", "x")
        assert state["error"]["code"] == "bad_credentials"
        assert "retry_in" not in state


def test_a_school_lock_pauses_at_once_and_releases_after_the_cooldown(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = make(tmp_path, clock=clock, login="locked")
    wizard.set_url("myschool.example")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "paused"
    assert state["error"]["message_key"] == "api.wizard.pausedLocked"
    assert state["retry_in"] == 300
    wizard.set_login("p", "x")
    assert prober.login_calls == 1
    clock.value = 1000 + 301
    assert "error" not in wizard.status()


def test_network_trouble_during_the_code_step_burns_no_attempt(tmp_path):
    wizard, _, _, _ = make(tmp_path, begin={"status": "network"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(4):
        state = wizard.connect(CODE)
    assert state["error"]["code"] == "network"
    assert "retry_in" not in state
    assert not state.get("attempts")


def test_a_missing_code_form_burns_no_attempt(tmp_path):
    wizard, _, _, _ = make(tmp_path, begin={"status": "no_form"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(4):
        state = wizard.connect(CODE)
    assert state["error"]["code"] == "no_form"
    assert "retry_in" not in state


def test_a_wrong_code_names_the_code_as_the_reason_for_the_pause(tmp_path):
    wizard, _, _, _ = make(tmp_path, begin={"status": "bad_code"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    for _ in range(3):
        state = wizard.connect(CODE)
    assert state["error"]["message_key"] == "api.wizard.pausedCode"


def test_starting_over_during_a_pause_keeps_the_pause_for_the_same_school(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = pause_with_bad_password(tmp_path, clock)
    for leave in (wizard.reset, wizard.start_new, wizard.cancel):
        leave()
        wizard.set_url("myschool.example")
        state = wizard.set_login("p", "x")
        assert state["error"]["code"] == "paused"
    assert prober.login_calls == 3


def test_starting_over_with_another_school_is_not_held_by_the_pause(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = pause_with_bad_password(tmp_path, clock)
    wizard.reset()
    wizard.set_url("otherschool.example")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "bad_credentials"
    assert prober.login_calls == 4


def test_going_back_during_a_pause_keeps_the_pause(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = pause_with_bad_password(tmp_path, clock)
    state = wizard.back()
    assert state["retry_in"] == 30
    wizard.set_url("myschool.example")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "paused"
    assert prober.login_calls == 3


def test_a_stale_blocking_error_from_an_older_version_is_healed(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    for code in ("paused", "locked"):
        state = store.base.load_wizard()
        state["error"] = {"code": code, "message_key": "api.wizard.paused"}
        state.pop("paused_until", None)
        store.base.save_wizard(state)
        state = wizard.status()
        assert "error" not in state
        assert state["step"] == "login"


def test_a_mistyped_url_does_not_lift_the_pause(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = pause_with_bad_password(tmp_path, clock)
    wizard.back()
    prober.url_ok = False
    wizard.set_url("typo.example")
    prober.url_ok = True
    wizard.set_url("myschool.example")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "paused"
    assert prober.login_calls == 3


def test_a_detour_through_another_school_does_not_lift_the_pause(tmp_path):
    clock = Clock(1000)
    wizard, _, prober, _ = pause_with_bad_password(tmp_path, clock)
    wizard.back()
    wizard.set_url("otherschool.example")
    wizard.back()
    wizard.set_url("myschool.example")
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "paused"
    assert prober.login_calls == 3


def test_changing_the_url_does_not_reset_the_attempt_counter(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="bad_credentials")
    wizard.set_url("myschool.example")
    for _ in range(10):
        wizard.set_login("p", "x")
        wizard.set_login("p", "x")
        wizard.back()
        prober.url_ok = False
        wizard.set_url("typo.example")
        prober.url_ok = True
        wizard.set_url("myschool.example")
    assert prober.login_calls == 3


def test_failed_attempts_are_forgotten_after_a_quiet_cooldown(tmp_path):
    clock = Clock(1000)
    wizard, _, _, _ = make(tmp_path, clock=clock, login="bad_credentials")
    wizard.set_url("myschool.example")
    wizard.set_login("p", "x")
    state = wizard.set_login("p", "x")
    assert state["attempts"] == 2
    clock.value = 1000 + 601
    assert wizard.status()["attempts"] == 0
    state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "bad_credentials"


def test_a_successful_login_clears_the_attempts_of_that_school_only(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="bad_credentials")
    wizard.set_url("otherschool.example")
    wizard.set_login("p", "x")
    wizard.back()
    wizard.set_url("myschool.example")
    prober.login = "twofactor"
    state = wizard.set_login("p", "s")
    assert state["attempts"] == 0
    assert list(state["pauses"]) == ["https://otherschool.example"]


def test_an_expired_password_is_named_and_burns_no_attempt(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="password_expired")
    wizard.set_url("myschool.example")
    for _ in range(4):
        state = wizard.set_login("p", "x")
    assert state["error"]["code"] == "password_expired"
    assert state["error"]["message_key"] == "api.lockout.passwordExpired"
    assert "retry_in" not in state
    assert prober.login_calls == 4


def test_a_captcha_is_named_and_pauses_like_a_lock(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="captcha")
    wizard.set_url("myschool.example")
    for _ in range(4):
        state = wizard.set_login("p", "x")
    assert state["error"]["message_key"] == "api.lockout.captcha"
    assert state["retry_in"] == 300
    assert prober.login_calls == 1


def test_an_active_pause_from_an_older_version_is_kept(tmp_path):
    clock = Clock(1000)
    wizard, store, prober, _ = make(tmp_path, clock=clock, login="bad_credentials")
    wizard.set_url("myschool.example")
    state = store.base.load_wizard()
    state.update(attempts=3, paused_until=1300, error={"code": "paused", "message_key": "api.wizard.paused"})
    store.base.save_wizard(state)
    state = wizard.status()
    assert state["retry_in"] == 300
    assert "paused_until" not in state
    wizard.set_login("p", "x")
    assert prober.login_calls == 0
    clock.value = 1301
    assert "error" not in wizard.status()


def test_a_default_password_is_named_and_burns_no_attempt(tmp_path):
    wizard, _, prober, _ = make(tmp_path, login="default_password_blocked")
    wizard.set_url("myschool.example")
    for _ in range(5):
        state = wizard.set_login("p", "x")
    assert state["step"] == "login"
    assert state["error"]["code"] == "default_password_blocked"
    assert state["error"]["message_key"] == "api.lockout.defaultPassword"
    assert state["attempts"] == 0
    assert "retry_in" not in state
    assert prober.login_calls == 1


def test_an_unknown_account_is_named_and_counts_like_a_wrong_password(tmp_path):
    wizard, _, _, _ = make(tmp_path, login="unknown_account")
    wizard.set_url("myschool.example")
    state = wizard.set_login("nobody", "x")
    assert state["error"]["code"] == "unknown_account"
    assert state["error"]["message_key"] == "api.lockout.unknownAccount"
    assert state["attempts"] == 1
    wizard.set_login("nobody", "x")
    state = wizard.set_login("nobody", "x")
    assert state["error"]["code"] == "paused"
    assert state["error"]["message_key"] == "api.wizard.pausedCredentials"
    assert state["retry_in"] == 30


def test_a_forced_two_factor_setup_leads_to_the_connect_step_without_an_error(tmp_path):
    wizard, store, _, _ = make(tmp_path, login="twofactor_required_setup")
    wizard.set_url("myschool.example")
    state = wizard.set_login("parent", "secret")
    assert state["step"] == "connect"
    assert state["has_2fa"] is True
    assert state["needs_2fa_setup"] is True
    assert state["verified_2fa"] is False
    assert "error" not in state
    assert state["attempts"] == 0
    assert store.load_secrets()["password"] == "secret"


def test_a_code_while_iserv_still_waits_for_the_setup_is_explained_and_burns_no_attempt(tmp_path):
    wizard, _, prober, _ = make(
        tmp_path, login="twofactor_required_setup", begin={"status": "twofactor_required_setup"}
    )
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    for _ in range(4):
        state = wizard.connect(CODE)
    assert state["step"] == "connect"
    assert state["needs_2fa_setup"] is True
    assert state["error"]["code"] == "twofactor_required_setup"
    assert state["error"]["message_key"] == "api.wizard.twofactorSetupPending"
    assert state["attempts"] == 0
    assert prober.begin_calls == 4


def test_after_the_setup_in_the_browser_the_normal_connect_finishes(tmp_path):
    wizard, store, prober, _ = make(tmp_path, login="twofactor_required_setup")
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    state = complete_connect(wizard)
    assert state["step"] == "child"
    assert state["verified_2fa"] is True
    assert store.load_secrets()["totp_secret"] == VALID_SECRET
    wizard.back()
    wizard.back()
    prober.login = "twofactor"
    state = wizard.set_login("parent", "secret")
    assert state["needs_2fa_setup"] is False


def test_the_same_blocked_default_password_is_not_sent_to_iserv_twice(tmp_path):
    wizard, store, prober, _ = make(tmp_path, login="default_password_blocked")
    wizard.set_url("myschool.example")
    first = wizard.set_login("parent", "start123")
    second = wizard.set_login(" parent ", "start123")
    assert first["error"]["code"] == second["error"]["code"] == "default_password_blocked"
    assert prober.login_calls == 1
    wizard.set_login("parent", "changed-password")
    assert prober.login_calls == 2


def test_the_refused_default_password_is_forgotten_after_a_day_and_on_reset(tmp_path):
    clock = Clock()
    wizard, store, prober, _ = make(tmp_path, clock=clock, login="default_password_blocked")
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "start123")
    wizard.set_login("parent", "start123")
    assert prober.login_calls == 1
    remembered = store.load_secrets()["refused_login"]
    assert "start123" not in str(remembered)
    assert set(remembered) == {"salt", "login", "until"}
    clock.value += 24 * 60 * 60 + 1
    wizard.set_login("parent", "start123")
    assert prober.login_calls == 2
    connection_id = wizard.status()["connection_id"]
    wizard.reset(connection_id)
    assert "refused_login" not in store.base.load_secrets(connection_id)


def test_a_refusal_from_the_stored_secret_check_stops_before_a_new_token(tmp_path):
    for status, code, key in (
        ("locked", "paused", "api.wizard.pausedLocked"),
        ("unknown_account", "unknown_account", "api.lockout.unknownAccount"),
        ("default_password_blocked", "default_password_blocked", "api.lockout.defaultPassword"),
    ):
        wizard, _, prober, _ = make(tmp_path / status)
        wizard.set_url("myschool.example")
        wizard.set_login("parent", "s")
        complete_connect(wizard)
        prober.verify_totp_result = status
        prober.begin_calls = 0
        prober.register_calls = 0
        state = wizard.connect(CODE)
        assert prober.begin_calls == 0, status
        assert prober.register_calls == 0, status
        assert state["error"]["code"] == code
        assert state["error"]["message_key"] == key


def test_signing_in_again_in_the_setup_clears_a_session_hold(tmp_path):
    wizard, store, _, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    connection_id = wizard.status()["connection_id"]
    held = dict(store.load_secrets(), login_hold={"reason": "session_not_opened", "until": 9e9, "wait": 300})
    store.base.save_secrets(connection_id, held)
    wizard.set_login("parent", "s")
    assert "login_hold" not in store.load_secrets()


def test_a_password_repaired_while_the_setup_registers_a_token_is_never_undone(tmp_path):
    wizard, store, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    connection_id = wizard.status()["connection_id"]
    wizard.connect(CODE)
    original = prober.confirm_2fa

    def confirm_while_a_repair_lands(*args, **kwargs):
        store.base.save_secrets(connection_id, dict(store.load_secrets(), password="repaired"))
        return original(*args, **kwargs)

    prober.confirm_2fa = confirm_while_a_repair_lands
    state = wizard.connect(CODE2)
    assert state["step"] == "child"
    saved = store.load_secrets()
    assert saved["password"] == "repaired"
    assert saved["totp_secret"] == VALID_SECRET


def test_a_refused_stored_password_stops_the_setup_before_a_new_token(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "s")
    complete_connect(wizard)
    prober.verify_totp_result = "bad_credentials"
    prober.begin_calls = 0
    state = wizard.connect(CODE)
    assert prober.begin_calls == 0
    assert state["error"]["code"] == "bad_credentials"
    assert state["error"]["message_key"] == "api.wizard.connectBadCredentials"


def another_secret_write_lands_during_the_first_save(store, connection_id, action):
    import threading

    from tests.test_login_reasons_running import AnnouncingLock

    base = store.base
    armed = threading.Event()
    blocked_or_done = threading.Event()

    def write():
        try:
            base.connection_store(connection_id).edit_secrets(
                lambda secrets: secrets.__setitem__("messenger_user_id", "@parent:school.example")
            )
        finally:
            blocked_or_done.set()

    worker = threading.Thread(target=write)
    base.lock = AnnouncingLock(base.lock, lambda: threading.current_thread() is worker, blocked_or_done)
    original = base.save_secrets

    def save_while_another_write_lands(wanted, secrets):
        if armed.is_set() and threading.current_thread() is not worker:
            armed.clear()
            worker.start()
            assert blocked_or_done.wait(timeout=30)
        original(wanted, secrets)

    base.save_secrets = save_while_another_write_lands
    armed.set()
    action()
    worker.join(timeout=30)
    assert not worker.is_alive()
    return base.load_secrets(connection_id)


def test_new_credentials_from_the_setup_never_undo_a_secret_written_meanwhile(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    wizard.reset(connection_id)
    wizard.set_url("school-one.example")
    saved = another_secret_write_lands_during_the_first_save(
        store, connection_id, lambda: wizard.set_login("parent", "new-secret")
    )
    assert saved["messenger_user_id"] == "@parent:school.example"
    assert saved["password"] == "new-secret"


def test_a_remembered_refused_default_password_never_undoes_a_secret_written_meanwhile(tmp_path):
    wizard, store, prober, _ = make(tmp_path, login="default_password_blocked")
    wizard.set_url("myschool.example")
    connection_id = wizard.status()["connection_id"]
    saved = another_secret_write_lands_during_the_first_save(
        store, connection_id, lambda: wizard.set_login("parent", "start123")
    )
    assert saved["messenger_user_id"] == "@parent:school.example"
    assert "refused_login" in saved


def test_forgetting_the_login_on_a_reset_never_undoes_a_secret_written_meanwhile(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    saved = another_secret_write_lands_during_the_first_save(store, connection_id, lambda: wizard.reset(connection_id))
    assert saved["messenger_user_id"] == "@parent:school.example"
    assert "password" not in saved


def test_a_crash_while_switching_the_account_never_leaves_the_old_children_with_the_new_login(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    wizard.reset(connection_id)
    wizard.set_url("school-one.example")
    base = store.base
    original = base.update_connection

    def crash_on_children(wanted, **fields):
        if "children" in fields:
            raise RuntimeError("stopped")
        return original(wanted, **fields)

    base.update_connection = crash_on_children
    with pytest.raises(RuntimeError):
        wizard.set_login("other.parent", "s")
    base.update_connection = original
    kept = base.connection(connection_id)["children"]
    assert not (base.load_secrets(connection_id).get("username") == "other.parent" and kept)


def test_a_setup_start_that_opened_no_session_asks_for_a_fresh_code_and_stays_on_the_code_step(tmp_path):
    wizard, _, prober, _ = make(tmp_path, begin={"status": "unknown"})
    wizard.set_url("myschool.example")
    wizard.set_login("p", "s")
    state = wizard.connect(CODE)
    assert (state["step"], state["error"]["code"]) == ("connect", "verify_failed")
    assert not state.get("awaiting_confirm")
    prober.begin = {"status": "awaiting_confirm"}
    assert wizard.connect(CODE2).get("awaiting_confirm") is True
    assert prober.begin_calls == 2


def test_signing_in_with_another_account_forgets_the_timetable_source(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    store.base.update_connection(connection_id, timetable_source="time-table")
    wizard.reset(connection_id)
    wizard.set_url("school-one.example")
    wizard.set_login("other.parent", "s")
    assert store.base.connection(connection_id)["timetable_source"] == ""


def test_signing_in_again_with_the_same_account_keeps_the_timetable_source(tmp_path):
    wizard, store, connection_id = finished_connection(tmp_path)
    store.base.update_connection(connection_id, timetable_source="time-table")
    wizard.reset(connection_id)
    wizard.set_url("school-one.example")
    wizard.set_login("parent", "s")
    assert store.base.connection(connection_id)["timetable_source"] == "time-table"
