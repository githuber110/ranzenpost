import pytest

from app.validate import clean_totp_secret, is_valid_code, is_valid_secret, normalize_school_url


def test_normalize_adds_https_and_strips_path():
    assert normalize_school_url("myschool.example") == "https://myschool.example"
    assert normalize_school_url("https://x.de/iserv/") == "https://x.de"
    assert normalize_school_url("  X.DE  ") == "https://x.de"


def test_normalize_forces_https():
    assert normalize_school_url("http://x.de") == "https://x.de"


def test_normalize_rejects_invalid():
    for bad in ["", "notahost", "https://"]:
        with pytest.raises(ValueError):
            normalize_school_url(bad)


def test_normalize_blocks_private_and_loopback_ips():
    for bad in ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"]:
        with pytest.raises(ValueError):
            normalize_school_url(bad)


def test_clean_totp_secret():
    assert clean_totp_secret("jbsw y3dp-ehpk") == "JBSWY3DPEHPK"


def test_is_valid_secret():
    assert is_valid_secret("JBSWY3DPEHPK3PXP")
    assert not is_valid_secret("123456")
    assert not is_valid_secret("SHORT")


def test_is_valid_code():
    assert is_valid_code("123456")
    assert not is_valid_code("12345")
    assert not is_valid_code("abcdef")
