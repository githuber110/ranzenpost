import time as clock_module
from datetime import date, datetime, timedelta, timezone

import requests

from .iserv.absences import berlin_offset

SOURCE_BASE_URL = "https://openholidaysapi.org"
COUNTRY_ISO_CODE = "DE"
SOURCE_LANGUAGE = "DE"
REQUEST_TIMEOUT = 10
ACTIVE_TTL_SECONDS = 7 * 24 * 60 * 60
FAILURE_BACKOFF_SECONDS = 15 * 60
PREFETCH_FROM_MONTH = 10
MAX_SPAN_DAYS = 400
MAX_WEEK_OFFSET = 8

CONFIG_KEY = "holiday_region"

REGION_KEY_PREFIX = "holidays.region."
PERIOD_KEY_PREFIX = "holidays.period."

STATUS_DISABLED = "disabled"
STATUS_OK = "ok"
STATUS_UNKNOWN = "unknown"

COVERAGE_FULL = "full"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"

KIND_SCHOOL = "school"
KIND_PUBLIC = "public"

REGION_CODES = (
    "DE-BW",
    "DE-BY",
    "DE-BE",
    "DE-BB",
    "DE-HB",
    "DE-HH",
    "DE-HE",
    "DE-MV",
    "DE-NI",
    "DE-NW",
    "DE-RP",
    "DE-SL",
    "DE-SN",
    "DE-ST",
    "DE-SH",
    "DE-TH",
)

REQUEST_PARAM_KEYS = frozenset(
    {"countryIsoCode", "subdivisionCode", "languageIsoCode", "validFrom", "validTo"}
)

LOCAL_SCOPE = "Local"
STATE_CODE_PARTS = 2
EXCEPTION_TAG = "Exception"

SOURCE_PERIOD_NAMES = {
    "sommerferien": "summer",
    "herbstferien": "autumn",
    "weihnachtsferien": "christmas",
    "osterferien": "easter",
    "pfingstferien": "whitsun",
    "winterferien": "winter",
    "fruehjahrsferien": "spring",
    "halbjahresferien": "midterm",
    "halbjahrespause": "midterm",
    "fastnachtsferien": "carnival",
    "zusaetzlicher ferientag": "free_day",
    "unterrichtsfreier tag": "free_day",
    "variabler ferientag": "free_day",
    "schulfreier tag": "free_day",
}

SOURCE_PERIOD_STEMS = (
    ("sommer", "summer"),
    ("herbst", "autumn"),
    ("weihnacht", "christmas"),
    ("oster", "easter"),
    ("pfingst", "whitsun"),
    ("fruehjahr", "spring"),
    ("halbjahr", "midterm"),
    ("fastnacht", "carnival"),
    ("karneval", "carnival"),
    ("winter", "winter"),
)

WEEK_LABEL_KEYS = {
    COVERAGE_FULL: "holidays.week.full",
    COVERAGE_PARTIAL: "holidays.week.partial",
    COVERAGE_NONE: "",
}

UMLAUT_MAP = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"))

SCHOOL_DAYS_PER_WEEK = 5


def berlin_today(moment=None):
    utc_naive = moment or datetime.now(timezone.utc).replace(tzinfo=None)
    if berlin_offset(utc_naive + timedelta(hours=2)) == 2:
        return (utc_naive + timedelta(hours=2)).date()
    return (utc_naive + timedelta(hours=1)).date()


def region_options():
    return [
        {"code": code, "name_key": REGION_KEY_PREFIX + code.split("-")[1].lower()}
        for code in REGION_CODES
    ]


def clean_region(value):
    candidate = str(value or "").strip().upper()
    return candidate if candidate in REGION_CODES else ""


def parse_day(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    parts = text.split(".")
    if len(parts) == 3:
        try:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, TypeError):
            return None
    return None


def clamp_week_offset(value):
    try:
        offset = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(-MAX_WEEK_OFFSET, min(MAX_WEEK_OFFSET, offset))


