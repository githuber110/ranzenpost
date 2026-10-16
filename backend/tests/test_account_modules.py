import logging

import pytest
from fastapi.testclient import TestClient

from app import modules
from app.iserv import addressbook, files, mailinglists
from app.iserv.errors import DataError
from app.server import create_app
from app.service import IServService
from app.store import Store
from tests.account_fakes import LIST_ROOT, OWN_ROOT, SCHOOL, TOKEN, FakeAccountSchool
from tests.mail_web_fakes import SCHOOL as MAIL_SCHOOL
from tests.mail_web_fakes import FakeMailWeb
from tests.support import add_school

ENTRIES = [
    {"segment": "file", "slug": "file", "label": "Dateien"},
    {"segment": "addressbook", "slug": "addressbook", "label": "Adressbuch"},
    {"segment": "mailinglist", "slug": "mailinglist", "label": "Verteilerlisten"},
]
MAIL_ENTRY = {"segment": "mail", "slug": "mail", "label": "E-Mail"}


def school_service(tmp_path, school=None, entries=ENTRIES, url=SCHOOL):
    school = school or FakeAccountSchool()
    store = Store(tmp_path / "data")
    connection_id = add_school(store, url)
    store.connection_store(connection_id).save_modules({"unsupported": list(entries)})
    return IServService(store, client_factory=lambda base: school), connection_id, school


def entry_named(listing, name):
    return next(entry for entry in listing["entries"] if entry["name"] == name)


def test_the_file_table_is_read_by_its_header_words():
    school = FakeAccountSchool()
    parsed = files.parse_listing(school.file_page(OWN_ROOT, ""), SCHOOL + OWN_ROOT)
    assert [(entry["name"], entry["kind"]) for entry in parsed["entries"]] == [
        ("Projekte", "folder"),
        ("Lesetagebuch.pdf", "file"),
        ("Notizen.txt", "file"),
    ]
    pdf = parsed["entries"][1]
    assert pdf["path"] == OWN_ROOT + "/Lesetagebuch.pdf"
    assert (pdf["size_text"], pdf["type_text"], pdf["modified"]) == ("120 KB", "PDF-Dokument", "2026-10-12T08:30")
    assert parsed["upload"]["file_field"] == "upload[file][]"
    assert parsed["upload"]["multiple"] is True
    assert ("upload[_token]", TOKEN) in parsed["upload"]["hidden"]
    assert parsed["upload"]["submit"] == ("upload[submit]", "")
    assert parsed["search"]["field"] == "search[search]"
    assert parsed["search"]["submit"] == ("submit", "")
    assert parsed["crumbs"] == [{"name": "Eigene", "path": OWN_ROOT}]
    assert parsed["location"] == "/Files"


def test_an_empty_file_table_is_framed_without_entries():
    school = FakeAccountSchool(own={"": []})
    parsed = files.parse_listing(school.file_page(OWN_ROOT, ""), SCHOOL + OWN_ROOT)
    assert parsed["framed"] is True
    assert parsed["entries"] == []


def test_a_folder_without_a_type_column_is_known_by_its_icon_or_missing_extension():
    html = (
        "<table id='files'><thead><tr><th>Name</th></tr></thead><tbody>"
        "<tr><td><span class='fa fa-folder'></span><a href='/iserv/file/-/Files/Klasse%205.2'>Klasse 5.2</a></td></tr>"
        "<tr><td><a href='/iserv/file/-/Files/Ablage'>Ablage</a></td></tr>"
        "<tr><td><a href='/iserv/file/-/Files/Plan.pdf'>Plan.pdf</a></td></tr>"
        "</tbody></table>"
    )
    parsed = files.parse_listing(html, SCHOOL + OWN_ROOT)
    assert [(entry["name"], entry["kind"]) for entry in parsed["entries"]] == [("Ablage", "folder"), ("Klasse 5.2", "folder"), ("Plan.pdf", "file")]
    assert parsed["upload"] is None


