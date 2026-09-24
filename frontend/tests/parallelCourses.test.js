import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const CHILD = "s1:c1";
const ELECTIVES = [
  ["E1", "Frau Castor", "R201"],
  ["E2", "Herr Dachs", "R202"],
  ["F1", "Frau Elster", "R203"],
  ["L1", "Herr Fink", "R204"],
  ["SP", "Frau Gans", "GYM1"],
  ["SP", "Herr Hase", "GYM2"],
];

function lesson(day, period, code, teacher, room, extra) {
  return Object.assign({
    date: "01.09.2026",
    day_of_week: day,
    period,
    start_time: "08:00",
    subject_code: code,
    subject_label: code,
    teacher_code: teacher.slice(-3).toUpperCase(),
    teacher_label: teacher,
    room,
    change_kind: "",
    course_key: `${code}|${teacher}`,
  }, extra || {});
}

function week(chosen) {
  return {
    lessons: [
      lesson(2, 1, "D", "Frau Amsel", "R101"),
      lesson(2, 2, "M", "Herr Biber", "R101"),
      lesson(2, 2, "TEAM", "Frau Amsel", "R102"),
      ...ELECTIVES.map(([code, teacher, room]) => lesson(2, 3, code, teacher, room)),
    ],
    period_times: { 1: "08:00", 2: "08:50", 3: "09:45" },
    courses: { parallel: 8, chosen: !!chosen, hidden: 0, new: 0, signature: chosen ? "x" : "" },
  };
}

function withChild(window) {
  window.eval(`state.children = [{ key: "${CHILD}", child_id: "c1", connection_id: "s1", name: "Kim Muster", class_name: "9x" }]; state.childId = "${CHILD}";`);
}

function renderGrid(window, data) {
  withChild(window);
  return window.eval("(function (data) { state.weekOffset = 0; return timetableGrid(data, state.childId); })")(data);
}

function renderTodayAt(window, fixedIso, data) {
  withChild(window);
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
  return run(fixedIso, data);
}

function openSheetNode(window) {
  return window.eval("state.sheet()");
}

const catalogue = {
  chosen: false,
  courses: [
    { key: "E1|CCC", subject_code: "E1", subject_label: "E1", group: "E", teacher_label: "Frau Castor", rooms: ["R201"], count: 2, chosen: false, new: false },
    { key: "E2|DDD", subject_code: "E2", subject_label: "E2", group: "E", teacher_label: "Herr Dachs", rooms: ["R202"], count: 2, chosen: true, new: false },
    { key: "F1|EEE", subject_code: "F1", subject_label: "F1", group: "F", teacher_label: "Frau Elster", rooms: ["R203"], count: 2, chosen: false, new: true },
    { key: "OLD|ZZZ", subject_code: "OLD", subject_label: "OLD", group: "OLD", teacher_label: "Herr Zander", rooms: [], count: 0, chosen: false, new: false },
  ],
};

function renderCoursesPage(window, data) {
  withChild(window);
  return window.eval(`(function (data) {
    state.coursesPage = { child: "${CHILD}", data, failed: false, draft: null, search: "", saving: false, from: "settings" };
    return coursesPageView();
  })`)(data);
}

