import logging

import pytest
import requests

from app.iserv.letters import (
    REPLY_ABSENT,
    REPLY_PRESENT,
    REPLY_UNKNOWN,
    build_reply_payload,
    parse_reply_form,
)
from app.letter_service import LETTER_UNKNOWN_KEY
from tests.test_letters import (
    ARCHIVE_PATH,
    EMPTY_LIST,
    FOREIGN_LETTER,
    FOREIGN_RECIPIENT,
    INDEX_PATH,
    archive_page,
    assert_untouched,
    later,
    letter_school,
    listed_page,
    two_letter_schools,
)
from tests.test_service import (
    CONFIRM_LETTER,
    CONFIRM_RECIPIENT,
    _confirm_service,
    _fixture_text,
)

SHOW_URL = f"https://school.example/iserv/parentletter/parent/show/{CONFIRM_LETTER}/{CONFIRM_RECIPIENT}"
REQUEST_ID = "0123456789abcdef0123456789abcdef"
OTHER_REQUEST_ID = "fedcba9876543210fedcba9876543210"
TOKEN = "fixture-token-0006"
REPLY_TEXT = "Wir kommen gern <3"
SUBMIT_TAG = '<button type="submit" id="reply_submit" name="reply[submit]" class="btn btn-primary">'


def reply_page():
    return _fixture_text("letter_reply_form.html")


def changed(old, new):
    html = reply_page()
    assert html.count(old) == 1
    return html.replace(old, new, 1)


def test_the_modelled_reply_form_is_recognised_with_the_editor_fields():
    found = parse_reply_form(reply_page(), SHOW_URL)
    assert found["state"] == REPLY_PRESENT
    form = found["form"]
    assert form["action"] == SHOW_URL
    assert form["editor"] == "reply[text]"
    assert form["fields"] == {
        "reply[_token]": TOKEN,
        "reply[text][html]": "<p></p>",
        "reply[text][plain]": "",
        "reply[text][mode]": "rich",
    }
    assert form["submits"] == {"reply[submit]": ""}


def test_the_reply_payload_carries_the_text_in_both_editor_fields_and_the_one_submit():
    form = parse_reply_form(reply_page(), SHOW_URL)["form"]
    assert build_reply_payload(form, "Danke\nbis bald <3") == {
        "reply[_token]": TOKEN,
        "reply[text][html]": "<p>Danke</p><p>bis bald &lt;3</p>",
        "reply[text][plain]": "Danke\nbis bald <3",
        "reply[text][mode]": "rich",
        "reply[submit]": "",
    }


@pytest.mark.parametrize("name", ["letter_confirm_done.html", "letter_detail.html", "letter_confirm_none.html"])
def test_a_page_without_any_message_field_has_no_reply_form(fixture, name):
    found = parse_reply_form(fixture(name), SHOW_URL)
    assert found["state"] == REPLY_ABSENT
    assert found["form"] is None


def test_the_confirmation_form_with_its_editor_is_never_taken_for_a_reply_form(fixture):
    found = parse_reply_form(fixture("letter_confirm_seen_editor.html"), SHOW_URL)
    assert found["state"] == REPLY_UNKNOWN
    assert found["form"] is None
    assert found["outline"]["marked"] == 1


UNKNOWN_SHAPES = {
    "second submit": (SUBMIT_TAG, '<button type="submit" name="reply[cancel]">x</button>' + SUBMIT_TAG),
    "unnamed submit": (' name="reply[submit]"', ""),
    "disabled submit": (SUBMIT_TAG, SUBMIT_TAG[:-1] + " disabled>"),
    "missing token": (' name="reply[_token]"', ' name="reply[other]"'),
    "visible input": (SUBMIT_TAG, '<input type="text" name="reply[subject]" value="">' + SUBMIT_TAG),
    "checkbox": (SUBMIT_TAG, '<input type="checkbox" name="reply[seen]" value="1">' + SUBMIT_TAG),
    "extra textarea": (SUBMIT_TAG, '<textarea name="reply[note]"></textarea>' + SUBMIT_TAG),
    "select": (SUBMIT_TAG, '<select name="reply[to]"><option>a</option></select>' + SUBMIT_TAG),
    "get method": ('method="post"', 'method="get"'),
    "multipart": ('method="post"', 'method="post" enctype="multipart/form-data"'),
    "foreign action": ('action=""', 'action="https://elsewhere.example/collect"'),
    "foreign button target": (SUBMIT_TAG, SUBMIT_TAG[:-1] + ' formaction="https://elsewhere.example/x">'),
    "confirmation marker": (SUBMIT_TAG, SUBMIT_TAG[:-1] + ' confirmation-type="NONE">'),
    "editor outside the form names": ('name="reply[text]"', 'name="text"'),
    "second editor": ("</iserv-editor>", '</iserv-editor><iserv-editor name="reply[more]"></iserv-editor>'),
    "unknown form element": ("</iserv-editor>", '</iserv-editor><iserv-picker name="reply[kind]"></iserv-picker>'),
    "read-only editor": ("<iserv-editor ", "<iserv-editor readonly "),
    "nameless form": ('<form name="reply"', "<form"),
}


