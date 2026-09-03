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

describe("[C22] today card: 'Jetzt'/'Als Naechstes' label on the highlighted row", () => {
  test("during a lesson's 45-minute window, the highlighted row says 'Jetzt'", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, { 1: "08:00" });
    const next = section.querySelector(".row.next");
    expect(next.querySelector(".row-now-label").textContent).toBe("Jetzt");
  });

  test("before a lesson starts, the highlighted row says 'Als Naechstes'", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "10:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "10:00" });
    const next = section.querySelector(".row.next");
    expect(next.querySelector(".row-now-label").textContent).toBe("Als Nächstes");
  });

  test("only the highlighted row carries the label, later rows do not", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const rows = section.querySelectorAll(".rows.flat .row");
    expect(rows[0].querySelector(".row-now-label")).not.toBeNull();
    expect(rows[1].querySelector(".row-now-label")).toBeNull();
  });

  test("the .row.next highlight and the label always render together", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, { 1: "08:00" });
    const highlighted = section.querySelectorAll(".row.next");
    expect(highlighted.length).toBe(1);
    expect(highlighted[0].querySelector(".row-now-label")).not.toBeNull();
    const notHighlighted = Array.from(section.querySelectorAll(".row")).filter((r) => !r.classList.contains("next"));
    for (const row of notHighlighted) expect(row.querySelector(".row-now-label")).toBeNull();
  });

  test("[P118] 'now' comes from configured period_times, not the school/IServ-provided times", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "09:00", subject_code: "D" }],
      period_times: { 1: "09:00" },
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, { 1: "08:00" });
    const next = section.querySelector(".row.next");
    expect(next.querySelector(".row-now-label").textContent).toBe("Jetzt");
  });

  test("[P138] a free period does not stretch the previous lesson's 'now' window: it ends at the next configured period, not the next lesson's period", () => {
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
    const rows = section.querySelectorAll(".rows.flat .row");
    expect(rows[0].querySelector(".row-title").textContent).toBe("M");
    expect(rows[0].classList.contains("past")).toBe(true);
    expect(rows[0].classList.contains("next")).toBe(false);
    expect(rows[1].querySelector(".row-title").textContent).toBe("SP");
    expect(rows[1].classList.contains("next")).toBe(true);
    expect(rows[1].querySelector(".row-now-label").textContent).toBe("Als Nächstes");
  });

  test("[P118] configured period_times empty: no row is marked now/next", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T08:20:00", week, {});
    expect(section.querySelector(".row.next")).toBeNull();
  });
});
