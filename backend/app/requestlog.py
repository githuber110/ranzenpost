import logging

from .pathpattern import path_only, path_pattern

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
REDIRECT_STATUSES = (301, 302, 303, 307, 308)


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


def body_length(response):
    declared = str((getattr(response, "headers", None) or {}).get("Content-Length") or "").strip()
    if declared.isdigit():
        return int(declared)
    content = getattr(response, "content", None)
    return len(content) if isinstance(content, (bytes, bytearray)) else 0


def duration_ms(response):
    elapsed = getattr(response, "elapsed", None)
    return int(elapsed.total_seconds() * 1000) if elapsed is not None else 0


def describe(response):
    request = getattr(response, "request", None)
    path = path_pattern(getattr(response, "url", "") or "")
    return {
        "method": str(getattr(request, "method", "") or "GET").upper(),
        "path": path,
        "tag": module_tag(path),
        "status": int(getattr(response, "status_code", 0) or 0),
        "content_type": content_type_of(getattr(response, "headers", None)),
        "length": body_length(response),
        "duration_ms": duration_ms(response),
        "location": path_pattern((getattr(response, "headers", None) or {}).get("Location") or ""),
    }


def log_response(response, *args, **kwargs):
    try:
        facts = describe(response)
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
        logger.info(line)
    except Exception:
        logger.debug("request log line failed", exc_info=True)
    return response


def install(session):
    hooks = getattr(session, "hooks", None)
    if not isinstance(hooks, dict):
        return session
    listed = hooks.setdefault("response", [])
    if log_response not in listed:
        listed.append(log_response)
    return session
