import imaplib
import logging
import re

import pytest
from fastapi.testclient import TestClient

from app import integration, modules
from app.iserv import mail, mail_structure
from app.iserv.errors import DataError
from app.mail_service import MailService
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.mail_fakes import PDF_BYTES, PNG_BYTES, FakeImap, FakeSmtp
from tests.test_school_events import Answer, CalendarClient

SCHOOL_URL = "https://school.example"
MAIL_ENTRY = {"segment": "mail", "slug": "mail", "label": "E-Mail"}
def signed_in(imap=None):
    imap = imap or FakeImap()
    imap.login("u", "p")
    return imap


def test_the_folder_list_names_every_selectable_folder_with_its_role_and_counts():
    imap = signed_in()
    imap.folders.pop("Archive")
    folders = mail.list_folders(imap)
    assert [(entry["id"], entry["role"], entry["name"], entry["depth"]) for entry in folders] == [
        ("INBOX", "inbox", "INBOX", 0),
        ("Drafts", "drafts", "Drafts", 0),
        ("Sent", "sent", "Sent", 0),
        ("Trash", "trash", "Trash", 0),
        ("INBOX/Projekt &AMQ-", "folder", "Projekt Ä", 0),
    ]
    assert folders[0]["unread"] == 1 and folders[0]["total"] == 2
    assert folders[4]["path"] == "INBOX/Projekt Ä"
    assert folders[4]["delimiter"] == "/"


def test_a_folder_without_counts_is_kept_with_unknown_counts():
    imap = signed_in()
    answer = imap.status
    imap.status = lambda quoted, items: ("NO", [b"busy"]) if "Sent" in quoted else answer(quoted, items)
    sent = [entry for entry in mail.list_folders(imap) if entry["id"] == "Sent"][0]
    assert sent["unread"] is None and sent["total"] is None


def test_modified_utf7_folder_names_decode():
    assert mail.decode_folder_name("Entw&APw-rfe") == "Entwürfe"
    assert mail.decode_folder_name("A &- B") == "A & B"
    assert mail.decode_folder_name("Broken &%%%-") == "Broken &%%%-"


def test_the_message_list_peeks_newest_first_and_never_marks_read():
    imap = signed_in()
    listed = mail.list_messages(imap, "INBOX")
    assert [entry["uid"] for entry in listed["messages"]] == ["9", "7"]
    unread, read = listed["messages"]
    assert unread["unread"] is True and read["unread"] is False
    assert unread["subject"] == "Rückmeldung"
    assert unread["from"] == [{"name": "Schülerbüro", "address": "office@school.example"}]
    assert read["to"][0] == {"name": "Parent Example", "address": "parent@school.example"}
    assert read["has_attachments"] is True and unread["has_attachments"] is False
    assert read["date"].startswith("2026-10-13T06:15:00")
    assert listed["more"] is False
    assert ("select", "INBOX", True) in imap.calls
    assert imap.stores() == []


def test_the_message_list_pages_by_offset():
    imap = signed_in()
    first = mail.list_messages(imap, "INBOX", limit=1)
    assert [entry["uid"] for entry in first["messages"]] == ["9"] and first["more"] is True and first["total"] == 2
    second = mail.list_messages(imap, "INBOX", offset=1, limit=1)
    assert [entry["uid"] for entry in second["messages"]] == ["7"] and second["more"] is False


def test_an_unknown_folder_is_a_named_error():
    with pytest.raises(mail.MailUnreadable) as caught:
        mail.list_messages(signed_in(), "Nope")
    assert caught.value.message_key == mail.UNKNOWN_FOLDER_KEY


def test_the_detail_is_sanitised_keeps_attachments_and_stays_unread():
    imap = signed_in()
    detail = mail_structure.message_detail(imap, "INBOX", "7", "school.example")
    assert detail["subject"] == "Ausflug am Freitag"
    assert [entry["address"] for entry in detail["to"]] == ["parent@school.example", "other@school.example"]
    assert detail["cc"] == [{"name": "Office", "address": "office@school.example"}]
    html = detail["body_html"]
    assert "<script" not in html and "alert" not in html
    assert 'href="https://example.org/trip"' in html
    assert "school.example/iserv" not in html and 'href="/iserv' not in html
    assert "<p>Files <a" in html and "</a> Mail</p>" in html
    assert "cid:" not in html
    assert 'src="https://example.org/pic.png"' in html
    assert detail["body_text"] == ""
    assert [(entry["id"], entry["filename"], entry["mimetype"]) for entry in detail["attachments"]] == [
        ("2", "Elternbrief Ausflug.pdf", "application/pdf"),
        ("3", "map.png", "image/png"),
    ]
    assert abs(detail["attachments"][0]["size"] - len(PDF_BYTES)) <= 4
    assert detail["unread"] is False
    assert imap.stores() == []
    assert imap.readonly is True


