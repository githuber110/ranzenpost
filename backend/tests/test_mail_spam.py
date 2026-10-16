import pytest
from fastapi.testclient import TestClient

from app.iserv.errors import DataError
from app.server import create_app
from tests.mail_fakes import FakeImap, default_folders
from tests.test_mail_imap import service_with_mail

NO_JUNK = {"Sent": "\\Sent", "Drafts": "\\Drafts", "Archive": "\\Archive", "Trash": "\\Trash"}


def junk_named_otherwise():
    folders = default_folders()
    folders["Unerwuenscht"] = []
    folders["Junk"] = []
    special = dict(NO_JUNK, Unerwuenscht="\\Junk")
    return FakeImap(folders=folders, special=special)


def test_spam_needs_the_confirmation(tmp_path):
    imap = FakeImap(folders=dict(default_folders(), Junk=[]))
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    with pytest.raises(DataError) as caught:
        service.mail_call(school, "spam", "INBOX", ["7"])
    assert caught.value.message_key == "api.mail.confirmRequired"
    assert [entry["uid"] for entry in imap.folders["INBOX"]] == [7, 9]


def test_spam_moves_to_the_folder_marked_junk_by_the_server_and_names_the_way_back(tmp_path):
    imap = junk_named_otherwise()
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    result = service.mail_call(school, "spam", "INBOX", ["7"], True, expect={"7": "<trip-1@school.example>"})
    assert result["ok"] is True and result["moved"] == ["7"]
    assert result["junk"] == "Unerwuenscht"
    assert imap.folders["Junk"] == []
    moved = imap.folders["Unerwuenscht"][0]["uid"]
    assert result["restore"] == {"folder": "Unerwuenscht", "uids": [str(moved)], "target": "INBOX"}
    back = service.mail_call(school, "move", "Unerwuenscht", result["restore"]["uids"], "INBOX")
    assert back["ok"] is True
    assert sorted(entry["uid"] for entry in imap.folders["INBOX"])[-1] > moved
    assert imap.folders["Unerwuenscht"] == []


def test_without_a_marked_junk_folder_nothing_is_moved(tmp_path):
    folders = dict(default_folders(), Junk=[])
    imap = FakeImap(folders=folders, special=NO_JUNK)
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    with pytest.raises(DataError) as caught:
        service.mail_call(school, "spam", "INBOX", ["7"], True)
    assert caught.value.message_key == "api.mail.noJunk"
    assert [entry["uid"] for entry in imap.folders["INBOX"]] == [7, 9]


def test_a_mail_in_the_junk_folder_is_not_moved_again(tmp_path):
    imap = junk_named_otherwise()
    imap.folders["Unerwuenscht"] = [dict(imap.folders["INBOX"][0])]
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    with pytest.raises(DataError) as caught:
        service.mail_call(school, "spam", "Unerwuenscht", ["7"], True)
    assert caught.value.message_key == "api.mail.alreadyJunk"


def test_the_spam_route_passes_the_confirmation(tmp_path):
    imap = junk_named_otherwise()
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    api = TestClient(create_app(service))
    refused = api.post("/api/mail/spam", json={"connection_id": school, "folder": "INBOX", "uids": ["9"]}).json()
    assert refused["ok"] is False and refused["message_key"] == "api.mail.confirmRequired"
    done = api.post("/api/mail/spam", json={"connection_id": school, "folder": "INBOX", "uids": ["9"], "confirmed": True}).json()
    assert done["ok"] is True and done["junk"] == "Unerwuenscht"
    assert "unread_mail" in done


def test_the_folder_list_names_the_junk_folder_by_the_server_flag_only(tmp_path):
    imap = junk_named_otherwise()
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    folders = {entry["id"]: entry for entry in service.mail_call(school, "folders")["folders"]}
    assert folders["Unerwuenscht"]["junk"] is True
    assert folders["Junk"]["junk"] is False
    assert folders["INBOX"]["junk"] is False


def test_two_mails_sharing_a_message_id_both_come_back_with_undo(tmp_path):
    imap = junk_named_otherwise()
    twin = dict(imap.folders["INBOX"][0], uid=11, flags=set())
    imap.folders["INBOX"].append(twin)
    imap.folders["Unerwuenscht"].append(dict(imap.folders["INBOX"][0], uid=3, flags=set()))
    service, _store, school, _opened, _clock = service_with_mail(tmp_path, lambda: imap)
    result = service.mail_call(school, "spam", "INBOX", ["7", "11"], True)
    assert sorted(result["moved"]) == ["11", "7"]
    assert len(result["restore"]["uids"]) == 2
    assert "3" not in result["restore"]["uids"]
    service.mail_call(school, "move", "Unerwuenscht", result["restore"]["uids"], "INBOX")
    assert [entry["uid"] for entry in imap.folders["Unerwuenscht"]] == [3]
    assert len(imap.folders["INBOX"]) == 3
