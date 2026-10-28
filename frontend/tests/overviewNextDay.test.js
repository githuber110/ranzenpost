import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const CHILD = "s1:c1";

function renderNextDayAt(window, fixedIso, weeks) {
  const run = window.eval(`
    (function (fixedIso, weeks, child) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.children = [{ key: child, name: "Alex" }];
      state.childId = child;
      state.weekOffset = 0;
      state.timetable = weeks[0] || null;
      state.overviewWeeks = { [child]: Object.assign({}, weeks) };
      state.config = { period_times: {} };
      const chapter = nextDayChapter("normal");
      const node = chapter ? overviewFlatten(document.createElement("div"), [chapter])[0] || null : null;
      Date = RealDate;
      return { chapter, node };
    })
  `);
  return run(fixedIso, weeks, CHILD);
}

function lesson(day, period, code, extra = {}) {
  return { day_of_week: day, period, start_time: `0${7 + period}:00`, subject_code: code, ...extra };
}

describe("the next school day block of the overview", () => {
  test("shows tomorrow under the label tomorrow with its lessons and changes", () => {
    const { window } = loadApp();
    const week = { lessons: [lesson(2, 1, "D"), lesson(3, 1, "MA"), lesson(3, 2, "EN", { change_kind: "cancelled" })], period_times: {} };
    const { chapter, node } = renderNextDayAt(window, "2026-09-01T10:00:00", { 0: week });

    expect(chapter.title).toBe("Morgen");
    expect(chapter.count).toBe(1);
    const titles = [...node.querySelectorAll(".rows.flat .row-title")].map((item) => item.textContent);
    expect(titles).toEqual(["MA", "EN"]);
  });

  test("on a Friday it finds Monday in the next week and names weekday and date", () => {
    const { window } = loadApp();
    const thisWeek = { lessons: [lesson(5, 1, "D")], period_times: {} };
    const nextWeek = { lessons: [lesson(1, 1, "BIO")], period_times: {} };
    const { chapter } = renderNextDayAt(window, "2026-09-04T13:00:00", { 0: thisWeek, 1: nextWeek });

    expect(chapter.title).toBe("Montag");
    expect(chapter.meta).toBe("07.09.2026");
  });

  test("waits for a week that is not loaded yet instead of calling the day free", () => {
    const { window } = loadApp();
    const thisWeek = { lessons: [lesson(5, 1, "D")], period_times: {} };
    const { chapter } = renderNextDayAt(window, "2026-09-04T13:00:00", { 0: thisWeek });

    expect(chapter.loading).toBe(true);
  });

  test("shows the failure with a retry instead of calling the next school day unknown when a week fails", () => {
    const { window } = loadApp();
    const thisWeek = { lessons: [lesson(5, 1, "D")], period_times: {} };
    const { chapter, node } = renderNextDayAt(window, "2026-09-04T13:00:00", { 0: thisWeek, 1: { error: "unreachable" } });

    expect(chapter.blocks.map((block) => block.key)).toEqual(["next_day:failed"]);
    expect(node.textContent).not.toContain("Der nächste Schultag steht noch nicht im Stundenplan.");
  });

  test("says honestly that the next school day is unknown when no week holds one", () => {
    const { window } = loadApp();
    const empty = { lessons: [], period_times: {} };
    const { chapter, node } = renderNextDayAt(window, "2026-09-04T13:00:00", { 0: empty, 1: empty, 2: empty, 3: empty, 4: empty });

    expect(chapter.title).toBe("Nächster Schultag");
    expect(node.textContent).toContain("Der nächste Schultag steht noch nicht im Stundenplan.");
  });
});

describe("the next lesson block of the overview during holidays", () => {
  test("skips lessons on holiday days and finds the first lesson after the holidays", () => {
    const { window } = loadApp();
    const run = window.eval(`
      (function (child) {
        const RealDate = Date;
        function FixedDate(...args) { return args.length ? new RealDate(...args) : new RealDate("2026-10-21T15:00:00"); }
        FixedDate.prototype = RealDate.prototype;
        Date = FixedDate;
        const days = {};
        for (const iso of ["2026-10-22", "2026-10-23"]) days[iso] = { free: true, overrides_lessons: true, kind: "school", name: "Herbstferien", period_id: "h1" };
        state.holidays = { s1: { status: "ok", kind: "school", weeks: [], periods: [], days } };
        state.children = [{ key: child, name: "Alex", connection_id: "s1" }];
        state.childId = child;
        state.weekOffset = 0;
        const lesson = (day, code) => ({ day_of_week: day, period: 1, start_time: "07:55", subject_code: code });
        state.timetable = { lessons: [lesson(4, "MA"), lesson(5, "EN")], period_times: {} };
        state.overviewWeeks = { [child]: { 0: state.timetable, 1: { lessons: [lesson(1, "D")], period_times: {} } } };
        state.config = { period_times: {} };
        const chapter = nextLessonChapter("normal");
        Date = RealDate;
        return chapter.blocks.map((block) => block.node.textContent);
      })
    `);
    const rows = run("s1:c1");
    expect(rows.some((text) => text.includes("MA") || text.includes("EN"))).toBe(false);
    expect(rows[0]).toContain("D");
  });
});

