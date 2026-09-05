import json
import os
from pathlib import Path

from . import atomic_write, crypto
from .mapping import migrate_subject_colors

CORRUPT_SUFFIX = ".corrupt"

DEFAULT_CONFIG = {
    "school_url": "",
    "language": "system",
    "children": [],
    "subjects": {},
    "teachers": {},
    "period_times": {},
    "phones": [],
    "holiday_region": "",
    "notify_services": [],
    "notify_events": {
        "timetable": True,
        "letters": True,
        "pinboard": True,
        "conferences": True,
        "messenger": True,
    },
}

DEFAULT_WIZARD = {"step": "url", "attempts": 0}


class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.secrets_path = self.dir / "secrets.enc"
        self.wizard_path = self.dir / "wizard.json"
        self.seen_path = self.dir / "seen.json"
        self.absence_history_path = self.dir / "absence_history.json"
        self.letters_search_cache_path = self.dir / "letters_search_cache.json"
        self.letters_confirmations_path = self.dir / "letters_confirmations.json"
        self.holidays_cache_path = self.dir / "holidays_cache.json"
        self.calendar_subscriptions_path = self.dir / "calendar_subscriptions.json"
        self.calendar_snapshot_path = self.dir / "calendar_snapshot.json"
        self.calendar_state_path = self.dir / "calendar_state.json"
        self.marks_path = self.dir / "marks.json"
        self.cancellations_path = self.dir / "cancellations.json"
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

    def load_config(self):
        merged = dict(DEFAULT_CONFIG)
        merged.update(self._load_json_object(self.config_path, quarantine=True))
        old_service = merged.pop("notify_service", None)
        if old_service and not merged.get("notify_services"):
            merged["notify_services"] = [old_service]
        return migrate_subject_colors(merged)

    def save_config(self, config):
        atomic_write.write_json(self.config_path, config)

    def reset_config(self):
        if self.config_path.exists():
            self.config_path.unlink()

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

    def load_secrets(self):
        if not self.secrets_path.exists():
            return {}
        token = self._read_text(self.secrets_path, encoding="ascii").strip()
        if not token:
            return {}
        try:
            return crypto.decrypt_dict(token, self._key())
        except ValueError:
            return {}

    def save_secrets(self, secrets):
        token = crypto.encrypt_dict(secrets, self._key())
        atomic_write.write_text(self.secrets_path, token, encoding="ascii")

    def delete_secrets(self):
        if self.secrets_path.exists():
            self.secrets_path.unlink()

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
