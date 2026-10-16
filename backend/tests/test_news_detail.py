from types import SimpleNamespace

import pytest

from app import school_lists
from app.iserv.errors import DataError
from app.iserv.news_detail import detail_shape, parse_news_detail
from tests.test_refused_probes import Answer

BASE = "https://school.example"
ITEM = "/iserv/news/general/12"
NAV = """<nav class="navbar"><a href="/iserv/">Home</a><a href="/iserv/news">News</a></nav>
<ol class="breadcrumb"><li><a href="/iserv/news">News</a></li><li>Library</li></ol>"""

ARTICLE = f"""<html><body>{NAV}<div class="container"><article class="news-show">
<h1>Library opens later</h1><p class="text-muted"><time datetime="2026-10-03">03.10.2026</time> · <a href="/iserv/news/general">General</a></p>
<p>From <b>Monday</b> the library opens at nine.</p><p>Bring your card.<br>Ask at the desk.</p>
<img src="/iserv/news/image/abc" alt="Front door"><img src="data:image/png;base64,AAAA">
<p><a href="/iserv/file/download/Groups/info.pdf">Opening hours</a> <a href="https://example.org/library">Library site</a>
<a href="/iserv/news">Back</a> <a href="mailto:office@example.org">Mail</a></p>
</article><form action="/iserv/news/comment"><textarea></textarea><button>Send</button></form></div></body></html>"""

PANEL = f"""<html><body>{NAV}<div class="panel panel-default"><div class="panel-heading"><h3 class="panel-title">Sports day</h3></div>
<div class="panel-body">Line one<br>Line <i>two</i><br><br>Line three<dl><dt>Where</dt><dd>Field</dd></dl>
<a href="files/plan.docx">Plan</a></div></div></body></html>"""


def test_an_article_reads_text_images_files_and_links_without_page_parts():
    detail = parse_news_detail(ARTICLE, ITEM, "Library opens later")
    assert detail["lines"] == [
        "03.10.2026 · General",
        "From Monday the library opens at nine.",
        "Bring your card.",
        "Ask at the desk.",
        "Opening hours Library site Back Mail",
    ]
    assert detail["images"] == [{"href": "/iserv/news/image/abc", "label": "Front door"}]
    assert detail["files"] == [{"href": "/iserv/file/download/Groups/info.pdf", "label": "Opening hours"}]
    assert detail["links"] == [{"href": "https://example.org/library", "label": "Library site"}]


def test_a_panel_layout_keeps_line_breaks_inline_words_and_definition_lists():
    detail = parse_news_detail(PANEL, "/iserv/news/sport/13", "Sports day")
    assert detail["lines"] == ["Line one", "Line two", "Line three", "Where", "Field", "Plan"]
    assert detail["files"] == [{"href": "/iserv/news/sport/files/plan.docx", "label": "Plan"}]


@pytest.mark.parametrize("html", ["", "<html><body></body></html>", "<html><body><nav>Menu</nav></body></html>"])
def test_unknown_markup_reads_an_empty_detail(html):
    assert parse_news_detail(html, ITEM) == {"lines": [], "images": [], "files": [], "links": []}


def test_broken_markup_does_not_crash():
    assert parse_news_detail("<<<not html", ITEM)["images"] == []


def test_a_very_long_text_is_cut_at_the_limit():
    html = "<article>" + "".join("<p>%s</p>" % ("word%d " % number * 60) for number in range(200)) + "</article>"
    lines = parse_news_detail(html, ITEM)["lines"]
    assert 0 < sum(len(line) for line in lines) <= 12000


def test_the_shape_names_structure_and_counts_only():
    shape = detail_shape(ARTICLE, ITEM)
    assert shape["tag"] == "article"
    assert shape["classes"] == ["news-show"]
    assert (shape["lines"], shape["images"], shape["files"], shape["links"]) == (6, 1, 1, 1)
    assert shape["time_tag"] is True and shape["definition_list"] is False
    assert "Library" not in repr(shape)


class Pages:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def fetch(self, path, params=None):
        self.asked.append(path)
        return self.answer


