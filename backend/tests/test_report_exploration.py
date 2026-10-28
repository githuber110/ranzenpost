import json
from datetime import date

import pytest
import requests

from app import diagnostics, reportcrawl, reportexplore, scriptscan
from app.iserv.client import iserv_sign_in_step, module_sign_in_steps
from tests.test_diagnostics import SCHOOL_ONE_URL, menu_of, recording_client

TODAY = date(2026, 10, 16)
OTHER = "https://pay.other.example"


def html_answer(text, headers=None):
    return (200, dict({"Content-Type": "text/html"}, **(headers or {})), text.encode("utf-8"))


def json_answer(payload):
    return (200, {"Content-Type": "application/json"}, json.dumps(payload).encode("utf-8"))


def nav(*paths):
    return html_answer("<nav>%s</nav>" % "".join('<a href="%s">x</a>' % path for path in paths))


def guessed_row(slug, segment, page):
    return {"slug": slug, "segment": segment, "name": slug, "page": page, "json": None, "guessed_page": True}


def structure(answers, row):
    client, adapter = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher))
    return lines, [url[len(SCHOOL_ONE_URL):] if url.startswith(SCHOOL_ONE_URL) else url for url in adapter.sent], adapter


def record_headers(adapter):
    adapter.headers = {}
    send = adapter.send

    def recording(request, **kwargs):
        adapter.headers[request.url] = dict(request.headers)
        return send(request, **kwargs)

    adapter.send = recording


def foreign_session_headers(adapter):
    return [headers for url, headers in adapter.headers.items() if "pay.other.example" in url and "X-Synthetic-Session" in headers]


def assert_private(lines, words):
    text = "\n".join(lines).casefold()
    for word in words:
        assert word.casefold() not in text, word


FORUM_LANDING = """
<html><head><title>Foren</title></head><body>
<table id="forum-list"><tr><th>Titel</th><th>Neu</th></tr>
<tr><td><a href="/iserv/forum/7">Elternrat Mia Musterkind</a></td><td><a href="/iserv/forum/7/99">Letzter Beitrag</a></td></tr></table>
<a href="/iserv/forum/unread">Ungelesen</a>
<a href="/iserv/forum/unread/elternrat">Elternrat</a>
<a href="/iserv/forum/settings">Einstellungen</a>
<a href="/iserv/forum/group/klasse-5a-mia">Klasse 5a</a>
<a href="/iserv/forum/topic/99">Sommerfest Ideen</a>
<a href="/iserv/forum/read">Alle gelesen</a>
<a href="/iserv/forum/allgemein/willkommen">Willkommen</a>
<form action="/iserv/forum/read" method="post"><button name="forum_all_read[submit]">Alle gelesen markieren</button></form>
<form action="/iserv/forums/change" method="post"><select name="change_subscription[type]" required>
<option value="none">keine</option><option value="highlight">hervorheben</option><option value="notify">benachrichtigen</option>
</select></form>
</body></html>
"""
FORUM_GROUP = """
<html><body><a href="/iserv/forum/group/klasse-5a-mia/123">Thema Mia</a><a href="/iserv/forum/topic/123">Thema</a>
<a href="/iserv/forum/group/klasse-5a-mia/thread/5">Thema</a></body></html>
"""


def forum_answers():
    page = SCHOOL_ONE_URL + "/iserv/"
    return {
        page: nav("/iserv/forums"),
        page + "forums": html_answer(FORUM_LANDING),
        page + "forum/unread": html_answer("<html><body><a href='/iserv/forum/topic/5'>Neu</a></body></html>"),
        page + "forum/settings": html_answer("<html><body><form method='post'><input name='settings[signature]'></form></body></html>"),
        page + "forum/group/klasse-5a-mia": html_answer(FORUM_GROUP),
    }


def test_the_forum_is_explored_under_its_link_prefix_without_opening_a_topic_or_marking_it_read():
    lines, sent, _ = structure(forum_answers(), guessed_row("forum", "forums", "/iserv/forums/"))
    assert "- Crawl prefixes: /iserv/forums/, /iserv/forum/" in lines
    for path in ("/iserv/forum/unread", "/iserv/forum/settings", "/iserv/forum/group/klasse-5a-mia"):
        assert path in sent, path
    for path in sent:
        assert "topic" not in path and "thread" not in path, path
        assert not path.endswith(("/forum/read", "/forum/7", "/7/99", "/123", "/willkommen", "/unread/elternrat")), path
    assert "##### Page /iserv/forum/group/<seg>" in lines
    assert "  - change_subscription[type] (select, required, options 3, values none / highlight / notify)" in lines
    assert_private(lines, ("Musterkind", "klasse-5a-mia", "Sommerfest", "Willkommen", "Elternrat"))


TODO_PAGE = """
<html><head><title>To-do</title><script type="module" src="/iserv/todo/static/assets/main-a1b2c3d4.js"></script></head>
<body><div id="app"></div></body></html>
"""
TODO_SCRIPT = (
    'const api=axios.create({baseURL:"/iserv/todo"});api.get("/api/v1/lists");fetch(base+"/api/v1/tasks?done=0");'
    'const one="/api/v1/tasks/"+id;fetch("/api/v1/lists/markAllRead");axios.post("/api/v1/tasks",{title:t});'
)


