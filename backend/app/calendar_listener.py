import logging
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8100
DEFAULT_HOST = "0.0.0.0"

INVALID_REQUEST_LOGGER_NAME = "uvicorn.error"
INVALID_REQUEST_MESSAGE = "Invalid HTTP request received."
INVALID_REQUEST_SUMMARY_INTERVAL = 60.0
LISTENER_THREAD_NAME = "calendar-listener"


class InvalidRequestSummarizer(logging.Filter):
    def __init__(self, clock=None, on_summary=None, thread_name=None):
        super().__init__()
        self.thread_name = thread_name
        self.clock = clock or time.monotonic
        self.on_summary = on_summary or self._log_summary
        self._lock = threading.Lock()
        self._count = 0
        self._window_start = self.clock()

    def filter(self, record):
        if self.thread_name is not None and record.threadName != self.thread_name:
            return True
        if record.getMessage() != INVALID_REQUEST_MESSAGE:
            return True
        with self._lock:
            self._count += 1
            self._flush_if_due()
        return False

    def flush(self):
        with self._lock:
            self._flush_if_due(force=True)

    def _flush_if_due(self, force=False):
        now = self.clock()
        if not force and now - self._window_start < INVALID_REQUEST_SUMMARY_INTERVAL:
            return
        if self._count:
            self.on_summary(self._count)
        self._count = 0
        self._window_start = now

    def _log_summary(self, count):
        logger.info("calendar listener saw %s invalid HTTP request(s) in the last minute", count)


def start_calendar_listener(app, port=DEFAULT_PORT, host=DEFAULT_HOST):
    import uvicorn

    summarizer = InvalidRequestSummarizer(thread_name=LISTENER_THREAD_NAME)
    logging.getLogger(INVALID_REQUEST_LOGGER_NAME).addFilter(summarizer)

    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    )

    def run():
        try:
            server.run()
        except Exception:
            logger.warning("calendar listener stopped", exc_info=True)
        finally:
            summarizer.flush()
            logging.getLogger(INVALID_REQUEST_LOGGER_NAME).removeFilter(summarizer)

    thread = threading.Thread(target=run, daemon=True, name=LISTENER_THREAD_NAME)
    thread.start()
    return thread
