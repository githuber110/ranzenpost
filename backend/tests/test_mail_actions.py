import smtplib
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

from app import integration
from app.iserv import mail, mail_compose, mail_manage
from app.mail_service import MailConfirmRequired
from app.server import create_app
from tests.mail_fakes import PDF_BYTES, FakeImap, FakeSmtp
from tests.test_mail_imap import service_with_mail, signed_in

REQUEST = "a" * 32


def uids(imap, folder):
    return [entry["uid"] for entry in imap.folders[folder]]


def test_search_filters_by_status_scope_words_dates_and_tags():
    imap = signed_in()
    mail.select(imap, "INBOX")
    assert mail.search_uids(imap, {"status": "unread"}) == [9]
    assert mail.search_uids(imap, {"status": "read"}) == [7]
    assert mail.search_uids(imap, {"query": "teacher", "scope": "from"}) == [7]
    assert mail.search_uids(imap, {"query": "parent", "scope": "to"}) == [7, 9]
    assert mail.search_uids(imap, {"query": "Ausflug", "scope": "subject"}) == [7]
    assert mail.search_uids(imap, {"query": "Line two", "scope": "body"}) == [9]
    assert mail.search_uids(imap, {"since": "2026-10-14"}) == [9]
    assert mail.search_uids(imap, {"until": "2026-10-13"}) == [7]
    imap.folders["INBOX"][0]["flags"].add("$label1")
    assert mail.search_uids(imap, {"tag": "$label1"}) == [7]


def test_a_non_ascii_search_word_goes_as_a_utf8_literal():
    imap = signed_in()
    mail.select(imap, "INBOX")
    assert mail.search_uids(imap, {"query": "rückmeldung", "scope": "subject"}) == [9]
    charset = [call for call in imap.calls if call[:3] == ("uid", "SEARCH", "CHARSET")]
    assert charset and imap.literal is None


@pytest.mark.parametrize("search", [{"tag": "bad tag"}, {"tag": "\\Seen"}])
def test_tags_must_be_plain_keywords(search):
    with pytest.raises(mail.MailUnreadable):
        mail.search_terms(search)


def test_the_list_sorts_by_size_and_age():
    imap = signed_in()
    assert [entry["uid"] for entry in mail.list_messages(imap, "INBOX", order="largest")["messages"]] == ["7", "9"]
    assert [entry["uid"] for entry in mail.list_messages(imap, "INBOX", order="smallest")["messages"]] == ["9", "7"]
    assert [entry["uid"] for entry in mail.list_messages(imap, "INBOX", order="oldest")["messages"]] == ["7", "9"]


def test_flags_tags_and_unread_are_set_and_cleared():
    imap = signed_in()
    mail_manage.set_flag(imap, "INBOX", ["7", "9"], "flagged", True)
    mail_manage.set_flag(imap, "INBOX", ["7"], "seen", False)
    mail_manage.set_flag(imap, "INBOX", ["9"], "$label2", True)
    flags = {entry["uid"]: entry["flags"] for entry in imap.folders["INBOX"]}
    assert flags[7] == {"\\Flagged"}
    assert flags[9] == {"\\Flagged", "$label2"}
    summaries = {entry["uid"]: entry for entry in mail.list_messages(imap, "INBOX")["messages"]}
    assert summaries["9"]["tags"] == ["$label2"] and summaries["9"]["flagged"] is True
    with pytest.raises(mail.MailUnreadable):
        mail_manage.set_flag(imap, "INBOX", ["7"], "\\Deleted", True)


def test_move_uses_move_or_copy_with_uid_expunge_and_refuses_otherwise():
    imap = signed_in()
    mail_manage.move_messages(imap, "INBOX", ["9"], "Archive")
    assert uids(imap, "INBOX") == [7] and len(imap.folders["Archive"]) == 1
    older = signed_in(FakeImap(capabilities=("IMAP4REV1", "UIDPLUS")))
    mail_manage.move_messages(older, "INBOX", ["9"], "Archive")
    assert uids(older, "INBOX") == [7]
    assert ("uid", "EXPUNGE", "9") in older.calls
    plain = signed_in(FakeImap(capabilities=("IMAP4REV1",)))
    with pytest.raises(mail.MailUnreadable) as caught:
        mail_manage.move_messages(plain, "INBOX", ["9"], "Archive")
    assert caught.value.message_key == mail_manage.UNSUPPORTED_KEY


