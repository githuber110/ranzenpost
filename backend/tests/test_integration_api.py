from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import integration, integration_api, mapping, modules
from app.integration_api import IntegrationAccess
from app.server import create_app
from app.store import Store
from app.subscriptions import SubscriptionRegistry

from tests.test_calendar_feed import FakeHolidayCalendar, _day, _lesson, _snapshot

SCHOOL = "a1b2c3d4"
SECOND_SCHOOL = "b2c3d4e5"
CHILD_ID = f"{SCHOOL}:child-uuid-a"
SECOND_CHILD_ID = f"{SCHOOL}:child-uuid-b"
OTHER_CHILD_ID = f"{SECOND_SCHOOL}:child-uuid-a"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
SECOND_CHILD_NAME = "Kraakebolle Nebelkraehe"
NOW = datetime(2026, 9, 2, 6, 10)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
WEDNESDAY = "02.09.2026"
THURSDAY = "03.09.2026"
PREFIX = "/api/integration"
CHILD_QUERY = f"child={CHILD_ID}"


class FakeConnection:
    def __init__(self, service, connection_id):
        self.id = connection_id
        self.store = service.store.connection_store(connection_id)
        self.service = service

    def is_configured(self):
        return self.service.configured

    def modules(self):
        return self.service.modules_of(self.id)

    def display_name(self):
        return self.store.display_name()


class FakeService:
    def __init__(self, store, configured=True):
        self.store = store
        self.configured = configured

    def is_configured(self):
        return self.configured

    def check_connection(self):
        return "ok"

    def connection(self, connection_id):
        return FakeConnection(self, connection_id)

    def connections(self, include_pending=False):
        return [self.connection(entry["id"]) for entry in self.store.connections()]

    def modules_of(self, connection_id):
        return self.store.connection_store(connection_id).load_modules()

    def children(self, connection_id=None):
        return [{"child_id": "child-uuid-a", "name": CHILD_NAME, "key": CHILD_ID, "connection_id": SCHOOL}]

    def summaries(self, with_status=False):
        return [
            {
                "id": entry["id"],
                "name": entry["school_url"],
                "school_url": entry["school_url"],
                "setup_complete": True,
                "username": "u",
                "children": [],
                "status": "ok",
            }
            for entry in self.store.connections()
        ]

    def health_overview(self):
        rows = self.summaries(with_status=True)
        for row in rows:
            row["stale"] = False
        return self.check_connection(), rows


def _raw(child_key):
    return child_key.split(":", 1)[-1]


def _store(tmp_path, language="de", schools=1):
    store = Store(tmp_path / "data")
    config = store.load_config()
    config["language"] = language
    store.save_config(config)
    store.add_connection(
        "https://schule.example.test/iserv",
        connection_id=SCHOOL,
        setup_complete=True,
        holiday_region="DE-NI",
        children=[
            {"child_id": _raw(CHILD_ID), "name": CHILD_NAME, "class_name": "5A"},
            {"child_id": _raw(SECOND_CHILD_ID), "name": SECOND_CHILD_NAME, "class_name": "7B"},
        ],
        subjects={"D": {"label": "Deutsch", "color": "#0e6b70"}, "MA": {"label": "Mathe", "color": "#123456"}},
        period_times={"1": "08:00", "2": "08:50", "3": "09:45", "4": "10:30"},
    )
    if schools > 1:
        store.add_connection(
            "https://school-two.example",
            connection_id=SECOND_SCHOOL,
            setup_complete=True,
            school_name="School Two",
            holiday_region="DE-BY",
            children=[{"child_id": _raw(OTHER_CHILD_ID), "name": "Zwiebelfisch Other", "class_name": "1A"}],
            subjects={"D": {"label": "German", "color": "#654321"}},
            period_times={"1": "08:00"},
        )
    return store


class Clock:
    def __init__(self, epoch=NOW_EPOCH):
        self.epoch = epoch

    def __call__(self):
        return self.epoch


def _app(tmp_path, store=None, calendar=None, clock=None, service=None, warm=None, announce=None):
    store = store or _store(tmp_path)
    access = IntegrationAccess(store, clock=clock or Clock(), announce=announce)
    app = create_app(
        service or FakeService(store),
        holiday_calendar=calendar or FakeHolidayCalendar(),
        registry=SubscriptionRegistry(store),
        integration_access=access,
        calendar_warmer=warm or (lambda child_id: None),
    )
    return TestClient(app), store, access


def _auth(store):
    return {"Authorization": f"Bearer {store.load_integration_token()}"}


INGRESS = {"X-Ingress-Path": "/api/hassio_ingress/abc"}


