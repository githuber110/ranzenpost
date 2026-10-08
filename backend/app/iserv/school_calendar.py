from datetime import date, datetime, timedelta, timezone

from bs4 import BeautifulSoup

from .absences import berlin_date_from_utc

CALENDAR_SOURCES_PATH = "/iserv/calendar/api/eventsources"
CALENDAR_EVENTS_PATH = "/iserv/calendar/feed/calendar-multi"
TITLE_LIMIT = 200
TEXT_LIMIT = 2000
PERSONAL_CALENDAR_SUFFIX = "/home"
NAME_LIMIT = 120
CALENDAR_REFUSED_STATUSES = (401, 403, 404)


class CalendarShapeError(ValueError):
    pass


def events_params(first, last):
    return {"start": first.isoformat(), "end": last.isoformat()}


def parse_sources(payload):
    if not isinstance(payload, list):
        raise CalendarShapeError("calendar sources are not a list")
    sources = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        source_id = _text(item.get("id"), NAME_LIMIT)
        if not source_id:
            continue
        sources.append(
            {
                "id": source_id,
                "label": _text(item.get("label"), NAME_LIMIT),
                "type": _text(item.get("type"), NAME_LIMIT),
                "subscription": item.get("subscription") is True,
            }
        )
    return sources


def parse_events(payload):
    events = []
    seen = set()
    for item in _event_items(payload):
        if isinstance(item, dict) and personal_calendar(item.get("calendarId")):
            continue
        event = parse_event(item)
        if event is None:
            continue
        key = (event["uid"], event["start"])
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    events.sort(key=lambda event: (event["start"], event["title"]))
    return events


def _event_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        listed = payload.get("events")
        if isinstance(listed, list):
            return listed
        if any(not isinstance(value, list) for value in payload.values()):
            raise CalendarShapeError("calendar events carry something other than event lists")
        items = []
        for key, value in payload.items():
            if not personal_calendar(key):
                items.extend(value)
        return items
    raise CalendarShapeError("calendar events are neither a list nor an object")


def personal_calendar(calendar_id):
    return isinstance(calendar_id, str) and calendar_id.rstrip("/").endswith(PERSONAL_CALENDAR_SUFFIX)


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
    return berlin_date_from_utc(value.astimezone(timezone.utc).replace(tzinfo=None))


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
