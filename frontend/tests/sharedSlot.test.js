import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const stylesCss = fs.readFileSync(path.resolve(dirname, "..", "styles.css"), "utf8");

function renderGrid(window, data) {
  const run = window.eval(`
    (function (data) {
      state.weekOffset = 0;
      return timetableGrid(data);
    })
  `);
  return run(data);
}

function renderOverviewTodayAt(window, fixedDate, week) {
  const run = window.eval(`
    (function (fixedIso, week) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.weekOffset = 0;
      state.timetable = week;
      const result = overviewToday();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedDate, week);
}

const sharedWeek = {
  lessons: [
    { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D", room: "R1", change_kind: "" },
    { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "M", room: "R1", change_kind: "" },
    { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "TEAM", room: "R2", change_kind: "cancelled" },
  ],
  period_times: { 1: "08:00", 4: "10:40" },
};

describe("[P109][C03] shared slots survive the grid and the today card", () => {
  test("a slot with two lessons renders two chips inside one div container", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, sharedWeek);
    const stacks = grid.querySelectorAll(".tt-stack");
    expect(stacks.length).toBe(1);
    expect(stacks[0].tagName).toBe("DIV");
    const chips = stacks[0].querySelectorAll("button.tt-cell.compact");
    expect(chips.length).toBe(2);
    expect([...chips].map((chip) => chip.querySelector(".sub").textContent)).toEqual(["M", "TEAM"]);
    expect(chips[0].classList.contains("out")).toBe(false);
    expect(chips[1].classList.contains("out")).toBe(true);
    expect(chips[1].getAttribute("aria-label")).toContain("Entfällt");
    expect(grid.querySelectorAll("button button").length).toBe(0);
  });

  test("a slot with one lesson stays a single plain cell button", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, sharedWeek);
    const single = [...grid.querySelectorAll("button.tt-cell")].filter(
      (cell) => !cell.classList.contains("compact")
    );
    expect(single.length).toBe(1);
    expect(single[0].querySelector(".sub").textContent).toBe("D");
  });

  test("[P140b] the today card renders the shared slot as two full rows (name + teacher each), time shown once", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D", room: "R1", change_kind: "" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "M", room: "R1", teacher_label: "Frau Bauer", change_kind: "" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "TEAM", room: "R2", teacher_label: "Herr Klein", change_kind: "cancelled" },
      ],
      period_times: { 1: "08:00", 4: "10:40" },
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week);
    const rows = section.querySelectorAll(".rows.flat .row:not(.row-note)");
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector(".row-title").textContent).toBe("D");
    const pairRow = rows[1];
    const items = pairRow.querySelectorAll(".row-pair .row-pair-item");
    expect(items.length).toBe(2);
    expect([...items].map((item) => item.querySelector(".row-title").textContent)).toEqual(["M", "TEAM"]);
    expect([...items].map((item) => item.querySelector(".row-sub").textContent)).toEqual(
      ["Raum R1 · Frau Bauer", "Raum R2 · Herr Klein"]
    );
    expect(items[1].querySelector(".row-title").style.textDecoration).toBe("line-through");
    const metas = pairRow.querySelectorAll(".row-meta");
    expect(metas.length).toBe(1);
    expect(metas[0].textContent).toBe("10:40");
  });

  test("[P140b] .row-pair lays out its two cells side by side with a divider, not stacked", () => {
    const match = /\.row-pair\s*\{[^}]*\}/.exec(stylesCss);
    expect(match).not.toBeNull();
    expect(match[0]).toMatch(/flex-direction:\s*row/);
    expect(match[0]).not.toMatch(/flex-direction:\s*column/);
    const itemMatch = /\.row-pair-item\s*\{[^}]*\}/.exec(stylesCss);
    expect(itemMatch).not.toBeNull();
    expect(itemMatch[0]).toMatch(/flex:\s*1 1 0/);
    expect(itemMatch[0]).toMatch(/min-width:\s*0/);
    expect(stylesCss).toMatch(/\.row-pair-item \+ \.row-pair-item\s*\{[^}]*border-inline-start:\s*1px solid var\(--line\)/);
  });

  test("[P140b] each cell of the shared slot is independently tappable and opens its own lesson's detail sheet", () => {
    const { window } = loadApp();
    const week = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D", room: "R1", change_kind: "" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "M", room: "R1", teacher_label: "Frau Bauer", change_kind: "" },
        { day_of_week: 2, period: 4, start_time: "10:40", subject_code: "TEAM", room: "R2", teacher_label: "Herr Klein", change_kind: "cancelled" },
      ],
      period_times: { 1: "08:00", 4: "10:40" },
    };
    const section = renderOverviewTodayAt(window, "2026-09-01T06:00:00", week);
    const items = section.querySelectorAll(".row-pair .row-pair-item");
    expect(items.length).toBe(2);

    items[0].click();
    let titleFirst = window.eval("state.sheet().querySelector('.sheet-title').textContent");
    expect(titleFirst).toBe("M");

    items[1].click();
    let titleSecond = window.eval("state.sheet().querySelector('.sheet-title').textContent");
    expect(titleSecond).toBe("TEAM");
  });
});
