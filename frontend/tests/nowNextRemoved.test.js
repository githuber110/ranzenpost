import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderOverviewTodayAt(window, fixedDate, week, configPeriodTimes) {
  const run = window.eval(`
    (function (fixedIso, week, configPeriodTimes) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.weekOffset = 0;
      state.timetable = week;
      state.config = { period_times: configPeriodTimes || {} };
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedDate, week, configPeriodTimes);
}

describe("[P206] the today card no longer paints the running or the next lesson", () => {
  test("[P224] during a lesson the row carries a word mark but never the highlight class", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, { 1: "08:00" });
    expect(section.querySelector(".row.next")).toBeNull();
    expect(section.querySelector(".row.now")).toBeNull();
    expect(section.querySelector(".row-when.now")).not.toBeNull();
  });

  test("[P224] before the first lesson the next one is named in words, not painted", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "10:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "10:00" });
    expect(section.querySelector(".row.next")).toBeNull();
    expect(section.querySelector(".row-when.next")).not.toBeNull();
  });

  test("past lessons stay greyed out", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "SP" },
      ],
      period_times: {},
    };
    const configPeriodTimes = { 1: "08:00", 2: "08:50", 3: "09:50", 4: "10:40" };
    const section = renderOverviewTodayAt(window, "2026-09-01T10:00:00", week, configPeriodTimes);
    const rows = section.querySelectorAll(".rows.flat .row:not(.row-note)");
    expect(rows[0].querySelector(".row-title").textContent).toBe("M");
    expect(rows[0].classList.contains("past")).toBe(true);
    expect(rows[1].querySelector(".row-title").textContent).toBe("SP");
    expect(rows[1].classList.contains("past")).toBe(false);
  });

  test("the now detection survives as the entry anchor even though the styling is gone", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, { 1: "08:00", 2: "08:50" });
    const current = section.querySelectorAll('[aria-current="true"]');
    expect(current.length).toBe(1);
    expect(current[0].querySelector(".row-title").textContent).toBe("D");
  });
});
