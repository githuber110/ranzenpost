import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderCell(window, lesson, compact) {
  const run = window.eval("(function (lesson, compact) { return lessonCell(lesson, '', compact); })");
  return run(lesson, !!compact);
}

describe("[C11] cancelled lessons get the neutral 'empty' look, substitution stays amber", () => {
  test("a cancelled lesson does not carry the .subbed amber class, only .out", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "cancelled" });
    expect(cell.classList.contains("out")).toBe(true);
    expect(cell.classList.contains("subbed")).toBe(false);
  });

  test("a cancelled lesson has no colored bar element", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "cancelled" });
    expect(cell.querySelector(".bar")).toBeNull();
  });

  test("a substitution (changed) keeps its bar and the .subbed class", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "changed" });
    expect(cell.classList.contains("subbed")).toBe(true);
    expect(cell.querySelector(".bar")).not.toBeNull();
  });

  test("a cancelled lesson shows 'Entfällt' in the room line, even when a room is set", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "cancelled", room: "R204" });
    expect(cell.querySelector(".room").textContent).toBe("Entfällt");
  });

  test("a substitution shows 'Vertr.' in the room line", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "changed", room: "R204" });
    expect(cell.querySelector(".room").textContent).toBe("Vertr.");
  });

  test("a plain lesson still shows its room unchanged", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", room: "R204" });
    expect(cell.querySelector(".room").textContent).toBe("R204");
  });

  test("legend shows an x symbol for Entfällt and a dot for Vertretung", () => {
    const { window } = loadApp();
    window.eval("state.timetable = { lessons: [], last_updated: null };");
    const view = window.eval("timetableView()");
    const legend = view.querySelector(".legend");
    expect(legend.textContent).toContain("Entfällt");
    expect(legend.textContent).toContain("Vertretung");
    const symbol = legend.querySelector("i.sym");
    expect(symbol).not.toBeNull();
    expect(symbol.textContent).toBe("×");
  });
});
