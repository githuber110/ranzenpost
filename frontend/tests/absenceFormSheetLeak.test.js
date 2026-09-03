import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P111-A2] startAbsenceForm clears stale sheetForm", () => {
  test("namesSheet builds a fresh draft after an absence form was started", () => {
    const { window } = loadApp();
    window.eval(`
      state.sheetForm = { D: { label: "STALE", color: "" } };
      state.absence = { data: { children: [{ id: 1 }], rules: {}, day_options: { from: [], till: [] } } };
      startAbsenceForm("sick", 1);
    `);
    expect(window.eval("state.sheetForm")).toBeNull();

    const draft = window.eval(`
      state.config = { subjects: { D: { label: "Deutsch", color: "" } } };
      namesSheet();
      state.sheetForm;
    `);
    expect(draft.subjects.D.label).toBe("Deutsch");
  });
});
