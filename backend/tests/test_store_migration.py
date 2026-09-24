import json
import shutil
from pathlib import Path

import pytest

from app import atomic_write
from app.store import (
    SCHEMA_VERSION,
    ConnectionStore,
    Store,
    child_key,
    connection_of_key,
    split_child_key,
)

LEGACY_DIR = Path(__file__).parent / "fixtures" / "legacy_data"
LEGACY_CHILD = "11111111-aaaa-4bbb-8ccc-000000000001"
LEGACY_LETTER_CHILD = "letters:bob-example"
LEGACY_CONNECTION_KEYS = (
    "school_url",
    "children",
    "subjects",
    "teachers",
    "period_times",
    "phones",
    "holiday_region",
    "poll_state",
)


def legacy_store(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(LEGACY_DIR, target)
    return Store(target)


def raw_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_legacy_fixture_has_no_connections_and_a_single_secrets_file():
    config = raw_json(LEGACY_DIR / "config.json")
    assert "connections" not in config
    assert "schema_version" not in config
    assert (LEGACY_DIR / "secrets.enc").exists()
    assert not (LEGACY_DIR / "secrets").exists()


def test_child_key_helpers_round_trip():
    key = child_key("ab12cd34", LEGACY_CHILD)
    assert key == f"ab12cd34:{LEGACY_CHILD}"
    assert split_child_key(key) == ("ab12cd34", LEGACY_CHILD)
    assert connection_of_key(key) == "ab12cd34"
    assert split_child_key("") == ("", "")
    assert split_child_key("no-separator") == ("", "")
    assert split_child_key(":x") == ("", "")


def test_migration_creates_exactly_one_connection_from_the_legacy_config(tmp_path):
    store = legacy_store(tmp_path)
    config = store.load_config()
    assert config["schema_version"] == SCHEMA_VERSION
    assert len(config["connections"]) == 1
    entry = config["connections"][0]
    assert len(entry["id"]) == 8
    int(entry["id"], 16)
    assert entry["school_url"] == "https://school-one.example"
    assert entry["setup_complete"] is True
    assert entry["holiday_region"] == "DE-NI"
    assert entry["phones"] == [{"label": "Office", "number": "+49 000 0000"}]
    assert entry["subjects"]["D"]["label"] == "Deutsch"
    assert entry["teachers"]["BEH"]["label"] == "Fr. Behrend"
    assert entry["period_times"] == {"1": "08:00", "2": "08:50"}
    assert [child["child_id"] for child in entry["children"]] == [LEGACY_CHILD, LEGACY_LETTER_CHILD]
    assert config["language"] == "de"
    assert config["notify_services"] == ["notify.mobile_app_fixture"]
    assert config["notify_events"]["letters"] is False
    for key in LEGACY_CONNECTION_KEYS:
        assert key not in config


def test_migration_moves_the_secrets_into_the_connection_file(tmp_path):
    store = legacy_store(tmp_path)
    entry = store.connections()[0]
    secrets = store.load_secrets(entry["id"])
    assert secrets["username"] == "parent.one"
    assert secrets["totp_secret"] == "JBSWY3DPEHPK3PXP"
    assert store.secrets_path_for(entry["id"]).exists()
    assert not store.legacy_secrets_path.exists()


def test_migration_rewrites_every_child_keyed_store_file(tmp_path):
    store = legacy_store(tmp_path)
    connection_id = store.connections()[0]["id"]
    key = child_key(connection_id, LEGACY_CHILD)
    marks = store.load_marks()["marks"]
    assert marks[0]["child_key"] == key
    assert "child_id" not in marks[0]
    cancellations = store.load_cancellations()["cancellations"]
    assert cancellations[0]["child_key"] == key
    assert "child_id" not in cancellations[0]
    subscriptions = store.load_calendar_subscriptions()["subscriptions"]
    assert subscriptions[0]["child_key"] == key
    assert subscriptions[0]["token"] == "fixture-token-000000000000000000000000000000"
    snapshot = store.load_calendar_snapshot()
    assert list(snapshot["children"]) == [key]
    assert snapshot["children"][key]["last_success"] == 1
    poll_state = store.connections()[0]["poll_state"]
    assert poll_state[key]["signature"] == "abc"
    assert poll_state["letter_keys"] == ["l1:r1"]
    assert poll_state["pinboard_ids"] == ["100"]
    assert LEGACY_CHILD not in poll_state


def test_migration_nests_per_connection_files_under_the_connection_id(tmp_path):
    store = legacy_store(tmp_path)
    connection_id = store.connections()[0]["id"]
    scoped = ConnectionStore(store, connection_id)
    assert scoped.load_seen() == {"pinboard": [100, 101], "pinboard_initialised": True}
    assert scoped.load_absence_history()["a1"]["kind"] == "sick"
    assert scoped.load_letters_search_cache()["l1:r1"]["body_text"] == "text"
    assert scoped.load_letters_confirmations()["l1:r1"]["type"] == "seen"
    assert scoped.load_modules()["modules"]["conferences"] is False
    assert set(store.load_seen()) == {connection_id}
    assert set(store.load_modules()) == {connection_id}


def test_migration_splits_the_integration_state_into_shared_and_school_parts(tmp_path):
    store = legacy_store(tmp_path)
    connection_id = store.connections()[0]["id"]
    state = store.load_integration_state()
    assert state["last_request"] == 1758000000
    assert state["last_poll"] == 1758000100
    assert "letters" not in state
    assert "school_name" not in state
    school = state["schools"][connection_id]
    assert school["school_name"] == "School One"
    assert school["letters"] == ["Letter one"]
    assert school["last_poll_ok"] is True
    change = state["changes"][0]
    assert change["child_key"] == child_key(connection_id, LEGACY_CHILD)
    assert change["school_id"] == connection_id
    assert "child_id" not in change
    scoped = ConnectionStore(store, connection_id)
    assert scoped.load_integration_state()["school_name"] == "School One"


def test_migration_tags_the_wizard_state_with_the_connection(tmp_path):
    store = legacy_store(tmp_path)
    connection_id = store.connections()[0]["id"]
    assert store.load_wizard()["connection_id"] == connection_id
    assert store.load_wizard()["step"] == "done"


def test_migration_keeps_the_integration_token(tmp_path):
    store = legacy_store(tmp_path)
    assert store.load_integration_token() == "fixture-integration-token-0000000000000000000000"


def test_migration_is_idempotent(tmp_path):
    store = legacy_store(tmp_path)
    store.load_config()
    first = {path.name: path.read_bytes() for path in store.dir.rglob("*") if path.is_file()}
    store.migrate()
    store.load_config()
    second = {path.name: path.read_bytes() for path in store.dir.rglob("*") if path.is_file()}
    assert first == second
    assert len(store.connections()) == 1


def test_migration_survives_an_interruption_and_finishes_on_the_next_start(tmp_path, monkeypatch):
    store = legacy_store(tmp_path)
    original = atomic_write.write_json
    budget = {"left": 3}

    def failing_write(path, data, mode=atomic_write.PRIVATE_MODE):
        if budget["left"] <= 0:
            raise OSError("disk went away")
        budget["left"] -= 1
        return original(path, data, mode)

    monkeypatch.setattr(atomic_write, "write_json", failing_write)
    with pytest.raises(OSError):
        store.migrate()
    monkeypatch.setattr(atomic_write, "write_json", original)
    interrupted = raw_json(store.config_path)
    assert interrupted["school_url"] == "https://school-one.example"
    assert store.legacy_secrets_path.exists()
    assert store._decrypt_secrets_file(store.legacy_secrets_path)["username"] == "parent.one"
    connection_id = interrupted["connections"][0]["id"]
    reopened = Store(store.dir)
    config = reopened.load_config()
    assert config["schema_version"] == SCHEMA_VERSION
    assert [entry["id"] for entry in config["connections"]] == [connection_id]
    assert reopened.load_secrets(connection_id)["username"] == "parent.one"
    assert not reopened.legacy_secrets_path.exists()
    key = child_key(connection_id, LEGACY_CHILD)
    assert reopened.load_marks()["marks"][0]["child_key"] == key
    assert list(reopened.load_calendar_snapshot()["children"]) == [key]
    assert set(reopened.load_seen()) == {connection_id}


@pytest.mark.parametrize("budget", [0, 1, 2, 4, 5, 6, 8, 10])
def test_migration_completes_after_an_interruption_at_any_step(tmp_path, monkeypatch, budget):
    store = legacy_store(tmp_path)
    original_json = atomic_write.write_json
    original_text = atomic_write.write_text
    left = {"count": budget}

    def spend():
        if left["count"] <= 0:
            raise OSError("disk went away")
        left["count"] -= 1

    def failing_json(path, data, mode=atomic_write.PRIVATE_MODE):
        spend()
        return original_json(path, data, mode)

    def failing_text(path, text, encoding="utf-8", mode=atomic_write.PRIVATE_MODE):
        spend()
        return original_text(path, text, encoding, mode)

    monkeypatch.setattr(atomic_write, "write_json", failing_json)
    monkeypatch.setattr(atomic_write, "write_text", failing_text)
    try:
        store.migrate()
    except OSError:
        pass
    monkeypatch.setattr(atomic_write, "write_json", original_json)
    monkeypatch.setattr(atomic_write, "write_text", original_text)
    reopened = Store(store.dir)
    config = reopened.load_config()
    assert len(config["connections"]) == 1
    connection_id = config["connections"][0]["id"]
    assert reopened.load_secrets(connection_id)["username"] == "parent.one"
    assert reopened.load_marks()["marks"][0]["child_key"] == child_key(connection_id, LEGACY_CHILD)
    assert set(reopened.load_seen()) == {connection_id}
    assert reopened.load_integration_state()["schools"][connection_id]["school_name"] == "School One"
    assert not reopened.legacy_secrets_path.exists()


def test_a_fresh_store_needs_no_migration_and_writes_nothing(tmp_path):
    store = Store(tmp_path / "data")
    config = store.load_config()
    assert config["connections"] == []
    assert config["schema_version"] == SCHEMA_VERSION
    assert not store.config_path.exists()


def test_a_legacy_config_without_school_url_gets_no_connection(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"language": "en"})
    config = store.load_config()
    assert config["connections"] == []
    assert config["language"] == "en"
    assert raw_json(store.config_path)["schema_version"] == SCHEMA_VERSION


