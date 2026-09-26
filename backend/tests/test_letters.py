import logging
import threading
import time

import pytest

from app.iserv.errors import DataError
from app.iserv.letters import (
    build_archive_payload,
    build_confirmation_payload,
    parse_archive_form,
    parse_confirmation,
    parse_letter_detail,
    parse_letter_list,
)
from app.letter_service import LETTER_TABS, LETTER_UNKNOWN_KEY, LIST_REREAD_SECONDS
from app.service import IServService
from app.store import Store
from tests.support import add_school
from tests.test_service import CONFIRM_LETTER, CONFIRM_RECIPIENT, ConfirmClient, _fixture_text, make

BASE = "https://school.example/iserv/parentletter/parent/index"

LETTER_ONE = "10000000-0000-4000-8000-000000000001"
RECIPIENT_ONE = "20000000-0000-4000-8000-000000000001"


def test_parse_letter_list_returns_all_rows(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    assert [letter["title"] for letter in letters] == [
        "Einladung zum Schulfest",
        "Informationen zum Wandertag",
        "Persoenliche Mitteilung",
    ]


def test_parse_letter_list_extracts_ids_and_urls(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    first = letters[0]
    assert first["letter_id"] == LETTER_ONE
    assert first["recipient_id"] == RECIPIENT_ONE
    assert first["show_url"] == (
        "https://school.example/iserv/parentletter/parent/show/"
        + LETTER_ONE
        + "/"
        + RECIPIENT_ONE
    )
    assert first["multi_value"] == LETTER_ONE + "-" + RECIPIENT_ONE


def test_parse_letter_list_reads_cells(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    assert letters[0]["child"] == "Alex Example"
    assert letters[0]["sender"] == "M. Muster"
    assert letters[0]["additional_senders"] == ""
    assert letters[1]["additional_senders"] == "T. Test"
    assert letters[0]["recipients"] == "Jahrgang 01"
    assert letters[2]["recipients"] == "Persoenlich"
    assert letters[0]["published"] == "05.03.2026 14:30"
    assert letters[2]["published"] == "20.03.2026 16:45"


def test_parse_letter_list_collects_multi_values(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    values = [letter["multi_value"] for letter in letters]
    assert len(values) == 3
    assert all(values)


def test_parse_letter_list_without_table_returns_empty():
    assert parse_letter_list("<html><body>empty</body></html>", BASE) == []


def test_parse_letter_list_writes_out_all_additional_senders(fixture):
    letters = parse_letter_list(fixture("letters_index_many_senders.html"), BASE)
    assert letters[0]["additional_senders"] == "T. Test, A. Anders"


def test_parse_archive_form(fixture):
    form = parse_archive_form(fixture("letters_index.html"), BASE)
    assert form is not None
    assert form["action"] == "https://school.example/iserv/parentletter/parent/index"
    assert form["token"] == "synthetic-token-0001"
    assert form["action_field"] == "iserv_crud_multi_select[actions][parent-archive-letter]"


def test_parse_archive_form_without_batch_form_returns_none(fixture):
    assert parse_archive_form(fixture("letter_detail.html"), BASE) is None


def test_build_archive_payload(fixture):
    form = parse_archive_form(fixture("letters_index.html"), BASE)
    payload = build_archive_payload(form, ["a-b", "c-d"])
    assert payload["iserv_crud_multi_select[multi][]"] == ["a-b", "c-d"]
    assert payload["iserv_crud_multi_select[actions][parent-archive-letter]"] == ""
    assert payload["iserv_crud_multi_select[_token]"] == "synthetic-token-0001"


def test_parse_letter_detail_title_and_body(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    assert detail["title"] == "Einladung zum Schulfest"
    assert "Liebe Eltern" in detail["body_html"]
    assert "Schulfest" in detail["body_html"]


def test_parse_letter_detail_sanitizes_body(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    body = detail["body_html"]
    assert "<script" not in body
    assert "<style" not in body
    assert "onclick" not in body
    assert "javascript:" not in body
    assert "<iframe" not in body
    assert "style=" not in body


def test_parse_letter_detail_attachments(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    assert len(detail["attachments"]) == 2
    first = detail["attachments"][0]
    assert first["filename"] == "einladung.pdf"
    assert first["attachment_id"] == "30000000-0000-4000-8000-000000000001"
    assert first["url"] == (
        "https://school.example/iserv/parentletter/attachment/"
        "30000000-0000-4000-8000-000000000001"
    )
    assert detail["attachments"][1]["filename"] == "anmeldung.docx"


def test_parse_letter_detail_archive_url(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    assert detail["archive_url"] == (
        "https://school.example/iserv/parentletter/parent/parent_hide/"
        + LETTER_ONE
        + "/"
        + RECIPIENT_ONE
        + "/40000000-0000-4000-8000-000000000001"
    )


def test_parse_letter_detail_on_arbitrary_html():
    detail = parse_letter_detail("<p>plain</p>", BASE)
    assert detail["attachments"] == []
    assert detail["archive_url"] == ""
    assert "plain" in detail["body_html"]


def test_hide_confirmation_sends_only_the_affirmative_button(fixture):
    from app.iserv.letters import build_hide_payload, parse_hide_confirm

    page = "https://school.example/iserv/parentletter/parent/parent_hide/a/b/c"
    form = parse_hide_confirm(fixture("letter_hide_confirm.html"), page)
    assert form is not None
    assert form.action == page
    payload = build_hide_payload(form)
    assert payload["hide_confirm[_token]"] == "csrf-hide-token"
    assert "hide_confirm[actions][submit]" in payload
    assert "hide_confirm[actions][cancle]" not in payload


def test_hide_confirmation_is_none_without_the_form():
    from app.iserv.letters import parse_hide_confirm

    assert parse_hide_confirm("<html><body>nix</body></html>", "https://school.example") is None


def test_batch_confirmation_keeps_the_selection_and_drops_cancel(fixture):
    from app.iserv.letters import RESTORE_ACTION, build_batch_confirm_payload, parse_batch_confirm

    page = "https://school.example/iserv/parentletter/parent/archive/batch/confirm"
    form = parse_batch_confirm(fixture("letters_batch_confirm.html"), page)
    assert form is not None
    assert form.action == "https://school.example/iserv/parentletter/parent/archive/batch"
    payload = build_batch_confirm_payload(form, RESTORE_ACTION)
    assert payload["iserv_crud_multi_select[confirm]"] == "1"
    assert payload["iserv_crud_multi_select[_token]"] == "csrf-batch-token"
    assert RESTORE_ACTION in payload
    assert "iserv_crud_multi_select[actions][cancel]" not in payload
    assert payload["iserv_crud_multi_select[multi][]"].endswith("20000000-0000-4000-8000-000000000001")


def test_parse_letter_list_reads_the_iserv_unread_class(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    unread = [entry for entry in letters if entry["unread"]]
    assert len(unread) == 1
    assert unread[0]["title"] == "Informationen zum Wandertag"


def test_parse_letter_list_marks_the_rest_as_read(fixture):
    letters = parse_letter_list(fixture("letters_index.html"), BASE)
    assert sum(1 for entry in letters if not entry["unread"]) == len(letters) - 1


def test_attachment_links_are_removed_from_the_body(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    assert "/parentletter/attachment/" not in detail["body_html"]


def test_attachments_are_still_listed_separately(fixture):
    detail = parse_letter_detail(fixture("letter_detail.html"), BASE)
    assert len(detail["attachments"]) == 2
    assert all(entry["filename"] for entry in detail["attachments"])


def test_the_same_attachment_is_listed_only_once():
    html = """
    <html><body><div class="content">
      <p>Text</p>
      <a href="/iserv/parentletter/attachment/abc">Elternbrief.pdf</a>
      <a href="/iserv/parentletter/attachment/abc">Elternbrief.pdf</a>
    </div></body></html>
    """
    detail = parse_letter_detail(html, BASE)
    assert len(detail["attachments"]) == 1


SHOW_URL = (
    "https://school.example/iserv/parentletter/parent/show/"
    + LETTER_ONE
    + "/"
    + RECIPIENT_ONE
)


def test_parse_confirmation_reads_an_open_read_receipt(fixture):
    found = parse_confirmation(fixture("letter_confirm_seen.html"), SHOW_URL)
    assert found is not None
    assert found["type"] == "seen"
    assert found["sendable"] is True
    assert found["action"] == SHOW_URL
    assert found["fields"] == {"form[_token]": "fixture-token-0001"}
    assert found["submits"] == {"form[submit]": ""}
    assert found["text_field"] == ""


def test_parse_confirmation_is_none_for_a_letter_without_one(fixture):
    assert parse_confirmation(fixture("letter_detail.html"), SHOW_URL) is None


def test_parse_confirmation_is_none_once_the_form_is_gone(fixture):
    assert parse_confirmation(fixture("letter_confirm_done.html"), SHOW_URL) is None


def test_parse_confirmation_ignores_the_none_type(fixture):
    assert parse_confirmation(fixture("letter_confirm_none.html"), SHOW_URL) is None


def test_parse_confirmation_reads_the_optional_message_field(fixture):
    found = parse_confirmation(fixture("letter_confirm_seen_text.html"), SHOW_URL)
    assert found["text_field"] == "form[text]"
    assert found["text"] == ""
    assert found["sendable"] is True


def test_parse_confirmation_keeps_accept_decline_unsendable(fixture):
    found = parse_confirmation(fixture("letter_confirm_choice.html"), SHOW_URL)
    assert found["type"] == "confirmation"
    assert found["sendable"] is False
    assert set(found["submits"]) == {"form[accept]", "form[decline]"}


def test_build_confirmation_payload_carries_the_token_and_the_submit(fixture):
    found = parse_confirmation(fixture("letter_confirm_seen.html"), SHOW_URL)
    assert build_confirmation_payload(found) == {
        "form[_token]": "fixture-token-0001",
        "form[submit]": "",
    }


def test_build_confirmation_payload_leaves_the_message_untouched_without_text(fixture):
    found = parse_confirmation(fixture("letter_confirm_seen_text.html"), SHOW_URL)
    assert build_confirmation_payload(found)["form[text]"] == ""
    assert build_confirmation_payload(found, "danke")["form[text]"] == "danke"


FOREIGN_LETTER = "30000000-0000-4000-8000-000000000009"
FOREIGN_RECIPIENT = "40000000-0000-4000-8000-000000000009"
LISTED_KEY = f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}"
INDEX_PATH = "/iserv/parentletter/parent/index"
ARCHIVE_PATH = "/iserv/parentletter/parent/archive"
EMPTY_LIST = "<html><body><p>Keine Elternbriefe</p></body></html>"


def listed_page():
    return _fixture_text("letters_index.html")


def archive_page():
    return listed_page().replace("parent-archive-letter", "parent-restore-letter")


class LetterSchool(ConfirmClient):
    def __init__(self, url="https://school.example", pages=None, current=None, archive=None, post_text=""):
        pages = pages or [_fixture_text("letter_confirm_seen.html"), _fixture_text("letter_confirm_done.html")]
        super().__init__(url, pages, post_text=post_text)
        self.lists = {
            INDEX_PATH: listed_page() if current is None else current,
            ARCHIVE_PATH: EMPTY_LIST if archive is None else archive,
        }
        self.refused = set()
        self.fetched = []

    def fetch(self, path, params=None):
        self.fetched.append(path)
        response = super().fetch(path, params)
        if path in self.refused:
            response.status_code = 503
        if path in self.lists:
            response.text = self.lists[path]
        elif "/parent_hide/" in path:
            response.text = _fixture_text("letter_hide_confirm.html")
        return response

    def reads(self, path):
        return self.fetched.count(path)

    def opened(self):
        return [path for path in self.fetched if "/parent/show/" in path or "/parent_hide/" in path]


def letter_school(tmp_path, **kwargs):
    service, _ = make(tmp_path)
    client = LetterSchool(**kwargs)
    service.client_factory = lambda url: client
    service._session()
    client.fetched.clear()
    return service, client


def assert_untouched(client):
    assert client.posts == []
    assert client.opened() == []


def listed(service, tabs):
    return service._letters()._listed_keys({LISTED_KEY}, tabs)


def later(service, seconds=LIST_REREAD_SECONDS + 1):
    letters = service._letters()
    now = letters.clock()
    letters.clock = lambda: now + seconds


def test_confirming_a_letter_of_no_list_is_refused_without_contacting_the_letter(tmp_path):
    service, client = letter_school(tmp_path)
    result = service.confirm_letter(FOREIGN_LETTER, FOREIGN_RECIPIENT)
    assert result["ok"] is False
    assert result["message_key"] == LETTER_UNKNOWN_KEY
    assert_untouched(client)
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 1


def test_confirming_a_listed_letter_needs_no_new_list(tmp_path):
    service, client = letter_school(tmp_path)
    service.letters("current")
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["ok"] is True
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0
    assert len(client.posts) == 1


def test_confirming_a_letter_that_is_only_in_the_archive_works(tmp_path):
    service, client = letter_school(tmp_path, current=EMPTY_LIST, archive=archive_page())
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["ok"] is True
    assert len(client.posts) == 1


def test_an_unknown_letter_reads_the_list_once_and_then_confirms(tmp_path):
    service, client = letter_school(tmp_path, current=EMPTY_LIST)
    service.letters("current")
    client.lists[INDEX_PATH] = listed_page()
    later(service)
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["ok"] is True
    assert client.reads(INDEX_PATH) == 2
    assert client.reads(ARCHIVE_PATH) == 0
    assert len(client.posts) == 1


def test_a_letter_list_that_cannot_be_read_stops_the_confirmation_before_the_letter(tmp_path):
    service, client = letter_school(tmp_path)
    client.refused.add(INDEX_PATH)
    with pytest.raises(DataError):
        service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert_untouched(client)


def test_archiving_a_letter_of_no_list_is_refused_without_contacting_the_letter(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    with pytest.raises(DataError) as caught:
        service.archive_letter(FOREIGN_LETTER, FOREIGN_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert_untouched(client)
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0


def test_archiving_a_listed_letter_works_and_moves_it_to_the_archive(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letters("current")
    assert service.archive_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT) is True
    assert len(client.posts) == 1
    assert client.reads(INDEX_PATH) == 1
    assert listed(service, ("archive",)) == {LISTED_KEY}
    assert listed(service, ("current",)) == set()


def test_an_unknown_letter_reads_the_list_once_and_then_archives(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    assert service.archive_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT) is True
    assert client.reads(INDEX_PATH) == 1
    assert len(client.posts) == 1


def test_a_letter_that_is_only_in_the_archive_is_not_archived_again(tmp_path):
    service, client = letter_school(
        tmp_path, pages=[_fixture_text("letter_detail.html")], current=EMPTY_LIST, archive=archive_page()
    )
    service.letters("archive")
    with pytest.raises(DataError) as caught:
        service.archive_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert_untouched(client)
    assert client.reads(INDEX_PATH) == 1


def test_restoring_needs_the_letter_in_the_archive(tmp_path):
    service, client = letter_school(tmp_path)
    with pytest.raises(DataError) as caught:
        service.restore_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert client.posts == []
    assert client.reads(ARCHIVE_PATH) == 1
    assert client.reads(INDEX_PATH) == 0


def test_restoring_an_archived_letter_works_and_moves_it_back(tmp_path):
    service, client = letter_school(
        tmp_path, current=EMPTY_LIST, archive=archive_page(), post_text=_fixture_text("letters_batch_confirm.html")
    )
    assert service.restore_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT) is True
    assert len(client.posts) == 2
    assert listed(service, ("current",)) == {LISTED_KEY}


def test_marking_a_letter_of_no_list_read_opens_nothing(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    result = service.mark_letters_read([f"{FOREIGN_LETTER}:{FOREIGN_RECIPIENT}", LISTED_KEY])
    assert result == {"read": 1, "blocked": 0, "failed": 1}


PLANTED_HOST = "planted-school.example"


class HostLeakingLetterSchool(LetterSchool):
    def fetch(self, path, params=None):
        if "/parent/show/" in path:
            raise DataError(
                f"HTTPSConnectionPool(host='{PLANTED_HOST}', port=443): Max retries exceeded with url: {path}"
            )
        return super().fetch(path, params)


def test_marking_a_letter_read_logs_the_cause_without_the_school_host(tmp_path, caplog):
    service, _ = make(tmp_path)
    client = HostLeakingLetterSchool()
    service.client_factory = lambda url: client
    service._session()
    with caplog.at_level(logging.WARNING, logger="app.letter_service"):
        result = service.mark_letters_read([LISTED_KEY])
    assert result == {"read": 0, "blocked": 0, "failed": 1}
    assert "a letter could not be opened while marking it read: DataError at" in caplog.text
    assert PLANTED_HOST not in caplog.text
    assert caplog.records[-1].exc_info is None


def test_opening_a_letter_of_no_list_is_refused_without_a_page_request(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    with pytest.raises(DataError) as caught:
        service.letter_detail(FOREIGN_LETTER, FOREIGN_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert_untouched(client)
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 1


def test_opening_a_listed_letter_needs_no_new_list(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letters("current")
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["title"] == "Einladung zum Schulfest"
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0


def test_opening_a_letter_that_is_only_in_the_archive_works(tmp_path):
    service, client = letter_school(
        tmp_path, pages=[_fixture_text("letter_detail.html")], current=EMPTY_LIST, archive=archive_page()
    )
    service.letters("archive")
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["title"] == "Einladung zum Schulfest"
    assert client.reads(INDEX_PATH) == 0
    assert client.reads(ARCHIVE_PATH) == 1


def test_an_unknown_letter_reads_the_list_once_and_then_opens(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["title"] == "Einladung zum Schulfest"
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0
    assert len(client.opened()) == 1


def test_reading_the_list_and_its_confirmations_opens_no_letter(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letters("current")
    service.letters("archive")
    assert client.opened() == []


def search_entry(service, title):
    return next(entry for entry in service.letters("current")["letters"] if entry["title"] == title)


def test_a_letter_nobody_opened_carries_only_its_list_fields(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    entry = search_entry(service, "Informationen zum Wandertag")
    assert entry["body_text"] == ""
    assert entry["attachments"] == []
    assert entry["confirmation"] is None
    assert (entry["sender"], entry["child"], entry["recipients"]) == ("S. Sample", "Robin Example", "Klasse 02B")
    assert client.opened() == []


def test_opening_a_letter_stores_its_full_text_and_attachments_for_the_search(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    opened = search_entry(service, "Einladung zum Schulfest")
    assert "herzlich zum Schulfest" in opened["body_text"]
    assert [item["filename"] for item in opened["attachments"]] == ["einladung.pdf", "anmeldung.docx"]
    assert search_entry(service, "Persoenliche Mitteilung")["body_text"] == ""
    assert len(client.opened()) == 1


def test_opening_a_letter_again_refreshes_its_stored_text(tmp_path):
    first = _fixture_text("letter_detail.html")
    service, client = letter_school(tmp_path, pages=[first])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    client.pages = [first.replace("herzlich zum Schulfest", "herzlich zum Sommerfest")]
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert "Sommerfest" in search_entry(service, "Einladung zum Schulfest")["body_text"]


OPEN_CONFIRMATION = {"type": "seen", "sendable": True, "can_reply": False}


def with_open_confirmation(service):
    service._letters().connection.store.save_letters_search_cache(
        {LISTED_KEY: {"body_text": "old index text", "attachments": [], "confirmation": dict(OPEN_CONFIRMATION)}}
    )


def test_an_open_confirmation_from_an_older_cache_stays_until_the_letter_is_opened(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    with_open_confirmation(service)
    shown = search_entry(service, "Einladung zum Schulfest")
    assert shown["unread"] is False
    assert shown["confirmation"]["open"] is True
    assert client.opened() == []


def test_opening_the_letter_clears_a_confirmation_that_was_done_on_the_school_website(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    with_open_confirmation(service)
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"] is None
    shown = search_entry(service, "Einladung zum Schulfest")
    assert shown["confirmation"] is None
    assert "herzlich zum Schulfest" in shown["body_text"]
    assert len(client.opened()) == 1


def test_a_search_entry_from_before_the_change_is_still_served(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service._letters().connection.store.save_letters_search_cache(
        {LISTED_KEY: {"body_text": "old index text", "attachments": [], "confirmation": None}}
    )
    assert search_entry(service, "Einladung zum Schulfest")["body_text"] == "old index text"
    assert client.opened() == []


def test_opening_a_letter_of_another_school_is_refused(tmp_path):
    service, two, clients = two_letter_schools(tmp_path)
    service.letters()
    service.letters("archive")
    with pytest.raises(DataError) as caught:
        service.letter_detail(two, CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    for client in clients.values():
        assert_untouched(client)


SEEN_ATTACHMENT = "30000000-0000-4000-8000-000000000001"
UNSEEN_ATTACHMENT = "30000000-0000-4000-8000-000000000003"


def attachment_fetches(client):
    return [path for path in client.fetched if "/parentletter/attachment/" in path]


def test_an_attachment_that_no_opened_letter_showed_is_refused_without_a_request(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    with pytest.raises(DataError) as caught:
        service.letter_attachment(UNSEEN_ATTACHMENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert attachment_fetches(client) == []


def test_an_attachment_of_an_opened_letter_is_fetched(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    service.letter_attachment(SEEN_ATTACHMENT)
    assert attachment_fetches(client) == [f"/iserv/parentletter/attachment/{SEEN_ATTACHMENT}"]


def test_an_attachment_of_an_opened_letter_is_fetched_after_a_restart(tmp_path):
    service, _ = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    service._letters().forget_listed()
    client = LetterSchool(pages=[_fixture_text("letter_detail.html")])
    service.client_factory = lambda url: client
    service._sign_in.drop_session()
    service.letter_attachment(SEEN_ATTACHMENT)
    assert attachment_fetches(client) == [f"/iserv/parentletter/attachment/{SEEN_ATTACHMENT}"]


def test_an_attachment_seen_at_another_school_is_refused(tmp_path):
    service, two, clients = two_letter_schools(tmp_path)
    service.letters()
    service.letter_detail(SCHOOL_ONE_ID, CONFIRM_LETTER, CONFIRM_RECIPIENT)
    with pytest.raises(DataError) as caught:
        service.letter_attachment(two, SEEN_ATTACHMENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert attachment_fetches(clients[SCHOOL_TWO_URL]) == []


def test_a_list_read_a_moment_ago_is_not_read_again_for_an_unknown_letter(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letters("current")
    service.letters("archive")
    later(service, LIST_REREAD_SECONDS - 1)
    with pytest.raises(DataError) as caught:
        service.letter_detail(FOREIGN_LETTER, FOREIGN_RECIPIENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 1
    assert client.opened() == []
    later(service, LIST_REREAD_SECONDS + 1)
    with pytest.raises(DataError):
        service.letter_detail(FOREIGN_LETTER, FOREIGN_RECIPIENT)
    assert client.reads(INDEX_PATH) == 2
    assert client.reads(ARCHIVE_PATH) == 2


def test_parallel_openings_of_an_unknown_letter_share_one_list_read(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    entered = threading.Event()
    release = threading.Event()
    original = client.fetch

    def slow(path, params=None):
        if path == INDEX_PATH:
            entered.set()
            release.wait(5)
        return original(path, params)

    client.fetch = slow
    results = []

    def open_letter():
        results.append(service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["title"])

    first = threading.Thread(target=open_letter)
    second = threading.Thread(target=open_letter)
    first.start()
    assert entered.wait(5)
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(5)
    second.join(5)
    assert results == ["Einladung zum Schulfest", "Einladung zum Schulfest"]
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0


def one_letter_school(tmp_path):
    store = Store(tmp_path / "data")
    school = add_school(store, SCHOOL_ONE_URL, connection_id=SCHOOL_ONE_ID, school_name="School One")
    clients = {SCHOOL_ONE_URL: LetterSchool(SCHOOL_ONE_URL, pages=[_fixture_text("letter_detail.html")])}
    service = IServService(store, client_factory=lambda url: clients[url])
    return service, store, school, clients


def test_an_attachment_of_the_previous_account_is_refused_after_an_account_switch(tmp_path):
    service, store, school, clients = one_letter_school(tmp_path)
    service.letter_detail(school, CONFIRM_LETTER, CONFIRM_RECIPIENT)
    service.letter_attachment(school, SEEN_ATTACHMENT)
    clients[SCHOOL_ONE_URL] = LetterSchool(SCHOOL_ONE_URL, pages=[_fixture_text("letter_detail.html")], current=EMPTY_LIST)
    store.update_connection(school, login_revision=1)
    with pytest.raises(DataError) as caught:
        service.letter_attachment(school, SEEN_ATTACHMENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert attachment_fetches(clients[SCHOOL_ONE_URL]) == []


def test_an_opened_letter_still_serves_its_attachment_after_a_restart_with_the_same_account(tmp_path):
    service, store, school, clients = one_letter_school(tmp_path)
    service.letter_detail(school, CONFIRM_LETTER, CONFIRM_RECIPIENT)
    clients[SCHOOL_ONE_URL] = LetterSchool(SCHOOL_ONE_URL, pages=[_fixture_text("letter_detail.html")])
    store.update_connection(school, login_revision=1)
    service.letter_attachment(school, SEEN_ATTACHMENT)
    assert attachment_fetches(clients[SCHOOL_ONE_URL]) == [f"/iserv/parentletter/attachment/{SEEN_ATTACHMENT}"]


def test_an_attachment_of_a_letter_deleted_at_the_school_is_refused(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    client.lists[INDEX_PATH] = EMPTY_LIST
    service.letters("current")
    with pytest.raises(DataError) as caught:
        service.letter_attachment(SEEN_ATTACHMENT)
    assert caught.value.message_key == LETTER_UNKNOWN_KEY
    assert attachment_fetches(client) == []
    assert client.reads(INDEX_PATH) == 2
    assert client.reads(ARCHIVE_PATH) == 1


class HeldRead:
    def __init__(self, client, first_text, later_text):
        self.client = client
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.texts = [first_text, later_text]
        self.original = client.fetch
        client.fetch = self.fetch

    def fetch(self, path, params=None):
        if path != INDEX_PATH:
            return self.original(path, params)
        self.calls += 1
        self.client.lists[INDEX_PATH] = self.texts[min(self.calls, 2) - 1]
        response = self.original(path, params)
        if self.calls == 1:
            self.entered.set()
            self.release.wait(5)
        return response


def counting_clock(service):
    ticks = iter(range(1, 1000))
    service._letters().clock = lambda: next(ticks)


def test_an_older_list_read_that_finishes_last_does_not_replace_the_newer_list(tmp_path):
    service, client = letter_school(tmp_path)
    counting_clock(service)
    held = HeldRead(client, listed_page(), EMPTY_LIST)
    slow = threading.Thread(target=lambda: service.letters("current"))
    slow.start()
    assert held.entered.wait(5)
    assert service.letters("current")["letters"] == []
    held.release.set()
    slow.join(5)
    assert held.calls == 2
    assert listed(service, ("current",)) == set()
    assert service._letters()._read_stamp("current") == 2


def test_a_list_read_that_started_before_an_archive_does_not_bring_the_letter_back(tmp_path):
    service, client = letter_school(tmp_path, pages=[_fixture_text("letter_detail.html")])
    service.letters("current")
    held = HeldRead(client, listed_page(), listed_page())
    slow = threading.Thread(target=lambda: service.letters("current"))
    slow.start()
    assert held.entered.wait(5)
    assert service.archive_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT) is True
    held.release.set()
    slow.join(5)
    assert listed(service, ("current",)) == set()
    assert listed(service, ("archive",)) == {LISTED_KEY}


def test_clearing_local_data_forgets_the_listed_letters(tmp_path):
    service, _ = letter_school(tmp_path)
    service.letters("current")
    assert listed(service, LETTER_TABS) == {LISTED_KEY}
    service._clear_local_data()
    assert listed(service, LETTER_TABS) == set()


SCHOOL_ONE_URL = "https://school-one.example"
SCHOOL_TWO_URL = "https://school-two.example"
SCHOOL_ONE_ID = "a1b2c3d4"


def two_letter_schools(tmp_path):
    store = Store(tmp_path / "data")
    add_school(store, SCHOOL_ONE_URL, connection_id=SCHOOL_ONE_ID, school_name="School One")
    two = add_school(store, SCHOOL_TWO_URL, connection_id="b2c3d4e5", school_name="School Two")
    clients = {
        SCHOOL_ONE_URL: LetterSchool(SCHOOL_ONE_URL, pages=[_fixture_text("letter_detail.html")], archive=archive_page()),
        SCHOOL_TWO_URL: LetterSchool(SCHOOL_TWO_URL, pages=[_fixture_text("letter_detail.html")], current=EMPTY_LIST),
    }
    service = IServService(store, client_factory=lambda url: clients[url])
    return service, two, clients


@pytest.mark.parametrize("action", ["confirm", "archive", "restore"])
def test_a_letter_of_another_school_is_always_refused(tmp_path, action):
    service, two, clients = two_letter_schools(tmp_path)
    assert [entry["letter_id"] for entry in service.letters()["letters"]].count(CONFIRM_LETTER) == 1
    service.letters("archive")
    calls = {
        "confirm": lambda: service.confirm_letter(two, CONFIRM_LETTER, CONFIRM_RECIPIENT),
        "archive": lambda: service.archive_letter(two, CONFIRM_LETTER, CONFIRM_RECIPIENT),
        "restore": lambda: service.restore_letter(two, CONFIRM_LETTER, CONFIRM_RECIPIENT),
    }
    try:
        result = calls[action]()
    except DataError as error:
        result = {"message_key": error.message_key}
    assert result["message_key"] == LETTER_UNKNOWN_KEY
    for client in clients.values():
        assert_untouched(client)
