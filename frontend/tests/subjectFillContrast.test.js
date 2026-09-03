import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  const n = parseInt(clean, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(colorA, colorB, pctA) {
  const [ra, ga, ba] = hexToRgb(colorA);
  const [rb, gb, bb] = hexToRgb(colorB);
  const fa = pctA / 100;
  const fb = 1 - fa;
  return [ra * fa + rb * fb, ga * fa + gb * fb, ba * fa + bb * fb];
}

function relLuminance([r, g, b]) {
  const linear = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const [rl, gl, bl] = [linear(r), linear(g), linear(b)];
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
}

function contrastRatio(rgbA, rgbB) {
  const la = relLuminance(rgbA);
  const lb = relLuminance(rgbB);
  const [lighter, darker] = la >= lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

function rgbToXyz([r, g, b]) {
  const linear = (c) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const [rl, gl, bl] = [linear(r), linear(g), linear(b)];
  return [
    rl * 0.4124 + gl * 0.3576 + bl * 0.1805,
    rl * 0.2126 + gl * 0.7152 + bl * 0.0722,
    rl * 0.0193 + gl * 0.1192 + bl * 0.9505,
  ];
}

function xyzToLab([x, y, z]) {
  const ref = [0.95047, 1.0, 1.08883];
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(x / ref[0]), f(y / ref[1]), f(z / ref[2])];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function rgbToLab(rgb) {
  return xyzToLab(rgbToXyz(rgb));
}

function deltaE76(rgbA, rgbB) {
  const [l1, a1, b1] = rgbToLab(rgbA);
  const [l2, a2, b2] = rgbToLab(rgbB);
  return Math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2);
}

const CVD_MATRICES = {
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.011820, 0.042940, 0.968881],
  ],
  tritanopia: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.303900],
  ],
};

function toLinear(c) {
  const v = c / 255;
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function toEncoded(v) {
  const clamped = Math.max(0, Math.min(1, v));
  const e = clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  return Math.max(0, Math.min(255, e * 255));
}

function simulate(rgb, kind) {
  const m = CVD_MATRICES[kind];
  const lin = rgb.map(toLinear);
  return m.map((row) => toEncoded(row[0] * lin[0] + row[1] * lin[1] + row[2] * lin[2]));
}

const EDGE_COMPENSATION = 1.2;
const BASE_DELTA_E_FLOOR = 5.0;
const CVD_DELTA_E_FLOOR = 3.0;
const TEXT_MIX = 42;

const THEMES = {
  light: { surface: "#ffffff", ink: "#101917", fillPct: 32, deltaEFloor: BASE_DELTA_E_FLOOR - EDGE_COMPENSATION },
  dark: { surface: "#18201e", ink: "#e9efed", fillPct: 40, deltaEFloor: BASE_DELTA_E_FLOOR },
};

describe("[C12] subject fill contrast tripwire: 32% light / 40% dark", () => {
  test("--subject-fill is 32% in :root and 40% in both dark blocks", () => {
    const fs = require("node:fs");
    const path = require("node:path");
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    const rootBlock = css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)"));
    expect(rootBlock).toMatch(/--subject-fill:\s*32%/);
    expect(rootBlock).toMatch(new RegExp(`--subject-ink:\\s*${TEXT_MIX}%`));
    const darkMatches = css.match(/--subject-fill:\s*40%/g) || [];
    expect(darkMatches.length).toBe(2);
  });

  test("the cell label reads its mix from var(--subject-ink), not a literal", () => {
    const { window } = loadApp();
    const cell = window.eval("lessonCell({ subject_code: 'MA', color: '#2486ed' }, '', false)");
    expect(cell.style.color).toContain("var(--subject-ink)");
  });

  test("the palette carries enough colours for a full secondary school week", () => {
    const { window } = loadApp();
    expect(window.eval("SUBJECT_COLORS").length).toBeGreaterThanOrEqual(14);
  });

  test("gridCell reads the fill percentage from var(--subject-fill), not a literal", () => {
    const { window } = loadApp();
    const cell = window.eval(
      "lessonCell({ subject_code: 'MA', color: '#0e6b70' }, '', false)"
    );
    expect(cell.style.background).toContain("var(--subject-fill)");
  });

  for (const [themeName, theme] of Object.entries(THEMES)) {
    test(`${themeName}: every subject color keeps text/fill contrast >= 4.5`, () => {
      const { window } = loadApp();
      const colors = window.eval("SUBJECT_COLORS");
      for (const color of colors) {
        const textRgb = mix(color, theme.ink, TEXT_MIX);
        const fillRgb = mix(color, theme.surface, theme.fillPct);
        const ratio = contrastRatio(textRgb, fillRgb);
        expect(ratio, `${color} in ${themeName}`).toBeGreaterThanOrEqual(4.5);
      }
    });

    test(`${themeName}: every pair of fill colors keeps deltaE >= ${theme.deltaEFloor}`, () => {
      const { window } = loadApp();
      const colors = window.eval("SUBJECT_COLORS");
      const fills = colors.map((color) => mix(color, theme.surface, theme.fillPct));
      let minDelta = Infinity;
      for (let i = 0; i < fills.length; i += 1) {
        for (let j = i + 1; j < fills.length; j += 1) {
          minDelta = Math.min(minDelta, deltaE76(fills[i], fills[j]));
        }
      }
      expect(minDelta).toBeGreaterThanOrEqual(theme.deltaEFloor);
    });

    for (const kind of Object.keys(CVD_MATRICES)) {
      test(`${themeName}: fills stay apart under ${kind}`, () => {
        const { window } = loadApp();
        const colors = window.eval("SUBJECT_COLORS");
        const fills = colors.map((color) => simulate(mix(color, theme.surface, theme.fillPct), kind));
        let minDelta = Infinity;
        for (let i = 0; i < fills.length; i += 1) {
          for (let j = i + 1; j < fills.length; j += 1) {
            minDelta = Math.min(minDelta, deltaE76(fills[i], fills[j]));
          }
        }
        expect(minDelta).toBeGreaterThanOrEqual(CVD_DELTA_E_FLOOR);
      });
    }
  }
});
