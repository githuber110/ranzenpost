import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests

from app import conference_notices
from app.conference_bookings import CHILD_KEY, CLOSED_KEY, GONE_KEY, REFUSED_KEY, TAKEN_KEY
from app.conference_outcomes import (
    SUBMIT_ALREADY_KEY,
    SUBMIT_INVALID_REQUEST_KEY,
    SUBMIT_NO_PROFILE_KEY,
    SUBMIT_REJECTED_KEY,
    SUBMIT_SIGNED_OUT_KEY,
    SUBMIT_UNCERTAIN_KEY,
    SUBMIT_UNCONFIRMED_KEY,
)
from app.conference_service import ConferenceService
from app.iserv.client import IServClient
from app.iserv.conference_booking import children_of, conference_id_of, moment_of, school_messages
from app.iserv.errors import DataError
from app.reportcrawl import conference_booking_lines
from tests.conference_booking_school import (
    APPOINTMENTS_PATH,
    BOOKINGS_PATH,
    CONFERENCE,
    KIM,
    ORIGIN,
    STRANGER,
    WIZARD_PATH,
    BookingSchool,
    Connection,
    answer,
    wizard_page,
)

BOOKING_OPEN = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc).timestamp()
AFTER_WINDOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc).timestamp()
REQUEST = "0123456789abcdef0123"


def service_for(school, now=BOOKING_OPEN, profiles=None):
    service = ConferenceService(Connection(school, profiles), clock=lambda: now)
    return service, service.token(WIZARD_PATH)


def booking_of(service, token):
    return service.page(token)["booking"]


def book(service, token, slot="slot-2", host="host-1", children=("kim.muster",), request=REQUEST, confirmed=True):
    values = {"slot": slot, "host": host, "children": list(children)}
    return service.submit_booking(token, "book", values, request, confirmed)


def test_the_school_page_becomes_teachers_days_and_times():
    school = BookingSchool()
    service, token = service_for(school)
    page = service.page(token)
    booking = page["booking"]
    assert page["title"] == "Elternsprechtag"
    assert page["forms"] == [] and page["blocks"] == []
    assert booking["description"] == "Bitte tragen Sie sich ein."
    assert booking["window"] == {"state": "open", "begin": "2026-11-04", "end": "2026-11-12"}
    assert [host["name"] for host in booking["hosts"]] == ["Frau Muster", "Herr Beispiel"]
    assert booking["hosts"][0]["location"] == "R 101"
    assert [day["date"] for day in booking["days"]] == ["2026-11-17", "2026-11-19"]
    assert booking["days"][0]["slots"][0] == {"id": "slot-1", "begin": "15:00", "end": "15:15", "closed": False}
    assert booking["days"][0]["slots"][2]["closed"] is True
    assert [child["name"] for child in booking["children"]] == ["Kim Muster", "Lou Muster"]
    assert booking["profiles_missing"] is False
    assert booking["mine"] == [] and booking["taken"] == []


def test_times_are_shown_in_school_time_even_when_the_school_answers_in_utc():
    assert moment_of("2026-11-17T14:00:00Z").strftime("%d.%m. %H:%M") == "17.11. 15:00"
    assert moment_of("2026-11-17T14:00:00+00:00").strftime("%H:%M") == "15:00"
    assert moment_of("2026-07-01T14:00:00+00:00").strftime("%H:%M") == "16:00"
    assert moment_of("2026-11-17T15:00:00").strftime("%H:%M") == "15:00"
    assert moment_of("kein Datum") is None


def test_a_past_slot_cannot_be_chosen():
    school = BookingSchool()
    late = datetime(2026, 11, 17, 14, 10, tzinfo=timezone.utc).timestamp()
    service, token = service_for(school, late)
    slots = booking_of(service, token)["days"][0]["slots"]
    assert [slot["closed"] for slot in slots] == [True, False, True]


def test_another_family_shows_up_as_taken_without_their_child():
    school = BookingSchool()
    school.booked_by_other("slot-1", "host-1")
    service, token = service_for(school)
    booking = booking_of(service, token)
    assert booking["taken"] == [{"slot": "slot-1", "host": "host-1"}]
    assert booking["mine"] == []
    assert "Fremdes Kind" not in json.dumps(booking)
    assert "other-slot-1" not in json.dumps(booking)


