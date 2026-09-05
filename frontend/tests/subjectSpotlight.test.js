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

function renderTimetableScreen(window, week) {
  const run = window.eval(`
    (function (week) {
      state.config = { period_times: week.period_times || {} };
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.timetable = week;
      state.weekOffset = 0;
      state.view = "timetable";
      render();
      return document.querySelector(".screen");
    })
  `);
  return run(week || WEEK);
}

function tap(window, node) {
  node.dispatchEvent(new window.Event("pointerdown", { bubbles: true }));
  node.dispatchEvent(new window.Event("pointerup", { bubbles: true }));
  node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
}

function pressAndHold(window, node) {
  const realTimeout = window.setTimeout;
  window.setTimeout = (fn) => { fn(); return 0; };
  node.dispatchEvent(new window.Event("pointerdown", { bubbles: true }));
  window.setTimeout = realTimeout;
  node.dispatchEvent(new window.Event("pointerup", { bubbles: true }));
  node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
}

function holdClock(window) {
  const pending = [];
  const realSet = window.setTimeout;
  const realClear = window.clearTimeout;
  window.setTimeout = (fn, ms) => {
    pending.push({ fn, ms, id: pending.length + 1, cancelled: false, fired: false });
    return pending.length;
  };
  window.clearTimeout = (id) => {
    const entry = pending.find((item) => item.id === id);
    if (entry) entry.cancelled = true;
  };
  return {
    scheduled: () => pending.filter((item) => !item.cancelled && !item.fired),
    advance(ms) {
      for (const entry of pending) {
        if (!entry.cancelled && !entry.fired && entry.ms <= ms) {
          entry.fired = true;
          entry.fn();
        }
      }
    },
    restore() {
      window.setTimeout = realSet;
      window.clearTimeout = realClear;
    },
  };
}

function press(window, node, x, y) {
  node.dispatchEvent(new window.MouseEvent("pointerdown", { bubbles: true, clientX: x || 0, clientY: y || 0 }));
}

function move(window, node, x, y) {
  node.dispatchEvent(new window.MouseEvent("pointermove", { bubbles: true, clientX: x, clientY: y }));
}

describe("[P223] a tap opens the details, press and hold spotlights", () => {
  test("every lesson cell carries its subject so the whole week can be addressed", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    expect(cellsFor(grid, "D").length).toBe(3);
    expect(cellsFor(grid, "M").length).toBe(2);
  });

  test("[P223] a plain tap opens the detail sheet and leaves the spotlight alone", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window);
    tap(window, cellsFor(screen, "D")[0]);
    expect(spotlightOf(window)).toBe(null);
    expect(window.eval("!!state.sheet")).toBe(true);
  });

  test("[P223] press and hold spotlights the subject and opens no sheet", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window);
    pressAndHold(window, cellsFor(screen, "D")[0]);
    expect(spotlightOf(window)).toBe("D");
    expect(window.eval("!!state.sheet")).toBe(false);
  });

  test("[P223] while a spotlight stands the first tap anywhere only clears it", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window);
    pressAndHold(window, cellsFor(screen, "D")[0]);
    tap(window, cellsFor(screen, "M")[0]);
    expect(spotlightOf(window)).toBe(null);
    expect(window.eval("!!state.sheet")).toBe(false);
  });

  test("[P223] the next tap after the marking was cleared works normally again", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window);
    pressAndHold(window, cellsFor(screen, "D")[0]);
    tap(window, cellsFor(screen, "M")[0]);
    tap(window, cellsFor(screen, "M")[0]);
    expect(window.eval("!!state.sheet")).toBe(true);
  });

  test("[P223] a tap below the grid clears the marking just as well", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window);
    pressAndHold(window, cellsFor(screen, "D")[0]);
    tap(window, screen.querySelector(".legend") || screen);
    expect(spotlightOf(window)).toBe(null);
  });

  test("[P223] the detail sheet offers the spotlight as a named action", () => {
    const { window } = loadApp();
    renderTimetableScreen(window);
    const label = window.eval(`
      (function () {
        const lesson = state.timetable.lessons[0];
        openLessonSheet(lesson, "08:00", state.childId, state.timetable.lessons);
        const foot = state.sheet().querySelector(".sheet-foot") || state.sheet();
        const button = [...foot.querySelectorAll("button")].find((node) =>
          node.textContent === t("timetable.spotlight.action", { subject: "D" }));
        if (!button) return "";
        button.click();
        return state.spotlightSubject;
      })()
    `);
    expect(label).toBe("D");
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
  test("[P223] press and hold on a subject-less lesson spotlights nothing", () => {
    const { window } = loadApp();
    const screen = renderTimetableScreen(window, {
      lessons: [
        { day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" },
        { day_of_week: 1, period: 2, subject_code: "", subject_label: "", start_time: "08:50" },
      ],
      period_times: { 1: "08:00", 2: "08:50" },
    });
    const blank = [...screen.querySelectorAll(".tt-cell:not(.free)")].find((cell) => !cell.dataset.subject);
    expect(blank).toBeTruthy();
    pressAndHold(window, blank);
    expect(spotlightOf(window)).toBe(null);
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
    window.eval('state.spotlightSubject = "D";');
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

describe("[P223] the hold is a real hold, measured on the clock", () => {
  test("the spotlight waits for the full hold and only then appears", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    const cell = cellsFor(grid, "D")[0];
    const clock = holdClock(window);
    press(window, cell, 100, 100);
    const waiting = clock.scheduled();
    expect(waiting.length).toBe(1);
    expect(waiting[0].ms).toBe(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe(null);
    clock.advance(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe("D");
    clock.restore();
  });

  test("a tap that lets go before the hold elapses never spotlights", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    const cell = cellsFor(grid, "D")[0];
    const clock = holdClock(window);
    press(window, cell, 100, 100);
    cell.dispatchEvent(new window.Event("pointerup", { bubbles: true }));
    clock.advance(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe(null);
    clock.restore();
  });

  test("a small wobble of the finger does not lose the hold", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    const cell = cellsFor(grid, "D")[0];
    const clock = holdClock(window);
    const slop = window.eval("SPOTLIGHT_HOLD_SLOP");
    press(window, cell, 100, 100);
    move(window, cell, 100 + slop, 100 + slop);
    clock.advance(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe("D");
    clock.restore();
  });

  test("a real drag past the tolerance cancels the hold", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    const cell = cellsFor(grid, "D")[0];
    const clock = holdClock(window);
    const slop = window.eval("SPOTLIGHT_HOLD_SLOP");
    press(window, cell, 100, 100);
    move(window, cell, 100 + slop + 5, 100);
    clock.advance(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe(null);
    clock.restore();
  });

  test("a right button press never spotlights", () => {
    const { window } = loadApp();
    const grid = renderGrid(window);
    const cell = cellsFor(grid, "D")[0];
    const clock = holdClock(window);
    cell.dispatchEvent(new window.MouseEvent("pointerdown", { bubbles: true, button: 2, clientX: 5, clientY: 5 }));
    clock.advance(window.eval("SPOTLIGHT_HOLD_MS"));
    expect(spotlightOf(window)).toBe(null);
    clock.restore();
  });
});
