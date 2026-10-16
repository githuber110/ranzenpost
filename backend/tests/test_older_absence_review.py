import threading
import time

import pytest
from bs4 import BeautifulSoup

from app import absence_service
from app.iserv.older_absence_form import (
    OlderFormError,
    attachment_entries,
    create_path,
    form_values,
    offered_profiles,
    parse_create_form,
    upload_form,
)
from app.iserv.older_absences import _detail_path
from app.older_absence_actions import (
    ALREADY_SENT_KEY,
    ATTACHED_KEY,
    EXPORT_EMPTY_KEY,
    FILES_NOT_TAKEN_KEY,
    LOCKED_KEY,
    SENT_KEY,
    UNSUPPORTED_KEY,
)
from tests.support import Response
from tests.test_older_absence_form import (
    CHILDREN,
    FORM_GERMAN_SELECT,
    LIST,
    SCHOOL,
    UPLOAD,
    FakeSchool,
    attachment_school,
    older_school,
    report,
)


def keys_of(service, connection):
    return {item["name"]: item["key"] for item in service.older_absence_detail(connection.id, "older:481")["attachments"]}


def test_an_attachment_is_removed_by_its_key_even_when_the_list_moved_meanwhile(tmp_path):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf", "Brief.pdf"])
    school.removable = "form"
    brief = keys_of(service, connection)["Brief.pdf"]
    school.files["481"].insert(0, "Neu.pdf")
    result = service.delete_older_attachment(connection.id, "older:481", brief)
    assert result["ok"] is True
    assert school.files["481"] == ["Neu.pdf", "Attest.pdf"]
    assert school.posts[0][0] == SCHOOL + "/iserv/absence/481/attachment/brief-pdf/delete"


def test_an_unknown_attachment_key_is_refused_without_a_request(tmp_path):
    service, connection, school = attachment_school(tmp_path, files=["Attest.pdf"])
    school.removable = "form"
    assert service.delete_older_attachment(connection.id, "older:481", "0")["ok"] is False
    assert service.delete_older_attachment(connection.id, "older:481", 0)["ok"] is False
    with pytest.raises(Exception):
        service.older_absence_attachment(connection.id, "older:481", "0")
    assert school.posts == []
    key = keys_of(service, connection)["Attest.pdf"]
    assert service.older_absence_attachment(connection.id, "older:481", key).content == b"PDF-Attest.pdf"


def test_attachments_told_apart_only_by_their_query_keep_their_own_remove_link():
    html = (
        '<ul><li><a href="/iserv/absence/481/attachment/download?id=1">A.pdf</a> <a href="/iserv/absence/481/attachment/delete?id=1">x</a></li>'
        '<li><a href="/iserv/absence/481/attachment/download?id=2">B.pdf</a> <a href="/iserv/absence/481/attachment/delete?id=2">x</a></li></ul>'
    )
    found = {item.name: item.delete_link for item in attachment_entries(html, SCHOOL + "/iserv/absence/481/show")}
    assert found == {"A.pdf": "/iserv/absence/481/attachment/delete?id=1", "B.pdf": "/iserv/absence/481/attachment/delete?id=2"}


class EditOnDelete(FakeSchool):
    def get(self, path):
        if path == "/iserv/absence/481/delete":
            self.reads.append(path)
            return Response(200, SCHOOL + "/iserv/absence/481/show", '<form method="post" action="/iserv/absence/481/edit">'
                            '<textarea name="e[reason]">Fieber</textarea><input type="hidden" name="e[_token]" value="t">'
                            '<button type="submit" name="e[save]">Speichern</button></form>')
        return super().get(path)

    def post(self, url, data, headers, files=None):
        self.posts.append((url, list(data)))
        return Response(200, SCHOOL + LIST, self.list_page())


def test_withdraw_never_posts_a_form_that_is_not_the_delete_of_this_entry(tmp_path):
    school = EditOnDelete()
    school.rows[0]["delete"] = True
    service, connection, school = older_school(tmp_path, school)
    result = service.delete_absence(connection.id, {"type": "absence", "id": "older:481"})
    assert result["ok"] is False and result["message_key"] == LOCKED_KEY
    assert school.posts == []


