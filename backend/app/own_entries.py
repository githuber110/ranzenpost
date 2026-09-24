import secrets
import time
from datetime import date, timedelta

from . import period_grid
from .holidays import parse_day
from .store import edit_config
from .subscriptions import label_carries_child_name

ENTRIES_KEY = "own_entries"
TYPE_PAUSE = "pause"
TYPE_CLUB = "club"
TYPE_APPOINTMENT = "appointment"
TYPES = (TYPE_PAUSE, TYPE_CLUB, TYPE_APPOINTMENT)
REPEAT_ONCE = "once"
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
REPEAT_WEEKS = "weeks"
REPEATS = (REPEAT_ONCE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_WEEKS)
SCHOOL_DAYS = (0, 1, 2, 3, 4)
WEEK_DAYS = (0, 1, 2, 3, 4, 5, 6)
MIN_INTERVAL = 2
MAX_INTERVAL = 8
MAX_NAME_LENGTH = 60
MAX_ENTRIES = 200
ID_BYTES = 6
SUMMER = "summer"
SCHOOL_KIND = "school"
FALLBACK_LAST_MONTH = 7
FALLBACK_LAST_DAY = 31
ROLLOVER_NOTICE_DAYS = 28
ROLLOVER_SKIPPED = "rollover_skipped"
ROLLOVER_COPIED = "rollover_copied"
WEEKEND = (5, 6)
STATE_OK = "ok"
STATE_CUT = "cut"
STATE_HIDDEN = "hidden"
TIMING_FIELDS = ("start", "duration", "repeat", "days", "interval", "date", "from", "until", "child")

ERROR_TYPE = "api.ownEntries.error.type"
ERROR_NAME = "api.ownEntries.error.name"
ERROR_NAME_LENGTH = "api.ownEntries.error.nameLength"
ERROR_NAME_PERSON = "api.ownEntries.error.namePerson"
ERROR_START = "api.ownEntries.error.start"
ERROR_DURATION = "api.ownEntries.error.duration"
ERROR_MIDNIGHT = "api.ownEntries.error.midnight"
ERROR_REPEAT = "api.ownEntries.error.repeat"
ERROR_DAYS = "api.ownEntries.error.days"
ERROR_INTERVAL = "api.ownEntries.error.interval"
ERROR_DATE = "api.ownEntries.error.date"
ERROR_RANGE = "api.ownEntries.error.range"
ERROR_UNTIL = "api.ownEntries.error.until"
ERROR_FROM = "api.ownEntries.error.from"
ERROR_CHILD = "api.ownEntries.error.child"
ERROR_LESSON = "api.ownEntries.error.lesson"
ERROR_TAKEN = "api.ownEntries.error.taken"
ERROR_FULL = "api.ownEntries.error.full"
ERROR_NOT_FOUND = "api.ownEntries.error.notFound"
ERROR_EMPTY = "api.ownEntries.error.empty"
ERROR_ROLLOVER = "api.ownEntries.error.rollover"
ERROR_ROLLOVER_TAKEN = "api.ownEntries.error.rolloverTaken"
ERROR_PERIOD = "api.periods.error.period"
ERROR_PERIOD_TIME = "api.periods.error.time"
ERROR_PERIOD_FIXED = "api.periods.error.fixed"
ERROR_PERIOD_OWN = "api.periods.error.own"


class OwnEntryError(Exception):
    def __init__(self, message_key, variables=None):
        super().__init__(message_key)
        self.message_key = message_key
        self.variables = dict(variables or {})


def entries_of(config):
    raw = (config or {}).get(ENTRIES_KEY)
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict) and entry.get("id")]


def child_ids(config):
    return [str(child.get("child_id") or "") for child in (config or {}).get("children") or [] if isinstance(child, dict) and child.get("child_id")]


def start_of(entry):
    return period_grid.minutes_of(entry.get("start"))


def end_of(entry):
    start = start_of(entry)
    return None if start is None else start + int(entry.get("duration") or 0)


