import threading

from app import code_windows
from app.iserv.totp import generate_code
from app.iserv_prober import IServProber
from app.sign_in import _code_provider

SECRET = "JBSWY3DPEHPK3PXP"
START = 1_800_000_001.0


class FakeTime:
    def __init__(self, now):
        self.now = now
        self.slept = []
        self.lock = threading.Lock()

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        with self.lock:
            self.slept.append(seconds)
            self.now += seconds


class Registration:
    secret = SECRET


class Registering:
    def confirm_totp_registration(self, registration, name, code, at=None):
        return registration.secret

    def read_token_list(self):
        return []


def timed_prober(clock):
    prober = IServProber()
    prober.clock = clock
    prober.sleeper = clock.sleep
    return prober


def test_the_wizard_never_reuses_a_code_the_background_sign_in_just_sent():
    clock = FakeTime(START)
    background = _code_provider({"totp_secret": SECRET}, {}, clock.sleep, clock)()
    wizard = timed_prober(clock)._next_code(SECRET)
    assert background == generate_code(SECRET, at=START)
    assert wizard != background
    assert len(clock.slept) == 1


def test_the_background_sign_in_waits_after_the_wizard_registered_a_key():
    clock = FakeTime(START)
    prober = timed_prober(clock)
    prober._pending = {"client": Registering(), "registration": Registration(), "url": "https://x", "username": "u", "existing_uuids": set()}
    assert prober.confirm_2fa("https://x", "u", "p", "123456")["status"] == "ok"
    background = _code_provider({"totp_secret": SECRET}, {}, clock.sleep, clock)()
    assert background != generate_code(SECRET, at=START)
    assert len(clock.slept) == 1


def test_two_components_at_the_same_moment_get_different_windows():
    clock = FakeTime(START)
    codes = []
    threads = [
        threading.Thread(target=lambda: codes.append(code_windows.next_code(SECRET, None, clock.sleep, clock)))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert len(set(codes)) == 2


def test_the_memory_holds_no_secret_and_other_keys_never_wait():
    clock = FakeTime(START)
    code_windows.next_code(SECRET, None, clock.sleep, clock)
    code_windows.next_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", None, clock.sleep, clock)
    assert clock.slept == []
    assert SECRET not in repr(code_windows._LAST)
