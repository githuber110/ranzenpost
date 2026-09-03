import json
import time
from datetime import date
from urllib.parse import urlparse

import requests

from .auth import apply_login_fields, fill_two_factor_code
from .children import parse_children
from .errors import DataError, LoginError, PasswordError, TwoFactorError
from .forms import (
    find_client_redirect,
    find_login_form,
    find_two_factor_form,
    parse_forms,
)
from .timetable import build_filter, parse_timetable, week_bounds
from .totp import generate_code
from .twofactor import (
    build_confirm_payload,
    build_password_payload,
    extract_form_errors,
    parse_password_form,
    parse_registration,
    parse_token_names,
    parse_token_rows,
    password_changed,
    registration_rejected,
)

LOGIN_FAILED_MARKER = "Anmeldung fehlgeschlagen"
LOGIN_RETRY_SECONDS = 3
PASSWORD_UNVERIFIED = "password change could not be verified"
SESSION_COOKIE = "IServSession"
SECURITY_PATH = "/iserv/account/settings/security"
TWOFACTOR_ADD_PATH = "/iserv/auth/settings/twofactor/add"
TWOFACTOR_LIST_PATH = "/iserv/auth/settings/twofactor/"
TWOFACTOR_DELETE_PATH = "/iserv/auth/settings/twofactor/delete/{uuid}"
MAX_REDIRECTS = 6