def test_the_own_booking_is_listed_with_teacher_time_and_child():
    school = BookingSchool()
    booked = school.book_mine()
    service, token = service_for(school)
    mine = booking_of(service, token)["mine"]
    assert len(mine) == 1
    assert mine[0]["id"] == booked
    assert (mine[0]["teacher"], mine[0]["location"], mine[0]["date"]) == ("Frau Muster", "R 101", "2026-11-17")
    assert (mine[0]["begin"], mine[0]["end"], mine[0]["editable"]) == ("15:00", "15:15", True)
    assert mine[0]["children"] == [{"id": "kim.muster", "name": "Kim Muster"}]


def test_an_own_booking_after_the_window_stays_visible_but_read_only():
    school = BookingSchool()
    booked = school.book_mine(editable=False)
    service, token = service_for(school, AFTER_WINDOW)
    booking = booking_of(service, token)
    assert booking["window"]["state"] == "after"
    assert [(entry["id"], entry["editable"]) for entry in booking["mine"]] == [(booked, False)]
    result = service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)
    assert result["message_key"] == GONE_KEY
    assert school.sent == []


def test_only_children_of_this_account_are_offered():
    school = BookingSchool(children=[KIM, STRANGER])
    service, token = service_for(school)
    booking = booking_of(service, token)
    assert [child["id"] for child in booking["children"]] == ["kim.muster"]
    assert booking["withheld"] == 1
    assert "Nora" not in json.dumps(booking)


def test_a_child_of_two_profiles_is_not_offered():
    school = BookingSchool(children=[KIM])
    profiles = [{"child_id": "1", "name": "Kim Muster"}, {"child_id": "2", "name": "Kim Muster"}]
    service, token = service_for(school, profiles=profiles)
    assert booking_of(service, token)["children"] == []


def test_no_known_child_means_no_booking_at_all():
    school = BookingSchool(children=[STRANGER])
    service, token = service_for(school)
    booking = booking_of(service, token)
    assert booking["profiles_missing"] is True
    result = book(service, token, children=["nora.fremd"])
    assert result["message_key"] == SUBMIT_NO_PROFILE_KEY
    assert school.sent == []


def test_an_unreadable_child_list_counts_as_unknown_not_as_no_children():
    assert children_of("<div id='attendee-wizard'></div>") is None
    assert children_of("<script id='attendee-children'>kaputt</script>") is None
    assert children_of("<script id='attendee-children'>[]</script>") == []


def test_a_failed_read_raises_and_never_looks_like_no_bookings():
    school = BookingSchool()
    school.unavailable.add(APPOINTMENTS_PATH)
    service, token = service_for(school)
    with pytest.raises(DataError):
        service.page(token)


def test_booking_sends_exactly_what_the_school_page_sends_and_confirms_by_reading_again():
    school = BookingSchool()
    service, token = service_for(school)
    result = book(service, token)
    assert result["ok"] is True
    assert result["state"] == "done"
    method, url, payload, headers = school.sent[0]
    assert (method, url) == ("POST", ORIGIN + BOOKINGS_PATH)
    assert payload == {"timeslotId": "slot-2", "hostId": "host-1", "childrenIds": ["kim.muster"]}
    assert headers["Origin"] == ORIGIN
    assert headers["Referer"] == ORIGIN + WIZARD_PATH
    assert [entry["slot"] for entry in result["page"]["booking"]["mine"]] == ["slot-2"]


def test_the_same_request_is_sent_only_once():
    school = BookingSchool()
    service, token = service_for(school)
    assert book(service, token)["ok"] is True
    again = book(service, token)
    assert again["message_key"] == SUBMIT_ALREADY_KEY
    assert len(school.sent) == 1


@pytest.mark.parametrize(
    "request_id, confirmed, key",
    [(REQUEST, False, SUBMIT_UNCONFIRMED_KEY), ("", True, SUBMIT_INVALID_REQUEST_KEY), ("kurz", True, SUBMIT_INVALID_REQUEST_KEY)],
)
def test_nothing_goes_out_without_a_confirmation_and_a_request_id(request_id, confirmed, key):
    school = BookingSchool()
    service, token = service_for(school)
    assert book(service, token, request=request_id, confirmed=confirmed)["message_key"] == key
    assert school.sent == []


