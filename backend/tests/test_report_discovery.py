import json
from datetime import date

from app import diagnostics, reportcrawl
from tests.test_diagnostics import SCHOOL_ONE_URL, menu_of, recording_client

TODAY = date(2026, 1, 15)
CALENDAR_LINK = SCHOOL_ONE_URL + "/iserv/calendar"
CALENDAR_PAGE = SCHOOL_ONE_URL + "/iserv/calendar/"
OWN_SCRIPT = SCHOOL_ONE_URL + "/iserv/calendar/static/js/calendar.4f2a.js"
SHARED_SCRIPTS = [SCHOOL_ONE_URL + "/iserv/static/js/shared%d.9e1b.js" % number for number in range(9)]
SECRET_WORDS = ("Elternabend", "Musterkind", "Turnhalle", "f.max.muster", "Zeugnisse", "eltern", "5a", "Posteingang")
EVENT = {
    "id": "a1",
    "uid": "u1@school.example",
    "title": "Elternabend Musterkind",
    "start": "2026-10-12T19:00:00+02:00",
    "end": "2026-10-12T20:30:00+02:00",
    "allDay": False,
    "calendarName": "Eltern 5a",
    "location": "Turnhalle",
}


def json_answer(payload):
    return (200, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8"))


def html_answer(text):
    return (200, {"Content-Type": "text/html"}, text.encode("utf-8"))


def calendar_answers(landing=CALENDAR_PAGE):
    scripts = "".join('<script src="%s"></script>' % url[len(SCHOOL_ONE_URL):] for url in SHARED_SCRIPTS)
    page = '<html><head><title>Kalender</title>%s<script src="/iserv/calendar/static/js/calendar.4f2a.js"></script></head><body><main>Kalender</main></body></html>' % scripts
    answers = {
        SCHOOL_ONE_URL + "/iserv/": html_answer('<nav><a href="/iserv/calendar">Kalender</a><a href="/iserv/mail">E-Mail</a></nav>'),
        CALENDAR_LINK: (308, {"Location": landing, "Content-Type": "text/html"}, b""),
        CALENDAR_PAGE: html_answer(page),
        OWN_SCRIPT: (200, {"Content-Type": "application/javascript"}, b'fetch("/iserv/calendar/api/lookup_event");'),
        SCHOOL_ONE_URL + "/iserv/calendar/api/eventsources": json_answer(
            [{"label": "Eltern 5a", "id": "/eltern.5a/calendar", "subscription": False, "color": "#123456", "type": "cal"}]
        ),
        SCHOOL_ONE_URL + "/iserv/calendar/api/upcoming": json_answer({"events": [EVENT], "errors": []}),
        SCHOOL_ONE_URL + "/iserv/calendar/feed/calendar-multi": json_answer({"/eltern.5a/calendar": [EVENT]}),
        SCHOOL_ONE_URL + "/iserv/mail": html_answer("<html><title>E-Mail</title><body>mail</body></html>"),
        SCHOOL_ONE_URL + "/iserv/mail/api/folder/list": json_answer([{"name": "Posteingang", "path": "INBOX", "unread": 2}]),
        SCHOOL_ONE_URL + "/iserv/mail/api/message/list": json_answer(
            {"items": [{"subject": "Zeugnisse", "read": False, "date": "2026-10-07T10:00:00+02:00"}], "total": 1}
        ),
        SCHOOL_ONE_URL + "/iserv/app/navigation/badges": json_answer({"mail": 2, "exercise": 1}),
        SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/users/me": json_answer(
            {"id": 7, "displayname": "f.max.muster", "roles": [], "children": []}
        ),
    }
    for url in SHARED_SCRIPTS:
        answers[url] = (200, {"Content-Type": "application/javascript"}, b"var x=1;")
    return answers


def calendar_row():
    return {"slug": "calendar", "segment": "calendar", "name": "Kalender", "page": "/iserv/calendar", "json": None, "guessed_page": True}


def test_a_same_host_redirect_is_followed_to_the_module_page_and_its_structure():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert "- Page: /iserv/calendar -> 308 text/html 0B, redirect to same host" in lines
    assert "- Redirect: /iserv/calendar/ -> 200 text/html" in text
    assert "- Title: Kalender" in text
    assert CALENDAR_PAGE in adapter.sent


def test_the_module_own_script_is_read_before_the_shared_ones():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client)
    diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    scripts = [url for url in adapter.sent if url.endswith(".js")]
    assert scripts[0] == OWN_SCRIPT
    assert len(scripts) == reportcrawl.MAX_SCRIPTS_PER_MODULE


