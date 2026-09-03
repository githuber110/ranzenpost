import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from app import holidays
from app.iserv.absences import _date_part, _epoch
from app.server import create_app
from app.store import Store

FIXTURES = Path(__file__).parent / "fixtures"

FIXTURE_SOURCES = {
    ("DE-NI", 2026): ("holidays_school_de_ni_2026.json", "holidays_public_de_ni_2026.json"),
    ("DE-NI", 2027): ("holidays_school_de_ni_2027.json", "holidays_public_de_ni_2027.json"),
    ("DE-BY", 2026): ("holidays_school_de_by_2026.json", "holidays_public_de_by_2026.json"),
    ("DE-MV", 2026): ("holidays_school_de_mv_2026.json", None),
    ("DE-SH", 2026): ("holidays_school_de_sh_2026.json", None),
}

LIVE_SOURCE_PERIOD_NAMES = (
    "Sommerferien",
    "Herbstferien",
    "Weihnachtsferien",
    "Osterferien",
    "Pfingstferien",
    "Winterferien",
    "Frühjahrsferien",
    "Halbjahresferien",
    "Halbjahrespause",
    "Fastnachtsferien",
    "Zusätzlicher Ferientag",
    "Unterrichtsfreier Tag",
    "Variabler Ferientag",
    "Schulfreier Tag",
)


def load_fixture_json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_year(region, year):
    names = FIXTURE_SOURCES.get((region, year))
    if names is None:
        return []
    school_file, public_file = names
    entries = []
    for name, kind in ((school_file, holidays.KIND_SCHOOL), (public_file, holidays.KIND_PUBLIC)):
        if not name:
            continue
        entries += [holidays.normalize_entry(raw, kind) for raw in load_fixture_json(name)]
    return [entry for entry in entries if entry]


class CountingFetcher:
    def __init__(self, source=None):
        self.source = source or fixture_year
        self.calls = []
        self.offline = False

    def __call__(self, region, year):
        self.calls.append((region, year))
        if self.offline:
            raise requests.ConnectionError("offline")
        return self.source(region, year)


CLOCK_REFERENCE = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc).timestamp()


class FakeClock:
    def __init__(self, value=None):
        self.value = CLOCK_REFERENCE if value is None else value

    def __call__(self):
        return self.value


def make_store(tmp_path, region="DE-NI", name="data"):
    store = Store(tmp_path / name)
    config = store.load_config()
    config[holidays.CONFIG_KEY] = region
    store.save_config(config)
    return store


def make_calendar(tmp_path, region="DE-NI", name="data"):
    store = make_store(tmp_path, region, name)
    fetcher = CountingFetcher()
    clock = FakeClock()
    return holidays.HolidayCalendar(store, fetcher=fetcher, clock=clock), fetcher, clock, store


def week_row(payload, monday):
    for row in payload["weeks"]:
        if row["start"] == monday:
            return row
    raise AssertionError(f"no week row starting {monday}")


def test_the_autumn_break_starts_and_ends_on_the_exact_source_days(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 5), date(2026, 10, 31))
    assert payload["status"] == holidays.STATUS_OK
    assert payload["days"]["2026-10-11"]["free"] is False
    assert payload["days"]["2026-10-12"]["free"] is True
    assert payload["days"]["2026-10-24"]["free"] is True
    assert payload["days"]["2026-10-25"]["free"] is False


