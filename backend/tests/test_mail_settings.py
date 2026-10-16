import logging

import pytest
from fastapi.testclient import TestClient

from app.iserv import mail_web, settings_forms
from app.iserv.errors import DataError
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.mail_fakes import FakeImap
from tests.mail_web_fakes import SCHOOL, TOKEN, FakeMailWeb, mail_page
from tests.support import add_school

MAIL_ENTRY = {"segment": "mail", "slug": "mail", "label": "E-Mail"}


def service_with_web(tmp_path, web=None):
    web = web or FakeMailWeb()
    store = Store(tmp_path / "data")
    school = add_school(store, SCHOOL)
    store.connection_store(school).save_modules({"unsupported": [MAIL_ENTRY]})
    service = IServService(store, client_factory=lambda url: web)
    return service, school, web


def page_of(service, school, kind):
    pages = service.mail_web_call(school, "settings")["pages"]
    path = next(entry["path"] for entry in pages if entry["kind"] == kind)
    return service.mail_web_call(school, "settings_page", path)


def form_values(page):
    return {field["name"]: field.get("value") for field in page["forms"][0]["fields"] if field["kind"] not in ("checkbox", "radio")}


def test_the_php_data_gives_page_size_tags_flags_and_addresses():
    found = mail_web.account(mail_page(("alexa.muster@school.example", "x@else.example")))
    assert found["page_size"] == 25
    assert found["tags"] == [{"id": "$label1", "name": "Wichtig", "color": "#d33"}, {"id": "$label2", "name": "Elternrat", "color": "green"}]
    assert found["flags"] == {"hasActiveVacation": False}
    assert found["auto_archive"] == [{"path": "INBOX", "days": 90}]
    assert found["display_name"] == "Alexa Muster"
    assert found["addresses"] == ["alexa.muster@school.example", "x@else.example"]
    assert mail_web.account("<html></html>") is None


def test_settings_pages_are_found_from_links_and_known_places_and_the_shell_is_skipped(tmp_path, caplog):
    service, school, web = service_with_web(tmp_path)
    with caplog.at_level(logging.INFO):
        pages = service.mail_web_call(school, "settings")["pages"]
    assert [(entry["path"], entry["kind"], entry["guessed"]) for entry in pages] == [
        ("/iserv/mail/settings/vacation", "vacation", False),
        ("/iserv/mail/settings/forward", "forward", True),
        ("/iserv/mail/settings/filter", "filter", True),
        ("/iserv/mail/settings/signature", "signature", True),
    ]
    assert any("mail settings pages found: 4" in record.getMessage() for record in caplog.records)
    assert not any(path == "/iserv/mail/help" for path, _ in web.asked)


def test_a_form_is_described_with_labels_kinds_and_values_but_never_its_token(tmp_path):
    service, school, _ = service_with_web(tmp_path)
    page = page_of(service, school, "vacation")
    form = page["forms"][0]
    assert page["title"] == "Abwesenheitsnotiz"
    assert [(field["name"], field["kind"], field["label"]) for field in form["fields"]] == [
        ("vacation[enabled]", "checkbox", ""),
        ("vacation[subject]", "text", "Betreff"),
        ("vacation[message]", "textarea", "Nachricht"),
        ("vacation[start]", "date", "Beginn"),
    ]
    assert form["fields"][0]["choices"] == [{"value": "1", "label": "Abwesenheitsnotiz aktiv", "checked": False}]
    assert form["fields"][1]["maxlength"] == "120"
    assert form["has_token"] is True
    assert TOKEN not in str(page)


def test_saving_needs_confirmation_posts_with_the_token_and_verifies_by_reading_again(tmp_path):
    service, school, web = service_with_web(tmp_path)
    page = page_of(service, school, "vacation")
    values = {"vacation[enabled]": ["1"], "vacation[subject]": "Abwesend", "vacation[message]": "Ab Montag wieder da.", "vacation[start]": "2026-10-20"}
    fields = [field["name"] for field in page["forms"][0]["fields"]]
    with pytest.raises(DataError) as caught:
        service.mail_web_call(school, "save_settings", page["path"], 0, values, fields)
    assert caught.value.message_key == "api.mail.confirmRequired"
    assert web.posts == []
    result = service.mail_web_call(school, "save_settings", page["path"], 0, values, fields, True)
    assert result["ok"] is True and result["verified"] is True and result["unconfirmed"] == []
    assert web.vacation == {"enabled": True, "subject": "Abwesend", "message": "Ab Montag wieder da.", "start": "2026-10-20"}
    sent = dict(web.posts[0][1])
    assert sent["vacation[_token]"] == TOKEN and "vacation[save]" in sent


def test_a_save_iserv_ignores_is_reported_as_not_confirmed(tmp_path):
    service, school, _ = service_with_web(tmp_path, FakeMailWeb(ignore_posts=True))
    page = page_of(service, school, "vacation")
    result = service.mail_web_call(school, "save_settings", page["path"], 0, {"vacation[subject]": "Weg"}, None, True)
    assert result["ok"] is True and result["verified"] is False
    assert result["unconfirmed"] == ["Betreff"]


