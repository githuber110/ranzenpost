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

describe("[P100-BUG] overviewToday renders every lesson as a tile", () => {
  test("no lead heading: all today's lessons (including the next one) are .row tiles", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
        { day_of_week: 2, period: 3, start_time: "09:50", subject_code: "E" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "SP" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, {
      1: "08:00",
      2: "08:50",
      3: "09:50",
      4: "10:40",
    });
    expect(section.querySelector(".lead")).toBeNull();
    const tiles = section.querySelectorAll(".rows.flat .row");
    expect(tiles.length).toBe(4);
    expect(tiles[0].classList.contains("next")).toBe(true);
    expect(tiles[1].classList.contains("next")).toBe(false);
  });

  test("[P118] past lessons stay in the list but get the dimmed 'past' style, never filtered out", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
        { day_of_week: 2, period: 3, start_time: "09:50", subject_code: "E" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T10:00:00", week, {
      1: "08:00",
      2: "08:50",
      3: "09:50",
    });
    const tiles = section.querySelectorAll(".rows.flat .row");
    expect(tiles.length).toBe(3);
    const titles = [...tiles].map((tile) => tile.querySelector(".row-title").textContent);
    expect(titles).toEqual(["D", "M", "E"]);
    expect(tiles[0].classList.contains("past")).toBe(true);
    expect(tiles[1].classList.contains("past")).toBe(true);
    expect(tiles[2].classList.contains("past")).toBe(false);
  });

  test("[P133][P178] the chapter head carries the 'Zum Stundenplan' link into the timetable view", () => {
    const { window } = loadApp();
    const week = { lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week);
    const button = section.querySelector(".panel-head .panel-link");
    expect(button.textContent).toBe("Zum Stundenplan");
  });

  test("[P178] with configured period times the head link becomes the end of the school day", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const button = section.querySelector(".panel-head .panel-link");
    expect(button.textContent).toBe("bis 09:35");
  });
});

describe("[P140a] overview: no Morgen-pivot, calm evening note instead", () => {
  test("Tuesday evening, all of today's lessons long over: a single calm note, no second section, no 'Morgen'", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T20:00:00", week, { 1: "08:00", 2: "08:50" });
    const overlines = [...section.querySelectorAll(".section-label")].map((o) => o.textContent);
    expect(overlines).toEqual(["Heute"]);
    expect(section.querySelectorAll(".panel").length).toBe(0);
    const tiles = section.querySelectorAll(".rows.flat .row");
    expect(tiles.length).toBe(3);
    expect(tiles[0].classList.contains("past")).toBe(true);
    expect(tiles[1].classList.contains("past")).toBe(true);
    expect(tiles[2].classList.contains("row-note")).toBe(true);
    expect(section.textContent).toContain("Der Unterricht ist für heute vorbei.");
    expect(section.textContent).not.toContain("Morgen");
  });

  test("no 'Morgen' text anywhere in the overview regardless of time of day", () => {
    const { window } = loadApp();
    const week = {
      lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }],
      period_times: {},
    };
    for (const iso of ["2026-09-01T06:00:00", "2026-09-01T12:00:00", "2026-09-01T23:59:00"]) {
      const section = renderOverviewTodayAt(window, iso, week, { 1: "08:00" });
      expect(section.textContent).not.toContain("Morgen");
    }
  });

  test("weekend: no dedicated pivot day, just today's (empty) schedule", () => {
    const { window } = loadApp();
    const week = { lessons: [], period_times: {} };
    const section = renderOverviewTodayAt(window, "2026-09-05T10:00:00", week);
    expect(section.querySelector(".section-label").textContent).toBe("Heute");
    expect(section.textContent).toContain("Heute ist schulfrei.");
    expect(section.textContent).not.toContain("Morgen");
  });

  test("overviewView never prefetches week=1, on a weekend or otherwise", () => {
    const { window } = loadApp();
    window.eval(`
      window.__weeks = [];
      loadOverviewWeek = (childId, week) => { window.__weeks.push(week); return Promise.resolve(); };
      autoLoad = (key, fn) => fn();
      state.children = [{ child_id: "solo" }];
      state.overviewWeeks = {};
      state.absence = {};
      state.letters = {};
      state.pinboard = {};
      state.conferences = {};
      state.me = {};
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate("2026-09-05T10:00:00");
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      overviewView();
      Date = RealDate;
    `);
    expect(window.eval("window.__weeks")).toEqual([0]);
  });
});
