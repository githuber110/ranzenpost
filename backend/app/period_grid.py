import re
from datetime import timedelta

from .holidays import parse_day

DAY_MINUTES = 24 * 60
DEFAULT_MINUTES = 45
GRID_KEY = "period_grid"
TIMES_KEY = "period_times"
ISERV_LAYER = "iserv"
OWN_LAYER = "lessons"
PROFILE_LAYER = "days"
SEEN_LAYER = "seen"
SEEN_EMPTY = "empty"
FREE_AFTER_WEEKS = 3
SCHOOL_WEEKDAYS = (0, 1, 2, 3, 4)
MAX_VACATION_DAYS = 120
DURATION = "duration"
ADDED = "added"
SOURCE_ISERV = "iserv"
SOURCE_STANDARD = "standard"
SOURCE_OWN = "own"
SOURCE_SAVED = "saved"
ADDED_CHANGE = "added"
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
LOOSE_CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$")


def minutes_of(value):
    match = CLOCK.match(str(value or "").strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def loose_minutes_of(value):
    match = LOOSE_CLOCK.match(str(value or "").strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def clock_of(minutes):
    if minutes is None:
        return ""
    value = max(0, min(DAY_MINUTES, int(minutes)))
    return "%02d:%02d" % divmod(value, 60)


def number_of(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def duration_of(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number != value and str(number) != str(value).strip():
        return None
    return number if 0 < number <= DAY_MINUTES else None


def grid_of(config):
    raw = (config or {}).get(GRID_KEY)
    return raw if isinstance(raw, dict) else {}


def _layer(config, name):
    raw = grid_of(config).get(name)
    return raw if isinstance(raw, dict) else {}


def iserv_layer(config):
    layer = {}
    for key, slot in _layer(config, ISERV_LAYER).items():
        number = number_of(key)
        start = minutes_of((slot or {}).get("start")) if isinstance(slot, dict) else None
        if number is None or start is None:
            continue
        end = minutes_of(slot.get("end"))
        layer[number] = {"start": start, "end": end if end is not None and end > start else None}
    return layer


def own_layer(config):
    layer = {}
    for key, entry in _layer(config, OWN_LAYER).items():
        number = number_of(key)
        if number is None or not isinstance(entry, dict):
            continue
        layer[number] = {"duration": duration_of(entry.get(DURATION)), "added": bool(entry.get(ADDED))}
    return layer


def chosen_starts(config):
    raw = (config or {}).get(TIMES_KEY)
    starts = {}
    for key, value in (raw if isinstance(raw, dict) else {}).items():
        number = number_of(key)
        start = minutes_of(value)
        if number is not None and start is not None:
            starts[number] = start
    return starts


def base_duration(slot):
    if not slot:
        return None
    if slot.get("end") is not None:
        return slot["end"] - slot["start"]
    return DEFAULT_MINUTES


def resolve(config):
    iserv = iserv_layer(config)
    starts = chosen_starts(config)
    own = own_layer(config)
    numbers = set(iserv) | set(starts) | {number for number, entry in own.items() if entry["added"]}
    rows = []
    for number in sorted(numbers):
        base = iserv.get(number)
        mine = own.get(number, {"duration": None, "added": False})
        chosen = starts.get(number)
        if base is not None:
            start = base["start"] if mine["added"] or chosen is None else chosen
            iserv_duration = base_duration(base)
            duration = mine["duration"] or iserv_duration
            source = SOURCE_ISERV if base.get("end") is not None else SOURCE_STANDARD
            own_start = start != base["start"]
            own_duration = mine["duration"] is not None and mine["duration"] != iserv_duration
        else:
            if chosen is None:
                continue
            start = chosen
            iserv_duration = None
            duration = mine["duration"] or DEFAULT_MINUTES
            source = SOURCE_OWN if mine["added"] else SOURCE_SAVED
            own_start = False
            own_duration = not mine["added"] and mine["duration"] is not None
        rows.append({
            "number": number,
            "start": start,
            "duration": duration,
            "end": min(start + duration, DAY_MINUTES),
            "source": source,
            "iserv_start": base["start"] if base else None,
            "iserv_duration": iserv_duration,
            "own_start": own_start,
            "own_duration": own_duration,
            "added": base is None and mine["added"],
        })
    return rows


def row_view(row):
    return {
        "number": row["number"],
        "start": clock_of(row["start"]),
        "end": clock_of(row["end"]),
        "duration": row["duration"],
        "source": row["source"],
        "iserv_start": clock_of(row["iserv_start"]),
        "iserv_duration": row["iserv_duration"],
        "own_start": row["own_start"],
        "own_duration": row["own_duration"],
        "added": row["added"],
    }


def own_duration(config, period):
    number = number_of(period)
    if number is None:
        return None
    return own_layer(config).get(number, {}).get("duration")


def lesson_span(config, period, native_start, native_end):
    chosen = chosen_starts(config).get(number_of(period) or 0)
    start_native = minutes_of(native_start)
    end_native = minutes_of(native_end)
    native = end_native - start_native if start_native is not None and end_native is not None and end_native > start_native else None
    start = chosen if chosen is not None else start_native
    if start is None:
        return None, None
    duration = own_duration(config, period)
    if duration is None:
        if (chosen is None or chosen == start_native) and native is not None:
            return start, end_native
        if native is not None:
            duration = native
        else:
            slot = iserv_layer(config).get(number_of(period) or 0)
            duration = base_duration(slot) or DEFAULT_MINUTES
    end = start + duration
    return start, end if end < DAY_MINUTES else None


def normalize_slots(slots):
    layer = {}
    for key, value in (slots or {}).items():
        number = number_of(key)
        if number is None:
            continue
        if isinstance(value, dict):
            start = loose_minutes_of(value.get("start"))
            end = loose_minutes_of(value.get("end"))
        else:
            start = loose_minutes_of(value)
            end = None
        if start is None:
            continue
        layer[str(number)] = {"start": clock_of(start), "end": clock_of(end) if end is not None and end > start else ""}
    return layer


def merge_iserv(config, slots):
    fresh = normalize_slots(slots)
    if not fresh:
        return config
    grid = dict(grid_of(config))
    previous = _layer(config, ISERV_LAYER)
    lessons = {key: dict(value) for key, value in _layer(config, OWN_LAYER).items() if isinstance(value, dict)}
    times = dict((config or {}).get(TIMES_KEY) or {})
    for key, slot in fresh.items():
        current = minutes_of(times.get(key))
        before = minutes_of(previous[key].get("start")) if isinstance(previous.get(key), dict) else None
        mine = lessons.get(key)
        if mine is not None and mine.get(ADDED):
            mine.pop(ADDED, None)
            times[key] = slot["start"]
            if mine.get(DURATION) is None:
                lessons.pop(key, None)
        elif current is None or (before is not None and current == before):
            times[key] = slot["start"]
    grid[ISERV_LAYER] = fresh
    grid[OWN_LAYER] = lessons
    if not lessons:
        grid.pop(OWN_LAYER, None)
    merged = dict(config)
    merged[GRID_KEY] = grid
    merged[TIMES_KEY] = times
    return merged


def weekday_of(lesson):
    day = parse_day((lesson or {}).get("date"))
    return day.weekday() if day is not None else None


def regular_periods(lessons):
    days = {}
    for lesson in lessons or []:
        if not isinstance(lesson, dict):
            continue
        weekday = weekday_of(lesson)
        if weekday is None:
            continue
        found = days.setdefault(weekday, set())
        number = number_of(lesson.get("period"))
        if number is not None and str(lesson.get("change_kind") or "") != ADDED_CHANGE:
            found.add(number)
    return {weekday: sorted(numbers) for weekday, numbers in days.items()}


def profiles(config):
    raw = _layer(config, PROFILE_LAYER)
    result = {}
    for child_id, days in raw.items():
        if not isinstance(days, dict):
            continue
        clean = {}
        for key, numbers in days.items():
            text = str(key)
            if not text.isdigit() or int(text) > 6 or not isinstance(numbers, list):
                continue
            clean[int(text)] = sorted({number for number in (number_of(value) for value in numbers) if number})
        result[str(child_id)] = clean
    return result


def vacation_days(vacations):
    found = set()
    for item in vacations or []:
        if not isinstance(item, dict):
            continue
        first = parse_day(item.get("start_date"))
        last = parse_day(item.get("end_date"))
        if first is None or last is None or last < first or (last - first).days > MAX_VACATION_DAYS:
            continue
        day = first
        while day <= last:
            found.add(day)
            day += timedelta(days=1)
    return found


def week_monday(lessons):
    days = [parse_day((lesson or {}).get("date")) for lesson in lessons or [] if isinstance(lesson, dict)]
    days = [day for day in days if day is not None]
    if not days:
        return None
    first = min(days)
    return first - timedelta(days=first.weekday())


def merge_profile(config, child_id, lessons, vacations=()):
    found = regular_periods(lessons)
    monday = week_monday(lessons)
    if not found or not child_id or monday is None:
        return config
    grid = dict(grid_of(config))
    days = {key: dict(value) for key, value in _layer(config, PROFILE_LAYER).items() if isinstance(value, dict)}
    seen = {key: dict(value) for key, value in _layer(config, SEEN_LAYER).items() if isinstance(value, dict)}
    stored = dict(days.get(str(child_id)) or {})
    marks = {key: dict(value) for key, value in (seen.get(str(child_id)) or {}).items() if isinstance(value, dict)}
    week = monday.isoformat()
    off = vacation_days(vacations)
    for weekday, numbers in found.items():
        stored[str(weekday)] = numbers
        marks[str(weekday)] = {SEEN_EMPTY: []}
    for weekday in SCHOOL_WEEKDAYS:
        key = str(weekday)
        if weekday in found or monday + timedelta(days=weekday) in off:
            continue
        raw = (marks.get(key) or {}).get(SEEN_EMPTY)
        empty = [value for value in raw if isinstance(value, str)] if isinstance(raw, list) else []
        if week not in empty:
            empty = (empty + [week])[-FREE_AFTER_WEEKS:]
        marks[key] = {SEEN_EMPTY: empty}
        if len(empty) >= FREE_AFTER_WEEKS:
            stored[key] = []
    days[str(child_id)] = stored
    seen[str(child_id)] = marks
    grid[PROFILE_LAYER] = days
    grid[SEEN_LAYER] = seen
    merged = dict(config)
    merged[GRID_KEY] = grid
    return merged


def spans_for(rows, periods):
    wanted = set(periods or ())
    return sorted((row["start"], row["end"], row["number"]) for row in rows if row["number"] in wanted)
