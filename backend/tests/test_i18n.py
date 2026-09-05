import json
import re
from pathlib import Path

from tests.frontend_sources import (
    FRONTEND,
    ROOT,
    VENDOR_EXEMPT_PATHS,
    is_vendor_exempt,
    script_names,
    stylesheet_names,
)

BUNDLE_DIR = FRONTEND / "i18n"
BASE_LANGUAGE = "de"
LANGUAGES = ("de", "en", "ar", "tr", "ru", "uk")
PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")

SCANNED_FILES = script_names
STRING_LITERAL = re.compile(
    r'"(?:[^"\\\n]|\\.)*"'
    r"|'(?:[^'\\\n]|\\.)*'"
    r"|`(?:[^`\\]|\\.)*`",
    re.S,
)
GERMAN_LETTERS = re.compile(r"[äöüßÄÖÜ]")
GERMAN_WORDS = (
    "aber", "alle", "alles", "auch", "aus", "bei", "bereits", "bitte", "damit", "dann",
    "das", "dein", "deine", "deinem", "deiner", "dem", "den", "des", "dich",
    "diese", "diesem", "diesen", "dieser", "dieses", "eine", "einem", "einen", "einer",
    "eines", "erneut", "gib", "hier", "ihre", "ist", "jetzt", "kann", "kein", "keine",
    "keinen", "klappt", "können", "leer", "mehr", "muss", "müssen", "nicht", "noch",
    "nur", "oder", "ohne", "schon", "sich", "sind", "sobald", "sollte", "und", "vom",
    "von", "warten", "wenn", "werden", "wieder", "wird", "wurde", "zum", "zur",
    "abbrechen", "abgelehnt", "archivieren", "beitrag", "brief", "briefe",
    "eingereicht", "einstellungen", "fertig", "gelesen", "gemeldet", "genehmigt",
    "heute", "melden", "meldung", "morgen", "nummer", "passwort", "schule",
    "sichern", "speichern", "stunde", "stunden", "termin", "termine", "uhr",
    "ungelesen", "wechseln", "wiederherstellen", "woche",
)
GERMAN_WORD_PATTERN = re.compile(r"(?<![\w])(" + "|".join(GERMAN_WORDS) + r")(?![\w])", re.IGNORECASE)
ALLOWED_LITERALS = set()


def load_bundle(language):
    path = BUNDLE_DIR / f"{language}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def base_key(key):
    head, _, tail = key.rpartition(".")
    return head if head and tail in PLURAL_CATEGORIES else key


def plural_families(bundle):
    families = {}
    for key in bundle:
        head, _, tail = key.rpartition(".")
        if head and tail in PLURAL_CATEGORIES:
            families.setdefault(head, set()).add(tail)
    return families


def available_bundles():
    return {language: load_bundle(language) for language in LANGUAGES if load_bundle(language) is not None}


def test_every_supported_language_ships_a_bundle():
    missing = [language for language in LANGUAGES if load_bundle(language) is None]
    assert missing == [], f"frontend/i18n is missing a bundle for {missing}"


def test_base_bundle_exists_and_is_flat():
    bundle = load_bundle(BASE_LANGUAGE)
    assert bundle, "frontend/i18n/de.json is the single source of truth and must not be empty"
    assert all(isinstance(value, str) for value in bundle.values()), "language files stay flat: key -> string"


def test_no_empty_values_in_any_bundle():
    offenders = []
    for language, bundle in available_bundles().items():
        offenders.extend(f"{language}:{key}" for key, value in bundle.items() if not value.strip())
    assert offenders == []


def test_every_bundle_carries_the_same_keys_as_the_base():
    base = load_bundle(BASE_LANGUAGE)
    expected = {base_key(key) for key in base}
    for language, bundle in available_bundles().items():
        found = {base_key(key) for key in bundle}
        assert found - expected == set(), f"{language}.json has keys the base does not define"
        assert expected - found == set(), f"{language}.json is missing keys the base defines"


def test_plural_families_provide_at_least_the_other_category():
    for language, bundle in available_bundles().items():
        for family, categories in plural_families(bundle).items():
            assert "other" in categories, f"{language}.json: plural family {family} has no 'other' form"


