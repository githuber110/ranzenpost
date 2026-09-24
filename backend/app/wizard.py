import hashlib
import secrets as secrets_module
import time

from . import lockout, messages, signin_pause
from .signin_pause import MAX_ATTEMPTS, PAUSES, WAIT_OUT_OUTCOMES
from .store import DEFAULT_WIZARD, LOGIN_HOLD, LOGIN_REVISION_KEY, edit, host_of
from .validate import is_valid_code, normalize_school_url

TOKEN_NAME = "ISERV-Connector"
TENTATIVE_SECRET_KEYS = ("username", "password", "totp_secret", "twofactor_uuid", "refused_login")
STEP_DONE = "done"
STEP_URL = "url"
CREATED_FLAG = "created_connection"
ACCOUNT_KEY = "account_fingerprint"
SCHOOL_KEY = "school_identity"
DEFAULT_PORTS = (":443", ":80")
LEGACY_PAUSE_KEYS = ("paused_until", "pause_reason", "paused_school")
SETUP_PENDING = lockout.TWOFACTOR_REQUIRED_SETUP
UNCOUNTED_FAILURES = ("network", "no_form", SETUP_PENDING)
UNCOUNTED_FAILURE_KEYS = {
    "network": "api.wizard.network",
    "no_form": "api.wizard.noForm",
    SETUP_PENDING: "api.wizard.twofactorSetupPending",
}
UNCOUNTED_LOGIN_OUTCOMES = ("password_expired", lockout.DEFAULT_PASSWORD_BLOCKED)
REUSE_STOP_OUTCOMES = (
    lockout.BAD_CREDENTIALS,
    lockout.LOCKED,
    lockout.UNKNOWN_ACCOUNT,
    lockout.DEFAULT_PASSWORD_BLOCKED,
)
BLOCKING_ERRORS = ("paused", "locked")

REFUSED_LOGIN_KEY = "refused_login"
REFUSED_LOGIN_SECONDS = 24 * 60 * 60
REFUSED_LOGIN_ROUNDS = 100_000


def _store_token(secrets, result):
    secrets["totp_secret"] = result["secret"]
    if result.get("uuid"):
        secrets["twofactor_uuid"] = result["uuid"]
    else:
        secrets.pop("twofactor_uuid", None)


def account_fingerprint(username):
    return hashlib.sha256(str(username or "").strip().casefold().encode("utf-8")).hexdigest()


def school_identity(url):
    host = host_of(url).casefold()
    for port in DEFAULT_PORTS:
        if host.endswith(port):
            host = host[: -len(port)]
    return host


def login_fingerprint(school_url, username, password, salt):
    joined = "\n".join((str(school_url or ""), account_fingerprint(username), str(password or "")))
    return hashlib.pbkdf2_hmac("sha256", joined.encode("utf-8"), bytes.fromhex(salt), REFUSED_LOGIN_ROUNDS).hex()


