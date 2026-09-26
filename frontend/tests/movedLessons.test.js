import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");
const styles = fs.readFileSync(path.join(frontendDir, "styles.css"), "utf8");

const AWAY = {
  date: "08.09.2026", day_of_week: 2, period: 6, subject_code: "L", room: "R0.04",
  change_kind: "cancelled", changed_fields: [], previous: {},
  moved_to: { date: "10.09.2026", period: 5, period_end: 5 }, moved_from: null,
  change_note: "Material mitbringen", teacher_hidden: false, classes: "",
};
const HERE = {
  date: "10.09.2026", day_of_week: 4, period: 5, subject_code: "L", room: "R0.04",
  change_kind: "changed", changed_fields: ["subject"], previous: { subject: "E", teacher: "", room: "R0.04" },
  moved_to: null, moved_from: { date: "08.09.2026", period: 6, period_end: 6 },
  change_note: "", teacher_hidden: false, classes: "",
};
const HIDDEN = {
  date: "08.09.2026", day_of_week: 2, period: 2, subject_code: "Eth", room: "R0.06",
  change_kind: "changed", changed_fields: ["class"],
  previous: { subject: "Eth", teacher: "", room: "R0.06", class: "5A" },
  moved_to: null, moved_from: null, change_note: "", teacher_hidden: true, classes: "5A, 5B, 5C",
};

function cell(window, lesson, compact) {
  const run = window.eval("(function (lesson, compact) { state.cancellations = null; return lessonCell(lesson, '', compact); })");
  return run(lesson, !!compact);
}

function lessonSheetOf(window, lesson) {
  const run = window.eval("(function (lesson) { return lessonSheet(lesson, '', 'c1', [lesson]); })");
  return run(lesson);
}

function text(window, key, vars) {
  return window.t(key, vars || {});
}

