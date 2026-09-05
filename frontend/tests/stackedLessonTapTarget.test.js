import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const stylesCss = fs.readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "styles.css"),
  "utf8"
);

function rule(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`${escaped}\\s*\\{[^}]*\\}`).exec(stylesCss);
  return match ? match[0] : "";
}

function token(name) {
  const match = new RegExp(`${name}:\\s*([^;]+);`).exec(stylesCss);
  return match ? match[1].trim() : "";
}

function pixels(value) {
  const match = /(-?\d+(?:\.\d+)?)px/.exec(value || "");
  return match ? Number(match[1]) : null;
}

const stackedWeek = {
  lessons: [
    { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "M", room: "R1", change_kind: "" },
    { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "ENG", room: "R2", change_kind: "changed" },
  ],
  period_times: { 4: "10:40" },
};

function renderStack(window) {
  const run = window.eval(`
    (function (data) {
      state.weekOffset = 0;
      return timetableGrid(data);
    })
  `);
  const grid = run(stackedWeek);
  return grid.querySelectorAll(".tt-stack button.tt-cell");
}

describe("[P215] two lessons in one slot are still two real tap targets", () => {
  test("the minimum tap size lives in one token, not in scattered numbers", () => {
    expect(token("--tap-min")).toBe("44px");
  });

  test("a stacked lesson keeps the full minimum height instead of halving it", () => {
    const cell = rule(".tt-cell.compact");
    expect(cell).toMatch(/min-height:\s*var\(--tap-min\)/);
    expect(cell).not.toMatch(/min-height:\s*0/);
  });

  test("the stack reserves room for both of them plus the gap", () => {
    const stack = rule(".tt-stack");
    expect(stack).toMatch(/min-height:\s*calc\(var\(--tap-min\) \* 2 \+ var\(--tt-stack-gap\)\)/);
  });

  test("a stacked lesson never carries the pill chip class of the filter bars", () => {
    const { window } = loadApp();
    const cells = renderStack(window);
    expect(cells.length).toBe(2);
    for (const cell of cells) {
      expect(cell.classList.contains("compact")).toBe(true);
      expect(cell.classList.contains("chip")).toBe(false);
    }
  });

  test("the pill halo would swallow the gap between two stacked lessons", () => {
    const halo = Math.abs(pixels(/inset-block:\s*(-?\d+px)/.exec(rule(".chip::after"))?.[1]));
    const gap = pixels(token("--tt-stack-gap"));
    expect(halo).toBeGreaterThan(0);
    expect(gap).toBeGreaterThan(0);
    expect(halo * 2).toBeGreaterThan(gap);
  });

  test("two segment chips keep a dead zone between their halos", () => {
    const halo = Math.abs(pixels(/inset-inline:\s*(-?\d+px)/.exec(rule(".chipbar.segmented .chip::after"))?.[1]));
    const gap = pixels(token("--s-3"));
    expect(halo * 2).toBeLessThan(gap);
  });
});
