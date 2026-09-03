from app.iserv.forms import (
    find_client_redirect,
    find_login_form,
    find_two_factor_form,
    parse_forms,
)

BASE = "https://school.example/iserv/auth/login?step1"


def test_find_login_form_prefers_password_form(fixture):
    forms = parse_forms(fixture("login_page.html"), BASE)
    login = find_login_form(forms)
    assert login is not None
    assert "_username" in login.fields
    assert "_password" in login.fields
    assert login.action.startswith("https://school.example/iserv/auth/login")


def test_module_filter_form_is_not_login(fixture):
    forms = parse_forms(fixture("login_page.html"), BASE)
    login = find_login_form(forms)
    assert "filter" not in login.fields


def test_find_two_factor_form(fixture):
    forms = parse_forms(fixture("twofactor_page.html"), BASE)
    form = find_two_factor_form(forms)
    assert form is not None
    assert "otp" in form.fields
    assert "_csrf_token" in form.fields


def test_find_client_redirect_reads_meta_refresh(fixture):
    target = find_client_redirect(fixture("auth_continue.html"), BASE)
    assert target == "https://school.example/iserv/app/authentication/redirect?code=example-code"


def test_find_client_redirect_returns_none_without_redirect(fixture):
    assert find_client_redirect(fixture("portal.html"), BASE) is None


def test_affirmative_submit_skips_cancel_and_delete():
    from app.iserv.forms import affirmative_submit

    assert affirmative_submit({"f[actions][cancle]": "", "f[actions][submit]": ""}) == {"f[actions][submit]": ""}
    assert affirmative_submit({"f[delete]": "", "f[save]": ""}) == {"f[save]": ""}
    assert affirmative_submit({"f[cancel]": ""}) == {}
    assert affirmative_submit({}) == {}
    assert affirmative_submit({"weird": "x"}) == {"weird": "x"}
