import { describe, expect, test } from "vitest";

function readCss() {
  const fs = require("node:fs");
  const path = require("node:path");
  return fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
}

function chromeBlock(css) {
  const blockMatch = css.match(/button,\s*\.row,[^{]*\{\s*-webkit-user-select:\s*none;\s*user-select:\s*none;\s*-webkit-touch-callout:\s*none;\s*\}/);
  expect(blockMatch, "select:none chrome block not found").toBeTruthy();
  return blockMatch[0];
}

function selectNoneRuleFor(css, selector) {
  const block = chromeBlock(css);
  const selectors = block
    .slice(0, block.indexOf("{"))
    .split(",")
    .map((s) => s.trim());
  return selectors.includes(selector);
}

describe("[P141] chrome/interactive elements are not text-selectable", () => {
  const css = readCss();
  const chromeSelectors = [
    "button",
    ".row",
    ".opt",
    ".opt-main",
    ".chip",
    ".segment button",
    ".tab",
    ".tabbar",
    ".icon-btn",
    ".tech-btn",
    ".swatch",
    ".swatch-btn",
    ".swatch-trigger",
    ".setting-row",
    ".child-switch",
    ".weekbar .nav",
    ".sheet-close",
    ".select-bar-cancel",
    ".search-clear",
    ".lead",
    ".page-title",
    ".overline",
    ".badge",
    ".tag",
  ];

  for (const selector of chromeSelectors) {
    test(`${selector} is listed in the user-select:none chrome rule`, () => {
      expect(selectNoneRuleFor(css, selector)).toBe(true);
    });
  }
});

describe("[P141] content containers stay text-selectable", () => {
  const css = readCss();

  function selectTextRuleFor(selector) {
    const escaped = selector.replace(/[.[\]^$]/g, "\\$&");
    const re = new RegExp(`${escaped}\\s*[,{][^}]*user-select:\\s*text`);
    return re.test(css);
  }

  test(".body-html (letter body, pinboard post text, request/response text) carries user-select:text", () => {
    expect(selectTextRuleFor(".body-html")).toBe(true);
  });

  test(".fact (lesson-detail values, tech-details values, comments) carries user-select:text", () => {
    expect(selectTextRuleFor(".fact")).toBe(true);
  });

  test(".row-title.full (attachment filenames) carries user-select:text", () => {
    expect(css).toMatch(/\.row-title\.full\s*\{[^}]*user-select:\s*text/);
  });

  test("phone numbers (a.row[href^=\"tel:\"] .row-sub) carry user-select:text", () => {
    expect(css).toMatch(/a\.row\[href\^="tel:"\]\s*\.row-sub\s*\{[^}]*user-select:\s*text/);
  });

  test("none of the content-container selectors also appear in the chrome select:none rule", () => {
    const block = chromeBlock(css);
    expect(block).not.toMatch(/(^|,)\s*\.body-html\s*(,|\{)/m);
    expect(block).not.toMatch(/(^|,)\s*\.fact\s*(,|\{)/m);
  });
});
