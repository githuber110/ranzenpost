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
        SCHOOL_ONE_URL + "/iserv/mail/api/v2/setting/tag",
        SCHOOL_ONE_URL + "/iserv/mail/api/v2/setting/signature",
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


FEED_EVENT = dict(EVENT, calendarId="/eltern.5a/calendar")
EXAM_EVENTS = [dict(EVENT, uid="x1", title="Mathe Musterkind", calendarName=None), dict(EVENT, uid="x2", start="2026-02-03T08:00:00+01:00", end="2026-02-03T09:00:00+01:00")]
SOURCE_LIST = [
    {"label": "Musterkind privat", "id": "/f.max.muster/home", "subscription": False, "color": "#123456", "textColor": "#ffffff", "url": "/iserv/calendar/feed/calendar?cal=%2Ff.max.muster%2Fhome", "type": "cal", "droppable": True},
    {"label": "Eltern 5a", "id": "/eltern.5a/calendar", "subscription": True, "color": "#123456", "textColor": "#ffffff", "url": "/iserv/calendar/feed/calendar?cal=%2Feltern.5a%2Fcalendar", "type": "cal", "droppable": False},
    {"label": "Klausuren Turnhalle", "id": "exam", "subscription": False, "color": "#123456", "textColor": "#000000", "url": "/iserv/calendar/api/plugin?plugin=exam", "type": "plugin", "droppable": False},
    {"label": "Zeugnisse", "id": "zeugnisse", "subscription": False, "color": "#123456", "textColor": "#000000", "url": "/iserv/calendar/api/plugin?plugin=zeugnisse", "type": "plugin", "droppable": False},
    {"label": "Posteingang", "id": "/eltern/x", "subscription": False, "color": "#123456", "textColor": "#000000", "url": "/iserv/calendar/delete?id=5a", "type": "Eltern 5a", "droppable": False},
]


def source_answers():
    answers = calendar_answers()
    answers[SCHOOL_ONE_URL + "/iserv/calendar/api/eventsources"] = json_answer(SOURCE_LIST)

    def plugin(request):
        if "plugin=exam" in request.url:
            return json_answer(EXAM_EVENTS)
        return (500, {"Content-Type": "text/html"}, b"<html>Fehler Musterkind</html>")

    answers[SCHOOL_ONE_URL + "/iserv/calendar/api/plugin"] = plugin
    answers[SCHOOL_ONE_URL + "/iserv/calendar/feed/calendar"] = json_answer([FEED_EVENT])
    return answers


def source_lines(lines):
    head = lines.index("##### Calendar sources (app window 2026-01-08 to 2026-05-15)")
    return [line for line in lines[head + 1:] if line.startswith("- Source")]


def test_every_calendar_source_gets_one_line_with_type_rule_url_shape_status_and_count():
    client, adapter = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = source_lines(reportcrawl.known_api_lines(fetcher, "calendar", TODAY))
    assert lines[0].startswith("- Source 1: type cal, url /iserv/calendar/feed/calendar?cal=/<seg>/home -> 200 application/json ")
    assert lines[0].endswith("B, 1 events")
    assert lines[1].startswith("- Source 2: type cal, url /iserv/calendar/feed/calendar?cal=/<seg>/calendar -> 200 application/json ")
    assert lines[1].endswith("B, 1 events")
    assert lines[2].startswith("- Source 3: type plugin, url /iserv/calendar/api/plugin?plugin=exam -> 200 application/json ")
    assert lines[2].endswith("B, 2 events")
    assert lines[3].startswith("- Source 4: type plugin, url /iserv/calendar/api/plugin?plugin=<seg> -> 500 text/html ")
    assert lines[4] == "- Source 5: type <other>, url /iserv/calendar/delete?id=<seg>, not read: url outside the calendar feeds"
    assert len(lines) == 5


def test_the_calendar_source_lines_keep_labels_ids_and_the_account_out():
    client, adapter = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client)
    text = "\n".join(reportcrawl.known_api_lines(fetcher, "calendar", TODAY))
    for word in SECRET_WORDS + ("Klausuren", "privat", "zeugnisse"):
        assert word not in text


