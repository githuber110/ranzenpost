import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(times = 8) {
  for (let round = 0; round < times; round += 1) await settle();
}

async function ready() {
  const app = loadApp();
  await quiet(6);
  app.window.clearTimeout(app.window.eval("bootWatchdog"));
  return app;
}

function stubFetch(window, handler) {
  const calls = [];
  window.fetch = (url, options) => {
    const request = { url: String(url), options: options || {} };
    calls.push(request);
    const result = handler(request) || {};
    return Promise.resolve({
      ok: result.ok !== false,
      status: result.status || 200,
      json: () => Promise.resolve(result.body === undefined ? {} : result.body),
    });
  };
  return calls;
}

function lesson(overrides) {
  return Object.assign(
    {
      date: "02.09.2026",
      day_of_week: 3,
      period: 3,
      start_time: "09:45",
      subject_code: "MA",
      subject_label: "Mathe",
      teacher_code: "BEH",
      teacher_label: "Fr. Behrend",
      room: "R204",
      change_kind: "",
      changed_fields: [],
      previous: {},
    },
    overrides || {}
  );
}

function mark(overrides) {
  return Object.assign(
    {
      id: "m1",
      child_id: "c1",
      date: "2026-09-02",
      period: 3,
      subject_code: "MA",
      name: "Diktat",
      state: "confirmed",
    },
    overrides || {}
  );
}

function prepare(window, marks) {
  window.eval(`
    (function (marks) {
      state.config = { subjects: { MA: { label: "Mathe" }, D: { label: "Deutsch" } }, period_times: { "1": "07:00", "3": "09:45", "5": "11:30" } };
      state.children = [{ child_id: "c1", name: "Kind", class_name: "3b" }];
      state.childId = "c1";
      state.view = "timetable";
      state.marks = { data: { marks: marks } };
      state.timetable = { lessons: [], period_times: {} };
    })
  `)(marks || []);
}

function byText(nodes, text) {
  return [...nodes].find((node) => node.textContent.trim() === text) || null;
}

function label(window, key) {
  return window.eval(`t(${JSON.stringify(key)})`);
}

describe("[P179] marking a lesson as an exam", () => {
  test("the lesson sheet offers the mark action and the round trip posts the anchor", async () => {
    const { window, document } = await ready();
    prepare(window);
    const posts = stubFetch(window, (request) => {
      if (request.options.method === "POST") return { body: mark({ name: "Vokabeltest" }) };
      return { body: { marks: [mark({ name: "Vokabeltest" })], window: {} } };
    });

    window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);
    const add = document.querySelector(".sheet-foot .mark-add");
    expect(add).not.toBeNull();
    expect(add.textContent).toContain(label(window, "marks.action.add"));

    add.click();
    const input = document.querySelector(".sheet-body .inp");
    expect(input).not.toBeNull();
    expect(document.querySelector(".mark-context").textContent).toContain("Mathe");
    input.value = "Vokabeltest";
    input.dispatchEvent(new window.Event("input"));

    byText(document.querySelectorAll(".sheet-foot .btn"), label(window, "marks.form.submit")).click();
    await quiet();

    const created = posts.find((call) => call.options.method === "POST");
    expect(JSON.parse(created.options.body)).toEqual({
      child_id: "c1",
      date: "2026-09-02",
      period: 3,
      subject_code: "MA",
      name: "Vokabeltest",
    });
    expect(posts.some((call) => call.url.endsWith("api/marks") && !call.options.method)).toBe(true);
    expect(window.eval("state.sheet")).toBeNull();
    expect(document.querySelector(".toast").textContent).toContain(label(window, "marks.toast.saved"));
  });

  test("an existing mark turns the foot into rename and remove, and remove calls DELETE", async () => {
    const { window, document } = await ready();
    prepare(window, [mark()]);
    const calls = stubFetch(window, () => ({ body: { marks: [], window: {} } }));

    window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);
    expect(document.querySelector(".mark-panel .mark-name").textContent).toBe("Diktat");
    expect(document.querySelector(".sheet-foot .mark-add")).toBeNull();

    byText(document.querySelectorAll(".sheet-foot .btn"), label(window, "marks.action.remove")).click();
    await quiet();

    const removed = calls.find((call) => call.options.method === "DELETE");
    expect(removed).toBeTruthy();
    expect(removed.url).toContain("api/marks/m1");
    expect(document.querySelector(".toast").textContent).toContain(label(window, "marks.toast.removed"));
  });

  test("a rejected name is shown through the message key the backend sent", async () => {
    const { window, document } = await ready();
    prepare(window);
    stubFetch(window, (request) => {
      if (request.options.method === "POST") {
        return { ok: false, status: 400, body: { ok: false, message_key: "api.marks.error.name" } };
      }
      return { body: { marks: [], window: {} } };
    });

    window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);
    document.querySelector(".sheet-foot .mark-add").click();
    const input = document.querySelector(".sheet-body .inp");
    input.value = "Mira";
    input.dispatchEvent(new window.Event("input"));
    byText(document.querySelectorAll(".sheet-foot .btn"), label(window, "marks.form.submit")).click();
    await quiet();

    const toast = document.querySelector(".toast");
    expect(toast.classList.contains("bad")).toBe(true);
    expect(toast.textContent).toContain(label(window, "api.marks.error.name"));
    expect(window.eval("state.sheet")).not.toBeNull();
  });
});

