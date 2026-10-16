import logging

import pytest

from app.iserv import exercises
from app.iserv.forums import ForumShapeError, forum_key, is_forum_page, parse_forums, total_unread

READ_FORM = (
    '<form action="/iserv/forum/read" method="post" class="button-group form-inline">'
    '<input type="hidden" name="forum_mark_read[_token]" value="tok-1">'
    '<button type="submit" name="forum_mark_read[submit]">Alle gelesen markieren</button></form>'
)
SEARCH_FORM = '<form action="/iserv/forum/search" method="get"><input type="search" name="form[query]" required><button name="search"></button></form>'
OVERVIEW_MENU = (
    '<ul class="dropdown-menu"><li><a href="/iserv/forum/unread">Ungelesene Themen</a></li>'
    '<li><a href="/iserv/forum/unread/subscribed">Abonniert</a></li><li><a href="/iserv/forum/topics/own">Eigene</a></li>'
    '<li><a href="/iserv/forum/bookmarks">Markiert</a></li><li><a href="/iserv/forum/settings">Einstellungen</a></li></ul>'
)


def page(table, extra=READ_FORM + SEARCH_FORM):
    return f"<html><body><nav>{OVERVIEW_MENU}</nav>{extra}{table}</body></html>"


SIX_HEAD = "<thead><tr><th></th><th>Titel</th><th>Beiträge</th><th>Themen</th><th>Neu</th><th>Letzter Beitrag</th></tr></thead>"


def forum_row(link, title, topics, posts, new, last, checkbox=False):
    box = '<td><input type="checkbox" name="change_subscription[forums][]" value="7"></td>' if checkbox else ""
    return (
        f'<tr>{box}<td><i class="fa fa-comments"></i></td><td><a href="{link}">{title}</a><br><small>Fragen und Antworten</small></td>'
        f"<td>{topics}</td><td>{posts}</td><td>{new}</td><td>{last}</td></tr>"
    )


def test_categories_titles_and_unread_counts_are_read_by_the_header_words():
    rows = (
        '<tr><td colspan="6">Allgemeine Foren</td></tr>'
        + forum_row("/iserv/forum/12345", "Schulhof", 4, 20, 3, '<a href="/iserv/forum/12345/98765">Pausen</a> 03.10.2026 14:05')
        + '<tr><td colspan="6">Gruppenforen</td></tr>'
        + forum_row("/iserv/forum/group/klasse-5a", "Klasse 5a", 1, 2, "", "-")
    )
    parsed = parse_forums(page(f'<table id="forum-list" class="table table-hover">{SIX_HEAD}<tbody>{rows}</tbody></table>'))
    first, second = parsed["forums"]
    assert parsed["mark_read"] is True
    assert first["id"] == "12345"
    assert first["title"] == "Schulhof"
    assert first["description"] == "Fragen und Antworten"
    assert first["category"] == "Allgemeine Foren"
    assert first["unread"] == 3
    assert first["last_post"] == "Pausen 03.10.2026 14:05"
    assert first["last_post_date"] == "2026-10-03T14:05"
    assert first["path"] == "/iserv/forum/12345"
    assert {"label": "Beiträge", "value": "4"} in first["extra"]
    assert second["id"] == "group/klasse-5a"
    assert second["category"] == "Gruppenforen"
    assert second["unread"] == 0
    assert total_unread(parsed["forums"]) == 3


