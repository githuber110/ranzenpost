import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const SAMPLES = [
  ["#ff0000", "#000000", "#730000"],
  ["#00ff00", "#000000", "#007300"],
  ["#0000ff", "#ffffff", "#8c8cff"],
  ["#808080", "#000000", "#3a3a3a"],
  ["#ffffff", "#000000", "#737373"],
  ["#000000", "#ffffff", "#8c8c8c"],
  ["#e91e63", "#000000", "#690e2d"],
  ["#795548", "#ffffff", "#c3b3ad"],
  ["#607d8b", "#000000", "#2b383f"],
  ["#ffeb3b", "#000000", "#736a1b"],
  ["#0a0a0a", "#ffffff", "#919191"],
  ["#f5f5f5", "#000000", "#6e6e6e"],
  ["#7a1236", "#ffffff", "#c394a5"],
  ["#22d3ee", "#000000", "#0f5f6b"],
];

describe("colour.js: the shared subject colour guard", () => {
  test("ink and bar match the backend for the shared samples (backend/tests/test_mapping.py)", () => {
    const { window } = loadApp();
    for (const [fill, ink, bar] of SAMPLES) {
      expect(window.eval(`RanzenpostColour.inkFor("${fill}")`), fill).toBe(ink);
      expect(window.eval(`RanzenpostColour.barFor("${fill}")`), fill).toBe(bar);
    }
  });

  test("every custom fill gets a readable ink and a visible bar", () => {
    const { window } = loadApp();
    const check = window.eval(`
      (function () {
        const worst = { ink: Infinity, bar: Infinity };
        for (let r = 0; r < 256; r += 15) for (let g = 0; g < 256; g += 15) for (let b = 0; b < 256; b += 15) {
          const fill = "#" + [r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("");
          worst.ink = Math.min(worst.ink, RanzenpostColour.contrast(RanzenpostColour.inkFor(fill), fill));
          worst.bar = Math.min(worst.bar, RanzenpostColour.contrast(RanzenpostColour.barFor(fill), fill));
        }
        return worst;
      })()
    `);
    expect(check.ink).toBeGreaterThanOrEqual(4.5);
    expect(check.bar).toBeGreaterThanOrEqual(2.0);
  });

  test("parseHex accepts six hex digits with or without the hash and nothing else", () => {
    const { window } = loadApp();
    const parse = (value) => window.eval(`RanzenpostColour.parseHex(${JSON.stringify(value)})`);
    expect(parse("#ABCDEF")).toBe("#abcdef");
    expect(parse("abcdef")).toBe("#abcdef");
    expect(parse(" #123456 ")).toBe("#123456");
    expect(parse("#abc")).toBe("");
    expect(parse("#12345g")).toBe("");
    expect(parse("")).toBe("");
    expect(parse(null)).toBe("");
  });

  test("resolve knows palette names, base hexes, custom hexes and falls back for unknown names", () => {
    const { window } = loadApp();
    const resolve = (value) => window.eval(`RanzenpostColour.resolve(${JSON.stringify(value)})`);
    expect(resolve("yellow")).toEqual({
      name: "yellow",
      custom: false,
      hex: "#ffe100",
      light: { fill: "#ffe100", ink: "#000000", bar: "#8a7a00" },
      dark: { fill: "#e6cf00", ink: "#000000", bar: "#6e6300" },
    });
    expect(resolve("#ffe100").name).toBe("yellow");
    expect(resolve("#abcdef")).toEqual({
      name: "",
      custom: true,
      hex: "#abcdef",
      light: { fill: "#abcdef", ink: "#000000", bar: "#4d5c6c" },
      dark: { fill: "#abcdef", ink: "#000000", bar: "#4d5c6c" },
    });
    expect(resolve("no such colour").name).toBe("grey");
    expect(resolve("")).toBeNull();
  });

  test("cellVars hands palette colours to the theme tokens and custom colours as literals", () => {
    const { window } = loadApp();
    expect(window.eval('RanzenpostColour.cellVars("navy")')).toEqual({
      fill: "var(--subject-navy-fill)",
      ink: "var(--subject-navy-ink)",
      bar: "var(--subject-navy-bar)",
    });
    expect(window.eval('RanzenpostColour.cellVars("#1a2a66")').fill).toBe("var(--subject-navy-fill)");
    expect(window.eval('RanzenpostColour.cellVars("#abcdef")')).toEqual({ fill: "#abcdef", ink: "#000000", bar: "#4d5c6c" });
    expect(window.eval('RanzenpostColour.cellVars("")')).toBeNull();
  });

  test("the card carries the same colour code as the app", () => {
    const colour = fs.readFileSync(path.resolve(__dirname, "..", "colour.js"), "utf8");
    const card = fs.readFileSync(path.resolve(__dirname, "..", "..", "custom_components", "ranzenpost", "frontend", "ranzenpost-card.js"), "utf8");
    const strip = (text) => text.split("\n").map((line) => line.trim()).filter(Boolean).join("\n");
    expect(strip(card)).toContain(strip(colour));
  });
});

describe("timetable cells take their colour from the shared guard", () => {
  test("a palette colour paints the cell through the theme tokens", () => {
    const { window } = loadApp();
    const cell = window.eval("lessonCell({ subject_code: 'MA', color: 'blue' }, '', false)");
    expect(cell.classList.contains("subject")).toBe(true);
    expect(cell.classList.contains("subject-bar")).toBe(true);
    expect(cell.style.getPropertyValue("--subject-cell-fill")).toBe("var(--subject-blue-fill)");
    expect(cell.style.getPropertyValue("--subject-cell-ink")).toBe("var(--subject-blue-ink)");
    expect(cell.style.getPropertyValue("--subject-bar")).toBe("var(--subject-blue-bar)");
    expect(cell.style.background).toBe("");
  });

  test("a custom hex paints the cell with the literal fill, a computed ink and a derived bar", () => {
    const { window } = loadApp();
    const cell = window.eval("lessonCell({ subject_code: 'MA', color: '#1a2a66' }, '', false)");
    expect(cell.style.getPropertyValue("--subject-cell-fill")).toBe("var(--subject-navy-fill)");
    const custom = window.eval("lessonCell({ subject_code: 'MA', color: '#abcdef' }, '', false)");
    expect(custom.style.getPropertyValue("--subject-cell-fill")).toBe("#abcdef");
    expect(custom.style.getPropertyValue("--subject-cell-ink")).toBe("#000000");
    expect(custom.style.getPropertyValue("--subject-bar")).toBe("#4d5c6c");
  });

  test("a lesson without a colour hashes into the palette names, and a change keeps the warning fill", () => {
    const { window } = loadApp();
    const cell = window.eval("lessonCell({ subject_code: 'MA', color: '' }, '', false)");
    expect(cell.style.getPropertyValue("--subject-cell-fill")).toMatch(/^var\(--subject-[a-z]+-fill\)$/);
    const changed = window.eval("lessonCell({ subject_code: 'MA', color: 'blue', change_kind: 'changed' }, 'changed', false)");
    expect(changed.classList.contains("subject")).toBe(false);
    expect(changed.style.getPropertyValue("--subject-cell-fill")).toBe("");
  });

  test("the stylesheet paints .tt-cell.subject from the cell variables", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    expect(css).toMatch(/\.tt-cell\.subject\s*\{[^}]*background:\s*var\(--subject-cell-fill\)/);
    expect(css).toMatch(/\.tt-cell\.subject\s*\{[^}]*color:\s*var\(--subject-cell-ink\)/);
    expect(css).toMatch(/\.tt-cell\.subject-bar::before\s*\{[^}]*background:\s*var\(--subject-bar/);
  });

  test("overview dots show the base hex of the subject colour", () => {
    const { window } = loadApp();
    expect(window.eval("subjectDotColor({ subject_code: 'MA', color: 'blue' })")).toBe("#2a66d6");
    expect(window.eval("subjectDotColor({ subject_code: 'MA', color: '#abcdef' })")).toBe("#abcdef");
  });
});