@pytest.mark.parametrize(
    "values, key",
    [
        ({"slot": "slot-1", "host": "host-1", "children": ["kim.muster"]}, TAKEN_KEY),
        ({"slot": "slot-3", "host": "host-1", "children": ["kim.muster"]}, TAKEN_KEY),
        ({"slot": "unbekannt", "host": "host-1", "children": ["kim.muster"]}, TAKEN_KEY),
        ({"slot": "slot-2", "host": "unbekannt", "children": ["kim.muster"]}, TAKEN_KEY),
        ({"slot": "slot-2", "host": "host-1", "children": []}, CHILD_KEY),
        ({"slot": "slot-2", "host": "host-1", "children": ["nora.fremd"]}, CHILD_KEY),
        ({"slot": "slot-2", "host": "host-1", "children": "kim.muster"}, CHILD_KEY),
    ],
)
def test_a_choice_the_school_no_longer_offers_is_refused_before_sending(values, key):
    school = BookingSchool()
    school.booked_by_other("slot-1", "host-1")
    service, token = service_for(school)
    result = service.submit_booking(token, "book", values, REQUEST, True)
    assert result["message_key"] == key
    assert result["page"]["booking"]["taken"] == [{"slot": "slot-1", "host": "host-1"}]
    assert school.sent == []


def test_a_slot_of_another_teacher_stays_free():
    school = BookingSchool()
    school.booked_by_other("slot-2", "host-2")
    service, token = service_for(school)
    assert book(service, token, slot="slot-2", host="host-1")["ok"] is True


def test_booking_outside_the_window_is_refused_before_sending():
    school = BookingSchool()
    service, token = service_for(school, AFTER_WINDOW)
    assert book(service, token)["message_key"] == CLOSED_KEY
    assert school.sent == []


def test_the_school_refusal_is_passed_on_in_its_own_words():
    school = BookingSchool()
    school.refusal = (400, {"messages": ["Sie haben bereits einen Termin bei dieser Lehrkraft."]})
    service, token = service_for(school)
    result = book(service, token)
    assert result["ok"] is False
    assert result["message_key"] == REFUSED_KEY
    assert result["errors"] == ["Sie haben bereits einen Termin bei dieser Lehrkraft."]
    assert result["state"] == "invalid"
    assert result["page"]["booking"]["mine"] == []
    school.refusal = None
    assert book(service, token)["ok"] is True


def test_a_refusal_without_words_names_the_status():
    school = BookingSchool()
    school.refusal = (403, {})
    service, token = service_for(school)
    result = book(service, token)
    assert result["message_key"] == SUBMIT_REJECTED_KEY
    assert "403" in result["message"]


def test_a_lost_answer_is_settled_by_reading_again():
    school = BookingSchool()
    school.lost_answer = requests.ConnectionError("weg")
    service, token = service_for(school)
    result = book(service, token)
    assert result["ok"] is True
    assert len(school.sent) == 1


def test_a_lost_request_that_did_not_arrive_stays_unclear_and_blocks_a_blind_repeat():
    school = BookingSchool()
    school.silent = True
    service, token = service_for(school)
    result = book(service, token)
    assert result["ok"] is False
    assert result["state"] == "uncertain"
    assert result["message_key"] == SUBMIT_UNCERTAIN_KEY
    again = book(service, token)
    assert again["state"] == "uncertain"
    assert len(school.sent) == 1


def test_a_signed_out_answer_is_not_taken_for_success():
    school = BookingSchool()
    school.signed_out = True
    service, token = service_for(school)
    result = book(service, token)
    assert result["ok"] is False
    assert result["message_key"] == SUBMIT_SIGNED_OUT_KEY


def test_changing_the_children_keeps_time_and_teacher():
    school = BookingSchool()
    booked = school.book_mine()
    service, token = service_for(school)
    values = {"booking": booked, "children": ["kim.muster", "lou.muster"]}
    result = service.submit_booking(token, "change", values, REQUEST, True)
    assert result["ok"] is True
    method, url, payload, _headers = school.sent[0]
    assert (method, url) == ("PUT", ORIGIN + BOOKINGS_PATH + "/" + booked)
    assert payload == {"id": booked, "timeslotId": "slot-1", "hostId": "host-1", "childrenIds": ["kim.muster", "lou.muster"]}
    assert len(result["page"]["booking"]["mine"][0]["children"]) == 2