def test_a_stray_legacy_secrets_file_next_to_several_connections_is_quarantined(tmp_path):
    store = Store(tmp_path / "data")
    store.add_connection("https://school-one.example")
    store.add_connection("https://school-two.example")
    store.legacy_secrets_path.write_text("gAAAAA-old", encoding="ascii")
    store.load_config()
    assert not store.legacy_secrets_path.exists()
    assert store.legacy_secrets_path.with_name("secrets.enc.corrupt").exists()


def legacy_layout(tmp_path, secrets_text, config=None, wizard=None):
    data = tmp_path / "data"
    data.mkdir()
    if config is not None:
        (data / "config.json").write_text(config, encoding="utf-8")
    (data / "secrets.enc").write_text(secrets_text, encoding="ascii")
    if wizard is not None:
        (data / "wizard.json").write_text(json.dumps(wizard), encoding="utf-8")
    return data


def legacy_token(data, secrets):
    from app import crypto

    return crypto.encrypt_dict(secrets, Store(data)._key())


LEGACY_FLAT_CONFIG = json.dumps({"school_url": "https://school-one.example", "language": "de", "children": []})


@pytest.mark.parametrize("wizard", [{"step": "done"}, None], ids=["wizard_done", "no_wizard"])
def test_a_migration_without_the_passphrase_still_marks_the_school_as_set_up(tmp_path, monkeypatch, wizard):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("ISERV_PASSPHRASE", "correct horse")
    token = legacy_token(data, {"username": "parent.one", "password": "x", "totp_secret": "JBSWY3DPEHPK3PXP"})
    (data / "secrets.enc").write_text(token, encoding="ascii")
    (data / "config.json").write_text(LEGACY_FLAT_CONFIG, encoding="utf-8")
    if wizard is not None:
        (data / "wizard.json").write_text(json.dumps(wizard), encoding="utf-8")
    monkeypatch.delenv("ISERV_PASSPHRASE")

    entry = Store(data).connections()[0]

    assert entry["setup_complete"] is True
    assert entry["school_url"] == "https://school-one.example"
    assert not (data / "secrets.enc").exists()
    assert not (data / "secrets.enc.corrupt").exists()
    monkeypatch.setenv("ISERV_PASSPHRASE", "correct horse")
    assert Store(data).load_secrets(entry["id"])["username"] == "parent.one"


