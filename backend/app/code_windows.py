import hashlib
import threading
import time

from .iserv.totp import generate_code, normalize_secret

TOTP_PERIOD = 30

_LOCK = threading.Lock()
_LAST = {}


def _key(secret):
    return hashlib.sha256(normalize_secret(secret).encode("utf-8")).hexdigest()


def _remember(key, code, used):
    _LAST[key] = code
    if used is not None:
        used["code"] = code


def forget():
    with _LOCK:
        _LAST.clear()


def mark_used(secret, at):
    if not secret:
        return
    with _LOCK:
        _LAST[_key(secret)] = generate_code(secret, at=at)


def next_code(secret, used=None, sleeper=time.sleep, clock=time.time):
    key = _key(secret)
    with _LOCK:
        now = clock()
        code = generate_code(secret, at=now)
        if code not in (_LAST.get(key), (used or {}).get("code")):
            _remember(key, code, used)
            return code
        _LAST[key] = code
    sleeper(max(0.0, TOTP_PERIOD - (now % TOTP_PERIOD)) + 1)
    with _LOCK:
        code = generate_code(secret, at=clock())
        _remember(key, code, used)
        return code
