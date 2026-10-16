import logging

import pytest

from app import account_lists
from app.iserv import exercises
from app.iserv.errors import DataError
from app.iserv.infodisplay import INFODISPLAY_PATH, ScreenShapeError, is_infodisplay_page, parse_screens, screen_key
from tests.test_refused_probes import Answer

BASE = "https://school.example"
MENU = '<nav><a href="/iserv/infodisplay/index">Infobildschirm</a><a href="/iserv/news">News</a></nav>'


def page(body):
    return f"<html><body>{MENU}<main>{body}</main></body></html>"


def test_every_screen_link_becomes_one_screen_with_its_name_and_the_fullscreen_link_joins_it():
    body = (
        '<ul class="list-group">'
        '<li><a href="/iserv/infodisplay/show/1201">Eingangshalle</a> '
        '<a href="/iserv/infodisplay/fullscreen/show/1201" title="Im Vollbildmodus anzeigen"><i class="fa fa-expand"></i></a></li>'
        '<li><a href="/iserv/infodisplay/fullscreen/show/1202"><i class="fa fa-expand"></i></a> '
        '<a href="/iserv/infodisplay/show/1202">Mensa</a></li>'
        '<li><a href="/iserv/infodisplay/layout/edit/1203">Layout</a></li>'
        "</ul>"
    )
    assert parse_screens(page(body))["screens"] == [
        {"id": "1201", "title": "Eingangshalle", "path": "/iserv/infodisplay/show/1201"},
        {"id": "1202", "title": "Mensa", "path": "/iserv/infodisplay/show/1202"},
    ]


PROBE_PAGES = [
    '<div class="alert alert-danger">Keine Berechtigung</div>',
    "<p>No access to this module.</p>",
    '<div class="alert alert-warning">Keine Verbindung zur Datenbank möglich</div>',
    '<span class="badge is-empty">Fehler 500</span>',
    '<ul id="list" class="empty"></ul><p>No JavaScript?</p>',
    '<form method="post" action="/iserv/auth/login"><input type="password" name="_password"></form><p>Kein Konto?</p>',
    '<div class="dropdown-menu"><p>Keine neuen Benachrichtigungen</p></div>',
    "<p>Keine Foren</p>",
    '<div class="empty-state">No info displays</div>',
]


@pytest.mark.parametrize("body", PROBE_PAGES)
def test_a_page_without_screen_links_stays_unknown_whatever_it_says(body):
    with pytest.raises(ScreenShapeError):
        parse_screens(page(body))


def test_a_page_without_screen_links_is_unknown_and_logged_once(caplog):
    exercises._NOTED.clear()
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for body in ("<p>Willkommen im Infobildschirm</p>", ""):
            with pytest.raises(ScreenShapeError):
                parse_screens(page(body))
    assert sum("no screen links" in record.getMessage() for record in caplog.records) == 1


def test_an_unreadable_screen_page_is_an_error_for_the_poll():
    class Empty:
        def fetch(self, path, params=None):
            return Answer(200, BASE + path, page(""))

    with pytest.raises(DataError):
        account_lists.read_screens(Empty())


def test_screen_keys_and_pages():
    assert screen_key("/iserv/infodisplay/show/1201/") == "1201"
    assert screen_key("/iserv/infodisplay/fullscreen/show/1201") == "1201"
    assert screen_key("/iserv/infodisplay/index") == ""
    assert is_infodisplay_page("/iserv/infodisplay/index")
    assert not is_infodisplay_page("/iserv/")


class Pages:
    def fetch(self, path, params=None):
        return Answer(200, BASE + path, page('<a href="/iserv/infodisplay/show/9001">Foyer</a>'))


def test_the_screen_list_is_read_from_the_index_page():
    listed = account_lists.read_screens(Pages())
    assert listed == {"infodisplay": [{"id": "9001", "title": "Foyer", "path": "/iserv/infodisplay/show/9001"}], "carry": []}
    assert INFODISPLAY_PATH == "/iserv/infodisplay/index"
