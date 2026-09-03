import re
import time as clock_module

import requests

SOURCE_BASE_URL = "https://openplzapi.org"
LOCALITIES_PATH = "de/Localities"
REQUEST_TIMEOUT = 10
CACHE_TTL_SECONDS = 24 * 60 * 60

REQUEST_PARAM_KEYS = frozenset({"postalCode"})

POSTAL_CODE_PATTERN = re.compile(r"^[0-9]{5}$")

CONFIDENCE_HIGH = "high"
CONFIDENCE_NONE = "none"

ORIGIN_NONE = ""
ORIGIN_ISERV_POSTAL_CODE = "iserv_postal_code"

ORIGIN_KEYS = {
    ORIGIN_ISERV_POSTAL_CODE: "holidays.suggestion.origin.iservPostalCode",
}

REASON_NOT_CONFIGURED = "not_configured"
REASON_NO_POSTAL_CODE = "no_postal_code"
REASON_FOREIGN_COUNTRY = "foreign_country"
REASON_UNKNOWN_POSTAL_CODE = "unknown_postal_code"
REASON_AMBIGUOUS = "ambiguous"
REASON_UNAVAILABLE = "unavailable"

STATE_KEY_REGIONS = {
    "01": "DE-SH",
    "02": "DE-HH",
    "03": "DE-NI",
    "04": "DE-HB",
    "05": "DE-NW",
    "06": "DE-HE",
    "07": "DE-RP",
    "08": "DE-BW",
    "09": "DE-BY",
    "10": "DE-SL",
    "11": "DE-BE",
    "12": "DE-BB",
    "13": "DE-MV",
    "14": "DE-SN",
    "15": "DE-ST",
    "16": "DE-TH",
}

GERMAN_COUNTRY_NAMES = frozenset(
    {"", "d", "de", "deu", "deutschland", "germany", "bundesrepublik deutschland"}
)

CACHEABLE_REASONS = frozenset({"", REASON_UNKNOWN_POSTAL_CODE, REASON_AMBIGUOUS})


def clean_postal_code(value):
    text = "".join(str(value or "").split())
    return text if POSTAL_CODE_PATTERN.match(text) else ""


def is_german_country(value):
    return " ".join(str(value or "").strip().lower().split()) in GERMAN_COUNTRY_NAMES


def state_keys(rows):
    keys = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        state = row.get("federalState")
        if not isinstance(state, dict):
            continue
        key = str(state.get("key") or "").strip()
        if key:
            keys.add(key)
    return keys


def fetch_localities(postal_code):
    response = requests.get(
        f"{SOURCE_BASE_URL}/{LOCALITIES_PATH}",
        params={"postalCode": postal_code},
        headers={"accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("unexpected payload shape")
    return payload


def no_suggestion(reason):
    return {
        "region": "",
        "confidence": CONFIDENCE_NONE,
        "origin": ORIGIN_NONE,
        "origin_key": "",
        "reason": reason,
    }


def suggestion(region, origin):
    return {
        "region": region,
        "confidence": CONFIDENCE_HIGH,
        "origin": origin,
        "origin_key": ORIGIN_KEYS.get(origin, ""),
        "reason": "",
    }


def region_for_rows(rows):
    keys = state_keys(rows)
    if not keys:
        return "", REASON_UNKNOWN_POSTAL_CODE
    if len(keys) > 1:
        return "", REASON_AMBIGUOUS
    region = STATE_KEY_REGIONS.get(keys.pop(), "")
    if not region:
        return "", REASON_UNKNOWN_POSTAL_CODE
    return region, ""


class RegionSuggester:
    def __init__(self, service, fetcher=None, clock=None):
        self.service = service
        self.fetcher = fetcher or fetch_localities
        self.clock = clock or clock_module.time
        self._cache = {}

    def _school(self):
        try:
            profile = self.service.school_profile()
        except Exception:
            return None
        return profile if isinstance(profile, dict) else {}

    def _cached(self, postal_code):
        entry = self._cache.get(postal_code)
        if not entry:
            return None
        stamped_at, result = entry
        if self.clock() - stamped_at >= CACHE_TTL_SECONDS:
            self._cache.pop(postal_code, None)
            return None
        return dict(result)

    def _lookup(self, postal_code):
        cached = self._cached(postal_code)
        if cached is not None:
            return cached
        try:
            rows = self.fetcher(postal_code)
        except (requests.RequestException, ValueError, TypeError, KeyError, OSError):
            return no_suggestion(REASON_UNAVAILABLE)
        region, reason = region_for_rows(rows)
        result = (
            suggestion(region, ORIGIN_ISERV_POSTAL_CODE) if region else no_suggestion(reason)
        )
        if result["reason"] in CACHEABLE_REASONS:
            self._cache[postal_code] = (self.clock(), dict(result))
        return result

    def suggest(self):
        school = self._school()
        if school is None:
            return no_suggestion(REASON_NOT_CONFIGURED)
        if not is_german_country(school.get("country")):
            return no_suggestion(REASON_FOREIGN_COUNTRY)
        postal_code = clean_postal_code(school.get("postal_code"))
        if not postal_code:
            return no_suggestion(REASON_NO_POSTAL_CODE)
        return self._lookup(postal_code)
