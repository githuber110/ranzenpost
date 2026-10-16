import threading
import time
from urllib.parse import quote, urlencode

import requests

from . import code_windows
from .iserv.auth import apply_login_fields
from .iserv.client import (
    REGISTRATION_UNCONFIRMED_KEY,
    SESSION_COOKIE,
    SETUP_OK,
    SETUP_REJECTED,
    IServClient,
    login_form_of,
    server_failure,
)
from .iserv.errors import (
    REASON_CONNECTION,
    REASON_RATE_LIMITED,
    REASON_TIMEOUT,
    DataError,
    LoginError,
    OutageError,
    TwoFactorError,
    TwoFactorSetupRequired,
    login_reason,
    session_never_opened,
)
from .iserv.forms import find_client_redirect, find_login_form, find_two_factor_form, parse_forms
from .iserv.twofactor import setup_required, token_listed
from .lockout import TWOFACTOR_REQUIRED_SETUP, classify_login_response, login_refusal


RATE_LIMITED = "rate_limited"
OUTAGE = "outage"
SENT_MAYBE_REASONS = (REASON_TIMEOUT, REASON_CONNECTION)
SETUP_TOKEN_NAME = "Authenticator"
SETUP_ISSUER = "IServ"


class CodePromptShown(Exception):
    pass


def _no_code_expected():
    raise CodePromptShown()


def setup_uri(secret, uri, username):
    if uri:
        return uri
    label = quote("%s:%s" % (SETUP_ISSUER, username or ""), safe=":@")
    return "otpauth://totp/%s?%s" % (label, urlencode({"secret": secret, "issuer": SETUP_ISSUER}))


def _cookie_names(session):
    return {cookie.name for cookie in session.cookies}


def outage_status(error):
    return RATE_LIMITED if getattr(error, "reason", "") == REASON_RATE_LIMITED else OUTAGE


def outage_result(error):
    return {"status": outage_status(error), "retry_after": getattr(error, "retry_after", None)}


