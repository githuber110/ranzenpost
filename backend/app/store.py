import contextlib
import copy
import json
import os
import secrets as secret_tokens
import threading
import time
from pathlib import Path

from . import atomic_write, blocks, crypto
from .mapping import migrate_subject_colors

CORRUPT_SUFFIX = ".corrupt"
SCHEMA_VERSION = 2
CONNECTION_ID_BYTES = 4
KEY_SEPARATOR = ":"
SECRETS_DIR_NAME = "secrets"
SECRETS_SUFFIX = ".enc"
LEGACY_SECRETS_NAME = "secrets.enc"
LOGIN_HOLD = "login_hold"
LOGIN_REVISION_KEY = "login_revision"

NOTIFY_EVENT_DEFAULTS = {
    "timetable": True,
    "letters": True,
    "pinboard": True,
    "conferences": True,
    "messenger": True,
}

DEFAULT_CONFIG = {
    "schema_version": SCHEMA_VERSION,
    "language": "system",
    "notify_services": [],
    "notify_events": dict(NOTIFY_EVENT_DEFAULTS),
    "reported_modules": [],
    "modules_card_hidden": {},
    "overview_blocks": None,
    "navigation": None,
    "modules_disabled": [],
    "connections": [],
}

CONNECTION_DEFAULTS = {
    "id": "",
    "school_url": "",
    "school_name": "",
    "label": "",
    "short_name": "",
    "created_at": 0,
    "setup_complete": False,
    "children": [],
    "subjects": {},
    "teachers": {},
    "period_times": {},
    "period_grid": {},
    "own_entries": [],
    "own_entries_ha": False,
    "phones": [],
    "holiday_region": "",
    "course_filters": {},
    "poll_state": {},
    "timetable_source": "",
    "children_state": "",
}

CHILDREN_STATE_KEY = "children_state"
CHILDREN_LISTED = "listed"
CHILDREN_REFUSED = "refused"
CHILDREN_UNREADABLE = "unreadable"
CHILDREN_STATES = (CHILDREN_LISTED, CHILDREN_REFUSED, CHILDREN_UNREADABLE)

GLOBAL_SETTING_KEYS = (
    "language",
    "notify_services",
    "notify_events",
    "reported_modules",
    "modules_card_hidden",
    "overview_blocks",
    "navigation",
    "modules_disabled",
)
LAYOUT_KEYS = ("overview_blocks", "navigation", "modules_disabled")
CONNECTION_SETTING_KEYS = (
    "label",
    "short_name",
    "subjects",
    "teachers",
    "period_times",
    "phones",
    "holiday_region",
    "own_entries_ha",
)
CONNECTION_FIELD_KEYS = tuple(key for key in CONNECTION_DEFAULTS if key != "id")
LEGACY_CONNECTION_KEYS = (
    "school_url",
    "children",
    "subjects",
    "teachers",
    "period_times",
    "phones",
    "holiday_region",
    "poll_state",
)
POLL_STATE_MODULE_KEYS = ("letter_keys", "pinboard_ids", "conference_keys", "messenger_unread")
NESTED_FILE_NAMES = (
    "seen.json",
    "absence_history.json",
    "letters_search_cache.json",
    "letters_confirmations.json",
    "modules.json",
)
INTEGRATION_SCHOOLS_KEY = "schools"
INTEGRATION_SCHOOL_KEYS = ("last_poll", "last_poll_ok", "last_error", "letters", "posts", "conferences", "school_name")

DEFAULT_WIZARD = {"step": "url", "attempts": 0}

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def directory_key(directory):
    return os.path.normcase(str(Path(directory).resolve()))


def lock_for(directory):
    key = directory_key(directory)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def transaction(target):
    lock = getattr(target, "lock", None)
    return lock if lock is not None else contextlib.nullcontext()


def edit(target, load, save, change):
    with transaction(target):
        data = load()
        before = copy.deepcopy(data)
        change(data)
        if data != before:
            save(data)
        return data


def edit_config(target, change):
    editor = getattr(target, "edit_config", None)
    if callable(editor):
        return editor(change)
    return edit(target, target.load_config, lambda data: target.save_config(data), change)


