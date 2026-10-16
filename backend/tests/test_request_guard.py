import json

import pytest
from fastapi.testclient import TestClient

from app.integration_api import INGRESS_PROXY_ADDRESS
from app.server import create_app
from app.store import Store
from tests.test_server import FakeService

CROSS_SITE_KEY = "api.crossSite"
EVIL = "https://evil.example"


def app_for(tmp_path, ingress_only=False):
    calls = []

    def upload(self, connection_id, path, files, confirmed=False):
        calls.append((path, confirmed))
        return {"ok": True}

    service = FakeService(Store(tmp_path / "data"))
    service.file_upload = upload.__get__(service)
    return create_app(service, ingress_only=ingress_only), calls


def upload(client, headers):
    return client.post(
        "/api/files/upload",
        headers=headers,
        data={"data": json.dumps({"path": "own", "confirmed": True})},
        files={"files": ("x.txt", b"x", "text/plain")},
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": EVIL, "Sec-Fetch-Site": "cross-site"},
        {"Origin": "http://homeassistant.local:8123", "Sec-Fetch-Site": "same-site"},
        {"Origin": EVIL},
    ],
)
def test_a_write_from_another_site_is_refused_before_it_reaches_the_service(tmp_path, headers):
    app, calls = app_for(tmp_path)
    answer = upload(TestClient(app), headers)
    assert answer.status_code == 403
    assert answer.json()["message_key"] == CROSS_SITE_KEY
    assert calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Ranzenpost-App": "1"},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "none"},
        {},
    ],
)
def test_the_app_and_clients_without_a_browser_still_write(tmp_path, headers):
    app, calls = app_for(tmp_path)
    answer = upload(TestClient(app), headers)
    assert answer.status_code == 200
    assert calls == [("own", True)]


def test_every_write_method_is_guarded_and_reads_are_not(tmp_path):
    app, _calls = app_for(tmp_path)
    client = TestClient(app)
    cross = {"Origin": EVIL, "Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/config", json={}, headers=cross).status_code == 403
    assert client.delete("/api/marks/m1", headers=cross).status_code == 403
    assert client.post("/api/mail/spam", json={"folder": "INBOX", "uids": ["7"], "confirmed": True}, headers=cross).status_code == 403
    assert client.get("/api/timetable-availability", headers=cross).status_code == 200


def test_the_integration_routes_keep_their_own_token_check(tmp_path):
    app, _calls = app_for(tmp_path)
    answer = TestClient(app).post("/api/integration/feeds", json={}, headers={"Origin": EVIL, "Sec-Fetch-Site": "cross-site"})
    assert answer.json().get("message_key") != CROSS_SITE_KEY


def test_ingress_mode_lets_the_app_write_and_refuses_another_site(tmp_path):
    app, calls = app_for(tmp_path, ingress_only=True)
    proxied = TestClient(app, client=(INGRESS_PROXY_ADDRESS, 50000))
    ingress = {"X-Ingress-Path": "/api/hassio_ingress/abc", "Origin": "https://ha.example", "Sec-Fetch-Site": "same-origin", "X-Ranzenpost-App": "1"}
    assert upload(proxied, ingress).status_code == 200
    assert calls == [("own", True)]
    refused = upload(proxied, {"X-Ingress-Path": "/api/hassio_ingress/abc", "Origin": EVIL, "Sec-Fetch-Site": "cross-site"})
    assert refused.status_code == 403
    assert refused.json()["message_key"] == CROSS_SITE_KEY
    assert len(calls) == 1
