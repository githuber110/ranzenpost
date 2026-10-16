from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app import modules, school_lists, task_service
from app.iserv.errors import DataError
from app.iserv.exercise_detail import parse_task_detail, shape_of
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_refused_probes import Answer

BASE = "https://school.example"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPEN_PATH = "/iserv/exercise/show/31"
FEEDBACK_PATH = "/iserv/exercise/show/32"
CARDS_PATH = "/iserv/exercise/show/41"


def fixture(name):
    return (FIXTURES / ("exercise_show_%s.html" % name)).read_text(encoding="utf-8")


OPEN = fixture("open")
FEEDBACK = fixture("feedback")
CARDS = fixture("cards")
PAST = fixture("past")


def parsed(html, path=OPEN_PATH, title=""):
    return parse_task_detail(html, path, BASE + path, "school.example", title)


def operations(result):
    return {kind: form for form in result["forms"] for kind in form["operations"]}


def test_an_open_task_reads_text_facts_attachments_own_files_and_every_offered_form():
    result = parsed(OPEN, title="Bruchrechnung")
    assert result["text"][:3] == ["Bitte rechnet die Aufgaben 1 bis 4 auf Seite 12.", "Ladet ein Foto oder eine PDF hoch.", "Viel Erfolg!"]
    assert (result["start"], result["due"], result["tags"], result["state_text"]) == ("2026-10-01", "2026-10-20T18:00", ["Mathe", "Hausaufgabe"], "Begonnen")
    assert result["files"] == [{"href": "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf", "label": "arbeitsblatt.pdf", "meta": "120 KB"}]
    assert result["links"] == [{"href": "https://video.example.org/brueche", "label": "Erklärvideo"}]
    own = result["sections"]["submission"]["files"]
    assert [entry["label"] for entry in own] == ["foto-seite-12.jpg", "rechnung.pdf"]
    assert own[0]["meta"] == "2 MB · 12.10.2026 17:01"
    found = operations(result)
    assert set(found) == {"upload", "delete", "text", "confirm"}
    assert found["upload"]["file_field"] == "upload[file][]" and found["upload"]["multiple"] is True
    assert [target["value"] for target in found["delete"]["targets"]] == ["701", "702"]
    assert [target["label"] for target in found["delete"]["targets"]] == ["foto-seite-12.jpg", "rechnung.pdf"]
    assert found["text"]["editor"] is True and found["text"]["text"] == ["Meine Lösung zu Aufgabe 1"]
    assert all(form["writable"] for form in result["forms"])
    assert all("In meine Dateien kopieren" not in line for line in result["text"])


def test_a_done_task_reads_feedback_model_solutions_and_the_undo_form():
    result = parsed(FEEDBACK, FEEDBACK_PATH, "Gedicht")
    feedback = result["sections"]["feedback"]
    assert feedback["text"] == ["Sehr schön vorgetragen. Achte auf die Kommas."]
    assert feedback["facts"] == [{"label": "Rückmeldung vom", "value": "20.09.2026"}]
    assert [entry["label"] for entry in feedback["files"]] == ["korrektur.pdf"]
    assert [entry["label"] for entry in result["sections"]["solution"]["files"]] == ["loesung.pdf"]
    assert result["sections"]["submission"]["text"] == ["Abgeschriebenes Gedicht."]
    assert set(operations(result)) == {"undo"}


def test_a_card_layout_reads_definition_lists_attribute_dates_and_one_delete_form_per_file():
    result = parsed(CARDS, CARDS_PATH)
    assert (result["start"], result["due"], result["tags"]) == ("2026-10-05T08:00", "2026-10-25", ["English", "Writing"])
    assert result["files"] == [{"href": "/iserv/exercise/attachment/41/1", "label": "Essay guide"}]
    deletes = [form for form in result["forms"] if "delete" in form["operations"]]
    assert [form["targets"][0]["label"] for form in deletes] == ["draft.odt", "notes.txt"]
    assert len({form["id"] for form in deletes}) == 2
    upload = operations(result)["upload"]
    assert (upload["multiple"], upload["accept"], upload["required"]) == (False, ".pdf,.odt,.docx", True)


