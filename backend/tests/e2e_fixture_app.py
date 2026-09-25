import contextvars
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from app import courses, haservices, messages, modules, own_entries, subscriptions, supervisor
from app.iserv.errors import DataError, OutageError
from app.iserv.letters import REPLY_PRESENT, parse_reply_form
from app.letter_service import LETTERS_SHOW_PATH, LetterService
from app.messenger import (
    READ_FAILED_KEY,
    READ_OK_KEY,
    ROOM_INCOMPLETE_KEY,
    ROOM_OK_KEY,
)
from app.mapping import derive_subject_code
from app.server import create_app
from app.wizard import Wizard
from app.sorting import child_sort_key
from app.store import CONNECTION_DEFAULTS, DEFAULT_CONFIG, INTEGRATION_SCHOOLS_KEY, LAYOUT_KEYS, Store, connection_short_name, normalize_layout

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
E2E_DATA_DIR = Path(os.environ.get("ISERV_E2E_DATA_DIR", BACKEND_DIR.parent / "data-e2e"))


def reset_e2e_data_dir():
    if E2E_DATA_DIR.exists():
        shutil.rmtree(E2E_DATA_DIR)

LONG_SUBJECT = "Naturwissenschaften und angewandte Informatik"
LANG_COOKIE = "e2e_lang"
LANG_ENV = "ISERV_E2E_LANG"
LANG = contextvars.ContextVar("e2e_lang", default="")
CONTENT = {
    "de": {
        "subject_long": LONG_SUBJECT,
        "subject_german": "Deutsch",
        "subject_english_double": "Englisch als Doppelbelegung mit der Klassenlehrerin",
        "scenario_subjects": ["Deutsch", "Mathematik", LONG_SUBJECT, "Englisch", "Sport"],
        "showcase_subjects": [
            ("MAT", "Mathematik"),
            ("DEU", "Deutsch"),
            ("ENG", "Englisch"),
            ("SPO", "Sport"),
            ("MUS", "Musik"),
            ("SU", "Sachunterricht"),
            ("KUN", "Kunst"),
        ],
        "teacher": "Fr. Behrend",
        "teacher_long": "Fr. Behrend-Waldenburger",
        "teacher_substitute": "Fr. Schmidt-Waldenburger",
        "showcase_teachers": {
            "MAT": "Fr. Nordfeld",
            "DEU": "Hr. Lindqvist",
            "ENG": "Fr. Carter",
            "SPO": "Hr. Brandt",
            "MUS": "Fr. Rivera",
            "SU": "Fr. Patel",
            "KUN": "Fr. Brooks",
        },
        "showcase_substitute": "Hr. Eschbach",
        "class_3b": "Klasse 3b",
        "class_5a": "Klasse 5a",
        "letter_start": "Informationen zum Schuljahresstart und weiteren Terminen",
        "letter_conference": "Elternsprechtagsanmeldung für das Schuljahr 2026/2027",
        "letter_school_two": "Kennenlernabend der neuen Fuenften",
        "letter_reply": "Ausflug in den Tierpark: Rueckfragen gern per Antwort",
        "letter_confirmed": "Neue Hausordnung ab Oktober",
        "letter_scenario": "Elternbrief %02d mit einem sehr langen Titel zur Zeilenhoehe",
        "folder_council": "Elternbeirat",
        "folder_class": "Klasse 3b",
        "folder_school_two": "Schulleitung Zwei",
        "owner_office": "Schulleitung",
        "owner_class_teacher": "Klassenlehrerin",
        "owner_association": "Foerderverein",
        "column_news": "Aktuelles",
        "column_dates": "Termine",
        "post_trip_title": "Ausflug ins Schullandheim mit vielen Details zur Anreise und Ausruestung",
        "post_trip_text": "Bitte packt festes Schuhwerk ein.",
        "post_evening_title": "Elternabend",
        "post_evening_text": "Termin steht fest.",
        "post_welcome_title": "Willkommen",
        "post_welcome_text": "Willkommen im neuen Schuljahr.",
        "post_school_two_title": "Schulfest im Oktober",
        "post_school_two_text": "Der Foerderverein laedt ein.",
        "post_scenario_title": "Pinnwandbeitrag %02d mit einem laengeren Titel",
        "post_scenario_text": "Kurzer Vorschautext.",
        "period_name": "%d. Stunde",
        "period_label": "%d. Stunde %d:00 - %d:45",
        "absence_comment": "Fieberhafter Infekt mit ärztlicher Bescheinigung",
        "absence_attachment": "aerztliche-bescheinigung-fieberhafter-infekt-25-08-2026.pdf",
        "absence_submitted": "Meldung eingereicht.",
        "conference_class": "Elternsprechtag Klasse 3b",
        "conference_individual": "Individuelle Beratung",
        "showcase_pause_name": "Pause",
        "showcase_club_name": "Schach-AG",
        "showcase_appointment_name": "Zahnarzttermin",
    },
    "en": {
        "subject_long": "Natural Sciences and Applied Computing",
        "subject_german": "German",
        "subject_english_double": "English shared with the class teacher",
        "scenario_subjects": ["German", "Mathematics", "Natural Sciences and Applied Computing", "English", "Sport"],
        "showcase_subjects": [
            ("MAT", "Mathematics"),
            ("GER", "German"),
            ("ENG", "English"),
            ("SPO", "Sport"),
            ("MUS", "Music"),
            ("SCI", "Science"),
            ("ART", "Art"),
        ],
        "teacher": "Ms Behrend",
        "teacher_long": "Ms Behrend-Waldenburger",
        "teacher_substitute": "Ms Schmidt-Waldenburger",
        "showcase_teachers": {
            "MAT": "Ms Northfield",
            "GER": "Mr Lindqvist",
            "ENG": "Ms Carter",
            "SPO": "Mr Hughes",
            "MUS": "Ms Rivera",
            "SCI": "Dr Patel",
            "ART": "Ms Brooks",
        },
        "showcase_substitute": "Mr Ashby",
        "class_3b": "Class 3b",
        "class_5a": "Class 5a",
        "letter_start": "Information on the start of the school year and upcoming dates",
        "letter_conference": "Registration for the parent-teacher conference 2026/2027",
        "letter_school_two": "Welcome evening for the new fifth grade",
        "letter_reply": "Trip to the zoo: questions welcome as a reply",
        "letter_confirmed": "New school rules from October",
        "letter_scenario": "Parent letter %02d with a very long title to test the line height",
        "folder_council": "Parent council",
        "folder_class": "Class 3b",
        "folder_school_two": "Head office two",
        "owner_office": "Head office",
        "owner_class_teacher": "Class teacher",
        "owner_association": "Parents' association",
        "column_news": "News",
        "column_dates": "Dates",
        "post_trip_title": "School trip to the country hostel with details on travel and equipment",
        "post_trip_text": "Please pack sturdy shoes.",
        "post_evening_title": "Parents' evening",
        "post_evening_text": "The date is set.",
        "post_welcome_title": "Welcome",
        "post_welcome_text": "Welcome to the new school year.",
        "post_school_two_title": "School fair in October",
        "post_school_two_text": "The parents' association invites you.",
        "post_scenario_title": "Noticeboard post %02d with a longer title",
        "post_scenario_text": "Short preview text.",
        "period_name": "Period %d",
        "period_label": "Period %d, %d:00 to %d:45",
        "absence_comment": "Feverish infection, doctor's note attached",
        "absence_attachment": "doctors-note-feverish-infection-25-08-2026.pdf",
        "absence_submitted": "Report submitted.",
        "conference_class": "Parent-teacher conference class 3b",
        "conference_individual": "Individual consultation",
        "showcase_pause_name": "Break",
        "showcase_club_name": "Chess club",
        "showcase_appointment_name": "Dentist appointment",
    },
}


def content_language():
    chosen = LANG.get("") or os.environ.get(LANG_ENV, "")
    return "en" if str(chosen).strip().lower() == "en" else "de"


def text(key):
    return CONTENT[content_language()][key]

CONFIRM_LETTER_ID = "c3d4e5f6a7b8491023c4d5e6f7a8b901"
CONFIRMED_AT = "2026-09-03T14:05:00"
REPLY_LETTER_ID = "d4e5f6a7b8c9401234d5e6f7a8b9c012"
CONFIRMED_LETTER_ID = "e5f6a7b8c9d0412345e6f7a8b9c0d123"
CONFIRMED_RECIPIENT_ID = "f6a7b8c9d0e1423456f7a8b9c0d1e234"
FIXTURE_ORIGIN = "https://school.example"
LETTER_PAGES = {
    REPLY_LETTER_ID: BACKEND_DIR / "tests" / "fixtures" / "letter_reply_form.html",
    CONFIRMED_LETTER_ID: BACKEND_DIR / "tests" / "fixtures" / "letter_confirm_done.html",
}


def done_confirmation():
    return {"type": "seen", "open": False, "done": True, "sendable": False, "confirmed_at": CONFIRMED_AT}


def letter_page(letter_id, recipient_id):
    path = LETTERS_SHOW_PATH.format(letter=letter_id, recipient=recipient_id)
    return SimpleNamespace(
        status_code=200, url=FIXTURE_ORIGIN + path, text=LETTER_PAGES[letter_id].read_text(encoding="utf-8")
    )


def letter_list_page(path):
    rows = "".join(
        f'<tr><td><a href="{LETTERS_SHOW_PATH.format(letter=letter_id, recipient=CONFIRMED_RECIPIENT_ID)}">x</a></td></tr>'
        for letter_id in LETTER_PAGES
    )
    return SimpleNamespace(
        status_code=200, url=FIXTURE_ORIGIN + path, text=f'<table id="crud-table"><tbody>{rows}</tbody></table>'
    )


def letter_reply_offer(letter_id, recipient_id):
    page = letter_page(letter_id, recipient_id)
    return {"available": True} if parse_reply_form(page.text, page.url)["state"] == REPLY_PRESENT else None


class FixtureLetterClient:
    def __init__(self):
        self.sent = []

    def fetch_or_raise(self, path, params=None):
        if "/parent/show/" not in path:
            return letter_list_page(path)
        parts = path.rstrip("/").split("/")
        return letter_page(parts[-2], parts[-1])

    def post_absolute(self, url, data, timeout=30, headers=None):
        self.sent.append(dict(data))
        return SimpleNamespace(status_code=200, url=url, text="", history=[])


class FixtureReplyStore:
    def __init__(self):
        self.replies = {}

    def load_letters_replies(self):
        return dict(self.replies)

    def save_letters_replies(self, data):
        self.replies = dict(data)

    def load_letters_search_cache(self):
        return {}

    def load_letters_confirmations(self):
        return {}


FIXTURE_LETTER_CLIENT = FixtureLetterClient()
FIXTURE_LETTERS = LetterService(
    SimpleNamespace(id="fixture", store=FixtureReplyStore(), _session=lambda: FIXTURE_LETTER_CLIENT)
)

HOLIDAY_REGION = "DE-NI"
HOLIDAY_FULL_WEEK_OFFSET = 3
HOLIDAY_SINGLE_DAY_OFFSET = 5
HOLIDAY_SINGLE_DAY_WEEKDAY = 2
LONG_HOLIDAY_NAME = "Tag der Deutschen Einheit"
SCHOOL_DAYS = 5


LONG_DEVICE_NAME = "Test Device With A Very Long Friendly Name For Layout"

