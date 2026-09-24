import json
import threading

import pytest

from app import atomic_write, integration, store as store_module
from app.iserv.timetable import parse_timetable
from app.poller import Poller
from app.store import ConnectionStore, Store
from app.subscriptions import SubscriptionRegistry
from tests.conftest import load_fixture
from tests.support import add_school, connection_service
from tests.test_integration_poll import CHILD_ID, NOW_EPOCH, SCHOOL, RecordingService, _store

WAIT = 5
BLOCKED = 0.2
OTHER_CHILD = f"{SCHOOL}:child-uuid-b"
CHOSEN = {"chosen": ["SP|MUE"], "known": ["SP|MUE", "SP|SCH"]}


def run_while_held(edit, other):
    entered = threading.Event()
    release = threading.Event()
    failures = []

    def held(config):
        entered.set()
        assert release.wait(WAIT)
        return config

    def first():
        try:
            edit(held)
        except Exception as error:
            failures.append(error)

    def second():
        try:
            other()
        except Exception as error:
            failures.append(error)

    worker = threading.Thread(target=first)
    worker.start()
    assert entered.wait(WAIT)
    competitor = threading.Thread(target=second)
    competitor.start()
    competitor.join(BLOCKED)
    finished_early = not competitor.is_alive()
    release.set()
    worker.join(WAIT)
    competitor.join(WAIT)
    assert not worker.is_alive() and not competitor.is_alive()
    assert failures == []
    return finished_early


def two_schools(tmp_path):
    store = Store(tmp_path / "data")
    first = add_school(store, "https://school-one.example")
    second = add_school(store, "https://school-two.example")
    return store, first, second


def test_a_stale_school_snapshot_keeps_a_newer_global_setting(tmp_path):
    store, first, _ = two_schools(tmp_path)
    scoped = ConnectionStore(store, first)
    stale = scoped.load_config()
    newer = store.load_config()
    newer["language"] = "en"
    store.save_config(newer)
    stale["school_name"] = "Renamed"
    scoped.save_config(stale)
    assert store.load_config()["language"] == "en"
    assert store.connection(first)["school_name"] == "Renamed"


def test_a_school_edit_writes_only_what_it_changed(tmp_path):
    store, first, _ = two_schools(tmp_path)
    scoped = ConnectionStore(store, first)
    scoped.edit_config(lambda flat: flat.update(language="en", holiday_region="DE-NI"))
    assert store.load_config()["language"] == "en"
    assert store.connection(first)["holiday_region"] == "DE-NI"


def set_language(store, first, second):
    store.edit_config(lambda config: config.update(language="en"))


def label_second(store, first, second):
    ConnectionStore(store, second).edit_config(lambda flat: flat.update(label="Two"))


def label_first(store, first, second):
    ConnectionStore(store, first).edit_config(lambda flat: flat.update(label="One"))


def language_is_en(config, first, second):
    return config["language"] == "en"


def second_is_labelled(config, first, second):
    return {entry["id"]: entry for entry in config["connections"]}[second]["label"] == "Two"


def first_is_labelled(config, first, second):
    return {entry["id"]: entry for entry in config["connections"]}[first]["label"] == "One"


def first_region_kept(config, first, second):
    return {entry["id"]: entry for entry in config["connections"]}[first]["holiday_region"] == "DE-HH"


def services_kept(config, first, second):
    return config["notify_services"] == ["notify.phone"]


def edit_first_school(store, first, change):
    def apply(flat):
        change(flat)
        flat["holiday_region"] = "DE-HH"

    ConnectionStore(store, first).edit_config(apply)


def edit_globals(store, first, change):
    def apply(config):
        change(config)
        config["notify_services"] = ["notify.phone"]

    store.edit_config(apply)


@pytest.mark.parametrize(
    "held, competitor, held_kept, competitor_kept",
    [
        (edit_first_school, set_language, first_region_kept, language_is_en),
        (edit_first_school, label_second, first_region_kept, second_is_labelled),
        (edit_first_school, label_first, first_region_kept, first_is_labelled),
        (edit_globals, label_first, services_kept, first_is_labelled),
    ],
    ids=["global-during-school", "other-school", "same-school", "school-during-global"],
)
def test_an_edit_waits_for_a_running_edit_and_both_changes_survive(tmp_path, held, competitor, held_kept, competitor_kept):
    store, first, second = two_schools(tmp_path)
    finished_early = run_while_held(lambda wait: held(store, first, wait), lambda: competitor(store, first, second))
    assert finished_early is False
    config = store.load_config()
    assert held_kept(config, first, second)
    assert competitor_kept(config, first, second)


def test_a_failed_write_keeps_the_old_config_and_frees_the_store(tmp_path, monkeypatch):
    store, first, _ = two_schools(tmp_path)
    before = store.config_path.read_bytes()
    original = atomic_write.write_json

    def broken(path, data):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_write, "write_json", broken)
    with pytest.raises(OSError):
        ConnectionStore(store, first).edit_config(lambda flat: flat.update(label="Lost"))
    assert store.config_path.read_bytes() == before
    monkeypatch.setattr(atomic_write, "write_json", original)
    finished = threading.Event()

    def later():
        store.edit_config(lambda config: config.update(language="en"))
        finished.set()

    worker = threading.Thread(target=later)
    worker.start()
    worker.join(WAIT)
    assert finished.is_set()
    assert store.load_config()["language"] == "en"


