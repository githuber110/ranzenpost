import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const READY = `
  state.children = [{ child_id: "c1", name: "Alice", class_name: "3b" }];
  state.childId = "c1";
  state.weekOffset = 0;
  state.me = { forename: "Alice" };
  state.timetable = { lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
  state.letters = { letters: [] };
  state.pinboard = { folders: [], feed: [] };
  state.conferences = { items: [] };
  state.absence = { data: { entries: [], children: [] } };
`;

function renderOverview(window, seed) {
  const run = window.eval(`
    (function (seed) {
      ${READY}
      window.eval(seed);
      return overviewView();
    })
  `);
  return run(seed || "");
}

function areas(view) {
  return [...view.querySelectorAll(".panel")].map((panel) => panel.dataset.area);
}

describe("[P213] the overview only shows chapters that have something to say", () => {
  test("three panels in a fixed order when upcoming has nothing to show", () => {
    const { window } = loadApp();
    expect(areas(renderOverview(window))).toEqual(["today", "letters", "pinboard"]);
  });

  test("still three panels while every source is still loading, upcoming stays hidden until it knows", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.letters = null; state.pinboard = null; state.conferences = null; state.absence = null; state.overviewWeeks = {}; state.timetable = null;");
    expect(areas(view)).toEqual(["today", "letters", "pinboard"]);
    expect(view.querySelectorAll(".loading").length).toBe(3);
  });

  test("[C21] the old single 'Wird aktualisiert' line is gone, each chapter carries its own state", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.letters = null;");
    expect(view.querySelector(".overview-loading")).toBeNull();
    const letters = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "letters");
    expect(letters.querySelector(".loading")).not.toBeNull();
    const pinboard = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "pinboard");
    expect(pinboard.querySelector(".loading")).toBeNull();
  });

  test("[M19] exactly one HEUTE heading, and exactly three headings when upcoming is empty", () => {
    const { window } = loadApp();
    const view = renderOverview(window);
    const headings = [...view.querySelectorAll("h2.section-label")].map((node) => node.textContent);
    expect(headings).toEqual(["Heute", "Elternbriefe", "Pinnwand"]);
  });

  test("[M19] the HEUTE head link switches the timetable to the child that is on screen", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        ${READY}
        state.children = [
          { child_id: "c1", name: "Alice", class_name: "3b" },
          { child_id: "c2", name: "Bella", class_name: "1a" },
        ];
        state.overviewChildId = "c2";
        state.timetable = null;
        state.overviewWeeks = {
          c1: { 0: { lessons: [{ day_of_week: 2, period: 1, subject_code: "D" }], period_times: {} } },
          c2: { 0: { lessons: [{ day_of_week: 2, period: 1, subject_code: "M" }], period_times: {} } },
        };
        reloadTimetable = () => Promise.resolve();
        const panel = overviewToday();
        panel.querySelector(".panel-link").click();
        return { view: state.view, childId: state.childId };
      })()
    `);
    expect(result.view).toBe("timetable");
    expect(result.childId).toBe("c2");
  });
});

describe("[M9] a failing source keeps its own chapter honest and leaves the others intact", () => {
  for (const source of [
    { name: "letters", seed: 'state.letters = { error: "network" };', area: "letters" },
    { name: "pinboard", seed: 'state.pinboard = { error: "network" };', area: "pinboard" },
    {
      name: "today",
      seed: 'state.timetable = null; state.overviewWeeks = { c1: { 0: { lessons: [], error: "network" } } };',
      area: "today",
    },
  ]) {
    test(`${source.name}: its chapter shows the partial failure with a retry, the others do not`, () => {
      const { window } = loadApp();
      const view = renderOverview(window, source.seed);
      expect(areas(view)).toEqual(["today", "letters", "pinboard"]);
      const failed = [...view.querySelectorAll(".panel")].filter((panel) => panel.querySelector(".overview-failed"));
      expect(failed.map((panel) => panel.dataset.area)).toEqual([source.area]);
      expect(failed[0].textContent).toContain(window.eval('t("overview.partial.failed")'));
      const retry = [...failed[0].querySelectorAll("button")].find(
        (node) => node.textContent.trim() === window.eval('t("common.retry")')
      );
      expect(retry).toBeTruthy();
    });
  }

  test("chapter 4 with only the conferences broken keeps the absence half alive", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.conferences = { error: "network" };
      state.absence = { data: { children: [], entries: [{ id: "a1", label_key: "absence.entry.kind.sick", from_date: "2026-09-04", till_date: "2026-09-04" }] } };
      window.__realDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new window.__realDate("2026-09-03T08:00:00");
        return new window.__realDate(...args);
      }
      FixedDate.prototype = window.__realDate.prototype;
      Date = FixedDate;
    `);
    const upcoming = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "upcoming");
    expect(upcoming).toBeTruthy();
    expect(upcoming.querySelectorAll(".overview-failed").length).toBe(1);
    expect(upcoming.querySelector(".row-all")).toBeNull();
    expect(upcoming.querySelectorAll(".rows .row").length).toBe(1);
    window.eval("Date = window.__realDate;");
  });

  test("chapter 4 with both sources broken shows one failure, not two empty promises", () => {
    const { window } = loadApp();
    const view = renderOverview(window, 'state.conferences = { error: "network" }; state.absence = { error: "network" };');
    const upcoming = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "upcoming");
    expect(upcoming.querySelectorAll(".overview-failed").length).toBe(1);
    expect(upcoming.querySelector(".row-all")).toBeNull();
  });
});