ABSENCE_RULES = {
    "sick_by_lesson": True,
    "sick_comment": True,
    "sick_cutoff": "07:30",
    "sick_cutoff_message": "",
    "duty_hint": "",
    "leave_min_days": 3,
    "daycare_min_days": 0,
    "daycare_cutoff": "08:00",
    "daycare_reason_required": True,
    "daycare_custom_pickup": False,
    "daycare_pickup_times": ["13:30", "14:30", "15:30"],
}


def fake_notify_services():
    services = [
        {
            "service": f"notify.mobile_app_test_device_{index:02d}",
            "name": LONG_DEVICE_NAME if index == 1 else f"Test Device {index:02d}",
            "name_source": "device_tracker",
            "category": "mobile",
        }
        for index in range(1, 19)
    ]
    services.append(
        {
            "service": "notify.persistent_notification",
            "name": None,
            "name_source": None,
            "category": "persistent",
        }
    )
    services.append({"service": "notify.notify", "name": None, "name_source": None, "category": "group"})
    services.append(
        {
            "service": "notify.a_very_long_custom_notification_service_identifier",
            "name": None,
            "name_source": None,
            "category": "other",
        }
    )
    return {"supervisor": True, "services": services}


haservices.list_notify_services = fake_notify_services
real_feed_port_state = supervisor.feed_port_state


def fixture_feed_port_state(port=supervisor.FEED_PORT):
    scenario = current_scenario()
    if scenario and scenario.get("showcase"):
        return {"supervisor": True, "port_open": True, "mapped_port": int(port)}
    return real_feed_port_state(port)


supervisor.feed_port_state = fixture_feed_port_state


SCENARIO_COOKIE = "e2e_scenario"
SCENARIO = contextvars.ContextVar("e2e_scenario", default="")
SCHOOLS_COOKIE = "e2e_schools"
SCHOOLS_ENV = "ISERV_E2E_SCHOOLS"
SCHOOLS = contextvars.ContextVar("e2e_schools", default="")
SCHOOL_ONE = "a1b2c3d4"
SCHOOL_TWO = "b2c3d4e5"
SCHOOL_ONE_URL = "https://school-one.example"
SCHOOL_TWO_URL = "https://school-two.example"
SCHOOL_ONE_NAME = "Riverside Primary"
SCHOOL_TWO_NAME = "Hillview School"
SCHOOL_ONE_SHORT = "Riverside"
SCHOOL_TWO_SHORT = "Hillview"
SCHOOL_TWO_CHILDREN = [
    {"child_id": "child-1", "name": "Mia Musterkind", "class_name": "7c"},
    {"child_id": "child-3", "name": "Lena Musterkind", "class_name": "5a"},
]


def school_two_letters():
    return [
        {
            "letter_id": "t1",
            "recipient_id": "r9",
            "title": text("letter_school_two"),
            "child": "Lena Musterkind",
            "recipients": text("class_5a"),
            "published": "30.08.2026",
            "unread": True,
            "body_text": "",
            "attachments": [],
            "confirmation": {"type": "none", "open": False, "done": False, "sendable": False, "confirmed_at": ""},
        },
    ]


def school_two_folder():
    return {"id": 9, "title": text("folder_school_two"), "description": "", "columns": [], "attachments": []}


def school_two_post():
    return {
        "id": 9,
        "title": text("post_school_two_title"),
        "text": text("post_school_two_text"),
        "color": "forest",
        "owner": text("owner_association"),
        "folder_id": 9,
        "folder_title": text("folder_school_two"),
        "column_title": text("column_news"),
        "unread": True,
        "attachments": [],
    }


SCHOOL_TWO_ROOM = "!roomtwo:school-two.example"
SCHOOL_TWO_ROOM_NAME = "Klassenleitung 5a"
ROOM_WRITES_COOKIE = "e2e_room_writes"
ROOM_WRITES = contextvars.ContextVar("e2e_room_writes", default="")
OUTAGE_COOKIE = "e2e_outage"
OUTAGE = contextvars.ContextVar("e2e_outage", default="")
OUTAGE_SINCE_EPOCH = 1_789_777_080
OUTAGE_LAST_SUCCESS_EPOCH = 1_789_775_280
MODULES_COOKIE = "e2e_modules"
MODULES_ENV = "ISERV_E2E_MODULES"
MODULES_NONE = "none"
MODULES = contextvars.ContextVar("e2e_modules", default="")
LONG_SUBJECTS_COOKIE = "e2e_long_subjects"
LONG_SUBJECTS = contextvars.ContextVar("e2e_long_subjects", default="")
LONG_SUBJECT_NAMES = [
    "Naturwissenschaften und angewandte Informatik",
    "Wirtschaft und Verwaltung",
    "Musische Bildung und Kreativitaet",
    "Gesellschaftswissenschaften",
]
REPORTS_COOKIE = "e2e_reports"
REPORTS = contextvars.ContextVar("e2e_reports", default="")
EMPTY_COOKIE = "e2e_empty"
EMPTY = contextvars.ContextVar("e2e_empty", default="")
LAYOUT_COOKIE = "e2e_layout"
LAYOUT = contextvars.ContextVar("e2e_layout", default="")
WIZARD_COOKIE = "e2e_wizard"
WIZARD_MODE = contextvars.ContextVar("e2e_wizard", default="")
COURSES_COOKIE = "e2e_courses"
COURSES = contextvars.ContextVar("e2e_courses", default="")
TIMETABLE_SOURCE_COOKIE = "e2e_timetable_source"
TIMETABLE_SOURCE = contextvars.ContextVar("e2e_timetable_source", default="")
TIMETABLE_SOURCE_MODES = {"time-table": "lessons", "empty": "empty"}
TIMETABLE_SOURCE_OPTION = "0f1e2d3c-4b5a-4968-8776-a5b4c3d2e1f0"
TIMETABLE_SOURCE_SCHOOLS = {}
COURSE_PERIODS = {
    3: [("E1", "CCC", "R201"), ("E2", "DDD", "R202"), ("F1", "EEE", "R203"), ("L1", "FFF", "R204"), ("SP", "GGG", "GYM1"), ("SP", "HHH", "GYM2")],
    4: [("REV", "III", "R301"), ("RKA", "JJJ", "R302"), ("WN", "KKK", "R303")],
    5: [("KU", "LLL", "R401"), ("MU", "MMM", "R402")],
}
COURSE_SINGLES = {1: ("D", "BEH", "R101"), 2: ("M", "MUE", "R101")}
COURSE_TEACHERS = {
    "BEH": "Behrens", "MUE": "Mueller", "CCC": "Castor", "DDD": "Dachs", "EEE": "Elster", "FFF": "Fink",
    "GGG": "Gans", "HHH": "Hase", "III": "Igel", "JJJ": "Jaguar", "KKK": "Kranich", "LLL": "Luchs",
    "MMM": "Marder", "ZZZ": "Zander",
}
COURSE_SUBSTITUTION = (2, 3, "E2", "ZZZ")
COURSE_FILTER_STATE = {}
LAYOUT_STATE = {}
REPORT_FLAG_KEYS = ("reported_modules", "modules_card_hidden")
UNKNOWN_MODULES = [
    {"segment": "mail", "label": "E-Mail"},
    {"segment": "videoconference", "label": "Videokonferenzen"},
]
FIXTURE_ISERV_VERSION = "3.9.1"
CONFERENCE_FIRST_OFFSET = 5
CONFERENCE_SECOND_OFFSET = 12
ABSENCE_AHEAD_OFFSET = 3

SCENARIO_CHILDREN = [
    {"child_id": "child-1", "name": "Mia Musterkind", "class_name": "3b"},
    {"child_id": "child-2", "name": "Tom Musterkind-Langenscheidt", "class_name": "1a"},
]

SCENARIOS = {
    "short-day": {"children": 1, "periods": 2, "letters": 0, "posts": 0},
    "long-day": {"children": 1, "periods": 8, "letters": 3, "posts": 3},
    "two-children": {"children": 2, "periods": 5, "letters": 3, "posts": 3},
    "two-long": {"children": 2, "periods": 8, "letters": 3, "posts": 3},
    "full-cap": {"children": 2, "periods": 8, "letters": 20, "posts": 20},
    "showcase": {"children": 2, "periods": 5, "letters": 0, "posts": 0, "showcase": True},
}

SCENARIO_WEEKDAYS = range(1, 8)
SHOWCASE_DAYS = 5
SHOWCASE_PERIODS = 5
SHOWCASE_TODAY_OFFSET = 2
SHOWCASE_COLORS = ["blue", "maroon", "lavender", "green", "sand", "mint", "magenta"]
SHOWCASE_CHANGES = {
    "child-1": {(3, 3): "changed", (3, 5): "cancelled"},
    "child-2": {(3, 2): "cancelled", (3, 4): "changed"},
}


def current_scenario():
    return SCENARIOS.get(SCENARIO.get(""), None)


def list_scenario():
    scenario = current_scenario()
    return None if not scenario or scenario.get("showcase") else scenario


def read_cookie(scope, wanted):
    for key, value in scope.get("headers", []):
        if key != b"cookie":
            continue
        for part in value.decode("latin-1").split(";"):
            name, _, raw = part.strip().partition("=")
            if name == wanted:
                return raw
    return ""


def scenario_cookie(scope):
    return read_cookie(scope, SCENARIO_COOKIE)


def room_writes_allowed():
    return ROOM_WRITES.get("") == "1"


def outage_active():
    return OUTAGE.get("") == "1"


def long_subjects_active():
    return LONG_SUBJECTS.get("") == "1"


def long_subject_lessons():
    taken = set()
    codes = []
    for name in LONG_SUBJECT_NAMES:
        code = derive_subject_code(name, taken)
        taken.add(code)
        codes.append(code)
    lessons = []
    for day in range(1, 6):
        for period in range(1, 5):
            index = (day + period) % len(LONG_SUBJECT_NAMES)
            lessons.append(
                {
                    "date": "31.08.2026",
                    "day_of_week": day,
                    "period": period,
                    "start_time": f"{7 + period}:00",
                    "subject_code": codes[index],
                    "subject_label": LONG_SUBJECT_NAMES[index],
                    "color": "teal",
                    "teacher_code": "BEH",
                    "teacher_label": text("teacher"),
                    "is_class_teacher": True,
                    "room": "R1",
                    "change_kind": "",
                    "changed_fields": [],
                    "previous": {"subject": "", "teacher": "", "room": ""},
                }
            )
    return lessons


def raise_when_unreachable():
    if outage_active():
        raise OutageError("status:503")


def school_count():
    chosen = SCHOOLS.get("") or os.environ.get(SCHOOLS_ENV, "")
    return 2 if str(chosen).strip() == "2" else 1


def school_ids():
    return [SCHOOL_ONE, SCHOOL_TWO][: school_count()]


def child_key(connection_id, child_id):
    return f"{connection_id}:{child_id}"


def split_key(key):
    connection_id, _, child_id = str(key or "").partition(":")
    return connection_id, child_id


def school_display_name(connection_id):
    return SCHOOL_TWO_NAME if connection_id == SCHOOL_TWO else SCHOOL_ONE_NAME


def tag(connection_id, item):
    tagged = dict(item)
    tagged["connection_id"] = connection_id
    tagged["school"] = school_display_name(connection_id)
    return tagged