def test_the_report_reads_only_the_listed_school_feeds_with_the_app_window():
    client, adapter = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client)
    reportcrawl.known_api_lines(fetcher, "calendar", TODAY)
    feeds = [url for url in adapter.sent if ("/iserv/calendar/feed/" in url or "/iserv/calendar/api/plugin" in url) and "calendar-multi" not in url]
    assert feeds == [
        SCHOOL_ONE_URL + "/iserv/calendar/feed/calendar?cal=%2Ff.max.muster%2Fhome&start=2026-01-08&end=2026-05-15",
        SCHOOL_ONE_URL + "/iserv/calendar/feed/calendar?cal=%2Feltern.5a%2Fcalendar&start=2026-01-08&end=2026-05-15",
        SCHOOL_ONE_URL + "/iserv/calendar/api/plugin?plugin=exam&start=2026-01-08&end=2026-05-15",
        SCHOOL_ONE_URL + "/iserv/calendar/api/plugin?plugin=zeugnisse&start=2026-01-08&end=2026-05-15",
    ]
    assert not [url for url in adapter.sent if "/delete" in url]


def test_the_page_structure_reuses_the_source_list_it_already_read():
    client, adapter = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client)
    row = {"slug": "calendar", "segment": "calendar", "name": "Kalender", "page": "/iserv/calendar/", "json": "calendar"}
    lines = diagnostics.page_structure(fetcher, row, TODAY, {})
    assert len(source_lines(lines)) == 5
    assert adapter.sent.count(SCHOOL_ONE_URL + "/iserv/calendar/api/eventsources") == 1


def test_an_unreadable_source_list_says_so():
    answers = source_answers()
    answers[SCHOOL_ONE_URL + "/iserv/calendar/api/eventsources"] = json_answer({"error": "denied"})
    client, _ = recording_client(answers)
    lines = reportcrawl.known_api_lines(diagnostics.ReportFetcher(client), "calendar", TODAY)
    assert "- Sources: unreadable, the app falls back to the combined feed" in lines


def test_calendar_source_reads_stop_with_the_page_budget():
    client, _ = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client, reportcrawl.CrawlBudget(pages=5))
    lines = reportcrawl.known_api_lines(fetcher, "calendar", TODAY)
    assert "- Calendar source reads stopped: the report page limit is reached" in lines
    assert len(source_lines(lines)) == 2


