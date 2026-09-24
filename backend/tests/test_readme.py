import hashlib
import pathlib
import re

import tests.test_no_personal_data as personal_data
from app import modules
from tests.test_no_personal_data import line_contains_forbidden_token

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
README_DE = ROOT / "README.de.md"
READMES = {"README.md": README, "README.de.md": README_DE}
SCREENSHOTS = ROOT / "docs" / "screenshots"
REFERENCE = re.compile(r"docs/screenshots/([A-Za-z0-9._-]+\.png)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
IMAGE_TARGET = re.compile(r"""(?:<img[^>]*\ssrc|<source[^>]*\ssrcset)="([^"]+)"|!\[[^\]]*\]\(([^)\s]+)""")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_TARGET = re.compile(r"""<a[^>]*\shref="([^"]+)"|\[[^\]]*\]\(([^)\s]+)\)""")
SENTENCE_DASHES = (" - ", " – ", " — ")
BULLET = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
FENCE = "```"
MODULES_HEADING = "Supported IServ modules"
LANGUAGE_LINE = "[English](README.md) | [Deutsch](README.de.md)"


def readme_text():
    return README.read_text(encoding="utf-8")


def text_of(path):
    return path.read_text(encoding="utf-8")


def referenced_names(text=None):
    return set(REFERENCE.findall(text if text is not None else readme_text()))


def stored_names():
    return {path.name for path in SCREENSHOTS.glob("*.png")}


def prose_lines(text):
    inside_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(FENCE):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        yield number, line


def headings(text):
    return [(len(match.group(1)), match.group(2)) for _, line in prose_lines(text) if (match := HEADING.match(line))]


def targets(pattern, text):
    return [first or second for first, second in pattern.findall(text)]


def image_targets(text):
    return targets(IMAGE_TARGET, text)


def link_targets(text):
    return targets(LINK_TARGET, MARKDOWN_IMAGE.sub("image", text))


def module_table(text):
    heading_index = [title for _, title in headings(readme_text())].index(MODULES_HEADING)
    seen = -1
    rows = []
    collecting = False
    for _, line in prose_lines(text):
        if HEADING.match(line):
            seen += 1
            collecting = seen == heading_index
            continue
        if collecting and line.lstrip().startswith("|") and not TABLE_SEPARATOR.match(line):
            rows.append(line)
    return rows[1:]


def sentence_dash_offenders(name, text):
    offenders = []
    for number, line in prose_lines(text):
        if TABLE_SEPARATOR.match(line):
            continue
        body = BULLET.sub("", line, count=1)
        if any(dash in body for dash in SENTENCE_DASHES):
            offenders.append(f"{name}:{number}")
    return offenders


def test_the_readme_is_there_and_shows_screenshots():
    assert README.is_file()
    assert README_DE.is_file()
    assert SCREENSHOTS.is_dir()
    assert referenced_names(), "no screenshot reference found - the gallery or this pattern broke"


def test_the_readmes_carry_no_personal_data():
    offenders = [
        f"{name}:{number}"
        for name, path in READMES.items()
        for number, line in enumerate(text_of(path).splitlines(), 1)
        if line_contains_forbidden_token(line.lower())
    ]
    assert offenders == []


def test_every_referenced_screenshot_exists():
    assert sorted(referenced_names() - stored_names()) == []


def test_every_stored_screenshot_is_used():
    assert sorted(stored_names() - referenced_names()) == []


def test_the_screenshot_folder_is_not_empty():
    assert stored_names()


def test_both_readmes_start_with_the_language_line():
    for name, path in READMES.items():
        assert text_of(path).splitlines()[0] == LANGUAGE_LINE, name


def test_both_readmes_have_the_same_heading_structure():
    english = [level for level, _ in headings(readme_text())]
    german = [level for level, _ in headings(text_of(README_DE))]
    assert english, "no headings found in README.md"
    assert german == english


def test_both_readmes_show_the_same_images_in_the_same_order():
    english = image_targets(readme_text())
    german = image_targets(text_of(README_DE))
    assert english, "no image found in README.md"
    assert german == english


def test_both_readmes_link_the_same_targets_in_the_same_order():
    english = link_targets(readme_text())
    german = link_targets(text_of(README_DE))
    assert english, "no link found in README.md"
    assert german == english


def test_both_readmes_reference_the_same_screenshots():
    assert referenced_names(text_of(README_DE)) == referenced_names()


def test_no_readme_sentence_carries_a_dash():
    offenders = [
        offender for name, path in READMES.items() for offender in sentence_dash_offenders(name, text_of(path))
    ]
    assert offenders == [], f"a dash inside a sentence; use a comma, a colon or a full stop: {offenders}"


def test_every_known_module_is_in_the_module_table_of_both_readmes():
    for name, path in READMES.items():
        rows = module_table(text_of(path))
        assert len(rows) >= len(modules.MODULES), f"{name}: the module table has {len(rows)} rows"
        for module in modules.MODULES:
            segment = modules.PROBES[module][0].split("/")[2]
            assert any(f"`{segment}`" in row for row in rows), f"{name}: no table row names {module} ({segment})"


def test_the_module_table_finder_still_bites():
    rows = module_table(readme_text())
    assert rows
    assert not module_table("# Something else\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")


def test_the_link_finder_sees_the_target_behind_a_badge():
    assert link_targets("[![Build](https://x/badge.svg)](https://x/run) and [docs](DOCS.md)") == ["https://x/run", "DOCS.md"]
    assert image_targets('<img src="a.png"> ![b](b.png) <source srcset="c.png">') == ["a.png", "b.png", "c.png"]


def test_the_dash_check_still_bites():
    assert sentence_dash_offenders("x", "A sentence - with a dash.") == ["x:1"]
    assert sentence_dash_offenders("x", "A sentence – with a dash.") == ["x:1"]
    assert sentence_dash_offenders("x", "A sentence — with a dash.") == ["x:1"]
    assert sentence_dash_offenders("x", "- A bullet without a dash inside.") == []
    assert sentence_dash_offenders("x", "| --- | --- |") == []
    assert sentence_dash_offenders("x", "```\na - b\n```") == []


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
