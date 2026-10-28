import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const CHILD = "s1:c1";

function at(window, fixedIso, body, data) {
  const run = window.eval(`
    (function (fixedIso, child, data) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      FixedDate.now = () => new RealDate(fixedIso).getTime();
      Date = FixedDate;
      try {
        return (${body})(child, data);
      } finally {
        Date = RealDate;
      }
    })
  `);
  return run(fixedIso, CHILD, data === undefined ? null : window.JSON.parse(JSON.stringify(data)));
}

function seed(window) {
  window.eval(`
    state.children = [{ key: "${CHILD}", name: "Alex", connection_id: "s1", student_id: 4711 }];
    state.childId = "${CHILD}";
    state.weekOffset = 0;
    state.config = { period_times: {} };
    state.overviewWeeks = {};
    state.overviewWeekMondays = {};
  `);
}

const LESSON = { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "MA" };

describe("the overview week cache", () => {
  test("a good overview week wins over a failed timetable load, so retry can heal the today block", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = at(window, "2026-09-01T07:00:00", `function (child, data) {
      state.timetable = failedWeek("unreachable", null);
      state.overviewWeeks[child] = { 0: { lessons: [data], period_times: {} } };
      return todayChapter("normal");
    }`, LESSON);
    expect(chapter.blocks.some((block) => block.key === "today:failed")).toBe(false);
    expect(chapter.blocks.some((block) => block.key === `${CHILD}:1`)).toBe(true);
  });

  test("a failed overview week does not hide a good timetable load", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = at(window, "2026-09-01T07:00:00", `function (child, data) {
      state.timetable = { lessons: [data], period_times: {} };
      state.overviewWeeks[child] = { 0: failedWeek("unreachable", null) };
      return todayChapter("normal");
    }`, LESSON);
    expect(chapter.blocks.some((block) => block.key === `${CHILD}:1`)).toBe(true);
  });

  test("a week loaded for an earlier Monday is dropped instead of shown under the wrong dates", () => {
    const { window } = loadApp();
    seed(window);
    const result = at(window, "2026-09-07T09:00:00", `function (child) {
      state.overviewWeeks[child] = { 1: { lessons: [], period_times: {} }, 2: { lessons: [], period_times: {} } };
      state.overviewWeekMondays[child] = { 1: "2026-09-07", 2: "2026-09-21" };
      return { one: overviewWeekData(child, 1), two: !!overviewWeekData(child, 2), kept: Object.keys(state.overviewWeeks[child]) };
    }`);
    expect(result.one).toBeNull();
    expect(result.two).toBe(true);
    expect(result.kept).toEqual(["2"]);
  });

  test("the timetable of a later week is used when the timetable view shows that week", () => {
    const { window } = loadApp();
    seed(window);
    const same = at(window, "2026-09-01T09:00:00", `function (child) {
      state.weekOffset = 2;
      state.timetable = { lessons: [], period_times: {}, mark: "shown" };
      return overviewWeekData(child, 2).mark;
    }`);
    expect(same).toBe("shown");
  });

  test("a timetable still holding last week is not shown as this week after Sunday midnight", () => {
    const { window } = loadApp();
    seed(window);
    const result = at(window, "2026-09-07T00:05:00", `function (child) {
      state.timetable = { lessons: [{ day_of_week: 1, period: 1, start_time: "08:00", subject_code: "MA" }], period_times: {} };
      state.timetableMonday = "2026-08-31";
      return overviewWeekData(child, 0);
    }`);
    expect(result).toBeNull();
  });

  test("every cached week is listed for a refresh, week 0 always", () => {
    const { window } = loadApp();
    seed(window);
    const weeks = at(window, "2026-09-01T09:00:00", `function (child) {
      state.overviewWeeks[child] = { 1: { lessons: [] }, 3: { lessons: [] } };
      return overviewCachedWeeks(child).sort();
    }`);
    expect(weeks).toEqual([0, 1, 3]);
  });
});

