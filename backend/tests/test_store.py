import json
import os
import stat

import pytest

from app.store import DEFAULT_CONFIG, Store


def test_config_roundtrip_and_defaults(tmp_path):
    store = Store(tmp_path / "data")
    assert store.load_config()["subjects"] == {}
    assert store.load_config()["phones"] == []
    store.save_config({"school_url": "https://x", "subjects": {"D": {"label": "Deutsch"}}})
    loaded = store.load_config()
    assert loaded["school_url"] == "https://x"
    assert loaded["subjects"]["D"]["label"] == "Deutsch"
    assert loaded["phones"] == []


@pytest.mark.skipif(os.name != "posix", reason="file mode bits are not meaningful on this OS")
def test_config_file_is_written_owner_only(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://x", "calendar_password": "secret"})
    mode = stat.S_IMODE(store.config_path.stat().st_mode)
    assert mode == 0o600


def test_secrets_roundtrip(tmp_path):
    store = Store(tmp_path / "data")
    assert store.load_secrets() == {}
    store.save_secrets({"username": "u", "password": "p", "totp_secret": "JBSW"})
    assert store.load_secrets()["username"] == "u"


def test_secrets_roundtrip_with_passphrase(tmp_path, monkeypatch):
    monkeypatch.setenv("ISERV_PASSPHRASE", "familie-geheim")
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "u"})
    assert store.load_secrets()["username"] == "u"
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
