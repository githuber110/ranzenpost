import argparse
import os

from .iserv.absences import KIND_LABEL_KEYS, KIND_LABELS, KINDS, SICK_LOCKED, SICK_LOCKED_KEY
from .store import Store


def build_entry(entry_id, kind, from_date, till_date, label=None, locked_reason=None):
    return {
        "id": entry_id,
        "kind": kind,
        "target": "",
        "label": label or KIND_LABELS.get(kind, ""),
        "label_key": "" if label else KIND_LABEL_KEYS.get(kind, ""),
        "target_key": "",
        "from_date": from_date,
        "till_date": till_date,
        "from_period": None,
        "till_period": None,
        "comment": "",
        "duty_to_report": False,
        "student_id": None,
        "status": "",
        "deletable": False,
        "locked_reason": locked_reason or SICK_LOCKED,
        "locked_reason_key": "" if locked_reason else SICK_LOCKED_KEY,
        "technical": {"id": entry_id},
    }


def seed(store, entry_id, kind, from_date, till_date):
    from .iserv.absences import seed_absence_history

    entry = build_entry(entry_id, kind, from_date, till_date)
    history = seed_absence_history(store.load_absence_history(), entry)
    store.save_absence_history(history)
    return history[str(entry_id)]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Seed the app-own absence history cache with one entry IServ no longer "
            "serves at all, so it stays visible for the remainder of its 30-day "
            "history window. Run once, manually, against the real data directory."
        )
    )
    parser.add_argument("id", type=int, help="the absence report id as last seen from IServ")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("from_date", help="YYYY-MM-DD")
    parser.add_argument("till_date", help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    store = Store(os.environ.get("ISERV_DATA_DIR", "/data"))
    seed(store, args.id, args.kind, args.from_date, args.till_date)


if __name__ == "__main__":
    main()