def module_registry():
    chosen = MODULES.get("") or os.environ.get(MODULES_ENV, "")
    registry = modules.default_registry()
    registry["checked_at"] = 1_756_800_000
    registry["iserv_version"] = FIXTURE_ISERV_VERSION
    if not chosen:
        return registry
    wanted = set() if chosen == MODULES_NONE else {part.strip() for part in chosen.split(",") if part.strip()}
    registry["modules"] = {name: name in wanted for name in modules.MODULES}
    registry["unknown"] = list(UNKNOWN_MODULES)
    return registry


class ScenarioMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            SCENARIO.set(scenario_cookie(scope))
            ROOM_WRITES.set(read_cookie(scope, ROOM_WRITES_COOKIE))
            MODULES.set(read_cookie(scope, MODULES_COOKIE))
            REPORTS.set(read_cookie(scope, REPORTS_COOKIE))
            SCHOOLS.set(read_cookie(scope, SCHOOLS_COOKIE))
            LANG.set(read_cookie(scope, LANG_COOKIE))
            OUTAGE.set(read_cookie(scope, OUTAGE_COOKIE))
            LONG_SUBJECTS.set(read_cookie(scope, LONG_SUBJECTS_COOKIE))
            EMPTY.set(read_cookie(scope, EMPTY_COOKIE))
            LAYOUT.set(read_cookie(scope, LAYOUT_COOKIE))
            WIZARD_MODE.set(read_cookie(scope, WIZARD_COOKIE))
            COURSES.set(read_cookie(scope, COURSES_COOKIE))
            TIMETABLE_SOURCE.set(read_cookie(scope, TIMETABLE_SOURCE_COOKIE))
        await self.app(scope, receive, send)


def timetable_source_mode():
    return TIMETABLE_SOURCE_MODES.get(TIMETABLE_SOURCE.get(""), "")


def timetable_source_school(mode):
    from app.service import ConnectionService
    from app.store import ConnectionStore
    from tests.time_table_school import TimeTableSchool, client_factory

    entry = TIMETABLE_SOURCE_SCHOOLS.get(mode)
    if entry is not None:
        return entry
    directory = E2E_DATA_DIR / ("timetable-source-" + mode)
    shutil.rmtree(directory, ignore_errors=True)
    store = Store(directory)
    created = store.add_connection(SCHOOL_ONE_URL, setup_complete=True)
    store.save_secrets(created["id"], {"username": "parent", "password": "fixture"})
    school = TimeTableSchool(
        child_id="child-1",
        child_name=("Mia", "Musterkind"),
        options=((TIMETABLE_SOURCE_OPTION, "Musterkind, Mia"),),
        time_table=mode,
    )
    entry = ConnectionService(ConnectionStore(store, created["id"]), client_factory=client_factory(school))
    TIMETABLE_SOURCE_SCHOOLS[mode] = entry
    return entry


def emptied_keys():
    return {part.strip() for part in EMPTY.get("").split(",") if part.strip()}


def courses_active():
    return COURSES.get("") == "1"


def course_lesson(day_date, day, period, code, teacher, room, change_kind="", regular_teacher=""):
    return {
        "date": day_date,
        "day_of_week": day,
        "period": period,
        "start_time": "%02d:00" % (7 + period),
        "subject_key": code,
        "subject_code": code,
        "subject_label": code,
        "color": "",
        "teacher_code": teacher,
        "teacher_label": COURSE_TEACHERS[teacher],
        "teacher_surname": COURSE_TEACHERS[teacher],
        "is_class_teacher": False,
        "room": room,
        "change_kind": change_kind,
        "changed_fields": ["teacher"] if change_kind == "changed" else [],
        "previous": {"subject": "", "teacher": COURSE_TEACHERS.get(regular_teacher, ""), "room": ""},
        "course_key": courses.course_key(code, regular_teacher or teacher),
    }


def course_week_lessons(week_offset=0):
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7 * week_offset)
    lessons = []
    for day in range(1, 6):
        day_date = (monday + timedelta(days=day - 1)).strftime("%d.%m.%Y")
        for period, (code, teacher, room) in COURSE_SINGLES.items():
            lessons.append(course_lesson(day_date, day, period, code, teacher, room))
        for period, listed in COURSE_PERIODS.items():
            for code, teacher, room in listed:
                if (day, period, code) == COURSE_SUBSTITUTION[:3]:
                    lessons.append(course_lesson(day_date, day, period, code, COURSE_SUBSTITUTION[3], room, "changed", teacher))
                else:
                    lessons.append(course_lesson(day_date, day, period, code, teacher, room))
    return lessons


def course_filters(connection_id):
    return dict(COURSE_FILTER_STATE.get(connection_id) or {}) if courses_active() else {}


def course_week(week_offset=0):
    monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7 * week_offset)
    lessons = course_week_lessons(week_offset)
    return {
        "last_updated": timetable_stamp(),
        "start_date": monday.strftime("%d.%m.%Y"),
        "end_date": (monday + timedelta(days=6)).strftime("%d.%m.%Y"),
        "lessons": lessons,
        "changes": [],
        "period_times": {str(period): "%02d:00" % (7 + period) for period in range(1, 6)},
        "change_count": sum(1 for lesson in lessons if lesson["change_kind"]),
        "week_offset": week_offset,
    }


def module_emptied(name):
    return name in emptied_keys()


def block_emptied(key):
    return key in emptied_keys()


def today_weekday():
    return fixture_today().isoweekday()


def scenario_lessons(child_id, periods, week_offset=0):
    if block_emptied("week") and week_offset == 0:
        return []
    if block_emptied("next_lesson") and week_offset != 0:
        return []
    today_dow = today_weekday()
    lessons = []
    offset = 0 if child_id == SCENARIO_CHILDREN[0]["child_id"] else 1
    for day in SCENARIO_WEEKDAYS:
        if block_emptied("today") and week_offset == 0 and day == today_dow:
            continue
        if block_emptied("next_lesson") and day != today_dow:
            continue
        for period in range(1, periods + 1):
            subjects = text("scenario_subjects")
            subject = subjects[(period + offset) % len(subjects)]
            start_time = "00:%02d" % period if block_emptied("next_lesson") else "%02d:00" % (7 + period)
            lessons.append(
                {
                    "date": "31.08.2026",
                    "day_of_week": day,
                    "period": period,
                    "start_time": start_time,
                    "subject_code": subject[:3].upper(),
                    "subject_label": subject,
                    "color": "teal",
                    "teacher_code": "BEH",
                    "teacher_label": text("teacher_long"),
                    "is_class_teacher": True,
                    "room": "R%d" % period,
                    "change_kind": "" if block_emptied("changes") else ("cancelled" if period == periods and offset == 0 else ""),
                    "changed_fields": [],
                    "previous": {"subject": "", "teacher": "", "room": ""},
                }
            )
    return lessons


def showcase_week_start():
    today = date.today()
    return today - timedelta(days=today.weekday())


def showcase_today():
    return showcase_week_start() + timedelta(days=SHOWCASE_TODAY_OFFSET)


def fixture_today():
    scenario = current_scenario()
    return showcase_today() if scenario and scenario.get("showcase") else date.today()


def timetable_stamp():
    scenario = current_scenario()
    if scenario and scenario.get("showcase"):
        return showcase_today().strftime("%d.%m.%Y") + " 07:12"
    return "31.08.2026 12:25"


def showcase_lessons(child_id):
    subjects = text("showcase_subjects")
    changes = SHOWCASE_CHANGES.get(child_id, {})
    offset = 0 if child_id == SCENARIO_CHILDREN[0]["child_id"] else 3
    room = "R%d" % (10 + offset)
    monday = showcase_week_start()
    lessons = []
    for day in range(1, SHOWCASE_DAYS + 1):
        for period in range(1, SHOWCASE_PERIODS + 1):
            index = (day * 2 + period + offset) % len(subjects)
            code, label = subjects[index]
            teacher = text("showcase_teachers")[code]
            kind = changes.get((day, period), "")
            substitute = kind == "changed"
            lessons.append(
                {
                    "date": (monday + timedelta(days=day - 1)).strftime("%d.%m.%Y"),
                    "day_of_week": day,
                    "period": period,
                    "start_time": "%02d:00" % (7 + period),
                    "subject_code": code,
                    "subject_label": label,
                    "color": SHOWCASE_COLORS[index],
                    "teacher_code": "SUB" if substitute else "CLT",
                    "teacher_label": text("showcase_substitute") if substitute else teacher,
                    "is_class_teacher": not substitute,
                    "room": "R%d" % (20 + period) if substitute else room,
                    "change_kind": kind,
                    "changed_fields": ["teacher", "room"] if substitute else [],
                    "previous": {"subject": "", "teacher": teacher if substitute else "", "room": room if substitute else ""},
                }
            )
    return lessons


SHOWCASE_OWN_ENTRY_WEEKDAY = 2
SHOWCASE_CLUB_CHILD = "child-1"
SHOWCASE_APPOINTMENT_CHILD = "child-2"


def showcase_own_entries():
    wide_from = (date.today() - timedelta(days=365)).isoformat()
    wide_until = (date.today() + timedelta(days=365)).isoformat()
    stamp = 1788300000
    base = {"interval": 1, "date": "", "from": "", "until": "", "holidays": True, "child": "", "created_at": stamp, "updated_at": stamp}
    return [
        {
            **base,
            "id": "f1e2d3c4b5a6",
            "type": own_entries.TYPE_PAUSE,
            "name": text("showcase_pause_name"),
            "start": "09:45",
            "duration": 15,
            "repeat": own_entries.REPEAT_DAILY,
            "days": list(own_entries.SCHOOL_DAYS),
            "from": wide_from,
            "until": wide_until,
        },
        {
            **base,
            "id": "a1b2c3d4e5f6",
            "type": own_entries.TYPE_CLUB,
            "name": text("showcase_club_name"),
            "start": "13:00",
            "duration": 60,
            "repeat": own_entries.REPEAT_WEEKLY,
            "days": [SHOWCASE_OWN_ENTRY_WEEKDAY],
            "child": SHOWCASE_CLUB_CHILD,
            "from": wide_from,
            "until": wide_until,
        },
        {
            **base,
            "id": "112233445566",
            "type": own_entries.TYPE_APPOINTMENT,
            "name": text("showcase_appointment_name"),
            "start": "15:00",
            "duration": 45,
            "repeat": own_entries.REPEAT_ONCE,
            "days": [],
            "child": SHOWCASE_APPOINTMENT_CHILD,
            "date": showcase_today().isoformat(),
        },
    ]


def scenario_letters(count):
    return [
        {
            "letter_id": "scenario-%02d" % index,
            "recipient_id": "r1",
            "title": text("letter_scenario") % index,
            "child": SCENARIO_CHILDREN[0]["name"],
            "recipients": text("class_3b"),
            "published": "31.08.2026",
            "unread": True,
            "body_text": "",
            "attachments": [],
        }
        for index in range(count)
    ]


def scenario_posts(count):
    return [
        {
            "id": 1000 + index,
            "title": text("post_scenario_title") % index,
            "text": text("post_scenario_text"),
            "color": "teal",
            "owner": text("owner_office"),
            "folder_id": 1,
            "folder_title": text("folder_council"),
            "column_title": text("column_news"),
            "unread": True,
            "attachments": [],
        }
        for index in range(count)
    ]


