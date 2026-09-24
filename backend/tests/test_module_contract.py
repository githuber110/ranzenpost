import json
import re
from pathlib import Path

import pytest

from app import blocks, diagnostics, module_catalogue, modules
from app.store import Store

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_BLOCKS = ROOT / "frontend" / "blocks.js"
CARD = ROOT / "custom_components" / "ranzenpost" / "frontend" / "ranzenpost-card.js"
FIXTURE = ROOT / "backend" / "tests" / "e2e_fixture_app.py"
I18N = ROOT / "frontend" / "i18n"
LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
BLOCK_TEXT_PARTS = ("title", "explain", "when", "compact", "normal", "target")
CARD_TEXT_PARTS = ("", ".explain")
CATALOGUE_ENTRY = re.compile(r'\{ key: "([a-z_]+)", module: "([a-z]+)", area: "([a-z]+)", compact: (\d+), normal: (\d+), size: "([a-z]+)"')


def js_catalogue(path):
    source = path.read_text(encoding="utf-8")
    start = source.index("BLOCK_CATALOGUE = [")
    end = source.index("];", start)
    entries = CATALOGUE_ENTRY.findall(source[start:end])
    assert entries, f"{path.name}: no catalogue entries found"
    return [
        {"key": key, "module": module, "area": area, "compact": int(compact), "normal": int(normal), "size": size}
        for key, module, area, compact, normal, size in entries
    ]


def python_catalogue():
    return [
        {"key": block["key"], "module": block["module"], "area": block["area"], "compact": block["compact"], "normal": block["normal"], "size": block["size"]}
        for block in blocks.BLOCKS
    ]


def catalogue_slugs(module):
    slugs = set()
    for segment, names in modules.SEGMENTS.items():
        if module in names:
            slug = module_catalogue.slug_of(segment)
            if slug:
                slugs.add(slug)
    return slugs


def bundle(language):
    return json.loads((I18N / f"{language}.json").read_text(encoding="utf-8"))


def card_texts():
    source = CARD.read_text(encoding="utf-8")
    start = source.index("const TEXTS = {")
    end = source.index("\n  };", start)
    found = {}
    for language in LANGUAGES:
        block_start = source.index(f"\n    {language}: {{", start, end)
        block_end = source.index("\n    },", block_start)
        found[language] = dict(re.findall(r'"([^"]+)": "((?:[^"\\]|\\.)*)"', source[block_start:block_end]))
    return found


def test_the_three_catalogues_list_the_same_blocks_with_the_same_modules_and_limits():
    frontend = js_catalogue(FRONTEND_BLOCKS)
    card = js_catalogue(CARD)
    backend = python_catalogue()
    assert frontend == backend
    assert card == backend


def test_the_block_keys_are_unique_and_every_module_is_known():
    keys = [block["key"] for block in blocks.BLOCKS]
    assert len(keys) == len(set(keys))
    for block in blocks.BLOCKS:
        assert block["module"] in modules.MODULES, block["key"]


@pytest.mark.parametrize("module", modules.MODULES)
def test_every_module_has_a_catalogue_entry_with_an_official_name(module):
    slugs = catalogue_slugs(module)
    assert slugs, f"{module}: no IServ segment of this module resolves to a catalogue slug"
    assert any(module_catalogue.official_name(slug) for slug in slugs), f"{module}: no official name in the catalogue"


@pytest.mark.parametrize("module", modules.MODULES)
def test_every_module_has_at_least_one_block_in_every_catalogue(module):
    for name, listed in (("backend", python_catalogue()), ("frontend", js_catalogue(FRONTEND_BLOCKS)), ("card", js_catalogue(CARD))):
        assert any(block["module"] == module for block in listed), f"{name}: {module} has no block"


@pytest.mark.parametrize("module", modules.MODULES)
def test_every_module_has_a_probe(module):
    path, _params = modules.PROBES[module]
    assert path.startswith("/iserv/"), module


@pytest.mark.parametrize("module", modules.MODULES)
def test_the_fixture_renders_every_module_with_and_without_content(module):
    source = FIXTURE.read_text(encoding="utf-8")
    assert f"module_emptied(modules.{module.upper()})" in source, f"{module}: the fixture cannot be emptied with the e2e_empty cookie"


