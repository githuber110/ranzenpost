import { describe, expect, test } from "vitest";

describe("[C15] typography scale: 9 sizes, dead sizes stay gone", () => {
  test("styles.css contains neither 0.8125rem nor 0.5625rem", () => {
    const fs = require("node:fs");
    const path = require("node:path");
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    expect(css).not.toMatch(/0\.8125rem/);
    expect(css).not.toMatch(/0\.5625rem/);
  });
});
