import io
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi.testclient import TestClient

from app import diagnostics, logbuffer, modules, pageshape, pathpattern, reportcrawl, reportfacts, requestlog, scriptscan
from app.iserv.client import REDIRECT_NONE, CappedBody, IServClient, UnfollowedAnswer, chain_target_allowed, redirect_kind
from app.iserv.errors import LoginError
from app.server import create_app
from app.store import Store, edit_config
from tests import report_session
from tests.support import Response, add_school
from tests.test_no_personal_data import line_contains_forbidden_token

FIXTURES = Path(__file__).parent / "fixtures"
LETTERS_PAGE = (FIXTURES / "letters_index.html").read_text(encoding="utf-8")
START_PAGE = """
<html><body>
<a href="/iserv/time-table/">Stundenplan</a>
<a href="/iserv/parentletter/parent/index">Elternbriefe</a>
<a href="/iserv/calendar/">Kalender</a>
<a href="/iserv/mystery/">Mystery</a>
<footer>IServ 3.9.1</footer>
</body></html>
"""
MYSTERY_PAGE = """
<html><body>
<nav id="main-nav" class="navbar"><a href="/iserv/mystery/entry/4711">Alex Example</a></nav>
<form action="/iserv/mystery/save/4711" method="post" id="mystery-form">
<input type="text" name="title" value="Secret title" required>
<select name="child"><option value="99">Alex Example</option></select>
<textarea name="body">Dear parents, the secret text.</textarea>
</form>
<table class="table"><thead><tr><th>Datum</th><th>Betreff</th></tr></thead>
<tbody><tr><td>05.03.2026</td><td>Secret row</td></tr></tbody></table>
<script>
  fetch("/iserv/mystery/api/items/4711?date=2026-03-05");
  const url = '/iserv/mystery/api/list';
</script>
</body></html>
"""
CHAT_SCRIPT = "/iserv/messenger/static/assets/chat-standalone-a1b2c3d4.js"
VENDOR_SCRIPT = "/iserv/messenger/static/assets/vendor-9f8e7d6c5b4a.js"
FOREIGN_SCRIPT = "https://cdn.example/iserv/messenger/static/assets/tracker-1a2b3c4d.js"
MESSENGER_PAGE = """
<html><body>
<div id="app"></div>
<script type="module" crossorigin src="%s"></script>
<script src="%s"></script>
<script src="%s"></script>
<script type="application/json" id="php-data">{"messenger_authentication": null, "messenger_routing_basepath": "/iserv/messenger"}</script>
<script>console.log("noise");</script>
</body></html>
""" % (CHAT_SCRIPT, VENDOR_SCRIPT, FOREIGN_SCRIPT)
CHAT_SCRIPT_TEXT = (
    'import{a as e}from"./vendor-9f8e7d6c5b4a.js";const t="Alex Example";const base="/iserv/messenger";'
    'async function login(){const r=await fetch("/iserv/messenger/api/auth/token",{method:"POST",'
    'headers:{"Content-Type":"application/json"},body:JSON.stringify({csrf:e})});const d=await r.json();'
    'return{access_token:d.access_token,user_id:d.user_id,device_id:d.device_id,homeserver:d.homeserver}}'
    + 'const filler="' + "f" * 600 + '";'
    + 'axios.get("/iserv/messenger/api/rooms/4711/members");'
    + 'const filler2="' + "g" * 600 + '";'
    + 'const x=new XMLHttpRequest();x.open("PUT","/_matrix/client/v3/rooms/"+roomId+"/typing/"+userId);'
    + 'const filler3="' + "h" * 600 + '";'
    + 'client.post(`/iserv/messenger/api/reports/${reportId}/close`);'
    + 'const filler4="' + "i" * 600 + '";'
    + 'const p="/messenger/"+section;const q="/api/v2/unread";const s=e.homeserver+"/_matrix/client/v3/sync";'
    'const greeting="Hello parent";const mail="parent.one@family.example";'
)
VENDOR_SCRIPT_TEXT = (
    'const before="/iserv/messenger/api/before-cap";'
    + 'const filler="' + "v" * reportcrawl.MAX_SCRIPT_BYTES + '";'
    + 'const after="/iserv/messenger/api/after-cap";'
)
SCHOOL_ONE_URL = "https://gymnasium-nord.example"
SCHOOL_TWO_URL = "https://grundschule-sued.example"
CHILD_ONE = "Mia Musterkind"
CHILD_TWO = "Tom Beispielsohn"
TEACHER = "Frau Lehrerin"
USER_ONE = "parent.one@family.example"
USER_TWO = "elternteil.zwei"
PASSWORD = "SuperSecretPass1"
TOTP = "JBSWY3DPEHPK3PXP"
PERSON_WORDS = (
    "gymnasium-nord", "grundschule-sued", "Musterkind", "Beispielsohn", "Lehrerin",
    USER_ONE, USER_TWO, PASSWORD, TOTP, "Secret title", "secret text", "Secret row",
    "Alex Example", "Einladung zum Schulfest", "Persoenliche Mitteilung", "synthetic-token-0001",
)


class Client:
    def __init__(self, base_url, pages, scripts=None):
        self.base_url = base_url
        self.pages = pages
        self.scripts = scripts or {}
        self.capped_calls = []
        self.unfollowed_calls = []

    def is_authenticated(self):
        return True

    def fetch(self, path, params=None):
        for prefix, response in self.pages.items():
            if path.startswith(prefix):
                return response
        return Response(404, self.base_url + path, "")

    def fetch_unfollowed(self, path, limit, timeout, expired=None):
        self.unfollowed_calls.append(path)
        response = Client.fetch(self, path)
        url = self.base_url + path
        redirect = redirect_kind(url, response.status_code, response.headers.get("Location"), self.base_url)
        body = "" if redirect != REDIRECT_NONE else response.text
        return UnfollowedAnswer(response.status_code, url, response.headers.get("Content-Type", ""), body[:limit], len(body) > limit, redirect)

    def fetch_capped(self, path, limit, timeout, expired=None):
        self.capped_calls.append((path, limit, timeout))
        text = self.scripts.get(path)
        if text is None:
            return CappedBody(404, "", False)
        return CappedBody(200, text[:limit], len(text) > limit)


class Connection:
    def __init__(self, store, connection_id, client, registry, me=None, failure=None):
        self.id = connection_id
        self.store = store.connection_store(connection_id)
        self.client = client
        self.registry = registry
        self._me = me or {}
        self.failure = failure

    def modules(self):
        return modules.normalize(self.registry)

    def me(self):
        if self.failure:
            raise self.failure
        return dict(self._me)

    def iserv_session(self):
        if self.failure:
            raise self.failure
        return self.client


class Service:
    def __init__(self, store, connections):
        self.store = store
        self._connections = connections

    def connections(self, include_pending=False):
        return list(self._connections)


def menu_of(client):
    return reportcrawl.menu_paths_by_segment(reportcrawl.start_page_links(client)[0])


def registry_for(base_url, pages):
    def fetch(path, params=None):
        for prefix, response in pages.items():
            if path.startswith(prefix):
                return response
        return Response(404, base_url + path, "")

    return modules.detect(START_PAGE, fetch, None, clock=lambda: 1_788_000_000)


def two_school_service(tmp_path):
    store = Store(tmp_path)
    one = add_school(
        store,
        SCHOOL_ONE_URL,
        secrets={"username": USER_ONE, "password": PASSWORD, "totp_secret": TOTP},
        school_name="Gymnasium Nord",
        children=[{"child_id": "4711", "name": CHILD_ONE, "class_name": "3b"}],
        teachers={"LEH": {"label": TEACHER, "surname": "Lehrerin"}},
    )
    two = add_school(
        store,
        SCHOOL_TWO_URL,
        secrets={"username": USER_TWO, "password": PASSWORD},
        school_name="Grundschule Sued",
        children=[{"child_id": "4712", "name": CHILD_TWO, "class_name": "1a"}],
    )
    pages_one = {
        modules.PROBES[modules.LETTERS][0]: Response(200, SCHOOL_ONE_URL + modules.PROBES[modules.LETTERS][0], LETTERS_PAGE),
        "/iserv/mystery/": Response(200, SCHOOL_ONE_URL + "/iserv/mystery/", MYSTERY_PAGE),
        "/iserv/time-table/": Response(403, SCHOOL_ONE_URL + "/iserv/time-table/", "denied"),
        modules.DSA_API: Response(200, SCHOOL_ONE_URL + modules.DSA_API, "{}", "application/json", json_data={"items": [{"id": 1, "name": "x"}]}),
        "/iserv/messenger/": Response(200, SCHOOL_ONE_URL + "/iserv/messenger/", MESSENGER_PAGE),
    }
    client_one = Client(SCHOOL_ONE_URL, pages_one, {CHAT_SCRIPT: CHAT_SCRIPT_TEXT, VENDOR_SCRIPT: VENDOR_SCRIPT_TEXT})
    me_one = {"forename": "Mia", "surname": "Musterkind", "username": USER_ONE, "email": USER_ONE, "is_guardian": True, "has_2nd_factor_active": True}
    first = Connection(store, one, client_one, registry_for(SCHOOL_ONE_URL, pages_one), me_one)
    second = Connection(store, two, Client(SCHOOL_TWO_URL, {}), modules.default_registry(), failure=LoginError("bad login"))
    return Service(store, [first, second]), first, second


def build(service, **kwargs):
    kwargs.setdefault("clock", lambda: 1_788_000_000)
    kwargs.setdefault("versions", {"app": "2609.02.00", "home_assistant": "2026.9.1"})
    return diagnostics.build_report(service, **kwargs)


def test_the_report_carries_every_section_in_order(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, log_lines=["2026-09-19 10:00:00,000 INFO app.service: school#abc modules available"])
    headings = [line for line in report.splitlines() if line.startswith("#")]
    assert headings[:4] == ["# Ranzenpost report", "## Versions", "## Schools", "## School 1"]
    assert "## School 2" in headings
    assert headings[-1] == "## Log"
    assert "- Ranzenpost: 2609.02.00" in report
    assert "- Home Assistant: 2026.9.1" in report
    assert "- IServ: 3.9.1" in report
    assert "- Schools: 2" in report
    assert "- Children: 1" in report
    assert "- Account: 2fa=yes guardian=yes" in report
    assert "- Account: 2fa=no guardian=unknown" in report
    assert "- Language: " in report
    assert "- Timezone: Europe/Berlin" in report


LIVE_SECTIONS = (
    "### School app", "### Letters", "### Menu", "### IServ version",
    "### Unsupported or unknown modules", "### Page structure",
)