def test_iserv_form_errors_come_back_as_text_and_nothing_is_called_saved(tmp_path):
    service, school, web = service_with_web(tmp_path)
    page = page_of(service, school, "forward")
    result = service.mail_web_call(school, "save_settings", page["path"], 0, {"forward[address]": "kaputt"}, None, True)
    assert result["ok"] is False and result["errors"] == ["Diese Adresse ist ungültig."]
    assert web.forward["address"] == ""


def test_unknown_fields_and_unknown_pages_are_refused(tmp_path):
    service, school, web = service_with_web(tmp_path)
    page = page_of(service, school, "forward")
    with pytest.raises(DataError) as caught:
        service.mail_web_call(school, "save_settings", page["path"], 0, {"other[field]": "x"}, None, True)
    assert caught.value.message_key == settings_forms.FORM_FIELD_KEY
    with pytest.raises(DataError) as unknown:
        service.mail_web_call(school, "settings_page", "/iserv/admin/users")
    assert unknown.value.message_key == "api.mail.settings.unknown"
    with pytest.raises(DataError) as changed:
        service.mail_web_call(school, "save_settings", page["path"], 0, {"forward[address]": "a@b.example"}, ["forward[address]"], True)
    assert changed.value.message_key == settings_forms.FORM_CHANGED_KEY
    assert web.posts == []


def test_rules_are_added_and_removed_through_the_form_prototype(tmp_path):
    service, school, web = service_with_web(tmp_path)
    page = page_of(service, school, "filter")
    form = page["forms"][0]
    collection = form["collections"][0]
    assert collection["next_index"] == 1 and collection["entries"] == [0]
    assert [field["name"] for field in collection["fields"]][0] == "filter[rules][__name__][name]"
    added = {"filter[rules][1][%s]" % key: value for key, value in (("name", "Spam"), ("field", "subject"), ("value", "Gewinn"), ("action", "discard"), ("target", ""))}
    result = service.mail_web_call(school, "save_settings", page["path"], 0, added, None, True)
    assert result["verified"] is True
    assert [rule["name"] for rule in web.rules] == ["Newsletter", "Spam"]
    removed = {"filter[rules][0][%s]" % key: None for key in ("name", "field", "value", "action", "target")}
    result = service.mail_web_call(school, "save_settings", page["path"], 0, removed, None, True)
    assert result["verified"] is True
    assert [rule["name"] for rule in web.rules] == ["Spam"]


def test_select_values_outside_the_options_are_dropped(tmp_path):
    service, school, web = service_with_web(tmp_path)
    page = page_of(service, school, "signature")
    result = service.mail_web_call(school, "save_settings", page["path"], 0, {"signature[default]": "evil@else.example", "signature[text]": "Gruß"}, None, True)
    assert dict(web.posts[0][1]).get("signature[default]") is None
    assert result["verified"] is False


def test_recipient_lookup_uses_the_discovered_paths_and_remembers_the_parameter(tmp_path):
    service, school, web = service_with_web(tmp_path)
    found = service.mail_web_call(school, "recipients", "teach")
    assert found["recipients"] == [{"name": "Class Teacher", "address": "teacher@school.example", "group": False}]
    groups = service.mail_web_call(school, "recipients", "eltern")
    assert groups["recipients"] == [{"name": "Eltern 3b", "address": "eltern.3b@school.example", "group": True}]
    lookups = [params for path, params in web.asked if "autocomplete" in path]
    assert lookups[0] == {"query": "teach"}
    assert service.mail_web_call(school, "recipients", "a")["recipients"] == []


def test_sender_addresses_from_the_web_are_offered_only_on_the_school_domain(tmp_path):
    service, school, _ = service_with_web(tmp_path)
    connection = service.connection(school)
    from app.mail_service import MailService

    connection._mail_service = MailService(connection, opener=lambda host: FakeImap())
    senders = [entry["address"] for entry in service.mail_call(school, "compose_start")["senders"]]
    assert senders == ["u@school.example", "alexa.muster@school.example", "elternrat@school.example"]


def test_the_web_routes(tmp_path):
    service, school, web = service_with_web(tmp_path)
    api = TestClient(create_app(service))
    assert api.get("/api/mail/account", params={"connection": school}).json()["account"]["page_size"] == 25
    pages = api.get("/api/mail/settings", params={"connection": school}).json()["pages"]
    assert len(pages) == 4
    page = api.get("/api/mail/settings/page", params={"connection": school, "path": "/iserv/mail/settings/forward"}).json()
    assert page["forms"][0]["fields"][0]["name"] == "forward[address]"
    refused = api.post("/api/mail/settings/page", json={"connection_id": school, "path": page["path"], "form": 0, "values": {"forward[address]": "a@school.example"}}).json()
    assert refused["ok"] is False and refused["message_key"] == "api.mail.confirmRequired"
    saved = api.post("/api/mail/settings/page", json={"connection_id": school, "path": page["path"], "form": 0, "values": {"forward[address]": "a@school.example", "forward[keep]": []}, "confirmed": True}).json()
    assert saved["ok"] is True and saved["verified"] is True
    assert web.forward == {"address": "a@school.example", "keep": False}
    assert api.get("/api/mail/recipients", params={"connection": school, "q": "office"}).json()["recipients"][0]["address"] == "office@school.example"
