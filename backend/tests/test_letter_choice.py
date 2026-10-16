import logging

import pytest
from requests import ConnectionError as RequestsConnectionError

from app.iserv.letters import (
    build_choice_payload,
    choice_recorded,
    confirmation_shape,
    parse_confirmation,
    picked_options,
    public_choice,
)
from app import reportfacts
from tests.test_service import CONFIRM_LETTER, CONFIRM_RECIPIENT, ConfirmClient, _fixture_text, make

SHOW_URL = f"https://school.example/iserv/parentletter/parent/show/{CONFIRM_LETTER}/{CONFIRM_RECIPIENT}"
KEY = f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}"


def parsed(name):
    return parse_confirmation(_fixture_text(name), SHOW_URL)


def option_id(found, label):
    return next(option["id"] for option in found["choice"]["options"] if option["label"] == label)


def test_accept_and_decline_buttons_become_two_answers():
    found = parsed("letter_confirm_choice.html")
    assert found["type"] == "confirmation"
    assert found["sendable"] is True
    assert public_choice(found["choice"]) == {
        "mode": "submit",
        "multiple": False,
        "options": [
            {"id": option_id(found, "Zustimmen"), "label": "Zustimmen", "selected": False},
            {"id": option_id(found, "Ablehnen"), "label": "Ablehnen", "selected": False},
        ],
    }


def test_the_public_choice_carries_no_field_names_or_values():
    found = parsed("letter_confirm_choice_radio.html")
    shown = str(public_choice(found["choice"]))
    assert "form[answer]" not in shown
    assert "fixture-token" not in shown


def test_a_button_answer_sends_the_token_and_only_the_chosen_button_like_a_browser():
    found = parsed("letter_confirm_choice.html")
    picked = picked_options(found["choice"], [option_id(found, "Ablehnen")])
    assert build_choice_payload(found, picked) == {"form[_token]": "fixture-token-0003", "form[decline]": ""}


def test_a_radio_answer_reads_the_labels_and_sends_the_value_with_the_one_submit():
    found = parsed("letter_confirm_choice_radio.html")
    assert found["choice"]["mode"] == "radio"
    assert [option["label"] for option in found["choice"]["options"]] == [
        "Mein Kind nimmt teil",
        "Mein Kind nimmt nicht teil",
    ]
    picked = picked_options(found["choice"], [option_id(found, "Mein Kind nimmt teil")])
    assert build_choice_payload(found, picked) == {
        "form[_token]": "fixture-token-0007",
        "form[answer]": "1",
        "form[submit]": "",
    }


def test_a_select_answer_skips_the_empty_placeholder_and_keeps_the_message():
    found = parsed("letter_confirm_choice_select.html")
    assert found["choice"]["mode"] == "select"
    assert [option["label"] for option in found["choice"]["options"]] == ["Montag", "Dienstag"]
    picked = picked_options(found["choice"], [option_id(found, "Dienstag")])
    assert build_choice_payload(found, picked, "Gern") == {
        "form[_token]": "fixture-token-0009",
        "form[text]": "Gern",
        "form[answer]": "b",
        "form[submit]": "",
    }


def test_checkboxes_allow_several_answers_and_leave_out_a_disabled_one():
    found = parsed("letter_confirm_choice_checkbox.html")
    assert found["choice"]["multiple"] is True
    assert [option["label"] for option in found["choice"]["options"]] == ["Kuchen", "Getraenke"]
    picked = picked_options(found["choice"], [option_id(found, "Kuchen"), option_id(found, "Getraenke")])
    assert build_choice_payload(found, picked)["form[options][]"] == ["x1", "x2"]


def test_a_single_answer_form_refuses_two_answers_and_unknown_ids():
    found = parsed("letter_confirm_choice.html")
    both = [option["id"] for option in found["choice"]["options"]]
    assert picked_options(found["choice"], both) is None
    assert picked_options(found["choice"], ["0000000000000000"]) is None
    assert picked_options(found["choice"], []) is None


def test_a_form_with_an_unknown_control_is_not_sendable():
    found = parsed("letter_confirm_choice_unknown.html")
    assert found["sendable"] is False
    assert found["choice"] is None


def test_a_form_that_posts_to_another_host_is_not_sendable():
    html = _fixture_text("letter_confirm_choice.html").replace(
        'action=""', 'action="https://elsewhere.example/iserv/parentletter/answer"'
    )
    found = parse_confirmation(html, SHOW_URL)
    assert found["sendable"] is False


