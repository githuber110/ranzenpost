import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from . import holidays
from .subscriptions import known_child, label_carries_child_name

WINDOW_WEEKS = 8
MAX_NAME_LENGTH = 60
FRESH_AFTER_SECONDS = 24 * 60 * 60
WEEK_SPAN_DAYS = 6

STATE_CONFIRMED = "confirmed"
STATE_SUBSTITUTED = "substituted"
STATE_FOREIGN = "foreign"
STATE_CANCELLED = "cancelled"
STATE_ORPHANED = "orphaned"
STATE_UNKNOWN = "unknown"
STATES = (
    STATE_CONFIRMED,
    STATE_SUBSTITUTED,
    STATE_FOREIGN,
    STATE_CANCELLED,
    STATE_ORPHANED,
    STATE_UNKNOWN,
)

ERROR_CHILD = "api.marks.error.child"
ERROR_DATE = "api.marks.error.date"
ERROR_PERIOD = "api.marks.error.period"
ERROR_SUBJECT = "api.marks.error.subject"
ERROR_DUPLICATE = "api.marks.error.duplicate"
ERROR_NAME = "api.marks.error.name"
ERROR_NAME_LENGTH = "api.marks.error.nameLength"
ERROR_NOT_FOUND = "api.marks.error.notFound"


class MarkError(Exception):
    def __init__(self, message_key):
        super().__init__(message_key)
        self.message_key = message_key


def window(today):
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(days=7 * WINDOW_WEEKS)
    end = monday + timedelta(days=7 * (WINDOW_WEEKS + 1) - 1)
    return start, end


def entries_of(data):
    stored = (data or {}).get("marks")
    if not isinstance(stored, list):
        return []
    return [entry for entry in stored if isinstance(entry, dict)]


def normalize_date(value, today):
    day = holidays.parse_day(value)
    if day is None:
        raise MarkError(ERROR_DATE)
    start, end = window(today)
    if day < start or day > end:
        raise MarkError(ERROR_DATE)
    return day.isoformat()


def period_numbers(config):
    times = (config or {}).get("period_times") or {}
    numbers = set()
    for key in times:
        try:
            numbers.add(int(str(key).strip()))
        except (TypeError, ValueError):
            continue
    return numbers


def normalize_period(value, config):
    if isinstance(value, bool):
        raise MarkError(ERROR_PERIOD)
    try:
        period = int(str(value).strip())
    except (TypeError, ValueError):
        raise MarkError(ERROR_PERIOD)
    if period not in period_numbers(config):
        raise MarkError(ERROR_PERIOD)
    return period


def normalize_subject(value):
    code = " ".join(str(value or "").split())
    if not code:
        raise MarkError(ERROR_SUBJECT)
    return code


def normalize_name(value, config):
    text = " ".join(str(value or "").split())
    if len(text) > MAX_NAME_LENGTH:
        raise MarkError(ERROR_NAME_LENGTH)
    if text and label_carries_child_name(text, config):
        raise MarkError(ERROR_NAME)
    return text


def slot_of(entry):
    return (
        str(entry.get("child_id") or ""),
        str(entry.get("date") or ""),
        int(entry.get("period") or 0),
    )


def public_view(entry, state=STATE_UNKNOWN):
    return {
        "id": entry.get("id", ""),
        "child_id": entry.get("child_id", ""),
        "date": entry.get("date", ""),
        "period": int(entry.get("period") or 0),
        "subject_code": entry.get("subject_code", ""),
        "name": entry.get("name", ""),
        "state": state,
        "created_at": int(entry.get("created_at") or 0),
        "updated_at": int(entry.get("updated_at") or 0),
    }


def week_for(child_snapshot, value):
    day = holidays.parse_day(value)
    if day is None:
        return None
    weeks = (child_snapshot or {}).get("weeks") or {}
    if not isinstance(weeks, dict):
        return None
    for week in weeks.values():
        if not isinstance(week, dict):
            continue
        start = holidays.parse_day(week.get("start_date"))
        if start is None:
            continue
        stored_end = holidays.parse_day(week.get("end_date"))
        end = start + timedelta(days=WEEK_SPAN_DAYS)
        if stored_end is not None and stored_end > end:
            end = stored_end
        if start <= day <= end:
            return week
    return None


def is_fresh(week, now_epoch):
    if not isinstance(week, dict):
        return False
    fetched = week.get("fetched_at")
    if not isinstance(fetched, (int, float)) or isinstance(fetched, bool):
        return False
    age = now_epoch - fetched
    return 0 <= age <= FRESH_AFTER_SECONDS


def lessons_at(week, entry):
    day = holidays.parse_day(entry.get("date"))
    period = int(entry.get("period") or 0)
    found = []
    for lesson in (week or {}).get("lessons") or []:
        if not isinstance(lesson, dict):
            continue
        if holidays.parse_day(lesson.get("date")) != day:
            continue
        try:
            number = int(str(lesson.get("period")).strip())
        except (TypeError, ValueError):
            continue
        if number == period:
            found.append(lesson)
    return found