MESSENGER_SELF = "@parent-fixture:example.test"
MESSENGER_TEACHER = "@teacher-fixture:example.test"
MESSENGER_OFFICE = "@office-fixture:example.test"
MESSENGER_ROOM_A = "!room-a-fixture:example.test"
MESSENGER_ROOM_B = "!room-b-fixture:example.test"
MESSENGER_ROOM_NEW = "!room-new-fixture:example.test"
MESSENGER_TEACHER_NAME = "Fr. Behrend-Waldenburger"
MESSENGER_NEW_TEACHER = "@teacher-osterkamp-fixture:example.test"
MESSENGER_NEW_TEACHER_NAME = "Hr. Osterkamp"
MESSENGER_NEW_TEACHER_VALUE = "teacher-osterkamp-fixture"
MESSENGER_TEACHER_VALUE = "teacher-behrend-fixture"
MESSENGER_TEACHER_DIRECTORY = [
    {"value": MESSENGER_NEW_TEACHER_VALUE, "label": MESSENGER_NEW_TEACHER_NAME, "extra": "Klasse 4a", "match": "osterkamp"},
    {"value": MESSENGER_TEACHER_VALUE, "label": MESSENGER_TEACHER_NAME, "extra": "Klasse 3b", "match": "behrend"},
]
MESSENGER_OFFICE_NAME = "Schulleitung"
MESSENGER_ROOM_A_NAME = "Klasse 3b - Elternchat mit der Klassenlehrerin und dem Sekretariat"
MESSENGER_BASE_TS = 1788336000000
MESSENGER_MINUTE = 60000
MESSENGER_DAY = 86400000
MESSENGER_OLDER_TOKEN = "fixture-page-2"
MESSENGER_IMAGE_ID = "image-fixture"
MESSENGER_FILE_ID = "file-fixture"
MESSENGER_SERVER = "media.example.test"
MESSENGER_LONG_TEXT = (
    "Guten Tag, der Ausflug am Donnerstag startet um acht Uhr am Schultor und wir sind "
    "gegen sechzehn Uhr zurueck. Bitte gebt festes Schuhwerk, Regenjacke und ausreichend "
    "Verpflegung mit."
)
MESSENGER_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101006000600000ffdb004300ffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffc00011080001000103012200021101031101ffc400"
    "1f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020"
    "4030505040400000178000102030004110512213106134151076122713214328191a1082342b1c11552"
    "d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a5354555657585"
    "95a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8"
    "a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f"
    "3f4f5f6f7f8f9faffda0008010100003f00fbfe8a28a2803fffd9"
)


class FixtureMediaResponse:
    def __init__(self, content, content_type, disposition=""):
        self.content = content
        self.headers = {"content-type": content_type}
        if disposition:
            self.headers["content-disposition"] = disposition


def messenger_text(event_id, sender, offset, body):
    return {
        "event_id": event_id,
        "sender": sender,
        "sent_at": MESSENGER_BASE_TS + offset,
        "kind": "text",
        "body": body,
    }


def messenger_newest_page():
    return [
        messenger_text("$m6", MESSENGER_SELF, 25 * MESSENGER_MINUTE, "Alles klar, ist notiert."),
        {
            "event_id": "$m5",
            "sender": MESSENGER_TEACHER,
            "sent_at": MESSENGER_BASE_TS + 20 * MESSENGER_MINUTE,
            "kind": "image",
            "body": "ausflug-gruppenfoto-am-schultor.jpg",
            "media_url": f"api/messenger/media/{MESSENGER_SERVER}/{MESSENGER_IMAGE_ID}",
            "mimetype": "image/jpeg",
            "size": len(MESSENGER_TINY_JPEG),
        },
        {
            "event_id": "$m4",
            "sender": MESSENGER_OFFICE,
            "sent_at": MESSENGER_BASE_TS + 15 * MESSENGER_MINUTE,
            "kind": "file",
            "body": "elternabend-protokoll-2026-09-02.txt",
            "media_url": f"api/messenger/media/{MESSENGER_SERVER}/{MESSENGER_FILE_ID}",
            "mimetype": "text/plain",
            "size": 42,
        },
        messenger_text(
            "$m3",
            MESSENGER_SELF,
            10 * MESSENGER_MINUTE,
            "Vielen Dank fuer die Information, wir packen alles ein.",
        ),
        messenger_text("$m2", MESSENGER_TEACHER, 5 * MESSENGER_MINUTE, MESSENGER_LONG_TEXT),
        {
            "event_id": "$m1",
            "sender": MESSENGER_OFFICE,
            "sent_at": MESSENGER_BASE_TS,
            "kind": "system",
            "system_kind": "join",
        },
    ]


def messenger_older_page():
    return [
        messenger_text(
            "$m0",
            MESSENGER_TEACHER,
            -MESSENGER_DAY,
            "Guten Tag, hier ist der Elternchat der Klasse 3b.",
        ),
        {
            "event_id": "$m-1",
            "sender": MESSENGER_OFFICE,
            "sent_at": MESSENGER_BASE_TS - MESSENGER_DAY - MESSENGER_MINUTE,
            "kind": "system",
            "system_kind": "invite",
        },
    ]


class FixtureConnection:
    def __init__(self, service, connection_id):
        self.id = connection_id
        self.service = service
        self.store = service.store.connection_store(connection_id)

    def display_name(self):
        return school_display_name(self.id)

    def child_key(self, child_id):
        return child_key(self.id, child_id)

    def modules(self):
        return module_registry()

    def check_connection(self):
        return "outage" if outage_active() else "ok"