def monday_of(day):
    return day - timedelta(days=day.weekday())


def occurs_on(entry, day):
    if entry.get("repeat") == REPEAT_ONCE:
        return parse_day(entry.get("date")) == day
    first = parse_day(entry.get("from"))
    last = parse_day(entry.get("until"))
    if first is None or last is None or day < first or day > last:
        return False
    if day.weekday() not in (entry.get("days") or ()):
        return False
    if entry.get("repeat") == REPEAT_WEEKS:
        weeks = (monday_of(day) - monday_of(first)).days // 7
        return weeks % max(1, int(entry.get("interval") or 1)) == 0
    return True


def weekdays_of(entry):
    if entry.get("repeat") == REPEAT_ONCE:
        day = parse_day(entry.get("date"))
        return [day.weekday()] if day is not None else []
    return sorted(set(entry.get("days") or ()))


def occurrence_days(entry):
    if entry.get("repeat") == REPEAT_ONCE:
        day = parse_day(entry.get("date"))
        return {day} if day is not None else set()
    first = parse_day(entry.get("from"))
    last = parse_day(entry.get("until"))
    found = set()
    if first is None or last is None:
        return found
    day = first
    while day <= last:
        if occurs_on(entry, day):
            found.add(day)
        day += timedelta(days=1)
    return found


def applies_to(entry, child_id):
    owner = str(entry.get("child") or "")
    return not owner or owner == str(child_id)


def children_of_entry(entry, children):
    owner = str(entry.get("child") or "")
    return [owner] if owner else list(children)


def clip(start, end, blockers):
    by = None
    for block_start, block_end, number in sorted(blockers, key=lambda item: (item[0], item[1])):
        if block_start <= start < block_end:
            start = block_end
            if by is None:
                by = number
        if start < block_start < end:
            end = block_start
            if by is None:
                by = number
    return start, end, by


def pause_counts(entry, spans):
    if entry.get("type") != TYPE_PAUSE:
        return True
    if spans is None:
        return True
    start = start_of(entry)
    return any(span[0] <= start for span in spans) and any(span[0] >= start for span in spans)


def _order(entry):
    return (start_of(entry) or 0, str(entry.get("id") or ""))


def _clipped(entry, blockers):
    first = start_of(entry)
    last = end_of(entry)
    start, end, by = clip(first, last, blockers)
    if end <= start:
        state = STATE_HIDDEN
    elif (start, end) != (first, last):
        state = STATE_CUT
    else:
        state = STATE_OK
    return {"entry": entry, "start": start, "end": end, "state": state, "number": by if state != STATE_OK else None}


def resolve_day(entries, spans, day, child_id, free=False):
    blockers = list(spans or [])
    chosen = [entry for entry in entries if applies_to(entry, child_id) and occurs_on(entry, day)]
    items = []
    taken = []
    for entry in sorted((item for item in chosen if item.get("repeat") == REPEAT_ONCE), key=_order):
        item = _clipped(entry, blockers)
        items.append(item)
        if item["state"] != STATE_HIDDEN:
            taken.append((item["start"], item["end"], None))
    for entry in sorted((item for item in chosen if item.get("repeat") != REPEAT_ONCE), key=_order):
        if free and not entry.get("holidays"):
            continue
        items.append(_clipped(entry, blockers + taken))
    items.sort(key=lambda item: (item["start"], str(item["entry"].get("id") or "")))
    return items


def entry_status(entry, rows, profile_map, children):
    worst = {"state": STATE_OK, "number": None, "start": None, "end": None}
    for child_id in children_of_entry(entry, children):
        days = profile_map.get(str(child_id)) or {}
        for weekday in weekdays_of(entry):
            if weekday not in days:
                continue
            spans = period_grid.spans_for(rows, days[weekday])
            if not pause_counts(entry, spans):
                continue
            start, end, by = clip(start_of(entry), end_of(entry), spans)
            if end <= start:
                return {"state": STATE_HIDDEN, "number": by, "start": None, "end": None}
            if by is not None and worst["state"] == STATE_OK:
                worst = {"state": STATE_CUT, "number": by, "start": start, "end": end}
    return worst