def test_the_read_receipt_stays_a_plain_confirmation_without_a_choice():
    found = parsed("letter_confirm_seen.html")
    assert found["sendable"] is True
    assert found["choice"] is None


def test_an_answer_counts_as_recorded_once_the_form_shows_it_selected():
    before = parsed("letter_confirm_choice_radio.html")
    after = parsed("letter_confirm_choice_radio_answered.html")
    no = picked_options(before["choice"], [option_id(before, "Mein Kind nimmt nicht teil")])
    yes = picked_options(before["choice"], [option_id(before, "Mein Kind nimmt teil")])
    assert choice_recorded(after, no) is True
    assert choice_recorded(after, yes) is False
    assert choice_recorded(before, no) is False


def test_the_shape_names_controls_and_mode_but_no_labels_or_values():
    shape = confirmation_shape(_fixture_text("letter_confirm_choice_radio.html"), SHOW_URL)
    assert "marks=SELECTION" in shape
    assert "input:radio x2" in shape
    assert "mode=radio options=2" in shape
    assert "nimmt" not in shape
    assert "fixture-token" not in shape
    unknown = confirmation_shape(_fixture_text("letter_confirm_choice_unknown.html"), SHOW_URL)
    assert "input:file x1" in unknown
    assert "mode=unsupported" in unknown


def choice_service(tmp_path, pages, post_status=200):
    service, store = make(tmp_path)
    client = ConfirmClient("https://school.example", pages, post_status)
    service.client_factory = lambda url: client
    return service, store, client


def test_the_detail_offers_the_answers_of_an_open_choice(tmp_path):
    service, _, _ = choice_service(tmp_path, [_fixture_text("letter_confirm_choice.html")])
    confirmation = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"]
    assert confirmation["open"] is True
    assert confirmation["sendable"] is True
    assert [option["label"] for option in confirmation["choice"]["options"]] == ["Zustimmen", "Ablehnen"]


def test_an_unrecognised_form_is_open_but_not_sendable_and_its_shape_is_kept_for_the_report(tmp_path):
    service, store, _ = choice_service(tmp_path, [_fixture_text("letter_confirm_choice_unknown.html")])
    confirmation = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"]
    assert confirmation["sendable"] is False
    assert "choice" not in confirmation
    cached = store.load_letters_search_cache()[KEY]["confirmation"]
    assert "input:file x1" in cached["shape"]


