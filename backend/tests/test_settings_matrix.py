import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import cancellations as cancellations_module
from app import feed, feed_ics, holidays, mapping, messages, scheduler
from app.calendar_server import create_calendar_app
from app.integration_api import IntegrationAccess
from app.iserv.absences import LEAVE_PATH
from app.iserv.models import Child, Lesson, TimetableWeek
from app.marks import MarkRegistry
from app.poller import Poller
from app.server import create_app
from app.service import IServService
from app.store import CONNECTION_DEFAULTS, DEFAULT_CONFIG, Store
from app.subscriptions import SubscriptionRegistry
from tests.support import DEFAULT_SECRETS, add_school
from tests.test_holidays import fixture_year

SCHOOL = "a1b2c3d4"
SCHOOL_URL = "https://school-one.example"
RAW_CHILD = "child-uuid-a"
CHILD_KEY = f"{SCHOOL}:{RAW_CHILD}"
CHILD_NAME = "Zwiebelfisch Quastenflosser"
STUDENT_ID = 7
NOW = datetime(2026, 9, 2, 6, 10)
NOW_EPOCH = int(NOW.replace(tzinfo=timezone.utc).timestamp())
WEEK_START = "31.08.2026"
WEEK_END = "06.09.2026"
WEDNESDAY = "02.09.2026"
THURSDAY = "03.09.2026"
WEDNESDAY_ISO = "2026-09-02"
PERIOD_TIMES = {"1": "08:00", "2": "08:50", "3": "09:45"}
FIRST_SERVICE = "notify.parent_phone"
SECOND_SERVICE = "notify.other_phone"
MODULE_FLAGS = {"timetable": True, "letters": True, "pinboard": False, "absences": True, "conferences": False, "messenger": False}
LETTER = {"letter_id": "letter-1", "recipient_id": "recipient-1", "title": "Field trip", "published": "01.09.2026 12:00", "sender": "Office"}
LETTER_KEY = f"{LETTER['letter_id']}:{LETTER['recipient_id']}"
COMPONENTS = ["timetable", "school_holidays", "public_holidays", "marks", "absences"]
EVENT_RANGE = {"start": "2026-08-31", "end": "2026-09-06"}
HOLIDAY_RANGE = {"start": "2026-09-01", "end": "2027-01-31"}
PASSPHRASE_ENV = "ISERV_PASSPHRASE"
NEW_COLOR = "green"
OLD_COLOR = "maroon"
CUSTOM_COLOR = "#abcdef"


def _end_of(start):
    hours, minutes = start.split(":")
    return "%02d:%02d" % divmod(int(hours) * 60 + int(minutes) + 45, 60)


def _lesson(day, weekday, period, subject, teacher, subject_name, teacher_name, surname, start):
    return Lesson(
        day,
        weekday,
        period,
        subject,
        teacher,
        "R1",
        "5A",
        subject_name=subject_name,
        teacher_name=teacher_name,
        teacher_surname=surname,
        start_time=start,
        end_time=_end_of(start),
    )


class TimetableSource:
    def __init__(self):
        self.changes = []
        self.lessons = [
            _lesson(WEDNESDAY, 3, 1, "D", "BEH", "Deutsch", "Frau Behrens", "Behrens", "08:00"),
            _lesson(WEDNESDAY, 3, 2, "Mathematik", "MUE", "Mathematik", "Herr Mueller", "Mueller", "08:50"),
            _lesson(WEDNESDAY, 3, 3, "D", "BEH", "Deutsch", "Frau Behrens", "Behrens", "09:45"),
            _lesson(THURSDAY, 4, 1, "D", "BEH", "Deutsch", "Frau Behrens", "Behrens", "08:00"),
        ]

    def bump(self):
        self.changes = [{"marker": len(self.changes) + 1}]


class FakeClient:
    def __init__(self, url, source):
        self.url = url
        self.base_url = url
        self.session = None
        self.source = source
        self.authed = False

    def login(self, username, password, code_provider):
        assert code_provider()
        self.authed = True
        return self

    def is_authenticated(self):
        return self.authed

    def get_children(self):
        return [Child(RAW_CHILD, CHILD_NAME)]

    def read_time_table_week(self, child_id, reference=None):
        lessons = list(self.source.lessons)
        return TimetableWeek(WEEK_START, WEEK_END, "01.09.2026 12:00", lessons, lessons, list(self.source.changes))


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {}


class FakeDsa:
    def __init__(self):
        self.requests = {LEAVE_PATH: []}
        self.next_id = 1

    def school_settings(self):
        return {"requestToSchools_studentAbsence_isActive": True, "requestToSchools_studentAbsence_minDays": 1}

    def students(self):
        return [{"id": STUDENT_ID, "name": CHILD_NAME, "class_name": "5A"}]

    def sick_notes(self, since=None):
        return []

    def sick_note_children(self):
        return [{"id": STUDENT_ID, "name": CHILD_NAME, "class_name": "5A"}]

    def sick_note_children_or_raise(self):
        return self.sick_note_children()

    def lesson_slots(self):
        return [{"number": number, "name": f"Period {number}"} for number in (1, 2, 3)]

    def period_times(self):
        return {}

    def user_requests(self, path, student_id=None):
        return list(self.requests.get(path, []))

    def user_requests_or_raise(self, path, student_id=None):
        return self.user_requests(path, student_id)

    def send_request(self, request):
        data = getattr(request, "payload", None)
        data = data if isinstance(data, dict) else {}
        entry = {
            "id": self.next_id,
            "student": STUDENT_ID,
            "absentFrom": data.get("absentFrom"),
            "absentUntil": data.get("absentUntil"),
            "topic": data.get("topic") or "",
            "accepted": None,
            "createdAt": "2026-09-01T10:00:00",
        }
        self.next_id += 1
        self.requests[LEAVE_PATH].append(entry)
        return FakeResponse(201)

    def delete_entry(self, path):
        identifier = int(path.rsplit("/", 1)[-1])
        self.requests[LEAVE_PATH] = [entry for entry in self.requests[LEAVE_PATH] if entry["id"] != identifier]
        return FakeResponse(204)

    def accept_all(self):
        for entry in self.requests[LEAVE_PATH]:
            entry["accepted"] = True


