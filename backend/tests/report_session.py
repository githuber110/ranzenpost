from app import modules, reportfacts
from app.iserv.client import REDIRECT_NONE, CappedBody, UnfollowedAnswer, redirect_kind
from tests.support import Response

PLANTED_CHILD = "Jonas Pflanzkind"
PLANTED_ADULT = "Erika Saatmuster"
PLANTED_TEACHER = "Herr Keimling"
PLANTED_TOKEN = "planted-token-7f3a9c"
PLANTED_SSO = "https://pay.planted.example/sso/eyJwbGFudGVkIjoxfQ.c2VlZHNpZ24?code=planted-code-0001#seedfrag"
LOWER_TOKEN = "qwertzuiopasdfghjklyxcvb"
MIXED_TOKEN = "k3jf8hs9dk2llmq0pzx7"
LOG_TOKEN = "mnbvcxylkjhgfdsapoiuztre"
PLANTED_WORDS = (
    "mustermann", "lisa", "anna", "schmidt", "mueller",
    LOWER_TOKEN, MIXED_TOKEN, LOG_TOKEN, "jonas", "erika",
    "Jonas", "Pflanzkind", "Erika", "Saatmuster", "Keimling", "planted-token", "planted-code",
    "pay.planted", "eyJwbGFudGVk", "c2VlZHNpZ24", "seedfrag", "Pflanzklasse", "Geheimbrief", "Saatbrief",
)
COURSE_IDS = [5, 7]

START_PAGE = """
<html><head><meta name="generator" content="IServ 3.9.1"></head><body>
<nav id="sidebar">
<a href="/iserv/parentletter/parent/index">Elternbriefe</a>
<a href="/iserv/mail/">E-Mail</a>
<a href="/iserv/videoconference/room/Jonas-Pflanzkind">Videokonferenzen</a>
<a href="/iserv/klassengeld/redirect">Klassengeld</a>
<a href="/iserv/addressbook/public/show/erika.saatmuster">Erika Saatmuster</a>
<a href="https://pay.planted.example/iserv/remote/Jonas">extern</a>
<a href="/iserv/profile/jonas">Profil</a>
<a href="/iserv/mail/folder/qwertzuiopasdfghjklyxcvb">Ordner</a>
<a href="/iserv/mail/k3jf8hs9dk2llmq0pzx7/show">Token</a>
</nav>
<main>
<p>Hallo Erika Saatmuster, Nachricht von Herr Keimling.</p>
<a href="/iserv/file/-/Groups/Pflanzklasse%205b/Elternabend">Pflanzklasse</a>
<a href="/iserv/klassengeld/sso/planted-token-7f3a9c">sso</a>
</main>
</body></html>
"""
LEGAL_PAGE = "<html><body><footer>IServ 3.9.1, Kontakt Erika Saatmuster</footer></body></html>"
TIME_TABLE_PAGE = """
<html><body>
<select id="timetable-filter-child-select"><option value="31">Jonas Pflanzkind</option><option value="32">Jonas Pflanzkind</option></select>
<table id="timetable-content-changes"><tr><th>Datum</th><th>Stunde</th></tr><tr><td>Herr Keimling</td></tr></table>
</body></html>
"""
LETTERS_PAGE = """
<html><body>
<form action="/iserv/parentletter/parent/index" method="post">
<table id="crud-table"><tbody>
<tr class="parent-index-table-unread">
<td><input type="checkbox" name="iserv_crud_multi_select[multi][]" value="10000000-0000-4000-8000-000000000001-20000000-0000-4000-8000-000000000001"></td>
<td><a href="/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000001/20000000-0000-4000-8000-000000000001">Geheimbrief</a></td>
<td>Jonas Pflanzkind</td><td>Herr Keimling</td><td></td><td>Pflanzklasse</td><td>05.03.2026 14:30</td>
</tr>
<tr>
<td><input type="checkbox" name="iserv_crud_multi_select[multi][]" value="10000000-0000-4000-8000-000000000002-20000000-0000-4000-8000-000000000002"></td>
<td><a href="/iserv/parentletter/parent/show/10000000-0000-4000-8000-000000000002/20000000-0000-4000-8000-000000000002">Saatbrief</a></td>
<td>Erika Saatmuster</td><td>Herr Keimling</td><td></td><td>Pflanzklasse</td><td>06.03.2026 14:30</td>
</tr>
</tbody></table>
<button type="submit" name="iserv_crud_multi_select[actions][parent-archive-letter]">Jonas Pflanzkind archivieren</button>
<input type="hidden" name="iserv_crud_multi_select[_token]" value="planted-token-7f3a9c">
</form>
</body></html>
"""
MAIL_PAGE = """
<html><body><nav><a href="/iserv/mail/folder/Erika-Saatmuster">Erika Saatmuster</a>
<a href="/iserv/mail/read/jonas">x</a><a href="/iserv/mail/qwertzuiopasdfghjklyxcvb/list">y</a><a href="/iserv/mail/max.erika">z</a></nav>
<form action="/iserv/mail/send/erika" method="post"><input name="to"></form>
<script>fetch("/iserv/mail/api/k3jf8hs9dk2llmq0pzx7", {method: "PUT"}); const next = "/iserv/mail/show/jonas";</script>
<script src="/iserv/mail/static/erika-app.js"></script>
<section class="box-mustermann"><form id="form-mustermann" action="/iserv/mail/compose" method="post">
<input name="users[max.mustermann]"><input name="child_LISA"><button name="confirm_anna">x</button></form></section>
<table id="tbl-schmidt"><tr><th>x</th></tr></table>
<script type="application/json" id="data-anna">{"max.mustermann.anna": 1, "anna_schmidt": 2, "MUELLER": 3}</script>
<form action="/iserv/mail/compose" method="post"><input name="to" value="erika.saatmuster@planted.example"><textarea name="body">Geheimbrief</textarea></form>
<table><tr><th>Jonas Pflanzkind</th></tr><tr><td>Herr Keimling</td></tr></table>
<script type="application/json" id="mail-data">{"owner": "Erika Saatmuster", "token": "planted-token-7f3a9c", "link": "/iserv/mail/show/jonas/qwertzuiopasdfghjklyxcvb"}</script>
</body></html>
"""
ME = {"children": [{"id": 31, "forename": "Jonas", "surname": "Pflanzkind", "courses": [{"id": 5}, {"id": 7}]}]}
STUDENTS = [{"id": 31, "displayname": PLANTED_CHILD}, {"id": 31, "displayname": PLANTED_CHILD}]
SETTINGS = [{"timetable_availableForGuardiansAndStudents": True, "substitutions_availableForGuardiansAndStudents": True}]
TIMETABLE = {"students": [{"name": PLANTED_CHILD, "entries": [{"teacher": PLANTED_TEACHER}, {"teacher": PLANTED_TEACHER}]}]}
SLOTS = [{"number": 1, "label": PLANTED_TEACHER}, {"number": 2}]


class PlantedClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.requested = []
        self.pages = {
            "/iserv/": Response(200, base_url + "/iserv/", START_PAGE),
            "/iserv/app/legal": Response(200, base_url + "/iserv/app/legal", LEGAL_PAGE),
            "/iserv/time-table/": Response(200, base_url + "/iserv/time-table/jonas/k3jf8hs9dk2llmq0pzx7", TIME_TABLE_PAGE),
            modules.PROBES[modules.LETTERS][0]: Response(200, base_url + modules.PROBES[modules.LETTERS][0], LETTERS_PAGE),
            "/iserv/mail/": Response(200, base_url + "/iserv/mail/", MAIL_PAGE),
            "/iserv/klassengeld/redirect": Response(302, base_url + "/iserv/klassengeld/redirect", "", location=PLANTED_SSO),
            "/iserv/videoconference/room/Jonas-Pflanzkind": Response(302, base_url + "/iserv/videoconference/room/Jonas-Pflanzkind", "", location="/iserv/auth/login?user=Jonas-Pflanzkind"),
            reportfacts.SCHOOL_ACCOUNT_ME_PATH: self._json(reportfacts.SCHOOL_ACCOUNT_ME_PATH, ME),
            reportfacts.SICK_NOTE_SELECTION_PATH: self._json(reportfacts.SICK_NOTE_SELECTION_PATH, STUDENTS),
            reportfacts.SCHOOL_SETTINGS_PATH: self._json(reportfacts.SCHOOL_SETTINGS_PATH, SETTINGS),
            reportfacts.CURRENT_TIMETABLE_QUERY_PATH: self._json(reportfacts.CURRENT_TIMETABLE_QUERY_PATH, TIMETABLE),
            reportfacts.TIMETABLE_SLOTS_PATH: self._json(reportfacts.TIMETABLE_SLOTS_PATH, SLOTS),
        }

    def _json(self, path, data):
        return Response(200, self.base_url + path, "{}", "application/json", json_data=data)

    def is_authenticated(self):
        return True

    def fetch(self, path, params=None):
        self.requested.append(path)
        return self.pages.get(path) or Response(404, self.base_url + path, "")

    def fetch_unfollowed(self, path, limit, timeout, expired=None):
        self.requested.append(path)
        answer = self.pages.get(path) or Response(404, self.base_url + path, "")
        redirect = redirect_kind(answer.url, answer.status_code, answer.headers.get("Location"), self.base_url)
        body = "" if redirect != REDIRECT_NONE else answer.text
        return UnfollowedAnswer(answer.status_code, answer.url, answer.headers.get("Content-Type", ""), body[:limit], len(body) > limit, redirect)

    def fetch_capped(self, path, limit, timeout, expired=None):
        if path == "/iserv/mail/static/erika-app.js":
            return CappedBody(200, 'axios.post("/iserv/mail/api/jonas/qwertzuiopasdfghjklyxcvb");fetch("/iserv/mail/api/erika")', False)
        return CappedBody(404, "", False)


def with_course_ids(current):
    current["children"] = [dict(child, course_ids=list(COURSE_IDS)) for child in current.get("children") or []]


def planted_log_line():
    import logging
    from datetime import timedelta
    import requests
    from app import requestlog

    lines = []

    class Collect(logging.Handler):
        def emit(self, record):
            lines.append("2026-09-19 10:00:01,000 INFO iserv: " + record.getMessage())

    handler = Collect()
    logger = logging.getLogger("iserv")
    logger.addHandler(handler)
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        response = requests.Response()
        response.status_code = 302
        response.url = "https://school-one.example/iserv/mail/read/jonas/" + LOG_TOKEN
        response.headers["Location"] = "/iserv/mail/show/erika/" + MIXED_TOKEN
        response._content = b""
        response.request = requests.Request("GET", response.url).prepare()
        response.elapsed = timedelta(milliseconds=3)
        requestlog.log_response(response)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    return lines
