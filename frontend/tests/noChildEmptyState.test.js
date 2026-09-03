import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P137] overview and tab bar with no child assigned", () => {
  test("overviewToday shows an honest empty state instead of an empty timetable card when no child is available", () => {
    const { window } = loadApp();
    const section = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.timetable = null;
        state.timetableAvailable = true;
        return overviewToday();
      })()
    `);
    expect(section.querySelector(".child-today")).toBeNull();
    expect(section.textContent).toContain("Es ist kein Kind ausgewählt.");
  });

  test("overviewToday shows an honest empty state when the school turned the timetable module off", () => {
    const { window } = loadApp();
    const section = window.eval(`
      (function () {
        state.children = [{ child_id: "anna", name: "Anna" }];
        state.childId = "anna";
        state.timetable = { lessons: [], period_times: {} };
        state.timetableAvailable = false;
        return overviewToday();
      })()
    `);
    expect(section.querySelector(".child-today")).toBeNull();
    expect(section.textContent).toContain("Der Stundenplan ist für diese Schule nicht freigeschaltet.");
  });

  test("tabbar hides the Plan tab when timetableAvailable is false", () => {
    const { window } = loadApp();
    const bar = window.eval(`
      (function () {
        state.timetableAvailable = false;
        return tabbar();
      })()
    `);
    const labels = [...bar.querySelectorAll(".tab span:not(.badge)")].map((n) => n.textContent);
    expect(labels).not.toContain("Plan");
  });

  test("tabbar shows the Plan tab when timetableAvailable is true", () => {
    const { window } = loadApp();
    const bar = window.eval(`
      (function () {
        state.timetableAvailable = true;
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
        state.timetableAvailable = false;
        return timetableView();
      })()
    `);
    expect(view.textContent).toContain("Der Stundenplan ist für diese Schule nicht freigeschaltet.");
    expect(view.querySelector(".weekbar")).toBeNull();
  });

  test("[P146] timetableView shows an honest empty state instead of a spinner when no child is available", () => {
    const { window } = loadApp();
    const view = window.eval(`
      (function () {
        state.children = [];
        state.childId = null;
        state.timetable = null;
        state.timetableAvailable = true;
        return timetableView();
      })()
    `);
    expect(view.textContent).toContain("Es ist kein Kind ausgewählt.");
    expect(view.querySelector(".weekbar")).toBeNull();
    expect(view.querySelector(".loading")).toBeNull();
  });
});
