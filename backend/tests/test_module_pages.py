import pytest
from fastapi.testclient import TestClient

from app import blocks, modules
from app.file_service import AccountModuleNotOffered
from app.iserv.conferences import module_path, parse_conference_page
from app.iserv.errors import DataError
from app.iserv.module_pages import PAGE_MODULES, TASK_LIST, page_allowed, read_module_page, read_todo
from app.module_pages import ModulePages
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.account_fakes import page as school_page
from tests.module_pages_school import COURSE_PAGE, PAGES, PRINT_PAGE, ROOMS_PAGE, SCHOOL, ModuleConnection, ModuleSchool
from tests.support import add_school

ENTRIES = [
    {"segment": "print", "slug": "print", "label": "Drucken"},
    {"segment": "courseselection", "slug": "course-selection", "label": "Kurswahlen"},
]


def pages(school=None):
    return ModulePages(ModuleConnection(school))


def table_of(result):
    return next(block for block in result["blocks"] if block["kind"] == "table")


def school_service(tmp_path, school=None, entries=ENTRIES):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL)
    store.connection_store(connection_id).save_modules({"unsupported": list(entries)})
    return IServService(store, client_factory=lambda base: school or ModuleSchool()), connection_id


def test_the_modules_agree_on_what_the_app_reads():
    assert set(PAGE_MODULES) | {TASK_LIST} == set(modules.READ_PAGE_MODULES)
    assert set(modules.READ_PAGE_MODULES) == set(blocks.AREA_MODULES[blocks.AREA_MODULE_PAGES])
    assert set(modules.READ_PAGE_MODULES) <= modules.READ_BY_APP


def test_print_jobs_are_read_without_any_way_to_act():
    result = pages().read("print")
    rows = table_of(result)["rows"]
    assert [row["cells"][:3] for row in rows] == [["Elternbrief.pdf", "2", "Gedruckt"], ["Liste.pdf", "1", "Wartet"]]
    assert all(row["links"] == [] for row in rows)
    assert "Abbrechen" not in str(result) and "Hochladen" not in str(result)
    assert "forms" not in result


def test_a_read_only_page_offers_no_forms_and_no_write_links():
    for html, slug, path in ((PRINT_PAGE, "print", "/iserv/print"), (COURSE_PAGE, "course-selection", "/iserv/courseselection/7")):
        model = read_module_page(html, SCHOOL + path, slug)
        assert model["forms"] == []
        assert all(block["kind"] != "form" for block in model["blocks"])


def test_a_course_selection_opens_from_its_list_and_only_shows_its_text():
    module = pages()
    listing = module.read("course-selection")
    link = table_of(listing)["rows"][0]["links"][0]
    assert link["label"] == "Wahlpflicht 2027"
    detail = module.read("course-selection", link["page"])
    assert detail["title"] == "Wahlpflicht 2027"
    assert {"kind": "text", "text": "Bitte bis 30.11.2026 wählen."} in detail["blocks"]
    assert "Spanisch" not in str(detail) and "Speichern" not in str(detail)


def test_video_rooms_show_who_is_there_and_never_a_join_link():
    result = pages().read("videoconference")
    rows = table_of(result)["rows"]
    assert rows[0]["cells"][:2] == ["Klassenraum 4a", "3"]
    assert rows[0]["links"] == []
    assert "Beitreten" not in str(result) and "Neuer Raum" not in str(result)


def test_an_empty_poll_list_says_what_the_school_says():
    assert {"kind": "text", "text": "Keine Umfragen"} in pages().read("poll")["blocks"]


def test_the_todo_list_separates_open_from_done_and_keeps_local_time():
    block = pages().read("todo")["blocks"][0]
    assert block["kind"] == "tasks"
    assert block["open"] == [{"id": "t1", "summary": "Sportzeug mitbringen", "description": "Für Freitag", "date": "2026-11-20", "time": "12:00"}]
    assert [task["summary"] for task in block["done"]] == ["Buch abgeben"]


@pytest.mark.parametrize("text", [
    "",
    "<html></html>",
    "[]",
    '{"tasks": "none"}',
    '{"tasks": ["a", "b"]}',
    '{"tasks": [{"title": "unknown fields"}]}',
    '{"tasks": [{"uid": "t", "summary": "s", "completed": "false"}]}',
])
def test_an_unreadable_todo_answer_is_an_error_and_not_an_empty_list(text):
    with pytest.raises(DataError):
        read_todo(text)


