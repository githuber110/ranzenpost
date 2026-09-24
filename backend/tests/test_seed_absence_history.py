from app.iserv.absences import KIND_SICK
from app.seed_absence_history import main, seed
from app.store import Store


def test_seed_writes_an_entry_into_the_history_cache(tmp_path):
    store = Store(tmp_path / "data")
    entry = seed(store, 555, KIND_SICK, "2026-09-01", "2026-09-01")
    assert entry["id"] == 555
    assert entry["kind"] == KIND_SICK
    assert entry["deletable"] is False
    history = store.load_absence_history()
    assert history["555"]["from_date"] == "2026-09-01"


def test_seed_is_idempotent_and_does_not_override_a_newer_observation(tmp_path):
    store = Store(tmp_path / "data")
    seed(store, 555, KIND_SICK, "2026-09-01", "2026-09-01")
    store.save_absence_history(
        {**store.load_absence_history(), "555": {"id": 555, "status": "already-observed-live"}}
    )
    seed(store, 555, KIND_SICK, "2026-09-01", "2026-09-01")
    assert store.load_absence_history()["555"]["status"] == "already-observed-live"


def test_the_command_seeds_the_history_of_the_chosen_school(tmp_path, monkeypatch):
    store = Store(tmp_path / "data")
    first = store.add_connection("https://school-one.example", setup_complete=True)["id"]
    second = store.add_connection("https://school-two.example", setup_complete=True)["id"]
    monkeypatch.setenv("ISERV_DATA_DIR", str(tmp_path / "data"))
    main(["555", KIND_SICK, "2026-09-01", "2026-09-01"])
    main(["556", KIND_SICK, "2026-09-02", "2026-09-02", "--connection", second])
    assert list(store.connection_store(first).load_absence_history()) == ["555"]
    assert list(store.connection_store(second).load_absence_history()) == ["556"]
