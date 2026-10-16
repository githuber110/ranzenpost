import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import account_routes, signin_pause
from app.iserv.client import IServClient
from app.iserv.errors import OutageError, PasswordUnclearError
from tests.test_client import BASE, SecuritySession
from tests.test_service import FakeClient, make


class LostAnswerClient(FakeClient):
    accepts = True
    refusal = ""

    def __init__(self, url):
        super().__init__(url)
        self.probes = []

    def change_password(self, current, new):
        raise PasswordUnclearError("the password change answer was lost")

    def accepts_password(self, password):
        self.probes.append(password)
        return self.accepts


def lost_answer(tmp_path, accepts, refusal=""):
    service, store = make(tmp_path)
    clients = []

    def factory(url):
        client = LostAnswerClient(url)
        client.accepts = accepts
        client.refusal = refusal
        clients.append(client)
        return client

    service.client_factory = factory
    return service, store, clients


def probes(clients):
    return [password for client in clients for password in client.probes]


def test_a_lost_answer_is_checked_with_the_new_password_and_stored_when_it_signs_in(tmp_path):
    service, store, clients = lost_answer(tmp_path, True)
    assert service.change_password("old-pass", "new-pass-123") is True
    assert store.load_secrets()["password"] == "new-pass-123"
    assert probes(clients) == ["new-pass-123"]


def test_a_lost_answer_whose_new_password_does_not_sign_in_keeps_the_old_one_and_never_tries_the_old(tmp_path):
    service, store, clients = lost_answer(tmp_path, False)
    old = store.load_secrets()["password"]
    assert service.change_password("old-pass", "new-pass-123") == "not_arrived"
    assert store.load_secrets()["password"] == old
    assert probes(clients) == ["new-pass-123"]


def test_a_lost_answer_without_a_check_answer_is_unclear_and_keeps_the_stored_password(tmp_path):
    service, store, clients = lost_answer(tmp_path, None)
    old = store.load_secrets()["password"]
    assert service.change_password("old-pass", "new-pass-123") == "unclear"
    assert store.load_secrets()["password"] == old


def test_the_check_after_a_lost_answer_counts_in_the_sign_in_pause_and_stops_there(tmp_path):
    service, store, clients = lost_answer(tmp_path, False)
    for _ in range(signin_pause.MAX_ATTEMPTS):
        service.change_password("old-pass", "new-pass-123")
    tried = len(probes(clients))
    assert tried == signin_pause.MAX_ATTEMPTS
    assert service.change_password("old-pass", "new-pass-123") == "unclear"
    assert len(probes(clients)) == tried


def test_a_timed_out_password_post_is_reported_as_a_lost_answer():
    session = SecuritySession("security_password.html", "security_password_ok.html")

    def post(*args, **kwargs):
        raise requests.ReadTimeout("timed out")

    session.post = post
    with pytest.raises(PasswordUnclearError):
        IServClient(BASE, session=session).change_password("old-pass", "new-pass-123")


def test_a_password_post_that_never_left_stays_an_outage():
    session = SecuritySession("security_password.html", "security_password_ok.html")

    def post(*args, **kwargs):
        raise requests.ConnectionError("Connection refused")

    session.post = post
    with pytest.raises(OutageError):
        IServClient(BASE, session=session).change_password("old-pass", "new-pass-123")


@pytest.mark.parametrize(
    "outcome, key",
    [("unclear", "api.password.unclear"), ("not_arrived", "api.password.notArrived")],
)
def test_the_password_route_names_an_unclear_change(outcome, key):
    class Service:
        store = None

        def change_password(self, connection_id, current, new):
            return outcome

    app = FastAPI()
    account_routes.register_routes(app, Service(), None)
    body = TestClient(app).post("/api/password", json={"current": "old-pass", "new": "new-pass-123"}).json()
    assert body["ok"] is False
    assert body["message_key"] == key
