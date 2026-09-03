import json
import pathlib
import sys

import pytest
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import holidays, schoolregion
from app.iserv.dsa import parse_school


def locality(state_key, state_name="Some State"):
    return {
        "postalCode": "12345",
        "name": "Some Place",
        "federalState": {"key": state_key, "name": state_name},
    }


class StubService:
    def __init__(self, profile=None, error=None):
        self.profile = profile
        self.error = error
        self.calls = 0

    def school_profile(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.profile


def suggester(profile, rows=None, error=None, clock=None):
    calls = []

    def fetcher(postal_code):
        calls.append(postal_code)
        if error is not None:
            raise error
        return rows

    made = schoolregion.RegionSuggester(StubService(profile), fetcher=fetcher, clock=clock)
    made.fetch_calls = calls
    return made


def test_every_federal_state_key_maps_to_a_region_the_holiday_calendar_accepts():
    assert sorted(schoolregion.STATE_KEY_REGIONS) == [f"{index:02d}" for index in range(1, 17)]
    regions = sorted(schoolregion.STATE_KEY_REGIONS.values())
    assert regions == sorted(holidays.REGION_CODES)
    for region in regions:
        assert holidays.clean_region(region) == region


def test_a_filled_postal_code_yields_a_high_confidence_suggestion():
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("03")])
    result = made.suggest()
    assert result == {
        "region": "DE-NI",
        "confidence": schoolregion.CONFIDENCE_HIGH,
        "origin": schoolregion.ORIGIN_ISERV_POSTAL_CODE,
        "origin_key": "holidays.suggestion.origin.iservPostalCode",
        "reason": "",
    }


def test_a_postal_code_shared_by_two_states_produces_no_suggestion():
    made = suggester(
        {"postal_code": "21039", "country": "DE"},
        rows=[locality("01"), locality("02")],
    )
    result = made.suggest()
    assert result["region"] == ""
    assert result["confidence"] == schoolregion.CONFIDENCE_NONE
    assert result["reason"] == schoolregion.REASON_AMBIGUOUS


def test_an_unknown_postal_code_produces_no_suggestion():
    made = suggester({"postal_code": "00000", "country": ""}, rows=[])
    assert made.suggest()["reason"] == schoolregion.REASON_UNKNOWN_POSTAL_CODE


def test_an_empty_iserv_postal_code_produces_no_suggestion_and_no_request():
    made = suggester({"postal_code": "", "country": "", "town": "Some Place"}, rows=[])
    result = made.suggest()
    assert result["reason"] == schoolregion.REASON_NO_POSTAL_CODE
    assert result["region"] == ""
    assert made.fetch_calls == []


@pytest.mark.parametrize("value", ["1234", "123456", "3015a", "", None, "  ", "١٢٣٤٥"])
def test_only_five_ascii_digits_count_as_a_postal_code(value):
    assert schoolregion.clean_postal_code(value) == ""


def test_surrounding_whitespace_in_the_postal_code_is_tolerated():
    assert schoolregion.clean_postal_code(" 30159 ") == "30159"


@pytest.mark.parametrize("value", ["", "DE", "de", "Deutschland", "Germany", "  DEU "])
def test_german_country_values_are_accepted(value):
    assert schoolregion.is_german_country(value) is True


@pytest.mark.parametrize("value", ["AT", "Austria", "CH", "Schweiz", "NL"])
def test_a_foreign_country_blocks_the_suggestion_before_any_request(value):
    made = suggester({"postal_code": "30159", "country": value})
    result = made.suggest()
    assert result["reason"] == schoolregion.REASON_FOREIGN_COUNTRY
    assert result["region"] == ""
    assert made.fetch_calls == []


def test_a_network_failure_produces_no_suggestion_instead_of_an_error():
    made = suggester(
        {"postal_code": "30159", "country": ""}, error=requests.RequestException("boom")
    )
    result = made.suggest()
    assert result["region"] == ""
    assert result["reason"] == schoolregion.REASON_UNAVAILABLE


