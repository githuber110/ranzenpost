import copy

from app.iserv.errors import DataError, LoginError
from app import messages
from app.poller import BAD_CREDENTIALS_KEY, Poller


SCHOOL = "s1"


class FakeService:
    def __init__(self, children, timetables, store=None):
        self.id = SCHOOL
        self._children = children
        self._timetables = timetables
        self.store = store

    def children(self):
        return self._children

    def timetable(self, child_id):
        value = self._timetables[child_id]
        if isinstance(value, Exception):
            raise value
        return value


class FakeStore:
    def __init__(self, config=None):
        self._config = copy.deepcopy(config) if config else {}

    def load_config(self):
        return copy.deepcopy(self._config)

    def save_config(self, config):
        self._config = copy.deepcopy(config)


class NotifierRecorder:
    def __init__(self, delivers=True):
        self.calls = []
        self.delivers = delivers

    def __call__(self, name, message):
        self.calls.append({"name": name, "message": message})
        return self.delivers


def _timetable(
    last_updated,
    lessons=None,
    changes=None,
    start_date="2026-08-31",
    end_date="2026-09-04",
):
    return {
        "last_updated": last_updated,
        "start_date": start_date,
        "end_date": end_date,
        "lessons": lessons if lessons is not None else [],
        "changes": changes if changes is not None else [],
    }


def _display_lesson(
    date="2026-08-31",
    period=1,
    subject_code="MA",
    teacher_code="ABC",
    room="R1",
    color="#123456",
    subject_label="Mathe",
):
    return {
        "date": date,
        "day_of_week": 1,
        "period": period,
        "start_time": "08:00",
        "subject_code": subject_code,
        "subject_label": subject_label,
        "color": color,
        "teacher_code": teacher_code,
        "teacher_label": teacher_code,
        "is_class_teacher": False,
        "room": room,
        "change_kind": "",
        "changed_fields": [],
        "previous": {"subject": "", "teacher": "", "room": ""},
    }


def test_first_run_reports_a_change_and_does_not_notify_without_changes():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    events = poller.poll_once()
    assert notifier.calls == []
    assert events == [{"child_key": f"{SCHOOL}:c1", "changed": True, "has_changes": False}]


def test_unchanged_second_run_reports_no_change_and_does_not_notify():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    events = poller.poll_once()
    assert notifier.calls == []
    assert events == [{"child_key": f"{SCHOOL}:c1", "changed": False, "has_changes": False}]


def test_the_push_text_names_the_child_by_first_name():
    children = [{"child_id": "c1", "name": "Musterkind, Anna Lena"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    notifier = NotifierRecorder()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=FakeStore())
    poller.poll_once()
    timetables["c1"] = _timetable(
        "2026-08-31T12:00",
        lessons=[{"subject": "Math"}],
        changes=[{"lesson": 3, "note": "Entfall"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["name"] == "Anna"
    assert notifier.calls[0]["message"] == messages.text_count("de", "notify.timetable.changes", 1, {"name": "Anna"})
    assert "Musterkind" not in notifier.calls[0]["message"]


def test_new_changes_trigger_notifier():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    assert notifier.calls == []
    timetables["c1"] = _timetable(
        "2026-08-31T12:00",
        lessons=[{"subject": "Math"}],
        changes=[{"lesson": 3, "note": "Entfall"}],
    )
    events = poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["name"] == "Alice"
    assert "Stundenplan" in notifier.calls[0]["message"]
    assert "Alice" in notifier.calls[0]["message"]
    assert events == [{"child_key": f"{SCHOOL}:c1", "changed": True, "has_changes": True}]


def test_signature_change_without_new_changes_reports_but_does_not_notify():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    timetables["c1"] = _timetable("2026-08-31T11:00", lessons=[{"subject": "English"}])
    events = poller.poll_once()
    assert notifier.calls == []
    assert events == [{"child_key": f"{SCHOOL}:c1", "changed": True, "has_changes": False}]


def test_every_change_notifies_even_when_count_stays():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {
        "c1": _timetable("2026-08-31T10:00", changes=[{"lesson": 3, "note": "Vertretung"}])
    }
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    assert len(notifier.calls) == 1
    timetables["c1"] = _timetable("2026-08-31T12:00", changes=[{"lesson": 4, "note": "Ausfall"}])
    poller.poll_once()
    assert len(notifier.calls) == 2
    poller.poll_once()
    assert len(notifier.calls) == 2


def test_fetch_error_for_one_child_does_not_abort_others():
    children = [
        {"child_id": "c1", "name": "Alice"},
        {"child_id": "c2", "name": "Bella"},
    ]
    timetables = {
        "c1": RuntimeError("boom"),
        "c2": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}]),
    }
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=FakeStore(),
    )
    events = poller.poll_once()
    assert events[0] == {"child_key": f"{SCHOOL}:c1", "error": "boom", "kind": "RuntimeError"}
    assert events[1] == {"child_key": f"{SCHOOL}:c2", "changed": True, "has_changes": False}


