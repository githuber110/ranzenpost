import pytest

from app.validate import is_valid_code, normalize_school_url


def test_normalize_adds_https_and_strips_path():
    assert normalize_school_url("myschool.example") == "https://myschool.example"
    assert normalize_school_url("https://school.example/iserv/") == "https://school.example"
    assert normalize_school_url("  SCHOOL.EXAMPLE  ") == "https://school.example"


def test_normalize_forces_https():
    assert normalize_school_url("http://school.example") == "https://school.example"


def test_normalize_rejects_invalid():
    for bad in ["", "notahost", "https://"]:
        with pytest.raises(ValueError):
            normalize_school_url(bad)


def test_normalize_blocks_private_and_loopback_ips():
    for bad in ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"]:
        with pytest.raises(ValueError):
            normalize_school_url(bad)


def test_is_valid_code():
    assert is_valid_code("123456")
    assert not is_valid_code("12345")
    assert not is_valid_code("abcdef")
