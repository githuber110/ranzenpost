import copy

from app.iserv.errors import LoginError
from app import messages
from app.poller import BAD_CREDENTIALS_KEY, Poller


class FakeService:
    def __init__(self, children, timetables, store=None):
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


class PublisherRecorder:
    def __init__(self):
        self.calls = []

    def publish_state(self, child_id, last_updated, has_changes, error=None):
        self.calls.append(
            {
                "child_id": child_id,
                "last_updated": last_updated,
                "has_changes": has_changes,
                "error": error,
            }
        )


class NotifierRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, name, message):
        self.calls.append({"name": name, "message": message})


def _timetable(last_updated, lessons=None, changes=None):
    return {
        "last_updated": last_updated,
        "start_date": "2026-08-31",
        "end_date": "2026-09-04",
        "lessons": lessons if lessons is not None else [],
        "changes": changes if changes is not None else [],
    }


def test_first_run_publishes_and_does_not_notify_without_changes():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
        notifier=notifier,
        store=FakeStore(),
    )
    events = poller.poll_once()
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["child_id"] == "c1"
    assert publisher.calls[0]["has_changes"] is False
    assert publisher.calls[0]["error"] is None
    assert notifier.calls == []
    assert events == [{"child_id": "c1", "changed": True, "has_changes": False}]


def test_unchanged_second_run_does_not_republish_or_notify():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    first_count = len(publisher.calls)
    events = poller.poll_once()
    assert len(publisher.calls) == first_count
    assert notifier.calls == []
    assert events == [{"child_id": "c1", "changed": False, "has_changes": False}]


def test_new_changes_trigger_notifier():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
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
    assert publisher.calls[-1]["has_changes"] is True
    assert events == [{"child_id": "c1", "changed": True, "has_changes": True}]


def test_signature_change_without_new_changes_publishes_but_does_not_notify():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {"c1": _timetable("2026-08-31T10:00", lessons=[{"subject": "Math"}])}
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
        notifier=notifier,
        store=FakeStore(),
    )
    poller.poll_once()
    before = len(publisher.calls)
    timetables["c1"] = _timetable("2026-08-31T11:00", lessons=[{"subject": "English"}])
    events = poller.poll_once()
    assert len(publisher.calls) == before + 1
    assert publisher.calls[-1]["has_changes"] is False
    assert notifier.calls == []
    assert events == [{"child_id": "c1", "changed": True, "has_changes": False}]


def test_every_change_notifies_even_when_count_stays():
    children = [{"child_id": "c1", "name": "Alice"}]
    timetables = {
        "c1": _timetable("2026-08-31T10:00", changes=[{"lesson": 3, "note": "Vertretung"}])
    }
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
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
    publisher = PublisherRecorder()
    notifier = NotifierRecorder()
    poller = Poller(
        FakeService(children, timetables),
        publisher=publisher,
        notifier=notifier,
        store=FakeStore(),
    )
    events = poller.poll_once()
    assert events[0] == {"child_id": "c1", "error": "boom"}
    assert events[1] == {"child_id": "c2", "changed": True, "has_changes": False}
    error_calls = [call for call in publisher.calls if call["error"] is not None]
    assert error_calls == [
        {"child_id": "c1", "last_updated": None, "has_changes": False, "error": "boom"}
    ]
    assert any(call["child_id"] == "c2" and call["error"] is None for call in publisher.calls)


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
    assert "c1" in config["poll_state"]
    assert config["poll_state"]["c1"]["changes_count"] == 0
    assert isinstance(config["poll_state"]["c1"]["signature"], str)


class AuthFailingService:
    def __init__(self, store, fail_times, children_after=None):
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