def test_day_info_names_the_period_and_offers_a_translation_key(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    info = calendar.day_info(date(2026, 10, 12))
    assert info["free"] is True
    assert info["kind"] == holidays.KIND_SCHOOL
    assert info["type"] == "autumn"
    assert info["name_key"] == "holidays.period.autumn"
    assert info["name"] == "Herbstferien"


def test_a_regular_school_day_is_not_free(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    info = calendar.day_info(date(2026, 9, 14))
    assert info["free"] is False
    assert info["name_key"] == ""
    assert info["name"] == ""


def test_the_christmas_break_covers_both_sides_of_the_year_boundary(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 12, 28), date(2027, 1, 8))
    assert payload["status"] == holidays.STATUS_OK
    assert payload["days"]["2026-12-31"]["free"] is True
    assert payload["days"]["2027-01-04"]["free"] is True
    assert payload["days"]["2026-12-31"]["type"] == "christmas"
    assert payload["days"]["2027-01-04"]["type"] == "christmas"


def test_a_january_week_alone_still_finds_the_period_that_started_last_year(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    payload = calendar.range_info(date(2027, 1, 4), date(2027, 1, 8))
    assert fetcher.calls == [("DE-NI", 2027)]
    assert payload["days"]["2027-01-04"]["type"] == "christmas"
    assert week_row(payload, "2027-01-04")["coverage"] == holidays.COVERAGE_FULL


def test_a_range_across_two_years_reports_the_shared_period_only_once(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 12, 28), date(2027, 1, 8))
    christmas = [
        period for period in payload["periods"] if period["type"] == "christmas"
    ]
    assert len(christmas) == 1
    assert christmas[0]["start"] == "2026-12-23"
    assert christmas[0]["end"] == "2027-01-09"


def test_a_week_inside_the_autumn_break_is_fully_covered(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    row = week_row(payload, "2026-10-12")
    assert row["week"] == 42
    assert row["iso_year"] == 2026
    assert row["coverage"] == holidays.COVERAGE_FULL
    assert row["free_school_days"] == 5
    assert row["label_key"] == "holidays.week.full"
    assert row["primary"]["type"] == "autumn"


def test_the_second_autumn_week_is_also_fully_covered(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 19), date(2026, 10, 25))
    row = week_row(payload, "2026-10-19")
    assert row["coverage"] == holidays.COVERAGE_FULL
    assert row["free_school_days"] == 5


def test_a_week_after_the_break_is_a_normal_week(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 26), date(2026, 11, 1))
    row = week_row(payload, "2026-10-26")
    assert row["coverage"] == holidays.COVERAGE_NONE
    assert row["free_school_days"] == 0
    assert row["label_key"] == ""
    assert row["primary"] is None


def test_a_public_holiday_on_a_saturday_does_not_make_the_week_partial(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 26), date(2026, 11, 1))
    assert payload["days"]["2026-10-31"]["free"] is True
    assert payload["days"]["2026-10-31"]["weekend"] is True
    assert week_row(payload, "2026-10-26")["coverage"] == holidays.COVERAGE_NONE


def test_a_bridge_day_next_to_a_public_holiday_makes_the_week_partial(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 5, 11), date(2026, 5, 17))
    row = week_row(payload, "2026-05-11")
    assert row["coverage"] == holidays.COVERAGE_PARTIAL
    assert row["free_school_days"] == 2
    assert row["label_key"] == "holidays.week.partial"
    assert payload["days"]["2026-05-14"]["kind"] == holidays.KIND_PUBLIC
    assert payload["days"]["2026-05-15"]["kind"] == holidays.KIND_SCHOOL


def test_a_single_holiday_day_makes_the_week_partial(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 5, 25), date(2026, 5, 31))
    row = week_row(payload, "2026-05-25")
    assert row["coverage"] == holidays.COVERAGE_PARTIAL
    assert row["free_school_days"] == 2


def test_a_school_period_wins_over_an_overlapping_public_holiday(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 12, 21), date(2026, 12, 27))
    assert payload["days"]["2026-12-25"]["kind"] == holidays.KIND_SCHOOL
    assert payload["days"]["2026-12-25"]["type"] == "christmas"


def test_a_request_for_a_partial_week_is_widened_to_whole_weeks(tmp_path):
    calendar = make_calendar(tmp_path)[0]
    payload = calendar.range_info(date(2026, 10, 14), date(2026, 10, 15))
    assert payload["requested_from"] == "2026-10-14"
    assert payload["requested_to"] == "2026-10-15"
    assert payload["from"] == "2026-10-12"
    assert payload["to"] == "2026-10-18"
    assert len(payload["weeks"]) == 1


def test_the_cache_answers_the_second_call_without_a_second_fetch(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026)]
    calendar.range_info(date(2026, 10, 19), date(2026, 10, 25))
    assert fetcher.calls == [("DE-NI", 2026)]


def test_an_expired_cache_entry_is_fetched_again(tmp_path):
    calendar, fetcher, clock = make_calendar(tmp_path)[:3]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    clock.value += holidays.ACTIVE_TTL_SECONDS + 1
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026), ("DE-NI", 2026)]


def test_a_cache_entry_just_under_the_expiry_is_still_used(tmp_path):
    calendar, fetcher, clock = make_calendar(tmp_path)[:3]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    clock.value += holidays.ACTIVE_TTL_SECONDS - 1
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026)]