class FakeLetters:
    def __init__(self, store):
        self.store = store
        self.current = [dict(LETTER, unread=True)]
        self.archive = []

    def _view(self, entry, tab):
        record = self.store.load_letters_confirmations().get(f"{entry['letter_id']}:{entry['recipient_id']}")
        shown = dict(entry)
        shown["unread"] = bool(entry.get("unread")) and tab != "archive"
        shown["body_text"] = ""
        shown["attachments"] = []
        shown["confirmation"] = {
            "type": "read",
            "open": record is None,
            "done": record is not None,
            "sendable": True,
            "confirmed_at": (record or {}).get("confirmed_at", ""),
        }
        return shown

    def letters(self, tab="current"):
        listed = self.archive if tab == "archive" else self.current
        return {"letters": [self._view(entry, tab) for entry in listed]}

    def archive_letter(self, letter_id, recipient_id):
        moved = [entry for entry in self.current if entry["letter_id"] == letter_id]
        self.current = [entry for entry in self.current if entry["letter_id"] != letter_id]
        self.archive.extend(moved)
        return True

    def restore_letter(self, letter_id, recipient_id):
        moved = [entry for entry in self.archive if entry["letter_id"] == letter_id]
        self.archive = [entry for entry in self.archive if entry["letter_id"] != letter_id]
        self.current.extend(moved)
        return True

    def confirm_letter(self, letter_id, recipient_id, text=None):
        records = self.store.load_letters_confirmations()
        records[f"{letter_id}:{recipient_id}"] = {"type": "read", "confirmed_at": "2026-09-02T08:10:00"}
        self.store.save_letters_confirmations(records)
        return messages.result(True, "api.letters.confirm.ok", confirmed_at="2026-09-02T08:10:00")


class Clock:
    def __init__(self, epoch=NOW_EPOCH):
        self.epoch = epoch

    def __call__(self):
        return self.epoch


class Harness:
    def __init__(self, tmp_path, monkeypatch):
        self.clock = Clock()
        self.sent = []
        self.source = TimetableSource()
        self.dsa = FakeDsa()
        self.store = Store(tmp_path / "data")
        config = self.store.load_config()
        config["language"] = "de"
        config["notify_services"] = [FIRST_SERVICE]
        self.store.save_config(config)
        add_school(
            self.store,
            SCHOOL_URL,
            connection_id=SCHOOL,
            label="School One",
            short_name="one",
            holiday_region="DE-NI",
            period_times=dict(PERIOD_TIMES),
            subjects={"D": {"label": "Deutsch", "color": "#84142a", "color_source": "user"}},
            children=[{"child_id": RAW_CHILD, "name": CHILD_NAME, "class_name": "5A", "student_id": STUDENT_ID}],
        )
        registry_state = {
            "modules": dict(MODULE_FLAGS),
            "unsupported": [],
            "unknown": [],
            "probes": {},
            "checked_at": NOW_EPOCH,
            "iserv_version": "3.9",
        }
        self.store.connection_store(SCHOOL).save_modules(registry_state)
        self.service = IServService(self.store, client_factory=lambda url: FakeClient(url, self.source))
        connection = self.service.connection(SCHOOL)
        connection._dsa = lambda: self.dsa
        self.letters = FakeLetters(self.store.connection_store(SCHOOL))
        for name in (
            "letters",
            "archive_letter",
            "restore_letter",
            "confirm_letter",
        ):
            setattr(connection, name, getattr(self.letters, name))
        monkeypatch.setattr(scheduler, "notify", self._capture)
        real_registry = cancellations_module.CancellationRegistry
        monkeypatch.setattr(
            cancellations_module,
            "CancellationRegistry",
            lambda store, clock=None: real_registry(store, clock=self.clock),
        )
        self.holidays = holidays.HolidayCalendar(self.store, fetcher=fixture_year, clock=self.clock)
        self.registry = SubscriptionRegistry(self.store, clock=self.clock)
        self.poller = Poller(
            self.service,
            notifier=scheduler._make_notifier(self.store),
            notifiers=scheduler.notifiers_for(self.store),
            registry=self.registry,
            holiday_calendar=self.holidays,
            clock=self.clock,
        )
        self.access = IntegrationAccess(self.store, clock=self.clock, announce=lambda token: None)
        app = create_app(
            self.service,
            holiday_calendar=self.holidays,
            registry=self.registry,
            integration_access=self.access,
            calendar_warmer=self.poller.refresh_child,
            mark_registry=MarkRegistry(self.store, clock=self.clock),
        )
        self.client = TestClient(app)
        self.calendar = TestClient(
            create_calendar_app(
                self.store,
                self.registry,
                holiday_calendar=self.holidays,
                builder=lambda subscription, store, source: feed.build_feed(subscription, store, source, now=NOW),
            ),
            raise_server_exceptions=False,
        )
        created = self.client.post(
            "/api/calendar/subscriptions",
            json={"child_key": CHILD_KEY, "components": COMPONENTS, "label": "5A"},
        )
        assert created.status_code == 200, created.text
        self.subscription = created.json()
        self.poll()

    def _capture(self, message, service=None, title="Ranzenpost"):
        self.sent.append({"message": message, "service": service})
        return True

    def poll(self):
        self.poller.poll_once()

    def auth(self):
        return {"Authorization": f"Bearer {self.store.load_integration_token()}"}

    def connection_view(self):
        return self.client.get(f"/api/connections/{SCHOOL}").json()

    def patch_connection(self, **fields):
        response = self.client.post(f"/api/connections/{SCHOOL}", json=fields)
        assert response.status_code == 200, response.text

    def patch_config(self, **fields):
        response = self.client.post("/api/config", json=fields)
        assert response.status_code == 200, response.text

    def patch_subject(self, key, **fields):
        subjects = self.connection_view()["subjects"]
        entry = dict(subjects[key])
        for name, value in fields.items():
            if value is None:
                entry.pop(name, None)
            else:
                entry[name] = value
        subjects[key] = entry
        self.patch_connection(subjects=subjects)

    def patch_teacher(self, code, **fields):
        teachers = self.connection_view()["teachers"]
        teachers[code] = dict(teachers[code], **fields)
        self.patch_connection(teachers=teachers)

    def feed_response(self, token=None):
        return self.calendar.get(f"/calendar/{token or self.subscription['token']}.ics")

    def feed_text(self):
        response = self.feed_response()
        assert response.status_code == 200
        return response.text.replace("\r\n ", "")

    def feed_events(self):
        events = {}
        for block in self.feed_text().split("BEGIN:VEVENT")[1:]:
            props = {}
            for line in block.split("\r\n"):
                name, separator, value = line.partition(":")
                if separator and name and name != "END":
                    props[name.split(";")[0]] = value
            events[props.get("UID", "")] = props
        return events

    def feed_event(self, marker):
        return next((props for uid, props in self.feed_events().items() if marker in uid), None)

    def state(self):
        response = self.client.get("/api/integration/state", params={"child": CHILD_KEY}, headers=self.auth())
        assert response.status_code == 200, response.text
        return response.json()

    def events(self, kind, **window):
        params = {"kind": kind}
        params.update(window or EVENT_RANGE)
        if kind == "holidays":
            params["school"] = SCHOOL
        else:
            params["child"] = CHILD_KEY
        response = self.client.get("/api/integration/events", params=params, headers=self.auth())
        assert response.status_code == 200, response.text
        return response.json()

    def lesson_event(self, period):
        return next(item for item in self.events("lessons") if _event_uid(period) in item["uid"])

    def info(self):
        return self.client.get("/api/integration/info", headers=self.auth()).json()

    def school(self):
        return self.client.get("/api/integration/school", params={"id": SCHOOL}, headers=self.auth()).json()

    def timetable(self):
        response = self.client.get("/api/timetable", params={"child": CHILD_KEY})
        assert response.status_code == 200, response.text
        return response.json()

    def lesson(self, period, day=WEDNESDAY):
        return next(entry for entry in self.timetable()["lessons"] if entry["date"] == day and entry["period"] == period)

    def push_after_change(self):
        start = len(self.sent)
        self.source.bump()
        self.poll()
        return self.sent[start:]

    def absences(self):
        response = self.client.get("/api/absences")
        assert response.status_code == 200, response.text
        return response.json()

    def letters_list(self, tab="current"):
        return self.client.get("/api/letters", params={"tab": tab}).json()["letters"]

    def summary(self):
        return self.client.get("/api/connections").json()["connections"][0]

    def subscriptions(self):
        return self.client.get("/api/calendar/subscriptions").json()["subscriptions"]

    def marks(self):
        return [entry["id"] for entry in self.client.get("/api/marks", params={"child": CHILD_KEY}).json()["marks"]]

    def cancellations(self):
        listed = self.client.get("/api/cancellations", params={"child": CHILD_KEY}).json()["cancellations"]
        return [entry["period"] for entry in listed]


