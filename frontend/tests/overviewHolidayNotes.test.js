import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const ONE = "s1:c1";
const TWO = "s2:c2";

function at(window, fixedIso, body, data) {
  const run = window.eval(`
    (function (fixedIso, data) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      FixedDate.now = () => new RealDate(fixedIso).getTime();
      Date = FixedDate;
      try {
        return (${body})(data);
      } finally {
        Date = RealDate;
      }
    })
  `);
  return run(fixedIso, data === undefined ? null : window.JSON.parse(JSON.stringify(data)));
}

function seed(window, extra = "") {
  window.eval(`
    state.children = [{ key: "${ONE}", name: "Alex", connection_id: "s1" }];
    state.childId = "${ONE}";
    state.weekOffset = 0;
    state.config = { period_times: {} };
    state.overviewWeeks = {};
    state.overviewWeekMondays = {};
    state.holidays = { s1: { status: "ok", kind: "school", weeks: [], periods: [], days: {} } };
    ${extra}
  `);
}

function lesson(day, period, code, extra = {}) {
  return { day_of_week: day, period, start_time: `0${7 + period}:00`, subject_code: code, ...extra };
}

const texts = (chapter) => chapter.blocks.map((block) => block.node.textContent);

describe("holiday notes in the look-ahead blocks", () => {
  test("next lesson says when holiday dates are unknown instead of trusting the timetable blindly", () => {
    const { window } = loadApp();
    seed(window, 'state.holidays = { s1: { status: "unknown" } };');
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: data, period_times: {} }, 1: { lessons: [], period_times: {} } };
      return nextLessonChapter("normal");
    }`, [lesson(3, 1, "MA")]);
    const unknown = window.eval('t("overview.holidays.unknown")');
    expect(texts(chapter).some((text) => text.includes(unknown))).toBe(true);
  });

  test("a failed holiday load counts as unknown too", () => {
    const { window } = loadApp();
    seed(window, "state.holidays = { s1: null };");
    const result = at(window, "2026-09-01T10:00:00", "function () { return holidaysUnsure(\"s1\"); }");
    expect(result).toBe(true);
  });

  test("a day that may be free is named in the next day block", () => {
    const { window } = loadApp();
    seed(window, `state.holidays.s1.days["2026-09-02"] = { free: true, overrides_lessons: false, kind: "public", name: "Weltkindertag" };`);
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: data, period_times: {} } };
      return nextDayChapter("normal");
    }`, [lesson(3, 1, "MA")]);
    expect(texts(chapter).some((text) => text.includes("Weltkindertag"))).toBe(true);
  });

  test("the next school day skips a free day that has no name", () => {
    const { window } = loadApp();
    seed(window, 'state.holidays.s1.days["2026-09-02"] = { free: true, overrides_lessons: true, kind: "school" };');
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: data, period_times: {} } };
      return nextDayChapter("normal");
    }`, [lesson(3, 1, "MA"), lesson(4, 1, "EN")]);
    expect(chapter.title).toBe("Donnerstag");
  });
});

describe("look-ahead blocks say loading or failed instead of vanishing", () => {
  test("next lesson stays away while the weeks load and shows a retry when one failed", () => {
    const { window } = loadApp();
    seed(window);
    const loading = at(window, "2026-09-01T10:00:00", `function () {
      window.loadOverviewWeek = () => Promise.resolve();
      return nextLessonChapter("normal");
    }`);
    expect(loading).toBeNull();
    const failed = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: [], period_times: {} }, 1: failedWeek("unreachable", null) };
      return nextLessonChapter("normal");
    }`);
    expect(failed.blocks.map((block) => block.key)).toEqual(["next_lesson:failed"]);
  });

  test("next lesson on another day shows no countdown in hours", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = at(window, "2026-09-04T13:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: [], period_times: {} }, 1: { lessons: data, period_times: {} } };
      return nextLessonChapter("normal");
    }`, [lesson(1, 1, "BIO")]);
    const hours = window.eval("minutesUntilLabel(66 * 60)");
    expect(texts(chapter)[0]).not.toContain(hours);
  });

  test("the week block shows a retry when its week failed", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: failedWeek("unreachable", null) };
      return weekChapter("normal");
    }`);
    expect(chapter.blocks.map((block) => block.key)).toEqual(["week:failed"]);
  });
});