def todo_answers():
    page = SCHOOL_ONE_URL + "/iserv/"
    return {
        page: nav("/iserv/todo/home"),
        page + "todo/home": html_answer(TODO_PAGE),
        page + "todo/static/assets/main-a1b2c3d4.js": (200, {"Content-Type": "text/javascript"}, TODO_SCRIPT.encode("utf-8")),
        page + "todo/api/v1/lists": json_answer([{"id": 3, "title": "Mia Hausaufgaben", "color": "#123456"}]),
        page + "todo/api/v1/tasks": json_answer([{"id": 9, "title": "Brief an Frau Lehrerin", "date": "2026-10-20", "done": False}]),
    }


def test_the_to_do_app_endpoints_are_resolved_against_the_app_base_and_read_as_shapes():
    lines, sent, _ = structure(todo_answers(), guessed_row("todo", "todo", "/iserv/todo/"))
    assert "- App root: div#app, children 0" in lines
    assert "- App base: /iserv/todo/ (module path)" in lines
    assert "- Resolved endpoint: /api/v1/lists -> /iserv/todo/api/v1/lists" in lines
    assert "- Resolved endpoint: <expr>/api/v1/tasks -> /iserv/todo/api/v1/tasks" in lines
    assert "##### API GET /iserv/todo/api/v1/lists" in lines
    assert "  - [].title: string len 16, free text" in lines
    assert "  - [].date: string len 10, iso date" in lines
    assert "/iserv/todo/api/v1/lists" in sent and "/iserv/todo/api/v1/tasks" in sent
    assert not [path for path in sent if "markAllRead" in path or path.startswith("/api/")]
    assert any(line.startswith("| GET | /api/v1/lists |") for line in lines)
    assert_private(lines, ("Hausaufgaben", "Lehrerin", "Mia"))


def test_a_base_tag_comes_first_and_only_app_api_paths_are_resolved():
    html = '<html><head><base href="/iserv/todo/app/"></head></html>'
    bases, from_tag = reportexplore.app_bases(html, SCHOOL_ONE_URL + "/iserv/todo/home", ("/iserv/todo/",))
    assert (bases, from_tag) == (["/iserv/todo/app/", "/iserv/todo/"], True)
    assert reportexplore.resolved_paths("/api/v1/lists", bases) == ["/iserv/todo/app/api/v1/lists", "/iserv/todo/api/v1/lists"]
    assert reportexplore.resolved_paths("<expr>/lists", bases) == ["/iserv/todo/app/lists", "/iserv/todo/lists"]
    assert reportexplore.resolved_paths("/iserv/todo/api/v1/lists", bases) == ["/iserv/todo/api/v1/lists"]
    assert reportexplore.resolved_paths("/static/x/y", bases) == []
    assert reportexplore.resolved_paths("/api/v1/tasks/<expr>", bases) == []
    foreign = '<html><head><base href="https://cdn.example/iserv/todo/"></head></html>'
    assert reportexplore.app_bases(foreign, SCHOOL_ONE_URL + "/iserv/todo/home", ("/iserv/todo/",)) == (["/iserv/todo/"], False)


FILE_LANDING = """
<html><body>
<a href="/iserv/file/-/Groups">Gruppen</a><a href="/iserv/files/Brief-an-Mia.pdf">Brief</a><a href="/iserv/file/cloud">Wolke</a>
<form action="/iserv/file/-/Files" method="post">
<select name="form[action]"><option value="">-</option><option value="delete">Löschen</option><option value="move">Verschieben</option>
<option value="copy">Kopieren</option><option value="mueller-ordner">Müller</option></select>
<select name="form[preview][size]"><option value="1">klein</option><option value="2">mittel</option></select>
<button name="form[delete]">Löschen</button>
</form>
<input type="checkbox" name="form[files][]" value="Brief-an-Mia.pdf" form="files-form">
</body></html>
"""
FILE_GROUPS = """
<html><body>
<a href="/iserv/file/-/Groups/Elternrat">Elternrat</a><a href="/iserv/file/-/Groups/Klasse%205a">Klasse 5a</a>
<a href="/iserv/file/-/Groups/Elternrat/Protokolle">Protokolle</a><a href="/iserv/file/-/Groups/Elternrat/download">Herunterladen</a>
<a href="/iserv/file/-/Groups/Upload">Upload</a>
</body></html>
"""


def file_answers():
    page = SCHOOL_ONE_URL + "/iserv/"
    return {
        page: nav("/iserv/file/-/Files"),
        page + "file/-/Files": html_answer(FILE_LANDING),
        page + "file/-/Groups": html_answer(FILE_GROUPS),
        page + "file/-/Groups/Elternrat": html_answer("<html><body><table id='files'><tr><td>a</td></tr></table></body></html>"),
        page + "file/cloud": html_answer("<html><body>cloud</body></html>"),
    }


def test_files_read_the_group_folders_one_level_deep_and_name_the_action_values():
    lines, sent, _ = structure(file_answers(), guessed_row("file", "file", "/iserv/file/"))
    assert "/iserv/file/-/Groups" in sent and "/iserv/file/cloud" in sent
    assert "/iserv/file/-/Groups/Elternrat" in sent
    assert "/iserv/file/-/Groups/Klasse%205a" not in sent
    for path in sent:
        assert not path.endswith(("/Protokolle", "/download", "/Upload")) and "Brief" not in path, path
    assert "##### Page /iserv/file/-/Groups/<seg>" in lines
    assert any(line.startswith("  - form[action] (select, options 5, values delete / move / copy / <word>") for line in lines)
    assert "  - form[preview][size] (select, options 2, values 1 / 2)" in lines
    assert_private(lines, ("Elternrat", "Mueller", "Brief-an-Mia", "Protokolle"))


