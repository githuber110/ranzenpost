import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const WEEK = {
  lessons: [
    { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
    { day_of_week: 1, period: 2, subject_code: "M", start_time: "08:50" },
    { day_of_week: 2, period: 1, subject_code: "D", start_time: "08:00" },
    { day_of_week: 3, period: 3, subject_code: "D", start_time: "09:50" },
    { day_of_week: 4, period: 2, subject_code: "M", start_time: "08:50" },
  ],
  period_times: { 1: "08:00", 2: "08:50", 3: "09:50" },
};

function renderGrid(window, week) {
  const run = window.eval(`
    (function (week) {
      state.timetable = week;
      state.weekOffset = 0;
      state.config = { period_times: week.period_times || {} };
      return timetableGrid(week);
    })
  `);
  return run(week || WEEK);
}

function spotlightOf(window) {
  return window.eval("state.spotlightSubject");
}

function cellsFor(grid, subject) {
  return [...grid.querySelectorAll(`.tt-cell[data-subject="${subject}"]`)];
}

describe("[P212] tapping a lesson spotlights that subject across the week", () => {
  test("every lesson cell carries its subject so the whole week can be addressed", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    expect(cellsFor(grid, "D").length).toBe(3);
    expect(cellsFor(grid, "M").length).toBe(2);
  });

  test("a tap turns the spotlight on for that subject", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    cellsFor(grid, "D")[0].click();
    expect(spotlightOf(window)).toBe("D");
  });

  test("tapping another subject switches the spotlight instead of adding one", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    cellsFor(grid, "D")[0].click();
    cellsFor(grid, "M")[0].click();
    expect(spotlightOf(window)).toBe("M");
  });

  test("a tap on a free slot clears the spotlight", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    cellsFor(grid, "D")[0].click();
    expect(spotlightOf(window)).toBe("D");
    const free = grid.querySelector(".tt-cell.free");
    expect(free).not.toBeNull();
    free.click();
    expect(spotlightOf(window)).toBe(null);
  });

  test("a rebuilt grid marks exactly the spotlit subject and flags itself", () => {
    const { window } = loadApp();
    renderGrid(window);
    window.eval('state.spotlightSubject = "D";');
    const grid = renderGrid(window);
    expect(grid.classList.contains("spotlight")).toBe(true);
    expect(cellsFor(grid, "D").every((cell) => cell.classList.contains("spot"))).toBe(true);
    expect(cellsFor(grid, "M").some((cell) => cell.classList.contains("spot"))).toBe(false);
  });

  test("without a spotlight the grid carries no dimming flag at all", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    expect(grid.classList.contains("spotlight")).toBe(false);
    expect(grid.querySelectorAll(".tt-cell.spot").length).toBe(0);
  });

  test("switching the tab resets the spotlight", () => {
    const { window } = loadApp();
    renderGrid(window);
    window.eval('state.spotlightSubject = "D"; setView("settings");');
    expect(spotlightOf(window)).toBe(null);
  });

  test("the spotlight survives a week change so the subject can be followed forwards", () => {
    const { window } = loadApp();
    renderGrid(window);
    window.eval('state.spotlightSubject = "D"; shiftWeek(1);');
    expect(spotlightOf(window)).toBe("D");
  });
});

