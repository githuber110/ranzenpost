import json
from types import SimpleNamespace

import pytest
import requests

from app.conference_service import (
    CONFERENCE_UNKNOWN_KEY,
    SUBMIT_ALREADY_KEY,
    SUBMIT_CHOICE_KEY,
    SUBMIT_INVALID_KEY,
    SUBMIT_NO_PROFILE_KEY,
    SUBMIT_OK_KEY,
    SUBMIT_OPENED_KEY,
    SUBMIT_REJECTED_KEY,
    SUBMIT_REQUIRED_KEY,
    SUBMIT_STALE_KEY,
    SUBMIT_UNCERTAIN_KEY,
    SUBMIT_UNCONFIRMED_KEY,
    ConferenceService,
)
from app.iserv.errors import DataError
from tests.conference_school import BOOK_PATH, ORIGIN, TEACHER_PATH, ConferenceSchool, answer

REQUEST = "0123456789abcdef0123"
OTHER_REQUEST = "fedcba9876543210fedc"


KNOWN_PROFILES = [{"child_id": "c1", "name": "Kim Muster"}]


def rig(profiles=None):
    school = ConferenceSchool()
    known = KNOWN_PROFILES if profiles is None else profiles
    service = ConferenceService(SimpleNamespace(id="s1", _session=lambda: school, stored_children=lambda: list(known)))
    return school, service


def open_teacher(service):
    listed = service.conferences()
    detail = service.page(listed["items"][0]["page"])
    teachers = [block for block in detail["blocks"] if block["kind"] == "table"][-1]
    return detail, service.page(teachers["rows"][0]["links"][0]["page"])


def book(service, page, values, request_id=REQUEST, confirmed=True, check=None):
    form = page["forms"][0]
    return service.submit(page["page"], form["id"], check or form["check"], 0, values, request_id, confirmed)


GOOD_VALUES = {"booking[slot]": "101", "booking[child]": "501", "booking[note]": "Kurz"}


def booking_posts(school):
    return [pairs for url, pairs in school.sent if url == ORIGIN + BOOK_PATH]


def test_the_list_hands_out_page_tokens_and_no_school_addresses():
    _school, service = rig()
    listed = service.conferences()
    assert listed["empty"] is False
    assert [item["cells"][0] for item in listed["items"]] == ["Elternsprechtag Herbst", "Elternsprechtag Frühjahr"]
    assert len(listed["items"][0]["page"]) == 24
    assert listed["items"][1]["page"] == ""
    assert "/iserv/" not in json.dumps(listed) and "school.example" not in json.dumps(listed)


def test_a_page_shows_tables_and_forms_without_addresses_or_hidden_tokens():
    _school, service = rig()
    _detail, teacher = open_teacher(service)
    text = json.dumps(teacher, ensure_ascii=False)
    assert "/iserv/" not in text and "school.example" not in text and "token-book-1" not in text
    form = teacher["forms"][0]
    assert [field["kind"] for field in form["fields"]] == ["radio", "select", "textarea"]
    assert form["submits"] == [{"id": form["submits"][0]["id"], "label": "Buchen", "destructive": False}]
    assert len(form["submits"][0]["id"]) == 12 and int(form["submits"][0]["id"], 16) >= 0


def test_an_unknown_page_token_is_refused_after_reading_the_list_again():
    school, service = rig()
    with pytest.raises(DataError) as raised:
        service.page("0" * 24)
    assert raised.value.message_key == CONFERENCE_UNKNOWN_KEY
    assert "/iserv/parentconference/attendee/" in school.fetched


def test_a_list_token_survives_a_restart_by_reading_the_list_again():
    _school, service = rig()
    token = service.conferences()["items"][0]["page"]
    _other, fresh = rig()
    assert fresh.page(token)["title"] == "Elternsprechtag Herbst"


