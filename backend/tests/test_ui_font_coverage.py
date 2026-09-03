import json
import re
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BUNDLE_DIR = FRONTEND / "i18n"
FONT_DIR = FRONTEND / "fonts"
STYLESHEET = FRONTEND / "styles.css"

LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
UI_FAMILIES = ("Archivo", "Schibsted Grotesk")

FONT_FACE_BLOCK = re.compile(r"@font-face\s*\{([^}]*)\}", re.S)
DECLARATION = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;]+);")
SRC_URL = re.compile(r"url\(\s*\"([^\"]+)\"\s*\)")
RANGE_ITEM = re.compile(r"[Uu]\+([0-9A-Fa-f?]{1,6})(?:-([0-9A-Fa-f]{1,6}))?")

LATIN_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
ASCII_PUNCTUATION = " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
GERMAN_LETTERS = "ÄÖÜäöüß"
TURKISH_LETTERS = "ÇĞİIÖŞÜçğıöşü"
POLISH_LETTERS = "ĄĆĘŁŃÓŚŹŻąćęłńóśźż"
NAME_ACCENTS = "ÀÁÂÃÅÆÈÉÊËÌÍÎÏÑÒÓÔÕØÙÚÛÝàáâãåæèéêëìíîïñòóôõøùúûýÿ"
TYPOGRAPHY = "€§°·…–—„“”‚‘’«»‹›•±×÷©®™№"
UI_SYMBOLS = "→←↑↓"

GERMAN_DATA_BASELINE = frozenset(
    LATIN_LETTERS
    + DIGITS
    + ASCII_PUNCTUATION
    + GERMAN_LETTERS
    + TURKISH_LETTERS
    + POLISH_LETTERS
    + NAME_ACCENTS
    + TYPOGRAPHY
    + UI_SYMBOLS
)


def _collect_strings(node, sink):
    if isinstance(node, str):
        sink.update(node)
    elif isinstance(node, dict):
        for value in node.values():
            _collect_strings(value, sink)
    elif isinstance(node, list):
        for value in node:
            _collect_strings(value, sink)


def bundle_characters(language):
    path = BUNDLE_DIR / f"{language}.json"
    sink = set()
    _collect_strings(json.loads(path.read_text(encoding="utf-8")), sink)
    return sink


def required_characters(language):
    return {ch for ch in bundle_characters(language) | GERMAN_DATA_BASELINE if not ch.isspace()}


def parse_unicode_range(value):
    spans = []
    for item in value.split(","):
        match = RANGE_ITEM.search(item)
        if match is None:
            continue
        start_text, end_text = match.group(1), match.group(2)
        if "?" in start_text:
            spans.append((int(start_text.replace("?", "0"), 16), int(start_text.replace("?", "F"), 16)))
        elif end_text:
            spans.append((int(start_text, 16), int(end_text, 16)))
        else:
            spans.append((int(start_text, 16), int(start_text, 16)))
    return spans


def parse_font_faces():
    css = STYLESHEET.read_text(encoding="utf-8")
    faces = []
    for block in FONT_FACE_BLOCK.findall(css):
        declarations = {name.lower(): value.strip() for name, value in DECLARATION.findall(block)}
        family = declarations.get("font-family", "").strip().strip('"')
        url = SRC_URL.search(declarations.get("src", ""))
        if not family or url is None:
            continue
        spans = parse_unicode_range(declarations["unicode-range"]) if "unicode-range" in declarations else [(0, 0x10FFFF)]
        faces.append({"family": family, "path": (FRONTEND / url.group(1)).resolve(), "spans": spans})
    return faces


def font_codepoints(path):
    font = TTFont(str(path), lazy=True)
    codepoints = set()
    for table in font["cmap"].tables:
        codepoints.update(table.cmap.keys())
    font.close()
    return codepoints


def faces_claiming(faces, family, codepoint):
    return [
        face
        for face in faces
        if face["family"] == family
        and any(start <= codepoint <= end for start, end in face["spans"])
    ]


def test_font_faces_reference_existing_files():
    faces = parse_font_faces()
    assert faces, "no @font-face rule found in styles.css"
    missing = [str(face["path"]) for face in faces if not face["path"].is_file()]
    assert missing == [], f"@font-face points at missing files: {missing}"


def test_ui_families_are_declared():
    families = {face["family"] for face in parse_font_faces()}
    assert set(UI_FAMILIES) <= families, f"missing @font-face families: {sorted(set(UI_FAMILIES) - families)}"


def test_every_language_is_fully_covered_by_the_shipped_fonts():
    faces = parse_font_faces()
    coverage = {face["path"]: font_codepoints(face["path"]) for face in faces if face["path"].is_file()}
    failures = []
    for language in LANGUAGES:
        for character in sorted(required_characters(language)):
            codepoint = ord(character)
            for family in UI_FAMILIES:
                claiming = faces_claiming(faces, family, codepoint)
                if not claiming:
                    failures.append(
                        f"{language}: U+{codepoint:04X} {character!r} is claimed by no @font-face of family {family!r}"
                    )
                    continue
                if not any(codepoint in coverage.get(face["path"], set()) for face in claiming):
                    files = ", ".join(face["path"].name for face in claiming)
                    failures.append(
                        f"{language}: U+{codepoint:04X} {character!r} missing from {family!r} -> {files}"
                    )
    assert failures == [], "font coverage gaps:\n" + "\n".join(failures[:60]) + f"\n({len(failures)} total)"


def test_shipped_fonts_carry_a_licence():
    licences = sorted(path.name for path in FONT_DIR.glob("OFL*.txt"))
    assert licences, "no OFL licence file next to the shipped web fonts"
    for name in licences:
        assert (FONT_DIR / name).stat().st_size > 0, f"empty licence file {name}"


def test_no_web_font_is_shipped_without_being_referenced():
    referenced = {face["path"] for face in parse_font_faces()}
    orphans = sorted(path.name for path in FONT_DIR.glob("*.woff2") if path.resolve() not in referenced)
    assert orphans == [], f"web fonts shipped but never referenced from styles.css: {orphans}"
