import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
CARD = ROOT / "custom_components" / "ranzenpost" / "frontend" / "ranzenpost-card.js"
STYLESHEETS = ("styles.css", "wizard.css", "pdfviewer.css")
TOKEN_BLOCK_HEADS = (":root", ":root[", "[data-theme=", "@media (prefers-color-scheme")
NAMED_COLOURS = (
    "white", "black", "red", "green", "blue", "yellow", "orange", "purple", "pink", "gray", "grey",
    "silver", "maroon", "navy", "teal", "olive", "lime", "aqua", "fuchsia", "cyan", "magenta", "brown",
)
LITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\b(?:rgb|rgba|hsl|hsla)\("
    r"|(?<![\w-])(?:" + "|".join(NAMED_COLOURS) + r")(?![\w-])"
)
VAR_FALLBACK = re.compile(r"var\(\s*--[\w-]+\s*,\s*[^)]*\)")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
ALLOWED = {
    ("styles.css", ".cal-qr-frame", "#ffffff"): "a QR code needs a white quiet zone so phone cameras can scan it in both themes",
    ("styles.css", ".viewer-overlay", "rgba("): "the file viewer stage is a near-opaque dark backdrop in both themes, like a cinema",
    ("pdfviewer.css", ".pdfv", "rgba("): "the PDF viewer stage is a near-opaque dark backdrop in both themes, like a cinema",
    ("pdfviewer.css", ".pdfv-page", "#ffffff"): "a PDF page is paper and stays white so its own colours read as printed",
}


def strip_token_blocks(css):
    kept = []
    depth = 0
    skipping = False
    for line in css.splitlines():
        stripped = line.strip()
        if depth == 0 and any(stripped.startswith(head) for head in TOKEN_BLOCK_HEADS):
            skipping = True
        if skipping:
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                skipping = False
                depth = 0
            continue
        kept.append(line)
    return "\n".join(kept)


def selector_of(lines, index):
    for cursor in range(index, -1, -1):
        text = lines[cursor].strip()
        if text.endswith("{"):
            return text[:-1].strip()
    return ""


def offenders_in(name, css):
    lines = COMMENT.sub("", css).splitlines()
    found = []
    for index, line in enumerate(lines):
        scanned = VAR_FALLBACK.sub("", line)
        for match in LITERAL.finditer(scanned):
            literal = match.group(0)
            key = (name, selector_of(lines, index), literal if literal.startswith("rgb") or literal.startswith("hsl") else literal.lower())
            if key in ALLOWED:
                continue
            found.append(f"{name}:{index + 1} {key[1]} {literal}")
    return found


def card_styles():
    source = CARD.read_text(encoding="utf-8")
    styles = []
    for name in ("const STYLE = `", "const EDITOR_STYLE = `"):
        start = source.index(name) + len(name)
        end = source.index("`;", start)
        styles.append(source[start:end])
    return "\n".join(styles)


@pytest.mark.parametrize("name", STYLESHEETS)
def test_the_app_stylesheets_take_every_colour_from_a_token(name):
    css = strip_token_blocks((FRONTEND / name).read_text(encoding="utf-8"))
    assert offenders_in(name, css) == []


def test_the_card_stylesheet_takes_every_colour_from_a_token():
    css = strip_token_blocks(card_styles())
    assert offenders_in("ranzenpost-card.js", css) == []


def test_every_allowed_literal_is_still_there_and_carries_a_reason():
    for (name, selector, literal), reason in ALLOWED.items():
        css = strip_token_blocks((FRONTEND / name).read_text(encoding="utf-8"))
        block = css[css.index(selector + " {"):]
        block = block[: block.index("}")]
        assert literal in block.lower() or literal in block, f"{name} {selector} no longer carries {literal}, drop the allow-list line"
        assert len(reason.split()) >= 8, f"{name} {selector}: the reason must let a reader weigh it"


def test_the_colour_guard_still_bites():
    planted = ".x {\n  color: #fff;\n}\n.y {\n  background: rgb(1, 2, 3);\n}\n.z {\n  border-color: white;\n}\n"
    assert len(offenders_in("planted.css", planted)) == 3
    assert offenders_in("planted.css", ".x {\n  color: var(--ink, #fff);\n}\n") == []
    assert offenders_in("planted.css", strip_token_blocks(":root {\n  --ink: #fff;\n}\n.x {\n  color: var(--ink);\n}\n")) == []
