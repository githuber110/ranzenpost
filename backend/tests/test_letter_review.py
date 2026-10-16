import pytest

from app.iserv.letters import find_answer_edit, parse_answer_form, parse_confirmation
from tests.test_letter_choice import (
    EDIT_PATH,
    KEY,
    SHOW_URL,
    EditClient,
    choice_service,
    option_id,
)
from tests.test_service import CONFIRM_LETTER, CONFIRM_RECIPIENT, ConfirmClient, _fixture_text, make

LOGIN_PAGE = (
    '<html><body><form method="post" action="/iserv/auth/login">'
    '<input name="_username"><input type="password" name="_password">'
    '<button type="submit">Anmelden</button></form></body></html>'
)
DEADLINE_PAGE = (
    '<html><body><div class="alert alert-danger">Die Frist ist abgelaufen.</div>'
    + _fixture_text("letter_confirm_choice.html")
    + "</body></html>"
)
OTHER_LETTER = "30000000-0000-4000-8000-000000000003"
EDIT_URL = "https://school.example" + EDIT_PATH


def edit_service(tmp_path, edits, post_text="", letter="letter_confirm_answered_editable.html"):
    service, store = make(tmp_path)
    client = EditClient(
        "https://school.example", _fixture_text(letter), [_fixture_text(name) for name in edits], post_text=post_text
    )
    service.client_factory = lambda url: client
    return service, store, client


def form_option(service, label):
    form = service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    return next(option["id"] for option in form["choice"]["options"] if option["label"] == label)


def test_a_button_edit_answered_by_a_login_page_is_never_reported_as_changed(tmp_path):
    service, store, client = edit_service(
        tmp_path, ("letter_answer_edit_buttons.html", "letter_answer_edit_buttons.html"), post_text=LOGIN_PAGE
    )
    result = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, None, [form_option(service, "Ablehnen")])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}


def test_a_button_edit_counts_as_changed_only_when_the_school_shows_the_new_answer(tmp_path):
    service, _, _ = edit_service(tmp_path, ("letter_answer_edit_buttons.html", "letter_answer_edit_buttons_plain.html"))
    unclear = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, None, [form_option(service, "Ablehnen")])
    assert unclear["message_key"] == "api.letters.confirm.uncertain"
    service, store, _ = edit_service(
        tmp_path / "shown", ("letter_answer_edit_buttons.html", "letter_answer_edit_buttons_declined.html")
    )
    shown = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, None, [form_option(service, "Ablehnen")])
    assert shown["ok"] is True
    assert store.load_letters_confirmations()[KEY]["answer"] == ["Ablehnen"]


def test_an_answer_that_was_ticked_before_sending_is_not_proof_of_sending(tmp_path):
    ticked = _fixture_text("letter_confirm_choice_radio_answered.html")
    service, store, client = choice_service(tmp_path, [ticked, ticked])
    found = parse_confirmation(ticked, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Mein Kind nimmt nicht teil")])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}


def test_an_error_box_in_the_reply_is_never_a_sent_answer(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store = make(tmp_path)
    client = ConfirmClient("https://school.example", [choice, _fixture_text("letter_confirm_done.html")], post_text=DEADLINE_PAGE)
    service.client_factory = lambda url: client
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}


def test_a_login_page_in_the_reply_of_a_first_answer_is_never_a_sent_answer(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store = make(tmp_path)
    client = ConfirmClient("https://school.example", [choice, _fixture_text("letter_confirm_done.html")], post_text=LOGIN_PAGE)
    service.client_factory = lambda url: client
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["ok"] is False
    assert store.load_letters_confirmations() == {}


def test_clearing_the_text_on_an_edit_sends_an_empty_text(tmp_path):
    service, store, client = edit_service(
        tmp_path, ("letter_answer_edit_radio.html", _cleared_radio_page(tmp_path))
    )
    picked = form_option(service, "Mein Kind nimmt teil")
    result = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, "", [picked])
    assert client.posts[0][1]["answer[text]"] == ""
    assert result["ok"] is True


def _cleared_radio_page(tmp_path):
    path = tmp_path / "cleared.html"
    text = _fixture_text("letter_answer_edit_radio.html").replace("Wir bringen Kuchen mit.", "")
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_an_edit_that_changes_nothing_sends_nothing(tmp_path):
    service, store, client = edit_service(tmp_path, ("letter_answer_edit_radio.html",))
    picked = form_option(service, "Mein Kind nimmt teil")
    result = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, "Wir bringen Kuchen mit.", [picked])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.edit.unchanged"
    assert client.posts == []


def test_a_disabled_read_button_is_no_open_confirmation_but_a_done_one(tmp_path):
    assert parse_confirmation(_fixture_text("letter_confirm_seen_disabled.html"), SHOW_URL) is None
    service, _, _ = choice_service(tmp_path, [_fixture_text("letter_confirm_seen_disabled.html")])
    confirmation = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"]
    assert confirmation["done"] is True
    assert confirmation["open"] is False


def test_a_button_answer_the_school_still_shows_open_is_uncertain_not_rejected(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store, _ = choice_service(tmp_path, [choice])
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Ablehnen")])
    assert result["message_key"] == "api.letters.confirm.uncertain"


def test_a_read_receipt_with_a_message_that_stays_open_is_uncertain(tmp_path):
    page = _fixture_text("letter_confirm_seen_text.html")
    service, store, _ = choice_service(tmp_path, [page, page])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, "Danke")
    assert result["message_key"] == "api.letters.confirm.uncertain"
    plain = _fixture_text("letter_confirm_seen.html")
    service, _, _ = choice_service(tmp_path / "plain", [plain, plain])
    assert service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)["message_key"] == "api.letters.confirm.rejected"


def test_the_rejected_text_does_not_invite_a_second_send():
    from app import messages

    assert "noch einmal" not in messages.text("api.letters.confirm.rejected")


def test_an_edit_link_of_another_letter_is_ignored():
    page = _fixture_text("letter_confirm_answered_editable.html")
    assert find_answer_edit(page, SHOW_URL, CONFIRM_LETTER, CONFIRM_RECIPIENT) == EDIT_URL
    foreign = page.replace(CONFIRM_LETTER + "/" + CONFIRM_RECIPIENT + "/edit", OTHER_LETTER + "/" + CONFIRM_RECIPIENT + "/edit")
    assert find_answer_edit(foreign, SHOW_URL, CONFIRM_LETTER, CONFIRM_RECIPIENT) is None


def test_an_edit_form_posting_to_another_letter_is_ignored():
    page = _fixture_text("letter_answer_edit_radio.html")
    assert parse_answer_form(page, EDIT_URL, CONFIRM_LETTER, CONFIRM_RECIPIENT) is not None
    foreign = page.replace("answer/" + CONFIRM_LETTER, "answer/" + OTHER_LETTER)
    assert parse_answer_form(foreign, EDIT_URL, CONFIRM_LETTER, CONFIRM_RECIPIENT) is None


@pytest.mark.parametrize("word", ["Antwort ändern", "Antwort bearbeiten", "Edit"])
def test_the_edit_link_is_found_by_its_german_or_english_word(word):
    url = "/iserv/parentletter/parent/reply/" + CONFIRM_LETTER + "/" + CONFIRM_RECIPIENT
    page = f'<html><body><a class="btn" href="{url}">{word}</a></body></html>'
    assert find_answer_edit(page, SHOW_URL, CONFIRM_LETTER, CONFIRM_RECIPIENT) == "https://school.example" + url