def week_range(week_offset=0, today=None):
    reference = (today or berlin_today()) + timedelta(days=7 * clamp_week_offset(week_offset))
    monday = reference - timedelta(days=reference.weekday())
    return monday, monday + timedelta(days=6)


def normalize_source_name(value):
    text = str(value or "").strip().lower()
    for source, target in UMLAUT_MAP:
        text = text.replace(source, target)
    return " ".join(text.split())


def classify_period(name):
    normalized = normalize_source_name(name)
    if not normalized:
        return ""
    exact = SOURCE_PERIOD_NAMES.get(normalized)
    if exact:
        return exact
    for stem, period_type in SOURCE_PERIOD_STEMS:
        if stem in normalized:
            return period_type
    return ""


def _source_name(value):
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return ""
    fallback = ""
    for entry in value:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        if str(entry.get("language") or "").upper() == SOURCE_LANGUAGE:
            return text
        fallback = fallback or text
    return fallback


def _parse_source_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def is_local_scope(raw):
    if not isinstance(raw, dict):
        return False
    if str(raw.get("regionalScope") or "").strip() == LOCAL_SCOPE:
        return True
    subdivisions = raw.get("subdivisions")
    if not isinstance(subdivisions, list) or not subdivisions:
        return False
    codes = [
        str(entry.get("code") or "").strip()
        for entry in subdivisions
        if isinstance(entry, dict)
    ]
    codes = [code for code in codes if code]
    if not codes:
        return False
    return all(len(code.split("-")) > STATE_CODE_PARTS for code in codes)


def _code_list(value):
    if not isinstance(value, list):
        return []
    codes = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip()
        if code:
            codes.append(code)
    return sorted(set(codes))


def has_exception_tag(raw):
    tags = raw.get("tags") if isinstance(raw, dict) else None
    if not isinstance(tags, list):
        return False
    return any(str(tag).strip() == EXCEPTION_TAG for tag in tags)


def normalize_entry(raw, kind):
    if not isinstance(raw, dict):
        return None
    if is_local_scope(raw):
        return None
    start = _parse_source_date(raw.get("startDate"))
    end = _parse_source_date(raw.get("endDate"))
    if start is None and end is None:
        return None
    start = start or end
    end = end or start
    if end < start:
        start, end = end, start
    name = _source_name(raw.get("name"))
    period_type = classify_period(name)
    identifier = str(raw.get("id") or "").strip()
    if not identifier:
        identifier = f"{kind}|{start.isoformat()}|{end.isoformat()}|{name}"
    return {
        "id": identifier,
        "kind": kind,
        "type": period_type,
        "name": name,
        "name_key": PERIOD_KEY_PREFIX + period_type if period_type else "",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "groups": _code_list(raw.get("groups")),
        "exception": has_exception_tag(raw),
    }


def build_params(region, year):
    return {
        "countryIsoCode": COUNTRY_ISO_CODE,
        "subdivisionCode": region,
        "languageIsoCode": SOURCE_LANGUAGE,
        "validFrom": f"{year}-01-01",
        "validTo": f"{year}-12-31",
    }


