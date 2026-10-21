import logging
import threading
import time

from . import supervisor
from .versions import clean_version, parse_version

STATE_NEWER = "newer"
STATE_CURRENT = "current"
STATE_UNKNOWN = "unknown"
CACHE_SECONDS = 3600
RETRY_SECONDS = 300

logger = logging.getLogger(__name__)


def evaluate(info):
    info = info if isinstance(info, dict) else {}
    slug = str(info.get("slug") or "").strip()
    version = parse_version(clean_version(info.get("version")))
    latest_text = clean_version(info.get("latest"))
    latest = parse_version(latest_text)
    if version is None or latest is None:
        return {"state": STATE_UNKNOWN, "latest": "", "slug": slug}
    if latest > version:
        return {"state": STATE_NEWER, "latest": latest_text, "slug": slug}
    return {"state": STATE_CURRENT, "latest": "", "slug": slug}


class AppUpdateCheck:
    def __init__(self, fetch=None, clock=time.monotonic):
        self.fetch = fetch
        self.clock = clock
        self.lock = threading.Lock()
        self.entry = None

    def forget(self):
        with self.lock:
            self.entry = None

    def status(self):
        now = self.clock()
        with self.lock:
            if self.entry is not None and now < self.entry[0]:
                return dict(self.entry[1])
        try:
            result = evaluate((self.fetch or supervisor.self_update_info)())
        except Exception:
            logger.warning("the app update check could not ask the supervisor", exc_info=True)
            result = evaluate(None)
        if result["state"] == STATE_NEWER:
            logger.info("a newer app version is available: %s", result["latest"])
        ttl = RETRY_SECONDS if result["state"] == STATE_UNKNOWN else CACHE_SECONDS
        with self.lock:
            self.entry = (now + ttl, result)
        return dict(result)


CHECK = AppUpdateCheck()


def status():
    return CHECK.status()


def report_line(result):
    if result.get("state") == STATE_NEWER:
        return "- Newer app available: %s" % result.get("latest")
    if result.get("state") == STATE_CURRENT:
        return "- App update check: up to date"
    return "- App update check: unknown"
