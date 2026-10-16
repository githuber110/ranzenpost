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
REMOVAL_REFUSALS = REUSE_STOP_OUTCOMES + UNCOUNTED_LOGIN_OUTCOMES
SETUP_PHASE = "twofactor_setup"
SETUP_START = "start"
SETUP_CODE = "code"
SETUP_UNCERTAIN = "uncertain"
SETUP_DONE = "done"
SETUP_KEY = "setup_key"
UNCONFIRMED = "registration_unconfirmed"
STALE_UUIDS = "stale_uuids"
OTHER_TOKENS = "other_tokens"
STALE_REMOVED = "stale_removed"
STALE_STEPS = ("child", STEP_DONE)
LOGIN_SCOPED_KEYS = (UNCONFIRMED, STALE_UUIDS, OTHER_TOKENS, STALE_REMOVED, "stale_removable")
PREVIOUS_UUID = "previous_twofactor_uuid"

REFUSED_LOGIN_KEY = "refused_login"
REFUSED_LOGIN_SECONDS = 24 * 60 * 60
REFUSED_LOGIN_ROUNDS = 100_000


def _store_token(secrets, result):
    secrets.pop(PREVIOUS_UUID, None)
    secrets["totp_secret"] = result["secret"]
    if result.get("uuid"):
        secrets["twofactor_uuid"] = result["uuid"]
    else:
        secrets.pop("twofactor_uuid", None)


def _keep_previous_uuid(secrets):
    if secrets.get("twofactor_uuid"):
        secrets[PREVIOUS_UUID] = secrets["twofactor_uuid"]