def overlaps(first_start, first_end, second_start, second_end):
    return first_start < second_end and second_start < first_end


def _spans(rows, profile_map, child_id, weekday):
    days = profile_map.get(str(child_id))
    if not days or weekday not in days:
        return None
    return period_grid.spans_for(rows, days[weekday])


def check_conflicts(candidate, others, rows, profile_map, children, lessons=True):
    start = start_of(candidate)
    end = end_of(candidate)
    once = candidate.get("repeat") == REPEAT_ONCE
    own_days = occurrence_days(candidate)
    kids = children_of_entry(candidate, children)
    for child_id in kids if lessons else ():
        for weekday in weekdays_of(candidate):
            spans = _spans(rows, profile_map, child_id, weekday)
            if not pause_counts(candidate, spans):
                continue
            for block_start, block_end, number in spans or []:
                if block_start <= start < block_end:
                    raise OwnEntryError(ERROR_LESSON, {"number": number})
                if start < block_start < end:
                    raise OwnEntryError(ERROR_LESSON, {"number": number})
    for other in others:
        if other.get("id") == candidate.get("id"):
            continue
        if (other.get("repeat") == REPEAT_ONCE) != once:
            continue
        shared = [child_id for child_id in kids if applies_to(other, child_id)]
        if not shared:
            continue
        common = own_days & occurrence_days(other)
        if not common:
            continue
        for child_id in shared:
            for weekday in sorted({day.weekday() for day in common}):
                spans = _spans(rows, profile_map, child_id, weekday)
                if not pause_counts(candidate, spans) or not pause_counts(other, spans):
                    continue
                other_start, other_end, _ = clip(start_of(other), end_of(other), spans or [])
                if other_end > other_start and overlaps(start, end, other_start, other_end):
                    raise OwnEntryError(ERROR_TAKEN, {"name": other.get("name", "")})


def until_limit(today, periods):
    starts = sorted(
        day
        for day in (parse_day(period.get("start")) for period in periods or [] if isinstance(period, dict)
                    and period.get("type") == SUMMER and period.get("kind") == SCHOOL_KIND)
        if day is not None
    )
    for first in starts:
        if first > today:
            return first - timedelta(days=1), first
    fallback = date(today.year, FALLBACK_LAST_MONTH, FALLBACK_LAST_DAY)
    if today > fallback:
        fallback = date(today.year + 1, FALLBACK_LAST_MONTH, FALLBACK_LAST_DAY)
    return fallback, None


def _summers(periods):
    found = []
    for period in periods or []:
        if not isinstance(period, dict) or period.get("type") != SUMMER or period.get("kind") != SCHOOL_KIND:
            continue
        first = parse_day(period.get("start"))
        last = parse_day(period.get("end"))
        if first is not None and last is not None and last >= first:
            found.append((first, last))
    return sorted(found)


def school_year_end(today, periods):
    for first, last in _summers(periods):
        if last >= today:
            return first - timedelta(days=1), last + timedelta(days=1)
    fallback = date(today.year, FALLBACK_LAST_MONTH, FALLBACK_LAST_DAY)
    if today > fallback:
        fallback = date(today.year + 1, FALLBACK_LAST_MONTH, FALLBACK_LAST_DAY)
    return fallback, fallback + timedelta(days=1)


def first_school_day(day):
    while day.weekday() in WEEKEND:
        day += timedelta(days=1)
    return day


