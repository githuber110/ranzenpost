import logging

import pytest
from fastapi.testclient import TestClient

from app import account_lists, account_poll, modules
from app.iserv import exercises
from app.iserv.errors import DataError, ModulePageRefusedError
from app.iserv.whiteboards import WHITEBOARDS_PATH, WhiteboardShapeError, is_whiteboard_page, parse_whiteboards, whiteboard_key
from app.poller import Poller
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_refused_probes import Answer

BASE = "https://school.example"
MENU = '<nav><a href="/iserv/excalidraw/">Tafeln</a><a href="/iserv/etherpad">Texte</a></nav>'
HEAD = (
    '<thead><tr><th><input type="checkbox" class="select-all"></th><th>Titel</th><th>Besitzer</th>'
    "<th>Erstellt am</th><th>Geändert am</th></tr></thead>"
)
DELETE_FORM = '<form method="post" action="/iserv/excalidraw/delete" id="multi">{table}<button type="submit" name="board_multi_select[delete]">Löschen</button></form>'
EMPTY_ROW = '<tr><td colspan="5" class="text-center">Keine Tafeln vorhanden.</td></tr>'
ADD_LINK = '<a href="/iserv/excalidraw/add">Tafel hinzufügen</a>'


def row(key, title, owner, created, changed):
    return (
        f'<tr><td><input type="checkbox" name="board_multi_select[multi][]" value="{key}" form="multi"></td>'
        f'<td><a href="/iserv/excalidraw/{key}">{title}</a></td><td>{owner}</td><td>{created}</td><td>{changed}</td></tr>'
    )


def page(rows, head=HEAD):
    table = f'<table id="board-table" class="table table-condensed">{head}<tbody>{rows}</tbody></table>'
    return f"<html><head><title>Tafeln - IServ</title></head><body>{MENU}<main>{ADD_LINK}{DELETE_FORM.format(table=table)}</main></body></html>"


def test_the_crud_table_with_only_its_notice_row_is_a_confirmed_empty_list():
    assert parse_whiteboards(page(EMPTY_ROW)) == {"whiteboards": []}


def test_every_row_becomes_a_whiteboard_with_owner_and_both_dates():
    rows = row("7f3a", "Bruchrechnen", "Kim Muster", "01.10.2026 08:30", "20.10.2026 16:45") + row("9b1c", "Klassenfahrt", "Schülerrat", "02.10.2026", "")
    assert parse_whiteboards(page(rows))["whiteboards"] == [
        {
            "id": "7f3a", "title": "Bruchrechnen", "owner": "Kim Muster",
            "created": "2026-10-01T08:30", "created_text": "01.10.2026 08:30",
            "changed": "2026-10-20T16:45", "changed_text": "20.10.2026 16:45",
            "path": "/iserv/excalidraw/7f3a",
        },
        {
            "id": "9b1c", "title": "Klassenfahrt", "owner": "Schülerrat",
            "created": "2026-10-02", "created_text": "02.10.2026",
            "changed": "", "changed_text": "",
            "path": "/iserv/excalidraw/9b1c",
        },
    ]


def test_a_row_without_a_checkbox_or_link_keeps_a_stable_id_from_its_texts():
    rows = "<tr><td></td><td>Tafel ohne Link</td><td>Kim</td><td>01.10.2026</td><td>02.10.2026</td></tr>"
    first = parse_whiteboards(page(rows))["whiteboards"][0]
    assert first["id"].startswith("h") and first["path"] == "" and first["title"] == "Tafel ohne Link"
    assert parse_whiteboards(page(rows))["whiteboards"][0]["id"] == first["id"]


def test_columns_are_found_by_their_header_names_in_any_order():
    head = "<thead><tr><th></th><th>Geändert am</th><th>Owner</th><th>Title</th><th>Created</th></tr></thead>"
    rows = '<tr><td></td><td>2026-10-20</td><td>Kim</td><td><a href="/iserv/excalidraw/a1">Plan</a></td><td>2026-10-01</td></tr>'
    board = parse_whiteboards(page(rows, head))["whiteboards"][0]
    assert (board["id"], board["title"], board["owner"], board["created"], board["changed"]) == ("a1", "Plan", "Kim", "2026-10-01", "2026-10-20")


UNKNOWN_PAGES = [
    "",
    "<p>Keine Tafeln vorhanden.</p>",
    '<div class="alert alert-danger">Keine Berechtigung</div>',
    '<table class="table"><thead><tr><th>Datum</th><th>Raum</th></tr></thead><tbody>' + EMPTY_ROW + "</tbody></table>",
]


