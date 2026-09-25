import pytest
import requests
from fastapi.testclient import TestClient

from app import integration
from app.iserv.errors import LoginError, OutageError
from app.server import create_app
from app.service import IServService
from tests.support import add_school
from tests.test_connections import SCHOOL_ONE, SCHOOL_TWO, FakeClient, two_schools

NOW_EPOCH = 1_788_328_800


def _outage_client(url):
    return FakeClient(url, fail=OutageError("status:503"))


def test_an_outage_school_is_reported_as_outage_not_as_a_login_failure(tmp_path):
    service, _, _, _, _ = two_schools(tmp_path, {SCHOOL_TWO: _outage_client})
    assert [row["status"] for row in service.summaries(with_status=True)] == ["ok", "outage"]
    assert service.check_connection() == "ok"


def test_the_overall_state_is_outage_only_when_every_school_is_unreachable(tmp_path):
    service, _, _, _, _ = two_schools(tmp_path, {SCHOOL_ONE: _outage_client, SCHOOL_TWO: _outage_client})
    assert service.check_connection() == "outage"
    mixed, _, _, _, _ = two_schools(
        tmp_path / "mixed",
        {SCHOOL_ONE: _outage_client, SCHOOL_TWO: lambda url: FakeClient(url, fail=LoginError("two"))},
    )
    assert mixed.check_connection() == "network"


def test_the_stored_children_stay_available_while_every_school_is_unreachable(tmp_path):
    service, store, one, two, _ = two_schools(tmp_path, {SCHOOL_ONE: _outage_client, SCHOOL_TWO: _outage_client})
    store.update_connection(one, children=[{"child_id": "c1", "name": "Alice Example", "class_name": "3b"}])
    store.update_connection(two, children=[{"child_id": "c2", "name": "Ben Example", "class_name": "5a"}])
    listed = service.children()
    assert [child["key"] for child in listed] == [f"{one}:c1", f"{two}:c2"]
    assert all(child.get("unavailable") for child in listed)


def test_without_stored_children_an_outage_still_raises_as_before(tmp_path):
    service, _, _, _, _ = two_schools(tmp_path, {SCHOOL_ONE: _outage_client, SCHOOL_TWO: _outage_client})
    with pytest.raises(OutageError):
        service.children()


def test_a_login_failure_next_to_an_outage_is_still_raised(tmp_path):
    service, store, one, two, _ = two_schools(
        tmp_path, {SCHOOL_ONE: lambda url: FakeClient(url, fail=LoginError("one")), SCHOOL_TWO: _outage_client}
    )
    store.update_connection(one, children=[{"child_id": "c1", "name": "Alice Example"}])
    store.update_connection(two, children=[{"child_id": "c2", "name": "Ben Example"}])
    with pytest.raises(LoginError):
        service.children()


def _app(tmp_path, factories):
    service, store, one, two, _ = two_schools(tmp_path, factories)
    app = create_app(service)
    return TestClient(app), service, store, one, two


def test_health_names_the_outage_with_its_start_and_the_last_success(tmp_path):
    api, service, store, one, two = _app(tmp_path, {SCHOOL_TWO: _outage_client})
    integration.record_school_poll(store, two, NOW_EPOCH - 7200, True)
    integration.note_outage(store, two, NOW_EPOCH - 3600, "status:503", 1800)
    health = api.get("/api/health").json()
    assert health["connection"] == "ok"
    rows = {row["id"]: row for row in health["connections"]}
    assert rows[two]["status"] == "outage"
    assert rows[two]["since"] == integration.berlin_iso(NOW_EPOCH - 3600)
    assert rows[two]["last_success"] == integration.berlin_iso(NOW_EPOCH - 7200)
    assert rows[one]["status"] == "ok"
    assert rows[one]["since"] is None
    assert "message" not in rows[two]


def test_health_reports_an_outage_the_poller_has_not_seen_yet_without_a_start(tmp_path):
    api, _, _, one, two = _app(tmp_path, {SCHOOL_TWO: _outage_client})
    rows = {row["id"]: row for row in api.get("/api/health").json()["connections"]}
    assert rows[two]["status"] == "outage"
    assert rows[two]["since"] is None
    assert rows[two]["last_success"] is None