def test_an_edit_without_a_change_does_not_write(tmp_path, monkeypatch):
    store, first, _ = two_schools(tmp_path)
    writes = []
    monkeypatch.setattr(atomic_write, "write_json", lambda path, data: writes.append(path))
    ConnectionStore(store, first).edit_config(lambda flat: None)
    store.edit_config(lambda config: None)
    assert writes == []


def test_nested_files_of_two_schools_are_edited_one_after_the_other(tmp_path):
    store, first, second = two_schools(tmp_path)
    one = ConnectionStore(store, first)
    two = ConnectionStore(store, second)

    def edit(held):
        store_module.edit(store, store.load_seen, store.save_seen, lambda seen: seen.update({first: held({"pinboard": [1]})}))

    finished_early = run_while_held(edit, lambda: two.save_seen({"pinboard": [2]}))
    assert finished_early is False
    assert one.load_seen() == {"pinboard": [1]}
    assert two.load_seen() == {"pinboard": [2]}


def test_a_course_choice_saved_while_the_timetable_learns_period_times_is_kept(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, children=[{"child_id": "c1", "name": "Kim"}])
    service = connection_service(store, connection_id)

    week = parse_timetable(json.loads(load_fixture("timetable_data.json")))

    def school_times():
        service.save_course_filter("c1", CHOSEN["chosen"], CHOSEN["known"])
        return {"1": "08:00"}

    service._cached_child = lambda child_id: None
    service._session = lambda: type("Session", (), {"get_timetable": lambda self, child_id, target: week})()
    service._school_period_times = school_times
    service._substitutions_released = lambda: False
    service._timetable_payload("c1")
    entry = store.connection(connection_id)
    assert entry["course_filters"]["c1"]["chosen"] == CHOSEN["chosen"]
    assert entry["period_times"]["1"] == "08:00"


def test_a_calendar_entry_written_during_a_poll_is_kept(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH - 600)

    class WritesDuringPoll(RecordingService):
        def timetable(self, child_id, week_offset=0):
            if week_offset == 0 and not self.calls:
                written = store.load_calendar_snapshot()
                written.setdefault("children", {})[OTHER_CHILD] = {"weeks": {"x": {"lessons": []}}, "last_success": 1}
                store.save_calendar_snapshot(written)
            return super().timetable(child_id, week_offset)

    service = WritesDuringPoll(store)
    Poller(service, store=store, registry=SubscriptionRegistry(store), clock=lambda: NOW_EPOCH).poll_once()
    children = store.load_calendar_snapshot()["children"]
    assert children[OTHER_CHILD]["last_success"] == 1
    assert "31.08.2026" in children[CHILD_ID]["weeks"]


def test_an_integration_request_noted_during_a_poll_record_is_kept(tmp_path):
    store = _store(tmp_path)

    def edit(held):
        integration.edit_state(store, lambda state: state.update(held({"marker": 1})))

    finished_early = run_while_held(edit, lambda: integration.note_request(store, NOW_EPOCH))
    assert finished_early is False
    state = store.load_integration_state()
    assert state["marker"] == 1
    assert integration.last_request(store) == NOW_EPOCH


@pytest.mark.parametrize(
    "fresh, before, after, depth, expected",
    [
        ({"a": 1, "b": 2}, {"a": 1}, {"a": 3}, 1, {"a": 3, "b": 2}),
        ({"a": 1, "b": 2}, {"a": 1}, {}, 1, {"b": 2}),
        ({"c": {"x": 1}}, {}, {"c": {"y": 2}}, 2, {"c": {"x": 1, "y": 2}}),
        ({"c": {"w1": 1, "w9": 9}}, {"c": {"w1": 1}}, {"c": {"w1": 2}}, 2, {"c": {"w1": 2, "w9": 9}}),
        ({"c": {"w1": 1, "w9": 9}}, {"c": {"w1": 1}}, {"c": {"w1": 2}}, 1, {"c": {"w1": 2}}),
        ({"c": [1]}, {"c": [1]}, {"c": [1, 2]}, 3, {"c": [1, 2]}),
        ({"c": {"x": 1}}, {"c": {"x": 1}}, {"c": "text"}, 3, {"c": "text"}),
    ],
    ids=["changed-leaf", "removed-key", "new-subtree-merges", "nested-keeps-other", "shallow-replaces", "list-value", "dict-to-text"],
)
def test_rebase_applies_only_what_changed(fresh, before, after, depth, expected):
    assert store_module.rebase(fresh, before, after, depth) == expected


