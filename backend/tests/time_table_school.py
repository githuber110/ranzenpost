import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from requests.structures import CaseInsensitiveDict

from app.iserv.client import IServClient

DSA_ROOT = "/iserv/dieschulapp/api/1.0/"
PAGE = "/iserv/time-table/"
DATA = "/iserv/time-table/data"
DATE_FORMAT = "%d.%m.%Y"
LESSONS = "lessons"
EMPTY = "empty"
FORBIDDEN = "forbidden"
ODD = "odd"
ABSENT = "absent"
BROKEN = "broken"
PAGE_SHOWN = "shown"
PAGE_FORBIDDEN = "forbidden"
PAGE_LOGIN = "login"
PAGE_ROOT = "root"
PAGE_FOREIGN = "foreign"
SCHOOL_APP_ANSWERS = "answers"
SCHOOL_APP_REFUSES = "refuses"
REFUSAL_TEXT = "<html><body><h1>403 Forbidden</h1><p>Access denied.</p></body></html>"
LOGIN_PAGE = (
    "<html><body><form method=\"post\" action=\"/iserv/auth/login\">"
    "<input name=\"_username\"><input type=\"password\" name=\"_password\"></form></body></html>"
)
VACATIONS = [{"name": "Herbstferien", "startDate": "2026-10-17", "endDate": "2026-10-31"}]
OTHER_CHILD = ("33333333-3333-4333-8333-333333333333", "Robin Anders")
WEEK_PLAN = (
    (1, 1, "D", "KLE", "R101"),
    (1, 2, "MA", "BRA", "R101"),
    (2, 1, "EN", "WOL", "R204"),
    (3, 3, "SP", "FUC", "GYM"),
    (4, 2, "MA", "BRA", "R101"),
    (5, 1, "KU", "HAS", "R12"),
)


class Cookie:
    def __init__(self, name):
        self.name = name


class Answer:
    def __init__(self, url, status_code=200, text="", payload=None, content_type="text/html"):
        self.url = url
        self.status_code = status_code
        self.headers = CaseInsensitiveDict({"Content-Type": content_type})
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else text
        self.content = self.text.encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def child_page(options):
    if options is None:
        return "<html><body><table id=\"timetable-content-combined\"></table></body></html>"
    rows = "".join('<option value="%s">%s</option>' % option for option in options)
    return (
        "<html><body><select id=\"timetable-filter-child-select\">"
        '<option value=""></option>%s</select>'
        "<table id=\"timetable-content-combined\"></table></body></html>" % rows
    )


def time_table_entry(monday, day, period, subject, teacher, room, index):
    return {
        "id": 4000 + index,
        "class": "5A",
        "teacher": teacher,
        "subject": subject,
        "room": room,
        "dow": day,
        "period": period,
        "internal_id": str(100 + index),
        "date": (monday + timedelta(days=day - 1)).strftime(DATE_FORMAT),
        "period_reference": None,
    }


def time_table_week(start, end, filled=True, plan=WEEK_PLAN):
    monday = datetime.strptime(start, DATE_FORMAT).date()
    entries = [time_table_entry(monday, *row, index) for index, row in enumerate(plan)] if filled else []
    return {
        "meta": {"filter": {"startDate": start, "endDate": end}, "last-updated": start + " 07:00"},
        "data": {"timetable": entries, "orphan-changes": []},
        "plain-timetable": [dict(entry) for entry in entries],
        "plain-changes": [],
    }