def test_the_detail_read_opens_the_item_page_once_and_keeps_school_files_as_paths():
    pages = Pages(Answer(200, BASE + ITEM, ARTICLE))
    detail = school_lists.read_news_detail(pages, BASE, ITEM, "Library opens later")
    assert pages.asked == [ITEM]
    assert detail["text"][1] == "From Monday the library opens at nine."
    assert detail["images"] == [{"label": "Front door", "path": "/iserv/news/image/abc"}]
    assert detail["files"] == [{"label": "Opening hours", "path": "/iserv/file/download/Groups/info.pdf"}]
    assert detail["links"] == [{"label": "Library site", "url": "https://example.org/library"}]
    assert BASE not in repr(detail)


@pytest.mark.parametrize("answer", [Answer(200, BASE + "/iserv/news", "<html></html>"), Answer(404, BASE + ITEM), Answer(200, BASE + "/iserv/auth/login")])
def test_a_detail_that_lands_elsewhere_is_unreadable(answer):
    with pytest.raises(DataError):
        school_lists.read_news_detail(Pages(answer), BASE, ITEM)


def test_only_news_item_paths_are_opened():
    pages = Pages(Answer(200, BASE + "/iserv/logout", ""))
    with pytest.raises(DataError):
        school_lists.read_news_detail(pages, BASE, "/iserv/logout")
    assert pages.asked == []


from app.iserv.errors import OutageError
from tests.test_school_lists import NEWS, NEWS_SPEC, HolidaysStub, ListConnection, poller_for
from app import integration


class DetailConnection(ListConnection):
    def __init__(self, connection_id, news, failures=None):
        super().__init__(connection_id, news=news)
        self.opened = []
        self.failures = failures or {}

    def news_detail(self, path, title=""):
        self.opened.append(path)
        failure = self.failures.get(path)
        if failure is not None:
            raise failure
        return {"text": ["Text of " + title], "images": [], "files": [], "links": []}


def news_item(number, **changes):
    item = dict(NEWS, id="general/%d" % number, title="Item %d" % number, path="/iserv/news/general/%d" % number)
    return dict(item, **changes)


def stored_news(store, connection_id):
    return store.load_calendar_snapshot()["news"][connection_id]["news"]


