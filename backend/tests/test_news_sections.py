from app import school_lists
from app.iserv.errors import DataError, OutageError
from app.iserv.news import NEWS_PATH, section_links
from app.reportlists import list_lines
from tests.test_refused_probes import Answer

BASE = "https://school.example"
MAIN = """<html><body><div class="news-nav"><a href="/iserv/news">Neueste</a><a href="/iserv/news/general">Allgemein</a>
<a href="/iserv/news/archive">Archiv</a><a href="/iserv/news/iserv">Paketnews</a></div>
<ul><li><a href="/iserv/news/general/2">Second</a></li><li><a href="/iserv/news/general/1">First</a></li></ul></body></html>"""
ARCHIVE = """<html><body><ul><li><a href="/iserv/news/general/1">First</a></li><li><a href="/iserv/news/general/0">Zero</a></li></ul></body></html>"""
PACKAGES = """<html><body><ul><li><a href="/iserv/news/iserv/77">Update</a></li></ul></body></html>"""


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def fetch(self, path, params=None):
        self.asked.append(path)
        found = self.pages.get(path)
        if found is None:
            return Answer(404, BASE + path)
        return found if isinstance(found, Answer) else Answer(200, BASE + path, found)


def test_the_archive_and_package_news_are_found_by_their_link_or_their_name():
    assert section_links(MAIN) == {"archive": "/iserv/news/archive", "packages": "/iserv/news/iserv"}
    assert section_links('<a href="/iserv/news/archiv">Alte News</a><a href="/iserv/news/packages">x</a>') == {"archive": "/iserv/news/archiv", "packages": "/iserv/news/packages"}
    assert section_links('<a href="/iserv/news/general">Allgemein</a><a href="/iserv/news/general/3">Archiv</a>') == {}


def test_the_news_list_reads_only_the_main_list_and_remembers_the_section_links():
    pages = Pages({NEWS_PATH: MAIN, "/iserv/news/archive": ARCHIVE, "/iserv/news/iserv": PACKAGES})
    listed = school_lists.read_news(pages)
    assert [(item["id"], item.get("section")) for item in listed["news"]] == [("general/2", None), ("general/1", None)]
    assert listed["sections"] == {"archive": "/iserv/news/archive", "packages": "/iserv/news/iserv"}
    assert pages.asked == [NEWS_PATH]


def test_a_section_is_read_on_its_own_and_its_items_are_marked():
    pages = Pages({"/iserv/news/archive": ARCHIVE})
    items = school_lists.read_news_section(pages, "/iserv/news/archive", "archive")
    assert [(item["id"], item["section"]) for item in items] == [("general/1", "archive"), ("general/0", "archive")]
    for path, section in (("/iserv/news", "archive"), ("/iserv/exercise", "archive"), ("/iserv/news/archive", "other")):
        try:
            school_lists.read_news_section(pages, path, section)
        except DataError:
            continue
        raise AssertionError("%s was read as %s" % (path, section))


def test_stored_section_items_are_dropped_by_the_next_list():
    listed = {"news": [{"id": "general/2"}], "carry": ["current"]}
    stored = [{"id": "general/0", "section": "archive"}, {"id": "iserv/5", "section": "packages"}, {"id": "general/9"}]
    assert [item["id"] for item in school_lists.carried(listed, "news", stored)] == ["general/2", "general/9"]


def test_an_outage_of_the_main_list_still_fails_the_read():
    pages = Pages({NEWS_PATH: Answer(503, BASE + NEWS_PATH)})
    try:
        school_lists.read_news(pages)
    except OutageError:
        return
    raise AssertionError("the outage was swallowed")


def test_the_report_names_the_linked_sections():
    lines = list_lines("news", {NEWS_PATH: Answer(200, BASE + NEWS_PATH, MAIN)})
    assert "- News sections linked: archive yes, packages yes" in lines


def section_service(tmp_path, pages, clock):
    from app import modules
    from app.service import IServService
    from app.store import Store
    from tests.support import add_school

    store = Store(tmp_path / "data")
    connection_id = add_school(store, BASE)
    school_lists.store_list(store, connection_id, "news", [{"id": "general/2", "title": "Second", "path": "/iserv/news/general/2"}], 1, {"sections": {"archive": "/iserv/news/archive"}})
    service = IServService(store)
    connection = service.connections()[0]
    connection.store.save_modules({"modules": {modules.NEWS: True}})
    connection._session = lambda: pages
    connection.clock = clock
    return service, connection_id


def test_the_poll_never_reads_archive_or_package_news_and_home_assistant_sees_only_the_main_list(tmp_path):
    from app import integration
    from app.poller import Poller
    from tests.test_school_lists import NEWS_SPEC, HolidaysStub

    pages = Pages({NEWS_PATH: MAIN, "/iserv/news/archive": ARCHIVE, "/iserv/news/iserv": PACKAGES, "/iserv/news/general/2": "<article><p>Two</p></article>", "/iserv/news/general/1": "<article><p>One</p></article>"})
    service, connection_id = section_service(tmp_path, pages, lambda: 1_791_000_000)
    connection = service.connections()[0]
    poller = Poller(None, store=service.store, notifiers={"news": lambda name, message: True})
    poller.clock = lambda: 1_791_000_000
    poller._poll_school_list(connection, connection_id, True, NEWS_SPEC, {}, "en")
    assert not [path for path in pages.asked if path in ("/iserv/news/archive", "/iserv/news/iserv")]
    school = integration.build_school(service.store, HolidaysStub(), 1_791_000_000, connection_id)
    assert [item["id"] for item in school["news"]["items"]] == ["general/2", "general/1"]
    assert service.news()["schools"][0]["sections"] == ["archive", "packages"]


def test_the_app_reads_a_section_when_asked_and_keeps_it_for_a_while(tmp_path):
    from fastapi.testclient import TestClient

    from app.server import create_app

    now = [1_791_000_000]
    pages = Pages({"/iserv/news/archive": ARCHIVE, "/iserv/news/general/0": "<article><p>Zero text</p></article>"})
    service, connection_id = section_service(tmp_path, pages, lambda: now[0])
    app = TestClient(create_app(service=service))
    first = app.get("/api/news/section", params={"section": "archive"}).json()
    assert [(item["id"], item["section"], item["connection_id"]) for item in first["news"]] == [("general/1", "archive", connection_id), ("general/0", "archive", connection_id)]
    app.get("/api/news/section", params={"section": "archive"})
    assert pages.asked == ["/iserv/news/archive"]
    detail = app.get("/api/news/section/detail", params={"connection": connection_id, "section": "archive", "item": "general/0"}).json()
    assert detail["text"] == ["Zero text"]
    assert app.get("/api/news/section", params={"section": "packages"}).json()["news"] == []
    now[0] += 3600
    again = app.get("/api/news/section", params={"section": "archive"}).json()
    assert pages.asked.count("/iserv/news/archive") == 2
    assert next(item for item in again["news"] if item["id"] == "general/0")["detail"]["text"] == ["Zero text"]
