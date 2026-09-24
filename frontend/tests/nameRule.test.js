import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

const CONNECTIONS = [
  { id: ONE, school_url: "https://gymsued.example", school_name: "Gymnasium Süd", setup_complete: true, phones: [], period_times: {}, subjects: {}, teachers: {} },
  { id: TWO, school_url: "https://iserv.gs-nord.example", school_name: "Grundschule Nord", short_name: "GS Nord", setup_complete: true, phones: [], period_times: {}, subjects: {}, teachers: {} },
];

function seed(window, children, schools = 2) {
  window.eval(`
    state.config = { connections: ${JSON.stringify(CONNECTIONS.slice(0, schools))}, language: "de", notify_services: [] };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(children[0].key)};
    state.schools = [];
    state.schoolStatus = {};
    state.loadedAt = {};
  `);
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

describe("name helpers", () => {
  test("firstName takes the first token, also after a comma-separated surname, and copes with empty input", () => {
    const { window } = loadApp();
    expect(window.eval('firstName("Mia Musterkind")')).toBe("Mia");
    expect(window.eval('firstName("Tom Musterkind-Langenscheidt")')).toBe("Tom");
    expect(window.eval('firstName("Musterkind, Anna Lena")')).toBe("Anna");
    expect(window.eval('firstName("  Lea  ")')).toBe("Lea");
    expect(window.eval('firstName("")')).toBe("");
    expect(window.eval("firstName(null)")).toBe("");
  });

  test("teacherSurname keeps a multi-part surname from the source and falls back to the full label, then the code", () => {
    const { window } = loadApp();
    expect(window.eval('teacherSurname({ teacher_surname: "van der Berg", teacher_label: "Anna van der Berg", teacher_code: "VDB" })')).toBe("van der Berg");
    expect(window.eval('teacherSurname({ teacher_surname: "", teacher_label: "Anna van der Berg", teacher_code: "VDB" })')).toBe("Anna van der Berg");
    expect(window.eval('teacherSurname({ teacher_code: "VDB" })')).toBe("VDB");
    expect(window.eval("teacherSurname(null)")).toBe("");
  });

  test("today rows show the teacher surname next to the subject, never the first name", () => {
    const { window } = loadApp();
    seed(window, [{ key: `${ONE}:c1`, connection_id: ONE, name: "Mia Musterkind", class_name: "7b" }], 1);
    const row = window.eval(`compactLesson({ lesson: { period: 1, subject_code: "M", subject_label: "Mathe", teacher_label: "Anna Beispiel", teacher_surname: "Beispiel" }, time: "08:00", childId: ${JSON.stringify(`${ONE}:c1`)}, mark: null }, false)`);
    expect(row.querySelector(".row-sub").textContent).toBe("Beispiel");
  });
});

describe("children are named by first name outside detail pages", () => {
  const CHILDREN = [
    { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, school: "Gymnasium Süd", name: "Mia Musterkind", class_name: "7b" },
    { key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, school: "Grundschule Nord", name: "Mia Beispiel", class_name: "3a" },
    { key: `${TWO}:c3`, child_id: "c3", connection_id: TWO, school: "Grundschule Nord", name: "Lea Beispiel", class_name: "1c" },
  ];

  test("the overview chips carry the first name and the short name only on the two children who share it", () => {
    const { window } = loadApp();
    seed(window, CHILDREN);
    const bar = window.eval(`overviewChips(${JSON.stringify(`${TWO}:c3`)})`);
    expect(texts(bar.querySelectorAll(".chip"))).toEqual(["Mia · gymsued", "Mia · GS Nord", "Lea"]);
    expect(bar.querySelector(".chip .chip-label").textContent).toBe(window.eval('t("child.labelWithSchool", { label: "Mia", school: "gymsued" })'));
  });

  test("with one school the chips are plain first names", () => {
    const { window } = loadApp();
    seed(window, [CHILDREN[0], Object.assign({}, CHILDREN[2], { key: `${ONE}:c3`, connection_id: ONE })], 1);
    const bar = window.eval(`overviewChips(${JSON.stringify(`${ONE}:c1`)})`);
    expect(texts(bar.querySelectorAll(".chip"))).toEqual(["Mia", "Lea"]);
  });

  test("two children with the same first name at the same school fall back to the full name", () => {
    const { window } = loadApp();
    seed(window, [CHILDREN[0], Object.assign({}, CHILDREN[1], { key: `${ONE}:c9`, connection_id: ONE })], 1);
    const bar = window.eval(`overviewChips(${JSON.stringify(`${ONE}:c1`)})`);
    expect(texts(bar.querySelectorAll(".chip"))).toEqual(["Mia Musterkind", "Mia Beispiel"]);
  });

  test("the header child switch of a single school shows first name and class", () => {
    const { window } = loadApp();
    seed(window, [CHILDREN[0], Object.assign({}, CHILDREN[2], { key: `${ONE}:c3`, connection_id: ONE })], 1);
    window.eval('state.view = "timetable"; state.timetable = { lessons: [], period_times: {} };');
    const bar = window.eval('header("timetable")');
    expect(bar.querySelector(".child-switch .who").textContent).toBe("Mia");
    expect(bar.querySelector(".child-switch .cls").textContent).toBe("7b");
    expect(bar.querySelector(".child-switch .avatar").textContent).toBe("M");
  });

  test("the child sheet lists first names with the class line underneath", () => {
    const { window } = loadApp();
    seed(window, [CHILDREN[0], Object.assign({}, CHILDREN[2], { key: `${ONE}:c3`, connection_id: ONE })], 1);
    const sheet = window.eval("childSheet()");
    expect(texts(sheet.querySelectorAll(".opt-main b"))).toEqual(["Mia", "Lea"]);
    expect(sheet.querySelector(".opt-main small").textContent).toBe(window.eval('t("child.class", { name: "7b" })'));
  });

  test("absence rows name the child by first name, the absence detail by full name", () => {
    const { window } = loadApp();
    seed(window, CHILDREN);
    window.eval(`state.absence = { data: { entries: [], children: [{ id: "s1", name: "Mia Musterkind" }, { id: "s2", name: "Lea Beispiel" }], rules: {} }, connectionId: ${JSON.stringify(ONE)} };`);
    const entry = { id: 7, student_id: "s2", from_date: "2026-09-08", till_date: "2026-09-08", kind: "sick", status: "accepted" };
    expect(window.eval(`absenceRow(${JSON.stringify(entry)}).querySelector(".row-sub").textContent`)).toContain("Lea");
    expect(window.eval(`absenceRow(${JSON.stringify(entry)}).querySelector(".row-sub").textContent`)).not.toContain("Beispiel");
    expect(window.eval(`absenceChildName(${JSON.stringify(entry)}, true)`)).toBe("Lea Beispiel");
  });

  test("the letter child chip and the calendar card overline carry the first name", () => {
    const { window } = loadApp();
    seed(window, CHILDREN);
    expect(window.eval('letterChildTag({ child: "Lea Beispiel" }).textContent')).toBe("Lea");
    expect(window.eval('letterChildTag({ child: "Beispiel, Lea" }).textContent')).toBe("Lea");
    const card = window.eval(`calendarChildCard(state.children[2], null)`);
    expect(card.querySelector(".overline").textContent).toBe(window.eval('t("calendar.subscribe.forChild", { name: "Lea" })'));
  });

  test("the full name stays on the profile sheet and the letter detail meta", () => {
    const { window } = loadApp();
    seed(window, CHILDREN);
    window.eval('state.me = { forename: "Alexa", surname: "Musterkind-Langenscheidt", displayname: "Alexa Musterkind-Langenscheidt", username: "alexa" };');
    const entries = window.eval("meTechEntries()");
    expect(entries.map((entry) => entry.value)).toContain("Musterkind-Langenscheidt");
    const letter = { key: "k", letter_id: "l1", recipient_id: "r1", connection_id: ONE, title: "Trip", sender: "Anna Beispiel", published: "01.09.2026", child: "Lea Beispiel" };
    window.eval(`state.letterDetail = { letter: ${JSON.stringify(letter)}, detail: { body_html: "" }, loading: false, error: null };`);
    const meta = window.eval("letterDetailView().querySelector('.row-meta').textContent");
    expect(meta).toContain("Anna Beispiel");
  });
});
