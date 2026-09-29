from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from tests.time_table_school import (
    DSA_ROOT,
    EMPTY,
    FORBIDDEN,
    LESSONS,
    PAGE_FORBIDDEN,
    SCHOOL_APP_ANSWERS,
    SCHOOL_APP_REFUSES,
    SCHOOL_APP_REGULAR,
    SCHOOL_APP_SUBSTITUTED,
    WEEK_PLAN,
    Answer,
    TimeTableSchool,
    moved_week_changes,
    MOVED_WEEK_PLAN,
)

FIXTURES = Path(__file__).parent / "fixtures"
PROVIDER = "https://pay.provider.example/start"


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def start_page(segments):
    links = "".join('<a href="/iserv/%s">%s</a>' % (segment, segment) for segment in segments)
    return "<html><body><nav id=\"main\">%s</nav><main><h1>Start</h1></main></body></html>" % links


CLASSIC_ABSENCE_PAGE = (
    "<html><body><nav><a href=\"/modules/absence_obsolete/\">Hilfe</a></nav>"
    "<table id=\"crud-table\"><thead><tr><th>Zeitraum</th><th>Name</th><th>Klasse</th><th>Status</th></tr></thead>"
    "<tbody><tr><td><input type=\"checkbox\"></td><td>01.09.2026</td><td>Kim Muster</td><td>5A</td><td>offen</td>"
    "<td>-</td><td>-</td></tr></tbody></table></body></html>"
)
PAGES = {
    "/iserv/parentletter/parent/index": lambda: fixture_text("letters_index.html"),
    "/iserv/parentconference/attendee/": lambda: fixture_text("conferences_empty.html"),
    "/iserv/absence/": lambda: CLASSIC_ABSENCE_PAGE,
    "/iserv/ausleihe/": lambda: "<html><body><h1>Ausleihe</h1></body></html>",
}


class ProfileSchool(TimeTableSchool):
    def __init__(self, menu=(), children_listed=True, sick_notes=True, **fields):
        super().__init__(sick_notes=sick_notes, **fields)
        self.menu = tuple(menu)
        self.children_listed = children_listed

    def _me(self):
        me = super()._me()
        if not self.children_listed:
            me["children"] = []
        return me

    def _school_app(self, url, rest, params=None):
        if rest.startswith("pinboards"):
            return Answer(url, payload=[], content_type="application/json")
        if rest.startswith("sickNotes/userSelection") and not self.children_listed:
            return Answer(url, payload=[], content_type="application/json")
        return super()._school_app(url, rest, params)

    def _offers(self, segment):
        return any(item.split("/")[0] == segment for item in self.menu)

    def get(self, url, params=None, timeout=None, **kwargs):
        path = urlsplit(url).path
        segment = path.split("/")[2] if path.startswith("/iserv/") and path.count("/") >= 2 else ""
        if path in ("/iserv/", "/iserv"):
            self.calls.append((path, dict(params or {})))
            return Answer(url, text=start_page(self.menu))
        if path in PAGES and self._offers(segment):
            self.calls.append((path, dict(params or {})))
            return Answer(url, text=PAGES[path]())
        if path == "/iserv/klassengeld/redirect" and self._offers("klassengeld"):
            self.calls.append((path, dict(params or {})))
            answer = Answer(url, 302, "")
            answer.headers["Location"] = PROVIDER
            return answer
        if path.startswith(DSA_ROOT) or path.startswith("/iserv/time-table/"):
            return super().get(url, params=params, timeout=timeout, **kwargs)
        self.calls.append((path, dict(params or {})))
        return Answer(url, 404, "")


NINE_COURSES = tuple((3, 1, subject, None, "R%d" % index) for index, subject in enumerate(
    ("BICH", "D-PJ", "EK-PJ", "IF", "MU-PJ", "PA-PJ", "SPE-PJ", "SPE-PJ2", "WIPO-PJ")
))
BASE_MENU = ("parentletter/", "parentconference/")


@dataclass(frozen=True)
class Profile:
    name: str
    story: str
    fields: dict
    menu: tuple
    source: str | None
    most_parallel: int = 1
    timetable_module: bool = True
    children_listed: bool = True
    covered: tuple = ()
    unsupported: tuple = ()
    unknown: tuple = ()
    changed_lessons: bool = False
    report_source: str = "school-app"
    substitution_line: str = ""
    stored_children: tuple = ()

    def school(self):
        return ProfileSchool(menu=self.menu, children_listed=self.children_listed, **self.fields)


