import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

function renderWeekBar(window) {
  return window.eval("(function () { return weekBar(); })")();
}

describe("week navigation has no past weeks", () => {
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

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("week loads that overlap", () => {
  test("an older week answering last does not replace the shown week", async () => {
    const { window } = loadApp();
    for (let round = 0; round < 6; round += 1) await tick();
    window.clearTimeout(window.eval("bootWatchdog"));
    const pending = {};
    window.fetch = (url) => {
      const target = String(url);
      if (target.includes("api/config")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ connections: [] }) });
      }
      const week = new URL(target).searchParams.get("week");
      return new Promise((resolve) => {
        pending[week] = () => resolve({ ok: true, status: 200, json: () => Promise.resolve({ lessons: [], start_date: `week-${week}` }) });
      });
    };
    evalWith(window, 'state.detached = false; state.childId = testArgs[0]; state.view = "timetable";', "c1");

    const first = window.eval("setWeek(1)");
    await tick();
    const second = window.eval("setWeek(2)");
    await tick();
    pending["2"]();
    await second;
    expect(window.eval("state.timetable && state.timetable.start_date")).toBe("week-2");
    pending["1"]();
    await first;
    for (let round = 0; round < 3; round += 1) await tick();

    expect(window.eval("state.weekOffset")).toBe(2);
    expect(window.eval("state.timetable.start_date")).toBe("week-2");
  });
});
