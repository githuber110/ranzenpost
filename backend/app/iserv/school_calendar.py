import re
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlsplit

from bs4 import BeautifulSoup

from .. import berlin
from .pages import status_of
from .errors import REASON_RATE_LIMITED, DataError, LoginError, OutageError, SchoolCalendarRefusedError

CALENDAR_SOURCES_PATH = "/iserv/calendar/api/eventsources"
CALENDAR_EVENTS_PATH = "/iserv/calendar/feed/calendar-multi"
TITLE_LIMIT = 200
TEXT_LIMIT = 2000
NAME_LIMIT = 120
CALENDAR_REFUSED_STATUSES = (401, 403, 404)
POLL_DAYS_BACK = 7
POLL_DAYS_AHEAD = 120
CARRY_SECONDS = 7 * 24 * 3600
FEED_PATH = re.compile(r"^/iserv/calendar/feed(?:/[A-Za-z0-9_-]+){1,3}$")
WRITING_SEGMENTS = frozenset({"delete", "remove", "edit", "update", "create", "new", "action", "actions", "upload", "save"})
WINDOW_KEYS = frozenset({"start", "end"})
SOURCE_KIND = re.compile(r"^[a-z]{1,12}$")
OTHER_KIND = "<other>"
SOURCE_FAILURES = (DataError, LoginError, OutageError)
URL_REFUSED = "url outside the calendar feeds"
SchoolCalendarRead = namedtuple("SchoolCalendarRead", "events failed problems answered", defaults=((),))
SourceProblem = namedtuple("SourceProblem", "source kind path reason")


class CalendarShapeError(ValueError):
    pass


def poll_window(today):
    return today - timedelta(days=POLL_DAYS_BACK), today + timedelta(days=POLL_DAYS_AHEAD)


def window_params(today):
    return events_params(*poll_window(today))


def events_params(first, last):
    return {"start": first.isoformat(), "end": last.isoformat()}


def feed_sources(payload):
    if not isinstance(payload, list):
        raise CalendarShapeError("calendar sources are not a list")
    sources = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        source_id = _text(item.get("id"), NAME_LIMIT)
        if not source_id:
            continue
        url = item.get("url")
        sources.append(
            {
                "id": source_id,
                "label": _text(item.get("label"), NAME_LIMIT),
                "type": _text(item.get("type"), NAME_LIMIT),
                "subscription": item.get("subscription") is True,
                "url": url.strip() if isinstance(url, str) else "",
            }
        )
    return sources


def parse_sources(payload):
    return [{key: entry[key] for key in ("id", "label", "type", "subscription")} for entry in feed_sources(payload)]


def source_kind(value):
    text = str(value or "")
    return text if SOURCE_KIND.match(text) else OTHER_KIND


def problem_text(reason):
    return reason if isinstance(reason, str) else "%s: %s" % (type(reason).__name__, reason)


def feed_request(url, first, last):
    parts = urlsplit(str(url or "").strip())
    if parts.scheme or parts.netloc or parts.fragment or not FEED_PATH.match(parts.path):
        return None
    if WRITING_SEGMENTS.intersection(segment.casefold() for segment in parts.path.split("/")):
        return None
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in WINDOW_KEYS]
    return parts.path, query + list(events_params(first, last).items())


def source_events(payload, source):
    events = parse_events(payload)
    for event in events:
        event["source"] = source["id"]
        if not event["calendar"]:
            event["calendar"] = source["label"]
    return events


