import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

function seed(window, connections, children) {
  window.eval(`
    state.config = { connections: ${JSON.stringify(connections)}, language: "de", notify_services: [] };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(children[0] ? children[0].key : "")};
    state.loadedAt = {};
  `);
}

const READY = { id: ONE, school_url: "https://gym-sued.example", school_name: "School One", setup_complete: true, phones: [], period_times: {}, subjects: {}, teachers: {} };
const PENDING = { id: TWO, school_url: "https://school-two.example", school_name: "", setup_complete: false, phones: [], period_times: {}, subjects: {}, teachers: {} };
const SECOND = { ...PENDING, setup_complete: true, school_name: "School Two" };
const CHILD_ONE = { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, school: "School One", name: "Mia Example", class_name: "7b" };
const CHILD_TWO = { key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, school: "School Two", name: "Tom Example", class_name: "3a" };

describe("an abandoned add-school wizard does not count as a second school", () => {
  test("manySchools ignores a half connection and counts only ready schools", () => {
    const { window } = loadApp();
    seed(window, [READY, PENDING], [CHILD_ONE]);
    expect(window.eval("manySchools()")).toBe(false);
    seed(window, [READY, SECOND], [CHILD_ONE, CHILD_TWO]);
    expect(window.eval("manySchools()")).toBe(true);
    seed(window, [PENDING, { ...READY, setup_complete: false }], [CHILD_ONE]);
    expect(window.eval("manySchools()")).toBe(false);
  });
});

describe("the absence form is sent to the school it was opened for", () => {
  test("the payload names the school of the open absence data, not the school of the selected child", () => {
    const { window } = loadApp();
    seed(window, [READY, SECOND], [CHILD_ONE, CHILD_TWO]);
    window.eval(`
      state.absence = { data: { children: [{ id: "c1", name: "Tom Example" }], entries: [] }, connectionId: ${JSON.stringify(TWO)} };
      state.absenceForm = { type: "sick", student_id: "c1", from_date: "2126-09-01", till_date: "2126-09-01", repeat: "" };
    `);
    expect(window.eval("currentConnectionId()")).toBe(ONE);
    const payload = window.eval("absencePayload(state.absenceForm, state.absence.data.children)");
    expect(payload.connection_id).toBe(TWO);
  });

  test("without a school on the absence data the payload falls back to the current school", () => {
    const { window } = loadApp();
    seed(window, [READY, SECOND], [CHILD_ONE, CHILD_TWO]);
    window.eval(`
      state.absence = { data: { children: [{ id: "c1", name: "Mia Example" }], entries: [] } };
      state.absenceForm = { type: "sick", student_id: "c1", from_date: "2126-09-01", till_date: "2126-09-01", repeat: "" };
    `);
    const payload = window.eval("absencePayload(state.absenceForm, state.absence.data.children)");
    expect(payload.connection_id).toBe(ONE);
  });
});