PROFILES = {
    profile.name: profile
    for profile in (
        Profile(
            name="school_app_normal",
            story="The school app releases the timetable with lessons, slots and substitutions.",
            fields=dict(school_lessons=True, slots=True, time_table=EMPTY),
            menu=BASE_MENU + ("dsa-timetable/timetable",),
            source="school-app",
        ),
        Profile(
            name="school_app_with_substitutions",
            story="The school app releases substitutions and names them only as a changed teacher, a lesson that is "
            "gone and a lesson at another time compared with the regular plan.",
            fields=dict(school_week=(SCHOOL_APP_REGULAR, SCHOOL_APP_SUBSTITUTED), slots=True, time_table=EMPTY),
            menu=BASE_MENU + ("dsa-timetable/timetable",),
            source="school-app",
            changed_lessons=True,
            substitution_line="- Child 1 substitutions: regular plan 10 lessons, current 9, changed 1, only in the regular "
            "plan 2, only in the current plan 1, marked by the school 0, marks shown",
        ),
        Profile(
            name="time_table_with_changes",
            story="The school app week is empty, the older time-table module holds the plan and its changes, and the menu "
            "lists Klassengeld, the older absence page and an unknown lending module.",
            fields=dict(time_table=LESSONS, changes=moved_week_changes, plan=MOVED_WEEK_PLAN),
            menu=BASE_MENU + ("time-table/", "absence/", "klassengeld/redirect", "ausleihe/"),
            source="time-table",
            most_parallel=3,
            covered=("absence_obsolete",),
            unsupported=("klassengeld",),
            unknown=("ausleihe",),
            changed_lessons=True,
            report_source="time-table",
        ),
        Profile(
            name="second_school_without_children",
            story="A second school whose account lists no children; its time-table page refuses.",
            fields=dict(time_table=FORBIDDEN, page=PAGE_FORBIDDEN),
            menu=BASE_MENU + ("klassengeld/redirect",),
            source=None,
            children_listed=False,
            unsupported=("klassengeld",),
        ),
        Profile(
            name="second_school_with_a_stored_child",
            story="A second school whose account lists no children keeps a child stored earlier; the time-table page "
            "and its data both refuse.",
            fields=dict(time_table=FORBIDDEN, page=PAGE_FORBIDDEN),
            menu=BASE_MENU + ("klassengeld/redirect",),
            source=None,
            children_listed=False,
            unsupported=("klassengeld",),
            stored_children=({"child_id": "500001", "name": "Child One"},),
        ),
        Profile(
            name="school_app_empty_with_slots",
            story="The school app is released and has lesson slots but no lessons, the time-table module refuses.",
            fields=dict(slots=True, time_table=FORBIDDEN, page=PAGE_FORBIDDEN),
            menu=BASE_MENU + ("dsa-timetable/timetable", "klassengeld/redirect"),
            source="school-app",
            unsupported=("klassengeld",),
        ),
        Profile(
            name="release_off_hidden_teachers",
            story="The school withholds the school app timetable; the time-table module names no teachers, moves lessons "
            "and has three courses in one period.",
            fields=dict(school_app=SCHOOL_APP_REFUSES, released=False, slots=True, plan=MOVED_WEEK_PLAN, changes=moved_week_changes),
            menu=BASE_MENU + ("time-table/", "klassengeld/redirect"),
            source="time-table",
            most_parallel=3,
            unsupported=("klassengeld",),
            changed_lessons=True,
            report_source="time-table",
        ),
        Profile(
            name="no_timetable_classic_absence",
            story="Neither the school app nor the time-table module offers a timetable; the menu has the older absence page.",
            fields=dict(school_app=SCHOOL_APP_REFUSES, released=False, time_table=FORBIDDEN, page=PAGE_FORBIDDEN),
            menu=BASE_MENU + ("absence/",),
            source=None,
            timetable_module=False,
            covered=("absence_obsolete",),
            report_source="none, the school offers no timetable to this account",
        ),
        Profile(
            name="many_parallel_courses",
            story="The time-table module lists nine project courses in one period.",
            fields=dict(time_table=LESSONS, plan=WEEK_PLAN + NINE_COURSES),
            menu=BASE_MENU + ("time-table/",),
            source="time-table",
            most_parallel=9,
            report_source="time-table",
        ),
    )
}
