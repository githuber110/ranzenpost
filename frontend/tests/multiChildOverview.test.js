import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

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
      state.childId = children[0].child_id;
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
  { child_id: "c1", name: "Alice", class_name: "3b" },
  { child_id: "c2", name: "Bella", class_name: "1a" },
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

describe("[P178] HEUTE shows one child at a time, chosen through the pill row", () => {
  test("two children render one pill each and only the active child's lessons", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    const pills = panel.querySelectorAll(".chipbar.overview-pills .chip");
    expect(pills.length).toBe(2);
    expect(pills[0].getAttribute("aria-pressed")).toBe("true");
    expect(pills[1].getAttribute("aria-pressed")).toBe("false");
    expect(pills[0].textContent).toContain("Alice");
    expect(pills[0].textContent).toContain("3b");
    const rows = panel.querySelectorAll(".rows.flat .row");
    expect(rows.length).toBe(5);
  });

  test("the pill label comes from the child.nameWithClass key, never from a string join", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    const pill = panel.querySelector(".chipbar.overview-pills .chip");
    expect(pill.textContent).toBe(window.eval('t("child.nameWithClass", { name: "Alice", class: "3b" })'));
  });

  test("the inactive pill carries a change mark when that child's day has a change", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS);
    const pills = panel.querySelectorAll(".chipbar.overview-pills .chip");
    expect(pills[0].querySelector(".chip-mark")).toBeNull();
    expect(pills[1].querySelector(".chip-mark")).not.toBeNull();
  });

  test("selecting the second pill switches the chapter to that child's day", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", CHILDREN, WEEKS, "c2");
    const pills = panel.querySelectorAll(".chipbar.overview-pills .chip");
    expect(pills[1].getAttribute("aria-pressed")).toBe("true");
    const titles = [...panel.querySelectorAll(".rows.flat .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["SU", "K"]);
  });

  test("a child switch drops the anchor and re-arms the now anchor", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = ${JSON.stringify(CHILDREN)};
        state.childId = "c1";
        state.overviewChildId = "c1";
        state._overviewAnchor = { area: "today", blockKey: "c1:3" };
        state._overviewNow = false;
        overviewSelectChild("c2");
        return { child: state.overviewChildId, anchor: state._overviewAnchor, now: state._overviewNow };
      })()
    `);
    expect(result.child).toBe("c2");
    expect(result.anchor).toBeNull();
    expect(result.now).toBe(true);
  });

  test("exactly one child renders no pill row at all", () => {
    const { window } = loadApp();
    const panel = renderTodayChapterAt(window, "2026-09-01T06:00:00", [CHILDREN[0]], { c1: WEEKS.c1 });
    expect(panel.querySelector(".chipbar.overview-pills")).toBeNull();
    expect(panel.querySelectorAll(".rows.flat .row").length).toBe(5);
  });

  test("children not loaded yet still reserve the pill row, so the budget never shrinks later", () => {
    const { window } = loadApp();
    const panel = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.overviewChildId = null;
        state.timetable = { lessons: [], period_times: {} };
        return overviewToday();
      })()
    `);
    const bar = panel.querySelector(".chipbar.overview-pills");
    expect(bar).not.toBeNull();
    expect(bar.querySelectorAll(".chip-skeleton").length).toBe(2);
    expect(bar.querySelector("button")).toBeNull();
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

describe("[H3] the overview's HEUTE chapter always shows week 0, never the timetable tab's week", () => {
  test("after the timetable tab moved to week +1, the overview still reads the cached week 0", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = [{ child_id: "c1", name: "Alice" }];
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
        state.children = [{ child_id: "c1", name: "Alice" }];
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