def test_cancelling_sends_a_delete_and_confirms_the_booking_is_gone():
    school = BookingSchool()
    booked = school.book_mine()
    service, token = service_for(school)
    result = service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)
    assert result["ok"] is True
    method, url, payload, _headers = school.sent[0]
    assert (method, url, payload) == ("DELETE", ORIGIN + BOOKINGS_PATH + "/" + booked, None)
    assert result["page"]["booking"]["mine"] == []


def test_another_familys_booking_can_never_be_changed_or_cancelled():
    school = BookingSchool()
    school.booked_by_other("slot-1", "host-1")
    service, token = service_for(school)
    for action in ("cancel", "change"):
        values = {"booking": "other-slot-1", "children": ["kim.muster"]}
        assert service.submit_booking(token, action, values, REQUEST, True)["message_key"] == GONE_KEY
    assert school.sent == []


def test_an_unknown_action_is_refused():
    school = BookingSchool()
    service, token = service_for(school)
    assert service.submit_booking(token, "purge", {}, REQUEST, True)["message_key"] == SUBMIT_INVALID_REQUEST_KEY
    assert school.sent == []


def test_a_page_without_the_booking_mount_is_not_treated_as_a_booking():
    school = BookingSchool()
    service, token = service_for(school)
    original = school.fetch
    school.fetch = lambda path, params=None: answer(path, "<div id='content'><h1>Weg</h1></div>") if path == WIZARD_PATH else original(path, params)
    assert "booking" not in service.page(token)
    assert book(service, token)["ok"] is False
    assert school.sent == []


def test_the_own_cancellation_is_noted_so_no_cancelled_push_follows():
    school = BookingSchool()
    booked = school.book_mine()
    service, token = service_for(school)
    notes = []
    service._note_own_change = notes.append
    assert service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)["ok"] is True
    assert notes == [{"row": ["17.11.2026", "15:00 - 15:15", "Frau Muster"]}] * 2


def test_school_bookings_feed_reminders_and_cancel_notices():
    school = BookingSchool()
    school.book_mine()
    service, token = service_for(school)
    page = service.page(token)
    facts = {"id": "elternsprechtag", "title": "Elternsprechtag", "day": None, "open": True, "page": token}
    found = conference_notices.bookings_of(page, facts)
    assert found == [{
        "id": "elternsprechtag|2026-11-17|15:00|frau muster",
        "key": "2026-11-17|15:00|frau muster",
        "conference": "elternsprechtag",
        "summary": "17.11.2026 · 15:00 - 15:15 · Frau Muster",
        "title": "Elternsprechtag",
        "day": "2026-11-17",
        "time": "15:00",
        "place": "elternsprechtag|slot-1|host-1",
    }]


def test_an_own_cancellation_key_matches_the_notice_key():
    from app.iserv.conferences import booking_key, same_booking

    noted = booking_key(["17.11.2026", "15:00 - 15:15", "Frau Muster"])
    assert same_booking(noted, "2026-11-17|15:00|frau muster")


FACTS = {"id": "elternsprechtag", "title": "Elternsprechtag", "day": None, "open": True, "page": "x"}
NOTICE_NOW = datetime(2026, 11, 13, 12, 0)


def known_notice_state(school):
    service, token = service_for(school)
    page = service.page(token)
    _pushes, state = conference_notices.plan({}, [FACTS], {FACTS["id"]: conference_notices.bookings_of(page, FACTS)}, NOTICE_NOW)
    return state


def later_notices(state, page):
    bookings = conference_notices.bookings_of(page, FACTS) if conference_notices.page_read(page) else None
    pages = {FACTS["id"]: bookings} if bookings is not None else {}
    occupied = conference_notices.occupied_of(page, FACTS)
    return conference_notices.plan(state, [FACTS], pages, NOTICE_NOW, occupied=occupied)[0]


def test_a_page_that_stopped_being_a_booking_page_causes_no_cancelled_push():
    school = BookingSchool()
    school.book_mine()
    state = known_notice_state(school)
    service, token = service_for(school)
    original = school.fetch
    school.fetch = lambda path, params=None: answer(path, "<div id='content'><h1>Weg</h1><p>Text</p></div>") if path == WIZARD_PATH else original(path, params)
    page = service.page(token)
    assert page["booking_unread"] is True
    assert later_notices(state, page) == []


