import time
from collections import namedtuple
from datetime import date
from urllib.parse import urlparse

import requests

from .. import requestlog
from ..lockout import LOCKED, classify_login_response, login_refusal
from .auth import apply_login_fields, fill_two_factor_code
from .pages import base_shape, refusal_of
from .children import (
    CHILD_PAGE_FORBIDDEN_KEY,
    FORBIDDEN_STATUSES,
    child_page_message_key,
    child_select_present,
    page_diagnosis,
    parse_children,
    time_table_absence,
    time_table_recognised,
    time_table_session_lost,
)
from .dsa import SCHOOL_APP_EXPIRED_KEY
from .errors import (
    LOGIN_SESSION_KEY,
    LOGIN_TWOFACTOR_KEY,
    DataError,
    LoginError,
    OutageError,
    PasswordError,
    RATE_LIMIT_STATUS,
    REASON_BAD_CREDENTIALS,
    REASON_DEFAULT_PASSWORD,
    REASON_LOCKED,
    REASON_MAINTENANCE_PAGE,
    REASON_TWOFACTOR_SETUP,
    REASON_UNEXPECTED,
    REASON_UNKNOWN_ACCOUNT,
    TwoFactorError,
    rate_limit_outage,
    TwoFactorSetupRequired,
    status_reason,
    transport_outage,
)
from .forms import (
    find_client_redirect,
    find_login_form,
    find_two_factor_form,
    parse_forms,
)
from .timetable import (
    TIME_TABLE_SOURCE,
    TIMETABLE_SHAPE_KEY,
    data_params,
    parse_time_table,
    parse_timetable,
)
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
    setup_required,
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
TIME_TABLE_PAGE = "/iserv/time-table/"
TIME_TABLE_DATA = "/iserv/time-table/data"


ACCEPTED_LOGIN_STATUSES = (200, 302)
REGISTRATION_UNCONFIRMED_KEY = "api.twofactor.unconfirmed"
LOGIN_CREDENTIALS_KEY = "api.login.credentials"
LOGIN_UNKNOWN_ACCOUNT_KEY = "api.login.unknownAccount"
LOGIN_DEFAULT_PASSWORD_KEY = "api.login.defaultPassword"
LOGIN_TWOFACTOR_SETUP_KEY = "api.login.twofactorSetup"
LOGIN_LOCKED_KEY = "api.login.locked"
REFUSAL_KEYS = {
    REASON_BAD_CREDENTIALS: LOGIN_CREDENTIALS_KEY,
    REASON_UNKNOWN_ACCOUNT: LOGIN_UNKNOWN_ACCOUNT_KEY,
    REASON_DEFAULT_PASSWORD: LOGIN_DEFAULT_PASSWORD_KEY,
    REASON_LOCKED: LOGIN_LOCKED_KEY,
}
MAINTENANCE_MARKERS = ("wartung", "maintenance")


def server_failure(response):
    status = int(getattr(response, "status_code", 0) or 0)
    if status == RATE_LIMIT_STATUS:
        return rate_limit_outage(response)
    if status >= 500:
        return OutageError(status_reason(status), detail=base_shape(response))
    return None


def login_form_of(response):
    failure = server_failure(response)
    if failure is not None:
        raise failure
    text = getattr(response, "text", "") or ""
    form = find_login_form(parse_forms(text, getattr(response, "url", "")))
    if form is not None:
        return form
    lowered = text.lower()
    reason = REASON_MAINTENANCE_PAGE if any(marker in lowered for marker in MAINTENANCE_MARKERS) else REASON_UNEXPECTED
    raise OutageError(reason, detail=base_shape(response))


def login_shape(response, stage, two_factor_offered):
    text = getattr(response, "text", "") or ""
    forms = parse_forms(text, getattr(response, "url", ""))
    shape = base_shape(response)
    shape.update({
        "login_stage": stage,
        "two_factor_offered": two_factor_offered,
        "two_factor_again": find_two_factor_form(forms) is not None,
        "login_form_again": find_login_form(forms) is not None,
    })
    wording = refusal_of(response)
    if wording:
        shape["refusal"] = wording
    return shape


