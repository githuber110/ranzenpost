import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const styles = fs.readFileSync(path.join(path.resolve(__dirname, ".."), "styles.css"), "utf8");

function renderTodayAgainAt(window, fixedDate) {
  const run = window.eval(`
    (function (fixedIso) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedDate);
}

function renderTodayChapterAt(window, fixedDate, children, weeks, activeId) {
  const run = window.eval(`
    (function (fixedIso, children, weeks, activeId) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.children = children;
      state.childId = children[0].key;
      state.overviewChildId = activeId || null;
      state.timetable = null;
      state.overviewWeeks = {};
      for (const childId of Object.keys(weeks)) {
        state.overviewWeeks[childId] = { 0: weeks[childId] };
      }
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedDate, children, weeks, activeId);
}

const CHILDREN = [
  { key: "c1", name: "Alice Example", class_name: "3b" },
  { key: "c2", name: "Bella Example", class_name: "1a" },
];

const WEEKS = {
  c1: {
    lessons: [
      { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
      { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      { day_of_week: 2, period: 3, start_time: "09:50", subject_code: "E" },
      { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "SP" },
      { day_of_week: 2, period: 5, start_time: "11:40", subject_code: "MU" },
    ],
    period_times: {},
  },
  c2: {
    lessons: [
      { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "SU", change_kind: "cancelled" },
      { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "K" },
    ],
    period_times: {},
  },
};

describe("HEUTE shows one child at a time, chosen through a chip row of first names", () => {
  test("two children render one chip each, the first name only, and only the active child's lessons", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    expect(panel.querySelector(".today-stack")).toBeNull();
    const chips = panel.querySelectorAll(".chipbar.overview-chips .chip");
    expect(chips.length).toBe(2);
    expect([...chips].map((chip) => chip.textContent)).toEqual(["Alice", "Bella"]);
    expect(chips[0].getAttribute("aria-pressed")).toBe("true");
    expect(chips[1].getAttribute("aria-pressed")).toBe("false");
    const rows = panel.querySelectorAll(".rows.flat .row:not(.row-note)");
    expect(rows.length).toBe(5);
    expect(panel.dataset.blocks.split(" ")).toEqual(["c1:1", "c1:2", "c1:3", "c1:4", "c1:5", "c1:schoolEnd"]);
  });

  test("the chip row sits between the head and the rows, outside the paged blocks", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    const children = [...panel.children].map((node) => node.className);
    expect(children.slice(0, 3)).toEqual(["panel-head", "chipbar overview-chips", "rows flat"]);
    expect(panel.querySelector(".chipbar.overview-chips [data-block]")).toBeNull();
  });

  test("the inactive chip carries a change mark when that child's day has a change", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    const chips = panel.querySelectorAll(".chipbar.overview-chips .chip");
    expect(chips[0].querySelector(".chip-mark")).toBeNull();
    expect(chips[1].querySelector(".chip-mark")).not.toBeNull();
  });

  test("selecting the second chip switches the chapter to that child's day", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS, "c2");
    const chips = panel.querySelectorAll(".chipbar.overview-chips .chip");
    expect(chips[1].getAttribute("aria-pressed")).toBe("true");
    const titles = [...panel.querySelectorAll(".rows.flat .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["SU", "K"]);
  });

  test("tapping a chip stores the choice, drops the anchor and re-arms the now anchor", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = ${JSON.stringify(CHILDREN)};
        state.childId = "c1";
        state.overviewChildId = "c1";
        state._overviewAnchor = { area: "today", blockKey: "c1:3" };
        state._overviewNow = false;
        rerender = () => { state.rerendered = (state.rerendered || 0) + 1; };
        overviewSelectChild("c2");
        overviewSelectChild("c2");
        return { child: state.overviewChildId, anchor: state._overviewAnchor, now: state._overviewNow, rerendered: state.rerendered };
      })()
    `);
    expect(result.child).toBe("c2");
    expect(result.anchor).toBeNull();
    expect(result.now).toBe(true);
    expect(result.rerendered).toBe(1);
  });

  test("the choice survives a re-render and the chips are rebuilt from it", () => {
    const { window } = loadApp();
    const first = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS, "c2");
    expect(first.querySelectorAll('.overview-chips .chip[aria-pressed="true"]')[0].textContent).toBe("Bella");
    const again = renderTodayAgainAt(window, "2026-09-01T06:00:00");
    expect(again.querySelectorAll('.overview-chips .chip[aria-pressed="true"]')[0].textContent).toBe("Bella");
    expect([...again.querySelectorAll(".rows.flat .row-title")].map((node) => node.textContent)).toEqual(["SU", "K"]);
  });

  test("the first child is the default when nothing was chosen", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS, null);
    expect(panel.querySelector('.overview-chips .chip[aria-pressed="true"]').textContent).toBe("Alice");
  });

  test("exactly one child renders no chip row at all", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", [CHILDREN[0]], { c1: WEEKS.c1 });
    expect(panel.querySelector(".chipbar")).toBeNull();
    expect(panel.querySelectorAll(".rows.flat .row:not(.row-note)").length).toBe(5);
  });

  test("children not loaded yet still reserve the chip row, so the budget never shrinks later", () => {
    const { window } = loadApp();
    const panel = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.overviewChildId = null;
        state.timetable = { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
        return overviewToday();
      })()
    `);
    const bar = panel.querySelector(".chipbar.overview-chips");
    expect(bar).not.toBeNull();
    expect(bar.querySelectorAll(".chip-skeleton").length).toBe(2);
    expect(bar.querySelector("button")).toBeNull();
  });

  test("no today chapter is wide any more and the stack styles are gone", () => {
    expect(styles).not.toMatch(/\.today-stack/);
    expect(styles).not.toMatch(/\.panel-wide/);
    expect(styles).not.toMatch(/\.today-child/);
    expect(styles).toMatch(/\.overview-chips\s*{/);
    expect(styles).toMatch(/\.chip-mark\s*{/);
  });

  test("in the wide grid the chip row wraps instead of scrolling out of its column", () => {
    const wide = styles.slice(styles.indexOf("@media (min-width: 900px)"));
    expect(wide).toMatch(/\.overview \.overview-chips\s*{[^}]*flex-wrap:\s*wrap/);
    expect(wide).toMatch(/\.overview \.overview-chips\s*{[^}]*overflow:\s*visible/);
  });

  test("persistConfig invalidation clears overviewWeeks for all children", () => {
    const { window } = loadApp();
    const run = window.eval(`
      (function () {
        state.overviewWeeks = { c1: { 0: { lessons: [] } }, c2: { 0: { lessons: [] } } };
        window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
        return persistConfig().then(() => JSON.stringify(state.overviewWeeks));
      })
    `);
    return run().then((json) => {
      expect(json).toBe("{}");
    });
  });
});

describe("the overview's HEUTE chapter always shows week 0, never the timetable tab's week", () => {
  test("after the timetable tab moved to week +1, the overview still reads the cached week 0", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = [{ key: "c1", name: "Alice" }];
        state.childId = "c1";
        state.weekOffset = 1;
        state.timetable = { lessons: [{ day_of_week: 2, period: 9, subject_code: "WRONG" }], period_times: {} };
        state.overviewWeeks = { c1: { 0: { lessons: [{ day_of_week: 2, period: 1, subject_code: "RIGHT" }], period_times: {} } } };
        const week = overviewWeekData("c1", 0);
        return week.lessons[0].subject_code;
      })()
    `);
    expect(result).toBe("RIGHT");
  });

  test("with the timetable tab on week 0 the live timetable is still reused as the cache", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = [{ key: "c1", name: "Alice" }];
        state.childId = "c1";
        state.weekOffset = 0;
        state.timetable = { lessons: [{ day_of_week: 2, period: 1, subject_code: "LIVE" }], period_times: {} };
        state.overviewWeeks = {};
        return overviewWeekData("c1", 0).lessons[0].subject_code;
      })()
    `);
    expect(result).toBe("LIVE");
  });
});