describe("[P179] the name chips learn from what was used", () => {
  test("saving a name remembers it, the next form offers it, and a chip fills the field", async () => {
    const { window, document } = await ready();
    prepare(window);
    stubFetch(window, (request) => {
      if (request.options.method === "POST") return { body: mark({ name: "Diktat" }) };
      return { body: { marks: [], window: {} } };
    });

    window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);
    document.querySelector(".sheet-foot .mark-add").click();
    const input = document.querySelector(".sheet-body .inp");
    input.value = "Diktat";
    input.dispatchEvent(new window.Event("input"));
    byText(document.querySelectorAll(".sheet-foot .btn"), label(window, "marks.form.submit")).click();
    await quiet();

    expect(JSON.parse(window.localStorage.getItem("markNames"))).toEqual(["Diktat"]);

    window.eval(`openLessonSheet(${JSON.stringify(lesson({ period: 5 }))}, "11:30", "c1")`);
    document.querySelector(".sheet-foot .mark-add").click();
    const chips = document.querySelectorAll(".chip-row .mark-chip");
    expect([...chips].map((chip) => chip.textContent)).toEqual(["Diktat"]);

    chips[0].click();
    expect(document.querySelector(".sheet-body .inp").value).toBe("Diktat");
    expect(window.eval("state.sheetForm.name")).toBe("Diktat");
  });

  test("at most four names are kept, newest first, without duplicates", async () => {
    const { window } = await ready();
    window.eval(`
      ["A", "B", "C", "D", "E", "B"].forEach((name) => rememberMarkName(name));
    `);
    expect(JSON.parse(window.localStorage.getItem("markNames"))).toEqual(["B", "E", "D", "C"]);
  });

  test("an empty name is never learned", async () => {
    const { window } = await ready();
    window.eval(`rememberMarkName("   ")`);
    expect(window.localStorage.getItem("markNames")).toBeNull();
  });
});

describe("[P179] the clarification tile, one anchor state at a time", () => {
  const ways = ["marks.clarify.keep", "marks.clarify.move", "marks.clarify.remove"];

  for (const state of ["cancelled", "foreign", "orphaned"]) {
    test(`${state} shows the tile with all three ways`, async () => {
      const { window, document } = await ready();
      prepare(window, [mark({ state })]);
      window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);

      const tile = document.querySelector(".mark-clarify");
      expect(tile).not.toBeNull();
      expect(tile.textContent).toContain(label(window, `marks.clarify.${state}.title`));
      expect(tile.textContent).toContain(label(window, `marks.clarify.${state}.text`));
      const buttons = [...tile.querySelectorAll(".btn")].map((node) => node.textContent.trim());
      expect(buttons).toEqual(ways.map((key) => label(window, key)));
      const foot = [...document.querySelectorAll(".sheet-foot .btn")].map((node) => node.textContent.trim());
      expect(foot).toEqual([label(window, "marks.action.rename")]);
    });
  }

  for (const state of ["confirmed", "unknown"]) {
    test(`${state} stays quiet - no tile at all`, async () => {
      const { window, document } = await ready();
      prepare(window, [mark({ state })]);
      window.eval(`openLessonSheet(${JSON.stringify(lesson())}, "09:45", "c1")`);
      expect(document.querySelector(".mark-clarify")).toBeNull();
      expect(document.querySelector(".mark-panel")).not.toBeNull();
    });
  }

  test("substituted keeps the mark and only adds a quiet note", async () => {
    const { window, document } = await ready();
    prepare(window, [mark({ state: "substituted" })]);
    window.eval(`openLessonSheet(${JSON.stringify(lesson({ change_kind: "changed" }))}, "09:45", "c1")`);
    expect(document.querySelector(".mark-clarify")).toBeNull();
    expect(document.querySelector(".mark-panel .mark-note").textContent).toBe(
      label(window, "marks.state.substituted")
    );
  });

  test("keeping the mark closes the sheet and writes nothing", async () => {
    const { window, document } = await ready();
    prepare(window, [mark({ state: "cancelled" })]);
    const calls = stubFetch(window, () => ({ body: {} }));
    window.eval(`openLessonSheet(${JSON.stringify(lesson({ change_kind: "cancelled" }))}, "09:45", "c1")`);

    byText(document.querySelectorAll(".mark-clarify .btn"), label(window, "marks.clarify.keep")).click();
    expect(window.eval("state.sheet")).toBeNull();
    expect(calls).toEqual([]);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "marks.clarify.kept"));
  });
});