HOME = "R0.04"
MOVED_WEEK_PLAN = (
    (1, 1, "BK", None, "R0.01"), (1, 2, "BK", None, "R0.01"), (1, 3, "Bio", None, "R0.02"), (1, 4, "Mu", None, "R0.03"),
    (1, 5, "D", None, HOME), (1, 6, "G", None, HOME), (1, 6, "GE-BIL", None, "R0.05"),
    (2, 1, "M", None, HOME), (2, 2, "Eth", None, "R0.06"), (2, 2, "REL-A", None, "R0.07"), (2, 2, "REL-B", None, HOME),
    (2, 3, "Ek", None, HOME), (2, 4, "E", None, HOME), (2, 5, "L", None, HOME), (2, 6, "L", None, HOME),
    (2, 7, "GE-BIL", None, "R0.08"),
    (3, 1, "L", None, HOME), (3, 2, "E", None, HOME), (3, 3, "Bio", None, "R0.02"), (3, 4, "M", None, HOME),
    (3, 5, "SP-A", None, "Gym-1"), (3, 5, "SP-B", None, "Gym-3"), (3, 6, "D", None, HOME), (3, 7, "CHOR", None, "R0.10"),
    (4, 1, "Ek", None, HOME), (4, 2, "L", None, HOME), (4, 3, "M", None, HOME), (4, 4, "G", None, HOME),
    (4, 4, "GE-BIL", None, "R0.05"), (4, 5, "E", None, HOME), (4, 6, "Mu", None, "R0.09"),
    (5, 1, "SP-A", None, "Gym-2"), (5, 1, "SP-B", None, "Gym-3"), (5, 2, "SP-A", None, "Gym-2"), (5, 2, "SP-B", None, "Gym-3"),
    (5, 3, "D", None, HOME), (5, 4, "Eth", None, "R0.06"), (5, 4, "REL-A", None, "R0.07"), (5, 4, "REL-B", None, HOME),
    (5, 5, "D", None, HOME), (5, 6, "M", None, HOME),
)
JOINED_CLASSES = ["5B", "5A", "5C"]
MOVED_WEEK_CHANGES = (
    (1, 4, "Mu", "M", "R0.03", HOME, ["3", "5"], "", ["5A"]),
    (2, 2, "Eth", "Eth", "R0.06", "R0.06", ["2", "4"], "", JOINED_CLASSES),
    (2, 6, "L", "", HOME, "", ["1", "5"], "Material mitbringen", ["5A"]),
    (3, 3, "Bio", "Bio", "R0.02", "R0.02", ["2", "4"], "", ["5A"]),
    (4, 5, "E", "L", HOME, HOME, ["3", "5"], "", ["5A"]),
    (5, 4, "Eth", "Eth", "R0.06", "R0.06", ["2", "4"], "", JOINED_CLASSES),
    (5, 6, "M", "", HOME, "", ["1", "5"], "", ["5A"]),
)


def moved_week_change(monday, index, day, period, subject, new_subject, room, new_room, kinds, text, classes):
    return {
        "id": 8100 + index,
        "date": (monday + timedelta(days=day - 1)).strftime(DATE_FORMAT),
        "chgdow": str(day),
        "period": period,
        "origTeacher": None,
        "substitutionTeacher": None,
        "origSubject": subject,
        "substitutionSubject": new_subject,
        "origRoom": room,
        "substitutionRoom": new_room,
        "origClass": ["5A"],
        "substitutionClass": list(classes),
        "text": text,
        "change_types": list(kinds),
        "updated": "20261005%04d" % (700 + index),
        "internal_id": str(9000 + index),
        "periodStart": period,
        "periodEnd": period,
    }


def moved_week_changes(start_text):
    try:
        monday = datetime.strptime(start_text, DATE_FORMAT).date()
    except ValueError:
        return []
    return [moved_week_change(monday, index, *row) for index, row in enumerate(MOVED_WEEK_CHANGES)]


def withheld_school(**overrides):
    fields = dict(
        school_app=SCHOOL_APP_REFUSES,
        released=False,
        slots=True,
        plan=MOVED_WEEK_PLAN,
        changes=moved_week_changes,
    )
    fields.update(overrides)
    return TimeTableSchool(**fields)


def school_app_entry():
    return {
        "id": 91001,
        "weekday": 0,
        "courseSubject": {
            "id": 81001,
            "teachers": [{"id": 3001, "externalId": "KLE", "forename": "Kai", "surname": "Klein"}],
            "subject": {"id": 71001, "acronym": "D", "name": "Deutsch", "hexColor": "#0F3BEB"},
            "course": {"id": 7001, "name": "Klasse 5A"},
        },
        "timeTableSlot": {"id": 1, "number": 1, "startTime": "08:00", "endTime": "08:45"},
        "room": {"id": 5001, "name": "R101"},
    }