def test_poll_state_is_kept_next_to_other_config():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    store = FakeStore(
        {
            "children": children,
            "host": "schule.example",
            "nested": {"totp": "secret"},
        }
    )
    poller = Poller(FakeService(children, timetables), store=store)
    poller.poll_once()
    config = store.load_config()
    assert config["host"] == "schule.example"
    assert config["nested"] == {"totp": "secret"}
    assert "poll_state" in config
    assert f"{SCHOOL}:c1" in config["poll_state"]
    assert config["poll_state"][f"{SCHOOL}:c1"]["changes_count"] == 0
    assert isinstance(config["poll_state"][f"{SCHOOL}:c1"]["signature"], str)


class AuthFailingService:
    def __init__(self, store, fail_times, children_after=None):
        self.id = SCHOOL
        self.store = store
        self._fail_times = fail_times
        self._children_after = children_after if children_after is not None else []

    def children(self):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise LoginError("invalid username or password")
        return self._children_after


def test_bad_credentials_notifies_exactly_once_across_repeated_polls():
    store = FakeStore()
    auth_notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=3)
    poller = Poller(service, store=store, notifiers={"auth": auth_notifier})

    poller.poll_once()
    poller.poll_once()
    poller.poll_once()

    assert len(auth_notifier.calls) == 1
    assert auth_notifier.calls[0]["message"] == messages.text(BAD_CREDENTIALS_KEY)


def test_bad_credentials_message_falls_back_to_the_base_language():
    store = FakeStore()
    auth_notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=1)
    Poller(service, store=store, notifiers={"auth": auth_notifier}).poll_once()

    assert auth_notifier.calls[0]["message"] == messages.text(BAD_CREDENTIALS_KEY)
    assert "IServ" in auth_notifier.calls[0]["message"]


def test_bad_credentials_message_follows_the_configured_language():
    store = FakeStore({"language": "ru"})
    auth_notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=1)
    Poller(service, store=store, notifiers={"auth": auth_notifier}).poll_once()

    sent = auth_notifier.calls[0]["message"]
    assert sent == messages.text_in("ru", BAD_CREDENTIALS_KEY)
    assert sent != messages.text(BAD_CREDENTIALS_KEY)


def test_bad_credentials_marker_resets_after_successful_poll_and_notifies_again():
    store = FakeStore()
    auth_notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=1, children_after=[])
    poller = Poller(service, store=store, notifiers={"auth": auth_notifier})

    poller.poll_once()
    assert len(auth_notifier.calls) == 1

    poller.poll_once()
    assert "auth_incident_sent" not in store.load_config()
    assert "auth_incident" not in store.load_config()

    service._fail_times = 1
    poller.poll_once()
    assert len(auth_notifier.calls) == 2


