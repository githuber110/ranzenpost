import pytest

from app.iserv.auth import apply_login_fields, fill_two_factor_code
from app.iserv.forms import parse_forms

BASE = "https://school.example/iserv/auth/twofactor/confirm"


def test_fill_two_factor_sets_otp_and_digits(fixture):
    form = parse_forms(fixture("twofactor_page.html"), BASE)[0]
    filled = fill_two_factor_code(form.fields, "451884")
    assert filled["otp"] == "451884"
    digits = [filled[f"two_factor_login_form[two_factor_code_digit_{i}]"] for i in range(1, 7)]
    assert digits == ["4", "5", "1", "8", "8", "4"]


def test_fill_two_factor_keeps_csrf_token(fixture):
    form = parse_forms(fixture("twofactor_page.html"), BASE)[0]
    filled = fill_two_factor_code(form.fields, "123456")
    assert filled["_csrf_token"] == "csrf-token-example"
    assert filled["two_factor_login_form[two_factor_code_digit_3]"] == "3"


def test_fill_two_factor_raises_without_fields():
    with pytest.raises(ValueError):
        fill_two_factor_code({"other": ""}, "123456")


def test_apply_login_fields_sets_remember_me(fixture):
    form = parse_forms(fixture("login_page.html"), BASE)[0]
    payload = apply_login_fields(form.fields, "parent", "secret")
    assert payload["_username"] == "parent"
    assert payload["_password"] == "secret"
    assert payload["_remember_me"] == "on"
