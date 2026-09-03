import requests

from .iserv.auth import apply_login_fields
from .iserv.client import SESSION_COOKIE, IServClient
from .iserv.errors import LoginError, TwoFactorError
from .iserv.forms import find_client_redirect, find_login_form, find_two_factor_form, parse_forms
from .iserv.totp import generate_code
from . import messages
from .lockout import classify_login_response

LOGIN_FAILED = "Anmeldung fehlgeschlagen"


def _cookie_names(session):
    return {cookie.name for cookie in session.cookies}


class IServProber:
    def __init__(self, timeout=15):
        self.timeout = timeout
        self._pending = None

    def probe_url(self, base):
        try:
            response = requests.Session().get(f"{base}/iserv/", timeout=self.timeout)
        except requests.RequestException:
            return {"ok": False, "error": "url_unreachable",
                    "message_key": "api.wizard.urlUnreachable",
                    "message": messages.text("api.wizard.urlUnreachable")}
        forms = parse_forms(response.text, response.url)
        looks_iserv = "/iserv/" in response.text or "iserv" in response.url.lower()
        if find_login_form(forms) is not None and looks_iserv:
            return {"ok": True, "host": base}
        return {"ok": False, "error": "not_iserv",
                "message_key": "api.wizard.notIserv",
                "message": messages.text("api.wizard.notIserv")}

    def verify_login(self, url, username, password):
        try:
            session = requests.Session()
            page = session.get(f"{url}/iserv/", timeout=self.timeout)
            login_form = find_login_form(parse_forms(page.text, page.url))
            if login_form is None:
                return "unknown"
            payload = apply_login_fields(login_form.fields, username, password)
            response = session.post(login_form.action, data=payload, timeout=self.timeout)
        except requests.RequestException:
            return "unknown"
        if LOGIN_FAILED in response.text:
            return "bad_credentials"
        if find_two_factor_form(parse_forms(response.text, response.url)) is not None:
            return "twofactor"
        for _ in range(5):
            if SESSION_COOKIE in _cookie_names(session):
                return "no_2fa"
            target = find_client_redirect(response.text, response.url)
            if not target:
                break
            try:
                response = session.get(target, timeout=self.timeout)
            except requests.RequestException:
                break
        if SESSION_COOKIE in _cookie_names(session):
            return "no_2fa"
        if classify_login_response(response.text, response.status_code) != "normal":
            return "locked"
        return "unknown"

    def verify_totp(self, url, username, password, secret):
        try:
            client = IServClient(url, timeout=self.timeout)
            client.login(username, password, lambda: generate_code(secret))
        except TwoFactorError:
            return "bad_code"
        except LoginError:
            return "bad_credentials"
        except requests.RequestException:
            return "unknown"
        return "ok" if client.is_authenticated() else "unknown"

    @staticmethod
    def _stale_tokens(client, name):
        try:
            return sum(1 for entry in client.list_totp_tokens() if entry == name)
        except Exception:
            return 0

    @staticmethod
    def _token_uuids(client):
        try:
            return {row["uuid"] for row in client.list_totp_token_rows()}
        except Exception:
            return set()

    def begin_2fa(self, url, username, password, code, name="ISERV-Connector"):
        try:
            client = IServClient(url, timeout=self.timeout)
            client.login(username, password, lambda: code)
        except TwoFactorError:
            return {"status": "bad_code"}
        except LoginError:
            return {"status": "bad_credentials"}
        except requests.RequestException:
            return {"status": "network"}
        try:
            registration = client.start_totp_registration()
        except TwoFactorError:
            return {"status": "no_form"}
        except requests.RequestException:
            return {"status": "network"}
        self._pending = {
            "client": client,
            "registration": registration,
            "url": url,
            "username": username,
            "existing_uuids": self._token_uuids(client),
        }
        return {"status": "awaiting_confirm", "stale_tokens": self._stale_tokens(client, name)}

    def confirm_2fa(self, url, username, password, code, name="ISERV-Connector"):
        pending = self._pending
        if not pending or pending.get("url") != url or pending.get("username") != username:
            return {"status": "expired"}
        client = pending["client"]
        registration = pending["registration"]
        try:
            secret = client.confirm_totp_registration(registration, name, code)
        except TwoFactorError as error:
            self._pending = None
            return {"status": "code_rejected", "message": str(error)}
        except requests.RequestException:
            return {"status": "network"}
        self._pending = None
        new_uuids = self._token_uuids(client) - pending.get("existing_uuids", set())
        result = {"status": "ok", "secret": secret}
        if len(new_uuids) == 1:
            result["uuid"] = new_uuids.pop()
        return result

    def register_2fa(self, url, username, password, code, name="ISERV-Connector"):
        started = self.begin_2fa(url, username, password, code)
        if started.get("status") != "awaiting_confirm":
            return started
        return self.confirm_2fa(url, username, password, code, name)