def resolve_state(entry, week, now_epoch):
    if not is_fresh(week, now_epoch):
        return STATE_UNKNOWN
    slot = lessons_at(week, entry)
    if not slot:
        return STATE_ORPHANED
    code = str(entry.get("subject_code") or "")
    matching = [lesson for lesson in slot if str(lesson.get("subject_code") or "") == code]
    if not matching:
        return STATE_FOREIGN
    if any(str(lesson.get("change_kind") or "") == "cancelled" for lesson in matching):
        return STATE_CANCELLED
    if any(str(lesson.get("change_kind") or "") for lesson in matching):
        return STATE_SUBSTITUTED
    return STATE_CONFIRMED


def state_for(snapshot, entry, now_epoch):
    child = ((snapshot or {}).get("children") or {}).get(entry.get("child_id")) or {}
    week = week_for(child, entry.get("date"))
    if week is None:
        return STATE_UNKNOWN
    return resolve_state(entry, week, now_epoch)


def resolved_lesson(snapshot, entry, now_epoch):
    child = ((snapshot or {}).get("children") or {}).get(entry.get("child_id")) or {}
    week = week_for(child, entry.get("date"))
    if not is_fresh(week, now_epoch):
        return None
    code = str(entry.get("subject_code") or "")
    for lesson in lessons_at(week, entry):
        if str(lesson.get("subject_code") or "") == code:
            return lesson
    return None


def today_for(clock):
    return holidays.berlin_today(
        datetime.fromtimestamp(clock(), timezone.utc).replace(tzinfo=None)
    )


def in_range(entry, start, end):
    day = holidays.parse_day(entry.get("date"))
    return day is not None and start <= day <= end


class MarkRegistry:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or time.time
        self._lock = threading.Lock()

    def _read(self):
        return entries_of(self.store.load_marks())

    def _write(self, entries):
        self.store.save_marks({"marks": entries})

    def _today(self):
        return today_for(self.clock)

    def _refuse_duplicate(self, entries, candidate):
        taken = slot_of(candidate)
        for entry in entries:
            if entry.get("id") == candidate.get("id"):
                continue
            if slot_of(entry) == taken:
                raise MarkError(ERROR_DUPLICATE)

    def list(self, child_id=""):
        start, end = window(self._today())
        snapshot = self.store.load_calendar_snapshot()
        now = int(self.clock())
        result = []
        for entry in self._read():
            if child_id and entry.get("child_id") != child_id:
                continue
            if not in_range(entry, start, end):
                continue
            result.append(public_view(entry, state_for(snapshot, entry, now)))
        result.sort(key=lambda item: (item["date"], item["period"], item["id"]))
        return {"marks": result, "window": {"start": start.isoformat(), "end": end.isoformat()}}

    def create(self, child_id, date_value, period, subject_code, name=""):
        config = self.store.load_config()
        if not known_child(config, child_id):
            raise MarkError(ERROR_CHILD)
        stamp = int(self.clock())
        entry = {
            "id": uuid.uuid4().hex,
            "child_id": child_id,
            "date": normalize_date(date_value, self._today()),
            "period": normalize_period(period, config),
            "subject_code": normalize_subject(subject_code),
            "name": normalize_name(name, config),
            "created_at": stamp,
            "updated_at": stamp,
        }
        with self._lock:
            entries = self._read()
            self._refuse_duplicate(entries, entry)
            entries.append(entry)
            self._write(entries)
        return public_view(entry, self._state_of(entry))

    def update(self, mark_id, date_value=None, period=None, subject_code=None, name=None):
        config = self.store.load_config()
        with self._lock:
            entries = self._read()
            for index, stored in enumerate(entries):
                if stored.get("id") != mark_id:
                    continue
                entry = dict(stored)
                if date_value is not None:
                    entry["date"] = normalize_date(date_value, self._today())
                if period is not None:
                    entry["period"] = normalize_period(period, config)
                if subject_code is not None:
                    entry["subject_code"] = normalize_subject(subject_code)
                if name is not None:
                    entry["name"] = normalize_name(name, config)
                entry["updated_at"] = int(self.clock())
                self._refuse_duplicate(entries, entry)
                entries[index] = entry
                self._write(entries)
                return public_view(entry, self._state_of(entry))
        raise MarkError(ERROR_NOT_FOUND)

    def delete(self, mark_id):
        with self._lock:
            entries = self._read()
            remaining = [entry for entry in entries if entry.get("id") != mark_id]
            if len(remaining) == len(entries):
                raise MarkError(ERROR_NOT_FOUND)
            self._write(remaining)
        return {"deleted": mark_id}

    def children_with_marks(self):
        return {
            entry.get("child_id") for entry in self._read() if entry.get("child_id")
        }

    def _state_of(self, entry):
        return state_for(self.store.load_calendar_snapshot(), entry, int(self.clock()))