def test_the_own_files_and_a_folder_are_read_and_unknown_paths_are_refused(tmp_path):
    service, school_id, school = school_service(tmp_path)
    own = service.file_listing(school_id)
    assert own["root"] == "own" and own["can_upload"] is True and own["can_search"] is True
    folder = entry_named(own, "Projekte")
    inner = service.file_listing(school_id, folder["path"])
    assert [entry["name"] for entry in inner["entries"]] == ["Plakat.png"]
    with pytest.raises(DataError) as caught:
        service.file_listing(school_id, "/iserv/file/-/Files/Geheim")
    assert caught.value.message_key == "api.files.unknownFolder"
    with pytest.raises(DataError):
        service.file_listing(school_id, "/iserv/admin/users")
    groups = service.file_listing(school_id, "groups")
    assert groups["root"] == "groups" and groups["can_upload"] is False
    group = service.file_listing(school_id, entry_named(groups, "Klasse 3b")["path"])
    assert group["root"] == "groups" and group["can_upload"] is True
    assert [entry["name"] for entry in groups["entries"]] == ["Klasse 3b"]


def test_a_listed_file_is_downloaded_through_the_app_and_an_unlisted_one_is_refused(tmp_path):
    service, school_id, _school = school_service(tmp_path)
    own = service.file_listing(school_id)
    found = service.school_file(school_id, entry_named(own, "Lesetagebuch.pdf")["path"])
    assert found.content == b"%PDF-1.4 reading log"
    with pytest.raises(DataError) as caught:
        service.school_file(school_id, OWN_ROOT + "/Fremd.pdf")
    assert caught.value.message_key == "api.files.unknownFile"
    api = TestClient(create_app(service))
    answer = api.get("/api/files/file", params={"connection": school_id, "path": OWN_ROOT + "/Notizen.txt"})
    assert answer.status_code == 200
    assert answer.headers["content-disposition"].startswith("attachment")


def test_the_file_search_sends_the_evidenced_form_and_reads_the_answer(tmp_path):
    service, school_id, school = school_service(tmp_path)
    found = service.file_search(school_id, "own", "plakat")
    assert [entry["name"] for entry in found["entries"]] == ["Plakat.png"]
    assert found["query"] == "plakat"
    sent = dict(school.posts[-1]["data"])
    assert school.posts[-1]["path"] == "/iserv/file/search"
    assert sent == {"search[search]": "plakat", "search[path]": "/Files", "search[_token]": TOKEN, "submit": ""}
    assert service.school_file(school_id, OWN_ROOT + "/Projekte/Plakat.png").content == b"\x89PNG fixture"


def test_an_upload_needs_the_confirmation_and_sends_nothing_without_it(tmp_path):
    service, school_id, school = school_service(tmp_path)
    upload = [{"filename": "Brief.pdf", "content": b"%PDF", "content_type": "application/pdf"}]
    answer = service.file_upload(school_id, "own", upload, confirmed=False)
    assert answer["ok"] is False and answer["message_key"] == "api.files.upload.unconfirmed"
    assert school.posts == []


def test_a_confirmed_upload_posts_the_form_and_is_seen_in_the_list_again(tmp_path, caplog):
    service, school_id, school = school_service(tmp_path)
    own = service.file_listing(school_id)
    folder = entry_named(own, "Projekte")["path"]
    upload = [{"filename": "C:\\fakepath\\Brief.pdf", "content": b"%PDF", "content_type": "application/pdf"}]
    with caplog.at_level(logging.INFO):
        answer = service.file_upload(school_id, folder, upload, confirmed=True)
    assert answer["ok"] is True and answer["outcome"] == "done"
    assert [entry["name"] for entry in answer["listing"]["entries"]] == ["Brief.pdf", "Plakat.png"]
    post = school.posts[-1]
    assert post["path"] == "/iserv/file/upload"
    assert post["data"] == [("upload[path]", "/Files/Projekte"), ("upload[_token]", TOKEN), ("upload[submit]", "")]
    assert post["files"] == [("upload[file][]", "Brief.pdf", 4)]
    assert any("file upload done and seen" in record.getMessage() for record in caplog.records)


