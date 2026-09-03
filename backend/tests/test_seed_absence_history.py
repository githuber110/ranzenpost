from app.iserv.absences import KIND_SICK
from app.seed_absence_history import seed
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