@pytest.fixture
def harness(tmp_path, monkeypatch):
    return Harness(tmp_path, monkeypatch)


def _event_uid(period, day="20260902"):
    return f"-{day}-p{period}-0@"


def _flip(h, read, apply):
    before = read(h)
    apply(h)
    return before, read(h)


def shift_first_period(h):
    h.patch_connection(period_times=dict(PERIOD_TIMES, **{"1": "08:15"}))


def period_time_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["start_time"], shift_first_period)
    assert (before, after) == ("08:00", "08:15")
    assert h.timetable()["period_times"]["1"] == "08:15"


def period_time_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["DTSTART"], shift_first_period)
    assert (before, after) == ("20260902T080000", "20260902T081500")


def period_time_state(h):
    before, after = _flip(h, lambda h: h.state(), shift_first_period)
    assert before["now_lesson"]["start"] == "2026-09-02T08:00:00+02:00"
    assert before["next_lesson"]["start"] == "2026-09-02T08:50:00+02:00"
    assert after["now_lesson"] is None
    assert after["next_lesson"]["start"] == "2026-09-02T08:15:00+02:00"


def period_time_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["start"], shift_first_period)
    assert (before, after) == ("2026-09-02T08:00:00+02:00", "2026-09-02T08:15:00+02:00")


def lengthen_first_period(h):
    response = h.client.post(f"/api/connections/{SCHOOL}/periods/lessons/1", json={"start": "08:00", "duration": 50})
    assert response.status_code == 200, response.text


def period_duration_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["end_time"], lengthen_first_period)
    assert (before, after) == ("08:45", "08:50")


def period_duration_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["DTEND"], lengthen_first_period)
    assert (before, after) == ("20260902T084500", "20260902T085000")


OWN_ENTRY = {"type": "club", "name": "Chess", "start": "15:00", "duration": 60, "repeat": "weekly", "days": [2], "from": "2026-08-31", "until": "2026-12-16", "holidays": True, "child": RAW_CHILD}


def add_own_entry(h):
    response = h.client.post(f"/api/connections/{SCHOOL}/own-entries", json=OWN_ENTRY)
    assert response.status_code == 200, response.text
    updated = h.client.post(f"/api/calendar/subscriptions/{h.subscription['id']}", json={"components": COMPONENTS + ["own_entries"]})
    assert updated.status_code == 200, updated.text


def own_entry_app(h):
    listed = lambda h: [entry["name"] for entry in h.client.get(f"/api/connections/{SCHOOL}/periods").json()["entries"]]
    before, after = _flip(h, listed, add_own_entry)
    assert (before, after) == ([], ["Chess"])


def own_entry_feed(h):
    before, after = _flip(h, lambda h: h.feed_event("-20260902-own-"), add_own_entry)
    assert before is None
    assert after["SUMMARY"] == "Chess" and after["DTSTART"] == "20260902T150000" and after["DTEND"] == "20260902T160000"


def share_own_entries(h):
    h.patch_connection(own_entries_ha=True)


def with_own_entry(h):
    response = h.client.post(f"/api/connections/{SCHOOL}/own-entries", json=OWN_ENTRY)
    assert response.status_code == 200, response.text


def own_entries_ha_app(h):
    read = lambda h: h.client.get(f"/api/connections/{SCHOOL}").json()["own_entries_ha"]
    assert _flip(h, read, share_own_entries) == (False, True)
    refused = h.client.post(f"/api/connections/{SCHOOL}", json={"own_entries_ha": "yes"})
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_value"
    assert read(h) is True


def own_entries_ha_info(h):
    assert _flip(h, lambda h: h.info()["schools"][0]["own_entries"], share_own_entries) == (False, True)


