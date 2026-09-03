import ast
import json
import os
import pathlib
import stat

import pytest

from app import atomic_write, crypto
from app.store import DEFAULT_WIZARD, Store

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"
GUARDED_MODULES = ("store.py", "crypto.py")
WRITE_METHODS = {"write_text", "write_bytes", "writelines"}
WRITE_MODE_MARKERS = ("w", "a", "x", "+")


class Interrupted(Exception):
    pass


def temp_files(directory):
    return sorted(path.name for path in directory.glob(f"*{atomic_write.TEMP_SUFFIX}"))


def collect_direct_writes(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Attribute):
            if isinstance(target.value, ast.Name) and target.value.id == "atomic_write":
                continue
            if target.attr in WRITE_METHODS or (target.attr == "open" and _is_os(target.value)):
                found.append(f"{path.name}:{node.lineno} {target.attr}")
            if target.attr == "fdopen":
                found.append(f"{path.name}:{node.lineno} {target.attr}")
        if isinstance(target, ast.Name) and target.id == "open" and _opens_for_writing(node):
            found.append(f"{path.name}:{node.lineno} open")
    return found


def _is_os(node):
    return isinstance(node, ast.Name) and node.id == "os"


def _opens_for_writing(node):
    modes = [
        argument.value
        for argument in list(node.args[1:2]) + [keyword.value for keyword in node.keywords if keyword.arg == "mode"]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]
    return any(marker in mode for mode in modes for marker in WRITE_MODE_MARKERS)


def test_store_and_crypto_never_write_a_target_file_directly():
    offenders = []
    for name in GUARDED_MODULES:
        offenders.extend(collect_direct_writes(APP_DIR / name))
    assert offenders == []


def test_direct_write_detector_flags_a_reintroduced_raw_write(tmp_path):
    sample = tmp_path / "store.py"
    sample.write_text(
        "import os\n"
        "def save(path, payload):\n"
        "    path.write_text(payload)\n",
        encoding="utf-8",
    )
    assert collect_direct_writes(sample) == ["store.py:3 write_text"]


def test_direct_write_detector_accepts_the_shared_helper(tmp_path):
    sample = tmp_path / "store.py"
    sample.write_text(
        "from . import atomic_write\n"
        "def save(path, payload):\n"
        "    atomic_write.write_text(path, payload)\n",
        encoding="utf-8",
    )
    assert collect_direct_writes(sample) == []


def test_every_store_save_method_uses_the_shared_helper():
    tree = ast.parse((APP_DIR / "store.py").read_text(encoding="utf-8"))
    checked = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or "save" not in node.name:
            continue
        calls = {
            child.func.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
        }
        assert calls & {"write_json", "write_text", "write_bytes", "_save_private_json"}, node.name
        checked.append(node.name)
    assert len(checked) >= 10


