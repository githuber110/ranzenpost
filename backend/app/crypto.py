import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import atomic_write

SALT_BYTES = 16


def generate_key():
    return Fernet.generate_key().decode("ascii")


def generate_salt():
    return base64.b64encode(os.urandom(SALT_BYTES)).decode("ascii")


def is_valid_key(value):
    try:
        Fernet(value.encode("ascii"))
    except (ValueError, TypeError):
        return False
    return True


def is_valid_salt(value):
    try:
        return len(base64.b64decode(value.encode("ascii"), validate=True)) == SALT_BYTES
    except (ValueError, TypeError):
        return False


def derive_key(passphrase, salt_b64):
    salt = base64.b64decode(salt_b64.encode("ascii"))
    kdf = Scrypt(salt=salt, length=32, n=2 ** 14, r=8, p=1)
    raw = kdf.derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _fernet(key):
    return Fernet(key.encode("ascii"))


def encrypt_dict(data, key):
    import json

    token = _fernet(key).encrypt(json.dumps(data).encode("utf-8"))
    return token.decode("ascii")


def decrypt_dict(token, key):
    import json

    try:
        raw = _fernet(key).decrypt(token.encode("ascii"))
    except InvalidToken as error:
        raise ValueError("cannot decrypt secrets with this key") from error
    return json.loads(raw.decode("utf-8"))


def _read_key(path):
    try:
        with open(path, "r", encoding="ascii") as handle:
            return handle.read().strip()
    except (OSError, ValueError):
        return ""


def load_or_create_key(path):
    stored = _read_key(path)
    if stored and is_valid_key(stored):
        return stored
    key = generate_key()
    atomic_write.write_text(path, key, encoding="ascii")
    return key


def looks_like_base32(value):
    cleaned = value.replace(" ", "").replace("-", "").upper()
    if len(cleaned) < 16:
        return False
    try:
        base64.b32decode(cleaned + "=" * (-len(cleaned) % 8), casefold=False)
    except (ValueError, TypeError):
        return False
    return True
