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
    Response,
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


LETTER_ROW = (
    '<tr><td><a href="/iserv/parentletter/parent/show/{letter}/{recipient}">Letter {number}</a></td>'
    "<td>Alex Sample</td><td>M. Sample</td><td></td><td>Class 3b</td><td>01.09.2026 08:00</td></tr>"
)


def _letter_list(count):
    rows = "".join(
        LETTER_ROW.format(
            letter=f"10000000-0000-4000-8000-{number:012d}", recipient=f"20000000-0000-4000-8000-{number:012d}", number=number
        )
        for number in range(1, count + 1)
    )
    return f'<html><body><table id="crud-table"><tbody>{rows}</tbody></table></body></html>'


class LetterProbeClient(ProbeClient):
    def __init__(self, url, missing, letters):
        super().__init__(url, missing=missing)
        self.letters = letters

    def fetch(self, path, params=None):
        if path == modules.PROBES[modules.LETTERS][0]:
            self.calls.append(path)
            return Response(200, self.base_url + path, _letter_list(self.letters["count"]))
        return super().fetch(path, params)

    def fetch_or_raise(self, path, params=None):
        return self.fetch(path, params)


def test_a_poll_opens_no_letter_page_however_many_letters_are_new(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school-one.example")
    missing = [
        path
        for name in modules.MODULES
        if name != modules.LETTERS
        for path, _ in modules.probes_of(name, datetime.fromtimestamp(NOW_EPOCH).date())
    ] + [modules.LEGACY_TIMETABLE_PATH]
    letters = {"count": 3}
    holder = {}

    def factory(url):
        holder["client"] = LetterProbeClient(url, missing, letters)
        return holder["client"]

    service = connection_service(store, connection_id, factory)
    service._dsa = lambda: SchoolApp()
    assert service.check_connection() == "ok"
    assert service.modules()["modules"][modules.LETTERS] is True
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    letters["count"] = 40
    Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    calls = holder["client"].calls
    assert calls.count(modules.PROBES[modules.LETTERS][0]) >= 3
    assert [path for path in calls if "/parent/show/" in path] == []


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


def test_the_poller_reads_and_counts_a_week_the_school_app_refuses(tmp_path, caplog):
    from app.store import child_key
    from tests.time_table_school import MOVED_WEEK_PLAN, client_factory, withheld_school

    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school-one.example")
    school = withheld_school()
    service = connection_service(store, connection_id, client_factory(school))
    with caplog.at_level(logging.INFO):
        Poller(service, store=store, clock=lambda: NOW_EPOCH).poll_once()
    assert service.modules()["modules"][modules.TIMETABLE] is True
    state = service.store.load_config()["poll_state"][child_key(connection_id, "500001")]
    assert state["timetable_source"] == "time-table"
    assert state["changes_count"] == 5
    lessons_outside_unchosen_parallel_courses = len(MOVED_WEEK_PLAN) - 17
    assert state["push_view"] == "parallel_pending"
    assert len(state["plan_fields"]["date"]) == lessons_outside_unchosen_parallel_courses == 24
    assert school.paths("/iserv/time-table/data")
    assert _warnings(caplog) == []


def withheld_poller(tmp_path, notifier=None, **school_fields):
    from tests.time_table_school import client_factory, withheld_school

    store = Store(tmp_path / "data")
    connection_id = add_school(store, "https://school-one.example")
    school = withheld_school(**school_fields)
    service = connection_service(store, connection_id, client_factory(school))
    poller = Poller(service, store=store, clock=lambda: NOW_EPOCH, notifier=notifier)
    return poller, service, school, connection_id


def poll_state_of(service, connection_id):
    from app.store import child_key

    return service.store.load_config()["poll_state"][child_key(connection_id, "500001")]


def marked_in_push_view(service):
    from app.poller import push_view_of

    view, _ = push_view_of(service.timetable("500001"))
    return sum(1 for lesson in view["lessons"] if lesson["change_kind"]), view


def test_the_pushed_change_count_equals_the_marked_lessons_while_parallel_courses_are_open(tmp_path):
    poller, service, _, connection_id = withheld_poller(tmp_path)
    poller.poll_once()
    marked, view = marked_in_push_view(service)
    hidden_parallel_course_changes = 2
    assert poll_state_of(service, connection_id)["changes_count"] == marked == len(view["changes"]) == 7 - hidden_parallel_course_changes
    assert {item["subject"] for item in view["changes"]} == {"M", "L", "Bio"}


def test_the_pushed_change_count_equals_the_marked_lessons_once_the_courses_are_chosen(tmp_path):
    from app import courses

    poller, service, _, connection_id = withheld_poller(tmp_path)
    parallel = sorted(courses.parallel_keys(service.timetable("500001")["lessons"]))
    service.save_course_filter("500001", ["Eth|", "SP-A|", "G|"], parallel)
    poller.poll_once()
    marked, view = marked_in_push_view(service)
    assert poll_state_of(service, connection_id)["changes_count"] == marked == len(view["changes"]) == 7


def test_a_week_with_moved_lessons_says_so_in_the_push(tmp_path):
    from app import messages
    from tests.time_table_school import moved_week_changes

    calls = []
    poller, service, school, connection_id = withheld_poller(tmp_path, notifier=lambda name, message: calls.append(message) or True, changes=())
    poller.poll_once()
    course_hint = messages.text_in("de", "notify.timetable.courses", {"name": "Kim"})
    assert [message for message in calls if course_hint not in message] == []
    school.changes = moved_week_changes
    poller.poll_once()
    pushed = [message for message in calls if course_hint not in message]
    expected = messages.text_count("de", "notify.timetable.changesMoved", 5, {"name": "Kim"})
    assert len(pushed) == 1
    assert expected in pushed[0]
    assert poll_state_of(service, connection_id)["changes_format"] == "lessons"


def test_the_new_change_list_format_does_not_push_the_known_changes_again(tmp_path):
    calls = []
    poller, service, _, connection_id = withheld_poller(tmp_path, notifier=lambda name, message: calls.append(message) or True)
    poller.poll_once()
    before = list(calls)
    config = service.store.load_config()
    state = next(iter(config["poll_state"].values()))
    state.pop("changes_format")
    state["changes_signature"] = "signature-of-the-raw-records"
    service.store.save_config(config)
    poller.poll_once()
    assert calls == before
    assert poll_state_of(service, connection_id)["changes_format"] == "lessons"
    poller.poll_once()
    assert calls == before
