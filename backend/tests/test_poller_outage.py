import logging

from app import integration, messages
from app.iserv.errors import LoginError, OutageError
from app.poller import (
    AUTH_NOTIFIED_FLAG,
    BAD_CREDENTIALS_KEY,
    OUTAGE_BACK_KEY,
    OUTAGE_PUSH_AFTER_SECONDS,
    OUTAGE_SINCE_KEY,
    Poller,
)
from app.store import Store
from app.subscriptions import SubscriptionRegistry

from tests.test_integration_poll import NOW_EPOCH, RAW_CHILD_ID, SCHOOL, RecordingService, _store
from tests.test_poller import NotifierRecorder

INTERVAL = 1800
HOUR = 3600


class Clock:
    def __init__(self, start=NOW_EPOCH):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FlakyService(RecordingService):
    def __init__(self, store, outcomes):
        super().__init__(store)
        self.outcomes = list(outcomes)
        self.attempts = 0

    def display_name(self):
        return "Testschule"

    def children(self):
        self.attempts += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return super().children()


def _outage(reason="status:503"):
    return OutageError(reason)


def _poller(store, service, clock, notifier):
    return Poller(
        service,
        store=store,
        registry=SubscriptionRegistry(store),
        clock=clock,
        notifiers={"auth": notifier, "outage": notifier},
        poll_interval=INTERVAL,
    )


def _run(store, outcomes, rounds, notifier=None, clock=None, step=INTERVAL):
    clock = clock or Clock()
    notifier = notifier or NotifierRecorder()
    service = FlakyService(store, outcomes)
    for _ in range(rounds):
        _poller(store, service, clock, notifier).poll_once()
        clock.advance(step)
    return service, notifier, clock


def test_an_outage_is_recorded_as_its_own_state_and_never_as_a_login_failure(tmp_path):
    store = _store(tmp_path)
    _, notifier, _ = _run(store, [_outage()], 1)
    slot = integration.school_state(store, SCHOOL)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot["last_poll_ok"] is False
    assert slot[integration.OUTAGE_SINCE] == NOW_EPOCH
    assert slot[integration.OUTAGE_REASON] == "status:503"
    assert notifier.calls == []
    assert AUTH_NOTIFIED_FLAG not in store.connection_store(SCHOOL).load_config()


def test_an_outage_keeps_the_snapshot_and_the_last_known_summaries(tmp_path):
    store = _store(tmp_path)
    service = FlakyService(store, ["ok", _outage()])
    service.letters_value = {"letters": [{"letter_id": "l1", "recipient_id": "r1", "title": "Ausflug", "unread": True}]}
    clock = Clock()
    notifier = NotifierRecorder()
    _poller(store, service, clock, notifier).poll_once()
    before = store.load_calendar_snapshot()
    letters_before = integration.school_state(store, SCHOOL)["letters"]
    clock.advance(INTERVAL)
    _poller(store, service, clock, notifier).poll_once()
    assert store.load_calendar_snapshot() == before
    slot = integration.school_state(store, SCHOOL)
    assert slot["letters"] == letters_before
    assert slot[integration.LAST_SUCCESS] == NOW_EPOCH


def test_the_second_consecutive_outage_skips_the_next_poll_and_the_wait_caps_at_two_hours(tmp_path):
    store = _store(tmp_path)
    service, _, _ = _run(store, [_outage()] * 12, 12)
    assert service.attempts == 5
    slot = integration.school_state(store, SCHOOL)
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 2 * HOUR


def test_a_manual_retry_ignores_the_backoff(tmp_path):
    store = _store(tmp_path)
    service, notifier, clock = _run(store, [_outage()] * 3, 2)
    attempts = service.attempts
    _poller(store, service, clock, notifier).poll_once(connection_id=SCHOOL)
    assert service.attempts == attempts + 1


def test_the_outage_ends_quietly_when_iserv_answers_again(tmp_path, caplog):
    store = _store(tmp_path)
    caplog.set_level(logging.INFO, logger="app.poller")
    _run(store, [_outage(), _outage(), "ok"], 4)
    slot = integration.school_state(store, SCHOOL)
    assert integration.OUTAGE_SINCE not in slot
    assert slot["last_poll_ok"] is True
    assert slot["last_error"] == ""
    entered = [record for record in caplog.records if "unreachable" in record.getMessage()]
    left = [record for record in caplog.records if "reachable again" in record.getMessage()]
    assert len(entered) == 1
    assert len(left) == 1
    assert all(record.levelno == logging.INFO for record in entered + left)
    assert all("Testschule" not in record.getMessage() for record in entered + left)


def test_a_short_outage_sends_no_push_at_all(tmp_path):
    store = _store(tmp_path)
    _, notifier, _ = _run(store, [_outage()] * 6 + ["ok"], 12)
    assert notifier.calls == []


def test_a_429_with_retry_after_backs_off_by_the_honoured_wait_not_a_login_failure(tmp_path):
    store = _store(tmp_path)
    rate_limited = OutageError("rate_limited", retry_after=900)
    service, notifier, _ = _run(store, [rate_limited], 1)
    slot = integration.school_state(store, SCHOOL)
    assert slot["last_error"] == integration.ERROR_OUTAGE
    assert slot[integration.OUTAGE_REASON] == "rate_limited"
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 900
    assert notifier.calls == []
    assert AUTH_NOTIFIED_FLAG not in store.connection_store(SCHOOL).load_config()


def test_a_429_without_retry_after_falls_back_to_the_normal_outage_backoff(tmp_path):
    store = _store(tmp_path)
    rate_limited = OutageError("rate_limited")
    service, _, _ = _run(store, [rate_limited] * 12, 12)
    slot = integration.school_state(store, SCHOOL)
    assert slot[integration.OUTAGE_REASON] == "rate_limited"
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 2 * HOUR