VIDEO_LANDING = """
<html><head><script src="/iserv/videoconference/static/assets/room-list-a1b2c3d4.js"></script></head><body>
<table class="table"><tr><th>Raum</th></tr>
<tr><td>Klasse 5a Mia Musterkind</td><td><a href="/iserv/videoconference/room/abc123def456/join?token=synthetic-token-77">Betreten</a></td></tr>
<tr><td>Elternrat</td><td><button data-href="https://bbb.other.example/bigbluebutton/api/join?checksum=synthetic-sum">Betreten</button></td></tr>
<tr><td>Eigene</td><td><a href="/iserv/videoconference/room/abc123def456/start">Starten</a></td></tr>
</table>
<a href="/iserv/videoconference/rooms">Räume</a>
</body></html>
"""
VIDEO_SCRIPT = 'fetch("/iserv/videoconference/api/rooms");fetch("/iserv/videoconference/api/rooms/"+id+"/join",{method:"POST"});'


def video_answers():
    page = SCHOOL_ONE_URL + "/iserv/"
    return {
        page: nav("/iserv/videoconference/"),
        page + "videoconference/": html_answer(VIDEO_LANDING),
        page + "videoconference/rooms": html_answer("<html><body>rooms</body></html>"),
        page + "videoconference/static/assets/room-list-a1b2c3d4.js": (200, {"Content-Type": "text/javascript"}, VIDEO_SCRIPT.encode("utf-8")),
        page + "videoconference/api/rooms": json_answer({"own": [], "shared": [{"name": "Klasse 5a", "running": True, "url": "/iserv/videoconference/room/abc/join"}]}),
    }


def test_video_conferences_record_rooms_and_the_join_host_kind_but_never_join():
    lines, sent, adapter = structure(video_answers(), guessed_row("videoconference", "videoconference", "/iserv/videoconference/"))
    assert "- Join targets: 2, same host 1 (/iserv/videoconference/room/<seg>/join), other host 1, never opened" in lines
    assert any(line.startswith("- Table 1 row texts: Raum ; Klasse <word> <word> <word> / <word> ; <word> / <word>") for line in lines)
    assert "/iserv/videoconference/rooms" in sent
    assert "##### API GET /iserv/videoconference/api/rooms" in lines
    assert any(line.endswith("[].running: boolean") for line in lines)
    assert not [url for url in adapter.sent if "join" in url or "start" in url or "bbb.other" in url]
    assert_private(lines, ("Musterkind", "Elternrat", "synthetic-token", "synthetic-sum", "bbb.other", "abc123def456"))


METHODS_PAGE = """
<html><head><title>MethodenGuide</title></head><body>
<iframe class="embed-responsive-item" src="https://pay.other.example/methoden/start?embed=1#top"></iframe></body></html>
"""


def test_the_methods_guide_follows_its_frame_to_the_other_host_and_records_the_framing_rules():
    answers = {
        SCHOOL_ONE_URL + "/iserv/": nav("/iserv/methodenguide"),
        SCHOOL_ONE_URL + "/iserv/methodenguide": html_answer(METHODS_PAGE),
        OTHER + "/methoden/start": html_answer(
            "<html><head><title>Methoden</title></head><body><a href='/tools'>Tools</a></body></html>",
            {"X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "default-src 'self'; frame-ancestors 'self' https://*.gymnasium-nord.example"},
        ),
    }
    client, adapter = recording_client(answers)
    client.session.headers["X-Synthetic-Session"] = "synthetic-session-header"
    record_headers(adapter)
    fetcher = diagnostics.ReportFetcher(client)
    row = guessed_row("methodenguide", "methodenguide", "/iserv/methodenguide/")
    lines = diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher))
    assert "- Frame: iframe to another host, path /<seg>/<seg>" in lines
    assert "- Frame chain: 200 same host -> 200 other host" in lines
    assert any(line.startswith("- Landing page: 200 text/html") for line in lines)
    assert "- Framing: x-frame-options sameorigin, frame-ancestors 'self' <host>" in lines
    assert [url for url in adapter.headers if "pay.other.example" in url]
    assert foreign_session_headers(adapter) == []
    assert_private(lines, ("pay.other", "gymnasium-nord", "embed=1"))


def test_a_frame_line_names_missing_rules():
    class Answer:
        headers = {}

    assert reportexplore.frame_line(Answer()) == "- Framing: x-frame-options not set, frame-ancestors not set"


EDUPOOL_AUTH = SCHOOL_ONE_URL + "/iserv/edupool/auth"


def edupool_answers(back=EDUPOOL_AUTH + "?state=synthetic-state-1"):
    def iserv_auth(request):
        if "IServSession=synthetic-iserv-cookie" in request.headers.get("Cookie", ""):
            return 302, {"Location": OTHER + "/edupool/home"}, b""
        return 302, {"Location": "/iserv/auth/login"}, b""

    return {
        SCHOOL_ONE_URL + "/iserv/": nav("/iserv/edupool"),
        SCHOOL_ONE_URL + "/iserv/edupool": (302, {"Location": OTHER + "/edupool/sso?code=synthetic-code-1", "Content-Type": "text/html"}, b""),
        OTHER + "/edupool/sso": (302, {"Location": back}, b""),
        EDUPOOL_AUTH: iserv_auth,
        SCHOOL_ONE_URL + "/iserv/klassengeld/auth": iserv_auth,
        OTHER + "/edupool/home": html_answer("<html><head><title>Mediathek</title></head><body><main>Mia</main></body></html>"),
    }