def rollover_plan(entries, today, periods, later=None):
    year_end, next_from = school_year_end(today, periods)
    if today < year_end - timedelta(days=ROLLOVER_NOTICE_DAYS):
        return None
    handled = year_end.isoformat()
    chosen = []
    for entry in entries:
        copied = str(entry.get(ROLLOVER_COPIED) or "")
        if entry.get("repeat") == REPEAT_ONCE or entry.get(ROLLOVER_SKIPPED) == handled or (copied and copied >= str(entry.get("until") or "")):
            continue
        first = parse_day(entry.get("from"))
        last = parse_day(entry.get("until"))
        if first is not None and last is not None and first <= year_end <= last < next_from:
            chosen.append(entry)
    if not chosen:
        return None
    next_until, _ = until_limit(next_from, later(next_from) if later is not None else periods)
    return {
        "ids": [entry["id"] for entry in chosen],
        "year_end": year_end,
        "until": min(parse_day(entry.get("until")) for entry in chosen),
        "from": first_school_day(next_from),
        "to": next_until,
    }


def rollover_view(entries, today, periods, later=None):
    plan = rollover_plan(entries, today, periods, later)
    if plan is None:
        return None
    return {
        "count": len(plan["ids"]),
        "until": plan["until"].isoformat(),
        "from": plan["from"].isoformat(),
        "to": plan["to"].isoformat(),
    }


def rollover(store, today, periods, later=None, clock=time.time):
    outcome = {"copied": 0, "skipped": 0}

    def change(config):
        entries = entries_of(config)
        plan = rollover_plan(entries, today, periods, later)
        if plan is None:
            raise OwnEntryError(ERROR_ROLLOVER)
        if len(entries) + len(plan["ids"]) > MAX_ENTRIES:
            raise OwnEntryError(ERROR_FULL)
        rows, profile_map, children = _context(config)
        now = int(clock())
        handled = plan["year_end"].isoformat()
        current = list(entries)
        for entry_id in plan["ids"]:
            index = next(position for position, item in enumerate(current) if item.get("id") == entry_id)
            copy = {key: value for key, value in current[index].items() if key not in (ROLLOVER_SKIPPED, ROLLOVER_COPIED)}
            copy.update({
                "id": secrets.token_hex(ID_BYTES),
                "from": plan["from"].isoformat(),
                "until": plan["to"].isoformat(),
                "created_at": now,
                "updated_at": now,
            })
            try:
                check_conflicts(copy, current, rows, profile_map, children, lessons=False)
            except OwnEntryError:
                current[index] = dict(current[index], **{ROLLOVER_SKIPPED: handled})
                outcome["skipped"] += 1
                continue
            current[index] = dict(current[index], **{ROLLOVER_COPIED: handled})
            current.append(copy)
            outcome["copied"] += 1
        config[ENTRIES_KEY] = current

    edit_config(store, change)
    if not outcome["copied"]:
        raise OwnEntryError(ERROR_ROLLOVER_TAKEN)
    return dict(outcome)


def _text(value):
    return " ".join(str(value or "").split())


def _day(value, error):
    day = parse_day(value)
    if day is None or len(str(value).strip()) != 10:
        raise OwnEntryError(error)
    return day