def edit_slot(target, kind, change):
    editor = getattr(type(target), "edit_slot", None)
    if callable(editor):
        return target.edit_slot(kind, change)
    return edit(target, getattr(target, f"load_{kind}"), lambda data: getattr(target, f"save_{kind}")(data), change)


def edit_secrets(target, change):
    editor = getattr(type(target), "edit_secrets", None)
    if callable(editor):
        return target.edit_secrets(change)
    return edit(target, target.load_secrets, target.save_secrets, change)


def connection_known(target, connection_id):
    base = getattr(target, "base", target)
    if not callable(getattr(type(base), "connection", None)):
        return True
    return base.connection(connection_id) is not None


def rebase(fresh, before, after, depth):
    if depth <= 0 or not isinstance(before, dict) or not isinstance(after, dict):
        return copy.deepcopy(after)
    result = dict(fresh) if isinstance(fresh, dict) else {}
    for key in set(before) | set(after):
        if key not in after:
            result.pop(key, None)
            continue
        old = before.get(key, {} if isinstance(after[key], dict) else None)
        if key not in before or old != after[key]:
            result[key] = rebase(result.get(key), old, after[key], depth - 1)
    return result


def new_connection_id():
    return secret_tokens.token_hex(CONNECTION_ID_BYTES)


def child_key(connection_id, child_id):
    return f"{connection_id}{KEY_SEPARATOR}{child_id}"


def split_child_key(key):
    text = str(key or "")
    connection_id, separator, child_id = text.partition(KEY_SEPARATOR)
    if not separator or not connection_id or not child_id:
        return "", ""
    return connection_id, child_id


def connection_of_key(key):
    return split_child_key(key)[0]


def normalize_connection(entry):
    merged = dict(CONNECTION_DEFAULTS)
    if isinstance(entry, dict):
        merged.update(entry)
    merged["children"] = [child for child in (merged.get("children") or []) if isinstance(child, dict)]
    for name in ("subjects", "teachers", "period_times", "period_grid", "course_filters", "poll_state"):
        if not isinstance(merged.get(name), dict):
            merged[name] = {}
    for name in ("phones", "own_entries"):
        if not isinstance(merged.get(name), list):
            merged[name] = []
    merged["own_entries_ha"] = merged.get("own_entries_ha") is True
    merged["timetable_source"] = merged["timetable_source"] if isinstance(merged.get("timetable_source"), str) else ""
    merged[CHILDREN_STATE_KEY] = merged[CHILDREN_STATE_KEY] if merged.get(CHILDREN_STATE_KEY) in CHILDREN_STATES else ""
    merged["id"] = str(merged.get("id") or "")
    return migrate_subject_colors(merged)


def connection_display_name(entry):
    entry = entry or {}
    for name in ("label", "school_name"):
        text = " ".join(str(entry.get(name) or "").split())
        if text:
            return text
    return host_of(entry.get("school_url"))


def host_of(url):
    text = str(url or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].split("@")[-1]


def default_short_name(url):
    host = host_of(url).split(":", 1)[0]
    labels = [label for label in host.split(".") if label]
    if len(labels) > 1:
        labels = labels[:-1]
    return ".".join(labels)


def connection_short_name(entry):
    entry = entry or {}
    text = " ".join(str(entry.get("short_name") or "").split())
    return text or default_short_name(entry.get("school_url"))


def children_of_connection(entry):
    entry = normalize_connection(entry)
    listed = []
    for child in entry["children"]:
        child_id = str(child.get("child_id") or "")
        if not child_id:
            continue
        item = dict(child)
        item["child_id"] = child_id
        item["connection_id"] = entry["id"]
        item["key"] = child_key(entry["id"], child_id)
        listed.append(item)
    return listed


def normalize_layout(config):
    disabled = blocks.normalize_modules_disabled(config.get("modules_disabled"))
    return {
        "overview_blocks": blocks.normalize_overview_blocks(config.get("overview_blocks"), disabled),
        "navigation": blocks.normalize_navigation(config.get("navigation")),
        "modules_disabled": disabled,
    }


