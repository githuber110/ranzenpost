import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function render(payload) {
  const { window } = loadApp();
  window.eval(`state.timetable = ${JSON.stringify(payload)};`);
  return window.eval("timetableView()");
}

describe("a week in which IServ lists no lessons", () => {
  test("shows a short hint instead of a bare grid", () => {
    const view = render({ lessons: [], no_lessons: true, start_date: "07.09.2026", end_date: "13.09.2026" });
    const block = view.querySelector(".empty");
    expect(block).not.toBeNull();
    expect(block.querySelector("b").textContent).toBe("Keine Stunden eingetragen");
    expect(block.querySelector("p").textContent).toBe("IServ nennt für diese Woche keine Stunden.");
    expect(view.querySelector(".tt")).toBeNull();
  });

  test("keeps the grid when the answer does not say the week is empty", () => {
    const view = render({ lessons: [], start_date: "07.09.2026", end_date: "13.09.2026" });
    expect(view.querySelector(".tt")).not.toBeNull();
    expect(view.textContent).not.toContain("Keine Stunden eingetragen");
  });

  test("an unreadable answer stays an error and never becomes the empty hint", () => {
    const view = render({ error: "network", no_lessons: true });
    expect(view.textContent).toContain("Nicht erreichbar");
    expect(view.textContent).not.toContain("Keine Stunden eingetragen");
  });

  test("the column of a child in the side by side view shows the hint too", () => {
    const { window } = loadApp();
    window.eval("state.childId = 'a1b2c3d4:child-1'; state.timetable = { lessons: [], no_lessons: true };");
    const column = window.eval("timetableChildColumn({ key: 'a1b2c3d4:child-1', child_id: 'child-1', name: 'Mia Beispiel' })");
    expect(column.querySelector(".empty b").textContent).toBe("Keine Stunden eingetragen");
    expect(column.querySelector(".tt")).toBeNull();
  });

  test("the hint uses known message keys", () => {
    const { window } = loadApp();
    for (const key of ["timetable.empty.title", "timetable.empty.text"]) {
      expect(window.eval(`hasMessage(${JSON.stringify(key)})`)).toBe(true);
    }
  });
});