def own_entries_ha_events(h):
    with_own_entry(h)
    read = lambda h: [(item["summary"], item["start"]) for item in h.events("own_entries")]
    card = lambda h: [(item["summary"], item["start"]) for item in h.events("own_entries", **dict(EVENT_RANGE, purpose="card"))]
    card_before = card(h)
    before, after = _flip(h, read, share_own_entries)
    assert before == []
    assert ("Chess", "2026-09-02T15:00:00+02:00") in after
    assert card_before == card(h) == after


def rename_subject(h):
    h.patch_subject("D", label="German")


def subject_name_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["subject_label"], rename_subject)
    assert (before, after) == ("Deutsch", "German")


def subject_name_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["SUMMARY"], rename_subject)
    assert "Deutsch" in before and "German" not in before
    assert "German" in after and "Deutsch" not in after


def subject_name_state(h):
    before, after = _flip(h, lambda h: h.state()["now_lesson"]["subject"], rename_subject)
    assert (before, after) == ("Deutsch", "German")


def subject_name_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["subject"], rename_subject)
    assert (before, after) == ("Deutsch", "German")


def drop_derived_code(h):
    h.patch_subject("Mathematik", code=None, derived=None)
    h.timetable()


def subject_code_derived_app(h):
    before, after = _flip(h, lambda h: h.lesson(2)["subject_code"], drop_derived_code)
    assert (before, after) == ("MA", "MA")
    entry = h.connection_view()["subjects"]["Mathematik"]
    assert entry["code"] == "MA" and entry["derived"] is True


def subject_code_derived_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(2)["subject_code"], drop_derived_code)
    assert (before, after) == ("MA", "MA")


def edit_code(h):
    h.patch_subject("Mathematik", code="MTH", derived=None)


def subject_code_edit_app(h):
    before, after = _flip(h, lambda h: h.lesson(2)["subject_code"], edit_code)
    assert (before, after) == ("MA", "MTH")
    assert "derived" not in h.connection_view()["subjects"]["Mathematik"]


def subject_code_edit_state(h):
    before, after = _flip(h, lambda h: h.state()["next_lesson"]["subject_code"], edit_code)
    assert (before, after) == ("MA", "MTH")


def subject_code_edit_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(2)["subject_code"], edit_code)
    assert (before, after) == ("MA", "MTH")


def recolor(code, color=NEW_COLOR):
    return lambda h: h.patch_subject(code, color=color, color_source="user")


def subject_color_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["color"], recolor("D"))
    assert (before, after) == (OLD_COLOR, NEW_COLOR)


def subject_color_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["COLOR"], recolor("D"))
    assert before == feed_ics.nearest_color_name(mapping.subject_base(OLD_COLOR))
    assert after == feed_ics.nearest_color_name(mapping.subject_base(NEW_COLOR))
    assert before != after


def subject_color_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["color"], recolor("D"))
    assert (before, after) == (mapping.subject_base(OLD_COLOR), mapping.subject_base(NEW_COLOR))
    assert mapping.is_hex_color(before) and mapping.is_hex_color(after)


def subject_color_hex_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["color"], recolor("D", CUSTOM_COLOR.upper()))
    assert (before, after) == (OLD_COLOR, CUSTOM_COLOR)


def subject_color_hex_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["COLOR"], recolor("D", CUSTOM_COLOR))
    assert before == feed_ics.nearest_color_name(mapping.subject_base(OLD_COLOR))
    assert after == feed_ics.nearest_color_name(CUSTOM_COLOR)
    assert before != after


def subject_color_hex_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["color"], recolor("D", CUSTOM_COLOR))
    assert (before, after) == (mapping.subject_base(OLD_COLOR), CUSTOM_COLOR)


def subject_color_derived_app(h):
    before, after = _flip(h, lambda h: h.lesson(2)["color"], recolor("Mathematik"))
    assert before != NEW_COLOR and after == NEW_COLOR


def subject_color_derived_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(2)).get("COLOR"), recolor("Mathematik"))
    assert before != feed_ics.nearest_color_name(mapping.subject_base(NEW_COLOR))
    assert after == feed_ics.nearest_color_name(mapping.subject_base(NEW_COLOR))


def subject_color_derived_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(2)["color"], recolor("Mathematik"))
    assert before != mapping.subject_base(NEW_COLOR) and after == mapping.subject_base(NEW_COLOR)


def teacher_label_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["teacher_label"], lambda h: h.patch_teacher("BEH", label="Frau Bergmann"))
    assert (before, after) == ("Frau Behrens", "Frau Bergmann")


def forget_surnames(h):
    h.source.lessons = [
        Lesson(*[getattr(lesson, name) for name in ("date", "day_of_week", "period", "subject", "teacher", "room", "class_name")], subject_name=lesson.subject_name, teacher_name=lesson.teacher_name, start_time=lesson.start_time, end_time=lesson.end_time)
        for lesson in h.source.lessons
    ]
    h.patch_teacher("BEH", surname="")
    h.poll()


def rename_teacher_without_surname(h):
    forget_surnames(h)
    h.patch_teacher("BEH", label="Frau Bergmann")


def teacher_label_plain_app(h):
    before, after = _flip(h, lambda h: h.lesson(1)["teacher_label"], rename_teacher_without_surname)
    assert (before, after) == ("Frau Behrens", "Frau Bergmann")
    assert h.lesson(1)["teacher_surname"] == ""


def teacher_label_plain_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["SUMMARY"], rename_teacher_without_surname)
    assert "Behrens" in before and "Frau Bergmann" in after and "Behrens" not in after


def teacher_label_plain_state(h):
    before, after = _flip(h, lambda h: h.state()["now_lesson"]["teacher"], rename_teacher_without_surname)
    assert (before, after) == ("Behrens", "Frau Bergmann")


def teacher_label_plain_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["summary"], rename_teacher_without_surname)
    assert "(Behrens)" in before and "(Frau Bergmann)" in after


def change_region(h):
    h.patch_connection(holiday_region="DE-BY")


def app_holidays(h):
    response = h.client.get("/api/holidays", params=dict(HOLIDAY_RANGE, connection=SCHOOL))
    assert response.status_code == 200, response.text
    return response.json()


def holiday_region_app(h):
    before, after = _flip(h, app_holidays, change_region)
    assert before["region"] == "DE-NI" and after["region"] == "DE-BY"
    assert before["days"]["2026-10-12"]["free"] is True and after["days"]["2026-10-12"]["free"] is False
    assert after["days"]["2026-11-18"]["free"] is True


