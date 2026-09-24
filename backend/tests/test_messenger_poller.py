import pytest

from app import messages
from app.poller import MESSENGER_KEY, Poller


class StubStore:
    def __init__(self, config=None):
        self.config = config or {}

    def load_config(self):
        return dict(self.config)

    def save_config(self, config):
        self.config = config

    def load_calendar_snapshot(self):
        return {}

    def save_calendar_snapshot(self, snapshot):
        pass


class StubService:
    def __init__(self, store, counts):
        self.store = store
        self._counts = list(counts)

    def children(self):
        return []

    def messenger_unread_pulse(self):
        return self._counts.pop(0)


def make_poller(counts, notifier_calls):
    store = StubStore()
    service = StubService(store, counts)
    poller = Poller(
        service,
        notifiers={"messenger": lambda name, message: notifier_calls.append(message) or True},
        store=store,
    )
    return poller


@pytest.fixture(autouse=True)
def restore_base_messages():
    original = dict(messages.BASE_MESSAGES)
    yield
    messages.BASE_MESSAGES.clear()
    messages.BASE_MESSAGES.update(original)


def test_no_push_is_sent_while_the_frontend_i18n_keys_are_missing():
    messages.BASE_MESSAGES.pop(f"{MESSENGER_KEY}.one", None)
    messages.BASE_MESSAGES.pop(f"{MESSENGER_KEY}.other", None)
    notifier_calls = []
    poller = make_poller([0, 3], notifier_calls)
    poller.poll_once()
    poller.poll_once()
    assert notifier_calls == []


def test_a_push_fires_once_the_i18n_keys_exist_and_the_unread_count_rose():
    messages.BASE_MESSAGES[f"{MESSENGER_KEY}.one"] = "1 neue Nachricht"
    messages.BASE_MESSAGES[f"{MESSENGER_KEY}.other"] = "{count} neue Nachrichten"
    notifier_calls = []
    poller = make_poller([0, 3], notifier_calls)
    poller.poll_once()
    poller.poll_once()
    assert notifier_calls == ["3 neue Nachrichten"]


def test_no_push_when_the_unread_count_does_not_increase():
    messages.BASE_MESSAGES[f"{MESSENGER_KEY}.one"] = "1 neue Nachricht"
    messages.BASE_MESSAGES[f"{MESSENGER_KEY}.other"] = "{count} neue Nachrichten"
    notifier_calls = []
    poller = make_poller([3, 3], notifier_calls)
    poller.poll_once()
    poller.poll_once()
    assert notifier_calls == []


def test_a_missing_messenger_pulse_method_is_tolerated():
    store = StubStore()

    class NoMessengerService:
        def __init__(self, store):
            self.store = store

        def children(self):
            return []

    poller = Poller(NoMessengerService(store), store=store)
    events = poller.poll_once()
    assert not any(event.get("module") == "messenger" for event in events)


class WithheldService(StubService):
    def __init__(self, store, error):
        super().__init__(store, [])
        self.error = error

    def messenger_unread_pulse(self):
        raise self.error


def test_withheld_chat_credentials_do_not_count_as_a_failed_poll():
    from app.iserv.messenger import STAGE_NO_CREDENTIALS, MessengerStageError

    store = StubStore()
    poller = Poller(WithheldService(store, MessengerStageError(STAGE_NO_CREDENTIALS)), store=store)
    events = poller.poll_once()
    assert not [event for event in events if isinstance(event, dict) and event.get("error")]
    assert {"module": "messenger", "skipped": True} in events


def test_a_broken_chat_still_counts_as_a_failed_poll():
    from app.iserv.messenger import STAGE_MATRIX, MessengerStageError

    store = StubStore()
    poller = Poller(WithheldService(store, MessengerStageError(STAGE_MATRIX)), store=store)
    events = poller.poll_once()
    assert [event for event in events if isinstance(event, dict) and event.get("error")]