def test_a_past_task_offers_nothing_to_hand_in():
    result = parsed(PAST, "/iserv/exercise/show/50", "Plakat")
    assert result["forms"] == []
    assert result["due"] == "2026-06-01"
    assert result["sections"]["submission"]["text"] == ["Keine Abgabe mehr möglich."]


@pytest.mark.parametrize("html", ["", "<<<not html", "<html><body><nav>Menu</nav></body></html>", "<html><body><form method='post'></form></body></html>"])
def test_unknown_markup_reads_an_empty_detail_without_crashing(html):
    result = parsed(html)
    assert result["files"] == [] and result["sections"]["submission"]["files"] == []
    assert all(form["operations"] == {} for form in result["forms"])
    assert task_service.public_detail(result, BASE, 1)["actions"] == {}


def test_a_form_that_posts_to_another_host_or_the_sign_in_is_never_writable():
    html = """<div id="content"><h3>Abgabe</h3>
    <form method="post" action="https://evil.example/iserv/exercise/upload" enctype="multipart/form-data"><input type="file" name="f"><button>Speichern</button></form>
    <form method="post" action="/iserv/auth/logout"><button>Erledigt</button></form>
    <form method="post" action="/iserv/exercise/../auth/x"><button>Erledigt</button></form></div>"""
    result = parsed(html)
    assert [form["writable"] for form in result["forms"]] == [False, False, False]
    assert task_service.public_detail(result, BASE, 1)["actions"] == {}


def test_the_shape_names_structure_only():
    shape = shape_of(parsed(OPEN, title="Bruchrechnung"))
    text = repr(shape)
    for content in ("Bruchrechnung", "rechnet", "foto-seite", "tok-", "Lehrkraft", "Meine Lösung", "701"):
        assert content not in text
    assert [form["kind"] for form in shape["forms"]] == ["upload", "delete", "text", "confirm"]
    assert shape["sections"]["submission"]["files"] == 2


def test_the_public_detail_keeps_school_paths_for_the_proxy_and_shows_other_hosts_as_text():
    detail = task_service.public_detail(parsed(OPEN, title="Bruchrechnung"), BASE, 7)
    assert detail["files"] == [{"label": "arbeitsblatt.pdf", "meta": "120 KB", "path": "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf"}]
    assert detail["links"] == [{"label": "Erklärvideo", "url": "https://video.example.org/brueche"}]
    assert detail["actions"]["upload"]["multiple"] is True
    assert detail["actions"]["text"]["text"] == ["Meine Lösung zu Aufgabe 1"]
    assert [(entry["target"], entry["file"]) for entry in detail["actions"]["delete"]] == [(0, 0), (1, 1)]
    assert "confirm" in detail["actions"] and "undo" not in detail["actions"]
    assert detail["read_at"] == 7
    for form in detail["actions"].values():
        for entry in form if isinstance(form, list) else [form]:
            assert set(entry) <= {"form", "multiple", "accept", "text", "max_length", "target", "label", "value", "file"}


@pytest.mark.parametrize(
    "kind, index, expected",
    [
        ("files", 0, "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf"),
        ("submission", 1, "/iserv/fs/file/exercise-submission/702/rechnung.pdf"),
        ("submission", 2, ""),
        ("links", 0, ""),
        ("feedback", 0, ""),
        ("files", -1, ""),
        ("files", True, ""),
        ("other", 0, ""),
    ],
)
def test_only_school_files_stored_with_that_task_can_be_fetched(kind, index, expected):
    detail = task_service.public_detail(parsed(OPEN, title="Bruchrechnung"), BASE, 1)
    assert task_service.task_file_path(detail, kind, index) == expected


@pytest.mark.parametrize("path", ["/iserv/../etc/passwd", "/other/file.pdf", "/iserv/fs\\file.pdf"])
def test_a_stored_path_outside_the_school_file_root_is_refused(path):
    assert task_service.task_file_path({"files": [{"label": "x", "path": path}]}, "files", 0) == ""


