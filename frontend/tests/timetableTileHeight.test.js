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
    state.children = [{ key: "c1", name: "Mia" }];
  `);
  return window.eval(`(function (week) { return timetableGrid(week); })`)(WEEK);
}

describe("what a lesson tile shows", () => {
  test("a tile carries the code and, for larger tiles, the name, room and teacher surname", () => {
    const { window } = loadApp();
    const node = grid(window);
    const cell = node.querySelector(".tt-cell:not(.free)");
    expect(cell.querySelector(".sub").textContent).toBe("D");
    expect(cell.querySelector(".lname").textContent).toBe("D");
    expect(cell.querySelector(".lroom").textContent).toBe("R1");
    expect(cell.querySelector(".lteacher").textContent).toBe("Beispiel");
    for (const part of cell.querySelectorAll(".lname, .lroom, .lteacher")) expect(part.getAttribute("dir")).toBe("auto");
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

describe("the today rows name the room and the teacher by surname", () => {
  test("the compact row names room and surname", () => {
    const { window } = loadApp();
    window.eval(`state.config = { subjects: {}, teachers: {} };`);
    const row = window.eval(`(function (entry) { return compactLesson(entry, false); })`)({
      lesson: WEEK.lessons[0],
      time: "08:00",
      childId: "c1",
    });
    expect(row.querySelector(".row-sub").textContent).toBe("R1 · Beispiel");
  });

  test("the full name stands in when IServ named no surname", () => {
    const { window } = loadApp();
    window.eval(`state.config = { subjects: {}, teachers: {} };`);
    const row = window.eval(`(function (entry) { return compactLesson(entry, false); })`)({
      lesson: { day_of_week: 1, period: 1, subject_code: "D", room: "R1", teacher_label: "Frau Beispiel", change_kind: "" },
      time: "08:00",
      childId: "c1",
    });
    expect(row.querySelector(".row-sub").textContent).toBe("R1 · Frau Beispiel");
  });
});