@pytest.mark.parametrize("body", UNKNOWN_PAGES)
def test_a_page_without_the_whiteboard_table_stays_unknown_whatever_it_says(body):
    with pytest.raises(WhiteboardShapeError):
        parse_whiteboards(f"<html><body>{MENU}<main>{body}</main></body></html>")


def test_a_table_without_rows_and_without_the_empty_notice_stays_unknown():
    with pytest.raises(WhiteboardShapeError):
        parse_whiteboards(page(""))


def test_a_table_whose_rows_carry_neither_title_nor_link_stays_unknown_and_is_logged_once(caplog):
    exercises._NOTED.clear()
    rows = "<tr><td></td><td></td><td>Kim</td><td>01.10.2026</td><td></td></tr>"
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            with pytest.raises(WhiteboardShapeError):
                parse_whiteboards(page(rows))
    assert sum("whiteboard rows unreadable" in record.getMessage() for record in caplog.records) == 1


def test_whiteboard_keys_and_pages():
    assert whiteboard_key("/iserv/excalidraw/7f3a/") == "7f3a"
    assert whiteboard_key("/iserv/excalidraw/add") == ""
    assert whiteboard_key("/iserv/excalidraw/") == ""
    assert is_whiteboard_page("/iserv/excalidraw/")
    assert is_whiteboard_page("/iserv/excalidraw")
    assert not is_whiteboard_page("/iserv/excalidrawing")
    assert WHITEBOARDS_PATH == "/iserv/excalidraw/"


class Pages:
    def __init__(self, html, status=200, final=WHITEBOARDS_PATH):
        self.html = html
        self.status = status
        self.final = final
        self.paths = []

    def fetch(self, path, params=None):
        self.paths.append(path)
        return Answer(self.status, BASE + self.final, self.html)


def test_the_whiteboard_list_is_read_from_the_module_page():
    client = Pages(page(row("7f3a", "Bruchrechnen", "Kim", "01.10.2026", "02.10.2026")))
    listed = account_lists.read_whiteboards(client)
    assert client.paths == ["/iserv/excalidraw/"]
    assert [board["id"] for board in listed["whiteboards"]] == ["7f3a"]
    assert listed["carry"] == []


def test_an_unreadable_whiteboard_page_is_a_data_error_and_a_refusal_stays_a_refusal():
    with pytest.raises(DataError):
        account_lists.read_whiteboards(Pages("<html><body><p>Tafeln</p></body></html>"))
    with pytest.raises(DataError):
        account_lists.read_whiteboards(Pages(page(EMPTY_ROW), final="/iserv/"))
    with pytest.raises(ModulePageRefusedError):
        account_lists.read_whiteboards(Pages("", status=403))


def test_the_module_is_found_by_its_menu_segment_and_confirmed_by_its_own_page():
    assert modules.SEGMENTS["excalidraw"] == (modules.WHITEBOARDS,)
    assert modules.PROBES[modules.WHITEBOARDS] == ("/iserv/excalidraw/", None)
    assert modules.WHITEBOARDS in modules.CONFIRMED_ONLY
    assert modules.split_links(modules.harvest_links('<a href="/iserv/excalidraw/">Tafeln</a>')) == ([], [])


class BoardConnection:
    def __init__(self, connection_id, boards=None, failure=None):
        self.id = connection_id
        self.boards = boards or []
        self.failure = failure

    def forums(self):
        return {"forums": [], "carry": [], "mark_read": False, "complete": True}

    def infodisplay(self):
        return {"infodisplay": [], "carry": []}

    def whiteboards(self):
        if self.failure is not None:
            raise self.failure
        return {"whiteboards": [dict(board) for board in self.boards], "carry": []}


BOARD = {"id": "7f3a", "title": "Bruchrechnen", "owner": "Kim", "created": "2026-10-01", "created_text": "", "changed": "", "changed_text": "", "path": "/iserv/excalidraw/7f3a"}


