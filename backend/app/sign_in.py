import hashlib
import logging
import math
import threading
import time

from .iserv.client import LOGIN_SESSION_KEY, LOGIN_TWOFACTOR_KEY, LOGIN_TWOFACTOR_SETUP_KEY, REFUSAL_KEYS
from .iserv.errors import (
    REASON_BAD_CREDENTIALS,
    REASON_CODE_STEP_FAILED,
    REASON_DEFAULT_PASSWORD,
    REASON_LOCKED,
    REASON_SESSION_NOT_OPENED,
    REASON_TWOFACTOR_SETUP,
    REASON_UNKNOWN_ACCOUNT,
    LoginError,
    TwoFactorError,
    TwoFactorSetupRequired,
    code_step_failed,
    login_reason,
    session_never_opened,
)
from .iserv.totp import generate_code
from .not_configured import NotConfiguredError
from .store import LOGIN_HOLD, edit_secrets

logger = logging.getLogger(__name__)

TOTP_PERIOD = 30
EXPIRY_TRUST_SECONDS = 10 * 60
EXPIRY_TRUST_MAX_SECONDS = 24 * 60 * 60
SETUP_RETRY_SECONDS = 6 * 60 * 60
REFUSAL_WAIT_FIRST_SECONDS = 30 * 60
REFUSAL_WAIT_CAP_SECONDS = 12 * 60 * 60
REFUSAL_LEVEL_RESET_SECONDS = 24 * 60 * 60
SESSION_NOT_OPENED = REASON_SESSION_NOT_OPENED
SESSION_HOLD_FIRST_SECONDS = 5 * 60
SESSION_HOLD_CAP_SECONDS = 60 * 60
CODE_STEP_FAILED = REASON_CODE_STEP_FAILED
SHORT_HOLDS = (SESSION_NOT_OPENED, CODE_STEP_FAILED)
CODE_FAILURES_KEY = "code_failures"
CODE_FAILED_AT_KEY = "code_failed_at"
CODE_FAILURES_BEFORE_HOLD = 2
CODE_HOLDS_KEY = "code_holds"
CODE_HOLDS_BEFORE_REPAIR = 3
CODE_REPAIR_KEY = "code_repair"
CODE_REPAIR_SENT_KEY = "code_repair_sent"
CODE_REPAIR_FIELDS = (CODE_REPAIR_KEY, CODE_REPAIR_SENT_KEY)
HELD_REFUSALS = (REASON_BAD_CREDENTIALS, REASON_UNKNOWN_ACCOUNT, REASON_DEFAULT_PASSWORD, REASON_LOCKED)


def next_totp_code(secret, used=None, sleeper=time.sleep, clock=time.time):
    code = generate_code(secret)
    if used is not None and used.get("code") == code:
        now = clock()
        sleeper(max(0.0, TOTP_PERIOD - (now % TOTP_PERIOD)) + 1)
        code = generate_code(secret)
    if used is not None:
        used["code"] = code
    return code


def _code_provider(secrets, used=None, sleeper=time.sleep, clock=time.time):
    def provide():
        secret = secrets.get("totp_secret")
        if not secret:
            raise TwoFactorSetupRequired(
                "iserv asks for a two-factor code but no key is stored",
                message_key=LOGIN_TWOFACTOR_SETUP_KEY,
                detail={"login_stage": "two_factor", "key_stored": False},
            )
        return next_totp_code(secret, used, sleeper, clock)

    return provide


def sign_in_failure_reason(error):
    if session_never_opened(error):
        return SESSION_NOT_OPENED
    if code_step_failed(error):
        return CODE_STEP_FAILED
    return login_reason(error) or REASON_BAD_CREDENTIALS


