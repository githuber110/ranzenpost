import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const STYLES = fs.readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "styles.css"), "utf8");

function renderCell(window, lesson, compact) {
  const run = window.eval("(function (lesson, compact) { return lessonCell(lesson, '', compact); })");
  return run(lesson, !!compact);
}

describe("cancelled lessons get the neutral 'empty' look, substitution stays amber", () => {
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

  test("a substitution keeps its room next to the label for tiles large enough for the room", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "changed", room: "WK1" });
    expect(cell.querySelector(".room.paired").textContent).toBe("Vertr.");
    expect([...cell.querySelectorAll(".lroom")].map((node) => node.textContent)).toEqual(["Vertr. · WK1"]);
  });

  test("a compact substitution tile shows no room", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "changed", room: "WK1" }, true);
    expect(cell.querySelector(".lroom")).toBeNull();
  });

  test("a substitution without a room keeps the plain label", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "changed" });
    expect(cell.querySelector(".room").classList.contains("paired")).toBe(false);
    expect(cell.querySelector(".lroom")).toBeNull();
  });

  test("a cancelled lesson keeps its look and shows no room", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", change_kind: "cancelled", room: "WK1" });
    expect(cell.querySelector(".room").classList.contains("paired")).toBe(false);
    expect(cell.querySelector(".lroom")).toBeNull();
  });

  test("the paired label replaces the short one in the tile tier that shows the room", () => {
    expect(STYLES).toMatch(/@container \(min-width: 96px\) and \(min-height: 64px\) \{ \.tt-cell \.lroom \{ display: block; \} \.tt-cell \.room\.paired \{ display: none; \} \}/);
  });

  test("a plain lesson carries its subject alone, without the room", () => {
    const { window } = loadApp();
    const cell = renderCell(window, { subject_code: "MA", room: "R204" });
    expect(cell.querySelector(".sub").textContent).toBe("MA");
    expect(cell.querySelector(".room")).toBeNull();
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