def test_a_malformed_page_token_is_refused_without_a_request():
    school, service = rig()
    with pytest.raises(DataError):
        service.page("../../iserv/mail")
    assert school.fetched == []


def test_booking_sends_the_school_form_and_confirms_by_reading_the_page_again():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["ok"] is True and result["state"] == "done" and result["message_key"] == SUBMIT_OK_KEY
    assert result["notices"] == ["Der Termin wurde gebucht."]
    assert booking_posts(school) == [[
        ("booking[_token]", "token-book-1"),
        ("booking[slot]", "101"),
        ("booking[child]", "501"),
        ("booking[note]", "Kurz"),
        ("booking[submit]", ""),
    ]]
    assert school.bookings == {"31": "101"}
    slot = result["page"]["forms"][0]["fields"][0]
    assert slot["options"][0]["disabled"] is True
    assert school.fetched[-1] == TEACHER_PATH


def test_nothing_is_sent_without_the_confirmation_from_the_app():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES, confirmed=False)
    assert result["ok"] is False and result["message_key"] == SUBMIT_UNCONFIRMED_KEY
    assert school.sent == []


def test_a_missing_required_choice_stops_before_sending():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, {"booking[slot]": "101"})
    assert result["state"] == "invalid" and result["message_key"] == SUBMIT_REQUIRED_KEY
    assert result["missing"] == ["Kind"]
    assert school.sent == []


def test_a_choice_the_school_does_not_offer_is_refused_before_sending():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, dict(GOOD_VALUES, **{"booking[slot]": "102"}))
    assert result["message_key"] == SUBMIT_CHOICE_KEY and result["state"] == "refused"
    assert school.sent == []


def test_a_validation_error_of_the_school_is_shown_and_nothing_counts_as_booked():
    school, service = rig()
    school.browser_checks = False
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, {"booking[slot]": "101", "booking[child]": ""})
    assert result["ok"] is False and result["state"] == "invalid" and result["message_key"] == SUBMIT_INVALID_KEY
    assert result["errors"] == ["Das Formular enthält Fehler.", "Bitte wählen Sie ein Kind aus."]
    assert result["page"]["page"] == teacher["page"]
    assert result["page"]["forms"][0]["fields"][1]["error"] == "Bitte wählen Sie ein Kind aus."
    assert school.bookings == {}
    again = book(service, teacher, GOOD_VALUES)
    assert again["ok"] is True
    assert len(booking_posts(school)) == 2


def test_a_server_failure_leaves_the_outcome_open_and_is_never_sent_again():
    school, service = rig()
    school.failing_slot = "103"
    _detail, teacher = open_teacher(service)
    values = dict(GOOD_VALUES, **{"booking[slot]": "103"})
    result = book(service, teacher, values)
    assert result["ok"] is False and result["state"] == "uncertain" and result["message_key"] == SUBMIT_UNCERTAIN_KEY
    assert result["diagnosis"]["post_status"] == 502
    assert result["page"]["title"] == "Frau Muster"
    repeated = book(service, teacher, values)
    assert repeated["state"] == "uncertain"
    assert len(booking_posts(school)) == 1


def test_a_lost_connection_while_sending_is_uncertain_and_not_retried():
    school, service = rig()
    _detail, teacher = open_teacher(service)

    def broken(url, data, timeout=30, follow_redirects=True, headers=None):
        school.sent.append((url, list(data)))
        raise requests.ConnectionError("reset")

    school.post_absolute = broken
    result = book(service, teacher, GOOD_VALUES)
    assert result["state"] == "uncertain"
    assert len(school.sent) == 1


def test_an_answer_without_any_change_on_the_page_is_uncertain():
    school, service = rig()
    school.quiet_slot = "101"
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["state"] == "uncertain" and result["ok"] is False


def test_a_refusal_of_the_school_is_reported_with_its_status():
    school, service = rig()
    school.refusing = True
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["state"] == "rejected" and result["message_key"] == SUBMIT_REJECTED_KEY
    assert result["message_vars"] == {"status": 403}


