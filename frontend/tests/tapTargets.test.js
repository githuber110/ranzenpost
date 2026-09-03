import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const e2eDir = path.resolve(dirname, "..", "..", "e2e");

describe("[C19] search keyboard hints", () => {
  test("searchField input carries enterkeyhint=search", () => {
    const { window } = loadApp();
    const run = window.eval("(function () { return searchField('', 'Suchen', () => {}, null); })");
    const field = run();
    const input = field.querySelector(".search-input");
    expect(input.getAttribute("enterkeyhint")).toBe("search");
  });

  test("pressing Enter in the search field blurs it (keyboard shows 'Suchen' and gets out of the way)", () => {
    const { window } = loadApp();
    const run = window.eval("(function () { return searchField('', 'Suchen', () => {}, null); })");
    const field = run();
    window.document.body.appendChild(field);
    const input = field.querySelector(".search-input");
    input.focus();
    expect(window.document.activeElement).toBe(input);
    input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(window.document.activeElement).not.toBe(input);
  });
});

describe("[W1d] real tap-target geometry moved to e2e", () => {
  test("checkTapTargets and checkTapTargetOverlaps exist and measure rendered rectangles, not CSS source text", () => {
    const helpersSource = fs.readFileSync(path.join(e2eDir, "helpers.js"), "utf8");
    expect(helpersSource).toMatch(/async function checkTapTargets\(page\)/);
    expect(helpersSource).toMatch(/async function checkTapTargetOverlaps\(page/);
    expect(helpersSource).toMatch(/getBoundingClientRect/);
    expect(fs.existsSync(path.join(e2eDir, "responsive-guard-tap-overlap.spec.js"))).toBe(true);
  });
});
