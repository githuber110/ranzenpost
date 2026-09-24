import logging
from datetime import datetime, timezone

import requests

from app import integration, modules
from app.iserv.errors import OutageError
from app.poller import Poller
from app.store import Store
from app.subscriptions import COMPONENT_ABSENCES, COMPONENT_TIMETABLE, SubscriptionRegistry

from tests.support import add_school, connection_service
from tests.test_poller import _display_lesson, _timetable
from tests.test_service_modules import (
    AUTHENTICATE_ANSWER,
    MESSENGER_PAGE,
    MESSENGER_PAGE_WITHOUT_CREDENTIALS,
    MESSENGER_PAGE_WITHOUT_DATA,
    ProbeClient,
    SchoolApp,
)

SCHOOL = "a1b2c3d4"
RAW_CHILD_ID = "child-uuid-a"
CHILD_ID = f"{SCHOOL}:{RAW_CHILD_ID}"
NOW_EPOCH = int(datetime(2026, 9, 2, 6, 0, tzinfo=timezone.utc).timestamp())


def registry(**flags):
    return {
        "modules": {name: flags.get(name, True) for name in modules.MODULES},
        "unknown": [],
        "checked_at": 100,
        "iserv_version": "",
    }


class ModularService:
    def __init__(self, store, available):
        self.store = store
        self.id = SCHOOL
        self.registry = registry(**available)
        self.calls = []
        self.refreshes = 0

    def is_configured(self):
        return True

    def modules(self):
        return self.registry

    def refresh_modules(self, force=False):
        self.refreshes += 1
        return self.registry

    def children(self):
        self.calls.append("children")
        return [{"child_id": RAW_CHILD_ID, "name": "Alex Sample", "student_id": 7}]

    def timetable(self, child_id, week_offset=0):
        self.calls.append(("timetable", child_id, week_offset))
        return _timetable("02.09.2026 06:00", lessons=[_display_lesson(date="2026-09-02")], start_date="31.08.2026")

    def letters(self, tab="current"):
        self.calls.append("letters")
        return {"letters": [{"letter_id": "a", "recipient_id": "r", "title": "Trip", "unread": True}]}

    def enrich_letters_search(self, tab="current"):
        self.calls.append("enrich_letters_search")

    def pending_confirmation_keys(self, tab="current"):
        return set()

    def pinboard(self):
        self.calls.append("pinboard")
        return {"feed": [{"id": 1, "title": "Post", "unread": True}]}

    def conferences(self):
        self.calls.append("conferences")
        return {"empty": False, "items": [{"cells": ["2026-11-05", "Talk"]}]}

    def messenger_unread_pulse(self):
        self.calls.append("messenger")
        return 3

    def absences_overview(self):
        self.calls.append("absences")
        return {
            "children": [{"id": 7, "name": "Alex Sample"}],
            "entries": [
                {
                    "id": 1,
                    "kind": "sick",
                    "student_id": 7,
                    "status": "open",
                    "from_date": "2026-09-02",
                    "till_date": "2026-09-02",
                }
            ],
        }

    def me(self):
        return {"school_name": "Sample School"}


def _store(tmp_path):
    store = Store(tmp_path / "data")
    store.add_connection(
        "https://school-one.example",
        connection_id=SCHOOL,
        setup_complete=True,
        holiday_region="DE-NI",
        children=[{"child_id": RAW_CHILD_ID, "name": "Alex Sample", "class_name": "3b"}],
    )
    return store


def _school_state(store):
    return integration.school_state(store, SCHOOL)


def _poller(store, service):
    subscriptions = SubscriptionRegistry(store)
    subscriptions.create(CHILD_ID, [COMPONENT_TIMETABLE, COMPONENT_ABSENCES], "", "")
    return Poller(service, store=store, registry=subscriptions, clock=lambda: NOW_EPOCH)


def _names(calls):
    return [call[0] if isinstance(call, tuple) else call for call in calls]


def test_every_module_is_polled_when_everything_is_available(tmp_path):
    store = _store(tmp_path)
    service = ModularService(store, {})
    _poller(store, service).poll_once()
    names = _names(service.calls)
    assert {"timetable", "letters", "pinboard", "conferences", "messenger", "absences"} <= set(names)
    assert service.refreshes == 1


def test_missing_modules_are_never_requested(tmp_path, caplog):
    store = _store(tmp_path)
    service = ModularService(store, {"letters": False, "pinboard": False, "conferences": False, "messenger": False, "absences": False})
    with caplog.at_level(logging.DEBUG):
        events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert "letters" not in names
    assert "enrich_letters_search" not in names
    assert "pinboard" not in names
    assert "conferences" not in names
    assert "messenger" not in names
    assert "absences" not in names
    assert "timetable" in names
    assert [entry for entry in events if isinstance(entry, dict) and entry.get("error")] == []
    assert [record for record in caplog.records if record.name.startswith("app.")] == []