def test_the_fixture_reads_the_empty_cookie_per_request():
    source = FIXTURE.read_text(encoding="utf-8")
    assert 'EMPTY_COOKIE = "e2e_empty"' in source
    assert "EMPTY.set(read_cookie(scope, EMPTY_COOKIE))" in source


BLOCK_EMPTY_MARKER = {
    "today": 'block_emptied("today")',
    "next_lesson": 'block_emptied("next_lesson")',
    "week": 'block_emptied("week")',
    "letters": 'module_emptied(modules.LETTERS)',
    "noticeboard": 'block_emptied("noticeboard")',
    "absences": 'module_emptied(modules.ABSENCES)',
    "conferences": 'module_emptied(modules.CONFERENCES)',
    "chat": 'block_emptied("chat")',
    "holidays": 'block_emptied("holidays")',
    "changes": 'block_emptied("changes")',
}


@pytest.mark.parametrize("key", sorted(BLOCK_EMPTY_MARKER))
def test_the_fixture_can_empty_this_block_key_on_its_own(key):
    source = FIXTURE.read_text(encoding="utf-8")
    assert BLOCK_EMPTY_MARKER[key] in source, f"{key}: no independent e2e_empty gate found in the fixture"


def test_every_block_key_is_independently_emptiable():
    assert set(BLOCK_EMPTY_MARKER) == set(blocks.BLOCK_KEYS)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_block_has_its_texts_in_every_language(language):
    texts = bundle(language)
    missing = [
        f"blocks.{block['key']}.{part}"
        for block in blocks.BLOCKS
        for part in BLOCK_TEXT_PARTS
        if not str(texts.get(f"blocks.{block['key']}.{part}", "")).strip()
    ]
    assert missing == [], f"{language}.json lacks {missing}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_block_has_its_card_texts_in_every_language(language):
    texts = card_texts()[language]
    missing = [f"block.{block['key']}{part}" for block in blocks.BLOCKS for part in CARD_TEXT_PARTS if not texts.get(f"block.{block['key']}{part}")]
    assert missing == [], f"the card's {language} texts lack {missing}"


def test_every_navigation_area_maps_to_known_modules():
    for area, names in blocks.AREA_MODULES.items():
        assert names, area
        for name in names:
            assert name in modules.MODULES, f"{area}: {name}"
    for area in blocks.DEFAULT_NAVIGATION:
        assert area in blocks.AREA_MODULES


def test_the_catalogue_parser_still_bites(tmp_path):
    bogus = tmp_path / "bogus.js"
    bogus.write_text("const BLOCK_CATALOGUE = [\n  { key: 1 },\n];", encoding="utf-8")
    with pytest.raises(AssertionError):
        js_catalogue(bogus)


class ReportPages:
    def fetch(self, path, params=None):
        return ReportAnswer(path)


class ReportAnswer:
    def __init__(self, path):
        self.status_code = 200
        self.url = "https://school.example" + path
        self.text = "<html><body><form action='%s' method='post'><input name='field'></form></body></html>" % path
        self.content = self.text.encode("utf-8")
        self.headers = {"Content-Type": "text/html"}


class ReportConnection:
    id = "contract"
    store = None

    def modules(self):
        return dict(modules.default_registry(), checked_at=1_788_000_000)

    def iserv_session(self):
        return ReportPages()


class ReportService:
    def __init__(self, store):
        self.store = store

    def connections(self):
        return [ReportConnection()]


@pytest.fixture(scope="module")
def full_report(tmp_path_factory):
    store = Store(tmp_path_factory.mktemp("contract"))
    return diagnostics.build_report(ReportService(store), log_lines=[], clock=lambda: 1_788_000_000, versions={"app": "x", "home_assistant": "y"})


@pytest.mark.parametrize("module", modules.MODULES)
def test_every_module_contributes_a_row_and_a_structure_section_to_the_report(module, full_report):
    slugs = [slug for name, slug, _page in diagnostics.KNOWN_ROWS if name == module]
    assert slugs, f"{module}: no row in diagnostics.KNOWN_ROWS"
    for slug in slugs:
        assert f"| {slug} |" in full_report, f"{module}: the module table has no row {slug}"
        section = full_report.split(f"#### {slug} (", 1)
        assert len(section) == 2, f"{module}: the page structure has no section {slug}"
        assert "- Page: " in section[1].split("\n#### ", 1)[0], f"{module}: the section {slug} reads no page"