def children_of_config(config):
    config = config or {}
    listed = config.get("connections")
    if isinstance(listed, list):
        children = []
        for entry in listed:
            children.extend(children_of_connection(entry))
        return children
    return children_of_connection(
        {
            "id": config.get("connection_id") or config.get("id") or "",
            "children": config.get("children") or [],
        }
    )


def config_for_child(store, key):
    connection_id = connection_of_key(key)
    base = getattr(store, "base", store)
    scoped = getattr(base, "connection_store", None)
    if connection_id and callable(scoped):
        return scoped(connection_id).load_config()
    return store.load_config()


def config_for_connection(store, connection_id):
    base = getattr(store, "base", store)
    scoped = getattr(base, "connection_store", None)
    if connection_id and callable(scoped):
        return scoped(connection_id).load_config()
    return store.load_config()


def _wrapped_under(data, connection_id):
    return isinstance(data, dict) and (not data or set(data) == {connection_id})


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = lock_for(self.dir)
        self.config_path = self.dir / "config.json"
        self.secrets_dir = self.dir / SECRETS_DIR_NAME
        self.legacy_secrets_path = self.dir / LEGACY_SECRETS_NAME
        self.wizard_path = self.dir / "wizard.json"
        self.seen_path = self.dir / "seen.json"
        self.absence_history_path = self.dir / "absence_history.json"
        self.letters_search_cache_path = self.dir / "letters_search_cache.json"
        self.letters_confirmations_path = self.dir / "letters_confirmations.json"
        self.letters_replies_path = self.dir / "letters_replies.json"
        self.holidays_cache_path = self.dir / "holidays_cache.json"
        self.calendar_subscriptions_path = self.dir / "calendar_subscriptions.json"
        self.calendar_snapshot_path = self.dir / "calendar_snapshot.json"
        self.calendar_state_path = self.dir / "calendar_state.json"
        self.marks_path = self.dir / "marks.json"
        self.cancellations_path = self.dir / "cancellations.json"
        self.integration_token_path = self.dir / "integration_token"
        self.integration_state_path = self.dir / "integration_state.json"
        self.modules_path = self.dir / "modules.json"
        self.salt_path = self.dir / "salt"
        env_key = os.environ.get("ISERV_KEY_PATH")
        self.key_path = Path(env_key) if env_key else (self.dir / "key")
        if env_key:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
        for stale_name in ("letters_read_override.json", "letters_unread_override.json"):
            stale_path = self.dir / stale_name
            if stale_path.exists():
                stale_path.unlink()
        atomic_write.clear_stale_temp_files(self.dir)
        atomic_write.clear_stale_temp_files(self.secrets_dir)
        if self.key_path.parent != self.dir:
            atomic_write.clear_stale_temp_files(self.key_path.parent)

    def _read_text(self, path, encoding="utf-8"):
        try:
            return path.read_text(encoding=encoding)
        except (OSError, ValueError):
            return ""

    def _quarantine(self, path):
        try:
            os.replace(str(path), str(path.with_name(path.name + CORRUPT_SUFFIX)))
        except OSError:
            pass

    def _read_json_dict(self, path, quarantine=False):
        if not path.exists():
            return None
        try:
            data = json.loads(self._read_text(path))
        except ValueError:
            data = None
        if not isinstance(data, dict):
            if quarantine:
                self._quarantine(path)
            return None
        return data

    def _load_json_object(self, path, quarantine=False):
        data = self._read_json_dict(path, quarantine)
        return {} if data is None else data

    def _raw_config(self):
        return self._load_json_object(self.config_path, quarantine=True)

    def _needs_migration(self, raw):
        if self.legacy_secrets_path.exists():
            return True
        if not raw:
            return False
        return raw.get("schema_version") != SCHEMA_VERSION

    def _normalize_config(self, raw):
        merged = dict(DEFAULT_CONFIG)
        merged["notify_events"] = dict(NOTIFY_EVENT_DEFAULTS)
        merged.update(raw)
        old_service = merged.pop("notify_service", None)
        if old_service and not merged.get("notify_services"):
            merged["notify_services"] = [old_service]
        if not isinstance(merged.get("notify_events"), dict):
            merged["notify_events"] = dict(NOTIFY_EVENT_DEFAULTS)
        if not isinstance(merged.get("notify_services"), list):
            merged["notify_services"] = []
        if not isinstance(merged.get("reported_modules"), list):
            merged["reported_modules"] = []
        if not isinstance(merged.get("modules_card_hidden"), dict):
            merged["modules_card_hidden"] = {}
        merged.update(normalize_layout(merged))
        listed = merged.get("connections")
        merged["connections"] = [
            normalize_connection(entry) for entry in (listed if isinstance(listed, list) else []) if isinstance(entry, dict)
        ]
        merged["connections"] = [entry for entry in merged["connections"] if entry["id"]]
        merged["schema_version"] = SCHEMA_VERSION
        return merged

    def load_config(self):
        with self.lock:
            raw = self._raw_config()
            if self._needs_migration(raw):
                self.migrate()
                raw = self._raw_config()
            return self._normalize_config(raw)

    def save_config(self, config):
        with self.lock:
            atomic_write.write_json(self.config_path, config)

    def edit_config(self, change):
        return edit(self, self.load_config, self.save_config, change)

    def reset_config(self):
        with self.lock:
            if self.config_path.exists():
                self.config_path.unlink()

    def connections(self):
        return list(self.load_config()["connections"])

    def connection(self, connection_id):
        for entry in self.connections():
            if entry["id"] == connection_id:
                return entry
        return None

    def add_connection(self, school_url="", connection_id=None, **fields):
        added = {}

        def change(config):
            taken = {entry["id"] for entry in config["connections"]}
            wanted = connection_id or new_connection_id()
            while wanted in taken:
                wanted = new_connection_id()
            entry = normalize_connection(dict(fields, id=wanted, school_url=school_url, created_at=int(time.time())))
            config["connections"].append(entry)
            added.update(entry)

        self.edit_config(change)
        return added

    def save_connection(self, entry):
        wanted = str((entry or {}).get("id") or "")
        found = []

        def change(config):
            for index, stored in enumerate(config["connections"]):
                if stored["id"] == wanted:
                    config["connections"][index] = normalize_connection(entry)
                    found.append(index)
                    return

        self.edit_config(change)
        return bool(found)

    def update_connection(self, connection_id, **fields):
        updated = {}

        def change(config):
            for index, stored in enumerate(config["connections"]):
                if stored["id"] == connection_id:
                    config["connections"][index] = normalize_connection(dict(stored, **fields))
                    updated.update(config["connections"][index])
                    return

        self.edit_config(change)
        return updated or None

    def remove_connection(self, connection_id):
        with self.lock:
            removed = []

            def change(config):
                kept = [entry for entry in config["connections"] if entry["id"] != connection_id]
                removed.append(len(kept) != len(config["connections"]))
                config["connections"] = kept

            self.edit_config(change)
            self.delete_secrets(connection_id)
            self._drop_nested_slot(connection_id)
            self._drop_child_keys(connection_id)
            return removed[0]

    def _drop_nested_slot(self, connection_id):
        for load, save in (
            (self.load_seen, self.save_seen),
            (self.load_absence_history, self.save_absence_history),
            (self.load_letters_search_cache, self.save_letters_search_cache),
            (self.load_letters_confirmations, self.save_letters_confirmations),
            (self.load_letters_replies, self.save_letters_replies),
            (self.load_modules, self.save_modules),
        ):
            edit(self, load, save, lambda data: data.pop(connection_id, None))

        def drop_school(state):
            schools = state.get(INTEGRATION_SCHOOLS_KEY)
            if isinstance(schools, dict):
                schools.pop(connection_id, None)

        edit(self, self.load_integration_state, self.save_integration_state, drop_school)

    def _drop_child_keys(self, connection_id):
        for load, save, holder in (
            (self.load_marks, self.save_marks, "marks"),
            (self.load_cancellations, self.save_cancellations, "cancellations"),
            (self.load_calendar_subscriptions, self.save_calendar_subscriptions, "subscriptions"),
        ):

            def drop(data, holder=holder):
                entries = data.get(holder)
                if not isinstance(entries, list):
                    return
                data[holder] = [
                    entry
                    for entry in entries
                    if not (isinstance(entry, dict) and connection_of_key(entry.get("child_key")) == connection_id)
                ]

            edit(self, load, save, drop)

        def drop_children(snapshot):
            children = snapshot.get("children")
            if isinstance(children, dict):
                snapshot["children"] = {
                    key: value for key, value in children.items() if connection_of_key(key) != connection_id
                }

        edit(self, self.load_calendar_snapshot, self.save_calendar_snapshot, drop_children)

    def children(self):
        listed = []
        for entry in self.connections():
            listed.extend(children_of_connection(entry))
        return listed

    def find_child(self, key):
        for child in self.children():
            if child["key"] == key:
                return child
        return None

    def connection_store(self, connection_id):
        return ConnectionStore(self, connection_id)

    def _key(self):
        passphrase = os.environ.get("ISERV_PASSPHRASE")
        if passphrase:
            return crypto.derive_key(passphrase, self._salt())
        return crypto.load_or_create_key(str(self.key_path))

    def _salt(self):
        stored = self._read_text(self.salt_path, encoding="ascii").strip()
        if stored and crypto.is_valid_salt(stored):
            return stored
        salt = crypto.generate_salt()
        atomic_write.write_text(self.salt_path, salt, encoding="ascii")
        return salt

    def secrets_path_for(self, connection_id):
        return self.secrets_dir / f"{connection_id}{SECRETS_SUFFIX}"

    def _decrypt_secrets_file(self, path):
        if not path.exists():
            return {}
        token = self._read_text(path, encoding="ascii").strip()
        if not token:
            return {}
        try:
            return crypto.decrypt_dict(token, self._key())
        except ValueError:
            return {}

    def load_secrets(self, connection_id):
        return self._decrypt_secrets_file(self.secrets_path_for(connection_id))

    def save_secrets(self, connection_id, secrets):
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        token = crypto.encrypt_dict(secrets, self._key())
        atomic_write.write_text(self.secrets_path_for(connection_id), token, encoding="ascii")

    def delete_secrets(self, connection_id):
        path = self.secrets_path_for(connection_id)
        if path.exists():
            path.unlink()

    def load_wizard(self):
        if not self.wizard_path.exists():
            return dict(DEFAULT_WIZARD)
        state = self._read_json_dict(self.wizard_path, quarantine=True)
        return dict(DEFAULT_WIZARD) if state is None else state

    def save_wizard(self, state):
        atomic_write.write_json(self.wizard_path, state)

    def load_seen(self):
        return self._load_json_object(self.seen_path)

    def save_seen(self, seen):
        atomic_write.write_json(self.seen_path, seen)

    def load_absence_history(self):
        return self._load_json_object(self.absence_history_path)

    def save_absence_history(self, history):
        atomic_write.write_json(self.absence_history_path, history)

    def load_letters_search_cache(self):
        return self._load_json_object(self.letters_search_cache_path)

    def save_letters_search_cache(self, cache):
        atomic_write.write_json(self.letters_search_cache_path, cache)

    def load_letters_confirmations(self):
        return self._load_json_object(self.letters_confirmations_path)

    def save_letters_confirmations(self, data):
        atomic_write.write_json(self.letters_confirmations_path, data)

    def load_letters_replies(self):
        return self._load_json_object(self.letters_replies_path)

    def save_letters_replies(self, data):
        atomic_write.write_json(self.letters_replies_path, data)

    def load_holidays_cache(self):
        return self._load_json_object(self.holidays_cache_path)

    def save_holidays_cache(self, cache):
        atomic_write.write_json(self.holidays_cache_path, cache)

    def _save_private_json(self, path, data):
        atomic_write.write_json(path, data)

    def load_calendar_subscriptions(self):
        return self._load_json_object(self.calendar_subscriptions_path)

    def save_calendar_subscriptions(self, data):
        self._save_private_json(self.calendar_subscriptions_path, data)

    def load_calendar_snapshot(self):
        return self._load_json_object(self.calendar_snapshot_path)

    def save_calendar_snapshot(self, data):
        self._save_private_json(self.calendar_snapshot_path, data)

    def load_calendar_state(self):
        return self._load_json_object(self.calendar_state_path)

    def save_calendar_state(self, data):
        self._save_private_json(self.calendar_state_path, data)

    def load_marks(self):
        return self._load_json_object(self.marks_path)

    def save_marks(self, data):
        self._save_private_json(self.marks_path, data)

    def load_cancellations(self):
        return self._load_json_object(self.cancellations_path)

    def save_cancellations(self, data):
        self._save_private_json(self.cancellations_path, data)

    def load_integration_token(self):
        return self._read_text(self.integration_token_path, encoding="ascii").strip()

    def save_integration_token(self, token):
        atomic_write.write_text(self.integration_token_path, token + "\n", encoding="ascii")

    def load_integration_state(self):
        return self._load_json_object(self.integration_state_path)

    def save_integration_state(self, data):
        self._save_private_json(self.integration_state_path, data)

    def load_modules(self):
        return self._load_json_object(self.modules_path)

    def save_modules(self, data):
        self._save_private_json(self.modules_path, data)

    def migrate(self):
        with self.lock:
            return self._migrate()

    def _migrate(self):
        raw = self._raw_config()
        legacy_config = raw.get("schema_version") != SCHEMA_VERSION
        connection_id = self._migration_connection_id(raw, legacy_config)
        if connection_id:
            self._migrate_secrets(connection_id)
            self._migrate_child_keys(connection_id)
            self._migrate_nested_files(connection_id)
            self._migrate_integration_state(connection_id)
            self._migrate_wizard(connection_id)
        if legacy_config or not raw:
            self._finish_config_migration(raw, connection_id)
        if self.legacy_secrets_path.exists():
            if connection_id and self.secrets_path_for(connection_id).exists():
                self.legacy_secrets_path.unlink()
            else:
                self._quarantine(self.legacy_secrets_path)
        return True

    def _migration_connection_id(self, raw, legacy_config):
        listed = raw.get("connections") if isinstance(raw.get("connections"), list) else []
        listed = [entry for entry in listed if isinstance(entry, dict) and entry.get("id")]
        if listed:
            if legacy_config or (len(listed) == 1 and self.legacy_secrets_path.exists()):
                return str(listed[0]["id"])
            return ""
        if not legacy_config and not self.legacy_secrets_path.exists():
            return ""
        if not raw.get("school_url"):
            return ""
        connection_id = new_connection_id()
        entry = {key: raw.get(key, CONNECTION_DEFAULTS[key]) for key in LEGACY_CONNECTION_KEYS}
        entry = normalize_connection(dict(entry, id=connection_id, created_at=int(time.time())))
        entry["setup_complete"] = bool(entry["school_url"]) and self._legacy_login_present()
        raw["connections"] = [entry]
        self.save_config(raw)
        return connection_id

    def _legacy_token(self):
        return self._read_text(self.legacy_secrets_path, encoding="ascii").strip()

    def _legacy_login_present(self):
        token = self._legacy_token()
        if not crypto.is_token_like(token):
            return False
        try:
            return bool(crypto.decrypt_dict(token, self._key()).get("username"))
        except ValueError:
            return True

    def _migrate_secrets(self, connection_id):
        if not self.legacy_secrets_path.exists():
            return
        target = self.secrets_path_for(connection_id)
        if target.exists():
            return
        token = self._legacy_token()
        if not token:
            return
        if not crypto.is_token_like(token):
            self._quarantine(self.legacy_secrets_path)
            return
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        atomic_write.write_text(target, token, encoding="ascii")

    def _migrate_child_keys(self, connection_id):
        for path, holder in (
            (self.marks_path, "marks"),
            (self.cancellations_path, "cancellations"),
            (self.calendar_subscriptions_path, "subscriptions"),
        ):
            data = self._load_json_object(path)
            entries = data.get(holder)
            if not isinstance(entries, list):
                continue
            changed = False
            for entry in entries:
                if not isinstance(entry, dict) or "child_key" in entry:
                    continue
                child_id = str(entry.pop("child_id", "") or "")
                entry["child_key"] = child_key(connection_id, child_id) if child_id else ""
                changed = True
            if changed:
                atomic_write.write_json(path, data)
        snapshot = self.load_calendar_snapshot()
        children = snapshot.get("children")
        if isinstance(children, dict):
            rewritten = {}
            changed = False
            for key, value in children.items():
                if connection_of_key(key) == connection_id:
                    rewritten[key] = value
                    continue
                rewritten[child_key(connection_id, key)] = value
                changed = True
            if changed:
                snapshot["children"] = rewritten
                self.save_calendar_snapshot(snapshot)

    def _migrate_poll_state(self, poll_state, connection_id):
        rewritten = {}
        for key, value in (poll_state or {}).items():
            if key in POLL_STATE_MODULE_KEYS or connection_of_key(key) == connection_id:
                rewritten[key] = value
            else:
                rewritten[child_key(connection_id, key)] = value
        return rewritten

    def _migrate_nested_files(self, connection_id):
        for name in NESTED_FILE_NAMES:
            path = self.dir / name
            if not path.exists():
                continue
            data = self._load_json_object(path)
            if _wrapped_under(data, connection_id):
                continue
            atomic_write.write_json(path, {connection_id: data})

    def _migrate_integration_state(self, connection_id):
        if not self.integration_state_path.exists():
            return
        state = self.load_integration_state()
        if INTEGRATION_SCHOOLS_KEY in state:
            return
        school = {key: state.pop(key) for key in INTEGRATION_SCHOOL_KEYS if key in state}
        for name in ("last_poll", "last_poll_ok", "last_error"):
            if name in school:
                state[name] = school[name]
        changes = []
        for entry in state.get("changes") or []:
            if not isinstance(entry, dict):
                continue
            moved = dict(entry)
            if "child_key" not in moved:
                child_id = str(moved.pop("child_id", "") or "")
                moved["child_key"] = child_key(connection_id, child_id) if child_id else ""
            moved["school_id"] = connection_id
            changes.append(moved)
        state["changes"] = changes
        state[INTEGRATION_SCHOOLS_KEY] = {connection_id: school}
        self.save_integration_state(state)

    def _migrate_wizard(self, connection_id):
        if not self.wizard_path.exists():
            return
        state = self._read_json_dict(self.wizard_path)
        if not isinstance(state, dict) or state.get("connection_id"):
            return
        state["connection_id"] = connection_id
        self.save_wizard(state)

    def _finish_config_migration(self, raw, connection_id):
        fresh = {key: value for key, value in raw.items() if key not in LEGACY_CONNECTION_KEYS}
        if connection_id:
            for entry in fresh.get("connections") or []:
                if isinstance(entry, dict) and entry.get("id") == connection_id:
                    entry["poll_state"] = self._migrate_poll_state(entry.get("poll_state"), connection_id)
        fresh["schema_version"] = SCHEMA_VERSION
        self.save_config(fresh)