def test_a_429_retry_after_beyond_two_hours_is_capped(tmp_path):
    store = _store(tmp_path)
    rate_limited = OutageError("rate_limited", retry_after=6 * HOUR)
    _run(store, [rate_limited], 1)
    slot = integration.school_state(store, SCHOOL)
    assert slot[integration.OUTAGE_RETRY_AT] - slot["last_poll"] == 2 * HOUR


def test_a_long_outage_pushes_once_after_twelve_hours_and_once_when_it_is_back(tmp_path):
    store = _store(tmp_path)
    notifier = NotifierRecorder()
    clock = Clock()
    service = FlakyService(store, [_outage()] * 40)
    while clock.now - NOW_EPOCH < OUTAGE_PUSH_AFTER_SECONDS + 3 * HOUR:
        _poller(store, service, clock, notifier).poll_once()
        clock.advance(INTERVAL)
    assert len(notifier.calls) == 1
    assert notifier.calls[0]["message"] == messages.text_in(
        "de", OUTAGE_SINCE_KEY, {"school": "Testschule", "since": integration.berlin_stamp(NOW_EPOCH)}
    )
    service.outcomes = ["ok"]
    _poller(store, service, clock, notifier).poll_once(connection_id=SCHOOL)
    assert len(notifier.calls) == 2
    assert notifier.calls[1]["message"] == messages.text_in("de", OUTAGE_BACK_KEY, {"school": "Testschule"})
    assert integration.OUTAGE_NOTIFIED not in integration.school_state(store, SCHOOL)


def test_the_long_outage_push_rides_the_outage_channel_not_auth(tmp_path):
    store = _store(tmp_path)
    auth_notifier = NotifierRecorder()
    outage_notifier = NotifierRecorder()
    clock = Clock()
    service = FlakyService(store, [_outage()] * 40)
    while clock.now - NOW_EPOCH < OUTAGE_PUSH_AFTER_SECONDS + 3 * HOUR:
        Poller(
            service,
            store=store,
            registry=SubscriptionRegistry(store),
            clock=clock,
            notifiers={"auth": auth_notifier, "outage": outage_notifier},
            poll_interval=INTERVAL,
        ).poll_once()
        clock.advance(INTERVAL)
    assert auth_notifier.calls == []
    assert len(outage_notifier.calls) == 1
    assert outage_notifier.calls[0]["message"] == messages.text_in(
        "de", OUTAGE_SINCE_KEY, {"school": "Testschule", "since": integration.berlin_stamp(NOW_EPOCH)}
    )
    service.outcomes = ["ok"]
    Poller(
        service,
        store=store,
        registry=SubscriptionRegistry(store),
        clock=clock,
        notifiers={"auth": auth_notifier, "outage": outage_notifier},
        poll_interval=INTERVAL,
    ).poll_once(connection_id=SCHOOL)
    assert auth_notifier.calls == []
    assert len(outage_notifier.calls) == 2
    assert outage_notifier.calls[1]["message"] == messages.text_in("de", OUTAGE_BACK_KEY, {"school": "Testschule"})


def test_the_long_outage_push_is_not_repeated_while_the_outage_goes_on(tmp_path):
    store = _store(tmp_path)
    notifier = NotifierRecorder()
    clock = Clock()
    service = FlakyService(store, [_outage()] * 80)
    while clock.now - NOW_EPOCH < 2 * OUTAGE_PUSH_AFTER_SECONDS:
        _poller(store, service, clock, notifier).poll_once()
        clock.advance(INTERVAL)
    assert len(notifier.calls) == 1


def test_a_login_rejected_after_the_outage_still_warns_about_the_password(tmp_path):
    store = _store(tmp_path)
    notifier = NotifierRecorder()
    _run(store, [_outage(), LoginError("bad credentials")], 2, notifier=notifier)
    assert [call["message"] for call in notifier.calls] == [messages.text_in("de", BAD_CREDENTIALS_KEY)]
    slot = integration.school_state(store, SCHOOL)
    assert slot["last_error"] == integration.ERROR_AUTH
    assert integration.OUTAGE_SINCE not in slot


def test_an_outage_leaves_an_earlier_login_warning_untouched(tmp_path):
    store = _store(tmp_path)
    notifier = NotifierRecorder()
    _run(store, [LoginError("bad"), _outage(), LoginError("bad")], 3, notifier=notifier)
    assert len(notifier.calls) == 1


def test_the_integration_reports_an_outage_school_as_unreachable(tmp_path):
    store = _store(tmp_path)
    _run(store, [_outage()], 1)

    class Configured:
        def is_configured(self):
            return True

    class ServiceStub:
        def connection(self, connection_id):
            return Configured()

    schools = integration.build_schools(ServiceStub(), store)
    assert schools[0]["status"] == integration.STATUS_UNREACHABLE


def test_a_school_in_backoff_leaves_the_other_school_polled(tmp_path):
    store = _store(tmp_path)
    other = "b2c3d4e5"
    store.add_connection("https://school-two.example", connection_id=other, setup_complete=True, children=[])
    clock = Clock()
    notifier = NotifierRecorder()
    down = FlakyService(store, [_outage()] * 10)
    up = RecordingService(store)
    up.id = other

    class Both:
        store = None

        def connections(self):
            return [down, up]

    for connection in (down, up):
        connection.store = store.connection_store(connection.id)
    poller_store = store
    for _ in range(4):
        Poller(Both(), store=poller_store, registry=SubscriptionRegistry(store), clock=clock, notifiers={"auth": notifier, "outage": notifier}, poll_interval=INTERVAL).poll_once()
        clock.advance(INTERVAL)
    assert down.attempts == 3
    assert len(up.calls) == 4