def test_an_expired_cache_still_answers_when_the_network_is_gone(tmp_path):
    calendar, fetcher, clock = make_calendar(tmp_path)[:3]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    clock.value += holidays.ACTIVE_TTL_SECONDS + 1
    fetcher.offline = True
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_OK
    assert payload["stale"] is True
    assert week_row(payload, "2026-10-12")["coverage"] == holidays.COVERAGE_FULL


def test_an_empty_cache_without_network_reports_unknown_and_invents_nothing(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    fetcher.offline = True
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_UNKNOWN
    assert payload["days"] == {}
    assert payload["weeks"] == []
    assert payload["periods"] == []


def test_a_missing_year_makes_the_answer_unknown_rather_than_half_true(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    calendar.range_info(date(2026, 12, 21), date(2026, 12, 27))
    fetcher.offline = True
    payload = calendar.range_info(date(2026, 12, 28), date(2027, 1, 3))
    assert payload["status"] == holidays.STATUS_UNKNOWN
    assert payload["days"] == {}


def test_the_cache_keeps_regions_apart(tmp_path):
    store = make_store(tmp_path, "DE-NI")
    fetcher = CountingFetcher()
    clock = FakeClock()
    calendar = holidays.HolidayCalendar(store, fetcher=fetcher, clock=clock)
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    config = store.load_config()
    config[holidays.CONFIG_KEY] = "DE-BY"
    store.save_config(config)
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026), ("DE-BY", 2026)]
    assert set(store.load_holidays_cache()) == {"DE-NI|2026", "DE-BY|2026"}


def test_a_corrupt_cache_file_is_ignored_instead_of_crashing(tmp_path):
    calendar, fetcher, _, store = make_calendar(tmp_path)
    store.holidays_cache_path.write_text("{not json", encoding="utf-8")
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_OK
    assert fetcher.calls == [("DE-NI", 2026)]


def test_without_a_region_the_calendar_reports_disabled(tmp_path):
    store = Store(tmp_path / "data")
    fetcher = CountingFetcher()
    calendar = holidays.HolidayCalendar(store, fetcher=fetcher, clock=FakeClock())
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_DISABLED
    assert payload["region"] == ""
    assert payload["days"] == {}
    assert fetcher.calls == []