def all_day_starts(h):
    return sorted(props["DTSTART"] for props in h.feed_events().values() if "T" not in props.get("DTSTART", ""))


def holiday_region_feed(h):
    before, after = _flip(h, all_day_starts, change_region)
    assert "20261012" in before and "20261012" not in after
    assert "20261118" in after


def holiday_region_school(h):
    before, after = _flip(h, lambda h: h.school(), change_region)
    assert before["region"] == "DE-NI" and before["next_holiday"]["start"] == "2026-10-12"
    assert after["region"] == "DE-BY" and after["next_holiday"]["start"] == "2026-11-18"


def holiday_region_events(h):
    starts = lambda h: sorted(item["start"] for item in h.events("holidays", **HOLIDAY_RANGE))
    before, after = _flip(h, starts, change_region)
    assert "2026-10-12" in before and "2026-10-12" not in after
    assert "2026-11-18" in after


def phones_app(h):
    phones = [{"label": "Office", "number": "+49 555 0100"}]
    before, after = _flip(h, lambda h: h.absences()["phones"], lambda h: h.patch_connection(phones=phones))
    assert before == [] and after == phones


def switch_language(h):
    h.patch_config(language="en")


def language_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(1))["DESCRIPTION"], switch_language)
    assert "Lehrkraft" in before and "Teacher" not in before
    assert "Teacher" in after and "Lehrkraft" not in after


def language_info(h):
    before, after = _flip(h, lambda h: h.info()["language"], switch_language)
    assert (before, after) == ("de", "en")


def language_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(1)["description"], switch_language)
    assert "Lehrkraft" in before and "Teacher" in after


def language_push(h):
    before, after = _flip(h, lambda h: h.push_after_change(), switch_language)
    assert before and "Stundenplan von" in before[0]["message"]
    assert after and "Timetable for" in after[0]["message"]


def notify_targets_push(h):
    before, after = _flip(h, lambda h: h.push_after_change(), lambda h: h.patch_config(notify_services=[SECOND_SERVICE]))
    assert [item["service"] for item in before] == [FIRST_SERVICE]
    assert [item["service"] for item in after] == [SECOND_SERVICE]


def mute_timetable(h):
    h.patch_config(notify_events={"timetable": False, "letters": True, "pinboard": True, "conferences": True, "messenger": True})


def notify_events_push(h):
    before, after = _flip(h, lambda h: h.push_after_change(), mute_timetable)
    assert len(before) == 1 and after == []


def short_name_app(h):
    before, after = _flip(h, lambda h: h.summary()["short_name"], lambda h: h.patch_connection(short_name="Alpha"))
    assert (before, after) == ("one", "Alpha")


def label_app(h):
    before, after = _flip(h, lambda h: h.summary()["name"], lambda h: h.patch_connection(label="Alpha School"))
    assert (before, after) == ("School One", "Alpha School")


def label_info(h):
    before, after = _flip(h, lambda h: h.info()["schools"][0]["name"], lambda h: h.patch_connection(label="Alpha School"))
    assert (before, after) == ("School One", "Alpha School")


def shrink_components(h):
    response = h.client.post(f"/api/calendar/subscriptions/{h.subscription['id']}", json={"components": ["school_holidays"]})
    assert response.status_code == 200, response.text


def has_lessons(events):
    return any("-p1-" in uid for uid in events)


def has_all_day(events):
    return any("T" not in props["DTSTART"] for props in events.values())


def components_feed(h):
    before, after = _flip(h, lambda h: h.feed_events(), shrink_components)
    assert has_lessons(before) and has_all_day(before)
    assert not has_lessons(after) and has_all_day(after)


def components_app(h):
    before, after = _flip(h, lambda h: h.subscriptions()[0]["components"], shrink_components)
    assert before == COMPONENTS and after == ["school_holidays"]


def rotate(h):
    response = h.client.post(f"/api/calendar/subscriptions/{h.subscription['id']}/rotate")
    assert response.status_code == 200, response.text
    h.rotated = response.json()


def rotate_feed(h):
    old_token = h.subscription["token"]
    before = set(h.feed_events())
    rotate(h)
    assert h.feed_response(old_token).status_code == 404
    assert h.feed_response(h.rotated["token"]).status_code == 200
    h.subscription = h.rotated
    assert set(h.feed_events()) == before


def rotate_app(h):
    before, after = _flip(h, lambda h: h.subscriptions()[0]["token"], rotate)
    assert before != after and after == h.rotated["token"]


def revoke(h):
    assert h.client.delete(f"/api/calendar/subscriptions/{h.subscription['id']}").status_code == 200


def revoke_feed(h):
    before, after = _flip(h, lambda h: h.feed_response().status_code, revoke)
    assert (before, after) == (200, 404)


def revoke_app(h):
    before, after = _flip(h, lambda h: len(h.subscriptions()), revoke)
    assert (before, after) == (1, 0)


def module_flags_app(h):
    flags = {"reported_modules": ["clubs"], "modules_card_hidden": {"until": NOW_EPOCH + 86400, "segments": ["clubs"]}}
    read = lambda h: {key: h.client.get("/api/config").json()[key] for key in flags}
    before, after = _flip(h, read, lambda h: h.patch_config(**flags))
    assert before == {"reported_modules": [], "modules_card_hidden": {}} and after == flags


def add_mark(h):
    response = h.client.post(
        "/api/marks",
        json={"child_key": CHILD_KEY, "date": WEDNESDAY_ISO, "period": 3, "subject_code": "D", "name": "Vocabulary"},
    )
    assert response.status_code == 200, response.text
    h.mark = response.json()


def remove_mark(h):
    assert h.client.delete(f"/api/marks/{h.mark['id']}").status_code == 200


def exam_mark_app(h):
    before, after = _flip(h, lambda h: h.marks(), add_mark)
    assert before == [] and after == [h.mark["id"]]
    remove_mark(h)
    assert h.marks() == []


def exam_mark_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(3))["SUMMARY"], add_mark)
    assert "Prüfung" not in before and "Prüfung Vocabulary" in after
    remove_mark(h)
    assert h.feed_event(_event_uid(3))["SUMMARY"] == before