def test_a_missing_timetable_skips_the_timetable_reads_but_keeps_the_rest(tmp_path):
    store = _store(tmp_path)
    service = ModularService(store, {"timetable": False})
    events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert "timetable" not in names
    assert {"letters", "pinboard", "conferences", "messenger", "absences"} <= set(names)
    assert [entry for entry in events if "child_key" in entry] == []
    snapshot = store.load_calendar_snapshot()
    assert "weeks" not in (snapshot.get("children") or {}).get(CHILD_ID, {})
    assert len(snapshot["children"][CHILD_ID]["absences"]) == 1


def test_the_snapshot_of_a_module_that_went_missing_is_emptied(tmp_path):
    store = _store(tmp_path)
    service = ModularService(store, {})
    _poller(store, service).poll_once()
    snapshot = store.load_calendar_snapshot()
    assert snapshot["children"][CHILD_ID]["weeks"]
    assert snapshot["children"][CHILD_ID]["absences"]
    state = _school_state(store)
    assert [item["title"] for item in state["letters"]] == ["Trip"]
    assert [item["title"] for item in state["posts"]] == ["Post"]
    assert state["conferences"]

    service.registry = registry(timetable=False, absences=False, letters=False, pinboard=False, conferences=False)
    _poller(store, service).poll_once()
    snapshot = store.load_calendar_snapshot()
    assert snapshot["children"][CHILD_ID].get("weeks", {}) == {}
    assert snapshot["children"][CHILD_ID]["absences"] == []
    state = _school_state(store)
    assert state["letters"] == [] and state["posts"] == [] and state["conferences"] == []
    assert state["last_poll_ok"] is True
    assert integration.state_of(store)["last_poll_ok"] is True


def test_no_module_at_all_still_records_a_clean_poll(tmp_path):
    store = _store(tmp_path)
    service = ModularService(store, {name: False for name in modules.MODULES})
    events = _poller(store, service).poll_once()
    assert service.calls == []
    assert events == []
    state = integration.state_of(store)
    assert state["last_poll_ok"] is True
    assert state["last_error"] == ""


class BareService(ModularService):
    modules = None
    refresh_modules = None


def test_a_service_without_a_registry_polls_everything(tmp_path):
    store = _store(tmp_path)
    service = BareService(store, {})
    _poller(store, service).poll_once()
    assert {"timetable", "letters", "pinboard", "conferences", "messenger", "absences"} <= set(_names(service.calls))


def test_a_module_missing_at_one_poll_and_present_at_the_next_is_fetched_from_then_on(tmp_path):
    store = _store(tmp_path)
    service = ModularService(store, {"letters": False})
    poller = _poller(store, service)
    poller.poll_once()
    assert "letters" not in _names(service.calls)
    assert _school_state(store)["letters"] == []

    service.registry = registry(letters=True)
    service.calls.clear()
    poller.poll_once()
    assert "letters" in _names(service.calls)
    assert [item["title"] for item in _school_state(store)["letters"]] == ["Trip"]
    assert service.refreshes == 2


def _real_school(tmp_path, messenger_page, authenticate=None):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school-one.example")
    others = [
        path
        for name in modules.MODULES
        if name != modules.MESSENGER
        for path, _ in modules.probes_of(name, datetime.fromtimestamp(NOW_EPOCH).date())
    ] + [modules.LEGACY_TIMETABLE_PATH]
    holder = {}

    def factory(url):
        holder["client"] = ProbeClient(url, missing=others, messenger_page=messenger_page, authenticate=authenticate)
        return holder["client"]

    service = connection_service(store, connection_id, factory)
    service._dsa = lambda: SchoolApp()
    pulses = []
    service.messenger_unread_pulse = lambda: pulses.append("messenger") or 0
    return store, service, pulses, holder


def _warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


def _registry_lines(caplog):
    return [record.getMessage() for record in caplog.records if "modules available" in record.getMessage()]


def _authenticate_calls(holder):
    return [path for path in holder["client"].calls if "authenticate" in path]


def test_a_messenger_page_without_data_and_without_authenticate_is_quietly_missing_and_never_polled(tmp_path, caplog):
    store, service, pulses, holder = _real_school(tmp_path, MESSENGER_PAGE_WITHOUT_DATA)
    with caplog.at_level(logging.DEBUG):
        assert service.check_connection() == "ok"
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.MESSENGER] is False
    assert pulses == []
    assert _warnings(caplog) == []
    assert _registry_lines(caplog) == [f"school#{service.id} modules available: none; missing: timetable, letters, pinboard, absences, conferences, messenger; not supported: 1 (mail); unknown: 0"]
    assert len(_authenticate_calls(holder)) == 2 * 3