describe("[P179] moving a mark offers only lessons the day really has", () => {
  function dayWeek(window, lessons) {
    window.eval(`(function (lessons) { state.timetable = { lessons: lessons, period_times: {} }; })`)(lessons);
  }

  test("the own period, cancelled lessons and already marked periods are left out", async () => {
    const { window, document } = await ready();
    prepare(window, [mark(), mark({ id: "m2", period: 5, subject_code: "D" })]);
    dayWeek(window, [
      lesson({ period: 1, subject_code: "D", subject_label: "Deutsch" }),
      lesson({ period: 3 }),
      lesson({ period: 5, subject_code: "D", subject_label: "Deutsch" }),
      lesson({ period: 6, subject_code: "SP", subject_label: "Sport", change_kind: "cancelled" }),
      lesson({ date: "03.09.2026", period: 2, subject_code: "EN", subject_label: "Englisch" }),
    ]);

    window.eval(`openMarkMove(markList()[0], "c1")`);
    const rows = [...document.querySelectorAll(".sheet-body .mark-target .row-title")].map((n) => n.textContent);
    expect(rows).toEqual([
      window.eval(`t("marks.move.option", { period: formatNumber(1), subject: "Deutsch" })`),
    ]);
  });

  test("with nothing left over the sheet says so instead of showing an empty list", async () => {
    const { window, document } = await ready();
    prepare(window, [mark()]);
    dayWeek(window, [lesson({ period: 3 })]);
    window.eval(`openMarkMove(markList()[0], "c1")`);
    expect(document.querySelector(".sheet-body").textContent).toContain(label(window, "marks.move.empty"));
    expect(document.querySelector(".mark-target")).toBeNull();
  });

  test("choosing a target sends period and the subject of that lesson", async () => {
    const { window, document } = await ready();
    prepare(window, [mark({ state: "cancelled" })]);
    dayWeek(window, [lesson({ period: 3, change_kind: "cancelled" }), lesson({ period: 5, subject_code: "D", subject_label: "Deutsch" })]);
    const calls = stubFetch(window, () => ({ body: { marks: [], window: {} } }));

    window.eval(`openMarkMove(markList()[0], "c1")`);
    document.querySelector(".mark-target").click();
    await quiet();

    const moved = calls.find((call) => call.options.method === "POST");
    expect(moved.url).toContain("api/marks/m1");
    expect(JSON.parse(moved.options.body)).toEqual({ period: 5, subject_code: "D" });
    expect(document.querySelector(".toast").textContent).toContain(label(window, "marks.toast.moved"));
  });
});

describe("[P179] the mark is visible where the lesson is", () => {
  test("the grid cell carries the marked class, a shape and the spoken label", async () => {
    const { window } = await ready();
    prepare(window, [mark()]);
    const cell = window.eval(`lessonCell(${JSON.stringify(lesson())}, "09:45", false)`);
    expect(cell.classList.contains("marked")).toBe(true);
    expect(cell.querySelector(".exam-flag")).not.toBeNull();
    expect(cell.getAttribute("aria-label")).toContain(
      window.eval(`t("marks.aria.marked", { name: "Diktat" })`)
    );
  });

  test("an unmarked cell stays untouched", async () => {
    const { window } = await ready();
    prepare(window, []);
    const cell = window.eval(`lessonCell(${JSON.stringify(lesson())}, "09:45", false)`);
    expect(cell.classList.contains("marked")).toBe(false);
    expect(cell.querySelector(".exam-flag")).toBeNull();
  });
});

