import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await settle();
  window.clearTimeout(window.eval("bootWatchdog"));
}

function showTimetable(window, released) {
  window.eval(`
    state.timetableAvailable = true;
    state.childrenFailure = null;
    state.children = [{ child_id: "c1", name: "Kim", class_name: "1d" }];
    state.childId = "c1";
    state.timetable = {
      lessons: [],
      changes: [],
      start_date: "07.09.2026",
      end_date: "13.09.2026",
      period_times: {},
      school_period_times: {},
      change_count: 0,
      week_offset: 0,
      substitutions_released: ${JSON.stringify(released)},
      vacations: [],
    };
    state.view = "timetable";
    rerender();
  `);
  return window.document.getElementById("app").textContent;
}

describe("[P238] the timetable says when the school keeps substitutions from parents", () => {
  test("the note is shown when the school does not release them", async () => {
    const { window } = loadApp();
    await quiet(window);
    const text = showTimetable(window, false);
    expect(text).toContain(window.eval('t("timetable.substitutions.notReleased")'));
  });

  test("the note stays away when the school releases them", async () => {
    const { window } = loadApp();
    await quiet(window);
    const text = showTimetable(window, true);
    expect(text).not.toContain(window.eval('t("timetable.substitutions.notReleased")'));
  });

  test("an answer that does not say either way shows no note", async () => {
    const { window } = loadApp();
    await quiet(window);
    const text = showTimetable(window, null);
    expect(text).not.toContain(window.eval('t("timetable.substitutions.notReleased")'));
  });
});
