import threading

REFUSAL_SECONDS = 24 * 3600


class Refusals:
    def __init__(self, clock, seconds=REFUSAL_SECONDS):
        self.clock = clock
        self.seconds = seconds
        self._lock = threading.Lock()
        self._entries = {}

    def status_of(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return 0
            if self.clock() - entry[0] >= self.seconds:
                del self._entries[key]
                return 0
            return entry[1]

    def refused(self, key):
        return bool(self.status_of(key))

    def note(self, key, status=403):
        with self._lock:
            self._entries[key] = (self.clock(), int(status or 403))

    def forget(self, key):
        with self._lock:
            self._entries.pop(key, None)

    def clear(self):
        with self._lock:
            self._entries.clear()
