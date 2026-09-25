import json
import logging

import pytest
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


PLANTED_HOST = "planted-school.example"
PLANTED_LETTER = "30000000-0000-4000-8000-000000000009"
PLANTED_RECIPIENT = "40000000-0000-4000-8000-000000000009"


def _planted_connection_error(*args, **kwargs):
    raise requests.ConnectionError(
        f"HTTPSConnectionPool(host='{PLANTED_HOST}', port=443): Max retries exceeded with url: "
        f"/iserv/parentletter/parent/show/{PLANTED_LETTER}/{PLANTED_RECIPIENT}"
    )


def _assert_no_letter_or_school(caplog):
    for secret in (PLANTED_HOST, PLANTED_LETTER, PLANTED_RECIPIENT):
        _assert_secret_absent(caplog, secret)


LETTER_WRITE_ROUTES = {
    "archive": ("archive_letter", {}),
    "confirm": ("confirm_letter", {"text": "Danke"}),
    "reply": ("reply_to_letter", {"text": "Danke", "request_id": "0123456789abcdef", "confirmed": True}),
}


@pytest.mark.parametrize("label", sorted(LETTER_WRITE_ROUTES))
def test_a_failed_letter_write_logs_the_cause_without_ids_or_school(tmp_path, monkeypatch, caplog, label):
    api, _ = client(tmp_path)
    method, extra = LETTER_WRITE_ROUTES[label]
    monkeypatch.setattr(FakeService, method, _planted_connection_error)
    body = {"connection_id": SCHOOL, "letter_id": PLANTED_LETTER, "recipient_id": PLANTED_RECIPIENT, **extra}
    with caplog.at_level(logging.WARNING, logger="app.letter_routes"):
        response = api.post(f"/api/letters/{label}", json=body)

    assert response.json()["error"] == "network"
    assert f"letter route {label} failed: ConnectionError at " in caplog.text
    _assert_no_letter_or_school(caplog)


def test_a_failed_letter_attachment_logs_the_cause_without_the_school(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)
    monkeypatch.setattr(FakeService, "letter_attachment", _planted_connection_error)
    with caplog.at_level(logging.WARNING, logger="app.letter_routes"):
        response = api.get(f"/api/letters/attachment/{PLANTED_LETTER}", params={"connection": SCHOOL})

    assert response.status_code == 502
    assert "letter attachment could not be fetched: ConnectionError at " in caplog.text
    _assert_no_letter_or_school(caplog)


@pytest.mark.parametrize(
    "method, url",
    [
        ("absence_attachment", f"/api/absences/attachment/{PLANTED_LETTER}.pdf"),
        ("sick_note_pdf", f"/api/absences/sick-note-pdf?id={PLANTED_LETTER}"),
    ],
)
def test_a_failed_absence_download_logs_the_cause_without_the_school(tmp_path, monkeypatch, caplog, method, url):
    api, _ = client(tmp_path)
    monkeypatch.setattr(FakeService, method, _planted_connection_error)
    with caplog.at_level(logging.WARNING, logger="app.absence_routes"):
        response = api.get(url)

    assert response.status_code == 502
    assert "could not be fetched: ConnectionError at " in caplog.text
    _assert_no_letter_or_school(caplog)


FOREIGN_FAILURE_ROUTES = [
    ("messenger_room_messages", "get", "/api/messenger/room?id=room-1", "app.messenger_routes", "messenger route room failed: ConnectionError at "),
    ("messenger_media", "get", f"/api/messenger/media/{PLANTED_HOST}/media-1", "app.messenger_routes", "messenger media could not be fetched: ConnectionError at "),
    ("pinboard_attachment", "get", "/api/pinboard/attachment/abcdef01-42.pdf", "app.pinboard_routes", "pinboard attachment could not be fetched: ConnectionError at "),
]


@pytest.mark.parametrize("method, verb, url, logger_name, expected", FOREIGN_FAILURE_ROUTES)
def test_messenger_and_pinboard_failures_log_the_cause_without_the_school(
    tmp_path, monkeypatch, caplog, method, verb, url, logger_name, expected
):
    api, _ = client(tmp_path)
    monkeypatch.setattr(FakeService, method, _planted_connection_error, raising=False)
    with caplog.at_level(logging.WARNING, logger=logger_name):
        getattr(api, verb)(url)

    assert expected in caplog.text
    _assert_no_letter_or_school(caplog)


def test_a_refused_messenger_media_request_logs_the_cause_without_the_school(tmp_path, monkeypatch, caplog):
    api, _ = client(tmp_path)

    def refused(*args, **kwargs):
        raise ValueError(f"media host {PLANTED_HOST} is not allowed")

    monkeypatch.setattr(FakeService, "messenger_media", refused, raising=False)
    with caplog.at_level(logging.WARNING, logger="app.messenger_routes"):
        response = api.get("/api/messenger/media/elsewhere.example/media-1")

    assert response.status_code == 400
    assert "messenger media was refused before the request: ValueError at " in caplog.text
    _assert_no_letter_or_school(caplog)


def test_the_logged_cause_names_the_failing_app_line_but_no_message():
    from app.letter_service import _clean_id
    from app.failure import failure_cause

    try:
        _clean_id(f"{PLANTED_HOST}/{PLANTED_LETTER}")
    except Exception as error:
        cause = failure_cause(error)
    assert cause.startswith("DataError at letter_service.py:")
    assert PLANTED_HOST not in cause
    assert "identifier" not in cause
    try:
        _planted_connection_error()
    except requests.ConnectionError as error:
        assert failure_cause(error) == "ConnectionError"


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