@pytest.fixture(autouse=True)
def _no_supervisor(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("ISERV_ADDON_VERSION", "2609.02.00")


def test_the_app_creates_the_token_on_first_start(tmp_path):
    _, store, access = _app(tmp_path)

    assert integration.is_valid_token(store.load_integration_token())
    assert access.token == store.load_integration_token()


@pytest.mark.parametrize(
    "path",
    ["/info", f"/state?{CHILD_QUERY}", f"/events?{CHILD_QUERY}&kind=lessons", f"/school?id={SCHOOL}", "/changes"],
)
def test_every_route_refuses_a_call_without_a_token(tmp_path, path):
    client, _, _ = _app(tmp_path)

    response = client.get(PREFIX + path)

    assert response.status_code == 401
    assert response.json()["message_key"] == integration_api.UNAUTHORIZED_KEY
    assert response.json()["error"] == "unauthorized"


def test_a_wrong_token_is_refused_the_same_way(tmp_path):
    client, _, _ = _app(tmp_path)

    response = client.get(PREFIX + "/info", headers={"Authorization": "Bearer " + "x" * 43})

    assert response.status_code == 401
    assert response.json()["message_key"] == integration_api.UNAUTHORIZED_KEY


def test_a_malformed_authorization_header_is_refused(tmp_path):
    client, store, _ = _app(tmp_path)

    response = client.get(PREFIX + "/info", headers={"Authorization": store.load_integration_token()})

    assert response.status_code == 401


def test_the_stored_token_opens_every_route(tmp_path):
    client, store, _ = _app(tmp_path)
    for path in (
        "/info",
        f"/state?{CHILD_QUERY}",
        f"/events?{CHILD_QUERY}&kind=lessons",
        f"/school?id={SCHOOL}",
        "/changes",
    ):
        assert client.get(PREFIX + path, headers=_auth(store)).status_code == 200, path


def test_the_comparison_runs_in_constant_time_even_without_a_header(tmp_path, monkeypatch):
    seen = []
    original = integration_api.compare_digest

    def spy(left, right):
        seen.append((len(left), len(right)))
        return original(left, right)

    monkeypatch.setattr(integration_api, "compare_digest", spy)
    client, store, _ = _app(tmp_path)

    client.get(PREFIX + "/info")
    client.get(PREFIX + "/info", headers={"Authorization": "Bearer short"})

    token_length = len(store.load_integration_token())
    assert len(seen) == 2
    assert all(right == token_length for _, right in seen)


def test_an_ingress_session_may_not_use_the_integration_routes(tmp_path):
    client, store, _ = _app(tmp_path)
    headers = dict(_auth(store))
    headers["X-Ingress-Path"] = "/api/hassio_ingress/abc"

    response = client.get(PREFIX + "/info", headers=headers)

    assert response.status_code == 403
    assert response.json()["message_key"] == integration_api.INGRESS_REFUSED_KEY


def test_ten_failed_attempts_a_minute_are_the_limit_per_source(tmp_path):
    clock = Clock()
    client, store, _ = _app(tmp_path, clock=clock)
    bad = {"Authorization": "Bearer " + "y" * 43}

    for _ in range(integration_api.FAILED_ATTEMPT_LIMIT):
        assert client.get(PREFIX + "/info", headers=bad).status_code == 401

    blocked = client.get(PREFIX + "/info", headers=bad)
    assert blocked.status_code == 429
    assert blocked.json()["message_key"] == integration_api.TOO_MANY_ATTEMPTS_KEY
    assert client.get(PREFIX + "/info", headers=_auth(store)).status_code == 429

    clock.epoch += integration_api.FAILED_ATTEMPT_WINDOW_SECONDS + 1
    assert client.get(PREFIX + "/info", headers=_auth(store)).status_code == 200


def test_successful_calls_never_count_against_the_limit(tmp_path):
    client, store, _ = _app(tmp_path)

    for _ in range(3 * integration_api.FAILED_ATTEMPT_LIMIT):
        assert client.get(PREFIX + "/info", headers=_auth(store)).status_code == 200


def test_info_describes_the_add_on_the_schools_and_the_children(tmp_path):
    client, store, _ = _app(tmp_path)
    integration.record_poll(store, NOW_EPOCH - 120, True)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH - 120, True, school_name="Testschule")

    body = client.get(PREFIX + "/info", headers=_auth(store)).json()

    assert body["version"] == "2609.02.00"
    assert set(body) == {"version", "schools", "language", "timezone", "feed_port_open", "last_poll", "ingress_path"}
    assert set(body["schools"][0]) == {
        "id", "name", "url_host", "modules", "disabled", "status", "status_reason", "children", "last_poll", "last_success", "own_entries"
    }
    assert body["schools"][0]["own_entries"] is False
    assert body["ingress_path"] == ""
    assert body["schools"][0]["disabled"] == {name: False for name in modules.MODULES}
    assert len(body["schools"]) == 1
    school = body["schools"][0]
    assert school["id"] == SCHOOL
    assert school["name"] == "Testschule"
    assert school["url_host"] == "schule.example.test"
    assert school["status"] == "ok"
    assert school["status_reason"] == ""
    assert school["children"] == [
        {"key": CHILD_ID, "name": CHILD_NAME, "class_name": "5A"},
        {"key": SECOND_CHILD_ID, "name": SECOND_CHILD_NAME, "class_name": "7B"},
    ]
    assert body["language"] == "de"
    assert body["timezone"] == "Europe/Berlin"
    assert body["feed_port_open"] is False
    assert body["last_poll"] == "2026-09-02T08:08:00+02:00"


