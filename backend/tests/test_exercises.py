import logging

import pytest

from app.iserv import exercises
from app.iserv.exercises import ExerciseShapeError, map_columns, parse_exercises, parse_moment

GERMAN_HEAD = """
<thead><tr>
  <th><input type="checkbox" class="select-all"></th>
  <th>Aufgabe</th><th>Starttermin</th><th>Abgabetermin</th><th>Tags</th><th>Erledigt</th>
</tr></thead>
"""

GERMAN_ROWS = """
<tbody>
<tr>
  <td><input type="checkbox" name="exercise[]" value="101"></td>
  <td><a href="/iserv/exercise/show/101">Read chapter three and write a very long summary that wraps</a></td>
  <td data-sort="2026-10-01 08:00">01.10.2026 08:00</td>
  <td>15.10.2026 23:59</td>
  <td><span class="label label-default">Maths</span> <span class="label label-default">Homework</span></td>
  <td><i class="fa fa-check text-success"></i></td>
</tr>
<tr>
  <td><input type="checkbox" name="exercise[]" value="102"></td>
  <td><a href="https://school.example/iserv/exercise/show/102">Poster</a></td>
  <td>02.10.2026</td>
  <td>20.10.2026</td>
  <td></td>
  <td>Nein</td>
</tr>
</tbody>
"""


def page(head, rows, table_id="crud-table", extra=""):
    return f"""<html><body><nav class="navbar"><a href="/iserv/">Home</a></nav>
    <form class="form-inline list-filter"><input name="filter[search]"><select name="filter[tag][]"></select></form>
    <table id="{table_id}" class="table table-striped">{head}{rows}</table>{extra}</body></html>"""


def test_german_headers_map_every_column_and_read_both_tasks():
    parsed = parse_exercises(page(GERMAN_HEAD, GERMAN_ROWS))
    first, second = parsed["tasks"]
    assert parsed["labels"] == ["", "Aufgabe", "Starttermin", "Abgabetermin", "Tags", "Erledigt"]
    assert first == {
        "id": "101",
        "title": "Read chapter three and write a very long summary that wraps",
        "start": "2026-10-01T08:00",
        "start_text": "01.10.2026 08:00",
        "due": "2026-10-15T23:59",
        "due_text": "15.10.2026 23:59",
        "tags": ["Maths", "Homework"],
        "done": True,
        "done_text": "",
        "past": False,
        "path": "/iserv/exercise/show/101",
        "extra": [],
    }
    assert second["id"] == "102"
    assert second["path"] == "/iserv/exercise/show/102"
    assert second["start"] == "2026-10-02"
    assert second["due"] == "2026-10-20"
    assert second["tags"] == []
    assert second["done"] is False


def test_english_headers_in_another_order_with_an_unknown_column_keep_that_column():
    head = "<thead><tr><th>Due date</th><th>Tags</th><th>Task</th><th>Teacher</th><th>Start date</th><th>Done</th></tr></thead>"
    rows = """<tbody><tr>
      <td>2026-11-03</td><td>Art</td><td><a href="/iserv/exercise/show/7">Sketch</a></td>
      <td>Teacher A</td><td>2026-10-27</td><td>Yes</td></tr></tbody>"""
    task = parse_exercises(page(head, rows))["tasks"][0]
    assert task["title"] == "Sketch"
    assert task["due"] == "2026-11-03"
    assert task["start"] == "2026-10-27"
    assert task["tags"] == ["Art"]
    assert task["done"] is True
    assert task["extra"] == [{"label": "Teacher", "value": "Teacher A"}]


def test_missing_columns_leave_their_fields_empty():
    head = "<thead><tr><th>Aufgabe</th><th>Abgabe</th></tr></thead>"
    rows = '<tbody><tr><td><a href="/iserv/exercise/show/9">Essay</a></td><td>05.11.2026</td></tr></tbody>'
    task = parse_exercises(page(head, rows))["tasks"][0]
    assert (task["title"], task["start"], task["due"], task["tags"], task["done"]) == ("Essay", "", "2026-11-05", [], None)