def test_archive_files_by_year_and_creates_the_year_folder():
    imap = signed_in()
    archive = mail_manage.archive_folder(mail.list_folders(imap))
    moved = mail_manage.archive_messages(imap, "INBOX", ["7"], archive)
    assert moved == {"Archive/2026": ["7"]}
    assert ("create", "Archive/2026") in imap.calls
    assert len(imap.folders["Archive/2026"]) == 1


def test_own_folders_are_created_renamed_and_deleted_but_special_ones_are_protected():
    imap = signed_in()
    folders = mail.list_folders(imap)
    target = mail_manage.own_folder_id("Elternrat Ä", "", "/")
    assert target == "Elternrat &AMQ-"
    mail_manage.create_folder(imap, target)
    folders = mail.list_folders(imap)
    own = mail_manage.find_folder(folders, target)
    renamed = mail_manage.rename_folder(imap, own, "Klasse 3b")
    assert renamed == "Klasse 3b" and "Klasse 3b" in imap.folders
    mail_manage.delete_folder(imap, mail_manage.find_folder(mail.list_folders(imap), "Klasse 3b"))
    assert "Klasse 3b" not in imap.folders
    for special in ("INBOX", "Sent", "Trash"):
        with pytest.raises(mail.MailUnreadable):
            mail_manage.delete_folder(imap, mail_manage.find_folder(folders, special))
    for bad in ("", "a/b", "x%", "INBOX", "a" * 200):
        with pytest.raises(mail.MailUnreadable):
            mail_manage.own_folder_id(bad, "", "/")


