from app.iserv.letters import (
    build_archive_payload,
    parse_archive_form,
    parse_letter_detail,
    parse_letter_list,
)

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
