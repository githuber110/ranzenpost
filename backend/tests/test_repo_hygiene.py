import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

INTERNAL_FILES = (
    "claude.md",
    "agents.md",
    "gemini.md",
    "copilot-instructions.md",
    ".cursorrules",
    ".aider.conf.yml",
    "handoff.md",
    "backlog.md",
    "prompts.md",
)

ASSISTANT_TRAILERS = (
    "co-authored-by: claude",
    "co-authored-by: chatgpt",
    "co-authored-by: copilot",
    "generated with [claude",
    "🤖 generated",
)

INTERNAL_TALK = (
    "ranzenpost-planung",
    "planungs-repo",
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


def test_no_internal_working_notes_are_tracked():
    if not _has_git():
        pytest.skip("no git checkout")
    tracked = [line.strip() for line in _git("ls-files").splitlines() if line.strip()]
    offenders = [
        path
        for path in tracked
        if pathlib.PurePosixPath(path).name.lower() in INTERNAL_FILES
    ]
    assert offenders == [], (
        "these files describe how the project is worked on, not what it does, and they name "
        f"paths that are meant to stay private: {offenders}"
    )


def test_no_commit_message_carries_an_assistant_signature():
    if not _has_git():
        pytest.skip("no git checkout")
    _require_full_history()
    messages = _git("log", "--format=%B").lower()
    offenders = [marker for marker in ASSISTANT_TRAILERS if marker in messages]
    assert offenders == [], (
        "the published history should read as ordinary project work; these markers say "
        f"otherwise: {offenders}"
    )


def test_no_commit_message_leaks_the_internal_process():
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
        for term in INTERNAL_TALK:
            if term in lowered:
                offenders.append(f"{sha}: '{term}' in '{subject[:60]}'")
    assert offenders == [], (
        "commit subjects are public and should describe the change, not the private "
        f"planning that led to it: {offenders}"
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