def merge_events(groups):
    merged = []
    seen = set()
    for events in groups:
        for event in events:
            if not isinstance(event, dict):
                continue
            key = event_key(event, event.get("source"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    merged.sort(key=lambda event: (str(event.get("start") or ""), str(event.get("title") or "")))
    return merged


def event_key(event, scope):
    uid = str(event.get("uid") or "")
    if "@" in uid:
        return uid, event.get("start")
    return scope, uid, event.get("start")


def _stamp(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def last_answer(stored, source):
    if not isinstance(stored, dict):
        return None
    stamps = stored.get("sources")
    stamp = _stamp(stamps.get(source)) if isinstance(stamps, dict) else None
    return stamp if stamp is not None else _stamp(stored.get("last_success"))


def answered_at(stored, read, now):
    stamps = {}
    for source in read.failed:
        stamp = last_answer(stored, source)
        stamps[source] = now if stamp is None else stamp
    for source in read.answered:
        stamps[source] = now
    return stamps


def _still_carried(stamp, now):
    return stamp is None or now - stamp < CARRY_SECONDS


def carried_events(stored, failed, now):
    if not failed or not isinstance(stored, dict) or not isinstance(stored.get("events"), list):
        return []
    sources = frozenset(source for source in failed if _still_carried(last_answer(stored, source), now))
    return [event for event in stored["events"] if isinstance(event, dict) and event.get("source") in sources]


def parse_events(payload):
    events = []
    seen = set()
    for scope, item in _event_items(payload):
        event = parse_event(item)
        if event is None:
            continue
        key = event_key(event, scope)
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    events.sort(key=lambda event: (event["start"], event["title"]))
    return events


def _event_items(payload):
    if isinstance(payload, list):
        return [(None, item) for item in payload]
    if isinstance(payload, dict):
        listed = payload.get("events")
        if isinstance(listed, list):
            return [(None, item) for item in listed]
        if any(not isinstance(value, list) for value in payload.values()):
            raise CalendarShapeError("calendar events carry something other than event lists")
        return [(scope, item) for scope, value in payload.items() for item in value]
    raise CalendarShapeError("calendar events are neither a list nor an object")


def _checked(response, path, server_failure):
    status = status_of(response)
    if status in CALENDAR_REFUSED_STATUSES:
        raise SchoolCalendarRefusedError("school calendar refused: %d" % status)
    failure = server_failure(response)
    if failure is not None:
        raise failure
    if status != 200:
        raise DataError("school calendar answered %d" % status, detail={"path": path})
    try:
        return response.json()
    except (ValueError, TypeError) as error:
        raise DataError("school calendar answered no readable events", detail={"path": path}) from error


def read_multi(client, first, last, server_failure):
    response = client.fetch(CALENDAR_EVENTS_PATH, params=events_params(first, last))
    payload = _checked(response, CALENDAR_EVENTS_PATH, server_failure)
    try:
        return parse_events(payload)
    except (ValueError, TypeError, CalendarShapeError) as error:
        raise DataError("school calendar answered no readable events", detail={"path": CALENDAR_EVENTS_PATH}) from error


def _listed_sources(client, server_failure):
    response = client.fetch(CALENDAR_SOURCES_PATH)
    failure = server_failure(response)
    if failure is not None:
        raise failure
    if status_of(response) != 200:
        return None
    try:
        return feed_sources(response.json())
    except (ValueError, TypeError, CalendarShapeError):
        return None


def _read_source(client, source, request, server_failure):
    path, params = request
    payload = _checked(client.fetch(path, params=params), path, server_failure)
    try:
        return source_events(payload, source)
    except (ValueError, TypeError, CalendarShapeError) as error:
        raise DataError("calendar source answered no readable events", detail={"path": path}) from error


def read_calendar(client, first, last, server_failure):
    sources = _listed_sources(client, server_failure)
    if sources is None:
        return SchoolCalendarRead(read_multi(client, first, last, server_failure), (), ())
    groups = []
    failed = []
    answered = []
    problems = []
    errors = []
    refused = 0
    skipped = 0
    for source in sources:
        request = feed_request(source["url"], first, last)
        if request is None:
            skipped += 1
            problems.append(SourceProblem(source["id"], source["type"], source["url"].split("?", 1)[0], URL_REFUSED))
            continue
        try:
            groups.append(_read_source(client, source, request, server_failure))
            answered.append(source["id"])
        except SchoolCalendarRefusedError as error:
            refused += 1
            problems.append(SourceProblem(source["id"], source["type"], request[0], error))
        except SOURCE_FAILURES as error:
            if isinstance(error, OutageError) and error.reason == REASON_RATE_LIMITED:
                raise
            failed.append(source["id"])
            errors.append(error)
            problems.append(SourceProblem(source["id"], source["type"], request[0], error))
    if not groups:
        if errors:
            raise errors[0]
        if refused:
            raise SchoolCalendarRefusedError("every school calendar source refused")
        if skipped:
            return SchoolCalendarRead(read_multi(client, first, last, server_failure), (), tuple(problems))
    return SchoolCalendarRead(merge_events(groups), tuple(failed), tuple(problems), tuple(answered))


def parse_event(item):
    if not isinstance(item, dict):
        return None
    title = _text(item.get("title") or item.get("summary"), TITLE_LIMIT)
    start = _moment(item.get("start"))
    if not title or start is None:
        return None
    end = _moment(item.get("end"))
    if isinstance(start, datetime) and isinstance(end, datetime) and (start.tzinfo is None) != (end.tzinfo is None):
        end = end.replace(tzinfo=start.tzinfo)
    all_day = item.get("allDay") is True or (isinstance(start, date) and not isinstance(start, datetime))
    if all_day:
        first = _day_of(start)
        last = _day_of(end) if end is not None else None
        if last is None or last <= first:
            last = first + timedelta(days=1)
        start_text, end_text = first.isoformat(), last.isoformat()
    else:
        if not isinstance(start, datetime):
            return None
        if not isinstance(end, datetime) or end <= start:
            end = start
        start_text, end_text = start.isoformat(), end.isoformat()
    uid = _text(item.get("uid") or item.get("id") or item.get("hash"), NAME_LIMIT) or f"{start_text}:{title}"
    return {
        "uid": uid,
        "title": title,
        "start": start_text,
        "end": end_text,
        "all_day": all_day,
        "location": _text(item.get("location"), TITLE_LIMIT),
        "calendar": _text(item.get("calendarName"), NAME_LIMIT),
        "category": _text(item.get("category"), NAME_LIMIT),
        "description": _plain(item.get("description"), TEXT_LIMIT),
    }


def _moment(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) == 10:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _day_of(value):
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.date()
    return berlin.date_from_utc(value.astimezone(timezone.utc).replace(tzinfo=None))


def _text(value, limit):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    return " ".join(str(value).split())[:limit]


def _plain(value, limit):
    if not isinstance(value, str):
        return ""
    text = BeautifulSoup(value, "html.parser").get_text("\n") if "<" in value else value
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]