def test_an_empty_list_with_only_the_header_row_reads_no_task():
    assert parse_exercises(page(GERMAN_HEAD, "<tbody></tbody>"))["tasks"] == []


def test_an_empty_state_row_is_not_a_task():
    rows = '<tbody><tr><td colspan="6" class="dataTables_empty">Keine Einträge vorhanden</td></tr></tbody>'
    assert parse_exercises(page(GERMAN_HEAD, rows))["tasks"] == []


def test_the_past_list_marks_its_tasks_past():
    parsed = parse_exercises(page(GERMAN_HEAD, GERMAN_ROWS), exercises.PAST_EXERCISE_PATH, past=True)
    assert [task["past"] for task in parsed["tasks"]] == [True, True]


def test_a_row_without_a_detail_link_still_counts_with_a_stable_id():
    rows = "<tbody><tr><td></td><td>Bring a pencil</td><td>01.10.2026</td><td>02.10.2026</td><td></td><td></td></tr></tbody>"
    first = parse_exercises(page(GERMAN_HEAD, rows))["tasks"]
    second = parse_exercises(page(GERMAN_HEAD, rows))["tasks"]
    assert first[0]["title"] == "Bring a pencil"
    assert first[0]["path"] == ""
    assert first[0]["id"].startswith("h")
    assert first[0]["id"] == second[0]["id"]


def test_a_table_without_a_header_row_maps_by_position():
    rows = '<tr><td><a href="/iserv/exercise/show/4">Quiz</a></td><td>01.10.2026</td><td>08.10.2026</td></tr>'
    task = parse_exercises(page("", rows))["tasks"][0]
    assert (task["title"], task["start"], task["due"]) == ("Quiz", "2026-10-01", "2026-10-08")


def test_a_page_without_the_task_table_raises_and_is_logged_once(caplog):
    exercises._NOTED.clear()
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            with pytest.raises(ExerciseShapeError):
                parse_exercises("<html><body><p>Nothing</p></body></html>", "/iserv/exercise/past/exercise")
    noted = [record.getMessage() for record in caplog.records if "shape unknown" in record.getMessage()]
    assert noted == ["exercise page shape unknown at /iserv/exercise/past/exercise: no task table"]


def test_a_table_without_the_crud_id_is_found_by_its_detail_links():
    rows = '<tbody><tr><td><a href="/iserv/exercise/show/5">Lab report</a></td></tr></tbody>'
    assert parse_exercises(page("<thead><tr><th>Aufgabe</th></tr></thead>", rows, table_id="other"))["tasks"][0]["id"] == "5"


def test_pagination_links_of_the_same_list_are_returned_once():
    extra = """<ul class="pagination"><li><a href="/iserv/exercise?page=2">2</a></li>
      <li><a href="/iserv/exercise?page=2">next</a></li><li><a href="/iserv/mail?page=2">x</a></li></ul>"""
    assert parse_exercises(page(GERMAN_HEAD, GERMAN_ROWS, extra=extra))["pages"] == ["/iserv/exercise?page=2"]


def test_the_same_detail_link_twice_is_one_task():
    rows = GERMAN_ROWS.replace("show/102", "show/101")
    assert [task["id"] for task in parse_exercises(page(GERMAN_HEAD, rows))["tasks"]] == ["101"]