def test_an_unreachable_iserv_produces_no_suggestion_instead_of_an_error():
    service = StubService(error=requests.RequestException("boom"))
    made = schoolregion.RegionSuggester(service, fetcher=lambda code: [])
    assert made.suggest()["reason"] == schoolregion.REASON_NOT_CONFIGURED


def test_a_malformed_school_profile_produces_no_suggestion():
    made = suggester("not a mapping", rows=[locality("03")])
    assert made.suggest()["reason"] == schoolregion.REASON_NO_POSTAL_CODE


def test_an_unknown_state_key_produces_no_suggestion():
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("99")])
    assert made.suggest()["reason"] == schoolregion.REASON_UNKNOWN_POSTAL_CODE


def test_rows_without_a_federal_state_produce_no_suggestion():
    made = suggester(
        {"postal_code": "30159", "country": ""},
        rows=[{"postalCode": "30159"}, {"federalState": None}, "junk"],
    )
    assert made.suggest()["reason"] == schoolregion.REASON_UNKNOWN_POSTAL_CODE


def test_a_repeated_lookup_is_served_from_the_cache():
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("03")])
    assert made.suggest()["region"] == "DE-NI"
    assert made.suggest()["region"] == "DE-NI"
    assert made.fetch_calls == ["30159"]


def test_the_cache_expires_and_the_source_is_asked_again():
    now = [0]
    made = suggester(
        {"postal_code": "30159", "country": ""},
        rows=[locality("03")],
        clock=lambda: now[0],
    )
    assert made.suggest()["region"] == "DE-NI"
    now[0] = schoolregion.CACHE_TTL_SECONDS - 1
    assert made.suggest()["region"] == "DE-NI"
    assert made.fetch_calls == ["30159"]
    now[0] = schoolregion.CACHE_TTL_SECONDS
    assert made.suggest()["region"] == "DE-NI"
    assert made.fetch_calls == ["30159", "30159"]


def test_a_network_failure_is_never_cached():
    made = suggester(
        {"postal_code": "30159", "country": ""}, error=requests.RequestException("boom")
    )
    made.suggest()
    made.suggest()
    assert made.fetch_calls == ["30159", "30159"]


def test_only_the_postal_code_ever_leaves_the_box(monkeypatch):
    seen = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    def stub_get(url, params=None, headers=None, timeout=None):
        seen.append({"url": url, "params": dict(params or {})})
        return StubResponse()

    monkeypatch.setattr(schoolregion.requests, "get", stub_get)
    schoolregion.fetch_localities("30159")
    assert len(seen) == 1
    assert seen[0]["url"].startswith(schoolregion.SOURCE_BASE_URL)
    assert set(seen[0]["params"]) == set(schoolregion.REQUEST_PARAM_KEYS)
    assert seen[0]["params"] == {"postalCode": "30159"}


def test_no_school_field_other_than_the_postal_code_reaches_the_source(monkeypatch):
    seen = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    def stub_get(url, params=None, headers=None, timeout=None):
        seen.append(json.dumps({"url": url, "params": dict(params or {})}, ensure_ascii=False))
        return StubResponse()

    monkeypatch.setattr(schoolregion.requests, "get", stub_get)
    profile = {
        "id": 5075,
        "name": "SchoolName",
        "street": "StreetName 1",
        "postal_code": "30159",
        "town": "TownName",
        "country": "DE",
    }
    schoolregion.RegionSuggester(StubService(profile)).suggest()
    body = " ".join(seen)
    for secret in ("SchoolName", "StreetName", "TownName", "5075"):
        assert secret not in body


def test_an_unexpected_payload_shape_is_treated_like_a_network_failure(monkeypatch):
    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": True}

    monkeypatch.setattr(schoolregion.requests, "get", lambda *a, **k: StubResponse())
    made = schoolregion.RegionSuggester(StubService({"postal_code": "30159", "country": ""}))
    assert made.suggest()["reason"] == schoolregion.REASON_UNAVAILABLE


