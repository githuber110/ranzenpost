import pytest

from app.crypto import (
    decrypt_dict,
    derive_key,
    encrypt_dict,
    generate_key,
    generate_salt,
    load_or_create_key,
    looks_like_base32,
)


def test_encrypt_decrypt_roundtrip():
    key = generate_key()
    token = encrypt_dict({"username": "u", "password": "p"}, key)
    assert token != "u"
    assert decrypt_dict(token, key) == {"username": "u", "password": "p"}


def test_decrypt_with_wrong_key_raises():
    token = encrypt_dict({"a": 1}, generate_key())
    with pytest.raises(ValueError):
        decrypt_dict(token, generate_key())


def test_load_or_create_key_is_stable(tmp_path):
    path = str(tmp_path / "key")
    first = load_or_create_key(path)
    assert load_or_create_key(path) == first


def test_looks_like_base32():
    assert looks_like_base32("JBSWY3DPEHPK3PXP")
    assert not looks_like_base32("123456")
    assert not looks_like_base32("has spaces and punctuation!!!")


def test_derive_key_is_deterministic():
    salt = generate_salt()
    assert derive_key("hunter2", salt) == derive_key("hunter2", salt)


def test_derive_key_changes_with_salt_and_passphrase():
    assert derive_key("hunter2", generate_salt()) != derive_key("hunter2", generate_salt())
    salt = generate_salt()
    assert derive_key("hunter2", salt) != derive_key("other", salt)


def test_derived_key_works_with_fernet():
    key = derive_key("pw", generate_salt())
    assert decrypt_dict(encrypt_dict({"x": 1}, key), key) == {"x": 1}
