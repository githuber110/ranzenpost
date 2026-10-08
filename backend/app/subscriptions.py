import hmac
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from .store import children_of_config, config_for_child, owning_connection

COMPONENT_TIMETABLE = "timetable"
COMPONENT_SCHOOL_HOLIDAYS = "school_holidays"
COMPONENT_PUBLIC_HOLIDAYS = "public_holidays"
COMPONENT_MARKS = "marks"
COMPONENT_ABSENCES = "absences"
COMPONENT_OWN_ENTRIES = "own_entries"
COMPONENT_SCHOOL_EVENTS = "school_events"
COMPONENTS = (
    COMPONENT_TIMETABLE,
    COMPONENT_SCHOOL_HOLIDAYS,
    COMPONENT_PUBLIC_HOLIDAYS,
    COMPONENT_MARKS,
    COMPONENT_ABSENCES,
    COMPONENT_OWN_ENTRIES,
    COMPONENT_SCHOOL_EVENTS,
)
SCHOOL_COMPONENTS = (
    COMPONENT_SCHOOL_HOLIDAYS,
    COMPONENT_PUBLIC_HOLIDAYS,
    COMPONENT_SCHOOL_EVENTS,
)

LAST_FETCH_FIELD = "last_fetched_at"
WATCH_FIELD = "watched_since"
TOKEN_BYTES = 32
IDENTIFIER_BYTES = 8
MAX_LABEL_LENGTH = 60
MIN_NAME_TOKEN_LENGTH = 3
TOKEN_LOG_PREFIX_LENGTH = 4
ONLINE_FIELD = "online"
WEBHOOK_FIELD = "webhook_id"
REPORT_FIELD = "online_report"
WEBHOOK_PREFIX = "ranzenpost_"
WEBHOOK_BYTES = 16
MAX_ONLINE_URL_LENGTH = 512
ONLINE_URL_SCHEMES = ("https", "http")
ONLINE_OFF = "off"
ONLINE_PENDING = "pending"
ONLINE_READY = "ready"
ONLINE_UNREACHABLE = "unreachable"
ONLINE_STALLED = "stalled"
ONLINE_NO_INTEGRATION = "no_integration"
OFFERED_FIELD = "offered_at"
INTEGRATION_WINDOW_SECONDS = 2 * 60 * 60
STALL_GRACE_SECONDS = 120
INTERNET_READY = "ready"
INTERNET_NO_INTEGRATION = "no_integration"
INTERNET_UPDATE = "update_integration"
INTERNET_NO_ACCESS = "no_access"
INTERNET_CHECKING = "checking"
INTERNET_REFUSALS = {
    INTERNET_CHECKING: "calendar.subscribe.variant.internet.checking",
    INTERNET_NO_INTEGRATION: "calendar.subscribe.variant.internet.noIntegration",
    INTERNET_UPDATE: "calendar.subscribe.variant.internet.update",
    INTERNET_NO_ACCESS: "calendar.subscribe.variant.internet.noAccess",
}

ERROR_COMPONENTS = "api.calendar.error.components"
ERROR_CHILD = "api.calendar.error.child"
ERROR_SCHOOL = "api.calendar.error.school"
ERROR_LABEL_LENGTH = "api.calendar.error.labelLength"
ERROR_REGION = "api.calendar.error.region"
ERROR_NOT_FOUND = "api.calendar.error.notFound"

_NAME_SPLIT = re.compile(r"[^\w]+", re.UNICODE)
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class SubscriptionError(Exception):
    def __init__(self, message_key):
        super().__init__(message_key)
        self.message_key = message_key


def normalize_components(values, allowed=COMPONENTS):
    if not isinstance(values, (list, tuple)):
        raise SubscriptionError(ERROR_COMPONENTS)
    selected = [name for name in allowed if name in values]
    unknown = [str(name) for name in values if name not in allowed]
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
    for child in children_of_config(config):
        for part in _NAME_SPLIT.split(str(child.get("name") or "")):
            folded = part.casefold()
            if len(folded) >= MIN_NAME_TOKEN_LENGTH:
                tokens.add(folded)
    return tokens


def label_carries_child_name(label, config):
    folded = str(label or "").casefold()
    return any(token in folded for token in child_name_tokens(config))


