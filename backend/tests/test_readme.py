import hashlib
import pathlib
import re

import tests.test_no_personal_data as personal_data
from tests.test_no_personal_data import line_contains_forbidden_token

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SCREENSHOTS = ROOT / "docs" / "screenshots"
REFERENCE = re.compile(r"docs/screenshots/([A-Za-z0-9._-]+\.png)")


def readme_text():
    return README.read_text(encoding="utf-8")


def referenced_names():
    return set(REFERENCE.findall(readme_text()))


def stored_names():
    return {path.name for path in SCREENSHOTS.glob("*.png")}


def test_the_readme_is_there_and_shows_screenshots():
    assert README.is_file()
    assert SCREENSHOTS.is_dir()
    assert referenced_names(), "no screenshot reference found - the gallery or this pattern broke"


def test_the_readme_carries_no_personal_data():
    offenders = [
        f"README.md:{number}"
        for number, line in enumerate(readme_text().splitlines(), 1)
        if line_contains_forbidden_token(line.lower())
    ]
    assert offenders == []


def test_every_referenced_screenshot_exists():
    assert sorted(referenced_names() - stored_names()) == []


def test_every_stored_screenshot_is_used():
    assert sorted(stored_names() - referenced_names()) == []


def test_the_screenshot_folder_is_not_empty():
    assert stored_names()


def test_the_personal_data_check_still_bites(monkeypatch):
    canary = "zzzreadmecanary"
    monkeypatch.setattr(
        personal_data,
        "FORBIDDEN_LENGTHS",
        sorted(set(personal_data.FORBIDDEN_LENGTHS) | {len(canary)}),
    )
    monkeypatch.setattr(
        personal_data,
        "FORBIDDEN_HASH_SET",
        personal_data.FORBIDDEN_HASH_SET | {hashlib.sha256(canary.encode("utf-8")).hexdigest()},
    )
    assert line_contains_forbidden_token(f"a screenshot caption naming {canary} here")
    assert not line_contains_forbidden_token("a screenshot caption naming nobody here")