def test_choosing_an_answer_sends_it_reads_the_letter_again_and_records_the_answer(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store, client = choice_service(tmp_path, [choice, _fixture_text("letter_confirm_done.html")])
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["ok"] is True
    assert result["message_key"] == "api.letters.confirm.answered"
    assert result["answer"] == ["Zustimmen"]
    assert client.posts == [(SHOW_URL, {"form[_token]": "fixture-token-0003", "form[accept]": ""})]
    record = store.load_letters_confirmations()[KEY]
    assert record["answer"] == ["Zustimmen"]
    detail = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"]
    assert detail["done"] is True
    assert detail["answer"] == ["Zustimmen"]


def test_a_radio_answer_that_the_school_shows_selected_counts_as_sent(tmp_path):
    before = _fixture_text("letter_confirm_choice_radio.html")
    service, store, _ = choice_service(tmp_path, [before, _fixture_text("letter_confirm_choice_radio_answered.html")])
    found = parse_confirmation(before, SHOW_URL)
    result = service.confirm_letter(
        CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Mein Kind nimmt nicht teil")]
    )
    assert result["ok"] is True
    assert store.load_letters_confirmations()[KEY]["answer"] == ["Mein Kind nimmt nicht teil"]


def test_a_button_answer_the_school_still_asks_for_stays_unconfirmed_and_unrecorded(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store, client = choice_service(tmp_path, [choice])
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Ablehnen")])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}
    again = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Ablehnen")])
    assert again["message_key"] == "api.letters.confirm.uncertain"
    assert len(client.posts) == 2


def test_a_choice_letter_sends_nothing_without_a_chosen_answer(tmp_path):
    service, store, client = choice_service(tmp_path, [_fixture_text("letter_confirm_choice.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert result["message_key"] == "api.letters.confirm.noChoice"
    assert client.posts == []


def test_an_answer_that_no_longer_matches_the_form_sends_nothing(tmp_path):
    service, store, client = choice_service(tmp_path, [_fixture_text("letter_confirm_choice.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=["0000000000000000"])
    assert result["message_key"] == "api.letters.confirm.changed"
    assert client.posts == []


def test_an_answer_to_a_plain_read_receipt_sends_nothing(tmp_path):
    service, store, client = choice_service(tmp_path, [_fixture_text("letter_confirm_seen.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=["0000000000000000"])
    assert result["message_key"] == "api.letters.confirm.changed"
    assert client.posts == []


def test_an_unrecognised_form_sends_nothing(tmp_path):
    service, store, client = choice_service(tmp_path, [_fixture_text("letter_confirm_choice_unknown.html")])
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=["0000000000000000"])
    assert result["message_key"] == "api.letters.confirm.unsupported"
    assert client.posts == []


class FailingPostClient(ConfirmClient):
    def __init__(self, url, pages, lands):
        super().__init__(url, pages)
        self.lands = lands

    def post_absolute(self, url, data, timeout=30, headers=None):
        self.posts.append((url, dict(data)))
        if self.lands:
            self.stage += 1
        raise RequestsConnectionError("connection reset")


@pytest.mark.parametrize("lands, ok, key", [(True, True, "api.letters.confirm.answered"), (False, False, "api.letters.confirm.uncertain")])
def test_a_lost_answer_request_is_settled_by_reading_the_letter_again(tmp_path, lands, ok, key):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store = make(tmp_path)
    client = FailingPostClient("https://school.example", [choice, _fixture_text("letter_confirm_done.html")], lands)
    service.client_factory = lambda url: client
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["ok"] is ok
    assert result["message_key"] == key
    assert (KEY in store.load_letters_confirmations()) is ok


class UnreadableAfterPostClient(ConfirmClient):
    def fetch(self, path, params=None):
        if self.posts and "/parent/show/" in path:
            raise RequestsConnectionError("school gone")
        return super().fetch(path, params)


def test_an_answer_whose_letter_cannot_be_read_again_is_uncertain_and_not_recorded(tmp_path, caplog):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store = make(tmp_path)
    client = UnreadableAfterPostClient("https://school.example", [choice])
    service.client_factory = lambda url: client
    found = parse_confirmation(choice, SHOW_URL)
    with caplog.at_level(logging.WARNING):
        result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}
    assert "the letter was not readable" in caplog.text


def test_an_answer_form_closed_after_sending_counts_as_answered(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    changed = choice.replace('confirmation-type="CONFIRMATION">Ablehnen', 'confirmation-type="CONFIRMATION" disabled>Ablehnen')
    changed = changed.replace('confirmation-type="CONFIRMATION">Zustimmen', 'confirmation-type="CONFIRMATION" disabled>Zustimmen')
    service, store, _ = choice_service(tmp_path, [choice, changed])
    found = parse_confirmation(choice, SHOW_URL)
    result = service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    assert result["ok"] is True
    assert store.load_letters_confirmations()[KEY]["answer"] == ["Zustimmen"]


def test_the_report_lists_the_shape_of_reply_forms_seen_in_opened_letters(tmp_path):
    service, store, _ = choice_service(tmp_path, [_fixture_text("letter_confirm_choice_unknown.html")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    lines = reportfacts.letter_reply_form_lines(store)
    assert lines[0].startswith("- Reply forms in opened letters: 1")
    assert any("input:file x1" in line and "signature" in line for line in lines)
    assert "Unterschrift" not in "\n".join(lines)


def test_the_report_says_when_no_opened_letter_had_a_reply_form(tmp_path):
    _, store = make(tmp_path)
    assert reportfacts.letter_reply_form_lines(store) == ["- Reply forms in opened letters: none"]


EDIT_PATH = f"/iserv/parentletter/parent/answer/{CONFIRM_LETTER}/{CONFIRM_RECIPIENT}/edit"


class EditClient(ConfirmClient):
    def __init__(self, url, letter_page, edit_pages, post_status=200, post_text=""):
        super().__init__(url, [letter_page], post_status, post_text)
        self.edit_pages = list(edit_pages)
        self.edit_reads = 0

    def fetch_or_raise(self, path, params=None):
        if EDIT_PATH in path:
            self.edit_reads += 1
            response = type("R", (), {})()
            response.status_code = 200
            response.url = "https://school.example" + EDIT_PATH
            response.text = self.edit_pages[min(self.stage, len(self.edit_pages) - 1)]
            return response
        return super().fetch_or_raise(path, params)


def edit_service(tmp_path, letter="letter_confirm_answered_editable.html", edits=("letter_answer_edit_radio.html",)):
    service, store = make(tmp_path)
    client = EditClient("https://school.example", _fixture_text(letter), [_fixture_text(name) for name in edits])
    service.client_factory = lambda url: client
    return service, store, client


def test_an_answered_letter_with_an_edit_link_offers_to_change_the_answer(tmp_path):
    service, _, client = edit_service(tmp_path)
    confirmation = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"]
    assert confirmation["done"] is True
    assert confirmation["editable"] is True
    assert confirmation["type"] == "answered"
    assert client.edit_reads == 0


def test_an_answered_letter_without_an_edit_link_is_not_editable(tmp_path):
    service, _, _ = edit_service(tmp_path, letter="letter_confirm_done.html")
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["confirmation"] is None


def test_the_answer_form_shows_the_given_answer_and_text(tmp_path):
    service, _, client = edit_service(tmp_path)
    form = service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert form["ok"] is True
    assert form["can_reply"] is True
    assert form["text"] == "Wir bringen Kuchen mit."
    assert [(option["label"], option["selected"]) for option in form["choice"]["options"]] == [
        ("Mein Kind nimmt teil", True),
        ("Mein Kind nimmt nicht teil", False),
    ]
    assert client.posts == []


def test_changing_the_answer_sends_the_edit_form_and_reads_the_new_answer_back(tmp_path):
    service, store, client = edit_service(
        tmp_path, edits=("letter_answer_edit_radio.html", "letter_answer_edit_radio_changed.html")
    )
    form = service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    second = form["choice"]["options"][1]["id"]
    result = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, "Leider krank.", [second])
    assert result["ok"] is True
    assert result["message_key"] == "api.letters.edit.ok"
    assert result["answer"] == ["Mein Kind nimmt nicht teil"]
    url, payload = client.posts[0]
    assert url == "https://school.example" + EDIT_PATH
    assert payload == {
        "answer[text]": "Leider krank.",
        "answer[_token]": "fixture-token-0012",
        "answer[choice]": "2",
        "answer[submit]": "",
    }
    assert store.load_letters_confirmations()[KEY]["answer"] == ["Mein Kind nimmt nicht teil"]


def test_a_changed_answer_the_school_does_not_show_is_uncertain_and_not_recorded(tmp_path):
    service, store, client = edit_service(tmp_path, edits=("letter_answer_edit_radio.html",))
    form = service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    second = form["choice"]["options"][1]["id"]
    result = service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, None, [second])
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.confirm.uncertain"
    assert store.load_letters_confirmations() == {}


def test_changing_the_answer_without_an_edit_link_sends_nothing(tmp_path):
    service, _, client = edit_service(tmp_path, letter="letter_confirm_done.html")
    assert service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)["message_key"] == "api.letters.edit.unavailable"
    assert service.edit_answer(CONFIRM_LETTER, CONFIRM_RECIPIENT, None, ["x"])["message_key"] == "api.letters.edit.unavailable"
    assert client.posts == []


def test_an_unknown_edit_form_sends_nothing_and_its_shape_reaches_the_report(tmp_path):
    service, store, client = edit_service(tmp_path, edits=("letter_answer_edit_unknown.html",))
    assert service.answer_form(CONFIRM_LETTER, CONFIRM_RECIPIENT)["message_key"] == "api.letters.confirm.unsupported"
    assert client.posts == []
    lines = reportfacts.letter_reply_form_lines(store)
    assert any("answer edit" in line and "input:date x1" in line for line in lines)


def test_an_answer_sent_in_the_app_records_how_the_answered_letter_looks(tmp_path):
    choice = _fixture_text("letter_confirm_choice.html")
    service, store, _ = choice_service(tmp_path, [choice, _fixture_text("letter_confirm_done.html")])
    found = parse_confirmation(choice, SHOW_URL)
    service.confirm_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, choices=[option_id(found, "Zustimmen")])
    service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    shape = store.load_letters_search_cache()[KEY]["answer_shape"]
    assert shape.startswith("answered page;")
    assert "/iserv/parentletter/parent/index" in shape
    assert "Alex" not in shape