def normalize_label(label, config, child_key):
    text = " ".join(str(label or "").split())
    if len(text) > MAX_LABEL_LENGTH:
        raise SubscriptionError(ERROR_LABEL_LENGTH)
    return settled_label(text, config, child_key)


def settled_label(label, config, child_key):
    text = " ".join(str(label or "").split())
    if text and text.casefold() == _class_name(config, child_key).casefold():
        return ""
    return text


def _child(config, child_key):
    for child in children_of_config(config):
        if child.get("key") == child_key:
            return child
    return {}


def _class_name(config, child_key):
    return " ".join(str(_child(config, child_key).get("class_name") or "").split())


def child_name(config, child_key):
    return " ".join(str(_child(config, child_key).get("name") or "").split())


def child_first_name(name):
    text = " ".join(str(name or "").split())
    given = text.rsplit(",", 1)[-1] if "," in text else text
    parts = given.split()
    return parts[0] if parts else ""


def known_child(config, child_key):
    return any(child.get("key") == child_key for child in children_of_config(config))


def known_school(config, school_id):
    listed = (config or {}).get("connections")
    if not school_id or not isinstance(listed, list):
        return False
    return any(
        isinstance(entry, dict) and entry.get("id") == school_id and entry.get("setup_complete") is True for entry in listed
    )


def is_school_subscription(entry):
    return not entry.get("child_key")


def allowed_components(entry):
    return SCHOOL_COMPONENTS if is_school_subscription(entry) else COMPONENTS


def token_log_prefix(token):
    return str(token or "")[:TOKEN_LOG_PREFIX_LENGTH]


def _as_epoch(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value) if value > 0 else 0


def online_url(value):
    text = str(value or "").strip()
    if not text or len(text) > MAX_ONLINE_URL_LENGTH or any(char.isspace() for char in text):
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme not in ONLINE_URL_SCHEMES or not parts.hostname or parts.username or parts.password:
        return ""
    return text


def _online_report(entry):
    report = entry.get(REPORT_FIELD)
    if not isinstance(report, dict) or report.get(WEBHOOK_FIELD) != entry.get(WEBHOOK_FIELD):
        return None
    return report


def online_state(entry):
    if not entry.get(ONLINE_FIELD) or not entry.get(WEBHOOK_FIELD):
        return ONLINE_OFF
    report = _online_report(entry)
    if report is None:
        return ONLINE_PENDING
    return ONLINE_READY if report.get("cloud_url") or report.get("external_url") else ONLINE_UNREACHABLE


def online_address(entry):
    report = _online_report(entry) if online_state(entry) == ONLINE_READY else None
    if report is None:
        return ""
    return report.get("cloud_url") or report.get("external_url") or ""


def _new_webhook_id():
    return WEBHOOK_PREFIX + secrets.token_hex(WEBHOOK_BYTES)


def _go_online(entry):
    entry[ONLINE_FIELD] = True
    entry[WEBHOOK_FIELD] = _new_webhook_id()
    entry.pop(REPORT_FIELD, None)
    entry.pop(OFFERED_FIELD, None)
    return entry


def _go_offline(entry):
    for field in (ONLINE_FIELD, WEBHOOK_FIELD, REPORT_FIELD, OFFERED_FIELD):
        entry.pop(field, None)
    return entry


def integration_present(integration_seen, now):
    seen = _as_epoch(integration_seen)
    return bool(seen) and 0 <= now - seen <= INTEGRATION_WINDOW_SECONDS


def internet_access(outside, integration_seen, now, started=0):
    if not integration_present(integration_seen, now):
        return INTERNET_NO_INTEGRATION
    if not isinstance(outside, dict):
        if _as_epoch(integration_seen) < _as_epoch(started) + STALL_GRACE_SECONDS:
            return INTERNET_CHECKING
        return INTERNET_UPDATE
    return INTERNET_READY if outside.get("cloud") or outside.get("external") else INTERNET_NO_ACCESS


def settle_online_state(view, integration_seen, now):
    state = view.get("online_state")
    if state == ONLINE_OFF:
        return view
    if not integration_present(integration_seen, now):
        return dict(view, online_state=ONLINE_NO_INTEGRATION, online_url="")
    offered = _as_epoch(view.get(OFFERED_FIELD))
    if state == ONLINE_PENDING and offered and now - offered >= STALL_GRACE_SECONDS:
        return dict(view, online_state=ONLINE_STALLED)
    return view