def test_an_unknown_region_value_is_treated_as_switched_off(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config[holidays.CONFIG_KEY] = "DE-XX"
    store.save_config(config)
    fetcher = CountingFetcher()
    calendar = holidays.HolidayCalendar(store, fetcher=fetcher, clock=FakeClock())
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_DISABLED
    assert fetcher.calls == []


def test_the_default_config_ships_the_region_switched_off(tmp_path):
    store = Store(tmp_path / "data")
    assert store.load_config()[holidays.CONFIG_KEY] == ""


def test_all_sixteen_regions_are_offered_with_a_translation_key():
    options = holidays.region_options()
    assert len(options) == 16
    assert {option["code"] for option in options} == set(holidays.REGION_CODES)
    assert options[0] == {"code": "DE-BW", "name_key": "holidays.region.bw"}
    for option in options:
        assert option["name_key"].startswith(holidays.REGION_KEY_PREFIX)


def test_every_region_and_period_key_exists_in_every_language_bundle():
    bundle_dir = Path(__file__).resolve().parents[2] / "frontend" / "i18n"
    expected = {option["name_key"] for option in holidays.region_options()}
    expected |= {
        holidays.PERIOD_KEY_PREFIX + period_type
        for period_type in set(holidays.SOURCE_PERIOD_NAMES.values())
    }
    expected |= set(key for key in holidays.WEEK_LABEL_KEYS.values() if key)
    expected.add("api.holidays.error.range")
    for language in ("de", "en", "ar", "tr", "ru", "uk"):
        bundle = json.loads((bundle_dir / f"{language}.json").read_text(encoding="utf-8"))
        missing = sorted(key for key in expected if key not in bundle)
        assert missing == [], f"{language}.json is missing {missing}"


def test_classify_recognises_every_name_the_live_source_uses():
    unclassified = [
        name for name in LIVE_SOURCE_PERIOD_NAMES if not holidays.classify_period(name)
    ]
    assert unclassified == []


def test_classify_survives_a_reworded_source_name():
    assert holidays.classify_period("Sommerferien 2027") == "summer"
    assert holidays.classify_period("  HERBSTFERIEN  ") == "autumn"
    assert holidays.classify_period("Fruehjahrsferien") == "spring"


def test_an_unknown_period_name_keeps_the_source_text_instead_of_a_made_up_key():
    entry = holidays.normalize_entry(
        {
            "id": "x",
            "startDate": "2026-06-01",
            "endDate": "2026-06-01",
            "name": [{"language": "DE", "text": "Reformationsfest"}],
        },
        holidays.KIND_SCHOOL,
    )
    assert entry["type"] == ""
    assert entry["name_key"] == ""
    assert entry["name"] == "Reformationsfest"


def test_normalize_keeps_the_source_calendar_date_unshifted():
    entry = holidays.normalize_entry(
        {
            "id": "x",
            "startDate": "2026-10-12",
            "endDate": "2026-10-24",
            "name": [{"language": "DE", "text": "Herbstferien"}],
        },
        holidays.KIND_SCHOOL,
    )
    assert entry["start"] == "2026-10-12"
    assert entry["end"] == "2026-10-24"


def test_normalize_drops_entries_without_a_usable_date():
    assert holidays.normalize_entry({"id": "x", "name": []}, holidays.KIND_SCHOOL) is None
    assert holidays.normalize_entry("nonsense", holidays.KIND_SCHOOL) is None
    assert holidays.normalize_entry({"startDate": "not-a-date"}, holidays.KIND_SCHOOL) is None


def test_normalize_repairs_a_reversed_range_and_a_missing_end():
    reversed_range = holidays.normalize_entry(
        {"id": "x", "startDate": "2026-10-24", "endDate": "2026-10-12", "name": []},
        holidays.KIND_SCHOOL,
    )
    assert reversed_range["start"] == "2026-10-12"
    assert reversed_range["end"] == "2026-10-24"
    open_end = holidays.normalize_entry(
        {"id": "y", "startDate": "2026-10-12", "name": []}, holidays.KIND_SCHOOL
    )
    assert open_end["end"] == "2026-10-12"


def test_berlin_today_matches_the_proven_absence_conversion_all_year():
    day = date(2026, 1, 1)
    while day <= date(2026, 12, 31):
        for moment in (time(0, 0), time(12, 0), time(23, 30)):
            stamp = _epoch(day, moment)
            utc_naive = datetime.fromtimestamp(stamp, timezone.utc).replace(tzinfo=None)
            assert holidays.berlin_today(utc_naive).isoformat() == _date_part(stamp)
        day += timedelta(days=1)


def test_berlin_today_holds_at_both_daylight_saving_edges():
    for day, moment in (
        (date(2026, 3, 28), time(23, 30)),
        (date(2026, 3, 29), time(0, 30)),
        (date(2026, 10, 24), time(23, 30)),
        (date(2026, 10, 25), time(0, 30)),
    ):
        stamp = _epoch(day, moment)
        utc_naive = datetime.fromtimestamp(stamp, timezone.utc).replace(tzinfo=None)
        assert holidays.berlin_today(utc_naive) == day


def test_a_week_offset_resolves_to_a_monday_to_sunday_span():
    start, end = holidays.week_range(0, date(2026, 10, 14))
    assert start == date(2026, 10, 12)
    assert end == date(2026, 10, 18)
    assert holidays.week_range(1, date(2026, 10, 14))[0] == date(2026, 10, 19)
    assert holidays.week_range(-1, date(2026, 10, 14))[0] == date(2026, 10, 5)


def test_a_week_offset_beyond_the_limit_is_clamped():
    assert holidays.clamp_week_offset(99) == holidays.MAX_WEEK_OFFSET
    assert holidays.clamp_week_offset(-99) == -holidays.MAX_WEEK_OFFSET
    assert holidays.clamp_week_offset("nonsense") == 0


def test_parse_day_reads_both_the_iso_and_the_iserv_date_format():
    assert holidays.parse_day("2026-10-12") == date(2026, 10, 12)
    assert holidays.parse_day("12.10.2026") == date(2026, 10, 12)
    assert holidays.parse_day("") is None
    assert holidays.parse_day("nonsense") is None
    assert holidays.parse_day("32.10.2026") is None


def test_the_outgoing_request_carries_only_the_region_and_the_period(monkeypatch):
    seen = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    def stub_get(url, params=None, headers=None, timeout=None):
        seen.append({"url": url, "params": dict(params or {})})
        return StubResponse()

    monkeypatch.setattr(holidays.requests, "get", stub_get)
    holidays.fetch_year("DE-NI", 2026)
    assert len(seen) == 2
    for call in seen:
        assert call["url"].startswith(holidays.SOURCE_BASE_URL)
        assert set(call["params"]) == set(holidays.REQUEST_PARAM_KEYS)
        assert call["params"] == {
            "countryIsoCode": "DE",
            "subdivisionCode": "DE-NI",
            "languageIsoCode": "DE",
            "validFrom": "2026-01-01",
            "validTo": "2026-12-31",
        }


def test_an_unexpected_payload_shape_is_handled_like_a_network_failure(tmp_path, monkeypatch):
    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": True}

    monkeypatch.setattr(
        holidays.requests, "get", lambda *args, **kwargs: StubResponse()
    )
    store = make_store(tmp_path)
    calendar = holidays.HolidayCalendar(store, clock=FakeClock())
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_UNKNOWN


def test_a_malformed_entry_is_dropped_while_the_rest_survives(tmp_path, monkeypatch):
    good = {
        "id": "good",
        "startDate": "2026-10-12",
        "endDate": "2026-10-16",
        "name": [{"language": "DE", "text": "Herbstferien"}],
    }

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [good, {"id": "bad"}, "nonsense"]

    monkeypatch.setattr(
        holidays.requests, "get", lambda *args, **kwargs: StubResponse()
    )
    store = make_store(tmp_path)
    calendar = holidays.HolidayCalendar(store, clock=FakeClock())
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_OK
    assert week_row(payload, "2026-10-12")["coverage"] == holidays.COVERAGE_FULL


class StubService:
    def __init__(self, store):
        self.store = store

    def is_configured(self):
        return True

    def check_connection(self):
        return "ok"


@pytest.fixture
def client(tmp_path):
    calendar, fetcher, _, store = make_calendar(tmp_path)
    app = create_app(StubService(store), holiday_calendar=calendar)
    return TestClient(app), store, fetcher


def test_the_region_endpoint_lists_all_sixteen_states(client):
    http, _, _ = client
    body = http.get("/api/holidays/regions").json()
    assert len(body["regions"]) == 16
    assert {region["code"] for region in body["regions"]} == set(holidays.REGION_CODES)


def test_the_holiday_endpoint_answers_for_an_explicit_range(client):
    http, _, _ = client
    body = http.get("/api/holidays?start=2026-10-12&end=2026-10-18").json()
    assert body["status"] == "ok"
    assert body["region"] == "DE-NI"
    assert body["from"] == "2026-10-12"
    assert body["to"] == "2026-10-18"
    assert len(body["weeks"]) == 1
    assert body["weeks"][0]["coverage"] == "full"
    assert body["weeks"][0]["primary"]["name_key"] == "holidays.period.autumn"
    assert body["days"]["2026-10-12"]["free"] is True


def test_the_holiday_endpoint_accepts_the_iserv_date_format(client):
    http, _, _ = client
    body = http.get("/api/holidays?start=12.10.2026&end=18.10.2026").json()
    assert body["from"] == "2026-10-12"
    assert body["weeks"][0]["coverage"] == "full"


def test_the_holiday_endpoint_falls_back_to_a_week_offset(client):
    http, _, _ = client
    body = http.get("/api/holidays?week=0").json()
    assert len(body["weeks"]) == 1
    assert body["weeks"][0]["start"] == body["from"]
    assert (
        date.fromisoformat(body["to"]) - date.fromisoformat(body["from"])
    ).days == 6


def test_the_holiday_endpoint_refuses_an_oversized_range(client):
    http, _, _ = client
    response = http.get("/api/holidays?start=2026-01-01&end=2027-12-31")
    assert response.status_code == 400
    assert response.json()["message_key"] == "api.holidays.error.range"


def test_the_holiday_endpoint_reports_disabled_without_a_region(tmp_path):
    store = Store(tmp_path / "data")
    calendar = holidays.HolidayCalendar(store, fetcher=CountingFetcher(), clock=FakeClock())
    http = TestClient(create_app(StubService(store), holiday_calendar=calendar))
    body = http.get("/api/holidays?start=2026-10-12&end=2026-10-18").json()
    assert body["status"] == "disabled"
    assert body["days"] == {}


def test_the_region_setting_survives_a_post_and_a_get(client):
    http, store, _ = client
    saved = http.post("/api/config", json={holidays.CONFIG_KEY: "DE-BY"})
    assert saved.status_code == 200
    assert saved.json() == {"saved": True}
    assert store.load_config()[holidays.CONFIG_KEY] == "DE-BY"
    assert http.get("/api/config").json()[holidays.CONFIG_KEY] == "DE-BY"


def test_the_region_key_is_covered_by_the_config_allow_list(client):
    http, _, _ = client
    response = http.post("/api/config", json={holidays.CONFIG_KEY: "DE-SH"})
    assert response.status_code == 200
    assert "unknown_keys" not in response.json()


def test_switching_the_region_off_again_is_accepted(client):
    http, store, _ = client
    http.post("/api/config", json={holidays.CONFIG_KEY: ""})
    assert store.load_config()[holidays.CONFIG_KEY] == ""
    body = http.get("/api/holidays?start=2026-10-12&end=2026-10-18").json()
    assert body["status"] == "disabled"


def by_calendar(tmp_path):
    return make_calendar(tmp_path, "DE-BY", "by")[0]


def mv_calendar(tmp_path):
    return make_calendar(tmp_path, "DE-MV", "mv")[0]


def sh_calendar(tmp_path):
    return make_calendar(tmp_path, "DE-SH", "sh")[0]


def test_a_local_public_holiday_never_reaches_the_payload(tmp_path):
    payload = by_calendar(tmp_path).range_info(date(2026, 8, 3), date(2026, 8, 9))
    assert payload["status"] == holidays.STATUS_OK
    assert payload["periods"] == []
    assert payload["days"]["2026-08-08"]["free"] is False
    assert payload["days"]["2026-08-08"]["overrides_lessons"] is False


def test_a_state_wide_public_holiday_may_override_the_lessons(tmp_path):
    info = by_calendar(tmp_path).day_info(date(2026, 11, 1))
    assert info["free"] is True
    assert info["kind"] == holidays.KIND_PUBLIC
    assert info["overrides_lessons"] is True


def test_a_school_free_day_without_a_public_holiday_may_override(tmp_path):
    info = by_calendar(tmp_path).day_info(date(2026, 11, 18))
    assert info["free"] is True
    assert info["kind"] == holidays.KIND_SCHOOL
    assert info["overrides_lessons"] is True


def test_the_very_same_day_stays_a_school_day_in_another_state(tmp_path):
    info = make_calendar(tmp_path)[0].day_info(date(2026, 11, 18))
    assert info["free"] is False
    assert info["overrides_lessons"] is False


def test_is_local_scope_reads_both_markers():
    assert holidays.is_local_scope({"regionalScope": "Local"}) is True
    assert holidays.is_local_scope({"subdivisions": [{"code": "DE-BY-AU"}]}) is True
    assert holidays.is_local_scope({"subdivisions": [{"code": "DE-BY"}]}) is False
    assert holidays.is_local_scope({"regionalScope": "Regional"}) is False
    assert holidays.is_local_scope("nonsense") is False


def test_normalize_keeps_the_group_and_exception_markers():
    entry = holidays.normalize_entry(
        {
            "id": "x",
            "startDate": "2026-07-13",
            "endDate": "2026-08-29",
            "name": [{"language": "DE", "text": "Sommerferien"}],
            "groups": [{"code": "DE-MV-BBS"}],
            "tags": ["Exception"],
        },
        holidays.KIND_SCHOOL,
    )
    assert entry["groups"] == ["DE-MV-BBS"]
    assert entry["exception"] is True


def test_a_period_for_one_school_type_alone_must_not_hide_lessons(tmp_path):
    payload = mv_calendar(tmp_path).range_info(date(2026, 8, 24), date(2026, 8, 30))
    assert payload["groups"] == ["DE-MV-ABS", "DE-MV-BBS"]
    row = week_row(payload, "2026-08-24")
    assert row["coverage"] == holidays.COVERAGE_FULL
    assert row["free_school_days"] == 5
    assert row["override_school_days"] == 0
    assert row["overrides_lessons"] is False
    assert payload["days"]["2026-08-24"]["free"] is True
    assert payload["days"]["2026-08-24"]["overrides_lessons"] is False


def test_a_day_free_for_every_school_type_may_hide_lessons(tmp_path):
    payload = mv_calendar(tmp_path).range_info(date(2026, 7, 13), date(2026, 7, 19))
    row = week_row(payload, "2026-07-13")
    assert row["coverage"] == holidays.COVERAGE_FULL
    assert row["override_school_days"] == 5
    assert row["overrides_lessons"] is True


def test_a_single_day_listed_for_all_groups_may_hide_lessons(tmp_path):
    info = mv_calendar(tmp_path).day_info(date(2026, 11, 26))
    assert info["free"] is True
    assert info["overrides_lessons"] is True


def test_an_island_exception_period_never_hides_lessons(tmp_path):
    payload = sh_calendar(tmp_path).range_info(date(2026, 10, 5), date(2026, 10, 11))
    row = week_row(payload, "2026-10-05")
    assert row["coverage"] == holidays.COVERAGE_FULL
    assert row["override_school_days"] == 0
    assert row["overrides_lessons"] is False
    assert payload["days"]["2026-10-05"]["free"] is True
    assert payload["days"]["2026-10-05"]["overrides_lessons"] is False


def test_the_mainland_period_of_the_same_state_does_hide_lessons(tmp_path):
    payload = sh_calendar(tmp_path).range_info(date(2026, 10, 12), date(2026, 10, 18))
    row = week_row(payload, "2026-10-12")
    assert row["overrides_lessons"] is True
    assert payload["days"]["2026-10-12"]["overrides_lessons"] is True


def test_an_unknown_status_offers_nothing_that_could_hide_lessons(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    fetcher.offline = True
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_UNKNOWN
    assert payload["days"] == {}
    assert payload["weeks"] == []


def test_a_disabled_calendar_offers_nothing_that_could_hide_lessons(tmp_path):
    store = Store(tmp_path / "off")
    calendar = holidays.HolidayCalendar(store, fetcher=CountingFetcher(), clock=FakeClock())
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_DISABLED
    assert payload["days"] == {}


def test_a_stale_answer_still_allows_the_override(tmp_path):
    calendar, fetcher, clock = make_calendar(tmp_path)[:3]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    clock.value += holidays.ACTIVE_TTL_SECONDS + 1
    fetcher.offline = True
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["stale"] is True
    assert week_row(payload, "2026-10-12")["overrides_lessons"] is True


def test_a_past_year_is_never_fetched_again(tmp_path):
    calendar, fetcher, clock, store = make_calendar(tmp_path)
    store.save_holidays_cache({"DE-NI|2025": {"fetched_at": 0, "periods": []}})
    payload = calendar.range_info(date(2025, 10, 13), date(2025, 10, 17))
    assert payload["status"] == holidays.STATUS_OK
    assert fetcher.calls == []


def test_a_failed_fetch_is_not_retried_on_the_very_next_request(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    fetcher.offline = True
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026)]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026)]