def test_an_upload_the_list_does_not_show_stays_uncertain(tmp_path):
    school = FakeAccountSchool()
    school.upload_ignored = True
    service, school_id, _ = school_service(tmp_path, school)
    answer = service.file_upload(school_id, "own", [{"filename": "a.txt", "content": b"a"}], confirmed=True)
    assert (answer["ok"], answer["outcome"], answer["message_key"]) == (False, "uncertain", "api.files.upload.uncertain")


def test_an_upload_the_school_refuses_names_the_reason(tmp_path):
    school = FakeAccountSchool()
    school.upload_refused = True
    service, school_id, _ = school_service(tmp_path, school)
    answer = service.file_upload(school_id, "own", [{"filename": "a.txt", "content": b"a"}], confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (False, "rejected")
    assert answer["errors"] == ["Die Datei ist zu groß."]


def test_a_confirmed_upload_into_a_group_folder_uses_the_same_form_and_is_read_again(tmp_path):
    service, school_id, school = school_service(tmp_path)
    groups = service.file_listing(school_id, "groups")
    folder = entry_named(groups, "Klasse 3b")["path"]
    assert service.file_upload(school_id, folder, [{"filename": "a.txt", "content": b"a"}], confirmed=False)["message_key"] == "api.files.upload.unconfirmed"
    assert school.posts == []
    answer = service.file_upload(school_id, folder, [{"filename": "Plan.pdf", "content": b"%PDF"}], confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (True, "done")
    assert [entry["name"] for entry in answer["listing"]["entries"]] == ["Elternbrief.pdf", "Plan.pdf"]
    post = school.posts[-1]
    assert post["path"] == "/iserv/file/upload"
    assert post["data"] == [("upload[path]", "/Groups/Klasse 3b"), ("upload[_token]", TOKEN), ("upload[submit]", "")]
    assert post["files"] == [("upload[file][]", "Plan.pdf", 4)]


def test_a_folder_page_without_the_upload_form_is_refused_before_sending(tmp_path):
    service, school_id, school = school_service(tmp_path)
    answer = service.file_upload(school_id, "groups", [{"filename": "a.txt", "content": b"a"}], confirmed=True)
    assert answer["outcome"] == "unavailable"
    assert school.posts == []


def test_the_upload_route_reads_the_multipart_body(tmp_path):
    service, school_id, school = school_service(tmp_path)
    api = TestClient(create_app(service))
    answer = api.post(
        "/api/files/upload",
        data={"data": '{"connection_id": "%s", "path": "own", "confirmed": true}' % school_id},
        files={"files": ("Neu.txt", b"hello", "text/plain")},
    ).json()
    assert answer["ok"] is True
    assert "Neu.txt" in [entry["name"] for entry in answer["listing"]["entries"]]


def test_a_school_without_the_module_offers_no_files(tmp_path):
    service, school_id, _ = school_service(tmp_path, entries=[])
    with pytest.raises(DataError) as caught:
        service.file_listing(school_id)
    assert caught.value.message_key == "api.account.notOffered"
    assert service.account_modules() == {"schools": []}


def test_the_account_modules_are_listed_per_school_and_marked_as_read_by_the_app(tmp_path):
    service, school_id, _ = school_service(tmp_path, entries=ENTRIES[:1])
    listed = service.account_modules()["schools"]
    assert [(entry["connection_id"], entry["file"], entry["addressbook"], entry["mailinglist"]) for entry in listed] == [(school_id, True, False, False)]
    registry = modules.normalize({"unsupported": ENTRIES})
    assert registry["unsupported"] == []
    assert [entry["slug"] for entry in registry["covered"]] == ["file", "addressbook", "mailinglist"]


def test_the_address_books_are_searched_on_demand(tmp_path):
    service, school_id, school = school_service(tmp_path)
    found = service.address_search(school_id, "beh")
    assert [(person["name"], person["address"], person["class_name"]) for person in found["people"]] == [
        ("Anna Behrens", "anna.behrens@school-one.example", "3b"),
        ("Tom Behrendt", "tom.behrendt@school-one.example", "4a"),
    ]
    searched = [params for path, params in school.fetched if params and path.startswith("/iserv/addressbook")]
    assert searched == [{"filter[search]": "beh"}, {"filter[search]": "beh"}]
    assert service.address_search(school_id, "b")["people"] == []


def test_the_address_book_parser_takes_the_address_from_the_mail_link():
    html = (
        "<table id='crud-table'><thead><tr><th></th><th>Name</th><th>E-Mail-Adresse</th><th>Klasse</th></tr></thead><tbody>"
        "<tr><td></td><td>Muster, Mia</td><td><a href='mailto:mia@school.example'>Mail</a></td><td>3b</td></tr>"
        "<tr><td colspan='4'>Keine Einträge</td></tr></tbody></table>"
    )
    assert [(person["name"], person["address"]) for person in addressbook.parse_people(html)] == [("Muster, Mia", "mia@school.example")]
    assert addressbook.parse_people("<html></html>") is None


def test_the_recipient_lookup_also_offers_the_address_book(tmp_path):
    class MailAndBook(FakeMailWeb):
        def __init__(self):
            super().__init__()
            self.book = FakeAccountSchool(base=MAIL_SCHOOL)

        def fetch(self, path, params=None):
            if path.startswith("/iserv/addressbook") or path == "/iserv/":
                return self.book.fetch(path, params)
            return super().fetch(path, params)

    web = MailAndBook()
    service, school_id, _ = school_service(tmp_path, web, ENTRIES + [MAIL_ENTRY], url=MAIL_SCHOOL)
    found = service.mail_web_call(school_id, "recipients", "behr")["recipients"]
    assert {"name": "Anna Behrens", "address": "anna.behrens@school-one.example", "group": False} in found
    teachers = service.mail_web_call(school_id, "recipients", "teach")["recipients"]
    assert teachers[0] == {"name": "Class Teacher", "address": "teacher@school.example", "group": False}


def test_the_mailing_lists_and_their_addresses_are_read(tmp_path):
    service, school_id, _ = school_service(tmp_path)
    overview = service.mailing_lists(school_id)
    assert [(entry["id"], entry["title"], entry["deletable"]) for entry in overview["lists"]] == [("41", "Elternrat 3b", True)]
    assert overview["can_import"] is True and overview["can_delete"] is True
    assert overview["import_fields"] == [{"name": "form[list][title]", "label": "Titel", "required": False, "maxlength": ""}]
    detail = service.mailing_list_detail(school_id, "41")
    assert detail["addresses"] == ["anna.behrens@school-one.example", "eltern.mia@example.org"]
    with pytest.raises(DataError) as caught:
        service.mailing_list_detail(school_id, "99")
    assert caught.value.message_key == "api.lists.unknown"


def test_a_confirmed_import_sends_the_form_and_finds_the_new_list(tmp_path):
    service, school_id, school = school_service(tmp_path)
    upload = [{"filename": "Sportfest.txt", "content": b"a@example.org\nb@example.org\n", "content_type": "text/plain"}]
    assert service.mailing_list_import(school_id, {}, upload, confirmed=False)["message_key"] == "api.lists.unconfirmed"
    assert school.posts == []
    answer = service.mailing_list_import(school_id, {"form[list][title]": "Sportfest", "form[other]": "x"}, upload, confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (True, "done")
    assert [entry["title"] for entry in answer["overview"]["lists"]] == ["Elternrat 3b", "Sportfest"]
    post = school.posts[-1]
    assert post["path"] == LIST_ROOT + "/import"
    assert post["data"] == [("form[_token]", TOKEN), ("form[list][title]", "Sportfest"), ("form[submit]", "")]
    assert post["files"] == [("form[list][upload]", "Sportfest.txt", 28)]


def test_a_confirmed_delete_answers_the_confirmation_page_and_checks_the_list(tmp_path):
    service, school_id, school = school_service(tmp_path)
    service.mailing_lists(school_id)
    assert service.mailing_list_delete(school_id, "41", confirmed=False)["message_key"] == "api.lists.unconfirmed"
    answer = service.mailing_list_delete(school_id, "41", confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (True, "done")
    assert answer["overview"]["lists"] == []
    first, second = school.posts
    assert first["path"] == LIST_ROOT + "/batch/confirm"
    assert first["data"] == [("iserv_crud_multi_select[_token]", TOKEN), ("iserv_crud_multi_select[multi][]", "41"), ("iserv_crud_multi_select[actions][delete]", "")]
    assert second["path"] == LIST_ROOT + "/batch"
    assert ("iserv_crud_multi_select_confirm[confirm]", "") in second["data"]
    assert not any("cancel" in name for name, _ in second["data"])


def test_a_delete_without_a_confirmation_page_is_checked_the_same_way(tmp_path):
    school = FakeAccountSchool()
    school.delete_asks = False
    service, school_id, _ = school_service(tmp_path, school)
    service.mailing_lists(school_id)
    answer = service.mailing_list_delete(school_id, "41", confirmed=True)
    assert answer["ok"] is True
    assert len(school.posts) == 1


FIRST_ACTION = SCHOOL + LIST_ROOT + "/batch/confirm"
TWO_LISTS = [{"id": "7", "title": "Chor", "addresses": []}, {"id": "8", "title": "Sport", "addresses": []}]


def test_the_follow_up_form_is_never_the_import_or_a_form_without_the_chosen_list():
    school = FakeAccountSchool()
    overview = school.list_page()
    assert mailinglists.follow_up_form(overview, SCHOOL + LIST_ROOT, "41", FIRST_ACTION, ["41"]) is None
    assert mailinglists.follow_up_form(school.confirm_page(["41"]), SCHOOL + LIST_ROOT, "7", FIRST_ACTION, ["41", "7"]) is None
    found = mailinglists.follow_up_form(school.confirm_page(["41"]), FIRST_ACTION, "41", FIRST_ACTION, ["41"])
    assert found["action"] == SCHOOL + LIST_ROOT + "/batch"


def test_a_confirmation_naming_a_second_list_is_never_answered():
    school = FakeAccountSchool(lists=[dict(entry) for entry in TWO_LISTS])
    assert mailinglists.follow_up_form(school.confirm_page(["7", "8"]), FIRST_ACTION, "7", FIRST_ACTION, ["7", "8"]) is None


def test_the_overview_shown_again_with_the_box_ticked_is_never_answered():
    html = (
        "<form action='/iserv/mailinglist/batch/export' method='post'><table id='crud-table'><tbody>"
        "<tr><td><input type='checkbox' name='iserv_crud_multi_select[multi][]' value='7' checked></td><td>Chor</td></tr>"
        "<tr><td><input type='checkbox' name='iserv_crud_multi_select[multi][]' value='8'></td><td>Sport</td></tr>"
        "</tbody></table><button type='submit' name='iserv_crud_multi_select[actions][export]'>Export</button>"
        "<input type='hidden' name='iserv_crud_multi_select[_token]' value='t'></form>"
    )
    assert mailinglists.follow_up_form(html, FIRST_ACTION, "7", FIRST_ACTION, ["7", "8"]) is None
    alone = html.replace("value='8'", "value='9'").replace("batch/export", "batch/remove").replace("[actions][export]", "[actions][delete]")
    assert mailinglists.follow_up_form(alone, FIRST_ACTION, "7", FIRST_ACTION, ["7"]) is None
    again = (
        "<form action='/iserv/mailinglist/batch/confirm' method='post'>"
        "<input type='checkbox' name='iserv_crud_multi_select[multi][]' value='7' checked>"
        "<button type='submit' name='iserv_crud_multi_select[actions][delete]'>Löschen</button>"
        "<input type='hidden' name='iserv_crud_multi_select[_token]' value='t'></form>"
    )
    assert mailinglists.follow_up_form(again, FIRST_ACTION, "7", FIRST_ACTION, ["7"]) is None


def test_an_unrelated_form_carrying_the_same_number_is_never_answered():
    html = (
        "<form action='/iserv/mailinglist/settings' method='post'><input type='hidden' name='page' value='7'>"
        "<input type='hidden' name='settings[_token]' value='t'><button type='submit' name='settings[save]'>Speichern</button></form>"
    )
    assert mailinglists.follow_up_form(html, FIRST_ACTION, "7", FIRST_ACTION, ["7"]) is None


def test_a_confirmation_naming_another_list_too_is_not_sent_and_stays_uncertain(tmp_path):
    school = FakeAccountSchool(lists=[dict(entry) for entry in TWO_LISTS])
    school.confirm_extra = ["8"]
    service, school_id, _ = school_service(tmp_path, school)
    service.mailing_lists(school_id)
    answer = service.mailing_list_delete(school_id, "7", confirmed=True)
    assert answer["outcome"] == "uncertain"
    assert [post["path"] for post in school.posts] == [LIST_ROOT + "/batch/confirm"]
    assert [entry["id"] for entry in school.lists] == ["7", "8"]


def test_a_redirected_answer_is_never_followed(tmp_path):
    school = FakeAccountSchool()
    school.confirm_redirected = True
    service, school_id, _ = school_service(tmp_path, school)
    service.mailing_lists(school_id)
    answer = service.mailing_list_delete(school_id, "41", confirmed=True)
    assert answer["outcome"] == "uncertain"
    assert len(school.posts) == 1


def test_a_delete_that_also_removed_another_list_is_reported_uncertain(tmp_path):
    school = FakeAccountSchool(lists=[dict(entry) for entry in TWO_LISTS])
    school.delete_also = ["8"]
    service, school_id, _ = school_service(tmp_path, school)
    service.mailing_lists(school_id)
    answer = service.mailing_list_delete(school_id, "7", confirmed=True)
    assert (answer["ok"], answer["outcome"], answer["message_key"]) == (False, "uncertain", "api.lists.delete.othersGone")


def test_the_list_detail_skips_the_page_frame_addresses():
    school = FakeAccountSchool()
    detail = mailinglists.parse_detail(school.list_detail_page("41"))
    assert detail["title"] == "Elternrat 3b"
    assert "owner@school-one.example" not in detail["addresses"]
    assert "support@school-one.example" not in detail["addresses"]


def test_a_folder_link_outside_the_listing_root_is_kept_and_opened_through_the_app(tmp_path):
    html = (
        "<table id='files'><thead><tr><th>Name</th><th>Typ</th></tr></thead><tbody>"
        "<tr><td><a href='/iserv/file/a1b2/folder'>Klasse 5</a></td><td>Ordner</td></tr></tbody></table>"
    )
    parsed = files.parse_listing(html, SCHOOL + OWN_ROOT)
    assert [(entry["name"], entry["kind"], entry["path"]) for entry in parsed["entries"]] == [("Klasse 5", "folder", "/iserv/file/a1b2/folder")]


def test_the_shared_address_book_is_searched_when_the_start_page_is_missing(tmp_path):
    school = FakeAccountSchool()
    school.book_root_missing = True
    service, school_id, _ = school_service(tmp_path, school)
    found = service.address_search(school_id, "office")
    assert [person["address"] for person in found["people"]] == ["office@school-one.example"]


def test_an_import_named_after_the_whole_file_name_is_found_again(tmp_path):
    school = FakeAccountSchool()
    school.title_with_extension = True
    service, school_id, _ = school_service(tmp_path, school)
    upload = [{"filename": "Chor.csv", "content": b"a@example.org", "content_type": "text/csv"}]
    answer = service.mailing_list_import(school_id, {}, upload, confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (True, "done")


PRIVATE = "Mia Muster Zeugnisse"


def test_file_names_stay_out_of_the_log_and_the_error_details(tmp_path, caplog):
    school = FakeAccountSchool()
    school.own[""].append({"name": PRIVATE, "folder": True, "date": "2026-10-01 10:00"})
    school.own[PRIVATE] = []
    school.broken_folders = [PRIVATE]
    service, school_id, _ = school_service(tmp_path, school)
    own = service.file_listing(school_id)
    details = []
    with caplog.at_level(logging.INFO):
        for call in (
            lambda: service.file_listing(school_id, entry_named(own, PRIVATE)["path"]),
            lambda: service.file_listing(school_id, OWN_ROOT + "/Mia%20Muster%20Geheim"),
            lambda: service.school_file(school_id, OWN_ROOT + "/Mia%20Muster%20Zeugnis.pdf"),
        ):
            with pytest.raises(DataError) as caught:
                call()
            details.append(str(caught.value.detail) + " " + str(caught.value))
    text = " ".join(record.getMessage() for record in caplog.records) + " ".join(details)
    assert "Mia" not in text and "Zeugnis" not in text


def test_an_upload_the_school_stored_under_another_name_is_not_taken_as_done(tmp_path):
    school = FakeAccountSchool()
    school.rename_uploads = True
    service, school_id, _ = school_service(tmp_path, school)
    answer = service.file_upload(school_id, "own", [{"filename": "Brief.pdf", "content": b"%PDF"}], confirmed=True)
    assert (answer["ok"], answer["outcome"]) == (False, "uncertain")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_the_same_upload_is_refused_for_a_while_after_an_unclear_run(tmp_path):
    school = FakeAccountSchool()
    school.upload_ignored = True
    service, school_id, _ = school_service(tmp_path, school)
    clock = Clock()
    files_service = service.connection(school_id).files()
    files_service.clock = clock
    upload = [{"filename": "a.txt", "content": b"a"}]
    assert service.file_upload(school_id, "own", upload, confirmed=True)["outcome"] == "uncertain"
    sent = len(school.posts)
    again = service.file_upload(school_id, "own", upload, confirmed=True)
    assert (again["ok"], again["message_key"]) == (False, "api.files.upload.recent")
    assert len(school.posts) == sent
    assert service.file_upload(school_id, "own", [{"filename": "a.txt", "content": b"b"}], confirmed=True)["outcome"] == "uncertain"
    clock.now += 601
    assert service.file_upload(school_id, "own", upload, confirmed=True)["outcome"] == "uncertain"
    assert len(school.posts) == sent + 2


def test_the_same_import_is_refused_for_a_while_after_an_unclear_run(tmp_path):
    school = FakeAccountSchool()
    school.import_ignored = True
    service, school_id, _ = school_service(tmp_path, school)
    clock = Clock()
    contacts = service.connection(school_id).contacts("mailinglist")
    contacts.clock = clock
    upload = [{"filename": "Chor.txt", "content": b"a@example.org"}]
    assert service.mailing_list_import(school_id, {}, upload, confirmed=True)["outcome"] == "uncertain"
    sent = len(school.posts)
    again = service.mailing_list_import(school_id, {}, upload, confirmed=True)
    assert (again["ok"], again["message_key"]) == (False, "api.lists.import.recent")
    assert len(school.posts) == sent
    clock.now += 601
    assert service.mailing_list_import(school_id, {}, upload, confirmed=True)["outcome"] == "uncertain"
    assert len(school.posts) == sent + 1