@pytest.mark.parametrize("slug,path", [
    ("course-selection", "/iserv/courseselection/7/choose?course=1"),
    ("course-selection", "/iserv/courseselection/7/select/1"),
    ("course-selection", "/iserv/courseselection/7/result.pdf"),
    ("course-selection", "/iserv/courseselection/add"),
    ("poll", "/iserv/poll/5/answer?option=2"),
    ("poll", "/iserv/poll/5/choose/2?_token=abc"),
    ("poll", "/iserv/poll/5/close"),
    ("poll", "/iserv/poll/add"),
    ("poll", "/iserv/poll/5?_token=abc"),
    ("print", "/iserv/print/job/7/abort?_token=abc"),
    ("print", "/iserv/print/job/7/print"),
    ("print", "/iserv/print/job/7/file"),
    ("videoconference", "/iserv/videoconference/room/5"),
    ("videoconference", "/iserv/videoconference/room/5/joinRoom"),
    ("videoconference", "/iserv/videoconference/%6Aoin/5"),
])
def test_only_known_page_shapes_can_be_opened(slug, path):
    assert page_allowed(slug, path) is False


@pytest.mark.parametrize("slug,path", [
    ("course-selection", "/iserv/courseselection"),
    ("course-selection", "/iserv/courseselection/7"),
    ("course-selection", "/iserv/courseselection?page=2"),
    ("poll", "/iserv/poll/5"),
    ("poll", "/iserv/poll/5/results"),
    ("print", "/iserv/print/"),
    ("videoconference", "/iserv/videoconference"),
])
def test_the_lists_and_their_read_pages_can_be_opened(slug, path):
    assert page_allowed(slug, path) is True


def test_a_link_that_is_not_a_known_page_keeps_its_text_but_opens_nothing():
    html = school_page("Umfragen", '''
    <table><thead><tr><th>Titel</th><th></th></tr></thead><tbody>
    <tr><td><a href="/iserv/poll/manage/5">Ausflug</a></td><td><a class="btn" href="/iserv/poll/5/answer?o=2">Teilnehmen</a></td></tr>
    <tr><td><a href="/iserv/poll/6">Sportfest</a></td><td></td></tr>
    </tbody></table>''')
    rows = next(block for block in read_module_page(html, SCHOOL + "/iserv/poll", "poll")["blocks"] if block["kind"] == "table")["rows"]
    assert rows[0]["cells"][0] == "Ausflug" and rows[0]["links"] == []
    assert "Teilnehmen" not in str(rows)
    assert [link["path"] for link in rows[1]["links"]] == ["/iserv/poll/6"]


@pytest.mark.parametrize("target", [
    SCHOOL + "/iserv/videoconference/room/5/join",
    "https://other.example/iserv/videoconference/",
])
def test_a_redirect_away_from_a_known_page_is_not_followed(target):
    school = ModuleSchool(redirects={"/iserv/videoconference/": target})
    with pytest.raises(DataError) as caught:
        pages(school).read("videoconference")
    assert caught.value.message_key == "api.modulePages.unreadable"
    assert school.fetched == ["/iserv/videoconference/"]


def test_an_expired_session_signs_in_again_and_reads_the_page_once_more():
    school = ModuleSchool(redirects={"/iserv/print": SCHOOL + "/iserv/auth/login"})
    connection = ModuleConnection(school)
    assert table_of(ModulePages(connection).read("print"))["rows"][0]["cells"][0] == "Elternbrief.pdf"
    assert connection.forgotten == 1
    assert school.fetched == ["/iserv/print", "/iserv/print"]


def test_a_redirect_to_the_same_list_is_followed():
    school = ModuleSchool(redirects={"/iserv/print": SCHOOL + "/iserv/print/"}, pages={"/iserv/print/": PRINT_PAGE})
    assert table_of(pages(school).read("print"))["rows"][0]["cells"][0] == "Elternbrief.pdf"
    assert school.fetched == ["/iserv/print", "/iserv/print/"]


def test_redirects_in_a_circle_end_in_an_error():
    school = ModuleSchool(redirects={"/iserv/print": SCHOOL + "/iserv/print/", "/iserv/print/": SCHOOL + "/iserv/print"})
    with pytest.raises(DataError):
        pages(school).read("print")
    assert len(school.fetched) == 3


@pytest.mark.parametrize("text,kind", [
    ("<html><body><div id='app'></div></body></html>", None),
    ("<html><body><main><h1>Umfragen</h1><h2>Offen</h2><div id='polls'></div></main></body></html>", None),
    ("<html><body><main><form method='post'><input type='hidden' name='t' value='x'></form><div id='app'></div></main></body></html>", None),
    ("<html><body><main><div data-url='/x'><table><tbody></tbody></table></div></main></body></html>", None),
    ("<html><body><main><table data-ajax='/x'><tbody></tbody></table></main></body></html>", None),
    ("<html><body><form method='post'><input type='text' name='u'><input type='password' name='p'></form></body></html>", None),
    ("%PDF-1.7 1 0 obj", "application/pdf"),
    ('{"joinUrl": "https://x"}', "application/json"),
])
def test_what_cannot_be_read_is_an_error_and_never_an_empty_page(text, kind):
    school = ModuleSchool(pages={"/iserv/poll": text}, kinds={"/iserv/poll": kind} if kind else {})
    with pytest.raises(DataError) as caught:
        pages(school).read("poll")
    assert caught.value.message_key == "api.modulePages.unreadable"


