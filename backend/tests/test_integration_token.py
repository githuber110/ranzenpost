import os
import stat
import sys

import pytest

from app import integration
from app.store import Store


def _store(tmp_path):
    return Store(tmp_path / "data")


def test_the_first_start_writes_a_token_file_next_to_the_config(tmp_path):
    store = _store(tmp_path)

    token = integration.ensure_token(store)

    path = store.integration_token_path
    assert path.name == "integration_token"
    assert path.parent == store.dir
    assert path.read_text(encoding="ascii").strip() == token


def test_the_token_is_32_urlsafe_bytes(tmp_path):
    token = integration.ensure_token(_store(tmp_path))

    assert integration.is_valid_token(token)
    assert len(token) == 43
    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_a_second_start_keeps_the_token(tmp_path):
    store = _store(tmp_path)

    first = integration.ensure_token(store)
    second = integration.ensure_token(store)

    assert first == second
    assert integration.ensure_token(Store(store.dir)) == first


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_the_token_file_is_readable_by_the_owner_alone(tmp_path):
    store = _store(tmp_path)
    integration.ensure_token(store)

    mode = stat.S_IMODE(os.stat(store.integration_token_path).st_mode)

    assert mode == 0o600


def test_the_token_file_is_written_atomically(tmp_path, monkeypatch):
    from app import atomic_write

    seen = []
    original = atomic_write.write_text

    def spy(path, text, encoding="utf-8", mode=atomic_write.PRIVATE_MODE):
        seen.append((str(path), mode))
        return original(path, text, encoding=encoding, mode=mode)

    monkeypatch.setattr(atomic_write, "write_text", spy)
    store = _store(tmp_path)

    integration.ensure_token(store)

    assert seen == [(str(store.integration_token_path), 0o600)]


def test_rotation_replaces_the_token_and_persists_it(tmp_path):
    store = _store(tmp_path)
    old = integration.ensure_token(store)

    new = integration.rotate_token(store)

    assert new != old
    assert integration.is_valid_token(new)
    assert store.load_integration_token() == new
    assert integration.ensure_token(store) == new


def test_an_unusable_token_file_is_replaced_on_start(tmp_path):
    store = _store(tmp_path)
    store.integration_token_path.write_text("short\n", encoding="ascii")

    token = integration.ensure_token(store)

    assert token != "short"
    assert integration.is_valid_token(token)


def test_a_token_file_with_trailing_whitespace_still_counts(tmp_path):
    store = _store(tmp_path)
    token = integration.generate_token()
    store.integration_token_path.write_text(f"  {token}\n", encoding="ascii")

    assert integration.ensure_token(store) == token


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", False),
        (None, False),
        ("a" * 42, False),
        ("a" * 43, True),
        ("a" * 64, True),
        ("a" * 65, False),
        ("a" * 42 + "!", False),
        ("a" * 42 + "/", False),
    ],
)
def test_is_valid_token_accepts_only_urlsafe_tokens_of_a_sane_length(value, expected):
    assert integration.is_valid_token(value) is expected


def test_a_store_without_a_token_file_still_gets_a_token_for_the_process():
    class Bare:
        pass

    token = integration.ensure_token(Bare())

    assert integration.is_valid_token(token)
    assert integration.is_valid_token(integration.rotate_token(Bare()))


def test_the_integration_state_lives_in_its_own_private_file(tmp_path):
    store = _store(tmp_path)

    assert store.load_integration_state() == {}
    store.save_integration_state({"last_request": 1})

    assert store.load_integration_state() == {"last_request": 1}
    assert store.integration_state_path.parent == store.dir
    assert store.integration_state_path.name == "integration_state.json"
