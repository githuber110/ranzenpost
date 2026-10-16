import pytest

from app import reportcrawl
from app.iserv import pages
from app.iserv.older_absence_form import attachment_entries

WRITE_PATHS = (
    "/iserv/parentconference/attendee/booking/31/cancel",
    "/iserv/parentconference/attendee/booking/31/unbook",
    "/iserv/parentconference/attendee/booking/31/storno",
    "/iserv/parentletter/parent/5/hide",
    "/iserv/parentletter/parent/5/restore",
    "/iserv/exercise/5/markread",
    "/iserv/mail/5/send",
    "/iserv/news/5/update",
)


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_the_shared_list_names_every_write_verb(path):
    assert pages.action_link(path)


@pytest.mark.parametrize("path", WRITE_PATHS)
def test_the_report_crawler_never_follows_a_shared_write_verb(path):
    assert reportcrawl.write_path(path)


def test_the_report_crawler_keeps_its_stricter_booking_nouns():
    assert reportcrawl.write_path("/iserv/parentconference/attendee/1/book")
    assert reportcrawl.write_path("/iserv/parentconference/attendee/booking/31")
    assert pages.WRITE_WORDS - pages.FORM_PAGE_WORDS <= reportcrawl.WRITE_WORDS
    assert not reportcrawl.write_path("/iserv/absence/add")


def test_a_page_that_shows_free_slots_is_not_a_write_link():
    assert not pages.action_link("/iserv/parentconference/attendee/1/book")
    assert not pages.action_link("/iserv/parentconference/attendee/booking/31")


def test_an_archive_list_is_a_page_to_read_not_a_write_link():
    assert not pages.action_link("/iserv/parentletter/parent/archive")
    assert not reportcrawl.write_path("/iserv/ausleihe/archive")


def test_an_older_absence_file_link_with_a_write_verb_is_no_attachment():
    page = (
        '<div><a href="/iserv/absence/7/attachment/3">note.pdf</a>'
        '<a href="/iserv/absence/7/attachment/4/hide">hidden.pdf</a>'
        '<a href="/iserv/absence/7/attachment/5/storno">old.pdf</a></div>'
    )
    found = attachment_entries(page, "https://school.example/iserv/absence/7")
    assert [item.path for item in found] == ["/iserv/absence/7/attachment/3"]
