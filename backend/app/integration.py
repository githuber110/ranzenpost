import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from . import blocks, cancellations, feed, holidays, marks, messages, modules, supervisor
from .iserv.absences import berlin_offset
from .iserv.errors import QUIET_SIGN_IN_REASONS, REASON_CODE_STEP_FAILED, REASON_RATE_LIMITED
from .mapping import configured_time
from .store import (
    INTEGRATION_SCHOOLS_KEY,
    children_of_config,
    config_for_child,
    config_for_connection,
    connection_display_name,
    connection_known,
    connection_of_key,
    edit,
)
from .subscriptions import (
    COMPONENT_ABSENCES,
    COMPONENT_MARKS,
    COMPONENT_OWN_ENTRIES,
    COMPONENT_PUBLIC_HOLIDAYS,
    COMPONENT_SCHOOL_HOLIDAYS,
    COMPONENT_TIMETABLE,
)

TOKEN_BYTES = 32
TOKEN_MIN_LENGTH = 43
TOKEN_MAX_LENGTH = 64
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

ACTIVE_WINDOW_SECONDS = 24 * 60 * 60
CONNECTED_WINDOW_SECONDS = 5 * 60
REQUEST_WRITE_INTERVAL_SECONDS = 60
MAX_CHANGES = 50
TIMEZONE = "Europe/Berlin"

ERROR_AUTH = "auth_failed"
AUTH_REASON = "auth_reason"
ERROR_NETWORK = "network"
ERROR_OUTAGE = "outage"
OUTAGE_SINCE = "outage_since"
OUTAGE_COUNT = "outage_count"
OUTAGE_REASON = "outage_reason"
OUTAGE_RETRY_AT = "outage_retry_at"
OUTAGE_NOTIFIED = "outage_notified"
OUTAGE_FIELDS = (OUTAGE_SINCE, OUTAGE_COUNT, OUTAGE_REASON, OUTAGE_RETRY_AT, OUTAGE_NOTIFIED)
LAST_SUCCESS = "last_success"
OUTAGE_SKIP_AFTER = 2
OUTAGE_BACKOFF_CAP_SECONDS = 2 * 60 * 60

KIND_CANCELLATION = "cancellation"
KIND_SUBSTITUTION = "substitution"
KIND_ROOM_CHANGE = "room_change"
KIND_NEW_LESSON = "new_lesson"
CHANGE_KINDS = (KIND_SUBSTITUTION, KIND_CANCELLATION, KIND_ROOM_CHANGE, KIND_NEW_LESSON)

LAST_REQUEST = "last_request"
CHANGE_KEYS = "change_keys"

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_UNREACHABLE = "unreachable"
STATUS_AUTH_FAILED = "auth_failed"

KIND_LESSONS = "lessons"
KIND_EXAMS = "exams"
KIND_ABSENCES = "absences"
KIND_HOLIDAYS = "holidays"
KIND_OWN_ENTRIES = "own_entries"
EVENT_COMPONENTS = {
    KIND_LESSONS: [COMPONENT_TIMETABLE],
    KIND_EXAMS: [COMPONENT_MARKS],
    KIND_ABSENCES: [COMPONENT_ABSENCES],
    KIND_HOLIDAYS: [COMPONENT_SCHOOL_HOLIDAYS, COMPONENT_PUBLIC_HOLIDAYS],
    KIND_OWN_ENTRIES: [COMPONENT_OWN_ENTRIES],
}
OWN_ENTRIES_SETTING = "own_entries_ha"
PURPOSE_CALENDAR = "calendar"
PURPOSE_CARD = "card"
PURPOSES = (PURPOSE_CALENDAR, PURPOSE_CARD)
MAX_EVENT_RANGE_DAYS = 400
VERSION_ENV = "ISERV_ADDON_VERSION"
LAST_UPDATED_FORMATS = ("%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")
ABSENCE_STATUS_REJECTED = "rejected"
CONFERENCE_TITLE_CELLS = 2
CONFERENCE_TITLE_SEPARATOR = " · "
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
LESSON_DAYS_AHEAD = 14
EXAM_DAYS_AHEAD = 30
MAX_NOTICES = 10
STAMP_SOURCE_ISERV = "iserv"
STAMP_SOURCE_APP = "app"
CHANGE_FIELDS = ("subject", "teacher", "room")

_version_cache = {}


def generate_token():
    return secrets.token_urlsafe(TOKEN_BYTES)


