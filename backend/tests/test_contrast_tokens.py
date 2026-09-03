import pathlib
import re

from app.mapping import DEFAULT_COLORS

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"
STYLES = FRONTEND / "styles.css"

ROOT_BLOCK_RE = re.compile(r":root\s*\{(.*?)\n\}", re.DOTALL)
MEDIA_DARK_BLOCK_RE = re.compile(
    r'@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{(.*?)\n  \}\n\}',
    re.DOTALL,
)
ATTR_DARK_BLOCK_RE = re.compile(r':root\[data-theme="dark"\]\s*\{(.*?)\n\}', re.DOTALL)
TOKEN_RE = re.compile(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6});")


def parse_tokens(block_text):
    return dict(TOKEN_RE.findall(block_text))


def load_css():
    return STYLES.read_text(encoding="utf-8")


def extract_light_tokens(css):
    match = ROOT_BLOCK_RE.search(css)
    assert match, "bare :root block not found"
    return parse_tokens(match.group(1))


def extract_dark_blocks(css):
    media = MEDIA_DARK_BLOCK_RE.search(css)
    attr = ATTR_DARK_BLOCK_RE.search(css)
    assert media, "prefers-color-scheme dark block not found"
    assert attr, "data-theme dark block not found"
    return parse_tokens(media.group(1)), parse_tokens(attr.group(1))


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def channel_to_linear(channel):
    c = channel / 255
    if c <= 0.03928:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color):
    r, g, b = hex_to_rgb(hex_color)
    r, g, b = (channel_to_linear(c) for c in (r, g, b))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a, hex_b):
    lum_a = relative_luminance(hex_a)
    lum_b = relative_luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


CSS = load_css()
LIGHT = extract_light_tokens(CSS)
DARK_MEDIA, DARK_ATTR = extract_dark_blocks(CSS)

PERCENT_RE = re.compile(r"--([a-z0-9-]+):\s*(\d+)%;")

SUBJECT_COLORS = DEFAULT_COLORS


def parse_percents(block_text):
    return {name: int(value) for name, value in PERCENT_RE.findall(block_text)}


def extract_percents(css):
    light = parse_percents(ROOT_BLOCK_RE.search(css).group(1))
    media = parse_percents(MEDIA_DARK_BLOCK_RE.search(css).group(1))
    attr = parse_percents(ATTR_DARK_BLOCK_RE.search(css).group(1))
    assert media["subject-fill"] == attr["subject-fill"], "both dark blocks must share one subject fill"
    return light, attr


LIGHT_PCT, DARK_PCT = extract_percents(CSS)
SUBJECT_LABEL_PCT = LIGHT_PCT["subject-ink"]


def srgb_mix(hex_a, hex_b, pct_a):
    rgb_a = hex_to_rgb(hex_a)
    rgb_b = hex_to_rgb(hex_b)
    return tuple(
        round(pct_a / 100 * rgb_a[i] + (1 - pct_a / 100) * rgb_b[i]) for i in range(3)
    )


def contrast_ratio_rgb(rgb_a, rgb_b):
    r_a, g_a, b_a = rgb_a
    r_b, g_b, b_b = rgb_b
    lum_a = (
        0.2126 * channel_to_linear(r_a)
        + 0.7152 * channel_to_linear(g_a)
        + 0.0722 * channel_to_linear(b_a)
    )
    lum_b = (
        0.2126 * channel_to_linear(r_b)
        + 0.7152 * channel_to_linear(g_b)
        + 0.0722 * channel_to_linear(b_b)
    )
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def test_contrast_tokens_meet_wcag_targets():
    assert contrast_ratio(LIGHT["line-strong"], LIGHT["surface"]) >= 3.0
    assert contrast_ratio(LIGHT["line-strong"], LIGHT["bg"]) >= 3.0
    assert contrast_ratio(LIGHT["line-strong"], LIGHT["surface-2"]) >= 3.0
    assert contrast_ratio(LIGHT["ink"], LIGHT["bg"]) >= 4.5
    assert contrast_ratio(LIGHT["ink-2"], LIGHT["bg"]) >= 4.5
    assert contrast_ratio(LIGHT["ink-3"], LIGHT["bg"]) >= 4.5
    assert contrast_ratio(LIGHT["ink-3"], LIGHT["surface"]) >= 4.5
    assert contrast_ratio(LIGHT["ink-3"], LIGHT["surface-2"]) >= 4.5
    assert contrast_ratio(LIGHT["ink-3"], LIGHT["surface-sunken"]) >= 4.5
    assert contrast_ratio(LIGHT["accent"], LIGHT["bg"]) >= 4.5
    assert contrast_ratio(LIGHT["badge-ink"], LIGHT["danger"]) >= 4.5

    for dark in (DARK_MEDIA, DARK_ATTR):
        assert contrast_ratio(dark["badge-ink"], dark["danger"]) >= 4.5

    for dark in (DARK_MEDIA, DARK_ATTR):
        assert contrast_ratio(dark["line-strong"], dark["surface"]) >= 3.0
        assert contrast_ratio(dark["line-strong"], dark["bg"]) >= 3.0

    shared_keys = set(DARK_MEDIA) & set(DARK_ATTR)
    assert shared_keys
    mismatched = {
        key: (DARK_MEDIA[key], DARK_ATTR[key])
        for key in shared_keys
        if DARK_MEDIA[key] != DARK_ATTR[key]
    }
    assert mismatched == {}


def test_subject_color_cells_meet_wcag_on_new_fill():
    for theme_name, tokens, percents in (("light", LIGHT, LIGHT_PCT), ("dark", DARK_ATTR, DARK_PCT)):
        surface = tokens["surface"]
        ink = tokens["ink"]
        for subject_hex in SUBJECT_COLORS:
            fill = srgb_mix(subject_hex, surface, percents["subject-fill"])
            label = srgb_mix(subject_hex, ink, SUBJECT_LABEL_PCT)
            ratio = contrast_ratio_rgb(label, fill)
            assert ratio >= 4.5, (
                f"{theme_name} {subject_hex}: label {label} on fill {fill} "
                f"only {ratio:.2f}:1"
            )