def edupool_structure(answers):
    client, adapter = recording_client(answers)
    client.session.cookies.set("IServSession", "synthetic-iserv-cookie", domain="gymnasium-nord.example")
    client.session.headers["X-Synthetic-Session"] = "synthetic-session-header"
    record_headers(adapter)
    fetcher = diagnostics.ReportFetcher(client)
    row = guessed_row("edupool", "edupool", "/iserv/edupool/")
    return diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher)), adapter


def test_an_external_service_signs_in_through_its_own_module_step_and_records_the_landing_page():
    lines, adapter = edupool_structure(edupool_answers())
    assert "- Redirect chain: 302 same host -> 302 other host -> 302 same host -> 200 other host" in lines
    assert "- Title: <word>" in lines
    assert "synthetic-iserv-cookie" in adapter.cookies[EDUPOOL_AUTH + "?state=synthetic-state-1"]
    assert adapter.headers[EDUPOOL_AUTH + "?state=synthetic-state-1"]["X-Synthetic-Session"] == "synthetic-session-header"
    assert [url for url in adapter.headers if "pay.other.example" in url]
    assert foreign_session_headers(adapter) == []
    assert_private(lines, ("synthetic-state", "synthetic-code", "Mediathek", "pay.other"))


def test_the_sign_in_step_of_another_module_is_not_taken():
    lines, adapter = edupool_structure(edupool_answers(back=SCHOOL_ONE_URL + "/iserv/klassengeld/auth"))
    assert "- Landing page: not read, chain stopped at an IServ page" in lines
    assert not [url for url in adapter.sent if "/iserv/klassengeld/" in url]


def test_only_plain_module_sign_in_steps_are_accepted():
    assert module_sign_in_steps(["/iserv/edupool/auth", "/iserv/edupool/logout", "/iserv/a/b/auth", "/iserv/Edupool/auth", 7]) == ("/iserv/edupool/auth",)
    steps = ("/iserv/edupool/auth",)
    assert iserv_sign_in_step(SCHOOL_ONE_URL + "/iserv/edupool/auth?x=1", steps)
    assert not iserv_sign_in_step(SCHOOL_ONE_URL + "/iserv/edupool/auth/../logout", steps)
    assert not iserv_sign_in_step(SCHOOL_ONE_URL + "/iserv/edupool/auth")
    assert reportcrawl.chain_home_steps(type("A", (), {"url": SCHOOL_ONE_URL + "/iserv/edupool"})()) == steps


def test_a_long_sign_in_chain_reaches_its_landing_page():
    hops = ["/a", "/b", "/c", "/d", "/e"]
    answers = {
        SCHOOL_ONE_URL + "/iserv/": nav("/iserv/eduplacesconnector/"),
        SCHOOL_ONE_URL + "/iserv/eduplacesconnector/": (302, {"Location": OTHER + hops[0], "Content-Type": "text/html"}, b""),
        SCHOOL_ONE_URL + "/iserv/auth/auth": (302, {"Location": OTHER + "/launchpad"}, b""),
        OTHER + "/launchpad": html_answer("<html><head><title>Launchpad</title></head><body></body></html>"),
    }
    for index, hop in enumerate(hops):
        target = OTHER + hops[index + 1] if index + 1 < len(hops) else SCHOOL_ONE_URL + "/iserv/auth/auth?client_id=x"
        answers[OTHER + hop] = (307 if index < 2 else 302, {"Location": target}, b"")
    client, _ = recording_client(answers)
    fetcher = diagnostics.ReportFetcher(client)
    row = guessed_row("eduplacesconnector", "eduplacesconnector", "/iserv/eduplacesconnector/")
    lines = diagnostics.page_structure(fetcher, row, TODAY, {}, nav_paths=menu_of(fetcher))
    assert any(line.startswith("- Landing page: 200 text/html") for line in lines)
    assert reportcrawl.MAX_CHAIN_HOPS == 10


START_PAGE = """
<html><body>
<nav class="sidebar"><div class="card"><a href="/iserv/poll">Umfragen</a></div></nav>
<main>
<div class="panel panel-default"><div class="panel-heading">Laufende Umfragen</div>
<div class="card"><a href="/iserv/poll/participate/12">Elternbefragung Mia</a></div></div>
<div class="alert alert-info">Neue Schnellumfrage von Frau Lehrerin <a href="/iserv/poll-quick/vote/5">Abstimmen</a>
<form method="post" action="/iserv/poll-quick/vote/5"><button>Ja</button></form></div>
</main></body></html>
"""


def test_the_start_page_notices_are_listed_as_blocks_with_link_and_form_shapes():
    client, adapter = recording_client({SCHOOL_ONE_URL + "/iserv/": html_answer(START_PAGE)})
    lines = reportcrawl.start_notice_lines(diagnostics.ReportFetcher(client))
    assert lines == [
        "### Start page notices",
        "- Blocks: 2",
        "- Block 1 div.panel.panel-default: heading '<word> Umfragen', links /iserv/poll/participate/<n>, forms -",
        "- Block 2 div.alert.alert-info: heading '-', links /iserv/poll-quick/vote/<n>, forms POST /iserv/poll-quick/vote/<n>",
    ]
    assert adapter.sent == [SCHOOL_ONE_URL + "/iserv/"]
    assert reportcrawl.start_notice_lines(None) == ["### Start page notices", "- Not read: no session"]