class IServClient:
    def __init__(self, base_url, session=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "ranzenpost/2609.01.01")
        self.timeout = timeout
        self.username = ""
        self.sleeper = time.sleep

    def login(self, username, password, code_provider):
        self.username = username
        response = self._get("/iserv/")
        login_form = find_login_form(parse_forms(response.text, response.url))
        if login_form is None:
            raise LoginError("login form not found")

        payload = apply_login_fields(login_form.fields, username, password)
        response = self._post(login_form.action, payload)
        if LOGIN_FAILED_MARKER in response.text:
            raise LoginError("invalid username or password")

        two_factor_form = find_two_factor_form(parse_forms(response.text, response.url))
        if two_factor_form is not None:
            code = code_provider()
            payload = fill_two_factor_code(two_factor_form.fields, code)
            if "_remember_me" in payload:
                payload["_remember_me"] = "on"
            response = self._post(two_factor_form.action, payload)

        response = self._follow_client_redirects(response)
        if not self.is_authenticated():
            raise TwoFactorError("session was not established")
        return self

    def is_authenticated(self):
        return SESSION_COOKIE in self._cookie_names()

    def get_security_page(self):
        return self._get(SECURITY_PATH)

    def get_twofactor_add_page(self):
        return self._get(TWOFACTOR_ADD_PATH)

    def fetch(self, path, params=None):
        return self._get(path, params=params)

    def fetch_or_raise(self, path, params=None):
        response = self._get(path, params=params)
        if response.status_code != 200:
            raise DataError(f"request failed: {response.status_code}")
        return response

    def start_totp_registration(self):
        response = self.get_twofactor_add_page()
        registration = parse_registration(response.text, response.url)
        if registration is None:
            raise TwoFactorError("two-factor registration form not found")
        return registration

    def list_totp_tokens(self):
        response = self._get(TWOFACTOR_LIST_PATH)
        return parse_token_names(response.text)

    def get_twofactor_list_page(self):
        return self._get(TWOFACTOR_LIST_PATH)

    def list_totp_token_rows(self):
        return parse_token_rows(self.get_twofactor_list_page().text)

    def delete_totp_token(self, uuid, code, csrf_token):
        path = TWOFACTOR_DELETE_PATH.format(uuid=uuid)
        self._delete(path, {"delete[code]": code, "delete[_token]": csrf_token})
        remaining = {row["uuid"] for row in self.list_totp_token_rows()}
        return uuid not in remaining

    def _token_count(self, name):
        return sum(1 for entry in self.list_totp_tokens() if entry == name)

    def confirm_totp_registration(self, registration, name, verification_code, at=None):
        payload = build_confirm_payload(
            registration,
            name,
            verification_code,
            generate_code(registration.secret, at=at),
        )
        try:
            before = self._token_count(name)
        except requests.RequestException:
            before = None
        result = self._post(registration.action, payload)
        try:
            registered = self._token_count(name) > before if before is not None else None
        except requests.RequestException:
            registered = None
        if registered is None:
            registered = not registration_rejected(result.text)
        if registered:
            return registration.secret
        errors = extract_form_errors(result.text)
        raise TwoFactorError(errors[0] if errors else "two-factor registration was rejected")

    def register_totp(self, name, verification_code, at=None):
        registration = self.start_totp_registration()
        return self.confirm_totp_registration(registration, name, verification_code, at=at)

    def change_password(self, current, new):
        response = self.get_security_page()
        form = parse_password_form(response.text, response.url)
        if form is None:
            raise PasswordError("password change form not found")
        payload = build_password_payload(form, current, new)
        result = self._post(form.action, payload)
        return self._verify_password_change(current, new, result.text)

    def _verify_password_change(self, current, new, html):
        if self.accepts_password(new) is True:
            return True
        self.sleeper(LOGIN_RETRY_SECONDS)
        if self.accepts_password(current) is True:
            raise PasswordError(extract_form_errors(html) or "password change was rejected")
        if password_changed(html):
            return True
        raise PasswordError(PASSWORD_UNVERIFIED)

    def accepts_password(self, password):
        if not self.username or not password:
            return None
        probe = requests.Session()
        probe.headers.update(self.session.headers)
        try:
            page = probe.get(f"{self.base_url}/iserv/", timeout=self.timeout)
            form = find_login_form(parse_forms(page.text, page.url))
            if form is None:
                return None
            payload = apply_login_fields(form.fields, self.username, password)
            answer = probe.post(form.action, data=payload, timeout=self.timeout)
        except requests.RequestException:
            return None
        finally:
            probe.close()
        return LOGIN_FAILED_MARKER not in answer.text

    def get_children(self):
        response = self._get("/iserv/time-table/")
        return parse_children(response.text)

    def get_timetable(self, child_id, reference=None):
        start, end = week_bounds(reference or date.today())
        week_filter = build_filter(child_id, start, end)
        params = {
            "filter": json.dumps(week_filter, separators=(",", ":")),
            "childId": child_id,
        }
        response = self._get("/iserv/time-table/data", params=params)
        if response.status_code != 200:
            raise DataError(f"timetable request failed: {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise DataError("timetable response was not json") from error
        return parse_timetable(payload)

    def _cookie_names(self):
        return {cookie.name for cookie in self.session.cookies}

    def _follow_client_redirects(self, response):
        for _ in range(MAX_REDIRECTS):
            if self.is_authenticated():
                return response
            target = find_client_redirect(response.text, response.url)
            if not target:
                return response
            response = self._get(target)
        return response

    def _get(self, path, **kwargs):
        return self.session.get(self._url(path), timeout=self.timeout, **kwargs)

    def _post(self, path, data):
        return self.session.post(self._url(path), data=data, timeout=self.timeout)

    def _delete(self, path, data):
        return self.session.request("DELETE", self._url(path), data=data, timeout=self.timeout)

    def _is_same_origin(self, url):
        target = urlparse(url)
        base = urlparse(self.base_url)
        return target.scheme == base.scheme and target.netloc == base.netloc

    def _url(self, path):
        if path.startswith("http"):
            if not self._is_same_origin(path):
                raise DataError("cross-origin request blocked")
            return path
        return f"{self.base_url}{path}"

    def post_absolute(self, url, data, timeout=30):
        if not self._is_same_origin(url):
            raise DataError("cross-origin request blocked")
        return self.session.post(url, data=data, timeout=timeout)