def test_the_same_request_is_answered_from_memory_after_success():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    assert book(service, teacher, GOOD_VALUES)["ok"] is True
    repeated = book(service, teacher, GOOD_VALUES)
    assert repeated["ok"] is True and repeated["message_key"] == SUBMIT_ALREADY_KEY
    assert len(booking_posts(school)) == 1


def test_a_changed_form_is_refused_and_the_fresh_page_is_returned():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES, check="0" * 16)
    assert result["message_key"] == SUBMIT_STALE_KEY
    assert result["page"]["title"] == "Frau Muster"
    assert school.sent == []


def test_cancelling_a_booking_uses_the_row_form_and_reads_the_page_again():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    book(service, teacher, GOOD_VALUES)
    detail = service.page(service.conferences()["items"][0]["page"])
    bookings = [block for block in detail["blocks"] if block["kind"] == "table"][0]
    form = detail["forms"][bookings["rows"][0]["forms"][0]]
    assert form["destructive"] is True and form["fields"] == []
    result = service.submit(detail["page"], form["id"], form["check"], 0, {}, OTHER_REQUEST, True)
    assert result["ok"] is True and result["notices"] == ["Der Termin wurde abgesagt."]
    assert school.bookings == {}
    rows = [block for block in result["page"]["blocks"] if block["kind"] == "table"][0]["rows"]
    assert rows == []


def test_a_get_form_opens_the_page_it_names_without_a_confirmation():
    school, service = rig()
    page = (
        "<div id='content'><h1>Auswahl</h1><form method='get' action='/iserv/parentconference/attendee/conference/7'>"
        "<select name='teacher'><option value='12'>Frau Muster</option></select><button>Anzeigen</button></form></div>"
    )
    original = school.page

    def serve(path):
        if path.startswith("/iserv/parentconference/attendee/choose"):
            return answer("/iserv/parentconference/attendee/choose", page)
        return original(path)

    school.page = serve
    token = service.token("/iserv/parentconference/attendee/choose")
    chooser = service.page(token)
    form = chooser["forms"][0]
    result = service.submit(token, form["id"], form["check"], 0, {"teacher": "12"})
    assert result["ok"] is True and result["message_key"] == SUBMIT_OPENED_KEY
    assert school.fetched[-1] == "/iserv/parentconference/attendee/conference/7?teacher=12"
    assert school.sent == []


def child_field(page):
    return page["forms"][0]["fields"][1]


def test_the_child_choice_offers_only_profiles_known_to_this_account():
    school, service = rig()
    page = school.teacher_page().replace('<option value="501">Kim</option>', '<option value="501">Kim</option><option value="502">Ola Fremd</option>')
    school.teacher_page = lambda invalid=False, chosen="": page
    _detail, teacher = open_teacher(service)
    field = child_field(teacher)
    assert [option["value"] for option in field["options"]] == ["", "501"]
    assert field["profile"] is True and field["withheld"] == 1 and field["profiles_missing"] is False
    refused = book(service, teacher, dict(GOOD_VALUES, **{"booking[child]": "502"}))
    assert refused["message_key"] == SUBMIT_CHOICE_KEY
    assert school.sent == []


def test_without_a_matching_profile_the_form_says_so_and_sends_nothing():
    school, service = rig(profiles=[{"child_id": "c9", "name": "Ola Fremd"}])
    _detail, teacher = open_teacher(service)
    field = child_field(teacher)
    assert [option["value"] for option in field["options"]] == [""]
    assert field["profiles_missing"] is True
    result = book(service, teacher, GOOD_VALUES)
    assert result["message_key"] == SUBMIT_NO_PROFILE_KEY and result["ok"] is False
    assert school.sent == []


