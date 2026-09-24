import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi.testclient import TestClient

from app import diagnostics, logbuffer, modules, pathpattern, requestlog
from app.iserv.client import CappedBody, IServClient
from app.iserv.errors import LoginError
from app.server import create_app
from app.store import Store
from tests.support import add_school
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
    + 'const filler="' + "v" * diagnostics.MAX_SCRIPT_BYTES + '";'
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


class Response:
    def __init__(self, status_code, url, text="", content_type="text/html; charset=utf-8", json_data=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.json_data = json_data

    def json(self):
        if self.json_data is None:
            raise ValueError("no json")
        return self.json_data


class Client:
    def __init__(self, base_url, pages, scripts=None):
        self.base_url = base_url
        self.pages = pages
        self.scripts = scripts or {}
        self.capped_calls = []

    def is_authenticated(self):
        return True

    def fetch(self, path, params=None):
        for prefix, response in self.pages.items():
            if path.startswith(prefix):
                return response
        return Response(404, self.base_url + path, "")

    def fetch_capped(self, path, limit, timeout):
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
    assert "- Form: /iserv/mystery/save/<n> (post) #mystery-form" in report
    assert "  - title (text, required)" in report
    assert "  - body (textarea)" in report
    assert "- Endpoints: /iserv/mystery/api/items/<n> | /iserv/mystery/api/list" in report
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
    assert line == "letters GET /iserv/parentletter/parent/show/<uuid>/2 302 text/html 13B 42ms -> /iserv/auth/login"
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
        len(CHAT_SCRIPT_TEXT.encode("utf-8")), diagnostics.MAX_SCRIPT_BYTES) in section
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
        (CHAT_SCRIPT, diagnostics.MAX_SCRIPT_BYTES, diagnostics.SCRIPT_TIMEOUT),
        (VENDOR_SCRIPT, diagnostics.MAX_SCRIPT_BYTES, diagnostics.SCRIPT_TIMEOUT),
    ]
    assert not any("tracker" in path for path, _limit, _timeout in first.client.capped_calls)
    assert diagnostics.MAX_SCRIPT_BYTES == 2 * 1024 * 1024
    assert diagnostics.SCRIPT_TIMEOUT == 10
    assert diagnostics.MAX_SCRIPTS_PER_MODULE == 8


def test_at_most_eight_scripts_per_module_are_read_and_each_only_once(tmp_path):
    tags = "".join('<script src="/iserv/many/static/bundle-%02d0000.js"></script>' % index for index in range(10))
    page = "<html><body>%s<script src=\"/iserv/many/static/bundle-000000.js\"></script></body></html>" % tags
    scripts = {"/iserv/many/static/bundle-%02d0000.js" % index: 'fetch("/iserv/many/api/%02d")' % index for index in range(10)}
    client = Client(SCHOOL_ONE_URL, {"/iserv/many/": Response(200, SCHOOL_ONE_URL + "/iserv/many/", page)}, scripts)
    row = {"slug": "many", "name": "Many", "page": "/iserv/many/", "json": None}
    lines = diagnostics.page_structure(client, row, datetime(2026, 9, 19).date(), {})
    assert len(client.capped_calls) == 8
    assert len({path for path, _limit, _timeout in client.capped_calls}) == 8
    text = "\n".join(lines)
    assert "- Scripts skipped: 2 beyond the limit of 8" in text
    assert "| GET | /iserv/many/api/07 | bundle-<hash>.js | - |" in text
    assert "/iserv/many/api/08" not in text
    assert "/iserv/many/api/09" not in text


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
    found = diagnostics.script_endpoints(text, "one.js")
    assert found == {
        ("DELETE", "<expr>/iserv/x/<expr>/y", "one.js"): set(),
        ("PATCH", "/api/plain", "one.js"): set(),
        ("PUT", "/_matrix/media/v3/upload", "one.js"): set(),
        ("GET", "/iserv/z/<uuid>/file/<n>", "one.js"): {"matrix_access_token", "accessToken", "refresh_token"},
        ("-", "/rooms/$roomId/send/$eventType", "one.js"): set(),
    }


def test_script_labels_hide_hashes_but_keep_plain_names():
    assert diagnostics.script_label("/iserv/messenger/static/assets/chat-standalone-a1b2c3d4.js?v=3") == "chat-standalone-<hash>.js"
    assert diagnostics.script_label("/iserv/js/main.7f3a9c2b1d.chunk.js") == "main.<hash>.chunk.js"
    assert diagnostics.script_label("/iserv/js/index-BqK3x9Zp.min.js") == "index-<hash>.min.js"
    assert diagnostics.script_label("/iserv/js/parentletter.js") == "parentletter.js"
    assert diagnostics.script_label("/iserv/js/vendor~chunk.abc123def456789012345678.js") == "vendor~chunk.<hash>.js"


def test_the_endpoint_limits_the_structure_to_one_module(tmp_path):
    service, _first, _second = two_school_service(tmp_path)
    client = TestClient(create_app(service))
    report = client.get("/api/diagnostics?module=messenger").json()["report"]
    assert "- Structure module: messenger" in report
    assert "#### messenger (" in report
    assert "#### parentletter (" not in report
    assert "#### mystery (" not in report
    assert "| parentletter |" in report
    assert "##### Script endpoints" in report
    missing = client.get("/api/diagnostics?module=nothing-here").json()["report"]
    assert "- Not read: no module named nothing-here" in missing
    assert "####" not in missing
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
    whole = IServClient("https://school.example", session=StreamingSession(StreamedAnswer([b"ab", b"cd"]))).fetch_capped("/iserv/js/b.js", 7, 10)
    assert whole == CappedBody(200, "abcd", False)