def test_the_school_endpoint_payload_is_parsed_into_the_expected_shape():
    payload = [
        {
            "id": 5075,
            "name": "SchoolName",
            "street": "StreetName 1",
            "zip": "30159",
            "town": "TownName",
            "country": "DE",
            "logo": "logo.png",
            "photo": None,
            "colorPrimary": "#123456",
            "colorAccent": None,
        }
    ]
    assert parse_school(payload) == {
        "id": 5075,
        "name": "SchoolName",
        "street": "StreetName 1",
        "postal_code": "30159",
        "town": "TownName",
        "country": "DE",
    }


def test_a_school_payload_with_empty_address_fields_is_parsed_without_inventing_values():
    payload = [{"id": 5075, "name": "SchoolName", "street": "", "zip": "", "town": "", "country": ""}]
    parsed = parse_school(payload)
    assert parsed["postal_code"] == ""
    assert parsed["town"] == ""
    assert parsed["country"] == ""


@pytest.mark.parametrize("payload", [None, [], {}, "junk", [None]])
def test_an_absent_school_payload_parses_to_an_empty_profile(payload):
    assert parse_school(payload) == {}


def test_the_suggestion_never_reports_medium_confidence():
    assert {schoolregion.CONFIDENCE_HIGH, schoolregion.CONFIDENCE_NONE} == {"high", "none"}
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("03")])
    for result in (made.suggest(), schoolregion.no_suggestion(schoolregion.REASON_AMBIGUOUS)):
        assert result["confidence"] in (schoolregion.CONFIDENCE_HIGH, schoolregion.CONFIDENCE_NONE)


def test_a_suggestion_without_a_region_is_impossible():
    for reason in (
        schoolregion.REASON_AMBIGUOUS,
        schoolregion.REASON_NO_POSTAL_CODE,
        schoolregion.REASON_UNAVAILABLE,
        schoolregion.REASON_UNKNOWN_POSTAL_CODE,
        schoolregion.REASON_FOREIGN_COUNTRY,
        schoolregion.REASON_NOT_CONFIGURED,
    ):
        result = schoolregion.no_suggestion(reason)
        assert result["region"] == ""
        assert result["confidence"] == schoolregion.CONFIDENCE_NONE
        assert result["origin"] == ""
        assert result["origin_key"] == ""


def _api(made, tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app
    from app.store import Store

    class MinimalService:
        def __init__(self, store):
            self.store = store

        def is_configured(self):
            return True

    store = Store(tmp_path)
    return TestClient(create_app(MinimalService(store), region_suggester=made)), store


def test_the_endpoint_hands_the_suggestion_to_the_ui(tmp_path):
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("03")])
    body = _api(made, tmp_path)[0].get("/api/holidays/region-suggestion").json()
    assert body["region"] == "DE-NI"
    assert body["confidence"] == "high"
    assert body["origin_key"] == "holidays.suggestion.origin.iservPostalCode"


def test_the_endpoint_answers_honestly_when_iserv_stores_no_postal_code(tmp_path):
    made = suggester({"postal_code": "", "country": ""}, rows=[])
    response = _api(made, tmp_path)[0].get("/api/holidays/region-suggestion")
    assert response.status_code == 200
    assert response.json() == {
        "region": "",
        "confidence": "none",
        "origin": "",
        "origin_key": "",
        "reason": "no_postal_code",
    }


def test_the_endpoint_never_writes_the_suggestion_into_the_configuration(tmp_path):
    made = suggester({"postal_code": "30159", "country": ""}, rows=[locality("03")])
    api, store = _api(made, tmp_path)
    assert api.get("/api/holidays/region-suggestion").json()["region"] == "DE-NI"
    assert store.load_config()["holiday_region"] == ""


def test_the_origin_key_exists_in_every_language_bundle():
    root = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "i18n"
    keys = [
        "holidays.suggestion.confirm",
        "holidays.suggestion.label",
        "holidays.suggestion.origin.iservPostalCode",
    ]
    assert set(schoolregion.ORIGIN_KEYS.values()) <= set(keys)
    for path in sorted(root.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for key in keys:
            assert bundle.get(key), f"{path.name} misses {key}"