def test_info_lists_two_schools_with_their_own_children_and_names(tmp_path):
    store = _store(tmp_path, schools=2)
    client, _, _ = _app(tmp_path, store=store)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, school_name="School One")
    integration.record_school_poll(store, SECOND_SCHOOL, NOW_EPOCH, False, integration.ERROR_NETWORK)

    schools = client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"]

    assert [school["id"] for school in schools] == [SCHOOL, SECOND_SCHOOL]
    assert [school["name"] for school in schools] == ["School One", "School Two"]
    assert [school["status"] for school in schools] == ["ok", "error"]
    assert [child["key"] for child in schools[1]["children"]] == [OTHER_CHILD_ID]
    assert schools[1]["url_host"] == "school-two.example"


def test_info_prefers_the_label_over_the_school_name(tmp_path):
    store = _store(tmp_path)
    store.update_connection(SCHOOL, label="Village school", school_name="Long official name")
    client, _, _ = _app(tmp_path, store=store)

    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["name"] == "Village school"


def test_info_leaves_out_a_school_whose_setup_is_not_finished(tmp_path):
    store = _store(tmp_path, schools=2)
    store.update_connection(SECOND_SCHOOL, setup_complete=False)
    client, _, _ = _app(tmp_path, store=store)

    assert [school["id"] for school in client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"]] == [SCHOOL]


def test_info_status_follows_the_configuration_and_the_last_poll(tmp_path):
    store = _store(tmp_path)
    client, _, _ = _app(tmp_path, store=store, service=FakeService(store, configured=False))
    body = client.get(PREFIX + "/info", headers=_auth(store)).json()
    assert body["schools"][0]["status"] == "unconfigured"
    assert body["last_poll"] is None

    client, store, _ = _app(tmp_path, store=store)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, False, integration.ERROR_AUTH)
    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["status"] == "auth_failed"


def test_info_tells_an_auth_failure_apart_from_a_network_error(tmp_path):
    store = _store(tmp_path)
    client, store, _ = _app(tmp_path, store=store)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, False, integration.ERROR_NETWORK)
    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["status"] == "error"

    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, False, integration.ERROR_AUTH)
    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["status"] == "auth_failed"


def test_info_falls_back_to_the_host_until_the_school_name_becomes_known(tmp_path):
    store = _store(tmp_path)
    client, store, _ = _app(tmp_path, store=store)
    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["name"] == "schule.example.test"

    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, school_name="Testschule")
    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"][0]["name"] == "Testschule"


def test_info_reads_the_language_the_way_the_feed_does(tmp_path):
    client, store, _ = _app(tmp_path, store=_store(tmp_path, language="system"))

    assert client.get(PREFIX + "/info", headers=_auth(store)).json()["language"] == "de"


def _today_snapshot(store):
    lessons = [
        _lesson(day=WEDNESDAY, period=1, subject_code="D", subject_label="Deutsch", teacher_surname="Behrens"),
        _lesson(day=WEDNESDAY, period=3, subject_code="MA", subject_label="Mathe", teacher_code="OTT", teacher_label="Otte", room="R2"),
        _lesson(
            day=WEDNESDAY,
            period=4,
            subject_code="SP",
            subject_label="Sport",
            teacher_code="KLE",
            teacher_label="Klein",
            room="GYM",
            change_kind="cancelled",
        ),
        _lesson(
            day=WEDNESDAY,
            period=2,
            subject_code="EN",
            subject_label="Englisch",
            teacher_code="NEU",
            teacher_label="Neu",
            room="R7",
            change_kind="changed",
            changed_fields=["room"],
            previous={"subject": "", "teacher": "", "room": "R1"},
        ),
        _lesson(day=THURSDAY, period=2, subject_code="D", subject_label="Deutsch"),
    ]
    snapshot = _snapshot(lessons)
    snapshot["children"][CHILD_ID]["absences"] = [
        {"id": 5, "kind": "leave", "status": "open", "from_date": "2026-09-10", "till_date": "2026-09-10", "label_key": "absence.kind.leave", "subject": "Zahnarzt"},
        {"id": 6, "kind": "sick", "status": "", "from_date": "2026-09-01", "till_date": "2026-09-01"},
        {"id": 7, "kind": "leave", "status": "rejected", "from_date": "2026-09-12", "till_date": "2026-09-12"},
    ]
    store.save_calendar_snapshot(snapshot)
    store.update_connection(SCHOOL, poll_state={CHILD_ID: {"last_updated": "02.09.2026 06:00"}})
    integration.record_poll(store, NOW_EPOCH - 60, True)
    integration.record_school_poll(
        store, SCHOOL, NOW_EPOCH - 60, True, letters=["Wandertag", "Elternabend"], posts=["Mensa"]
    )


