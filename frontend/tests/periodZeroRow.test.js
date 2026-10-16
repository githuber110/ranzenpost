import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const periodsSource = fs.readFileSync(path.join(dirname, "..", "periods.js"), "utf8");

function renderGrid(window, lessons, times) {
  const run = window.eval(
    "(function (data) { state.childId = 'c1'; state.children = [{ key: 'c1' }]; return timetableGrid(data); })"
  );
  return run({ lessons, period_times: times || {} });
}

const FRIDAY_ZERO = [
  { day_of_week: 5, period: 0, subject_code: "M" },
  { day_of_week: 1, period: 1, subject_code: "D" },
  { day_of_week: 1, period: 2, subject_code: "D" },
  { day_of_week: 5, period: 1, subject_code: "AS" },
];

describe("week grid shows period 0 when a lesson in the week has it", () => {
  test("a period 0 lesson on one day adds a row 0 with its time before row 1", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, FRIDAY_ZERO, { 0: "08:00", 1: "08:50", 2: "09:40" });
    const hours = [...grid.querySelectorAll(".tt-hour")];
    expect(hours.map((node) => node.querySelector("b").textContent)).toEqual(["0", "1", "2"]);
    expect(hours[0].querySelector("span").textContent).toBe("08:00");
    expect(hours[0].style.gridRow).toBe("2");
    expect(hours[1].style.gridRow).toBe("3");
  });

  test("the period 0 lesson sits in row 0 of its own day only", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, FRIDAY_ZERO, {});
    const cells = [...grid.querySelectorAll(".tt-cell")];
    const rowZero = cells.filter((node) => node.style.gridRow === "2");
    expect(rowZero.filter((node) => !node.classList.contains("free")).map((node) => node.style.gridColumn)).toEqual(["6"]);
    expect(rowZero.filter((node) => node.classList.contains("free")).length).toBe(4);
  });

  test("without a period 0 lesson the grid still starts at row 1", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, FRIDAY_ZERO.filter((lesson) => lesson.period > 0), {});
    const hours = [...grid.querySelectorAll(".tt-hour")];
    expect(hours.map((node) => node.querySelector("b").textContent)).toEqual(["1", "2"]);
    expect(hours[0].style.gridRow).toBe("2");
  });

  test("a week that only has period 0 renders one row 0", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, [{ day_of_week: 2, period: 0, subject_code: "M" }], {});
    expect([...grid.querySelectorAll(".tt-hour b")].map((node) => node.textContent)).toEqual(["0"]);
  });

  test("the period fact of a period 0 lesson is shown and not treated as missing", () => {
    const { window } = loadApp();
    const fact = window.eval("(lesson) => lessonPeriodFact(lesson, '08:00')");
    expect(fact({ period: 0 })).not.toBe(window.eval("t('common.none')"));
    expect(fact({ period: "" })).toBe(window.eval("t('common.none')"));
  });
});

describe("period rules keep period 0", () => {
  test("regularPeriods lists period 0 and still skips added lessons", () => {
    const context = { window: {} };
    vm.runInNewContext(periodsSource, context);
    const P = context.window.RanzenpostPeriods;
    const found = P.regularPeriods([
      { date: "2026-10-16", period: 0 },
      { date: "2026-10-16", period: 1 },
      { date: "2026-10-15", period: 0, change_kind: "added" },
      { date: "2026-10-15", period: 2 },
    ]);
    expect(found["2026-10-16"]).toEqual([0, 1]);
    expect(found["2026-10-15"]).toEqual([2]);
  });
});

describe("a lesson without a period never lands in row 0", () => {
  test("a null or empty period neither creates row 0 nor a cell", () => {
    const { window } = loadApp();
    const lessons = [
      { day_of_week: 1, period: 1, subject_code: "D" },
      { day_of_week: 2, period: null, subject_code: "X" },
      { day_of_week: 3, period: "", subject_code: "Y" },
    ];
    const grid = renderGrid(window, lessons, {});
    expect([...grid.querySelectorAll(".tt-hour b")].map((node) => node.textContent)).toEqual(["1"]);
    expect(grid.querySelectorAll(".tt-cell:not(.free)").length).toBe(1);
  });
});

describe("absence details show period 0", () => {
  test("a sick note from period 0 lists the hours range", () => {
    const { window } = loadApp();
    const text = (entry) => window.eval("(entry) => absenceDetailParts(entry).body[0].textContent")(entry);
    const label = window.eval("t('absence.fact.hours')");
    const base = { kind: "sick", from_date: "2026-10-16", till_date: "2026-10-16" };
    expect(text(Object.assign({}, base, { from_period: 0, till_period: 0 }))).toContain(window.eval("t('absence.fact.hoursRange', { from: '0', till: '0' })"));
    expect(text(Object.assign({}, base, { from_period: 0, till_period: 3 }))).toContain(window.eval("t('absence.fact.hoursRange', { from: '0', till: '3' })"));
    expect(text(Object.assign({}, base, { from_period: 0, till_period: null }))).toContain(window.eval("t('absence.fact.hoursRange', { from: '0', till: '0' })"));
    expect(text(Object.assign({}, base, { from_period: null }))).not.toContain(label);
  });
});