def test_the_detail_fetches_the_structure_and_only_the_text_parts():
    imap = signed_in()
    mail_structure.message_detail(imap, "INBOX", "7")
    fetched = [items for uid, items in imap.fetched]
    assert fetched[0] == ["UID", "FLAGS", "INTERNALDATE", "RFC822.SIZE", "BODYSTRUCTURE", "BODY.PEEK[HEADER]"]
    assert fetched[1] == ["UID", "BODY.PEEK[1.2]"]
    assert not any("BODY.PEEK[]" in item for items in fetched for item in items)


def test_a_plain_mail_keeps_its_text():
    detail = mail_structure.message_detail(signed_in(), "INBOX", "9")
    assert detail["body_html"] == ""
    assert detail["body_text"] == "Line one\nLine two"
    assert detail["attachments"] == []
    assert detail["unread"] is True


def test_an_attachment_is_read_by_its_section_and_body_parts_are_refused():
    imap = signed_in()
    pdf = mail_structure.attachment(imap, "INBOX", "7", "2")
    assert pdf == {"filename": "Elternbrief Ausflug.pdf", "mimetype": "application/pdf", "content": PDF_BYTES}
    assert imap.fetched[-1] == (7, ["UID", "BODY.PEEK[2]"])
    for wrong in ("1.1", "1.2", "9", "../1", "0", "1.", ""):
        with pytest.raises(mail.MailUnreadable):
            mail_structure.attachment(imap, "INBOX", "7", wrong)


def test_inline_images_are_rendered_from_their_part():
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = "a@school.example"
    message["Subject"] = "Bild"
    message.set_content("text")
    message.add_alternative('<p>Logo</p><img src="cid:logo@school">', subtype="html")
    message.get_payload()[1].add_related(PNG_BYTES, maintype="image", subtype="png", cid="<logo@school>")
    imap = signed_in(FakeImap(folders={"INBOX": [{"uid": 5, "flags": set(), "raw": message.as_bytes()}]}))
    plain = mail_structure.message_detail(imap, "INBOX", "5")
    assert "cid:" not in plain["body_html"]
    framed = mail_structure.message_detail(imap, "INBOX", "5", inline=True)
    assert 'src="data:image/png;base64,' in framed["body_html"]


def test_the_source_is_read_in_part_with_a_cap():
    imap = signed_in()
    found = mail_structure.source(imap, "INBOX", "7", 100)
    assert len(found["source"]) == 100 and found["cut"] is True
    assert imap.fetched[-1][1] == ["UID", "RFC822.SIZE", "BODY.PEEK[]<0.100>"]


def test_the_bodystructure_parser_reads_nested_parts_and_literals():
    data = [
        (b'1 (UID 4 BODYSTRUCTURE ((("TEXT" "PLAIN" ("CHARSET" "utf-8") NIL NIL "QUOTED-PRINTABLE" 10 1 NIL NIL NIL NIL)'
         b'("TEXT" "HTML" ("CHARSET" "utf-8") NIL NIL "7BIT" 20 1 NIL NIL NIL NIL) "ALTERNATIVE" ("BOUNDARY" "b") NIL NIL NIL)'
         b'("APPLICATION" "PDF" ("NAME" {9}', b"Brief.pdf"),
        b') NIL NIL "BASE64" 400 NIL ("ATTACHMENT" ("FILENAME" "Brief.pdf")) NIL NIL) "MIXED" ("BOUNDARY" "a") NIL NIL NIL))',
    ]
    items = mail_structure.fetch_items(data)[0]
    parts = mail_structure.leaves(mail_structure.parse_structure(items["BODYSTRUCTURE"]))
    assert [(part["section"], mail_structure.content_type(part), part["filename"]) for part in parts] == [
        ("1.1", "text/plain", ""), ("1.2", "text/html", ""), ("2", "application/pdf", "Brief.pdf"),
    ]
    assert parts[0]["encoding"] == "quoted-printable" and parts[2]["disposition"] == "attachment"


