import json
import logging

import pytest

from app import account_lists
from app.iserv import exercises
from app.iserv.errors import DataError, LoginError
from app.iserv.texts import TEXTS_PATH, TextShapeError, is_text_page, parse_texts, text_key
from tests.test_refused_probes import Answer

BASE = "https://school.example"


def row(key, title, owner="Kim Muster", changed="20261007224700", created="20260901080000", tags=()):
    return {
        "_multi_select": f'<input type="checkbox" name="iserv_crud_multi_select[multi][]" value="{key}">',
        "title": {"value": title, "html": f'<a href="/iserv/etherpad/{key}">{title}</a>', "type": "property"},
        "owner": {"value": owner, "display": owner, "type": "entity"},
        "lastChangeAt": {"value": changed, "display": "07.10.2026 22:47", "type": "datetime"},
        "created": {"value": created, "display": "01.09.2026 08:00", "type": "datetime"},
        "tags": {"value": list(tags), "display": ", ".join(tags), "type": "tags"},
    }


FILTER = (
    '<form method="get" class="form-inline list-filter"><select name="filter[Default]">'
    '<option value="visible" selected>Sichtbare</option><option value="hidden">Ausgeblendete</option>'
    '<option value="own">Meine Texte</option><option value="all">Alle</option></select>'
    '<select name="filter[etherpad_filter_tag][]" multiple></select><input name="filter[search]"></form>'
)


def page(rows, extra=FILTER):
    data = json.dumps({"data": rows})
    return (
        f'<html><body>{extra}<table id="crud-table" class="table table-striped"><thead><tr><th>Titel</th>'
        f'<th>Besitzer</th><th>Letzte Änderung</th></tr></thead></table>'
        f'<script type="application/json" id="crud-data">{data}</script>'
        f'<script type="application/json" id="current-user">{{"displayName": "x"}}</script></body></html>'
    )


def test_the_embedded_data_gives_title_owner_times_tags_and_the_text_page():
    parsed = parse_texts(page([row("a1b2", "Protokoll Elternabend", tags=("Klasse 5", "Wichtig"))]))
    assert parsed["texts"] == [{
        "id": "a1b2",
        "title": "Protokoll Elternabend",
        "owner": "Kim Muster",
        "changed": "2026-10-07T22:47",
        "changed_text": "07.10.2026 22:47",
        "created": "2026-09-01T08:00",
        "created_text": "01.09.2026 08:00",
        "tags": ["Klasse 5", "Wichtig"],
        "path": "/iserv/etherpad/a1b2",
    }]
    assert parsed["filter_field"] == "filter[Default]"
    assert [(choice["value"], choice["selected"]) for choice in parsed["filters"]] == [
        ("visible", True), ("hidden", False), ("own", False), ("all", False),
    ]


def test_tags_given_as_objects_and_a_row_without_link_still_read():
    entry = row("x", "Ideen", tags=())
    entry["tags"]["value"] = [{"name": "Projekt"}, {"title": "Kunst"}, "Projekt"]
    entry["title"] = {"value": "Ideen", "type": "property"}
    entry["_multi_select"] = '<input type="checkbox" value="77">'
    text = parse_texts(page([entry]))["texts"][0]
    assert text["tags"] == ["Projekt", "Kunst"]
    assert text["id"] == "77"
    assert text["path"] == ""


def test_an_empty_data_list_is_an_empty_list():
    assert parse_texts(page([]))["texts"] == []


def test_a_page_without_embedded_data_is_unreadable_and_logged_once(caplog):
    exercises._NOTED.clear()
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            with pytest.raises(TextShapeError):
                parse_texts("<html><body><table id='crud-table'></table></body></html>")
    assert sum("no embedded text data" in record.getMessage() for record in caplog.records) == 1


@pytest.mark.parametrize("path, key", [
    ("/iserv/etherpad/a1b2", "a1b2"),
    ("/iserv/etherpad/add", ""),
    ("/iserv/etherpad/a1b2/confirm", ""),
    ("/iserv/etherpad", ""),
])
def test_text_keys(path, key):
    assert text_key(path) == key