def test_base_bundle_placeholders_survive_in_every_translation():
    base = load_bundle(BASE_LANGUAGE)
    placeholder = re.compile(r"\{(\w+)\}")
    for language, bundle in available_bundles().items():
        if language == BASE_LANGUAGE:
            continue
        for key, value in bundle.items():
            if key not in base:
                continue
            assert set(placeholder.findall(value)) == set(placeholder.findall(base[key])), (
                f"{language}.json:{key} does not carry the same placeholders as the base"
            )


def hardcoded_german(text):
    offenders = []
    for match in STRING_LITERAL.finditer(text):
        literal = match.group(0)
        if literal in ALLOWED_LITERALS:
            continue
        body = literal[1:-1]
        if GERMAN_LETTERS.search(body) or GERMAN_WORD_PATTERN.search(body):
            offenders.append(literal)
    return offenders


def find_hardcoded_german():
    offenders = []
    for name in SCANNED_FILES():
        path = FRONTEND / name
        if is_vendor_exempt(path):
            continue
        text = path.read_text(encoding="utf-8")
        for match in STRING_LITERAL.finditer(text):
            literal = match.group(0)
            if literal in ALLOWED_LITERALS:
                continue
            body = literal[1:-1]
            if GERMAN_LETTERS.search(body) or GERMAN_WORD_PATTERN.search(body):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{name}:{line} {literal[:70]}")
    return offenders


def test_frontend_carries_no_hardcoded_german_ui_strings():
    assert find_hardcoded_german() == []


def test_the_german_tripwire_still_catches_a_planted_string():
    assert hardcoded_german('const label = "Bitte ein Datum wählen.";')
    assert hardcoded_german('toast("Der Brief wurde archiviert");')
    assert hardcoded_german("const hint = `Woche ${week}`;")
    assert hardcoded_german('el("span", {}, "Einstellungen")')
    assert hardcoded_german('const x = "api/absences";') == []
    assert hardcoded_german('t("absence.problem.subject")') == []


def test_the_allowlist_is_the_only_escape_hatch():
    planted = '"Bitte warten"'
    source = f"const x = {planted};"
    assert hardcoded_german(source)
    ALLOWED_LITERALS.add(planted)
    try:
        assert hardcoded_german(source) == []
    finally:
        ALLOWED_LITERALS.discard(planted)


def test_every_translation_key_used_in_the_frontend_exists_in_the_base_bundle():
    base = load_bundle(BASE_LANGUAGE)
    families = set(plural_families(base))
    call = re.compile(r'\b(?:t|label|tCount)\(\s*"([a-z][\w.]*)"')
    missing = []
    for name in SCANNED_FILES():
        text = (FRONTEND / name).read_text(encoding="utf-8")
        for match in call.finditer(text):
            key = match.group(1)
            if key in base or key in families:
                continue
            missing.append(f"{name}: {key}")
    assert missing == []


def test_index_html_static_translation_hooks_resolve():
    base = load_bundle(BASE_LANGUAGE)
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    keys = re.findall(r'data-i18n="([^"]+)"', html)
    assert keys, "index.html must mark its pre-boot text for translation"
    assert [key for key in keys if key not in base] == []


STYLESHEETS = stylesheet_names
PHYSICAL_PROPERTY = re.compile(
    r"(?<![\w-])(margin|padding|border)-(left|right)\s*:"
    r"|(?<![\w-])text-align\s*:\s*(left|right)\b"
    r"|(?<![\w-])(left|right)\s*:"
    r"|(?<![\w-])float\s*:"
)
CENTERED_OFFSET = re.compile(r"^(left|right)\s*:$")
INLINE_ROTATE = re.compile(r"transform\s*:\s*rotate")

CENTERED_BARS = {
    ".toast": "one centred bar, left: 50% plus translateX(-50%), symmetric in both directions",
    ".select-bar": "one centred bar, left: 50% plus translateX(-50%), symmetric in both directions",
    ".tabbar": "one centred bar, left: 50% plus translateX(-50%), symmetric in both directions",
}

JS_SOURCES = script_names
JS_PHYSICAL_STYLE = re.compile(
    r"style\s*:\s*[\"'`][^\"'`]*?(?<![\w-])(left|right|float)\s*:"
    r"|\.style\.(left|right|marginLeft|marginRight|paddingLeft|paddingRight|borderLeft|borderRight|float|boxShadow|textAlign)\s*="
    r"|setProperty\(\s*[\"'](left|right|float|margin-left|margin-right|box-shadow|text-align)[\"']"
)