def test_a_school_edit_can_remove_a_school_key(tmp_path):
    store, first, _ = two_schools(tmp_path)
    scoped = ConnectionStore(store, first)
    scoped.edit_config(lambda flat: flat.update(auth_incident=True))
    assert store.connection(first)["auth_incident"] is True
    scoped.edit_config(lambda flat: flat.pop("auth_incident"))
    assert "auth_incident" not in store.connection(first)


def test_a_moved_child_keeps_siblings_that_share_an_old_id(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(
        store, children=[{"child_id": "", "name": "Kim Muster"}, {"child_id": "", "name": "Unknown Person"}]
    )
    service = connection_service(store, connection_id)
    service._migrate_stored_children([{"child_id": "new1", "name": "Kim Muster"}])
    stored = store.connection(connection_id)["children"]
    assert [child["child_id"] for child in stored] == ["new1", ""]


def test_a_subscription_change_does_not_bring_back_a_removed_school(tmp_path):
    store, first, _ = two_schools(tmp_path)
    store.update_connection(first, children=[{"child_id": "c1", "name": "Kim"}], holiday_region="DE-NI")
    registry = SubscriptionRegistry(store)
    created = registry.create(f"{first}:c1", ["timetable"])

    def edit(held):
        def change(entry):
            held(entry)
            return dict(entry, label="Renamed")

        try:
            registry._mutate(created["id"], change)
        except Exception:
            pass

    finished_early = run_while_held(edit, lambda: store.remove_connection(first))
    assert finished_early is False
    assert store.load_calendar_subscriptions().get("subscriptions") == []


def test_two_polls_of_the_same_school_run_one_after_the_other(tmp_path):
    store = _store(tmp_path)
    inside = threading.Event()
    release = threading.Event()
    starts = []

    class SlowService(RecordingService):
        def timetable(self, child_id, week_offset=0):
            starts.append(threading.current_thread().name)
            if not inside.is_set():
                inside.set()
                assert release.wait(WAIT)
            return super().timetable(child_id, week_offset)

    service = SlowService(store)

    def poll():
        Poller(service, store=store, registry=SubscriptionRegistry(store), clock=lambda: NOW_EPOCH).poll_once()

    first = threading.Thread(target=poll, name="first")
    first.start()
    assert inside.wait(WAIT)
    second = threading.Thread(target=poll, name="second")
    second.start()
    second.join(BLOCKED)
    overlapped = "second" in starts
    release.set()
    first.join(WAIT)
    second.join(WAIT)
    assert not first.is_alive() and not second.is_alive()
    assert overlapped is False
    assert starts == ["first", "second"]


def test_a_school_removed_during_its_poll_leaves_no_traces(tmp_path):
    store = _store(tmp_path)
    integration.note_request(store, NOW_EPOCH - 600)

    class RemovedDuringPoll(RecordingService):
        def timetable(self, child_id, week_offset=0):
            value = super().timetable(child_id, week_offset)
            if week_offset == 0:
                store.remove_connection(SCHOOL)
            return value

    Poller(RemovedDuringPoll(store), store=store, registry=SubscriptionRegistry(store), clock=lambda: NOW_EPOCH).poll_once()
    assert CHILD_ID not in (store.load_calendar_snapshot().get("children") or {})
    assert SCHOOL not in (store.load_integration_state().get("schools") or {})


@pytest.mark.parametrize("kind", ["seen", "modules", "letters_search_cache", "letters_confirmations", "absence_history"])
def test_a_school_slot_is_not_written_back_after_the_school_was_removed(tmp_path, kind):
    store, first, _ = two_schools(tmp_path)
    scoped = ConnectionStore(store, first)
    store.remove_connection(first)
    store_module.edit_slot(scoped, kind, lambda slot: slot.update({"late": True}))
    getattr(scoped, f"save_{kind}")({"late": True})
    assert first not in getattr(store, f"load_{kind}")()


def test_a_poll_waiting_for_a_school_that_is_removed_meanwhile_skips_it(tmp_path):
    store = _store(tmp_path)
    inside = threading.Event()
    release = threading.Event()
    starts = []

    class SlowService(RecordingService):
        def timetable(self, child_id, week_offset=0):
            starts.append(threading.current_thread().name)
            if not inside.is_set():
                inside.set()
                assert release.wait(WAIT)
            return super().timetable(child_id, week_offset)

    service = SlowService(store)

    def poll():
        Poller(service, store=store, registry=SubscriptionRegistry(store), clock=lambda: NOW_EPOCH).poll_once(SCHOOL)

    first = threading.Thread(target=poll, name="first")
    first.start()
    assert inside.wait(WAIT)
    second = threading.Thread(target=poll, name="second")
    second.start()
    second.join(BLOCKED)
    store.remove_connection(SCHOOL)
    release.set()
    first.join(WAIT)
    second.join(WAIT)
    assert starts == ["first"]


def test_the_login_of_a_removed_school_is_not_written_back(tmp_path):
    store, first, _ = two_schools(tmp_path)
    scoped = ConnectionStore(store, first)
    stale = scoped.load_secrets()
    store.remove_connection(first)
    scoped.save_secrets(dict(stale, messenger_token="late"))
    assert not store.secrets_path_for(first).exists()