@pytest.mark.parametrize("shape", sorted(UNKNOWN_SHAPES))
def test_any_other_shape_is_unknown_and_never_offered(shape):
    old, new = UNKNOWN_SHAPES[shape]
    found = parse_reply_form(changed(old, new), SHOW_URL)
    assert found["state"] == REPLY_UNKNOWN
    assert found["form"] is None


def test_two_forms_with_a_message_field_are_unknown():
    html = reply_page()
    start = html.index('<form name="reply"')
    end = html.index("</form>") + len("</form>")
    doubled = html[:end] + html[start:end] + html[end:]
    assert parse_reply_form(doubled, SHOW_URL)["state"] == REPLY_UNKNOWN


def test_a_textarea_form_is_unknown_instead_of_guessed(fixture):
    assert parse_reply_form(fixture("letter_confirm_seen_text.html").replace('confirmation-type="SEEN"', ""), SHOW_URL)[
        "state"
    ] == REPLY_UNKNOWN


def test_a_reply_link_without_a_form_is_unknown(fixture):
    html = fixture("letter_confirm_done.html").replace(
        '<a class="btn btn-default" href="/iserv/parentletter/parent/index">Zurueck</a>\n</div>\n</div>',
        '<a class="btn btn-default" href="/iserv/parentletter/parent/reply/1/2">Antworten</a>\n</div>\n</div>',
        1,
    )
    found = parse_reply_form(html, SHOW_URL)
    assert found["state"] == REPLY_UNKNOWN
    assert found["outline"]["hints"] == 1


def test_a_reply_link_inside_the_letter_text_is_not_a_hint(fixture):
    html = fixture("letter_confirm_done.html").replace(
        "<p>Liebe Eltern,</p>", '<p>Liebe Eltern, <a href="https://forms.example/answer/1">Umfrage</a></p>', 1
    )
    assert parse_reply_form(html, SHOW_URL)["state"] == REPLY_ABSENT


def _reply_service(tmp_path, pages=None, **kwargs):
    return _confirm_service(tmp_path, pages or [reply_page()], **kwargs)


def _reply(service, text=REPLY_TEXT, request_id=REQUEST_ID, confirmed=True):
    return service.reply_to_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, text, request_id, confirmed)


def test_the_detail_of_a_confirmed_letter_offers_the_recognised_reply_form(tmp_path):
    service, _, client = _reply_service(tmp_path)
    detail = service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)
    assert detail["reply"] == {"available": True}
    assert detail["confirmation"] is None
    assert client.posts == []


