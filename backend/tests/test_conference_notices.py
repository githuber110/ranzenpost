from datetime import date, datetime, timezone

from app import conference_notices, messages
from app.conference_service import OWN_CANCELLATIONS_KEY, OWN_CHANGE_KEY
from app.poller import Poller
from app.scheduler import NOTIFY_EVENTS
from app.store import NOTIFY_EVENT_DEFAULTS
from tests.test_poller import FakeStore, ModuleService

TITLE = "Elternsprechtag Herbst"
DAY = "Donnerstag, 05.11.2026, 14:00 - 18:00 Uhr"
WINDOW = "Buchungszeitraum: 20.10.2026 - 03.11.2026"
PAGE = "a" * 24
EVENTS = (
    conference_notices.EVENT_BOOKING_OPEN,
    conference_notices.EVENT_CANCELLED,
    conference_notices.EVENT_REMINDER,
    conference_notices.EVENT_BOOKING_REMINDER,
)


def berlin(year, month, day, hour=9, minute=0):
    offset = 2 if (month, day) < (10, 25) else 1
    return datetime(year, month, day, hour - offset, minute, tzinfo=timezone.utc).timestamp()


def booking_page(*rows):
    return {
        "page": PAGE,
        "title": TITLE,
        "notices": [],
        "blocks": [{"kind": "table", "caption": "", "headers": ["Zeit", "Lehrkraft"], "rows": [
            {"cells": list(cells), "links": [], "forms": [index]} for index, cells in enumerate(rows)
        ]}],
        "forms": [{"id": index, "destructive": True, "fields": [], "submits": []} for index, _cells in enumerate(rows)],
    }


class ConferenceModuleService(ModuleService):
    def __init__(self, store, items, page=None):
        super().__init__([], {}, store=store, conferences={"empty": False, "items": items})
        self.page = page
        self.pages_read = []

    def conference_page(self, token):
        self.pages_read.append(token)
        if isinstance(self.page, Exception):
            raise self.page
        return self.page or booking_page()


def poll(store, items, at, page=None):
    sent = []
    notifiers = {event: (lambda event: lambda name, message: sent.append((event, message)) or True)(event) for event in EVENTS}
    service = ConferenceModuleService(store, items, page)
    poller = Poller(service, store=store, notifiers=notifiers, clock=lambda: at)
    poller.poll_once()
    return sent, service


def text(key, **variables):
    return messages.text_in("de", key, variables)


def test_every_conference_push_has_its_own_switch_and_is_on_by_default():
    for event in EVENTS:
        assert event in NOTIFY_EVENTS
        assert NOTIFY_EVENT_DEFAULTS[event] is True


def test_booking_opens_once_when_the_school_offers_the_booking_page():
    store = FakeStore()
    closed = [{"cells": [TITLE, DAY], "page": ""}]
    opened = [{"cells": [TITLE, DAY], "page": PAGE}]
    assert poll(store, closed, berlin(2026, 10, 1))[0] == []
    sent, _service = poll(store, opened, berlin(2026, 10, 2))
    assert sent == [(conference_notices.EVENT_BOOKING_OPEN, text(conference_notices.BOOKING_OPEN_KEY, title=TITLE))]
    assert poll(store, opened, berlin(2026, 10, 3))[0] == []


def test_booking_opens_by_the_named_booking_period_and_never_twice_after_a_restart():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY, WINDOW], "page": ""}]
    assert poll(store, items, berlin(2026, 10, 19))[0] == []
    sent, _service = poll(store, items, berlin(2026, 10, 20))
    assert [event for event, _message in sent] == [conference_notices.EVENT_BOOKING_OPEN]
    assert poll(store, items, berlin(2026, 10, 21))[0] == []


def test_a_conference_first_seen_while_open_gives_no_booking_push():
    store = FakeStore()
    assert poll(store, [{"cells": [TITLE, DAY], "page": PAGE}], berlin(2026, 10, 1))[0] == []


def test_the_reminder_comes_three_days_before_and_only_once():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": ""}]
    assert poll(store, items, berlin(2026, 11, 1))[0] == []
    sent, _service = poll(store, items, berlin(2026, 11, 2))
    assert sent == [(conference_notices.EVENT_REMINDER, text(conference_notices.REMINDER_KEY, title=TITLE, date="05.11.2026"))]
    assert poll(store, items, berlin(2026, 11, 3))[0] == []
    assert poll(store, items, berlin(2026, 11, 5, 8))[0] == []


