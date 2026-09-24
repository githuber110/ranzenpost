from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

from requests import RequestException, Timeout

from .pages import base_shape


class IServError(Exception):
    def __init__(self, note="", message_key="", detail=None):
        super().__init__(note)
        self.message_key = message_key
        self.detail = dict(detail or {})


REASON_BAD_CREDENTIALS = "bad_credentials"
REASON_UNKNOWN_ACCOUNT = "unknown_account"
REASON_DEFAULT_PASSWORD = "default_password_blocked"
REASON_TWOFACTOR_SETUP = "twofactor_required_setup"
REASON_LOCKED = "locked"
REASON_SESSION_NOT_OPENED = "session_not_opened"
REASON_CODE_STEP_FAILED = "code_step_failed"
QUIET_SIGN_IN_REASONS = (REASON_SESSION_NOT_OPENED, REASON_CODE_STEP_FAILED)
LATE_SIGN_IN_REASONS = (REASON_CODE_STEP_FAILED, REASON_SESSION_NOT_OPENED)
LOGIN_SESSION_KEY = "api.login.session"
LOGIN_TWOFACTOR_KEY = "api.login.twofactor"
LOGIN_REASONS = (
    REASON_BAD_CREDENTIALS,
    REASON_UNKNOWN_ACCOUNT,
    REASON_DEFAULT_PASSWORD,
    REASON_TWOFACTOR_SETUP,
    REASON_LOCKED,
)


class LoginError(IServError):
    def __init__(self, note="", message_key="", detail=None, reason=REASON_BAD_CREDENTIALS):
        super().__init__(note, message_key=message_key, detail=detail)
        self.reason = reason if reason in LOGIN_REASONS else REASON_BAD_CREDENTIALS


class TwoFactorError(IServError):
    pass


class TwoFactorSetupRequired(LoginError):
    def __init__(self, note="", message_key="", detail=None):
        super().__init__(note, message_key=message_key, detail=detail, reason=REASON_TWOFACTOR_SETUP)


def sign_in_reason_rank(reason):
    return LATE_SIGN_IN_REASONS.index(reason) + 1 if reason in LATE_SIGN_IN_REASONS else 0


def login_reason(error):
    if isinstance(error, LoginError):
        return error.reason
    return ""


def session_never_opened(error):
    detail = getattr(error, "detail", None)
    if not isinstance(error, TwoFactorError) or not isinstance(detail, dict):
        return False
    stage = detail.get("login_stage")
    return stage == "session" or (stage == "two_factor" and error.message_key == LOGIN_SESSION_KEY)


def code_step_failed(error):
    detail = getattr(error, "detail", None)
    return isinstance(error, TwoFactorError) and isinstance(detail, dict) and detail.get("login_stage") == "two_factor"


class DataError(IServError):
    pass


class PasswordError(IServError):
    pass


OUTAGE_KEY = "api.outage"
REASON_TIMEOUT = "timeout"
REASON_DNS = "dns"
REASON_REFUSED = "refused"
REASON_CONNECTION = "connection"
REASON_MAINTENANCE_PAGE = "maintenance_page"
REASON_UNEXPECTED = "unexpected"
REASON_RATE_LIMITED = "rate_limited"
DNS_MARKERS = ("nameresolutionerror", "getaddrinfo", "name or service not known", "nodename nor servname", "errno 11001")
REFUSED_MARKERS = ("connection refused", "econnrefused", "winerror 10061", "actively refused")
RATE_LIMIT_STATUS = 429
RATE_LIMIT_CAP_SECONDS = 2 * 60 * 60


class OutageError(IServError, RequestException):
    def __init__(self, reason, note="", message_key="", detail=None, retry_after=None):
        super().__init__(note or f"iserv unreachable: {reason}", message_key=message_key or OUTAGE_KEY, detail=detail)
        self.reason = str(reason or REASON_UNEXPECTED)
        self.retry_after = retry_after


def status_reason(status):
    return f"status:{int(status)}"


def parse_retry_after(value, now=None):
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return max(0, min(int(text), RATE_LIMIT_CAP_SECONDS))
    try:
        target = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    seconds = int((target - now).total_seconds())
    return max(0, min(seconds, RATE_LIMIT_CAP_SECONDS))


def rate_limit_outage(response):
    headers = getattr(response, "headers", None) or {}
    retry_after = parse_retry_after(headers.get("Retry-After"))
    detail = base_shape(response)
    if retry_after is not None:
        detail["retry_after"] = retry_after
    return OutageError(REASON_RATE_LIMITED, detail=detail, retry_after=retry_after)


def transport_reason(error):
    if isinstance(error, Timeout):
        return REASON_TIMEOUT
    haystack = " ".join(str(part) for part in _chain(error)).lower()
    if any(marker in haystack for marker in DNS_MARKERS):
        return REASON_DNS
    if any(marker in haystack for marker in REFUSED_MARKERS):
        return REASON_REFUSED
    return REASON_CONNECTION


def transport_outage(error):
    reason = transport_reason(error)
    outage = OutageError(reason, detail={"reason": reason, "failure": type(error).__name__})
    outage.__cause__ = error
    return outage


def _chain(error):
    seen = []
    current = error
    while current is not None and current not in seen and len(seen) < 8:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen
