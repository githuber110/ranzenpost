import json
import random
from datetime import date, timedelta
from pathlib import Path

from app import own_entries, period_grid

CASES = Path(__file__).resolve().parents[2] / "tests" / "own-entries-cases.json"
SEED = 344
FIRST_DAY = date(2026, 9, 21)
CHILDREN = ["sam", "mika"]


def random_entry(rng, index):
    repeat = rng.choice(own_entries.REPEATS)
    first = FIRST_DAY + timedelta(days=rng.randint(-10, 10))
    return {
        "id": f"e{index:02d}",
        "type": rng.choice(own_entries.TYPES),
        "name": f"Entry {index}",
        "start": period_grid.clock_of(rng.randrange(6 * 60, 22 * 60, 5)),
        "duration": rng.choice([5, 15, 30, 45, 60, 90, 150]),
        "repeat": repeat,
        "days": [0, 1, 2, 3, 4] if repeat == own_entries.REPEAT_DAILY else sorted(rng.sample(range(7), rng.randint(1, 3))),
        "interval": rng.randint(2, 4) if repeat == own_entries.REPEAT_WEEKS else 1,
        "date": (FIRST_DAY + timedelta(days=rng.randint(0, 20))).isoformat() if repeat == own_entries.REPEAT_ONCE else "",
        "from": "" if repeat == own_entries.REPEAT_ONCE else first.isoformat(),
        "until": "" if repeat == own_entries.REPEAT_ONCE else (first + timedelta(days=rng.randint(7, 40))).isoformat(),
        "holidays": True if repeat == own_entries.REPEAT_ONCE else rng.random() < 0.5,
        "child": rng.choice(["", "sam", "mika"]),
    }


def random_grid(rng):
    start = rng.randrange(7 * 60, 8 * 60 + 30, 5)
    rows = []
    for number in range(1, rng.randint(5, 10)):
        duration = rng.choice([45, 45, 45, 60, 90])
        rows.append({"number": number, "start": period_grid.clock_of(start), "end": period_grid.clock_of(start + duration), "duration": duration})
        start += duration + rng.choice([0, 5, 5, 10, 20])
    return rows


def random_profiles(rng, grid):
    numbers = [row["number"] for row in grid]
    return {child: {str(day): sorted(rng.sample(numbers, rng.randint(0, len(numbers)))) for day in range(5) if rng.random() < 0.9} for child in CHILDREN}


def rows_of(grid):
    return [{"number": row["number"], "start": period_grid.minutes_of(row["start"]), "end": period_grid.minutes_of(row["end"])} for row in grid]


def profile_map(profiles):
    return {child: {int(day): numbers for day, numbers in days.items()} for child, days in profiles.items()}


def build_cases():
    rng = random.Random(SEED)
    cases = []
    for index in range(30):
        grid = random_grid(rng)
        profiles = random_profiles(rng, grid)
        entries = [random_entry(rng, number) for number in range(rng.randint(1, 8))]
        rows = rows_of(grid)
        days = []
        for offset in range(0, 21, 3):
            day = FIRST_DAY + timedelta(days=offset)
            child = rng.choice(CHILDREN)
            free = rng.random() < 0.2
            periods = profile_map(profiles).get(child, {}).get(day.weekday(), [])
            spans = period_grid.spans_for(rows, periods)
            items = own_entries.resolve_day(entries, spans, day, child, free)
            days.append({
                "day": day.isoformat(),
                "child": child,
                "free": free,
                "periods": periods,
                "items": [[item["entry"]["id"], item["start"], item["end"], item["state"], item["number"]] for item in items],
            })
        statuses = {}
        for entry in entries:
            status = own_entries.entry_status(entry, rows, profile_map(profiles), CHILDREN)
            statuses[entry["id"]] = [status["state"], status["number"], status["start"], status["end"]]
        cases.append({"name": f"case {index}", "grid": grid, "profiles": profiles, "entries": entries, "days": days, "statuses": statuses})
    return {"seed": SEED, "children": CHILDREN, "cases": cases}


def rendered():
    return json.dumps(build_cases(), separators=(",", ":"), ensure_ascii=False) + "\n"


def test_the_shared_rule_cases_match_the_backend_rules():
    assert CASES.read_text(encoding="utf-8") == rendered(), "tests/own-entries-cases.json is stale, write it from rendered()"


if __name__ == "__main__":
    CASES.write_bytes(rendered().encode("utf-8"))
