from types import SimpleNamespace

import pytest

from app.iserv.errors import DataError
from app.school_lists import read_school_file
from tests.test_letters import CONFIRM_LETTER, CONFIRM_RECIPIENT, SEEN_ATTACHMENT, letter_school
from tests.test_older_absence_form import SchoolClient, attachment_school
from tests.test_service import FileClient, _fixture_text, with_client

SCHOOL = "https://school.example"
SIGN_IN = (
    b"<html><body><form action='/iserv/auth/login' method='post'><input name='_username'>"
    b"<input type='password' name='_password'></form></body></html>"
)


def answer(url, content=b"%PDF", kind="application/pdf"):
    return SimpleNamespace(status_code=200, url=url, headers={"content-type": kind}, content=content, truncated=False)


def test_a_sign_in_page_is_never_served_as_a_school_file():
    client = SimpleNamespace(fetch_file=lambda path, limit, timeout=60: answer(SCHOOL + path, SIGN_IN, "text/html; charset=utf-8"))
    with pytest.raises(DataError):
        read_school_file(client, "/iserv/parentletter/attachment/abc", SCHOOL)
    client = SimpleNamespace(fetch_file=lambda path, limit, timeout=60: answer(SCHOOL + path))
    assert read_school_file(client, "/iserv/parentletter/attachment/abc", SCHOOL).content == b"%PDF"


class GuardedFiles(FileClient):
    def __init__(self, url, served):
        super().__init__(url)
        self.served = served

    def fetch(self, path, params=None):
        raise AssertionError("a file must not be read with the redirect-following fetch")

    def fetch_file(self, path, limit, timeout=60):
        self.paths.append(path)
        return self.served(path)


@pytest.mark.parametrize(
    "served",
    [
        lambda path: answer(SCHOOL + "/iserv/auth/login", SIGN_IN, "text/html"),
        lambda path: answer(SCHOOL + path, SIGN_IN, "text/html"),
        lambda path: answer("https://elsewhere.example" + path),
    ],
)
def test_a_pinboard_file_from_a_sign_in_page_or_another_host_is_refused(tmp_path, served):
    client = GuardedFiles(SCHOOL, served)
    service, _ = with_client(tmp_path, client)
    with pytest.raises(DataError):
        service.pinboard_attachment("0123456789abcdef0123456789abcdef-42.pdf")
    assert len(client.paths) == 1


def test_a_letter_file_is_read_with_the_strict_file_fetch_and_a_sign_in_page_is_refused(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    asked = []

    def served(path, limit, timeout=60):
        asked.append(path)
        return answer(SCHOOL + path, SIGN_IN, "text/html")

    client.fetch_file = served
    with pytest.raises(DataError):
        service.letter_attachment(SEEN_ATTACHMENT)
    assert asked == [f"/iserv/parentletter/attachment/{SEEN_ATTACHMENT}"]


def test_an_older_absence_file_from_another_host_is_refused(tmp_path, monkeypatch):
    service, connection, _school = attachment_school(tmp_path, files=["Attest.pdf"])
    entry = service.absences_overview(connection.id)["entries"][0]
    key = service.older_absence_detail(connection.id, entry["id"])["attachments"][0]["key"]
    monkeypatch.setattr(SchoolClient, "fetch_file", lambda self, path, limit, timeout=60: answer("https://elsewhere.example" + path))
    with pytest.raises(DataError):
        service.older_absence_attachment(connection.id, entry["id"], key)