def test_the_mail_api_probe_is_repeated_once_with_json_headers():
    def folders(request):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" and "json" in request.headers.get("Accept", ""):
            return json_answer([{"name": "Posteingang", "path": "INBOX", "unread": 2}])
        return html_answer("<html><body><div id='app'></div></body></html>")

    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/mail/api/folder/list": folders,
        SCHOOL_ONE_URL + "/iserv/mail/api/message/list": json_answer({"items": [], "total": 0}),
    })
    lines = reportcrawl.known_api_lines(diagnostics.ReportFetcher(client), "mail", TODAY)
    assert "##### Known API GET /iserv/mail/api/folder/list with json headers" in lines
    assert any(line.startswith("- Page: /iserv/mail/api/folder/list with json headers -> 200 application/json ") for line in lines)
    assert "  - [].unread: int >0" in lines
    assert not [line for line in lines if "message/list +query with json headers" in line]
    assert adapter.sent.count(SCHOOL_ONE_URL + "/iserv/mail/api/folder/list") == 2
    assert_private(lines, ("Posteingang",))


DISPLAY_SHOW = """
<html><body><iframe src="/iserv/infodisplay/slides/7"></iframe><object data="/iserv/infodisplay/file/7/vertretungsplan-mia.pdf"></object>
<img src="/iserv/img/logo.png"><img src="https://cdn.other.example/slides/abc.jpg"></body></html>
"""


def test_an_info_display_page_names_its_sources_and_their_content_types():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/infodisplay/index"),
        page + "infodisplay/index": html_answer('<html><body><a href="/iserv/infodisplay/show/1">A</a></body></html>'),
        page + "infodisplay/show/1": html_answer(DISPLAY_SHOW),
        page + "infodisplay/slides/7": html_answer("<html><body>slide</body></html>"),
        page + "infodisplay/file/7/vertretungsplan-mia.pdf": (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4"),
    }
    lines, sent, _ = structure(answers, guessed_row("infodisplay", "infodisplay", "/iserv/infodisplay/"))
    shown = next(line for line in lines if line.startswith("- Embedded sources: iframe /iserv/infodisplay/slides/<n>"))
    assert "object /iserv/infodisplay/file/<n>/<file>.pdf" in shown and "<other host>" in shown
    assert "- Source /iserv/infodisplay/slides/<n> -> 200 text/html 31B" in lines
    assert not [path for path in sent if path.endswith((".pdf", ".png", ".jpg"))]
    assert_private(lines, ("vertretungsplan", "cdn.other"))


DETAIL_CASES = (
    (
        "etherpad", "etherpad", "/iserv/etherpad",
        '<a href="/iserv/etherpad/a1b2c3d4e5">Mia</a><a href="/iserv/etherpad/a1b2c3d4e5/export/txt">Export</a>'
        '<a href="/iserv/etherpad/markallread">x</a><a href="/iserv/etherpad/add">Neu</a>',
        ("/iserv/etherpad/a1b2c3d4e5", "/iserv/etherpad/add"), ("/export/txt", "/markallread"),
    ),
    (
        "mailinglist", "mailinglist", "/iserv/mailinglist",
        '<a href="/iserv/mailinglist/show/4">Liste</a><a href="/iserv/mailinglist/edit/4">Bearbeiten</a>'
        '<a href="/iserv/mailinglist/export/4">Export</a><a href="/iserv/mailinglist/delete/4">Löschen</a>',
        ("/iserv/mailinglist/show/4", "/iserv/mailinglist/edit/4"), ("/export/4", "/delete/4"),
    ),
    (
        "poll", "poll", "/iserv/poll",
        '<a href="/iserv/poll/participate/12">Umfrage</a><a href="/iserv/poll/vote/12/3">Ja</a><a href="/iserv/poll/results/12">x</a>',
        ("/iserv/poll/participate/12",), ("/vote/12/3",),
    ),
    (
        "course-selection", "courseselection", "/iserv/courseselection",
        '<div id="app"></div><a href="/iserv/courseselection/show/3">Wahl</a><a href="/iserv/courseselection/show/3/choose">x</a>',
        ("/iserv/courseselection/show/3",), ("/choose",),
    ),
    (
        "print", "print", "/iserv/print",
        '<a href="/iserv/print/job/12">Auftrag</a><a href="/iserv/print/job/12/download">PDF</a><a href="/iserv/print/job/12/cancel">x</a>'
        '<a href="/iserv/print/redeem">Einlösen</a>',
        ("/iserv/print/job/12", "/iserv/print/redeem"), ("/download", "/cancel"),
    ),
    (
        "addressbook", "addressbook", "/iserv/addressbook/private",
        '<a href="/iserv/addressbook/public">Alle</a><a href="/iserv/addressbook/private/show/8">Kontakt</a>'
        '<a href="/iserv/addressbook/private/export/vcard">vCard</a>',
        ("/iserv/addressbook/public", "/iserv/addressbook/private/show/8"), ("/export/",),
    ),
)


@pytest.mark.parametrize("slug, segment, page, links, opened, closed", DETAIL_CASES, ids=[case[0] for case in DETAIL_CASES])
def test_module_detail_pages_are_read_but_never_their_write_or_download_routes(slug, segment, page, links, opened, closed):
    answers = {SCHOOL_ONE_URL + "/iserv/": nav(page), SCHOOL_ONE_URL + page: html_answer("<html><body>%s</body></html>" % links)}
    for path in opened:
        answers[SCHOOL_ONE_URL + path] = html_answer("<html><body><form method='post'><input name='entry[title]'></form></body></html>")
    lines, sent, _ = structure(answers, guessed_row(slug, segment, page + "/"))
    for path in opened:
        assert path in sent, path
    for part in closed:
        assert not [path for path in sent if part in path], part
    if slug == "course-selection":
        assert "- App root: div#app, children 0" in lines