def test_marking_read_stores_the_seen_flag_in_a_writable_folder():
    imap = signed_in()
    mail.mark_seen(imap, "INBOX", "9")
    assert imap.stores() == [("uid", "STORE", "9", "+FLAGS.SILENT", "(\\Seen)")]
    assert ("select", "INBOX", False) in imap.calls
    assert mail.folder_counts(imap, "INBOX") == {"unread": 0, "total": 2}


@pytest.mark.parametrize("uid", ["", "0", "1,2", "1:*", "abc", "12345678901"])
def test_message_ids_are_plain_uids(uid):
    with pytest.raises(mail.MailUnreadable):
        mail.mark_seen(signed_in(), "INBOX", uid)


def service_with_mail(tmp_path, imap_factory, password="p", answer=None, smtp=None):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_URL, secrets={"username": "u", "password": password, "totp_secret": "JBSWY3DPEHPK3PXP"})
    store.connection_store(connection_id).save_modules({"unsupported": [MAIL_ENTRY]})
    client = CalendarClient(SCHOOL_URL, answer or Answer(200, {"mail": 0}))
    service = IServService(store, client_factory=lambda url: client)
    connection = service.connection(connection_id)
    clock = {"now": 1000.0}
    opened = []

    def opener(host):
        opened.append(host)
        return imap_factory()

    connection._mail_service = MailService(connection, opener=opener, clock=lambda: clock["now"], submitter=lambda host: smtp)
    return service, store, connection_id, opened, clock


def test_the_service_reads_folders_over_imap_of_the_school_host(tmp_path):
    imaps = []

    def factory():
        imaps.append(FakeImap())
        return imaps[-1]

    service, _, connection_id, opened, _ = service_with_mail(tmp_path, factory)
    body = service.mail_call(connection_id, "folders")
    assert opened == ["school.example"]
    assert body["connection_id"] == connection_id
    assert [entry["role"] for entry in body["folders"]] == ["inbox", "drafts", "sent", "archive", "trash", "folder"]
    assert imaps[0].logged_out is True


def test_a_non_ascii_password_signs_in_with_plain(tmp_path):
    imaps = []

    def factory():
        imaps.append(FakeImap(password="pässwort"))
        return imaps[-1]

    service, _, connection_id, _, _ = service_with_mail(tmp_path, factory, password="pässwort")
    service.mail_call(connection_id, "folders")
    assert imaps[0].calls[0][:2] == ("authenticate", "PLAIN")


def test_a_refused_mail_sign_in_is_held_and_not_retried_until_the_password_changes(tmp_path, caplog):
    service, store, connection_id, opened, clock = service_with_mail(tmp_path, lambda: FakeImap(password="other"))
    with caplog.at_level(logging.WARNING):
        with pytest.raises(mail.MailSignInRefused):
            service.mail_call(connection_id, "folders")
        with pytest.raises(mail.MailSignInRefused):
            service.mail_call(connection_id, "messages", "INBOX")
    assert len(opened) == 1
    assert sum("mail sign-in refused" in record.getMessage() for record in caplog.records) == 1
    clock["now"] += 16 * 60
    with pytest.raises(mail.MailSignInRefused):
        service.mail_call(connection_id, "folders")
    assert len(opened) == 2
    store.save_secrets(connection_id, {"username": "u", "password": "new", "totp_secret": "JBSWY3DPEHPK3PXP"})
    with pytest.raises(mail.MailSignInRefused):
        service.mail_call(connection_id, "folders")
    assert len(opened) == 3


def test_an_unreachable_mail_server_is_named_and_not_a_sign_in_failure(tmp_path):
    def factory():
        raise OSError("connection refused")

    service, _, connection_id, _, _ = service_with_mail(tmp_path, factory)
    with pytest.raises(mail.MailUnreachable) as caught:
        service.mail_call(connection_id, "folders")
    assert caught.value.message_key == mail.UNREACHABLE_KEY


def test_reading_a_mail_never_marks_it_and_the_seen_call_does_and_recounts(tmp_path):
    imap = FakeImap()
    service, store, connection_id, _, _ = service_with_mail(tmp_path, lambda: imap, answer=Answer(200, {"mail": 0}))
    integration.record_school_mail(store, connection_id, 1)
    service.mail_call(connection_id, "messages", "INBOX")
    detail = service.mail_call(connection_id, "message", "INBOX", "9")
    assert detail["unread"] is True
    assert imap.stores() == []
    result = service.mail_call(connection_id, "mark_seen", "INBOX", "9")
    assert result["ok"] is True and result["unread"] == 0 and result["total"] == 2
    assert imap.stores() == [("uid", "STORE", "9", "+FLAGS.SILENT", "(\\Seen)")]
    assert result["unread_mail"] == 0
    assert integration.school_mail(store, connection_id) == 0


