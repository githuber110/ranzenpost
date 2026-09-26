import logging
import re
from urllib.parse import urljoin, urlsplit

from . import logfile
from .pathpattern import path_only, path_pattern
from .valueshape import link_shape, table_cell

logger = logging.getLogger("iserv")

ISERV_ROOT = "/iserv"
SCHOOL_APP_PREFIX = "/iserv/dieschulapp/api/"
MATRIX_PREFIX = "/_matrix/"
SEGMENT_TAGS = {
    "time-table": "timetable",
    "dsa-timetable": "timetable",
    "parentletter": "letters",
    "parentconference": "conferences",
    "messenger": "messenger",
    "dsa-pinboard": "pinboard",
    "dsa-absences": "absences",
    "auth": "auth",
    "login": "auth",
    "app": "app",
}
SCHOOL_APP_TAGS = (
    ("pinboards", "pinboard"),
    ("sickNotes", "absences"),
    ("requestToSchools", "absences"),
    ("userSelection", "absences"),
    ("school-settings", "absences"),
    ("current-timetable", "timetable"),
    ("timetable-slots", "timetable"),
    ("timetable", "timetable"),
)
SCHOOL_APP_TAG = "school-app"
MATRIX_TAG = "messenger"
START_TAG = "start"
OTHER_TAG = "other"
OTHER_HOST_MARK = "<other host>"
REQUEST_LOG_LINE = re.compile(
    r"\biserv: (?P<tag>[\w-]+) (?P<method>[A-Z]+) (?P<path>\S+) (?P<status>\d+) \S+ (?P<length>\d+)B (?P<duration>\d+)ms"
    r"(?:.* (?P<school>school#[0-9a-f]+))?"
)
SLOW_REQUEST_MS = 3000
ERROR_STATUS_MIN = 400
REQUESTS_TABLE_HEAD = "| Area | Requests | Max duration | Statuses |"
REQUESTS_TABLE_RULE = "|---|---|---|---|"
MAX_REQUEST_ROWS = 30
SYNC_PATH_MARKER = "/sync"


def module_tag(path):
    path = path_only(path)
    if path.startswith(MATRIX_PREFIX):
        return MATRIX_TAG
    if path.startswith(SCHOOL_APP_PREFIX):
        versioned = path[len(SCHOOL_APP_PREFIX):]
        rest = versioned.split("/", 1)[1] if "/" in versioned else ""
        for marker, tag in SCHOOL_APP_TAGS:
            if rest.startswith(marker):
                return tag
        return SCHOOL_APP_TAG
    if path.rstrip("/") == ISERV_ROOT:
        return START_TAG
    if not path.startswith(ISERV_ROOT + "/"):
        return OTHER_TAG
    segment = path[len(ISERV_ROOT) + 1:].split("/", 1)[0].strip().lower()
    return SEGMENT_TAGS.get(segment, segment or START_TAG)


def content_type_of(headers):
    raw = str((headers or {}).get("Content-Type") or "")
    return raw.split(";", 1)[0].strip().lower()


def _body_unread(response):
    return getattr(response, "_content", None) is False


def body_length(response):
    if _body_unread(response):
        return 0
    declared = str((getattr(response, "headers", None) or {}).get("Content-Length") or "").strip()
    if declared.isdigit():
        return int(declared)
    content = getattr(response, "content", None)
    return len(content) if isinstance(content, (bytes, bytearray)) else 0


def duration_ms(response):
    elapsed = getattr(response, "elapsed", None)
    return int(elapsed.total_seconds() * 1000) if elapsed is not None else 0


