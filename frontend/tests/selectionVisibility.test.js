import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const stylesCss = fs.readFileSync(path.resolve(dirname, "..", "styles.css"), "utf8");
const wizardCss = fs.readFileSync(path.resolve(dirname, "..", "wizard.css"), "utf8");

function rule(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`${escaped}\\s*\\{[^}]*\\}`).exec(css);
  return match ? match[0] : "";
}

const MARKED_WEEK = {
  lessons: [
    { day_of_week: 3, period: 1, start_time: "08:00", subject_code: "D", date: "2026-09-02", change_kind: "" },
    { day_of_week: 3, period: 2, start_time: "08:50", subject_code: "M", date: "2026-09-02", change_kind: "" },
    { day_of_week: 3, period: 3, start_time: "09:50", subject_code: "M", date: "2026-09-02", change_kind: "" },
  ],
  period_times: { 1: "08:00", 2: "08:50", 3: "09:50" },
};

function overviewWithMark(window) {
  const run = window.eval(`
    (function (week) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate("2026-09-02T07:00:00");
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.childId = "c1";
      state.children = [{ child_id: "c1", name: "Kind" }];
      state.weekOffset = 0;
      state.timetable = week;
      state.config = { period_times: week.period_times };
      state.marks = { data: { marks: [
        { id: "m1", child_id: "c1", date: "2026-09-02", period: 2, kind: "exam", label: "" },
        { id: "m2", child_id: "c1", date: "2026-09-02", period: 3, kind: "exam", label: "" }
      ] } };
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(MARKED_WEEK);
}

describe("[P232] every selected state is loud enough to see", () => {
  test("a marked lesson inside a double period is reachable by the ring rule", () => {
    const { window } = loadApp();
    const section = overviewWithMark(window);
    const marked = section.querySelectorAll(".marked");
    expect(marked.length).toBeGreaterThan(0);
    for (const node of marked) {
      const isRow = node.classList.contains("row");
      const isPairItem = node.classList.contains("row-pair-item");
      expect(isRow || isPairItem, `a marked node carries neither .row nor .row-pair-item: ${node.className}`).toBe(true);
      expect(node.querySelector(".row-dot i"), "a marked node has no dot to ring").not.toBeNull();
    }
    const ringRule = rule(stylesCss, ".row.marked .row-dot i,\n.row-pair-item.marked .row-dot i");
    expect(ringRule).toMatch(/var\(--accent\)/);
    expect(ringRule).not.toMatch(/--accent-soft/);
  });

  test("the now mark is a filled accent pill, the next mark carries the accent too", () => {
    const now = rule(stylesCss, ".row-when.now");
    expect(now).toMatch(/background:\s*var\(--accent\)/);
    expect(now).toMatch(/var\(--accent-ink\)/);
    const next = rule(stylesCss, ".row-when.next");
    expect(next).toMatch(/var\(--accent\)/);
    expect(next).toMatch(/font-weight/);
  });

  test("the next mark no longer looks like ordinary row meta", () => {
    const base = rule(stylesCss, ".row-when");
    expect(base).toMatch(/var\(--ink-3\)/);
    const next = rule(stylesCss, ".row-when.next");
    expect(next).not.toBe("");
    expect(next).not.toMatch(/var\(--ink-3\)/);
  });

  test("the wizard's chosen child is filled, not tinted", () => {
    const chosen = rule(wizardCss, '.sw-body .wz-child[aria-pressed="true"]');
    expect(chosen).toMatch(/background:\s*var\(--accent\)/);
    expect(chosen).toMatch(/var\(--accent-ink\)/);
    expect(chosen).not.toMatch(/--accent-soft/);
  });

  test("no selection state is left hanging off the near-invisible soft tint", () => {
    const offenders = [];
    const pattern = /([^{}]+)\{[^}]*--accent-soft[^}]*\}/g;
    for (const css of [stylesCss, wizardCss]) {
      let hit;
      while ((hit = pattern.exec(css)) !== null) {
        const selector = hit[1].trim().split("\n").pop().trim();
        if (/aria-pressed="true"|aria-selected="true"|aria-current|\.marked|\.picked/.test(selector)) {
          offenders.push(selector);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("dead selection styling is gone instead of lying in wait", () => {
    expect(stylesCss).not.toMatch(/\.row\.next\s*\{/);
    expect(wizardCss).not.toMatch(/\.wz-dot/);
    expect(wizardCss).not.toMatch(/\.wz-child\.picked/);
  });
});