def test_state_reads_the_day_from_the_snapshot(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"]["subject"] == "Deutsch"
    assert body["now_lesson"]["subject_code"] == "D"
    assert body["now_lesson"]["teacher"] == "Behrens"
    assert body["now_lesson"]["room"] == "R1"
    assert body["now_lesson"]["start"] == "2026-09-02T08:00:00+02:00"
    assert body["now_lesson"]["end"] == "2026-09-02T08:45:00+02:00"
    assert body["now_lesson"]["substitution"] is False
    assert body["now_lesson"]["cancelled"] is False
    assert body["now_lesson"]["note"] == ""
    assert body["next_lesson"]["subject"] == "Englisch"
    assert body["next_lesson"]["substitution"] is True
    assert body["next_lesson"]["room"] == "R7"
    assert "R1" in body["next_lesson"]["note"] and "R7" in body["next_lesson"]["note"]
    assert body["school_end_today"] == "2026-09-02T10:30:00+02:00"
    assert body["next_school_day"]["start"] == "2026-09-03T08:50:00+02:00"
    assert [entry["subject"] for entry in body["changes_today"]] == ["Englisch", "Sport"]
    assert body["changes_today"][1]["cancelled"] is True
    assert [item["title"] for item in body["unread_letters"]["items"]] == ["Wandertag", "Elternabend"]
    assert body["unread_letters"]["count"] == 2
    assert body["unread_posts"]["count"] == 1
    assert body["open_absences"]["count"] == 1
    assert body["open_absences"]["items"][0]["start"] == "2026-09-10"
    assert body["open_absences"]["items"][0]["status"] == "open"
    assert body["next_absence"]["start"] == "2026-09-10"
    assert body["next_absence"]["end"] == "2026-09-10"
    assert body["next_absence"]["kind"] == "leave"
    assert body["next_absence"]["status"] == "open"
    assert body["next_absence"]["days_until"] == 8
    assert body["school_day_today"] is True
    assert body["timetable_changed_today"] is True
    assert body["timetable_last_updated"] == "2026-09-02T06:00:00+02:00"


def test_next_absence_picks_the_earliest_open_one(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    snapshot = store.load_calendar_snapshot()
    snapshot["children"][CHILD_ID]["absences"].append(
        {"id": 8, "kind": "appointment", "status": "open", "from_date": "2026-09-05", "till_date": "2026-09-05"}
    )
    store.save_calendar_snapshot(snapshot)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["open_absences"]["count"] == 2
    assert body["next_absence"]["start"] == "2026-09-05"
    assert body["next_absence"]["kind"] == "appointment"
    assert body["next_absence"]["days_until"] == 3


def test_next_absence_skips_a_past_open_absence(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    snapshot = store.load_calendar_snapshot()
    snapshot["children"][CHILD_ID]["absences"].append(
        {"id": 9, "kind": "sick", "status": "open", "from_date": "2026-08-10", "till_date": "2026-08-11"}
    )
    store.save_calendar_snapshot(snapshot)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["open_absences"]["count"] == 2
    assert body["open_absences"]["items"][0]["days_until"] == -23
    assert body["next_absence"]["start"] == "2026-09-10"
    assert body["next_absence"]["days_until"] == 8


def test_next_absence_counts_an_ongoing_absence_as_today(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    snapshot = store.load_calendar_snapshot()
    snapshot["children"][CHILD_ID]["absences"].append(
        {"id": 9, "kind": "sick", "status": "open", "from_date": "2026-09-01", "till_date": "2026-09-04"}
    )
    store.save_calendar_snapshot(snapshot)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["open_absences"]["items"][0]["days_until"] == -1
    assert body["next_absence"]["start"] == "2026-09-01"
    assert body["next_absence"]["end"] == "2026-09-04"
    assert body["next_absence"]["days_until"] == 0


def test_next_absence_is_none_when_every_open_absence_is_over(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    snapshot = store.load_calendar_snapshot()
    snapshot["children"][CHILD_ID]["absences"] = [
        {"id": 9, "kind": "sick", "status": "open", "from_date": "2026-08-10", "till_date": "2026-09-01"}
    ]
    store.save_calendar_snapshot(snapshot)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["open_absences"]["count"] == 1
    assert body["next_absence"] is None


def test_a_cancelled_lesson_never_becomes_the_current_or_next_lesson(tmp_path):
    client, store, _ = _app(tmp_path, clock=Clock(NOW_EPOCH + 105 * 60))
    _today_snapshot(store)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"]["subject"] == "Mathe"
    assert body["next_lesson"]["subject"] == "Deutsch"
    assert body["next_lesson"]["start"] == "2026-09-03T08:50:00+02:00"


def test_an_own_marker_counts_as_cancelled_in_the_state(tmp_path):
    from app.cancellations import CancellationRegistry

    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    CancellationRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-02", 1)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"] is None
    assert body["changes_today"][0]["subject"] == "Deutsch"
    assert body["changes_today"][0]["cancelled"] is True


def test_a_holiday_makes_no_school_day(tmp_path):
    calendar = FakeHolidayCalendar(days={"2026-09-02": _day(free=True, overrides=True, kind="school", name="Herbstferien")})
    client, store, _ = _app(tmp_path, calendar=calendar)
    _today_snapshot(store)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["school_day_today"] is False
    assert body["now_lesson"] is None
    assert body["school_end_today"] is None
    assert body["changes_today"] == []


def test_an_empty_snapshot_gives_an_honest_empty_state_and_warms_the_child(tmp_path):
    warmed = []
    client, store, _ = _app(tmp_path, warm=warmed.append)

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store))

    assert body["now_lesson"] is None
    assert body["next_lesson"] is None
    assert body["school_end_today"] is None
    assert body["next_school_day"] is None
    assert body["next_exam"] is None
    assert body["exams_upcoming"] == {"count": 0, "items": [], "days": integration.EXAM_DAYS_AHEAD}
    assert body["changes_today"] == []
    assert body["school_day_today"] is False
    assert body["timetable_changed_today"] is False
    assert body["timetable_last_updated"] is None
    assert body["unread_letters"] == {"count": 0, "items": []}
    assert body["open_absences"] == {"count": 0, "items": []}
    assert body["next_absence"] is None
    assert warmed == [CHILD_ID]


def test_state_for_an_unknown_child_is_refused(tmp_path):
    client, store, _ = _app(tmp_path)

    response = client.get(PREFIX + "/state?child=somebody-else", headers=_auth(store))

    assert response.status_code == 404
    assert response.json()["message_key"] == integration_api.UNKNOWN_CHILD_KEY


def test_lesson_events_carry_the_feed_texts_and_the_cancelled_flag(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    body = client.get(
        PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-02&end=2026-09-02",
        headers=_auth(store),
    ).json()

    timed = [event for event in body if not event["all_day"]]
    assert [event["cancelled"] for event in timed] == [False, False, False, True]
    assert timed[0]["start"] == "2026-09-02T08:00:00+02:00"
    assert timed[0]["end"] == "2026-09-02T08:45:00+02:00"
    assert timed[0]["location"] == "R1"
    assert timed[0]["color"] == mapping.subject_base(store.connection(SCHOOL)["subjects"]["D"]["color"])
    assert mapping.is_hex_color(timed[0]["color"])
    assert timed[0]["uid"].endswith("@ranzenpost.local")
    assert "Deutsch" in timed[0]["summary"]
    assert "Datum" in timed[0]["description"]
    assert set(timed[0]) == {"uid", "summary", "description", "location", "start", "end", "all_day", "cancelled", "color", "subject_code", "subject", "name", "kind"}


def test_events_are_cut_to_the_requested_range(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    thursday = client.get(
        PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-03&end=2026-09-03",
        headers=_auth(store),
    ).json()

    assert [event["start"] for event in thursday if not event["all_day"]] == ["2026-09-03T08:50:00+02:00"]


def test_events_without_a_range_cover_the_feed_window(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=lessons", headers=_auth(store)).json()

    assert len([event for event in body if not event["all_day"]]) == 5


def test_exam_events_come_from_the_marks(tmp_path):
    from app.marks import MarkRegistry

    client, store, _ = _app(tmp_path)
    _today_snapshot(store)
    MarkRegistry(store, clock=lambda: NOW_EPOCH).create(CHILD_ID, "2026-09-02", 3, "MA", "Diktat")

    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=exams", headers=_auth(store)).json()

    assert len(body) == 1
    assert "Diktat" in body[0]["summary"]
    assert body[0]["start"] == "2026-09-02T09:45:00+02:00"
    assert body[0]["cancelled"] is False


def test_absence_events_list_the_settled_absences(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    body = client.get(PREFIX + f"/events?{CHILD_QUERY}&kind=absences", headers=_auth(store)).json()

    assert [event["start"] for event in body] == ["2026-09-01"]
    assert body[0]["all_day"] is True
    assert body[0]["end"] == "2026-09-02"


def test_holiday_events_need_no_child(tmp_path):
    calendar = FakeHolidayCalendar(
        days={
            "2026-10-05": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1"),
            "2026-10-06": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1"),
            "2026-10-03": _day(free=True, overrides=True, kind="public", name="Tag der Deutschen Einheit"),
        }
    )
    client, store, _ = _app(tmp_path, calendar=calendar)

    body = client.get(
        PREFIX + f"/events?kind=holidays&school={SCHOOL}&start=2026-10-01&end=2026-10-31", headers=_auth(store)
    ).json()

    assert [(event["summary"], event["start"], event["end"]) for event in body] == [
        ("Tag der Deutschen Einheit", "2026-10-03", "2026-10-04"),
        ("Herbstferien", "2026-10-05", "2026-10-07"),
    ]
    assert all(event["all_day"] for event in body)


def test_holiday_events_need_a_known_school(tmp_path):
    client, store, _ = _app(tmp_path)

    missing = client.get(PREFIX + "/events?kind=holidays", headers=_auth(store))
    unknown = client.get(PREFIX + "/events?kind=holidays&school=deadbeef", headers=_auth(store))

    assert missing.status_code == 404
    assert missing.json()["message_key"] == integration_api.UNKNOWN_SCHOOL_KEY
    assert unknown.json()["error"] == "unknown_school"


def test_holiday_events_follow_the_region_of_the_named_school(tmp_path):
    seen = []

    class RegionSpy(FakeHolidayCalendar):
        def range_info(self, start, end, config=None):
            seen.append((config or {}).get("holiday_region"))
            return super().range_info(start, end, config)

    store = _store(tmp_path, schools=2)
    client, _, _ = _app(tmp_path, store=store, calendar=RegionSpy())

    client.get(PREFIX + f"/events?kind=holidays&school={SECOND_SCHOOL}&start=2026-10-01&end=2026-10-31", headers=_auth(store))
    client.get(PREFIX + f"/events?child={OTHER_CHILD_ID}&kind=lessons", headers=_auth(store))

    assert seen == ["DE-BY", "DE-BY"]


@pytest.mark.parametrize(
    "query,key",
    [
        (f"{CHILD_QUERY}&kind=homework", integration_api.BAD_KIND_KEY),
        ("kind=lessons", integration_api.UNKNOWN_CHILD_KEY),
        ("child=nobody&kind=lessons", integration_api.UNKNOWN_CHILD_KEY),
        ("child=child-uuid-a&kind=lessons", integration_api.UNKNOWN_CHILD_KEY),
        (f"{CHILD_QUERY}&kind=lessons&start=2026-13-01", integration_api.BAD_RANGE_KEY),
        (f"{CHILD_QUERY}&kind=lessons&start=2026-09-10&end=2026-09-01", integration_api.BAD_RANGE_KEY),
        (f"{CHILD_QUERY}&kind=lessons&start=2026-01-01&end=2027-12-31", integration_api.BAD_RANGE_KEY),
    ],
)
def test_events_refuse_bad_parameters(tmp_path, query, key):
    client, store, _ = _app(tmp_path)

    response = client.get(PREFIX + "/events?" + query, headers=_auth(store))

    assert response.status_code in (400, 404)
    assert response.json()["message_key"] == key


def test_school_names_the_next_holiday_and_the_next_conference(tmp_path):
    calendar = FakeHolidayCalendar(
        days={
            "2026-10-05": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1"),
            "2026-10-06": _day(free=True, overrides=True, kind="school", name="Herbstferien", period_id="h1"),
        }
    )
    client, store, _ = _app(tmp_path, calendar=calendar)
    integration.record_school_poll(
        store,
        SCHOOL,
        NOW_EPOCH,
        True,
        conferences=[
            ["01.09.2026", "Frau Alt", "Raum 1", "Termin buchen"],
            ["15.09.2026", "Frau Muster", "Raum 101", "Termin buchen"],
            ["22.09.2026", "Herr Beispiel", "Raum 202", "Termin buchen"],
        ],
    )

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert body["next_holiday"] == {"name": "Herbstferien", "start": "2026-10-05", "end": "2026-10-06", "days_until": 33}
    assert body["next_conference"]["date"] == "2026-09-15"
    assert body["next_conference"]["title"] == "Frau Muster · Raum 101"
    assert body["region"] == "DE-NI"


def test_school_admits_when_nothing_is_ahead(tmp_path):
    client, store, _ = _app(tmp_path)

    body = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()

    assert body == {"next_holiday": None, "next_conference": None, "region": "DE-NI"}


def test_school_answers_per_school_and_refuses_an_unknown_one(tmp_path):
    store = _store(tmp_path, schools=2)
    client, _, _ = _app(tmp_path, store=store)
    integration.record_school_poll(store, SECOND_SCHOOL, NOW_EPOCH, True, conferences=[["15.09.2026", "Frau Zwei"]])

    one = client.get(PREFIX + f"/school?id={SCHOOL}", headers=_auth(store)).json()
    two = client.get(PREFIX + f"/school?id={SECOND_SCHOOL}", headers=_auth(store)).json()
    unknown = client.get(PREFIX + "/school?id=deadbeef", headers=_auth(store))
    missing = client.get(PREFIX + "/school", headers=_auth(store))

    assert one["region"] == "DE-NI" and one["next_conference"] is None
    assert two["region"] == "DE-BY" and two["next_conference"]["title"] == "Frau Zwei"
    assert unknown.status_code == 404
    assert unknown.json()["message_key"] == integration_api.UNKNOWN_SCHOOL_KEY
    assert missing.status_code == 404


def test_changes_hands_out_the_recorded_change_events(tmp_path):
    client, store, _ = _app(tmp_path)
    event = {
        "child_key": CHILD_ID,
        "school_id": SCHOOL,
        "at": "2026-09-02T08:00:00+02:00",
        "kind": "cancellation",
        "summary": "Ausfall: 1. Deutsch (Behrens)",
        "date": "2026-09-02",
        "period": 1,
        "new": True,
    }
    integration.record_poll(store, NOW_EPOCH, True, changes=[event])

    body = client.get(PREFIX + "/changes", headers=_auth(store)).json()

    assert body == [event]


def test_the_ingress_status_route_tells_whether_the_integration_is_connected(tmp_path):
    clock = Clock()
    client, store, _ = _app(tmp_path, clock=clock)

    before = client.get("/api/integration-status", headers=INGRESS).json()
    client.get(PREFIX + "/info", headers=_auth(store))
    after = client.get("/api/integration-status", headers=INGRESS).json()

    assert before["connected"] is False
    assert before["last_request"] is None
    assert before["token"] == store.load_integration_token()
    assert before["port"] == integration_api.INTEGRATION_PORT
    assert after["connected"] is True
    assert after["last_request"] == "2026-09-02T08:10:00+02:00"

    clock.epoch += integration.CONNECTED_WINDOW_SECONDS + 1
    assert client.get("/api/integration-status", headers=INGRESS).json()["connected"] is False


def test_a_failed_call_does_not_count_as_a_connection(tmp_path):
    client, _, _ = _app(tmp_path)

    client.get(PREFIX + "/info", headers={"Authorization": "Bearer " + "z" * 43})

    assert client.get("/api/integration-status", headers=INGRESS).json()["connected"] is False


def test_the_last_request_survives_a_restart(tmp_path):
    store = _store(tmp_path)
    client, _, _ = _app(tmp_path, store=store)
    client.get(PREFIX + "/info", headers=_auth(store))

    client, _, _ = _app(tmp_path, store=store)

    assert client.get("/api/integration-status", headers=INGRESS).json()["last_request"] == "2026-09-02T08:10:00+02:00"


def test_rotation_replaces_the_token_locks_out_the_old_one_and_announces_the_new_one(tmp_path):
    announced = []
    client, store, access = _app(tmp_path, announce=announced.append)
    old = store.load_integration_token()

    body = client.post("/api/integration-status/rotate", headers=INGRESS).json()

    assert body["ok"] is True
    assert body["message_key"] == integration_api.TOKEN_ROTATED_KEY
    assert body["token"] != old
    assert body["token"] == store.load_integration_token() == access.token
    assert client.get(PREFIX + "/info", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.get(PREFIX + "/info", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
    assert announced == [body["token"]]


def test_the_ingress_routes_need_no_bearer_token(tmp_path):
    client, _, _ = _app(tmp_path)

    assert client.get("/api/integration-status", headers=INGRESS).status_code == 200
    assert client.post("/api/integration-status/rotate", headers=INGRESS).status_code == 200


def test_the_status_routes_refuse_a_call_that_does_not_come_through_ingress(tmp_path):
    announced = []
    client, store, _ = _app(tmp_path, announce=announced.append)
    before = store.load_integration_token()

    status = client.get("/api/integration-status")
    rotate = client.post("/api/integration-status/rotate")

    assert status.status_code == 403
    assert status.json()["error"] == "forbidden"
    assert status.json()["message_key"] == integration_api.INGRESS_REQUIRED_KEY
    assert before not in status.text
    assert rotate.status_code == 403
    assert rotate.json()["message_key"] == integration_api.INGRESS_REQUIRED_KEY
    assert store.load_integration_token() == before
    assert announced == []


def test_a_bearer_token_does_not_open_the_status_routes_either(tmp_path):
    client, store, _ = _app(tmp_path)

    assert client.get("/api/integration-status", headers=_auth(store)).status_code == 403
    assert client.post("/api/integration-status/rotate", headers=_auth(store)).status_code == 403


def test_the_token_never_travels_through_the_plain_config_endpoint(tmp_path):
    client, store, _ = _app(tmp_path)

    assert store.load_integration_token() not in str(client.get("/api/config").json())
    assert store.load_integration_token() not in str(client.get("/api/health").json())


def test_a_second_child_sees_only_its_own_snapshot(tmp_path):
    client, store, _ = _app(tmp_path)
    _today_snapshot(store)

    body = client.get(PREFIX + f"/state?child={SECOND_CHILD_ID}", headers=_auth(store)).json()

    assert body["now_lesson"] is None
    assert body["changes_today"] == []
    assert body["unread_letters"]["count"] == 2


def test_times_switch_to_winter_offset_after_the_clock_change(tmp_path):
    winter = datetime(2026, 11, 4, 7, 10)
    client, store, _ = _app(tmp_path, clock=Clock(int(winter.replace(tzinfo=timezone.utc).timestamp())))
    store.save_calendar_snapshot(_snapshot([_lesson(day="04.11.2026", period=1)], week="02.11.2026"))

    body = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()

    assert body["now_lesson"]["start"] == "2026-11-04T08:00:00+01:00"


def test_the_feed_window_start_and_end_default_around_today(tmp_path):
    start, end = integration.default_event_range(NOW.date())

    assert start <= NOW.date() - timedelta(days=7)
    assert end >= NOW.date() + timedelta(days=21)


def test_info_carries_the_module_registry_of_each_school(tmp_path):
    store = _store(tmp_path, schools=2)
    store.connection_store(SCHOOL).save_modules({
        "modules": {"timetable": True, "letters": False, "pinboard": True, "absences": False, "conferences": True, "messenger": False},
        "unknown": [{"segment": "mail", "label": "E-Mail"}],
        "checked_at": NOW_EPOCH,
        "iserv_version": "3.9",
    })

    client, _, _ = _app(tmp_path, store=store)
    schools = client.get(PREFIX + "/info", headers=_auth(store)).json()["schools"]
    assert schools[0]["modules"] == {
        "timetable": True,
        "letters": False,
        "pinboard": True,
        "absences": False,
        "conferences": True,
        "messenger": False,
    }
    assert schools[1]["modules"] == {name: True for name in ("timetable", "letters", "pinboard", "absences", "conferences", "messenger")}
    assert "unknown" not in schools[0]


def test_info_shows_every_module_for_a_school_without_a_registry(tmp_path):
    client, store, _ = _app(tmp_path)
    body = client.get(PREFIX + "/info", headers=_auth(store)).json()
    assert body["schools"][0]["modules"] == {name: True for name in ("timetable", "letters", "pinboard", "absences", "conferences", "messenger")}


def test_state_reads_unread_counts_from_the_school_of_the_child(tmp_path):
    store = _store(tmp_path, schools=2)
    client, _, _ = _app(tmp_path, store=store)
    integration.record_school_poll(store, SCHOOL, NOW_EPOCH, True, letters=["One"], posts=[])
    integration.record_school_poll(store, SECOND_SCHOOL, NOW_EPOCH, True, letters=["Two", "Three"], posts=["Post"])

    first = client.get(PREFIX + f"/state?{CHILD_QUERY}", headers=_auth(store)).json()
    other = client.get(PREFIX + f"/state?child={OTHER_CHILD_ID}", headers=_auth(store)).json()

    assert [item["title"] for item in first["unread_letters"]["items"]] == ["One"]
    assert [item["title"] for item in other["unread_letters"]["items"]] == ["Two", "Three"]
    assert other["unread_letters"]["count"] == 2
    assert other["unread_posts"]["count"] == 1


def test_events_carry_a_derived_subject_code_when_iserv_only_delivered_a_long_name(tmp_path):
    from app.iserv.models import Lesson
    from app.mapping import merge_discovered_codes, to_display

    client, store, _ = _app(tmp_path)
    long_name_lesson = Lesson(
        date=WEDNESDAY, day_of_week=3, period=1, subject="Mathematik", teacher="BEH",
        room="R1", class_name="1a", subject_name="Mathematik",
    )
    config = merge_discovered_codes(store.connection(SCHOOL), [long_name_lesson])
    store.update_connection(SCHOOL, subjects=config["subjects"])
    lesson = to_display(long_name_lesson, config)
    store.save_calendar_snapshot(_snapshot([lesson]))
    store.update_connection(SCHOOL, poll_state={CHILD_ID: {"last_updated": "02.09.2026 06:00"}})
    integration.record_poll(store, NOW_EPOCH - 60, True)

    body = client.get(
        PREFIX + f"/events?{CHILD_QUERY}&kind=lessons&start=2026-09-02&end=2026-09-02",
        headers=_auth(store),
    ).json()

    timed = [event for event in body if not event["all_day"]]
    assert timed[0]["subject_code"] == "MAT"
    assert "Mathematik" in timed[0]["summary"]


def test_info_reports_the_modules_the_user_switched_off(tmp_path):
    client, store, _ = _app(tmp_path)
    config = store.load_config()
    config["modules_disabled"] = ["letters", "messenger"]
    store.save_config(config)
    body = client.get(PREFIX + "/info", headers=_auth(store)).json()
    disabled = body["schools"][0]["disabled"]
    assert disabled == {name: name in ("letters", "messenger") for name in modules.MODULES}
    assert body["schools"][0]["modules"]["letters"] is True


def test_the_ingress_path_comes_from_the_supervisor_slug(monkeypatch):
    from app import supervisor

    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"slug": "ranzenpost", "ingress": True})
    assert supervisor.ingress_path() == "/hassio/ingress/ranzenpost"
    monkeypatch.setattr(supervisor, "_addon_info", lambda: {"slug": "ranzenpost", "ingress": False})
    assert supervisor.ingress_path() == ""
    monkeypatch.setattr(supervisor, "_addon_info", lambda: None)
    assert supervisor.ingress_path() == ""
