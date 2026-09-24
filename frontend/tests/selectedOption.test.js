import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");

function rules(selectorPattern) {
  const found = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  let match;
  while ((match = pattern.exec(css))) {
    const selector = match[1].trim();
    if (selectorPattern.test(selector)) found.push({ selector, body: match[2] });
  }
  return found;
}

describe("the selected option is filled and carries a check at the inline end", () => {
  test("no rule draws a stripe beside an option", () => {
    expect(rules(/\.opt[^,]*::before/)).toEqual([]);
    const stripes = rules(/(^|[\s,])\.opt(\[|\.|:|\s*$)/).filter((rule) => /inset-inline-start\s*:\s*0|width\s*:\s*3px/.test(rule.body));
    expect(stripes).toEqual([]);
  });

  test("the selected state fills the option and adds a check pushed to the inline end", () => {
    const filled = rules(/^\.opt\[aria-pressed="true"\]$/);
    expect(filled.length).toBe(1);
    expect(filled[0].body).toMatch(/background:\s*var\(--accent\)/);
    const check = rules(/^\.opt\[aria-pressed="true"\]::after$/);
    expect(check.length).toBe(1);
    expect(check[0].body).toMatch(/margin-inline-start:\s*auto/);
    expect(check[0].body).toMatch(/mask:\s*url\("data:image\/svg\+xml/);
    expect(check[0].body).not.toMatch(/(^|[^-])(left|right)\s*:/);
  });

  test("the theme sheet marks exactly the chosen theme as pressed", () => {
    const { window, document } = loadApp();
    window.eval("state.theme = 'dark'; openSheet(themeSheet);");
    const pressed = [...document.querySelectorAll(".sheet .opt")].filter((node) => node.getAttribute("aria-pressed") === "true");
    expect(pressed.length).toBe(1);
  });
});