def test_a_booking_that_vanishes_from_the_school_page_is_reported_once():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    booked = booking_page(("14:00 - 14:10", "Frau Muster"))
    assert poll(store, items, berlin(2026, 10, 21), booked)[0] == []
    sent, _service = poll(store, items, berlin(2026, 10, 22), booking_page())
    assert sent == [(conference_notices.EVENT_CANCELLED, text(conference_notices.CANCELLED_KEY, summary="14:00 - 14:10 · Frau Muster"))]
    assert poll(store, items, berlin(2026, 10, 23), booking_page())[0] == []


def test_an_own_change_in_the_app_is_not_reported_as_a_cancellation():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    poll(store, items, berlin(2026, 10, 21), booking_page(("14:00 - 14:10", "Frau Muster")))
    config = store.load_config()
    config[OWN_CHANGE_KEY] = int(berlin(2026, 10, 21, 12))
    store.save_config(config)
    assert poll(store, items, berlin(2026, 10, 22), booking_page())[0] == []


def test_an_unreadable_page_keeps_the_bookings_and_reports_nothing():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    poll(store, items, berlin(2026, 10, 21), booking_page(("14:00 - 14:10", "Frau Muster")))
    assert poll(store, items, berlin(2026, 10, 22), RuntimeError("down"))[0] == []
    sent, _service = poll(store, items, berlin(2026, 10, 23), booking_page())
    assert [event for event, _message in sent] == [conference_notices.EVENT_CANCELLED]


def test_the_booking_reminder_comes_within_one_poll_interval_before_the_start_and_once():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    booked = booking_page(("14:00 - 14:10", "Frau Muster"))
    first, _service = poll(store, items, berlin(2026, 11, 5, 13, 20), booked)
    assert conference_notices.EVENT_BOOKING_REMINDER not in [event for event, _message in first]
    sent, _service = poll(store, items, berlin(2026, 11, 5, 13, 40), booked)
    assert sent == [(
        conference_notices.EVENT_BOOKING_REMINDER,
        text(conference_notices.BOOKING_REMINDER_KEY, time="14:00", summary="14:00 - 14:10 · Frau Muster"),
    )]
    assert poll(store, items, berlin(2026, 11, 5, 13, 50), booked)[0] == []


def test_past_conferences_are_not_read_again():
    store = FakeStore()
    _sent, service = poll(store, [{"cells": [TITLE, DAY], "page": PAGE}], berlin(2026, 11, 6))
    assert service.pages_read == []


def test_the_plan_keeps_no_state_of_conferences_that_left_the_list():
    pushes, state = conference_notices.plan(
        {"seen": ["x"], "open": ["x"], "reminded": ["x"], "bookings": {}, "booking_reminded": []},
        [],
        {},
        datetime(2026, 11, 1, 9, 0),
    )
    assert pushes == [] and state["seen"] == [] and state["reminded"] == []


def test_the_facts_read_the_day_outside_the_booking_period():
    facts = conference_notices.conference_facts({"cells": [TITLE, WINDOW, DAY], "page": ""}, date(2026, 10, 25))
    assert facts["day"] == date(2026, 11, 5) and facts["open"] is True


def headed_page(heading, rows, forms=None):
    return {
        "page": PAGE,
        "title": TITLE,
        "notices": [],
        "blocks": [
            {"kind": "heading", "text": heading},
            {"kind": "table", "caption": "", "headers": [], "rows": [
                {"cells": list(cells), "links": [], "forms": list(row_forms)} for cells, row_forms in rows
            ]},
        ],
        "forms": forms or [],
    }


def test_a_booking_keeps_its_identity_when_other_cells_of_its_row_change():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    poll(store, items, berlin(2026, 10, 21), booking_page(("14:00 - 14:10", "Frau Muster", "R 101")))
    assert poll(store, items, berlin(2026, 10, 22), booking_page(("14:00 - 14:10", "Frau Muster", "R 102")))[0] == []


def test_a_booking_without_a_cancel_button_still_counts_and_its_loss_is_reported():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    listed = headed_page("Ihre Termine", [(("14:00 - 14:10", "Frau Muster"), ())])
    poll(store, items, berlin(2026, 10, 21), listed)
    sent, _service = poll(store, items, berlin(2026, 10, 22), headed_page("Ihre Termine", []))
    assert [event for event, _message in sent] == [conference_notices.EVENT_CANCELLED]


