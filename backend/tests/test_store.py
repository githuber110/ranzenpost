import json
import os
import stat

import pytest

from app.store import CONNECTION_DEFAULTS, DEFAULT_CONFIG, ConnectionStore, Store, child_key


def test_config_roundtrip_and_defaults(tmp_path):
    store = Store(tmp_path / "data")
    assert store.load_config()["connections"] == []
    assert store.load_config()["language"] == "system"
    entry = store.add_connection("https://x", subjects={"D": {"label": "Deutsch"}})
    loaded = store.load_config()
    assert loaded["connections"][0]["school_url"] == "https://x"
    assert loaded["connections"][0]["subjects"]["D"]["label"] == "Deutsch"
    assert loaded["connections"][0]["phones"] == []
    assert store.connection(entry["id"])["id"] == entry["id"]


def test_connection_ids_are_eight_hex_characters_and_stable(tmp_path):
    store = Store(tmp_path / "data")
    first = store.add_connection("https://school-one.example")
    second = store.add_connection("https://school-one.example")
    assert len(first["id"]) == 8 and len(second["id"]) == 8
    int(first["id"], 16)
    assert first["id"] != second["id"]
    assert [entry["id"] for entry in store.connections()] == [first["id"], second["id"]]
    store.update_connection(first["id"], label="First")
    assert [entry["id"] for entry in store.connections()] == [first["id"], second["id"]]
    assert store.connection(first["id"])["label"] == "First"


def test_children_carry_connection_id_and_key(tmp_path):
    store = Store(tmp_path / "data")
    one = store.add_connection("https://school-one.example", children=[{"child_id": "c1", "name": "Alice Example"}])
    two = store.add_connection("https://school-two.example", children=[{"child_id": "c1", "name": "Alice Other"}])
    listed = store.children()
    assert [child["key"] for child in listed] == [child_key(one["id"], "c1"), child_key(two["id"], "c1")]
    assert listed[0]["connection_id"] == one["id"]
    assert listed[1]["name"] == "Alice Other"
    assert store.find_child(child_key(two["id"], "c1"))["name"] == "Alice Other"
    assert store.find_child("missing:c1") is None


@pytest.mark.skipif(os.name != "posix", reason="file mode bits are not meaningful on this OS")
def test_config_file_is_written_owner_only(tmp_path):
    store = Store(tmp_path / "data")
    store.add_connection("https://x")
    mode = stat.S_IMODE(store.config_path.stat().st_mode)
    assert mode == 0o600


def test_secrets_roundtrip_per_connection(tmp_path):
    store = Store(tmp_path / "data")
    assert store.load_secrets("a1b2c3d4") == {}
    store.save_secrets("a1b2c3d4", {"username": "u", "password": "p", "totp_secret": "JBSW"})
    store.save_secrets("e5f6a7b8", {"username": "other"})
    assert store.load_secrets("a1b2c3d4")["username"] == "u"
    assert store.load_secrets("e5f6a7b8")["username"] == "other"
    assert store.secrets_path_for("a1b2c3d4").name == "a1b2c3d4.enc"
    assert store.secrets_path_for("a1b2c3d4").parent == store.dir / "secrets"
    store.delete_secrets("a1b2c3d4")
    assert store.load_secrets("a1b2c3d4") == {}
    assert store.load_secrets("e5f6a7b8")["username"] == "other"


def test_secrets_roundtrip_with_passphrase(tmp_path, monkeypatch):
    monkeypatch.setenv("ISERV_PASSPHRASE", "familie-geheim")
    store = Store(tmp_path / "data")
    store.save_secrets("a1b2c3d4", {"username": "u"})
    assert store.load_secrets("a1b2c3d4")["username"] == "u"
    assert not (tmp_path / "data" / "key").exists()
    assert (tmp_path / "data" / "salt").exists()


def test_default_config_notify_events_all_enabled():
    assert DEFAULT_CONFIG["notify_events"] == {
        "timetable": True,
        "letters": True,
        "pinboard": True,
        "conferences": True,
        "messenger": True,
    }


def test_load_config_for_new_store_enables_all_notify_events(tmp_path):
    store = Store(tmp_path / "data")

    config = store.load_config()

    assert all(config["notify_events"].values())


def test_load_config_migrates_old_single_notify_service_to_list(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"notify_service": "notify.mobile_app_phone"})

    config = store.load_config()

    assert config["notify_services"] == ["notify.mobile_app_phone"]
    assert "notify_service" not in config


def test_load_config_migration_does_not_keep_writing_old_key(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"notify_service": "notify.mobile_app_phone"})
    config = store.load_config()
    store.save_config(config)

    raw = json.loads(store.config_path.read_text(encoding="utf-8"))

    assert "notify_service" not in raw
    assert raw["notify_services"] == ["notify.mobile_app_phone"]


def test_load_config_prefers_existing_notify_services_list_over_old_key(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"notify_service": "notify.old", "notify_services": ["notify.new"]})

    config = store.load_config()

    assert config["notify_services"] == ["notify.new"]