describe("moved lessons of the time-table module", () => {
  test("the cancelled half of a move names its new place in the cell", () => {
    const { window } = loadApp();
    const node = cell(window, AWAY);
    expect(node.classList.contains("out")).toBe(true);
    expect(node.classList.contains("moved")).toBe(true);
    expect(node.querySelector(".room").textContent).toBe("auf Do 5");
    expect(node.querySelector(".bar")).toBeNull();
  });

  test("the new place of a move names where the lesson came from", () => {
    const { window } = loadApp();
    const node = cell(window, HERE);
    expect(node.classList.contains("subbed")).toBe(true);
    expect(node.classList.contains("moved")).toBe(true);
    expect(node.querySelector(".room").textContent).toBe("von Di 6");
    expect(node.getAttribute("aria-label")).toContain("von Di 6");
  });

  test("a moved double period names the span", () => {
    const { window } = loadApp();
    const node = cell(window, Object.assign({}, AWAY, { moved_to: { date: "10.09.2026", period: 3, period_end: 4 } }));
    expect(node.querySelector(".room").textContent).toBe("auf Do 3–4");
  });

  test("a change without a move keeps the known labels", () => {
    const { window } = loadApp();
    expect(cell(window, Object.assign({}, AWAY, { moved_to: null })).querySelector(".room").textContent).toBe("Entfällt");
    expect(cell(window, Object.assign({}, HIDDEN)).querySelector(".room").textContent).toBe("Vertr.");
    expect(cell(window, Object.assign({}, HIDDEN)).classList.contains("moved")).toBe(false);
  });

  test("the note of the school shows as a hint in the cell and in its spoken label", () => {
    const { window } = loadApp();
    const node = cell(window, AWAY);
    expect(node.querySelector(".note-flag")).not.toBeNull();
    expect(node.getAttribute("aria-label")).toContain(text(window, "timetable.aria.note", { note: "Material mitbringen" }));
    expect(cell(window, HERE).querySelector(".note-flag")).toBeNull();
    const unchanged = Object.assign({}, HERE, { change_kind: "", moved_from: null, change_note: "Material mitbringen" });
    expect(cell(window, unchanged).querySelector(".note-flag")).toBeNull();
  });

  test("the lesson sheet shows the move and the note as sent by the school", () => {
    const { window } = loadApp();
    const sheet = lessonSheetOf(window, AWAY);
    const banner = sheet.querySelector(".banner");
    expect(banner.classList.contains("moved")).toBe(true);
    expect(styles).toContain(".banner.moved .mark { background: var(--moved); }");
    expect(banner.textContent).toContain(text(window, "timetable.change.moved"));
    expect(banner.textContent).toContain("Diese Stunde wird auf Donnerstag, 10.09., 5. Stunde verlegt.");
    const note = sheet.querySelector(".change-note");
    expect(note.textContent).toBe("Material mitbringen");
    expect(note.getAttribute("dir")).toBe("auto");
    expect(sheet.textContent).toContain(text(window, "timetable.schoolNote"));
  });

  test("the lesson sheet of the new place names the old place", () => {
    const { window } = loadApp();
    const sheet = lessonSheetOf(window, HERE);
    expect(sheet.querySelector(".banner").textContent).toContain("Diese Stunde wurde von Dienstag, 08.09., 6. Stunde hierher verlegt.");
    expect(sheet.querySelector(".change-note")).toBeNull();
  });

  test("a substitute whose teacher the school hides says so, and joined classes show both lists", () => {
    const { window } = loadApp();
    const sheet = lessonSheetOf(window, HIDDEN);
    expect(sheet.querySelector(".banner").textContent).toContain(text(window, "timetable.banner.hiddenTeacher"));
    const swaps = [...sheet.querySelector(".field-group").querySelectorAll(".cell")].map((row) => row.textContent);
    expect(swaps).toEqual([`${text(window, "timetable.field.class")}5A→5A, 5B, 5C`]);
    const facts = [...sheet.querySelectorAll(".field-group")].pop().textContent;
    expect(facts).toContain(`${text(window, "timetable.field.teacher")}${text(window, "timetable.teacher.hidden")}`);
  });

  test("the legend names moved lessons only in a week that has one", () => {
    const { window } = loadApp();
    const moved = window.eval("(function (lessons) { return movedLegendItems({ lessons }); })");
    expect(moved([AWAY, HERE]).map((item) => item.textContent)).toEqual([text(window, "timetable.change.moved")]);
    expect(moved([HIDDEN])).toEqual([]);
  });

  test("an Arabic reader gets the move in Arabic and the hint keeps logical positions", () => {
    const { window } = loadApp();
    const ar = JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", "ar.json"), "utf8"));
    window.setLanguageBundle("ar", ar, ar);
    const label = cell(window, AWAY).querySelector(".room").textContent;
    expect(label.startsWith("إلى ")).toBe(true);
    const rules = styles.split("}").filter((rule) => /\.note-flag|\.moved/.test(rule));
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) expect(rule).not.toMatch(/(^|[^-])(left|right)\s*:/);
  });

  test("the overview lists both halves of a move and the next lesson skips the moved-away one", () => {
    const { window } = loadApp();
    const run = window.eval(`
      (function (lessons) {
        const RealDate = Date;
        function FixedDate(...args) {
          if (args.length === 0) return new RealDate("2026-09-07T06:00:00");
          return new RealDate(...args);
        }
        FixedDate.prototype = RealDate.prototype;
        Date = FixedDate;
        state.modules = { available: { timetable: true } };
        state.children = [{ key: "c1", name: "Kim Muster" }];
        state.childId = "c1";
        state.timetable = null;
        state.overviewWeeks = { c1: { 0: { lessons, period_times: {} }, 1: { lessons: [], period_times: {} } } };
        const chapter = changesChapter("normal");
        const next = nextLessonChapter("normal");
        Date = RealDate;
        const text = (block) => (block.node ? block.node.textContent : String(block.textContent || ""));
        return { rows: chapter.blocks.map(text), next: next.blocks.map(text) };
      })
    `);
    const plain = { date: "08.09.2026", day_of_week: 2, period: 5, start_time: "11:40", subject_code: "D", change_kind: "" };
    const result = run([AWAY, HERE, plain]);
    const joined = JSON.stringify(result.rows);
    expect(joined).toContain("auf Do 5");
    expect(joined).toContain("von Di 6");
    expect(result.rows.length).toBe(2);
    expect(result.next[0]).toContain("D");
    expect(result.next[0]).not.toContain("L");
  });
});

