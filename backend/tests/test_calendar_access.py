import re
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import calendar_server, feed
from app.calendar_server import RateLimiter, create_calendar_app
from app.store import Store
from app.subscriptions import SubscriptionRegistry

ADDON = Path(__file__).resolve().parents[2] / "iserv_connector"
LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
CHILD_ID = "child-uuid-a"
SECOND_CHILD_ID = "child-uuid-b"
CHILD_NAME = "Zwiebelfisch Quastenflosser"


class StubHolidays:
    def range_info(self, start, end, config=None):
        days = {}
        day = start
        while day <= end:
            days[day.isoformat()] = {
                "free": False,
                "overrides_lessons": False,
                "weekend": False,
                "kind": "",
                "type": "",
                "name": "",
                "name_key": "",
                "period_id": "",
            }
            day += timedelta(days=1)
        return {"status": "ok", "stale": False, "days": days, "periods": []}


def _store(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["holiday_region"] = "DE-NI"
    config["children"] = [
        {"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"},
        {"child_id": SECOND_CHILD_ID, "name": "Kraakebolle", "class_name": "7B"},
    ]
    store.save_config(config)
    return store


def _client(tmp_path, limiter=None):
    store = _store(tmp_path)
    registry = SubscriptionRegistry(store)
    app = create_calendar_app(store, registry, holiday_calendar=StubHolidays(), limiter=limiter)
    return TestClient(app, raise_server_exceptions=False), store, registry


def test_a_valid_token_serves_the_feed(tmp_path):
    client, store, registry = _client(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    response = client.get(created["path"])

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.headers["cache-control"] == "private, max-age=600, must-revalidate"
    assert response.text.startswith("BEGIN:VCALENDAR")


def test_the_address_never_carries_the_child_name(tmp_path):
    client, store, registry = _client(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    for part in CHILD_NAME.split():
        assert part.casefold() not in created["path"].casefold()
    assert CHILD_ID not in created["path"]
    assert len(created["token"]) >= 40


def test_an_unknown_token_answers_exactly_like_a_wrong_one(tmp_path):
    client, store, registry = _client(tmp_path)
    registry.create(CHILD_ID, ["timetable"], "5A")

    unknown = client.get("/calendar/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.ics")
    short = client.get("/calendar/x.ics")

    assert unknown.status_code == short.status_code == 404
    assert unknown.text == short.text == "not found"
    assert "www-authenticate" not in unknown.headers


def test_a_missing_token_is_a_plain_404(tmp_path):
    client, _, _ = _client(tmp_path)

    response = client.get("/calendar/.ics")

    assert response.status_code == 404
    assert response.text == "not found"


def test_a_revoked_token_stops_working(tmp_path):
    client, store, registry = _client(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")
    assert client.get(created["path"]).status_code == 200

    registry.revoke(created["id"])

    assert client.get(created["path"]).status_code == 404


def test_rotating_kills_the_old_address_and_mints_a_new_one(tmp_path):
    client, store, registry = _client(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    rotated = registry.rotate(created["id"])

    assert rotated["token"] != created["token"]
    assert client.get(created["path"]).status_code == 404
    assert client.get(rotated["path"]).status_code == 200


def test_one_childs_token_never_serves_the_other_childs_lessons(tmp_path):
    client, store, registry = _client(tmp_path)
    store.save_calendar_snapshot(
        {
            "children": {
                CHILD_ID: {
                    "weeks": {
                        "31.08.2026": {
                            "start_date": "31.08.2026",
                            "end_date": "06.09.2026",
                            "lessons": [],
                        }
                    },
                    "last_success": 0,
                }
            }
        }
    )
    first = registry.create(CHILD_ID, ["timetable"], "5A")
    second = registry.create(SECOND_CHILD_ID, ["timetable"], "7B")

    assert feed.child_tag(CHILD_ID) not in client.get(second["path"]).text
    assert client.get(first["path"]).text != client.get(second["path"]).text


def test_the_calendar_listener_has_no_way_into_the_app_api(tmp_path):
    client, store, registry = _client(tmp_path)

    for path in ("/api/config", "/api/absences", "/api/calendar/subscriptions", "/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.text == "not found", path
    assert client.post("/api/absences", json={}).status_code == 404


def test_the_calendar_listener_is_built_without_a_service_object():
    from inspect import signature

    parameters = signature(create_calendar_app).parameters
    assert "service" not in parameters
    assert list(parameters)[:2] == ["store", "registry"]


def test_a_repeat_request_revalidates_cheaply(tmp_path):
    client, store, registry = _client(tmp_path)
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    first = client.get(created["path"])
    again = client.get(created["path"], headers={"If-None-Match": first.headers["etag"]})

    assert first.headers["etag"]
    assert again.status_code == 304
    assert again.text == ""


def test_the_rate_limit_closes_the_door(tmp_path):
    client, store, registry = _client(tmp_path, limiter=RateLimiter(limit=3, window=300))
    created = registry.create(CHILD_ID, ["timetable"], "5A")

    codes = [client.get(created["path"]).status_code for _ in range(5)]

    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429]


def test_the_rate_limit_forgets_old_hits():
    clock = {"now": 0.0}
    limiter = RateLimiter(limit=2, window=10, clock=lambda: clock["now"])

    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]
    clock["now"] = 11.0
    assert limiter.allow("a") is True


def test_a_full_token_never_lands_in_the_log(tmp_path, caplog):
    client, store, registry = _client(tmp_path)
    caplog.set_level("INFO", logger=calendar_server.logger.name)

    client.get("/calendar/abcdefghijklmnopqrstuvwxyz012345.ics")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "abcdef" in logged
    assert "abcdefghijklmnopqrstuvwxyz012345" not in logged


def test_the_app_port_is_never_published(tmp_path):
    text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    ports = text.split("ports:", 1)[1].split("options:", 1)[0]

    assert "ingress_port: 8099" in text
    assert "8099" not in ports


def test_the_calendar_port_is_declared_but_switched_off(tmp_path):
    text = (ADDON / "config.yaml").read_text(encoding="utf-8")
    ports = text.split("ports:", 1)[1].split("options:", 1)[0]

    assert re.search(r"8100/tcp:\s*null", ports)


def test_the_port_hint_is_translated_into_every_language():
    for language in LANGUAGES:
        path = ADDON / "translations" / f"{language}.yaml"
        assert path.is_file(), language
        text = path.read_text(encoding="utf-8")
        assert "network:" in text
        assert "8100/tcp" in text


def test_the_calendar_listener_runs_on_its_own_port():
    from app.calendar_listener import DEFAULT_PORT

    run_sh = (ADDON / "run.sh").read_text(encoding="utf-8")

    assert DEFAULT_PORT == 8100
    assert "--port 8099" in run_sh
    assert "ISERV_CALENDAR_PORT" in run_sh