def test_load_config_does_not_migrate_existing_false_toggle(tmp_path):
    store = Store(tmp_path / "data")
    saved = dict(DEFAULT_CONFIG)
    saved["notify_events"] = {
        "timetable": False,
        "letters": True,
        "pinboard": True,
        "conferences": True,
        "messenger": False,
    }
    store.save_config(saved)

    config = store.load_config()

    assert config["notify_events"]["timetable"] is False
    assert config["notify_events"]["messenger"] is False


def test_connection_store_reads_a_flat_view_and_writes_back_split(tmp_path):
    store = Store(tmp_path / "data")
    entry = store.add_connection("https://school-one.example", holiday_region="DE-NI")
    store.add_connection("https://school-two.example")
    scoped = ConnectionStore(store, entry["id"])
    flat = scoped.load_config()
    assert flat["connection_id"] == entry["id"]
    assert flat["school_url"] == "https://school-one.example"
    assert flat["holiday_region"] == "DE-NI"
    assert flat["language"] == "system"
    assert set(CONNECTION_DEFAULTS) - {"id"} <= set(flat)
    assert "connections" not in flat
    flat["subjects"] = {"M": {"label": "Mathematik"}}
    flat["language"] = "en"
    scoped.save_config(flat)
    config = store.load_config()
    assert config["language"] == "system"
    scoped.edit_config(lambda current: current.update(language="en"))
    config = store.load_config()
    assert config["language"] == "en"
    assert config["connections"][0]["subjects"]["M"]["label"] == "Mathematik"
    assert config["connections"][1]["subjects"] == {}
    assert "subjects" not in config


def test_connection_store_scopes_secrets_and_nested_files(tmp_path):
    store = Store(tmp_path / "data")
    one = ConnectionStore(store, store.add_connection("https://school-one.example")["id"])
    two = ConnectionStore(store, store.add_connection("https://school-two.example")["id"])
    one.save_secrets({"username": "first"})
    two.save_secrets({"username": "second"})
    one.save_seen({"pinboard": [1]})
    two.save_seen({"pinboard": [2]})
    one.save_modules({"modules": {"timetable": False}})
    one.save_letters_confirmations({"l:r": {"type": "seen"}})
    one.save_integration_state({"school_name": "One"})
    two.save_integration_state({"school_name": "Two"})
    assert one.load_secrets()["username"] == "first"
    assert two.load_secrets()["username"] == "second"
    assert one.load_seen() == {"pinboard": [1]}
    assert two.load_seen() == {"pinboard": [2]}
    assert one.load_modules()["modules"]["timetable"] is False
    assert two.load_modules() == {}
    assert two.load_letters_confirmations() == {}
    assert one.load_integration_state() == {"school_name": "One"}
    assert store.load_integration_state()["schools"][two.id] == {"school_name": "Two"}
    assert one.load_calendar_snapshot() == {}
    assert one.load_integration_token() == ""


def test_remove_connection_purges_everything_that_belongs_to_it(tmp_path):
    store = Store(tmp_path / "data")
    one = store.add_connection("https://school-one.example", children=[{"child_id": "c1", "name": "Alice"}])
    two = store.add_connection("https://school-two.example", children=[{"child_id": "c1", "name": "Bob"}])
    one_key = child_key(one["id"], "c1")
    two_key = child_key(two["id"], "c1")
    store.save_secrets(one["id"], {"username": "first"})
    store.save_secrets(two["id"], {"username": "second"})
    store.save_seen({one["id"]: {"pinboard": [1]}, two["id"]: {"pinboard": [2]}})
    store.save_modules({one["id"]: {"modules": {}}, two["id"]: {"modules": {}}})
    store.save_letters_replies({one["id"]: {"r1": {"state": "sent"}}, two["id"]: {"r2": {"state": "sent"}}})
    store.save_marks({"marks": [{"id": "m1", "child_key": one_key}, {"id": "m2", "child_key": two_key}]})
    store.save_cancellations({"cancellations": [{"id": "c1", "child_key": one_key}]})
    store.save_calendar_subscriptions(
        {"subscriptions": [{"id": "s1", "child_key": one_key}, {"id": "s2", "child_key": two_key}]}
    )
    store.save_calendar_snapshot({"children": {one_key: {"weeks": {}}, two_key: {"weeks": {}}}})
    store.save_integration_state(
        {"last_request": 1, "schools": {one["id"]: {"school_name": "One"}, two["id"]: {"school_name": "Two"}}}
    )
    assert store.remove_connection(one["id"]) is True
    assert [entry["id"] for entry in store.connections()] == [two["id"]]
    assert store.load_secrets(one["id"]) == {}
    assert store.load_secrets(two["id"])["username"] == "second"
    assert set(store.load_seen()) == {two["id"]}
    assert set(store.load_modules()) == {two["id"]}
    assert set(store.load_letters_replies()) == {two["id"]}
    assert [entry["id"] for entry in store.load_marks()["marks"]] == ["m2"]
    assert store.load_cancellations()["cancellations"] == []
    assert [entry["id"] for entry in store.load_calendar_subscriptions()["subscriptions"]] == ["s2"]
    assert list(store.load_calendar_snapshot()["children"]) == [two_key]
    assert set(store.load_integration_state()["schools"]) == {two["id"]}
    assert store.load_integration_state()["last_request"] == 1
    assert store.remove_connection(one["id"]) is False