describe("a change record that changes nothing visible", () => {
  const BARE = {
    date: "05.10.2026", day_of_week: 1, period: 1, subject_code: "D", teacher_code: "KLE", room: "R101",
    change_kind: "changed", changed_fields: [], previous: { subject: "D", teacher: "KLE", room: "R101" },
    moved_to: null, moved_from: null, change_note: "", teacher_hidden: false, classes: "", no_details: true,
  };

  test("the cell and the sheet say the school changed it, not that it is covered", () => {
    const { window } = loadApp();
    const node = cell(window, BARE);
    expect(node.querySelector(".room").textContent).toBe(text(window, "timetable.cell.school"));
    expect(node.getAttribute("aria-label")).toContain(text(window, "timetable.change.school"));
    const banner = lessonSheetOf(window, BARE).querySelector(".banner");
    expect(banner.textContent).toContain(text(window, "timetable.change.school"));
    expect(banner.textContent).toContain(text(window, "timetable.banner.school"));
    expect(banner.textContent).not.toContain(text(window, "timetable.banner.changed"));
  });

  test("a covered lesson keeps the covered label", () => {
    const { window } = loadApp();
    const covered = Object.assign({}, BARE, { teacher_code: "MEY", changed_fields: ["teacher"], no_details: false });
    const older = { subject_code: "MA", change_kind: "changed", room: "R204" };
    expect(cell(window, older).querySelector(".room").textContent).toBe(text(window, "timetable.cell.substitute"));
    expect(cell(window, covered).querySelector(".room").textContent).toBe(text(window, "timetable.cell.substitute"));
    expect(lessonSheetOf(window, covered).querySelector(".banner").textContent).toContain(text(window, "timetable.banner.changed"));
  });
});

describe("wording of moves and hidden teachers", () => {
  function bundle(window, language) {
    const loaded = JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", `${language}.json`), "utf8"));
    window.setLanguageBundle(language, loaded, loaded);
  }

  test("Russian and Ukrainian name the old place of a move in the genitive", () => {
    const ru = loadApp();
    bundle(ru.window, "ru");
    expect(lessonSheetOf(ru.window, HERE).querySelector(".banner").textContent).toContain("6-го урока");
    const uk = loadApp();
    bundle(uk.window, "uk");
    expect(lessonSheetOf(uk.window, HERE).querySelector(".banner").textContent).toContain("6-го уроку");
  });

  test("a hidden teacher replacing a named one keeps the change row", () => {
    const { window } = loadApp();
    const named = Object.assign({}, HIDDEN, { changed_fields: ["teacher"], previous: { subject: "Eth", teacher: "KLE", room: "R0.06" } });
    const rows = [...lessonSheetOf(window, named).querySelector(".field-group").querySelectorAll(".cell")].map((row) => row.textContent);
    expect(rows).toEqual([`${text(window, "timetable.field.teacher")}KLE→${text(window, "timetable.teacher.hidden")}`]);
  });
});

describe("a moved-away lesson that carries an exam mark", () => {
  test("keeps the ring of the exam mark", () => {
    const rules = styles.split("}").map((rule) => rule.trim());
    const clearing = rules.filter((rule) => /\.tt-cell\.out\.moved[^{]*\{[^}]*box-shadow\s*:\s*none/.test(rule));
    expect(clearing.length).toBeGreaterThan(0);
    for (const rule of clearing) expect(rule.split("{")[0]).toContain(":not(.marked)");
  });
});

describe("the note of the school is text, never markup", () => {
  test("a note with an image tag renders as plain text in the sheet and the cell", () => {
    const { window } = loadApp();
    const note = "<img src=x onerror=alert(1)>";
    const lesson = Object.assign({}, AWAY, { change_note: note });
    const sheet = lessonSheetOf(window, lesson);
    expect(sheet.querySelector("img")).toBeNull();
    expect(sheet.querySelector(".change-note").textContent).toBe(note);
    const node = cell(window, lesson);
    expect(node.querySelector("img")).toBeNull();
    expect(node.getAttribute("aria-label")).toContain(note);
  });
});
