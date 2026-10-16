from datetime import date, datetime, timedelta

from .iserv.conferences import booking_heading, booking_key, booking_window, dates_in, event_day, first_time, same_booking

STATE_KEY = "conference_notices"
EVENT_BOOKING_OPEN = "conference_booking_open"
EVENT_CANCELLED = "conference_cancelled"
EVENT_REMINDER = "conference_reminder"
EVENT_BOOKING_REMINDER = "conference_booking_reminder"
BOOKING_OPEN_KEY = "notify.conferences.bookingOpen"
CANCELLED_KEY = "notify.conferences.cancelled"
REMINDER_KEY = "notify.conferences.reminder"
BOOKING_REMINDER_KEY = "notify.conferences.bookingReminder"
DATE_KEY = "notify.conferences.date"
REMINDER_DAYS = 3
REMINDER_EARLIEST_HOUR = 7
BOOKING_REMINDER_MINUTES = 15
MAX_PAGES = 6
MAX_TEXT = 160


def _text(value):
    return " ".join(str(value or "").split())[:MAX_TEXT]


def conference_facts(item, today):
    cells = [_text(cell) for cell in item.get("cells") or [] if _text(cell)]
    if not cells:
        return None
    window = booking_window(cells)
    within = window is not None and window[0] <= today and (window[1] is None or today <= window[1])
    day = event_day(cells)
    return {
        "id": cells[0].casefold(),
        "title": cells[0],
        "day": day,
        "open": bool(item.get("page")) or within,
        "page": str(item.get("page") or ""),
    }


def bookings_of(page, conference):
    forms = {form.get("id"): form for form in page.get("forms") or []}
    found = []
    heading = ""
    for block in page.get("blocks") or []:
        if block.get("kind") == "heading":
            heading = block.get("text") or ""
            continue
        if block.get("kind") != "table":
            continue
        listed = booking_heading(block.get("caption")) or booking_heading(heading)
        for row in block.get("rows") or []:
            row_forms = [forms.get(index) or {} for index in row.get("forms") or []]
            cancellable = any(form.get("destructive") for form in row_forms)
            cells = [_text(cell) for cell in row.get("cells") or [] if _text(cell)]
            if not cells or not first_time(cells):
                continue
            if not cancellable and (row_forms or not listed):
                continue
            day = next((found_day for cell in cells for found_day in dates_in(cell)), None) or conference["day"]
            key = booking_key(cells, day.isoformat() if day else "")
            found.append({
                "id": "%s|%s" % (conference["id"], key),
                "key": key,
                "conference": conference["id"],
                "summary": " · ".join(cells),
                "title": conference["title"],
                "day": day.isoformat() if day else "",
                "time": first_time(cells),
            })
        heading = ""
    return found


def _moment(record):
    try:
        day = date.fromisoformat(str(record.get("day") or ""))
    except ValueError:
        return None
    clock = str(record.get("time") or "")
    if not clock:
        return datetime.combine(day, datetime.min.time())
    hour, minute = clock.split(":")
    return datetime.combine(day, datetime.min.time()).replace(hour=int(hour), minute=int(minute))


def _upcoming(record, now):
    moment = _moment(record)
    if moment is None:
        return True
    if not record.get("time"):
        return moment.date() >= now.date()
    return moment >= now


def _own(record, own_keys):
    key = record.get("key") or ""
    return any(same_booking(key, own) for own in own_keys)


def plan(state, conferences, pages, now, own_keys=(), own_change_since=False, gap_seconds=1800):
    state = state if isinstance(state, dict) else {}
    initialised = isinstance(state.get("seen"), list)
    seen = set(state.get("seen") or [])
    was_open = set(state.get("open") or [])
    reminded = set(state.get("reminded") or [])
    known = state.get("bookings") if isinstance(state.get("bookings"), dict) else {}
    booking_reminded = set(state.get("booking_reminded") or [])
    today = now.date()
    pushes = []
    for conference in conferences:
        if initialised and conference["id"] in seen and conference["open"] and conference["id"] not in was_open:
            pushes.append(_push(EVENT_BOOKING_OPEN, BOOKING_OPEN_KEY, {"title": conference["title"]}, conference["id"]))
        day = conference["day"]
        due = day is not None and 0 <= (day - today).days <= REMINDER_DAYS and now.hour >= REMINDER_EARLIEST_HOUR
        if due and conference["id"] not in reminded:
            pushes.append(_push(EVENT_REMINDER, REMINDER_KEY, {"title": conference["title"], "date": day}, conference["id"]))
            reminded.add(conference["id"])
    read = set(pages)
    current = {}
    for bookings in pages.values():
        for booking in bookings:
            current[booking["id"]] = booking
    for booking_id, record in known.items():
        if booking_id in current or not isinstance(record, dict):
            continue
        if record.get("conference") not in read:
            current[booking_id] = record
            continue
        if not initialised or not record.get("key") or not _upcoming(record, now):
            continue
        if _own(record, own_keys) or own_change_since:
            continue
        variables = {"summary": record.get("summary") or "", "title": record.get("title") or ""}
        pushes.append(_push(EVENT_CANCELLED, CANCELLED_KEY, variables, booking_id, dict(record)))
    window = timedelta(minutes=BOOKING_REMINDER_MINUTES, seconds=0)
    window = max(window, timedelta(seconds=int(gap_seconds or 0)))
    for booking_id, record in current.items():
        if booking_id in booking_reminded or not record.get("time"):
            continue
        moment = _moment(record)
        if moment is not None and now <= moment <= now + window:
            variables = {"time": record["time"], "summary": record.get("summary") or "", "title": record.get("title") or ""}
            pushes.append(_push(EVENT_BOOKING_REMINDER, BOOKING_REMINDER_KEY, variables, booking_id))
            booking_reminded.add(booking_id)
    listed = {conference["id"] for conference in conferences}
    fresh = {
        "seen": sorted(listed),
        "open": sorted(conference["id"] for conference in conferences if conference["open"]),
        "reminded": sorted(reminded & listed),
        "bookings": {booking_id: _stored(record) for booking_id, record in current.items() if _upcoming(record, now)},
        "booking_reminded": sorted(booking_reminded & set(current)),
    }
    return pushes, fresh


def _push(event, key, variables, identity, record=None):
    return {"event": event, "key": key, "variables": variables, "identity": identity, "record": record}


def not_delivered(state, push):
    identity = push["identity"]
    if push["event"] == EVENT_BOOKING_OPEN:
        state["open"] = [entry for entry in state.get("open") or [] if entry != identity]
    elif push["event"] == EVENT_REMINDER:
        state["reminded"] = [entry for entry in state.get("reminded") or [] if entry != identity]
    elif push["event"] == EVENT_BOOKING_REMINDER:
        state["booking_reminded"] = [entry for entry in state.get("booking_reminded") or [] if entry != identity]
    elif push["event"] == EVENT_CANCELLED and push.get("record"):
        state.setdefault("bookings", {})[identity] = _stored(push["record"])
    return state


def _stored(record):
    return {key: record.get(key) or "" for key in ("conference", "key", "summary", "title", "day", "time")}