def test_modules_without_an_exploration_rule_keep_the_read_only_allowlist():
    assert reportexplore.rule_for(("/iserv/ausleihe/",)) is None
    assert reportexplore.rule_for(("/iserv/forums/",)) is reportexplore.RULES["forum"]
    assert reportcrawl.module_scope("/iserv/ausleihe/").rule is None
    assert not reportcrawl.api_allowed("/iserv/x/api/v1", "/iserv/x/")
    rule = reportexplore.RULES["todo"]
    assert reportcrawl.api_allowed("/iserv/todo/api/v1/lists", ("/iserv/todo/",), reportcrawl.module_scope("/iserv/todo/").api_routes, rule=rule)
    assert not reportcrawl.api_allowed("/iserv/todo/api/v1/lists/delete", ("/iserv/todo/",), reportcrawl.module_scope("/iserv/todo/").api_routes, rule=rule)


def test_the_join_lines_say_when_a_page_has_no_join_target():
    assert reportexplore.join_lines("<html></html>", SCHOOL_ONE_URL + "/iserv/videoconference/", reportcrawl.menu_shape) == ["- Join targets: none in the page"]


def test_the_notice_heading_prefers_a_heading_tag():
    soup = '<div class="card"><h3>Umfragen</h3><strong>Mia</strong></div>'
    assert reportexplore.notice_blocks(soup, SCHOOL_ONE_URL + "/iserv/", reportcrawl.menu_shape)[1] == "- Block 1 div.card: heading 'Umfragen', links -, forms -"


UNSAFE_SOURCES = """
<html><body><iframe src="/iserv/exercise/show/55"></iframe><img src="/iserv/auth/logout">
<iframe src="/iserv/forum/topic/9/markread"></iframe><iframe src="/iserv/infodisplay/show/3/markread"></iframe>
<iframe src="/iserv/infodisplay/logout"></iframe><video src="/iserv/infodisplay/clip/4"></video></body></html>
"""


def test_embedded_sources_outside_the_module_or_on_write_and_sign_out_paths_are_never_requested():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/infodisplay/index"),
        page + "infodisplay/index": html_answer('<html><body><a href="/iserv/infodisplay/show/1">A</a></body></html>'),
        page + "infodisplay/show/1": html_answer(UNSAFE_SOURCES),
    }
    lines, sent, _ = structure(answers, guessed_row("infodisplay", "infodisplay", "/iserv/infodisplay/"))
    for part in ("/exercise/", "/auth/", "/forum/", "markread", "/infodisplay/logout", "/clip/"):
        assert not [path for path in sent if part in path], part
    assert not [line for line in lines if line.startswith("- Source ")]
    assert any(line.startswith("- Embedded sources: iframe /iserv/exercise/show/<n>") for line in lines)


def test_ajax_calls_name_their_method_from_the_options_object():
    script = (
        '$.ajax({url:"/iserv/poll/start",type:"POST"});jQuery.ajax({method:"POST",url:"/iserv/poll/api/participate"});'
        '$.ajax("/iserv/poll/api/vote",{type:"post"});$.ajax({url:"/iserv/poll/api/polls",type:"GET"});'
        'const base="/iserv/poll/api/base";const later={method:"POST"};'
    )
    found = {pattern: method for method, pattern, _label in scriptscan.script_endpoints(script, "x")}
    assert found["/iserv/poll/start"] == "POST"
    assert found["/iserv/poll/api/participate"] == "POST"
    assert found["/iserv/poll/api/vote"] == "POST"
    assert found["/iserv/poll/api/polls"] == "GET"
    assert found["/iserv/poll/api/base"] == "-"


POLL_SCRIPT = (
    'const a="/iserv/poll/start";const b="/iserv/poll/api/participate";const c="/iserv/poll/api/polls/archive";'
    'const d="/iserv/poll/api/polls";$.ajax({url:"/iserv/poll/api/answers",type:"POST"});fetch("/iserv/poll/api/archive");'
)


def test_endpoints_without_a_method_are_read_only_when_they_name_a_listing():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/poll"),
        page + "poll": html_answer('<html><head><script src="/iserv/poll/static/app-a1b2c3d4.js"></script></head><body></body></html>'),
        page + "poll/static/app-a1b2c3d4.js": (200, {"Content-Type": "text/javascript"}, POLL_SCRIPT.encode("utf-8")),
        page + "poll/api/polls": json_answer([]),
    }
    lines, sent, _ = structure(answers, guessed_row("poll", "poll", "/iserv/poll/"))
    assert "/iserv/poll/api/polls" in sent
    for path in ("/iserv/poll/start", "/iserv/poll/api/participate", "/iserv/poll/api/polls/archive", "/iserv/poll/api/answers", "/iserv/poll/api/archive"):
        assert path not in sent, path


def chain_answers(steps):
    answers = {
        SCHOOL_ONE_URL + "/iserv/": nav("/iserv/edupool"),
        SCHOOL_ONE_URL + "/iserv/edupool": (302, {"Location": OTHER + "/hop/0", "Content-Type": "text/html"}, b""),
    }
    for number, target in enumerate(steps):
        answers[OTHER + "/hop/%d" % number] = (302, {"Location": target}, b"")
    return answers