def normalize(raw, config, today, until_max, existing=None, later_limit=None):
    raw = raw if isinstance(raw, dict) else {}
    kind = str(raw.get("type") or "")
    if kind not in TYPES:
        raise OwnEntryError(ERROR_TYPE)
    name = _text(raw.get("name"))
    if not name:
        raise OwnEntryError(ERROR_NAME)
    if len(name) > MAX_NAME_LENGTH:
        raise OwnEntryError(ERROR_NAME_LENGTH)
    if label_carries_child_name(name, config):
        raise OwnEntryError(ERROR_NAME_PERSON)
    start = period_grid.minutes_of(raw.get("start"))
    if start is None:
        raise OwnEntryError(ERROR_START)
    duration = period_grid.duration_of(raw.get("duration"))
    if duration is None:
        raise OwnEntryError(ERROR_DURATION)
    if start + duration > period_grid.DAY_MINUTES:
        raise OwnEntryError(ERROR_MIDNIGHT)
    repeat = str(raw.get("repeat") or "")
    if repeat not in REPEATS:
        raise OwnEntryError(ERROR_REPEAT)
    child = str(raw.get("child") or "")
    if child and child not in child_ids(config):
        raise OwnEntryError(ERROR_CHILD)
    entry = {
        "type": kind,
        "name": name,
        "start": period_grid.clock_of(start),
        "duration": duration,
        "repeat": repeat,
        "days": [],
        "interval": 1,
        "date": "",
        "from": "",
        "until": "",
        "holidays": True,
        "child": child,
    }
    if repeat == REPEAT_ONCE:
        day = _day(raw.get("date"), ERROR_DATE)
        kept = existing is not None and existing.get("date") == day.isoformat()
        if (day < today or day > until_max) and not kept:
            raise OwnEntryError(ERROR_DATE)
        entry["date"] = day.isoformat()
        return entry
    first = _day(raw.get("from"), ERROR_RANGE)
    if later_limit is not None and first > later_limit(until_max + timedelta(days=1)):
        raise OwnEntryError(ERROR_FROM)
    limit = until_max if later_limit is None or first <= until_max else later_limit(first)
    last = _day(raw.get("until") or limit.isoformat(), ERROR_RANGE)
    stored_from = parse_day((existing or {}).get("from"))
    moved_back = stored_from is not None and stored_from > until_max >= first
    kept = existing is not None and existing.get("until") == last.isoformat() and not moved_back
    if last > limit and not kept:
        raise OwnEntryError(ERROR_UNTIL)
    if last < first:
        raise OwnEntryError(ERROR_RANGE)
    if repeat == REPEAT_DAILY:
        days = list(SCHOOL_DAYS)
    else:
        picked = raw.get("days")
        if not isinstance(picked, list) or not picked or any(isinstance(day, bool) or day not in WEEK_DAYS for day in picked):
            raise OwnEntryError(ERROR_DAYS)
        days = sorted(set(picked))
    if repeat == REPEAT_WEEKS:
        interval = raw.get("interval")
        if isinstance(interval, bool) or not isinstance(interval, int) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise OwnEntryError(ERROR_INTERVAL)
        entry["interval"] = interval
    entry.update({"days": days, "from": first.isoformat(), "until": last.isoformat(), "holidays": bool(raw.get("holidays"))})
    if not occurrence_days(entry):
        raise OwnEntryError(ERROR_EMPTY)
    return entry


def _timing(entry):
    return tuple(str(entry.get(field)) for field in TIMING_FIELDS)


def _context(config):
    return period_grid.resolve(config), period_grid.profiles(config), child_ids(config)


def create(store, raw, today, until_max, clock=time.time, later_limit=None):
    created = {}

    def change(config):
        entries = entries_of(config)
        if len(entries) >= MAX_ENTRIES:
            raise OwnEntryError(ERROR_FULL)
        entry = normalize(raw, config, today, until_max, later_limit=later_limit)
        entry["id"] = secrets.token_hex(ID_BYTES)
        rows, profile_map, children = _context(config)
        check_conflicts(entry, entries, rows, profile_map, children)
        now = int(clock())
        entry["created_at"] = now
        entry["updated_at"] = now
        config[ENTRIES_KEY] = entries + [entry]
        created.update(entry)

    edit_config(store, change)
    return dict(created)


def update(store, entry_id, raw, today, until_max, clock=time.time, later_limit=None):
    updated = {}

    def change(config):
        entries = entries_of(config)
        current = next((entry for entry in entries if entry.get("id") == entry_id), None)
        if current is None:
            raise OwnEntryError(ERROR_NOT_FOUND)
        entry = normalize(raw, config, today, until_max, existing=current, later_limit=later_limit)
        entry["id"] = entry_id
        if _timing(entry) != _timing(current):
            rows, profile_map, children = _context(config)
            check_conflicts(entry, entries, rows, profile_map, children)
        entry["created_at"] = int(current.get("created_at") or 0)
        entry["updated_at"] = int(clock())
        if current.get(ROLLOVER_COPIED):
            entry[ROLLOVER_COPIED] = current[ROLLOVER_COPIED]
        config[ENTRIES_KEY] = [entry if item.get("id") == entry_id else item for item in entries]
        updated.update(entry)

    edit_config(store, change)
    return dict(updated)


