import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

TRAILERS = (
    "co-authored-by:",
    "generated with [",
    "🤖 generated",
)

PRIVATE_TERMS = (
    "-planung",
    "handoff.md",
    "backlog.md",
)

TICKET_ID = re.compile(r"\[P\d{1,4}\]")


def _git(*args):
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        pytest.skip(f"git is not usable here: {result.stderr.strip()[:120]}")
    return result.stdout


def _has_git():
    return (ROOT / ".git").exists()


def _require_full_history():
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.fail(
            "this checkout carries only the newest commit, so a guard over the history would "
            "pass without looking at anything - give the checkout fetch-depth: 0"
        )


def _excluded_names():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    names = set()
    for line in text.splitlines():
        entry = line.strip().rstrip("/")
        if not entry or entry.startswith("#") or entry.startswith("!") or "*" in entry:
            continue
        names.add(entry.lower())
    return names


def test_nothing_the_ignore_list_excludes_is_tracked_anyway():
    if not _has_git():
        pytest.skip("no git checkout")
    excluded = _excluded_names()
    assert excluded, "the ignore list should not be empty"
    tracked = [line.strip() for line in _git("ls-files").splitlines() if line.strip()]
    offenders = [
        path
        for path in tracked
        if path.lower() in excluded or pathlib.PurePosixPath(path).name.lower() in excluded
    ]
    assert offenders == [], f"these are excluded but tracked anyway: {offenders}"


def test_no_commit_message_carries_a_trailer():
    if not _has_git():
        pytest.skip("no git checkout")
    _require_full_history()
    messages = _git("log", "--format=%B").lower()
    offenders = [marker for marker in TRAILERS if marker in messages]
    assert offenders == [], f"commit messages end with their last paragraph: {offenders}"


def test_every_commit_is_written_under_the_project_owner():
    if not _has_git():
        pytest.skip("no git checkout")
    _require_full_history()
    people = set()
    for line in _git("log", "--format=%an <%ae>%n%cn <%ce>").splitlines():
        entry = line.strip()
        if entry:
            people.add(entry)
    assert len(people) == 1, f"the history should carry one name, not {sorted(people)}"


def test_no_commit_subject_points_at_something_unpublished():
    if not _has_git():
        pytest.skip("no git checkout")
    _require_full_history()
    offenders = []
    for line in _git("log", "--format=%h\t%s").splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        if TICKET_ID.search(subject):
            offenders.append(f"{sha}: ticket id in '{subject[:60]}'")
        lowered = subject.lower()
        for term in PRIVATE_TERMS:
            if term in lowered:
                offenders.append(f"{sha}: '{term}' in '{subject[:60]}'")
    assert offenders == [], (
        f"a subject should describe the change, not where it was written down: {offenders}"
    )


def test_commit_subjects_stay_short_enough_to_read():
    if not _has_git():
        pytest.skip("no git checkout")
    _require_full_history()
    long_ones = []
    for line in _git("log", "--format=%h\t%s").splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        if len(subject) > 110:
            long_ones.append(f"{sha}: {len(subject)} characters")
    assert long_ones == [], f"these subjects read as prose rather than as a summary: {long_ones}"
