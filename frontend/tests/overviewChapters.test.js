import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const READY = `
  state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
  state.childId = "c1";
  state.weekOffset = 0;
  state.me = { forename: "Alice" };
  state.timetable = { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
  state.letters = { tab: "current", letters: [{ letter_id: "l1", recipient_id: "r1", title: "Brief", unread: true }] };
  state.pinboard = { folders: [], feed: [{ id: "p1", unread: true, title: "Neu", text: "" }] };
  state.conferences = { items: [] };
  state.absence = { data: { entries: [], children: [] } };
  state.messengerRooms = { rooms: [] };
  state.config = { overview_blocks: [{ key: "today" }, { key: "letters" }, { key: "noticeboard" }, { key: "conferences" }, { key: "absences" }, { key: "chat" }] };
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

function fixedDate(iso) {
  return `
    window.__realDate = Date;
    function FixedDate(...args) {
      if (args.length === 0) return new window.__realDate("${iso}");
      return new window.__realDate(...args);
    }
    FixedDate.prototype = window.__realDate.prototype;
    Date = FixedDate;
  `;
}

describe("the overview only shows chapters that have something to say", () => {
  test("three panels in the configured order when the other blocks have no content", () => {
    const { window } = loadApp();
    expect(areas(renderOverview(window))).toEqual(["today", "letters", "noticeboard"]);
  });

  test("a chapter without content renders nothing, not even its head", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.letters = { tab: 'current', letters: [] }; state.pinboard = { folders: [], feed: [] };");
    expect(areas(view)).toEqual(["today"]);
    expect(view.textContent).not.toContain(window.eval('t("blocks.letters.title")'));
  });

  test("the loading chapters keep their place while every source is still loading", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.letters = null; state.pinboard = null; state.conferences = null; state.absence = null; state.overviewWeeks = {}; state.timetable = null;");
    expect(areas(view)).toEqual(["today", "letters", "noticeboard"]);
    expect(view.querySelectorAll(".loading").length).toBe(3);
  });

  test("the old single 'Wird aktualisiert' line is gone, each chapter carries its own state", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.letters = null;");
    expect(view.querySelector(".overview-loading")).toBeNull();
    const letters = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "letters");
    expect(letters.querySelector(".loading")).not.toBeNull();
    const pinboard = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "noticeboard");
    expect(pinboard.querySelector(".loading")).toBeNull();
  });

  test("exactly one HEUTE heading, and exactly three headings when the rest is empty", () => {
    const { window } = loadApp();
    const view = renderOverview(window);
    const headings = [...view.querySelectorAll("h2.section-label")].map((node) => node.textContent);
    expect(headings).toEqual(["Heute", "Elternbriefe", "Pinnwand"]);
  });

  test("every panel carries its block key so guards can walk the rendered blocks", () => {
    const { window } = loadApp();
    const view = renderOverview(window);
    expect([...view.querySelectorAll(".panel[data-block]")].map((panel) => panel.dataset.block)).toEqual(["today", "letters", "noticeboard"]);
  });

  test("the HEUTE head link switches the timetable to the child that is on screen", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        ${READY}
        state.children = [
          { key: "c1", name: "Alice", class_name: "3b" },
          { key: "c2", name: "Bella", class_name: "1a" },
        ];
        state.overviewChildId = "c2";
        state.timetable = null;
        state.overviewWeeks = {
          c1: { 0: { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, subject_code: "D" }], period_times: {} } },
          c2: { 0: { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, subject_code: "M" }], period_times: {} } },
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

  test("nothing at all leaves a calm empty state with a way into the overview settings", () => {
    const { window } = loadApp();
    const view = renderOverview(window, "state.config = { overview_blocks: [] };");
    expect(view.querySelectorAll(".panel").length).toBe(0);
    const empty = view.querySelector(".overview-empty .empty");
    expect(empty).not.toBeNull();
    expect(empty.querySelector("b").textContent).toBe(window.eval('t("blocks.overview.emptyTitle")'));
    expect(empty.querySelector("button").textContent).toBe(window.eval('t("settings.blocks.title")'));
  });
});

describe("a failing source keeps its own chapter honest and leaves the others intact", () => {
  for (const source of [
    { name: "letters", seed: 'state.letters = { error: "network" };', area: "letters" },
    { name: "pinboard", seed: 'state.pinboard = { error: "network" };', area: "noticeboard" },
    {
      name: "today",
      seed: 'state.timetable = null; state.overviewWeeks = { c1: { 0: { lessons: [], error: "network" } } };',
      area: "today",
    },
  ]) {
    test(`${source.name}: its chapter shows the partial failure with a retry, the others do not`, () => {
      const { window } = loadApp();
      const view = renderOverview(window, source.seed);
      expect(areas(view)).toEqual(["today", "letters", "noticeboard"]);
      const failed = [...view.querySelectorAll(".panel")].filter((panel) => panel.querySelector(".overview-failed"));
      expect(failed.map((panel) => panel.dataset.area)).toEqual([source.area]);
      expect(failed[0].textContent).toContain(window.eval('t("overview.partial.failed")'));
      const retry = [...failed[0].querySelectorAll("button")].find(
        (node) => node.textContent.trim() === window.eval('t("common.retry")')
      );
      expect(retry).toBeTruthy();
    });
  }

  test("broken conferences show their own failure while the absences block stays alive on its own", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.conferences = { error: "network" };
      state.absence = { data: { children: [], entries: [{ id: "a1", label_key: "absence.entry.kind.sick", from_date: "2026-09-04", till_date: "2026-09-04" }] } };
      ${fixedDate("2026-09-03T08:00:00")}
    `);
    const conferences = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "conferences");
    expect(conferences.querySelectorAll(".overview-failed").length).toBe(1);
    expect(conferences.querySelector(".row-all")).toBeNull();
    const absences = [...view.querySelectorAll(".panel")].find((panel) => panel.dataset.area === "absences");
    expect(absences.querySelectorAll(".rows .row:not(.row-all)").length).toBe(1);
    expect(absences.querySelector(".row-all").textContent).toBe(window.eval('t("overview.all.absences")'));
    window.eval("Date = window.__realDate;");
  });

  test("both broken sources show one failure each, never an empty promise", () => {
    const { window } = loadApp();
    const view = renderOverview(window, 'state.conferences = { error: "network" }; state.absence = { error: "network" };');
    for (const area of ["conferences", "absences"]) {
      const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === area);
      expect(panel.querySelectorAll(".overview-failed").length).toBe(1);
      expect(panel.querySelector(".row-all")).toBeNull();
    }
  });
});

