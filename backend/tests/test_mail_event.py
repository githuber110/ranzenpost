import pytest
import requests
from fastapi.testclient import TestClient

from app.iserv import mail_web
from app.iserv.errors import DataError
from app.mail_service import MailService
from app.server import create_app
from tests.mail_fakes import FakeImap, plain_mail
from tests.mail_web_fakes import TOKEN, FakeMailWeb
from tests.test_mail_settings import service_with_web

LONG_BODY = "Wir fahren zum Wildpark. " * 60
REQUEST = "0123456789abcdef0123"
OTHER = "fedcba9876543210fedc"
SIGN_IN = "<form action='/iserv/auth/login' method='post'><input name='_username'><input type='password' name='_password'></form>"


def with_mail(tmp_path, web=None):
    service, school, web = service_with_web(tmp_path, web)
    connection = service.connection(school)
    imap = FakeImap()
    raw = plain_mail().replace(b"Line one\nLine two\n", LONG_BODY.encode())
    imap.folders["INBOX"][1]["raw"] = raw
    connection._mail_service = MailService(connection, opener=lambda host: imap)
    return service, school, web, imap


def test_the_create_path_comes_from_the_calendar_page_and_falls_back():
    page = '<script type="application/json" id="calendar-x">{"r": {"calendar_create_event": "/iserv/calendar/neu"}}</script>'
    assert mail_web.create_event_path(page) == "/iserv/calendar/neu"
    assert mail_web.create_event_path("<html></html>") == ""


def test_the_form_is_prefilled_with_subject_and_the_body_cut_to_800_characters(tmp_path):
    service, school, _, imap = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    assert found["path"] == "/iserv/calendar/create"
    names = [field["name"] for field in found["form"]["fields"]]
    assert names == ["event[subject]", "event[calendar]", "event[startDate]", "event[startTime]", "event[allDay]", "event[location]", "event[description]"]
    assert found["prefill"]["event[subject]"] == "Rückmeldung"
    assert len(found["prefill"]["event[description]"]) == 800
    assert found["prefill"]["event[description]"].startswith("Wir fahren zum Wildpark.")
    assert [option["label"] for option in found["form"]["fields"][1]["options"]] == ["Mein Kalender", "Eltern 3b"]
    assert imap.stores() == []
    assert TOKEN not in str(found)


def save(service, school, found, values, fields=None, request_id=REQUEST, check=None, confirmed=True):
    return service.mail_web_call(
        school, "save_event", found["path"], found["form"]["index"], values, fields, confirmed,
        request_id=request_id, check=found["check"] if check is None else check,
    )


EVENT_VALUES = {"event[calendar]": "/eltern.3b/calendar", "event[startDate]": "2026-10-23", "event[startTime]": "09:30"}