def delete(store, entry_id):
    def change(config):
        entries = entries_of(config)
        if not any(entry.get("id") == entry_id for entry in entries):
            raise OwnEntryError(ERROR_NOT_FOUND)
        config[ENTRIES_KEY] = [entry for entry in entries if entry.get("id") != entry_id]

    edit_config(store, change)


def _grid(config):
    grid = dict(period_grid.grid_of(config))
    lessons = grid.get(period_grid.OWN_LAYER)
    grid[period_grid.OWN_LAYER] = {key: dict(value) for key, value in (lessons or {}).items() if isinstance(value, dict)}
    return grid


def _store_grid(config, grid):
    if not grid.get(period_grid.OWN_LAYER):
        grid.pop(period_grid.OWN_LAYER, None)
    config[period_grid.GRID_KEY] = grid


def _neighbours(rows, number):
    ordered = sorted(rows, key=lambda row: row["number"])
    index = next((position for position, row in enumerate(ordered) if row["number"] == number), None)
    if index is None:
        raise OwnEntryError(ERROR_PERIOD)
    before = ordered[index - 1] if index > 0 else None
    after = ordered[index + 1] if index + 1 < len(ordered) else None
    return ordered[index], before, after


def _checked_span(start_value, duration_value, before, after):
    start = period_grid.minutes_of(start_value)
    duration = period_grid.duration_of(duration_value)
    if start is None or duration is None:
        raise OwnEntryError(ERROR_PERIOD_TIME)
    if before is not None and start < before["end"]:
        raise OwnEntryError(ERROR_PERIOD_TIME)
    limit = after["start"] if after is not None else period_grid.DAY_MINUTES
    if start + duration > limit:
        raise OwnEntryError(ERROR_PERIOD_TIME)
    return start, duration


def set_lesson(store, number, start_value, duration_value):
    def change(config):
        rows = period_grid.resolve(config)
        row, before, after = _neighbours(rows, number)
        start, duration = _checked_span(start_value, duration_value, before, after)
        key = str(number)
        grid = _grid(config)
        lessons = grid[period_grid.OWN_LAYER]
        times = dict(config.get(period_grid.TIMES_KEY) or {})
        times[key] = period_grid.clock_of(start)
        if row["added"]:
            lessons[key] = {period_grid.DURATION: duration, period_grid.ADDED: True}
        elif row["iserv_duration"] is not None and duration == row["iserv_duration"]:
            lessons.pop(key, None)
        else:
            lessons[key] = {period_grid.DURATION: duration}
        config[period_grid.TIMES_KEY] = times
        _store_grid(config, grid)

    edit_config(store, change)


def reset_lessons(store, numbers=None):
    def change(config):
        rows = period_grid.resolve(config)
        wanted = None if numbers is None else set(numbers)
        grid = _grid(config)
        lessons = grid[period_grid.OWN_LAYER]
        times = dict(config.get(period_grid.TIMES_KEY) or {})
        touched = False
        for row in rows:
            if row["iserv_start"] is None or (wanted is not None and row["number"] not in wanted):
                continue
            key = str(row["number"])
            times[key] = period_grid.clock_of(row["iserv_start"])
            lessons.pop(key, None)
            touched = True
        if wanted is not None and not touched:
            raise OwnEntryError(ERROR_PERIOD_OWN)
        config[period_grid.TIMES_KEY] = times
        _store_grid(config, grid)

    edit_config(store, change)