class Wizard:
    def __init__(self, store, prober, now=time.time):
        self.store = store
        self.prober = prober
        self.now = now

    def status(self):
        return self._decorate(self._release_if_expired(self.store.load_wizard()))

    def _connection_id(self, state):
        connection_id = str(state.get("connection_id") or "")
        if connection_id and self.store.connection(connection_id) is None:
            state.pop("connection_id", None)
            return ""
        return connection_id

    def _entry(self, state):
        connection_id = self._connection_id(state)
        return self.store.connection(connection_id) if connection_id else None

    def _secrets(self, state):
        connection_id = self._connection_id(state)
        return self.store.load_secrets(connection_id) if connection_id else {}

    def _other_complete(self, state):
        connection_id = str(state.get("connection_id") or "")
        return any(
            entry.get("setup_complete") and entry["id"] != connection_id for entry in self.store.connections()
        )

    def _decorate(self, state):
        shown = dict(state)
        shown["additional"] = self._other_complete(state)
        entry = self._pause_entry(state)
        shown["attempts"] = entry.get("attempts", 0)
        if self._is_paused(state):
            shown["retry_in"] = signin_pause.seconds_left(entry, self.now())
        return shown

    def _fresh(self, state, base=None):
        fresh = dict(base or DEFAULT_WIZARD)
        if state.get(PAUSES):
            fresh[PAUSES] = state[PAUSES]
        return fresh

    def start_new(self):
        state = self._release_if_expired(self.store.load_wizard())
        entry = self._entry(state)
        if entry is not None and not entry.get("setup_complete") and state.get("step") != STEP_DONE:
            return self._decorate(state)
        return self._save(self._fresh(state))

    def cancel(self):
        state = self.store.load_wizard()
        entry = self._entry(state)
        if entry is not None and not entry.get("setup_complete"):
            self._drop_entry(state)
        if any(item.get("setup_complete") for item in self.store.connections()):
            return self._save(self._fresh(state, {"step": STEP_DONE, "attempts": 0}))
        return self._save(self._fresh(state))

    def _edit_secrets(self, state, change):
        connection_id = self._connection_id(state)
        if connection_id:
            edit(
                self.store,
                lambda: self.store.load_secrets(connection_id),
                lambda secrets: self.store.save_secrets(connection_id, secrets),
                change,
            )

    def _drop_entry(self, state):
        entry = self._entry(state)
        if entry is None:
            return None
        if not entry.get("setup_complete") and state.get(CREATED_FLAG):
            self.store.remove_connection(entry["id"])
            return None

        def forget(secrets):
            if secrets.get("username") and not secrets.get(ACCOUNT_KEY):
                secrets[ACCOUNT_KEY] = account_fingerprint(secrets["username"])
            if entry.get("school_url") and not secrets.get(SCHOOL_KEY):
                secrets[SCHOOL_KEY] = school_identity(entry["school_url"])
            for key in TENTATIVE_SECRET_KEYS:
                secrets.pop(key, None)

        self._edit_secrets(state, forget)
        self.store.update_connection(entry["id"], setup_complete=False)
        return entry["id"]

    def set_url(self, raw):
        state = self._release_if_expired(self.store.load_wizard())
        try:
            base = normalize_school_url(raw)
        except ValueError:
            return self._error(state, "url_invalid", "api.wizard.urlInvalid")
        if base != state.get("school_url"):
            for key in ("verified_2fa", "needs_2fa_setup", "has_2fa", "awaiting_confirm", "last_code"):
                state.pop(key, None)
        result = self.prober.probe_url(base)
        if not result.get("ok"):
            code = result.get("error", "url_unreachable")
            if result.get("message_key"):
                return self._error(state, code, result["message_key"])
            if result.get("message"):
                return self._error_text(state, code, result["message"])
            return self._error(state, code, "api.wizard.urlNotIserv")
        host = result.get("host", base)
        entry = self._entry(state)
        if entry is None or (entry.get("setup_complete") and state.get("step") == STEP_DONE):
            entry = self.store.add_connection(host)
            state["connection_id"] = entry["id"]
            state[CREATED_FLAG] = True
        state["school_url"] = host
        state["step"] = "login"
        state.pop("error", None)
        return self._save(state)

    def set_login(self, username, password):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        username = (username or "").strip()
        if self._repeats_refused_login(state, username, password):
            return self._error(state, lockout.DEFAULT_PASSWORD_BLOCKED, lockout.human_message_key(lockout.DEFAULT_PASSWORD_BLOCKED))
        outcome = self.prober.verify_login(state.get("school_url"), username, password)
        if outcome in ("twofactor", "no_2fa", SETUP_PENDING):
            self._stash_credentials(state, username, password)
            self._clear_pause(state)
            state["username"] = username
            state.pop("error", None)
            state.pop("awaiting_confirm", None)
            state.pop("last_code", None)
            if outcome == "no_2fa":
                state["has_2fa"] = False
                state["needs_2fa_setup"] = False
                state["verified_2fa"] = True
                state["step"] = "child"
            else:
                state["has_2fa"] = True
                state["needs_2fa_setup"] = outcome == SETUP_PENDING
                state["verified_2fa"] = False
                state["step"] = "connect"
            return self._save(state)
        if outcome in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, outcome, getattr(self.prober, "retry_after", None))
        if outcome in UNCOUNTED_LOGIN_OUTCOMES:
            if outcome == lockout.DEFAULT_PASSWORD_BLOCKED:
                self._remember_refused_login(state, username, password)
            return self._error(state, outcome, lockout.human_message_key(outcome))
        self._register_failure(state, outcome)
        if outcome == lockout.CAPTCHA:
            return self._error(state, outcome, lockout.human_message_key(outcome))
        if self._is_paused(state):
            return self._paused(state)
        if outcome == "bad_credentials":
            return self._error(state, "bad_credentials", "api.wizard.badCredentials")
        if outcome == lockout.UNKNOWN_ACCOUNT:
            return self._error(state, outcome, lockout.human_message_key(outcome))
        return self._error(state, "unknown", "api.wizard.unknown")

    def connect(self, code):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        secrets = self._secrets(state)
        reused = self._reuse_existing_secret(state, secrets)
        if reused == "ok":
            return self._decorate(state)
        if reused in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, reused, getattr(self.prober, "retry_after", None))
        if reused in REUSE_STOP_OUTCOMES:
            return self._connect_outcome(state, {"status": reused})
        if not is_valid_code(code):
            return self._error(state, "code_invalid", "api.wizard.codeInvalid")
        code = code.strip()
        url = state.get("school_url")
        username = secrets.get("username")
        password = secrets.get("password")
        if not state.get("awaiting_confirm"):
            started = self.prober.begin_2fa(url, username, password, code, TOKEN_NAME)
            if started.get("status") == "awaiting_confirm":
                state["awaiting_confirm"] = True
                state["last_code"] = code
                state["stale_tokens"] = started.get("stale_tokens", 0)
                state.pop("error", None)
                return self._save(state)
            result = started
        elif code == state.get("last_code"):
            return self._error(state, "same_code", "api.wizard.sameCode")
        else:
            result = self.prober.confirm_2fa(url, username, password, code, TOKEN_NAME)
            if result.get("status") == "expired":
                state.pop("awaiting_confirm", None)
                state.pop("last_code", None)
                return self._error(state, "expired", "api.wizard.expired")
        return self._connect_outcome(state, result)

    def _connect_outcome(self, state, result):
        status = result.get("status")
        if status in UNCOUNTED_FAILURES:
            return self._error(state, status, UNCOUNTED_FAILURE_KEYS[status])
        if status in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, status, result.get("retry_after"))
        if status in UNCOUNTED_LOGIN_OUTCOMES:
            return self._error(state, status, lockout.human_message_key(status))
        if status in ("ok", "ok_unverified"):
            self._edit_secrets(state, lambda secrets: _store_token(secrets, result))
            if status == "ok_unverified":
                state["unverified_reason"] = result.get("reason", "")
            else:
                state.pop("unverified_reason", None)
            self._clear_pause(state)
            state.pop("awaiting_confirm", None)
            state.pop("last_code", None)
            state.pop("stale_tokens", None)
            state["verified_2fa"] = True
            state["step"] = "child"
            state.pop("error", None)
            return self._save(state)
        self._register_failure(state, status)
        if self._is_paused(state):
            return self._paused(state)
        if status == "bad_credentials":
            return self._error(state, "bad_credentials", "api.wizard.connectBadCredentials")
        if status == lockout.UNKNOWN_ACCOUNT:
            return self._error(state, status, lockout.human_message_key(status))
        if status in ("bad_code", "code_rejected"):
            state.pop("awaiting_confirm", None)
            state.pop("last_code", None)
            detail = (result.get("message") or "").strip()
            if detail:
                return self._error(state, "code_rejected", "api.wizard.codeRejectedDetail", {"detail": detail})
            return self._error(state, "code_rejected", "api.wizard.codeRejected")
        return self._error(state, "verify_failed", "api.wizard.verifyFailed")

    def _reuse_existing_secret(self, state, secrets):
        stored = secrets.get("totp_secret")
        if not stored:
            return None
        outcome = self.prober.verify_totp(
            state.get("school_url"), secrets.get("username"), secrets.get("password"), stored
        )
        if outcome != "ok":
            return outcome
        state["verified_2fa"] = True
        state["reused_secret"] = True
        state["step"] = "child"
        state.pop("awaiting_confirm", None)
        state.pop("last_code", None)
        state.pop("error", None)
        self._save(state)
        return outcome

    def select_child(self, child_id, name="", class_name=""):
        state = self._release_if_expired(self.store.load_wizard())
        child_id = str(child_id or "").strip()
        if state.get("step") not in ("child", STEP_DONE) or not self._offered_child(state, child_id):
            return self._error(state, "child_unknown", "api.wizard.childUnknown")
        self._persist_child(state, child_id, name, class_name)
        state["selected_child"] = child_id
        state["step"] = STEP_DONE
        state.pop("error", None)
        return self._save(state)

    def skip_child(self):
        state = self._release_if_expired(self.store.load_wizard())
        state.pop("selected_child", None)
        self._complete(state)
        state["step"] = STEP_DONE
        state.pop("error", None)
        return self._save(state)

    def reset(self, connection_id=None):
        state = self.store.load_wizard()
        if connection_id:
            if connection_id != state.get("connection_id"):
                state.pop(CREATED_FLAG, None)
            state["connection_id"] = connection_id
        fresh = self._fresh(state)
        kept = self._drop_entry(state)
        if kept:
            fresh["connection_id"] = kept
        return self._save(fresh)

    def back(self):
        state = self._release_if_expired(self.store.load_wizard())
        steps = self._steps(state)
        current = state.get("step", STEP_URL)
        state.pop("awaiting_confirm", None)
        state.pop("last_code", None)
        if current in steps:
            index = steps.index(current)
            state["step"] = steps[max(0, index - 1)]
        else:
            state["step"] = STEP_URL
        state.pop("error", None)
        return self._save(state)

    def _steps(self, state):
        if state.get("has_2fa") is False:
            return [STEP_URL, "login", "child"]
        return [STEP_URL, "login", "connect", "child"]

    def _offered_child(self, state, child_id):
        wanted = str(child_id or "").strip()
        entry = self._entry(state)
        if not wanted or entry is None:
            return False
        return any(str(child.get("child_id") or "") == wanted for child in entry.get("children") or [])

    def _persist_child(self, state, child_id, name, class_name):
        entry = self._entry(state)
        if entry is None:
            return
        children = [dict(child) for child in entry.get("children", []) if child.get("child_id") != child_id]
        item = {"child_id": child_id}
        if name:
            item["name"] = name
        if class_name:
            item["class_name"] = class_name
        children.append(item)
        self.store.update_connection(entry["id"], children=children, setup_complete=True)

    def _complete(self, state):
        entry = self._entry(state)
        if entry is not None:
            self.store.update_connection(entry["id"], setup_complete=True)

    def _stash_credentials(self, state, username, password):
        account = account_fingerprint(username)
        school = school_identity(state.get("school_url"))
        switched = self._switches_login(self._secrets(state), account, school)
        if switched:
            self._forget_children(state)
        seen = {"new": True}

        def stash(secrets):
            seen["new"] = username != state.get("username") or secrets.get("username") != username
            secrets[ACCOUNT_KEY] = account
            if school:
                secrets[SCHOOL_KEY] = school
            if seen["new"]:
                secrets.pop("totp_secret", None)
                secrets.pop("twofactor_uuid", None)
            secrets["username"] = username
            secrets["password"] = password
            secrets.pop(LOGIN_HOLD, None)
            secrets.pop(REFUSED_LOGIN_KEY, None)

        self._edit_secrets(state, stash)
        if seen["new"]:
            state["verified_2fa"] = False
        self._bump_login_revision(state, forget_children=switched)

    @staticmethod
    def _switches_login(secrets, account, school):
        previous = secrets.get(ACCOUNT_KEY) or (account_fingerprint(secrets["username"]) if secrets.get("username") else "")
        previous_school = secrets.get(SCHOOL_KEY) or ""
        return bool((previous and previous != account) or (previous_school and school and previous_school != school))

    def _pause_entry(self, state):
        return (state.get(PAUSES) or {}).get(state.get("school_url") or "") or {}

    def _register_failure(self, state, reason):
        self._put_pause(state, signin_pause.register_failure(self._pause_entry(state), reason, self.now()))

    def _put_pause(self, state, entry):
        pauses = dict(state.get(PAUSES) or {})
        pauses[state.get("school_url") or ""] = entry
        state[PAUSES] = pauses

    def _wait_out(self, state, outcome, retry_after):
        wait = signin_pause.wait_for(outcome, retry_after)
        if wait is None:
            return self._error(state, "outage", "api.wizard.outage")
        self._put_pause(state, signin_pause.hold(self._pause_entry(state), outcome, wait, self.now()))
        return self._paused(state)

    def _clear_pause(self, state):
        pauses = dict(state.get(PAUSES) or {})
        pauses.pop(state.get("school_url") or "", None)
        self._store_pauses(state, pauses)

    def _store_pauses(self, state, pauses):
        if pauses:
            state[PAUSES] = pauses
        else:
            state.pop(PAUSES, None)

    def _is_paused(self, state):
        return signin_pause.is_paused(self._pause_entry(state), self.now())

    def _adopt_legacy_pause(self, state):
        if not any(key in state for key in LEGACY_PAUSE_KEYS):
            return False
        until = state.get("paused_until")
        school = state.get("school_url") or state.get("paused_school")
        if until is not None and school and self.now() < until:
            pauses = dict(state.get(PAUSES) or {})
            pauses[school] = {
                "attempts": MAX_ATTEMPTS,
                "reason": state.get("pause_reason") or "bad_credentials",
                "last": self.now(),
                "until": until,
            }
            state[PAUSES] = pauses
        for key in LEGACY_PAUSE_KEYS:
            state.pop(key, None)
        return True

    def _release_if_expired(self, state):
        changed = self._adopt_legacy_pause(state)
        now = self.now()
        pauses = state.get(PAUSES) or {}
        kept = signin_pause.live_pauses(pauses, now)
        if kept != pauses:
            self._store_pauses(state, kept)
            changed = True
        if not self._is_paused(state) and (state.get("error") or {}).get("code") in BLOCKING_ERRORS:
            state.pop("error", None)
            changed = True
        if changed:
            self.store.save_wizard(state)
        return state

    def _paused(self, state):
        return self._error(state, "paused", signin_pause.message_key(self._pause_entry(state)))

    def _error(self, state, code, key, variables=None):
        error = {"code": code}
        error.update(messages.payload(key, variables))
        state["error"] = error
        return self._save(state)

    def _error_text(self, state, code, message):
        state["error"] = {"code": code, "message": message}
        return self._save(state)

    def _sync_school_url(self, state):
        host = state.get("school_url")
        entry = self._entry(state)
        if not host or entry is None:
            return
        if entry.get("school_url") == host:
            return
        self.store.update_connection(entry["id"], school_url=host)

    def _repeats_refused_login(self, state, username, password):
        refused = self._secrets(state).get(REFUSED_LOGIN_KEY)
        if not isinstance(refused, dict) or float(refused.get("until") or 0) <= self.now():
            return False
        try:
            attempt = login_fingerprint(state.get("school_url"), username, password, refused.get("salt", ""))
        except ValueError:
            return False
        return secrets_module.compare_digest(attempt, str(refused.get("login") or ""))

    def _remember_refused_login(self, state, username, password):
        if not self._connection_id(state):
            return
        salt = secrets_module.token_hex(16)
        refused = {
            "salt": salt,
            "login": login_fingerprint(state.get("school_url"), username, password, salt),
            "until": self.now() + REFUSED_LOGIN_SECONDS,
        }
        self._edit_secrets(state, lambda secrets: secrets.__setitem__(REFUSED_LOGIN_KEY, refused))

    def _bump_login_revision(self, state, forget_children=False):
        entry = self._entry(state)
        if entry is None:
            return
        fields = {LOGIN_REVISION_KEY: int(entry.get(LOGIN_REVISION_KEY) or 0) + 1}
        if forget_children:
            fields.update(children=[], course_filters={})
        self.store.update_connection(entry["id"], **fields)

    def _forget_children(self, state):
        entry = self._entry(state)
        if entry is not None and (entry.get("children") or entry.get("course_filters")):
            self.store.update_connection(entry["id"], children=[], course_filters={})

    def _save(self, state):
        self._sync_school_url(state)
        self.store.save_wizard(state)
        return self._decorate(state)