class FixtureService:
    def __init__(self, store):
        self.store = store
        self._teacher_room_created = False

    def connection(self, connection_id):
        return FixtureConnection(self, connection_id)

    def connections(self, include_pending=False):
        return [self.connection(connection_id) for connection_id in school_ids()]

    def known_connection(self, connection_id):
        if connection_id not in school_ids():
            raise DataError("unknown connection", message_key="api.connection.unknown")
        return self.connection(connection_id)

    def first_connection(self):
        return self.connection(school_ids()[0])

    def summaries(self, with_status=False):
        rows = []
        for connection_id in school_ids():
            children = self._raw_children(connection_id)
            row = {
                "id": connection_id,
                "name": school_display_name(connection_id),
                "school_name": school_display_name(connection_id),
                "label": "",
                "short_name": SCHOOL_TWO_SHORT if connection_id == SCHOOL_TWO else SCHOOL_ONE_SHORT,
                "school_url": SCHOOL_TWO_URL if connection_id == SCHOOL_TWO else SCHOOL_ONE_URL,
                "host": "school-two.example" if connection_id == SCHOOL_TWO else "school-one.example",
                "setup_complete": True,
                "username": "parent.two" if connection_id == SCHOOL_TWO else "parent.one",
                "children": [
                    dict(tag(connection_id, child), key=child_key(connection_id, child["child_id"])) for child in children
                ],
            }
            if with_status:
                row["status"] = "outage" if outage_active() else "ok"
            rows.append(row)
        return rows

    def health_overview(self):
        rows = self.summaries(with_status=True)
        for row in rows:
            row["stale"] = False
        return ("outage" if outage_active() else "ok"), rows

    def modules_of(self, connection_id):
        self.known_connection(connection_id)
        return module_registry()

    def messenger_rooms(self):
        raise_when_unreachable()
        if module_emptied(modules.MESSENGER) or block_emptied("chat"):
            return {"rooms": [], "self_user_id": MESSENGER_SELF, "unavailable": []}
        rooms = [
            {
                "room_id": MESSENGER_ROOM_A,
                "name": MESSENGER_ROOM_A_NAME,
                "members": [MESSENGER_OFFICE_NAME, MESSENGER_TEACHER_NAME],
                "member_names": {
                    MESSENGER_TEACHER: MESSENGER_TEACHER_NAME,
                    MESSENGER_OFFICE: MESSENGER_OFFICE_NAME,
                },
                "last_message": "Alles klar, ist notiert.",
                "last_message_at": MESSENGER_BASE_TS + 25 * MESSENGER_MINUTE,
                "unread_count": 3,
            },
            {
                "room_id": MESSENGER_ROOM_B,
                "name": MESSENGER_TEACHER_NAME,
                "members": [MESSENGER_TEACHER_NAME],
                "member_names": {MESSENGER_TEACHER: MESSENGER_TEACHER_NAME},
                "last_message": MESSENGER_LONG_TEXT,
                "last_message_at": MESSENGER_BASE_TS - MESSENGER_DAY,
                "unread_count": 0,
            },
        ]
        if self._teacher_room_created and room_writes_allowed():
            rooms.append(
                {
                    "room_id": MESSENGER_ROOM_NEW,
                    "name": MESSENGER_NEW_TEACHER_NAME,
                    "members": [MESSENGER_NEW_TEACHER_NAME],
                    "member_names": {MESSENGER_NEW_TEACHER: MESSENGER_NEW_TEACHER_NAME},
                    "last_message": "",
                    "last_message_at": MESSENGER_BASE_TS,
                    "unread_count": 0,
                }
            )
        rooms = [dict(tag(SCHOOL_ONE, room), self_user_id=MESSENGER_SELF) for room in rooms]
        self_user_ids = {SCHOOL_ONE: MESSENGER_SELF}
        if SCHOOL_TWO in school_ids():
            rooms.append(
                dict(
                    tag(
                        SCHOOL_TWO,
                        {
                            "room_id": SCHOOL_TWO_ROOM,
                            "name": SCHOOL_TWO_ROOM_NAME,
                            "members": [SCHOOL_TWO_ROOM_NAME],
                            "member_names": {},
                            "last_message": "Bis Montag.",
                            "last_message_at": MESSENGER_BASE_TS - 2 * MESSENGER_DAY,
                            "unread_count": 0,
                        },
                    ),
                    self_user_id=MESSENGER_SELF,
                )
            )
            self_user_ids[SCHOOL_TWO] = MESSENGER_SELF
        return {
            "self_user_id": MESSENGER_SELF,
            "self_user_ids": self_user_ids,
            "rooms": rooms,
            "can_write_to_teacher": True,
            "unavailable": [],
        }

    def messenger_room_messages(self, connection_id, room_id, before=None):
        if room_id == MESSENGER_ROOM_NEW:
            return {"messages": [], "before": "", "self_user_id": MESSENGER_SELF}
        if before == MESSENGER_OLDER_TOKEN:
            return {
                "messages": messenger_older_page(),
                "before": "",
                "self_user_id": MESSENGER_SELF,
            }
        if room_id == MESSENGER_ROOM_B:
            return {"messages": [], "before": "", "self_user_id": MESSENGER_SELF}
        return {
            "messages": messenger_newest_page(),
            "before": MESSENGER_OLDER_TOKEN,
            "self_user_id": MESSENGER_SELF,
        }

    def messenger_send(self, connection_id, room_id, text):
        if not str(text or "").strip():
            return {"ok": False, "message_key": "api.messenger.send.empty"}
        return {"ok": True, "message_key": "api.messenger.send.ok", "event_id": "$fixture-sent"}

    def messenger_mark_read(self, connection_id, room_id, event_id):
        if not str(room_id or "").strip() or not str(event_id or "").strip():
            return messages.result(False, READ_FAILED_KEY)
        return messages.result(True, READ_OK_KEY)

    def messenger_teacher_search(self, connection_id, query):
        query = str(query or "").strip()
        if not query:
            return {"teachers": [], "allowed": True}
        needle = query.lower()
        hits = [
            {"value": entry["value"], "label": entry["label"], "extra": entry["extra"]}
            for entry in MESSENGER_TEACHER_DIRECTORY
            if entry["match"] in needle
        ]
        return {"teachers": hits, "allowed": True}

    def messenger_teacher_room_children(self, connection_id=None):
        return {
            "allowed": True,
            "children": [
                {"id": child["child_id"], "name": child["name"]} for child in SCENARIO_CHILDREN
            ],
        }

    def messenger_create_teacher_room(self, connection_id, teacher, child_ids, add_other_parents):
        teacher = str(teacher or "").strip()
        wanted = [str(value or "").strip() for value in (child_ids or [])]
        wanted = [value for value in wanted if value]
        if not teacher or not wanted:
            return messages.result(False, ROOM_INCOMPLETE_KEY)
        if teacher == MESSENGER_TEACHER_VALUE:
            return messages.result(True, ROOM_OK_KEY, room_id=MESSENGER_ROOM_B, joined=True)
        self._teacher_room_created = True
        return messages.result(True, ROOM_OK_KEY, room_id=MESSENGER_ROOM_NEW, joined=True)

    def messenger_media(self, connection_id, server_name, media_id):
        if media_id == MESSENGER_IMAGE_ID:
            return FixtureMediaResponse(MESSENGER_TINY_JPEG, "image/jpeg")
        return FixtureMediaResponse(
            b"Protokoll des Elternabends.\n",
            "text/plain",
            'inline; filename="elternabend-protokoll-2026-09-02.txt"',
        )

    def is_configured(self):
        return True

    def check_connection(self):
        return "outage" if outage_active() else "ok"

    def me(self, connection_id=None):
        raise_when_unreachable()
        return {
            "forename": "Alexa",
            "displayname": "Alexa Musterkind-Langenscheidt",
            "id": "f8e2c1a0b3d4457e9a6f0c2d1b3a4f5e",
            "surname": "Musterkind-Langenscheidt",
            "username": "alexa.musterkind-langenscheidt",
            "email": "alexa.musterkind-langenscheidt@elternvertretung.grundschule-am-stadtpark.example",
            "external_id": "ext-f8e2c1a0-b3d4-457e-9a6f-0c2d1b3a4f5e",
            "is_active": True,
            "is_activated": True,
            "needs_re_registration": False,
            "in_preparation": False,
            "is_web_user": True,
            "is_guardian": True,
            "is_main_teacher": False,
            "roles": ["guardian", "parent-council"],
            "is_notified_by_email": True,
            "is_receiver_of_serial_print": False,
            "is_newsletter_receiver": True,
            "has_active_devices": True,
            "has_2nd_factor_active": True,
            "has_restricted_access_pin": False,
        }

    def _raw_children(self, connection_id):
        if connection_id == SCHOOL_TWO:
            return [dict(child) for child in SCHOOL_TWO_CHILDREN]
        scenario = current_scenario()
        if scenario:
            return [dict(child) for child in SCENARIO_CHILDREN[: scenario["children"]]]
        return [{"child_id": "child-1", "name": "Mia Musterkind", "class_name": "3b"}]

    def children(self, connection_id=None):
        listed = []
        for school in ([connection_id] if connection_id else school_ids()):
            for child in self._raw_children(school):
                listed.append(dict(tag(school, child), key=child_key(school, child["child_id"])))
        if connection_id:
            return listed
        return sorted(listed, key=child_sort_key)

    def modules(self):
        return module_registry()

    def recheck_modules(self, connection_id=None):
        return messages.result(True, "api.modules.rechecked", modules=module_registry())

    def _course_config(self, connection_id):
        return dict(self.store.connection_store(connection_id).load_config(), course_filters=course_filters(connection_id))

    def timetable_courses(self, key):
        connection_id, child_id = split_key(key)
        if connection_id not in school_ids():
            raise DataError("unknown child", message_key="api.child.unknown")
        config = self._course_config(connection_id)
        lessons = course_week_lessons(0) + course_week_lessons(1) if courses_active() else []
        return courses.catalogue(lessons, courses.filter_of(config, child_id), config)

    def save_course_filter(self, key, chosen, known, confirmed_empty=False):
        connection_id, child_id = split_key(key)
        if connection_id not in school_ids() or child_id not in {child["child_id"] for child in self._raw_children(connection_id)}:
            raise DataError("unknown child", message_key="api.child.unknown")
        value = None if chosen is None else {"chosen": chosen, "known": known}
        if value is not None and confirmed_empty:
            value[courses.CONFIRMED_EMPTY_KEY] = True
        merged = courses.with_filter({"course_filters": COURSE_FILTER_STATE.get(connection_id) or {}}, child_id, value)
        COURSE_FILTER_STATE[connection_id] = merged["course_filters"]
        stored = courses.filter_of(merged, child_id)
        return messages.result(True, "api.courses.saved" if stored else "api.courses.reset")

    def timetable(self, key, week_offset=0):
        connection_id, child_id = split_key(key)
        if connection_id not in school_ids():
            raise DataError("unknown child", message_key="api.child.unknown")
        raise_when_unreachable()
        if timetable_source_mode() and connection_id == SCHOOL_ONE and child_id == "child-1":
            return timetable_source_school(timetable_source_mode()).timetable(child_id, week_offset=week_offset)
        if courses_active():
            return courses.apply(course_week(week_offset), courses.filter_of(self._course_config(connection_id), child_id))
        if module_emptied(modules.TIMETABLE):
            return {
                "last_updated": timetable_stamp(),
                "start_date": "31.08.2026",
                "end_date": "06.09.2026",
                "lessons": [],
                "changes": [],
                "period_times": {},
                "change_count": 0,
                "week_offset": week_offset,
            }
        scenario = current_scenario()
        if scenario:
            lessons = (
                showcase_lessons(child_id)
                if scenario.get("showcase")
                else scenario_lessons(child_id, scenario["periods"], week_offset)
            )
            early_times = block_emptied("next_lesson") and not scenario.get("showcase")
            period_times = dict(
                (str(period), "00:%02d" % period if early_times else "%02d:00" % (7 + period))
                for period in range(1, scenario["periods"] + 1)
            )
            return {
                "last_updated": timetable_stamp(),
                "start_date": "31.08.2026",
                "end_date": "06.09.2026",
                "lessons": lessons,
                "changes": [],
                "period_times": period_times,
                "change_count": 1,
                "week_offset": week_offset,
            }
        if long_subjects_active():
            return {
                "last_updated": timetable_stamp(),
                "start_date": "31.08.2026",
                "end_date": "06.09.2026",
                "lessons": long_subject_lessons(),
                "changes": [],
                "period_times": {str(period): f"{7 + period}:00" for period in range(1, 5)},
                "change_count": 0,
                "week_offset": week_offset,
            }
        lessons = []
        monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7 * week_offset)
        for day in SCENARIO_WEEKDAYS:
            for period in range(1, 7):
                if (day + period) % 4 == 0:
                    continue
                lessons.append(
                    {
                        "date": (monday + timedelta(days=day - 1)).strftime("%d.%m.%Y"),
                        "day_of_week": day,
                        "period": period,
                        "start_time": f"{7 + period}:00",
                        "subject_code": "NWI" if period == 3 else "D",
                        "subject_label": text("subject_long") if period == 3 else text("subject_german"),
                        "color": "teal",
                        "teacher_code": "BEH",
                        "teacher_label": text("teacher"),
                        "is_class_teacher": True,
                        "room": "R1",
                        "change_kind": "" if block_emptied("changes") else ("cancelled" if period == 5 and day == 1 else ""),
                        "changed_fields": [],
                        "previous": {"subject": "", "teacher": "", "room": ""},
                    }
                )
        lessons.append(
            {
                "date": monday.strftime("%d.%m.%Y"),
                "day_of_week": 1,
                "period": 1,
                "start_time": "8:00",
                "subject_code": "ENG",
                "subject_label": text("subject_english_double"),
                "color": "purple",
                "teacher_code": "SCH",
                "teacher_label": text("teacher_substitute"),
                "is_class_teacher": False,
                "room": "R2",
                "change_kind": "" if block_emptied("changes") else "changed",
                "changed_fields": [] if block_emptied("changes") else ["room", "teacher"],
                "previous": {"subject": "", "teacher": "", "room": ""} if block_emptied("changes") else {"subject": "", "teacher": text("teacher"), "room": "R1"},
            }
        )
        return {
            "last_updated": timetable_stamp(),
            "start_date": "31.08.2026",
            "end_date": "06.09.2026",
            "lessons": lessons,
            "changes": [],
            "period_times": {str(period): f"{7 + period}:00" for period in range(1, 7)},
            "change_count": 1,
            "week_offset": week_offset,
        }

    def pinboard(self):
        raise_when_unreachable()
        if module_emptied(modules.PINBOARD) or block_emptied("noticeboard"):
            return {"folders": [], "feed": [], "unavailable": []}
        payload = self._pinboard()
        folders = [dict(tag(SCHOOL_ONE, folder), key=f"{SCHOOL_ONE}:{folder['id']}") for folder in payload["folders"]]
        feed = [
            dict(tag(SCHOOL_ONE, entry), key=f"{SCHOOL_ONE}:{entry['id']}", folder_key=f"{SCHOOL_ONE}:{entry['folder_id']}")
            for entry in payload["feed"]
        ]
        if SCHOOL_TWO in school_ids() and not list_scenario():
            folder = school_two_folder()
            post = school_two_post()
            folders.append(dict(tag(SCHOOL_TWO, folder), key=f"{SCHOOL_TWO}:{folder['id']}"))
            feed.append(
                dict(
                    tag(SCHOOL_TWO, post),
                    key=f"{SCHOOL_TWO}:{post['id']}",
                    folder_key=f"{SCHOOL_TWO}:{post['folder_id']}",
                )
            )
        return {"folders": folders, "feed": feed, "unavailable": []}

    def _pinboard(self):
        scenario = list_scenario()
        if scenario:
            return {
                "folders": [
                    {
                        "id": 1,
                        "title": text("folder_council"),
                        "unread": scenario["posts"],
                        "last_post_id": 1000,
                        "columns": [],
                        "attachments": [],
                        "author": text("owner_office"),
                        "students_can_create_tiles": False,
                    }
                ],
                "feed": scenario_posts(scenario["posts"]),
            }
        folders = [
            {
                "id": 1,
                "title": text("folder_council"),
                "unread": 1,
                "last_post_id": 3,
                "columns": [],
                "attachments": [],
                "author": text("owner_office"),
                "students_can_create_tiles": False,
            },
            {
                "id": 2,
                "title": text("folder_class"),
                "unread": 0,
                "last_post_id": 1,
                "columns": [],
                "attachments": [],
                "author": text("owner_class_teacher"),
                "students_can_create_tiles": False,
            },
        ]
        feed = [
            {
                "id": 3,
                "title": text("post_trip_title"),
                "text": text("post_trip_text"),
                "color": "teal",
                "owner": text("owner_office"),
                "folder_id": 1,
                "folder_title": text("folder_council"),
                "column_title": text("column_news"),
                "unread": True,
                "attachments": [],
            },
            {
                "id": 2,
                "title": text("post_evening_title"),
                "text": text("post_evening_text"),
                "color": "purple",
                "owner": text("owner_class_teacher"),
                "folder_id": 2,
                "folder_title": text("folder_class"),
                "column_title": text("column_dates"),
                "unread": False,
                "attachments": [],
            },
            {
                "id": 1,
                "title": text("post_welcome_title"),
                "text": text("post_welcome_text"),
                "color": "brown",
                "owner": text("owner_office"),
                "folder_id": 1,
                "folder_title": text("folder_council"),
                "column_title": text("column_news"),
                "unread": False,
                "attachments": [],
            },
        ]
        return {"folders": folders, "feed": feed}

    def mark_pinboard_seen(self, keys=None, mark_all=False, unseen=False):
        return {"seen": len(keys or [])}

    def letters(self, tab="current"):
        raise_when_unreachable()
        if module_emptied(modules.LETTERS):
            return {"letters": [], "unavailable": []}
        letters = [
            dict(tag(SCHOOL_ONE, letter), key=f"{SCHOOL_ONE}:{letter['letter_id']}:{letter['recipient_id']}")
            for letter in self._letters(tab)
        ]
        if SCHOOL_TWO in school_ids() and tab == "current" and not list_scenario():
            letters.extend(
                dict(tag(SCHOOL_TWO, letter), key=f"{SCHOOL_TWO}:{letter['letter_id']}:{letter['recipient_id']}")
                for letter in school_two_letters()
            )
        return {"letters": letters, "unavailable": []}

    def _letters(self, tab="current"):
        scenario = list_scenario()
        if scenario:
            return scenario_letters(scenario["letters"] if tab == "current" else 0)
        letters = [
            {
                "letter_id": CONFIRM_LETTER_ID,
                "recipient_id": "r1",
                "title": text("letter_start"),
                "child": "Mia Musterkind",
                "recipients": text("class_3b"),
                "published": "31.08.2026",
                "unread": tab == "current",
                "body_text": "",
                "attachments": [],
                "confirmation": self._confirmation_state(),
            },
            {
                "letter_id": "l2",
                "recipient_id": "r1",
                "title": text("letter_conference"),
                "child": "Mia Musterkind",
                "recipients": text("class_3b"),
                "published": "20.08.2026",
                "unread": False,
                "body_text": "",
                "attachments": [],
                "confirmation": {
                    "type": "confirmation",
                    "open": True,
                    "done": False,
                    "sendable": False,
                    "confirmed_at": "",
                },
            },
            {
                "letter_id": REPLY_LETTER_ID,
                "recipient_id": CONFIRMED_RECIPIENT_ID,
                "title": text("letter_reply"),
                "child": "Mia Musterkind",
                "recipients": text("class_3b"),
                "published": "12.08.2026",
                "unread": False,
                "body_text": "",
                "attachments": [],
                "confirmation": done_confirmation(),
            },
            {
                "letter_id": CONFIRMED_LETTER_ID,
                "recipient_id": CONFIRMED_RECIPIENT_ID,
                "title": text("letter_confirmed"),
                "child": "Mia Musterkind",
                "recipients": text("class_3b"),
                "published": "05.08.2026",
                "unread": False,
                "body_text": "",
                "attachments": [],
                "confirmation": done_confirmation(),
            },
        ]
        return letters

    def _confirmation_state(self):
        return {"type": "seen", "open": True, "done": False, "sendable": True, "confirmed_at": ""}

    def mark_letters_read(self, keys=None, mark_all=False):
        return {"read": len(keys or [])}

    def confirm_letter(self, connection_id, letter_id, recipient_id, text=None):
        return {
            "ok": True,
            "message_key": "api.letters.confirm.ok",
            "confirmed_at": CONFIRMED_AT,
        }

    def reply_to_letter(self, connection_id, letter_id, recipient_id, text, request_id, confirmed=False):
        if letter_id not in LETTER_PAGES:
            return messages.result(False, "api.letters.reply.unavailable")
        return FIXTURE_LETTERS.reply_to_letter(letter_id, recipient_id, text, request_id, confirmed)

    def letter_detail(self, connection_id, letter_id, recipient_id):
        if letter_id in LETTER_PAGES:
            return {
                "title": "Letter",
                "body_html": "<p>Inhalt</p>",
                "attachments": [],
                "archive_url_present": True,
                "confirmation": done_confirmation(),
                "reply": letter_reply_offer(letter_id, recipient_id),
            }
        return {
            "title": "Letter",
            "body_html": "<p>Inhalt</p>",
            "attachments": [],
            "archive_url_present": True,
            "confirmation": self._confirmation_state()
            if letter_id == CONFIRM_LETTER_ID
            else {
                "type": "confirmation",
                "open": True,
                "done": False,
                "sendable": False,
                "confirmed_at": "",
            },
        }

    def archive_letter(self, connection_id, letter_id, recipient_id):
        return True

    def conferences(self):
        raise_when_unreachable()
        if module_emptied(modules.CONFERENCES):
            return {"empty": True, "items": [], "unavailable": []}
        today = fixture_today()
        first = (today + timedelta(days=CONFERENCE_FIRST_OFFSET)).strftime("%d.%m.%Y")
        second = (today + timedelta(days=CONFERENCE_SECOND_OFFSET)).strftime("%d.%m.%Y")
        return {
            "empty": False,
            "items": [
                tag(SCHOOL_ONE, {"cells": [text("conference_class"), f"{first}, 16:00"], "links": []}),
                tag(SCHOOL_ONE, {"cells": [text("conference_individual"), f"{second}, 17:30"], "links": []}),
            ],
            "unavailable": [],
        }

    def absences_overview(self, connection_id=None):
        raise_when_unreachable()
        today = fixture_today()
        week_leading_entry = [
            {
                "id": "d4e5f6a7b8c9401234e5f6a7b8c9d0e1",
                "kind": "sick",
                "label_key": "absence.type.sick.label",
                "student_id": "",
                "status": "accepted",
                "from_date": today.isoformat(),
                "till_date": today.isoformat(),
                "comment": "",
                "deletable": False,
                "attachments": [],
                "technical": {"id": "d4e5f6a7b8c9401234e5f6a7b8c9d0e1", "created_at": 1787990400},
            }
        ] if block_emptied("week") else []
        return {
            "connection_id": connection_id or SCHOOL_ONE,
            "school": school_display_name(connection_id or SCHOOL_ONE),
            "children": [{"id": "child-1", "name": "Mia Musterkind", "class_name": "3b"}],
            "types": ["sick", "leave", "deregister", "daycare"],
            "deregister_options": ["bus", "lunch", "kindergarten"],
            "periods": [{"number": index, "name": text("period_name") % index} for index in range(1, 7)],
            "period_labels": [
                {"number": index, "label": text("period_label") % (index, 6 + index, 6 + index)} for index in range(1, 7)
            ],
            "rules": ABSENCE_RULES,
            "day_options": {
                "from": [
                    {"value": today.isoformat(), "label_key": "absence.day.today"},
                    {"value": (today + timedelta(days=1)).isoformat(), "label_key": "absence.day.tomorrow"},
                ],
                "till": [
                    {"value": (today + timedelta(days=offset)).isoformat(), "label": "", "label_key": ""}
                    for offset in range(0, 6)
                ],
            },
            "leave_min_days": 3,
            "notes": [],
            "phones": [],
            "entries": [] if module_emptied(modules.ABSENCES) else [
                {
                    "id": "b2d3c4e5f6a7481902b3c4d5e6f7a819",
                    "kind": "leave",
                    "label_key": "absence.type.leave.label",
                    "student_id": "child-1",
                    "status": "open",
                    "from_date": (today + timedelta(days=ABSENCE_AHEAD_OFFSET)).isoformat(),
                    "till_date": (today + timedelta(days=ABSENCE_AHEAD_OFFSET + 1)).isoformat(),
                    "comment": "",
                    "deletable": True,
                    "attachments": [],
                    "technical": {"id": "b2d3c4e5f6a7481902b3c4d5e6f7a819", "created_at": 1787990400},
                },
                {
                    "id": "a1c2b3d4e5f6470891a2b3c4d5e6f708",
                    "kind": "sick",
                    "label_key": "absence.type.sick.label",
                    "student_id": "child-1",
                    "status": "accepted",
                    "from_date": "2026-08-25",
                    "till_date": "2026-08-26",
                    "comment": text("absence_comment"),
                    "deletable": False,
                    "attachments": [
                        {
                            "filename": text("absence_attachment"),
                            "url": "api/absences/attachment?id=a1c2b3d4e5f6470891a2b3c4d5e6f708",
                        }
                    ],
                    "technical": {
                        "id": "a1c2b3d4e5f6470891a2b3c4d5e6f708",
                        "created_at": 1787990400,
                    },
                },
            ] + week_leading_entry,
        }

    def report_absence(self, connection_id, payload, attachments=None):
        return {"ok": True, "message": text("absence_submitted")}


