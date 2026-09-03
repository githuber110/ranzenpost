import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const css = fs.readFileSync(path.join(dirname, "..", "styles.css"), "utf8");

function ruleFor(selector) {
  const index = css.indexOf(selector);
  if (index < 0) return "";
  const open = css.indexOf("{", index);
  const close = css.indexOf("}", open);
  return open < 0 || close < 0 ? "" : css.slice(open + 1, close);
}

describe("[P193] native date and time fields are clamped to their container", () => {
  test("the wizard builds them as .inp with a native type, so the stylesheet reaches them", () => {
    const { window } = loadApp();
    const date = window.eval('dateField("Von", "2026-09-03", "2026-09-01", function () {})').querySelector("input");
    const time = window.eval('timeField("Von", "08:00", function () {})').querySelector("input");
    expect(date.getAttribute("type")).toBe("date");
    expect(time.getAttribute("type")).toBe("time");
    expect(date.className).toBe("inp");
    expect(time.className).toBe("inp");
  });

  test("the shared rule caps the inline size and allows shrinking below the intrinsic width", () => {
    const rule = ruleFor('.inp[type="date"],');
    expect(rule).toMatch(/inline-size:\s*100%/);
    expect(rule).toMatch(/min-inline-size:\s*0/);
    expect(rule).toMatch(/max-inline-size:\s*100%/);
  });

  test("the webkit block tames the native inner value box", () => {
    const block = css.slice(css.indexOf("@supports (-webkit-touch-callout: none)"));
    expect(block).toContain("-webkit-appearance: none");
    expect(block).toContain("::-webkit-datetime-edit");
    expect(block).toContain("::-webkit-date-and-time-value");
    expect(block.slice(0, block.indexOf("\n}\n"))).toMatch(/min-inline-size:\s*0/);
  });

  test("the clamp uses logical properties only, so right-to-left keeps working", () => {
    const rule = ruleFor('.inp[type="date"],');
    expect(rule).not.toMatch(/(^|[^-])width:/);
    expect(rule).not.toMatch(/text-align:\s*(left|right)/);
  });
});
