import json
import smtplib
import threading
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.iserv import mail, mail_web, sieve
from app.server import create_app
from tests.mail_fakes import FakeImap, FakeSieveTransport, FakeSmtp
from tests.test_mail_actions import REQUEST, compose_payload
from tests.test_mail_imap import service_with_mail

I18N = Path(__file__).resolve().parents[2] / "frontend" / "i18n"


def mail_with_files():
    message = EmailMessage()
    message["From"] = "a@school.example"
    message["Subject"] = "Dateien"
    message["Message-ID"] = "<files-1@school.example>"
    message.set_content("siehe Anhang")
    message.add_attachment(b"parent.document.title='pwned';", maintype="application", subtype="javascript", filename="x.js")
    message.add_attachment(b"<script>parent.document.title='pwned'</script>", maintype="text", subtype="html", filename="x.html")
    message.add_attachment(b"<svg onload=alert(1)></svg>", maintype="image", subtype="svg+xml", filename="x.svg")
    message.add_attachment(b"\x89PNG\r\n\x1a\nimage", maintype="image", subtype="png", filename="ok.png")
    return message.as_bytes()


def api_with(tmp_path, imap, smtp=None):
    service, store, school, opened, clock = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    return TestClient(create_app(service)), service, school


def test_script_like_attachments_are_served_as_inert_downloads(tmp_path):
    imap = FakeImap()
    imap.folders["INBOX"].append({"uid": 11, "flags": set(), "raw": mail_with_files()})
    api, _, school = api_with(tmp_path, imap)
    for part, served in (("2", "application/octet-stream"), ("3", "application/octet-stream"), ("4", "application/octet-stream"), ("5", "image/png")):
        answer = api.get("/api/mail/attachment", params={"connection": school, "folder": "INBOX", "uid": "11", "part": part})
        assert answer.status_code == 200
        assert answer.headers["content-type"].split(";")[0] == served
        assert answer.headers["x-content-type-options"] == "nosniff"
        assert answer.headers["content-disposition"].startswith("attachment;")
        assert answer.headers["content-security-policy"] == "sandbox; default-src 'none'"
        assert answer.headers["cross-origin-resource-policy"] == "same-origin"


def test_the_mail_body_is_its_own_sandboxed_document(tmp_path):
    imap = FakeImap()
    api, _, school = api_with(tmp_path, imap)
    answer = api.get("/api/mail/body", params={"connection": school, "folder": "INBOX", "uid": "7", "theme": "dark"})
    assert answer.status_code == 200
    policy = answer.headers["content-security-policy"]
    assert "sandbox" in policy and "default-src 'none'" in policy and "img-src https: data:" in policy
    assert "upgrade-insecure-requests" in policy
    assert "allow-scripts" not in policy and "allow-same-origin" not in policy and "script-src" not in policy
    assert "<script" not in answer.text and "Hello <b>all</b>" in answer.text
    assert "#18201e" in answer.text
    app_policy = api.get("/api/mail", params={}).headers["content-security-policy"]
    assert "frame-src 'self' blob:" in app_policy


