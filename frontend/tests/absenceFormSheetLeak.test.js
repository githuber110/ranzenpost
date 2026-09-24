import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("startAbsenceForm clears stale sheetForm", () => {
  test("the names page builds a fresh draft after an absence form was started", () => {
    const { window } = loadApp();
    window.eval(`
      state.sheetForm = { D: { label: "STALE", color: "" } };
      state.absence = { data: { children: [{ id: 1 }], rules: {}, day_options: { from: [], till: [] } } };
      startAbsenceForm("sick", 1);
    `);
    expect(window.eval("state.sheetForm")).toBeNull();

    const draft = window.eval(`
      state.config = { connections: [{ id: "s1", subjects: { D: { label: "Deutsch", color: "" } } }] };
      namesPageView();
      state.pageForm;
    `);
    expect(draft.subjects.D.label).toBe("Deutsch");
  });
});
