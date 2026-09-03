import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function pad2(value) {
  return String(value).padStart(2, "0");
}

function isoToday() {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

function startForm(window, type, data) {
  const run = window.eval(
    "(function (type, data) { state.absence = { data }; startAbsenceForm(type); return state.absenceForm; })"
  );
  return run(type, data);
}

describe("[P105] absence forms default to today, not tomorrow", () => {
  test("deregister (bus/lunch/kindergarten) defaults to today", () => {
    const { window } = loadApp();
    const data = { children: [{ id: 1 }], rules: {}, deregister_options: ["bus"] };
    const form = startForm(window, "deregister", data);
    expect(form.date).toBe(isoToday());
  });

  test("daycare (Ganztag) defaults to today when no min-days rule and before cutoff", () => {
    const { window } = loadApp();
    const data = { children: [{ id: 1 }], rules: {} };
    const form = startForm(window, "daycare", data);
    expect(form.date).toBe(isoToday());
  });

  test("daycare still respects an explicit min-days rule (cutoff behaviour unchanged)", () => {
    const { window } = loadApp();
    const data = { children: [{ id: 1 }], rules: { daycare_min_days: 1 } };
    const form = startForm(window, "daycare", data);
    const expected = window.eval("isoDate(addDays(new Date(), 1))");
    expect(form.date).toBe(expected);
  });
});