def exam_mark_state(h):
    before, after = _flip(h, lambda h: h.state(), add_mark)
    assert before["next_exam"] is None and before["exams_upcoming"]["count"] == 0
    assert after["next_exam"]["name"] == "Vocabulary" and after["next_exam"]["start"] == "2026-09-02T09:45:00+02:00"
    assert after["exams_upcoming"]["count"] == 1
    remove_mark(h)
    assert h.state()["next_exam"] is None


def exam_mark_events(h):
    before, after = _flip(h, lambda h: h.events("exams"), add_mark)
    assert before == [] and [item["name"] for item in after] == ["Vocabulary"]
    remove_mark(h)
    assert h.events("exams") == []


def cancel_lesson(h):
    response = h.client.post("/api/cancellations", json={"child_key": CHILD_KEY, "date": WEDNESDAY_ISO, "period": 2})
    assert response.status_code == 200, response.text
    h.cancellation = response.json()


def undo_cancellation(h):
    assert h.client.delete(f"/api/cancellations/{h.cancellation['id']}").status_code == 200


def cancellation_app(h):
    before, after = _flip(h, lambda h: h.cancellations(), cancel_lesson)
    assert before == [] and after == [2]
    undo_cancellation(h)
    assert h.cancellations() == []


def cancellation_feed(h):
    before, after = _flip(h, lambda h: h.feed_event(_event_uid(2)), cancel_lesson)
    assert "Fällt aus" not in before["SUMMARY"] and before["TRANSP"] == "OPAQUE"
    assert after["SUMMARY"].startswith("Fällt aus") and after["TRANSP"] == "TRANSPARENT"
    undo_cancellation(h)
    assert h.feed_event(_event_uid(2))["SUMMARY"] == before["SUMMARY"]


def cancellation_state(h):
    before, after = _flip(h, lambda h: h.state(), cancel_lesson)
    assert before["next_lesson"]["period"] == 2 and before["changes_today"] == []
    assert after["next_lesson"]["period"] == 3
    assert [item["period"] for item in after["changes_today"]] == [2] and after["changes_today"][0]["cancelled"] is True
    assert after["timetable_changed_today"] is True
    undo_cancellation(h)
    assert h.state()["next_lesson"]["period"] == 2


def cancellation_events(h):
    before, after = _flip(h, lambda h: h.lesson_event(2)["cancelled"], cancel_lesson)
    assert (before, after) == (False, True)
    undo_cancellation(h)
    assert h.lesson_event(2)["cancelled"] is False


ABSENCE_BODY = {
    "type": "leave",
    "student_id": STUDENT_ID,
    "from_date": WEDNESDAY_ISO,
    "till_date": WEDNESDAY_ISO,
    "subject": "Dentist",
    "body": "Appointment",
}


def report_absence(h):
    response = h.client.post("/api/absences", json=ABSENCE_BODY)
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True, response.text
    h.absence = h.dsa.requests[LEAVE_PATH][-1]


def report_and_poll(h):
    report_absence(h)
    h.poll()


def report_accept_and_poll(h):
    report_absence(h)
    h.dsa.accept_all()
    h.poll()


def withdraw_absence(h):
    response = h.client.post("/api/absences/delete", json={"type": "leave", "id": h.absence["id"]})
    assert response.status_code == 200, response.text
    assert response.json().get("ok") is True, response.text


def absence_subjects(h):
    return [entry["subject"] for entry in h.absences()["entries"]]


def absence_app(h):
    before, after = _flip(h, absence_subjects, report_absence)
    assert before == [] and after == ["Dentist"]
    withdraw_absence(h)
    assert absence_subjects(h) == []


def absence_state(h):
    before, after = _flip(h, lambda h: h.state()["open_absences"], report_and_poll)
    assert before["count"] == 0
    assert after["count"] == 1 and after["items"][0]["start"] == WEDNESDAY_ISO and after["items"][0]["status"] == "open"
    withdraw_absence(h)
    h.poll()
    assert h.state()["open_absences"]["count"] == 0


def absence_uids(h):
    return [uid for uid in h.feed_events() if "-absence-" in uid]


def absence_feed(h):
    before, after = _flip(h, absence_uids, report_accept_and_poll)
    assert before == [] and len(after) == 1
    withdraw_absence(h)
    h.poll()
    assert absence_uids(h) == []


def absence_events(h):
    before, after = _flip(h, lambda h: h.events("absences"), report_accept_and_poll)
    assert before == [] and after[0]["start"] == WEDNESDAY_ISO and after[0]["kind"] == "leave"
    withdraw_absence(h)
    h.poll()
    assert h.events("absences") == []


LETTER_BODY = {"connection_id": SCHOOL, "letter_id": LETTER["letter_id"], "recipient_id": LETTER["recipient_id"]}


def archive_letter(h):
    response = h.client.post("/api/letters/archive", json=LETTER_BODY)
    assert response.status_code == 200 and response.json().get("ok") is True, response.text


def restore_letter(h):
    response = h.client.post("/api/letters/restore", json=LETTER_BODY)
    assert response.status_code == 200 and response.json().get("ok") is True, response.text


def letter_titles(h):
    return [entry["title"] for entry in h.letters_list()], [entry["title"] for entry in h.letters_list("archive")]


def letter_archive_app(h):
    before, after = _flip(h, letter_titles, archive_letter)
    assert before == (["Field trip"], []) and after == ([], ["Field trip"])
    restore_letter(h)
    assert letter_titles(h) == before


def archive_and_poll(h):
    archive_letter(h)
    h.poll()


def letter_archive_state(h):
    before, after = _flip(h, lambda h: h.state()["unread_letters"], archive_and_poll)
    assert before["count"] == 1 and before["items"][0]["title"] == "Field trip"
    assert after["count"] == 0
    restore_letter(h)
    h.poll()
    assert h.state()["unread_letters"]["count"] == 1


def confirm_letter(h):
    response = h.client.post("/api/letters/confirm", json=LETTER_BODY)
    assert response.status_code == 200 and response.json().get("ok") is True, response.text


def letter_confirm_app(h):
    before, after = _flip(h, lambda h: h.letters_list()[0]["confirmation"], confirm_letter)
    assert before["open"] is True and before["done"] is False
    assert after["open"] is False and after["done"] is True and after["confirmed_at"]