def test_the_known_calendar_apis_are_read_as_shapes_without_values():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert "##### Known API GET /iserv/calendar/api/eventsources" in lines
    assert "##### Known API GET /iserv/calendar/api/upcoming +query" in lines
    assert "##### Known API GET /iserv/calendar/feed/calendar-multi +query" in lines
    for key in ("events[].title", "events[].calendarName", "events[].start"):
        assert key in text
    for word in SECRET_WORDS:
        assert word not in text
    sent = [url for url in adapter.sent if "calendar-multi" in url]
    assert sent == [SCHOOL_ONE_URL + "/iserv/calendar/feed/calendar-multi?start=2026-01-15&end=2026-02-14"]


def test_a_redirect_to_the_sign_in_page_is_never_followed():
    answers = calendar_answers(landing=SCHOOL_ONE_URL + "/iserv/auth/login?_target_path=/iserv/calendar/")
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    assert "- Redirect: stopped before /iserv/auth/login, not a module page" in lines
    assert not [url for url in adapter.sent if "/iserv/auth/" in url]


def test_a_redirect_loop_stops_after_the_hop_limit():
    answers = calendar_answers()
    answers[CALENDAR_PAGE] = (302, {"Location": CALENDAR_LINK, "Content-Type": "text/html"}, b"")
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    assert any(line.startswith("- Redirect: stopped before") and "too many hops" in line for line in lines)
    assert adapter.sent.count(CALENDAR_PAGE) <= reportcrawl.MAX_SAME_HOST_HOPS