describe("[P178] the defined amount each chapter shows", () => {
  test("letters: unread only, capped at twelve, with a trailing row into the tab", () => {
    const { window } = loadApp();
    const letters = [];
    for (let index = 0; index < 20; index += 1) {
      letters.push({ letter_id: `l${index}`, recipient_id: "r", title: `Brief ${index}`, unread: true });
    }
    letters.push({ letter_id: "read", recipient_id: "r", title: "Gelesen", unread: false });
    const view = renderOverview(window, `state.letters = { letters: ${JSON.stringify(letters)} };`);
    const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === "letters");
    const rows = panel.querySelectorAll(".rows .row");
    expect(rows.length).toBe(13);
    expect(panel.textContent).not.toContain("Gelesen");
    expect(rows[12].classList.contains("row-all")).toBe(true);
    expect(rows[12].textContent).toBe(window.eval('t("overview.all.letters")'));
  });

  test("pinboard: unread posts come first, seen ones fill up behind them", () => {
    const { window } = loadApp();
    const feed = [
      { id: 1, title: "Gelesen", text: "", unread: false, folder_title: "A" },
      { id: 2, title: "Neu", text: "", unread: true, folder_title: "B" },
    ];
    const view = renderOverview(window, `state.pinboard = { folders: [], feed: ${JSON.stringify(feed)} };`);
    const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === "pinboard");
    const titles = [...panel.querySelectorAll(".rows .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Neu", "Gelesen", window.eval('t("overview.all.pinboard")')]);
  });

  test("upcoming: conferences and absences mixed by date, later than fourteen days dropped", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.conferences = { items: [{ cells: ["Sprechtag", "05.09.2026"] }, { cells: ["Zu spaet", "05.12.2026"] }] };
      state.absence = { data: { children: [], entries: [{ id: "a1", label_key: "absence.entry.kind.sick", from_date: "2026-09-04", till_date: "2026-09-04" }] } };
      window.__realDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new window.__realDate("2026-09-03T08:00:00");
        return new window.__realDate(...args);
      }
      FixedDate.prototype = window.__realDate.prototype;
      Date = FixedDate;
    `);
    const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === "upcoming");
    const titles = [...panel.querySelectorAll(".rows .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Krankmeldung", "Sprechtag"]);
    window.eval("Date = window.__realDate;");
  });

  test("a rest state says what it checked and never removes the letters or pinboard chapter", () => {
    const { window } = loadApp();
    const view = renderOverview(window);
    const panels = [...view.querySelectorAll(".panel")];
    const letters = panels.find((panel) => panel.dataset.area === "letters");
    const pinboard = panels.find((panel) => panel.dataset.area === "pinboard");
    expect(letters.textContent).toContain(window.eval('t("overview.letters.none")'));
    expect(pinboard.textContent).toContain(window.eval('t("overview.pinboard.none")'));
  });
});

describe("[P213] upcoming only appears when it has something real to say", () => {
  test("no chapter at all when there is nothing upcoming and nothing failed", () => {
    const { window } = loadApp();
    const view = renderOverview(window);
    const upcoming = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "upcoming");
    expect(upcoming).toBeUndefined();
    expect(window.eval("t('overview.chapter.upcoming')").length).toBeGreaterThan(0);
  });

  test("appears directly behind today as soon as it has content", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.conferences = { items: [{ cells: ["Sprechtag", "05.09.2026"] }] };
      window.__realDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new window.__realDate("2026-09-03T08:00:00");
        return new window.__realDate(...args);
      }
      FixedDate.prototype = window.__realDate.prototype;
      Date = FixedDate;
    `);
    expect(areas(view)).toEqual(["today", "upcoming", "letters", "pinboard"]);
    window.eval("Date = window.__realDate;");
  });

  test("still appears with just its error block when a source failed, even with zero rows", () => {
    const { window } = loadApp();
    const view = renderOverview(window, 'state.conferences = { error: "network" }; state.absence = { error: "network" };');
    expect(areas(view)).toEqual(["today", "upcoming", "letters", "pinboard"]);
    const upcoming = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "upcoming");
    expect(upcoming.querySelectorAll(".overview-failed").length).toBe(1);
    expect(upcoming.querySelector(".row-all")).toBeNull();
    expect(upcoming.querySelector(".panel-link")).toBeNull();
  });
});
