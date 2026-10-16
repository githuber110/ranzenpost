from types import SimpleNamespace

import pytest
import requests

from app.conference_service import (
    CONFERENCE_UNKNOWN_KEY,
    SUBMIT_ALREADY_KEY,
    SUBMIT_INVALID_REQUEST_KEY,
    SUBMIT_OK_KEY,
    SUBMIT_OPENED_KEY,
    SUBMIT_UNCERTAIN_KEY,
    SUBMIT_UNCONFIRMED_KEY,
    ConferenceService,
    form_check,
    submit_key,
)
from app.iserv.conferences import parse_conference_page, parse_conferences
from app.iserv.errors import DataError
from tests.conference_school import ORIGIN, answer

MINE = "/iserv/parentconference/attendee/mine"
CANCEL = "/iserv/parentconference/attendee/booking/31/cancel"
DELETE = "/iserv/parentconference/attendee/booking/31/delete"
EDIT = "/iserv/parentconference/attendee/booking/31/edit"
REQUEST = "0123456789abcdef0123"
OTHER = "fedcba9876543210fedc"
ROW = "<tr><td>14:00</td><td>Frau Muster</td><td>{action}</td></tr>"
EDIT_PAGE = (
    "<div id='content'><h1>Termin ändern</h1><form method='post' action='%s'>"
    "<input type='hidden' name='_token' value='t'><textarea name='note'></textarea>"
    "<button>Speichern</button></form></div>" % EDIT
)


class School:
    def __init__(self, action):
        self.action = action
        self.booked = True
        self.fetched = []
        self.failing = False
        self.forgotten = 0

    def mine(self):
        rows = ROW.format(action=self.action) if self.booked else ""
        return "<div id='content'><h1>Meine Termine</h1><table><tbody>%s</tbody></table></div>" % rows

    def fetch(self, path, params=None):
        self.fetched.append(path)
        clean = path.split("?", 1)[0]
        if clean == MINE:
            return answer(MINE, self.mine())
        if clean in (CANCEL, DELETE):
            if self.failing:
                raise requests.ReadTimeout("timed out")
            self.booked = False
            return answer(MINE, self.mine(), history=[answer(clean, "", status=302)])
        if clean == EDIT:
            return answer(EDIT, EDIT_PAGE)
        return answer(clean, "<h1>Nicht gefunden</h1>", status=404)

    def fetch_or_raise(self, path, params=None):
        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed")
        return response

    def forget_kept(self):
        self.forgotten += 1

    def post_absolute(self, url, data, timeout=30, follow_redirects=True, headers=None):
        raise AssertionError("no post expected")


def rig(action):
    school = School(action)
    service = ConferenceService(SimpleNamespace(id="s1", _session=lambda: school, stored_children=lambda: []))
    token = service.token(MINE)
    return school, service, token


def writes_to(school, path):
    return [asked for asked in school.fetched if asked.split("?", 1)[0] == path]


def test_a_get_form_that_deletes_is_a_write_and_never_runs_without_confirmation():
    form_html = (
        "<form method='get' action='%s'><input type='hidden' name='confirm' value='1'>"
        "<button>Absagen</button></form>" % DELETE
    )
    school, service, token = rig(form_html)
    shown = service.page(token)
    form = shown["forms"][0]
    assert form["writes"] is True and form["destructive"] is True
    key = form["submits"][0]["id"]
    refused = service.submit(token, form["id"], form["check"], key, {}, "", False)
    assert refused["ok"] is False and refused["message_key"] == SUBMIT_UNCONFIRMED_KEY
    missing = service.submit(token, form["id"], form["check"], key, {}, "", True)
    assert missing["message_key"] == SUBMIT_INVALID_REQUEST_KEY
    assert writes_to(school, DELETE) == []
    done = service.submit(token, form["id"], form["check"], key, {}, REQUEST, True)
    assert done["ok"] is True and done["message_key"] == SUBMIT_OK_KEY and done["state"] == "done"
    assert writes_to(school, DELETE) == [DELETE + "?confirm=1"]
    assert school.forgotten == 1
    again = service.submit(token, form["id"], form["check"], key, {}, REQUEST, True)
    assert again["message_key"] == SUBMIT_ALREADY_KEY
    assert len(writes_to(school, DELETE)) == 1


def test_a_reading_get_form_still_opens_without_confirmation():
    form_html = (
        "<form method='get' action='/iserv/parentconference/attendee/conference/7'>"
        "<select name='teacher'><option value='12'>Frau Muster</option></select><button>Anzeigen</button></form>"
    )
    _school, service, token = rig(form_html)
    form = service.page(token)["forms"][0]
    assert form["writes"] is False