def test_the_quick_report_opens_no_session_and_reads_nothing_live(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    opened = []
    calls = []
    first.iserv_session = lambda: opened.append(True) or first.client
    first.client.fetch = lambda path, params=None: calls.append(path)
    report = build(service, structure=False)
    assert opened == []
    assert calls == []
    assert first.client.unfollowed_calls == []
    assert "### Children" in report
    for heading in LIVE_SECTIONS:
        assert heading not in report


def test_the_full_report_reads_each_page_at_most_once(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    calls = []
    original = first.client.fetch

    def counting(path, params=None):
        calls.append((path, diagnostics._params_key(params)))
        return original(path, params)

    first.client.fetch = counting
    report = build(service, structure=True)
    for heading in LIVE_SECTIONS:
        assert heading in report
    assert calls
    assert sorted(call for call in set(calls) if calls.count(call) > 1) == []
    unfollowed = first.client.unfollowed_calls
    assert len(unfollowed) == len(set(unfollowed))


def test_the_report_lists_every_module_row_with_probe_facts(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=False)
    rows = [line for line in report.splitlines() if line.startswith("| ") and not line.startswith("| Module")]
    slugs = {line.split("|")[2].strip() for line in rows}
    for slug in ("timetable", "dsa-timetable", "parentletter", "dsa-pinboard", "absence", "parentconference", "messenger"):
        assert slug in slugs
    assert "calendar" in slugs
    assert "mystery" in slugs
    letters = next(line for line in rows if "| parentletter |" in line)
    assert "| supported |" in letters
    assert "| 200 |" in letters
    assert "| text/html |" in letters
    assert "| /iserv/parentletter/parent/index |" in letters
    calendar = next(line for line in rows if "| calendar |" in line)
    assert "| Kalender |" in calendar
    assert "| present, not supported |" in calendar
    mystery = next(line for line in rows if "| mystery |" in line)
    assert "| unknown |" in mystery
    native = next(line for line in rows if "| timetable |" in line)
    assert "| obsolete |" in native
    assert "| not probed |" in native
    fresh = next(line for line in rows if "| dsa-timetable |" in line)
    assert "| new |" in fresh
    assert "| supported |" in fresh
    assert "| 200 |" in fresh
    assert "| application/json |" in fresh


def test_the_report_contains_no_person_host_or_credential(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, log_lines=[
        f"2026-09-19 10:00:00,000 INFO app.service: login of {USER_ONE} at {SCHOOL_ONE_URL} for {CHILD_ONE}",
        f"2026-09-19 10:00:01,000 INFO app.poller: Bearer abc.def-ghi cookie IServSession=verysecretcookievalue; {TEACHER}",
        f"2026-09-19 10:00:02,000 INFO app.wizard: password {PASSWORD} totp {TOTP} mail elternteil.zwei@mail.example",
    ])
    lowered = report.lower()
    for word in PERSON_WORDS:
        assert word.lower() not in lowered, word
    assert "<email>" in report
    assert "<host>" in report
    assert "<child>" in report
    assert "<secret>" in report
    assert "Bearer <secret>" in report
    assert "IServSession=<secret>" in report


def test_the_skeleton_names_fields_headers_links_and_endpoints_but_no_content(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=True)
    assert "### Page structure" in report
    assert "- Form: /iserv/parentletter/parent/index (post)" in report
    assert "  - filter (text)" in report
    assert "  - iserv_crud_multi_select[multi][] (checkbox)" in report
    assert "- Table headers: Titel | Kind | Absender | Weitere Absender | Empfaenger | Veroeffentlicht" in report
    assert "/iserv/parentletter/parent/show/<uuid>/<uuid>" in report
    assert "- Form: /iserv/<seg>/save/<n> (post) #<word>-form" in report
    assert "  - title (text, required)" in report
    assert "  - body (textarea)" in report
    assert "- Endpoints: /iserv/<seg>/api/items/<n> | /iserv/<seg>/api/list" in report
    assert "- Landmarks: nav#main-nav.navbar" in report
    for word in ("Einladung", "Schulfest", "Mitteilung", "Secret", "secret", "Dear parents", "synthetic-token", "2026-03-05", "05.03.2026"):
        assert word not in report, word
    without = build(service, structure=False)
    assert "### Page structure" not in without


def test_a_json_page_shows_the_shape_of_every_value_but_never_the_value(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=True)
    assert "- JSON value shapes:" in report
    assert "  - items: array len 1 of object" in report
    assert "  - items[].id: int >0" in report
    assert "  - items[].name: string len 1, letters" in report
    assert '"x"' not in report


def test_a_school_whose_login_fails_is_reported_as_an_error_and_the_rest_survives(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=True)
    assert "- Session: error (LoginError)" in report
    assert "## School 2" in report
    assert "| parentletter | current | assumed, never checked |" in report
    assert "## Log" in report


def test_the_log_section_keeps_timestamps_levels_and_module_tags(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    lines = [
        "2026-09-19 10:00:00,123 INFO iserv: letters GET /iserv/parentletter/parent/index 200 text/html 12345B 34ms",
        "2026-09-19 10:00:01,456 WARNING app.poller: poll failed",
    ]
    report = build(service, log_lines=lines)
    tail = report.split("## Log", 1)[1]
    for line in lines:
        assert line in tail
    assert "- Lines: 2" in tail


def test_an_empty_log_says_so(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    tail = build(service, log_lines=[]).split("## Log", 1)[1]
    assert "- Lines: 0" in tail


def test_slow_request_lines_summarise_slow_and_failed_areas_only():
    lines = [
        "2026-09-19 05:56:00,000 INFO iserv: absences GET /iserv/dsa-absences/ 500 text/html 12B 18000ms",
        "2026-09-19 05:56:01,000 INFO iserv: absences GET /iserv/dsa-absences/ 200 text/html 12B 4500ms",
        "2026-09-19 06:00:00,000 INFO iserv: letters GET /iserv/parentletter/parent/index 200 text/html 12345B 34ms",
        "2026-09-19 06:00:01,000 WARNING app.poller: poll failed",
    ]
    section = requestlog.slow_request_lines(lines)
    assert section[0] == "### Slow or failed requests"
    assert "| absences | 2 | 18000ms | 200, 500 |" in section
    assert not any(line.startswith("| letters |") for line in section)


def test_slow_request_lines_says_so_when_nothing_was_slow_or_failed():
    section = requestlog.slow_request_lines(["2026-09-19 06:00:00,000 INFO iserv: letters GET /iserv/parentletter/ 200 text/html 1B 5ms"])
    assert section == ["### Slow or failed requests", "- None found in the log"]


def test_messenger_sync_lines_count_and_size_sync_queries_only():
    lines = [
        "2026-09-19 06:00:00,000 INFO iserv: messenger GET /_matrix/client/v3/sync 200 application/json 1300000B 900ms",
        "2026-09-19 06:05:00,000 INFO iserv: messenger GET /_matrix/client/v3/sync 200 application/json 1400000B 850ms",
        "2026-09-19 06:06:00,000 INFO iserv: messenger GET /iserv/messenger/api/rooms/<room>/members 200 application/json 500B 30ms",
    ]
    section = requestlog.messenger_sync_lines(lines)
    assert section[0] == "### Messenger sync"
    assert "- Sync queries: 2" in section
    assert "- Size: total 2 MB, average 1 MB, max 1 MB" in section


def test_slow_request_lines_keep_two_schools_apart():
    lines = [
        "2026-09-26 07:30:00,000 INFO iserv: absences GET /iserv/dsa-absences/ 500 text/html 12B 18000ms school#c691e908",
        "2026-09-26 07:30:01,000 INFO iserv: absences GET /iserv/dsa-absences/ 200 text/html 12B 4000ms school#65f0ebd5",
    ]
    section = requestlog.slow_request_lines(lines)
    assert "| absences school#c691e908 | 1 | 18000ms | 500 |" in section
    assert "| absences school#65f0ebd5 | 1 | 4000ms | 200 |" in section


def test_messenger_sync_lines_show_each_school():
    lines = [
        "2026-09-26 00:27:44,838 INFO iserv: messenger GET /_matrix/client/v3/sync 200 application/json 1387057B 201ms school#c691e908",
        "2026-09-26 00:27:44,897 INFO iserv: messenger GET /_matrix/client/v3/sync 200 application/json 4757B 39ms school#65f0ebd5",
    ]
    section = requestlog.messenger_sync_lines(lines)
    assert "- Sync queries: 2" in section
    assert "- school#c691e908: 1 queries, total 1 MB, max 1 MB" in section
    assert "- school#65f0ebd5: 1 queries, total 4 KB, max 4 KB" in section


def test_messenger_sync_lines_say_so_when_no_sync_seen():
    assert requestlog.messenger_sync_lines([]) == ["### Messenger sync", "- Sync queries: none found in the log"]


def test_the_report_shows_the_slow_request_summary_before_the_log(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, log_lines=[
        "2026-09-19 05:56:00,000 INFO iserv: messenger GET /iserv/messenger/ 200 text/html 12B 9000ms",
    ])
    before_log = report.split("## Log", 1)[0]
    assert "### Slow or failed requests" in before_log
    assert "| messenger | 1 | 9000ms | 200 |" in before_log


E2E_REPORT_SCRIPT = """
from app import diagnostics
from tests import e2e_fixture_app
store = e2e_fixture_app.FixtureStore(e2e_fixture_app.E2E_DATA_DIR / "report")
e2e_fixture_app.seed_config(store)
service = e2e_fixture_app.FixtureService(store)
print(diagnostics.build_report(service, log_lines=["2026-09-19 10:00:00,000 INFO app: boot"], versions={"app": "x", "home_assistant": "y"}))
"""


def test_the_report_of_the_e2e_fixture_passes_the_personal_data_token_check(tmp_path):
    env = dict(
        os.environ,
        ISERV_E2E_DATA_DIR=str(tmp_path),
        ISERV_E2E_MODULES="timetable,letters,pinboard,absences,conferences,messenger",
        PYTHONIOENCODING="utf-8",
    )
    run = subprocess.run(
        [sys.executable, "-c", E2E_REPORT_SCRIPT],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert run.returncode == 0, run.stderr
    report = run.stdout
    assert "## School 1" in report
    assert "| videoconference |" in report
    for number, line in enumerate(report.splitlines(), 1):
        assert not line_contains_forbidden_token(line.lower()), f"line {number}"


E2E_SESSION_REPORT_SCRIPT = """
from app import diagnostics
from app.store import edit_config
from tests import e2e_fixture_app, report_session
store = e2e_fixture_app.FixtureStore(e2e_fixture_app.E2E_DATA_DIR / "report")
e2e_fixture_app.seed_config(store)
service = e2e_fixture_app.FixtureService(store)
for connection in service.connections():
    edit_config(connection.store, report_session.with_course_ids)
clients = {}
def session(self):
    url = self.store.load_config()["school_url"]
    return clients.setdefault(url, report_session.PlantedClient(url))
e2e_fixture_app.FixtureConnection.iserv_session = session
log = ["2026-09-19 10:00:00,000 INFO app: boot"] + report_session.planted_log_line()
print(diagnostics.build_report(service, log_lines=log, versions={"app": "x", "home_assistant": "y"}))
"""


def test_every_live_report_section_of_the_e2e_fixture_hides_planted_personal_data(tmp_path):
    env = dict(
        os.environ,
        ISERV_E2E_DATA_DIR=str(tmp_path),
        ISERV_E2E_MODULES="timetable,letters,pinboard,absences,conferences,messenger",
        PYTHONIOENCODING="utf-8",
    )
    run = subprocess.run(
        [sys.executable, "-c", E2E_SESSION_REPORT_SCRIPT],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert run.returncode == 0, run.stderr
    report = run.stdout
    school = report.split("## School 1", 1)[1].split("## School 2", 1)[0] + report.split("## Log", 1)[1]
    for expected in (
        "- Session: ok",
        "| School account | 1 | 0 | 0 |",
        "| Timetable page | 2 | 0 | 1 |",
        "| School app | 2 | 1 | 1 |",
        "| Letters | 2 | 0 | 0 |",
        "- Settings: timetable_availableForGuardiansAndStudents=yes, substitutions_availableForGuardiansAndStudents=yes",
        "- Timetable query: week=true, substitutions=true, one query per child",
        "- Child 1: courses in filter 2, students 1, entries per student 2",
        "- Timetable slots: 2",
        "- Rows: 2, unread: 1",
        "- Forms: 1, actions: parent-archive-letter",
        "- Source: navigation",
        "| /iserv/addressbook/public/show/<seg> | not probed |",
        "| /iserv/videoconference/room/<seg> | match |",
        "- legal page (/iserv/app/legal): 3.9.1",
        "| mail | /iserv/mail/ | 200 | none |",
        "| videoconference | /iserv/videoconference/room/<seg> | 302 | same host |",
        "#### mail (",
        "- Page: /iserv/videoconference/room/<seg> -> 302 text/html 0B, redirect to same host",
        "(final /iserv/time-table/<seg>/<seg>)",
        "- Form: /iserv/mail/<seg> (post) #form-<word>",
        "  - users[<word>.<word>] (text)",
        "  - child_<word> (text)",
        "  - confirm_<word> (button, label '<word>')",
        "- Table rows #tbl-<word>: 1 (1 cells x1)",
        "section.box-<word>",
        "- Embedded JSON #data-<word>:",
        "  - <key>.<key>.<key>: int >0",
        "  - <key>_<key>: int >0",
        "  - <key>: int >0",
        "- Form: /iserv/mail/<seg>/<seg> (post)",
        "  - link: string len 47, path /iserv/mail/show/<seg>/<seg>",
        "PUT /iserv/mail/api/<seg> script 'inline'",
        "| POST | /iserv/mail/api/<seg>/<seg> | <word>-app.js | - |",
        "- Scripts: /iserv/mail/static/<word>-app.js",
        "- Links: /iserv/mail/folder/<seg> | /iserv/mail/read/<seg> | /iserv/mail/<seg>/list | /iserv/mail/<seg>",
        "iserv: mail GET /iserv/mail/read/<seg>/<seg> 302 - 0B 3ms -> /iserv/mail/show/<seg>/<seg>",
    ):
        assert expected in school, expected
    lowered = report.lower()
    for word in report_session.PLANTED_WORDS:
        assert word.lower() not in lowered, word
    for number, line in enumerate(report.splitlines(), 1):
        assert not line_contains_forbidden_token(line.lower()), f"line {number}"


def test_redact_replaces_names_hosts_mails_and_tokens_but_keeps_plain_words():
    words = diagnostics.RedactionWords(
        children=["Mia Musterkind"], schools=["Gymnasium Nord"], teachers=["Frau Lehrerin"],
        users=["parent.one"], hosts=["gymnasium-nord.example"], secrets=["SuperSecretPass1"],
    )
    line = "Mia said: Musterkind at gymnasium-nord.example, parent.one wrote to x@y.example with SuperSecretPass1 via Gymnasium Nord and Lehrerin"
    redacted = diagnostics.redact(line, words)
    assert "Musterkind" not in redacted
    assert "Mia" not in redacted
    assert "gymnasium-nord" not in redacted
    assert "parent.one" not in redacted
    assert "x@y.example" not in redacted
    assert "SuperSecretPass1" not in redacted
    assert "Gymnasium Nord" not in redacted
    assert "Lehrerin" not in redacted
    assert "said" in redacted and "wrote to" in redacted
    assert diagnostics.redact("custom tomorrow", diagnostics.RedactionWords(children=["Tom"])) == "custom tomorrow"
    assert diagnostics.redact("a b", diagnostics.RedactionWords(children=["a"])) == "a b"


def test_redact_stays_linear_on_pathological_long_lines():
    words = diagnostics.RedactionWords(hosts=["gymnasium-nord.example"], secrets=["SuperSecretPass1"])
    pathological_lines = (
        "a" * 100_000,
        ("token" * 3 + "_") * 20_000,
        ("x." * 50_000) + "de",
        "x" * 100_000 + "@" + "y" * 100_000,
        "https://" + "x" * 200_000,
        "Bearer " + "x" * 200_000,
    )
    for line in pathological_lines:
        start = time.monotonic()
        diagnostics.redact(line, words)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"redact took {elapsed:.2f}s on a {len(line)}-char line"


def test_long_secret_names_and_long_values_are_still_redacted():
    words = diagnostics.RedactionWords(hosts=[], secrets=[])
    name = "a_really_long_cookie_prefix_that_keeps_going_on_" + "session_marker"
    line = f"{name}=AbcDef1234567890 and Bearer {'t' * 3000} and x_{'y' * 40}_token=ZyXw9876"
    redacted = diagnostics.redact(line, words)
    assert "AbcDef1234567890" not in redacted
    assert "ZyXw9876" not in redacted
    assert "t" * 100 not in redacted


def test_path_patterns_hide_ids_uuids_dates_and_long_numbers():
    assert pathpattern.path_pattern("/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000002") == "/iserv/parentletter/parent/show/<uuid>/<uuid>"
    assert pathpattern.path_pattern("/iserv/mystery/entry/4711?date=2026-03-05") == "/iserv/mystery/entry/<n>"
    assert pathpattern.path_pattern("/iserv/dieschulapp/api/1.0/sickNotes/12") == "/iserv/dieschulapp/api/1.0/sickNotes/12"
    assert pathpattern.path_pattern("https://school.example/iserv/x/2026-03-05/") == "/iserv/x/<date>/"
    assert pathpattern.path_pattern("/iserv/file/-/abc/05.03.2026") == "/iserv/file/-/abc/<date>"
    assert pathpattern.placeholders("letter-12345 on 05.03.2026 and 2026-03-05 with 10000000-0000-4000-8000-000000000001") == "letter-<n> on <date> and <date> with <uuid>"


def test_the_ring_buffer_keeps_the_last_lines_from_info_upwards():
    root = logging.getLogger("ringtest")
    root.propagate = False
    root.setLevel(logging.DEBUG)
    handler = logbuffer.install(root, capacity=3)
    try:
        root.debug("quiet")
        for index in range(5):
            root.info("line %s", index)
        root.warning("last")
        lines = handler.lines()
        assert len(lines) == 3
        assert lines[-1].endswith("WARNING ringtest: last")
        assert lines[0].endswith("INFO ringtest: line 3")
        assert not any("quiet" in line for line in lines)
        assert lines[0][:4].isdigit()
    finally:
        root.removeHandler(handler)


def test_the_request_hook_writes_one_structured_line_per_answer(caplog):
    session = requests.Session()
    requestlog.install(session)
    requestlog.install(session)
    assert session.hooks["response"].count(requestlog.log_response) == 1
    response = requests.Response()
    response.status_code = 302
    response.url = "https://school.example/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001/2"
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Location"] = "https://school.example/iserv/auth/login?target=4711"
    response._content = b"<html></html>"
    response.request = requests.Request("GET", response.url).prepare()
    response.elapsed = timedelta(milliseconds=42)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(response)
    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert line == "letters GET /iserv/parentletter/parent/show/<uuid>/<n> 302 text/html 13B 42ms -> /iserv/auth/login"
    assert "school.example" not in line


def test_the_request_hook_leaves_a_session_without_hooks_alone():
    class Bare:
        pass

    bare = Bare()
    assert requestlog.install(bare) is bare


def test_module_tags_follow_the_path():
    assert requestlog.module_tag("/iserv/dieschulapp/api/1.0/pinboards/") == "pinboard"
    assert requestlog.module_tag("/iserv/dieschulapp/api/1.0/sickNotes/") == "absences"
    assert requestlog.module_tag("/iserv/dieschulapp/api/1.0/current-timetable/") == "timetable"
    assert requestlog.module_tag("/iserv/dieschulapp/api/1.0/users/me") == "school-app"
    assert requestlog.module_tag("/_matrix/client/v3/sync") == "messenger"
    assert requestlog.module_tag("/iserv/auth/login") == "auth"
    assert requestlog.module_tag("/iserv/") == "start"
    assert requestlog.module_tag("/iserv/mystery/x") == "mystery"


def test_the_registry_keeps_the_last_probe_answer_per_module():
    pages = {
        modules.PROBES[modules.LETTERS][0]: Response(200, SCHOOL_ONE_URL + modules.PROBES[modules.LETTERS][0], LETTERS_PAGE),
        "/iserv/time-table/": Response(403, SCHOOL_ONE_URL + "/iserv/time-table/", "denied"),
    }
    registry = registry_for(SCHOOL_ONE_URL, pages)
    probe = registry["probes"][modules.LETTERS]
    assert probe["status"] == 200
    assert probe["content_type"] == "text/html"
    assert probe["length"] == len(LETTERS_PAGE.encode("utf-8"))
    assert probe["final_path"] == "/iserv/parentletter/parent/index"
    assert probe["verdict"] == modules.AVAILABLE
    assert registry["probes"][modules.TIMETABLE]["status"] == 403
    assert registry["probes"][modules.CONFERENCES]["status"] == 404
    assert modules.normalize({"probes": {modules.LETTERS: {"status": "200", "extra": 1}}})["probes"][modules.LETTERS]["status"] == 200
    assert modules.normalize({"probes": {"other": {"status": 200}}})["probes"] == {}
    assert modules.default_registry()["probes"] == {}


def test_the_endpoint_returns_the_report_and_honours_the_structure_flag(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    app = create_app(service)
    client = TestClient(app)
    answer = client.get("/api/diagnostics?structure=1")
    assert answer.status_code == 200
    body = answer.json()
    assert body["report"].startswith("# Ranzenpost report")
    assert "### Page structure" in body["report"]
    assert body["segments"] == ["calendar", "mystery"]
    plain = client.get("/api/diagnostics?structure=0").json()["report"]
    assert "### Page structure" not in plain


def test_the_endpoint_never_raises_for_a_school_that_cannot_log_in(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    first.failure = LoginError("bad login")
    client = TestClient(create_app(service))
    answer = client.get("/api/diagnostics")
    assert answer.status_code == 200
    assert "- Session: error (LoginError)" in answer.json()["report"]


def test_the_report_date_is_iso_with_offset(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, clock=lambda: 1_788_000_000)
    stamp = next(line for line in report.splitlines() if line.startswith("- Generated: "))
    moment = datetime.fromisoformat(stamp[len("- Generated: "):])
    assert moment.utcoffset() is not None


def script_section(report):
    messenger = report.split("#### messenger (", 1)[1]
    return messenger.split("\n#### ", 1)[0].split("\n## ", 1)[0]


def endpoint_rows(section):
    return [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Method")]


def test_script_endpoints_list_method_path_script_and_credential_keys(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    section = script_section(build(service, structure=True))
    assert "##### Script endpoints" in section
    assert "- Scripts: /iserv/messenger/static/assets/chat-standalone-<hash>.js (%dB) | /iserv/messenger/static/assets/vendor-<hash>.js (truncated at %dB)" % (
        len(CHAT_SCRIPT_TEXT.encode("utf-8")), reportcrawl.MAX_SCRIPT_BYTES) in section
    assert "| Method | Path | Script | Keys nearby |" in section
    rows = endpoint_rows(section)
    assert rows == [
        "| PUT | /_matrix/client/v3/rooms/<expr>/typing/<expr> | chat-standalone-<hash>.js | userId |",
        "| - | <expr>/_matrix/client/v3/sync | chat-standalone-<hash>.js | - |",
        "| - | /api/v2/unread | chat-standalone-<hash>.js | - |",
        "| - | /iserv/messenger | chat-standalone-<hash>.js | - |",
        "| POST | /iserv/messenger/api/auth/token | chat-standalone-<hash>.js | access_token, device_id, homeserver, user_id |",
        "| - | /iserv/messenger/api/before-cap | vendor-<hash>.js | - |",
        "| POST | /iserv/messenger/api/reports/<expr>/close | chat-standalone-<hash>.js | - |",
        "| GET | /iserv/messenger/api/rooms/<n>/members | chat-standalone-<hash>.js | - |",
        "| - | /messenger/<expr> | chat-standalone-<hash>.js | - |",
    ]
    for literal in ("Alex Example", "Hello parent", "application/json", "Content-Type", "./vendor", "after-cap", "4711", "a1b2c3d4", "9f8e7d6c5b4a", "fff", "family.example"):
        assert literal not in section, literal


def test_scripts_from_other_hosts_are_never_fetched_and_the_limits_are_passed(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    build(service, structure=True)
    assert first.client.capped_calls == [
        (CHAT_SCRIPT, reportcrawl.MAX_SCRIPT_BYTES, reportcrawl.SCRIPT_TIMEOUT),
        (VENDOR_SCRIPT, reportcrawl.MAX_SCRIPT_BYTES, reportcrawl.SCRIPT_TIMEOUT),
    ]
    assert not any("tracker" in path for path, _limit, _timeout in first.client.capped_calls)
    assert reportcrawl.MAX_SCRIPT_BYTES == 2 * 1024 * 1024
    assert reportcrawl.SCRIPT_TIMEOUT == 5
    assert reportcrawl.MAX_SCRIPTS_PER_MODULE == 8


def test_at_most_eight_scripts_per_module_are_read_and_each_only_once(tmp_path):
    tags = "".join('<script src="/iserv/many/static/bundle-%02d0000.js"></script>' % index for index in range(10))
    page = "<html><body>%s<script src=\"/iserv/many/static/bundle-000000.js\"></script></body></html>" % tags
    words = ("list", "show", "items", "entries", "events", "members", "messages", "rooms", "users", "files")
    scripts = {"/iserv/many/static/bundle-%02d0000.js" % index: 'fetch("/iserv/many/api/%s")' % words[index] for index in range(10)}
    client = Client(SCHOOL_ONE_URL, {"/iserv/many/": Response(200, SCHOOL_ONE_URL + "/iserv/many/", page)}, scripts)
    row = {"slug": "many", "name": "Many", "page": "/iserv/many/", "json": None}
    lines = diagnostics.page_structure(client, row, datetime(2026, 9, 19).date(), {})
    assert len(client.capped_calls) == 8
    assert len({path for path, _limit, _timeout in client.capped_calls}) == 8
    text = "\n".join(lines)
    assert "- Scripts skipped: 2 beyond the limit of 8" in text
    assert "| GET | /iserv/<seg>/api/rooms | bundle-<hash>.js | - |" in text
    assert "api/users" not in text
    assert "api/files" not in text


def test_a_page_without_external_scripts_has_no_script_subsection(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    report = build(service, structure=True)
    mystery = report.split("#### mystery (", 1)[1].split("\n#### ", 1)[0]
    assert "Script endpoints" not in mystery


def test_the_script_section_contains_no_person_host_or_mail(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    section = script_section(build(service, structure=True))
    lowered = section.lower()
    for word in PERSON_WORDS:
        assert word.lower() not in lowered, word
    assert "@" not in section
    assert "gymnasium" not in lowered
    for number, line in enumerate(section.splitlines(), 1):
        assert not line_contains_forbidden_token(line.lower()), f"line {number}"


def test_script_endpoint_extraction_covers_verbs_templates_and_concatenations():
    text = (
        'fetch(this.base+"/iserv/x/"+id+"/y",{method:"delete"});'
        'axios({url:"/api/plain",method:"PATCH"});'
        'http.put(`/_matrix/media/v3/upload?filename=${name}`);'
        'const junk="/";const other="not/a/path";const label="Hello there";'
        + 'const pad="' + "p" * 400 + '";'
        + 'req.open("GET", "/iserv/z/12345678-1234-4123-8123-123456789012/file/20260919");'
        'const key={matrix_access_token:1,accessToken:2,refresh_token:3};'
        + 'const pad2="' + "q" * 400 + '";'
        + 'this.http.authedRequest(Method.Post, "/rooms/$roomId/send/$eventType");'
        'const single="/single";const folder="/static/";const flag="/";'
    )
    found = scriptscan.script_endpoints(text, "one.js")
    assert found == {
        ("DELETE", "<expr>/iserv/x/<expr>/y", "one.js"): set(),
        ("PATCH", "/api/plain", "one.js"): set(),
        ("PUT", "/_matrix/media/v3/upload", "one.js"): set(),
        ("GET", "/iserv/z/<uuid>/file/<n>", "one.js"): {"matrix_access_token", "accessToken", "refresh_token"},
        ("-", "/rooms/$roomId/send/$eventType", "one.js"): set(),
    }


def test_script_labels_hide_names_in_file_names():
    assert scriptscan.script_label("/iserv/mail/static/erika-app.js") == "<word>-app.js"
    assert scriptscan.script_label("/iserv/mail/static/jonas.pflanzkind.js") == "<word>.<word>.js"
    assert scriptscan.script_label("/iserv/mail/static/app-12.js") == "app-<n>.js"


def test_script_labels_hide_hashes_but_keep_plain_names():
    assert scriptscan.script_label("/iserv/messenger/static/assets/chat-standalone-a1b2c3d4.js?v=3") == "chat-standalone-<hash>.js"
    assert scriptscan.script_label("/iserv/js/main.7f3a9c2b1d.chunk.js") == "main.<hash>.chunk.js"
    assert scriptscan.script_label("/iserv/js/index-BqK3x9Zp.min.js") == "index-<hash>.min.js"
    assert scriptscan.script_label("/iserv/js/parentletter.js") == "parentletter.js"
    assert scriptscan.script_label("/iserv/js/vendor~chunk.abc123def456789012345678.js") == "vendor~chunk.<hash>.js"


def test_the_endpoint_limits_the_structure_to_one_module_but_always_shows_unknown_ones(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    client = TestClient(create_app(service))
    report = client.get("/api/diagnostics?module=messenger").json()["report"]
    assert "- Structure module: messenger" in report
    assert "#### messenger (" in report
    assert "#### parentletter (" not in report
    assert "#### mystery (" in report
    assert "| parentletter |" in report
    assert "##### Script endpoints" in report
    missing = client.get("/api/diagnostics?module=nothing-here").json()["report"]
    assert "- Not read: no module named nothing-here" in missing
    assert "#### mystery (" in missing
    assert "#### messenger (" not in missing
    assert "#### parentletter (" not in missing
    odd = client.get("/api/diagnostics?module=%3Cscript%3E").json()["report"]
    assert "<script>" not in odd
    assert "- Not read: no module named script" in odd


class StreamedAnswer:
    def __init__(self, chunks, status_code=200):
        self.chunks = chunks
        self.status_code = status_code
        self.closed = False
        self.encoding = "utf-8"

    def iter_content(self, chunk_size=1):
        for chunk in self.chunks:
            yield chunk

    def close(self):
        self.closed = True


class StreamingSession:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.headers = {}
        self.hooks = {"response": []}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.answer


def test_the_client_reads_a_capped_script_and_stops_at_the_limit():
    answer = StreamedAnswer([b"abc", b"def", b"ghi", b"jkl"])
    session = StreamingSession(answer)
    client = IServClient("https://school.example", session=session)
    body = client.fetch_capped("/iserv/js/a.js", 7, 10)
    assert body == CappedBody(200, "abcdefg", True)
    assert answer.closed
    url, kwargs = session.calls[0]
    assert url == "https://school.example/iserv/js/a.js"
    assert kwargs["timeout"] == 10
    assert kwargs["stream"] is True
    assert kwargs["allow_redirects"] is False
    whole = IServClient("https://school.example", session=StreamingSession(StreamedAnswer([b"ab", b"cd"]))).fetch_capped("/iserv/js/b.js", 7, 10)
    assert whole == CappedBody(200, "abcd", False)


TIME_TABLE_ROW = {"slug": "timetable", "name": "Stundenplan", "page": "/iserv/time-table/", "json": None, "data": "/iserv/time-table/data"}
PLAIN_TIME_TABLE = "<html><body><table id='timetable-content-changes'><tr><th>Datum</th><th>Stunde</th></tr></table></body></html>"


def time_table_client(page_html, data=None):
    recorded = []
    pages = {
        "/iserv/time-table/data": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/data", "{}", "application/json", json_data=data or {"meta": {}, "data": {"timetable": []}}),
        "/iserv/time-table/": Response(200, SCHOOL_ONE_URL + "/iserv/time-table/", page_html),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    fetch = client.fetch

    def recording(path, params=None):
        recorded.append((path, params))
        return fetch(path, params)

    client.fetch = recording
    return client, recorded


def test_a_single_child_page_without_a_select_is_probed_without_a_child():
    client, recorded = time_table_client(PLAIN_TIME_TABLE)
    children = [{"child_id": "4711", "name": CHILD_ONE}]
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "4711", children)
    assert "- Child select: none" in lines
    assert "- Data query: week filter without childId" in lines
    assert "- Page: /iserv/time-table/data -> 200 application/json 2B" in lines
    assert "  - data.timetable: array len 0" in lines
    params = [params for path, params in recorded if path == "/iserv/time-table/data"][0]
    assert "childId" not in params
    assert '"startDate":"21.09.2026"' in params["filter"]


def test_a_page_without_a_select_is_not_probed_for_two_children():
    client, recorded = time_table_client(PLAIN_TIME_TABLE)
    children = [{"child_id": "4711", "name": CHILD_ONE}, {"child_id": "4712", "name": CHILD_TWO}]
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "4711", children)
    assert "- Data: not read, no child select and 2 listed children" in lines
    assert not [path for path, _params in recorded if path == "/iserv/time-table/data"]


def test_a_select_without_the_listed_child_is_not_probed():
    page = "<select id='timetable-filter-child-select'><option value='x-1'>Robin Anders</option><option value='x-2'>Sam Anders</option></select>"
    client, recorded = time_table_client(page)
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "4711", [{"child_id": "4711", "name": CHILD_ONE}, {"child_id": "4712", "name": CHILD_TWO}])
    assert "- Child select: present, options 2, listed children 2" in lines
    assert "- Data: not read, no listed child matches the child select" in lines
    assert not [path for path, _params in recorded if path == "/iserv/time-table/data"]


def test_table_rows_are_counted_per_row_shape_without_cell_text():
    html = (
        "<table id='timetable-content-timetable'><tr><th>Std.</th><th>Montag</th><th>Dienstag</th></tr>"
        "<tr><td>1</td><td>Secret row</td><td>Alex Example</td></tr><tr><td>2</td><td>x</td><td>y</td></tr>"
        "<tr><td colspan='3'>Hinweis fuer Alex Example</td></tr></table><table></table>"
    )
    lines = pageshape.html_skeleton(html)
    assert "- Table rows #timetable-content-timetable: 4 (1 cells x1, 3 cells x3)" in lines
    assert "- Table rows (no id): 0" in lines
    assert not any("Secret" in line or "Alex" in line or "Hinweis" in line for line in lines)


MATRIX_PATH = "https://matrix.example/_matrix/client/v3/rooms/!ckNsmbrtnUzxgVSMbQ:12345678-1234-4123-8123-123456789012/messages?from=abc"


def test_matrix_room_ids_are_masked_in_paths_logs_and_reports():
    assert pathpattern.path_pattern(MATRIX_PATH) == "/_matrix/client/v3/rooms/<room>/messages"
    assert pathpattern.placeholders("/rooms/%21AbCdEfGh%3Aiserv.example/state") == "/rooms/<room>/state"
    assert diagnostics.scrub_line("sync room !AbCdEfGhIj:iserv.example:8448 failed") == "sync room <room> failed"
    assert diagnostics.scrub_line("rooms/!ckNsmbrtnUzxgVSMbQ:<uuid>/messages") == "rooms/<room>/messages"
    assert diagnostics.scrub_line("Hallo! Termin: morgen") == "Hallo! Termin: morgen"


def test_the_request_log_masks_a_matrix_room(caplog):
    class Answer:
        url = MATRIX_PATH
        status_code = 200
        headers = {"Content-Type": "application/json"}
        content = b"{}"
        request = None
        elapsed = None

    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(Answer())
    assert "ckNsmbrtnUzxgVSMbQ" not in caplog.text
    assert "/_matrix/client/v3/rooms/<room>/messages" in caplog.text


def test_the_report_names_the_timetable_source(tmp_path):
    service, first, _second = two_school_service(tmp_path)
    edit_config(first.store, lambda config: config.update(timetable_source="time-table"))
    report = build(service, structure=False)
    one, two = report.split("## School 1", 1)[1].split("## School 2", 1)
    assert "- Timetable source: time-table" in one
    assert "- Timetable source: school-app" in two


def test_the_report_counts_the_listed_children_the_way_the_app_does():
    page = "<select id='timetable-filter-child-select'><option value='x-1'>Robin Anders</option></select>"
    client, recorded = time_table_client(page)
    children = [{"child_id": "4711", "name": CHILD_ONE}]
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "4711", children, 2)
    assert "- Child select: present, options 1, listed children 2" in lines
    assert "- Data: not read, no listed child matches the child select" in lines
    assert not [path for path, _params in recorded if path == "/iserv/time-table/data"]


class CountingConnection:
    def __init__(self, count):
        self.count = count

    def listed_child_count(self):
        return self.count


def test_the_listed_count_comes_from_the_connection_and_falls_back_to_the_stored_children():
    children = [{"child_id": "4711", "name": CHILD_ONE}]
    assert diagnostics._listed_count(CountingConnection(3), children) == 3
    assert diagnostics._listed_count(CountingConnection(0), children) == 1
    assert diagnostics._listed_count(object(), children) == 1


def test_time_table_data_lines_report_change_counts_and_shape():
    payload = {
        "meta": {"filter": {}},
        "data": {"timetable": [{"date": "23.09.2026", "period": 1, "subject": "Mathe", "teacher": "Herr X", "room": "101", "class": "5a", "id": 1}]},
        "plain-changes": [
            {"date": "23.09.2026", "period": 1, "origSubject": "Mathe", "substitutionRoom": "102", "updated": "2026-09-23T05:00:00"},
            {"date": "23.09.2026", "period": 2, "origSubject": "Unknown", "updated": "2026-09-23T05:01:00"},
        ],
    }
    client, _recorded = time_table_client(PLAIN_TIME_TABLE, data=payload)
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "", [], 1)
    assert "- Time-table changes: raw 2, applied 1" in lines
    assert "- Time-table change record shape:" in lines
    assert "Herr X" not in "\n".join(lines)


def test_time_table_data_lines_skip_change_counts_without_plain_changes():
    payload = {"meta": {"filter": {}}, "data": {"timetable": []}, "plain-changes": []}
    client, _recorded = time_table_client(PLAIN_TIME_TABLE, data=payload)
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "", [], 1)
    assert not any(line.startswith("- Time-table changes:") for line in lines)


def test_a_login_page_instead_of_the_time_table_is_reported_as_absent():
    client, recorded = time_table_client("<form><input name='_password'></form>")
    lines = diagnostics.page_structure(client, TIME_TABLE_ROW, datetime(2026, 9, 23).date(), {}, "4711", [{"child_id": "4711", "name": CHILD_ONE}])
    assert "- Data: not read, the session has expired (login page)" in lines
    assert not [path for path, _params in recorded if path == "/iserv/time-table/data"]


def test_unsupported_module_lines_probe_the_real_link_and_never_leak_a_redirect_token():
    menu_html = '<html><body><nav><a href="/iserv/klassengeld/redirect">Klassengeld</a></nav></body></html>'
    redirect_response = Response(302, SCHOOL_ONE_URL + "/iserv/klassengeld/redirect", "")
    redirect_response.headers["Location"] = "https://sso.klassengeld.example/login?token=synthetic-secret-abcdef123456"
    pages = {
        "/iserv/klassengeld/redirect": redirect_response,
        reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL, menu_html),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    rows = [{"slug": "klassengeld", "segment": "klassengeld", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED}]
    lines = reportcrawl.unsupported_module_lines(client, rows, menu_of(client))
    joined = "\n".join(lines)
    assert "synthetic-secret" not in joined
    assert "token" not in joined
    assert "sso.klassengeld.example" not in joined
    assert lines[0] == "### Unsupported or unknown modules"
    assert "| klassengeld | /iserv/klassengeld/redirect | 302 | other host |" in lines


class RecordingAdapter(requests.adapters.BaseAdapter):
    def __init__(self, answers):
        super().__init__()
        self.answers = answers
        self.sent = []
        self.cookies = {}

    def send(self, request, **kwargs):
        self.sent.append(request.url)
        self.cookies[request.url] = request.headers.get("Cookie", "")
        status, headers, body = self.answers.get(request.url.split("?", 1)[0], (404, {}, b""))
        response = requests.Response()
        response.status_code = status
        response.headers.update(headers)
        response.raw = body if hasattr(body, "read") else io.BytesIO(body)
        response.url = request.url
        response.request = request
        response.connection = self
        return response

    def close(self):
        pass


def recording_client(answers):
    adapter = RecordingAdapter(answers)

    def mounted():
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    client = IServClient(SCHOOL_ONE_URL, session=mounted())
    client.new_chain_session = mounted
    client.resolve_host = fake_resolver
    return client, adapter


FAKE_ADDRESSES = {
    "pay.other.example": ["93.184.216.34", "2606:2800:220:1::1"],
    "127.1": ["127.0.0.1"],
    "0x7f.0.0.1": ["127.0.0.1"],
    "10.1": ["10.0.0.1"],
    "nas.10-0-0-5.nip.io": ["10.0.0.5"],
    "mixed.example": ["93.184.216.34", "192.168.1.20"],
}


def fake_resolver(host):
    if host not in FAKE_ADDRESSES:
        raise OSError("unknown host")
    return FAKE_ADDRESSES[host]


FOREIGN_SSO = "https://pay.other.example/sso/eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl?code=synthetic-code-0001#frag"
FOREIGN_WORDS = ("pay.other", "eyj", "c2lnbmf0dxjl", "synthetic-code", "/sso", "frag")


def test_the_real_client_never_follows_a_module_redirect_to_another_host(caplog):
    redirect = SCHOOL_ONE_URL + "/iserv/klassengeld/redirect"
    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/": (200, {"Content-Type": "text/html"}, b'<nav><a href="/iserv/klassengeld/redirect">K</a></nav>'),
        redirect: (302, {"Location": FOREIGN_SSO, "Content-Type": "text/html"}, b""),
        FOREIGN_SSO.split("?", 1)[0]: (200, {"Content-Type": "text/html"}, b"<html>dashboard</html>"),
    })
    rows = [{"slug": "klassengeld", "segment": "klassengeld", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED}]
    with caplog.at_level(logging.INFO, logger="iserv"):
        lines = reportcrawl.unsupported_module_lines(client, rows, menu_of(client))
    assert adapter.sent.count(redirect) == 1
    assert not [url for url in adapter.sent if "pay.other.example" in url]
    assert "| klassengeld | /iserv/klassengeld/redirect | 302 | other host |" in lines
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "GET /iserv/klassengeld/redirect 302 text/html 0B" in logged
    assert "-> <other host>" in logged
    for text in ("\n".join(lines).lower(), logged.lower()):
        for word in FOREIGN_WORDS:
            assert word not in text, word


def test_the_structure_of_a_linked_module_uses_the_menu_link_and_stops_at_its_redirect():
    redirect = SCHOOL_ONE_URL + "/iserv/klassengeld/redirect"
    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/": (200, {"Content-Type": "text/html"}, b'<nav><a href="/iserv/klassengeld/redirect">K</a></nav>'),
        redirect: (302, {"Location": FOREIGN_SSO, "Content-Type": "text/html"}, b""),
    })
    fetcher = diagnostics.ReportFetcher(client)
    nav_paths = menu_of(fetcher)
    row = {"slug": "klassengeld", "segment": "klassengeld", "name": "Klassengeld", "page": "/iserv/klassengeld/", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(fetcher, row, datetime(2026, 9, 23).date(), {}, nav_paths=nav_paths)
    assert lines == [
        "#### klassengeld (Klassengeld)",
        "- Page: /iserv/klassengeld/redirect -> 302 text/html 0B, redirect to other host",
        "- Redirect chain: 302 same host -> 404 other host",
        "- Landing page: 404 - 0B",
    ]
    assert adapter.sent == [SCHOOL_ONE_URL + "/iserv/", redirect, FOREIGN_SSO.split("#", 1)[0]]


PROVIDER_LOGIN = "https://pay.other.example/sso/login?ticket=synthetic-ticket-0042"
PROVIDER_HOME = "https://pay.other.example/tenant/gymnasium-nord/dashboard/k3jf8Hs9dK2lLmQ0pZx7"
PROVIDER_PAGE = b"""
<html><head><title>Kontostand Jonas Pflanzkind</title>
<script src="/assets/app-9f8e7d6c5b4a.js"></script></head><body>
<nav id="provider-nav"><a href="/tenant/gymnasium-nord/invoices/4711">Rechnungen</a><a href="/tenant/gymnasium-nord/profile/jonas.pflanzkind">Jonas</a>
<a href="/dashboard">Dashboard</a><a href="/projects">Projekte</a><a href="/transactions">Buchungen</a>
<a href="/remind/4711">Details</a><a href="/api/bank/refresh">Details</a><a href="/logoff">Details</a><a href="/session/end">Details</a></nav>
<script>fetch("/api/overview");</script>
<main>
<h1>Hallo Erika Saatmuster</h1>
<form action="/tenant/gymnasium-nord/pay/Xk29dLm3PqR8sT4v" method="post" id="payment">
<input type="hidden" name="csrf" value="synthetic-csrf-9911">
<input type="text" name="amount" value="42,50 EUR" required>
<button type="submit" name="pay">Jonas Pflanzkind 42,50 EUR bezahlen</button>
</form>
<table id="invoices"><tr><th>Rechnung</th><th>Betrag</th></tr><tr><td>Klassenfahrt Jonas</td><td>123,45 EUR</td></tr></table>
<script type="application/json" id="state">{"child": "Jonas Pflanzkind", "balance": "123,45", "iban": "DE02120300000000202051"}</script>
</main></body></html>
"""
PROVIDER_SCRIPT = b'fetch("/api/tenants/gymnasium-nord/balance",{method:"POST"});axios.get("/api/v2/invoices/"+id);'
PROVIDER_WORDS = (
    "pay.other", "sso", "ticket", "synthetic-ticket", "gymnasium-nord", "k3jf8", "xk29d", "4711", "jonas", "pflanzkind",
    "erika", "saatmuster", "42,50", "123,45", "synthetic-csrf", "de0212", "kontostand", "klassenfahrt", "eyj", "synthetic-code",
)


def provider_chain_client():
    return recording_client({
        SCHOOL_ONE_URL + "/iserv/": (200, {"Content-Type": "text/html"}, b'<nav><a href="/iserv/klassengeld/redirect">K</a></nav>'),
        SCHOOL_ONE_URL + "/iserv/klassengeld/redirect": (302, {"Location": FOREIGN_SSO, "Content-Type": "text/html"}, b""),
        FOREIGN_SSO.split("?", 1)[0]: (302, {"Location": PROVIDER_LOGIN}, b""),
        PROVIDER_LOGIN.split("?", 1)[0]: (302, {"Location": PROVIDER_HOME}, b""),
        PROVIDER_HOME: (200, {"Content-Type": "text/html; charset=utf-8"}, PROVIDER_PAGE),
        "https://pay.other.example/assets/app-9f8e7d6c5b4a.js": (200, {"Content-Type": "text/javascript"}, PROVIDER_SCRIPT),
        "https://pay.other.example/dashboard": (200, {"Content-Type": "text/html"}, b"<html><body><h1>Jonas</h1></body></html>"),
        "https://pay.other.example/projects": (200, {"Content-Type": "text/html"}, b"<html><body><h1>Jonas</h1></body></html>"),
        "https://pay.other.example/transactions": (200, {"Content-Type": "text/html"}, b"<html><body><h1>Jonas</h1></body></html>"),
    })


KLASSENGELD_ROW = {"slug": "klassengeld", "segment": "klassengeld", "name": "Klassengeld", "page": "/iserv/klassengeld/", "json": None, "guessed_page": True}


def test_the_structure_of_an_external_module_follows_its_sign_in_chain_and_keeps_only_shapes(caplog):
    client, adapter = provider_chain_client()
    client.session.cookies.set("IServSession", "synthetic-iserv-cookie", domain="gymnasium-nord.example")
    fetcher = diagnostics.ReportFetcher(client)
    nav_paths = menu_of(fetcher)
    with caplog.at_level(logging.INFO, logger="iserv"):
        lines = diagnostics.page_structure(fetcher, KLASSENGELD_ROW, datetime(2026, 9, 23).date(), {}, nav_paths=nav_paths)
    assert "- Redirect chain: 302 same host -> 302 other host -> 302 other host -> 200 other host" in lines
    assert any(line.startswith("- Landing page: 200 text/html ") for line in lines)
    assert "- Form: /<seg>/<seg>/<seg>/<seg> (post) #payment" in lines
    assert "  - amount (text, required)" in lines
    assert "  - pay (button, label '<word> <word> <n>,<n> <word> <word>')" in lines
    assert "- Functions: write candidates: POST /<seg>/<seg>/<seg>/<seg> form 'payment' buttons pay; POST /api/<seg>/<seg>/<seg> script 'app-<hash>.js'" in lines
    assert "- Table headers: Rechnung | <word>" in lines
    assert any(line.startswith("- Embedded JSON #state:") for line in lines)
    assert "  - iban: string len 22, hex" in lines
    assert any(line.startswith("- Scripts: /assets/app-<hash>.js") for line in lines)
    assert "| POST | /api/<seg>/<seg>/<seg> | app-<hash>.js | - |" in lines
    external = [url for url in adapter.sent if "pay.other.example" in url]
    provider_paths = [url.split("pay.other.example", 1)[1] for url in external]
    for path in ("/dashboard", "/projects", "/transactions"):
        assert path in provider_paths, path
    for path in ("/remind/4711", "/api/bank/refresh", "/logoff", "/session/end", "/api/overview", "/api/v2/invoices/"):
        assert not [found for found in provider_paths if found.startswith(path)], path
    assert len(external) == 7
    assert all(adapter.cookies[url] == "" for url in external)
    assert "synthetic-iserv-cookie" in adapter.cookies[SCHOOL_ONE_URL + "/iserv/klassengeld/redirect"]
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for text in ("\n".join(lines).lower(), logged.lower()):
        for word in PROVIDER_WORDS:
            assert word not in text, word


LOAN = SCHOOL_ONE_URL + "/iserv/ausleihe/"
LOAN_LIST = """
<html><head><title>Ausleihen von Jonas Pflanzkind</title></head><body>
<nav><a href="/iserv/calendar/">Kalender</a><a href="/iserv/ausleihe/logout">Abmelden</a></nav>
<ul class="tabs"><li><a href="/iserv/ausleihe/overview">Übersicht</a></li><li><a href="/iserv/ausleihe/list">Liste</a></li>
<li><a href="/iserv/ausleihe/archive">Archiv</a></li><li><a href="/iserv/ausleihe/history">Verlauf</a></li>
<li><a href="/iserv/ausleihe/current">Alle</a></li></ul>
<table id="loans"><tr><th>Geraet</th><th>Betrag</th></tr>
<tr><td><a href="/iserv/ausleihe/show/4711">Laptop Jonas Pflanzkind</a></td><td>12,50 EUR</td></tr>
</table>
<a href="/iserv/ausleihe/list?page=2">2</a>
<a href="/iserv/ausleihe/index">Weiter</a>
<a href="/iserv/ausleihe/list?page=2&amp;owner=jonas">2</a>
<a href="/iserv/ausleihe/files/Jonas-Vertrag.pdf">Vertrag</a>
</body></html>
""".encode("utf-8")
LOAN_OVERVIEW = b"""
<html><head><title>Laptop Jonas Pflanzkind</title></head><body>
<form action="/iserv/ausleihe/return/4711" method="post" id="return-form">
<label for="note">Notiz fuer Herr Keimling</label><input id="note" name="note" value="Jonas bringt es 12,50">
<select name="reason"><option>kaputt</option><option>fertig</option></select>
<button type="submit" name="return">Laptop Jonas Pflanzkind zurueckgeben</button>
</form>
<div class="card">Jonas</div><div class="card-body">Erika</div>
<script>
fetch("/iserv/ausleihe/api/extend/4711", {method: "POST"});
fetch("/iserv/ausleihe/api/items");
fetch("/iserv/ausleihe/api/remove-all");
</script>
</body></html>
"""
LOAN_ITEMS = b'[{"owner": "Jonas Pflanzkind", "id": 4711, "fee": "12,50"}]'
LOAN_ALLOWED = ("overview", "list", "archive", "history", "current", "list?page=2", "index")
LOAN_NOT_FETCHED = (
    "/iserv/ausleihe/show/4711", "/iserv/ausleihe/logout", "/iserv/ausleihe/files/Jonas-Vertrag.pdf", "/iserv/calendar/",
    "/iserv/ausleihe/api/remove-all", "/iserv/ausleihe/api/extend/4711", "/iserv/ausleihe/return/4711",
    "/iserv/ausleihe/list?page=2&owner=jonas",
)
LOAN_WORDS = ("jonas", "pflanzkind", "erika", "saatmuster", "keimling", "12,50", "4711", "laptop", "vertrag")
LOAN_ROW = {"slug": "ausleihe", "segment": "ausleihe", "name": "<word>", "page": "/iserv/ausleihe/", "json": None, "guessed_page": True}


def loan_client(landing=LOAN_LIST, extra=None):
    answers = {
        SCHOOL_ONE_URL + "/iserv/": (200, {"Content-Type": "text/html"}, b'<nav><a href="/iserv/ausleihe/">Ausleihe</a></nav>'),
        LOAN: (200, {"Content-Type": "text/html"}, landing),
        LOAN + "overview": (200, {"Content-Type": "text/html"}, LOAN_OVERVIEW),
        LOAN + "api/items": (200, {"Content-Type": "application/json"}, LOAN_ITEMS),
    }
    for route in ("list", "archive", "history", "current", "index"):
        answers[LOAN + route] = (200, {"Content-Type": "text/html"}, b"<html><body><p>Jonas</p></body></html>")
    answers.update(extra or {})
    return recording_client(answers)


def loan_structure(budget=None, landing=LOAN_LIST, row=LOAN_ROW):
    client, adapter = loan_client(landing)
    fetcher = diagnostics.ReportFetcher(client)
    if budget is not None:
        fetcher.budget = budget
    nav_paths = menu_of(fetcher)
    lines = diagnostics.page_structure(fetcher, row, datetime(2026, 9, 23).date(), {}, nav_paths=nav_paths)
    return lines, adapter


def fetched_paths(adapter):
    return [url.split(SCHOOL_ONE_URL, 1)[-1] for url in adapter.sent]


def test_a_module_crawl_reads_allowed_pages_and_names_its_write_functions():
    lines, adapter = loan_structure()
    fetched = fetched_paths(adapter)
    for path in LOAN_NOT_FETCHED:
        assert path not in fetched, path
    assert [path for path in fetched if path.startswith("/iserv/ausleihe/") and "/api/" not in path and path != "/iserv/ausleihe/"] == [
        "/iserv/ausleihe/" + route for route in LOAN_ALLOWED[:5]
    ]
    assert "/iserv/ausleihe/api/items" in fetched
    assert "- Crawl: 5 linked pages, skipped path not allowed 2, query not allowed 1, detail page 1, other module 1, limit 2" in lines
    assert "##### Page /iserv/<seg>/overview" in lines
    assert "  - reason (select, options 2)" in lines
    assert "  - note (text, label '<word> fuer <word> <word>')" in lines
    assert "- Lists: 0 with 0 items, cards: 2" in lines
    assert "##### API GET /iserv/<seg>/api/items" in lines
    assert "  - [].owner: string len 16, free text" in lines
    functions = next(line for line in lines if line.startswith("- Functions: "))
    assert "POST /iserv/<seg>/<seg>/<n> form 'return-form' buttons return" in functions
    assert "POST /iserv/<seg>/api/<seg>/<n> script 'inline'" in functions
    joined = "\n".join(lines).lower()
    for word in LOAN_WORDS:
        assert word not in joined, word


REVIEW_PATHS = (
    "markallread", "readall", "markasread", "read/5", "seen", "deleteall", "logoutall", "done", "close", "pin", "gelesen",
    "erledigt", "zusagen", "reservieren", "eintragen", "bestaetigung", "confirmation", "unarchive", "switch_user",
    "list?_token=abc", "list?do=read",
)
REVIEW_ANCHORS = (
    '<a href="/iserv/ausleihe/overview">Als gelesen markieren</a>',
    '<a href="/iserv/ausleihe/history">Log out</a>',
    '<a href="/iserv/ausleihe/current">Ausloggen</a>',
    '<a href="/iserv/ausleihe/today" data-method="post">Alle</a>',
    '<a href="/iserv/ausleihe/week" data-confirm="sure">Alle</a>',
    '<a href="/iserv/ausleihe/month" onclick="go()">Alle</a>',
)


def test_a_module_crawl_follows_no_link_outside_the_read_only_allowlist():
    anchors = "".join('<a href="/iserv/ausleihe/%s">Alle</a>' % path for path in REVIEW_PATHS) + "".join(REVIEW_ANCHORS)
    landing = ("<html><body>%s</body></html>" % anchors).encode("utf-8")
    lines, adapter = loan_structure(landing=landing)
    assert fetched_paths(adapter) == ["/iserv/", "/iserv/ausleihe/"]
    assert "- Crawl: 0 linked pages, skipped path not allowed 18, query not allowed 2, script attribute 3, text not allowed 3, detail page 1" in lines


NEWS_ENTRIES = """
<html><body>
<ul>
<li><span class="badge">Neu</span><a href="/iserv/news/show/1">Alle</a></li>
<li class="fw-bold"><a href="/iserv/news/show/2">Alle</a></li>
<li class="isUnread"><a href="/iserv/news/show/3">Alle</a></li>
<li data-read="false"><a href="/iserv/news/show/4">Alle</a></li>
</ul>
<div class="card"><a href="/iserv/news/show/5">Alle</a></div>
<a href="/iserv/news/entry?id=5">Alle</a>
<a href="/iserv/news/show/my-first-post">Alle</a>
<a href="/iserv/news/message/7"><i class="fa fa-envelope"></i></a>
<table><tr><td><a href="/iserv/news/show/12">Alle</a></td></tr></table>
</body></html>
"""


def test_no_detail_page_of_any_module_is_opened():
    lines, adapter = loan_structure(landing=NEWS_ENTRIES.replace("/iserv/news/", "/iserv/ausleihe/").encode("utf-8"))
    assert fetched_paths(adapter) == ["/iserv/", "/iserv/ausleihe/"]
    assert "- Crawl: 0 linked pages, skipped path not allowed 2, detail page 7" in lines


LETTER_ROW = {"slug": "parentletter", "name": "Elternbriefe", "page": modules.PROBES[modules.LETTERS][0], "json": None}


LETTER_SHOW = "/iserv/parentletter/parent/show/10000000-0000-4000-8000-00000000000%d/20000000-0000-4000-8000-00000000000%d"
LETTER_VARIANTS = (
    '<tr><td><a href="{href}">Alle</a></td></tr>',
    '<tr class="unreadRow"><td><a href="{href}">Alle</a></td></tr>',
    '<tr class="fw-bold"><td><a href="{href}">Alle</a></td></tr>',
    '<tr style="font-weight:bold"><td><a href="{href}">Alle</a></td></tr>',
    '<tr data-unread="1"><td><a href="{href}">Alle</a></td></tr>',
    '<tr><td><span class="badge">Neu</span><a href="{href}">Alle</a></td></tr>',
    '<tr aria-label="ungelesen"><td><a href="{href}">Alle</a></td></tr>',
    '<tr class="nicht-gelesen"><td><a href="{href}">Alle</a></td></tr>',
    '<tr><td><ul><li><article><a href="{href}">Alle</a></article></li></ul></td></tr>',
)


def test_the_report_never_opens_a_parent_letter():
    index = SCHOOL_ONE_URL + modules.PROBES[modules.LETTERS][0]
    rows = "".join(variant.format(href=LETTER_SHOW % (number, number)) for number, variant in enumerate(LETTER_VARIANTS, 1))
    page = '<html><body><table id="crud-table"><tbody>%s</tbody></table></body></html>' % rows
    for html in (page, LETTERS_PAGE):
        client, adapter = recording_client({index: (200, {"Content-Type": "text/html"}, html.encode("utf-8"))})
        lines = diagnostics.page_structure(diagnostics.ReportFetcher(client), LETTER_ROW, datetime(2026, 9, 23).date(), {})
        assert adapter.sent == [index]
        assert not [line for line in lines if line.startswith("##### Page ")]
        assert any(line.startswith("- Crawl: 0 linked pages, skipped ") and "detail page" in line for line in lines)


def test_a_module_crawl_stops_at_the_report_page_limit():
    lines, adapter = loan_structure(reportcrawl.CrawlBudget(pages=1))
    assert "- Crawl stopped: the report page limit is reached" in lines
    crawled = [url for url in adapter.sent if url.startswith(LOAN) and url != LOAN]
    assert len(crawled) == 1


class SlowClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_slow_school_stops_the_crawl_at_the_time_budget_with_short_request_timeouts():
    clock = SlowClock()
    client, adapter = loan_client()
    timeouts = {}
    send = adapter.send

    def slow_send(request, **kwargs):
        timeouts[request.url] = kwargs.get("timeout")
        clock.now += 20
        return send(request, **kwargs)

    adapter.send = slow_send
    budget = reportcrawl.CrawlBudget(seconds=60, clock=clock)
    fetcher = diagnostics.ReportFetcher(client, budget)
    nav_paths = menu_of(fetcher)
    lines = diagnostics.page_structure(fetcher, LOAN_ROW, datetime(2026, 9, 23).date(), {}, nav_paths=nav_paths)
    assert "- Crawl stopped after 1 pages, time budget reached" in lines
    assert "- API reads stopped after 1 pages, time budget reached" in lines
    assert adapter.sent == [SCHOOL_ONE_URL + "/iserv/", LOAN, LOAN + "overview"]
    assert timeouts[LOAN] == reportcrawl.REQUEST_SECONDS
    assert timeouts[LOAN + "overview"] == reportcrawl.REQUEST_SECONDS
    later = diagnostics.ReportFetcher(client, budget)
    assert reportcrawl.menu_lines(reportcrawl.start_page_links(later), []) == ["### Menu", "- Not read: request failed"]
    assert len(adapter.sent) == 3


def test_a_request_near_the_deadline_gets_only_the_remaining_time():
    clock = SlowClock()
    budget = reportcrawl.CrawlBudget(seconds=60, clock=clock)
    clock.now = 58
    assert budget.timeout(5) == 2
    clock.now = 59.9
    assert budget.timeout(5) == reportcrawl.MIN_REQUEST_SECONDS


def test_a_read_only_module_says_so():
    html = '<html><body><a href="/iserv/x/list">L</a><form method="get" action="/iserv/x/search"></form></body></html>'
    assert reportcrawl.write_forms(html, reportcrawl.menu_shape, str) == []
    assert reportcrawl.functions_line([]) == "- Functions: read-only, no form or script writes found"


def test_api_reads_follow_the_same_allowlist():
    assert reportcrawl.api_allowed("/iserv/x/api/items", "/iserv/x/")
    assert not reportcrawl.api_allowed("/iserv/x/api/items/12", "/iserv/x/")
    assert not reportcrawl.api_allowed("/iserv/x/api/markAllRead", "/iserv/x/")
    assert not reportcrawl.api_allowed("/iserv/y/api/items", "/iserv/x/")


def test_the_sign_in_chain_refuses_a_target_inside_the_home_network():
    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/klassengeld/redirect": (302, {"Location": "https://192.168.1.10/admin"}, b""),
    })
    answer = client.fetch_unfollowed("/iserv/klassengeld/redirect", 1024, 5)
    chain = client.continue_chain(answer, 5, 1024, 5)
    assert chain.landing is None
    assert chain.stop == "target refused"
    assert adapter.sent == [SCHOOL_ONE_URL + "/iserv/klassengeld/redirect"]
    for target in (
        "http://pay.other.example/x", "https://localhost/x", "https://nas.local/x", "https://router/x", "https://[::1]/x",
        "https://127.1/x", "https://0x7f.0.0.1/x", "https://10.1/x", "https://nas.10-0-0-5.nip.io/x", "https://mixed.example/x",
        "https://unknown.example/x",
    ):
        assert not diagnostics_client_allows(target), target
    assert diagnostics_client_allows("https://pay.other.example/x")


def test_the_sign_in_chain_refuses_a_name_that_resolves_into_the_home_network():
    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/klassengeld/redirect": (302, {"Location": "https://nas.10-0-0-5.nip.io/admin"}, b""),
    })
    answer = client.fetch_unfollowed("/iserv/klassengeld/redirect", 1024, 5)
    chain = client.continue_chain(answer, 5, 1024, 5)
    assert chain.stop == "target refused"
    assert adapter.sent == [SCHOOL_ONE_URL + "/iserv/klassengeld/redirect"]


def diagnostics_client_allows(url):
    return chain_target_allowed(url, fake_resolver)


def test_the_sign_in_chain_stops_after_five_redirects():
    loop = "https://pay.other.example/loop"
    client, adapter = recording_client({
        SCHOOL_ONE_URL + "/iserv/klassengeld/redirect": (302, {"Location": loop}, b""),
        loop: (302, {"Location": loop}, b""),
    })
    answer = client.fetch_unfollowed("/iserv/klassengeld/redirect", 1024, 5)
    chain = client.continue_chain(answer, 5, 1024, 5)
    assert chain.stop == "too many redirects"
    assert adapter.sent.count(loop) == 5


def test_the_structure_of_a_module_missing_from_the_menu_reads_the_guessed_page_without_redirects():
    guessed = SCHOOL_ONE_URL + "/iserv/ausleihe/"
    client, adapter = recording_client({guessed: (302, {"Location": FOREIGN_SSO}, b"")})
    row = {"slug": "ausleihe", "segment": "ausleihe", "name": "<word>", "page": "/iserv/ausleihe/", "json": None, "guessed_page": True}
    lines = diagnostics.page_structure(diagnostics.ReportFetcher(client), row, datetime(2026, 9, 23).date(), {}, nav_paths={})
    assert lines[1] == "- Page: /iserv/<seg>/ (guessed, not in the menu) -> 302 - 0B, redirect to other host"
    assert lines[2] == "- Redirect chain: 302 same host -> 404 other host"
    assert adapter.sent == [guessed, FOREIGN_SSO.split("#", 1)[0]]


def test_the_real_client_reports_a_same_host_redirect_without_following_it():
    target = SCHOOL_ONE_URL + "/iserv/ausleihe/"
    client, adapter = recording_client({
        target: (302, {"Location": "/iserv/auth/login?_target_path=/iserv/ausleihe/"}, b""),
    })
    answer = client.fetch_unfollowed("/iserv/ausleihe/", 1024, 5)
    assert (answer.status_code, answer.redirect, answer.text) == (302, "same host", "")
    assert adapter.sent == [target]


class DrippingBody:
    def __init__(self, clock, pieces):
        self.clock = clock
        self.pieces = pieces
        self.reads = 0

    def read(self, amount=None, *args, **kwargs):
        if self.reads >= self.pieces:
            return b""
        self.reads += 1
        self.clock.now += 10
        return b"x" * 10

    def close(self):
        pass


def test_a_dripping_answer_stops_at_the_report_deadline():
    clock = SlowClock()
    body = DrippingBody(clock, 100)
    client, _adapter = recording_client({LOAN: (200, {"Content-Type": "text/html"}, body)})
    budget = reportcrawl.CrawlBudget(seconds=60, clock=clock)
    answer = client.fetch_unfollowed("/iserv/ausleihe/", 1024, 5, expired=budget.expired)
    assert answer.truncated
    assert body.reads == 6
    assert len(answer.text) == 60
    capped = IServClient.fetch_capped(client, "/iserv/ausleihe/", 1024, 5, expired=budget.expired)
    assert capped.truncated
    assert body.reads == 7


def test_the_real_client_caps_an_unfollowed_body():
    target = SCHOOL_ONE_URL + "/iserv/ausleihe/"
    client, _adapter = recording_client({target: (200, {"Content-Type": "text/html"}, b"x" * 5000)})
    answer = client.fetch_unfollowed("/iserv/ausleihe/", 1000, 5)
    assert (answer.status_code, answer.redirect, len(answer.text), answer.truncated) == (200, "none", 1000, True)


def test_the_request_log_masks_a_location_on_another_host(caplog):
    response = requests.Response()
    response.status_code = 302
    response.url = "https://school.example/iserv/klassengeld/redirect"
    response.headers["Location"] = FOREIGN_SSO
    response._content = b""
    response.request = requests.Request("GET", response.url).prepare()
    response.elapsed = timedelta(milliseconds=5)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(response)
    line = caplog.records[0].getMessage()
    assert line == "klassengeld GET /iserv/klassengeld/redirect 302 - 0B 5ms -> <other host>"


def test_the_host_bound_request_log_masks_an_answer_from_another_host(caplog):
    response = requests.Response()
    response.status_code = 200
    response.url = FOREIGN_SSO
    response._content = b"<html></html>"
    response.request = requests.Request("GET", response.url).prepare()
    response.elapsed = timedelta(milliseconds=5)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.HostLog("school.example")(response)
    line = caplog.records[0].getMessage()
    assert line.startswith("other GET <other host> 200")
    for word in FOREIGN_WORDS:
        assert word not in line.lower(), word


def test_the_host_bound_request_log_replaces_the_plain_hook_once():
    session = requests.Session()
    requestlog.install(session)
    requestlog.install(session, "school.example")
    requestlog.install(session, "school.example")
    requestlog.install(session)
    hooks = session.hooks["response"]
    assert hooks == [requestlog.HostLog("school.example")]


def test_the_request_log_does_not_read_a_streamed_body():
    response = requests.Response()
    response.status_code = 200
    response.url = "https://school.example/iserv/js/a.js"
    response.raw = io.BytesIO(b"x" * 1000)
    assert requestlog.body_length(response) == 0
    assert response.raw.tell() == 0


def test_unsupported_module_lines_report_a_module_not_found_in_the_menu():
    pages = {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL, "<html><body></body></html>")}
    client = Client(SCHOOL_ONE_URL, pages)
    rows = [{"slug": "ausleihe", "segment": "ausleihe", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED}]
    lines = reportcrawl.unsupported_module_lines(client, rows, menu_of(client))
    assert "| ausleihe | not in menu | - | - |" in lines


def test_unsupported_module_lines_without_a_session_says_so():
    rows = [{"slug": "ausleihe", "segment": "ausleihe", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED}]
    assert reportcrawl.unsupported_module_lines(None, rows, {}) == [
        "### Unsupported or unknown modules", reportcrawl.UNSUPPORTED_TABLE_HEAD, reportcrawl.UNSUPPORTED_TABLE_RULE,
        "| ausleihe | not read | - | - |",
    ]


def test_unsupported_module_lines_flag_an_internal_link_as_not_external():
    menu_html = '<html><body><nav><a href="/iserv/ausleihe/">Ausleihe</a></nav></body></html>'
    pages = {
        "/iserv/ausleihe/": Response(200, SCHOOL_ONE_URL + "/iserv/ausleihe/", "<html></html>"),
        reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL, menu_html),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    rows = [{"slug": "ausleihe", "segment": "ausleihe", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED}]
    lines = reportcrawl.unsupported_module_lines(client, rows, menu_of(client))
    assert "| ausleihe | /iserv/<seg>/ | 200 | none |" in lines


def test_the_row_lines_of_a_page_are_limited():
    html = "".join("<table><tr><td>x</td></tr></table>" for _ in range(pageshape.MAX_TABLE_ROWS_LINES + 5))
    lines = pageshape.html_skeleton(html)
    assert len([line for line in lines if line.startswith("- Table rows (no id)")]) == pageshape.MAX_TABLE_ROWS_LINES
    assert "- Table rows skipped: 5 beyond the limit of %d" % pageshape.MAX_TABLE_ROWS_LINES in lines


def test_iserv_version_lines_report_every_source_tried():
    pages = {
        modules.ISERV_ROOT + "/app/legal": Response(200, SCHOOL_ONE_URL, "<footer>IServ 3.9.1</footer>"),
        reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL, "<html><body>no version here</body></html>"),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    lines = reportfacts.iserv_version_lines(client)
    assert lines[0] == "### IServ version"
    assert "- start page (/iserv/): not found" in lines
    assert "- legal page (/iserv/app/legal): 3.9.1" in lines
    assert "- Chosen: 3.9.1" in lines


def test_iserv_version_lines_say_unknown_when_no_source_found_it():
    pages = {
        reportcrawl.MENU_LINK_PREFIX: Response(404, SCHOOL_ONE_URL, ""),
        modules.ISERV_ROOT + "/app/legal": Response(404, SCHOOL_ONE_URL, ""),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    lines = reportfacts.iserv_version_lines(client)
    assert "- start page (/iserv/): status 404" in lines
    assert "- legal page (/iserv/app/legal): status 404" in lines
    assert "- Chosen: unknown" in lines


def test_iserv_version_lines_without_a_session_says_so():
    assert reportfacts.iserv_version_lines(None) == ["### IServ version", "- Not read: no session"]


def test_menu_lines_flag_a_mismatch_between_the_link_and_the_probed_path():
    menu_html = """
    <html><body><nav>
    <a href="/iserv/dsa-timetable/timetable">Stundenplan</a>
    <a href="/iserv/klassengeld/redirect">Klassengeld</a>
    <a href="/iserv/parentletter/parent/index">Elternbriefe</a>
    </nav></body></html>
    """
    pages = {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL, menu_html)}
    client = Client(SCHOOL_ONE_URL, pages)
    rows = [
        {"page": "/iserv/dsa-timetable/"},
        {"page": "/iserv/klassengeld/"},
        {"page": modules.PROBES[modules.LETTERS][0]},
    ]
    lines = reportcrawl.menu_lines(reportcrawl.start_page_links(client), rows)
    assert lines[0] == "### Menu"
    assert "- Source: navigation" in lines
    assert "| /iserv/dsa-timetable/timetable | mismatch (probed /iserv/dsa-timetable/) |" in lines
    assert "| /iserv/klassengeld/redirect | mismatch (probed /iserv/klassengeld/) |" in lines
    assert "| /iserv/parentletter/parent/index | match |" in lines


def test_menu_lines_without_a_session_says_so():
    assert reportcrawl.menu_lines(None, []) == ["### Menu", "- Not read: no session"]


PLANTED_LINKS = (
    "/iserv/file/-/Groups/Klasse%205b%20Mueller/Elternabend",
    "/iserv/addressbook/public/show/erika.musterfrau",
    "/iserv/addressbook/public/show/erika",
    "/iserv/ausleihe/show/Laptop-Max-Mustermann",
    "/iserv/klassengeld/sso/eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl",
    "/iserv/klassengeld/sso/k3jf8Hs9dK2lLmQ0pZx7",
    "/iserv/q7Zp2Lx9Wv4Rt8Ks/start",
    "https://pay.other.example/iserv/remote/entry",
)
PLANTED_LINK_WORDS = (
    "mueller", "elternabend", "erika", "musterfrau", "laptop", "mustermann",
    "eyj", "c2lnbmF0dXJl", "k3jf8", "q7zp2", "pay.other", "remote",
)


def planted_start_page(inside_nav):
    anchors = "".join('<a href="%s">x</a>' % link for link in PLANTED_LINKS)
    nav = '<nav><a href="/iserv/klassengeld/redirect">Klassengeld</a>%s</nav>' % (anchors if inside_nav else "")
    return "<html><body>%s<main>%s</main></body></html>" % (nav, "" if inside_nav else anchors)


def assert_no_planted_link_word(lines):
    joined = "\n".join(lines).lower()
    for word in PLANTED_LINK_WORDS:
        assert word.lower() not in joined, word


def test_menu_lines_read_only_the_navigation_and_never_print_names_or_tokens():
    client = Client(SCHOOL_ONE_URL, {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL + "/iserv/", planted_start_page(False))})
    lines = reportcrawl.menu_lines(reportcrawl.start_page_links(client), [])
    assert "- Source: navigation" in lines
    assert "| /iserv/klassengeld/redirect | not probed |" in lines
    assert len([line for line in lines if line.startswith("| /iserv/")]) == 1
    assert_no_planted_link_word(lines)