def test_a_name_shared_by_two_known_profiles_is_never_offered():
    school, service = rig(profiles=[{"child_id": "c1", "name": "Kim Muster"}, {"child_id": "c2", "name": "Kim Beispiel"}])
    _detail, teacher = open_teacher(service)
    assert child_field(teacher)["profiles_missing"] is True


def test_sending_a_form_notes_the_own_change_for_the_poller(tmp_path):
    from app.store import Store

    store = Store(tmp_path / "data")
    school = ConferenceSchool()
    service = ConferenceService(
        SimpleNamespace(id="s1", _session=lambda: school, stored_children=lambda: list(KNOWN_PROFILES), store=store),
        clock=lambda: 1_800_000_000,
    )
    _detail, teacher = open_teacher(service)
    book(service, teacher, GOOD_VALUES)
    assert store.load_config()["conference_own_change"] == 1_800_000_000


def detail_with_bookings(service, school, *slots):
    for slot in slots:
        school.bookings[str(school.next_booking)] = slot
        school.next_booking += 1
    return service.page(service.conferences()["items"][0]["page"])


def cancel_forms(detail):
    table = [block for block in detail["blocks"] if block["kind"] == "table"][0]
    return [detail["forms"][row["forms"][0]] for row in table["rows"]]


def test_an_old_cancel_form_never_hits_the_booking_that_moved_into_its_place():
    school, service = rig()
    school.shared_cancel = True
    detail = detail_with_bookings(service, school, "101", "103")
    first, _second = cancel_forms(detail)
    done = service.submit(detail["page"], first["id"], first["check"], 0, {}, REQUEST, True)
    assert done["ok"] is True and set(school.bookings.values()) == {"103"}
    again = service.submit(detail["page"], first["id"], first["check"], 0, {}, OTHER_REQUEST, True)
    assert again["ok"] is False and again["message_key"] == SUBMIT_STALE_KEY
    assert set(school.bookings.values()) == {"103"}


def test_the_form_check_ignores_only_token_values():
    school, service = rig()
    school.shared_cancel = True
    detail = detail_with_bookings(service, school, "101")
    form = cancel_forms(detail)[0]
    original = school.detail_page
    school.detail_page = lambda notice="": original(notice).replace('value="token-cancel"', 'value="token-cancel-fresh"')
    result = service.submit(detail["page"], form["id"], form["check"], 0, {}, REQUEST, True)
    assert result["ok"] is True


def test_a_warning_of_the_school_is_never_counted_as_done():
    school, service = rig()
    school.warning_slot = "101"
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["ok"] is False and result["state"] == "invalid"
    assert "Der Termin ist bereits vergeben." in result["errors"]


def test_a_success_next_to_an_error_is_unclear():
    school, service = rig()
    school.mixed_slot = "101"
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["ok"] is False and result["state"] == "uncertain"


def test_a_change_that_does_not_match_the_sent_choice_is_unclear():
    school, service = rig()
    school.unrelated_slot = "101"
    _detail, teacher = open_teacher(service)
    result = book(service, teacher, GOOD_VALUES)
    assert result["ok"] is False and result["state"] == "uncertain"


def test_the_same_request_running_twice_at_once_is_sent_only_once():
    import threading

    school, service = rig()
    school.quiet_slot = "101"
    _detail, teacher = open_teacher(service)
    second_checked = threading.Event()
    first_done = threading.Event()
    calls = {"count": 0}
    original_fetch = school.fetch_or_raise

    def fetch(path, params=None):
        if path == TEACHER_PATH:
            calls["count"] += 1
            if calls["count"] == 1:
                second_checked.wait(2)
            else:
                second_checked.set()
                first_done.wait(2)
        return original_fetch(path, params)

    school.fetch_or_raise = fetch
    results = []

    def first():
        results.append(book(service, teacher, GOOD_VALUES))
        first_done.set()

    def second():
        results.append(book(service, teacher, GOOD_VALUES))
        second_checked.set()

    one = threading.Thread(target=first)
    two = threading.Thread(target=second)
    one.start()
    while calls["count"] < 1:
        pass
    two.start()
    one.join(5)
    two.join(5)
    assert len(results) == 2
    assert len(booking_posts(school)) == 1