@pytest.mark.parametrize(
    "labels, expected",
    [
        (["Aufgabe", "Starttermin", "Abgabetermin", "Tags", "Erledigt"], ["title", "start", "due", "tags", "done"]),
        (["Title ▲", "Start:", "Due", "Labels", "Status"], ["title", "start", "due", "tags", "done"]),
        (["", "Aufgabe", "Erstellt von"], [None, "title", None]),
    ],
)
def test_column_labels_map_case_and_noise_tolerant(labels, expected):
    mapping = map_columns(labels)
    assert [mapping.get(index) for index in range(len(labels))] == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("01.10.2026", "2026-10-01"),
        ("1.2.2026, 9:05", "2026-02-01T09:05"),
        ("2026-10-01 08:00", "2026-10-01T08:00"),
        ("13/10/2026", "2026-10-13"),
        ("10/13/2026 3:30 pm", "2026-10-13T15:30"),
        ("05/06/2026", ""),
        ("31.02.2026", ""),
        ("soon", ""),
        ("", ""),
    ],
)
def test_moments_parse_german_iso_and_unambiguous_slash_dates(text, expected):
    assert parse_moment(text) == expected


@pytest.mark.parametrize(
    "labels, expected",
    [
        (["Aufgabe", "Lehrende", "Abgabe"], ["title", None, "due"]),
        (["Aufgabe", "Lehrende", "Ende"], ["title", None, "due"]),
        (["Hausaufgabe", "Unterrichtsbeginn", "Endabgabe", "Bearbeitungsstatus"], ["title", "start", "due", "done"]),
        (["Aufgabe", "Abgabe bis", "Erstellt von"], ["title", "due", None]),
        (["Aufgabentitel", "Kalender", "Legende"], ["title", None, None]),
    ],
)
def test_labels_match_whole_words_and_compound_endings_only(labels, expected):
    mapping = map_columns(labels)
    assert [mapping.get(index) for index in range(len(labels))] == expected


def test_a_teacher_column_is_kept_as_extra_and_not_read_as_due_date():
    head = "<thead><tr><th>Aufgabe</th><th>Lehrende</th><th>Abgabe</th></tr></thead>"
    rows = '<tbody><tr><td><a href="/iserv/exercise/show/3">Essay</a></td><td>Teacher B</td><td>05.11.2026</td></tr></tbody>'
    task = parse_exercises(page(head, rows))["tasks"][0]
    assert task["due"] == "2026-11-05"
    assert task["extra"] == [{"label": "Lehrende", "value": "Teacher B"}]


def test_a_row_without_a_detail_link_keeps_its_id_when_due_date_or_state_change():
    before = "<tbody><tr><td></td><td>Bring a pencil</td><td>01.10.2026</td><td>02.10.2026</td><td></td><td>Nein</td></tr></tbody>"
    after = "<tbody><tr><td></td><td>Bring a pencil</td><td>01.10.2026</td><td>09.10.2026</td><td></td><td>Ja</td></tr></tbody>"
    first = parse_exercises(page(GERMAN_HEAD, before))["tasks"][0]
    second = parse_exercises(page(GERMAN_HEAD, after))["tasks"][0]
    assert first["due"] != second["due"]
    assert first["id"] == second["id"]


def test_two_rows_without_links_and_the_same_title_are_both_kept():
    row = "<tr><td></td><td>Bring a pencil</td><td>01.10.2026</td><td>02.10.2026</td><td></td><td></td></tr>"
    tasks = parse_exercises(page(GERMAN_HEAD, "<tbody>" + row + row + "</tbody>"))["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["id"] != tasks[1]["id"]


@pytest.mark.parametrize("href", ["?page=2", "./exercise?page=2", "exercise?page=2", "/iserv/exercise/?page=2"])
def test_relative_pagination_links_resolve_against_the_list(href):
    extra = f'<ul class="pagination"><li><a href="{href}">2</a></li></ul>'
    assert parse_exercises(page(GERMAN_HEAD, GERMAN_ROWS, extra=extra))["pages"] == ["/iserv/exercise?page=2"]


def test_the_first_page_link_is_the_list_itself():
    extra = """<ul class="pagination"><li><a href="/iserv/exercise?page=1">1</a></li>
      <li><a href="?page=2">2</a></li></ul>"""
    assert parse_exercises(page(GERMAN_HEAD, GERMAN_ROWS, extra=extra))["pages"] == ["/iserv/exercise?page=2"]