class ModuleService(FakeService):
    def __init__(self, children, timetables, store=None, letters=None, pinboard=None, conferences=None):
        super().__init__(children, timetables, store=store)
        self._letters = letters if letters is not None else {"letters": []}
        self._pinboard = pinboard if pinboard is not None else {"feed": []}
        self._conferences = conferences if conferences is not None else {"empty": True, "items": []}

    def letters(self, tab="current"):
        if isinstance(self._letters, Exception):
            raise self._letters
        return self._letters

    def pinboard(self):
        return self._pinboard

    def conferences(self):
        return self._conferences


def _letter(key):
    return {"letter_id": key, "recipient_id": "r"}


def _module_service(store, letters, pinboard, conferences):
    return ModuleService([], {}, store=store, letters=letters, pinboard=pinboard, conferences=conferences)


def test_module_poll_does_not_notify_on_first_run():
    store = FakeStore()
    sent = []
    service = _module_service(
        store,
        {"letters": [_letter("a"), _letter("b")]},
        {"feed": [{"id": 1}, {"id": 2}]},
        {"empty": False, "items": [{"cells": ["x"]}]},
    )
    poller = Poller(service, store=store, notifiers={
        "letters": lambda n, m: sent.append(("letters", m)),
        "pinboard": lambda n, m: sent.append(("pinboard", m)),
        "conferences": lambda n, m: sent.append(("conferences", m)),
    })
    poller.poll_once()
    assert sent == []
    assert set(store.load_config()["poll_state"]["letter_keys"]) == {"a:r", "b:r"}


def test_module_poll_notifies_only_for_new_entries():
    store = FakeStore()
    sent = []
    notifiers = {
        "letters": lambda n, m: sent.append(("letters", m)),
        "pinboard": lambda n, m: sent.append(("pinboard", m)),
        "conferences": lambda n, m: sent.append(("conferences", m)),
    }
    first = _module_service(store, {"letters": [_letter("a")]}, {"feed": [{"id": 1}]}, {"empty": True, "items": []})
    Poller(first, store=store, notifiers=notifiers).poll_once()
    assert sent == []

    second = _module_service(
        store,
        {"letters": [_letter("a"), _letter("b")]},
        {"feed": [{"id": 1}, {"id": 2}, {"id": 3}]},
        {"empty": False, "items": [{"cells": ["neu"]}]},
    )
    Poller(second, store=store, notifiers=notifiers).poll_once()
    kinds = [kind for kind, _ in sent]
    assert kinds == ["letters", "pinboard", "conferences"]
    assert "Neuer Elternbrief" in sent[0][1]
    assert "2 neue Pinnwand-Beiträge" in sent[1][1]

    third = _module_service(
        store,
        {"letters": [_letter("a"), _letter("b")]},
        {"feed": [{"id": 1}, {"id": 2}, {"id": 3}]},
        {"empty": False, "items": [{"cells": ["neu"]}]},
    )
    sent.clear()
    Poller(third, store=store, notifiers=notifiers).poll_once()
    assert sent == []


def test_module_poll_survives_a_failing_module():
    store = FakeStore()
    sent = []
    service = _module_service(store, RuntimeError("down"), {"feed": [{"id": 9}]}, {"empty": True, "items": []})
    events = Poller(service, store=store, notifiers={"pinboard": lambda n, m: sent.append(m)}).poll_once()
    assert any(item.get("module") == "letters" and item.get("error") for item in events)
    assert any(item.get("module") == "pinboard" for item in events)


class ConfirmModuleService(ModuleService):
    def __init__(self, store, letters, pending):
        super().__init__([], {}, store=store, letters=letters)
        self._pending = set(pending)

    def pending_confirmation_keys(self, tab="current"):
        return set(self._pending)


def test_a_new_letter_with_an_open_receipt_says_so_in_the_push():
    store = FakeStore()
    sent = []
    notifiers = {"letters": lambda n, m: sent.append(m)}
    first = ConfirmModuleService(store, {"letters": [_letter("a")]}, set())
    Poller(first, store=store, notifiers=notifiers).poll_once()
    assert sent == []

    second = ConfirmModuleService(
        store, {"letters": [_letter("a"), _letter("b")]}, {"b:r"}
    )
    Poller(second, store=store, notifiers=notifiers).poll_once()
    assert len(sent) == 1
    assert sent[0] == messages.text_count("de", "notify.letters.newConfirm", 1)
    assert sent[0] != messages.text_count("de", "notify.letters.new", 1)


