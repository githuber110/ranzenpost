import time

from . import messages
from .store import DEFAULT_WIZARD
from .validate import is_valid_code, normalize_school_url

MAX_ATTEMPTS = 3
COOLDOWN_SECONDS = 600
TOKEN_NAME = "ISERV-Connector"
TENTATIVE_SECRET_KEYS = ("username", "password", "totp_secret", "twofactor_uuid")


class Wizard:
    def __init__(self, store, prober, now=time.time):
        self.store = store
        self.prober = prober
        self.now = now

    def status(self):
        return self._release_if_expired(self.store.load_wizard())

    def set_url(self, raw):
        state = self._release_if_expired(self.store.load_wizard())
        try:
            base = normalize_school_url(raw)
        except ValueError:
            return self._error(state, "url_invalid", "api.wizard.urlInvalid")
        if base != state.get("school_url"):
            for key in ("attempts", "paused_until", "verified_2fa", "needs_2fa_setup", "has_2fa", "awaiting_confirm", "last_code"):
                state.pop(key, None)
        result = self.prober.probe_url(base)
        if not result.get("ok"):
            code = result.get("error", "url_unreachable")
            if result.get("message_key"):
                return self._error(state, code, result["message_key"])
            if result.get("message"):
                return self._error_text(state, code, result["message"])
            return self._error(state, code, "api.wizard.urlNotIserv")
        state["school_url"] = result.get("host", base)
        state["step"] = "login"
        state.pop("error", None)
        return self._save(state)

    def set_login(self, username, password):
        state = self._release_if_expired(self.store.load_wizard())
        if self._is_paused(state):
            return self._paused(state)
        username = (username or "").strip()
        outcome = self.prober.verify_login(state.get("school_url"), username, password)
        if outcome in ("twofactor", "no_2fa"):
            self._stash_credentials(state, username, password)
            state["attempts"] = 0
            state.pop("paused_until", None)
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
                state["needs_2fa_setup"] = False
                state["verified_2fa"] = False
                state["step"] = "connect"
            return self._save(state)
        self._register_failure(state)
        if self._is_paused(state):
            return self._paused(state)
        if outcome == "locked":
            return self._error(state, "locked", "api.wizard.locked")
        if outcome == "bad_credentials":
            return self._error(state, "bad_credentials", "api.wizard.badCredentials")
        return self._error(state, "unknown", "api.wizard.unknown")

    def connect(self, code):
        state = self._release_if_expired(self.store.load_wizard())
        secrets = self.store.load_secrets()
        if self._reuse_existing_secret(state, secrets):
            return state
        if self._is_paused(state):
            return self._paused(state)
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
        status = result.get("status")
        if status in ("ok", "ok_unverified"):
            secrets["totp_secret"] = result["secret"]
            if result.get("uuid"):
                secrets["twofactor_uuid"] = result["uuid"]
            else:
                secrets.pop("twofactor_uuid", None)
            self.store.save_secrets(secrets)
            if status == "ok_unverified":
                state["unverified_reason"] = result.get("reason", "")
            else:
                state.pop("unverified_reason", None)
            state["attempts"] = 0
            state.pop("paused_until", None)
            state.pop("awaiting_confirm", None)
            state.pop("last_code", None)
            state.pop("stale_tokens", None)
            state["verified_2fa"] = True
            state["step"] = "child"
            state.pop("error", None)
            return self._save(state)
        self._register_failure(state)
        if self._is_paused(state):
            return self._paused(state)
        if status == "locked":
            return self._error(state, "locked", "api.wizard.connectLocked")
        if status == "bad_credentials":
            return self._error(state, "bad_credentials", "api.wizard.connectBadCredentials")
        if status == "network":
            return self._error(state, "network", "api.wizard.network")
        if status == "no_form":
            return self._error(state, "no_form", "api.wizard.noForm")
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
            return False
        outcome = self.prober.verify_totp(
            state.get("school_url"), secrets.get("username"), secrets.get("password"), stored
        )
        if outcome != "ok":
            return False
        state["verified_2fa"] = True
        state["reused_secret"] = True
        state["step"] = "child"
        state.pop("awaiting_confirm", None)
        state.pop("last_code", None)
        state.pop("error", None)
        self._save(state)
        return True

    def select_child(self, child_id, name="", class_name=""):
        state = self._release_if_expired(self.store.load_wizard())
        config = self.store.load_config()
        known = {child.get("child_id") for child in config.get("children", [])}
        if known and child_id not in known:
            return self._error(state, "child_unknown", "api.wizard.childUnknown")
        self._persist_child(config, child_id, name, class_name)
        state["selected_child"] = child_id
        state["step"] = "done"
        state.pop("error", None)
        return self._save(state)

    def skip_child(self):
        state = self._release_if_expired(self.store.load_wizard())
        state.pop("selected_child", None)
        state["step"] = "done"
        state.pop("error", None)
        return self._save(state)

    def reset(self):
        secrets = self.store.load_secrets()
        for key in TENTATIVE_SECRET_KEYS:
            secrets.pop(key, None)
        self.store.save_secrets(secrets)
        return self._save(dict(DEFAULT_WIZARD))

    def back(self):
        state = self._release_if_expired(self.store.load_wizard())
        steps = self._steps(state)
        current = state.get("step", "url")
        state.pop("awaiting_confirm", None)
        state.pop("last_code", None)
        if current in steps:
            index = steps.index(current)
            state["step"] = steps[max(0, index - 1)]
        else:
            state["step"] = "url"
        state.pop("error", None)
        return self._save(state)

    def _steps(self, state):
        if state.get("has_2fa") is False:
            return ["url", "login", "child"]
        return ["url", "login", "connect", "child"]

    def _persist_child(self, config, child_id, name, class_name):
        children = [dict(child) for child in config.get("children", []) if child.get("child_id") != child_id]
        entry = {"child_id": child_id}
        if name:
            entry["name"] = name
        if class_name:
            entry["class_name"] = class_name
        children.append(entry)
        config["children"] = children
        self.store.save_config(config)

    def _stash_credentials(self, state, username, password):
        secrets = self.store.load_secrets()
        if username != state.get("username") or secrets.get("username") != username:
            secrets.pop("totp_secret", None)
            secrets.pop("twofactor_uuid", None)
            state["verified_2fa"] = False
        secrets["username"] = username
        secrets["password"] = password
        self.store.save_secrets(secrets)

    def _register_failure(self, state):
        state["attempts"] = state.get("attempts", 0) + 1
        if state["attempts"] >= MAX_ATTEMPTS:
            state["paused_until"] = self.now() + COOLDOWN_SECONDS

    def _is_paused(self, state):
        return state.get("paused_until") is not None and self.now() < state["paused_until"]

    def _release_if_expired(self, state):
        if state.get("paused_until") is not None and self.now() >= state["paused_until"]:
            state.pop("paused_until", None)
            state["attempts"] = 0
            self.store.save_wizard(state)
        return state

    def _paused(self, state):
        return self._error(state, "paused", "api.wizard.paused")

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
        if not host:
            return
        config = self.store.load_config()
        if config.get("school_url") != host:
            config["school_url"] = host
            self.store.save_config(config)

    def _save(self, state):
        self._sync_school_url(state)
        self.store.save_wizard(state)
        return state
