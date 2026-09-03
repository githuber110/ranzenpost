import pyotp

from app.iserv.totp import generate_code, normalize_secret

SECRET = "JBSWY3DPEHPK3PXP"


def test_normalize_secret_strips_spaces_and_uppercases():
    assert normalize_secret("jbsw y3dp") == "JBSWY3DP"


def test_generate_code_matches_pyotp_at_timestamp():
    assert generate_code(SECRET, at=1788191965) == pyotp.TOTP(SECRET).at(1788191965)


def test_generate_code_is_six_digits():
    code = generate_code(SECRET, at=0)
    assert len(code) == 6
    assert code.isdigit()