class FixtureHolidays:
    def _monday(self):
        today = date.today()
        return today - timedelta(days=today.weekday())

    def _periods(self):
        if module_emptied(modules.TIMETABLE) or block_emptied("holidays"):
            return []
        base = self._monday()
        full_start = base + timedelta(days=7 * HOLIDAY_FULL_WEEK_OFFSET)
        single = base + timedelta(
            days=7 * HOLIDAY_SINGLE_DAY_OFFSET + HOLIDAY_SINGLE_DAY_WEEKDAY
        )
        return [
            {
                "id": "fixture-autumn",
                "kind": "school",
                "type": "autumn",
                "name": "Herbstferien",
                "name_key": "holidays.period.autumn",
                "start": full_start.isoformat(),
                "end": (full_start + timedelta(days=6)).isoformat(),
                "groups": [],
                "exception": False,
            },
            {
                "id": "fixture-unity",
                "kind": "public",
                "type": "",
                "name": LONG_HOLIDAY_NAME,
                "name_key": "",
                "start": single.isoformat(),
                "end": single.isoformat(),
                "groups": [],
                "exception": False,
            },
        ]

    def region(self, config=None):
        return HOLIDAY_REGION

    def _day_map(self, window_start, window_end, periods):
        days = {}
        day = window_start
        while day <= window_end:
            iso = day.isoformat()
            hit = next((entry for entry in periods if entry["start"] <= iso <= entry["end"]), None)
            days[iso] = {
                "free": hit is not None,
                "overrides_lessons": hit is not None,
                "weekend": day.weekday() >= SCHOOL_DAYS,
                "kind": hit["kind"] if hit else "",
                "type": hit["type"] if hit else "",
                "name": hit["name"] if hit else "",
                "name_key": hit["name_key"] if hit else "",
                "period_id": hit["id"] if hit else "",
            }
            day += timedelta(days=1)
        return days

    def _week_rows(self, window_start, window_end, days, periods):
        rows = []
        monday = window_start
        while monday <= window_end:
            school = [monday + timedelta(days=index) for index in range(SCHOOL_DAYS)]
            free = [entry for entry in school if days[entry.isoformat()]["free"]]
            hits = []
            for entry in school:
                for period in periods:
                    if period["start"] <= entry.isoformat() <= period["end"] and period not in hits:
                        hits.append(period)
            if len(free) == SCHOOL_DAYS:
                coverage = "full"
                label_key = "holidays.week.full"
            elif free:
                coverage = "partial"
                label_key = "holidays.week.partial"
            else:
                coverage = "none"
                label_key = ""
            calendar = monday.isocalendar()
            rows.append(
                {
                    "week": calendar[1],
                    "iso_year": calendar[0],
                    "start": monday.isoformat(),
                    "end": (monday + timedelta(days=6)).isoformat(),
                    "coverage": coverage,
                    "label_key": label_key,
                    "school_days": SCHOOL_DAYS,
                    "free_school_days": len(free),
                    "override_school_days": len(free),
                    "overrides_lessons": len(free) == SCHOOL_DAYS,
                    "primary": hits[0] if hits else None,
                    "periods": hits,
                }
            )
            monday += timedelta(days=7)
        return rows

    def range_info(self, start, end, config=None):
        if end < start:
            start, end = end, start
        window_start = start - timedelta(days=start.weekday())
        window_end = end + timedelta(days=6 - end.weekday())
        periods = self._periods()
        days = self._day_map(window_start, window_end, periods)
        return {
            "region": HOLIDAY_REGION,
            "status": "ok",
            "stale": False,
            "from": window_start.isoformat(),
            "to": window_end.isoformat(),
            "requested_from": start.isoformat(),
            "requested_to": end.isoformat(),
            "groups": [],
            "days": days,
            "weeks": self._week_rows(window_start, window_end, days, periods),
            "periods": [
                period
                for period in periods
                if period["start"] <= window_end.isoformat()
                and period["end"] >= window_start.isoformat()
            ],
        }