def test_config_survives_an_interruption_in_the_middle_of_a_write(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example", "subjects": {"D": {"color": "#ff0000"}}})
    before = store.config_path.read_bytes()

    monkeypatch.setattr(atomic_write.os, "replace", _raise_interrupted)
    with pytest.raises(Interrupted):
        store.save_config({"school_url": "", "subjects": {}})

    assert store.config_path.read_bytes() == before
    assert store.load_config()["subjects"]["D"]["color"] == "#ff0000"
    assert temp_files(store.dir) == []


def test_config_survives_an_interruption_before_the_data_reaches_the_disk(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_config({"period_times": {"1": "07:55"}})
    before = store.config_path.read_bytes()

    monkeypatch.setattr(atomic_write.os, "fsync", _raise_interrupted)
    with pytest.raises(Interrupted):
        store.save_config({"period_times": {}})

    assert store.config_path.read_bytes() == before
    assert store.load_config()["period_times"] == {"1": "07:55"}
    assert temp_files(store.dir) == []


def test_secrets_survive_an_interruption_in_the_middle_of_a_write(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent", "password": "old"})
    before = store.secrets_path.read_bytes()

    monkeypatch.setattr(atomic_write.os, "replace", _raise_interrupted)
    with pytest.raises(Interrupted):
        store.save_secrets({"username": "parent", "password": "new"})

    assert store.secrets_path.read_bytes() == before
    assert store.load_secrets() == {"username": "parent", "password": "old"}
    assert temp_files(store.dir) == []


def test_a_successful_write_leaves_no_temporary_file_behind(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.save_secrets({"username": "parent"})
    store.save_wizard({"step": "done", "attempts": 0})
    store.save_seen({"letters": ["1"]})
    store.save_absence_history({"child": []})
    store.save_letters_search_cache({"query": []})
    store.save_holidays_cache({"2026": []})
    store.save_calendar_subscriptions({"token": {}})
    store.save_calendar_snapshot({"events": []})
    store.save_calendar_state({"cursor": "1"})

    assert temp_files(store.dir) == []


def test_a_leftover_temporary_file_is_removed_on_the_next_start(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    leftover = atomic_write.temp_path_for(store.config_path)
    leftover.write_text("half written", encoding="utf-8")

    restarted = Store(tmp_path / "data")

    assert temp_files(restarted.dir) == []
    assert restarted.load_config()["school_url"] == "https://school.example"


def test_secret_files_are_never_created_with_wider_permissions(tmp_path, monkeypatch):
    modes = []
    real_open = atomic_write.os.open

    def recording_open(path, flags, *rest):
        if flags & os.O_CREAT:
            modes.append((str(path), rest[0] if rest else None))
        return real_open(path, flags, *rest)

    monkeypatch.setattr(atomic_write.os, "open", recording_open)
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent", "totp_secret": "JBSWY3DPEHPK3PXP"})

    assert modes, "no file was created"
    assert all(mode == 0o600 for _, mode in modes), modes
    assert all(name.endswith(atomic_write.TEMP_SUFFIX) for name, _ in modes), modes


@pytest.mark.skipif(os.name != "posix", reason="file mode bits are not meaningful on this OS")
def test_the_temporary_secret_file_is_owner_only_before_it_is_renamed(tmp_path, monkeypatch):
    observed = []
    real_replace = atomic_write.os.replace

    def watching_replace(source, target):
        observed.append((str(source), stat.S_IMODE(os.stat(source).st_mode)))
        return real_replace(source, target)

    monkeypatch.setattr(atomic_write.os, "replace", watching_replace)
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent"})

    assert observed
    assert all(mode == 0o600 for _, mode in observed), observed
    assert stat.S_IMODE(store.secrets_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.key_path.stat().st_mode) == 0o600


def test_a_corrupt_config_does_not_block_the_app_and_is_kept_for_recovery(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example"})
    store.config_path.write_text('{"school_url": "https://sch', encoding="utf-8")

    config = store.load_config()

    assert config["school_url"] == ""
    assert config["subjects"] == {}
    assert (tmp_path / "data" / "config.json.corrupt").exists()


def test_an_empty_config_does_not_block_the_app(tmp_path):
    store = Store(tmp_path / "data")
    store.config_path.write_text("", encoding="utf-8")

    assert store.load_config()["notify_events"]["letters"] is True


def test_a_corrupt_wizard_state_falls_back_to_the_first_step(tmp_path):
    store = Store(tmp_path / "data")
    store.save_wizard({"step": "children", "attempts": 2})
    store.wizard_path.write_text("{ nope", encoding="utf-8")

    assert store.load_wizard() == DEFAULT_WIZARD
    assert (tmp_path / "data" / "wizard.json.corrupt").exists()


def test_an_empty_wizard_state_is_still_a_valid_state(tmp_path):
    store = Store(tmp_path / "data")
    store.save_wizard({})

    assert store.load_wizard() == {}


@pytest.mark.parametrize(
    "attribute",
    [
        "seen_path",
        "absence_history_path",
        "letters_search_cache_path",
        "holidays_cache_path",
        "calendar_subscriptions_path",
        "calendar_snapshot_path",
        "calendar_state_path",
    ],
)
@pytest.mark.parametrize("content", ["", "{ half", "[1, 2]", "null"])
def test_a_corrupt_cache_file_never_blocks_the_app(tmp_path, attribute, content):
    store = Store(tmp_path / "data")
    path = getattr(store, attribute)
    path.write_text(content, encoding="utf-8")
    loaders = {
        "seen_path": store.load_seen,
        "absence_history_path": store.load_absence_history,
        "letters_search_cache_path": store.load_letters_search_cache,
        "holidays_cache_path": store.load_holidays_cache,
        "calendar_subscriptions_path": store.load_calendar_subscriptions,
        "calendar_snapshot_path": store.load_calendar_snapshot,
        "calendar_state_path": store.load_calendar_state,
    }

    assert loaders[attribute]() == {}


def test_a_corrupt_cache_file_can_be_written_again(tmp_path):
    store = Store(tmp_path / "data")
    store.holidays_cache_path.write_text("{ half", encoding="utf-8")

    store.save_holidays_cache({"2026": ["2026-10-05"]})

    assert store.load_holidays_cache() == {"2026": ["2026-10-05"]}


def test_a_truncated_secrets_file_asks_for_a_new_connection_instead_of_crashing(tmp_path):
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent", "password": "old"})
    store.secrets_path.write_text("gAAAAAB-truncated", encoding="ascii")

    assert store.load_secrets() == {}

    store.save_secrets({"username": "parent", "password": "fresh"})

    assert store.load_secrets()["password"] == "fresh"


def test_an_empty_secrets_file_asks_for_a_new_connection_instead_of_crashing(tmp_path):
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent"})
    store.secrets_path.write_text("", encoding="ascii")

    assert store.load_secrets() == {}


def test_a_corrupt_key_file_does_not_break_saving_secrets(tmp_path):
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent"})
    store.key_path.write_text("not-a-fernet-key", encoding="ascii")

    assert store.load_secrets() == {}

    store.save_secrets({"username": "parent"})

    assert store.load_secrets() == {"username": "parent"}
    assert crypto.is_valid_key(store.key_path.read_text(encoding="ascii").strip())


def test_a_corrupt_salt_file_does_not_break_saving_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ISERV_PASSPHRASE", "family-secret")
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent"})
    store.salt_path.write_text("!!!not-base64!!!", encoding="ascii")

    assert store.load_secrets() == {}

    store.save_secrets({"username": "parent"})

    assert store.load_secrets() == {"username": "parent"}
    assert crypto.is_valid_salt(store.salt_path.read_text(encoding="ascii").strip())


def test_a_valid_salt_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("ISERV_PASSPHRASE", "family-secret")
    store = Store(tmp_path / "data")
    store.save_secrets({"username": "parent"})
    salt = store.salt_path.read_text(encoding="ascii")

    assert store.load_secrets() == {"username": "parent"}
    assert store.salt_path.read_text(encoding="ascii") == salt


def test_written_files_stay_readable_json(tmp_path):
    store = Store(tmp_path / "data")
    store.save_config({"school_url": "https://school.example", "children": [{"id": "1"}]})

    raw = json.loads(store.config_path.read_text(encoding="utf-8"))

    assert raw["children"] == [{"id": "1"}]


def _raise_interrupted(*args, **kwargs):
    raise Interrupted("write interrupted")
