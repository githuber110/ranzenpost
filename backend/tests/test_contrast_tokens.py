import pathlib
import re

import math

from app.mapping import PALETTE, bar_for, ink_for

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

def _lab(hex_color):
    red, green, blue = (channel_to_linear(channel) for channel in hex_to_rgb(hex_color))
    x = (red * 0.4124 + green * 0.3576 + blue * 0.1805) / 0.95047
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = (red * 0.0193 + green * 0.1192 + blue * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _hue(a, b):
    if a == 0 and b == 0:
        return 0.0
    angle = math.degrees(math.atan2(b, a))
    return angle + 360 if angle < 0 else angle


def delta_e2000(hex_a, hex_b):
    l1, a1, b1 = _lab(hex_a)
    l2, a2, b2 = _lab(hex_b)
    mean_c = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(mean_c ** 7 / (mean_c ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = _hue(a1p, b1), _hue(a2p, b2)
    dl, dc = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    big_dh = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    mean_l, mean_cp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        mean_h = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        mean_h = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        mean_h = (h1p + h2p + 360) / 2
    else:
        mean_h = (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h))
        + 0.32 * math.cos(math.radians(3 * mean_h + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h - 63))
    )
    d_theta = 30 * math.exp(-(((mean_h - 275) / 25) ** 2))
    rc = 2 * math.sqrt(mean_cp ** 7 / (mean_cp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / math.sqrt(20 + (mean_l - 50) ** 2)
    sc = 1 + 0.045 * mean_cp
    sh = 1 + 0.015 * mean_cp * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (big_dh / sh) ** 2 + rt * (dc / sc) * (big_dh / sh))


PALETTE_SIZE = 24
REQUIRED_NAMES = {
    "white", "yellow", "orange", "red", "pink", "purple", "indigo", "blue", "sky", "cyan",
    "teal", "green", "lime", "olive", "brown", "sand", "grey", "black",
}
MIN_TEXT_CONTRAST = 4.5
MIN_BAR_CONTRAST = 2.5
MIN_DISTANCE = {"light": 12.0, "dark": 10.0}
THEME_TOKENS = {"light": LIGHT, "dark": DARK_ATTR}


def palette_tokens(tokens, name):
    return tuple(tokens[f"subject-{name}-{part}"] for part in ("fill", "bar", "ink"))


def test_the_palette_has_twenty_four_named_colours_including_the_required_ones():
    names = [entry[0] for entry in PALETTE]
    assert len(names) == PALETTE_SIZE
    assert len(set(names)) == PALETTE_SIZE
    assert REQUIRED_NAMES <= set(names)


def test_every_palette_colour_has_fill_bar_and_ink_tokens_in_every_theme_block():
    for name, base, light_fill, light_bar, dark_fill, dark_bar in PALETTE:
        assert palette_tokens(LIGHT, name) == (light_fill, light_bar, ink_for(light_fill))
        assert palette_tokens(DARK_ATTR, name) == (dark_fill, dark_bar, ink_for(dark_fill))
        assert palette_tokens(DARK_MEDIA, name) == palette_tokens(DARK_ATTR, name)


def test_every_palette_colour_meets_wcag_aa_on_its_fill_in_both_themes():
    for theme, tokens in THEME_TOKENS.items():
        for name, *_ in PALETTE:
            fill, bar, ink = palette_tokens(tokens, name)
            text = contrast_ratio(ink, fill)
            assert text >= MIN_TEXT_CONTRAST, f"{theme} {name}: ink {ink} on fill {fill} only {text:.2f}:1"
            stripe = contrast_ratio(bar, fill)
            assert stripe >= MIN_BAR_CONTRAST, f"{theme} {name}: bar {bar} on fill {fill} only {stripe:.2f}:1"


def test_the_ink_is_dark_on_light_fills_and_light_on_dark_fills():
    for theme, tokens in THEME_TOKENS.items():
        for name, *_ in PALETTE:
            fill, _, ink = palette_tokens(tokens, name)
            expected = "#000000" if relative_luminance(fill) > 0.18 else "#ffffff"
            assert ink == expected, f"{theme} {name}"


def test_every_pair_of_palette_fills_stays_apart():
    for theme, tokens in THEME_TOKENS.items():
        fills = [(name, palette_tokens(tokens, name)[0]) for name, *_ in PALETTE]
        closest = min(
            (delta_e2000(fill_a, fill_b), name_a, name_b)
            for index, (name_a, fill_a) in enumerate(fills)
            for name_b, fill_b in fills[index + 1 :]
        )
        assert closest[0] >= MIN_DISTANCE[theme], f"{theme}: {closest[1]} and {closest[2]} only {closest[0]:.1f} apart"


def test_the_stage_tokens_carry_the_grid_background_of_each_theme():
    assert LIGHT["stage-light"] == LIGHT["surface-sunken"]
    assert DARK_ATTR["stage-dark"] == DARK_ATTR["surface-sunken"]
    assert DARK_ATTR["stage-light"] == LIGHT["stage-light"]
    assert LIGHT["stage-dark"] == DARK_ATTR["stage-dark"]


def test_a_custom_colour_always_gets_a_readable_ink_and_a_visible_bar():
    samples = ["#ff0000", "#00ff00", "#0000ff", "#808080", "#ffffff", "#000000", "#e91e63", "#795548", "#607d8b", "#ffeb3b"]
    step = 51
    samples += ["#%02x%02x%02x" % (r, g, b) for r in range(0, 256, step) for g in range(0, 256, step) for b in range(0, 256, step)]
    for fill in samples:
        assert contrast_ratio(ink_for(fill), fill) >= MIN_TEXT_CONTRAST, fill
        assert contrast_ratio(bar_for(fill), fill) >= 2.0, fill


SELECTED_STATE_RULES = (
    r'\.tab\[aria-current="page"\] \.ico-slot',
    r'\.segment button\[aria-selected="true"\]',
    r'\.chip\[aria-selected="true"\]',
    r'\.pick button\[aria-pressed="true"\]',
    r'\.opt\[aria-pressed="true"\]',
)


def test_the_active_tab_is_marked_by_more_than_a_colour():
    pill = re.search(r'\.tab\[aria-current="page"\] \.ico-slot\s*\{([^}]*)\}', CSS)
    assert pill, "the active tab has no pill rule"
    assert "var(--accent)" in pill.group(1)
    label = re.search(r'\.tab\[aria-current="page"\]\s*\{([^}]*)\}', CSS)
    assert label, "the active tab has no own rule"
    assert "font-weight" in label.group(1), "colour alone must not carry the active tab"
    slot = re.search(r'\.tab \.ico-slot\s*\{([^}]*)\}', CSS)
    assert slot, "every tab needs the same slot geometry so the bar does not jump"
    assert "inline-size" in slot.group(1) and "block-size" in slot.group(1)


def test_every_selected_state_is_a_filled_accent_surface():
    for pattern in SELECTED_STATE_RULES:
        match = re.search(pattern + r"\s*\{([^}]*)\}", CSS)
        assert match, f"no rule found for {pattern}"
        body = match.group(1)
        assert "background: var(--accent)" in body, f"{pattern} does not fill with the accent"
        assert "var(--accent-ink)" in body, f"{pattern} does not invert its content"
        assert "--accent-soft" not in body, f"{pattern} still uses the near-invisible soft tint"
