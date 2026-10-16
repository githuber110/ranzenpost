from tests.test_wizard import CODE, CODE2, SETUP_SECRET, VALID_SECRET, complete_connect, make

SETUP_CODE = "135790"


def forced(tmp_path, **kwargs):
    wizard, store, prober, clock = make(tmp_path, login="twofactor_required_setup", **kwargs)
    wizard.set_url("myschool.example")
    state = wizard.set_login("parent", "secret")
    return wizard, store, prober, state


def stored_text(tmp_path):
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in tmp_path.rglob("*") if path.is_file())


def test_a_forced_setup_starts_in_the_app_without_an_error(tmp_path):
    _, _, prober, state = forced(tmp_path)
    assert state["step"] == "connect"
    assert state["needs_2fa_setup"] is True
    assert state["twofactor_setup"] == "start"
    assert "setup_key" not in state
    assert "error" not in state
    assert prober.setup_calls == 0


def test_starting_the_setup_shows_the_key_but_never_stores_it(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    state = wizard.start_setup()
    assert state["twofactor_setup"] == "code"
    assert state["setup_key"]["secret"] == SETUP_SECRET
    assert state["setup_key"]["uri"].startswith("otpauth://")
    assert wizard.status()["setup_key"]["secret"] == SETUP_SECRET
    assert SETUP_SECRET not in stored_text(tmp_path)


def test_a_wrong_code_is_named_in_the_app_and_keeps_the_key(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "rejected", "key_changed": False}]
    state = wizard.confirm_setup("000000")
    assert state["error"]["code"] == "setup_rejected"
    assert state["error"]["message_key"] == "api.wizard.setup.rejected"
    assert state["twofactor_setup"] == "code"
    assert state["setup_key"]["secret"] == SETUP_SECRET
    assert state["attempts"] == 0
    assert prober.setup_codes == ["000000"]


def test_a_new_key_after_a_wrong_code_is_named(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "rejected", "key_changed": True}]
    assert wizard.confirm_setup("000000")["error"]["message_key"] == "api.wizard.setup.rejectedNewKey"


def test_a_successful_setup_continues_with_the_usual_connect(tmp_path):
    wizard, store, prober, _ = forced(tmp_path)
    wizard.start_setup()
    state = wizard.confirm_setup(SETUP_CODE)
    assert state["step"] == "connect"
    assert state["needs_2fa_setup"] is False
    assert state["twofactor_setup"] == "done"
    assert "setup_key" not in state
    assert "error" not in state
    state = complete_connect(wizard)
    assert state["step"] == "child"
    assert store.load_secrets()["totp_secret"] == VALID_SECRET
    assert SETUP_SECRET not in stored_text(tmp_path)


def test_an_unclear_answer_is_uncertain_and_is_checked_by_signing_in(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "uncertain"}]
    state = wizard.confirm_setup(SETUP_CODE)
    assert state["twofactor_setup"] == "uncertain"
    assert state["error"]["message_key"] == "api.wizard.setup.uncertain"
    assert "setup_key" not in state
    assert len(prober.setup_codes) == 1
    calls = prober.login_calls
    prober.login = "twofactor"
    state = wizard.check_setup()
    assert prober.login_calls == calls + 1
    assert state["needs_2fa_setup"] is False
    assert state["twofactor_setup"] == "done"
    assert "error" not in state


def test_a_check_that_still_finds_the_setup_starts_over(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "uncertain"}]
    wizard.confirm_setup(SETUP_CODE)
    state = wizard.check_setup()
    assert state["twofactor_setup"] == "start"
    assert state["needs_2fa_setup"] is True
    assert state["error"]["message_key"] == "api.wizard.setup.notActive"


def test_the_setup_never_sends_a_code_on_its_own(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "uncertain"}]
    wizard.confirm_setup(SETUP_CODE)
    assert wizard.confirm_setup(SETUP_CODE)["error"]["code"] == "setup_not_pending"
    assert prober.setup_codes == [SETUP_CODE]