def test_a_legacy_token_without_a_login_leaves_the_school_unfinished(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    token = legacy_token(data, {})
    (data / "secrets.enc").write_text(token, encoding="ascii")
    (data / "config.json").write_text(LEGACY_FLAT_CONFIG, encoding="utf-8")

    entry = Store(data).connections()[0]

    assert entry["setup_complete"] is False
    assert not (data / "secrets.enc").exists()


def test_a_corrupt_legacy_secrets_file_is_quarantined_instead_of_copied(tmp_path):
    data = legacy_layout(tmp_path, "this is not a token", config=LEGACY_FLAT_CONFIG, wizard={"step": "done"})

    store = Store(data)
    entry = store.connections()[0]

    assert entry["school_url"] == "https://school-one.example"
    assert entry["setup_complete"] is False
    assert not store.secrets_path_for(entry["id"]).exists()
    assert store.load_secrets(entry["id"]) == {}
    assert not (data / "secrets.enc").exists()
    assert (data / "secrets.enc.corrupt").read_text(encoding="ascii") == "this is not a token"


def test_a_corrupt_legacy_config_next_to_a_secrets_file_yields_no_connection(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    token = legacy_token(data, {"username": "parent.one", "password": "x"})
    (data / "secrets.enc").write_text(token, encoding="ascii")
    (data / "config.json").write_text("{ not json", encoding="utf-8")

    store = Store(data)
    config = store.load_config()

    assert config["connections"] == []
    assert (data / "config.json.corrupt").exists()
    assert not (data / "secrets.enc").exists()
    assert (data / "secrets.enc.corrupt").read_text(encoding="ascii") == token
    assert not store.secrets_dir.exists() or list(store.secrets_dir.iterdir()) == []
    assert raw_json(store.config_path)["schema_version"] == SCHEMA_VERSION