def new_letter_push(h):
    start = len(h.sent)
    h.letters.current.append(dict(LETTER, letter_id="letter-2", recipient_id="recipient-2", title="Sports day", unread=True))
    h.poll()
    return h.sent[start:]


def letter_confirm_push(h):
    before, after = _flip(h, new_letter_push, switch_language)
    assert len(before) == 1 and before[0]["service"] == FIRST_SERVICE
    assert after == []
    h.letters.current.append(dict(LETTER, letter_id="letter-3", recipient_id="recipient-3", title="Fair", unread=True))
    h.poll()
    assert h.sent[-1]["message"] != before[0]["message"]


def relayout_overview(h):
    blocks = h.client.get("/api/config").json()["overview_blocks"]
    kept = [dict(block) for block in blocks if block["key"] != "week"]
    letters = next(block for block in kept if block["key"] == "letters")
    kept.remove(letters)
    kept.insert(0, letters)
    for block in kept:
        if block["key"] == "today":
            block["size"] = "compact"
    kept.append({"key": "not-a-real-block"})
    h.patch_config(overview_blocks=kept)


def overview_blocks_app(h):
    before, after = _flip(h, lambda h: h.client.get("/api/config").json()["overview_blocks"], relayout_overview)
    assert [block["key"] for block in before][:1] == ["today"]
    assert [block["key"] for block in after][:1] == ["letters"]
    after_keys = [block["key"] for block in after]
    assert "week" not in after_keys and "not-a-real-block" not in after_keys
    assert next(block for block in after if block["key"] == "today")["size"] == "compact"


def reorder_navigation(h):
    h.patch_config(navigation=["absence", "timetable", "bogus-area"])


def navigation_app(h):
    before, after = _flip(h, lambda h: h.client.get("/api/config").json()["navigation"], reorder_navigation)
    assert before[:2] == ["timetable", "absence"]
    assert after[:2] == ["absence", "timetable"]
    assert "bogus-area" not in after
    assert set(after) == set(before)


def disable_timetable_module(h):
    h.patch_config(modules_disabled=["timetable"])


def modules_disabled_info(h):
    before, after = _flip(h, lambda h: h.info()["schools"][0]["disabled"], disable_timetable_module)
    assert before["timetable"] is False
    assert after["timetable"] is True


PARALLEL_COURSES = (("E1", "CCC", "Englisch", "Frau Castor"), ("E2", "DDD", "Englisch", "Herr Dachs"))
CHOSEN_COURSE = "E1|CCC"


def add_parallel_courses(h):
    h.source.lessons = list(h.source.lessons) + [
        _lesson(WEDNESDAY, 3, 3, code, teacher, name, teacher_name, teacher_name.split()[-1], "09:45")
        for code, teacher, name, teacher_name in PARALLEL_COURSES
    ]
    h.poll()


def choose_courses(h):
    listed = h.client.get("/api/timetable/courses", params={"child": CHILD_KEY})
    assert listed.status_code == 200, listed.text
    known = [entry["key"] for entry in listed.json()["courses"]]
    assert sorted(known) == ["D|BEH", "E1|CCC", "E2|DDD"]
    response = h.client.post("/api/timetable/courses", json={"child": CHILD_KEY, "chosen": [CHOSEN_COURSE], "known": known})
    assert response.status_code == 200 and response.json()["ok"] is True, response.text


def wednesday_codes(h, period):
    return sorted(entry["subject_code"] for entry in h.timetable()["lessons"] if entry["date"] == WEDNESDAY and entry["period"] == period)


def course_filter_app(h):
    add_parallel_courses(h)
    before, after = _flip(h, lambda h: (wednesday_codes(h, 3), wednesday_codes(h, 1)), choose_courses)
    assert before == (["D", "E1", "E2"], ["D"])
    assert after == (["E1"], [])
    assert h.timetable()["courses"]["chosen"] is True


def feed_summaries(h, period):
    return sorted(props["SUMMARY"] for uid, props in h.feed_events().items() if f"-20260902-p{period}-" in uid)


def course_filter_feed(h):
    add_parallel_courses(h)
    before, after = _flip(h, lambda h: (feed_summaries(h, 3), feed_summaries(h, 1)), choose_courses)
    assert len(before[0]) == 3 and any("Herr Dachs" in summary or "Dachs" in summary for summary in before[0])
    assert len(after[0]) == 1 and "Castor" in after[0][0]
    assert before[1] and after[1] == []


def course_filter_state(h):
    add_parallel_courses(h)
    before, after = _flip(h, lambda h: h.state(), choose_courses)
    assert before["now_lesson"]["subject"] == "Deutsch"
    assert after["now_lesson"] is None
    assert after["next_lesson"]["period"] == 2


def course_filter_events(h):
    add_parallel_courses(h)
    read = lambda h: sorted(item["subject_code"] for item in h.events("lessons") if "-20260902-p3-" in item["uid"])
    before, after = _flip(h, read, choose_courses)
    assert before == ["D", "E1", "E2"] and after == ["E1"]


def passphrase_secrets(h):
    os.environ[PASSPHRASE_ENV] = "correct horse battery staple"
    try:
        store = Store(h.store.dir.parent / "sealed")
        add_school(store, SCHOOL_URL, connection_id=SCHOOL)
        assert Store(store.dir).load_secrets(SCHOOL)["username"] == DEFAULT_SECRETS["username"]
        os.environ[PASSPHRASE_ENV] = "another passphrase"
        assert Store(store.dir).load_secrets(SCHOOL) == {}
    finally:
        os.environ.pop(PASSPHRASE_ENV, None)


@dataclass(frozen=True)
class Row:
    name: str
    keys: tuple
    cells: dict = field(default_factory=dict)