def _sign_in_fingerprint(secrets):
    material = "\x00".join(
        str(secrets.get(name) or "") for name in ("username", "password", "totp_secret")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _login_hold_of(secrets, fingerprint, now):
    hold = secrets.get(LOGIN_HOLD)
    if not isinstance(hold, dict) or hold.get("fingerprint") != fingerprint:
        return None
    until = _stored_time(hold.get("until"))
    if until is None or now >= until or until - now > REFUSAL_WAIT_CAP_SECONDS:
        return None
    return hold


def _stored_seconds(entry, name):
    value = entry.get(name)
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _stored_time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _refused_at(previous):
    stamp = _stored_time(previous.get("refused_at"))
    if stamp is not None:
        return stamp
    until = _stored_time(previous.get("until"))
    return None if until is None else until - min(_stored_seconds(previous, "wait"), REFUSAL_WAIT_CAP_SECONDS)


def _recent_code_count(previous, now, name, cap):
    stamp = _stored_time(previous.get(CODE_FAILED_AT_KEY))
    if stamp is None or not 0 <= now - stamp < REFUSAL_LEVEL_RESET_SECONDS:
        return 0
    return min(_stored_seconds(previous, name), cap)


def _recent_code_failures(previous, now):
    return _recent_code_count(previous, now, CODE_FAILURES_KEY, CODE_FAILURES_BEFORE_HOLD)


def _recent_code_holds(previous, now):
    if previous.get("reason") != CODE_STEP_FAILED:
        return 0
    return _recent_code_count(previous, now, CODE_HOLDS_KEY, CODE_HOLDS_BEFORE_REPAIR)


def _login_hold_fields(reason, previous, now):
    if reason == REASON_TWOFACTOR_SETUP:
        return {"wait": SETUP_RETRY_SECONDS}
    held_refusal = previous.get("reason") in HELD_REFUSALS
    level = min(_stored_seconds(previous, "wait" if held_refusal else "refusal_wait"), REFUSAL_WAIT_CAP_SECONDS)
    refused_at = _refused_at(previous) if level else None
    if refused_at is not None and now - refused_at >= REFUSAL_LEVEL_RESET_SECONDS:
        level = 0
    if reason not in SHORT_HOLDS:
        wait = min(level * 2, REFUSAL_WAIT_CAP_SECONDS) if level else REFUSAL_WAIT_FIRST_SECONDS
        return {"wait": wait, "refused_at": now}
    last = _stored_seconds(previous, "session_wait") if previous.get("reason") in SHORT_HOLDS else 0
    session = min(max(last * 2, SESSION_HOLD_FIRST_SECONDS), SESSION_HOLD_CAP_SECONDS)
    fields = {"wait": max(session, level), "session_wait": session}
    if level:
        fields["refusal_wait"] = level
        if refused_at is not None:
            fields["refused_at"] = refused_at
    return fields


def _held_login_error(hold):
    reason = str(hold.get("reason") or REASON_BAD_CREDENTIALS)
    if reason == REASON_TWOFACTOR_SETUP:
        return TwoFactorSetupRequired("two-factor setup still pending", message_key=LOGIN_TWOFACTOR_SETUP_KEY)
    if reason == SESSION_NOT_OPENED:
        return TwoFactorError(
            "sign-in held after a session that never opened",
            message_key=LOGIN_SESSION_KEY,
            detail={"login_stage": "session", "held": True},
        )
    if reason == CODE_STEP_FAILED:
        return TwoFactorError(
            "sign-in held after the code step failed",
            message_key=LOGIN_TWOFACTOR_KEY,
            detail={"login_stage": "two_factor", "held": True},
        )
    return LoginError(
        "sign-in held after a refusal",
        message_key=REFUSAL_KEYS.get(reason, REFUSAL_KEYS[REASON_BAD_CREDENTIALS]),
        reason=reason,
    )


class SignInService:
    def __init__(self, connection):
        self.connection = connection
        self._client = None
        self._last_code = {}
        self._session_lock = threading.RLock()
        self._signed_in_at = 0.0
        self._forced_relogin_at = 0.0
        self._expiry_window = EXPIRY_TRUST_SECONDS
        self._fresh_refusal_logged = False

    def _login(self, timeout=None):
        with self._session_lock:
            client = self._client
            if client is not None and client.is_authenticated():
                return client
            return self._login_now(timeout)

    def _login_now(self, timeout=None):
        config = self.connection.store.load_config()
        secrets = self.connection.store.load_secrets()
        if not config.get("school_url") or not secrets.get("username"):
            raise NotConfiguredError("school url or credentials missing")
        held = self.connection._outage_hold(self.connection.clock())
        if held is not None:
            raise held
        fingerprint = _sign_in_fingerprint(secrets)
        hold = _login_hold_of(secrets, fingerprint, self.connection.clock())
        if hold is not None:
            raise _held_login_error(hold)
        client = self.connection.client_factory(config["school_url"])
        if timeout is not None:
            client.timeout = timeout
        try:
            client.login(
                secrets["username"],
                secrets["password"],
                _code_provider(secrets, self._last_code),
            )
        except TwoFactorSetupRequired:
            self._hold_login(fingerprint, REASON_TWOFACTOR_SETUP)
            raise
        except LoginError as error:
            if error.reason in HELD_REFUSALS:
                self._hold_login(fingerprint, error.reason)
            raise
        except TwoFactorError as error:
            if code_step_failed(error):
                self._count_code_failure(fingerprint, error)
            elif session_never_opened(error):
                self._hold_login(fingerprint, SESSION_NOT_OPENED)
            raise
        self._release_login_hold(fingerprint)
        self._client = client
        self._signed_in_at = self.connection.clock()
        self.connection._detect_modules(client)
        return client

    def session_not_opened_held(self):
        secrets = self.connection.store.load_secrets()
        hold = _login_hold_of(secrets, _sign_in_fingerprint(secrets), self.connection.clock())
        return hold is not None and hold.get("reason") == SESSION_NOT_OPENED

    def _code_record(self):
        secrets = self.connection.store.load_secrets()
        record = secrets.get(LOGIN_HOLD)
        if not isinstance(record, dict) or record.get("fingerprint") != _sign_in_fingerprint(secrets):
            return {}
        return record

    def code_refused_since_sign_in(self):
        return _recent_code_failures(self._code_record(), self.connection.clock()) > 0

    def code_refusal_needs_setup(self):
        return self._code_record().get(CODE_REPAIR_KEY) is True

    def code_repair_announced(self):
        return self._code_record().get(CODE_REPAIR_SENT_KEY) is True

    def note_code_repair_announced(self):
        def note(secrets):
            record = secrets.get(LOGIN_HOLD)
            if not isinstance(record, dict) or record.get("fingerprint") != _sign_in_fingerprint(secrets):
                return
            if record.get(CODE_REPAIR_KEY) is True:
                record[CODE_REPAIR_SENT_KEY] = True

        edit_secrets(self.connection.store, note)

    def _hold_login(self, fingerprint, reason):
        edit_secrets(self.connection.store, lambda secrets: self._put_login_hold(secrets, fingerprint, reason))

    def _count_code_failure(self, fingerprint, error):
        reason = SESSION_NOT_OPENED if session_never_opened(error) else CODE_STEP_FAILED

        def count(secrets):
            if _sign_in_fingerprint(secrets) != fingerprint:
                return
            previous = secrets.get(LOGIN_HOLD)
            previous = previous if isinstance(previous, dict) and previous.get("fingerprint") == fingerprint else {}
            now = self.connection.clock()
            failures = _recent_code_failures(previous, now) + 1
            counted = {CODE_FAILURES_KEY: failures, CODE_FAILED_AT_KEY: now}
            if failures < CODE_FAILURES_BEFORE_HOLD:
                secrets[LOGIN_HOLD] = dict(previous, fingerprint=fingerprint, **counted)
                secrets[LOGIN_HOLD].pop(CODE_HOLDS_KEY, None)
                return
            if reason == CODE_STEP_FAILED:
                holds = min(_recent_code_holds(previous, now) + 1, CODE_HOLDS_BEFORE_REPAIR)
                counted[CODE_HOLDS_KEY] = holds
                if holds >= CODE_HOLDS_BEFORE_REPAIR:
                    counted[CODE_REPAIR_KEY] = True
            self._put_login_hold(secrets, fingerprint, reason)
            secrets[LOGIN_HOLD].update(counted)

        edit_secrets(self.connection.store, count)

    def _put_login_hold(self, secrets, fingerprint, reason):
        if _sign_in_fingerprint(secrets) != fingerprint:
            return
        previous = secrets.get(LOGIN_HOLD)
        previous = previous if isinstance(previous, dict) and previous.get("fingerprint") == fingerprint else {}
        now = self.connection.clock()
        fields = _login_hold_fields(reason, previous, now)
        kept = {name: previous[name] for name in CODE_REPAIR_FIELDS if name in previous}
        secrets[LOGIN_HOLD] = dict(fields, **kept, fingerprint=fingerprint, reason=reason, until=now + fields["wait"])

    def _release_login_hold(self, fingerprint):
        def release(secrets):
            hold = secrets.get(LOGIN_HOLD)
            owner = hold.get("fingerprint") if isinstance(hold, dict) else None
            if owner is not None and owner != fingerprint and owner == _sign_in_fingerprint(secrets):
                return
            secrets.pop(LOGIN_HOLD, None)

        edit_secrets(self.connection.store, release)

    def _session(self):
        with self._session_lock:
            if self._client is None or not self._client.is_authenticated():
                return self.connection._login()
            return self._client

    def _trust_school_app(self):
        if self._expiry_window != EXPIRY_TRUST_SECONDS:
            with self._session_lock:
                self._expiry_window = EXPIRY_TRUST_SECONDS
                self._fresh_refusal_logged = False

    def _forget_session(self, client):
        with self._session_lock:
            if self._client is not client:
                return
            now = self.connection.clock()
            age = now - self._signed_in_at
            window = self._expiry_window
            if age < window or now - self._forced_relogin_at < window:
                if not self._fresh_refusal_logged:
                    logger.warning(
                        "school#%s school app refused a fresh session, keeping it for up to %d minutes",
                        self.connection.id,
                        window // 60,
                    )
                    self._fresh_refusal_logged = True
                return
            if age < 2 * window:
                self._expiry_window = min(window * 2, EXPIRY_TRUST_MAX_SECONDS)
            else:
                self._expiry_window = EXPIRY_TRUST_SECONDS
            if self._expiry_window != window:
                self._fresh_refusal_logged = False
            logger.info("school#%s school app session expired, signing in again on the next request", self.connection.id)
            self._forced_relogin_at = now
            self.drop_session()

    def drop_session(self):
        with self._session_lock:
            self._client = None