def test_menu_lines_shape_every_planted_link_inside_the_navigation():
    client = Client(SCHOOL_ONE_URL, {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL + "/iserv/", planted_start_page(True))})
    lines = reportcrawl.menu_lines(reportcrawl.start_page_links(client), [])
    assert "| /iserv/file/-/Groups/<seg>/<more> | not probed |" in lines
    assert "| /iserv/addressbook/public/show/<seg> | not probed |" in lines
    assert "| /iserv/<seg>/show/<seg> | not probed |" in lines
    assert "| /iserv/klassengeld/<seg>/<seg> | not probed |" in lines
    assert "| /iserv/<seg>/<seg> | not probed |" in lines
    assert_no_planted_link_word(lines)


def test_menu_lines_fall_back_to_the_whole_start_page_and_still_shape_it():
    html = "<html><body><div>%s</div></body></html>" % "".join('<a href="%s">x</a>' % link for link in PLANTED_LINKS)
    client = Client(SCHOOL_ONE_URL, {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL + "/iserv/", html)})
    lines = reportcrawl.menu_lines(reportcrawl.start_page_links(client), [])
    assert "- Source: whole start page, no navigation found" in lines
    assert "| /iserv/addressbook/public/show/<seg> | not probed |" in lines
    assert_no_planted_link_word(lines)