ROWS = (
    Row("period_time", ("period_times",), {"app_timetable": period_time_app, "feed": period_time_feed, "integration_state": period_time_state, "integration_events": period_time_events}),
    Row("period_duration", ("period_grid",), {"app_timetable": period_duration_app, "feed": period_duration_feed}),
    Row("own_entry", ("own_entries",), {"app_periods": own_entry_app, "feed": own_entry_feed}),
    Row("own_entries_ha", ("own_entries_ha",), {"app_connections": own_entries_ha_app, "integration_info": own_entries_ha_info, "integration_events": own_entries_ha_events}),
    Row("subject_name", ("subjects",), {"app_timetable": subject_name_app, "feed": subject_name_feed, "integration_state": subject_name_state, "integration_events": subject_name_events}),
    Row("subject_code_derived", ("subjects",), {"app_timetable": subject_code_derived_app, "integration_events": subject_code_derived_events}),
    Row("subject_code_edit", ("subjects",), {"app_timetable": subject_code_edit_app, "integration_state": subject_code_edit_state, "integration_events": subject_code_edit_events}),
    Row("subject_color", ("subjects",), {"app_timetable": subject_color_app, "feed": subject_color_feed, "integration_events": subject_color_events}),
    Row("subject_color_hex", ("subjects",), {"app_timetable": subject_color_hex_app, "feed": subject_color_hex_feed, "integration_events": subject_color_hex_events}),
    Row("subject_color_derived_code", ("subjects",), {"app_timetable": subject_color_derived_app, "feed": subject_color_derived_feed, "integration_events": subject_color_derived_events}),
    Row("teacher_label", ("teachers",), {"app_timetable": teacher_label_app}),
    Row("teacher_label_without_surname", ("teachers",), {"app_timetable": teacher_label_plain_app, "feed": teacher_label_plain_feed, "integration_state": teacher_label_plain_state, "integration_events": teacher_label_plain_events}),
    Row("holiday_region", ("holiday_region",), {"app_holidays": holiday_region_app, "feed": holiday_region_feed, "integration_school": holiday_region_school, "integration_events": holiday_region_events}),
    Row("phones", ("phones",), {"app_absences": phones_app}),
    Row("course_filter", ("course_filters",), {"app_timetable": course_filter_app, "feed": course_filter_feed, "integration_state": course_filter_state, "integration_events": course_filter_events}),
    Row("language", ("language",), {"feed": language_feed, "integration_info": language_info, "integration_events": language_events, "push": language_push}),
    Row("notify_targets", ("notify_services",), {"push": notify_targets_push}),
    Row("notify_events", ("notify_events",), {"push": notify_events_push}),
    Row("short_name", ("short_name",), {"app_connections": short_name_app}),
    Row("label", ("label",), {"app_connections": label_app, "integration_info": label_info}),
    Row("calendar_components", (), {"feed": components_feed, "app_calendar": components_app}),
    Row("subscription_rotate", (), {"feed": rotate_feed, "app_calendar": rotate_app}),
    Row("subscription_delete", (), {"feed": revoke_feed, "app_calendar": revoke_app}),
    Row("module_card_flags", ("reported_modules", "modules_card_hidden"), {"app_config": module_flags_app}),
    Row("overview_blocks", ("overview_blocks",), {"app_config": overview_blocks_app}),
    Row("navigation", ("navigation",), {"app_config": navigation_app}),
    Row("modules_disabled", ("modules_disabled",), {"integration_info": modules_disabled_info}),
    Row("passphrase", (), {"secrets": passphrase_secrets}),
    Row("action_exam_mark", (), {"app_marks": exam_mark_app, "feed": exam_mark_feed, "integration_state": exam_mark_state, "integration_events": exam_mark_events}),
    Row("action_cancellation", (), {"app_cancellations": cancellation_app, "feed": cancellation_feed, "integration_state": cancellation_state, "integration_events": cancellation_events}),
    Row("action_absence", (), {"app_absences": absence_app, "integration_state": absence_state, "feed": absence_feed, "integration_events": absence_events}),
    Row("action_letter_archive", (), {"app_letters": letter_archive_app, "integration_state": letter_archive_state}),
    Row("action_letter_confirm", (), {"app_letters": letter_confirm_app, "push": letter_confirm_push}),
)

EXEMPT_ROWS = {
    "teacher_surname": "learned from the school timetable, not editable in the app; the feed and the rows prefer it over the label (test_calendar_feed.py)",
    "theme": "browser-only attribute, covered by e2e/settings-matrix.spec.js and frontend/tests/themeColor.test.js",
    "child_switch": "app navigation state, covered by e2e/settings-matrix.spec.js and tests/card/settingsMatrix.test.js",
    "school_filter_chips": "app navigation state, covered by e2e/settings-matrix.spec.js",
}

EXEMPT_KEYS = {
    "schema_version": "internal store version",
    "connections": "container of the per-school entries",
    "school_url": "fixed by the wizard, not a setting",
    "school_name": "learned from the school profile, not a setting",
    "created_at": "internal timestamp",
    "setup_complete": "internal wizard flag",
    "children": "chosen in the wizard, propagation covered by test_children_page.py and e2e/two-schools.spec.js",
    "poll_state": "internal poller bookkeeping",
    "timetable_source": "learned from the school answers, covered by test_timetable_source.py",
    "children_state": "learned from the child list answers, covered by test_several_schools.py",
}

SHARED_SCHEMA = Path(__file__).resolve().parents[2] / "tests" / "settings-schema.json"


def schema_keys():
    return set(DEFAULT_CONFIG) | {key for key in CONNECTION_DEFAULTS if key != "id"}


CELLS = [pytest.param(row, surface, id=f"{row.name}-{surface}") for row in ROWS for surface in row.cells]


@pytest.mark.parametrize("row, surface", CELLS)
def test_a_change_reaches_the_surface(harness, row, surface):
    row.cells[surface](harness)


def test_every_config_key_has_a_matrix_row_or_a_reason():
    covered = {key for row in ROWS for key in row.keys}
    schema = schema_keys()
    missing = sorted(key for key in schema if key not in covered and key not in EXEMPT_KEYS)
    assert missing == [], f"config keys without a matrix row or an exemption: {missing}"
    stale = sorted(key for key in EXEMPT_KEYS if key not in schema)
    assert stale == [], f"exemptions for keys that no longer exist: {stale}"
    assert not (covered & set(EXEMPT_KEYS))


def test_every_row_name_is_unique_and_exempt_rows_are_not_covered():
    names = [row.name for row in ROWS]
    assert len(names) == len(set(names))
    assert not (set(names) & set(EXEMPT_ROWS))


def test_the_schema_file_the_js_matrices_read_matches_the_store():
    shared = json.loads(SHARED_SCHEMA.read_text(encoding="utf-8"))
    expected = {"keys": sorted(schema_keys()), "internal": EXEMPT_KEYS}
    assert shared == expected, f"tests/settings-schema.json is stale, write it as: {json.dumps(expected, indent=2)}"
