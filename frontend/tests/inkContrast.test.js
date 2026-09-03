import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";

function hexToRgb(hex) {
  const clean = hex.trim().replace("#", "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean.slice(0, 6);
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function relLuminance([r, g, b]) {
  const linear = (c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const [rl, gl, bl] = [linear(r), linear(g), linear(b)];
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl;
}

function contrastRatio(hexA, hexB) {
  const la = relLuminance(hexToRgb(hexA));
  const lb = relLuminance(hexToRgb(hexB));
  const [lighter, darker] = la >= lb ? [la, lb] : [lb, la];
  return (lighter + 0.05) / (darker + 0.05);
}

function extractVars(block) {
  const vars = {};
  const re = /--([\w-]+):\s*(#[0-9a-fA-F]{3,8})\s*;/g;
  let match;
  while ((match = re.exec(block)) !== null) {
    vars[match[1]] = match[2];
  }
  return vars;
}

function extractBlock(css, selectorRe) {
  const match = selectorRe.exec(css);
  if (!match) throw new Error(`block not found for ${selectorRe}`);
  const start = match.index + match[0].length;
  const end = css.indexOf("}", start);
  return css.slice(start, end);
}

function themeSources(css) {
  const rootBlock = extractBlock(css, /:root\s*\{/);
  const mediaDarkBlock = extractBlock(css, /:root:not\(\[data-theme="light"\]\)\s*\{/);
  const dataThemeDarkBlock = extractBlock(css, /:root\[data-theme="dark"\]\s*\{/);
  return {
    light: { name: "light (:root)", vars: extractVars(rootBlock) },
    darkMedia: { name: "dark (@media prefers-color-scheme block)", vars: extractVars(mediaDarkBlock) },
    darkAttr: { name: 'dark ([data-theme="dark"] block)', vars: extractVars(dataThemeDarkBlock) },
  };
}

const INK_RE = /^ink(-\d+)?$/;
const SURFACE_RE = /^(bg|surface(-[\w-]+)?)$/;
const MIN_TEXT_RATIO = 4.5;
const MIN_RAMP_SEPARATION = 1.35;

const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
const sources = themeSources(css);

describe("[P167][P170] every --ink-* keeps >= 4.5:1 against every surface tone the stylesheet defines", () => {
  for (const { name, vars } of Object.values(sources)) {
    const inkNames = Object.keys(vars).filter((varName) => INK_RE.test(varName)).sort();
    const surfaceNames = Object.keys(vars).filter((varName) => SURFACE_RE.test(varName)).sort();

    test(`${name} defines the full ink ramp and every surface tone`, () => {
      expect(inkNames, `${name} ink tokens`).toEqual(["ink", "ink-2", "ink-3"]);
      expect(surfaceNames, `${name} surface tokens`).toContain("bg");
      expect(surfaceNames, `${name} surface tokens`).toContain("surface");
      expect(surfaceNames.length, `${name} surface tokens`).toBeGreaterThanOrEqual(4);
    });

    for (const inkName of inkNames) {
      for (const surfaceName of surfaceNames) {
        test(`${name}: --${inkName} (${vars[inkName]}) on --${surfaceName} (${vars[surfaceName]})`, () => {
          const ratio = contrastRatio(vars[inkName], vars[surfaceName]);
          expect(
            ratio,
            `--${inkName} ${vars[inkName]} on --${surfaceName} ${vars[surfaceName]} is only ${ratio.toFixed(2)}:1`
          ).toBeGreaterThanOrEqual(MIN_TEXT_RATIO);
        });
      }
    }

    test(`${name}: the ink ramp stays visually separated step by step`, () => {
      for (let i = 1; i < inkNames.length; i++) {
        const previous = inkNames[i - 1];
        const current = inkNames[i];
        const ratio = contrastRatio(vars[previous], vars[current]);
        expect(
          ratio,
          `--${previous} ${vars[previous]} and --${current} ${vars[current]} are only ${ratio.toFixed(3)}:1 apart`
        ).toBeGreaterThanOrEqual(MIN_RAMP_SEPARATION);
      }
    });
  }

  test("both dark blocks carry identical ink and surface tokens", () => {
    const keys = [...Object.keys(sources.darkMedia.vars)].filter(
      (varName) => INK_RE.test(varName) || SURFACE_RE.test(varName)
    );
    expect(keys.length).toBeGreaterThanOrEqual(7);
    for (const key of keys) {
      expect(sources.darkAttr.vars[key], `--${key}`).toBe(sources.darkMedia.vars[key]);
    }
  });

  test("the surface sweep really would catch a token that only one background breaks", () => {
    const vars = sources.light.vars;
    const surfaceNames = Object.keys(vars).filter((varName) => SURFACE_RE.test(varName));
    const planted = "#5c6a64";
    const failing = surfaceNames.filter((surfaceName) => contrastRatio(planted, vars[surfaceName]) < MIN_TEXT_RATIO);
    expect(failing.length).toBeGreaterThan(0);
    expect(surfaceNames.length).toBeGreaterThan(failing.length);
  });
});