def test_saving_needs_confirmation_and_is_checked_in_the_calendar(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    values = dict(found["prefill"], **EVENT_VALUES)
    fields = [field["name"] for field in found["form"]["fields"]]
    with pytest.raises(DataError):
        save(service, school, found, values, fields, confirmed=False)
    assert web.events == []
    result = save(service, school, found, values, fields)
    assert result["ok"] is True and result["verified"] is True
    assert result["event"] == {"title": "Rückmeldung", "start": "2026-10-23T09:30:00+02:00", "calendar": "Eltern 3b"}
    assert dict(web.posts[0][1])["event[_token]"] == TOKEN


def test_form_errors_are_shown_and_a_missing_entry_is_not_called_saved(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    refused = save(service, school, found, {"event[subject]": "X"})
    assert (refused["ok"], refused["verified"], refused["errors"], refused["event"]) == (False, False, ["Dieser Wert sollte nicht leer sein."], None)
    service2, school2, _, _ = with_mail(tmp_path / "two", FakeMailWeb(ignore_posts=True))
    found2 = service2.mail_web_call(school2, "event_form", "INBOX", "9")
    quiet = save(service2, school2, found2, {"event[subject]": "X", "event[startDate]": "2026-10-23"})
    assert quiet["ok"] is False and quiet["verified"] is False and quiet["state"] == "uncertain"
    assert quiet["message_key"] == "api.mail.event.uncertain"


def test_only_the_calendar_create_page_takes_entries(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    with pytest.raises(DataError) as caught:
        service.mail_web_call(school, "save_event", "/iserv/mail/settings/forward", 0, {"forward[address]": "a@b.example"}, None, True, request_id=REQUEST, check="x")
    assert caught.value.message_key == "api.mail.event.unknown"
    assert web.posts == []


def test_the_event_routes(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    api = TestClient(create_app(service))
    found = api.get("/api/mail/event", params={"connection": school, "folder": "INBOX", "uid": "9"}).json()
    body = {
        "connection_id": school, "path": found["path"], "form": 0, "values": dict(found["prefill"], **{"event[startDate]": "2026-10-23"}),
        "confirmed": True, "request_id": REQUEST, "check": found["check"],
    }
    saved = api.post("/api/mail/event", json=body).json()
    assert saved["verified"] is True and web.events[0]["allDay"] is True


def test_a_request_without_an_id_or_with_a_changed_form_sends_nothing(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    values = dict(found["prefill"], **EVENT_VALUES)
    with pytest.raises(DataError) as caught:
        save(service, school, found, values, request_id="")
    assert caught.value.message_key == "api.mail.event.invalidRequest"
    with pytest.raises(DataError) as caught:
        save(service, school, found, values, check="0" * 16)
    assert caught.value.message_key == "api.mail.settings.changed"
    assert web.posts == []


def test_only_the_event_form_of_the_calendar_may_be_posted(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    values = dict(found["prefill"], **EVENT_VALUES)
    with pytest.raises(DataError) as caught:
        service.mail_web_call(school, "save_event", found["path"], 1, values, None, True, request_id=REQUEST, check=found["check"])
    assert caught.value.message_key == "api.mail.event.unknown"
    page = web._create_page
    web._create_page = lambda: page().replace('action="/iserv/calendar/create"', 'action="/iserv/mail/settings/forward"')
    with pytest.raises(DataError) as caught:
        save(service, school, found, values, request_id=OTHER)
    assert caught.value.message_key == "api.mail.event.unknown"
    extra = '<input type="hidden" name="event[owner]" value="someone"><input type="hidden" name="event[_token]"'
    web._create_page = lambda: page().replace('<input type="hidden" name="event[_token]"', extra)
    with pytest.raises(DataError) as caught:
        save(service, school, found, values, request_id="1111111111111111")
    assert caught.value.message_key == "api.mail.settings.changed"
    assert web.posts == []


def test_a_sign_in_page_as_the_answer_is_uncertain_not_saved(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    original = web.post_absolute

    def post(url, data, timeout=30, follow_redirects=True, headers=None):
        answer = original(url, data, timeout, follow_redirects, headers)
        answer.text = SIGN_IN
        return answer

    web.post_absolute = post
    result = save(service, school, found, dict(found["prefill"], **EVENT_VALUES))
    assert result["ok"] is False and result["state"] == "uncertain"


def test_a_lost_connection_is_uncertain_and_the_same_request_is_never_sent_again(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    sent = []

    def broken(url, data, timeout=30, follow_redirects=True, headers=None):
        sent.append(url)
        raise requests.ReadTimeout("timed out")

    web.post_absolute = broken
    values = dict(found["prefill"], **EVENT_VALUES)
    first = save(service, school, found, values)
    assert first["ok"] is False and first["state"] == "uncertain" and first["message_key"] == "api.mail.event.uncertain"
    again = save(service, school, found, values)
    assert again["state"] == "uncertain"
    assert len(sent) == 1


def test_a_saved_entry_is_answered_again_without_a_second_post(tmp_path):
    service, school, web, _ = with_mail(tmp_path)
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    values = dict(found["prefill"], **EVENT_VALUES)
    assert save(service, school, found, values)["verified"] is True
    again = save(service, school, found, values)
    assert again["ok"] is True and again["verified"] is True and again["event"]["calendar"] == "Eltern 3b"
    assert len(web.posts) == 1


def test_an_entry_with_the_same_title_at_another_time_or_calendar_is_not_proof(tmp_path):
    service, school, web, _ = with_mail(tmp_path, FakeMailWeb(ignore_posts=True))
    title = service.mail_web_call(school, "event_form", "INBOX", "9")["prefill"]["event[subject]"]
    web.events.append({"uid": "old", "title": title, "start": "2026-10-23T08:00:00+02:00", "allDay": False, "calendarName": "Eltern 3b"})
    web.events.append({"uid": "own", "title": title, "start": "2026-10-23T09:30:00+02:00", "allDay": False, "calendarName": "Mein Kalender"})
    found = service.mail_web_call(school, "event_form", "INBOX", "9")
    result = save(service, school, found, dict(found["prefill"], **EVENT_VALUES))
    assert result["ok"] is False and result["verified"] is False and result["state"] == "uncertain"