def is_valid_token(value):
    text = value if isinstance(value, str) else ""
    return TOKEN_MIN_LENGTH <= len(text) <= TOKEN_MAX_LENGTH and TOKEN_PATTERN.match(text) is not None


def ensure_token(store):
    reader = getattr(store, "load_integration_token", None)
    existing = reader() if callable(reader) else ""
    if is_valid_token(existing):
        return existing
    return rotate_token(store)


def rotate_token(store):
    token = generate_token()
    writer = getattr(store, "save_integration_token", None)
    if callable(writer):
        writer(token)
    return token


def state_of(store):
    reader = getattr(store, "load_integration_state", None)
    if not callable(reader):
        return {}
    try:
        data = reader()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(store, data):
    writer = getattr(store, "save_integration_state", None)
    if callable(writer):
        writer(data)


def edit_state(store, change):
    return edit(store, lambda: state_of(store), lambda data: save_state(store, data), change)


def _edit_school_slot(store, school_id, change):
    outcome = {}

    def apply(state):
        if not connection_known(store, school_id):
            return
        schools = state.get(INTEGRATION_SCHOOLS_KEY)
        schools = dict(schools) if isinstance(schools, dict) else {}
        stored = schools.get(school_id)
        stored = stored if isinstance(stored, dict) else {}
        slot = dict(stored)
        outcome["result"] = change(slot)
        outcome["slot"] = slot
        if slot != stored:
            schools[school_id] = slot
            state[INTEGRATION_SCHOOLS_KEY] = schools

    edit_state(store, apply)
    return outcome.get("result"), outcome.get("slot", {})