def _split_old_tokens(old_tokens, own, new):
    mine, others = [], []
    for token in old_tokens or []:
        uuid = str(token.get("uuid") or "")
        if not uuid or uuid == new:
            continue
        if uuid == own:
            mine.append(uuid)
        else:
            others.append({"uuid": uuid, "name": TOKEN_NAME, "created": str(token.get("created") or "")})
    return mine, others


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
        if shown.get(SETUP_PHASE) == SETUP_CODE:
            key = self.prober.setup_key(state.get("school_url"), self._secrets(state).get("username"))
            if key:
                shown[SETUP_KEY] = key
            else:
                shown[SETUP_PHASE] = SETUP_START
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
        self.prober.drop_setup()
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
            _keep_previous_uuid(secrets)
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
            for key in ("verified_2fa", "needs_2fa_setup", "has_2fa", "awaiting_confirm", "last_code", SETUP_PHASE) + LOGIN_SCOPED_KEYS:
                state.pop(key, None)
        result = self.prober.probe_url(base)
        if not result.get("ok"):
            code = result.get("error", "url_unreachable")
            if result.get("message_key"):
                return self._error(state, code, result["message_key"])
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
            state.pop(SETUP_PHASE, None)
            for key in LOGIN_SCOPED_KEYS:
                state.pop(key, None)
            self.prober.drop_setup()
            if outcome == SETUP_PENDING:
                state[SETUP_PHASE] = SETUP_START
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
            state.pop(UNCONFIRMED, None)
            started = self.prober.begin_2fa(url, username, password, code, TOKEN_NAME)
            if started.get("status") == "awaiting_confirm":
                state["awaiting_confirm"] = True
                state["last_code"] = code
                state["stale_tokens"] = started.get("stale_tokens", 0)
                state["stale_removable"] = started.get("stale_removable", 0)
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
            if result.get("status") == "unconfirmed":
                state.pop("awaiting_confirm", None)
                state.pop("last_code", None)
                state[UNCONFIRMED] = True
                return self._error(state, "unconfirmed", "api.twofactor.unconfirmed")
        return self._connect_outcome(state, result)

    def _setup_pending(self, state):
        return state.get("step") == "connect" and state.get("needs_2fa_setup") is True

    def _setup_credentials(self, state):
        secrets = self._secrets(state)
        return state.get("school_url"), secrets.get("username"), secrets.get("password")

    def _setup_finished(self, state):
        state["needs_2fa_setup"] = False
        state[SETUP_PHASE] = SETUP_DONE
        state.pop("awaiting_confirm", None)
        state.pop("last_code", None)
        state.pop("error", None)
        self._clear_pause(state)
        return self._save(state)

    def _setup_without_two_factor(self, state):
        state.pop(SETUP_PHASE, None)
        state["has_2fa"] = False
        state["needs_2fa_setup"] = False
        state["verified_2fa"] = True
        state["step"] = "child"
        state.pop("error", None)
        self._clear_pause(state)
        return self._save(state)

    def start_setup(self):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        if not self._setup_pending(state):
            return self._error(state, "setup_not_pending", "api.wizard.setup.notPending")
        result = self.prober.begin_setup(*self._setup_credentials(state))
        status = result.get("status")
        if status == "awaiting_setup_code":
            state[SETUP_PHASE] = SETUP_CODE
            state.pop("error", None)
            return self._save(state)
        if status == "twofactor":
            return self._setup_finished(state)
        if status == "no_2fa":
            return self._setup_without_two_factor(state)
        state[SETUP_PHASE] = SETUP_START
        if status == "no_form":
            return self._error(state, "setup_no_form", "api.wizard.setup.noForm")
        return self._connect_outcome(state, result)

    def confirm_setup(self, code):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        if not self._setup_pending(state) or state.get(SETUP_PHASE) != SETUP_CODE:
            return self._error(state, "setup_not_pending", "api.wizard.setup.notPending")
        if not is_valid_code(code):
            return self._error(state, "code_invalid", "api.wizard.codeInvalid")
        url, username, password = self._setup_credentials(state)
        result = self.prober.confirm_setup(url, username, password, code.strip())
        status = result.get("status")
        if status == "ok":
            return self._setup_finished(state)
        if status == "rejected":
            key = "api.wizard.setup.rejectedNewKey" if result.get("key_changed") else "api.wizard.setup.rejected"
            return self._error(state, "setup_rejected", key)
        if status == "expired":
            state[SETUP_PHASE] = SETUP_START
            return self._error(state, "setup_expired", "api.wizard.setup.expired")
        state[SETUP_PHASE] = SETUP_UNCERTAIN
        return self._error(state, "setup_uncertain", "api.wizard.setup.uncertain")

    def check_setup(self):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        if not self._setup_pending(state) or state.get(SETUP_PHASE) != SETUP_UNCERTAIN:
            return self._error(state, "setup_not_pending", "api.wizard.setup.notPending")
        url, username, password = self._setup_credentials(state)
        outcome = self.prober.verify_login(url, username, password)
        if outcome == "twofactor":
            return self._setup_finished(state)
        if outcome == SETUP_PENDING:
            state[SETUP_PHASE] = SETUP_START
            return self._error(state, "setup_not_active", "api.wizard.setup.notActive")
        if outcome == "no_2fa":
            return self._setup_without_two_factor(state)
        if outcome in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, outcome, getattr(self.prober, "retry_after", None))
        if outcome in REUSE_STOP_OUTCOMES:
            return self._connect_outcome(state, {"status": outcome})
        return self._error(state, "setup_uncertain", "api.wizard.setup.uncertain")

    def check_registration(self):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        if state.get("step") != "connect" or not state.get(UNCONFIRMED):
            return self._error(state, "registration_not_pending", "api.wizard.setup.notPending")
        result = self.prober.check_registration(state.get("school_url"), self._secrets(state).get("username"), TOKEN_NAME)
        status = result.get("status")
        if status == "ok":
            return self._connect_outcome(state, result)
        if status == "unconfirmed":
            return self._error(state, "unconfirmed", "api.twofactor.unconfirmed")
        state.pop(UNCONFIRMED, None)
        return self._error(state, "registration_missing", "api.wizard.registration.missing")

    def remove_stale_tokens(self):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        secrets = self._secrets(state)
        uuids = [uuid for uuid in state.get(STALE_UUIDS) or [] if uuid != secrets.get("twofactor_uuid")]
        if not self._removal_open(state, secrets, uuids):
            return self._error(state, "stale_not_pending", "api.wizard.setup.notPending")
        result = self._remove(state, secrets, uuids)
        refused = self._removal_refused(state, result)
        if refused is not None:
            return refused
        left = [uuid for uuid in result.get("left", uuids) if uuid in uuids]
        if result.get("status") == "ok" and not left:
            state.pop(STALE_UUIDS, None)
            return self._removed(state, len(uuids))
        state[STALE_UUIDS] = left or uuids
        if result.get("status") == "partial":
            return self._error(state, "stale_partial", "api.wizard.stale.partial", {"count": len(state[STALE_UUIDS])})
        return self._error(state, "stale_failed", "api.wizard.stale.failed")

    def remove_other_token(self, uuid, confirmed):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        secrets = self._secrets(state)
        others = [dict(token) for token in state.get(OTHER_TOKENS) or []]
        chosen = uuid if isinstance(uuid, str) else ""
        offered = any(token.get("uuid") == chosen for token in others) and chosen != secrets.get("twofactor_uuid")
        if confirmed is not True or not offered or not self._removal_open(state, secrets, [chosen]):
            return self._error(state, "stale_not_pending", "api.wizard.setup.notPending")
        result = self._remove(state, secrets, [chosen])
        refused = self._removal_refused(state, result)
        if refused is not None:
            return refused
        if result.get("status") == "ok" and chosen not in (result.get("left") or []):
            kept = [token for token in others if token.get("uuid") != chosen]
            if kept:
                state[OTHER_TOKENS] = kept
            else:
                state.pop(OTHER_TOKENS, None)
            return self._removed(state, 1)
        return self._error(state, "stale_failed", "api.wizard.stale.failed")

    def _removal_open(self, state, secrets, uuids):
        return state.get("step") in STALE_STEPS and bool(uuids) and bool(secrets.get("totp_secret"))

    def _remove(self, state, secrets, uuids):
        return self.prober.remove_stale_tokens(
            state.get("school_url"), secrets.get("username"), secrets.get("password"), secrets["totp_secret"], uuids
        )

    def _removed(self, state, count):
        state[STALE_REMOVED] = int(state.get(STALE_REMOVED) or 0) + count
        state.pop("error", None)
        return self._save(state)

    def _removal_refused(self, state, result):
        status = result.get("status")
        if status in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, status, result.get("retry_after"))
        if status in REMOVAL_REFUSALS:
            return self._connect_outcome(state, {"status": status})
        return None

    def _connect_outcome(self, state, result):
        status = result.get("status")
        if status == SETUP_PENDING:
            state[SETUP_PHASE] = SETUP_START
        if status in UNCOUNTED_FAILURES:
            return self._error(state, status, UNCOUNTED_FAILURE_KEYS[status])
        if status in WAIT_OUT_OUTCOMES:
            return self._wait_out(state, status, result.get("retry_after"))
        if status in UNCOUNTED_LOGIN_OUTCOMES:
            return self._error(state, status, lockout.human_message_key(status))
        if status == "ok":
            before = self._secrets(state)
            own = before.get("twofactor_uuid") or before.get(PREVIOUS_UUID)
            mine, others = _split_old_tokens(result.get("old_tokens"), own, result.get("uuid"))
            self._edit_secrets(state, lambda secrets: _store_token(secrets, result))
            self._clear_pause(state)
            state.pop("awaiting_confirm", None)
            state.pop("last_code", None)
            state.pop("stale_tokens", None)
            state.pop("stale_removable", None)
            state.pop(UNCONFIRMED, None)
            state.pop(STALE_REMOVED, None)
            for key, value in ((STALE_UUIDS, mine), (OTHER_TOKENS, others)):
                if value:
                    state[key] = value
                else:
                    state.pop(key, None)
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
        self.prober.drop_setup()
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
            if switched:
                secrets.pop(PREVIOUS_UUID, None)
            elif seen["new"]:
                _keep_previous_uuid(secrets)
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
            fields.update(children=[], course_filters={}, timetable_source="")
        self.store.update_connection(entry["id"], **fields)

    def _forget_children(self, state):
        entry = self._entry(state)
        if entry is not None and (entry.get("children") or entry.get("course_filters") or entry.get("timetable_source")):
            self.store.update_connection(entry["id"], children=[], course_filters={}, timetable_source="")

    def _save(self, state):
        self._sync_school_url(state)
        self.store.save_wizard(state)
        return self._decorate(state)
