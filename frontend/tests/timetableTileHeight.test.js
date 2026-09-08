import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const WEEK = {
  lessons: [
    { day_of_week: 1, period: 1, subject_code: "D", room: "R1", teacher_label: "Katrin Beispiel", teacher_surname: "Beispiel", change_kind: "" },
    { day_of_week: 1, period: 2, subject_code: "M", room: "R2", teacher_label: "Olga Zweit", teacher_surname: "Zweit", change_kind: "" },
    { day_of_week: 1, period: 2, subject_code: "SP", room: "H1", teacher_label: "Ben Dritt", teacher_surname: "Dritt", change_kind: "" },
  ],
  period_times: { 1: "08:00", 2: "08:50" },
};

function grid(window) {
  window.eval(`
    state.config = { subjects: {}, teachers: {}, period_times: { "1": "08:00", "2": "08:50" } };
    state.childId = "c1";
    state.children = [{ child_id: "c1", name: "Mia" }];
  `);
  return window.eval(`(function (week) { return timetableGrid(week); })`)(WEEK);
}

describe("[P243] what a lesson tile shows", () => {
  test("a tile carries the subject code and no room", () => {
    const { window } = loadApp();
    const node = grid(window);
    const cell = node.querySelector(".tt-cell:not(.free)");
    expect(cell.querySelector(".sub").textContent).toBe("D");
    expect(cell.textContent).not.toContain("R1");
  });

  test("a period with two subjects stays one stack of two tiles", () => {
    const { window } = loadApp();
    const node = grid(window);
    const stack = node.querySelector(".tt-stack");
    expect(stack).not.toBeNull();
    expect(stack.querySelectorAll(".tt-cell.compact").length).toBe(2);
    expect(stack.textContent).not.toContain("R2");
    expect(stack.textContent).not.toContain("H1");
  });
});

describe("[P243] the today rows name the teacher by surname only", () => {
  test("no room travels into the compact row", () => {
    const { window } = loadApp();
    window.eval(`state.config = { subjects: {}, teachers: {} };`);
    const row = window.eval(`(function (entry) { return compactLesson(entry, false); })`)({
      lesson: WEEK.lessons[0],
      time: "08:00",
      childId: "c1",
    });
    expect(row.querySelector(".row-sub").textContent).toBe("Beispiel");
  });

  test("the full name stands in when IServ named no surname", () => {
    const { window } = loadApp();
    window.eval(`state.config = { subjects: {}, teachers: {} };`);
    const row = window.eval(`(function (entry) { return compactLesson(entry, false); })`)({
      lesson: { day_of_week: 1, period: 1, subject_code: "D", room: "R1", teacher_label: "Frau Beispiel", change_kind: "" },
      time: "08:00",
      childId: "c1",
    });
    expect(row.querySelector(".row-sub").textContent).toBe("Frau Beispiel");
  });
});