def test_a_letter_with_an_open_confirmation_offers_no_separate_reply(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    service, _, _ = _reply_service(tmp_path, [_fixture_text("letter_confirm_seen_editor.html")])
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["reply"] is None
    assert "letter reply form" not in caplog.text


PAGES_WITHOUT_OFFER = {
    "absent": (logging.INFO, lambda: _fixture_text("letter_confirm_done.html")),
    "unknown": (logging.WARNING, lambda: changed(SUBMIT_TAG, SUBMIT_TAG + '<button type="submit" name="reply[cancel]">x</button>')),
}


@pytest.mark.parametrize("state", sorted(PAGES_WITHOUT_OFFER))
def test_a_missing_or_unknown_form_offers_nothing_and_logs_one_line_without_values(tmp_path, caplog, state):
    caplog.set_level(logging.INFO)
    level, build = PAGES_WITHOUT_OFFER[state]
    service, _, _ = _reply_service(tmp_path, [build()])
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["reply"] is None
    assert service.letter_detail(CONFIRM_LETTER, CONFIRM_RECIPIENT)["reply"] is None
    lines = [record for record in caplog.records if record.getMessage().startswith("letter reply form")]
    assert len(lines) == 1
    assert lines[0].levelno == level
    assert lines[0].getMessage().startswith(f"letter reply form {state}:")
    for value in (TOKEN, CONFIRM_LETTER, CONFIRM_RECIPIENT, "Liebe Eltern", "school.example"):
        assert value not in caplog.text


def test_the_letter_list_neither_inspects_nor_logs_the_reply_form(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    service, _, _ = _reply_service(tmp_path, [_fixture_text("letter_confirm_done.html")])
    service.letters("current")
    assert "letter reply form" not in caplog.text


def test_a_confirmed_reply_is_sent_once_with_the_editor_fields(tmp_path):
    service, _, client = _reply_service(tmp_path)
    result = _reply(service)
    assert result["ok"] is True
    assert result["message_key"] == "api.letters.reply.ok"
    assert len(client.posts) == 1
    url, payload = client.posts[0]
    assert url == SHOW_URL
    assert payload == {
        "reply[_token]": TOKEN,
        "reply[text][html]": "<p>Wir kommen gern &lt;3</p>",
        "reply[text][plain]": REPLY_TEXT,
        "reply[text][mode]": "rich",
        "reply[submit]": "",
    }
    assert client.post_headers[0]["Origin"] == "https://school.example"


def test_a_retry_with_the_same_request_is_answered_without_a_second_send(tmp_path):
    service, _, client = _reply_service(tmp_path)
    assert _reply(service)["ok"] is True
    again = _reply(service)
    assert again["ok"] is True
    assert again["message_key"] == "api.letters.reply.alreadySent"
    assert len(client.posts) == 1


def test_a_new_message_is_a_new_request_and_is_sent(tmp_path):
    service, _, client = _reply_service(tmp_path)
    assert _reply(service)["ok"] is True
    assert _reply(service, request_id=OTHER_REQUEST_ID)["ok"] is True
    assert len(client.posts) == 2


def test_a_reply_that_is_still_being_sent_is_not_sent_twice(tmp_path):
    service, _, client = _reply_service(tmp_path)
    service._letters()._replying.add(f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}")
    result = _reply(service, request_id=OTHER_REQUEST_ID)
    assert result["message_key"] == "api.letters.reply.busy"
    assert client.posts == []


@pytest.mark.parametrize("confirmed", [False, None, "true", 1])
def test_without_the_explicit_confirmation_nothing_is_fetched_or_sent(tmp_path, confirmed):
    service, _, client = _reply_service(tmp_path)
    fetched = []
    client.fetch = lambda path, params=None: fetched.append(path)
    result = _reply(service, confirmed=confirmed)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.unconfirmed"
    assert fetched == []
    assert client.posts == []


@pytest.mark.parametrize(
    "text, request_id, key",
    [
        ("   ", REQUEST_ID, "api.letters.reply.empty"),
        (None, REQUEST_ID, "api.letters.reply.empty"),
        (REPLY_TEXT, "", "api.letters.reply.invalid"),
        (REPLY_TEXT, "short", "api.letters.reply.invalid"),
        (REPLY_TEXT, "0123456789abcdef/0123456789abcdef", "api.letters.reply.invalid"),
        (REPLY_TEXT, None, "api.letters.reply.invalid"),
    ],
)
def test_an_empty_text_or_a_bad_request_id_is_refused_before_sending(tmp_path, text, request_id, key):
    service, _, client = _reply_service(tmp_path)
    result = _reply(service, text=text, request_id=request_id)
    assert result["message_key"] == key
    assert client.posts == []


@pytest.mark.parametrize(
    "html",
    [
        _fixture_text("letter_confirm_done.html"),
        _fixture_text("letter_confirm_seen_editor.html"),
        _fixture_text("letter_reply_form.html").replace('method="post"', 'method="get"', 1),
    ],
)
def test_a_letter_whose_form_is_missing_or_unknown_sends_nothing(tmp_path, html):
    service, _, client = _reply_service(tmp_path, [html])
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.unavailable"
    assert client.posts == []


def test_a_client_error_on_the_post_is_a_refusal_that_names_the_status_and_allows_a_retry(tmp_path):
    service, _, client = _reply_service(tmp_path, post_status=400)
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.upstream"
    assert result["message_vars"] == {"status": 400}
    assert result["diagnosis"]["post_status"] == 400
    client.post_status = 200
    assert _reply(service)["ok"] is True
    assert len(client.posts) == 2


def test_a_form_error_in_the_answer_is_a_refusal_not_a_success(tmp_path):
    answer = changed("</iserv-editor>", '</iserv-editor><div class="invalid-feedback">Der Text fehlt.</div>')
    service, _, client = _reply_service(tmp_path, post_text=answer)
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.rejected"
    assert result["diagnosis"]["response_notices"] == ["Der Text fehlt."]
    assert len(client.posts) == 1


def test_a_login_page_as_the_answer_is_a_refusal_not_a_success(tmp_path):
    login = (
        '<form method="post" action="/iserv/auth/login"><input name="_username">'
        '<input type="password" name="_password"><button type="submit">Anmelden</button></form>'
    )
    service, _, _ = _reply_service(tmp_path, post_text=login)
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.rejected"


def test_a_lost_connection_while_sending_is_uncertain_and_never_sent_again(tmp_path):
    service, _, client = _reply_service(tmp_path)
    attempts = []

    def broken(url, data, timeout=30, headers=None):
        attempts.append(url)
        raise requests.ConnectionError("reset")

    client.post_absolute = broken
    first = _reply(service)
    assert first["ok"] is False
    assert first["message_key"] == "api.letters.reply.uncertain"
    again = _reply(service)
    assert again["message_key"] == "api.letters.reply.uncertain"
    assert len(attempts) == 1


def test_a_refusal_before_the_request_left_keeps_the_retry_open(tmp_path):
    from app.iserv.errors import DataError

    service, _, client = _reply_service(tmp_path)
    sending = client.post_absolute
    calls = []

    def blocked_once(url, data, timeout=30, headers=None):
        calls.append(url)
        if len(calls) == 1:
            raise DataError("cross-origin request blocked")
        return sending(url, data, timeout=timeout, headers=headers)

    client.post_absolute = blocked_once
    with pytest.raises(DataError):
        _reply(service)
    assert _reply(service)["ok"] is True
    assert len(client.posts) == 1


def test_sending_a_reply_logs_no_text_token_or_identifier(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    service, _, _ = _reply_service(tmp_path, post_status=400)
    _reply(service)
    service2, _, _ = _reply_service(tmp_path / "second")
    _reply(service2)
    assert "letter reply" in caplog.text
    for value in (REPLY_TEXT, "Wir kommen", TOKEN, REQUEST_ID, CONFIRM_LETTER, CONFIRM_RECIPIENT):
        assert value not in caplog.text


def _answering(client, status=200, text="", history=0):
    def post(url, data, timeout=30, headers=None):
        client.posts.append((url, dict(data)))
        client.post_headers.append(dict(headers or {}))
        return type("Answer", (), {"status_code": status, "url": url, "text": text, "history": [object()] * history})()

    client.post_absolute = post


ALERT_ANSWER = '<div class="alert alert-danger">Die Nachricht konnte nicht gespeichert werden.</div>'


def test_an_alert_danger_answer_is_a_refusal_and_never_counted_as_sent(tmp_path):
    service, _, client = _reply_service(tmp_path)
    _answering(client, text=ALERT_ANSWER)
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.rejected"
    assert result["diagnosis"]["response_notices"] == ["Die Nachricht konnte nicht gespeichert werden."]
    _answering(client)
    assert _reply(service)["message_key"] == "api.letters.reply.ok"
    assert len(client.posts) == 2


def test_an_empty_error_placeholder_does_not_count_as_an_error(tmp_path):
    service, _, client = _reply_service(tmp_path)
    _answering(client, text='<div class="invalid-feedback"></div><p>Gespeichert</p>')
    assert _reply(service)["message_key"] == "api.letters.reply.ok"


def test_the_form_shown_again_without_a_redirect_is_uncertain_never_sent(tmp_path):
    service, _, client = _reply_service(tmp_path)
    _answering(client, text=reply_page())
    result = _reply(service)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.uncertain"
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    assert len(client.posts) == 1


@pytest.mark.parametrize(
    "status, text, history",
    [(500, "", 0), (502, "", 0), (500, "", 1), (200, ALERT_ANSWER, 1), (404, "", 1)],
)
def test_a_server_error_or_a_redirect_that_ends_badly_is_uncertain_and_not_retried(tmp_path, status, text, history):
    service, _, client = _reply_service(tmp_path)
    _answering(client, status=status, text=text, history=history)
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    _answering(client)
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    assert len(client.posts) == 1


def test_a_redirect_to_a_calm_page_is_sent(tmp_path):
    service, _, client = _reply_service(tmp_path)
    _answering(client, text=_fixture_text("letter_confirm_done.html"), history=1)
    assert _reply(service)["message_key"] == "api.letters.reply.ok"


def test_a_failure_after_the_request_left_is_uncertain_not_a_generic_failure(tmp_path, monkeypatch):
    from app import letter_service

    def broken(html):
        raise ValueError("unexpected answer")

    monkeypatch.setattr(letter_service, "reply_form_errors", broken)
    service, _, client = _reply_service(tmp_path)
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    monkeypatch.undo()
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    assert len(client.posts) == 1


def test_a_sent_reply_survives_a_restart_of_the_add_on(tmp_path):
    from app.letter_service import LetterService

    service, _, client = _reply_service(tmp_path)
    assert _reply(service)["ok"] is True
    service._letter_service = LetterService(service)
    again = _reply(service)
    assert again["ok"] is True
    assert again["message_key"] == "api.letters.reply.alreadySent"
    assert len(client.posts) == 1


def test_an_uncertain_reply_survives_a_restart_of_the_add_on(tmp_path):
    from app.letter_service import LetterService

    service, _, client = _reply_service(tmp_path, post_status=500)
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    service._letter_service = LetterService(service)
    client.post_status = 200
    assert _reply(service)["message_key"] == "api.letters.reply.uncertain"
    assert len(client.posts) == 1


def test_a_sent_reply_survives_a_new_login(tmp_path):
    from app.service import IServService
    from app.store import LOGIN_REVISION_KEY

    service, store, client = _reply_service(tmp_path)
    base = store.base
    connection_id = store.id
    schools = IServService(base, client_factory=lambda url: client)
    before = schools.connection(connection_id)
    assert before.reply_to_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, REPLY_TEXT, REQUEST_ID, True)["ok"] is True
    base.update_connection(connection_id, **{LOGIN_REVISION_KEY: 7})
    after = schools.connection(connection_id)
    assert after is not before
    again = after.reply_to_letter(CONFIRM_LETTER, CONFIRM_RECIPIENT, REPLY_TEXT, REQUEST_ID, True)
    assert again["message_key"] == "api.letters.reply.alreadySent"
    assert len(client.posts) == 1


def test_the_stored_outcomes_are_kept_per_school_and_bounded_in_age_and_size(tmp_path):
    from datetime import datetime, timedelta

    from app import letter_service
    from app.store import edit_slot

    service, store, _ = _reply_service(tmp_path)
    old = (datetime.now() - timedelta(days=letter_service.REPLY_KEEP_DAYS + 1)).replace(microsecond=0).isoformat()
    fresh = datetime.now().replace(microsecond=0).isoformat()

    def seed(slot):
        slot["old-request-000000"] = {"letter": "a:b", "state": "sent", "at": old}
        for index in range(letter_service.REPLY_KEEP_COUNT + 5):
            slot[f"seed-request-{index:06d}"] = {"letter": "a:b", "state": "sent", "at": fresh}

    edit_slot(store, "letters_replies", seed)
    assert _reply(service)["ok"] is True
    kept = store.load_letters_replies()
    assert len(kept) == letter_service.REPLY_KEEP_COUNT
    assert "old-request-000000" not in kept
    assert kept[REQUEST_ID]["state"] == "sent"
    assert kept[REQUEST_ID]["letter"] == f"{CONFIRM_LETTER}:{CONFIRM_RECIPIENT}"
    assert REPLY_TEXT not in str(kept)
    assert store.base.load_letters_replies() == {store.id: kept}


def test_the_same_request_id_for_another_letter_is_an_invalid_request(tmp_path):
    other_letter = "30000000-0000-4000-8000-000000000003"
    service, _, client = _reply_service(tmp_path)
    assert _reply(service)["ok"] is True
    result = service.reply_to_letter(other_letter, CONFIRM_RECIPIENT, REPLY_TEXT, REQUEST_ID, True)
    assert result["ok"] is False
    assert result["message_key"] == "api.letters.reply.invalid"
    assert len(client.posts) == 1


@pytest.mark.parametrize(
    "action",
    [
        "/iserv/mail/compose",
        "/iserv/parentletterx/show",
        "/iserv/",
        "https://school.example/other/parentletter/x",
        "/iserv/parentletter/%2e%2e/mail/compose",
        "/iserv/parentletter/%2E%2E/mail/compose",
        "/iserv/parentletter/..%2fmail/compose",
        "/iserv/parentletter/../mail/compose",
    ],
)
def test_a_send_target_outside_the_letter_module_is_never_recognised(action):
    html = changed('action=""', f'action="{action}"')
    assert parse_reply_form(html, SHOW_URL)["state"] == REPLY_UNKNOWN


def test_a_send_target_inside_the_letter_module_on_the_same_host_is_recognised():
    html = changed('action=""', 'action="/iserv/parentletter/parent/reply/1/2"')
    found = parse_reply_form(html, SHOW_URL)
    assert found["state"] == REPLY_PRESENT
    assert found["form"]["action"] == "https://school.example/iserv/parentletter/parent/reply/1/2"


def test_the_diagnostic_memory_stays_bounded(tmp_path):
    from app import letter_service

    service, _, _ = _reply_service(tmp_path, [_fixture_text("letter_confirm_done.html")])
    letters = service._letters()
    for index in range(letter_service.REPLY_LOGGED_LIMIT + 10):
        letters._reply_offer(f"key-{index}", type("Page", (), {"text": "", "url": SHOW_URL})())
    assert len(letters._reply_logged) == letter_service.REPLY_LOGGED_LIMIT


def _listed_reply_school(tmp_path, **kwargs):
    return letter_school(tmp_path, pages=[reply_page()], **kwargs)


def test_a_reply_to_a_letter_of_no_list_is_refused_without_contacting_the_letter(tmp_path):
    service, client = _listed_reply_school(tmp_path)
    result = service.reply_to_letter(FOREIGN_LETTER, FOREIGN_RECIPIENT, REPLY_TEXT, REQUEST_ID, True)
    assert result["ok"] is False
    assert result["message_key"] == LETTER_UNKNOWN_KEY
    assert_untouched(client)
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 1
    assert service.store.load_letters_replies() == {}


def test_a_reply_to_a_listed_letter_needs_no_new_list(tmp_path):
    service, client = _listed_reply_school(tmp_path)
    service.letters("current")
    assert _reply(service)["ok"] is True
    assert client.reads(INDEX_PATH) == 1
    assert client.reads(ARCHIVE_PATH) == 0
    assert len(client.posts) == 1


def test_a_reply_to_a_letter_that_is_only_in_the_archive_works(tmp_path):
    service, client = _listed_reply_school(tmp_path, current=EMPTY_LIST, archive=archive_page())
    assert _reply(service)["ok"] is True
    assert len(client.posts) == 1


def test_an_unknown_letter_reads_the_list_once_and_then_takes_the_reply(tmp_path):
    service, client = _listed_reply_school(tmp_path, current=EMPTY_LIST)
    service.letters("current")
    client.lists[INDEX_PATH] = listed_page()
    later(service)
    assert _reply(service)["ok"] is True
    assert client.reads(INDEX_PATH) == 2
    assert client.reads(ARCHIVE_PATH) == 0
    assert len(client.posts) == 1


def test_a_reply_to_a_letter_of_another_school_is_refused(tmp_path):
    service, two, clients = two_letter_schools(tmp_path)
    service.letters()
    service.letters("archive")
    result = service.reply_to_letter(two, CONFIRM_LETTER, CONFIRM_RECIPIENT, REPLY_TEXT, REQUEST_ID, True)
    assert result["message_key"] == LETTER_UNKNOWN_KEY
    for client in clients.values():
        assert_untouched(client)
