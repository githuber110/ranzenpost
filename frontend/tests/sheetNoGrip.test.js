import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const stylesCss = fs.readFileSync(path.resolve(dirname, "..", "styles.css"), "utf8");

describe("[C20] sheets: no grip attrappe", () => {
  test("the sheet() factory no longer renders a .grip element", () => {
    const { window } = loadApp();
    const run = window.eval("(function () { return sheet('Titel', [document.createElement('div')]); })");
    const scrim = run();
    expect(scrim.querySelector(".grip")).toBeNull();
  });

  test("sheets still close via the X button", () => {
    const { window } = loadApp();
    window.eval("openSheet(() => sheet('Titel', [document.createElement('div')]));");
    expect(window.eval("!!state.sheet")).toBe(true);
    window.eval("closeSheet();");
    expect(window.eval("state.sheet")).toBeNull();
  });

  test("styles.css no longer defines .sheet .grip", () => {
    expect(stylesCss).not.toMatch(/\.sheet\s+\.grip/);
  });
});