def rule_selector(text, index):
    head = text.rfind("}", 0, index)
    start = text.rfind("{", 0, index)
    if start == -1:
        return ""
    return " ".join(text[head + 1 : start].split())


def find_physical_direction_rules():
    offenders = []
    for name in STYLESHEETS():
        text = (FRONTEND / name).read_text(encoding="utf-8")
        for match in PHYSICAL_PROPERTY.finditer(text):
            token = " ".join(match.group(0).split())
            selector = rule_selector(text, match.start())
            if CENTERED_OFFSET.match(token) and any(bar in selector for bar in CENTERED_BARS):
                continue
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{name}:{line} {selector} -> {token}")
    return offenders


def find_physical_inline_styles():
    offenders = []
    for name in JS_SOURCES():
        path = FRONTEND / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in JS_PHYSICAL_STYLE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{name}:{line} {match.group(0)[:60]}")
    return offenders


def test_stylesheets_use_logical_properties_so_arabic_mirrors():
    assert find_physical_direction_rules() == []


def test_no_script_sets_a_physical_direction_in_an_inline_style():
    assert find_physical_inline_styles() == [], (
        "a physical offset set from JavaScript is out of reach of [dir=rtl] - give the "
        "node a class and let the stylesheet mirror it"
    )


def test_every_centred_bar_exception_carries_a_reason():
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    for selector, reason in CENTERED_BARS.items():
        assert selector in css, f"{selector} is no longer part of the stylesheet"
        assert len(reason.split()) >= 8, f"{selector} needs a reason a reader can weigh"


def test_the_direction_tripwire_still_catches_a_planted_rule():
    assert PHYSICAL_PROPERTY.search(".row { padding-left: 8px; }")
    assert PHYSICAL_PROPERTY.search(".row { text-align: left; }")
    assert PHYSICAL_PROPERTY.search(".row { border-right: 1px solid red; }")
    assert PHYSICAL_PROPERTY.search(".row { left: -8px; }")
    assert PHYSICAL_PROPERTY.search(".row { right: 0; }")
    assert PHYSICAL_PROPERTY.search(".row { float: left; }")
    assert PHYSICAL_PROPERTY.search(".row { padding-inline-start: 8px; }") is None
    assert PHYSICAL_PROPERTY.search(".row { text-align: start; }") is None
    assert PHYSICAL_PROPERTY.search(".row { inset-inline-start: 0; }") is None


def test_the_inline_style_tripwire_still_catches_a_planted_assignment():
    assert JS_PHYSICAL_STYLE.search('el("div", { style: "position:absolute;left:-9999px" })')
    assert JS_PHYSICAL_STYLE.search("cell.style.boxShadow = `inset 3px 0 0 0 ${color}`;")
    assert JS_PHYSICAL_STYLE.search("node.style.marginLeft = \"4px\";")
    assert JS_PHYSICAL_STYLE.search('node.style.setProperty("margin-left", "4px");')
    assert JS_PHYSICAL_STYLE.search('el("div", { style: "margin-top:12px" })') is None
    assert JS_PHYSICAL_STYLE.search('node.style.setProperty("--subject-bar", color);') is None


def test_no_inline_rotation_survives_where_rtl_cannot_reach_it():
    offenders = []
    for name in SCANNED_FILES():
        text = (FRONTEND / name).read_text(encoding="utf-8")
        for match in INLINE_ROTATE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{name}:{line}")
    assert offenders == [], "rotate() belongs in the stylesheet, where [dir=rtl] can mirror it"


def test_the_stylesheet_mirrors_every_direction_sensitive_class_it_defines():
    css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
    for selector in (".chev-prev", ".chev-next", ".chev-toggle", ".header-back", ".swap .arrow"):
        assert f'[dir="rtl"] {selector}' in css, f"{selector} has no right-to-left counterpart"


def test_the_vendor_exemption_covers_only_the_vendor_directory():
    assert VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert is_vendor_exempt(FRONTEND / "vendor" / "pdfjs" / "pdf.mjs")
    assert is_vendor_exempt(FRONTEND / "vendor" / "readme.md")
    assert not is_vendor_exempt(FRONTEND / "app.js")
    assert not is_vendor_exempt(FRONTEND / "vendored.js")
    assert not is_vendor_exempt(ROOT / "backend" / "vendor" / "pdf.mjs")
    assert find_hardcoded_german() == []