def test_a_free_slot_with_a_booking_button_is_no_booking():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    slot_form = {"id": 0, "destructive": False, "fields": [], "submits": []}
    free = headed_page("Freie Zeiten", [(("14:00 - 14:10", "Frau Muster"), (0,))], [slot_form])
    poll(store, items, berlin(2026, 10, 21), free)
    taken = headed_page("Freie Zeiten", [], [])
    assert poll(store, items, berlin(2026, 10, 22), taken)[0] == []


def test_an_own_cancellation_recorded_by_the_app_is_not_reported():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    poll(store, items, berlin(2026, 10, 21), booking_page(("14:00 - 14:10", "Frau Muster"), ("14:20 - 14:30", "Herr Beispiel")))
    config = store.load_config()
    config[OWN_CANCELLATIONS_KEY] = [{"key": "|14:00|frau muster", "at": int(berlin(2026, 10, 21, 12))}]
    store.save_config(config)
    sent, _service = poll(store, items, berlin(2026, 10, 22), booking_page())
    assert sent == [(conference_notices.EVENT_CANCELLED, text(conference_notices.CANCELLED_KEY, summary="14:20 - 14:30 · Herr Beispiel"))]


class Ticking:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        self.now += 1
        return self.now


def test_an_own_change_noted_while_the_pages_are_read_is_not_reported_later():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    clock = Ticking(berlin(2026, 10, 21))
    booked = booking_page(("14:00 - 14:10", "Frau Muster"))

    class Noting(ConferenceModuleService):
        def conference_page(self, token):
            config = store.load_config()
            config[OWN_CHANGE_KEY] = int(clock())
            store.save_config(config)
            return booked

    sent = []
    notifiers = {event: (lambda event: lambda name, message: sent.append(event) or True)(event) for event in EVENTS}
    Poller(Noting(store, items, booked), store=store, notifiers=notifiers, clock=clock).poll_once()
    clock.now = berlin(2026, 10, 22)
    Poller(ConferenceModuleService(store, items, booking_page()), store=store, notifiers=notifiers, clock=clock).poll_once()
    assert conference_notices.EVENT_CANCELLED not in sent


def test_the_booking_reminder_window_follows_the_time_since_the_last_check():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": PAGE}]
    booked = booking_page(("14:00 - 14:10", "Frau Muster"))
    poll(store, items, berlin(2026, 11, 5, 12, 10), booked)
    sent, _service = poll(store, items, berlin(2026, 11, 5, 13, 10), booked)
    assert conference_notices.EVENT_BOOKING_REMINDER in [event for event, _message in sent]


def test_the_three_day_reminder_waits_for_the_morning():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": ""}]
    assert poll(store, items, berlin(2026, 11, 2, 5))[0] == []
    sent, _service = poll(store, items, berlin(2026, 11, 2, 7, 30))
    assert [event for event, _message in sent] == [conference_notices.EVENT_REMINDER]


def test_a_push_that_was_not_delivered_is_tried_again_on_the_next_poll():
    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": ""}]
    sent = []
    notifiers = {event: (lambda name, message: False) for event in EVENTS}
    Poller(ConferenceModuleService(store, items), store=store, notifiers=notifiers, clock=lambda: berlin(2026, 11, 2, 8)).poll_once()
    second, _service = poll(store, items, berlin(2026, 11, 2, 9))
    assert [event for event, _message in second] == [conference_notices.EVENT_REMINDER]


def test_switching_the_module_off_and_on_does_not_repeat_reminders():
    from app import modules

    store = FakeStore()
    items = [{"cells": [TITLE, DAY], "page": ""}]
    assert [event for event, _message in poll(store, items, berlin(2026, 11, 2, 8))[0]] == [conference_notices.EVENT_REMINDER]
    service = ConferenceModuleService(store, items)
    off = modules.registry_of(service)
    off = dict(off, modules=dict(off["modules"], conferences=False))
    poller = Poller(service, store=store, notifiers={}, clock=lambda: berlin(2026, 11, 2, 9))
    poller._registry = lambda connection: off
    poller.poll_once()
    assert poll(store, items, berlin(2026, 11, 2, 10))[0] == []


def test_the_reminder_date_follows_the_language_of_the_push():
    store = FakeStore()
    config = store.load_config()
    config["language"] = "en"
    store.save_config(config)
    sent, _service = poll(store, [{"cells": [TITLE, DAY], "page": ""}], berlin(2026, 11, 2, 8))
    assert sent == [(conference_notices.EVENT_REMINDER, messages.text_in("en", conference_notices.REMINDER_KEY, {"title": TITLE, "date": "05/11/2026"}))]