function renderTodayChapter(window, fixedIso, lessons, marks, absence) {
  const run = window.eval(`
    (function (fixedIso, lessons, marks, absence) {
      const RealDate = Date;
      function FixedDate(...args) {
        if (args.length === 0) return new RealDate(fixedIso);
        return new RealDate(...args);
      }
      FixedDate.prototype = RealDate.prototype;
      Date = FixedDate;
      state.weekOffset = 0;
      state.timetableAvailable = true;
      state.children = [{ child_id: "c1", name: "Kind", class_name: "3b" }];
      state.childId = "c1";
      state.overviewChildId = "c1";
      state.config = { subjects: { MA: { label: "Mathe" } }, period_times: {} };
      state.timetable = { lessons: lessons, period_times: {} };
      state.marks = { data: { marks: marks } };
      state.absence = absence ? { data: { entries: absence } } : null;
      const result = todayChapter();
      Date = RealDate;
      return result;
    })
  `);
  return run(fixedIso, lessons, marks, absence);
}

describe("[P179] the today chapter shows marks and approved absences", () => {
  const WEDNESDAY = "2026-09-02T06:00:00";
  const todayLessons = [
    lesson({ day_of_week: 3, period: 1, subject_code: "D", subject_label: "Deutsch", start_time: "07:00" }),
    lesson({ day_of_week: 3, period: 3, start_time: "09:45" }),
  ];

  test("the marked lesson row carries the exam tag and its name", async () => {
    const { window } = await ready();
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [mark()]);
    const nodes = chapter.blocks.map((block) => block.node);
    const tagged = nodes.filter((node) => node.querySelector && node.querySelector(".tag.exam"));
    expect(tagged.length).toBe(1);
    expect(tagged[0].querySelector(".tag.exam").textContent).toContain("Diktat");
    expect(tagged[0].classList.contains("marked")).toBe(true);
  });

  test("a mark that needs clarification gets its own row above the lessons", async () => {
    const { window } = await ready();
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [mark({ state: "cancelled" })]);
    const first = chapter.blocks[0];
    expect(first.key).toBe("c1:markCheck:m1");
    expect(first.node.textContent).toContain(label(window, "marks.today.needsCheck"));
    expect(first.node.textContent).toContain(label(window, "marks.clarify.cancelled.title"));
  });

  test("a confirmed mark produces no clarification row", async () => {
    const { window } = await ready();
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [mark()]);
    expect(chapter.blocks.some((block) => block.key.includes("markCheck"))).toBe(false);
  });

  test("an approved absence for today becomes one quiet row, an open one does not", async () => {
    const { window } = await ready();
    const approved = [
      { id: "a1", kind: "leave", status: "accepted", student_id: "c1", from_date: "2026-09-02", till_date: "2026-09-02" },
      { id: "a2", kind: "sick", status: "open", student_id: "c1", from_date: "2026-09-02", till_date: "2026-09-02" },
      { id: "a3", kind: "sick", status: "accepted", student_id: "c1", from_date: "2026-08-20", till_date: "2026-08-21" },
    ];
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [], approved);
    const rows = chapter.blocks.filter((block) => block.key.includes(":absence:"));
    expect(rows.length).toBe(1);
    expect(rows[0].key).toBe("c1:absence:a1");
    expect(rows[0].node.textContent).toContain(label(window, "overview.absence.title"));
    expect(rows[0].node.textContent).toContain(window.eval(`absenceTypeLabel("leave")`));
  });

  test("a sick note without a status still counts as absent today", async () => {
    const { window } = await ready();
    const entries = [{ id: "a4", kind: "sick", status: "", student_id: "c1", from_date: "2026-09-01", till_date: "2026-09-03" }];
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [], entries);
    expect(chapter.blocks.filter((block) => block.key.includes(":absence:")).length).toBe(1);
  });

  test("the now anchor still points at a lesson, not at a leading row", async () => {
    const { window } = await ready();
    const entries = [{ id: "a1", kind: "leave", status: "accepted", student_id: "c1", from_date: "2026-09-02", till_date: "2026-09-02" }];
    const chapter = renderTodayChapter(window, WEDNESDAY, todayLessons, [], entries);
    expect(chapter.nowKey).toBe("c1:1");
  });

  test("on a day without lessons an orphaned mark is still reachable", async () => {
    const { window } = await ready();
    const chapter = renderTodayChapter(window, WEDNESDAY, [], [mark({ state: "orphaned" })]);
    expect(chapter.blocks[0].key).toBe("c1:markCheck:m1");
    expect(chapter.blocks[chapter.blocks.length - 1].node.textContent).toContain(
      label(window, "overview.noSchool")
    );
  });
});