def test_an_empty_page_counts_as_not_read():
    assert conference_notices.page_read({"blocks": [], "forms": []}) is False
    assert conference_notices.page_read({"blocks": [{"kind": "text", "text": "x"}]}) is True
    assert conference_notices.page_read({"booking": {"mine": []}, "blocks": []}) is True


@pytest.mark.parametrize("change", ["no_children", "no_profiles", "bad_time"])
def test_a_booking_that_only_became_unreadable_causes_no_cancelled_push(change):
    school = BookingSchool()
    school.book_mine()
    state = known_notice_state(school)
    profiles = None
    if change == "no_children":
        school.appointments[0].update(editable=False, children=None)
    elif change == "no_profiles":
        school.appointments[0]["editable"] = False
        profiles = []
    else:
        school.slots[0]["begin"] = "kaputt"
    service, token = service_for(school, profiles=profiles)
    assert later_notices(state, service.page(token)) == []


def test_a_slot_that_is_really_free_again_causes_the_cancelled_push():
    school = BookingSchool()
    school.book_mine()
    state = known_notice_state(school)
    school.appointments.clear()
    service, token = service_for(school)
    pushes = later_notices(state, service.page(token))
    assert [push["event"] for push in pushes] == [conference_notices.EVENT_CANCELLED]


def test_a_booking_with_a_child_of_another_profile_cannot_be_changed_or_cancelled():
    school = BookingSchool(children=[KIM, STRANGER])
    booked = school.book_mine(children=("kim.muster", "nora.fremd"))
    service, token = service_for(school)
    mine = booking_of(service, token)["mine"]
    assert mine[0]["editable"] is False
    assert [child["id"] for child in mine[0]["children"]] == ["kim.muster"]
    assert "nora" not in json.dumps(mine)
    for action in ("cancel", "change"):
        values = {"booking": booked, "children": ["kim.muster"]}
        assert service.submit_booking(token, action, values, REQUEST, True)["message_key"] == GONE_KEY
    assert school.sent == []


def test_a_booking_cannot_be_cancelled_when_no_child_is_known():
    school = BookingSchool(children=[STRANGER])
    booked = school.book_mine(children=("nora.fremd",))
    service, token = service_for(school)
    assert service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)["message_key"] == GONE_KEY
    assert school.sent == []


@pytest.mark.parametrize("slot", ["slot-3", "slot-past"])
def test_a_blocked_or_past_booking_is_read_only(slot):
    school = BookingSchool()
    school.slots.append({"id": "slot-past", "begin": "2026-11-01T15:00:00+01:00", "end": "2026-11-01T15:15:00+01:00", "blocked": False})
    booked = school.book_mine(slot=slot)
    service, token = service_for(school)
    assert booking_of(service, token)["mine"][0]["editable"] is False
    assert service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)["message_key"] == GONE_KEY
    assert school.sent == []


def test_a_failed_cancel_is_not_reported_as_cancelled_when_the_booking_stops_looking_own():
    school = BookingSchool()
    booked = school.book_mine()
    school.refusal = (500, {})
    service, token = service_for(school)
    original = school.send_json

    def failing(*args):
        school.appointments[0].update(editable=False, children=[{"id": "x", "name": "x"}])
        return original(*args)

    school.send_json = failing
    result = service.submit_booking(token, "cancel", {"booking": booked}, REQUEST, True)
    assert result["ok"] is False
    assert result["state"] == "uncertain"


def test_a_change_that_fails_and_changes_nothing_is_not_reported_as_changed():
    school = BookingSchool()
    booked = school.book_mine()
    school.refusal = (500, {})
    service, token = service_for(school)
    values = {"booking": booked, "children": ["kim.muster"]}
    result = service.submit_booking(token, "change", values, REQUEST, True)
    assert result["ok"] is False
    assert result["state"] == "uncertain"


def test_time_slots_nobody_can_read_are_an_error_not_an_empty_day():
    school = BookingSchool()
    for slot in school.slots:
        slot["begin"] = "kaputt"
    service, token = service_for(school)
    with pytest.raises(DataError):
        service.page(token)