describe("the item limit of every block", () => {
  test("letters: unread only, five in normal, with a trailing row into the tab", () => {
    const { window } = loadApp();
    const letters = [];
    for (let index = 0; index < 20; index += 1) {
      letters.push({ letter_id: `l${index}`, recipient_id: "r", title: `Brief ${index}`, unread: true });
    }
    letters.push({ letter_id: "read", recipient_id: "r", title: "Gelesen", unread: false });
    const view = renderOverview(window, `state.letters = { tab: "current", letters: ${JSON.stringify(letters)} };`);
    const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === "letters");
    const rows = panel.querySelectorAll(".rows .row");
    expect(rows.length).toBe(6);
    expect(panel.textContent).not.toContain("Gelesen");
    expect(rows[5].classList.contains("row-all")).toBe(true);
    expect(rows[5].textContent).toBe(window.eval('t("overview.all.letters")'));
  });

  test("letters in compact: three one-line rows without sub line or tags", () => {
    const { window } = loadApp();
    const letters = [];
    for (let index = 0; index < 5; index += 1) {
      letters.push({ letter_id: `l${index}`, recipient_id: "r", title: `Brief ${index}`, sender: "Schule", unread: true });
    }
    const view = renderOverview(window, `
      state.letters = { tab: "current", letters: ${JSON.stringify(letters)} };
      state.config = { overview_blocks: [{ key: "letters", size: "compact" }] };
    `);
    const panel = view.querySelector(".panel[data-area='letters']");
    const rows = panel.querySelectorAll(".rows .row:not(.row-all)");
    expect(rows.length).toBe(3);
    expect([...rows].every((row) => row.classList.contains("compact"))).toBe(true);
    expect(panel.querySelector(".row-sub")).toBeNull();
    expect(panel.querySelector(".row-all")).not.toBeNull();
  });

  test("pinboard: unread posts only, the seen ones stay out", () => {
    const { window } = loadApp();
    const feed = [
      { id: 1, title: "Gelesen", text: "", unread: false, folder_title: "A" },
      { id: 2, title: "Neu", text: "", unread: true, folder_title: "B" },
    ];
    const view = renderOverview(window, `state.pinboard = { folders: [], feed: ${JSON.stringify(feed)} };`);
    const panel = [...view.querySelectorAll(".panel")].find((node) => node.dataset.area === "noticeboard");
    const titles = [...panel.querySelectorAll(".rows .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Neu", window.eval('t("overview.all.pinboard")')]);
  });

  test("conferences and absences are two blocks, each with its own rows and limit", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.timetable = { lessons: [{ day_of_week: 4, period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
      state.conferences = { items: [{ cells: ["Sprechtag", "05.09.2026"] }, { cells: ["Vorbei", "01.09.2026"] }] };
      state.absence = { data: { children: [], entries: [{ id: "a1", label_key: "absence.entry.kind.sick", from_date: "2026-09-04", till_date: "2026-09-04" }, { id: "a2", label_key: "absence.entry.kind.sick", from_date: "2026-12-04", till_date: "2026-12-04" }] } };
      ${fixedDate("2026-09-03T08:00:00")}
    `);
    expect(areas(view)).toEqual(["today", "letters", "noticeboard", "conferences", "absences"]);
    const conferences = view.querySelector(".panel[data-area='conferences']");
    expect([...conferences.querySelectorAll(".rows .row-title")].map((node) => node.textContent)).toEqual(["Sprechtag", window.eval('t("overview.all.conferences")')]);
    const absences = view.querySelector(".panel[data-area='absences']");
    expect([...absences.querySelectorAll(".rows .row-title")].map((node) => node.textContent)).toEqual(["04.09.2026", window.eval('t("overview.all.absences")')]);
    window.eval("Date = window.__realDate;");
  });

  test("today in compact skips past lessons and stops at three", () => {
    const { window } = loadApp();
    const lessons = [1, 2, 3, 4, 5, 6].map((period) => ({ day_of_week: 4, period, start_time: `${String(6 + period).padStart(2, "0")}:00`, subject_code: `F${period}` }));
    const view = renderOverview(window, `
      state.timetable = { lessons: ${JSON.stringify(lessons)}, period_times: {} };
      state.config = { overview_blocks: [{ key: "today", size: "compact" }] };
      ${fixedDate("2026-09-03T09:30:00")}
    `);
    const panel = view.querySelector(".panel[data-area='today']");
    const titles = [...panel.querySelectorAll(".rows .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["F3", "F4", "F5"]);
    window.eval("Date = window.__realDate;");
  });
});

describe("the new blocks", () => {
  test("changes lists substitutions and cancellations of the next fourteen days with a child tag", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.children = [{ key: "c1", name: "Alice", class_name: "3b" }, { key: "c2", name: "Bella", class_name: "1a" }];
      state.timetable = null;
      state.overviewWeeks = {
        c1: { 0: { lessons: [{ day_of_week: 5, period: 2, subject_code: "M", change_kind: "cancelled" }], period_times: {} }, 1: { lessons: [], period_times: {} } },
        c2: { 0: { lessons: [{ day_of_week: 5, period: 3, subject_code: "D", change_kind: "changed" }], period_times: {} }, 1: { lessons: [{ day_of_week: 1, period: 1, subject_code: "E", change_kind: "changed" }], period_times: {} } },
      };
      state.config = { overview_blocks: [{ key: "changes", size: "normal" }] };
      ${fixedDate("2026-09-03T08:00:00")}
    `);
    const panel = view.querySelector(".panel[data-area='changes']");
    expect(panel).not.toBeNull();
    expect([...panel.querySelectorAll(".rows .row-title")].map((node) => node.textContent)).toEqual(["M", "D", "E"]);
    expect([...panel.querySelectorAll(".tag.child")].map((node) => node.textContent)).toEqual(["Alice", "Bella", "Bella"]);
    expect(panel.querySelectorAll(".tag.no").length).toBe(1);
    window.eval("Date = window.__realDate;");
  });

  test("next lesson names the first lesson after now, tomorrow morning included", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.timetable = { lessons: [{ day_of_week: 4, period: 1, start_time: "08:00", subject_code: "D" }, { day_of_week: 5, period: 1, start_time: "08:00", subject_code: "M", room: "R1" }], period_times: {} };
      state.config = { overview_blocks: [{ key: "next_lesson", size: "normal" }] };
      ${fixedDate("2026-09-03T12:00:00")}
    `);
    const panel = view.querySelector(".panel[data-area='next_lesson']");
    expect(panel).not.toBeNull();
    expect(panel.querySelector(".row-title").textContent).toBe("M");
    expect(panel.querySelector(".row-meta").textContent).toContain(window.eval('t("blocks.day.tomorrow")'));
    expect(panel.querySelector(".row-sub").textContent).toContain("R1");
    window.eval("Date = window.__realDate;");
  });

  test("week renders the grid of the current week and nothing when the week is empty", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `state.config = { overview_blocks: [{ key: "week", size: "compact" }] };`);
    const panel = view.querySelector(".panel[data-area='week']");
    expect(panel).not.toBeNull();
    expect(panel.querySelector(".tt")).not.toBeNull();
    expect(panel.querySelector(".tt-compact")).not.toBeNull();
    const empty = renderOverview(window, `state.timetable = { lessons: [], period_times: {} }; state.config = { overview_blocks: [{ key: "week" }] };`);
    expect(empty.querySelector(".panel[data-area='week']")).toBeNull();
  });

  test("holidays lists the coming entries of the holiday calendar", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.holidays = { "": { status: "ok", days: {}, weeks: [], periods: [{ id: "h1", kind: "school", name: "Herbstferien", name_key: "holidays.period.autumn", start: "2026-10-12", end: "2026-10-24" }, { id: "h0", kind: "school", name: "Sommer", start: "2026-07-01", end: "2026-08-10" }] } };
      state.config = { overview_blocks: [{ key: "holidays", size: "normal" }] };
      ${fixedDate("2026-09-03T08:00:00")}
    `);
    const panel = view.querySelector(".panel[data-area='holidays']");
    expect(panel).not.toBeNull();
    expect([...panel.querySelectorAll(".row-title")].map((node) => node.textContent)).toEqual([window.eval('t("holidays.period.autumn")')]);
    window.eval("Date = window.__realDate;");
  });

  test("chat shows the unread rooms with the count as meta in compact", () => {
    const { window } = loadApp();
    const view = renderOverview(window, `
      state.messengerRooms = { rooms: [{ room_id: "!a:x", name: "Klasse", unread_count: 4 }, { room_id: "!b:x", name: "Still", unread_count: 0 }] };
      state.config = { overview_blocks: [{ key: "chat", size: "compact" }] };
    `);
    const panel = view.querySelector(".panel[data-area='chat']");
    expect([...panel.querySelectorAll(".row-title")].map((node) => node.textContent)).toEqual(["Klasse", window.eval('t("overview.all.messenger")')]);
    expect(panel.querySelector(".row-meta").textContent).toBe("4");
  });
});