def registration_shape(response, name):
    shape = base_shape(response)
    shape["token_listed"] = name in parse_token_names(getattr(response, "text", "") or "")
    shape["token_rows"] = len(parse_token_rows(getattr(response, "text", "") or ""))
    wording = refusal_of(response)
    if wording:
        shape["refusal"] = wording
    return shape


def password_outcome(answer, cookie_names):
    if int(getattr(answer, "status_code", 0) or 0) not in ACCEPTED_LOGIN_STATUSES:
        return None
    text = getattr(answer, "text", "") or ""
    if LOGIN_FAILED_MARKER in text or login_refusal(text):
        return False
    forms = parse_forms(text, getattr(answer, "url", ""))
    if find_two_factor_form(forms) is not None:
        return True
    if SESSION_COOKIE in (cookie_names or set()):
        return True
    return None


CappedBody = namedtuple("CappedBody", "status_code text truncated")
TimeTablePage = namedtuple("TimeTablePage", "absent select children")
CAPPED_CHUNK = 64 * 1024


class IServClient:
    def __init__(self, base_url, session=None, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.session = requestlog.install(session or requests.Session())
        self.session.headers.setdefault("User-Agent", "ranzenpost/2609.2.2")
        self.timeout = timeout
        self.username = ""
        self.login_page = ""
        self.landing_page = None
        self.refusal = ""
        self.answered = False
        self.sleeper = time.sleep

    def login(self, username, password, code_provider):
        self.username = username
        response = self._get("/iserv/")
        login_form = login_form_of(response)
        self.login_page = response.text

        payload = apply_login_fields(login_form.fields, username, password)
        response = self._post(login_form.action, payload)
        self._raise_server_failure(response)
        refusal = login_refusal(response.text)
        if not refusal and self._locked_out(response):
            refusal = REASON_LOCKED
        if refusal:
            raise LoginError(
                "iserv refused the sign-in: " + refusal,
                message_key=REFUSAL_KEYS[refusal],
                detail=login_shape(response, "credentials", False),
                reason=refusal,
            )

        two_factor_form = find_two_factor_form(parse_forms(response.text, response.url))
        offered = two_factor_form is not None
        if offered:
            code = code_provider()
            payload = fill_two_factor_code(two_factor_form.fields, code)
            if "_remember_me" in payload:
                payload["_remember_me"] = "on"
            response = self._post(two_factor_form.action, payload)
            self._raise_server_failure(response)

        response = self._follow_client_redirects(response)
        self.landing_page = response
        if not offered and setup_required(response.text, response.url, self.is_authenticated()):
            raise TwoFactorSetupRequired(
                "iserv requires setting up two-factor first",
                message_key=LOGIN_TWOFACTOR_SETUP_KEY,
                detail=login_shape(response, "twofactor_setup", False),
            )
        if not self.is_authenticated():
            again = find_two_factor_form(parse_forms(response.text, response.url)) is not None
            raise TwoFactorError(
                "session was not established",
                message_key=LOGIN_TWOFACTOR_KEY if offered and again else LOGIN_SESSION_KEY,
                detail=login_shape(response, "two_factor" if offered else "session", offered),
            )
        return self

    def _locked_out(self, response):
        if self.is_authenticated() or find_two_factor_form(parse_forms(response.text, response.url)) is not None:
            return False
        return classify_login_response(response.text) == LOCKED

    @staticmethod
    def _raise_server_failure(response):
        failure = server_failure(response)
        if failure is not None:
            raise failure

    def is_authenticated(self):
        return SESSION_COOKIE in self._cookie_names()

    def get_security_page(self):
        return self._get(SECURITY_PATH)

    def get_twofactor_add_page(self):
        return self._get(TWOFACTOR_ADD_PATH)

    def fetch(self, path, params=None):
        return self._get(path, params=params)

    def fetch_capped(self, path, limit, timeout):
        body = bytearray()
        truncated = False
        try:
            response = self.session.get(self._url(path), timeout=timeout, stream=True)
            try:
                for chunk in response.iter_content(chunk_size=CAPPED_CHUNK):
                    body.extend(chunk)
                    if len(body) > limit:
                        del body[limit:]
                        truncated = True
                        break
            finally:
                response.close()
        except requests.RequestException as error:
            raise transport_outage(error) from error
        return CappedBody(int(response.status_code or 0), bytes(body).decode("utf-8", "replace"), truncated)

    def fetch_or_raise(self, path, params=None):
        response = self._get(path, params=params)
        self._raise_server_failure(response)
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
        return parse_token_names(self.fetch_or_raise(TWOFACTOR_LIST_PATH).text)

    def get_twofactor_list_page(self):
        return self._get(TWOFACTOR_LIST_PATH)

    def list_totp_token_rows(self):
        return parse_token_rows(self.fetch_or_raise(TWOFACTOR_LIST_PATH).text)

    def delete_totp_token(self, uuid, code, csrf_token):
        path = TWOFACTOR_DELETE_PATH.format(uuid=uuid)
        answer = self._delete(path, {"delete[code]": code, "delete[_token]": csrf_token})
        status = int(getattr(answer, "status_code", 0) or 0)
        if status >= 400:
            raise DataError(f"two-factor delete failed: {status}")
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
        except (DataError, requests.RequestException):
            before = None
        result = self._post(registration.action, payload)
        try:
            registered = self._token_count(name) > before if before is not None else None
        except (DataError, requests.RequestException):
            registered = None
        if registered is None:
            registered = name in parse_token_names(result.text)
        if registered:
            return registration.secret
        errors = extract_form_errors(result.text)
        if errors or registration_rejected(result.text):
            raise TwoFactorError(errors[0] if errors else "two-factor registration was rejected")
        raise TwoFactorError(
            "two-factor registration could not be confirmed",
            message_key=REGISTRATION_UNCONFIRMED_KEY,
            detail=registration_shape(result, name),
        )

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
        accepts_new = self.accepts_password(new)
        if accepts_new is True:
            return True
        if accepts_new is False:
            raise PasswordError(extract_form_errors(html) or "password change was rejected")
        self.sleeper(LOGIN_RETRY_SECONDS)
        if self.accepts_password(current) is True:
            raise PasswordError(extract_form_errors(html) or "password change was rejected")
        if password_changed(html):
            return True
        raise PasswordError(PASSWORD_UNVERIFIED)

    def _probe_session(self):
        probe = requests.Session()
        probe.headers.update(self.session.headers)
        return probe

    def accepts_password(self, password):
        self.refusal = ""
        self.answered = False
        if not self.username or not password:
            return None
        probe = self._probe_session()
        try:
            page = probe.get(f"{self.base_url}/iserv/", timeout=self.timeout)
            form = find_login_form(parse_forms(page.text, page.url))
            if form is None:
                return None
            payload = apply_login_fields(form.fields, self.username, password)
            answer = probe.post(form.action, data=payload, timeout=self.timeout)
            for _ in range(MAX_REDIRECTS):
                if SESSION_COOKIE in {cookie.name for cookie in probe.cookies}:
                    break
                target = find_client_redirect(answer.text, answer.url)
                if not target:
                    break
                answer = probe.get(self._url(target), timeout=self.timeout)
            cookies = {cookie.name for cookie in probe.cookies}
            self.answered = server_failure(answer) is None
            self.refusal = login_refusal(answer.text) or ""
            code_prompt = find_two_factor_form(parse_forms(answer.text, answer.url)) is not None
            signed_in = SESSION_COOKIE in cookies
            if not self.refusal and not signed_in and not code_prompt and classify_login_response(answer.text) == LOCKED:
                self.refusal = LOCKED
            if not self.refusal and not code_prompt and setup_required(answer.text, answer.url, SESSION_COOKIE in cookies):
                self.refusal = REASON_TWOFACTOR_SETUP
            return password_outcome(answer, cookies)
        except requests.RequestException:
            return None
        finally:
            probe.close()

    def get_children(self):
        response = self._get("/iserv/time-table/")
        self._raise_server_failure(response)
        if response.status_code != 200 or not child_select_present(response.text):
            raise DataError(
                "child list page was not readable",
                message_key=child_page_message_key(response.status_code),
                detail=page_diagnosis(response),
            )
        return parse_children(response.text)

    def get_timetable(self, child_id, reference=None):
        params = data_params(child_id, reference or date.today())
        response = self._get(TIME_TABLE_DATA, params=params)
        self._raise_server_failure(response)
        if response.status_code in FORBIDDEN_STATUSES:
            raise DataError(
                f"timetable request failed: {response.status_code}",
                message_key=CHILD_PAGE_FORBIDDEN_KEY,
                detail=page_diagnosis(response),
            )
        if response.status_code != 200:
            raise DataError(f"timetable request failed: {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise DataError("timetable response was not json") from error
        return parse_timetable(payload)

    def read_time_table_page(self):
        response = self._get(TIME_TABLE_PAGE)
        status = self._secondary_status(response)
        self._raise_session_lost(response)
        absent = time_table_absence(response)
        if absent:
            return TimeTablePage(absent, False, [])
        if status != 200:
            raise self._time_table_refusal("time-table page", response)
        text = getattr(response, "text", "") or ""
        if not time_table_recognised(text):
            raise DataError(
                "the time-table page was not recognised",
                message_key=TIMETABLE_SHAPE_KEY,
                detail=dict(page_diagnosis(response), source=TIME_TABLE_SOURCE, recognised=False),
            )
        return TimeTablePage("", child_select_present(text), parse_children(text))

    def read_time_table_week(self, child_id, reference=None):
        response = self._get(TIME_TABLE_DATA, params=data_params(child_id, reference or date.today()))
        status = self._secondary_status(response)
        self._raise_session_lost(response)
        if status != 200:
            raise self._time_table_refusal("time-table data", response)
        try:
            payload = response.json()
        except ValueError as error:
            raise DataError(
                "time-table data was not json",
                message_key=TIMETABLE_SHAPE_KEY,
                detail=dict(page_diagnosis(response), source=TIME_TABLE_SOURCE),
            ) from error
        week = parse_time_table(payload)
        week.answer = base_shape(response)
        return week

    @staticmethod
    def _secondary_status(response):
        status = int(getattr(response, "status_code", 0) or 0)
        if status == RATE_LIMIT_STATUS:
            raise rate_limit_outage(response)
        return status

    @staticmethod
    def _raise_session_lost(response):
        lost = time_table_session_lost(response)
        if lost:
            raise DataError(
                "the time-table module answered without a session",
                message_key=SCHOOL_APP_EXPIRED_KEY,
                detail=dict(base_shape(response), source=TIME_TABLE_SOURCE, session=lost),
            )

    @staticmethod
    def _time_table_refusal(what, response):
        status = int(getattr(response, "status_code", 0) or 0)
        return DataError(
            f"{what} answered {status}",
            message_key=TIMETABLE_SHAPE_KEY,
            detail=dict(page_diagnosis(response), source=TIME_TABLE_SOURCE),
        )

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
        try:
            return self.session.get(self._url(path), timeout=self.timeout, **kwargs)
        except requests.RequestException as error:
            raise transport_outage(error) from error

    def _post(self, path, data):
        try:
            return self.session.post(self._url(path), data=data, timeout=self.timeout)
        except requests.RequestException as error:
            raise transport_outage(error) from error

    def _delete(self, path, data):
        try:
            return self.session.request("DELETE", self._url(path), data=data, timeout=self.timeout)
        except requests.RequestException as error:
            raise transport_outage(error) from error

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

    def post_absolute(self, url, data, timeout=30, follow_redirects=True, headers=None):
        if not self._is_same_origin(url):
            raise DataError("cross-origin request blocked")
        extra = {"headers": headers} if headers else {}
        return self.session.post(url, data=data, timeout=timeout, allow_redirects=follow_redirects, **extra)
