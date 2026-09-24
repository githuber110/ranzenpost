import copy
import logging
from datetime import date

import pytest

from app import modules
from app.iserv.errors import REASON_TIMEOUT, DataError, LoginError, OutageError
from app.iserv.messenger import STAGE_MATRIX, STAGE_NO_CREDENTIALS, MessengerStageError
from app.poller import Poller
from app.store import Store
from tests.support import add_school, connection_service
from tests.test_poller import FakeService, NotifierRecorder, _display_lesson, _timetable
from tests.test_poller_modules import CHILD_ID, NOW_EPOCH, RAW_CHILD_ID, SCHOOL, ModularService, _poller, _store
from tests.test_school_timetable import ME, SchoolApp

SECRET = "secret-value https://school.example/?token=abc"


def _dsa_entry(entry_id, weekday, period, name, acronym, teacher, room):
    return {
        "id": entry_id,
        "courseSubject": {
            "id": entry_id,
            "teachers": [{"forename": "A", "surname": "B", "externalId": teacher}],
            "subject": {"id": entry_id, "name": name, "acronym": acronym, "hexColor": "#123456"},
            "course": {"id": 7001, "name": "Klasse 01D", "type": "class"},
            "type": "lesson",
        },
        "timeTableSlot": {"number": period, "startTime": "08:00", "endTime": "08:45"},
        "weekday": weekday,
        "room": {"name": room},
    }


REGULAR = [
    _dsa_entry(1, 0, 1, "Musik", "", "LEH", "R1"),
    _dsa_entry(2, 0, 2, "Deutsch", "D", "BEI", "R2"),
    _dsa_entry(3, 1, 1, "Mathematik", "", "MUE", "R3"),
    _dsa_entry(4, 2, 1, "Chor", "", "LEH", "Aula"),
]
LATER = {
    1: [_dsa_entry(5, 3, 1, "Musical", "", "LEH", "Aula")],
    2: [_dsa_entry(6, 3, 2, "Mathe-AG", "", "MUE", "R3")],
}
MISSING = {3: {4}}


class WeeklySchoolApp(SchoolApp):
    def __init__(self, today):
        super().__init__(me=ME, timetable=None)
        self.today = today

    def current_timetable(self, reference, course_ids, substitutions=False):
        offset = (reference - self.today).days // 7
        entries = [entry for entry in REGULAR if entry["id"] not in MISSING.get(offset, set())]
        entries += LATER.get(offset, [])
        return {"students": [{"student": {"id": 500001}, "entries": copy.deepcopy(entries)}], "vacations": []}


class FeedRegistry:
    def __init__(self, key):
        self.key = key

    def children_with_timetable(self):
        return {self.key}

    def children_with_component(self, component):
        return set()


TIMETABLE_ONLY = {"modules": {name: name == modules.TIMETABLE for name in modules.MODULES}}


def _school_app_service(data_dir, connection_id=None):
    base = Store(data_dir)
    if connection_id is None:
        connection_id = add_school(base, "https://school.example")
    service = connection_service(base, connection_id, lambda url: None)
    app = WeeklySchoolApp(date.today())
    service._dsa = lambda: app
    service.modules = lambda: TIMETABLE_ONLY
    service.refresh_modules = lambda: TIMETABLE_ONLY
    return service, connection_id


def _poll_school_app(service, notifier):
    registry = FeedRegistry(service.child_key("500001"))
    Poller(service, notifier=notifier, store=service.store, registry=registry).poll_once()


def test_a_restart_on_the_school_app_timetable_pushes_nothing(tmp_path):
    notifier = NotifierRecorder()
    first, connection_id = _school_app_service(tmp_path / "data")
    _poll_school_app(first, notifier)
    _poll_school_app(first, notifier)
    assert notifier.calls == []

    restarted, _ = _school_app_service(tmp_path / "data", connection_id)
    _poll_school_app(restarted, notifier)
    _poll_school_app(restarted, notifier)
    assert notifier.calls == []


def _plan_lessons(subject_codes):
    return [
        _display_lesson(period=period, subject_code=code, teacher_code="ABC", room="R1")
        for period, code in enumerate(subject_codes, start=1)
    ]


