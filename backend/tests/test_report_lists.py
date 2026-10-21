from app import diagnostics, modules, reportlists
from app.iserv.exercises import EXERCISE_PATH, PAST_EXERCISE_PATH
from app.iserv.news import NEWS_PATH
from app.pageshape import html_skeleton
from tests.support import Response

SCHOOL = "https://school.example"
TASK_PAGE = """<html><body><table id="crud-table" class="table table-striped">
<thead><tr><th><input type="checkbox"></th><th>Aufgabe</th><th>Starttermin</th><th>Abgabetermin</th><th>Tags</th><th>Klecksfarbe</th></tr></thead>
<tbody><tr><td></td><td><a href="/iserv/exercise/show/31">Secret Homework Title</a></td><td>01.10.2026</td><td>09.10.2026</td>
<td><span class="label">Privatetag</span></td><td>Blau</td></tr></tbody></table></body></html>"""
NEWS_PAGE = """<html><body><h1>Alle News</h1><ul>
<li class="news-entry"><h3><a href="/iserv/news/general/4">Secret News Title</a></h3><time datetime="2026-10-01">01.10.2026</time>
<a href="/iserv/news/general">General</a><p>Body text</p></li></ul></body></html>"""


def test_task_table_headers_show_iserv_words_and_mask_the_rest():
    lines = html_skeleton(TASK_PAGE)
    assert "- Table headers: Aufgabe | Starttermin | Abgabetermin | Tags | <word>" in lines


def test_the_task_list_line_names_the_column_mapping_and_counts_without_titles():
    answers = {EXERCISE_PATH: Response(200, SCHOOL + EXERCISE_PATH, TASK_PAGE)}
    lines = reportlists.list_lines("exercise", answers)
    assert lines == [
        "- Task list /iserv/exercise: columns - | title | start | due | tags | other; "
        "tasks read 1 (with detail link 1, with due date 1, done known 0); more pages 0"
    ]
    assert "Secret" not in "\n".join(lines)


def test_a_page_without_the_task_table_is_named_in_the_report():
    answers = {PAST_EXERCISE_PATH: Response(200, SCHOOL + PAST_EXERCISE_PATH, "<html><body><p>x</p></body></html>")}
    assert reportlists.list_lines("exercise", answers) == ["- Task list /iserv/exercise/past/exercise: no task table found"]


def test_the_news_line_records_the_shape_of_one_item_only():
    lines = reportlists.list_lines("news", {NEWS_PATH: Response(200, SCHOOL + NEWS_PATH, NEWS_PAGE)})
    assert lines == [
        "- News list: items read 1, with date 1, more pages 0",
        "- News sections linked: archive no, packages no",
        "- News item shape: li.news-entry with a x2, h3 x1, p x1, time x1; title yes, date yes, time tag yes, category link yes",
    ]
    assert "Secret" not in "\n".join(lines)


def test_the_report_reads_the_past_task_list_next_to_the_current_one():
    row = next(row for row in diagnostics.module_rows(modules.default_registry()) if row["slug"] == "exercise")
    targets = diagnostics.structure_targets(row, None)
    assert targets[:2] == [(EXERCISE_PATH, None), (PAST_EXERCISE_PATH, None)]
    assert next(row for row in diagnostics.module_rows(modules.default_registry()) if row["slug"] == "news")["page"] == NEWS_PATH


NEWS_DETAIL = """<html><body><nav class="navbar"><a href="/iserv/news">News</a></nav><article class="news-show">
<h1>Secret News Title</h1><time datetime="2026-10-01">01.10.2026</time><p>Secret body sentence.</p>
<img src="/iserv/news/image/1" alt="Secret alt"><a href="/iserv/file/download/secret.pdf">Secret file</a></article></body></html>"""


class DetailClient:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def fetch(self, path, params=None):
        self.asked.append(path)
        return self.answer


def test_the_news_report_opens_one_detail_page_and_records_its_shape_only():
    client = DetailClient(Response(200, SCHOOL + "/iserv/news/general/4", NEWS_DETAIL))
    lines = reportlists.list_lines("news", {NEWS_PATH: Response(200, SCHOOL + NEWS_PATH, NEWS_PAGE)}, client)
    assert client.asked == ["/iserv/news/general/4"]
    assert lines[-1] == (
        "- News detail shape: article.news-show with a x1, h1 x1, img x1, p x1, time x1; "
        "text lines 4, images 1, files 1, links 0, time tag yes, definition list no"
    )
    assert "Secret" not in "\n".join(lines)


def test_a_news_detail_that_moves_elsewhere_is_named_without_a_shape():
    client = DetailClient(Response(200, SCHOOL + NEWS_PATH, NEWS_PAGE))
    lines = reportlists.list_lines("news", {NEWS_PATH: Response(200, SCHOOL + NEWS_PATH, NEWS_PAGE)}, client)
    assert lines[-1].startswith("- News detail ") and "answered 200, final /iserv/news" in lines[-1]


def test_the_page_structure_shows_the_main_text_with_names_masked():
    from app.pageshape import html_skeleton

    html = (
        "<html><body><nav><ul><li>Mail</li></ul></nav>"
        "<div id='content'><h1>Infobildschirm</h1><p>Keine Infobildschirme für Erika Musterfrau, 12 Tage.</p>"
        "<table><tr><td>Geheim</td></tr></table></div></body></html>"
    )
    line = next(line for line in html_skeleton(html) if line.startswith("- Main text:"))

    assert "Keine" in line and "Infobildschirm" in line
    assert "Erika" not in line and "Musterfrau" not in line and "12" not in line and "Geheim" not in line