def test_a_row_form_carries_its_row_for_the_confirmation():
    school, service = rig()
    detail = detail_with_bookings(service, school, "101")
    assert cancel_forms(detail)[0]["row"] == ["14:00 - 14:10", "Frau Muster", "R 101", "Kim", ""]


def test_an_own_cancellation_is_noted_by_its_booking_for_the_poller(tmp_path):
    from app.store import Store

    store = Store(tmp_path / "data")
    school = ConferenceSchool()
    service = ConferenceService(
        SimpleNamespace(id="s1", _session=lambda: school, stored_children=lambda: list(KNOWN_PROFILES), store=store),
        clock=lambda: 1_800_000_000,
    )
    detail = detail_with_bookings(service, school, "101")
    form = cancel_forms(detail)[0]
    assert service.submit(detail["page"], form["id"], form["check"], 0, {}, REQUEST, True)["ok"] is True
    assert store.load_config()["conference_own_cancellations"] == [{"key": "|14:00|frau muster", "at": 1_800_000_000}]
    assert "conference_own_change" not in store.load_config()


def custom_page(school, form_html):
    page = "<div id='content'><h1>Frau Muster</h1><form method='post' action='%s'>%s<button name='go'>Buchen</button></form></div>" % (BOOK_PATH, form_html)
    original = school.page

    def serve(path):
        if path.split("?", 1)[0] == TEACHER_PATH:
            return answer(TEACHER_PATH, page)
        return original(path)

    school.page = serve


def test_a_choice_with_an_unusual_name_is_still_filtered_by_known_profiles():
    school, service = rig()
    custom_page(school, "<label for='w'>Für</label><select id='w' name='booking[x]'><option value='501'>Kim Muster</option><option value='502'>Ola Fremd</option></select>")
    _detail, teacher = open_teacher(service)
    field = teacher["forms"][0]["fields"][0]
    assert field["profile"] is True
    assert [option["value"] for option in field["options"]] == ["501"]


def test_a_hidden_profile_id_must_be_a_known_profile():
    school, service = rig()
    custom_page(school, "<input type='hidden' name='booking[student]' value='c9'><input type='radio' name='booking[slot]' value='101'> 14:00")
    _detail, teacher = open_teacher(service)
    assert teacher["forms"][0]["fields"][0]["kind"] == "radio"
    assert any(field.get("profiles_missing") for field in teacher["forms"][0]["fields"]) or teacher["forms"][0].get("profiles_missing")
    result = book(service, teacher, {"booking[slot]": "101"})
    assert result["message_key"] == SUBMIT_NO_PROFILE_KEY
    assert school.sent == []


def test_a_hidden_profile_id_of_a_known_profile_is_accepted():
    school, service = rig()
    custom_page(school, "<input type='hidden' name='booking[student]' value='c1'><input type='radio' name='booking[slot]' value='101'> 14:00")
    _detail, teacher = open_teacher(service)
    assert not teacher["forms"][0].get("profiles_missing")


def test_a_sign_in_page_as_answer_is_unclear_and_remembered_as_unclear():
    school, service = rig()
    _detail, teacher = open_teacher(service)
    login = "<form method='post' action='/iserv/auth/login'><input name='_username'><input type='password' name='_password'></form>"
    school.post_absolute = lambda url, data, timeout=30, follow_redirects=True, headers=None: (school.sent.append((url, list(data))) or answer("/iserv/auth/login", login))
    result = book(service, teacher, GOOD_VALUES)
    assert result["state"] == "uncertain" and result["page"]["title"] == "Frau Muster"
    repeated = book(service, teacher, GOOD_VALUES)
    assert repeated["state"] == "uncertain"
    assert len(booking_posts(school)) == 1
