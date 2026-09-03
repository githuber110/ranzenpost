import app.iserv_prober as prober_mod
from app.iserv_prober import IServProber
from app.iserv.errors import LoginError, TwoFactorError

VALID_SECRET = "JBSWY3DPEHPK3PXP"


class StubClient:
    def __init__(self, login_exc=None, register=None, register_exc=None, authed=True, confirm_exc=None, token_rows=None):
        self.login_exc = login_exc
        self.register = register
        self.register_exc = register_exc
        self.confirm_exc = confirm_exc
        self._authed = authed
        self._token_rows = list(token_rows or [])

    def login(self, username, password, provider):
        provider()
        if self.login_exc:
            raise self.login_exc
        return self

    def start_totp_registration(self):
        if self.register_exc:
            raise self.register_exc
        return {"secret": self.register}

    def confirm_totp_registration(self, registration, name, code, at=None):
        if self.confirm_exc:
            raise self.confirm_exc
        return self.register

    def register_totp(self, name, code):
        registration = self.start_totp_registration()
        return self.confirm_totp_registration(registration, name, code)

    def is_authenticated(self):
        return self._authed

    def list_totp_token_rows(self):
        return list(self._token_rows)

    def add_token_row(self, name, uuid):
        self._token_rows.append({"name": name, "uuid": uuid})


def patch(monkeypatch, stubs):
    iterator = iter(stubs)
    monkeypatch.setattr(prober_mod, "IServClient", lambda url, timeout=None: next(iterator))


def test_register_2fa_success(monkeypatch):
    patch(monkeypatch, [StubClient(register=VALID_SECRET, authed=True), StubClient(authed=True)])
    result = IServProber().register_2fa("https://x", "u", "p", "123456")
    assert result == {"status": "ok", "secret": VALID_SECRET}


def test_register_2fa_bad_login_code(monkeypatch):
    patch(monkeypatch, [StubClient(login_exc=TwoFactorError("no"))])
    assert IServProber().register_2fa("https://x", "u", "p", "000000")["status"] == "bad_code"


def test_register_2fa_bad_credentials(monkeypatch):
    patch(monkeypatch, [StubClient(login_exc=LoginError("no"))])
    assert IServProber().register_2fa("https://x", "u", "p", "000000")["status"] == "bad_credentials"


def test_register_2fa_confirm_rejected(monkeypatch):
    patch(monkeypatch, [StubClient(register=VALID_SECRET, confirm_exc=TwoFactorError("rejected"))])
    assert IServProber().register_2fa("https://x", "u", "p", "000000")["status"] == "code_rejected"


def test_begin_2fa_reports_missing_form(monkeypatch):
    patch(monkeypatch, [StubClient(register_exc=TwoFactorError("no form"))])
    assert IServProber().begin_2fa("https://x", "u", "p", "123456")["status"] == "no_form"


def test_confirm_without_begin_is_expired():
    assert IServProber().confirm_2fa("https://x", "u", "p", "123456")["status"] == "expired"


def test_a_created_token_always_yields_its_secret(monkeypatch):
    patch(monkeypatch, [StubClient(register=VALID_SECRET, authed=True)])
    result = IServProber().register_2fa("https://x", "u", "p", "123456")
    assert result["status"] == "ok"
    assert result["secret"] == VALID_SECRET


def test_registration_does_not_burn_a_second_login_on_verification(monkeypatch):
    calls = []

    class Counting(StubClient):
        def login(self, username, password, provider):
            calls.append(provider())
            return super().login(username, password, provider)

    patch(monkeypatch, [Counting(register=VALID_SECRET, authed=True)])
    IServProber().register_2fa("https://x", "u", "p", "123456")
    assert len(calls) == 1


def test_confirm_2fa_captures_the_uuid_of_the_row_that_newly_appeared(monkeypatch):
    stub = StubClient(register=VALID_SECRET, authed=True)
    stub.add_token_row("parent@school.example", "existing-uuid")
    patch(monkeypatch, [stub])
    prober = IServProber()
    begun = prober.begin_2fa("https://x", "u", "p", "123456")
    assert begun["status"] == "awaiting_confirm"
    stub.add_token_row("ISERV-Connector", "new-uuid")
    result = prober.confirm_2fa("https://x", "u", "p", "123456")
    assert result == {"status": "ok", "secret": VALID_SECRET, "uuid": "new-uuid"}


def test_confirm_2fa_omits_the_uuid_when_no_new_row_can_be_identified(monkeypatch):
    stub = StubClient(register=VALID_SECRET, authed=True)
    patch(monkeypatch, [stub])
    prober = IServProber()
    prober.begin_2fa("https://x", "u", "p", "123456")
    result = prober.confirm_2fa("https://x", "u", "p", "123456")
    assert result == {"status": "ok", "secret": VALID_SECRET}