def test_an_unreadable_booking_period_is_unknown_not_open():
    school = BookingSchool()
    original = school._conference
    school._conference = lambda: dict(original(), bookingBegin="kaputt")
    service, token = service_for(school)
    assert booking_of(service, token)["window"]["state"] == "unknown"
    assert book(service, token)["ok"] is True


def test_a_second_request_sends_on_what_it_read_itself():
    school = BookingSchool()
    service, token = service_for(school)
    assert book(service, token)["ok"] is True
    second = book(service, token, request="fedcba9876543210fedc")
    assert second["message_key"] == TAKEN_KEY
    assert len(school.sent) == 1


def test_an_unexpected_failure_after_sending_keeps_the_request_blocked():
    school = BookingSchool()
    original = school.send_json

    def broken(*args):
        original(*args)
        return SimpleNamespace(status_code=200, url=None, text=None, history=None, headers={})

    school.send_json = broken
    service, token = service_for(school)
    service._bookings._settled = lambda *args: (_ for _ in ()).throw(ValueError("kaputt"))
    with pytest.raises(ValueError):
        book(service, token)
    assert book(service, token)["state"] == "uncertain"
    assert len(school.sent) == 1


def test_many_teachers_are_asked_in_portions():
    school = BookingSchool()
    school.hosts = [
        {"id": "host-%d" % index, "userId": "u%d" % index, "userName": "Lehrkraft %d" % index, "location": None, "abbreviation": None}
        for index in range(85)
    ]
    service, token = service_for(school)
    service.page(token)
    asked = [params for path, params in school.fetched if path == APPOINTMENTS_PATH]
    assert [len(params) for params in asked] == [40, 40, 5]


def test_school_messages_read_both_answer_forms():
    assert school_messages(json.dumps({"messages": ["Eins", "<b>Zwei</b>"]})) == ["Eins", "Zwei"]
    assert school_messages(json.dumps({"message": "Eins"})) == ["Eins"]
    assert school_messages("kein JSON") == []


def test_only_real_wizard_addresses_count():
    assert conference_id_of(WIZARD_PATH) == CONFERENCE
    assert conference_id_of(WIZARD_PATH + "/") == CONFERENCE
    assert conference_id_of("/iserv/parentconference/attendee/conference/7") is None
    assert conference_id_of(WIZARD_PATH + "/../../x") is None


def test_send_json_stays_on_the_school_and_sends_json():
    calls = []

    class Session:
        headers = {}

        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return SimpleNamespace(status_code=200, headers={}, text="{}")

        def get(self, *args, **kwargs):
            raise AssertionError("no read expected")

        def post(self, *args, **kwargs):
            raise AssertionError("no form post expected")

    client = IServClient(ORIGIN, session=Session())
    client.send_json("POST", ORIGIN + BOOKINGS_PATH, {"a": 1}, {"Origin": ORIGIN})
    assert calls[0][0:2] == ("POST", ORIGIN + BOOKINGS_PATH)
    assert calls[0][2]["data"] == '{"a": 1}'
    assert calls[0][2]["headers"] == {"Content-Type": "application/json", "Origin": ORIGIN}
    client.send_json("DELETE", ORIGIN + BOOKINGS_PATH + "/1")
    assert calls[1][2]["data"] is None
    with pytest.raises(DataError):
        client.send_json("POST", "https://elsewhere.example/x", {"a": 1})


def test_the_report_names_the_booking_shapes_without_values():
    school = BookingSchool()
    school.book_mine()

    def unfollowed(path, limit, timeout, expired=None):
        clean, _, query = path.partition("?")
        params = [tuple(part.split("=", 1)) for part in query.split("&")] if query else []
        params = [(key.replace("%5B%5D", "[]"), value) for key, value in params]
        return school.fetch(clean, params)

    client = SimpleNamespace(fetch_unfollowed=unfollowed)
    report = "\n".join(conference_booking_lines(client, answer(WIZARD_PATH, wizard_page([KIM]))))
    assert "children 1" in report
    assert "Conference data: status 200" in report
    assert "Conference appointments: status 200" in report
    assert "timeslots[].begin" in report and "appointments[].editable" in report and "hosts[].userName" in report
    for private in ("Frau Muster", "Kim Muster", "kim.muster", "R 101", CONFERENCE):
        assert private not in report
    assert conference_booking_lines(client, answer("/iserv/parentconference/attendee/", "<h1>Liste</h1>")) == []