def test_the_mail_module_reads_folder_and_list_shapes_but_never_a_message():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client)
    row = {"slug": "mail", "segment": "mail", "name": "E-Mail", "page": "/iserv/mail", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert "items[].read: boolean" in text
    assert "Zeugnisse" not in text
    reads = [url for url in adapter.sent if "/iserv/mail/api/" in url]
    assert [url.split("?", 1)[0] for url in reads] == [
        SCHOOL_ONE_URL + "/iserv/mail/api/folder/list",
        SCHOOL_ONE_URL + "/iserv/mail/api/message/list",
    ]


def test_the_account_apis_show_badge_and_school_account_shapes():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = reportcrawl.account_api_lines(fetcher, TODAY)
    text = "\n".join(lines)
    assert lines[0] == "### Account APIs"
    assert "##### Known API GET /iserv/app/navigation/badges" in lines
    assert "mail: int >0" in text
    assert "children: array len 0" in text
    assert "f.max.muster" not in text


def test_no_known_api_read_touches_a_writing_or_notification_path():
    paths = [path for targets in reportcrawl.KNOWN_APIS.values() for path, _ in targets]
    paths += [path for path, _ in reportcrawl.ACCOUNT_APIS]
    for path in paths:
        assert path.startswith("/iserv/")
        for word in ("delete", "mark", "read-all", "confirm", "send", "notification", "seen", "archive"):
            assert word not in path


def test_own_scripts_come_first_and_the_rest_keep_their_order():
    sources = ["/iserv/static/a.js", "/iserv/mail/static/b.js", "/iserv/static/c.js", "/iserv/js/mail.d.js"]
    assert reportcrawl.own_scripts_first(sources, SCHOOL_ONE_URL + "/iserv/mail/") == [
        "/iserv/mail/static/b.js",
        "/iserv/js/mail.d.js",
        "/iserv/static/a.js",
        "/iserv/static/c.js",
    ]
    assert reportcrawl.own_scripts_first(sources, SCHOOL_ONE_URL + "/") == sources


def test_tasks_follow_their_redirect_and_read_the_list_of_past_tasks_but_no_single_task():
    answers = {
        SCHOOL_ONE_URL + "/iserv/": html_answer('<nav><a href="/iserv/exercise/home">Aufgaben</a></nav>'),
        SCHOOL_ONE_URL + "/iserv/exercise/home": (302, {"Location": "/iserv/exercise", "Content-Type": "text/html"}, b""),
        SCHOOL_ONE_URL + "/iserv/exercise": html_answer(
            '<html><title>Aufgaben</title><body><a href="/iserv/exercise/past/exercise">Vergangene</a>'
            '<a href="/iserv/exercise/show/4711">Mathe Musterkind</a><table id="crud-table"><thead><tr><th>Aufgabe</th>'
            "<th>Abgabe</th></tr></thead><tbody><tr><td>Mathe Musterkind</td><td>12.10.2026</td></tr></tbody></table></body></html>"
        ),
        SCHOOL_ONE_URL + "/iserv/exercise/past/exercise": html_answer("<html><title>Aufgaben</title><body>old</body></html>"),
    }
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    row = {"slug": "exercise", "segment": "exercise", "name": "Aufgaben", "page": "/iserv/exercise/", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert SCHOOL_ONE_URL + "/iserv/exercise/past/exercise" in adapter.sent
    assert not [url for url in adapter.sent if "/show/" in url]
    assert "Musterkind" not in text


def test_one_info_display_page_is_read_and_other_modules_keep_skipping_details():
    answers = {
        SCHOOL_ONE_URL + "/iserv/": html_answer('<nav><a href="/iserv/infodisplay/index">Info</a><a href="/iserv/news">News</a></nav>'),
        SCHOOL_ONE_URL + "/iserv/infodisplay/index": html_answer(
            '<html><title>Infobildschirm</title><body><a href="/iserv/infodisplay/show/1">A</a>'
            '<a href="/iserv/infodisplay/show/2">B</a></body></html>'
        ),
        SCHOOL_ONE_URL + "/iserv/infodisplay/show/1": html_answer("<html><title>Infobildschirm</title><body>plan</body></html>"),
        SCHOOL_ONE_URL + "/iserv/news": html_answer('<html><title>News</title><body><a href="/iserv/news/show/9">N</a></body></html>'),
    }
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    nav = menu_of(fetcher)
    display = {"slug": "infodisplay", "segment": "infodisplay", "name": "Infobildschirm", "page": "/iserv/infodisplay/index", "json": None, "guessed_page": True}
    news = {"slug": "news", "segment": "news", "name": "News", "page": "/iserv/news", "json": None, "guessed_page": True}
    diagnostics.page_structure(fetcher, display, TODAY, {}, nav_paths=nav)
    diagnostics.page_structure(fetcher, news, TODAY, {}, nav_paths=nav)
    assert [url for url in adapter.sent if "/infodisplay/show/" in url] == [SCHOOL_ONE_URL + "/iserv/infodisplay/show/1"]
    assert not [url for url in adapter.sent if "/news/show/" in url]


def structure_after_redirect_to(location, extra=None):
    answers = calendar_answers(landing=location)
    answers.update(extra or {})
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, calendar_row(), TODAY, {}, nav_paths=menu_of(fetcher))
    return lines, adapter.sent


def test_redirects_to_any_sign_in_path_are_never_followed():
    for location in (
        SCHOOL_ONE_URL + "/iserv/app/login?_target_path=/iserv/calendar/",
        SCHOOL_ONE_URL + "/iserv/%61uth/login",
        SCHOOL_ONE_URL + "/iserv/oauth/authorize",
        SCHOOL_ONE_URL + "/iserv/calendar/sso/start",
    ):
        lines, sent = structure_after_redirect_to(location)
        assert any(line.startswith("- Redirect: stopped before") and "not a module page" in line for line in lines), location
        assert sent.count(location.split("?", 1)[0]) == 0, location


def test_a_redirect_outside_the_iserv_area_is_not_followed():
    lines, sent = structure_after_redirect_to(SCHOOL_ONE_URL + "/portal/start")
    assert any("not a module page" in line for line in lines)
    assert SCHOOL_ONE_URL + "/portal/start" not in sent


def test_a_landing_page_with_a_sign_in_form_stops_the_structure():
    landing = SCHOOL_ONE_URL + "/iserv/calendar/start"
    form = html_answer('<html><body><form method="post" action="/iserv/calendar/start"><input name="_username"><input type="password" name="_password"><button type="submit">Anmelden</button></form></body></html>')
    lines, sent = structure_after_redirect_to(landing, {landing: form})
    assert "- Redirect: /iserv/calendar/<seg> landed on the IServ sign-in page" in lines
    assert not [url for url in sent if url.endswith(".js")]


def test_another_host_after_a_same_host_redirect_is_not_followed():
    hop = SCHOOL_ONE_URL + "/iserv/calendar/go"
    lines, sent = structure_after_redirect_to(hop, {hop: (302, {"Location": "https://pay.other.example/start"}, b"")})
    assert "- Redirect: to another host after a same-host redirect, not followed" in lines
    assert not [url for url in sent if "pay.other.example" in url]


def test_known_api_reads_stop_when_the_page_budget_is_used_up():
    client, adapter = recording_client(calendar_answers())
    fetcher = diagnostics.ReportFetcher(client, reportcrawl.CrawlBudget(pages=1))
    lines = reportcrawl.known_api_lines(fetcher, "calendar", TODAY)
    assert len([line for line in lines if line.startswith("##### Known API GET")]) == 1
    assert "- Known API reads stopped: the report page limit is reached" in lines