def test_a_read_during_an_outage_answers_network_never_auth_failed(tmp_path):
    api, _, _, one, two = _app(tmp_path, {SCHOOL_TWO: _outage_client})
    body = api.get("/api/letters", params={"connection": two}).json()
    assert body.get("error") in (None, "network")
    body = api.get("/api/timetable", params={"child": f"{two}:c1"}).json()
    assert body["error"] == "network"
    assert body["message_key"] == "api.outage"


def test_the_manual_retry_polls_the_school_once_and_is_rate_limited(tmp_path):
    api, service, store, one, two = _app(tmp_path, {SCHOOL_TWO: _outage_client})
    first = api.post(f"/api/connections/{two}/retry").json()
    assert first["ok"] is True
    assert first["status"] == "outage"
    assert integration.school_state(store, two).get(integration.OUTAGE_SINCE)
    second = api.post(f"/api/connections/{two}/retry").json()
    assert second["ok"] is False
    assert second["error"] == "rate_limited"
    assert api.post("/api/connections/deadbeef/retry").status_code == 404


def test_the_manual_retry_reports_a_school_that_answers_again(tmp_path):
    api, service, store, one, two = _app(tmp_path, {})
    integration.note_outage(store, two, NOW_EPOCH - 3600, "status:503", 1800)
    integration.note_outage(store, two, NOW_EPOCH - 1800, "status:503", 1800)
    result = api.post(f"/api/connections/{two}/retry").json()
    assert result["ok"] is True
    assert result["status"] == "ok"
    assert integration.OUTAGE_SINCE not in integration.school_state(store, two)


class SessionClient(FakeClient):
    def __init__(self, url, answers):
        super().__init__(url)
        self.authed = True
        self.answers = list(answers)
        self.fetched = []

    def fetch(self, path, params=None):
        self.fetched.append(path)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Answer:
    def __init__(self, status_code, text="", url="https://school-one.example/iserv/"):
        self.status_code = status_code
        self.text = text
        self.url = url


def _signed_in(tmp_path, answers):
    service, store, one, two, clients = two_schools(tmp_path, {SCHOOL_ONE: lambda url: SessionClient(url, answers)})
    connection = service.connection(one)
    connection._sign_in._client = service.client_factory(SCHOOL_ONE)
    return service, store, one, connection


def test_a_signed_in_session_reports_the_outage_the_poller_noted_while_the_school_still_answers_with_an_error(tmp_path):
    service, store, one, connection = _signed_in(tmp_path, [Answer(503), OutageError("timeout")])
    integration.note_outage(store, one, NOW_EPOCH, "status:503", 1800)
    assert connection.check_connection() == "outage"
    assert connection.check_connection() == "outage"
    assert connection._client.fetched == ["/iserv/", "/iserv/"]


def test_a_signed_in_session_is_ok_again_as_soon_as_the_start_page_answers(tmp_path):
    service, store, one, connection = _signed_in(tmp_path, [Answer(200, "<html><body>/iserv/</body></html>")])
    integration.note_outage(store, one, NOW_EPOCH, "status:503", 1800)
    assert connection.check_connection() == "ok"


def test_a_signed_in_session_without_a_noted_outage_is_ok_without_a_probe(tmp_path):
    service, store, one, connection = _signed_in(tmp_path, [])
    assert connection.check_connection() == "ok"
    assert connection._client.fetched == []


def test_a_retry_during_a_running_poll_waits_for_it_instead_of_polling_again(tmp_path, monkeypatch):
    import threading

    from app import connection_routes
    from app.poller import school_lock

    api, service, store, one, two = _app(tmp_path, {})
    polls = []
    real = connection_routes.make_poller

    def counting(*args, **kwargs):
        poller = real(*args, **kwargs)
        original = poller.poll_once
        poller.poll_once = lambda **options: polls.append(options) or original(**options)
        return poller

    monkeypatch.setattr(connection_routes, "make_poller", counting)
    running = school_lock(store, two)
    running.acquire()
    answers = []
    worker = threading.Thread(target=lambda: answers.append(api.post(f"/api/connections/{two}/retry").json()))
    worker.start()
    worker.join(0.3)
    running.release()
    worker.join(10)
    assert answers and answers[0]["ok"] is True
    assert polls == []
