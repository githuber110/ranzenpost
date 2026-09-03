import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderGrid(window, lessons) {
  const run = window.eval(
    "(function (data) { state.childId = 'c1'; state.children = [{ child_id: 'c1' }]; return timetableGrid(data); })"
  );
  return run({ lessons, period_times: {} });
}

describe("[C13] timetable: trailing empty rows are capped, legend drops 'frei'", () => {
  test("a week with lessons only up to period 3 renders exactly 3 hour rows", () => {
    const { window } = loadApp();
    const lessons = [
      { day_of_week: 1, period: 1, subject_code: "MA" },
      { day_of_week: 2, period: 3, subject_code: "DE" },
    ];
    const grid = renderGrid(window, lessons);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(3);
  });

  test("a mid-week free period (period 2 with no lesson) still renders as a .free cell inside the capped range", () => {
    const { window } = loadApp();
    const lessons = [
      { day_of_week: 1, period: 1, subject_code: "MA" },
      { day_of_week: 1, period: 3, subject_code: "DE" },
    ];
    const grid = renderGrid(window, lessons);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(3);
    expect(grid.querySelectorAll(".tt-cell.free").length).toBeGreaterThan(0);
  });

  test("a completely empty week (holidays) falls back to 5 rows", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, []);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(5);
  });

  test("a 6th-period lesson grows the grid back to 6 rows automatically", () => {
    const { window } = loadApp();
    const lessons = [{ day_of_week: 3, period: 6, subject_code: "PH" }];
    const grid = renderGrid(window, lessons);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(6);
  });

  test("the legend no longer has a 'frei' entry", () => {
    const { window } = loadApp();
    window.eval("state.timetable = { lessons: [], last_updated: null };");
    const view = window.eval("timetableView()");
    const legendText = view.querySelector(".legend").textContent;
    expect(legendText).not.toContain("frei");
    expect(legendText).toContain("Entfällt");
    expect(legendText).toContain("Vertretung");
  });
});