def url_host(url):
    try:
        return (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _location(response, url, home):
    raw = str((getattr(response, "headers", None) or {}).get("Location") or "")
    if not raw:
        return ""
    try:
        target = url_host(urljoin(str(url or ""), raw))
    except ValueError:
        return OTHER_HOST_MARK
    if target and target != home:
        return OTHER_HOST_MARK
    return link_shape(raw)


def describe(response, own_host=""):
    request = getattr(response, "request", None)
    url = getattr(response, "url", "") or ""
    host = url_host(url)
    home = str(own_host or "").lower() or host
    foreign = bool(host) and host != home
    raw = "" if foreign else path_pattern(url)
    return {
        "method": str(getattr(request, "method", "") or "GET").upper(),
        "path": OTHER_HOST_MARK if foreign else link_shape(raw),
        "tag": module_tag(OTHER_HOST_MARK if foreign else raw),
        "status": int(getattr(response, "status_code", 0) or 0),
        "content_type": content_type_of(getattr(response, "headers", None)),
        "length": body_length(response),
        "duration_ms": duration_ms(response),
        "location": _location(response, url, home),
    }


def log_response(response, *args, own_host="", **kwargs):
    try:
        facts = describe(response, own_host)
        line = "%s %s %s %s %s %sB %sms" % (
            facts["tag"],
            facts["method"],
            facts["path"],
            facts["status"],
            facts["content_type"] or "-",
            facts["length"],
            facts["duration_ms"],
        )
        if facts["location"]:
            line += " -> " + facts["location"]
        logger.info(line + school_suffix(response))
    except Exception:
        logger.debug("request log line failed", exc_info=True)
    return response


class HostLog:
    def __init__(self, own_host):
        self.own_host = str(own_host or "").lower()

    def __call__(self, response, *args, **kwargs):
        return log_response(response, own_host=self.own_host)

    def __eq__(self, other):
        return isinstance(other, HostLog) and other.own_host == self.own_host

    def __hash__(self):
        return hash(self.own_host)


def _ours(hook):
    return hook is log_response or isinstance(hook, HostLog)


def install(session, own_host=""):
    hooks = getattr(session, "hooks", None)
    if not isinstance(hooks, dict):
        return session
    listed = hooks.setdefault("response", [])
    if not own_host:
        if not any(_ours(hook) for hook in listed):
            listed.append(log_response)
        return session
    wanted = HostLog(own_host)
    listed[:] = [hook for hook in listed if not _ours(hook) or hook == wanted]
    if wanted not in listed:
        listed.append(wanted)
    return session


SCHOOL_ATTRIBUTE = "ranzenpost_school"


def tag_school(client, school):
    adapters = getattr(getattr(client, "session", None), "adapters", None)
    if school and isinstance(adapters, dict):
        for adapter in adapters.values():
            setattr(adapter, SCHOOL_ATTRIBUTE, str(school))
    return client


def school_of(adapter):
    return str(getattr(adapter, SCHOOL_ATTRIBUTE, "") or "")


def school_suffix(response):
    school = school_of(getattr(response, "connection", None))
    return f" school#{school}" if school else ""


def _slow_or_failed(log_lines):
    for line in log_lines or ():
        match = REQUEST_LOG_LINE.search(line)
        if not match:
            continue
        status = int(match.group("status"))
        duration = int(match.group("duration"))
        if status == 0 or status >= ERROR_STATUS_MIN or duration >= SLOW_REQUEST_MS:
            yield _area(match), status, duration


def _area(match):
    school = match.group("school")
    return "%s %s" % (match.group("tag"), school) if school else match.group("tag")


def slow_request_lines(log_lines):
    buckets = {}
    for tag, status, duration in _slow_or_failed(log_lines):
        bucket = buckets.setdefault(tag, {"count": 0, "max_ms": 0, "statuses": []})
        bucket["count"] += 1
        bucket["max_ms"] = max(bucket["max_ms"], duration)
        if status not in bucket["statuses"]:
            bucket["statuses"].append(status)
    lines = ["### Slow or failed requests"]
    if not buckets:
        lines.append("- None found in the log")
        return lines
    lines.append(REQUESTS_TABLE_HEAD)
    lines.append(REQUESTS_TABLE_RULE)
    for tag in list(buckets)[:MAX_REQUEST_ROWS]:
        bucket = buckets[tag]
        statuses = ", ".join(str(status) for status in sorted(bucket["statuses"]))
        lines.append("| %s | %d | %dms | %s |" % (table_cell(tag), bucket["count"], bucket["max_ms"], table_cell(statuses)))
    if len(buckets) > MAX_REQUEST_ROWS:
        lines.append("- Areas skipped: %d beyond the limit of %d" % (len(buckets) - MAX_REQUEST_ROWS, MAX_REQUEST_ROWS))
    return lines


def _messenger_sync_sizes(log_lines):
    sizes = []
    for line in log_lines or ():
        match = REQUEST_LOG_LINE.search(line)
        if not match or match.group("tag") != MATRIX_TAG or SYNC_PATH_MARKER not in match.group("path"):
            continue
        sizes.append((match.group("school") or "", int(match.group("length"))))
    return sizes


def messenger_sync_lines(log_lines):
    found = _messenger_sync_sizes(log_lines)
    if not found:
        return ["### Messenger sync", "- Sync queries: none found in the log"]
    sizes = [size for _, size in found]
    total = sum(sizes)
    lines = [
        "### Messenger sync",
        "- Sync queries: %d" % len(sizes),
        "- Size: total %s, average %s, max %s" % (
            logfile.size_text(total), logfile.size_text(total // len(sizes)), logfile.size_text(max(sizes)),
        ),
    ]
    schools = []
    for school, _ in found:
        if school and school not in schools:
            schools.append(school)
    for school in schools:
        own = [size for tagged, size in found if tagged == school]
        lines.append("- %s: %d queries, total %s, max %s" % (
            school, len(own), logfile.size_text(sum(own)), logfile.size_text(max(own)),
        ))
    return lines