CHILD_ID = f"{SCHOOL_ONE}:child-1"
CHILD_NAME = "Mia Musterkind"
CHILD_CLASS = "3b"
SUBSCRIPTION_LABEL = "3b"
SUBSCRIPTION_COLOR = "#135859"
SUBSCRIPTION_TOKEN = "e2e-fixture-token-abcdefghijklmnopqrstuvwxyz012345"


class FixtureScopedConfig:
    def __init__(self, entry):
        self._entry = dict(entry)

    def load_config(self):
        return dict(self._entry)


SUBSCRIPTION_STATE = {}


def subscription_state():
    return SUBSCRIPTION_STATE.setdefault(matrix_key(), {"subscriptions": []})


class FixtureSubscriptionStore:
    def __init__(self, config):
        self._config = config

    def load_config(self):
        return self._config

    def connection_store(self, connection_id):
        entry = next((item for item in self._config.get("connections") or [] if item["id"] == connection_id), {})
        return FixtureScopedConfig(entry)

    def load_calendar_subscriptions(self):
        return subscription_state()

    def save_calendar_subscriptions(self, data):
        SUBSCRIPTION_STATE[matrix_key()] = data


def make_subscription_registry(config):
    registry = subscriptions.SubscriptionRegistry(FixtureSubscriptionStore(config))
    registry.create(
        CHILD_ID,
        [subscriptions.COMPONENT_TIMETABLE, subscriptions.COMPONENT_SCHOOL_HOLIDAYS],
        SUBSCRIPTION_LABEL,
        SUBSCRIPTION_COLOR,
    )
    entry = registry.store.load_calendar_subscriptions()["subscriptions"][0]
    entry["token"] = SUBSCRIPTION_TOKEN
    return registry


def seed_config(store):
    period_times = dict((str(period), "%02d:00" % (7 + period)) for period in range(1, 9))
    period_grid = {"iserv": {str(period): {"start": "%02d:00" % (7 + period), "end": "%02d:45" % (7 + period)} for period in range(1, 9)}}
    store.add_connection(
        SCHOOL_ONE_URL,
        connection_id=SCHOOL_ONE,
        setup_complete=True,
        school_name=SCHOOL_ONE_NAME,
        short_name=SCHOOL_ONE_SHORT,
        subjects={
            "NWI": {"label": LONG_SUBJECT, "color": "teal"},
            "D": {"label": "Deutsch", "color": ""},
        },
        holiday_region=HOLIDAY_REGION,
        period_times=period_times,
        period_grid=period_grid,
        children=[{"child_id": "child-1", "name": CHILD_NAME, "class_name": CHILD_CLASS}],
    )
    store.add_connection(
        SCHOOL_TWO_URL,
        connection_id=SCHOOL_TWO,
        setup_complete=True,
        school_name=SCHOOL_TWO_NAME,
        short_name=SCHOOL_TWO_SHORT,
        subjects={"D": {"label": "Deutsch", "color": ""}},
        holiday_region=HOLIDAY_REGION,
        period_times=period_times,
        period_grid=period_grid,
        children=list(SCHOOL_TWO_CHILDREN),
    )
    return store.load_config()


def reports_kept():
    return REPORTS.get("") == "1"


def layout_slot():
    name = LAYOUT.get("")
    return LAYOUT_STATE.get(name) if name else None


class FixtureStore(Store):
    def load_config(self):
        config = super().load_config()
        wanted = school_ids()
        scenario = current_scenario()
        showcase = bool(scenario and scenario.get("showcase"))
        config["connections"] = [
            dict(
                entry,
                course_filters=course_filters(entry["id"]),
                **({"own_entries": showcase_own_entries()} if showcase and entry["id"] == SCHOOL_ONE else {}),
            )
            for entry in config["connections"]
            if entry["id"] in wanted
        ]
        if not reports_kept():
            config["reported_modules"] = []
            config["modules_card_hidden"] = {}
        kept = layout_slot()
        for key in LAYOUT_KEYS:
            config[key] = kept[key] if kept else None
        config.update(normalize_layout(config))
        return config

    def save_config(self, config):
        name = LAYOUT.get("")
        if name:
            LAYOUT_STATE[name] = {key: config.get(key) for key in LAYOUT_KEYS}
        stored = dict(config)
        for key in LAYOUT_KEYS:
            stored.pop(key, None)
        stored["connections"] = self._merged_connections(stored.get("connections", []))
        super().save_config(stored)

    def _merged_connections(self, visible):
        wanted = school_ids()
        disk = super().load_config()["connections"]
        by_id = {entry["id"]: entry for entry in disk if entry["id"] not in wanted}
        by_id.update({entry["id"]: entry for entry in visible if isinstance(entry, dict) and entry.get("id")})
        order = [entry["id"] for entry in disk if entry["id"] in by_id]
        order.extend(identifier for identifier in by_id if identifier not in order)
        return [by_id[identifier] for identifier in order]

    def load_integration_state(self):
        state = super().load_integration_state()
        if not outage_active():
            return state
        schools = dict(state.get(INTEGRATION_SCHOOLS_KEY) or {})
        slot = dict(schools.get(SCHOOL_ONE) or {})
        slot.update(
            {
                "last_poll": OUTAGE_SINCE_EPOCH,
                "last_poll_ok": False,
                "last_error": "outage",
                "last_success": OUTAGE_LAST_SUCCESS_EPOCH,
                "outage_since": OUTAGE_SINCE_EPOCH,
                "outage_count": 1,
                "outage_reason": "status:503",
            }
        )
        schools[SCHOOL_ONE] = slot
        state[INTEGRATION_SCHOOLS_KEY] = schools
        return state


WIZARD_STEP_DONE = {"step": "done", "attempts": 0, "additional": True}
WIZARD_STEP_URL = {"step": "url", "attempts": 0, "additional": True}


class FixtureWizard:
    def __init__(self):
        self.state = dict(WIZARD_STEP_DONE)

    def status(self):
        return dict(self.state)

    def start_new(self):
        self.state = dict(WIZARD_STEP_URL)
        return dict(self.state)

    def cancel(self):
        self.state = dict(WIZARD_STEP_DONE)
        return dict(self.state)

    def reset(self, connection_id=None):
        return self.start_new()

    def back(self):
        return dict(self.state)

    def set_url(self, raw):
        self.state = dict(WIZARD_STEP_URL, error={"code": "url_unreachable", "message_key": "api.wizard.urlUnreachable"})
        return dict(self.state)

    def set_login(self, username, password):
        return dict(self.state)

    def connect(self, code):
        return dict(self.state)

    def select_child(self, child_id, name, class_name):
        return dict(self.state)

    def skip_child(self):
        return dict(self.state)


LIVE_WIZARD_DIR = E2E_DATA_DIR / "wizard-live"
LIVE_PASSWORD = "right-password"
LIVE_OUTCOMES = {
    "unknown-account": "unknown_account",
    "default-password": "default_password_blocked",
    "forced-2fa": "twofactor_required_setup",
}


class LiveWizardProber:
    def probe_url(self, base):
        return {"ok": True, "host": base}

    def verify_login(self, url, username, password):
        if password == LIVE_PASSWORD:
            return "no_2fa"
        return LIVE_OUTCOMES.get(password, "bad_credentials")

    def begin_2fa(self, url, username, password, code, name=""):
        return {"status": "twofactor_required_setup"}


class LiveWizardClock:
    def __init__(self):
        self.offset = 0

    def __call__(self):
        import time

        return time.time() + self.offset


def wizard_live_active():
    return WIZARD_MODE.get("").startswith("live")


def wizard_live_key():
    return WIZARD_MODE.get("") if wizard_live_active() else ""


class LiveWizardSwitch:
    def __init__(self, stub):
        self.stub = stub
        self._instances = {}

    def _entry(self, key):
        entry = self._instances.get(key)
        if entry is None:
            entry = {"clock": LiveWizardClock(), "wizard": None}
            self._instances[key] = entry
        return entry

    def restart(self):
        key = wizard_live_key()
        entry = self._entry(key)
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", key) if key else "default"
        directory = LIVE_WIZARD_DIR / safe
        shutil.rmtree(directory, ignore_errors=True)
        entry["clock"].offset = 0
        entry["wizard"] = Wizard(Store(directory), LiveWizardProber(), now=entry["clock"])

    @property
    def clock(self):
        return self._entry(wizard_live_key())["clock"]

    def __getattr__(self, name):
        if not wizard_live_active():
            return getattr(self.stub, name)
        key = wizard_live_key()
        entry = self._entry(key)
        if entry["wizard"] is None:
            self.restart()
            entry = self._entry(key)
        return getattr(entry["wizard"], name)


MATRIX_COOKIE = "e2e_matrix"
MATRIX = contextvars.ContextVar("e2e_matrix", default="")
MATRIX_HOLIDAY_SHIFT = contextvars.ContextVar("e2e_matrix_holiday_shift", default=0)
MATRIX_CONFIG_NAME = "config-matrix.json"
MATRIX_FEED_PREFIX = "/e2e-feed"
MATRIX_ABSENCE_ID_BASE = 910000
MATRIX_STATE = {}


def matrix_active():
    return bool(MATRIX.get(""))


def matrix_key():
    return MATRIX.get("")


def matrix_safe_key():
    return re.sub(r"[^A-Za-z0-9_-]", "_", matrix_key())


def matrix_config_filename():
    safe = matrix_safe_key()
    return f"config-matrix-{safe}.json" if safe else MATRIX_CONFIG_NAME


def matrix_scoped_path(base_path):
    if not matrix_active():
        return base_path
    safe = matrix_safe_key()
    if not safe:
        return base_path
    return base_path.with_name(f"{base_path.stem}-matrix-{safe}{base_path.suffix}")


class MatrixScopedAttr:
    def __set_name__(self, owner, name):
        self.base_name = f"_base_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return matrix_scoped_path(getattr(obj, self.base_name))

    def __set__(self, obj, value):
        setattr(obj, self.base_name, value)


def matrix_state():
    return MATRIX_STATE.setdefault(matrix_key(), {"archived": set(), "confirmed": set(), "absences": []})


def matrix_reset():
    MATRIX_STATE[matrix_key()] = {"archived": set(), "confirmed": set(), "absences": []}


class MatrixMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            MATRIX.set(read_cookie(scope, MATRIX_COOKIE))
        await self.app(scope, receive, send)


