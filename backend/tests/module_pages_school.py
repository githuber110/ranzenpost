import json

from tests.account_fakes import Answer, page

SCHOOL = "https://school-one.example"
PRINT_PAGE = page("Drucken", """
<table><thead><tr><th>Name</th><th>Seiten</th><th>Status</th><th></th></tr></thead><tbody>
<tr><td>Elternbrief.pdf</td><td>2</td><td>Gedruckt</td><td><a class="btn" href="/iserv/print/job/7/cancel">Abbrechen</a></td></tr>
<tr><td>Liste.pdf</td><td>1</td><td>Wartet</td><td><a href="/iserv/print/job/8/download">Herunterladen</a></td></tr>
</tbody></table>
<form method="post" action="/iserv/print/upload" name="job_upload"><input type="file" name="job_upload[file]">
<input type="hidden" name="job_upload[_token]" value="token"><button type="submit">Hochladen</button></form>
""")
COURSE_LIST_PAGE = page("Kurswahlen", """
<table><thead><tr><th>Titel</th><th>Zeitraum</th></tr></thead><tbody>
<tr><td><a href="/iserv/courseselection/7">Wahlpflicht 2027</a></td><td>01.11.2026 bis 30.11.2026</td></tr>
</tbody></table>
""")
COURSE_PAGE = page("Wahlpflicht 2027", """
<p>Bitte bis 30.11.2026 wählen.</p>
<form method="post" action="/iserv/courseselection/7/choose"><select name="choice[course]"><option value="1">Spanisch</option></select>
<button type="submit">Speichern</button></form>
""")
ROOMS_PAGE = page("Videokonferenzen", """
<table><thead><tr><th>Raum</th><th>Teilnehmer</th><th></th></tr></thead><tbody>
<tr><td>Klassenraum 4a</td><td>3</td><td><a class="btn" href="/iserv/videoconference/room/5/join">Beitreten</a></td></tr>
</tbody></table>
<a href="/iserv/videoconference/room/create">Neuer Raum</a>
""")
POLLS_PAGE = page("Umfragen", "<p>Keine Umfragen</p>")
TODO_ANSWER = {
    "tasks": [
        {"uid": "t1", "summary": "Sportzeug mitbringen", "description": "Für Freitag", "due": "2026-11-20T11:00:00+00:00", "completed": None},
        {"uid": "t2", "summary": "Buch abgeben", "description": None, "due": None, "completed": "2026-11-02T09:00:00+00:00"},
    ],
    "revision": "0" * 32,
}
PAGES = {
    "/iserv/print": PRINT_PAGE,
    "/iserv/courseselection": COURSE_LIST_PAGE,
    "/iserv/courseselection/7": COURSE_PAGE,
    "/iserv/videoconference/": ROOMS_PAGE,
    "/iserv/poll": POLLS_PAGE,
    "/iserv/todo/api/frontend/tasks": json.dumps(TODO_ANSWER),
}


class ModuleSchool:
    def __init__(self, pages=None, status=200, redirects=None, kinds=None):
        self.pages = dict(PAGES if pages is None else pages)
        self.status = status
        self.redirects = dict(redirects or {})
        self.kinds = dict(kinds or {})
        self.fetched = []

    def is_authenticated(self):
        return True

    def login(self, username, password, code_provider):
        return None

    def fetch_unfollowed(self, path, limit, timeout, expired=None, headers=None):
        self.fetched.append(path)
        if path in self.redirects:
            answer = Answer(302, SCHOOL + path)
            answer.next_url = self.redirects[path]
            return answer
        text = self.pages.get(path)
        if text is None:
            return Answer(404, SCHOOL + path)
        kind = self.kinds.get(path) or ("application/json" if "/api/" in path else "text/html; charset=utf-8")
        return Answer(self.status, SCHOOL + path, text, content_type=kind)


class ModuleConnection:
    id = "a1b2c3d4"

    def __init__(self, school=None):
        self.school = school or ModuleSchool()
        self.forgotten = 0

    def _session(self):
        return self.school

    def _forget_session(self, client):
        self.forgotten += 1
        self.school.redirects = {}