def test_a_reopened_draft_with_attachments_can_be_saved_again_and_sent(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    forward = service.mail_call(school, "compose_start", "INBOX", "7", "forward")
    first = service.mail_call(school, "save_draft", compose_payload(mode="forward", source=forward["source"], carry=[forward["attachments"][0]["id"]]))
    start = service.mail_call(school, "compose_start", first["draft"]["folder"], first["draft"]["uid"], "draft")
    carry = [part["id"] for part in start["attachments"]]
    second = service.mail_call(school, "save_draft", compose_payload(mode="draft", source=start["source"], carry=carry, draft=start["draft"]))
    assert second["source"] == second["draft"]
    assert [part["filename"] for part in second["attachments"]] == ["Elternbrief Ausflug.pdf"]
    carry = [part["id"] for part in second["attachments"]]
    sent = service.mail_call(school, "send", compose_payload(mode="draft", source=second["source"], carry=carry, draft=second["draft"]), [], True)
    assert sent["sent"] is True and sent["draft_removed"] is True
    assert imap.folders["Drafts"] == []
    assert b"Elternbrief Ausflug.pdf" in smtp.sent[0]["raw"]


def test_actions_on_a_mail_that_is_not_the_opened_one_are_refused(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    with pytest.raises(mail.MailUnreadable) as caught:
        service.mail_call(school, "mark_seen", "INBOX", "9", expect={"9": "<other@school.example>"})
    assert caught.value.message_key == "api.mail.changed"
    assert imap.stores() == []
    with pytest.raises(mail.MailUnreadable):
        service.mail_call(school, "trash", "INBOX", ["7"], expect={"7": "<office-2@school.example>"})
    assert len(imap.folders["INBOX"]) == 2
    service.mail_call(school, "mark_seen", "INBOX", "9", expect={"9": "<office-2@school.example>"})
    assert len(imap.stores()) == 1


def test_draft_removal_is_reported_only_when_the_draft_is_really_gone(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=FakeSmtp())
    first = service.mail_call(school, "save_draft", compose_payload())["draft"]
    second = service.mail_call(school, "save_draft", compose_payload(subject="later", draft=first))["draft"]
    stale = service.mail_call(school, "send", compose_payload(draft=first), [], True)
    assert stale["draft_removed"] is False
    assert [str(entry["uid"]) for entry in imap.folders["Drafts"]] == [second["uid"]]


def test_partly_refused_recipients_are_named_in_the_result(tmp_path):
    smtp = FakeSmtp(refuse={"quiet@school.example": (550, b"no such user")})
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    result = service.mail_call(school, "send", compose_payload(), [], True)
    assert result["sent"] is True and result["refused"] == ["quiet@school.example"]


def test_the_folder_list_is_not_read_again_for_every_write(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    service.mail_call(school, "move", "INBOX", ["9"], "Archive")
    service.mail_call(school, "move", "Archive", [str(imap.folders["Archive"][0]["uid"])], "INBOX")
    service.mail_call(school, "trash", "INBOX", ["7"])
    statuses = [call for call in imap.calls if call[0] == "list"]
    assert len(statuses) <= 1


def test_only_identity_addresses_of_the_account_are_offered_as_senders():
    data = {
        "mailbox": {"identities": ["alexa.muster@school.example"], "shared": {"owner": "head@school.example", "email": "office@school.example"}},
        "serverConfig": {"sender": "noreply@school.example"},
        "userData": {"contacts": [{"email": "teacher@school.example"}]},
    }
    page = '<script type="application/json" id="php-data">%s</script>' % json.dumps(data)
    assert mail_web.account(page)["addresses"] == ["alexa.muster@school.example"]


def test_a_read_receipt_is_sent_once_per_request_and_never_twice(tmp_path):
    imap = FakeImap()
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap, smtp=smtp)
    service.mail_call(school, "receipt", "INBOX", "7", True, True, REQUEST)
    again = service.mail_call(school, "receipt", "INBOX", "7", True, True, REQUEST)
    assert again["repeated"] is True
    other = service.mail_call(school, "receipt", "INBOX", "7", True, True, "c" * 32)
    assert other["already"] is True
    assert len(smtp.sent) == 1


def test_the_same_send_request_at_the_same_time_is_sent_once(tmp_path):
    smtp = FakeSmtp()
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap, smtp=smtp)
    gate = threading.Barrier(2)
    real = smtp.send_message

    def slow(*args, **kwargs):
        return real(*args, **kwargs)

    smtp.send_message = slow
    mail_service = service.connection(school).mail()
    original = mail_service._remember

    def remember(request_id):
        try:
            gate.wait(2)
        except threading.BrokenBarrierError:
            pass
        return original(request_id)

    mail_service._remember = remember
    outcomes = []

    def go():
        try:
            outcomes.append(service.mail_call(school, "send", compose_payload(request_id="b" * 32), [], True).get("sent"))
        except Exception as error:
            outcomes.append(type(error).__name__)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(smtp.sent) == 1


def test_only_real_drafts_can_be_deleted_as_drafts(tmp_path):
    imap = FakeImap()
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: imap)
    with pytest.raises(mail.MailUnreadable) as caught:
        service.mail_call(school, "delete_draft", "INBOX", "9", True)
    assert caught.value.message_key == "api.mail.notADraft"
    imap.folders["Drafts"].append({"uid": 40, "flags": {"\\Seen"}, "raw": imap.folders["INBOX"][1]["raw"]})
    with pytest.raises(mail.MailUnreadable):
        service.mail_call(school, "delete_draft", "Drafts", "40", True)
    assert len(imap.folders["INBOX"]) == 2 and len(imap.folders["Drafts"]) == 1


def test_a_failed_sieve_sign_in_closes_the_connection():
    transport = FakeSieveTransport()
    with pytest.raises(sieve.SieveSignInRefused):
        sieve.open_sieve("school.example", "u", "wrong", transport=transport)
    assert transport.closed is True


def test_sieve_errors_carry_no_user_text_keys():
    bundle = json.loads((I18N / "de.json").read_text(encoding="utf-8"))
    for error in (sieve.SieveError(), sieve.SieveUnreachable(), sieve.SieveSignInRefused()):
        assert error.message_key == "" or error.message_key in bundle


def test_listed_mails_carry_their_message_id_for_later_checks(tmp_path):
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap)
    listed = service.mail_call(school, "messages", "INBOX")["messages"]
    assert {entry["uid"]: entry["message_id"] for entry in listed} == {"9": "<office-2@school.example>", "7": "<trip-1@school.example>"}