def test_a_messenger_page_without_data_whose_authenticate_call_hands_out_credentials_is_polled(tmp_path, caplog):
    store, service, pulses, holder = _real_school(tmp_path, MESSENGER_PAGE_WITHOUT_DATA, authenticate=AUTHENTICATE_ANSWER)
    with caplog.at_level(logging.DEBUG):
        assert service.check_connection() == "ok"
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.MESSENGER] is True
    assert pulses == ["messenger"]
    assert _warnings(caplog) == []
    assert _authenticate_calls(holder) == ["/iserv/messenger/authenticate"] * 2


def test_a_messenger_page_whose_credentials_iserv_withholds_is_polled_without_any_authenticate_call(tmp_path, caplog):
    store, service, pulses, holder = _real_school(tmp_path, MESSENGER_PAGE_WITHOUT_CREDENTIALS)
    with caplog.at_level(logging.DEBUG):
        assert service.check_connection() == "ok"
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.MESSENGER] is True
    assert pulses == ["messenger"]
    assert _warnings(caplog) == []
    assert _authenticate_calls(holder) == []


def test_a_messenger_page_with_credentials_is_polled(tmp_path):
    store, service, pulses, holder = _real_school(tmp_path, MESSENGER_PAGE)
    assert service.check_connection() == "ok"
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.MESSENGER] is True
    assert pulses == ["messenger"]
    assert _authenticate_calls(holder) == []


def test_an_unreachable_authenticate_call_keeps_the_messenger_as_it_was(tmp_path, caplog):
    store, service, pulses, holder = _real_school(tmp_path, MESSENGER_PAGE_WITHOUT_DATA, authenticate=AUTHENTICATE_ANSWER)
    assert service.check_connection() == "ok"
    assert service.modules()["modules"][modules.MESSENGER] is True
    holder["client"].authenticate = requests.ConnectionError("down")
    with caplog.at_level(logging.DEBUG):
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.MESSENGER] is True
    assert pulses == ["messenger"]
    assert _warnings(caplog) == []


class RateLimitedService(ModularService):
    def __init__(self, store, available, fails_on):
        super().__init__(store, available)
        self.fails_on = fails_on

    def timetable(self, child_id, week_offset=0):
        if self.fails_on == "timetable":
            self.calls.append("timetable")
            raise OutageError("rate_limited", retry_after=600)
        return super().timetable(child_id, week_offset)

    def letters(self, tab="current"):
        if self.fails_on == "letters":
            self.calls.append("letters")
            raise OutageError("rate_limited", retry_after=600)
        return super().letters(tab)

    def messenger_unread_pulse(self):
        if self.fails_on == "messenger":
            self.calls.append("messenger")
            raise OutageError("rate_limited", retry_after=600)
        return super().messenger_unread_pulse()

    def absences_overview(self):
        if self.fails_on == "absences":
            self.calls.append("absences")
            raise OutageError("rate_limited", retry_after=600)
        return super().absences_overview()


def test_a_429_during_the_timetable_loop_stops_the_poll_and_backs_off(tmp_path):
    store = _store(tmp_path)
    service = RateLimitedService(store, {}, "timetable")
    events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert names == ["children", "timetable"]
    assert "letters" not in names and "pinboard" not in names and "messenger" not in names and "absences" not in names
    assert [entry for entry in events if "child_key" in entry] == []
    slot = _school_state(store)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_REASON] == "rate_limited"
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 600


def test_a_429_during_letters_stops_the_poll_before_pinboard_and_conferences(tmp_path):
    store = _store(tmp_path)
    service = RateLimitedService(store, {}, "letters")
    events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert "timetable" in names and "letters" in names
    assert "pinboard" not in names and "conferences" not in names and "messenger" not in names and "absences" not in names
    assert [entry for entry in events if isinstance(entry, dict) and entry.get("module") == "letters" and entry.get("error")] == []
    slot = _school_state(store)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 600


def test_a_429_during_messenger_stops_the_poll_before_absences(tmp_path):
    store = _store(tmp_path)
    service = RateLimitedService(store, {}, "messenger")
    events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert "messenger" in names and "absences" not in names
    assert [entry for entry in events if isinstance(entry, dict) and entry.get("module") == "messenger" and entry.get("error")] == []
    slot = _school_state(store)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 600


def test_a_429_during_absences_backs_off_without_a_per_item_error(tmp_path):
    store = _store(tmp_path)
    service = RateLimitedService(store, {}, "absences")
    events = _poller(store, service).poll_once()
    names = _names(service.calls)
    assert "absences" in names
    assert [entry for entry in events if isinstance(entry, dict) and "module" in entry and entry.get("error")] == []
    slot = _school_state(store)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 600