function renderTodayAt(window, fixedIso, weeks, entry, holidays) {
  const run = window.eval(`
    (function (fixedIso, weeks, child, entry, holidays) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.children = [{ key: child, name: "Alex", connection_id: "s1" }];
      state.childId = child;
      state.weekOffset = 0;
      state.timetable = weeks[0] || null;
      state.overviewWeeks = { [child]: Object.assign({}, weeks) };
      state.holidays = holidays || {};
      state.config = { period_times: {} };
      const chapter = todayChapter("normal", entry);
      const node = chapter ? overviewFlatten(document.createElement("div"), [chapter])[0] || null : null;
      Date = RealDate;
      return { chapter, node };
    })
  `);
  return run(fixedIso, weeks, CHILD, entry, holidays || null);
}

describe("the today block can switch to the next school day", () => {
  const week = { lessons: [lesson(2, 1, "D"), lesson(3, 1, "MA")], period_times: {} };

  test("from a set time it shows tomorrow under the label tomorrow, before that still today", () => {
    const { window } = loadApp();
    const late = renderTodayAt(window, "2026-09-01T15:30:00", { 0: week }, { key: "today", size: "normal", switch: "15:00" });
    expect(late.chapter.area).toBe("today");
    expect(late.chapter.title).toBe("Morgen");
    expect([...late.node.querySelectorAll(".row-title")].map((item) => item.textContent)).toEqual(["MA"]);

    const early = renderTodayAt(window, "2026-09-01T14:59:00", { 0: week }, { key: "today", size: "normal", switch: "15:00" });
    expect(early.chapter.title).toBe("Heute");
  });

  test("after the last lesson it switches, during the lessons it does not", () => {
    const { window } = loadApp();
    const entry = { key: "today", size: "normal", switch: "end" };
    expect(renderTodayAt(window, "2026-09-01T08:10:00", { 0: week }, entry).chapter.title).toBe("Heute");
    expect(renderTodayAt(window, "2026-09-01T10:00:00", { 0: week }, entry).chapter.title).toBe("Morgen");
  });

  test("on a holiday it switches right away and skips the holiday days", () => {
    const { window } = loadApp();
    const days = {};
    for (const iso of ["2026-09-01", "2026-09-02"]) days[iso] = { free: true, overrides_lessons: true, kind: "school", name: "Herbstferien", period_id: "h1" };
    const holidays = { s1: { status: "ok", kind: "school", weeks: [], periods: [], days } };
    const holidayWeek = { lessons: [lesson(2, 1, "D"), lesson(3, 1, "MA"), lesson(4, 1, "EN")], period_times: {} };
    const { chapter, node } = renderTodayAt(window, "2026-09-01T08:10:00", { 0: holidayWeek }, { key: "today", size: "normal", switch: "end" }, holidays);
    expect(chapter.title).toBe("Donnerstag");
    expect([...node.querySelectorAll(".row-title")].map((item) => item.textContent)).toEqual(["EN"]);
  });

  test("without a switch the today block stays today after school", () => {
    const { window } = loadApp();
    expect(renderTodayAt(window, "2026-09-01T18:00:00", { 0: week }, { key: "today", size: "normal" }).chapter.title).toBe("Heute");
  });
});

describe("the today switch follows real school days and lesson lengths", () => {
  test("with a set time a Saturday already shows Monday in the morning", () => {
    const { window } = loadApp();
    const thisWeek = { lessons: [lesson(5, 1, "D")], period_times: {} };
    const nextWeek = { lessons: [lesson(1, 1, "BIO")], period_times: {} };
    const { chapter } = renderTodayAt(window, "2026-09-05T10:00:00", { 0: thisWeek, 1: nextWeek }, { key: "today", size: "normal", switch: "15:00" });
    expect(chapter.title).toBe("Montag");
  });

  test("after the last lesson waits for the end of a 90 minute block from the school's period grid", () => {
    const { window } = loadApp();
    window.eval('state.periods = { s1: { grid: [{ number: 1, start: "08:00", end: "09:30", duration: 90 }], entries: [] } };');
    const week = { lessons: [lesson(2, 1, "D"), lesson(3, 1, "MA")], period_times: {} };
    const entry = { key: "today", size: "normal", switch: "end" };
    expect(renderTodayAt(window, "2026-09-01T09:10:00", { 0: week }, entry).chapter.title).toBe("Heute");
    expect(renderTodayAt(window, "2026-09-01T09:31:00", { 0: week }, entry).chapter.title).toBe("Morgen");
  });
});