def test_trash_moves_first_and_deletes_only_with_confirmation(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    moved = service.mail_call(school, "trash", "INBOX", ["9"])
    assert moved["ok"] is True and moved["targets"] == {"Trash": ["9"]}
    trashed = str(imap.folders["Trash"][0]["uid"])
    with pytest.raises(MailConfirmRequired):
        service.mail_call(school, "trash", "Trash", [trashed])
    assert len(imap.folders["Trash"]) == 1
    deleted = service.mail_call(school, "trash", "Trash", [trashed], True)
    assert deleted["ok"] is True and deleted["deleted"] == [trashed]
    assert imap.folders["Trash"] == []


def test_moving_re_reads_the_folder_and_names_what_stayed(tmp_path):
    imap = FakeImap()
    service, store, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    integration.record_school_mail(store, school, 5)
    result = service.mail_call(school, "move", "INBOX", ["9"], "Archive")
    assert result["ok"] is True and result["moved"] == ["9"] and result["left"] == []
    assert result["unread"] == 0 and result["total"] == 1
    assert result["unread_mail"] == 0
    with pytest.raises(mail.MailUnreadable):
        service.mail_call(school, "move", "INBOX", ["7"], "Nowhere")


def compose_payload(**extra):
    payload = {
        "from": "u@school.example",
        "to": [{"name": "Class Teacher", "address": "teacher@school.example"}],
        "cc": ["office@school.example"],
        "bcc": [{"address": "quiet@school.example"}],
        "subject": "Frage",
        "text": "Hallo",
        "request_id": REQUEST,
    }
    payload.update(extra)
    return payload


def test_sending_needs_a_confirmation_and_files_a_copy_in_sent(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    with pytest.raises(MailConfirmRequired):
        service.mail_call(school, "send", compose_payload())
    assert smtp.sent == []
    result = service.mail_call(school, "send", compose_payload(receipt=True), [{"filename": "a.pdf", "content": PDF_BYTES, "mimetype": "application/pdf"}], True)
    assert result["sent"] is True and result["saved"] is True
    assert smtp.sent[0]["from"] == "u@school.example"
    assert smtp.sent[0]["to"] == ["teacher@school.example", "office@school.example", "quiet@school.example"]
    stored = message_from_bytes(imap.folders["Sent"][-1]["raw"], policy=policy.default)
    assert stored["Subject"] == "Frage"
    assert stored["Disposition-Notification-To"] == "u@school.example"
    assert [part.get_filename() for part in stored.iter_attachments()] == ["a.pdf"]
    assert "\\Seen" in imap.folders["Sent"][-1]["flags"]


def test_the_same_send_request_never_sends_twice(tmp_path):
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    first = service.mail_call(school, "send", compose_payload(), [], True)
    again = service.mail_call(school, "send", compose_payload(), [], True)
    assert len(smtp.sent) == 1
    assert again["repeated"] is True and again["message_id"] == first["message_id"]


def test_a_broken_connection_while_sending_is_uncertain_and_blocks_a_repeat(tmp_path):
    smtp = FakeSmtp(failure=smtplib.SMTPServerDisconnected("gone"))
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    with pytest.raises(mail_compose.MailSendUncertain):
        service.mail_call(school, "send", compose_payload(), [], True)
    smtp.failure = None
    with pytest.raises(mail_compose.MailSendUncertain):
        service.mail_call(school, "send", compose_payload(), [], True)
    assert smtp.sent == []


def test_a_refused_mail_is_not_sent_and_may_be_tried_again(tmp_path):
    smtp = FakeSmtp(failure=smtplib.SMTPDataError(554, b"rejected"))
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    with pytest.raises(mail_compose.MailSendFailed):
        service.mail_call(school, "send", compose_payload(), [], True)
    smtp.failure = None
    assert service.mail_call(school, "send", compose_payload(), [], True)["sent"] is True


@pytest.mark.parametrize("change", [{"to": ["not an address"]}, {"from": "someone@else.example"}, {"to": [], "cc": [], "bcc": []}, {"request_id": "x"}])
def test_invalid_drafts_are_refused_before_sending(tmp_path, change):
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    with pytest.raises(mail.DataError):
        service.mail_call(school, "send", compose_payload(**change), [], True)
    assert smtp.sent == []


def test_a_reply_quotes_marks_the_original_answered_and_threads(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    start = service.mail_call(school, "compose_start", "INBOX", "7", "reply_all")
    assert start["to"] == [{"name": "Class Teacher", "address": "teacher@school.example"}]
    assert [entry["address"] for entry in start["cc"]] == ["parent@school.example", "other@school.example", "office@school.example"]
    assert start["subject"] == "Re: Ausflug am Freitag"
    assert start["in_reply_to"] == "<trip-1@school.example>"
    payload = compose_payload(to=start["to"], cc=[], bcc=[], subject=start["subject"], mode="reply", in_reply_to=start["in_reply_to"],
                              references=start["references"], source=start["source"])
    service.mail_call(school, "send", payload, [], True)
    sent = message_from_bytes(smtp.sent[0]["raw"], policy=policy.default)
    assert sent["In-Reply-To"] == "<trip-1@school.example>"
    assert "\\Answered" in imap.folders["INBOX"][0]["flags"]


def test_a_forward_carries_the_chosen_attachments(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    start = service.mail_call(school, "compose_start", "INBOX", "7", "forward")
    assert start["subject"] == "Fwd: Ausflug am Freitag" and start["to"] == []
    carry = [start["attachments"][0]["id"]]
    service.mail_call(school, "send", compose_payload(mode="forward", source=start["source"], carry=carry), [], True)
    sent = message_from_bytes(smtp.sent[0]["raw"], policy=policy.default)
    assert [part.get_filename() for part in sent.iter_attachments()] == ["Elternbrief Ausflug.pdf"]
    assert "$Forwarded" in imap.folders["INBOX"][0]["flags"]


def test_drafts_are_saved_replaced_and_deleted_only_with_confirmation(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    first = service.mail_call(school, "save_draft", compose_payload(to=[], cc=[], bcc=[]))
    assert first["draft"]["folder"] == "Drafts"
    assert imap.folders["Drafts"][0]["flags"] == {"\\Draft", "\\Seen"}
    second = service.mail_call(school, "save_draft", compose_payload(subject="Frage 2", draft=first["draft"]))
    assert second["replaced"] is True
    assert [str(entry["uid"]) for entry in imap.folders["Drafts"]] == [second["draft"]["uid"]]
    reopened = service.mail_call(school, "compose_start", "Drafts", second["draft"]["uid"], "draft")
    assert reopened["subject"] == "Frage 2" and reopened["draft"] == second["draft"]
    with pytest.raises(MailConfirmRequired):
        service.mail_call(school, "delete_draft", "Drafts", second["draft"]["uid"])
    assert service.mail_call(school, "delete_draft", "Drafts", second["draft"]["uid"], True)["ok"] is True
    assert imap.folders["Drafts"] == []


def test_a_sent_draft_leaves_the_drafts_folder(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=FakeSmtp())
    saved = service.mail_call(school, "save_draft", compose_payload())
    result = service.mail_call(school, "send", compose_payload(draft=saved["draft"]), [], True)
    assert result["draft_removed"] is True and imap.folders["Drafts"] == []


def test_a_read_receipt_is_sent_only_with_confirmation_and_marked(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    detail = service.mail_call(school, "message", "INBOX", "7")
    assert detail["receipt_to"] == [{"name": "Class Teacher", "address": "teacher@school.example"}]
    with pytest.raises(MailConfirmRequired):
        service.mail_call(school, "receipt", "INBOX", "7", True)
    result = service.mail_call(school, "receipt", "INBOX", "7", True, True, REQUEST)
    assert result["to"] == "teacher@school.example"
    assert smtp.sent[0]["to"] == ["teacher@school.example"]
    report = message_from_bytes(smtp.sent[0]["raw"], policy=policy.default)
    assert report.get_content_type() == "multipart/report"
    assert "$MDNSent" in imap.folders["INBOX"][0]["flags"]


def test_declining_a_receipt_only_marks_the_mail(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    service.mail_call(school, "receipt", "INBOX", "7", False)
    assert smtp.sent == [] and "$MDNSent" in imap.folders["INBOX"][0]["flags"]


def test_search_everywhere_names_the_folder_of_each_hit(tmp_path):
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap)
    found = service.mail_call(school, "search_everywhere", {"query": "Ausflug"})
    assert [(entry["folder"], entry["subject"]) for entry in found["messages"]] == [("INBOX", "Ausflug am Freitag"), ("Sent", "Re: Ausflug")]


def test_the_routes_cover_flags_moves_folders_drafts_and_sending(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    api = TestClient(create_app(service))
    assert api.post("/api/mail/flag", json={"connection_id": school, "folder": "INBOX", "uids": ["9"], "flag": "flagged", "on": True}).json()["ok"] is True
    listed = api.get("/api/mail/messages", params={"connection": school, "folder": "INBOX", "status": "flagged"}).json()
    assert [entry["uid"] for entry in listed["messages"]] == ["9"]
    unconfirmed = api.post("/api/mail/send", json=dict(compose_payload(), connection_id=school)).json()
    assert unconfirmed["ok"] is False and unconfirmed["message_key"] == "api.mail.confirmRequired"
    files = {"files": ("note.txt", b"hello", "text/plain")}
    data = {"data": '{"connection_id": "%s", "from": "u@school.example", "to": ["teacher@school.example"], "subject": "x", "text": "y", "request_id": "%s", "confirmed": true}' % (school, REQUEST)}
    sent = api.post("/api/mail/send", data=data, files=files).json()
    assert sent["ok"] is True and sent["sent"] is True
    created = api.post("/api/mail/folder/create", json={"connection_id": school, "name": "Elternrat"}).json()
    assert created["ok"] is True and created["folder"] == "Elternrat"
    assert api.post("/api/mail/folder/delete", json={"connection_id": school, "folder": "Elternrat"}).json()["ok"] is False
    assert api.post("/api/mail/folder/delete", json={"connection_id": school, "folder": "Elternrat", "confirmed": True}).json()["ok"] is True
    source = api.get("/api/mail/source", params={"connection": school, "folder": "INBOX", "uid": "9"}).json()
    assert "Line one" in source["source"]
    everywhere = api.get("/api/mail/messages", params={"connection": school, "everywhere": "true", "query": "Ausflug"}).json()
    assert len(everywhere["messages"]) == 2