def test_text_pages():
    assert is_text_page("/iserv/etherpad") and is_text_page("/iserv/etherpad/x")
    assert not is_text_page("/iserv/etherpadx")


class FilterPages:
    def __init__(self, pages, failing=()):
        self.pages = pages
        self.failing = set(failing)
        self.asked = []

    def fetch(self, path, params=None):
        value = (params or {}).get("filter[Default]", "")
        self.asked.append(value)
        if value in self.failing:
            return Answer(500, BASE + path, "")
        return Answer(200, BASE + path, self.pages[value])


def test_every_iserv_filter_is_read_so_hidden_texts_are_listed_and_the_filter_is_set_back():
    pages = FilterPages({
        "": page([row("a", "Sichtbar")]),
        "hidden": page([row("b", "Versteckt")]),
        "own": page([row("a", "Sichtbar")]),
        "all": page([row("a", "Sichtbar"), row("b", "Versteckt")]),
        "visible": page([row("a", "Sichtbar")]),
    })
    listed = account_lists.read_texts(pages)
    assert [(text["id"], text["filters"]) for text in listed["texts"]] == [
        ("a", ["visible", "own", "all"]),
        ("b", ["hidden", "all"]),
    ]
    assert listed["filters"] == [
        {"value": "visible", "label": "Sichtbare", "default": True},
        {"value": "hidden", "label": "Ausgeblendete", "default": False},
        {"value": "own", "label": "Meine Texte", "default": False},
        {"value": "all", "label": "Alle", "default": False},
    ]
    assert listed["carry"] == []
    assert pages.asked == ["", "hidden", "own", "all", "visible"]


def test_a_failing_filter_page_keeps_the_rest_and_asks_to_carry_earlier_texts():
    pages = FilterPages({"": page([row("a", "Sichtbar")]), "own": page([]), "all": page([]), "visible": page([])}, failing={"hidden"})
    listed = account_lists.read_texts(pages)
    assert [text["id"] for text in listed["texts"]] == ["a"]
    assert listed["carry"] == ["current"]


def test_a_list_without_filters_is_read_once():
    pages = FilterPages({"": page([row("a", "Eins")], extra="")})
    listed = account_lists.read_texts(pages)
    assert [text["filters"] for text in listed["texts"]] == [[]]
    assert listed["filters"] == []
    assert pages.asked == [""]


def test_an_unreadable_first_page_is_an_error():
    with pytest.raises(DataError):
        account_lists.read_texts(FilterPages({"": "<html><body></body></html>"}))


def test_a_text_without_link_keeps_its_id_when_it_is_renamed():
    first = row("x", "Ideen", owner="Kim Muster", created="20260901080000")
    for entry in (first,):
        entry["title"] = {"value": "Ideen", "type": "property"}
        entry["_multi_select"] = ""
    renamed = json.loads(json.dumps(first))
    renamed["title"]["value"] = "Ideen für das Fest"
    other = json.loads(json.dumps(first))
    other["owner"]["value"] = "Sam Beispiel"
    one = parse_texts(page([first]))["texts"][0]["id"]
    assert parse_texts(page([renamed]))["texts"][0]["id"] == one
    assert parse_texts(page([other]))["texts"][0]["id"] != one


MANY = (
    '<form method="get"><select name="filter[Default]">'
    + "".join(f'<option value="f{number}"{" selected" if number == 9 else ""}>F{number}</option>' for number in range(1, 11))
    + "</select></form>"
)


def test_the_active_selection_is_found_before_the_list_is_cut_and_set_back_last():
    pages = {"": page([row("a", "Eins")], extra=MANY)}
    pages.update({f"f{number}": page([row("a", "Eins")], extra=MANY) for number in range(1, 11)})
    reader = account_lists.TextReader()
    listed = reader.read(FilterPages(pages))
    assert [entry["value"] for entry in listed["filters"] if entry["default"]] == ["f9"]
    assert "f9" in [entry["value"] for entry in listed["filters"]]


