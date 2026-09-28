import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from extract_changelog_section import SectionNotFound, extract_section

CHANGELOG = REPO_ROOT / "iserv_connector" / "CHANGELOG.md"


def _top_heading(text: str) -> str:
    match = re.search(r"^## (\S+)", text, re.MULTILINE)
    assert match, "the changelog has no version heading"
    return match.group(1)


def test_extracts_exactly_the_current_release_section():
    text = CHANGELOG.read_text(encoding="utf-8")
    version = _top_heading(text)
    section = extract_section(text, version)

    assert section.strip()
    assert "### " in section
    assert not re.search(r"^## ", section, flags=re.MULTILINE), "the next release must not leak into the notes"
    assert f"## {version}" not in section
    bodies = re.split(r"^### .+$", section, flags=re.MULTILINE)[1:]
    assert all(body.strip() for body in bodies), "an empty heading must be left out, not printed empty"


def test_fails_on_a_version_the_changelog_does_not_have():
    text = CHANGELOG.read_text(encoding="utf-8")
    with pytest.raises(SectionNotFound):
        extract_section(text, "0.0.0-does-not-exist")


def _german_only_labels():
    german = json.loads((REPO_ROOT / "frontend" / "i18n" / "de.json").read_text(encoding="utf-8"))
    english = json.loads((REPO_ROOT / "frontend" / "i18n" / "en.json").read_text(encoding="utf-8"))
    card = (REPO_ROOT / "custom_components" / "ranzenpost" / "frontend" / "ranzenpost-card.js").read_text(encoding="utf-8")
    card_german = card[: card.index('"block.showAll": "Show all"')]
    labels = {value for key, value in german.items() if value != english.get(key)}
    labels |= set(re.findall(r'"block\.\w+": "([^"]+)"', card_german))
    return {label for label in labels if len(label) > 3}


def test_the_current_release_notes_quote_english_labels_only():
    text = CHANGELOG.read_text(encoding="utf-8")
    section = extract_section(text, _top_heading(text))
    quoted = set(re.findall(r'"([^"]+)"', section))
    assert sorted(quoted & _german_only_labels()) == []