def test_a_second_report_for_the_same_profile_and_days_needs_an_explicit_send_again(tmp_path):
    school = FakeSchool()
    school.store_posted = False
    service, connection, school = older_school(tmp_path, school)
    assert report(service, connection)["uncertain"] is True
    second = report(service, connection)
    assert second["ok"] is False and second["message_key"] == ALREADY_SENT_KEY
    assert len(school.posts) == 1
    assert report(service, connection, from_date="2026-10-22", till_date="2026-10-22")["uncertain"] is True
    assert len(school.posts) == 2
    report(service, connection, send_again=True)
    assert len(school.posts) == 3


def test_a_report_for_days_the_list_already_shows_needs_an_explicit_send_again(tmp_path):
    service, connection, school = older_school(tmp_path)
    blocked = report(service, connection, from_date="2026-09-14", till_date="2026-09-16")
    assert blocked["message_key"] == ALREADY_SENT_KEY
    assert school.posts == []


class NoticeList(FakeSchool):
    def list_page(self):
        return super().list_page().replace(
            "<body>",
            '<body><form method="post" action="/iserv/absence/"><input type="hidden" name="absence[_token]" value="f"></form>'
            '<div class="alert alert-danger">Krankmeldungen bitte bis 8 Uhr.</div>',
        )


class NoticeDetail(FakeSchool):
    def detail_page(self, entry_id, files):
        return super().detail_page(entry_id, files).replace("<h1>", '<div class="alert alert-danger">Atteste bitte als PDF.</div><h1>')


def test_a_report_the_list_shows_afterwards_is_a_success_despite_a_notice_on_the_page(tmp_path):
    service, connection, school = older_school(tmp_path, NoticeList())
    result = report(service, connection)
    assert result["ok"] is True and result["message_key"] == SENT_KEY


def test_an_attachment_the_detail_shows_afterwards_is_a_success_despite_a_notice(tmp_path):
    school = NoticeDetail()
    school.rows[0]["detail"] = True
    service, connection, school = older_school(tmp_path, school)
    result = service.attach_older_absence(connection.id, "older:481", UPLOAD)
    assert result["ok"] is True and result["message_key"] == ATTACHED_KEY


def hidden_student(value):
    return FORM_GERMAN_SELECT.replace(
        '<select id="absence_student" name="absence[student]" required><option value="">Bitte wählen</option>\n'
        '<option value="11">Muster, Mia</option><option value="12">Beispiel, Tom</option><option value="13">Fremd, Fritz</option></select>',
        '<input type="hidden" name="absence[student]" value="%s">' % value,
    )


def test_a_hidden_profile_field_with_an_unknown_id_is_never_sent(tmp_path):
    service, connection, school = older_school(tmp_path, FakeSchool(form_html=hidden_student("13")), children=CHILDREN[:1])
    result = report(service, connection)
    assert result["message_key"] == UNSUPPORTED_KEY
    assert school.posts == []
    assert service.older_absence_form(connection.id)["message_key"] == UNSUPPORTED_KEY


def test_a_hidden_profile_field_holding_a_known_id_offers_only_that_profile():
    form = parse_create_form(hidden_student("c-tom"), SCHOOL + "/iserv/absence/add", CHILDREN)
    assert form.unsupported == []
    assert offered_profiles(form, CHILDREN) == ["c-tom"]


def test_the_detail_link_is_only_the_plain_or_show_path_of_the_entry():
    row = BeautifulSoup('<tr><td><a href="/iserv/absence/481/copy">c</a><a href="/iserv/absence/481/show">i</a></td></tr>', "html.parser").tr
    assert _detail_path(row, "481") == "/iserv/absence/481/show"
    copy_only = BeautifulSoup('<tr><td><a href="/iserv/absence/481/copy">c</a></td></tr>', "html.parser").tr
    assert _detail_path(copy_only, "481") == ""
    plain = BeautifulSoup('<tr><td><a href="/iserv/absence/481">14.09.</a></td></tr>', "html.parser").tr
    assert _detail_path(plain, "481") == "/iserv/absence/481"


