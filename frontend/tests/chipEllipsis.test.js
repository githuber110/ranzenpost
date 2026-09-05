import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const stylesCss = fs.readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "styles.css"),
  "utf8"
);

function rule(selector) {
  const match = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{[^}]*\\}`).exec(stylesCss);
  return match ? match[0] : "";
}

describe("[P222] a long filter label is cut, not wrapped", () => {
  test("the chip label clips with an ellipsis on one line", () => {
    const label = rule(".chip-label");
    expect(label).toMatch(/text-overflow:\s*ellipsis/);
    expect(label).toMatch(/white-space:\s*nowrap/);
    expect(label).toMatch(/overflow:\s*hidden/);
  });

  test("the filter chip is capped so the label can run out of room at all", () => {
    expect(rule(".chip-filter")).toMatch(/max-inline-size/);
  });

  test("the cap uses a logical property so arabic mirrors with it", () => {
    expect(rule(".chip-filter")).not.toMatch(/max-width/);
    expect(rule(".chip-label")).not.toMatch(/margin-left|margin-right|padding-left|padding-right/);
  });
});
