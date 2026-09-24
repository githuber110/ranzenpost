const RanzenpostColour = (() => {
  const PALETTE = [
    ["white", "#ffffff", "#ffffff", "#8a9793", "#e3e8e6", "#6f7c79"],
    ["yellow", "#ffe100", "#ffe100", "#8a7a00", "#e6cf00", "#6e6300"],
    ["orange", "#ff9a1f", "#ff9a1f", "#8a4a00", "#ec8a14", "#7a4600"],
    ["red", "#d42020", "#d42020", "#ffb0b0", "#c92a2a", "#ffb0b0"],
    ["pink", "#ff69b4", "#ffb0cc", "#b8235f", "#f08ab2", "#8e1f4c"],
    ["magenta", "#c2187a", "#c2187a", "#ffb0dc", "#b8267a", "#ffb0dc"],
    ["purple", "#8f24b4", "#8f24b4", "#e2b8ff", "#9a38c0", "#e2b8ff"],
    ["lavender", "#9b7de8", "#d6c2ff", "#6f47c9", "#b39cf2", "#5b3bb0"],
    ["indigo", "#3d3ad0", "#3d3ad0", "#c0bfff", "#5a4ee6", "#c8c4ff"],
    ["blue", "#2a66d6", "#2a66d6", "#b0ccff", "#2860c8", "#b0ccff"],
    ["navy", "#1a2a66", "#1a2a66", "#9db0ff", "#243580", "#9db0ff"],
    ["sky", "#3b9cf0", "#b0d8ff", "#1c74c4", "#7ab8f2", "#0f4f8c"],
    ["cyan", "#22d3ee", "#22d3ee", "#0a6f80", "#22b8d0", "#075a68"],
    ["teal", "#0f7470", "#0f7470", "#9fe0dc", "#0f6e6a", "#9fe0dc"],
    ["mint", "#2ec48a", "#b6f0d6", "#1f8a63", "#7dd8b4", "#14624a"],
    ["green", "#2fa83c", "#4dbf57", "#1c5e22", "#3faa4c", "#164e1e"],
    ["forest", "#1f5c2c", "#1f5c2c", "#a8e6b4", "#2a6f39", "#a8e6b4"],
    ["lime", "#9be020", "#b8f03a", "#527a08", "#9fd428", "#4a6e08"],
    ["olive", "#8a8a1e", "#a8a626", "#4f4e0c", "#908e1e", "#3a3908"],
    ["brown", "#7a4a22", "#7a4a22", "#e6bd96", "#8a552a", "#e6bd96"],
    ["sand", "#c9a45c", "#e8d2a4", "#8a6a30", "#c9b07f", "#6e5426"],
    ["grey", "#8d9795", "#b9c0be", "#525c5a", "#8d9795", "#3e4745"],
    ["black", "#000000", "#262b2a", "#9aa5a1", "#000000", "#8a9793"],
    ["maroon", "#7a1236", "#7a1236", "#ffb0c8", "#8c1a42", "#ffb0c8"],
  ];
  const FIELDS = ["name", "base", "lightFill", "lightBar", "darkFill", "darkBar"];
  const DARK_INK = "#000000";
  const LIGHT_INK = "#ffffff";
  const BAR_SHADE = 0.55;
  const DEFAULT_NAME = "grey";
  const HEX = /^#?([0-9a-f]{6})$/;
  const entries = PALETTE.map((row) => Object.fromEntries(row.map((value, index) => [FIELDS[index], value])));
  const byName = new Map(entries.map((entry) => [entry.name, entry]));
  const byBase = new Map(entries.map((entry) => [entry.base, entry]));

  function parseHex(value) {
    const match = HEX.exec(String(value || "").trim().toLowerCase());
    return match ? `#${match[1]}` : "";
  }

  function isHex(value) {
    return /^#[0-9a-f]{6}$/i.test(String(value || "").trim());
  }

  function rgbOf(hex) {
    return [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16));
  }

  function hexOf(rgb) {
    return `#${rgb.map((channel) => Math.max(0, Math.min(255, Math.round(channel))).toString(16).padStart(2, "0")).join("")}`;
  }

  function linear(channel) {
    const value = channel / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  }

  function luminance(hex) {
    const [red, green, blue] = rgbOf(hex).map(linear);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  }

  function contrast(hexA, hexB) {
    const lumA = luminance(hexA);
    const lumB = luminance(hexB);
    const lighter = Math.max(lumA, lumB);
    const darker = Math.min(lumA, lumB);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function inkFor(fill) {
    return contrast(DARK_INK, fill) >= contrast(LIGHT_INK, fill) ? DARK_INK : LIGHT_INK;
  }

  function barFor(fill) {
    const target = inkFor(fill) === DARK_INK ? 0 : 255;
    return hexOf(rgbOf(fill).map((channel) => channel + (target - channel) * BAR_SHADE));
  }

  function entryOf(value) {
    const text = String(value || "").trim().toLowerCase();
    if (!text) return null;
    if (byName.has(text)) return byName.get(text);
    const hex = parseHex(text);
    if (hex) return byBase.get(hex) || null;
    return byName.get(DEFAULT_NAME);
  }

  function resolve(value) {
    const text = String(value || "").trim();
    if (!text) return null;
    const entry = entryOf(text);
    if (entry) {
      return {
        name: entry.name,
        custom: false,
        hex: entry.base,
        light: { fill: entry.lightFill, ink: inkFor(entry.lightFill), bar: entry.lightBar },
        dark: { fill: entry.darkFill, ink: inkFor(entry.darkFill), bar: entry.darkBar },
      };
    }
    const hex = parseHex(text);
    const theme = { fill: hex, ink: inkFor(hex), bar: barFor(hex) };
    return { name: "", custom: true, hex, light: theme, dark: { ...theme } };
  }

  function cellVars(value) {
    const colour = resolve(value);
    if (!colour) return null;
    if (colour.custom) return { fill: colour.light.fill, ink: colour.light.ink, bar: colour.light.bar };
    return {
      fill: `var(--subject-${colour.name}-fill)`,
      ink: `var(--subject-${colour.name}-ink)`,
      bar: `var(--subject-${colour.name}-bar)`,
    };
  }

  function tokens(theme) {
    const result = {};
    for (const entry of entries) {
      const fill = theme === "dark" ? entry.darkFill : entry.lightFill;
      result[`subject-${entry.name}-fill`] = fill;
      result[`subject-${entry.name}-bar`] = theme === "dark" ? entry.darkBar : entry.lightBar;
      result[`subject-${entry.name}-ink`] = inkFor(fill);
    }
    return result;
  }

  return {
    PALETTE: entries,
    NAMES: entries.map((entry) => entry.name),
    DARK_INK,
    LIGHT_INK,
    DEFAULT_NAME,
    parseHex,
    isHex,
    luminance,
    contrast,
    inkFor,
    barFor,
    entryOf,
    resolve,
    cellVars,
    tokens,
  };
})();
