import pytest

from app import upstream
from tests.test_server import FakeService, client

SANDBOX = "sandbox; default-src 'none'"


class Upstream:
    def __init__(self, content_type, disposition=None, content=b"parent.document.title='x';"):
        self.content = content
        self.headers = {"content-type": content_type}
        if disposition is not None:
            self.headers["content-disposition"] = disposition


ROUTES = [
    ("letter_attachment", "/api/letters/attachment/abc123"),
    ("pinboard_attachment", "/api/pinboard/attachment/abcdef01-42.js"),
    ("absence_attachment", "/api/absences/attachment/abcdef01-42.js"),
    ("messenger_media", "/api/messenger/media/server.example/media1"),
    ("older_absence_attachment", "/api/absences/older-attachment?id=1&key=k"),
    ("task_file", "/api/tasks/file?connection=c&task=t&kind=file&index=0"),
    ("news_file", "/api/news/file?connection=c&item=general/1&kind=file&index=0"),
    ("mail_attachment", "/api/mail/attachment?connection=c&folder=INBOX&uid=7&part=2"),
    ("school_file", "/api/files/file?connection=c&path=/iserv/file/-/Files/x.js"),
]


def _serve(monkeypatch, method, answer):
    monkeypatch.setattr(FakeService, method, lambda self, *args: answer, raising=False)


def _assert_locked(response):
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == SANDBOX
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


@pytest.mark.parametrize("method, path", ROUTES)
@pytest.mark.parametrize(
    "content_type", ["application/javascript", "text/javascript", "text/html", "image/svg+xml", "text/plain", ""]
)
def test_a_file_route_never_serves_script_or_markup(tmp_path, monkeypatch, method, path, content_type):
    _serve(monkeypatch, method, Upstream(content_type, 'inline; filename="x.js"'))
    api, _ = client(tmp_path)
    response = api.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"] == 'attachment; filename="x.js"'
    _assert_locked(response)


@pytest.mark.parametrize("method, path", ROUTES)
def test_a_file_route_without_a_name_is_still_a_download(tmp_path, monkeypatch, method, path):
    _serve(monkeypatch, method, Upstream("text/html"))
    api, _ = client(tmp_path)
    response = api.get(path)
    assert response.headers["content-disposition"] == "attachment"
    _assert_locked(response)


@pytest.mark.parametrize("method, path", ROUTES)
@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "image/jpeg; name=a.jpg"])
def test_images_and_pdfs_keep_their_type_for_the_preview(tmp_path, monkeypatch, method, path, content_type):
    _serve(monkeypatch, method, Upstream(content_type, "inline; filename=a"))
    api, _ = client(tmp_path)
    response = api.get(path)
    assert response.headers["content-type"] == content_type.split(";")[0]
    assert response.headers["content-disposition"] == "inline; filename=a"
    _assert_locked(response)


def test_the_sick_note_pdf_is_locked_like_every_other_file(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/absences/sick-note-pdf", params={"id": "42"})
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    _assert_locked(response)


def test_the_app_pages_keep_the_app_policy(tmp_path):
    api, _ = client(tmp_path)
    response = api.get("/api/health")
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert "sandbox" not in response.headers["content-security-policy"]


def test_task_and_news_files_share_the_locked_answer():
    answer = upstream.file_response(lambda: Upstream("application/x-javascript", "inline; filename=a.js"), "file")
    assert answer.media_type == "application/octet-stream"
    assert answer.headers["content-disposition"] == "attachment; filename=a.js"
    assert answer.headers["content-security-policy"] == SANDBOX
    assert answer.headers["cross-origin-resource-policy"] == "same-origin"