describe("the changes block across children", () => {
  function twoChildren(window) {
    seed(window, `
      state.children = [{ key: "${ONE}", name: "Alex", connection_id: "s1" }, { key: "${TWO}", name: "Sam", connection_id: "s2" }];
      state.holidays = { s1: { status: "ok", days: {} }, s2: { status: "ok", days: {} } };
    `);
  }

  test("sorts all children by date before cutting, so a sibling's change tomorrow stays visible", () => {
    const { window } = loadApp();
    twoChildren(window);
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      const cancelled = (day, period) => ({ day_of_week: day, period, start_time: "08:00", subject_code: "D", change_kind: "cancelled" });
      state.overviewWeeks["${ONE}"] = { 0: { lessons: [], period_times: {} }, 1: { lessons: [1, 2, 3, 4, 5].map((day) => cancelled(day, 1)).concat([cancelled(1, 2), cancelled(2, 2)]), period_times: {} } };
      state.overviewWeeks["${TWO}"] = { 0: { lessons: [cancelled(3, 1)], period_times: {} }, 1: { lessons: [], period_times: {} } };
      return changesChapter("compact");
    }`);
    expect(chapter.blocks[0].key).toBe(`change:${TWO}:2026-09-02:1`);
    expect(chapter.fresh).toBe(false);
  });

  test("says which child's timetable is missing when one sibling failed", () => {
    const { window } = loadApp();
    twoChildren(window);
    const chapter = at(window, "2026-09-01T10:00:00", `function () {
      state.overviewWeeks["${ONE}"] = { 0: { lessons: [{ day_of_week: 3, period: 1, start_time: "08:00", subject_code: "D", change_kind: "cancelled" }], period_times: {} }, 1: { lessons: [], period_times: {} } };
      state.overviewWeeks["${TWO}"] = { 0: failedWeek("unreachable", null), 1: { lessons: [], period_times: {} } };
      return changesChapter("normal");
    }`);
    expect(chapter.blocks.some((block) => block.key === "changes:partial")).toBe(true);
  });
});

describe("timetable links and school holidays", () => {
  test("opening the timetable from a row of next week opens next week", () => {
    const { window } = loadApp();
    seed(window);
    const offset = at(window, "2026-09-04T10:00:00", `function () {
      openTimetableOf("${ONE}", "2026-09-08");
      return state.weekOffset;
    }`);
    expect(offset).toBe(1);
  });

  test("a sibling's timetable grid uses the holidays of its own school", () => {
    const { window } = loadApp();
    seed(window, `
      state.children = [{ key: "${ONE}", name: "Alex", connection_id: "s1" }, { key: "${TWO}", name: "Sam", connection_id: "s2" }];
      state.holidays = {
        s1: { status: "ok", days: {}, weeks: [], periods: [] },
        s2: { status: "ok", weeks: [], periods: [], days: { "2026-09-02": { free: true, overrides_lessons: true, kind: "public", name: "Brückentag Süd" } } },
      };
    `);
    const text = at(window, "2026-09-01T10:00:00", `function () {
      const grid = timetableGrid({ lessons: data, period_times: {} }, "${TWO}", { monday: startOfWeek(new Date()), swipe: false });
      return grid.textContent;
    }`, [lesson(3, 1, "MA")]);
    expect(text).toContain("Brückentag Süd");
  });

  test("the navigation names mail, files and contacts modules with real words", () => {
    const { window } = loadApp();
    for (const name of ["mail", "file", "addressbook", "mailinglist"]) {
      const key = `settings.modules.name.${name}`;
      expect(evalWith(window, "t(testArgs[0])", key)).not.toBe(key);
    }
  });
});

describe("small overview details", () => {
  test("a one-day holiday shows one date, not a range", () => {
    const { window } = loadApp();
    seed(window, 'state.holidays = { s1: { status: "ok", days: {}, weeks: [], periods: [{ id: "p1", kind: "public", name: "Tag der Deutschen Einheit", start: "2026-10-03", end: "2026-10-03" }] } };');
    const chapter = at(window, "2026-09-01T10:00:00", "function () { return holidaysChapter(\"normal\"); }");
    const text = chapter.blocks[0].node.textContent;
    expect(text).toContain(window.eval('showDate("2026-10-03")'));
    expect(text).not.toContain("–");
  });

  test("the back button on the first page of a section names the section it goes back to", () => {
    const { window } = loadApp();
    seed(window);
    const label = window.eval(`(function () {
      const real = layoutMode;
      layoutMode = () => "phone";
      const head = overviewPanelHead({ title: "Elternbriefe", previousTitle: "Heute", meta: null, link: null }, 0, 2, 1);
      layoutMode = real;
      return head.querySelector(".panel-back").getAttribute("aria-label");
    })()`);
    expect(label).toBe(window.eval('t("overview.page.backArea", { area: "Heute" })'));
  });

});

describe("lists from several schools", () => {
  test("tasks say a school is missing instead of vanishing when the reachable school has nothing open", () => {
    const { window } = loadApp();
    seed(window);
    const keys = window.eval(`(function () {
      state.modules.available.tasks = true;
      state.tasks = { tasks: [], unavailable: ["s2"] };
      const chapter = tasksChapter("normal");
      return chapter ? chapter.blocks.map((block) => block.key) : null;
    })()`);
    expect(keys).toEqual(["tasks:failed"]);
  });

  test("news from the reachable school carry a note that the list is incomplete", () => {
    const { window } = loadApp();
    seed(window);
    const keys = window.eval(`(function () {
      state.modules.available.news = true;
      state.news = { news: [{ id: "n1", title: "Sportfest", connection_id: "s1", date: "2026-09-01" }], unavailable: ["s2"] };
      const chapter = newsChapter("normal");
      return chapter ? chapter.blocks.map((block) => block.key) : null;
    })()`);
    expect(keys).toContain("news:partial");
  });
});