def test_unsupported_module_lines_shape_the_link_column():
    nav = '<nav><a href="/iserv/ausleihe/show/Laptop-Max-Mustermann">x</a><a href="/iserv/klassengeld/sso/k3jf8Hs9dK2lLmQ0pZx7">y</a></nav>'
    pages = {reportcrawl.MENU_LINK_PREFIX: Response(200, SCHOOL_ONE_URL + "/iserv/", "<html><body>%s</body></html>" % nav)}
    client = Client(SCHOOL_ONE_URL, pages)
    rows = [
        {"slug": "ausleihe", "segment": "ausleihe", "guessed_page": True, "status": diagnostics.STATUS_UNKNOWN},
        {"slug": "klassengeld", "segment": "klassengeld", "guessed_page": True, "status": diagnostics.STATUS_UNSUPPORTED},
    ]
    lines = reportcrawl.unsupported_module_lines(client, rows, menu_of(client))
    assert any(line.startswith("| ausleihe | /iserv/<seg>/show/<seg> |") for line in lines)
    assert any(line.startswith("| klassengeld | /iserv/klassengeld/<seg>/<seg> |") for line in lines)
    assert_no_planted_link_word(lines)


def test_letters_summary_lines_count_rows_and_unread():
    pages = {modules.PROBES[modules.LETTERS][0]: Response(200, SCHOOL_ONE_URL, LETTERS_PAGE)}
    client = Client(SCHOOL_ONE_URL, pages)
    lines = reportfacts.letters_summary_lines(client)
    assert lines == [
        "### Letters", "- Rows: 3, unread: 1", "- Forms: 2, actions: parent-archive-letter", reportfacts.CONFIRMATION_NOT_COUNTED,
    ]