def test_a_new_letter_without_an_open_receipt_keeps_the_plain_push():
    store = FakeStore()
    sent = []
    notifiers = {"letters": lambda n, m: sent.append(m)}
    Poller(
        ConfirmModuleService(store, {"letters": [_letter("a")]}, set()),
        store=store,
        notifiers=notifiers,
    ).poll_once()
    Poller(
        ConfirmModuleService(store, {"letters": [_letter("a"), _letter("b")]}, {"a:r"}),
        store=store,
        notifiers=notifiers,
    ).poll_once()
    assert sent == [messages.text_count("de", "notify.letters.new", 1)]


def test_base_plan_rebuild_without_marked_changes_pushes_plan_key():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _timetable(
        "2026-08-31T11:00",
        lessons=[_display_lesson(room="R2")],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["name"] == "Alice"
    assert notifier.calls[0]["message"] == messages.text_in("de", "notify.timetable.plan", {"name": "Alice"})

    before = len(notifier.calls)
    poller.poll_once()
    assert len(notifier.calls) == before


def test_pure_colour_or_label_change_pushes_nothing():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _timetable(
        "2026-08-31T11:00",
        lessons=[_display_lesson(color="#ffffff", subject_label="MathX")],
    )
    poller.poll_once()
    assert notifier.calls == []


def test_changes_cleared_pushes_cleared_key_then_stays_silent():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {
        "c1": _timetable(
            "2026-08-31T10:00",
            lessons=[_display_lesson()],
            changes=[{"lesson": 3, "note": "Entfall"}],
        )
    }
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert len(notifier.calls) == 1

    timetables["c1"] = _timetable(
        "2026-08-31T12:00",
        lessons=[_display_lesson()],
        changes=[],
    )
    poller.poll_once()
    assert len(notifier.calls) == 2
    assert notifier.calls[1]["message"] == messages.text_in("de", "notify.timetable.cleared", {"name": "Alice"})

    before = len(notifier.calls)
    poller.poll_once()
    assert len(notifier.calls) == before


def test_changes_count_change_still_pushes_changes_key():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {
        "c1": _timetable(
            "2026-08-31T10:00",
            lessons=[_display_lesson()],
            changes=[{"lesson": 3, "note": "Entfall"}],
        )
    }
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert len(notifier.calls) == 1

    timetables["c1"] = _timetable(
        "2026-08-31T12:00",
        lessons=[_display_lesson()],
        changes=[{"lesson": 3, "note": "Entfall"}, {"lesson": 4, "note": "Vertretung"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 2
    assert notifier.calls[1]["message"] == messages.text_count("de", "notify.timetable.changes", 2, {"name": "Alice"})


def test_first_run_pushes_nothing_even_with_lessons():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert notifier.calls == []


def test_upgrade_migration_without_plan_signature_pushes_nothing_on_first_poll_after_upgrade():
    children = [{"child_id": "c1", "name": "Alice"}]
    old_lessons = [_display_lesson()]
    old_timetable = _timetable("2026-08-31T10:00", lessons=old_lessons)
    store = FakeStore(
        {
            "children": children,
            "poll_state": {
                f"{SCHOOL}:c1": {
                    "last_updated": "2026-08-31T10:00",
                    "changes_count": 0,
                    "signature": Poller._signature(old_lessons, []),
                    "changes_signature": Poller._changes_signature([]),
                }
            },
        }
    )
    timetables = {"c1": _timetable("2026-08-31T11:00", lessons=[_display_lesson(room="R2")])}
    notifier = NotifierRecorder()
    poller = Poller(FakeService(children, timetables), notifier=notifier, store=store)
    poller.poll_once()
    assert notifier.calls == []
    assert "plan_signature" in store.load_config()["poll_state"][f"{SCHOOL}:c1"]

    timetables["c1"] = _timetable("2026-08-31T12:00", lessons=[_display_lesson(room="R3")])
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["message"] == messages.text_in("de", "notify.timetable.plan", {"name": "Alice"})


def _next_week(last_updated, lessons=None, changes=None):
    return _timetable(
        last_updated,
        lessons=lessons,
        changes=changes,
        start_date="2026-09-07",
        end_date="2026-09-11",
    )


def _week_after_next(last_updated, lessons=None, changes=None):
    return _timetable(
        last_updated,
        lessons=lessons,
        changes=changes,
        start_date="2026-09-14",
        end_date="2026-09-18",
    )


def _poller(children, timetables, notifier, store=None):
    return Poller(
        FakeService(children, timetables),
        notifier=notifier,
        store=store if store is not None else FakeStore(),
    )


def test_an_unchanged_timetable_across_the_week_rollover_pushes_nothing():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _next_week(
        "2026-09-07T10:00", lessons=[_display_lesson(date="2026-09-07")]
    )
    poller.poll_once()
    assert notifier.calls == []

    poller.poll_once()
    assert notifier.calls == []


def test_an_active_change_falling_out_of_the_new_week_does_not_push_cleared():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T09:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _timetable(
        "2026-08-31T10:00",
        lessons=[_display_lesson(teacher_code="XYZ")],
        changes=[{"lesson": 1, "note": "Vertretung"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1

    timetables["c1"] = _next_week(
        "2026-09-07T08:00", lessons=[_display_lesson(date="2026-09-07")], changes=[]
    )
    poller.poll_once()
    assert len(notifier.calls) == 1


def test_a_vacation_week_pushes_nothing_at_either_boundary():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()

    timetables["c1"] = _next_week("2026-09-07T10:00", lessons=[])
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _week_after_next(
        "2026-09-14T10:00", lessons=[_display_lesson(date="2026-09-14")]
    )
    poller.poll_once()
    assert notifier.calls == []


def test_a_genuine_change_within_the_same_week_still_pushes():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _timetable(
        "2026-08-31T11:00",
        lessons=[_display_lesson()],
        changes=[{"lesson": 3, "note": "Entfall"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["message"] == messages.text_count(
        "de", "notify.timetable.changes", 1, {"name": "Alice"}
    )


def test_a_genuine_plan_rebuild_within_the_same_week_still_pushes_the_plan_key():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()

    timetables["c1"] = _timetable(
        "2026-08-31T11:00", lessons=[_display_lesson(period=2, room="R2")]
    )
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["message"] == messages.text_in(
        "de", "notify.timetable.plan", {"name": "Alice"}
    )


def test_the_first_poll_in_a_new_week_re_seeds_the_stored_anchor():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    store = FakeStore()
    poller = _poller(children, timetables, NotifierRecorder(), store=store)
    poller.poll_once()
    assert store.load_config()["poll_state"][f"{SCHOOL}:c1"]["week_anchor"] == "2026-08-31"

    timetables["c1"] = _next_week(
        "2026-09-07T10:00", lessons=[_display_lesson(date="2026-09-07")]
    )
    poller.poll_once()
    assert store.load_config()["poll_state"][f"{SCHOOL}:c1"]["week_anchor"] == "2026-09-07"


def test_withdrawn_changes_back_to_the_known_regular_plan_still_say_cleared():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T09:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()

    timetables["c1"] = _timetable(
        "2026-08-31T10:00",
        lessons=[_display_lesson(teacher_code="XYZ")],
        changes=[{"lesson": 1, "note": "Vertretung"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1

    timetables["c1"] = _timetable(
        "2026-08-31T12:00", lessons=[_display_lesson()], changes=[]
    )
    poller.poll_once()
    assert len(notifier.calls) == 2
    assert notifier.calls[1]["message"] == messages.text_in(
        "de", "notify.timetable.cleared", {"name": "Alice"}
    )


def test_a_plan_rebuild_alongside_withdrawn_changes_never_claims_the_plan_is_regular():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T09:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()

    timetables["c1"] = _timetable(
        "2026-08-31T10:00",
        lessons=[_display_lesson(teacher_code="XYZ")],
        changes=[{"lesson": 1, "note": "Vertretung"}],
    )
    poller.poll_once()
    assert len(notifier.calls) == 1

    timetables["c1"] = _timetable(
        "2026-08-31T12:00", lessons=[_display_lesson(room="R9")], changes=[]
    )
    poller.poll_once()
    assert len(notifier.calls) == 2
    assert notifier.calls[1]["message"] == messages.text_in(
        "de", "notify.timetable.plan", {"name": "Alice"}
    )
    assert notifier.calls[1]["message"] != messages.text_in(
        "de", "notify.timetable.cleared", {"name": "Alice"}
    )


def test_bad_credentials_without_a_target_are_not_latched_and_warn_once_one_exists():
    store = FakeStore()
    undeliverable = NotifierRecorder(delivers=False)
    service = AuthFailingService(store, fail_times=4)

    Poller(service, store=store, notifiers={"auth": undeliverable}).poll_once()
    Poller(service, store=store, notifiers={"auth": undeliverable}).poll_once()
    assert len(undeliverable.calls) == 2
    assert "auth_incident_sent" not in store.load_config()

    delivering = NotifierRecorder()
    Poller(service, store=store, notifiers={"auth": delivering}).poll_once()
    assert len(delivering.calls) == 1
    assert store.load_config()["auth_incident_sent"] is True

    Poller(service, store=store, notifiers={"auth": delivering}).poll_once()
    assert len(delivering.calls) == 1


def test_bad_credentials_with_a_target_are_delivered_once_and_not_repeated():
    store = FakeStore()
    notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=3)
    poller = Poller(service, store=store, notifiers={"auth": notifier})

    poller.poll_once()
    poller.poll_once()
    poller.poll_once()
    assert len(notifier.calls) == 1
    assert store.load_config()["auth_incident_sent"] is True


def test_a_legacy_latched_incident_is_warned_about_again():
    store = FakeStore({"auth_incident": True})
    notifier = NotifierRecorder()
    service = AuthFailingService(store, fail_times=2)
    poller = Poller(service, store=store, notifiers={"auth": notifier})

    poller.poll_once()
    assert len(notifier.calls) == 1
    assert "auth_incident" not in store.load_config()

    poller.poll_once()
    assert len(notifier.calls) == 1


class FeedWeeksConnection:
    def __init__(self, break_at):
        self.break_at = break_at
        self.calls = []

    def timetable(self, child_id, week_offset=0):
        self.calls.append(week_offset)
        if week_offset == self.break_at:
            raise DataError("the timetable payload shape was not understood")
        return {"start_date": f"week-{week_offset}"}


def test_collect_feed_weeks_logs_once_when_a_later_week_cannot_be_read(caplog):
    poller = Poller(FakeService({}, {}), store=FakeStore())
    connection = FeedWeeksConnection(break_at=2)
    current = {"start_date": "week-0"}

    with caplog.at_level("WARNING"):
        weeks = poller._collect_feed_weeks(connection, "c1", current)

    assert [week["start_date"] for week in weeks] == ["week-0", "week-1"]
    assert any("timetable child#c1 week 2 failed" in message for message in caplog.messages)
    assert any("DataError" in message for message in caplog.messages)


def test_collect_feed_weeks_keeps_every_week_when_all_reads_succeed():
    poller = Poller(FakeService({}, {}), store=FakeStore())
    connection = FeedWeeksConnection(break_at=None)
    current = {"start_date": "week-0"}

    weeks = poller._collect_feed_weeks(connection, "c1", current)

    assert [week["start_date"] for week in weeks] == [f"week-{i}" for i in range(4)]
def _filtered(timetable, signature):
    return dict(timetable, courses={"parallel": 2, "chosen": bool(signature), "hidden": 1, "new": 0, "signature": signature})


def test_choosing_courses_rebases_the_timetable_without_a_push():
    children = [{"child_id": "c1", "name": "Alice"}]
    both = [_display_lesson(subject_code="E1"), _display_lesson(subject_code="E2", teacher_code="DDD")]
    changed = [dict(both[1], change_kind="changed", changed_fields=["room"])]
    timetables = {"c1": _filtered(_timetable("2026-08-31T10:00", lessons=both, changes=[{"subject": "E2"}]), "")}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = _poller(children, timetables, notifier, store)
    poller.poll_once()
    notifier.calls.clear()

    timetables["c1"] = _filtered(_timetable("2026-08-31T10:00", lessons=both[:1], changes=[]), "abc")
    poller.poll_once()
    assert notifier.calls == []
    assert store.load_config()["poll_state"][f"{SCHOOL}:c1"]["course_signature"] == "abc"

    timetables["c1"] = _filtered(_timetable("2026-08-31T11:00", lessons=both[:1] + changed, changes=[{"subject": "E2"}]), "def")
    poller.poll_once()
    assert notifier.calls == []

    timetables["c1"] = _filtered(_timetable("2026-08-31T12:00", lessons=[dict(both[0], room="R9")] + changed, changes=[{"subject": "E2"}]), "def")
    poller.poll_once()
    assert len(notifier.calls) == 1


def test_a_poll_state_without_course_signature_is_not_a_rebase():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = _poller(children, timetables, notifier, store)
    poller.poll_once()
    state = store.load_config()
    state["poll_state"][f"{SCHOOL}:c1"].pop("course_signature")
    store.save_config(state)
    timetables["c1"] = _timetable("2026-08-31T11:00", lessons=[_display_lesson(room="R2")])
    poller.poll_once()
    assert notifier.calls[0]["message"] == messages.text_in("de", "notify.timetable.plan", {"name": "Alice"})


CHOSEN_DURING_POLL = {"c1": {"chosen": ["SP|MUE"], "known": ["SP|MUE", "SP|SCH"]}}


def _save_user_settings(store):
    config = store.load_config()
    config["course_filters"] = copy.deepcopy(CHOSEN_DURING_POLL)
    config["subjects"] = {"SP": {"code": "SP", "label": "Sport"}}
    store.save_config(config)


class SavesDuringTimetable(FakeService):
    def timetable(self, child_id):
        _save_user_settings(self.store)
        return super().timetable(child_id)


class SavesDuringLogin(FakeService):
    def children(self):
        _save_user_settings(self.store)
        raise LoginError("invalid username or password")


def test_a_course_choice_saved_during_a_poll_survives_the_poll_state_write():
    store = FakeStore({"language": "de", "course_filters": {}})
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    poller = Poller(SavesDuringTimetable(children, timetables, store=store), notifier=NotifierRecorder(), store=store)
    poller.poll_once()
    saved = store.load_config()
    assert saved["course_filters"] == CHOSEN_DURING_POLL
    assert saved["subjects"]["SP"]["label"] == "Sport"
    assert f"{SCHOOL}:c1" in saved["poll_state"]


def test_a_setting_saved_during_a_failed_login_survives_the_auth_flag_write():
    store = FakeStore({"language": "de"})
    poller = Poller(SavesDuringLogin([], {}, store=store), store=store, notifiers={"auth": NotifierRecorder()})
    poller.poll_once()
    saved = store.load_config()
    assert saved["course_filters"] == CHOSEN_DURING_POLL
    assert saved["auth_incident_sent"] is True


def test_the_poller_still_clears_its_own_auth_flags_after_a_good_poll():
    store = FakeStore({"language": "de", "auth_incident_sent": True, "auth_incident_reason": "bad_credentials", "auth_incident": True})
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00")}
    poller = Poller(SavesDuringTimetable(children, timetables, store=store), notifier=NotifierRecorder(), store=store)
    poller.poll_once()
    saved = store.load_config()
    assert "auth_incident_sent" not in saved
    assert "auth_incident_reason" not in saved
    assert "auth_incident" not in saved
    assert saved["course_filters"] == CHOSEN_DURING_POLL


def test_a_course_choice_saved_during_a_poll_survives_in_the_real_connection_store(tmp_path):
    from app import courses
    from app.store import Store
    from tests.support import add_school, scoped

    base = Store(tmp_path / "data")
    connection_id = add_school(base, children=[{"child_id": "c1", "name": "Alice"}])
    store = scoped(base, connection_id)
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00")}
    service = SavesDuringTimetable(children, timetables, store=store)
    service.id = connection_id
    Poller(service, notifier=NotifierRecorder(), store=store).poll_once()
    saved = store.load_config()
    assert courses.filter_of(saved, "c1") == CHOSEN_DURING_POLL["c1"]
    assert saved["subjects"]["SP"]["label"] == "Sport"
    assert saved["poll_state"]


def test_a_restart_with_an_unchanged_plan_pushes_nothing(tmp_path):
    from app.store import Store
    from tests.support import add_school, scoped

    base = Store(tmp_path / "data")
    connection_id = add_school(base, children=[{"child_id": "c1", "name": "Alice"}])
    store = scoped(base, connection_id)
    children = [{"child_id": "c1", "name": "Alice"}]
    lessons = [_display_lesson(), _display_lesson(period=2, subject_code="DE", teacher_code="XYZ")]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=lessons, changes=[{"subject": "DE"}])}
    notifier = NotifierRecorder()

    first = FakeService(children, timetables, store=store)
    first.id = connection_id
    Poller(first, notifier=notifier, store=store).poll_once()
    notifier.calls.clear()
    Poller(first, notifier=notifier, store=store).poll_once()
    assert notifier.calls == []

    restarted_store = scoped(Store(tmp_path / "data"), connection_id)
    again = FakeService(children, copy.deepcopy(timetables), store=restarted_store)
    again.id = connection_id
    Poller(again, notifier=notifier, store=restarted_store).poll_once()
    assert notifier.calls == []


def _sourced(timetable, source):
    return dict(timetable, source=source)


def test_a_switch_of_the_timetable_source_is_a_rebase_without_push_or_change_events(monkeypatch):
    from app import integration

    recorded = []
    real = integration.record_poll

    def capture(store, now_epoch, ok, error="", changes=None):
        recorded.append(list(changes or []))
        return real(store, now_epoch, ok, error, changes=changes)

    monkeypatch.setattr(integration, "record_poll", capture)
    children = [{"child_id": "c1", "name": "Alice"}]
    changed = dict(_display_lesson(subject_code="EN", teacher_code="XYZ"), change_kind="changed", changed_fields=["teacher"])
    timetables = {"c1": _sourced(_timetable("2026-08-31T10:00", lessons=[]), "school-app")}
    notifier = NotifierRecorder()
    store = FakeStore()
    poller = _poller(children, timetables, notifier, store)
    poller.poll_once()

    timetables["c1"] = _sourced(
        _timetable("2026-08-31T10:00", lessons=[_display_lesson(), changed], changes=[{"subject": "EN"}]), "time-table"
    )
    poller.poll_once()
    assert notifier.calls == []
    assert recorded[-1] == []
    assert store.load_config()["poll_state"][f"{SCHOOL}:c1"]["timetable_source"] == "time-table"

    timetables["c1"] = _sourced(_timetable("2026-08-31T11:00", lessons=[_display_lesson(room="R5")]), "school-app")
    poller.poll_once()
    assert notifier.calls == []
    assert recorded[-1] == []

    timetables["c1"] = _sourced(_timetable("2026-08-31T12:00", lessons=[_display_lesson(room="R6")]), "school-app")
    poller.poll_once()
    assert len(notifier.calls) == 1


def test_an_older_poll_state_counts_as_the_school_app_source():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[_display_lesson()])}
    notifier = NotifierRecorder()
    poller = _poller(children, timetables, notifier)
    poller.poll_once()
    timetables["c1"] = _sourced(_timetable("2026-08-31T11:00", lessons=[_display_lesson(room="R2")]), "school-app")
    poller.poll_once()
    assert len(notifier.calls) == 1
