import hmac
import re
import secrets
import threading
import time

COMPONENT_TIMETABLE = "timetable"
COMPONENT_SCHOOL_HOLIDAYS = "school_holidays"
COMPONENT_PUBLIC_HOLIDAYS = "public_holidays"
COMPONENT_MARKS = "marks"
COMPONENT_ABSENCES = "absences"
COMPONENTS = (
    COMPONENT_TIMETABLE,
    COMPONENT_SCHOOL_HOLIDAYS,
    COMPONENT_PUBLIC_HOLIDAYS,
    COMPONENT_MARKS,
    COMPONENT_ABSENCES,
)

TOKEN_BYTES = 32
IDENTIFIER_BYTES = 8
MAX_LABEL_LENGTH = 60
MIN_NAME_TOKEN_LENGTH = 3
TOKEN_LOG_PREFIX_LENGTH = 6

ERROR_COMPONENTS = "api.calendar.error.components"
ERROR_CHILD = "api.calendar.error.child"
ERROR_LABEL_NAME = "api.calendar.error.labelName"
ERROR_LABEL_LENGTH = "api.calendar.error.labelLength"
ERROR_REGION = "api.calendar.error.region"
ERROR_NOT_FOUND = "api.calendar.error.notFound"

_NAME_SPLIT = re.compile(r"[^\w]+", re.UNICODE)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class SubscriptionError(Exception):
    def __init__(self, message_key):
        super().__init__(message_key)
        self.message_key = message_key


def normalize_components(values):
    if not isinstance(values, (list, tuple)):
        raise SubscriptionError(ERROR_COMPONENTS)
    selected = [name for name in COMPONENTS if name in values]
    unknown = [str(name) for name in values if name not in COMPONENTS]
    if unknown or not selected:
        raise SubscriptionError(ERROR_COMPONENTS)
    return selected


def normalize_color(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("#"):
        text = "#" + text
    return text if _HEX_COLOR.match(text) else ""


def child_name_tokens(config):
    tokens = set()
    for child in config.get("children") or []:
        if not isinstance(child, dict):
            continue
        for part in _NAME_SPLIT.split(str(child.get("name") or "")):
            folded = part.casefold()
            if len(folded) >= MIN_NAME_TOKEN_LENGTH:
                tokens.add(folded)
    return tokens


def label_carries_child_name(label, config):
    folded = str(label or "").casefold()
    return any(token in folded for token in child_name_tokens(config))


def normalize_label(label, config, child_id):
    text = " ".join(str(label or "").split())
    if not text:
        text = _class_name(config, child_id)
    if len(text) > MAX_LABEL_LENGTH:
        raise SubscriptionError(ERROR_LABEL_LENGTH)
    if text and label_carries_child_name(text, config):
        raise SubscriptionError(ERROR_LABEL_NAME)
    return text


def _class_name(config, child_id):
    for child in config.get("children") or []:
        if isinstance(child, dict) and child.get("child_id") == child_id:
            return " ".join(str(child.get("class_name") or "").split())
    return ""


def known_child(config, child_id):
    children = config.get("children") or []
    if not children:
        return False
    return any(
        isinstance(child, dict) and child.get("child_id") == child_id for child in children
    )


def token_log_prefix(token):
    return str(token or "")[:TOKEN_LOG_PREFIX_LENGTH]


def public_view(entry):
    return {
        "id": entry.get("id", ""),
        "child_id": entry.get("child_id", ""),
        "label": entry.get("label", ""),
        "components": list(entry.get("components") or []),
        "color": entry.get("color", ""),
        "created_at": entry.get("created_at", 0),
        "rotated_at": entry.get("rotated_at", 0),
        "token": entry.get("token", ""),
        "path": feed_path(entry.get("token", "")),
    }


def feed_path(token):
    return f"/calendar/{token}.ics"


class SubscriptionRegistry:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or time.time
        self._lock = threading.Lock()

    def _read(self):
        data = self.store.load_calendar_subscriptions()
        entries = data.get("subscriptions")
        return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []

    def _write(self, entries):
        self.store.save_calendar_subscriptions({"subscriptions": entries})

    def list(self):
        return [public_view(entry) for entry in self._read()]

    def create(self, child_id, components, label="", color="", require_region=True):
        config = self.store.load_config()
        selected = normalize_components(components)
        if not known_child(config, child_id):
            raise SubscriptionError(ERROR_CHILD)
        if require_region and COMPONENT_TIMETABLE in selected and not config.get("holiday_region"):
            raise SubscriptionError(ERROR_REGION)
        resolved = normalize_label(label, config, child_id)
        entry = {
            "id": secrets.token_hex(IDENTIFIER_BYTES),
            "child_id": child_id,
            "label": resolved,
            "components": selected,
            "color": normalize_color(color),
            "token": secrets.token_urlsafe(TOKEN_BYTES),
            "created_at": int(self.clock()),
            "rotated_at": 0,
        }
        with self._lock:
            entries = self._read()
            entries.append(entry)
            self._write(entries)
        return public_view(entry)

    def _mutate(self, subscription_id, change):
        with self._lock:
            entries = self._read()
            for index, entry in enumerate(entries):
                if entry.get("id") != subscription_id:
                    continue
                updated = change(dict(entry))
                entries[index] = updated
                self._write(entries)
                return public_view(updated)
        raise SubscriptionError(ERROR_NOT_FOUND)

    def update(self, subscription_id, components=None, label=None, color=None, require_region=True):
        config = self.store.load_config()

        def change(entry):
            if color is not None:
                entry["color"] = normalize_color(color)
            if components is not None:
                selected = normalize_components(components)
                if require_region and COMPONENT_TIMETABLE in selected and not config.get("holiday_region"):
                    raise SubscriptionError(ERROR_REGION)
                entry["components"] = selected
            if label is not None:
                entry["label"] = normalize_label(label, config, entry.get("child_id", ""))
            return entry

        return self._mutate(subscription_id, change)

    def rotate(self, subscription_id):
        def change(entry):
            entry["token"] = secrets.token_urlsafe(TOKEN_BYTES)
            entry["rotated_at"] = int(self.clock())
            return entry

        return self._mutate(subscription_id, change)

    def revoke(self, subscription_id):
        with self._lock:
            entries = self._read()
            remaining = [entry for entry in entries if entry.get("id") != subscription_id]
            if len(remaining) == len(entries):
                raise SubscriptionError(ERROR_NOT_FOUND)
            self._write(remaining)
        return {"revoked": subscription_id}

    def find_by_token(self, token):
        candidate = str(token or "")
        found = None
        for entry in self._read():
            stored = str(entry.get("token") or "")
            if len(stored) == len(candidate) and hmac.compare_digest(stored, candidate):
                found = entry
        return found

    def children_with_component(self, component):
        return {
            entry.get("child_id")
            for entry in self._read()
            if component in (entry.get("components") or []) and entry.get("child_id")
        }

    def children_with_timetable(self):
        return self.children_with_component(COMPONENT_TIMETABLE)