def public_view(entry):
    return {
        "id": entry.get("id", ""),
        "child_key": entry.get("child_key", ""),
        "school_id": owning_connection(entry),
        "label": entry.get("label", ""),
        "components": list(entry.get("components") or []),
        "color": entry.get("color", ""),
        "created_at": entry.get("created_at", 0),
        "rotated_at": entry.get("rotated_at", 0),
        "last_fetched_at": _as_epoch(entry.get(LAST_FETCH_FIELD)),
        "watched_since": _as_epoch(entry.get(WATCH_FIELD)) or _as_epoch(entry.get("created_at")),
        "token": entry.get("token", ""),
        "path": feed_path(entry.get("token", "")),
        "online": online_state(entry) != ONLINE_OFF,
        "online_state": online_state(entry),
        "online_url": online_address(entry),
        "offered_at": _as_epoch(entry.get(OFFERED_FIELD)),
    }


def feed_path(token):
    return f"/calendar/{token}.ics"


class SubscriptionRegistry:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or time.time
        self._lock = getattr(store, "lock", None) or threading.Lock()
        self._outside = None
        self.started = int(self.clock())

    def _read(self):
        data = self.store.load_calendar_subscriptions()
        entries = data.get("subscriptions")
        entries = [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
        config = self.store.load_config()
        for entry in entries:
            entry["label"] = settled_label(entry.get("label"), config, entry.get("child_key", ""))
        return entries

    def _write(self, entries):
        self.store.save_calendar_subscriptions({"subscriptions": entries})

    def list(self):
        with self._lock:
            entries = self._read()
            stamp = int(self.clock())
            unwatched = [entry for entry in entries if not _as_epoch(entry.get(WATCH_FIELD))]
            for entry in unwatched:
                entry[WATCH_FIELD] = stamp
            if unwatched:
                self._write(entries)
        return [public_view(entry) for entry in entries]

    def move_child(self, old_key, new_key):
        if not old_key or not new_key or old_key == new_key:
            return 0
        with self._lock:
            entries = self._read()
            moved = 0
            for entry in entries:
                if entry.get("child_key") == old_key:
                    entry["child_key"] = new_key
                    moved += 1
            if moved:
                self._write(entries)
        return moved

    @property
    def outside_access(self):
        return dict(self._outside) if self._outside is not None else None

    def record_outside_access(self, outside):
        if not isinstance(outside, dict):
            return None
        self._outside = {"cloud": outside.get("cloud") is True, "external": outside.get("external") is True}
        return dict(self._outside)

    def create(self, child_key, components, label="", color="", online=False, school_id=""):
        config = self.store.load_config()
        if not child_key and school_id:
            return self._create_for_school(config, school_id, components, label, color, online)
        selected = normalize_components(components)
        if not known_child(config, child_key):
            raise SubscriptionError(ERROR_CHILD)
        region = config_for_child(self.store, child_key).get("holiday_region")
        if COMPONENT_TIMETABLE in selected and not region:
            raise SubscriptionError(ERROR_REGION)
        resolved = normalize_label(label, config, child_key)
        return self._store_new({"child_key": child_key}, selected, resolved, color, online)

    def _create_for_school(self, config, school_id, components, label, color, online):
        school = str(school_id)
        if not known_school(config, school):
            raise SubscriptionError(ERROR_SCHOOL)
        selected = normalize_components(components, SCHOOL_COMPONENTS)
        resolved = normalize_label(label, config, "")
        return self._store_new({"child_key": "", "school_id": school}, selected, resolved, color, online)

    def _store_new(self, owner, selected, resolved, color, online):
        entry = {
            "id": secrets.token_hex(IDENTIFIER_BYTES),
            **owner,
            "label": resolved,
            "components": selected,
            "color": normalize_color(color),
            "token": secrets.token_urlsafe(TOKEN_BYTES),
            "created_at": int(self.clock()),
            "rotated_at": 0,
        }
        entry[WATCH_FIELD] = entry["created_at"]
        if online is True:
            _go_online(entry)
        with self._lock:
            config = self.store.load_config()
            if owner.get("child_key") and not known_child(config, owner["child_key"]):
                raise SubscriptionError(ERROR_CHILD)
            if not owner.get("child_key") and not known_school(config, owner.get("school_id", "")):
                raise SubscriptionError(ERROR_SCHOOL)
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

    def update(self, subscription_id, components=None, label=None, color=None, online=None):
        config = self.store.load_config()

        def change(entry):
            if online is True and online_state(entry) == ONLINE_OFF:
                _go_online(entry)
            elif online is False:
                _go_offline(entry)
            if color is not None:
                entry["color"] = normalize_color(color)
            if components is not None:
                selected = normalize_components(components, allowed_components(entry))
                region = config_for_child(self.store, entry.get("child_key", "")).get("holiday_region")
                if COMPONENT_TIMETABLE in selected and not region:
                    raise SubscriptionError(ERROR_REGION)
                entry["components"] = selected
            if label is not None:
                entry["label"] = normalize_label(label, config, entry.get("child_key", ""))
            return entry

        return self._mutate(subscription_id, change)

    def rotate(self, subscription_id):
        def change(entry):
            entry["token"] = secrets.token_urlsafe(TOKEN_BYTES)
            entry["rotated_at"] = int(self.clock())
            entry.pop(LAST_FETCH_FIELD, None)
            entry[WATCH_FIELD] = entry["rotated_at"]
            if online_state(entry) != ONLINE_OFF:
                _go_online(entry)
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

    def find_online(self, subscription_id, webhook_id):
        wanted = str(subscription_id or "")
        presented = str(webhook_id or "")
        for entry in self._read():
            if not wanted or entry.get("id") != wanted or online_state(entry) == ONLINE_OFF:
                continue
            stored = str(entry.get(WEBHOOK_FIELD) or "")
            if presented and len(stored) == len(presented) and hmac.compare_digest(stored, presented):
                return entry
        return None

    def online_feeds(self):
        feeds = []
        for entry in self._read():
            if online_state(entry) == ONLINE_OFF:
                continue
            report = _online_report(entry) or {}
            feeds.append({
                "id": entry.get("id", ""),
                "webhook_id": entry.get(WEBHOOK_FIELD, ""),
                "cloud_url": report.get("cloud_url", ""),
                "external_url": report.get("external_url", ""),
                "reported": bool(report),
            })
        return feeds

    def mark_offered(self, webhook_ids):
        offered = {str(item) for item in webhook_ids}
        stamp = int(self.clock())
        with self._lock:
            entries = self._read()
            fresh = [
                entry for entry in entries
                if online_state(entry) == ONLINE_PENDING
                and not _as_epoch(entry.get(OFFERED_FIELD))
                and entry.get(WEBHOOK_FIELD) in offered
            ]
            for entry in fresh:
                entry[OFFERED_FIELD] = stamp
            if fresh:
                self._write(entries)
        return len(fresh)

    def record_online_reports(self, reports):
        wanted = {}
        for report in reports:
            if isinstance(report, dict) and report.get("id") and report.get(WEBHOOK_FIELD):
                wanted[str(report["id"])] = report
        stamp = int(self.clock())
        stored = []
        with self._lock:
            entries = self._read()
            for entry in entries:
                report = wanted.get(entry.get("id", ""))
                if report is None or online_state(entry) == ONLINE_OFF:
                    continue
                if str(report[WEBHOOK_FIELD]) != entry.get(WEBHOOK_FIELD):
                    continue
                entry[REPORT_FIELD] = {
                    WEBHOOK_FIELD: entry[WEBHOOK_FIELD],
                    "cloud_url": online_url(report.get("cloud_url")),
                    "external_url": online_url(report.get("external_url")),
                    "reported_at": stamp,
                }
                stored.append(entry)
            if stored:
                self._write(entries)
        return [online_state(entry) for entry in stored]

    def note_fetch(self, subscription_id):
        stamp = int(self.clock())
        with self._lock:
            entries = self._read()
            for entry in entries:
                if entry.get("id") != subscription_id:
                    continue
                if _as_epoch(entry.get(LAST_FETCH_FIELD)) == stamp:
                    return stamp
                entry[LAST_FETCH_FIELD] = stamp
                if not _as_epoch(entry.get(WATCH_FIELD)):
                    entry[WATCH_FIELD] = stamp
                self._write(entries)
                return stamp
        return 0

    def children_with_component(self, component):
        return {
            entry.get("child_key")
            for entry in self._read()
            if component in (entry.get("components") or []) and entry.get("child_key")
        }

    def children_with_timetable(self):
        return self.children_with_component(COMPONENT_TIMETABLE) | self.children_with_component(COMPONENT_OWN_ENTRIES)