def test_the_create_link_by_label_must_be_a_plain_module_page():
    page_url = SCHOOL + LIST
    assert create_path('<a href="/iserv/absence/print?page=2">Neu drucken</a>', page_url) == ""
    assert create_path('<a href="/iserv/absence/archive/old">Neu</a>', page_url) == ""
    assert create_path('<a href="/iserv/absence/report">Abwesenheit melden</a>', page_url) == "/iserv/absence/report"


def test_copy_move_or_rename_links_are_no_attachments_and_an_upload_form_belongs_to_the_entry():
    html = '<a href="/iserv/absence/481/attachment/1/copy">a</a><a href="/iserv/absence/481/file/1/move">b</a><a href="/iserv/absence/481/file/1/rename">c</a>'
    assert attachment_entries(html, SCHOOL + "/iserv/absence/481/show") == []
    other = '<form method="post" action="/iserv/absence/999/attachment/add"><input type="file" name="f"></form>'
    assert upload_form(other, SCHOOL + "/iserv/absence/481/show", "481") == (None, "")
    own = other.replace("999", "481")
    assert upload_form(own, SCHOOL + "/iserv/absence/481/show", "481")[1] == "f"


def test_an_unreadable_end_date_is_an_error_and_not_the_start_date():
    form = parse_create_form(FORM_GERMAN_SELECT, SCHOOL + "/iserv/absence/add", CHILDREN)
    with pytest.raises(OlderFormError) as error:
        form_values(form, {"from_date": "2026-10-20", "till_date": "21.10.2026"}, "c-mia", offered_profiles(form, CHILDREN))
    assert error.value.field_key == "till"


def test_an_export_without_rows_of_known_profiles_says_so(tmp_path):
    school = FakeSchool()
    school.export = "Zeitraum;Name\r\n15.09.2026;Fremd, Fritz\r\n".encode("utf-8")
    service, connection, school = older_school(tmp_path, school)
    with pytest.raises(Exception) as error:
        service.older_absence_export(connection.id)
    assert getattr(error.value, "message_key", "") == EXPORT_EMPTY_KEY


FORM_WITH_FILE = FORM_GERMAN_SELECT.replace("<textarea", '<input type="file" name="absence[file]"><textarea')


def test_files_with_a_report_go_through_the_file_field_of_the_create_form(tmp_path):
    service, connection, school = older_school(tmp_path, FakeSchool(form_html=FORM_WITH_FILE))
    payload = {"type": "absence", "student_id": "c-mia", "from_date": "2026-10-20", "till_date": "2026-10-21"}
    result = service.report_absence(connection.id, payload, attachments=[UPLOAD])
    assert result["ok"] is True
    assert school.posts[0][3] == [("absence[file]", ("attest.pdf", b"%PDF-1", "application/pdf"))]


def test_files_with_a_report_are_refused_when_the_form_takes_none(tmp_path):
    service, connection, school = older_school(tmp_path)
    payload = {"type": "absence", "student_id": "c-mia", "from_date": "2026-10-20", "till_date": "2026-10-21"}
    result = service.report_absence(connection.id, payload, attachments=[UPLOAD])
    assert result["ok"] is False and result["message_key"] == FILES_NOT_TAKEN_KEY
    assert school.posts == []


def test_every_thread_gets_the_same_absence_service_and_thus_the_same_send_lock(tmp_path, monkeypatch):
    service, connection, _school = older_school(tmp_path)
    connection._absence_service = None
    original = absence_service.AbsenceService.__init__

    def slow(self, owner):
        time.sleep(0.05)
        original(self, owner)

    monkeypatch.setattr(absence_service.AbsenceService, "__init__", slow)
    found = []
    threads = [threading.Thread(target=lambda: found.append(connection._absences())) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({id(item) for item in found}) == 1