class School:
    def __init__(self, pages, post=None):
        self.pages = {path: list(answers) if isinstance(answers, list) else [answers] for path, answers in pages.items()}
        self.asked = []
        self.posts = []
        self.post = post

    def fetch(self, path, params=None):
        self.asked.append(path)
        answers = self.pages.get(path)
        if not answers:
            return Answer(404, BASE + path)
        found = answers.pop(0) if len(answers) > 1 else answers[0]
        return Answer(200, BASE + path, found) if isinstance(found, str) else found

    def fetch_file(self, path, limit, timeout=60):
        answer = self.fetch(path)
        content = getattr(answer, "content", b"") or b""
        return SimpleNamespace(
            status_code=answer.status_code,
            url=getattr(answer, "final_url", None) or answer.url,
            headers=answer.headers,
            content=content[:limit],
            truncated=len(content) > limit,
        )

    def post_form(self, url, data, files=None, headers=None, timeout=60):
        self.posts.append({"url": url, "data": list(data), "files": files, "headers": headers})
        if self.post is None:
            return Answer(200, url, "<html><body>ok</body></html>")
        return self.post(url, data, files)


TASK = {"id": "31", "title": "Bruchrechnung", "due": "2026-10-20T18:00", "past": False, "done": False, "path": OPEN_PATH}
LINKLESS = {"id": "habc", "title": "Ohne Link", "past": False, "done": None, "path": ""}


def school_service(tmp_path, client, tasks=(TASK, LINKLESS)):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    school_lists.store_list(store, connection_id, "tasks", [dict(task) for task in tasks], 1)
    service = IServService(store)
    connection = service.connections()[0]
    connection.store.save_modules({"modules": {modules.TASKS: True}})
    connection._session = lambda: client
    connection.clock = lambda: 1_791_000_000
    return service, store, connection_id


def test_opening_a_task_reads_only_its_page_and_keeps_the_detail_and_its_shape(tmp_path):
    client = School({OPEN_PATH: OPEN})
    service, store, connection_id = school_service(tmp_path, client)
    detail = service.task_detail(connection_id, "31")
    assert client.asked == [OPEN_PATH]
    assert detail["text"][0].startswith("Bitte rechnet")
    assert task_service.stored_details(store, connection_id)["31"] == detail
    shape = task_service.stored_shape(store, connection_id)
    assert shape["read_at"] == 1_791_000_000 and "Bitte" not in repr(shape)
    listed = service.tasks()
    assert next(task for task in listed["tasks"] if task["id"] == "31")["detail"] == detail
    service.task_detail(connection_id, "31")
    assert client.asked == [OPEN_PATH, OPEN_PATH]


def test_a_task_that_is_not_listed_or_has_no_page_is_never_requested(tmp_path):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    with pytest.raises(DataError) as unknown:
        service.task_detail(connection_id, "99")
    assert unknown.value.message_key == task_service.TASK_UNKNOWN_KEY
    with pytest.raises(DataError) as linkless:
        service.task_detail(connection_id, "habc")
    assert linkless.value.message_key == task_service.TASK_NO_DETAIL_KEY
    assert client.asked == []


@pytest.mark.parametrize("answer", [Answer(200, BASE + "/iserv/auth/login", "<html></html>"), Answer(200, BASE + "/iserv/exercise", "<html></html>"), Answer(404, BASE + OPEN_PATH)])
def test_a_task_page_that_leads_elsewhere_is_an_error(tmp_path, answer):
    service, store, connection_id = school_service(tmp_path, School({OPEN_PATH: answer}))
    with pytest.raises(DataError):
        service.task_detail(connection_id, "31")
    assert task_service.stored_details(store, connection_id) == {}


class FileAnswer:
    status_code = 200
    url = BASE + "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf"
    content = b"%PDF-1.4"
    text = ""
    headers = {"content-type": "application/pdf", "content-disposition": 'attachment; filename="arbeitsblatt.pdf"'}


