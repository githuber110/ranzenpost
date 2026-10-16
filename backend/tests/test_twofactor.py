from pathlib import Path

from app.iserv.twofactor import (
    build_confirm_payload,
    build_password_payload,
    parse_delete_token,
    parse_password_form,
    parse_registration,
    parse_token_list,
    parse_token_rows,
    password_changed,
    registration_rejected,
)

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://school.example"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_registration_extracts_secret_token_and_action():
    page = "https://school.example/iserv/auth/settings/twofactor/add"
    reg = parse_registration(read("security_2fa_add.html"), page)
    assert reg is not None
    assert reg.secret == "JBSWY3DPEHPK3PXP"
    assert reg.token == "csrf-confirm-token"
    assert reg.action == "https://school.example/iserv/auth/settings/twofactor/add/confirm"


def test_parse_registration_returns_none_without_secret():
    assert parse_registration("<html><body>no secret here</body></html>", BASE) is None


def test_build_confirm_payload_keeps_honeypot_empty():
    reg = parse_registration(read("security_2fa_add.html"), BASE)
    payload = build_confirm_payload(reg, "Home Assistant", "111222", "333444")
    assert payload["confirm[name]"] == "Home Assistant"
    assert payload["confirm[verification]"] == "111222"
    assert payload["confirm[code]"] == "333444"
    assert payload["confirm[_fake_username]"] == ""
    assert payload["confirm[_token]"] == "csrf-confirm-token"


def test_registration_rejected_detects_invalid_code():
    assert registration_rejected(read("security_2fa_rejected.html")) is True
    assert registration_rejected(read("security_2fa_added.html")) is False


def test_parse_password_form_and_payload():
    form = parse_password_form(read("security_password.html"), BASE)
    assert form is not None
    payload = build_password_payload(form, "old-pass", "new-pass")
    assert payload["password_change[current]"] == "old-pass"
    assert payload["password_change[new][first]"] == "new-pass"
    assert payload["password_change[new][second]"] == "new-pass"
    assert payload["password_change[_token]"] == "csrf-password-token"


def test_password_changed_success_and_failure():
    assert password_changed(read("security_password_ok.html")) is True
    assert password_changed(read("security_password_bad.html")) is False


ADD_URL = "https://school.example/iserv/auth/settings/twofactor/add"


def test_registration_form_uses_the_htmx_target_not_the_empty_action():
    reg = parse_registration(read("security_2fa_add.html"), ADD_URL)
    assert reg is not None
    assert reg.action == "https://school.example/iserv/auth/settings/twofactor/add/confirm"


def test_security_page_alone_has_no_registration_form():
    assert parse_registration(read("security_password.html"), "https://school.example/iserv/account/settings/security") is None


def test_confirm_payload_includes_the_named_submit_button():
    reg = parse_registration(read("security_2fa_add.html"), ADD_URL)
    payload = build_confirm_payload(reg, "Home Assistant", "111222", "333444")
    assert payload["confirm[actions][submit]"] == ""
    assert "confirm[actions][submit]" in reg.submits


def test_unnamed_buttons_are_not_submitted():
    reg = parse_registration(read("security_2fa_add.html"), ADD_URL)
    assert list(reg.submits) == ["confirm[actions][submit]"]


def test_parse_token_rows_extracts_name_and_uuid_from_the_row_id():
    rows = parse_token_rows(read("twofactor_list_uuid.html"))
    assert rows == [{"name": "ISERV-Connector", "uuid": "b2b6b8b0-1111-4a2a-9c3c-abcdef123456"}]


def test_parse_token_rows_ignores_rows_without_a_client_row_id():
    rows = parse_token_rows(read("twofactor_list.html"))
    assert rows == []


def test_parse_delete_token_reads_the_shared_csrf_token():
    assert parse_delete_token(read("twofactor_list_uuid.html")) == "csrf-delete-token"


def test_parse_delete_token_returns_none_without_the_form():
    assert parse_delete_token(read("twofactor_list.html")) is None


DATED_LIST = """
<table>
  <thead><tr><th>Bezeichnung</th><th>Erstellt am</th><th>Aktionen</th></tr></thead>
  <tbody>
    <tr id="client-twofactor-row-b2b6b8b0-1111-4a2a-9c3c-abcdef123456"><td>ISERV-Connector</td><td>1.9.2026 08:15</td><td></td></tr>
    <tr id="client-twofactor-row-c3c3c3c3-2222-4b2b-8d3d-abcdef654321"><td>ISERV-Connector</td><td><time datetime="2026-10-02T07:00:00">gestern</time></td><td></td></tr>
    <tr id="client-twofactor-row-../../logout"><td>ISERV-Connector</td><td>31.02.2026</td><td></td></tr>
    <tr><td>Authenticator</td><td>unbekannt</td><td></td></tr>
  </tbody>
</table>
"""


def test_the_token_list_keeps_every_entry_with_a_checked_id_and_a_created_date():
    assert parse_token_list(DATED_LIST) == [
        {"name": "ISERV-Connector", "uuid": "b2b6b8b0-1111-4a2a-9c3c-abcdef123456", "created": "2026-09-01"},
        {"name": "ISERV-Connector", "uuid": "c3c3c3c3-2222-4b2b-8d3d-abcdef654321", "created": "2026-10-02"},
        {"name": "ISERV-Connector", "uuid": "", "created": ""},
        {"name": "Authenticator", "uuid": "", "created": ""},
    ]


def test_the_token_list_has_no_created_date_when_iserv_shows_none():
    rows = parse_token_list(read("twofactor_list_uuid.html"))
    assert rows == [
        {"name": "parent@school.example", "uuid": "", "created": ""},
        {"name": "ISERV-Connector", "uuid": "b2b6b8b0-1111-4a2a-9c3c-abcdef123456", "created": ""},
    ]
