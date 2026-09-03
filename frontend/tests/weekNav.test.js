import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderWeekBar(window) {
  return window.eval("(function () { return weekBar(); })")();
}

describe("[P95] week navigation has no past weeks", () => {
  test("WEEK_MIN is 0", () => {
    const { window } = loadApp();
    const min = window.eval("WEEK_MIN");
    expect(min).toBe(0);
  });

  test("back arrow is disabled at week offset 0", () => {
    const { window } = loadApp();
    const bar = renderWeekBar(window);
    const back = bar.querySelector('button[aria-label="Woche zurück"]');
    expect(back.disabled).toBe(true);
  });

  test("shiftWeek(-1) at offset 0 stays at offset 0", () => {
    const { window } = loadApp();
    window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    window.shiftWeek(-1);
    const offset = window.eval("state.weekOffset");
    expect(offset).toBe(0);
  });

  test("week list starts at the current week, no past entries", () => {
    const { window } = loadApp();
    const sheet = window.eval("(function () { return weekSheet(); })")();
    const firstOpt = sheet.querySelector(".opt-list .opt");
    expect(firstOpt.textContent).toContain("diese Woche");
  });
});