def _epoch(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def last_request(store):
    return _epoch(state_of(store).get(LAST_REQUEST))


def note_request(store, now_epoch):
    def change(state):
        previous = _epoch(state.get(LAST_REQUEST))
        if previous and now_epoch - previous < REQUEST_WRITE_INTERVAL_SECONDS:
            return
        state[LAST_REQUEST] = int(now_epoch)

    edit_state(store, change)


def is_active(store, now_epoch):
    seen = last_request(store)
    return bool(seen) and 0 <= now_epoch - seen <= ACTIVE_WINDOW_SECONDS


def is_connected(last_seen, now_epoch):
    return bool(last_seen) and 0 <= now_epoch - last_seen <= CONNECTED_WINDOW_SECONDS


def iso_local(local):
    offset = berlin_offset(local)
    return local.strftime("%Y-%m-%dT%H:%M:%S") + f"+{offset:02d}:00"


def berlin_iso(epoch):
    return iso_local(feed.berlin_moment(epoch))


def berlin_stamp(epoch):
    return feed.berlin_moment(epoch).strftime("%d.%m. %H:%M")


def change_key(lesson):
    return "|".join(
        [
            str(lesson.get("date") or ""),
            str(lesson.get("period") or ""),
            str(lesson.get("subject_code") or ""),
            str(lesson.get("change_kind") or ""),
            ",".join(sorted(str(name) for name in (lesson.get("changed_fields") or []))),
            str(lesson.get("room") or ""),
            str(lesson.get("teacher_code") or ""),
        ]
    )


def change_kind(lesson):
    kind = str(lesson.get("change_kind") or "")
    if kind == "cancelled":
        return KIND_CANCELLATION
    if kind == "added":
        return KIND_NEW_LESSON
    fields = {str(name) for name in (lesson.get("changed_fields") or [])}
    if fields and fields <= {"room"}:
        return KIND_ROOM_CHANGE
    return KIND_SUBSTITUTION


def change_event(language, child_key, lesson, now_epoch):
    day = holidays.parse_day(lesson.get("date"))
    return {
        "child_key": str(child_key or ""),
        "school_id": connection_of_key(child_key),
        "at": berlin_iso(now_epoch),
        "kind": change_kind(lesson),
        "summary": feed.lesson_summary(language, lesson),
        "date": day.isoformat() if day else "",
        "period": int(lesson.get("period") or 0),
        "new": True,
    }


def detect_changes(language, child_key, lessons, known_keys, now_epoch):
    current = {}
    for lesson in lessons or []:
        if not isinstance(lesson, dict) or not lesson.get("change_kind"):
            continue
        current[change_key(lesson)] = lesson
    if known_keys is None:
        return [], sorted(current)
    seen = set(known_keys)
    fresh = [
        change_event(language, child_key, lesson, now_epoch)
        for key, lesson in current.items()
        if key not in seen
    ]
    return fresh, sorted(current)


def _squeezed(value):
    return " ".join(str(value or "").split())


def _first_name(value):
    parts = _squeezed(value).split(" ")
    return parts[0] if parts else ""


def _published_day(value):
    day = holidays.parse_day(_squeezed(value).split(" ")[0])
    return day.isoformat() if day else ""


def notice_of(entry):
    if isinstance(entry, dict):
        return {
            "title": _squeezed(entry.get("title")),
            "sender": _squeezed(entry.get("sender") or entry.get("owner")),
            "date": _published_day(entry.get("published") or entry.get("date")),
            "child": _first_name(entry.get("child")),
        }
    return {"title": _squeezed(entry), "sender": "", "date": "", "child": ""}


def unread_notices(entries):
    return [notice_of(entry) for entry in entries or [] if isinstance(entry, dict) and entry.get("unread")]


def conference_rows(payload):
    if not isinstance(payload, dict) or payload.get("empty"):
        return []
    rows = []
    for item in payload.get("items") or []:
        cells = item.get("cells") if isinstance(item, dict) else None
        if isinstance(cells, list) and cells:
            rows.append([str(cell) for cell in cells])
    return rows


def record_poll(store, now_epoch, ok, error="", changes=()):
    def change(state):
        state["last_poll"] = int(now_epoch)
        state["last_poll_ok"] = bool(ok)
        state["last_error"] = str(error or "")
        kept = [dict(entry, new=False) for entry in state.get("changes") or [] if isinstance(entry, dict)]
        state["changes"] = (list(changes) + kept)[:MAX_CHANGES]

    edit_state(store, change)


def school_state(store, school_id):
    schools = state_of(store).get(INTEGRATION_SCHOOLS_KEY)
    slot = schools.get(school_id) if isinstance(schools, dict) else None
    return slot if isinstance(slot, dict) else {}


def record_school_poll(
    store,
    school_id,
    now_epoch,
    ok,
    error="",
    letters=None,
    posts=None,
    conferences=None,
    school_name=None,
    auth_reason="",
):
    def change(slot):
        slot["last_poll"] = int(now_epoch)
        slot["last_poll_ok"] = bool(ok)
        slot["last_error"] = str(error or "")
        if not ok and error == ERROR_AUTH and auth_reason:
            slot[AUTH_REASON] = str(auth_reason)
        else:
            slot.pop(AUTH_REASON, None)
        if ok:
            slot[LAST_SUCCESS] = int(now_epoch)
        if letters is not None:
            slot["letters"] = list(letters)
        if posts is not None:
            slot["posts"] = list(posts)
        if conferences is not None:
            slot["conferences"] = list(conferences)
        if school_name:
            slot["school_name"] = str(school_name)

    _edit_school_slot(store, school_id, change)


def outage_backoff(count, poll_interval):
    if count < OUTAGE_SKIP_AFTER:
        return 0
    return min(int(poll_interval) * 2 ** (count - 1), OUTAGE_BACKOFF_CAP_SECONDS)


def note_outage(store, school_id, now_epoch, reason, poll_interval, retry_after=None):
    def change(slot):
        count = int(slot.get(OUTAGE_COUNT) or 0) + 1
        slot[OUTAGE_SINCE] = _epoch(slot.get(OUTAGE_SINCE)) or int(now_epoch)
        slot[OUTAGE_COUNT] = count
        slot[OUTAGE_REASON] = str(reason or "")
        if retry_after is not None:
            wait = max(0, min(int(retry_after), OUTAGE_BACKOFF_CAP_SECONDS))
        else:
            wait = outage_backoff(count, poll_interval)
        slot[OUTAGE_RETRY_AT] = int(now_epoch) + wait if wait else 0

    return _edit_school_slot(store, school_id, change)[1]


def mark_outage_notified(store, school_id):
    _edit_school_slot(store, school_id, lambda slot: slot.update({OUTAGE_NOTIFIED: True}))


def end_outage(store, school_id):
    def change(slot):
        if not slot.get(OUTAGE_SINCE):
            return None
        return {name: slot.pop(name) for name in OUTAGE_FIELDS if name in slot}

    return _edit_school_slot(store, school_id, change)[0]


def outage_backoff_active(store, school_id, now_epoch):
    return _epoch(school_state(store, school_id).get(OUTAGE_RETRY_AT)) > int(now_epoch)


def outage_wait_left(slot, now_epoch):
    if not isinstance(slot, dict):
        return 0
    return max(0, _epoch(slot.get(OUTAGE_RETRY_AT)) - int(now_epoch))


def outage_rate_limited(store, school_id):
    return school_state(store, school_id).get(OUTAGE_REASON) == REASON_RATE_LIMITED


def lift_outage_backoff(store, school_id):
    def change(slot):
        if _epoch(slot.get(OUTAGE_RETRY_AT)):
            slot[OUTAGE_RETRY_AT] = 0

    _edit_school_slot(store, school_id, change)


def outage_view(store, school_id):
    slot = school_state(store, school_id)
    return {
        "since": _iso_or_none(_epoch(slot.get(OUTAGE_SINCE))),
        "last_success": _iso_or_none(_epoch(slot.get(LAST_SUCCESS))),
    }


def has_school_name(store, school_id):
    return bool(school_state(store, school_id).get("school_name"))


def addon_version():
    configured = str(os.environ.get(VERSION_ENV) or "").strip()
    if configured:
        return configured
    if not _version_cache.get("value"):
        _version_cache["value"] = supervisor.addon_version()
    return _version_cache.get("value") or ""


def utc_moment(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)


def _iso_or_none(value):
    return berlin_iso(value) if value else None


def default_event_range(today):
    return feed.lesson_window(today)


def children_of(config):
    return [
        {
            "key": child["key"],
            "name": str(child.get("name") or ""),
            "class_name": str(child.get("class_name") or ""),
        }
        for child in children_of_config(config)
    ]


def known_child(config, child_key):
    return any(child["key"] == child_key for child in children_of(config))


def _weekday(day):
    return WEEKDAYS[day.weekday()]


def _minutes_between(later, earlier):
    return max(0, int((later - earlier).total_seconds() // 60))


def _code_repair_needed(connection):
    check = getattr(connection, "code_refusal_needs_setup", None)
    return bool(callable(check) and check())


def _failed_poll(slot):
    return bool(slot.get("last_poll")) and not slot.get("last_poll_ok", True)


def _loud_sign_in_failure(slot):
    reason = slot.get(AUTH_REASON)
    return _failed_poll(slot) and slot.get("last_error") == ERROR_AUTH and reason not in QUIET_SIGN_IN_REASONS


def _school_status(connection, slot):
    if not connection.is_configured():
        return STATUS_UNCONFIGURED
    if _failed_poll(slot) and slot.get("last_error") == ERROR_OUTAGE:
        return STATUS_UNREACHABLE
    if _loud_sign_in_failure(slot) or _code_repair_needed(connection):
        return STATUS_AUTH_FAILED
    return STATUS_ERROR if _failed_poll(slot) else STATUS_OK


def _status_reason(connection, slot):
    if _school_status(connection, slot) != STATUS_AUTH_FAILED:
        return ""
    if not _loud_sign_in_failure(slot):
        return REASON_CODE_STEP_FAILED
    return str(slot.get(AUTH_REASON) or "bad_credentials")


def school_name_of(store, entry):
    named = dict(entry)
    if not named.get("school_name"):
        named["school_name"] = str(school_state(store, entry.get("id", "")).get("school_name") or "")
    return connection_display_name(named)


def disabled_modules(store):
    disabled = set(blocks.normalize_modules_disabled(store.load_config().get("modules_disabled")))
    return {name: name in disabled for name in modules.MODULES}


def build_schools(service, store):
    schools = []
    disabled = disabled_modules(store)
    for entry in store.connections():
        if not entry.get("setup_complete"):
            continue
        connection = service.connection(entry["id"])
        slot = school_state(store, entry["id"])
        schools.append(
            {
                "id": entry["id"],
                "name": school_name_of(store, entry),
                "url_host": supervisor.sanitize_host(entry.get("school_url")),
                "modules": modules.registry_of(connection)["modules"],
                "disabled": dict(disabled),
                "status": _school_status(connection, slot),
                "status_reason": _status_reason(connection, slot),
                "children": children_of(entry),
                "last_poll": _iso_or_none(_epoch(slot.get("last_poll"))),
                "last_success": _iso_or_none(_epoch(slot.get(LAST_SUCCESS))),
                "own_entries": entry.get(OWN_ENTRIES_SETTING) is True,
            }
        )
    return schools


def own_entries_shared(store, child_key):
    return config_for_child(store, child_key).get(OWN_ENTRIES_SETTING) is True


def build_info(service, store, now_epoch, feed_port_open):
    config = store.load_config()
    state = state_of(store)
    return {
        "version": addon_version(),
        "schools": build_schools(service, store),
        "language": messages.normalize_language(config.get("language")),
        "timezone": TIMEZONE,
        "feed_port_open": bool(feed_port_open),
        "last_poll": _iso_or_none(_epoch(state.get("last_poll"))),
        "ingress_path": supervisor.ingress_path(),
    }


def _change_values(lesson):
    fields = [name for name in (lesson.get("changed_fields") or []) if name in CHANGE_FIELDS]
    previous = lesson.get("previous") or {}
    before = {name: str(feed.previous_value(previous, name) or "") for name in fields}
    after = {name: str(feed.field_value(lesson, name) or "") for name in fields}
    return before, after


def _lesson_object(language, day, lesson, start_time, cancelled, local_now):
    start = feed.lesson_start(day, start_time)
    end = start + timedelta(minutes=feed.LESSON_MINUTES)
    shown = dict(lesson, change_kind="cancelled") if cancelled else lesson
    changed = bool(lesson.get("change_kind"))
    before, after = _change_values(lesson)
    return {
        "date": day.isoformat(),
        "weekday": _weekday(day),
        "period": int(lesson.get("period") or 0),
        "subject": feed.subject_of(language, lesson),
        "subject_code": str(lesson.get("subject_code") or ""),
        "teacher": feed.field_value(lesson, "teacher"),
        "room": str(lesson.get("room") or ""),
        "start": iso_local(start),
        "end": iso_local(end),
        "substitution": changed and not cancelled,
        "cancelled": bool(cancelled),
        "kind": KIND_CANCELLATION if cancelled else (change_kind(lesson) if changed else ""),
        "before": before,
        "after": after,
        "note": feed.change_note(language, shown),
        "minutes_until": _minutes_between(start, local_now),
        "minutes_left": _minutes_between(end, local_now),
    }


def _day_lessons(language, config, snapshot, child_key, day, day_map, blocked, dropped, local_now):
    if blocked or (day_map.get(day.isoformat()) or {}).get("overrides_lessons"):
        return []
    collected = feed.lessons_in_window(snapshot, child_key, day, day, config)
    items = []
    for _, (_, lesson) in sorted(collected.items(), key=lambda item: (item[0][1], item[0][2:])):
        period = int(lesson.get("period") or 0)
        start_time = configured_time(config, period) or str(lesson.get("start_time") or "").strip()
        if not start_time:
            continue
        cancelled = lesson.get("change_kind") == "cancelled" or (day, period) in dropped
        items.append(_lesson_object(language, day, lesson, start_time, cancelled, local_now))
    items.sort(key=lambda item: item["start"])
    return items


def _held(items):
    return [item for item in items if not item["cancelled"]]


def _next_school_day(days, today, now_iso):
    for day, items in days:
        held = _held(items)
        if not held:
            continue
        if day == today and held[0]["start"] <= now_iso:
            continue
        return {
            "date": day.isoformat(),
            "weekday": _weekday(day),
            "days_until": (day - today).days,
            "start": held[0]["start"],
            "end": max(item["end"] for item in held),
            "lessons": len(held),
            "first_lesson": held[0]["subject"],
        }
    return None


def _exam_object(language, config, snapshot, entry, today, now_epoch):
    day = holidays.parse_day(entry.get("date"))
    period = int(entry.get("period") or 0)
    start_time = configured_time(config, period)
    lesson = marks.resolved_lesson(snapshot, entry, now_epoch) or {}
    start = feed.lesson_start(day, start_time) if start_time else None
    return {
        "date": day.isoformat(),
        "weekday": _weekday(day),
        "days_until": (day - today).days,
        "period": period,
        "subject": feed.mark_subject(language, config, entry),
        "subject_code": str(entry.get("subject_code") or ""),
        "name": str(entry.get("name") or ""),
        "start": iso_local(start) if start else None,
        "end": iso_local(start + timedelta(minutes=feed.LESSON_MINUTES)) if start else None,
        "teacher": feed.field_value(lesson, "teacher") if lesson else "",
        "room": str(lesson.get("room") or "") if lesson else "",
    }


def _upcoming_exams(language, config, store, snapshot, child_key, today, now_epoch):
    horizon = today + timedelta(days=EXAM_DAYS_AHEAD)
    chosen = []
    for entry in marks.entries_of(store.load_marks()):
        if entry.get("child_key") != child_key or not marks.in_range(entry, today, horizon):
            continue
        chosen.append(_exam_object(language, config, snapshot, entry, today, now_epoch))
    chosen.sort(key=lambda item: (item["date"], item["period"]))
    return chosen


def _open_absences(language, snapshot, child_key, today):
    items = []
    for entry in feed.stored_absences(snapshot, child_key):
        status = str(entry.get("status") or "")
        if feed.absence_is_settled(entry) or status == ABSENCE_STATUS_REJECTED:
            continue
        first = holidays.parse_day(entry.get("from_date"))
        last = holidays.parse_day(entry.get("till_date")) or first
        items.append(
            {
                "kind": str(entry.get("kind") or ""),
                "summary": feed.absence_summary(language, entry),
                "start": first.isoformat() if first else "",
                "end": last.isoformat() if last else "",
                "status": status,
                "days_until": (first - today).days if first else 0,
            }
        )
    items.sort(key=lambda item: item["start"] or "9999-12-31")
    return items


def _next_absence(open_absences, today):
    for item in open_absences:
        if item["end"] and item["end"] < today.isoformat():
            continue
        return dict(item, days_until=max(0, item["days_until"]))
    return None


def _last_updated(config, snapshot, child_key):
    entry = (config.get("poll_state") or {}).get(child_key) or {}
    text = str(entry.get("last_updated") or "").strip()
    for pattern in LAST_UPDATED_FORMATS:
        try:
            return iso_local(datetime.strptime(text, pattern)), STAMP_SOURCE_ISERV
        except ValueError:
            continue
    fetched = feed.last_success(snapshot, child_key)
    if fetched:
        return berlin_iso(fetched), STAMP_SOURCE_APP
    return None, ""


def _counted(entries):
    values = [notice_of(entry) for entry in entries or []]
    return {"count": len(values), "items": values[:MAX_NOTICES]}


def build_state(store, holiday_calendar, child_key, now_epoch):
    config = config_for_child(store, child_key)
    language = messages.normalize_language(config.get("language"))
    state = school_state(store, connection_of_key(child_key))
    snapshot = store.load_calendar_snapshot()
    local_now = feed.berlin_moment(now_epoch)
    today = local_now.date()
    horizon = today + timedelta(days=LESSON_DAYS_AHEAD)
    payload = holiday_calendar.range_info(today, horizon, config)
    blocked = payload.get("status") != holidays.STATUS_OK
    day_map = payload.get("days") or {}
    dropped = feed.dropped_slots(cancellations.entries_of(store.load_cancellations()), child_key)
    days = [
        (day, _day_lessons(language, config, snapshot, child_key, day, day_map, blocked, dropped, local_now))
        for day in (today + timedelta(days=offset) for offset in range(LESSON_DAYS_AHEAD + 1))
    ]
    today_lessons = days[0][1]
    held_today = _held(today_lessons)
    held_ahead = [item for _, items in days for item in _held(items)]
    now_iso = iso_local(local_now)
    now_lesson = next((item for item in held_today if item["start"] <= now_iso < item["end"]), None)
    next_lesson = next((item for item in held_ahead if item["start"] > now_iso), None)
    changes_today = [item for item in today_lessons if item["substitution"] or item["cancelled"]]
    open_absences = _open_absences(language, snapshot, child_key, today)
    exams = _upcoming_exams(language, config, store, snapshot, child_key, today, now_epoch)
    stamp, source = _last_updated(config, snapshot, child_key)
    return {
        "now_lesson": now_lesson,
        "next_lesson": next_lesson,
        "school_end_today": max((item["end"] for item in held_today), default=None),
        "next_school_day": _next_school_day(days, today, now_iso),
        "changes_today": changes_today,
        "unread_letters": _counted(state.get("letters")),
        "unread_posts": _counted(state.get("posts")),
        "open_absences": {"count": len(open_absences), "items": open_absences},
        "next_absence": _next_absence(open_absences, today),
        "next_exam": exams[0] if exams else None,
        "exams_upcoming": {"count": len(exams), "items": exams, "days": EXAM_DAYS_AHEAD},
        "school_day_today": bool(today_lessons),
        "timetable_changed_today": bool(changes_today),
        "timetable_last_updated": stamp,
        "timetable_last_updated_source": source,
    }


def has_snapshot(store, child_key):
    child = ((store.load_calendar_snapshot() or {}).get("children") or {}).get(child_key) or {}
    return bool(child.get("weeks"))


def _event_day(value):
    return value.date() if isinstance(value, datetime) else value


def _serialize_event(event):
    if event.all_day:
        start, end = event.start.isoformat(), event.end.isoformat()
    else:
        start, end = iso_local(event.start), iso_local(event.end)
    return {
        "uid": event.uid,
        "summary": event.summary,
        "description": event.description,
        "location": event.location,
        "start": start,
        "end": end,
        "all_day": bool(event.all_day),
        "cancelled": bool(event.cancelled),
        "color": event.color or "",
        "subject_code": event.subject_code or "",
        "subject": event.subject or "",
        "name": event.name or "",
        "kind": event.kind or "",
    }


def build_events(store, holiday_calendar, child_key, kind, start, end, now_epoch, school_id="", purpose=PURPOSE_CALENDAR):
    if kind == KIND_OWN_ENTRIES:
        if purpose != PURPOSE_CARD and not own_entries_shared(store, child_key):
            return []
        school_id = connection_of_key(child_key)
    subscription = {
        "child_key": child_key,
        "school_id": school_id or connection_of_key(child_key),
        "components": list(EVENT_COMPONENTS[kind]),
        "label": "",
        "color": "",
    }
    events = feed.gather_events(subscription, store, holiday_calendar, utc_moment(now_epoch))
    chosen = []
    for event in events:
        first = _event_day(event.start)
        last = _event_day(event.end) - timedelta(days=1) if event.all_day else _event_day(event.end)
        if last < start or first > end:
            continue
        chosen.append(_serialize_event(event))
    return chosen


def _conference_date(cells):
    for cell in cells:
        day = holidays.parse_day(cell)
        if day is not None:
            return day
    return None


def _conference_title(cells, day):
    rest = [cell for cell in cells if holidays.parse_day(cell) != day]
    return CONFERENCE_TITLE_SEPARATOR.join(cell for cell in rest[:CONFERENCE_TITLE_CELLS] if cell)


def next_conference(state, today):
    candidates = []
    for cells in state.get("conferences") or []:
        if not isinstance(cells, list):
            continue
        day = _conference_date(cells)
        if day is None or day < today:
            continue
        candidates.append((day, cells))
    if not candidates:
        return None
    day, cells = min(candidates, key=lambda item: item[0])
    return {
        "date": day.isoformat(),
        "title": _conference_title(cells, day),
        "details": [cell for cell in cells if cell and holidays.parse_day(cell) != day],
        "days_until": (day - today).days,
    }


def build_school(store, holiday_calendar, now_epoch, school_id=""):
    config = config_for_connection(store, school_id)
    language = messages.normalize_language(config.get("language"))
    today = feed.berlin_moment(now_epoch).date()
    horizon = today + timedelta(days=feed.HOLIDAY_DAYS_AHEAD)
    payload = holiday_calendar.range_info(today, horizon, config)
    day_map = payload.get("days") or {}
    next_holiday = None
    for span in feed.holiday_spans(language, day_map, today, horizon, holidays.KIND_SCHOOL):
        if span["end"] >= today:
            next_holiday = {
                "name": span["name"],
                "start": span["start"].isoformat(),
                "end": span["end"].isoformat(),
                "days_until": max(0, (span["start"] - today).days),
            }
            break
    return {
        "next_holiday": next_holiday,
        "next_conference": next_conference(school_state(store, school_id), today),
        "region": str(config.get("holiday_region") or ""),
    }


def build_changes(store):
    entries = []
    for entry in state_of(store).get("changes") or []:
        if not isinstance(entry, dict):
            continue
        entries.append(
            {
                "child_key": str(entry.get("child_key") or ""),
                "school_id": str(entry.get("school_id") or connection_of_key(entry.get("child_key"))),
                "at": str(entry.get("at") or ""),
                "kind": str(entry.get("kind") or ""),
                "summary": str(entry.get("summary") or ""),
                "date": str(entry.get("date") or ""),
                "period": int(entry.get("period") or 0),
                "new": bool(entry.get("new")),
            }
        )
    return entries[:MAX_CHANGES]
