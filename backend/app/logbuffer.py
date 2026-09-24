import collections
import logging

CAPACITY = 2000
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity=CAPACITY):
        super().__init__(level=logging.INFO)
        self.records = collections.deque(maxlen=capacity)

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            self.handleError(record)
            return
        with self.lock:
            self.records.append(line)

    def lines(self):
        with self.lock:
            return list(self.records)

    def clear(self):
        with self.lock:
            self.records.clear()


BUFFER = None


def install(target=None, capacity=CAPACITY, log_format=LOG_FORMAT):
    global BUFFER
    handler = RingBufferHandler(capacity)
    handler.setFormatter(logging.Formatter(log_format))
    (target or logging.getLogger()).addHandler(handler)
    if target is None or target is logging.getLogger():
        BUFFER = handler
    return handler


def lines():
    return BUFFER.lines() if BUFFER is not None else []