def test_a_page_with_only_a_form_says_that_there_is_more():
    html = school_page("Wahl", '<form method="post" action="/iserv/poll/5"><select name="a"><option>Eins</option></select></form>')
    result = pages(ModuleSchool(pages={"/iserv/poll": html})).read("poll")
    assert result["hidden_forms"] == 1
    assert "Eins" not in str(result)


def test_a_form_in_a_table_row_counts_as_hidden():
    html = school_page("Wahl", '<table><tbody><tr><td><form method="post" action="/iserv/poll/5"><button>Wählen</button></form></td></tr></tbody></table>')
    result = pages(ModuleSchool(pages={"/iserv/poll": html})).read("poll")
    assert result["hidden_forms"] == 1
    assert "Wählen" not in str(result)


def test_a_logout_form_does_not_count_as_hidden():
    assert pages().read("poll")["hidden_forms"] == 0


def test_a_school_that_refuses_the_page_gets_its_own_message():
    with pytest.raises(DataError) as caught:
        pages(ModuleSchool(status=403)).read("print")
    assert caught.value.message_key == "api.modulePages.refused"


def test_a_page_never_seen_in_the_module_is_refused():
    module = pages()
    with pytest.raises(DataError) as caught:
        module.read("print", "f" * 24)
    assert caught.value.message_key == "api.conferences.page.unknown"


def test_a_token_of_one_module_does_not_open_a_page_of_another():
    module = pages()
    link = table_of(module.read("course-selection"))["rows"][0]["links"][0]
    with pytest.raises(DataError):
        module.read("print", link["page"])


def test_forget_drops_the_known_pages():
    module = pages()
    link = table_of(module.read("course-selection"))["rows"][0]["links"][0]
    module.forget()
    with pytest.raises(DataError):
        module.read("course-selection", link["page"])


@pytest.mark.parametrize("status", [403, 404, 500])
def test_a_refusing_school_is_an_error_and_not_an_empty_page(status):
    with pytest.raises(Exception):
        pages(ModuleSchool(status=status)).read("print")


def test_only_get_is_used_towards_the_school():
    school = ModuleSchool()
    module = pages(school)
    for slug in (*PAGE_MODULES, TASK_LIST):
        module.read(slug)
    assert not hasattr(school, "post")
    assert school.fetched == ["/iserv/print", "/iserv/courseselection", "/iserv/videoconference/", "/iserv/poll", "/iserv/todo/api/frontend/tasks"]


def test_the_conference_reader_stays_as_it_was():
    html = '<main><h1>T</h1><a href="/iserv/parentconference/x/delete">Weg</a><form method="post" action="/iserv/parentconference/x"><button>Los</button></form></main>'
    model = parse_conference_page(html, SCHOOL + "/iserv/parentconference/x")
    assert len(model["forms"]) == 2
    assert all(form["writes"] for form in model["forms"])
    assert module_path("/iserv/parentconference", SCHOOL + "/iserv/parentconference/x") is None
    bare = '<main><h1>T</h1><form method="post" action="/iserv/parentconference"><button>Los</button></form></main>'
    assert parse_conference_page(bare, SCHOOL + "/iserv/parentconference/x")["forms"] == []


def test_a_module_the_school_does_not_list_is_not_read(tmp_path):
    school = ModuleSchool()
    service, connection_id = school_service(tmp_path, school)
    with pytest.raises(AccountModuleNotOffered):
        service.module_page(connection_id, "poll")
    with pytest.raises(AccountModuleNotOffered):
        service.module_page(connection_id, "file")
    assert school.fetched == []


def test_the_service_lists_and_reads_a_page_per_school(tmp_path):
    service, connection_id = school_service(tmp_path)
    listed = service.account_modules()["schools"]
    assert [(entry["connection_id"], entry["print"], entry["course-selection"], entry["poll"]) for entry in listed] == [(connection_id, True, True, False)]
    result = service.module_page(connection_id, "print")
    assert result["connection_id"] == connection_id
    assert table_of(result)["rows"][0]["cells"][0] == "Elternbrief.pdf"


def test_the_route_answers_a_page_and_refuses_an_unlisted_module(tmp_path):
    service, connection_id = school_service(tmp_path)
    client = TestClient(create_app(service))
    answer = client.get("/api/module-pages/page", params={"connection": connection_id, "module": "print"})
    assert answer.status_code == 200
    assert table_of(answer.json())["rows"][1]["cells"][0] == "Liste.pdf"
    refused = client.get("/api/module-pages/page", params={"connection": connection_id, "module": "poll"})
    assert refused.json()["message_key"] == "api.account.notOffered"