def test_the_app_serves_files_of_the_opened_task_through_ranzenpost_only(tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app

    client = School({OPEN_PATH: OPEN, "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf": FileAnswer()})
    service, _store, connection_id = school_service(tmp_path, client)
    app = TestClient(create_app(service=service))
    before = app.get("/api/tasks/file", params={"connection": connection_id, "task": "31", "kind": "files", "index": 0})
    assert before.status_code == 400
    assert client.asked == []
    opened = app.get("/api/tasks/detail", params={"connection": connection_id, "task": "31"}).json()
    assert opened["files"][0]["path"].startswith("/iserv/")
    answer = app.get("/api/tasks/file", params={"connection": connection_id, "task": "31", "kind": "files", "index": 0})
    assert answer.status_code == 200 and answer.content == b"%PDF-1.4"
    other = app.get("/api/tasks/file", params={"connection": connection_id, "task": "habc", "kind": "files", "index": 0})
    assert other.status_code == 400
    assert client.asked == [OPEN_PATH, "/iserv/fs/file/exercise-dl/31/arbeitsblatt.pdf"]


def after_upload(names):
    rows = "".join(
        '<tr><td><input type="checkbox" name="files[]" value="%d"></td><td><a href="/iserv/fs/file/exercise-submission/%d/%s">%s</a></td></tr>' % (number, number, name, name)
        for number, name in enumerate(names, start=800)
    )
    return OPEN.replace("</tbody>", rows + "</tbody>")


def form_id(html, kind, path=OPEN_PATH):
    return next(form["id"] for form in parsed(html, path)["forms"] if kind in form["operations"])


def act(service, connection_id, action, html=OPEN, path=OPEN_PATH, task="31", **extra):
    return service.task_act(connection_id, task, action, extra.pop("form", None) or form_id(html, action, path), confirmed=extra.pop("confirmed", True), **extra)


def test_handing_in_files_posts_the_form_as_multipart_and_confirms_by_reading_the_task_again(tmp_path):
    client = School({OPEN_PATH: [OPEN, after_upload(["heft.pdf"])]})
    service, store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "C:\\fakepath\\heft.pdf", "content": b"%PDF", "content_type": "application/pdf"}])
    assert result["ok"] is True and result["outcome"] == "done"
    assert result["message_key"] == task_service.ACT_DONE_KEY
    assert len(client.posts) == 1
    sent = client.posts[0]
    assert sent["url"] == BASE + "/iserv/exercise/show/31/upload"
    assert ("upload[_token]", "tok-upload-1") in sent["data"] and ("upload[submit]", "") in sent["data"]
    assert sent["files"] == [("upload[file][]", ("heft.pdf", b"%PDF", "application/pdf"))]
    assert sent["headers"]["Referer"] == BASE + OPEN_PATH
    assert client.asked == [OPEN_PATH, OPEN_PATH]
    assert "heft.pdf" in [entry["label"] for entry in result["detail"]["submission"]["files"]]
    assert task_service.stored_details(store, connection_id)["31"] == result["detail"]


def test_a_file_the_task_page_does_not_show_afterwards_is_uncertain_and_never_sent_again(tmp_path):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "heft.pdf", "content": b"%PDF"}])
    assert result["ok"] is False and result["outcome"] == "uncertain"
    assert result["message_key"] == task_service.ACT_UNCERTAIN_KEY
    assert len(client.posts) == 1


def test_a_failed_request_is_uncertain_and_not_repeated(tmp_path):
    def broken(url, data, files):
        raise requests.ConnectionError("reset")

    client = School({OPEN_PATH: OPEN}, post=broken)
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "text", text="Antwort")
    assert result["outcome"] == "uncertain"
    assert len(client.posts) == 1


def test_a_validation_error_of_the_school_form_is_shown_as_rejected(tmp_path):
    page = OPEN.replace("<h3>Textabgabe</h3>", '<div class="alert alert-danger">Die Datei ist zu groß.</div><h3>Textabgabe</h3>')
    client = School({OPEN_PATH: OPEN}, post=lambda url, data, files: Answer(200, url, page))
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", files=[{"filename": "big.pdf", "content": b"x"}])
    assert result["ok"] is False and result["outcome"] == "rejected"
    assert result["errors"] == ["Die Datei ist zu groß."]
    assert result["detail"]["actions"]["upload"]