describe("parallel courses in the timetable grid", () => {
  test("a period with six lessons shows one compact courses cell instead of six chips", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, week(false));
    const cells = grid.querySelectorAll("button.tt-cell.courses");
    expect(cells.length).toBe(1);
    expect(cells[0].querySelector(".sub").textContent).toBe("6");
    expect(cells[0].querySelector(".courses-label").textContent).toBe("Kurse");
    expect(cells[0].getAttribute("aria-label")).toBe("6 Kurse gleichzeitig");
    expect(cells[0].closest(".tt-stack")).toBeNull();
  });

  test("single lessons and a two-lesson period keep today's cells", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, week(false));
    const stacks = grid.querySelectorAll(".tt-stack");
    expect(stacks.length).toBe(1);
    expect([...stacks[0].querySelectorAll("button.tt-cell.compact .sub")].map((node) => node.textContent)).toEqual(["M", "TEAM"]);
    const single = [...grid.querySelectorAll("button.tt-cell")].filter((cell) => !cell.classList.contains("compact") && !cell.classList.contains("courses"));
    expect(single.map((cell) => cell.querySelector(".sub").textContent)).toEqual(["D"]);
  });

  test("the courses cell opens a sheet listing every course with a hint to choose", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, week(false));
    grid.querySelector("button.tt-cell.courses").click();
    const sheet = openSheetNode(window);
    expect(sheet.querySelector(".sheet-title").textContent).toBe("6 Kurse gleichzeitig");
    expect(sheet.querySelector(".courses-hint").textContent).toContain("Kim");
    const rows = sheet.querySelectorAll(".courses-list .course-row");
    expect(rows.length).toBe(6);
    expect([...rows].map((row) => row.querySelector(".row-title").textContent)).toEqual(["E1", "E2", "F1", "L1", "SP", "SP"]);
    expect(rows[0].querySelector(".row-sub").textContent).toBe("Frau Castor · R201");
    const action = sheet.querySelector(".sheet-foot .courses-open");
    expect(action.textContent).toBe("Kurse auswählen");
    expect(action.classList.contains("ghost")).toBe(false);
  });

  test("once courses are chosen the sheet drops the hint and offers a quiet change button", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, week(true));
    grid.querySelector("button.tt-cell.courses").click();
    const sheet = openSheetNode(window);
    expect(sheet.querySelector(".courses-hint")).toBeNull();
    const action = sheet.querySelector(".sheet-foot .courses-open");
    expect(action.textContent).toBe("Kurse ändern");
    expect(action.classList.contains("ghost")).toBe(true);
  });

  test("a course row in the sheet opens that lesson's own sheet", () => {
    const { window } = loadApp();
    const grid = renderGrid(window, week(false));
    grid.querySelector("button.tt-cell.courses").click();
    openSheetNode(window).querySelectorAll(".course-row")[3].click();
    expect(openSheetNode(window).querySelector(".sheet-title").textContent).toBe("L1");
  });

  test("a changed course marks the courses cell", () => {
    const { window } = loadApp();
    const data = week(false);
    data.lessons[5] = Object.assign({}, data.lessons[5], { change_kind: "changed", changed_fields: ["teacher"], previous: { subject: "", teacher: "", room: "" } });
    const cell = renderGrid(window, data).querySelector("button.tt-cell.courses");
    expect(cell.classList.contains("subbed")).toBe(true);
  });
});

describe("parallel courses in the today card", () => {
  test("a period with many lessons becomes one row that opens the courses sheet", () => {
    const { window } = loadApp();
    const section = renderTodayAt(window, "2026-09-01T06:00:00", week(false));
    const row = section.querySelector(".rows.flat .courses-row");
    expect(row).not.toBeNull();
    expect(row.querySelector(".row-title").textContent).toBe("6 Kurse gleichzeitig");
    expect(row.querySelector(".row-meta").textContent).toBe("09:45");
    expect(row.querySelector(".courses-codes").textContent).toBe("E1, E2, F1, L1, SP, SP");
    const plain = section.querySelectorAll(".rows.flat .row:not(.row-note):not(.courses-row)");
    expect(plain.length).toBe(2);
    row.click();
    expect(openSheetNode(window).querySelectorAll(".course-row").length).toBe(6);
  });
});

