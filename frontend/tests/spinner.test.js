import { describe, expect, test } from "vitest";

function readStylesheet() {
  const fs = require("node:fs");
  const path = require("node:path");
  return fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
}

function spinRules(css) {
  const rules = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let match;
  while ((match = re.exec(css))) {
    const [, selector, body] = match;
    if (selector.includes(".spin")) rules.push({ selector: selector.trim(), body });
  }
  return rules;
}

describe("[P209] the spinner animates the same way everywhere, not just inside a button", () => {
  test("animation: spin is declared exactly once, so a divergent duration cannot creep back in", () => {
    const css = readStylesheet();
    const matches = css.match(/animation:\s*spin\b/g) || [];
    expect(matches.length).toBe(1);
  });

  test("@keyframes spin is defined exactly once", () => {
    const css = readStylesheet();
    const matches = css.match(/@keyframes\s+spin\b/g) || [];
    expect(matches.length).toBe(1);
  });

  test("no rule mentioning .spin sets a duration other than 700ms", () => {
    const css = readStylesheet();
    const rules = spinRules(css);
    const withDuration = rules.filter((rule) => /animation(-duration)?\s*:/.test(rule.body));
    expect(withDuration.length).toBeGreaterThan(0);
    for (const rule of withDuration) {
      const durationMatch = rule.body.match(/animation(?:-duration)?\s*:[^;]*?(\d+m?s)/);
      expect(durationMatch, `rule "${rule.selector}" declares an animation without a readable duration`).not.toBeNull();
      expect(durationMatch[1], `rule "${rule.selector}" uses a duration other than 700ms`).toBe("700ms");
    }
  });

  test("the canonical .spin rule carries flex: none so a flex parent cannot squash it into an ellipse", () => {
    const css = readStylesheet();
    const rules = spinRules(css);
    const canonical = rules.find((rule) => rule.selector === ".spin");
    expect(canonical).not.toBeUndefined();
    expect(canonical.body).toMatch(/flex\s*:\s*none\s*;/);
  });
});