def test_a_text_is_handed_in_as_editor_markup_and_seen_again(tmp_path):
    changed = OPEN.replace("&lt;p&gt;Meine Lösung zu Aufgabe 1&lt;/p&gt;", "&lt;p&gt;Zeile eins&lt;/p&gt;&lt;p&gt;Zeile &amp;lt;zwei&amp;gt;&lt;/p&gt;")
    client = School({OPEN_PATH: [OPEN, changed]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "text", text="Zeile eins\nZeile <zwei>")
    assert result["outcome"] == "done"
    assert ("text[text]", "<p>Zeile eins</p><p>Zeile &lt;zwei&gt;</p>") in client.posts[0]["data"]
    assert ("text[save]", "") in client.posts[0]["data"]
    assert client.posts[0]["files"] is None


def test_marking_done_posts_the_confirm_form_and_updates_the_listed_state(tmp_path):
    done = OPEN.split('<form name="confirm"')[0].replace("<td>Begonnen</td>", "<td>Erledigt</td>") + "</div></div></div></body></html>"
    client = School({OPEN_PATH: [OPEN, done]})
    service, store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "confirm")
    assert result["outcome"] == "done"
    assert client.posts[0]["url"] == BASE + "/iserv/exercise/show/31/confirm"
    assert client.posts[0]["data"] == [("confirm[_token]", "tok-confirm-1")]
    assert school_lists.stored_list(store, connection_id, "tasks")["tasks"][0]["done"] is True


def test_deleting_an_own_file_sends_only_that_file(tmp_path):
    gone = OPEN.replace('<tr><td><input type="checkbox" name="files[]" value="702"></td><td><a href="/iserv/fs/file/exercise-submission/702/rechnung.pdf">rechnung.pdf</a></td><td>80 KB</td><td>12.10.2026 17:03</td></tr>', "")
    client = School({OPEN_PATH: [OPEN, gone]})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "delete", target={"index": 1, "label": "rechnung.pdf", "value": "702"})
    assert result["outcome"] == "done"
    assert client.posts[0]["data"] == [("files[_token]", "tok-files-1"), ("files[]", "702"), ("files[delete]", "")]


def test_a_form_that_is_gone_after_the_deadline_is_not_sent(tmp_path):
    client = School({OPEN_PATH: PAST})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", form=form_id(OPEN, "upload"), files=[{"filename": "a.pdf", "content": b"x"}])
    assert result["outcome"] == "unavailable"
    assert result["message_key"] == task_service.ACT_UNAVAILABLE_KEY
    assert client.posts == []
    assert result["detail"]["actions"] == {}


@pytest.mark.parametrize(
    "extra, key",
    [
        ({"confirmed": False}, task_service.ACT_UNCONFIRMED_KEY),
        ({"files": []}, task_service.ACT_EMPTY_KEY),
        ({"files": [{"filename": "a", "content": b"x" * (task_service.MAX_FILE_BYTES + 1)}]}, task_service.ACT_FILE_TOO_LARGE_KEY),
    ],
)
def test_unconfirmed_or_invalid_uploads_never_reach_the_school(tmp_path, extra, key):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    result = act(service, connection_id, "upload", **extra)
    assert result["ok"] is False and result["message_key"] == key
    assert client.asked == [] and client.posts == []


def test_more_files_than_a_single_file_form_takes_are_refused(tmp_path):
    path = "/iserv/exercise/show/41"
    client = School({path: CARDS})
    task = dict(TASK, id="41", path=path)
    service, _store, connection_id = school_service(tmp_path, client, tasks=(task,))
    result = act(service, connection_id, "upload", html=CARDS, path=path, task="41", files=[{"filename": "a", "content": b"x"}, {"filename": "b", "content": b"y"}])
    assert result["message_key"] == task_service.ACT_ONE_FILE_KEY
    assert client.posts == []


def test_an_empty_text_and_a_running_hand_in_are_refused(tmp_path):
    client = School({OPEN_PATH: OPEN})
    service, _store, connection_id = school_service(tmp_path, client)
    assert act(service, connection_id, "text", text="  ")["message_key"] == task_service.ACT_EMPTY_KEY
    service.connections()[0]._task_service._busy.add("31")
    assert act(service, connection_id, "text", text="x")["message_key"] == task_service.ACT_BUSY_KEY
    assert client.posts == []