def test_a_lost_setup_after_a_restart_asks_to_start_again(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_open = False
    state = wizard.status()
    assert state["twofactor_setup"] == "start"
    assert "setup_key" not in state
    prober.setup_results = [{"status": "expired"}]
    wizard.store.save_wizard(dict(wizard.store.load_wizard(), twofactor_setup="code"))
    state = wizard.confirm_setup(SETUP_CODE)
    assert state["error"]["message_key"] == "api.wizard.setup.expired"
    assert state["twofactor_setup"] == "start"


def test_a_school_that_no_longer_forces_the_setup_goes_on(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    prober.setup_begin = {"status": "twofactor"}
    state = wizard.start_setup()
    assert state["needs_2fa_setup"] is False and state["twofactor_setup"] == "done"
    wizard2, _, prober2, _ = forced(tmp_path / "two")
    prober2.setup_begin = {"status": "no_2fa"}
    state = wizard2.start_setup()
    assert state["step"] == "child"
    assert state["has_2fa"] is False


def test_an_unknown_setup_page_is_named(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    prober.setup_begin = {"status": "no_form"}
    state = wizard.start_setup()
    assert state["error"]["message_key"] == "api.wizard.setup.noForm"
    assert state["twofactor_setup"] == "start"
    assert state["attempts"] == 0


def test_a_refused_password_during_the_setup_counts_like_the_connect(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    prober.setup_begin = {"status": "bad_credentials"}
    state = wizard.start_setup()
    assert state["error"]["message_key"] == "api.wizard.connectBadCredentials"
    assert state["attempts"] == 1


def test_an_outage_during_the_setup_waits(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    prober.setup_begin = {"status": "rate_limited", "retry_after": 30}
    state = wizard.start_setup()
    assert state["error"]["code"] == "paused"
    assert state["retry_in"] == 30


def test_a_code_in_the_connect_step_during_the_setup_points_to_the_start(tmp_path):
    wizard, _, prober, _ = forced(tmp_path, begin={"status": "twofactor_required_setup"})
    state = wizard.connect(CODE)
    assert state["twofactor_setup"] == "start"
    assert state["error"]["message_key"] == "api.wizard.twofactorSetupPending"


def test_the_setup_calls_need_the_forced_state(tmp_path):
    wizard, _, prober, _ = make(tmp_path)
    wizard.set_url("myschool.example")
    wizard.set_login("parent", "secret")
    for call in (wizard.start_setup, lambda: wizard.confirm_setup(CODE2), wizard.check_setup):
        assert call()["error"]["code"] == "setup_not_pending"
    assert prober.setup_calls == 0


def test_a_new_sign_in_and_a_reset_drop_an_open_setup(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    assert prober.setup_open is True
    wizard.set_login("parent", "secret")
    assert prober.setup_open is False
    wizard.start_setup()
    wizard.reset()
    assert prober.setup_open is False


def test_a_check_that_meets_a_refused_password_counts_it(tmp_path):
    wizard, _, prober, _ = forced(tmp_path)
    wizard.start_setup()
    prober.setup_results = [{"status": "uncertain"}]
    wizard.confirm_setup(SETUP_CODE)
    prober.login = "bad_credentials"
    state = wizard.check_setup()
    assert state["error"]["message_key"] == "api.wizard.connectBadCredentials"
    assert state["attempts"] == 1
    assert state["twofactor_setup"] == "uncertain"


def test_a_numeric_code_in_the_request_is_refused_instead_of_crashing(tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app
    from tests.test_server import FakeService

    wizard, store, prober, _ = forced(tmp_path)
    wizard.start_setup()
    api = TestClient(create_app(FakeService(store), wizard=wizard), raise_server_exceptions=False)
    answer = api.post("/api/wizard/twofactor/confirm", json={"code": 135790})
    assert answer.status_code == 200
    assert answer.json()["error"]["code"] == "code_invalid"
    assert prober.setup_codes == []
    answer = api.post("/api/wizard/connect", json={"code": 123456})
    assert answer.status_code == 200
    assert answer.json()["error"]["code"] == "code_invalid"
    assert prober.begin_calls == 0