def test_a_plugin_source_shows_the_shape_of_its_answer_so_one_report_settles_its_format():
    client, adapter = recording_client(source_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = reportcrawl.known_api_lines(fetcher, "calendar", TODAY)
    head = next(index for index, line in enumerate(lines) if line.startswith("- Source 3: type plugin"))
    shapes = []
    for line in lines[head + 1:]:
        if not line.startswith("  "):
            break
        shapes.append(line)
    assert shapes[0] == "  - JSON value shapes:"
    assert any("title: string" in line for line in shapes)
    assert not any("Mathe Musterkind" in line for line in shapes)


ME = SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/users/me"
OWN_PLAN = SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/current-timetable/"


def student_answers(plan):
    answers = calendar_answers()
    answers[ME] = json_answer({
        "id": 7, "displayname": "Max Musterkind", "roles": ["student"],
        "mainCourse": {"id": 5, "name": "5a"},
        "courses": [{"id": 12, "name": "Mathe 5a", "type": "course"}, {"id": 11, "name": "Deutsch 5a", "type": "course"}, {"name": "x"}],
    })
    answers[OWN_PLAN] = json_answer(plan)
    return answers


def test_the_report_asks_the_own_timetable_with_the_own_courses_and_shows_only_counts_and_shapes():
    plan = {"entries": [{"id": 1, "weekday": 0, "room": {"name": "Turnhalle"}}, {"id": 2, "weekday": 1}], "vacations": [], "schoolEvents": []}
    client, adapter = recording_client(student_answers(plan))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    text = "\n".join(lines)
    assert "- Own courses: 2" in lines
    assert "- Entries: no student blocks, entries at the top 2" in lines
    asked = [url for url in adapter.sent if url.startswith(OWN_PLAN) and "substitutions=false" in url]
    assert len(asked) == 1
    assert "filterBy=courseSubject.course%3Ain%2811%7C12%29" in asked[0]
    assert "substitutions=false" in asked[0]
    for word in SECRET_WORDS + ("Mathe", "Deutsch", "Max"):
        assert word not in text


def test_without_own_courses_the_own_timetable_is_not_asked():
    client, adapter = recording_client(calendar_answers())
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Own courses: 0" in lines
    assert "- Own timetable: not asked, the account lists no own courses" in lines
    assert not [url for url in adapter.sent if url.startswith(OWN_PLAN)]


def test_the_own_timetable_answer_of_a_parent_shape_counts_the_student_blocks():
    client, _ = recording_client(student_answers({"students": [{"student": {"id": 7}, "entries": [{"id": 1}]}]}))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Entries: student blocks 1, entries per block 1" in lines


STUDENTS = SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/students/"
PLANS = SCHOOL_ONE_URL + "/iserv/plan/"


def listed_answers(students, roles=("student",)):
    answers = student_answers({"entries": [{"id": 1, "weekday": 0}], "vacations": [], "schoolEvents": []})
    me = json.loads(answers[ME][2])
    me["roles"] = list(roles)
    answers[ME] = json_answer(me)
    answers[STUDENTS] = json_answer(students)
    return answers


def test_the_report_asks_the_student_list_and_the_timetable_the_way_the_school_app_does():
    students = [{"id": 7, "displayname": "Max Musterkind", "mainCourse": {"name": "5a"}, "courses": [{"id": 11}, {"id": 12}, {"id": 13}]}]
    client, adapter = recording_client(listed_answers(students))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    text = "\n".join(lines)
    assert "- Students listed: 1, the account itself among them: yes, courses of the first: 3, same as the account's own courses: no" in lines
    assert "- Entries: no student blocks, entries at the top 1" in lines
    asked = [url for url in adapter.sent if url.startswith(OWN_PLAN) and "substitutions=true" in url]
    assert len(asked) == 1
    assert "filterBy=courseSubject.course%3Ain%2811%7C12%7C13%29" in asked[0]
    assert "date=2026-01-12" in asked[0]
    assert "week=true" in asked[0]
    assert [url for url in adapter.sent if url.startswith(STUDENTS)][0].endswith(
        "?fields=id%2Cforename%2Csurname%2Cdisplayname%2CmainCourse%2CmainCourse.name%2Ccourses"
    )
    for word in SECRET_WORDS + ("Max",):
        assert word not in text


def test_a_teacher_account_never_asks_the_student_list():
    client, adapter = recording_client(listed_answers([{"id": 7, "courses": [{"id": 11}]}], roles=("teacher",)))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Student list: not asked, the roles do not clearly say student or guardian" in lines
    assert not [url for url in adapter.sent if url.startswith(STUDENTS)]


def test_staff_or_unclear_roles_never_ask_the_student_list():
    for roles in ((), ("ROLE_TEACHER",), ("schooladmin",), ("Lehrkraft",), ("Schulleitung",), ("student", "admin"), ("staff",), ("member",)):
        client, adapter = recording_client(listed_answers([{"id": 7, "courses": [{"id": 11}]}], roles=roles))
        lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
        assert "- Student list: not asked, the roles do not clearly say student or guardian" in lines, roles
        assert not [url for url in adapter.sent if url.startswith(STUDENTS)], roles


def test_role_objects_count_only_by_their_name():
    roles = ({"id": 3, "name": "Kollegium", "parent": None},)
    client, adapter = recording_client(listed_answers([{"id": 7, "courses": [{"id": 11}]}], roles=roles))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Student list: not asked, the roles do not clearly say student or guardian" in lines
    assert not [url for url in adapter.sent if url.startswith(STUDENTS)]
    client, adapter = recording_client(listed_answers([{"id": 7, "courses": [{"id": 11}]}], roles=({"id": 4, "name": "ROLE_STUDENT"},)))
    reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert [url for url in adapter.sent if url.startswith(STUDENTS)]


def test_a_broken_link_on_the_plans_page_does_not_stop_the_report():
    answers = calendar_answers()
    answers[PLANS] = html_answer('<html><body><a href="http://[broken/x">x</a><a href="/iserv/plan/show/A">A</a></body></html>')
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Plan links: 1, shapes /iserv/plan/show/<seg>" in lines


def test_a_guardian_account_asks_the_student_list_and_counts_its_children():
    students = [{"id": 21, "courses": [11, 12]}, {"id": 22, "courses": [{"id": 14}]}]
    client, adapter = recording_client(listed_answers(students, roles=("guardian",)))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Students listed: 2, the account itself among them: no, courses of the first: 2, same as the account's own courses: yes" in lines
    asked = [url for url in adapter.sent if url.startswith(OWN_PLAN) and "substitutions=true" in url]
    assert "filterBy=courseSubject.course%3Ain%2811%7C12%29" in asked[0]


def test_a_student_list_that_is_no_list_still_shows_its_shape():
    client, _ = recording_client(listed_answers({"items": [{"id": 7}], "total": 1}))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    head = lines.index(reportcrawl.STUDENT_LIST_HEAD)
    section = lines[head:lines.index(reportcrawl.PLAN_MODULE_HEAD)]
    assert "- Students listed: inside an object" in section
    assert any("items: array len 1" in line for line in section)
    assert "- Timetable: not asked, the first listed student has no courses" in section


def test_a_student_list_without_any_list_says_so():
    client, _ = recording_client(listed_answers({"total": 1}))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Students listed: answer is not a list" in lines


def test_an_empty_student_list_says_so_and_asks_no_timetable_for_it():
    client, adapter = recording_client(listed_answers([]))
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Students listed: 0, the account itself among them: no, courses of the first: 0, same as the account's own courses: no" in lines
    assert "- Timetable: not asked, the school app lists no student" in lines
    assert not [url for url in adapter.sent if url.startswith(OWN_PLAN) and "substitutions=true" in url]


def test_unknown_roles_leave_the_student_list_unasked():
    answers = calendar_answers()
    answers.pop(ME)
    client, adapter = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert "- Student list: not asked, the account roles are unknown" in lines
    assert not [url for url in adapter.sent if url.startswith(STUDENTS)]


def test_the_plans_module_shows_only_how_many_plans_it_links_and_their_shapes():
    answers = calendar_answers()
    answers[PLANS] = html_answer(
        '<html><body><a href="/iserv/plan/show/Vertretung%20Sch%C3%BCler">Vertretung</a>'
        '<a href="/iserv/plan/show/Lehrer">Lehrer</a><a href="/iserv/news">News</a></body></html>'
    )
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    text = "\n".join(lines)
    assert "- Plan links: 2, shapes /iserv/plan/show/<seg>" in lines
    assert "Vertretung" not in text and "Lehrer" not in text


def test_a_missing_plans_module_shows_only_its_answer():
    client, _ = recording_client(calendar_answers())
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    head = lines.index(reportcrawl.PLAN_MODULE_HEAD)
    assert lines[head + 1].startswith("- Page: /iserv/plan/ -> 404")
    assert not any(line.startswith("- Plan links") for line in lines)


SCREEN = (
    '<html><title>Vertretungsplan Schüler</title><body><main><div class="info" data-default-height="1080">'
    '<div class="grid-stack">'
    '<div class="grid-stack-item" data-gs-x="0"><div class="grid-stack-item-content infodisplay-widget infodisplay-widget-ext">'
    '<iframe class="infodisplay-widget-ext" src="/iserv/infodisplay/file/3/plan/k9x/Vertretung%20Sch%C3%BCler/subst_001.htm"></iframe></div></div>'
    '<div class="grid-stack-item"><div class="grid-stack-item-content infodisplay-widget infodisplay-widget-html" data-refresh="60">'
    '<table><tr><td>Mathe Musterkind</td><td>entfaellt</td></tr></table></div></div>'
    '<div class="grid-stack-item"><div class="infodisplay-widget" data-url="https://other.example/board/Plan5a"></div></div>'
    '</div></div></main></body></html>'
)


def test_the_info_screen_widgets_show_type_tags_sources_and_lengths_but_no_text():
    lines = reportcrawl.widget_lines(SCREEN, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    text = "\n".join(lines)
    assert lines[0] == "- Widgets: 1 grid(s) with 3 item(s)"
    assert "iframe /iserv/infodisplay/file/<n>/plan/<seg>/<seg>/<file>.htm" in lines[1]
    assert "tags iframe 1" in lines[1]
    assert "infodisplay-widget-ext" in lines[1]
    assert "tags table 1" in lines[2] and "data-refresh(number)" in lines[2]
    assert "data-url(<other host>/board/<seg>)" in lines[3]
    for word in ("Mathe", "Musterkind", "entfaellt", "Vertretung", "Plan5a", "other.example"):
        assert word not in text


def test_widget_classes_and_links_keep_only_known_words_and_survive_broken_addresses():
    screen = (
        '<div class="grid-stack"><div class="grid-stack-item infodisplay-widget-mueller-4711">'
        '<a href="http://[broken/x">x</a><img src="/iserv/infodisplay/picture/3/1/k?name=Mueller">'
        '<div data-url="' + SCHOOL_ONE_URL + '/iserv/infodisplay/file/3/plan/k/Mueller.htm?user=Mueller" data-x="http://[broken"></div>'
        '</div></div>'
    )
    lines = reportcrawl.widget_lines(screen, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    text = "\n".join(lines)
    assert "infodisplay-widget-<word>-<n>" in lines[1]
    assert "a unreadable link" in lines[1]
    assert "data-x(unreadable link)" in lines[1]
    assert "<other host>" not in lines[1]
    for word in ("mueller", "Mueller", "4711", "name=", "user="):
        assert word not in text


def test_an_info_screen_page_in_the_report_carries_its_widgets():
    answers = {
        SCHOOL_ONE_URL + "/iserv/": html_answer('<nav><a href="/iserv/infodisplay/index">Info</a></nav>'),
        SCHOOL_ONE_URL + "/iserv/infodisplay/index": html_answer('<html><title>Infobildschirm</title><body><a href="/iserv/infodisplay/show/3">A</a></body></html>'),
        SCHOOL_ONE_URL + "/iserv/infodisplay/show/3": html_answer(SCREEN),
    }
    client, _ = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    display = {"slug": "infodisplay", "segment": "infodisplay", "name": "Infobildschirm", "page": "/iserv/infodisplay/index", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(fetcher, display, TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert "- Widgets: 1 grid(s) with 3 item(s)" in lines
    assert "Mathe" not in text and "Musterkind" not in text


SUBSTITUTIONS = SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/substitutions/"
BOARD = SCHOOL_ONE_URL + "/iserv/dieschulapp/api/1.0/substitutionBoardMessages/"
FILES = SCHOOL_ONE_URL + "/iserv/file/-/Files"


def test_a_family_account_asks_substitutions_for_today_and_the_next_school_day_and_the_board_messages():
    answers = listed_answers([{"id": 7, "courses": [{"id": 11}]}])
    answers[SUBSTITUTIONS] = json_answer([{"id": 1, "date": "2026-01-15", "teacher": {"displayname": "Frau Musterkind"}, "note": "Turnhalle"}])
    answers[BOARD] = json_answer([{"id": 2, "text": "Elternabend heute"}])
    client, adapter = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    text = "\n".join(lines)
    asked = [url for url in adapter.sent if url.startswith(SUBSTITUTIONS)]
    assert len(asked) == 3
    assert "date%3Ais%282026-01-15%29" in asked[0]
    assert "date%3Ais%282026-01-16%29" in asked[1]
    assert "date%3AgreaterOrEqualThan%282026-01-08%29%2Cdate%3AsmallerOrEqualThan%282026-01-22%29" in asked[2]
    board = [url for url in adapter.sent if url.startswith(BOARD)][0]
    assert "validFromDate%3AsmallerOrEqualThan%282026-01-15%29" in board
    assert lines.count("- Entries: 1") >= 3
    for word in SECRET_WORDS:
        assert word not in text


def test_substitutions_are_not_asked_for_staff():
    client, adapter = recording_client(listed_answers([{"id": 7}], roles=("teacher",)))
    reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    assert not [url for url in adapter.sent if url.startswith((SUBSTITUTIONS, BOARD))]


def test_the_next_school_day_after_a_friday_is_monday():
    assert reportcrawl.next_school_day(date(2026, 1, 16)) == date(2026, 1, 19)


def file_page(request):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return json_answer({"data": [{"id": "a", "name": {"text": "Zeugnisse Musterkind.pdf", "link": "/iserv/file/-/Files/Zeugnisse"}, "size": {"order": 10}}]})
    return html_answer('<table id="files"><thead><tr><th>Name</th></tr></thead><tfoot><tr><td>x</td></tr></tfoot></table>')


def test_the_file_list_is_asked_the_way_the_file_page_loads_it_and_shows_only_its_shape():
    answers = calendar_answers()
    answers[FILES] = file_page
    client, adapter = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    head = lines.index(reportcrawl.FILE_LIST_HEAD)
    section = lines[head:]
    assert section[1].startswith("- Page: /iserv/file/-/Files +background request -> 200 application/json")
    assert "- Entries: 1" in section
    assert any("data[].name.text: string" in line for line in section)
    text = "\n".join(section)
    assert "Zeugnisse" not in text and "Musterkind" not in text


SUBST_FILE = (
    '<html><body><table class="mon_list"><tr class="list"><th>Klasse(n)</th><th>Stunde</th><th>Vertreter</th><th>Fach</th></tr>'
    '<tr class="list odd"><td>5a</td><td>3</td><td>Musterkind</td><td>Mathe</td></tr></table></body></html>'
)
WIDGET_SCREEN = (
    '<div class="grid-stack"><div class="grid-stack-item"><iframe src="/iserv/infodisplay/file/3/plan/k9x/Vertretung/subst_001.htm"></iframe></div>'
    '<div class="grid-stack-item"><iframe src="https://gym-nord.webuntis.com/WebUntis/monitor?school=gym-nord"></iframe></div>'
    '<div class="grid-stack-item"><div class="infodisplay-widget"><table><tr><th>Klasse</th><th>Musterkind</th></tr></table></div></div></div>'
)


def test_an_own_widget_source_is_read_once_as_a_shape_and_known_services_are_named():
    answers = {SCHOOL_ONE_URL + "/iserv/infodisplay/file/3/plan/k9x/Vertretung/subst_001.htm": html_answer(SUBST_FILE)}
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = reportcrawl.widget_lines(WIDGET_SCREEN, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    lines += reportcrawl.widget_source_lines(fetcher, WIDGET_SCREEN, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    text = "\n".join(lines)
    assert "iframe <other host: webuntis.com>" in lines[2]
    assert any(line.startswith("- Widget source /iserv/infodisplay/file/<n>/plan/<seg>/<seg>/<file>.htm -> 200 text/html") for line in lines)
    assert any("Table rows" in line and "4 cells x2" in line for line in lines)
    assert "table headers Klasse" in lines[3]
    assert not [url for url in adapter.sent if "webuntis" in url]
    for word in ("Musterkind", "Mathe", "gym-nord", "Vertretung", "5a"):
        assert word not in text


def test_the_first_plan_of_the_plans_module_is_read_as_a_shape():
    answers = calendar_answers()
    answers[PLANS] = html_answer('<a href="/iserv/plan/show/Vertretung%20Sch%C3%BCler">V</a>')
    answers[SCHOOL_ONE_URL + "/iserv/plan/show/Vertretung%20Sch%C3%BCler"] = html_answer(SUBST_FILE)
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    text = "\n".join(lines)
    assert any(line.startswith("- Page: first plan /iserv/plan/show/<seg> -> 200") for line in lines)
    assert any("Table rows" in line for line in lines)
    for word in ("Musterkind", "Mathe", "Vertretung"):
        assert word not in text


def test_a_refused_filter_shows_the_shape_of_the_error_answer():
    answers = listed_answers([{"id": 7, "courses": [{"id": 11}]}])
    answers[SUBSTITUTIONS] = (400, {"Content-Type": "application/json"}, json.dumps({"errors": [{"field": "date", "message": "unknown operator"}]}).encode())
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    head = lines.index(reportcrawl.SUBSTITUTIONS_HEAD)
    section = lines[head:head + 12]
    assert section[1].startswith("- Page: /iserv/dieschulapp/api/1.0/substitutions/ +date filter today -> 400")
    assert any("errors[].message: string" in line for line in section)


def groups_page(request):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return json_answer({"data": [{"id": "g", "name": '<a href="/iserv/file/-/Groups/Eltern 5a" class="file-link"><img src="/iserv/static/img/folder.png">Eltern 5a</a>', "path": "/iserv/file/-/Groups/Eltern 5a"}]})
    return html_answer("<table id='files'></table>")


def test_the_file_list_asks_files_and_groups_and_shows_html_fields_as_tags_and_link_shapes():
    answers = calendar_answers()
    answers[FILES] = file_page
    answers[SCHOOL_ONE_URL + "/iserv/file/-/Groups"] = groups_page
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    section = lines[lines.index(reportcrawl.FILE_LIST_HEAD):]
    text = "\n".join(section)
    assert any(line.startswith("- Page: /iserv/file/-/Groups +background request -> 200") for line in section)
    assert "- First row field name: html tags a, img; links /iserv/file/-/Groups/<seg> | /<seg>/<seg>/<seg>/<file>.png" in section or any(
        line.startswith("- First row field name: html tags a, img; links /iserv/file/-/Groups/<seg>") for line in section
    )
    assert "- First row field path: path /iserv/file/-/Groups/<seg>" in section
    assert "Eltern" not in text and "5a" not in text


FOLLOW_SCREEN = (
    '<div class="grid-stack">'
    '<div class="grid-stack-item"><iframe src="/iserv/infodisplay/file/3/plan/k9x/Vertretung/subst_001.htm?key=Mueller&amp;t=99"></iframe></div>'
    '<div class="grid-stack-item"><div class="infodisplay-widget" data-src="/iserv/infodisplay/pdf/4/1/k8"></div><img src="/iserv/infodisplay/picture/5/1/k7"></div>'
    '<div class="grid-stack-item"><iframe src="/iserv/mail"></iframe></div>'
    '</div>'
)


def follow_answers():
    first = SCHOOL_ONE_URL + "/iserv/infodisplay/file/3/plan/k9x/Vertretung/subst_001.htm"
    second = SCHOOL_ONE_URL + "/iserv/infodisplay/file/3/plan/k9x/Vertretung/subst_002.htm"
    return {
        first: html_answer('<html><head><meta http-equiv="refresh" content="8; URL=subst_002.htm"></head><body><table><tr><td>a</td></tr></table></body></html>'),
        second: html_answer(SUBST_FILE),
        SCHOOL_ONE_URL + "/iserv/infodisplay/pdf/4/1/k8": (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4 Musterkind"),
        SCHOOL_ONE_URL + "/iserv/infodisplay/picture/5/1/k7": (302, {"Location": "/iserv/infodisplay/picture/5/1/k7/full"}, b""),
        SCHOOL_ONE_URL + "/iserv/infodisplay/picture/5/1/k7/full": (200, {"Content-Type": "image/png"}, b"png"),
    }


def test_widget_sources_from_frames_data_attributes_and_images_are_read_with_query_names_only_and_followed_once():
    client, adapter = recording_client(follow_answers())
    fetcher = diagnostics.ReportFetcher(client)
    lines = reportcrawl.widget_source_lines(fetcher, FOLLOW_SCREEN, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    text = "\n".join(lines)
    assert lines[0] == "- Widget sources skipped: 1 (other host, write or sign-in path, or outside the widget areas)"
    assert any(line.startswith("- Widget source /iserv/infodisplay/file/<n>/plan/<seg>/<seg>/<file>.htm ?<word>&key -> 200") for line in lines)
    assert any(line.startswith("  - meta refresh to /iserv/infodisplay/file/<n>/plan/<seg>/<seg>/<file>.htm -> 200") for line in lines)
    assert any("Table rows" in line and "4 cells x2" in line for line in lines)
    assert any(line.startswith("- Widget source /iserv/infodisplay/pdf/<n>/<n>/<seg> -> 200 application/pdf") for line in lines)
    assert any(line.startswith("  - redirect to /iserv/infodisplay/picture/<n>/<n>/<seg>/<seg> -> 200 image/png") for line in lines)
    assert [url for url in adapter.sent if "subst_001.htm" in url][0].endswith("?key=Mueller&t=99")
    assert not [url for url in adapter.sent if url.endswith("/iserv/mail")]
    for word in ("Mueller", "99", "Musterkind", "Vertretung"):
        assert word not in text


def test_the_fullscreen_view_of_an_info_screen_is_crawled_too():
    answers = {
        SCHOOL_ONE_URL + "/iserv/": html_answer('<nav><a href="/iserv/infodisplay/index">Info</a></nav>'),
        SCHOOL_ONE_URL + "/iserv/infodisplay/index": html_answer(
            '<html><title>Infobildschirm</title><body><a href="/iserv/infodisplay/fullscreen/3">A</a></body></html>'
        ),
        SCHOOL_ONE_URL + "/iserv/infodisplay/fullscreen/3": html_answer(SCREEN),
    }
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    display = {"slug": "infodisplay", "segment": "infodisplay", "name": "Infobildschirm", "page": "/iserv/infodisplay/index", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(fetcher, display, TODAY, {}, nav_paths=menu_of(fetcher))
    assert SCHOOL_ONE_URL + "/iserv/infodisplay/fullscreen/3" in adapter.sent
    assert "- Widgets: 1 grid(s) with 3 item(s)" in lines


def test_html_fields_show_only_real_tag_names():
    line = reportcrawl.row_field_lines({"data": [{"name": "<Max Mustermann> report.pdf"}]})
    assert line == ["- First row field name: html tags <tag>; links -"]


def test_file_rows_given_as_arrays_show_each_html_or_path_column_as_a_shape():
    lines = reportcrawl.row_field_lines({"data": [["<input type=checkbox>", '<a href="/iserv/file/-/Files/Max Muster">Max Muster</a>', "12 KB", "/iserv/file/-/Files/Max"]]})
    assert lines == [
        "- First row field column 0: html tags input; links -",
        "- First row field column 1: html tags a; links /iserv/file/-/Files/<seg>",
        "- First row field column 3: path /iserv/file/-/Files/<seg>",
    ]


def test_error_answers_show_their_messages_with_unknown_words_masked():
    answers = listed_answers([{"id": 7, "courses": [{"id": 11}]}])
    answers[SUBSTITUTIONS] = (400, {"Content-Type": "application/json"}, json.dumps({"errors": [{"message": "Unknown filter for date Musterkind"}]}).encode())
    client, _ = recording_client(answers)
    lines = reportcrawl.account_api_lines(diagnostics.ReportFetcher(client), TODAY)
    texts = [line for line in lines if line.startswith("- Error texts: ")]
    assert texts and "filter" in texts[0] and "date" in texts[0]
    assert "Musterkind" not in "\n".join(lines)


def test_a_widget_source_that_leaves_for_a_known_service_names_the_service():
    screen = '<div class="grid-stack"><div class="grid-stack-item"><iframe src="/iserv/infodisplay/file/3/link/k/x.htm"></iframe></div></div>'
    answers = {SCHOOL_ONE_URL + "/iserv/infodisplay/file/3/link/k/x.htm": (302, {"Location": "https://gym-nord.dsbmobile.de/plan"}, b"")}
    client, _ = recording_client(answers)
    lines = reportcrawl.widget_source_lines(diagnostics.ReportFetcher(client), screen, SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    assert "  - redirect to <other host: dsbmobile.de>, not followed" in lines
    assert "gym-nord" not in "\n".join(lines)


def test_a_page_without_a_grid_says_so():
    lines = reportcrawl.widget_lines("<html><body><div class='panel'>x</div></body></html>", SCHOOL_ONE_URL + "/iserv/infodisplay/show/3", reportcrawl.valueshape.link_shape)
    assert lines == ["- Widgets: no grid on the page, elements with a widget class: 0"]


def test_a_calendar_appointments_source_shows_its_answer_shape():
    answers = calendar_answers()
    answers[SCHOOL_ONE_URL + "/iserv/calendar/api/eventsources"] = json_answer(
        [{"label": "Eltern 5a", "id": "/eltern.5a/calendar", "subscription": False, "type": "cal", "url": "/iserv/calendar/api/calendar-appointments?cal=/eltern.5a/calendar"}]
    )
    answers[SCHOOL_ONE_URL + "/iserv/calendar/api/calendar-appointments"] = json_answer({"events": [EVENT], "errors": []})
    client, _ = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, {"slug": "calendar", "segment": "calendar", "name": "Kalender", "page": "/iserv/calendar", "json": None}, TODAY, {}, nav_paths=menu_of(fetcher))
    text = "\n".join(lines)
    assert "type cal, url /iserv/calendar/api/calendar-appointments?cal=" in text
    assert "1 events" in text
    assert "JSON value shapes" in text.split("Calendar sources", 1)[1]
    for word in SECRET_WORDS:
        assert word not in text