def test_an_extra_checkbox_column_in_front_shifts_nothing():
    rows = forum_row("/iserv/forum/4711", "Elternrat", 2, 9, 5, "gestern", checkbox=True)
    rows += forum_row("/iserv/forum/4712", "Ohne Abo", 1, 1, 0, "heute")
    parsed = parse_forums(page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>'))
    assert [(forum["title"], forum["unread"], forum["last_post"]) for forum in parsed["forums"]] == [
        ("Elternrat", 5, "gestern"),
        ("Ohne Abo", 0, "heute"),
    ]


def test_a_header_with_spanned_title_and_a_trailing_checkbox_keeps_the_unread_column():
    head = '<thead><tr><th colspan="2">Titel</th><th>Beiträge</th><th>Neu</th><th>Letzter Beitrag</th><th></th></tr></thead>'
    row = (
        '<tr><td></td><td><a href="/iserv/forum/555">Technik</a></td><td>12</td><td>7</td><td>01.10.2026</td>'
        '<td><input type="checkbox" name="change_subscription[forums][]" value="555"></td></tr>'
    )
    forum = parse_forums(page(f'<table id="forum-list">{head}<tbody>{row}</tbody></table>'))["forums"][0]
    assert forum["unread"] == 7
    assert forum["last_post_date"] == "2026-10-01"


def test_without_an_unread_column_the_count_stays_unknown_and_is_logged_once(caplog):
    exercises._NOTED.clear()
    head = "<thead><tr><th>Titel</th><th>Beiträge</th></tr></thead>"
    row = '<tr><td><a href="/iserv/forum/1234">Eins</a></td><td>3</td></tr>'
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        forum = parse_forums(page(f'<table id="forum-list">{head}<tbody>{row}</tbody></table>'))["forums"][0]
        parse_forums(page(f'<table id="forum-list">{head}<tbody>{row}</tbody></table>'))
    assert forum["unread"] is None
    assert total_unread([forum]) == 0
    assert sum("no unread column" in record.getMessage() for record in caplog.records) == 1


def test_a_count_that_is_no_number_stays_unknown():
    rows = forum_row("/iserv/forum/1234", "Eins", 1, 1, "viele neue Beiträge seit gestern", "-")
    forum = parse_forums(page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>'))["forums"][0]
    assert forum["unread"] is None


def test_an_empty_forum_table_and_the_overview_menu_are_no_forums():
    rows = '<tr><td colspan="6">Allgemeine Foren</td></tr><tr><td colspan="6">Keine Foren vorhanden</td></tr>'
    parsed = parse_forums(page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>'))
    assert parsed["forums"] == []


def test_a_page_with_the_forum_forms_but_no_table_is_unknown_and_not_an_empty_list():
    with pytest.raises(ForumShapeError):
        parse_forums(page(""))
    with pytest.raises(ForumShapeError):
        parse_forums(page("<p>Willkommen</p>"))


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
def test_a_page_without_the_forum_table_stays_unknown_whatever_it_says(body):
    with pytest.raises(ForumShapeError):
        parse_forums(page(body))


def test_a_forum_table_without_item_rows_is_a_confirmed_empty_list():
    assert parse_forums(page(f'<table id="forum-list">{SIX_HEAD}<tbody></tbody></table>')) == {"forums": [], "mark_read": True, "complete": True}


def test_a_page_without_table_and_forms_is_unreadable_and_not_empty():
    with pytest.raises(ForumShapeError):
        parse_forums("<html><body><p>Fehler</p></body></html>")


def test_the_read_form_is_only_seen_as_a_post_to_the_read_route():
    rows = forum_row("/iserv/forum/1234", "Eins", 1, 1, 1, "-")
    table = f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>'
    assert parse_forums(page(table, SEARCH_FORM))["mark_read"] is False
    assert parse_forums(page(table, READ_FORM.replace('method="post"', 'method="get"')))["mark_read"] is False


@pytest.mark.parametrize("path, key", [
    ("/iserv/forum/12345", "12345"),
    ("/iserv/forum/group/klasse-5a/", "group/klasse-5a"),
    ("https://school.example/iserv/forum/allgemein?x=1", "allgemein"),
    ("/iserv/forum/read", ""),
    ("/iserv/forum/unread", ""),
    ("/iserv/forum/settings", ""),
    ("/iserv/forum/12345/98765", ""),
    ("/iserv/forums", ""),
])
def test_forum_keys_leave_out_the_overview_routes(path, key):
    assert forum_key(path) == key


@pytest.mark.parametrize("path, inside", [
    ("/iserv/forums", True),
    ("/iserv/forum/", True),
    ("/iserv/forum/123", True),
    ("/iserv/", False),
    ("/iserv/forumsx", False),
])
def test_forum_pages(path, inside):
    assert is_forum_page(path) is inside


@pytest.mark.parametrize("rows", [
    '<tr><td></td><td><a href="/iserv/forum/show/12">Schulhof</a></td><td>4</td><td>1</td><td>2</td><td>heute</td></tr>',
    "<tr><td></td><td>Schulhof</td><td>4</td><td>1</td><td>2</td><td>heute</td></tr>",
    '<tr><td colspan="6">Allgemeine Foren</td></tr><tr><td></td><td>Schulhof</td><td>4</td><td>1</td><td>2</td><td>heute</td></tr>',
])
def test_item_rows_that_cannot_be_read_are_unknown_and_logged_once(rows, caplog):
    exercises._NOTED.clear()
    table = page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>')
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            with pytest.raises(ForumShapeError):
                parse_forums(table)
    assert sum("unreadable" in record.getMessage() for record in caplog.records) == 1


def test_readable_rows_are_kept_beside_unreadable_ones_and_the_skip_is_logged_once(caplog):
    exercises._NOTED.clear()
    rows = forum_row("/iserv/forum/1234", "Eins", 1, 1, 2, "-") + "<tr><td></td><td>Ohne Link</td><td>4</td><td>1</td><td>2</td><td>-</td></tr>"
    table = page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>')
    with caplog.at_level(logging.INFO, logger="app.iserv.exercises"):
        for _ in range(2):
            parsed = parse_forums(table)
            assert [forum["title"] for forum in parsed["forums"]] == ["Eins"]
            assert parsed["complete"] is False
    lines = [record.getMessage() for record in caplog.records if "skipped" in record.getMessage()]
    assert len(lines) == 1 and "1 unreadable" in lines[0] and "Ohne" not in lines[0]


def test_a_table_read_in_full_says_so():
    table = page(f'<table id="forum-list">{SIX_HEAD}<tbody>{forum_row("/iserv/forum/1234", "Eins", 1, 1, 2, "-")}</tbody></table>')
    assert parse_forums(table)["complete"] is True


def test_section_rows_alone_are_a_confirmed_empty_table():
    rows = '<tr><td colspan="6">Allgemeine Foren</td></tr><tr><td colspan="6">Gruppenforen</td></tr><tr></tr>'
    assert parse_forums(page(f'<table id="forum-list">{SIX_HEAD}<tbody>{rows}</tbody></table>'))["forums"] == []