def test_letter_actions_name_buttons_only_and_hide_their_texts():
    html = """
    <form method="post"><button type="submit" name="iserv_crud_multi_select[actions][parent-confirm-letter]">Mia Musterkind bestaetigen</button>
    <button name="iserv_crud_multi_select[actions][Max-Mustermann]">x</button>
    <input type="hidden" name="secret_field" value="synthetic-token-0001">
    <input type="text" name="comment" value="Alex Example"></form>
    """
    forms, actions = reportfacts.letter_actions(html)
    assert forms == 1
    assert actions == ["parent-confirm-letter", "<word>-<word>"]
    joined = " ".join(actions)
    for word in ("Musterkind", "Max", "Mustermann", "secret_field", "synthetic", "comment", "Alex"):
        assert word not in joined


def test_letters_summary_lines_without_a_session_says_so():
    assert reportfacts.letters_summary_lines(None) == ["### Letters", "- Not read: no session"]


def school_app_client(settings_payload, timetable_payload):
    slots_payload = [{"number": 1}, {"number": 2}]
    pages = {
        reportfacts.SCHOOL_SETTINGS_PATH: Response(200, SCHOOL_ONE_URL, "[]", "application/json", json_data=settings_payload),
        reportfacts.TIMETABLE_SLOTS_PATH: Response(200, SCHOOL_ONE_URL, "[]", "application/json", json_data=slots_payload),
        reportfacts.CURRENT_TIMETABLE_QUERY_PATH: Response(200, SCHOOL_ONE_URL, "{}", "application/json", json_data=timetable_payload),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    queries = []
    original = client.fetch

    def recording(path, params=None):
        if path == reportfacts.CURRENT_TIMETABLE_QUERY_PATH:
            queries.append(dict(params or {}))
        return original(path, params)

    client.fetch = recording
    return client, queries


QUERY_CHILDREN = {"children": [
    {"child_id": "4711", "name": CHILD_ONE, "course_ids": [7, 5]},
    {"child_id": "4712", "name": CHILD_TWO, "course_ids": ["9"]},
    {"child_id": "4713", "name": "Robin Example"},
]}


def test_school_app_query_lines_mirror_the_query_of_the_app_per_child():
    settings = [{"id": 1, "timetable_availableForGuardiansAndStudents": True, "substitutions_availableForGuardiansAndStudents": True}]
    client, queries = school_app_client(settings, {"students": [{"entries": [{}, {}]}]})
    lines = reportfacts.school_app_query_lines(client, QUERY_CHILDREN, datetime(2026, 9, 23).date())
    assert lines[0] == "### School app"
    assert "- Settings: timetable_availableForGuardiansAndStudents=yes, substitutions_availableForGuardiansAndStudents=yes" in lines
    assert "- Timetable query: week=true, substitutions=true, one query per child" in lines
    assert "- Child 1: courses in filter 2, students 1, entries per student 2" in lines
    assert "- Child 2: courses in filter 1, students 1, entries per student 2" in lines
    assert "- Child 3: no course ids stored, the app reads the time-table module instead" in lines
    assert "- Timetable slots: 2" in lines
    assert any(line.startswith("- Week: ") for line in lines)
    assert [query.get("filterBy") for query in queries] == ["courseSubject.course:in(5|7)", "courseSubject.course:in(9)"]
    assert {query["substitutions"] for query in queries} == {"true"}
    assert {query["week"] for query in queries} == {"true"}
    joined = "\n".join(lines)
    for word in ("Robin", "Musterkind", "Beispielsohn", "4711", "4712", "4713"):
        assert word not in joined


def test_school_app_query_lines_accept_only_real_booleans():
    settings = {"timetable_availableForGuardiansAndStudents": "false", "substitutions_availableForGuardiansAndStudents": "true"}
    client, queries = school_app_client(settings, {"students": []})
    lines = reportfacts.school_app_query_lines(client, QUERY_CHILDREN, datetime(2026, 9, 23).date())
    assert "- Settings: timetable_availableForGuardiansAndStudents=not a boolean, substitutions_availableForGuardiansAndStudents=not a boolean" in lines
    assert "- Timetable query: week=true, substitutions=false, one query per child" in lines
    assert {query["substitutions"] for query in queries} == {"false"}
    assert "- Child 1: courses in filter 2, students 0, entries per student -" in lines


def test_school_app_query_lines_without_a_session_says_so():
    lines = reportfacts.school_app_query_lines(None, {}, datetime(2026, 9, 23).date())
    assert "- Settings: timetable_availableForGuardiansAndStudents=not read, substitutions_availableForGuardiansAndStudents=not read" in lines
    assert "- Timetable query: not read, no session" in lines


def test_children_lines_reconciles_every_source_without_a_client():
    config = {"children": [{"child_id": "4711", "name": CHILD_ONE}]}
    lines = reportfacts.children_lines(None, config)
    assert lines[0] == "### Children"
    assert "| Stored | 1 | 0 | 0 |" in lines
    for label in ("School account", "Timetable page", "School app", "Letters"):
        assert reportfacts.CHILDREN_NOT_READ % label in lines


def test_children_lines_flags_a_child_stored_twice_under_two_ids():
    config = {"children": [
        {"child_id": "4711", "name": CHILD_ONE},
        {"child_id": "4713", "name": CHILD_ONE},
    ]}
    lines = reportfacts.children_lines(None, config)
    assert "| Stored | 2 | 0 | 1 |" in lines
    assert CHILD_ONE not in "\n".join(lines)


def test_children_lines_flag_a_duplicate_id_in_the_school_app():
    payload = [{"id": 2, "displayname": "Robin Example"}, {"id": 2, "displayname": "Robin Beispiel"}]
    pages = {reportfacts.SICK_NOTE_SELECTION_PATH: Response(200, SCHOOL_ONE_URL, "[]", "application/json", json_data=payload)}
    lines = reportfacts.children_lines(Client(SCHOOL_ONE_URL, pages), {"children": []})
    assert "| School app | 2 | 1 | 0 |" in lines


def test_children_lines_reads_each_live_source_and_counts_only():
    me_payload = {"children": [{"id": 1, "forename": "Robin", "surname": "Example", "courses": []}]}
    school_app_payload = [{"id": 2, "displayname": "Robin Example"}]
    letters_html = LETTERS_PAGE
    pages = {
        reportfacts.SCHOOL_ACCOUNT_ME_PATH: Response(200, SCHOOL_ONE_URL, "{}", "application/json", json_data=me_payload),
        reportfacts.SICK_NOTE_SELECTION_PATH: Response(200, SCHOOL_ONE_URL, "[]", "application/json", json_data=school_app_payload),
        reportfacts.TIME_TABLE_PAGE_PATH: Response(200, SCHOOL_ONE_URL + reportfacts.TIME_TABLE_PAGE_PATH,
                                                    "<select id='timetable-filter-child-select'><option value='9'>Robin Example</option></select>"),
        modules.PROBES[modules.LETTERS][0]: Response(200, SCHOOL_ONE_URL, letters_html),
    }
    client = Client(SCHOOL_ONE_URL, pages)
    lines = reportfacts.children_lines(client, {"children": []})
    assert "| School account | 1 | 0 | 0 |" in lines
    assert "| School app | 1 | 0 | 0 |" in lines
    assert "| Timetable page | 1 | 0 | 0 |" in lines
    letters_line = next(line for line in lines if line.startswith("| Letters |"))
    assert letters_line.split("|")[2].strip().isdigit()
    assert "Robin" not in "\n".join(lines)
    assert "Example" not in "\n".join(lines)


class PlainAnswer:
    def __init__(self, text):
        self.status_code = 200
        self.url = SCHOOL_ONE_URL + "/iserv/x"
        self.text = text
        self.headers = {"Content-Type": "application/json"}


class PlainPages:
    def __init__(self, text):
        self.text = text

    def fetch(self, path, params=None):
        return PlainAnswer(self.text)


def test_answers_without_a_json_method_are_parsed_from_their_text():
    assert reportfacts.fetch_json(PlainPages('{"a": 1}'), "/iserv/x") == {"a": 1}
    assert reportfacts.fetch_json(PlainPages("<html></html>"), "/iserv/x") is None
    assert pageshape.response_skeleton(PlainAnswer('{"a": 1}'))[0] == "- JSON value shapes:"
    assert pageshape.response_skeleton(PlainAnswer("{broken")) == ["- JSON: unreadable"]


def test_a_capped_script_read_never_follows_a_redirect():
    script = SCHOOL_ONE_URL + "/iserv/js/app.js"
    client, adapter = recording_client({script: (302, {"Location": FOREIGN_SSO}, b"")})
    body = client.fetch_capped("/iserv/js/app.js", 1024, 5)
    assert body.status_code == 302
    assert adapter.sent == [script]


def test_a_crawled_page_scans_its_scripts_only_once(monkeypatch):
    page = SCHOOL_ONE_URL + "/iserv/ausleihe/overview"
    client = Client(
        SCHOOL_ONE_URL,
        {"/iserv/ausleihe/overview": Response(200, page, '<html><body><script src="/iserv/ausleihe/app.js"></script></body></html>')},
        scripts={"/iserv/ausleihe/app.js": 'fetch("/iserv/ausleihe/api/items")'},
    )
    scanned = []
    scan = reportcrawl.script_endpoints
    monkeypatch.setattr(reportcrawl, "script_endpoints", lambda text, label: scanned.append(label) or scan(text, label))
    landing = Response(200, SCHOOL_ONE_URL + "/iserv/ausleihe/", '<html><body><a href="/iserv/ausleihe/overview">overview</a></body></html>')
    lines = reportcrawl.module_crawl(client, landing, "/iserv/ausleihe/", reportcrawl.menu_shape, {}, "/iserv/")
    assert "- Crawl: 1 linked pages, skipped none" in lines
    assert len(scanned) == 1
