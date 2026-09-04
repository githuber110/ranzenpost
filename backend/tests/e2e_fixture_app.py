import contextvars
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from app import haservices, messages, subscriptions
from app.messenger import (
    READ_FAILED_KEY,
    READ_OK_KEY,
    ROOM_INCOMPLETE_KEY,
    ROOM_OK_KEY,
)
from app.server import create_app
from app.store import Store

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
E2E_DATA_DIR = Path(os.environ.get("ISERV_E2E_DATA_DIR", BACKEND_DIR.parent / "data-e2e"))
if E2E_DATA_DIR.exists():
    shutil.rmtree(E2E_DATA_DIR)

LONG_SUBJECT = "Naturwissenschaften und angewandte Informatik"

CONFIRM_LETTER_ID = "c3d4e5f6a7b8491023c4d5e6f7a8b901"
CONFIRMED_AT = "2026-09-03T14:05:00"

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


SCENARIO_COOKIE = "e2e_scenario"
SCENARIO = contextvars.ContextVar("e2e_scenario", default="")
ROOM_WRITES_COOKIE = "e2e_room_writes"
ROOM_WRITES = contextvars.ContextVar("e2e_room_writes", default="")

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
}

SCENARIO_SUBJECTS = ["Deutsch", "Mathematik", LONG_SUBJECT, "Englisch", "Sport"]
SCENARIO_WEEKDAYS = range(1, 8)


def current_scenario():
    return SCENARIOS.get(SCENARIO.get(""), None)


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


class ScenarioMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            SCENARIO.set(scenario_cookie(scope))
            ROOM_WRITES.set(read_cookie(scope, ROOM_WRITES_COOKIE))
        await self.app(scope, receive, send)


def scenario_lessons(child_id, periods):
    lessons = []
    offset = 0 if child_id == SCENARIO_CHILDREN[0]["child_id"] else 1
    for day in SCENARIO_WEEKDAYS:
        for period in range(1, periods + 1):
            subject = SCENARIO_SUBJECTS[(period + offset) % len(SCENARIO_SUBJECTS)]
            lessons.append(
                {
                    "date": "31.08.2026",
                    "day_of_week": day,
                    "period": period,
                    "start_time": "%02d:00" % (7 + period),
                    "subject_code": subject[:3].upper(),
                    "subject_label": subject,
                    "color": "#0e6b70",
                    "teacher_code": "BEH",
                    "teacher_label": "Fr. Behrend-Waldenburger",
                    "is_class_teacher": True,
                    "room": "R%d" % period,
                    "change_kind": "cancelled" if period == periods and offset == 0 else "",
                    "changed_fields": [],
                    "previous": {"subject": "", "teacher": "", "room": ""},
                }
            )
    return lessons


