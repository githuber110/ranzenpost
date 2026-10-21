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