def poller_for(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    pushes = []
    poller = Poller(None, store=store, notifiers={"forums": lambda name, message: pushes.append(message) or True})
    poller.clock = lambda: 1_791_000_000
    return poller, store, connection_id, pushes


def test_whiteboards_are_stored_per_school_without_push_and_dropped_when_switched_off(tmp_path):
    poller, store, connection_id, pushes = poller_for(tmp_path)
    connection = BoardConnection(connection_id, [BOARD])
    flags = {modules.WHITEBOARDS: True}
    events = account_poll.poll_account_lists(poller, connection, connection_id, flags, {}, "en")
    assert events == [{"module": "whiteboards", "items": 1}]
    stored = store.load_calendar_snapshot()["whiteboards"][connection_id]
    assert stored["whiteboards"] == [BOARD] and stored["last_success"] == 1_791_000_000
    assert pushes == []
    account_poll.poll_account_lists(poller, connection, connection_id, {modules.WHITEBOARDS: False}, {}, "en")
    assert connection_id not in store.load_calendar_snapshot()["whiteboards"]


def test_a_refused_whiteboard_page_drops_the_list_and_an_unreadable_one_keeps_it(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    flags = {modules.WHITEBOARDS: True}
    account_poll.poll_account_lists(poller, BoardConnection(connection_id, [BOARD]), connection_id, flags, {}, "en")
    unreadable = BoardConnection(connection_id, failure=DataError("whiteboard table carries no readable row"))
    events = account_poll.poll_account_lists(poller, unreadable, connection_id, flags, {}, "en")
    assert [event["module"] for event in events] == ["whiteboards"] and events[0].get("state") != "refused"
    assert store.load_calendar_snapshot()["whiteboards"][connection_id]["whiteboards"] == [BOARD]
    refused = BoardConnection(connection_id, failure=ModulePageRefusedError("403"))
    assert account_poll.poll_account_lists(poller, refused, connection_id, flags, {}, "en") == [{"module": "whiteboards", "state": "refused"}]
    assert connection_id not in store.load_calendar_snapshot()["whiteboards"]


def stored_service(tmp_path, boards):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    account_poll.poll_account_lists(poller, BoardConnection(connection_id, boards), connection_id, {modules.WHITEBOARDS: True}, {}, "en")
    service = IServService(store)
    service.connections()[0].store.save_modules({"modules": {modules.WHITEBOARDS: True}})
    return service, connection_id


def test_the_service_lists_the_stored_whiteboards_with_their_school(tmp_path):
    service, connection_id = stored_service(tmp_path, [BOARD])
    listed = service.whiteboards()
    assert [board["title"] for board in listed["whiteboards"]] == ["Bruchrechnen"]
    assert listed["whiteboards"][0]["connection_id"] == connection_id
    assert listed["schools"][0]["last_success"] == 1_791_000_000
    assert listed["unavailable"] == [] and listed["unreadable"] == []


def test_the_route_serves_the_stored_whiteboards(tmp_path):
    service, _connection_id = stored_service(tmp_path, [BOARD])
    body = TestClient(create_app(service)).get("/api/whiteboards").json()
    assert [board["id"] for board in body["whiteboards"]] == ["7f3a"]


def test_a_notice_row_beside_embedded_list_data_is_unreadable_not_empty():
    loading = '<tr><td colspan="5">Lade ...</td></tr>'
    html = page(loading).replace("</main>", '<script type="application/json" id="board-data">{"data": [{"id": 1}]}</script></main>')
    with pytest.raises(WhiteboardShapeError):
        parse_whiteboards(html)


def test_the_id_is_the_first_segment_after_the_module_path():
    assert whiteboard_key("/iserv/excalidraw/7f3a/show") == "7f3a"
    assert whiteboard_key("/iserv/excalidraw/show/7f3a") == "7f3a"
    assert whiteboard_key("/iserv/excalidraw/delete") == ""
    shared = (
        '<tr><td></td><td><a href="/iserv/excalidraw/aa11/show">Erste</a></td><td>A</td><td>01.10.2026</td><td></td></tr>'
        '<tr><td></td><td><a href="/iserv/excalidraw/bb22/show">Zweite</a></td><td>B</td><td>02.10.2026</td><td></td></tr>'
    )
    assert [board["id"] for board in parse_whiteboards(page(shared))["whiteboards"]] == ["aa11", "bb22"]


def test_an_action_link_is_never_kept_as_the_path_of_a_board():
    only_action = '<tr><td></td><td>Ohne Link</td><td>A</td><td>01.10.2026</td><td><a href="/iserv/excalidraw/cc33/delete">Löschen</a></td></tr>'
    board = parse_whiteboards(page(only_action))["whiteboards"][0]
    assert board["title"] == "Ohne Link"
    assert board["path"] == ""