describe("course choice page", () => {
  test("lists the courses grouped, marks chosen, new and unseen ones", () => {
    const { window } = loadApp();
    const view = renderCoursesPage(window, Object.assign({}, catalogue, { chosen: true }));
    expect(view.querySelector(".courses-question").textContent).toBe("Welche Kurse besucht Kim?");
    const groups = [...view.querySelectorAll(".courses-group .overline")].map((node) => node.textContent);
    expect(groups).toEqual(["E", "F", "OLD"]);
    const checked = [...view.querySelectorAll(".course-pick")].filter((input) => input.checked).map((input) => input.value);
    expect(checked).toEqual(["E2|DDD"]);
    expect(view.querySelector('[data-course="F1|EEE"] small').textContent).toBe("Neu");
    expect(view.querySelector('[data-course="OLD|ZZZ"] small').textContent).toBe("Diese zwei Wochen nicht im Plan");
    expect(view.querySelector(".note").textContent).toContain("1 Kurs ist neu");
    expect(view.querySelectorAll(".courses-save").length).toBe(1);
    expect(view.querySelector(".search-input")).toBeNull();
  });

  test("ticking and unticking updates the draft that will be saved", () => {
    const { window } = loadApp();
    const view = renderCoursesPage(window, Object.assign({}, catalogue, { chosen: true }));
    const first = view.querySelector('[data-course="E1|CCC"] input');
    first.checked = true;
    first.dispatchEvent(new window.Event("change"));
    const second = view.querySelector('[data-course="E2|DDD"] input');
    second.checked = false;
    second.dispatchEvent(new window.Event("change"));
    expect(window.eval("state.coursesPage.draft")).toEqual(["E1|CCC"]);
  });

  test("a long list gets a search that filters without losing ticks", () => {
    const { window } = loadApp();
    const many = { chosen: true, courses: [] };
    for (let index = 1; index <= 12; index += 1) {
      many.courses.push({ key: `K${index}|T${index}`, subject_code: `K${index}`, subject_label: `K${index}`, group: "K", teacher_label: `Lehrkraft ${index}`, rooms: [`R${index}`], count: 1, chosen: index === 2, new: false });
    }
    const view = renderCoursesPage(window, many);
    const input = view.querySelector(".search-input");
    expect(input).not.toBeNull();
    input.value = "lehrkraft 1";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(view.querySelectorAll(".course-check").length).toBe(4);
    input.value = "nichts";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(view.querySelectorAll(".course-check").length).toBe(0);
    expect(view.querySelector(".courses-groups").textContent).toBe("Kein Kurs passt zur Suche.");
    expect(window.eval("state.coursesPage.draft")).toEqual(["K2|T2"]);
  });

  test("the first visit ticks every course so saving right away hides nothing", () => {
    const { window } = loadApp();
    const view = renderCoursesPage(window, catalogue);
    const checked = [...view.querySelectorAll(".course-pick")].filter((input) => input.checked).map((input) => input.value);
    expect(checked).toEqual(["E1|CCC", "E2|DDD", "F1|EEE", "OLD|ZZZ"]);
    expect(window.eval("state.coursesPage.draft").slice().sort()).toEqual(["E1|CCC", "E2|DDD", "F1|EEE", "OLD|ZZZ"]);
  });

  function emptySave(window) {
    const posts = [];
    window.fetch = (url, options) => {
      if (options && options.method === "POST") {
        posts.push(JSON.parse(options.body));
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
      }
      return Promise.reject(new Error("network disabled in tests"));
    };
    renderCoursesPage(window, Object.assign({}, catalogue, { chosen: true }));
    window.eval("state.coursesPage.draft = []");
    const pending = window.eval("saveCoursePage()");
    return { posts, pending };
  }

  test("saving with no course ticked asks first and saves nothing on cancel", async () => {
    const { window } = loadApp();
    const { posts, pending } = emptySave(window);
    const sheet = openSheetNode(window);
    expect(sheet.querySelector(".sheet-title").textContent).toBe("Keinen Kurs wählen?");
    const [confirm, cancel] = sheet.querySelectorAll(".btn-stack .btn");
    expect(confirm.textContent).toBe("Alle ausblenden");
    cancel.click();
    await pending;
    expect(posts).toEqual([]);
    expect(window.eval("state.coursesPage.saving")).toBe(false);
  });

  test("saving with no course ticked goes through only after the confirmation", async () => {
    const { window } = loadApp();
    const { posts, pending } = emptySave(window);
    openSheetNode(window).querySelector(".btn-stack .btn").click();
    await pending;
    expect(posts.length).toBe(1);
    expect(posts[0].chosen).toEqual([]);
    expect(posts[0].confirm_empty).toBe(true);
  });

  test("a normal choice saves without asking", async () => {
    const { window } = loadApp();
    const posts = [];
    window.fetch = (url, options) => {
      if (options && options.method === "POST") posts.push(JSON.parse(options.body));
      return options && options.method === "POST"
        ? Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
        : Promise.reject(new Error("network disabled in tests"));
    };
    renderCoursesPage(window, Object.assign({}, catalogue, { chosen: true }));
    await window.eval("saveCoursePage()");
    expect(window.eval("state.sheet")).toBeNull();
    expect(posts.length).toBe(1);
    expect(posts[0].chosen).toEqual(["E2|DDD"]);
    expect(posts[0].confirm_empty).toBeUndefined();
  });

  test("a plan without parallel courses says there is nothing to choose", () => {
    const { window } = loadApp();
    const view = renderCoursesPage(window, { chosen: false, courses: [] });
    expect(view.querySelector(".courses-empty").textContent).toContain("keine Kurse parallel");
    expect(view.querySelector(".courses-save")).toBeNull();
  });
});

describe("course setting row", () => {
  function rows(window, config, weekData) {
    withChild(window);
    return window.eval(`(function (config, weekData) {
      state.config = config;
      state.overviewWeeks = { "${CHILD}": { 0: weekData } };
      state.timetable = null;
      return courseSettingRows("s1").map((row) => [row.querySelector(".lbl").textContent, row.querySelector(".val").textContent]);
    })`)(config, weekData);
  }

  test("appears only for a child whose plan has parallel courses or a stored choice", () => {
    const { window } = loadApp();
    const config = { connections: [{ id: "s1", course_filters: {} }] };
    expect(rows(window, config, { lessons: [], courses: { parallel: 0, chosen: false } })).toEqual([]);
    expect(rows(window, config, { lessons: [], courses: { parallel: 5, chosen: false } })).toEqual([["Kurse von Kim", "Alle"]]);
    const stored = { connections: [{ id: "s1", course_filters: { c1: { chosen: ["E1|CCC", "E2|DDD"], known: ["E1|CCC", "E2|DDD", "F1|EEE"] } } }] };
    expect(rows(window, stored, null)).toEqual([["Kurse von Kim", "2 gewählt"]]);
  });
});