def scenario_letters(count):
    return [
        {
            "letter_id": "scenario-%02d" % index,
            "recipient_id": "r1",
            "title": "Elternbrief %02d mit einem sehr langen Titel zur Zeilenhoehe" % index,
            "child": SCENARIO_CHILDREN[0]["name"],
            "recipients": "Klasse 3b",
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
            "title": "Pinnwandbeitrag %02d mit einem laengeren Titel" % index,
            "text": "Kurzer Vorschautext.",
            "color": "#0e6b70",
            "owner": "Schulleitung",
            "folder_id": 1,
            "folder_title": "Elternbeirat",
            "column_title": "Aktuelles",
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


class FixtureService:
    def __init__(self, store):
        self.store = store
        self._teacher_room_created = False

    def messenger_rooms(self):
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
        return {
            "self_user_id": MESSENGER_SELF,
            "rooms": rooms,
            "can_write_to_teacher": True,
        }

    def messenger_room_messages(self, room_id, before=None):
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

    def messenger_send(self, room_id, text):
        if not str(text or "").strip():
            return {"ok": False, "message_key": "api.messenger.send.empty"}
        return {"ok": True, "message_key": "api.messenger.send.ok", "event_id": "$fixture-sent"}

    def messenger_mark_read(self, room_id, event_id):
        if not str(room_id or "").strip() or not str(event_id or "").strip():
            return messages.result(False, READ_FAILED_KEY)
        return messages.result(True, READ_OK_KEY)

    def messenger_teacher_search(self, query):
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

    def messenger_create_teacher_room(self, teacher, child_ids, add_other_parents):
        teacher = str(teacher or "").strip()
        wanted = [str(value or "").strip() for value in (child_ids or [])]
        wanted = [value for value in wanted if value]
        if not teacher or not wanted:
            return messages.result(False, ROOM_INCOMPLETE_KEY)
        if teacher == MESSENGER_TEACHER_VALUE:
            return messages.result(True, ROOM_OK_KEY, room_id=MESSENGER_ROOM_B, joined=True)
        self._teacher_room_created = True
        return messages.result(True, ROOM_OK_KEY, room_id=MESSENGER_ROOM_NEW, joined=True)

    def messenger_media(self, server_name, media_id):
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
        return "ok"

    def me(self):
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

    def children(self):
        scenario = current_scenario()
        if scenario:
            return [dict(child) for child in SCENARIO_CHILDREN[: scenario["children"]]]
        return [{"child_id": "child-1", "name": "Mia Musterkind", "class_name": "3b"}]

    def timetable_available(self):
        return True

    def timetable(self, child_id, week_offset=0):
        scenario = current_scenario()
        if scenario:
            return {
                "last_updated": "31.08.2026 12:25",
                "start_date": "31.08.2026",
                "end_date": "06.09.2026",
                "lessons": scenario_lessons(child_id, scenario["periods"]),
                "changes": [],
                "period_times": dict(
                    (str(period), "%02d:00" % (7 + period)) for period in range(1, scenario["periods"] + 1)
                ),
                "change_count": 1,
                "week_offset": week_offset,
            }
        lessons = []
        for day in range(0, 5):
            for period in range(1, 7):
                if (day + period) % 4 == 0:
                    continue
                lessons.append(
                    {
                        "date": "31.08.2026",
                        "day_of_week": day,
                        "period": period,
                        "start_time": f"{7 + period}:00",
                        "subject_code": "NWI" if period == 3 else "D",
                        "subject_label": LONG_SUBJECT if period == 3 else "Deutsch",
                        "color": "#0e6b70",
                        "teacher_code": "BEH",
                        "teacher_label": "Fr. Behrend",
                        "is_class_teacher": True,
                        "room": "R1",
                        "change_kind": "cancelled" if period == 5 and day == 1 else "",
                        "changed_fields": [],
                        "previous": {"subject": "", "teacher": "", "room": ""},
                    }
                )
        lessons.append(
            {
                "date": "31.08.2026",
                "day_of_week": 0,
                "period": 1,
                "start_time": "8:00",
                "subject_code": "ENG",
                "subject_label": "Englisch als Doppelbelegung mit der Klassenlehrerin",
                "color": "#7a4b9c",
                "teacher_code": "SCH",
                "teacher_label": "Fr. Schmidt-Waldenburger",
                "is_class_teacher": False,
                "room": "R2",
                "change_kind": "changed",
                "changed_fields": ["room", "teacher"],
                "previous": {"subject": "", "teacher": "Fr. Behrend", "room": "R1"},
            }
        )
        return {
            "last_updated": "31.08.2026 12:25",
            "start_date": "31.08.2026",
            "end_date": "06.09.2026",
            "lessons": lessons,
            "changes": [],
            "period_times": {str(period): f"{7 + period}:00" for period in range(1, 7)},
            "change_count": 1,
            "week_offset": week_offset,
        }

    def pinboard(self):
        scenario = current_scenario()
        if scenario:
            return {
                "folders": [
                    {
                        "id": 1,
                        "title": "Elternbeirat",
                        "unread": scenario["posts"],
                        "last_post_id": 1000,
                        "columns": [],
                        "attachments": [],
                        "author": "Schulleitung",
                        "students_can_create_tiles": False,
                    }
                ],
                "feed": scenario_posts(scenario["posts"]),
            }
        folders = [
            {
                "id": 1,
                "title": "Elternbeirat",
                "unread": 1,
                "last_post_id": 3,
                "columns": [],
                "attachments": [],
                "author": "Schulleitung",
                "students_can_create_tiles": False,
            },
            {
                "id": 2,
                "title": "Klasse 3b",
                "unread": 0,
                "last_post_id": 1,
                "columns": [],
                "attachments": [],
                "author": "Klassenlehrerin",
                "students_can_create_tiles": False,
            },
        ]
        feed = [
            {
                "id": 3,
                "title": "Ausflug ins Schullandheim mit vielen Details zur Anreise und Ausruestung",
                "text": "Bitte packt festes Schuhwerk ein.",
                "color": "#0e6b70",
                "owner": "Schulleitung",
                "folder_id": 1,
                "folder_title": "Elternbeirat",
                "column_title": "Aktuelles",
                "unread": True,
                "attachments": [],
            },
            {
                "id": 2,
                "title": "Elternabend",
                "text": "Termin steht fest.",
                "color": "#7a4b9c",
                "owner": "Klassenlehrerin",
                "folder_id": 2,
                "folder_title": "Klasse 3b",
                "column_title": "Termine",
                "unread": False,
                "attachments": [],
            },
            {
                "id": 1,
                "title": "Willkommen",
                "text": "Willkommen im neuen Schuljahr.",
                "color": "#b4602a",
                "owner": "Schulleitung",
                "folder_id": 1,
                "folder_title": "Elternbeirat",
                "column_title": "Aktuelles",
                "unread": False,
                "attachments": [],
            },
        ]
        return {"folders": folders, "feed": feed}

    def mark_pinboard_seen(self, tile_ids=None, mark_all=False, unseen=False):
        return {"seen": len(tile_ids or [])}

    def letters(self, tab="current"):
        scenario = current_scenario()
        if scenario:
            return {"letters": scenario_letters(scenario["letters"] if tab == "current" else 0)}
        letters = [
            {
                "letter_id": CONFIRM_LETTER_ID,
                "recipient_id": "r1",
                "title": "Informationen zum Schuljahresstart und weiteren Terminen",
                "child": "Mia Musterkind",
                "recipients": "Klasse 3b",
                "published": "31.08.2026",
                "unread": tab == "current",
                "body_text": "",
                "attachments": [],
                "confirmation": self._confirmation_state(),
            },
            {
                "letter_id": "l2",
                "recipient_id": "r1",
                "title": "Elternsprechtagsanmeldung für das Schuljahr 2026/2027",
                "child": "Mia Musterkind",
                "recipients": "Klasse 3b",
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
        ]
        return {"letters": letters}

    def _confirmation_state(self):
        return {"type": "seen", "open": True, "done": False, "sendable": True, "confirmed_at": ""}

    def mark_letters_read(self, keys=None, mark_all=False):
        return {"read": len(keys or [])}

    def confirm_letter(self, letter_id, recipient_id, text=None):
        return {
            "ok": True,
            "message_key": "api.letters.confirm.ok",
            "confirmed_at": CONFIRMED_AT,
        }

    def letter_detail(self, letter_id, recipient_id):
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

    def archive_letter(self, letter_id, recipient_id):
        return True

    def conferences(self):
        return {
            "empty": False,
            "items": [
                {"cells": ["Elternsprechtag Klasse 3b", "12.09.2026, 16:00"], "links": []},
                {"cells": ["Individuelle Beratung", "19.09.2026, 17:30"], "links": []},
            ],
        }

    def absences_overview(self):
        today = date.today()
        return {
            "children": [{"id": "child-1", "name": "Mia Musterkind", "class_name": "3b"}],
            "types": ["sick", "leave", "deregister", "daycare"],
            "deregister_options": ["bus", "lunch", "kindergarten"],
            "periods": [{"number": index, "name": f"{index}. Stunde"} for index in range(1, 7)],
            "period_labels": [{"number": index, "label": f"{index}. Stunde {6 + index}:00 - {6 + index}:45"} for index in range(1, 7)],
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
            "entries": [
                {
                    "id": "a1c2b3d4e5f6470891a2b3c4d5e6f708",
                    "kind": "sick",
                    "label_key": "absence.type.sick.label",
                    "student_id": "child-1",
                    "status": "accepted",
                    "from_date": "2026-08-25",
                    "till_date": "2026-08-26",
                    "comment": "Fieberhafter Infekt mit ärztlicher Bescheinigung",
                    "deletable": False,
                    "attachments": [
                        {
                            "filename": "aerztliche-bescheinigung-fieberhafter-infekt-25-08-2026.pdf",
                            "url": "api/absences/attachment?id=a1c2b3d4e5f6470891a2b3c4d5e6f708",
                        }
                    ],
                    "technical": {
                        "id": "a1c2b3d4e5f6470891a2b3c4d5e6f708",
                        "created_at": 1787990400,
                    },
                }
            ],
        }

    def report_absence(self, payload, attachments=None):
        return {"ok": True, "message": "Meldung eingereicht."}


class FixtureHolidays:
    def _monday(self):
        today = date.today()
        return today - timedelta(days=today.weekday())

    def _periods(self):
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


CHILD_ID = "child-1"
CHILD_NAME = "Mia Musterkind"
CHILD_CLASS = "3b"
SUBSCRIPTION_LABEL = "3b"
SUBSCRIPTION_COLOR = "#135859"
SUBSCRIPTION_TOKEN = "e2e-fixture-token-abcdefghijklmnopqrstuvwxyz012345"


class FixtureSubscriptionStore:
    def __init__(self, config):
        self._config = config
        self._data = {"subscriptions": []}

    def load_config(self):
        return self._config

    def load_calendar_subscriptions(self):
        return self._data

    def save_calendar_subscriptions(self, data):
        self._data = data


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
    config = store.load_config()
    config["subjects"] = {
        "NWI": {"label": LONG_SUBJECT, "color": "#0e6b70"},
        "D": {"label": "Deutsch", "color": ""},
    }
    config["holiday_region"] = HOLIDAY_REGION
    config["period_times"] = dict(
        (str(period), "%02d:00" % (7 + period)) for period in range(1, 9)
    )
    config["children"] = [
        {"child_id": CHILD_ID, "name": CHILD_NAME, "class_name": CHILD_CLASS}
    ]
    store.save_config(config)
    return config


def create_fixture_app():
    store = Store(E2E_DATA_DIR)
    config = seed_config(store)
    service = FixtureService(store)
    app = create_app(
        service,
        frontend_dir=str(FRONTEND_DIR),
        holiday_calendar=FixtureHolidays(),
        registry=make_subscription_registry(config),
    )
    app.add_middleware(ScenarioMiddleware)
    return app


app = create_fixture_app()