def test_a_plan_push_names_the_fields_that_differ_and_how_often_never_the_values(caplog):
    from tests.test_poller import FakeStore

    store = FakeStore()
    notifier = NotifierRecorder()
    timetables = {"c1": _timetable("t1", lessons=_plan_lessons(["MA", "DE", "EN", "SP"]))}
    service = FakeService([{"child_id": "c1", "name": "Alice"}], timetables, store=store)
    Poller(service, notifier=notifier, store=store).poll_once()
    timetables["c1"] = _timetable("t2", lessons=_plan_lessons(["QX", "QY", "QZ", "SP"]))
    with caplog.at_level(logging.INFO, logger="app.poller"):
        Poller(service, notifier=notifier, store=store).poll_once()
    assert len(notifier.calls) == 1
    lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("push ")]
    assert lines == [f"push timetable plan school#{service.id} child#c1: subject_code differs in 3 lessons"]
    assert not any(value in lines[0] for value in ("QX", "MA", "Alice"))


def test_a_plan_push_without_stored_field_detail_says_so(caplog):
    from tests.test_poller import FakeStore

    store = FakeStore()
    notifier = NotifierRecorder()
    timetables = {"c1": _timetable("t1", lessons=_plan_lessons(["MA"]))}
    service = FakeService([{"child_id": "c1", "name": "Alice"}], timetables, store=store)
    Poller(service, notifier=notifier, store=store).poll_once()
    config = store.load_config()
    config["poll_state"][f"{service.id}:c1"].pop("plan_fields")
    store.save_config(config)
    timetables["c1"] = _timetable("t2", lessons=_plan_lessons(["DE"]))
    with caplog.at_level(logging.INFO, logger="app.poller"):
        Poller(service, notifier=notifier, store=store).poll_once()
    assert f"push timetable plan school#{service.id} child#c1: no field detail stored yet" in caplog.text


class FailingService(ModularService):
    def __init__(self, store, fail):
        super().__init__(store, {})
        self.fail = fail

    def _maybe(self, area, **context):
        error = self.fail.get(area)
        if error is not None and (area != "week" or context.get("offset", 0) > 0):
            raise error

    def children(self):
        self._maybe("children")
        return super().children()

    def timetable(self, child_id, week_offset=0):
        if week_offset == 0:
            self._maybe("timetable")
        self._maybe("week", offset=week_offset)
        return super().timetable(child_id, week_offset)

    def letters(self, tab="current"):
        self._maybe("letters")
        return super().letters(tab)

    def pinboard(self):
        self._maybe("pinboard")
        return super().pinboard()

    def conferences(self):
        self._maybe("conferences")
        return super().conferences()

    def messenger_unread_pulse(self):
        self._maybe("messenger")
        return super().messenger_unread_pulse()

    def absences_overview(self):
        self._maybe("absences")
        return super().absences_overview()


ERROR_PATHS = [
    ("timetable", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "timetable", f"child#{RAW_CHILD_ID}", "RuntimeError"]),
    ("week", DataError(SECRET, message_key="api.timetable.unreadable"), logging.WARNING, ["school#" + SCHOOL, "week 1", "DataError/api.timetable.unreadable"]),
    ("letters", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "letters failed", "RuntimeError"]),
    ("pinboard", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "pinboard failed", "RuntimeError"]),
    ("conferences", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "conferences failed", "RuntimeError"]),
    ("messenger", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "messenger failed", "RuntimeError"]),
    ("messenger", MessengerStageError(STAGE_MATRIX, note=SECRET), logging.WARNING, ["school#" + SCHOOL, "messenger failed", f"MessengerStageError/{STAGE_MATRIX}"]),
    ("messenger", MessengerStageError(STAGE_NO_CREDENTIALS, note=SECRET), logging.INFO, ["school#" + SCHOOL, "messenger skipped", STAGE_NO_CREDENTIALS]),
    ("absences", RuntimeError(SECRET), logging.WARNING, ["school#" + SCHOOL, "absences failed", "RuntimeError"]),
    ("children", LoginError(SECRET), logging.WARNING, ["school#" + SCHOOL, "sign-in failed", "LoginError/bad_credentials"]),
    ("children", OutageError(REASON_TIMEOUT, note=SECRET), logging.WARNING, ["school#" + SCHOOL, "outage", f"OutageError/{REASON_TIMEOUT}"]),
    ("children", RuntimeError(SECRET), logging.WARNING, [SCHOOL, "stopped with", "RuntimeError"]),
]


@pytest.mark.parametrize("area,error,level,parts", ERROR_PATHS, ids=[f"{row[0]}-{type(row[1]).__name__}-{index}" for index, row in enumerate(ERROR_PATHS)])
def test_every_poller_error_path_logs_its_own_line_with_area_and_kind(tmp_path, caplog, area, error, level, parts):
    store = _store(tmp_path)
    service = FailingService(store, {area: error})
    with caplog.at_level(logging.DEBUG):
        _poller(store, service).poll_once()
    matching = [
        record
        for record in caplog.records
        if record.name == "app.poller" and all(part in record.getMessage() for part in parts)
    ]
    assert matching, [record.getMessage() for record in caplog.records]
    assert matching[0].levelno == level
    assert "secret-value" not in caplog.text
    assert "token=" not in caplog.text


