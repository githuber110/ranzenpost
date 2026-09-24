import json
import pathlib

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ranzenpost.const import CONF_HOST, CONF_PORT, CONF_TOKEN, DOMAIN

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
HOST = "addon-host"
PORT = 8099
TOKEN = "a" * 43
NEW_TOKEN = "b" * 43
BASE_URL = f"http://{HOST}:{PORT}"
ENTRY_DATA = {CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: TOKEN}
UNIQUE_ID = f"{HOST}:{PORT}"
SCHOOL = "a1b2c3d4"
SECOND_SCHOOL = "b2c3d4e5"
CHILD_1 = f"{SCHOOL}:child-1"
CHILD_2 = f"{SCHOOL}:child-2"
FROZEN_NOW = "2026-09-02T07:15:00+00:00"
FROZEN_SATURDAY = "2026-09-05T01:50:00+00:00"
SCENARIO_SATURDAY = "saturday"


def fixture(name: str, scenario: str = ""):
    return json.loads((FIXTURES / scenario / f"{name}.json").read_text(encoding="utf-8"))


def route(path: str, base_url: str = BASE_URL, **params: str) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{base_url}/api/integration/{path}" + (f"?{query}" if query else "")


def school_of(school_id: str, name: str, url_host: str, children, modules=None, status: str = "ok") -> dict:
    return {
        "id": school_id,
        "name": name,
        "url_host": url_host,
        "modules": modules if modules is not None else fixture("info")["schools"][0]["modules"],
        "status": status,
        "children": [
            {"key": f"{school_id}:{child_id}", "name": child_name, "class_name": class_name}
            for child_id, child_name, class_name in children
        ],
    }


def info_with_schools(*schools) -> dict:
    info = fixture("info")
    info["schools"] = list(schools)
    return info


def two_schools_info() -> dict:
    return info_with_schools(
        fixture("info")["schools"][0],
        school_of(SECOND_SCHOOL, "Other School", "other.example", [("child-1", "Alex Other", "3a"), ("child-9", "Robin Other", "1c")]),
    )


def mock_addon(
    aioclient_mock: AiohttpClientMocker, info=None, changes=None, base_url: str = BASE_URL, scenario: str = ""
) -> None:
    listed = info if info is not None else fixture("info", scenario)
    aioclient_mock.get(route("info", base_url), json=listed)
    aioclient_mock.get(route("changes", base_url), json=changes if changes is not None else fixture("changes", scenario))
    for school in listed.get("schools") or []:
        aioclient_mock.get(route("school", base_url, id=school["id"]), json=fixture("school", scenario))
        aioclient_mock.get(
            route("events", base_url, kind="holidays", school=school["id"]), json=fixture("events_holidays", scenario)
        )
        for index, child in enumerate(school.get("children") or []):
            key = child["key"]
            state = fixture("state_child_1" if key == CHILD_1 else "state_child_2", scenario)
            aioclient_mock.get(route("state", base_url, child=key), json=state)
            for kind in ("lessons", "exams", "absences", "own_entries"):
                aioclient_mock.get(route("events", base_url, child=key, kind=kind), json=fixture(f"events_{kind}", scenario))


def make_entry(options=None, host: str = HOST, port: int = PORT, token: str = TOKEN) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Ranzenpost",
        unique_id=f"{host}:{port}",
        data={CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token},
        options=dict(options or {}),
        version=2,
    )


def make_legacy_entry(options=None, host: str = HOST, port: int = PORT, token: str = TOKEN) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Ranzenpost",
        unique_id=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token},
        options=dict(options or {}),
        version=1,
    )


async def setup_entry(
    hass, aioclient_mock: AiohttpClientMocker, options=None, info=None, scenario: str = ""
) -> MockConfigEntry:
    mock_addon(aioclient_mock, info=info, scenario=scenario)
    entry = make_entry(options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