class TimeTableSchool:
    def __init__(
        self,
        child_id=500001,
        child_name=("Kim", "Muster"),
        options=(("11111111-1111-4111-8111-111111111111", "Muster, Kim"),),
        school_lessons=False,
        slots=False,
        time_table=LESSONS,
        extra_children=(),
        page=PAGE_SHOWN,
        vacations=(),
        on_data=None,
        changes=(),
        school_app=SCHOOL_APP_ANSWERS,
        released=True,
        plan=WEEK_PLAN,
        sick_notes=False,
        me_courses=True,
    ):
        self.me_courses = me_courses
        self.sick_notes = sick_notes
        self.me_failures = 0
        self.school_app = school_app
        self.released = released
        self.plan = tuple(plan)
        self.child_id = child_id
        self.child_name = child_name
        self.options = options
        self.school_lessons = school_lessons
        self.slots = slots
        self.time_table = time_table
        self.extra_children = list(extra_children)
        self.page = page
        self.vacations = list(vacations)
        self.on_data = on_data
        self.changes = changes if callable(changes) else list(changes)
        self.headers = {}
        self.cookies = [Cookie("IServSession")]
        self.hooks = {"response": []}
        self.calls = []

    def paths(self, wanted):
        return [params for path, params in self.calls if path == wanted]

    def _me(self):
        forename, surname = self.child_name
        children = [
            {
                "id": self.child_id,
                "forename": forename,
                "surname": surname,
                "displayname": "%s %s" % (surname, forename),
                "mainCourse": {"id": 7001, "name": "Klasse 5A", "externalId": "klasse.5a"},
                "courses": [{"id": 7001, "name": "Klasse 5A", "type": "class"}] if self.me_courses else [],
            }
        ]
        children.extend(self.extra_children)
        return {"id": 900, "displayname": "Parent Example", "roles": ["guardian"], "children": children}

    def _school_app(self, url, rest):
        if rest.startswith("users/me"):
            if self.me_failures:
                self.me_failures -= 1
                return Answer(url, 500, "")
            return Answer(url, payload=self._me(), content_type="application/json")
        if rest.startswith("sickNotes/userSelection") and self.sick_notes:
            forename, surname = self.child_name
            student = {"id": self.child_id, "displayname": "%s %s" % (surname, forename), "mainCourse": {"id": 7001, "name": "Klasse 5A", "externalId": "klasse.5a"}}
            return Answer(url, payload=[student], content_type="application/json")
        if rest.startswith("school-settings"):
            settings = [{"timetable_availableForGuardiansAndStudents": self.released, "substitutions_availableForGuardiansAndStudents": False}]
            return Answer(url, payload=settings, content_type="application/json")
        if rest.startswith("timetable-slots"):
            slots = [{"id": 1, "number": 1, "startTime": "08:00", "endTime": "08:45", "type": "lesson"}] if self.slots else []
            return Answer(url, payload=slots, content_type="application/json")
        if rest.startswith("current-timetable"):
            if self.school_app == SCHOOL_APP_REFUSES:
                return Answer(url, 403, REFUSAL_TEXT)
            forename, surname = self.child_name
            student = {"id": self.child_id, "forename": forename, "surname": surname}
            entries = [school_app_entry()] if self.school_lessons else []
            payload = {"students": [{"student": student, "entries": entries}], "vacations": list(self.vacations), "schoolEvents": []}
            return Answer(url, payload=payload, content_type="application/json")
        return Answer(url, 404, "")

    def _page(self, url):
        base = url.split("/iserv/", 1)[0]
        if self.time_table == ABSENT:
            return Answer(url, 404, "")
        if self.page == PAGE_FORBIDDEN:
            return Answer(url, 403, "<html><head><title>Riverside Primary</title></head><body><h1>Riverside Primary</h1></body></html>")
        if self.page == PAGE_LOGIN:
            return Answer(base + "/iserv/auth/login?_target_path=/iserv/time-table/", text=LOGIN_PAGE)
        if self.page == PAGE_ROOT:
            return Answer(base + "/iserv/", text="<html><body><nav id=\"main\"></nav></body></html>")
        if self.page == PAGE_FOREIGN:
            return Answer(url, text="<html><body><p>Wartung</p></body></html>")
        return Answer(url, text=child_page(self.options))

    def _data(self, url, params):
        if self.on_data is not None:
            self.on_data()
        if self.time_table == FORBIDDEN:
            return Answer(url, 403, "<html><head><title>Riverside Primary</title></head><body><h1>Zugriff verweigert</h1></body></html>")
        if self.time_table == BROKEN:
            return Answer(url, 500, "<html><body>Fehler</body></html>")
        if self.time_table == ODD:
            return Answer(url, payload={"rows": [{"cells": 3}]}, content_type="application/json")
        week_filter = json.loads(params.get("filter") or "{}")
        payload = time_table_week(week_filter.get("startDate", ""), week_filter.get("endDate", ""), self.time_table == LESSONS, self.plan)
        records = self.changes(week_filter.get("startDate", "")) if callable(self.changes) else self.changes
        payload["plain-changes"] = [dict(record) for record in records]
        return Answer(url, payload=payload, content_type="application/json")

    def get(self, url, params=None, timeout=None, **kwargs):
        path = urlsplit(url).path
        self.calls.append((path, dict(params or {})))
        if path.startswith(DSA_ROOT):
            return self._school_app(url, path[len(DSA_ROOT):])
        if path == PAGE:
            return self._page(url)
        if path == DATA:
            return self._data(url, params or {})
        return Answer(url, 404, "")

    def post(self, url, data=None, timeout=None, **kwargs):
        return Answer(url, 404, "")


class SignedInClient(IServClient):
    def login(self, username, password, code_provider):
        self.username = username
        return self


def client_factory(school):
    return lambda url: SignedInClient(url, session=school)
