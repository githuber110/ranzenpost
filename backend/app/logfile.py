import logging
import logging.handlers
import re
from pathlib import Path

from . import logbuffer

timeline = logging.getLogger("timeline")

DIR_NAME = "log"
FILE_NAME = "ranzenpost.log"
VERSION_FILE = "last-version"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3
UNKNOWN_VERSION = "unknown"
START_MARK = "=== add-on start, version %s ==="
CHANGE_MARK = "=== version change %s -> %s ==="
STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
START_LINE = re.compile(r"=== add-on start, version (\S+) ===")
CHANGE_LINE = re.compile(r"=== version change (\S+) -> (\S+) ===")


class ScrubbingFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, path, scrub=None, max_bytes=MAX_BYTES, backups=BACKUPS):
        super().__init__(str(path), maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True)
        self.scrub = scrub
        self.setLevel(logging.INFO)

    def format(self, record):
        line = super().format(record)
        if self.scrub is None:
            return line
        try:
            return self.scrub(line)
        except Exception:
            return line


HANDLER = None


def log_dir(data_dir):
    return Path(data_dir) / DIR_NAME


def install(data_dir, scrub=None, target=None, max_bytes=MAX_BYTES, backups=BACKUPS, log_format=logbuffer.LOG_FORMAT):
    global HANDLER
    directory = log_dir(data_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = ScrubbingFileHandler(directory / FILE_NAME, scrub, max_bytes, backups)
    except OSError:
        logging.getLogger(__name__).warning("the log file in %s could not be opened", directory, exc_info=True)
        return None
    handler.setFormatter(logging.Formatter(log_format))
    (target or logging.getLogger()).addHandler(handler)
    if target is None or target is logging.getLogger():
        HANDLER = handler
    return handler


def files(handler=None):
    handler = handler or HANDLER
    if handler is None:
        return []
    current = Path(handler.baseFilename)
    found = []
    for index in range(handler.backupCount, 0, -1):
        rotated = current.with_name("%s.%d" % (current.name, index))
        if rotated.exists():
            found.append(rotated)
    if current.exists():
        found.append(current)
    return found


def lines(handler=None):
    handler = handler or HANDLER
    if handler is None:
        return logbuffer.lines()
    if handler.stream is not None:
        try:
            handler.flush()
        except Exception:
            pass
    collected = []
    for path in files(handler):
        try:
            collected.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return collected


def capacity(handler=None):
    handler = handler or HANDLER
    if handler is None:
        return 0, 0
    return handler.backupCount + 1, handler.maxBytes


def mark_start(version_reader, data_dir):
    try:
        version = str(version_reader() or "").strip() or UNKNOWN_VERSION
    except Exception:
        version = UNKNOWN_VERSION
    timeline.info(START_MARK, version)
    if version == UNKNOWN_VERSION:
        return version
    marker = log_dir(data_dir) / VERSION_FILE
    try:
        previous = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    except OSError:
        previous = ""
    if previous and previous != version:
        timeline.info(CHANGE_MARK, previous, version)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(version, encoding="utf-8")
    except OSError:
        timeline.info("the last version could not be stored")
    return version


def _stamp_of(line):
    match = STAMP.match(line)
    return match.group(1) if match else ""


def summarize(log_lines):
    stamps = [stamp for stamp in (_stamp_of(line) for line in log_lines) if stamp]
    starts = []
    changes = []
    for line in log_lines:
        start = START_LINE.search(line)
        if start:
            starts.append((_stamp_of(line), start.group(1)))
            continue
        change = CHANGE_LINE.search(line)
        if change:
            changes.append((_stamp_of(line), change.group(1), change.group(2)))
    return {
        "lines": len(log_lines),
        "first": stamps[0] if stamps else "",
        "last": stamps[-1] if stamps else "",
        "starts": starts,
        "changes": changes,
    }


def covered_line(summary):
    if not summary["first"]:
        return "- Covered: no timestamped lines"
    return "- Covered: %s to %s" % (summary["first"], summary["last"])


def size_text(size):
    if size >= 1024 * 1024:
        return "%d MB" % (size // (1024 * 1024))
    if size >= 1024:
        return "%d KB" % (size // 1024)
    return "%d B" % size


def header(summary, handler=None):
    count, size = capacity(handler)
    lines = ["# Ranzenpost log", covered_line(summary), "- Lines: %d" % summary["lines"]]
    if count:
        lines.append("- Kept: up to %d files of %s each, oldest first" % (count, size_text(size)))
    else:
        lines.append("- Kept: since the last start only")
    lines.append("- Add-on starts: %d" % len(summary["starts"]))
    for stamp, version in summary["starts"]:
        lines.append("  - %s start, version %s" % (stamp or "-", version))
    lines.append("- Version changes: %d" % len(summary["changes"]))
    for stamp, before, after in summary["changes"]:
        lines.append("  - %s %s -> %s" % (stamp or "-", before, after))
    return lines