describe("[P212] the detail sheet counts the subject's occurrences in the week", () => {
  test("the first of three says so, the last says so", () => {
    const { window } = loadApp();
    renderGrid(window);
    const position = window.eval(`
      (function () {
        const first = state.timetable.lessons[0];
        const last = state.timetable.lessons[3];
        return [lessonWeekPosition(first, state.timetable.lessons), lessonWeekPosition(last, state.timetable.lessons)];
      })()
    `);
    expect(position[0]).toEqual({ position: 1, total: 3 });
    expect(position[1]).toEqual({ position: 3, total: 3 });
  });

  test("a subject that happens once is the first of one", () => {
    const { window } = loadApp();
    renderGrid(window, {
      lessons: [{ day_of_week: 1, period: 1, subject_code: "SP", start_time: "08:00" }],
      period_times: { 1: "08:00" },
    });
    const position = window.eval("lessonWeekPosition(state.timetable.lessons[0], state.timetable.lessons)");
    expect(position).toEqual({ position: 1, total: 1 });
  });

  test("cancelled lessons do not inflate the count", () => {
    const { window } = loadApp();
    renderGrid(window, {
      lessons: [
        { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
        { day_of_week: 2, period: 1, subject_code: "D", start_time: "08:00", change_kind: "cancelled" },
      ],
      period_times: { 1: "08:00" },
    });
    const position = window.eval("lessonWeekPosition(state.timetable.lessons[0], state.timetable.lessons)");
    expect(position).toEqual({ position: 1, total: 1 });
  });
});

describe("[R2-19/23] the week count uses the right child, week and school days", () => {
  test("a subject-less lesson keeps the spotlight instead of silently dropping it", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, {
      lessons: [
        { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
        { day_of_week: 1, period: 2, subject_code: "", subject_label: "", start_time: "08:50" },
      ],
      period_times: { 1: "08:00", 2: "08:50" },
    });
    cellsFor(grid, "D")[0].click();
    expect(spotlightOf(window)).toBe("D");
    const blank = [...grid.querySelectorAll(".tt-cell:not(.free)")].find((cell) => !cell.dataset.subject);
    expect(blank).toBeTruthy();
    blank.click();
    expect(spotlightOf(window)).toBe("D");
  });

  test("the count is taken from the lessons handed in, not from whatever the timetable tab holds", () => {
    const { window } = loadApp();
    renderGrid(window, {
      lessons: [
        { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
        { day_of_week: 2, period: 1, subject_code: "D", start_time: "08:00" },
        { day_of_week: 3, period: 1, subject_code: "D", start_time: "08:00" },
      ],
      period_times: { 1: "08:00" },
    });
    const otherWeek = [
      { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
      { day_of_week: 4, period: 2, subject_code: "D", start_time: "08:50" },
    ];
    const position = window.eval(`lessonWeekPosition(${JSON.stringify(otherWeek[1])}, ${JSON.stringify(otherWeek)})`);
    expect(position).toEqual({ position: 2, total: 2 });
  });

  test("an empty week source yields no count line at all", () => {
    const { window } = loadApp();
    renderGrid(window);
    const position = window.eval("lessonWeekPosition(state.timetable.lessons[0], [])");
    expect(position).toBe(null);
  });

  test("lessons on a holiday-blocked day are not counted", () => {
    const { window } = loadApp();
    const lessons = [
      { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00", date: "01.09.2026" },
      { day_of_week: 5, period: 1, subject_code: "D", start_time: "08:00", date: "04.09.2026" },
    ];
    window.eval(`
      state.timetable = { lessons: ${JSON.stringify(lessons)}, period_times: { 1: "08:00" } };
      state.config = { period_times: { 1: "08:00" } };
      holidayBlocksLessons = function (iso) { return iso === "2026-09-04"; };
    `);
    const position = window.eval(`lessonWeekPosition(${JSON.stringify(lessons[0])}, state.timetable.lessons)`);
    expect(position).toEqual({ position: 1, total: 1 });
  });
});

describe("[R2-24] the spotlight can be cleared from the keyboard", () => {
  test("Escape inside the grid clears an active spotlight", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    cellsFor(grid, "D")[0].click();
    expect(spotlightOf(window)).toBe("D");
    grid.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(spotlightOf(window)).toBe(null);
  });

  test("Escape without a spotlight is left for the rest of the app", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    let bubbled = false;
    grid.addEventListener("keydown", () => { bubbled = true; }, true);
    grid.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(bubbled).toBe(true);
    expect(spotlightOf(window)).toBe(null);
  });
});
