from app.lockout import classify_login_response, human_message

LOCKED_EXAMPLE_HTML = (
    "<html><body><h1>Zugang gesperrt</h1><p>Ihr Konto wurde wegen zu vieler "
    "Fehlversuche vorübergehend gesperrt.</p></body></html>"
)

LOCKED_MIXED_CASE_EXAMPLE_HTML = (
    "<div>ACHTUNG: Konto GESPERRT nach zu vielen Anmeldeversuchen.</div>"
)

CAPTCHA_EXAMPLE_HTML = (
    "<html><body><p>Sicherheitsabfrage: Bitte bestätigen Sie, dass Sie kein "
    "Roboter sind.</p><div class=\"g-recaptcha\"></div></body></html>"
)

PASSWORD_EXPIRED_EXAMPLE_HTML = (
    "<html><body><p>Ihr Passwort ist abgelaufen. Bitte vergeben Sie ein neues "
    "Passwort, bevor Sie fortfahren.</p></body></html>"
)

NORMAL_PORTAL_EXAMPLE_HTML = (
    "<html><body><h1>Willkommen im Schulportal</h1><p>Ihre nächsten Termine.</p>"
    "</body></html>"
)

LOCKED_AND_CAPTCHA_EXAMPLE_HTML = (
    "<html><body><p>Ihr Konto ist gesperrt.</p><p>captcha erforderlich</p>"
    "</body></html>"
)

CAPTCHA_AND_PASSWORD_EXPIRED_EXAMPLE_HTML = (
    "<html><body><p>captcha erforderlich</p><p>Passwort ist abgelaufen.</p>"
    "</body></html>"
)


def test_classifies_generic_lockout_page_as_locked():
    assert classify_login_response(LOCKED_EXAMPLE_HTML) == "locked"


def test_classifies_lockout_marker_case_insensitively():
    assert classify_login_response(LOCKED_MIXED_CASE_EXAMPLE_HTML) == "locked"


def test_classifies_captcha_page_as_captcha():
    assert classify_login_response(CAPTCHA_EXAMPLE_HTML) == "captcha"


def test_classifies_password_expired_page_as_password_expired():
    assert classify_login_response(PASSWORD_EXPIRED_EXAMPLE_HTML) == "password_expired"


def test_classifies_plain_portal_page_as_normal():
    assert classify_login_response(NORMAL_PORTAL_EXAMPLE_HTML) == "normal"


def test_locked_marker_takes_priority_over_captcha_marker():
    assert classify_login_response(LOCKED_AND_CAPTCHA_EXAMPLE_HTML) == "locked"


def test_captcha_marker_takes_priority_over_password_expired_marker():
    assert classify_login_response(CAPTCHA_AND_PASSWORD_EXPIRED_EXAMPLE_HTML) == "captcha"


def test_rate_limit_status_code_classifies_as_locked_without_marker_text():
    assert classify_login_response(NORMAL_PORTAL_EXAMPLE_HTML, status_code=429) == "locked"


def test_human_message_is_distinct_actionable_text_per_kind():
    kinds = ("locked", "captcha", "password_expired", "normal")
    messages = {kind: human_message(kind) for kind in kinds}
    assert len(set(messages.values())) == len(kinds)
    for message in messages.values():
        assert len(message) > 20


def test_human_message_falls_back_to_normal_for_unknown_kind():
    assert human_message("unexpected_kind") == human_message("normal")
