import threading
import time
import uuid

from . import marks
from .store import config_for_child
from .subscriptions import known_child

ERROR_CHILD = "api.cancellations.error.child"
ERROR_DATE = "api.cancellations.error.date"
ERROR_PERIOD = "api.cancellations.error.period"
ERROR_NOT_FOUND = "api.cancellations.error.notFound"


class CancellationError(Exception):
    def __init__(self, message_key):
        super().__init__(message_key)
        self.message_key = message_key


def entries_of(data):
    stored = (data or {}).get("cancellations")
    if not isinstance(stored, list):
        return []
    return [entry for entry in stored if isinstance(entry, dict)]


def slot_of(entry):
    return (
        str(entry.get("child_key") or ""),
        str(entry.get("date") or ""),
        int(entry.get("period") or 0),
        marks.plain_code(entry.get("subject_code")),
    )


def public_view(entry):
    return {
        "id": entry.get("id", ""),
        "child_key": entry.get("child_key", ""),
        "date": entry.get("date", ""),
        "period": int(entry.get("period") or 0),
        "subject_code": str(entry.get("subject_code") or ""),
        "created_at": int(entry.get("created_at") or 0),
    }


class CancellationRegistry:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or time.time
        self._lock = getattr(store, "lock", None) or threading.Lock()

    def _read(self):
        return entries_of(self.store.load_cancellations())

    def _write(self, entries):
        self.store.save_cancellations({"cancellations": entries})

    def _today(self):
        return marks.today_for(self.clock)

    def list(self, child_key=""):
        start, end = marks.window(self._today())
        result = []
        for entry in self._read():
            if child_key and entry.get("child_key") != child_key:
                continue
            if not marks.in_range(entry, start, end):
                continue
            result.append(public_view(entry))
        result.sort(key=lambda item: (item["date"], item["period"], item["id"]))
        return {
            "cancellations": result,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
        }

    def create(self, child_key, date_value, period, subject_code=""):
        config = self.store.load_config()
        if not known_child(config, child_key):
            raise CancellationError(ERROR_CHILD)
        try:
            date = marks.normalize_date(date_value, self._today())
        except marks.MarkError:
            raise CancellationError(ERROR_DATE)
        try:
            number = marks.normalize_period(period, config_for_child(self.store, child_key))
        except marks.MarkError:
            raise CancellationError(ERROR_PERIOD)
        entry = {
            "id": uuid.uuid4().hex,
            "child_key": child_key,
            "date": date,
            "period": number,
            "subject_code": marks.normalize_subject(subject_code) if subject_code else "",
            "created_at": int(self.clock()),
        }
        with self._lock:
            entries = self._read()
            taken = slot_of(entry)
            for stored in entries:
                if slot_of(stored) == taken:
                    return public_view(stored)
            entries.append(entry)
            self._write(entries)
        return public_view(entry)

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

    def delete(self, cancellation_id):
        with self._lock:
            entries = self._read()
            remaining = [entry for entry in entries if entry.get("id") != cancellation_id]
            if len(remaining) == len(entries):
                raise CancellationError(ERROR_NOT_FOUND)
            self._write(remaining)
        return {"deleted": cancellation_id}
