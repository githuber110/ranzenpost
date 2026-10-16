import json

import pytest

from app import school_lists, task_service, upstream
from app.iserv.errors import DataError
from app.iserv.exercise_detail import form_errors
from tests.test_refused_probes import Answer
from tests.test_task_detail import BASE, OPEN, OPEN_PATH, School, act, after_upload, form_id, parsed, school_service

ROW_701 = '<tr><td><input type="checkbox" name="files[]" value="701"></td><td><a href="/iserv/fs/file/exercise-submission/701/foto-seite-12.jpg">foto-seite-12.jpg</a></td><td>2 MB</td><td>12.10.2026 17:01</td></tr>'
ROW_702 = '<tr><td><input type="checkbox" name="files[]" value="702"></td><td><a href="/iserv/fs/file/exercise-submission/702/rechnung.pdf">rechnung.pdf</a></td><td>80 KB</td><td>12.10.2026 17:03</td></tr>'
SWAPPED = OPEN.replace(ROW_701 + "\n" + ROW_702, ROW_702 + "\n" + ROW_701)
WITHOUT_702 = OPEN.replace(ROW_702, "")
WITHOUT_CONFIRM = OPEN.split('<form name="confirm"')[0] + "</div></div></div></body></html>"
RECHNUNG = {"index": 1, "label": "rechnung.pdf", "value": "702"}


def test_a_delete_picks_the_file_by_label_and_value_even_when_the_rows_moved(tmp_path):
    assert SWAPPED != OPEN
    client = School({OPEN_PATH: [SWAPPED, WITHOUT_702]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "delete", form=form_id(OPEN, "delete"), target=RECHNUNG)
    assert ("files[]", "702") in client.posts[0]["data"]
    assert ("files[]", "701") not in client.posts[0]["data"]
    assert result["outcome"] == "done"


@pytest.mark.parametrize("target", [{"index": 1, "label": "rechnung.pdf", "value": "999"}, {"index": 1, "label": "other.pdf", "value": "702"}, {"index": 1}, None])
def test_a_delete_whose_file_is_not_on_the_fresh_page_is_not_sent(tmp_path, target):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "delete", target=target)
    assert result["outcome"] == "unavailable"
    assert result["detail"]["actions"]["delete"]
    assert client.posts == []


def test_the_public_delete_offer_names_label_and_value():
    entries = task_service.public_detail(parsed(OPEN), BASE, 1)["actions"]["delete"]
    assert [(entry["label"], entry["value"]) for entry in entries] == [("foto-seite-12.jpg", "701"), ("rechnung.pdf", "702")]


def test_an_upload_counts_only_when_a_new_file_appears(tmp_path):
    already = after_upload(["heft.pdf"])
    client = School({OPEN_PATH: [already, already]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])
    assert result["outcome"] == "uncertain"


def test_an_upload_is_not_confirmed_by_a_longer_name_that_contains_it(tmp_path):
    client = School({OPEN_PATH: [OPEN, after_upload(["alter-heft.pdf"])]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])
    assert result["outcome"] == "uncertain"


def test_a_second_copy_of_an_existing_name_counts_as_new(tmp_path):
    client = School({OPEN_PATH: [after_upload(["heft.pdf"]), after_upload(["heft.pdf", "heft (1).pdf"])]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])
    assert result["outcome"] == "done"


def text_page(*lines):
    markup = "".join("&lt;p&gt;%s&lt;/p&gt;" % line for line in lines)
    return OPEN.replace("&lt;p&gt;Meine Lösung zu Aufgabe 1&lt;/p&gt;", markup)


@pytest.mark.parametrize(
    "before, after",
    [
        (OPEN, text_page("Antwort", "und noch mehr")),
        (text_page("Antwort"), text_page("Antwort")),
    ],
)
def test_a_text_counts_only_when_the_page_shows_exactly_the_new_text(tmp_path, before, after):
    client = School({OPEN_PATH: [before, after]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "text", html=before, text="Antwort")
    assert result["outcome"] == "uncertain"


def test_a_text_with_other_spacing_still_counts(tmp_path):
    client = School({OPEN_PATH: [OPEN, text_page("Erste  Zeile", "zweite")]})
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "text", text="Erste Zeile\nzweite")["outcome"] == "done"


def test_marking_done_needs_more_than_a_missing_form(tmp_path):
    client = School({OPEN_PATH: [OPEN, WITHOUT_CONFIRM]})
    service, store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "confirm")
    assert result["outcome"] == "uncertain"
    assert school_lists.stored_list(store, connection_id, "tasks")["tasks"][0]["done"] is False