class IServProber:
    def __init__(self, timeout=15):
        self.timeout = timeout
        self._pending = None
        self._setup = None
        self.retry_after = None
        self.sleeper = time.sleep
        self.clock = time.time
        self._code_lock = threading.Lock()

    def _next_code(self, secret):
        return code_windows.next_code(secret, None, self.sleeper, self.clock)

    def probe_url(self, base):
        try:
            response = requests.Session().get(f"{base}/iserv/", timeout=self.timeout)
        except requests.RequestException:
            return {"ok": False, "error": "url_unreachable", "message_key": "api.wizard.urlUnreachable"}
        forms = parse_forms(response.text, response.url)
        looks_iserv = "/iserv/" in response.text or "iserv" in response.url.lower()
        if find_login_form(forms) is not None and looks_iserv:
            return {"ok": True, "host": base}
        return {"ok": False, "error": "not_iserv", "message_key": "api.wizard.notIserv"}

    def verify_login(self, url, username, password):
        self.retry_after = None
        try:
            session = requests.Session()
            page = session.get(f"{url}/iserv/", timeout=self.timeout)
            login_form = login_form_of(page)
            payload = apply_login_fields(login_form.fields, username, password)
            response = session.post(login_form.action, data=payload, timeout=self.timeout)
            failure = server_failure(response)
            if failure is not None:
                raise failure
        except OutageError as error:
            self.retry_after = error.retry_after
            return outage_status(error)
        except requests.RequestException:
            return OUTAGE
        refusal = login_refusal(response.text)
        if refusal:
            return refusal
        if find_two_factor_form(parse_forms(response.text, response.url)) is not None:
            return "twofactor"
        for _ in range(5):
            if setup_required(response.text, response.url, SESSION_COOKIE in _cookie_names(session)):
                return TWOFACTOR_REQUIRED_SETUP
            if SESSION_COOKIE in _cookie_names(session):
                return "no_2fa"
            target = find_client_redirect(response.text, response.url)
            if not target:
                break
            try:
                response = session.get(target, timeout=self.timeout)
            except requests.RequestException:
                break
        if setup_required(response.text, response.url, SESSION_COOKIE in _cookie_names(session)):
            return TWOFACTOR_REQUIRED_SETUP
        if SESSION_COOKIE in _cookie_names(session):
            return "no_2fa"
        kind = classify_login_response(response.text)
        if kind != "normal":
            return kind
        return "unknown"

    def verify_totp(self, url, username, password, secret):
        with self._code_lock:
            return self._verify_totp(url, username, password, secret)

    def _verify_totp(self, url, username, password, secret):
        self.retry_after = None
        try:
            client = IServClient(url, timeout=self.timeout)
            client.login(username, password, lambda: self._next_code(secret))
        except TwoFactorError as error:
            return "unknown" if session_never_opened(error) else "bad_code"
        except TwoFactorSetupRequired:
            return TWOFACTOR_REQUIRED_SETUP
        except LoginError as error:
            return login_reason(error)
        except OutageError as error:
            self.retry_after = error.retry_after
            return outage_status(error)
        except requests.RequestException:
            return "unknown"
        return "ok" if client.is_authenticated() else "unknown"

    @staticmethod
    def _token_list(client):
        try:
            return client.read_token_list()
        except Exception:
            return None

    @staticmethod
    def _uuids(rows):
        return {row["uuid"] for row in rows if row.get("uuid")}

    def begin_2fa(self, url, username, password, code, name="ISERV-Connector"):
        try:
            client = IServClient(url, timeout=self.timeout)
            client.login(username, password, lambda: code)
        except TwoFactorError as error:
            return {"status": "unknown" if session_never_opened(error) else "bad_code"}
        except TwoFactorSetupRequired:
            return {"status": TWOFACTOR_REQUIRED_SETUP}
        except LoginError as error:
            return {"status": login_reason(error)}
        except OutageError as error:
            return outage_result(error)
        except requests.RequestException:
            return {"status": "network"}
        try:
            registration = client.start_totp_registration()
        except TwoFactorError:
            return {"status": "no_form"}
        except OutageError as error:
            return outage_result(error)
        except requests.RequestException:
            return {"status": "network"}
        rows = self._token_list(client)
        same = [row for row in rows or [] if row["name"] == name]
        old_tokens = [{"uuid": row["uuid"], "created": row.get("created", "")} for row in same if row["uuid"]]
        self._pending = {
            "client": client,
            "registration": registration,
            "url": url,
            "username": username,
            "existing_uuids": None if rows is None else self._uuids(rows),
            "old_tokens": old_tokens,
        }
        return {"status": "awaiting_confirm", "stale_tokens": len(same), "stale_removable": len(old_tokens)}

    def confirm_2fa(self, url, username, password, code, name="ISERV-Connector"):
        pending = self._pending
        if not pending or pending.get("url") != url or pending.get("username") != username:
            return {"status": "expired"}
        client = pending["client"]
        registration = pending["registration"]
        at = self.clock()
        try:
            with self._code_lock:
                code_windows.mark_used(getattr(registration, "secret", ""), at)
                secret = client.confirm_totp_registration(registration, name, code, at=at)
        except TwoFactorError as error:
            if error.message_key == REGISTRATION_UNCONFIRMED_KEY:
                pending["unconfirmed"] = True
                return {"status": "unconfirmed"}
            self._pending = None
            return {"status": "code_rejected", "message": str(error)}
        except OutageError as error:
            if error.reason in SENT_MAYBE_REASONS:
                pending["unconfirmed"] = True
                return {"status": "unconfirmed"}
            return outage_result(error)
        except requests.RequestException:
            pending["unconfirmed"] = True
            return {"status": "unconfirmed"}
        return self._registered(pending, secret, self._token_list(client))

    def _registered(self, pending, secret, rows):
        self._pending = None
        existing = pending.get("existing_uuids")
        listed = set() if rows is None else self._uuids(rows)
        new_uuids = set() if existing is None else listed - existing
        result = {"status": "ok", "secret": secret}
        if len(new_uuids) == 1:
            result["uuid"] = new_uuids.pop()
        old = [dict(token) for token in pending.get("old_tokens", []) if token["uuid"] in listed]
        if old:
            result["old_tokens"] = old
        return result

    def check_registration(self, url, username, name="ISERV-Connector"):
        pending = self._pending
        if not pending or not pending.get("unconfirmed") or pending.get("url") != url or pending.get("username") != username:
            return {"status": "expired"}
        rows = self._token_list(pending["client"])
        if rows is None:
            return {"status": "unconfirmed"}
        existing = pending.get("existing_uuids")
        if existing is None:
            if any(row["name"] == name for row in rows):
                return {"status": "unconfirmed"}
            self._pending = None
            return {"status": "missing"}
        if not any(row["name"] == name and row["uuid"] not in existing for row in rows):
            self._pending = None
            return {"status": "missing"}
        return self._registered(pending, pending["registration"].secret, rows)

    def remove_stale_tokens(self, url, username, password, secret, uuids):
        with self._code_lock:
            return self._remove_tokens(url, username, password, secret, uuids)

    def _remove_tokens(self, url, username, password, secret, uuids):
        wanted = [str(uuid) for uuid in uuids or []]
        client = IServClient(url, timeout=self.timeout)
        try:
            client.login(username, password, lambda: self._next_code(secret))
        except TwoFactorSetupRequired:
            return {"status": TWOFACTOR_REQUIRED_SETUP, "left": wanted}
        except TwoFactorError:
            return {"status": "failed", "left": wanted}
        except LoginError as error:
            return {"status": login_reason(error), "left": wanted}
        except OutageError as error:
            return dict(outage_result(error), left=wanted)
        except requests.RequestException:
            return {"status": "network", "left": wanted}
        failed = False
        for uuid in wanted:
            try:
                html, rows, token = client.token_removal_list()
                if not token_listed(html, rows, uuid):
                    continue
                client.delete_totp_token(uuid, self._next_code(secret), token)
            except (DataError, OutageError, requests.RequestException):
                failed = True
                break
        try:
            html, rows, _token = client.token_removal_list()
        except (DataError, requests.RequestException):
            return {"status": "uncertain", "left": wanted}
        left = [uuid for uuid in wanted if token_listed(html, rows, uuid)]
        if not left:
            return {"status": "ok", "left": [], "removed": len(wanted)}
        return {"status": "failed" if failed or len(left) == len(wanted) else "partial", "left": left}

    def begin_setup(self, url, username, password, name=SETUP_TOKEN_NAME):
        self._setup = None
        client = IServClient(url, timeout=self.timeout)
        try:
            client.login(username, password, _no_code_expected)
            return {"status": "no_2fa"}
        except CodePromptShown:
            return {"status": "twofactor"}
        except TwoFactorSetupRequired:
            pass
        except TwoFactorError:
            return {"status": "unknown"}
        except LoginError as error:
            return {"status": login_reason(error)}
        except OutageError as error:
            return outage_result(error)
        except requests.RequestException:
            return {"status": "network"}
        try:
            setup = client.open_twofactor_setup(name, password)
        except TwoFactorError:
            return {"status": "no_form"}
        except OutageError as error:
            return outage_result(error)
        except requests.RequestException:
            return {"status": "network"}
        self._setup = {"client": client, "setup": setup, "url": url, "username": username, "name": name}
        return {"status": "awaiting_setup_code"}

    def setup_key(self, url, username):
        pending = self._setup
        if not pending or pending.get("url") != url or pending.get("username") != username:
            return None
        setup = pending["setup"]
        return {"secret": setup.secret, "uri": setup_uri(setup.secret, setup.uri, username)}

    def confirm_setup(self, url, username, password, code):
        pending = self._setup
        if not pending or pending.get("url") != url or pending.get("username") != username:
            return {"status": "expired"}
        before = pending["setup"].secret
        try:
            outcome = pending["client"].confirm_twofactor_setup(pending["setup"], pending["name"], code, password)
        except OutageError as error:
            self._setup = None
            return dict(outage_result(error), status="uncertain")
        except requests.RequestException:
            self._setup = None
            return {"status": "uncertain"}
        if outcome.status == SETUP_REJECTED:
            pending["setup"] = outcome.setup
            return {"status": "rejected", "key_changed": outcome.setup.secret != before}
        self._setup = None
        return {"status": "ok" if outcome.status == SETUP_OK else "uncertain"}

    def drop_setup(self):
        self._setup = None