def test_a_backoff_skip_logs_an_info_line(tmp_path, caplog, monkeypatch):
    store = _store(tmp_path)
    service = FailingService(store, {})
    monkeypatch.setattr(Poller, "_outage_backoff_active", lambda self, connection, now_epoch: True)
    with caplog.at_level(logging.INFO):
        _poller(store, service).poll_once()
    skipped = [record for record in caplog.records if f"school#{SCHOOL} skipped: outage backoff" in record.getMessage()]
    assert skipped and skipped[0].levelno == logging.INFO
    ends = [record.getMessage() for record in caplog.records if record.getMessage().startswith("poll end after ")]
    assert ends[0].endswith(": 1 schools, 1 errors (school: outage backoff), 0 changes")


def test_the_poll_end_line_names_each_error(tmp_path, caplog):
    store = _store(tmp_path)
    service = FailingService(store, {"letters": RuntimeError(SECRET), "timetable": RuntimeError(SECRET)})
    with caplog.at_level(logging.INFO):
        _poller(store, service).poll_once()
    ends = [record.getMessage() for record in caplog.records if record.getMessage().startswith("poll end after ")]
    assert len(ends) == 1
    assert ends[0].endswith(": 1 schools, 1 errors (timetable: RuntimeError, letters: RuntimeError), 0 changes")


def test_a_clean_poll_end_line_keeps_its_short_form(tmp_path, caplog):
    store = _store(tmp_path)
    service = FailingService(store, {})
    with caplog.at_level(logging.INFO):
        _poller(store, service).poll_once()
    ends = [record.getMessage() for record in caplog.records if record.getMessage().startswith("poll end after ")]
    assert ends[0].endswith(": 1 schools, 0 errors, 0 changes")


class GrowingService(ModularService):
    def __init__(self, store):
        super().__init__(store, {})
        self.round = 0
        self.lessons = [_display_lesson(date="2026-09-02")]

    def children(self):
        if self.round == 2:
            raise LoginError("refused")
        return super().children()

    def timetable(self, child_id, week_offset=0):
        return _timetable("t", lessons=self.lessons, start_date="31.08.2026")

    def letters(self, tab="current"):
        extra = [{"letter_id": f"n{self.round}", "recipient_id": "r", "title": "New", "unread": True}]
        return {"letters": super().letters(tab)["letters"] + (extra if self.round else [])}

    def pinboard(self):
        extra = [{"id": 100 + self.round, "title": "New", "unread": True}]
        return {"feed": super().pinboard()["feed"] + (extra if self.round else [])}

    def conferences(self):
        extra = [{"cells": [f"2026-11-0{self.round + 1}", "Talk"]}]
        return {"empty": False, "items": super().conferences()["items"] + (extra if self.round else [])}

    def messenger_unread_pulse(self):
        return 3 + self.round


def test_no_push_leaves_the_poller_without_its_info_line(tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(Poller, "_messenger_push_ready", lambda self: True)
    store = _store(tmp_path)
    service = GrowingService(store)
    sent = []

    def recorder(event):
        return lambda name, message: sent.append(event) or True

    notifiers = {event: recorder(event) for event in ("timetable", "letters", "pinboard", "conferences", "auth", "messenger", "outage")}
    with caplog.at_level(logging.INFO, logger="app.poller"):
        for round_number in range(3):
            service.round = round_number
            if round_number == 1:
                service.lessons = [_display_lesson(date="2026-09-02", room="R9")]
            poller = _poller(store, service)
            poller.notifiers = notifiers
            poller.poll_once()
    pushed = [record.getMessage() for record in caplog.records if record.getMessage().startswith("push ")]
    assert sorted(sent) == sorted(line.split(" ")[1] for line in pushed)
    assert {"timetable", "letters", "pinboard", "conferences", "messenger", "auth"} <= set(sent)
    assert f"push timetable plan school#{SCHOOL} child#{RAW_CHILD_ID}: room differs in 1 lessons" in pushed
    assert f"push letters school#{SCHOOL}: 1 new" in pushed
    assert f"push messenger school#{SCHOOL}: 1 new, 4 unread" in pushed
    assert f"push auth school#{SCHOOL}: sign-in bad_credentials" in pushed
    assert "Alex" not in caplog.text
