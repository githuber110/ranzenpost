import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const LESSON = {
  day_of_week: 2,
  period: 1,
  subject_code: "D",
  subject_label: "Deutsch",
  room: "R1",
  start_time: "08:00",
  end_time: "08:45",
  change_kind: "",
};

function seed(window, entered) {
  window.eval(`
    state.config = { subjects: {}, teachers: {}, period_times: ${JSON.stringify(entered)} };
    state.timetable = { lessons: [], period_times: ${JSON.stringify(entered)} };
    state.childId = "c1";
    state.children = [{ child_id: "c1", name: "Mia" }];
  `);
}

function resolve(window, lesson, times) {
  return window.eval(`(function (lesson, times) { return lessonTime(lesson, times); })`)(
    lesson,
    times === undefined ? null : times
  );
}

describe("[P246] only the entered lesson times count", () => {
  test("an entered time beats the one the school sent", () => {
    const { window } = loadApp();
    seed(window, { 1: "07:40" });
    expect(resolve(window, LESSON, { 1: "07:40" })).toBe("07:40");
  });

  test("a period left empty falls back to the school time", () => {
    const { window } = loadApp();
    seed(window, { 1: "" });
    expect(resolve(window, LESSON, { 1: "" })).toBe("08:00");
  });

  test("a period the settings do not mention falls back too", () => {
    const { window } = loadApp();
    seed(window, { 2: "09:00" });
    expect(resolve(window, LESSON, { 2: "09:00" })).toBe("08:00");
  });

  test("without a table of its own it reads the settings", () => {
    const { window } = loadApp();
    seed(window, { 1: "07:40" });
    expect(resolve(window, LESSON)).toBe("07:40");
  });

  test("a lesson with no time at all stays empty rather than guessing", () => {
    const { window } = loadApp();
    seed(window, {});
    expect(resolve(window, Object.assign({}, LESSON, { start_time: "" }), {})).toBe("");
  });
});

describe("[P246] the overview follows the entered times", () => {
  function overviewRow(window, entered) {
    seed(window, entered);
    return window.eval(`(function (entry) { return compactLesson(entry, false); })`)({
      lesson: LESSON,
      time: window.eval(`(function (l) { return lessonTime(l, state.config.period_times); })`)(LESSON),
      childId: "c1",
    });
  }

  test("the row shows the entered time, not the school one", () => {
    const { window } = loadApp();
    const row = overviewRow(window, { 1: "07:40" });
    expect(row.querySelector(".row-meta").textContent).toBe("07:40");
  });

  test("the row shows the school time where nothing was entered", () => {
    const { window } = loadApp();
    const row = overviewRow(window, {});
    expect(row.querySelector(".row-meta").textContent).toBe("08:00");
  });
});