def _request(path, params):
    response = requests.get(
        f"{SOURCE_BASE_URL}/{path}",
        params=params,
        headers={"accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("unexpected payload shape")
    return payload


def fetch_year(region, year):
    params = build_params(region, year)
    collected = []
    for path, kind in (("SchoolHolidays", KIND_SCHOOL), ("PublicHolidays", KIND_PUBLIC)):
        for raw in _request(path, params):
            entry = normalize_entry(raw, kind)
            if entry:
                collected.append(entry)
    return collected


def _stamp(entry, field):
    value = entry.get(field) if isinstance(entry, dict) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return value


def _is_fresh(entry, now, year, current_year):
    if year < current_year:
        return True
    fetched_at = _stamp(entry, "fetched_at")
    if fetched_at is None:
        return False
    return now - fetched_at < ACTIVE_TTL_SECONDS


def _may_retry(raw_entry, now):
    failed_at = _stamp(raw_entry, "failed_at")
    if failed_at is None:
        return True
    return now - failed_at >= FAILURE_BACKOFF_SECONDS


def _covering(periods, iso_day):
    return [period for period in periods if period["start"] <= iso_day <= period["end"]]


def known_groups(periods):
    codes = set()
    for period in periods:
        codes.update(period.get("groups") or [])
    return codes


def _applies_state_wide(period):
    return not period.get("exception") and not (period.get("groups") or [])


def _overrides_lessons(hits, groups):
    covered = set()
    for hit in hits:
        if hit.get("exception"):
            continue
        if not (hit.get("groups") or []):
            return True
        covered.update(hit["groups"])
    return bool(groups) and covered >= groups


def _primary(hits):
    if not hits:
        return None
    ranked = sorted(
        hits,
        key=lambda hit: (
            0 if _applies_state_wide(hit) else 1,
            0 if hit["kind"] == KIND_SCHOOL else 1,
        ),
    )
    return ranked[0]


def _day_map(start, end, periods, groups):
    days = {}
    day = start
    while day <= end:
        iso_day = day.isoformat()
        hits = _covering(periods, iso_day)
        primary = _primary(hits)
        days[iso_day] = {
            "free": primary is not None,
            "overrides_lessons": _overrides_lessons(hits, groups),
            "weekend": day.weekday() >= SCHOOL_DAYS_PER_WEEK,
            "kind": primary["kind"] if primary else "",
            "type": primary["type"] if primary else "",
            "name": primary["name"] if primary else "",
            "name_key": primary["name_key"] if primary else "",
            "period_id": primary["id"] if primary else "",
        }
        day += timedelta(days=1)
    return days


def _dominant(week_periods, school_days):
    best = None
    best_score = -1
    for period in week_periods:
        covered = sum(
            1 for day in school_days if period["start"] <= day.isoformat() <= period["end"]
        )
        score = covered * 2 + (1 if period["kind"] == KIND_SCHOOL else 0)
        if score > best_score:
            best_score = score
            best = period
    return best


def _week_rows(start, end, days, periods):
    rows = []
    monday = start
    while monday <= end:
        school_days = [monday + timedelta(days=index) for index in range(SCHOOL_DAYS_PER_WEEK)]
        free_days = [
            day for day in school_days if days.get(day.isoformat(), {}).get("free")
        ]
        override_days = [
            day
            for day in school_days
            if days.get(day.isoformat(), {}).get("overrides_lessons")
        ]
        week_periods = []
        seen = set()
        for day in school_days:
            for hit in _covering(periods, day.isoformat()):
                if hit["id"] in seen:
                    continue
                seen.add(hit["id"])
                week_periods.append(hit)
        if len(free_days) == SCHOOL_DAYS_PER_WEEK:
            coverage = COVERAGE_FULL
        elif free_days:
            coverage = COVERAGE_PARTIAL
        else:
            coverage = COVERAGE_NONE
        calendar = monday.isocalendar()
        rows.append(
            {
                "week": calendar[1],
                "iso_year": calendar[0],
                "start": monday.isoformat(),
                "end": (monday + timedelta(days=6)).isoformat(),
                "coverage": coverage,
                "label_key": WEEK_LABEL_KEYS[coverage],
                "school_days": SCHOOL_DAYS_PER_WEEK,
                "free_school_days": len(free_days),
                "override_school_days": len(override_days),
                "overrides_lessons": len(override_days) == SCHOOL_DAYS_PER_WEEK,
                "primary": _dominant(week_periods, school_days),
                "periods": week_periods,
            }
        )
        monday += timedelta(days=7)
    return rows


class HolidayCalendar:
    def __init__(self, store, fetcher=None, clock=None):
        self.store = store
        self.fetcher = fetcher or fetch_year
        self.clock = clock or clock_module.time

    def region(self, config=None):
        source = config if config is not None else self.store.load_config()
        return clean_region(source.get(CONFIG_KEY))

    def _try_fetch(self, region, year):
        try:
            return self.fetcher(region, year)
        except (requests.RequestException, ValueError, TypeError, KeyError, OSError):
            return None

    def today(self):
        return berlin_today(
            datetime.fromtimestamp(self.clock(), timezone.utc).replace(tzinfo=None)
        )

    def _load_year(self, cache, region, year, now, current_year, outcome):
        key = f"{region}|{year}"
        raw_entry = cache.get(key)
        if not isinstance(raw_entry, dict):
            raw_entry = {}
        entry = raw_entry if isinstance(raw_entry.get("periods"), list) else None
        if entry is not None and _is_fresh(entry, now, year, current_year):
            return entry
        if not _may_retry(raw_entry, now):
            if entry is not None:
                outcome["stale"] = True
            return entry
        fetched = self._try_fetch(region, year)
        if fetched is None:
            failed = dict(raw_entry)
            failed["failed_at"] = now
            cache[key] = failed
            outcome["changed"] = True
            if entry is not None:
                outcome["stale"] = True
            return entry
        entry = {"fetched_at": now, "periods": fetched}
        cache[key] = entry
        outcome["changed"] = True
        return entry

    def _prefetch_years(self, today, required):
        if today.month < PREFETCH_FROM_MONTH:
            return []
        upcoming = today.year + 1
        return [] if upcoming in required else [upcoming]

    def _periods(self, region, start, end):
        cache = self.store.load_holidays_cache()
        now = int(self.clock())
        today = self.today()
        current_year = today.year
        outcome = {"stale": False, "changed": False}
        collected = {}
        complete = True
        required = list(range(start.year, end.year + 1))
        for year in required:
            entry = self._load_year(cache, region, year, now, current_year, outcome)
            if entry is None:
                complete = False
                continue
            for period in entry["periods"]:
                if isinstance(period, dict) and period.get("id"):
                    collected[period["id"]] = period
        for year in self._prefetch_years(today, required):
            self._load_year(cache, region, year, now, current_year, outcome)
        if outcome["changed"]:
            self.store.save_holidays_cache(cache)
        return list(collected.values()), complete, outcome["stale"]

    def range_info(self, start, end, config=None):
        if end < start:
            start, end = end, start
        window_start = start - timedelta(days=start.weekday())
        window_end = end + timedelta(days=6 - end.weekday())
        region = self.region(config)
        payload = {
            "region": region,
            "status": STATUS_DISABLED,
            "stale": False,
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "requested_from": start.isoformat(),
            "requested_to": end.isoformat(),
            "groups": [],
            "days": {},
            "weeks": [],
            "periods": [],
        }
        if not region:
            return payload
        periods, complete, stale = self._periods(region, window_start, window_end)
        payload["stale"] = stale
        if not complete:
            payload["status"] = STATUS_UNKNOWN
            return payload
        overlapping = [
            period
            for period in periods
            if period["start"] <= payload["to"] and period["end"] >= payload["from"]
        ]
        overlapping.sort(key=lambda period: (period["start"], period["end"], period["kind"], period["name"]))
        groups = known_groups(periods)
        payload["status"] = STATUS_OK
        payload["groups"] = sorted(groups)
        payload["periods"] = overlapping
        payload["days"] = _day_map(window_start, window_end, overlapping, groups)
        payload["weeks"] = _week_rows(window_start, window_end, payload["days"], overlapping)
        return payload

    def week_info(self, week_offset=0, today=None, config=None):
        start, end = week_range(week_offset, today)
        return self.range_info(start, end, config)

    def day_info(self, day, config=None):
        payload = self.range_info(day, day, config)
        entry = payload["days"].get(day.isoformat())
        return {
            "date": day.isoformat(),
            "status": payload["status"],
            "stale": payload["stale"],
            "free": bool(entry and entry["free"]),
            "overrides_lessons": bool(entry and entry["overrides_lessons"]),
            "weekend": bool(entry and entry["weekend"]),
            "kind": entry["kind"] if entry else "",
            "type": entry["type"] if entry else "",
            "name": entry["name"] if entry else "",
            "name_key": entry["name_key"] if entry else "",
            "period_id": entry["period_id"] if entry else "",
        }
