from types import SimpleNamespace

from app import reportcrawl
from app.iserv.conferences import LIST_PATH
from app.reportlists import list_lines
from tests.conference_school import DETAIL_PATH, ORIGIN, TEACHER_PATH, ConferenceSchool


class CrawlClient:
    def __init__(self, school):
        self.school = school
        self.read = []

    def fetch_unfollowed(self, path, limit, timeout, expired=None):
        self.read.append(path)
        response = self.school.page(path)
        return SimpleNamespace(
            status_code=response.status_code, url=response.url, text=response.text, headers={"Content-Type": "text/html"},
            truncated=False, redirect="none", next_url="",
        )


def crawl(school):
    client = CrawlClient(school)
    landing = school.page(LIST_PATH)
    landing.headers = {"Content-Type": "text/html"}
    lines = reportcrawl.module_crawl(client, landing, "/iserv/parentconference/", reportcrawl.menu_shape, {}, "/iserv/")
    return client, lines


def test_the_report_follows_a_conference_to_its_teacher_page_and_records_the_booking_form_shape():
    school = ConferenceSchool()
    school.bookings["31"] = "101"
    client, lines = crawl(school)
    assert DETAIL_PATH in client.read and TEACHER_PATH in client.read
    assert "/iserv/parentconference/attendee/conference/7/teacher/14" not in client.read
    assert not [path for path in client.read if path.endswith(("/book", "/delete"))]
    text = "\n".join(lines)
    assert "- Crawl from this page: 1 more linked pages" in text
    assert "  - <word>[<word>] (radio, choices 3, disabled 2)" in text
    assert "  - <word>[child] (select, required, options 2, values <n>, label 'Kind')" in text
    assert "- App form 1: POST /iserv/parentconference/attendee/conference/<n>/teacher/<n>/book; fields hidden 1, radio 1, select 1, textarea 1; open choices radio 1/3, select 2/2; required 2; submits 1 (destructive 0); errors 0" in text
    assert "- App table 1: columns 5, rows 1, rows with page link 0, rows with form 1" in text
    assert "POST /iserv/parentconference/attendee/booking/<n>/delete" in text
    for private in ("Muster", "Beispiel", "Kim", "token-book-1", "token-cancel-31", "school.example"):
        assert private not in text, private


def test_the_report_names_how_the_conference_list_was_read():
    school = ConferenceSchool()
    lines = list_lines("parentconference", {LIST_PATH: school.page(LIST_PATH)})
    assert lines == ["- Conference list /iserv/parentconference/attendee/: read as blocks, items 2, with page link 1, cells per item 3"]
    empty = list_lines("parentconference", {LIST_PATH: school.page("/iserv/parentconference/attendee/archive")})
    assert empty == ["- Conference list /iserv/parentconference/attendee/: read as empty, items 0, with page link 0, cells per item -"]


def test_the_report_never_follows_a_link_that_could_book_change_or_cancel():
    school = ConferenceSchool()
    links = "".join(
        '<a href="/iserv/parentconference/attendee/%s">x</a>' % path
        for path in (
            "conference/7/book", "booking/31/edit", "appointment/5", "slot/5/book-now", "conference/7/reserve",
            "booking/31/cancel", "slot/5/storno", "conference/7",
        )
    )
    landing = SimpleNamespace(
        status_code=200, url=ORIGIN + LIST_PATH, text="<div id='content'>%s</div>" % links,
        headers={"Content-Type": "text/html"}, history=[],
    )
    client = CrawlClient(school)
    reportcrawl.module_crawl(client, landing, "/iserv/parentconference/", reportcrawl.menu_shape, {}, "/iserv/")
    written = {"book", "edit", "appointment", "book-now", "reserve", "cancel", "storno", "booking"}
    assert [path for path in client.read if written & set(path.split("/"))] == []
    assert "/iserv/parentconference/attendee/conference/7" in client.read