def add_lesson(store, start_value, duration_value):
    added = {}

    def change(config):
        rows = sorted(period_grid.resolve(config), key=lambda row: row["number"])
        last = rows[-1] if rows else None
        start, duration = _checked_span(start_value, duration_value, last, None)
        number = (last["number"] if last else 0) + 1
        key = str(number)
        grid = _grid(config)
        grid[period_grid.OWN_LAYER][key] = {period_grid.DURATION: duration, period_grid.ADDED: True}
        times = dict(config.get(period_grid.TIMES_KEY) or {})
        times[key] = period_grid.clock_of(start)
        config[period_grid.TIMES_KEY] = times
        _store_grid(config, grid)
        added["number"] = number

    edit_config(store, change)
    return added.get("number")


def remove_lesson(store, number):
    def change(config):
        rows = period_grid.resolve(config)
        row, _, _ = _neighbours(rows, number)
        if not row["added"]:
            raise OwnEntryError(ERROR_PERIOD_FIXED)
        key = str(number)
        grid = _grid(config)
        grid[period_grid.OWN_LAYER].pop(key, None)
        times = dict(config.get(period_grid.TIMES_KEY) or {})
        times.pop(key, None)
        config[period_grid.TIMES_KEY] = times
        _store_grid(config, grid)

    edit_config(store, change)


def entry_range(entry, until_max, later_limit):
    first = parse_day(entry.get("from"))
    if entry.get("repeat") == REPEAT_ONCE or first is None or first <= until_max or later_limit is None:
        return {"from_min": "", "until_max": ""}
    return {"from_min": (until_max + timedelta(days=1)).isoformat(), "until_max": later_limit(first).isoformat()}


def entry_view(entry, connection_id, rows, profile_map, children, until_max=None, later_limit=None):
    view = {key: entry.get(key) for key in ("id", "type", "name", "start", "duration", "repeat", "days", "interval", "date", "from", "until", "holidays", "child")}
    view.update(entry_range(entry, until_max, later_limit) if until_max is not None else {"from_min": "", "until_max": ""})
    view["end"] = period_grid.clock_of(end_of(entry))
    view["child_key"] = f"{connection_id}:{entry['child']}" if entry.get("child") else ""
    status = entry_status(entry, rows, profile_map, children)
    view["status"] = {
        "state": status["state"],
        "number": status["number"],
        "start": period_grid.clock_of(status["start"]),
        "end": period_grid.clock_of(status["end"]),
    }
    return view


def view(config, connection_id, today, until_max, summer_start=None, periods=None, later=None):
    rows = period_grid.resolve(config)
    profile_map = period_grid.profiles(config)
    children = child_ids(config)
    iserv = period_grid.iserv_layer(config)
    limits = {}

    def later_limit(first):
        if first not in limits:
            limits[first] = until_limit(first, later(first) if later is not None else periods)[0]
        return limits[first]

    return {
        "grid": [period_grid.row_view(row) for row in rows],
        "entries": [entry_view(entry, connection_id, rows, profile_map, children, until_max, later_limit) for entry in entries_of(config)],
        "profiles": {
            child_id: {str(weekday): numbers for weekday, numbers in days.items()}
            for child_id, days in profile_map.items()
        },
        "today": today.isoformat(),
        "until_max": until_max.isoformat(),
        "summer_start": summer_start.isoformat() if summer_start else "",
        "iserv_known": bool(iserv),
        "iserv_ends": any(slot.get("end") is not None for slot in iserv.values()),
        "rollover": rollover_view(entries_of(config), today, periods, later),
    }


def feed_occurrences(entries, rows, child_id, first, last, periods_on, free_on, types=(TYPE_CLUB, TYPE_APPOINTMENT)):
    found = []
    day = first
    while day <= last:
        periods = periods_on(day)
        spans = period_grid.spans_for(rows, periods) if periods is not None else []
        for item in resolve_day(entries, spans, day, child_id, free_on(day)):
            if item["state"] != STATE_HIDDEN and item["entry"].get("type") in types:
                found.append((day, item))
        day += timedelta(days=1)
    return found
