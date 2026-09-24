import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNNER = "node scripts/run-frontend-tests.mjs"


def scripts():
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]


def test_every_full_vitest_suite_goes_through_the_runner_that_counts_the_files():
    listed = scripts()
    assert listed["test"] == RUNNER
    assert listed["test:card"] == RUNNER + " --suite=card"


def test_the_runner_knows_every_vitest_config_of_the_repo():
    source = (ROOT / "scripts" / "run-frontend-tests.mjs").read_text(encoding="utf-8")
    configs = sorted(path.name for path in ROOT.glob("vitest*.config.js") if path.name != "vitest.config.js")
    for name in configs:
        assert re.search(re.escape(name), source), f"{name} has no suite in the counting runner"


def test_the_full_matrix_runs_the_card_through_the_counting_script():
    source = (ROOT / "scripts" / "run-all-tests.mjs").read_text(encoding="utf-8")
    assert '"test:card"' in source