describe("the absent today row", () => {
  function absent(window, entries, children) {
    return at(window, "2026-09-01T07:00:00", `function (child, data) {
      if (data.children) state.children = data.children;
      state.timetable = { lessons: [data.lesson], period_times: {} };
      state.absence = { data: { entries: data.entries }, connectionId: "s1" };
      return todayChapter("normal").blocks.filter((block) => block.key.includes(":absence:")).map((block) => block.key);
    }`, { children: children || null, lesson: LESSON, entries });
  }

  const today = { kind: "sick", status: "accepted", from_date: "2026-09-01", till_date: "2026-09-01" };

  test("matches the child by its student id, not by the timetable key", () => {
    const { window } = loadApp();
    seed(window);
    expect(absent(window, [{ id: "a1", student_id: "4711", ...today }])).toEqual([`${CHILD}:absence:a1`]);
  });

  test("an absence of a sibling stays out", () => {
    const { window } = loadApp();
    seed(window);
    const children = [
      { key: CHILD, name: "Alex", student_id: 4711 },
      { key: "s1:c2", name: "Sam", student_id: 4712 },
    ];
    expect(absent(window, [{ id: "a2", student_id: 4712, ...today }], children)).toEqual([]);
  });

  test("an absence without a student id counts only when the school has a single child", () => {
    const { window } = loadApp();
    seed(window);
    expect(absent(window, [{ id: "a3", ...today }])).toEqual([`${CHILD}:absence:a3`]);
    const children = [
      { key: CHILD, name: "Alex", student_id: 4711 },
      { key: "s1:c2", name: "Sam", student_id: 4712 },
    ];
    expect(absent(window, [{ id: "a3", ...today }], children)).toEqual([]);
  });

  test("an absence of another school stays out", () => {
    const { window } = loadApp();
    seed(window);
    const result = at(window, "2026-09-01T07:00:00", `function (child, data) {
      state.timetable = { lessons: [data], period_times: {} };
      state.absence = { data: { entries: [{ id: "a4", student_id: 4711, kind: "sick", status: "accepted", from_date: "2026-09-01", till_date: "2026-09-01" }] }, connectionId: "s2" };
      return todayChapter("normal").blocks.filter((block) => block.key.includes(":absence:")).length;
    }`, LESSON);
    expect(result).toBe(0);
  });
});

describe("the overview follows the clock", () => {
  test("it re-renders once the next lesson boundary has passed, not before", () => {
    const { window } = loadApp();
    seed(window);
    const wake = at(window, "2026-09-01T07:30:00", `function (child, data) {
      state.timetable = { lessons: [data], period_times: {} };
      overviewChapters();
      return overviewWakeAt ? overviewWakeAt.getHours() * 60 + overviewWakeAt.getMinutes() : null;
    }`, LESSON);
    expect(wake).toBe(8 * 60);
    const calls = at(window, "2026-09-01T07:59:00", `function () {
      let count = 0;
      const real = rerender;
      rerender = () => { count += 1; };
      state.view = "overview";
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      overviewTick();
      rerender = real;
      return count;
    }`);
    expect(calls).toBe(0);
    const later = at(window, "2026-09-01T08:00:30", `function () {
      let count = 0;
      const real = rerender;
      rerender = () => { count += 1; };
      state.view = "overview";
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      overviewTick();
      rerender = real;
      return count;
    }`);
    expect(later).toBe(1);
  });

  test("after midnight it reloads instead of showing yesterday as today", () => {
    const { window } = loadApp();
    seed(window);
    at(window, "2026-09-01T23:59:00", "function () { overviewChapters(); return 0; }");
    const refreshed = at(window, "2026-09-02T00:00:30", `function () {
      let count = 0;
      const real = refreshActiveView;
      refreshActiveView = () => { count += 1; return Promise.resolve(); };
      state.view = "overview";
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      overviewTick();
      refreshActiveView = real;
      return count;
    }`);
    expect(refreshed).toBe(1);
  });
});