class MatrixStore(FixtureStore):
    calendar_subscriptions_path = MatrixScopedAttr()
    calendar_snapshot_path = MatrixScopedAttr()
    calendar_state_path = MatrixScopedAttr()
    marks_path = MatrixScopedAttr()
    cancellations_path = MatrixScopedAttr()
    holidays_cache_path = MatrixScopedAttr()
    letters_confirmations_path = MatrixScopedAttr()
    letters_search_cache_path = MatrixScopedAttr()
    absence_history_path = MatrixScopedAttr()
    modules_path = MatrixScopedAttr()
    seen_path = MatrixScopedAttr()

    @property
    def config_path(self):
        if not matrix_active():
            return self._base_config_path
        path = self.dir / matrix_config_filename()
        if not path.exists() and self._base_config_path.exists():
            shutil.copyfile(self._base_config_path, path)
        return path

    @config_path.setter
    def config_path(self, value):
        self._base_config_path = value

    def save_config(self, config):
        stored = self._load_json_object(self.config_path)
        listed = config.get("connections") if isinstance(config.get("connections"), list) else []
        shown = {entry.get("id") for entry in listed if isinstance(entry, dict)}
        visible = set(school_ids())
        hidden = [
            entry
            for entry in (stored.get("connections") or [])
            if isinstance(entry, dict) and entry.get("id") not in shown and entry.get("id") not in visible
        ]
        if hidden:
            config = dict(config, connections=listed + hidden)
        super().save_config(config)

    def drop_matrix_config(self):
        path = self.dir / matrix_config_filename()
        if path.exists():
            path.unlink()


def matrix_week_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def matrix_lesson_date(day_of_week, week_offset=0):
    monday = matrix_week_monday() + timedelta(days=7 * int(week_offset or 0))
    return (monday + timedelta(days=int(day_of_week or 1) - 1)).strftime("%d.%m.%Y")


def matrix_apply_config(config, payload, week_offset=0):
    from app.feed import relabel
    from app.mapping import configured_time, shift_time

    lessons = []
    for lesson in payload.get("lessons") or []:
        native = dict(lesson, subject_key=lesson.get("subject_code"), date=matrix_lesson_date(lesson.get("day_of_week"), week_offset))
        shown = relabel(config, native)
        chosen = configured_time(config, shown.get("period"))
        if chosen:
            shown["start_time"] = chosen
            shown["end_time"] = shift_time(chosen, 45)
        lessons.append(shown)
    monday = matrix_week_monday() + timedelta(days=7 * int(week_offset or 0))
    return dict(
        payload,
        lessons=lessons,
        start_date=monday.strftime("%d.%m.%Y"),
        end_date=(monday + timedelta(days=6)).strftime("%d.%m.%Y"),
        period_times=dict(config.get("period_times") or {}),
    )


def matrix_absence_entry(payload):
    identifier = MATRIX_ABSENCE_ID_BASE + len(matrix_state()["absences"]) + 1
    first = payload.get("from_date") or payload.get("day_from") or date.today().isoformat()
    kind = payload.get("type") or "leave"
    return {
        "id": identifier,
        "kind": kind,
        "target": payload.get("target") or "",
        "label_key": f"absence.type.{kind}.label",
        "target_key": "",
        "student_id": "child-1",
        "status": "open",
        "from_date": first,
        "till_date": payload.get("till_date") or payload.get("day_till") or first,
        "subject": payload.get("subject") or "",
        "comment": payload.get("body") or payload.get("comment") or "",
        "deletable": True,
        "attachments": [],
        "technical": {"id": identifier, "created_at": 1787990400},
    }


class MatrixConnection(FixtureConnection):
    def is_configured(self):
        return True


class MatrixService(FixtureService):
    def connection(self, connection_id):
        return MatrixConnection(self, connection_id)

    def summaries(self, with_status=False):
        rows = super().summaries(with_status)
        if not matrix_active():
            return rows
        for row in rows:
            entry = self.store.connection(row["id"]) or {}
            row["short_name"] = connection_short_name(dict(entry, school_url=row["school_url"]))
            row["label"] = str(entry.get("label") or "")
        return rows

    def timetable(self, key, week_offset=0):
        payload = super().timetable(key, week_offset)
        if not matrix_active():
            return payload
        connection_id = split_key(key)[0]
        return matrix_apply_config(self.store.connection_store(connection_id).load_config(), payload, week_offset)

    def letters(self, tab="current"):
        payload = super().letters(tab)
        if not matrix_active():
            return payload
        listed = payload["letters"]
        archived = matrix_state()["archived"]
        if tab == "archive":
            moved = [dict(entry, unread=False) for entry in super().letters("current")["letters"] if entry["key"] in archived]
            listed = moved + listed
        else:
            listed = [entry for entry in listed if entry["key"] not in archived]
        for entry in listed:
            if entry["key"] in matrix_state()["confirmed"]:
                entry["confirmation"] = {"type": "seen", "open": False, "done": True, "sendable": False, "confirmed_at": CONFIRMED_AT}
        return dict(payload, letters=listed)

    def archive_letter(self, connection_id, letter_id, recipient_id):
        if matrix_active():
            matrix_state()["archived"].add(f"{connection_id}:{letter_id}:{recipient_id}")
        return super().archive_letter(connection_id, letter_id, recipient_id)

    def restore_letter(self, connection_id, letter_id, recipient_id):
        matrix_state()["archived"].discard(f"{connection_id}:{letter_id}:{recipient_id}")
        return True

    def confirm_letter(self, connection_id, letter_id, recipient_id, text=None):
        if matrix_active():
            matrix_state()["confirmed"].add(f"{connection_id}:{letter_id}:{recipient_id}")
        return super().confirm_letter(connection_id, letter_id, recipient_id, text)

    def absences_overview(self, connection_id=None):
        payload = super().absences_overview(connection_id)
        if not matrix_active():
            return payload
        config = self.store.connection_store(connection_id or SCHOOL_ONE).load_config()
        return dict(payload, phones=list(config.get("phones") or []), entries=list(matrix_state()["absences"]) + payload["entries"])

    def report_absence(self, connection_id, payload, attachments=None):
        if matrix_active():
            matrix_state()["absences"].append(matrix_absence_entry(payload or {}))
        return super().report_absence(connection_id, payload, attachments)

    def delete_absence(self, connection_id, payload):
        wanted = str((payload or {}).get("id"))
        matrix_state()["absences"] = [entry for entry in matrix_state()["absences"] if str(entry["id"]) != wanted]
        return {"ok": True, "message_key": "api.absence.withdrawn"}


class MatrixHolidays(FixtureHolidays):
    def _periods(self):
        shift = MATRIX_HOLIDAY_SHIFT.get(0)
        periods = super()._periods()
        if not shift:
            return periods
        moved = []
        for period in periods:
            entry = dict(period)
            for name in ("start", "end"):
                entry[name] = (date.fromisoformat(period[name]) + timedelta(days=shift)).isoformat()
            moved.append(entry)
        return moved

    def range_info(self, start, end, config=None):
        region = str((config or {}).get("holiday_region") or HOLIDAY_REGION)
        token = MATRIX_HOLIDAY_SHIFT.set(7 if matrix_active() and region != HOLIDAY_REGION else 0)
        try:
            payload = super().range_info(start, end, config)
        finally:
            MATRIX_HOLIDAY_SHIFT.reset(token)
        payload["region"] = region
        return payload


def matrix_snapshot(store, service, now_epoch):
    from app.poller import ABSENCE_FIELDS

    weeks = [service.timetable(CHILD_ID, week_offset=offset) for offset in (0, 1)]
    entries = [
        {name: entry.get(name) for name in ABSENCE_FIELDS}
        for entry in service.absences_overview(SCHOOL_ONE)["entries"]
        if entry.get("student_id") == "child-1"
    ]
    snapshot = store.load_calendar_snapshot()
    children = snapshot.setdefault("children", {})
    holder = children.setdefault(CHILD_ID, {})
    holder["weeks"] = {
        week["start_date"]: {
            "start_date": week["start_date"],
            "end_date": week["end_date"],
            "lessons": week["lessons"],
            "fetched_at": now_epoch,
        }
        for week in weeks
    }
    holder["last_success"] = now_epoch
    holder["absences"] = entries
    holder["absences_fetched_at"] = now_epoch
    store.save_calendar_snapshot(snapshot)
    return {"ok": True, "lessons": sum(len(week["lessons"]) for week in weeks), "absences": len(entries)}


def register_matrix_hooks(app, store, service, registry, holiday_calendar):
    import time

    from app.calendar_server import RateLimiter, create_calendar_app
    from app.integration import ensure_token

    before = len(app.router.routes)
    feed_limiter = RateLimiter(limit=1_000_000, window=1)
    app.mount(
        MATRIX_FEED_PREFIX,
        create_calendar_app(store, registry, holiday_calendar=holiday_calendar, limiter=feed_limiter),
    )

    @app.post("/e2e/matrix/reset")
    def reset_matrix():
        matrix_reset()
        store.drop_matrix_config()
        if not matrix_active():
            return {"ok": True, "matrix": False}
        registry.store.save_calendar_subscriptions({"subscriptions": []})
        registry.create(
            CHILD_ID,
            [subscriptions.COMPONENT_TIMETABLE, subscriptions.COMPONENT_SCHOOL_HOLIDAYS],
            SUBSCRIPTION_LABEL,
            SUBSCRIPTION_COLOR,
        )
        registry.store.load_calendar_subscriptions()["subscriptions"][0]["token"] = SUBSCRIPTION_TOKEN
        teachers = {
            "BEH": {"label": text("teacher"), "surname": "", "is_class_teacher": True},
            "SCH": {"label": text("teacher_substitute"), "surname": "", "is_class_teacher": False},
        }
        store.update_connection(SCHOOL_ONE, teachers=teachers)
        return {"ok": True}

    @app.post("/e2e/matrix/snapshot")
    def snapshot_matrix():
        return matrix_snapshot(store, service, int(time.time()))

    @app.get("/e2e/matrix/token")
    def matrix_token():
        return {"token": ensure_token(store)}

    @app.get("/e2e/matrix/schema")
    def matrix_schema():
        return {"keys": sorted(set(DEFAULT_CONFIG) | {key for key in CONNECTION_DEFAULTS if key != "id"})}

    added = app.router.routes[before:]
    del app.router.routes[before:]
    app.router.routes[0:0] = added


def register_wizard_hooks(app, wizard):
    before = len(app.router.routes)

    @app.post("/e2e/wizard/restart")
    def restart_wizard():
        wizard.restart()
        return {"ok": True}

    @app.post("/e2e/wizard/advance")
    def advance_wizard(seconds: int = 0):
        wizard.clock.offset += seconds
        return {"offset": wizard.clock.offset}

    added = app.router.routes[before:]
    del app.router.routes[before:]
    app.router.routes[0:0] = added


def create_fixture_app():
    store = MatrixStore(E2E_DATA_DIR)
    config = seed_config(store)
    service = MatrixService(store)
    holiday_calendar = MatrixHolidays()
    registry = make_subscription_registry(config)
    wizard = LiveWizardSwitch(FixtureWizard())
    app = create_app(
        service,
        wizard=wizard,
        frontend_dir=str(FRONTEND_DIR),
        holiday_calendar=holiday_calendar,
        registry=registry,
    )
    register_matrix_hooks(app, store, service, registry, holiday_calendar)
    register_wizard_hooks(app, wizard)
    app.add_middleware(ScenarioMiddleware)
    app.add_middleware(MatrixMiddleware)
    return app


def create_server_app():
    reset_e2e_data_dir()
    return create_fixture_app()
