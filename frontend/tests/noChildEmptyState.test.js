import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("overview and tab bar with no child assigned", () => {
  test("overviewToday shows an honest empty state instead of an empty timetable card when no child is available", () => {
    const { window } = loadApp();
    const section = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.timetable = null;
        state.modules.available.timetable = true;
        return overviewToday();
      })()
    `);
    expect(section.querySelector(".child-today")).toBeNull();
    expect(section.textContent).toContain("Es ist keine Person ausgewählt.");
  });

  test("the today chapter is simply absent when the school has no timetable module", () => {
    const { window } = loadApp();
    const chapter = window.eval(`
      (function () {
        state.children = [{ key: "anna", name: "Anna" }];
        state.childId = "anna";
        state.timetable = { lessons: [], period_times: {} };
        state.modules.available.timetable = false;
        return todayChapter();
      })()
    `);
    expect(chapter).toBeNull();
  });

  test("tabbar hides the Plan tab when the timetable module is missing", () => {
    const { window } = loadApp();
    const bar = window.eval(`
      (function () {
        state.modules.available.timetable = false;
        return tabbar();
      })()
    `);
    const labels = [...bar.querySelectorAll(".tab span:not(.badge)")].map((n) => n.textContent);
    expect(labels).not.toContain("Plan");
  });

  test("tabbar shows the Plan tab when the timetable module is available", () => {
    const { window } = loadApp();
    const bar = window.eval(`
      (function () {
        state.modules.available.timetable = true;
        return tabbar();
      })()
    `);
    const labels = [...bar.querySelectorAll(".tab span:not(.badge)")].map((n) => n.textContent);
    expect(labels).toContain("Plan");
  });

  test("timetableView shows an honest empty state when the school turned the timetable module off", () => {
    const { window } = loadApp();
    const view = window.eval(`
      (function () {
        state.modules.available.timetable = false;
        return timetableView();
      })()
    `);
    expect(view.textContent).toContain("Der Stundenplan ist für diese Schule nicht freigeschaltet.");
    expect(view.querySelector(".weekbar")).toBeNull();
  });

  test("timetableView shows an honest empty state instead of a spinner when no child is available", () => {
    const { window } = loadApp();
    const view = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.timetable = null;
        state.modules.available.timetable = true;
        return timetableView();
      })()
    `);
    expect(view.textContent).toContain("Es ist keine Person ausgewählt.");
    expect(view.querySelector(".weekbar")).toBeNull();
    expect(view.querySelector(".loading")).toBeNull();
  });
});