def test_each_detail_is_opened_once_and_again_only_when_the_list_entry_changes(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    first = DetailConnection(connection_id, [news_item(1), news_item(2)])
    poller._poll_school_list(first, connection_id, True, NEWS_SPEC, state, "en")
    assert first.opened == ["/iserv/news/general/1", "/iserv/news/general/2"]
    assert stored_news(store, connection_id)[0]["detail"]["text"] == ["Text of Item 1"]
    same = DetailConnection(connection_id, [news_item(1), news_item(2)])
    poller._poll_school_list(same, connection_id, True, NEWS_SPEC, state, "en")
    assert same.opened == []
    changed = DetailConnection(connection_id, [news_item(1, title="Item 1 updated"), news_item(2)])
    poller._poll_school_list(changed, connection_id, True, NEWS_SPEC, state, "en")
    assert changed.opened == ["/iserv/news/general/1"]
    assert stored_news(store, connection_id)[0]["detail"]["text"] == ["Text of Item 1 updated"]


def test_details_are_opened_at_most_ten_per_poll_and_the_rest_follows(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    items = [news_item(number) for number in range(1, 15)]
    first = DetailConnection(connection_id, items)
    poller._poll_school_list(first, connection_id, True, NEWS_SPEC, state, "en")
    second = DetailConnection(connection_id, items)
    poller._poll_school_list(second, connection_id, True, NEWS_SPEC, state, "en")
    assert len(first.opened) == 10
    assert second.opened == ["/iserv/news/general/%d" % number for number in range(11, 15)]
    assert all("detail" in item for item in stored_news(store, connection_id))


def test_an_outage_pauses_the_details_and_an_unreadable_one_is_not_asked_again(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    state = {}
    failures = {"/iserv/news/general/1": DataError("gone"), "/iserv/news/general/2": OutageError("rate_limited")}
    first = DetailConnection(connection_id, [news_item(1), news_item(2), news_item(3)], failures)
    poller._poll_school_list(first, connection_id, True, NEWS_SPEC, state, "en")
    assert first.opened == ["/iserv/news/general/1", "/iserv/news/general/2"]
    assert [item.get("detail") for item in stored_news(store, connection_id)] == [{"unreadable": True}, None, None]
    second = DetailConnection(connection_id, [news_item(1), news_item(2), news_item(3)])
    poller._poll_school_list(second, connection_id, True, NEWS_SPEC, state, "en")
    assert second.opened == ["/iserv/news/general/2", "/iserv/news/general/3"]


def test_home_assistant_gets_the_start_of_the_news_text(tmp_path):
    poller, store, connection_id, _pushes = poller_for(tmp_path)
    poller._poll_school_list(DetailConnection(connection_id, [news_item(1)]), connection_id, True, NEWS_SPEC, {}, "en")
    school = integration.build_school(store, HolidaysStub(), 1_791_000_000, connection_id)
    assert school["news"]["items"][0]["text"] == "Text of Item 1"


STORED = [dict(NEWS, id="general/12", detail={
    "text": [], "links": [{"label": "Site", "url": "https://example.org/"}],
    "files": [{"label": "Plan", "path": "/iserv/file/download/plan.pdf"}, {"label": "Odd", "path": "/iserv/../logout"}],
    "images": [{"label": "Door", "path": "/iserv/news/image/abc"}],
})]


@pytest.mark.parametrize(
    "item, kind, index, expected",
    [
        ("general/12", "files", 0, "/iserv/file/download/plan.pdf"),
        ("general/12", "images", 0, "/iserv/news/image/abc"),
        ("general/12", "files", 1, ""),
        ("general/12", "files", 2, ""),
        ("general/12", "links", 0, ""),
        ("general/99", "files", 0, ""),
        ("general/12", "files", -1, ""),
    ],
)
def test_only_files_and_images_stored_with_a_news_item_can_be_fetched(item, kind, index, expected):
    assert school_lists.news_file_path(STORED, item, kind, index) == expected


class FilePages:
    def __init__(self, answer):
        self.answer = answer

    def fetch_file(self, path, limit, timeout=60):
        return SimpleNamespace(status_code=self.answer.status_code, url=self.answer.url, headers={}, content=b"", truncated=False)


@pytest.mark.parametrize("answer", [Answer(404, BASE + "/iserv/file/download/plan.pdf"), Answer(200, BASE + "/iserv/auth/login")])
def test_a_news_file_that_is_not_served_is_an_error(answer):
    with pytest.raises(DataError):
        school_lists.read_school_file(FilePages(answer), "/iserv/file/download/plan.pdf", BASE)


def test_the_app_serves_a_stored_news_file_through_ranzenpost(tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app
    from app.service import IServService
    from app.store import Store
    from tests.support import add_school

    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    school_lists.store_list(store, connection_id, "news", STORED, 1)
    asked = []

    class FileAnswer:
        status_code = 200
        url = BASE + "/iserv/file/download/plan.pdf"
        content = b"%PDF-1.4"
        headers = {"content-type": "application/pdf", "content-disposition": 'attachment; filename="plan.pdf"'}

    service = IServService(store)
    connection = service.connections()[0]
    answer = SimpleNamespace(status_code=200, url=FileAnswer.url, headers=FileAnswer.headers, content=FileAnswer.content, truncated=False)
    connection._session = lambda: type("Client", (), {"fetch_file": lambda self, path, limit, timeout=60: asked.append(path) or answer})()
    client = TestClient(create_app(service=service))
    answer = client.get("/api/news/file", params={"connection": connection_id, "item": "general/12", "kind": "files", "index": 0})
    assert answer.status_code == 200
    assert answer.content == b"%PDF-1.4"
    assert answer.headers["content-type"] == "application/pdf"
    assert asked == ["/iserv/file/download/plan.pdf"]
    refused = client.get("/api/news/file", params={"connection": connection_id, "item": "general/12", "kind": "links", "index": 0})
    assert refused.status_code == 400
    assert asked == ["/iserv/file/download/plan.pdf"]
