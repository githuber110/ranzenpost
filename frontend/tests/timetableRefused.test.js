import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const REFUSED = { error: "network", message_key: "api.timetable.refused", diagnosis: { status: 403 } };

function renderView(window, data) {
  const run = window.eval(
    "(function (data) { state.childId = 'c1'; state.children = [{ key: 'c1' }]; state.timetable = data; return timetableView(); })"
  );
  return run(data);
}

function renderToday(window, week) {
  const run = window.eval(`
    (function (week) {
      state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
      state.childId = "c1";
      state.timetable = null;
      state.overviewWeeks = { c1: { 0: week } };
      return overviewFlatten(document.createElement("div"), [todayChapter()].filter(Boolean))[0] || null;
    })
  `);
  return run(week);
}

function jsonResponse(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("a school that does not release the timetable to this account", () => {
  test("a refused load keeps the reason so the timetable can name it", async () => {
    const { window } = loadApp();
    window.clearTimeout(window.eval("bootWatchdog"));
    for (let round = 0; round < 6; round += 1) await settle();
    window.fetch = (input) => jsonResponse(String(input).includes("api/timetable?") ? REFUSED : {});
    window.eval("state.childId = 'c1'; state.children = [{ key: 'c1' }]; state.view = 'timetable';");
    await window.eval("reloadTimetable()");
    await window.eval("loadOverviewWeek('c1', 0)");
    expect(window.eval("state.timetable.message_key")).toBe("api.timetable.refused");
    expect(window.eval("state.overviewWeeks.c1[0].message_key")).toBe("api.timetable.refused");
    expect(window.eval("timetableView()").querySelector(".empty b").textContent).toBe(window.eval('t("timetable.refused.title")'));
  });

  test("the timetable says so calmly, without an error or a retry", () => {
    const { window } = loadApp();
    const view = renderView(window, REFUSED);
    expect(view.querySelector(".empty b").textContent).toBe(window.eval('t("timetable.refused.title")'));
    expect(view.querySelector(".empty p").textContent).toBe(window.eval('t("api.timetable.refused")'));
    expect(view.textContent).not.toContain(window.eval('t("timetable.error.title")'));
    expect(view.querySelector(".empty button")).toBeNull();
  });

  test("any other failure keeps the error with its retry", () => {
    const { window } = loadApp();
    const view = renderView(window, { error: "network", message_key: "api.timetable.unreadable" });
    expect(view.querySelector(".empty b").textContent).toBe(window.eval('t("timetable.error.title")'));
    expect(view.querySelector(".empty button")).not.toBeNull();
  });

  test("the overview's today chapter names the refusal instead of a partial failure", () => {
    const { window } = loadApp();
    const panel = renderToday(window, REFUSED);
    expect(panel.textContent).toContain(window.eval('t("api.timetable.refused")'));
    expect(panel.querySelector(".overview-failed")).toBeNull();
    expect(evalWith(window, 't("api.timetable.refused")')).not.toBe("api.timetable.refused");
  });
});