def test_the_selection_is_set_back_last_even_after_a_sign_in_failure():
    class SignIn(FilterPages):
        def fetch(self, path, params=None):
            if (params or {}).get("filter[Default]") == "hidden":
                self.asked.append("hidden")
                raise LoginError("signed out")
            return super().fetch(path, params)

    pages = SignIn({"": page([row("a", "Eins")]), "visible": page([row("a", "Eins")])})
    with pytest.raises(LoginError):
        account_lists.TextReader().read(pages)
    assert pages.asked[-1] == "visible"


def test_a_failed_set_back_is_a_warning_and_the_standard_stays_unknown_until_the_next_read_sets_it_back(caplog):
    pages = FilterPages({
        "": page([row("a", "Eins")]),
        "hidden": page([row("b", "Zwei")]),
        "own": page([]),
        "all": page([row("a", "Eins"), row("b", "Zwei")]),
    }, failing={"visible"})
    reader = account_lists.TextReader()
    with caplog.at_level(logging.WARNING, logger="app.account_lists"):
        listed = reader.read(pages)
    assert [entry["default"] for entry in listed["filters"]] == [False, False, False, False]
    assert any("not set back" in record.getMessage() for record in caplog.records if record.levelno == logging.WARNING)
    moved = FILTER.replace('<option value="visible" selected>', '<option value="visible">').replace('<option value="all">', '<option value="all" selected>')
    later = FilterPages({
        "": page([row("a", "Eins"), row("b", "Zwei")], extra=moved),
        "visible": page([row("a", "Eins")], extra=moved),
        "hidden": page([row("b", "Zwei")], extra=moved),
        "own": page([], extra=moved),
    })
    again = reader.read(later)
    assert later.asked[-1] == "visible"
    assert [entry["value"] for entry in again["filters"] if entry["default"]] == ["visible"]
    assert [(text["id"], text["filters"]) for text in again["texts"]] == [("a", ["all", "visible"]), ("b", ["all", "hidden"])]


def test_two_reads_of_one_school_never_interleave():
    import threading
    import time

    class Slow(FilterPages):
        def fetch(self, path, params=None):
            self.threads.append(threading.current_thread().name)
            time.sleep(0.005)
            return super().fetch(path, params)

    pages = Slow({"": page([row("a", "Eins")]), "hidden": page([]), "own": page([]), "all": page([]), "visible": page([])})
    pages.threads = []
    reader = account_lists.TextReader()
    workers = [threading.Thread(target=reader.read, args=(pages,), name=name) for name in ("one", "two")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    names = pages.threads
    assert names == sorted(names, key=names.index) and len(set(names[:5])) == 1 and len(set(names[5:])) == 1


def test_link_less_texts_of_one_owner_without_creation_date_stay_apart():
    first = row("x", "Ideen", owner="Kim Muster", created="")
    second = row("y", "Plan", owner="Kim Muster", created="")
    for entry in (first, second):
        entry["title"] = {"value": entry["title"]["value"], "type": "property"}
        entry["_multi_select"] = ""
    listed = parse_texts(page([first, second]))["texts"]
    assert [text["title"] for text in listed] == ["Ideen", "Plan"]
    assert listed[0]["id"] != listed[1]["id"]


def renamed(entry):
    moved = json.loads(json.dumps(entry))
    moved["name"] = moved.pop("title")
    moved["_multi_select"] = ""
    return moved


def test_data_rows_that_cannot_be_read_are_unknown_and_logged_once(caplog):
    exercises._NOTED.clear()
    html = page([renamed(row("a", "Eins")), renamed(row("b", "Zwei"))])
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            with pytest.raises(TextShapeError):
                parse_texts(html)
    assert sum("unreadable" in record.getMessage() for record in caplog.records) == 1


def test_readable_texts_are_kept_beside_unreadable_rows_and_the_skip_is_logged_once(caplog):
    exercises._NOTED.clear()
    html = page([row("a", "Eins"), renamed(row("b", "Geheimer Titel"))])
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            assert [text["title"] for text in parse_texts(html)["texts"]] == ["Eins"]
    lines = [record.getMessage() for record in caplog.records if "skipped" in record.getMessage()]
    assert len(lines) == 1 and "1 unreadable" in lines[0] and "Geheim" not in lines[0]
