import json
import logging

import requests
from fastapi.testclient import TestClient

from app.server import create_app
from app.service import NotConfiguredError
from app.store import Store
from tests.test_server import SCHOOL, FakeService, client


def _assert_secret_absent(caplog, secret):
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in str(record.args)
        assert secret not in (record.exc_text or "")


def test_letter_attachment_failure_is_logged_without_personal_data(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def broken(self, connection_id, attachment_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeService, "letter_attachment", broken)
    with caplog.at_level(logging.WARNING, logger="app.letter_routes"):
        response = api.get("/api/letters/attachment/abc123", params={"connection": SCHOOL})

    assert response.status_code == 400
    assert "letter attachment was refused before the request" in caplog.text
    assert "abc123" not in caplog.text


def test_letters_archive_failure_is_logged_and_falls_back(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def broken(self, connection_id, letter_id, recipient_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(FakeService, "archive_letter", broken)
    with caplog.at_level(logging.WARNING, logger="app.letter_routes"):
        response = api.post(
            "/api/letters/archive",
            json={"connection_id": SCHOOL, "letter_id": "l1", "recipient_id": "r1"},
        )

    assert response.json() == {"ok": False, "error": "archive_failed"}
    assert "letter route archive failed" in caplog.text
    assert "l1" not in caplog.text


def test_pinboard_attachment_failure_is_logged_without_personal_data(tmp_path, caplog):
    api, _ = client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.pinboard_routes"):
        response = api.get("/api/pinboard/attachment/no-extension")

    assert response.status_code == 400
    assert "pinboard attachment was refused before the request" in caplog.text
    assert "no-extension" not in caplog.text


def test_absence_attachment_failure_is_logged_without_personal_data(tmp_path, caplog):
    api, _ = client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.absence_routes"):
        response = api.get("/api/absences/attachment/no-extension")

    assert response.status_code == 400
    assert "absence attachment was refused before the request" in caplog.text
    assert "no-extension" not in caplog.text


def test_sick_note_pdf_unsupported_text_is_logged_without_personal_data(tmp_path, caplog):
    api, _ = client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.absence_routes"):
        response = api.get("/api/absences/sick-note-pdf", params={"id": "7"})

    assert response.status_code == 422
    assert "sick note pdf refused: unsupported text" in caplog.text


def test_absence_report_attachment_too_large_is_logged(tmp_path, caplog):
    service = FakeService(Store(tmp_path / "data"))
    api = TestClient(create_app(service))
    payload = {"type": "beurlaubungsantrag", "student_id": 7, "subject": "Test", "body": "Text"}
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    with caplog.at_level(logging.INFO, logger="app.absence_routes"):
        response = api.post(
            "/api/absences",
            data={"data": json.dumps(payload)},
            files=[("files", ("big.pdf", oversized, "application/pdf"))],
        )

    assert response.json()["message_key"] == "api.absence.error.attachmentTooLarge"
    assert "absence report refused: attachment too large" in caplog.text
    assert "big.pdf" not in caplog.text


def test_password_change_refusal_is_logged_without_the_password(tmp_path, caplog):
    api, _ = client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="app.account_routes"):
        response = api.post(
            "/api/password", json={"current": "wrong", "new": "planted-secret-new-pw"}
        )

    assert response.json()["error"] == "rejected"
    assert "password change was refused" in caplog.text
    _assert_secret_absent(caplog, "wrong")
    _assert_secret_absent(caplog, "planted-secret-new-pw")


def test_password_change_network_failure_is_logged_without_the_password(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def broken(self, connection_id, current, new):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(FakeService, "change_password", broken)
    with caplog.at_level(logging.WARNING, logger="app.account_routes"):
        response = api.post(
            "/api/password",
            json={"current": "planted-secret-current-pw", "new": "planted-secret-new-pw"},
        )

    assert response.json()["error"] == "network"
    assert "password change failed: ConnectionError" in caplog.text
    _assert_secret_absent(caplog, "planted-secret-current-pw")
    _assert_secret_absent(caplog, "planted-secret-new-pw")


def test_password_repair_failure_is_logged_without_the_password(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def broken(self, connection_id, password):
        raise NotConfiguredError("school url or credentials missing")

    monkeypatch.setattr(FakeService, "repair_password", broken, raising=False)
    with caplog.at_level(logging.WARNING, logger="app.account_routes"):
        response = api.post("/api/password/repair", json={"password": "planted-secret-repair-pw"})

    assert response.json()["error"] == "not_configured"
    assert "password repair failed: NotConfiguredError" in caplog.text
    _assert_secret_absent(caplog, "planted-secret-repair-pw")


def test_account_disconnect_failure_is_logged_without_the_username(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def broken(self, connection_id):
        raise NotConfiguredError("school url or credentials missing")

    monkeypatch.setattr(FakeService, "disconnect", broken, raising=False)
    with caplog.at_level(logging.WARNING, logger="app.account_routes"):
        response = api.post(
            "/api/account/disconnect", json={"connection_id": "planted-secret-username"}
        )

    assert response.json()["error"] == "not_configured"
    assert "account disconnect failed: NotConfiguredError" in caplog.text
    _assert_secret_absent(caplog, "planted-secret-username")