def test_marking_done_counts_when_the_undo_form_appears(tmp_path):
    undo = '<form method="post" action="/iserv/exercise/show/31/unconfirm"><input type="hidden" name="_token" value="u"><button type="submit">Als nicht erledigt markieren</button></form>'
    client = School({OPEN_PATH: [OPEN, OPEN.replace("<h3>Textabgabe</h3>", undo + "<h3>Textabgabe</h3>").split('<form name="confirm"')[0] + "</div></div></div></body></html>"]})
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "confirm")["outcome"] == "done"


def test_a_form_hint_is_no_error_but_a_hint_inside_an_error_group_is():
    hint = '<div class="form-group"><input name="x"><span class="help-block">Maximal 100 MB</span></div>'
    error = '<div class="form-group has-error"><input name="x"><span class="help-block">Die Datei ist zu groß.</span></div>'
    assert form_errors(hint) == []
    assert form_errors(error) == ["Die Datei ist zu groß."]
    assert form_errors('<span class="text-danger">Überfällig</span>') == []


def test_a_page_with_a_plain_hint_after_saving_is_checked_and_counts(tmp_path):
    hinted = after_upload(["heft.pdf"]).replace("</form>", '<span class="help-block">Maximal 100 MB</span></form>', 1)
    client = School({OPEN_PATH: [OPEN, hinted]}, post=lambda url, data, files: Answer(200, url, hinted))
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])["outcome"] == "done"


def test_a_refusal_whose_change_shows_on_the_page_is_uncertain(tmp_path):
    refused = OPEN.replace("<h3>Textabgabe</h3>", '<div class="alert alert-danger">Fehler</div><h3>Textabgabe</h3>')
    client = School({OPEN_PATH: [OPEN, after_upload(["heft.pdf"])]}, post=lambda url, data, files: Answer(200, url, refused))
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])["outcome"] == "uncertain"


def test_a_failure_after_the_post_is_uncertain_and_never_says_nothing_was_sent(tmp_path, monkeypatch):
    done = WITHOUT_CONFIRM.replace("<td>Begonnen</td>", "<td>Erledigt</td>")
    client = School({OPEN_PATH: [OPEN, done]})
    service, _store, connection_id = school_service(tmp_path, client)

    def broken(self, task, action):
        raise OSError("disk full")

    monkeypatch.setattr(task_service.TaskService, "_note_done_state", broken)
    result = act(service, connection_id, "confirm")
    assert len(client.posts) == 1
    assert result["outcome"] == "uncertain"
    assert result["message_key"] == task_service.ACT_UNCERTAIN_KEY


@pytest.mark.parametrize("href", ["/iserv/file/copy/31", "/iserv/exercise/show/31/files/702/delete", "/iserv/file/move/7", "/iserv/file/share/7"])
def test_links_that_would_change_something_are_neither_files_nor_links(href):
    html = OPEN.replace('<li><a href="https://video.example.org/brueche">Erklärvideo</a></li>', '<li><a href="%s">Kopieren.pdf</a></li>' % href)
    result = task_service.public_detail(parsed(html), BASE, 1)
    assert all(href not in str(entry) for entry in result["files"] + result["links"])


def test_unrecognised_post_forms_are_counted_for_the_app():
    html = OPEN.replace("<h3>Textabgabe</h3>", '<form method="post" action="/iserv/exercise/show/31/peer"><input type="hidden" name="t" value="1"><button type="submit">Weiter</button></form><h3>Textabgabe</h3>')
    assert task_service.public_detail(parsed(html), BASE, 1)["unrecognised"] == 1
    assert task_service.public_detail(parsed(OPEN), BASE, 1)["unrecognised"] == 0


@pytest.mark.parametrize(
    "files, key",
    [
        ([{"filename": "a%d" % number, "content": b"x"} for number in range(21)], task_service.ACT_TOO_MANY_KEY),
        ([{"filename": "a", "content": b"x" * (task_service.MAX_FILE_BYTES + 1)}], task_service.ACT_FILE_TOO_LARGE_KEY),
    ],
)
def test_each_upload_limit_has_its_own_message(tmp_path, files, key):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "upload", files=files)["message_key"] == key
    assert client.posts == []


def _app(tmp_path, client):
    from fastapi.testclient import TestClient

    from app.server import create_app

    service, _store, connection_id = school_service(tmp_path, client)
    return TestClient(create_app(service=service)), connection_id


def test_the_act_route_refuses_a_request_larger_than_the_limit_before_reading_it(tmp_path):
    app, connection_id = _app(tmp_path, School({OPEN_PATH: OPEN}))
    body = {"connection_id": connection_id, "task_id": "31", "action": "upload", "form": "x", "confirmed": True}
    answer = app.post(
        "/api/tasks/act",
        data={"data": json.dumps(body)},
        files=[("files", ("a.pdf", b"x", "application/pdf"))],
        headers={"content-length": str(task_service.MAX_TOTAL_BYTES * 2)},
    )
    assert answer.status_code == 200
    assert answer.json()["message_key"] == task_service.ACT_TOO_LARGE_KEY