def chain_structure(answers):
    client, adapter = recording_client(answers)
    client.session.cookies.set("IServSession", "synthetic-iserv-cookie", domain="gymnasium-nord.example")
    fetcher = diagnostics.ReportFetcher(client)
    lines = diagnostics.page_structure(fetcher, guessed_row("edupool", "edupool", "/iserv/edupool/"), TODAY, {}, nav_paths=menu_of(fetcher))
    return lines, adapter


def test_the_module_sign_in_step_is_taken_only_once_per_chain():
    answers = chain_answers([EDUPOOL_AUTH + "?round=1"])
    answers[EDUPOOL_AUTH] = (302, {"Location": OTHER + "/hop/1"}, b"")
    answers[OTHER + "/hop/1"] = (302, {"Location": EDUPOOL_AUTH + "?round=2"}, b"")
    lines, adapter = chain_structure(answers)
    assert "- Landing page: not read, chain stopped at a repeated IServ sign-in step" in lines
    assert len([url for url in adapter.sent if url.startswith(EDUPOOL_AUTH)]) == 1


@pytest.mark.parametrize("target", (OTHER + "/room/join", OTHER + "/session/logout", OTHER + "/api/delete-account", OTHER + "/sign/leave"))
def test_a_foreign_hop_to_a_write_or_sign_out_path_stops_the_chain(target):
    lines, adapter = chain_structure(chain_answers([target]))
    assert "- Landing page: not read, chain stopped before a write or sign-out path" in lines
    assert target not in adapter.sent


def test_a_chain_longer_than_ten_hops_stops():
    lines, adapter = chain_structure(chain_answers([OTHER + "/hop/%d" % (number + 1) for number in range(14)]))
    assert "- Landing page: not read, too many redirects" in lines
    assert len([url for url in adapter.sent if url.startswith(OTHER)]) == reportcrawl.MAX_CHAIN_HOPS


def test_a_foreign_url_carrying_the_step_path_never_gets_the_iserv_session():
    client, _ = recording_client({})
    router = client.chain_sessions(requests.Session(), ("/iserv/edupool/auth",))
    assert router.session_for(OTHER + "/iserv/edupool/auth") is not client.session
    assert router.session_for(SCHOOL_ONE_URL + "/iserv/edupool/auth") is client.session


@pytest.mark.parametrize("path", (
    "/iserv/forum/group/markallread", "/iserv/forum/group/readall", "/iserv/forum/group/%2e%2e", "/iserv/forum/group/a%2Fb",
    "/iserv/forum/group/%2E", "/iserv/forum/group/lastpost",
))
def test_free_forum_segments_refuse_dots_slashes_and_never_words(path):
    scope = reportcrawl.module_scope(("/iserv/forum/",))
    assert not reportcrawl.path_allowed(path, ("/iserv/forum/",), scope.routes, ids=False, rule=scope.rule)
    assert reportcrawl.path_allowed("/iserv/forum/group/klasse-5a", ("/iserv/forum/",), scope.routes, ids=False, rule=scope.rule)


def test_free_file_segments_refuse_dots_and_never_words():
    scope = reportcrawl.module_scope(("/iserv/file/",))
    for path in ("/iserv/file/groups/%2e%2e", "/iserv/file/-/Groups/%2E%2E", "/iserv/file/-/Groups/x%2fy", "/iserv/file/-/Groups/Downloads"):
        assert not reportcrawl.path_allowed(path, ("/iserv/file/",), scope.routes, ids=False, rule=scope.rule), path
    assert reportcrawl.path_allowed("/iserv/file/-/Groups/Elternrat", ("/iserv/file/",), scope.routes, ids=False, rule=scope.rule)


FILE_FRAMES = """
<html><body><iframe src="/iserv/infodisplay/file/7/plan.pdf"></iframe><iframe src="/iserv/infodisplay/attachment/9"></iframe>
<iframe src="/iserv/infodisplay/media/3"></iframe><iframe src="/iserv/infodisplay/show/2/export"></iframe>
<iframe src="/iserv/infodisplay/slides/plan.html"></iframe><iframe src="/iserv/infodisplay/downloads/4"></iframe></body></html>
"""


def test_frames_to_files_inside_the_module_are_never_downloaded():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/infodisplay/index"),
        page + "infodisplay/index": html_answer('<html><body><a href="/iserv/infodisplay/show/1">A</a></body></html>'),
        page + "infodisplay/show/1": html_answer(FILE_FRAMES),
    }
    lines, sent, _ = structure(answers, guessed_row("infodisplay", "infodisplay", "/iserv/infodisplay/"))
    for part in ("/file/", "/attachment/", "/media/", "/export", "plan.html", "/downloads/"):
        assert not [path for path in sent if part in path], part
    assert not [line for line in lines if line.startswith("- Source ")]


def test_the_generic_iserv_sign_in_step_is_taken_only_once_per_chain():
    iserv_auth = SCHOOL_ONE_URL + "/iserv/auth/auth"
    answers = chain_answers([iserv_auth + "?round=1"])
    answers[iserv_auth] = (302, {"Location": OTHER + "/hop/1"}, b"")
    answers[OTHER + "/hop/1"] = (302, {"Location": iserv_auth + "?round=2"}, b"")
    lines, adapter = chain_structure(answers)
    assert "- Landing page: not read, chain stopped at a repeated IServ sign-in step" in lines
    assert len([url for url in adapter.sent if url.startswith(iserv_auth)]) == 1