class ConnectionStore:
    def __init__(self, store, connection_id):
        self.base = store
        self.id = connection_id
        self.dir = store.dir

    def __getattr__(self, name):
        return getattr(self.base, name)

    def entry(self):
        return self.base.connection(self.id)

    def exists(self):
        return self.entry() is not None

    def display_name(self):
        return connection_display_name(self.entry())

    def child_key(self, child_id):
        return child_key(self.id, child_id)

    def load_config(self):
        config = self.base.load_config()
        entry = normalize_connection(next((item for item in config["connections"] if item["id"] == self.id), None))
        flat = {key: value for key, value in entry.items() if key != "id"}
        for key in GLOBAL_SETTING_KEYS:
            flat[key] = config[key]
        flat["connection_id"] = self.id
        return flat

    def save_config(self, flat):
        def change(config):
            for entry in config["connections"]:
                if entry["id"] != self.id:
                    continue
                for key, value in flat.items():
                    if key in GLOBAL_SETTING_KEYS or key in ("id", "connection_id"):
                        continue
                    entry[key] = value
                for key in [name for name in entry if name not in flat and name not in ("id",)]:
                    entry.pop(key, None)

        self.base.edit_config(change)

    def edit_config(self, change):
        with self.base.lock:
            before = self.load_config()
            flat = copy.deepcopy(before)
            change(flat)
            if flat != before:
                self.base.edit_config(lambda config: self._apply_flat(config, before, flat))
            return flat

    def _apply_flat(self, config, before, after):
        entry = next((item for item in config["connections"] if item["id"] == self.id), None)
        for key in set(before) | set(after):
            if key in ("id", "connection_id") or (key in before and key in after and before[key] == after[key]):
                continue
            if key in GLOBAL_SETTING_KEYS:
                if key in after:
                    config[key] = copy.deepcopy(after[key])
            elif entry is not None:
                if key in after:
                    entry[key] = copy.deepcopy(after[key])
                else:
                    entry.pop(key, None)

    def reset_config(self):
        self.base.remove_connection(self.id)

    def load_secrets(self):
        return self.base.load_secrets(self.id)

    def save_secrets(self, secrets):
        with self.base.lock:
            if connection_known(self.base, self.id):
                self.base.save_secrets(self.id, secrets)

    def edit_secrets(self, change):
        with self.base.lock:
            before = self.load_secrets()
            secrets = copy.deepcopy(before)
            change(secrets)
            if secrets != before:
                self.save_secrets(secrets)
            return secrets

    def delete_secrets(self):
        self.base.delete_secrets(self.id)

    def _nested(self, loader):
        data = loader()
        slot = data.get(self.id)
        return dict(slot) if isinstance(slot, dict) else {}

    def _put_nested(self, loader, saver, value):
        def change(data):
            if connection_known(self.base, self.id):
                data[self.id] = value

        edit(self.base, loader, saver, change)

    def edit_slot(self, kind, change):
        outcome = {}

        def apply(data):
            if not connection_known(self.base, self.id):
                return
            stored = data.get(self.id)
            slot = dict(stored) if isinstance(stored, dict) else {}
            change(slot)
            outcome["slot"] = slot
            if slot != (stored if isinstance(stored, dict) else {}):
                data[self.id] = slot

        edit(self.base, getattr(self.base, f"load_{kind}"), getattr(self.base, f"save_{kind}"), apply)
        return outcome.get("slot", {})

    def load_seen(self):
        return self._nested(self.base.load_seen)

    def save_seen(self, seen):
        self._put_nested(self.base.load_seen, self.base.save_seen, seen)

    def load_absence_history(self):
        return self._nested(self.base.load_absence_history)

    def save_absence_history(self, history):
        self._put_nested(self.base.load_absence_history, self.base.save_absence_history, history)

    def load_letters_search_cache(self):
        return self._nested(self.base.load_letters_search_cache)

    def save_letters_search_cache(self, cache):
        self._put_nested(self.base.load_letters_search_cache, self.base.save_letters_search_cache, cache)

    def load_letters_confirmations(self):
        return self._nested(self.base.load_letters_confirmations)

    def save_letters_confirmations(self, data):
        self._put_nested(self.base.load_letters_confirmations, self.base.save_letters_confirmations, data)

    def load_letters_replies(self):
        return self._nested(self.base.load_letters_replies)

    def save_letters_replies(self, data):
        self._put_nested(self.base.load_letters_replies, self.base.save_letters_replies, data)

    def load_modules(self):
        return self._nested(self.base.load_modules)

    def save_modules(self, data):
        self._put_nested(self.base.load_modules, self.base.save_modules, data)

    def load_integration_state(self):
        schools = self.base.load_integration_state().get(INTEGRATION_SCHOOLS_KEY)
        slot = schools.get(self.id) if isinstance(schools, dict) else None
        return dict(slot) if isinstance(slot, dict) else {}

    def save_integration_state(self, data):
        def change(state):
            if not connection_known(self.base, self.id):
                return
            schools = state.get(INTEGRATION_SCHOOLS_KEY)
            if not isinstance(schools, dict):
                schools = {}
            schools[self.id] = data
            state[INTEGRATION_SCHOOLS_KEY] = schools

        edit(self.base, self.base.load_integration_state, self.base.save_integration_state, change)