def test_the_act_route_answers_21_files_with_the_count_message(tmp_path):
    app, connection_id = _app(tmp_path, School({OPEN_PATH: OPEN}))
    body = {"connection_id": connection_id, "task_id": "31", "action": "upload", "form": "x", "confirmed": True}
    files = [("files", ("a%d.pdf" % number, b"x", "application/pdf")) for number in range(21)]
    answer = app.post("/api/tasks/act", data={"data": json.dumps(body)}, files=files).json()
    assert answer["message_key"] == task_service.ACT_TOO_MANY_KEY
    assert answer["message_vars"] == {"max": 20}


def test_a_file_in_the_data_field_is_a_client_error(tmp_path):
    app, _connection_id = _app(tmp_path, School({OPEN_PATH: OPEN}))
    answer = app.post("/api/tasks/act", files=[("data", ("data.json", b"{}", "application/json"))])
    assert answer.status_code == 400


@pytest.mark.parametrize(
    "value, expected",
    [
        ("application/pdf", "application/pdf"),
        ("image/png", "image/png"),
        ("IMAGE/JPEG; name=x.jpg", "image/jpeg"),
        ("text/plain; charset=utf-8", "application/octet-stream"),
        ("text/javascript", "application/octet-stream"),
        ("application/javascript", "application/octet-stream"),
        ("text/css", "application/octet-stream"),
        ("text/html; charset=utf-8", "application/octet-stream"),
        ("image/svg+xml", "application/octet-stream"),
        ("application/xhtml+xml", "application/octet-stream"),
        ("", "application/octet-stream"),
    ],
)
def test_served_files_never_carry_an_active_content_type(value, expected):
    assert upstream.safe_media_type(value) == expected


def file_answer(url, content=b"%PDF-1.4", content_type="application/pdf"):
    answer = Answer(200, url)
    answer.content = content
    answer.headers = {"content-type": content_type}
    return answer


def test_a_school_file_from_another_host_or_too_large_is_refused():
    path = "/iserv/fs/file/x.pdf"
    moved = file_answer("https://other.example" + path)
    moved.final_url = moved.url
    with pytest.raises(DataError):
        school_lists.read_school_file(School({path: moved}), path, BASE)
    with pytest.raises(DataError):
        school_lists.read_school_file(School({path: file_answer(BASE + path, b"x" * (school_lists.FILE_LIMIT + 1))}), path, BASE)
    assert school_lists.read_school_file(School({path: file_answer(BASE + path)}), path, BASE).content == b"%PDF-1.4"


def test_an_html_file_is_served_as_a_download_without_sniffing(tmp_path):
    path = "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf"
    client = School({OPEN_PATH: OPEN, path: file_answer(BASE + path, b"<script>x</script>", "text/html")})
    app, connection_id = _app(tmp_path, client)
    app.get("/api/tasks/detail", params={"connection": connection_id, "task": "31"})
    answer = app.get("/api/tasks/file", params={"connection": connection_id, "task": "31", "kind": "files", "index": 0})
    assert answer.headers["content-type"] == "application/octet-stream"
    assert answer.headers["x-content-type-options"] == "nosniff"


class StreamAnswer:
    def __init__(self, status, headers=None, body=b""):
        self.status_code = status
        self.headers = headers or {}
        self.body = body

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]

    def close(self):
        pass


class StreamSession:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []
        self.headers = {}
        self.cookies = []

    def get(self, url, **kwargs):
        self.asked.append(url)
        return self.answers.pop(0)


def test_the_client_follows_file_redirects_only_on_the_school_host_and_caps_the_body():
    from app.iserv.client import IServClient

    client = IServClient(BASE)
    client.session = StreamSession([StreamAnswer(302, {"location": "/iserv/fs/b.pdf"}), StreamAnswer(200, {"content-type": "application/pdf"}, b"x" * 10)])
    answer = client.fetch_file("/iserv/fs/a.pdf", 4)
    assert (answer.status_code, answer.url, answer.truncated) == (200, BASE + "/iserv/fs/b.pdf", True)
    client.session = StreamSession([StreamAnswer(302, {"location": "https://other.example/x.pdf"})])
    with pytest.raises(DataError):
        client.fetch_file("/iserv/fs/a.pdf", 4)
    assert client.session.asked == [BASE + "/iserv/fs/a.pdf"]