def test_the_method_key_wins_over_type_and_only_top_level_option_keys_count():
    script = (
        'fetch("/iserv/poll/api/polls",{body:JSON.stringify({type:"get"}),method:"POST"});'
        '$.ajax({url:"/iserv/poll/api/lists",data:{type:"get"},type:"POST"});'
        '$.ajax({url:"/iserv/poll/api/tasks",type:"GET",method:"POST"});'
        'fetch("/iserv/poll/api/items",{headers:{method:"POST"}});'
    )
    found = {pattern: method for method, pattern, _label in scriptscan.script_endpoints(script, "x")}
    assert found["/iserv/poll/api/polls"] == "POST"
    assert found["/iserv/poll/api/lists"] == "POST"
    assert found["/iserv/poll/api/tasks"] == "POST"
    assert found["/iserv/poll/api/items"] == "-"


def test_spread_assigned_and_string_braced_options_keep_their_method():
    script = (
        'fetch("/iserv/poll/api/tasks",_objectSpread(_objectSpread({},o),{},{method:"POST"}));'
        'fetch("/iserv/poll/api/entries",Object.assign({},{method:"POST"}));'
        'fetch("/iserv/poll/api/jobs",{body:"}",method:"POST"});'
        'fetch("/iserv/poll/api/lists",{body:"{",data:{method:"POST"},credentials:"same-origin"});'
        'fetch("/iserv/poll/api/polls");'
        'fetch("/iserv/poll/api/rooms",{credentials:"same-origin"});'
    )
    found = {pattern: method for method, pattern, _label in scriptscan.script_endpoints(script, "x")}
    assert found["/iserv/poll/api/tasks"] == "POST"
    assert found["/iserv/poll/api/entries"] == "POST"
    assert found["/iserv/poll/api/jobs"] == "POST"
    assert found["/iserv/poll/api/lists"] == "-"
    assert found["/iserv/poll/api/polls"] == "GET"
    assert found["/iserv/poll/api/rooms"] == "-"


def test_a_spread_post_endpoint_of_the_poll_module_is_never_read():
    script = 'fetch("/iserv/poll/api/tasks",_objectSpread(_objectSpread({},o),{},{method:"POST"}));fetch("/iserv/poll/api/polls");'
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/poll"),
        page + "poll": html_answer('<html><head><script src="/iserv/poll/static/app-a1b2c3d4.js"></script></head><body></body></html>'),
        page + "poll/static/app-a1b2c3d4.js": (200, {"Content-Type": "text/javascript"}, script.encode("utf-8")),
        page + "poll/api/polls": json_answer([]),
    }
    lines, sent, _ = structure(answers, guessed_row("poll", "poll", "/iserv/poll/"))
    assert "/iserv/poll/api/polls" in sent
    assert "/iserv/poll/api/tasks" not in sent


TODO_WORD_SCRIPT = (
    'const api=axios.create({baseURL:"/iserv/todo"});api.get("/api/todo-lists/tasks");'
    'fetch("/api/todo-lists/delete-all");axios.post("/api/todo-lists/tasks",{title:t});'
)


def test_app_api_words_from_the_module_script_open_its_read_endpoints_but_never_a_write():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = todo_answers()
    answers[page + "todo/static/assets/main-a1b2c3d4.js"] = (200, {"Content-Type": "text/javascript"}, TODO_WORD_SCRIPT.encode("utf-8"))
    answers[page + "todo/api/todo-lists/tasks"] = json_answer([{"id": 9, "title": "Brief an Frau Lehrerin", "done": False}])
    lines, sent, _ = structure(answers, guessed_row("todo", "todo", "/iserv/todo/"))
    assert "/iserv/todo/api/todo-lists/tasks" in sent
    assert "/iserv/todo/api/todo-lists/delete-all" not in sent
    assert "  - [].done: boolean" in lines
    assert_private(lines, ("Lehrerin",))


AUSLEIHE_PAGE = """
<html><head><script src="/iserv/ausleihe/static/js/app.a1b2c3d4.js"></script></head>
<body><div id="app"></div></body></html>
"""
AUSLEIHE_SCRIPT = 'fetch("/iserv/ausleihe/api/loans");fetch("/iserv/ausleihe/api/loans/return",{method:"POST"});'


def test_the_lending_library_reads_its_listing_api_as_shapes():
    page = SCHOOL_ONE_URL + "/iserv/"
    answers = {
        page: nav("/iserv/ausleihe/"),
        page + "ausleihe/": html_answer(AUSLEIHE_PAGE),
        page + "ausleihe/static/js/app.a1b2c3d4.js": (200, {"Content-Type": "text/javascript"}, AUSLEIHE_SCRIPT.encode("utf-8")),
        page + "ausleihe/api/loans": json_answer([{"id": 4, "title": "Mathebuch Klasse 5", "due": "2026-11-30"}]),
    }
    lines, sent, _ = structure(answers, guessed_row("ausleihe", "ausleihe", "/iserv/ausleihe/"))
    assert "/iserv/ausleihe/api/loans" in sent
    assert "/iserv/ausleihe/api/loans/return" not in sent
    assert any(line.endswith(": string len 10, iso date") for line in lines)
    assert_private(lines, ("Mathebuch",))


def test_script_words_never_open_a_write_verb_or_an_id():
    words = reportcrawl.script_words("/api/todo-lists/remove-all/archive/edit/4711/a1b2c3d4e5f6/tasks")
    assert words == frozenset({"api", "todo-lists", "tasks"})
