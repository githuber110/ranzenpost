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
    const tiles = section.querySelectorAll(".rows.flat .row:not(.row-note)");
    expect(tiles.length).toBe(4);
    expect(tiles[0].classList.contains("next")).toBe(false);
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
    const tiles = section.querySelectorAll(".rows.flat .row:not(.row-note)");
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

  test("[P207] the head keeps the timetable link and never shows an end time", () => {
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
    expect(button.textContent).toBe("Zum Stundenplan");
    expect(section.textContent).not.toContain("bis ");
  });

  test("[P226] every lesson shows only its start time, the end time is gone from the rows", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const metas = [...section.querySelectorAll(".rows.flat .row:not(.row-note) .row-meta")].map((node) => node.textContent);
    expect(metas).toEqual(["08:00", "08:50"]);
  });

  test("[P226] before the last lesson ends a note says when school is out today", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const note = section.querySelector(".rows.flat .row-note");
    expect(note.textContent).toBe(window.eval('t("overview.schoolEnds", { time: "09:35" })'));
  });

  test("[P226] a cancelled last lesson pulls the end of school forward", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M", change_kind: "cancelled" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const note = section.querySelector(".rows.flat .row-note");
    expect(note.textContent).toBe(window.eval('t("overview.schoolEnds", { time: "08:45" })'));
  });

  test("[P226] once every lesson is over the note switches to the day-over line", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T09:35:00", week, { 1: "08:00", 2: "08:50" });
    const note = section.querySelector(".rows.flat .row-note");
    expect(note.textContent).toBe(window.eval('t("overview.dayOver")'));
  });

  test("[P226] when every lesson of the day is cancelled the day-over line stands right away", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D", change_kind: "cancelled" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M", change_kind: "cancelled" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week, { 1: "08:00", 2: "08:50" });
    const note = section.querySelector(".rows.flat .row-note");
    expect(note.textContent).toBe(window.eval('t("overview.dayOver")'));
  });
});

describe("[P224] the today card marks the running and the upcoming lesson in words", () => {
  const week = {
    lessons: [
      { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
      { day_of_week: 2, period: 2, start_time: "08:45", subject_code: "SP" },
      { day_of_week: 2, period: 3, start_time: "09:45", subject_code: "M" },
    ],
    period_times: {},
  };
  const times = { 1: "08:00", 2: "08:45", 3: "09:45" };

  function rowsAt(window, iso) {
    const section = renderOverviewTodayAt(window, iso, week, times);
    return [...section.querySelectorAll(".rows.flat .row:not(.row-note)")];
  }

  test("[P224] 44 minutes in the lesson still runs and carries the now label", () => {
    const { window } = loadApp();
    const rows = rowsAt(window, "2026-09-01T09:29:00");
    expect(rows[1].classList.contains("past")).toBe(false);
    expect(rows[1].querySelector(".row-when.now").textContent).toBe(window.eval('t("overview.mark.now")'));
  });

  test("[P224] exactly at start plus 45 minutes the lesson counts as past", () => {
    const { window } = loadApp();
    const rows = rowsAt(window, "2026-09-01T09:30:00");
    expect(rows[1].classList.contains("past")).toBe(true);
    expect(rows[1].querySelector(".row-when")).toBeNull();
  });

  test("[P224] at start plus 46 minutes the finished lesson stays greyed out and the gap points at the next one", () => {
    const { window } = loadApp();
    const rows = rowsAt(window, "2026-09-01T09:31:00");
    expect(rows[0].classList.contains("past")).toBe(true);
    expect(rows[1].classList.contains("past")).toBe(true);
    expect(rows[2].classList.contains("past")).toBe(false);
    expect(rows[2].querySelector(".row-when.next").textContent).toBe(window.eval('t("overview.mark.next")'));
    expect(rows.filter((row) => row.querySelector(".row-when.now")).length).toBe(0);
  });

  test("[P224] the reported bug: at 09:38 the 08:45 lesson is past and the 09:00 lesson is the running one", () => {
    const { window } = loadApp();
    const reported = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:45", subject_code: "SP" },
        { day_of_week: 2, period: 2, start_time: "09:00", subject_code: "M" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T09:38:00", reported, { 1: "08:45", 2: "09:00" });
    const rows = [...section.querySelectorAll(".rows.flat .row:not(.row-note)")];
    expect(rows[0].classList.contains("past")).toBe(true);
    expect(rows[1].classList.contains("past")).toBe(false);
    expect(rows[1].querySelector(".row-when.now")).not.toBeNull();
  });

  test("[P224] before the first lesson the first one is labelled as next", () => {
    const { window } = loadApp();
    const rows = rowsAt(window, "2026-09-01T06:00:00");
    expect(rows[0].querySelector(".row-when.next")).not.toBeNull();
  });

  test("[P224] the last lesson of the day expires on its own end time, without a successor", () => {
    const { window } = loadApp();
    const lastOnly = { lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
    const before = renderOverviewTodayAt(window, "2026-09-01T08:44:00", lastOnly, { 1: "08:00" });
    expect(before.querySelector(".rows.flat .row:not(.row-note)").classList.contains("past")).toBe(false);
    const after = renderOverviewTodayAt(window, "2026-09-01T08:45:00", lastOnly, { 1: "08:00" });
    expect(after.querySelector(".rows.flat .row:not(.row-note)").classList.contains("past")).toBe(true);
    expect(after.querySelector(".rows.flat .row-note").textContent).toBe(window.eval('t("overview.dayOver")'));
  });

  test("[P224] a cancelled lesson never carries the now or next label", () => {
    const { window } = loadApp();
    const withGap = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D", change_kind: "cancelled" },
        { day_of_week: 2, period: 2, start_time: "08:45", subject_code: "SP" },
      ],
      period_times: {},
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", withGap, { 1: "08:00", 2: "08:45" });
    const rows = [...section.querySelectorAll(".rows.flat .row:not(.row-note)")];
    expect(rows[0].querySelector(".row-when")).toBeNull();
    expect(rows[1].querySelector(".row-when.next")).not.toBeNull();
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