def test_a_cancel_link_in_a_row_is_no_row_tap_but_a_confirmed_action():
    school, service, token = rig("<a href='%s'>Absagen</a>" % CANCEL)
    shown = service.page(token)
    row = [block for block in shown["blocks"] if block["kind"] == "table"][0]["rows"][0]
    assert row["links"] == []
    form = shown["forms"][row["forms"][0]]
    assert form["writes"] is True and form["destructive"] is True and form["method"] == "get"
    assert form["row"] == ["14:00", "Frau Muster", "Absagen"]
    assert writes_to(school, CANCEL) == []
    refused = service.submit(token, form["id"], form["check"], form["submits"][0]["id"], {}, REQUEST, False)
    assert refused["message_key"] == SUBMIT_UNCONFIRMED_KEY
    assert writes_to(school, CANCEL) == []
    done = service.submit(token, form["id"], form["check"], form["submits"][0]["id"], {}, REQUEST, True)
    assert done["ok"] is True and done["state"] == "done"
    assert writes_to(school, CANCEL) == [CANCEL]


def test_a_page_token_for_a_write_address_is_refused_without_a_request():
    school, service, _token = rig("")
    with pytest.raises(DataError) as raised:
        service.page(service.token(CANCEL))
    assert raised.value.message_key == CONFERENCE_UNKNOWN_KEY
    assert writes_to(school, CANCEL) == []


def test_the_list_never_hands_out_a_write_link_as_the_row_page():
    page = (
        "<table><tbody><tr><td>15.09.2026</td><td><a href='%s'>Absagen</a></td></tr>"
        "<tr><td>22.09.2026</td><td><a href='/iserv/parentconference/attendee/2/book'>Termin buchen</a></td></tr>"
        "</tbody></table>" % CANCEL
    )
    items = parse_conferences(page, ORIGIN + "/iserv/parentconference/attendee/")["items"]
    assert items[0]["paths"] == []
    assert items[1]["paths"] == ["/iserv/parentconference/attendee/2/book"]


def test_a_lost_connection_on_a_write_get_is_uncertain_and_never_sent_twice():
    school, service, token = rig("<a href='%s'>Absagen</a>" % CANCEL)
    school.failing = True
    form = service.page(token)["forms"][0]
    first = service.submit(token, form["id"], form["check"], form["submits"][0]["id"], {}, REQUEST, True)
    assert first["ok"] is False and first["message_key"] == SUBMIT_UNCERTAIN_KEY
    again = service.submit(token, form["id"], form["check"], form["submits"][0]["id"], {}, REQUEST, True)
    assert again["message_key"] == SUBMIT_UNCERTAIN_KEY
    assert len(writes_to(school, CANCEL)) == 1


def test_a_write_link_that_only_shows_a_form_opens_that_page():
    school, service, token = rig("<a href='%s'>Ändern</a>" % EDIT)
    form = service.page(token)["forms"][0]
    assert form["writes"] is True
    result = service.submit(token, form["id"], form["check"], form["submits"][0]["id"], {}, REQUEST, True)
    assert result["ok"] is True and result["message_key"] == SUBMIT_OPENED_KEY and result["state"] == "opened"
    assert result["page"]["title"] == "Termin ändern"
    assert school.booked is True


SWAPPED_A = (
    "<div id='content'><form method='post' action='/iserv/parentconference/attendee/booking/31'>"
    "<input type='hidden' name='_token' value='t'>"
    "<button name='op' value='keep'>Behalten</button><button name='op' value='cancel'>Absagen</button></form></div>"
)
SWAPPED_B = SWAPPED_A.replace(
    "<button name='op' value='keep'>Behalten</button><button name='op' value='cancel'>Absagen</button>",
    "<button name='op' value='cancel'>Absagen</button><button name='op' value='keep'>Behalten</button>",
)


def test_a_submit_button_is_chosen_by_name_value_and_label_not_by_position():
    base = ORIGIN + "/iserv/parentconference/attendee/booking/31"
    before = parse_conference_page(SWAPPED_A, base)["forms"][0]
    after = parse_conference_page(SWAPPED_B, base)["forms"][0]
    assert form_check(before) == form_check(after)
    keep = submit_key(before["submits"][0])
    chosen = ConferenceService._chosen_submit(after, keep)
    assert (chosen["value"], chosen["label"]) == ("keep", "Behalten")
    assert ConferenceService._chosen_submit(after, 0) is None
    assert ConferenceService._chosen_submit(after, "0") is None