def test_the_act_route_takes_multipart_files_and_needs_the_confirmation(tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app

    client = School({OPEN_PATH: [OPEN, after_upload(["heft.pdf"])]})
    service, _store, connection_id = school_service(tmp_path, client)
    app = TestClient(create_app(service=service))
    body = {"connection_id": connection_id, "task_id": "31", "action": "upload", "form": form_id(OPEN, "upload")}
    refused = app.post("/api/tasks/act", data={"data": __import__("json").dumps(body)}, files=[("files", ("heft.pdf", b"%PDF", "application/pdf"))]).json()
    assert refused["message_key"] == task_service.ACT_UNCONFIRMED_KEY
    assert client.posts == []
    body["confirmed"] = True
    answer = app.post("/api/tasks/act", data={"data": __import__("json").dumps(body)}, files=[("files", ("heft.pdf", b"%PDF", "application/pdf"))]).json()
    assert answer["ok"] is True and answer["outcome"] == "done"
    assert client.posts[0]["files"] == [("upload[file][]", ("heft.pdf", b"%PDF", "application/pdf"))]


def test_the_poll_reads_the_task_lists_but_never_a_task_page(tmp_path):
    from app.iserv.exercises import EXERCISE_PATH, PAST_EXERCISE_PATH
    from app.poller import SCHOOL_LISTS, Poller
    from tests.test_school_lists import task_page, task_row

    client = School({
        EXERCISE_PATH: task_page([task_row(31, "Bruchrechnung", "20.10.2026"), task_row(32, "Gedicht", "15.10.2026")]),
        PAST_EXERCISE_PATH: task_page([task_row(50, "Plakat", "01.06.2026", "Ja")]),
        OPEN_PATH: OPEN,
        FEEDBACK_PATH: FEEDBACK,
    })
    service, store, connection_id = school_service(tmp_path, client, tasks=())
    connection = service.connections()[0]
    poller = Poller(None, store=store, notifiers={"tasks": lambda name, message: True})
    poller.clock = lambda: 1_791_000_000
    spec = next(entry for entry in SCHOOL_LISTS if entry[0] == modules.TASKS)
    state = {}
    poller._poll_school_list(connection, connection_id, True, spec, state, "en")
    poller._poll_school_list(connection, connection_id, True, spec, state, "en")
    assert client.asked == [EXERCISE_PATH, PAST_EXERCISE_PATH, EXERCISE_PATH, PAST_EXERCISE_PATH]
    assert not any(path.startswith("/iserv/exercise/show/") for path in client.asked)
    assert task_service.stored_details(store, connection_id) == {}


def test_the_report_names_the_last_seen_task_page_shape_without_opening_one(tmp_path):
    from app.reportcrawl import crawl_links
    from app.reportlists import task_detail_lines

    client = School({OPEN_PATH: OPEN})
    service, store, connection_id = school_service(tmp_path, client)
    assert task_detail_lines(store, connection_id) == ["- Task detail shape: no task opened in the app yet; the report does not open one"]
    service.task_detail(connection_id, "31")
    lines = task_detail_lines(store, connection_id)
    assert lines[0].startswith("- Task detail shape (as seen when a task was last opened in the app): headings title description")
    assert any(line.startswith("  - Form upload (post, multipart): operations upload") for line in lines)
    text = "\n".join(lines)
    for content in ("Bruchrechnung", "rechnet", "foto-seite", "tok-", "Lehrkraft", "Lösung"):
        assert content not in text
    listed = '<a href="/iserv/exercise/show/31">Bruchrechnung</a><a href="/iserv/exercise/past/exercise">Vergangene</a>'
    chosen, skipped = crawl_links(listed, BASE + "/iserv/exercise", "/iserv/exercise", 10, details=False, any_text=True)
    assert all("/show/" not in link.path for link in chosen)
    assert skipped.get("detail page") == 1