def test_a_failed_recount_keeps_the_stored_count(tmp_path):
    service, store, connection_id, _, _ = service_with_mail(tmp_path, FakeImap, answer=Answer(500, None))
    integration.record_school_mail(store, connection_id, 4)
    result = service.mail_call(connection_id, "mark_seen", "INBOX", "9")
    assert result["unread_mail"] == 4


def test_mail_is_refused_without_the_module(tmp_path):
    service, store, connection_id, opened, _ = service_with_mail(tmp_path, FakeImap)
    store.connection_store(connection_id).save_modules({"unsupported": []})
    with pytest.raises(DataError) as caught:
        service.mail_call(connection_id, "folders")
    assert caught.value.message_key == "api.mail.notOffered"
    assert opened == []


def test_the_unread_counts_carry_no_link_to_iserv(tmp_path):
    service, store, connection_id, _, _ = service_with_mail(tmp_path, FakeImap)
    integration.record_school_mail(store, connection_id, 2)
    body = service.mail_counts()
    assert body["schools"][0]["unread"] == 2
    assert "open_url" not in body["schools"][0]


def test_the_routes_serve_the_list_detail_attachment_and_seen(tmp_path):
    imap = FakeImap()
    service, _, connection_id, _, _ = service_with_mail(tmp_path, lambda: imap)
    api = TestClient(create_app(service))
    folders = api.get("/api/mail/folders", params={"connection": connection_id}).json()
    assert folders["folders"][0]["id"] == "INBOX"
    listed = api.get("/api/mail/messages", params={"connection": connection_id, "folder": "INBOX"}).json()
    assert [entry["uid"] for entry in listed["messages"]] == ["9", "7"]
    detail = api.get("/api/mail/message", params={"connection": connection_id, "folder": "INBOX", "uid": "7"}).json()
    part = detail["attachments"][0]["id"]
    answer = api.get("/api/mail/attachment", params={"connection": connection_id, "folder": "INBOX", "uid": "7", "part": part})
    assert answer.status_code == 200
    assert answer.content == PDF_BYTES
    assert answer.headers["content-type"] == "application/pdf"
    assert answer.headers["content-disposition"] == "attachment; filename*=UTF-8''Elternbrief%20Ausflug.pdf"
    missing = api.get("/api/mail/attachment", params={"connection": connection_id, "folder": "INBOX", "uid": "7", "part": "0"})
    assert missing.status_code == 404
    assert missing.json()["message_key"] == mail.UNKNOWN_ATTACHMENT_KEY
    assert imap.stores() == []
    seen = api.post("/api/mail/seen", json={"connection_id": connection_id, "folder": "INBOX", "uid": "9"}).json()
    assert seen["ok"] is True
    assert len(imap.stores()) == 1


def test_a_refused_sign_in_reaches_the_app_as_an_unknown_state_with_its_reason(tmp_path):
    service, _, connection_id, _, _ = service_with_mail(tmp_path, lambda: FakeImap(password="other"))
    api = TestClient(create_app(service))
    body = api.get("/api/mail/folders", params={"connection": connection_id}).json()
    assert body["error"] == "network"
    assert body["message_key"] == mail.SIGN_IN_REFUSED_KEY
    assert body["message"]


def test_mail_moves_from_unsupported_to_read_by_the_app():
    registry = modules.normalize({"unsupported": [MAIL_ENTRY, {"segment": "print", "slug": "print", "label": "Drucken"}], "checked_at": 1})
    assert [entry["slug"] for entry in registry["unsupported"]] == ["print"]
    assert [entry["slug"] for entry in registry["covered"]] == ["mail"]
    assert modules.lists_module(registry, "mail") is True
    assert modules.lists_module(modules.normalize({"unsupported": [MAIL_ENTRY]}), "mail") is True
    assert modules.lists_module(modules.normalize({}), "mail") is False
    assert re.search(r"not supported: 1 \(print\).*read by the app: 1 \(mail\)", modules.summary(registry))
