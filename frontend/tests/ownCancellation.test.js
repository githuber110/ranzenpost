import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const CHILD = "c1";
const WEDNESDAY = "2026-09-02";

const WEEK = {
  lessons: [
    { day_of_week: 3, period: 1, start_time: "08:00", subject_code: "D", date: WEDNESDAY, change_kind: "" },
    { day_of_week: 3, period: 2, start_time: "08:50", subject_code: "M", date: WEDNESDAY, change_kind: "" },
    { day_of_week: 3, period: 3, start_time: "09:50", subject_code: "E", date: WEDNESDAY, change_kind: "" },
  ],
  period_times: {},
};

const TIMES = { 1: "08:00", 2: "08:50", 3: "09:50" };

function withCancellations(window, periods) {
  window.eval(`
    state.childId = ${JSON.stringify(CHILD)};
    state.children = [{ child_id: ${JSON.stringify(CHILD)}, name: "Kind" }];
    state.cancellations = { data: { cancellations: ${JSON.stringify(
      periods.map((period) => ({ id: `x${period}`, child_id: CHILD, date: WEDNESDAY, period }))
    )} } };
  `);
}

function overviewAt(window, fixedIso) {
  const run = window.eval(`
    (function (iso, week, times) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(iso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.weekOffset = 0;
      state.timetable = week;
      state.config = { period_times: times };
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedIso, WEEK, TIMES);
}

function grid(window) {
  return window.eval(`
    (function (week) {
      state.weekOffset = 0;
      return timetableGrid(week);
    })
  `)(WEEK);
}

function noteTexts(section) {
  return [...section.querySelectorAll(".row-note")].map((node) => node.textContent).join(" | ");
}

describe("[P227] a lesson the user marked counts exactly like a school cancellation", () => {
  test("the grid draws an own marker as cancelled, just as the school's own", () => {
    const { window } = loadApp();
    withCancellations(window, [2]);
    const cells = [...grid(window).querySelectorAll("button.tt-cell")];
    const marked = cells.find((cell) => (cell.querySelector(".sub") || {}).textContent === "M");
    const plain = cells.find((cell) => (cell.querySelector(".sub") || {}).textContent === "D");
    expect(marked.classList.contains("out")).toBe(true);
    expect(plain.classList.contains("out")).toBe(false);
  });

  test("school is out earlier when the last lesson is marked as cancelled", () => {
    const { window } = loadApp();
    const before = overviewAt(window, `${WEDNESDAY}T07:00:00`);
    expect(noteTexts(before)).toContain("10:35");

    const { window: marked } = loadApp();
    withCancellations(marked, [3]);
    const after = overviewAt(marked, `${WEDNESDAY}T07:00:00`);
    expect(noteTexts(after)).toContain("09:35");
    expect(noteTexts(after)).not.toContain("10:35");
  });

  test("with every lesson marked the day is over instead of announcing an end time", () => {
    const { window } = loadApp();
    withCancellations(window, [1, 2, 3]);
    const section = overviewAt(window, `${WEDNESDAY}T07:00:00`);
    expect(noteTexts(section)).toContain(window.eval("t('overview.dayOver')"));
  });

  test("a marked lesson is never the one carrying Now or Next", () => {
    const { window } = loadApp();
    withCancellations(window, [2]);
    const section = overviewAt(window, `${WEDNESDAY}T08:55:00`);
    const rows = [...section.querySelectorAll(".rows.flat .row:not(.row-note)")];
    const nowMark = window.eval("t('overview.mark.now')");
    const nextMark = window.eval("t('overview.mark.next')");
    const marked = rows.find((row) => row.textContent.includes("M"));
    expect(marked.textContent).not.toContain(nowMark);
    expect(marked.textContent).not.toContain(nextMark);
    const carrier = rows.find((row) => row.textContent.includes(nextMark));
    expect(carrier.textContent).toContain("E");
  });
});