def test_a_failed_fetch_is_retried_once_the_backoff_has_passed(tmp_path):
    calendar, fetcher, clock = make_calendar(tmp_path)[:3]
    fetcher.offline = True
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    clock.value += holidays.FAILURE_BACKOFF_SECONDS
    fetcher.offline = False
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026), ("DE-NI", 2026)]
    assert payload["status"] == holidays.STATUS_OK


def test_the_coming_year_is_fetched_ahead_in_autumn(tmp_path):
    store = make_store(tmp_path)
    fetcher = CountingFetcher()
    clock = FakeClock(datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc).timestamp())
    calendar = holidays.HolidayCalendar(store, fetcher=fetcher, clock=clock)
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert ("DE-NI", 2027) in fetcher.calls


def test_no_year_is_fetched_ahead_before_autumn(tmp_path):
    calendar, fetcher = make_calendar(tmp_path)[:2]
    calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert fetcher.calls == [("DE-NI", 2026)]


def test_a_prefetch_failure_does_not_poison_the_answer(tmp_path):
    store = make_store(tmp_path)

    class OnlyCurrentYear(CountingFetcher):
        def __call__(self, region, year):
            self.calls.append((region, year))
            if year != 2026:
                raise requests.ConnectionError("offline")
            return fixture_year(region, year)

    clock = FakeClock(datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc).timestamp())
    calendar = holidays.HolidayCalendar(store, fetcher=OnlyCurrentYear(), clock=clock)
    payload = calendar.range_info(date(2026, 10, 12), date(2026, 10, 18))
    assert payload["status"] == holidays.STATUS_OK
    assert payload["stale"] is False
