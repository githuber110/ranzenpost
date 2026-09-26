import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

const CONNECTIONS = [
  { id: ONE, school_url: "https://riverside.example", school_name: "Riverside Primary", short_name: "Riverside", setup_complete: true, phones: [], period_times: {}, subjects: {}, teachers: {} },
  { id: TWO, school_url: "https://hillview.example", school_name: "Hillview School", short_name: "Hillview", setup_complete: true, phones: [], period_times: {}, subjects: {}, teachers: {} },
];

const MIA = { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, school: "Riverside Primary", name: "Mia Example", class_name: "3b" };
const FORM_CHILD = { id: "11111111-1111-4111-8111-111111111111", name: "Lena Example" };
const TEACHER = { value: "userid:22222222-3333-4444-5555-666666666666", label: "Fr. Zweig", extra: "" };

function seed(window, { schools = 2, children = [MIA], teacherSchools = [ONE, TWO], extra = "" } = {}) {
  const connections = CONNECTIONS.slice(0, schools);
  window.eval(`
    state.config = { connections: ${JSON.stringify(connections)}, language: "de", notify_services: [] };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(children[0] ? children[0].key : null)};
    state.schools = ${JSON.stringify(connections.map((entry) => ({ id: entry.id, name: entry.school_name, status: "ok", setup_complete: true, children: 0 })))};
    state.schoolStatus = {};
    state.loadedAt = {};
    state.messengerRooms = { rooms: [], can_write_to_teacher: true, teacher_schools: ${JSON.stringify(teacherSchools)}, self_user_ids: {} };
    ${extra}
  `);
}

function stubFetch(window, answer) {
  const calls = [];
  window.fetch = (url, options) => {
    const path = String(url).slice(String(url).indexOf("api/"));
    const body = options && options.body ? JSON.parse(options.body) : null;
    calls.push([path, body]);
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(answer(path, body)) });
  };
  return calls;
}

const settle = async () => {
  for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

function label(window, key) {
  return window.eval(`t(${JSON.stringify(key)})`);
}

function sheetOptions(window) {
  const scrim = window.eval("state.sheet ? state.sheet() : null");
  return scrim ? [...scrim.querySelectorAll(".school-choice .opt")] : [];
}

function answerMessenger(path) {
  if (path.startsWith("api/messenger/room/teacher/children")) return { children: [FORM_CHILD], allowed: true };
  if (path.startsWith("api/messenger/teachers")) return { teachers: [TEACHER], allowed: true };
  if (path.startsWith("api/messenger/room/teacher")) return { ok: true, message_key: "api.messenger.room.ok", room_id: "!new:hillview.example" };
  if (path.startsWith("api/messenger/rooms")) return { rooms: [], teacher_schools: [ONE, TWO], can_write_to_teacher: true };
  return {};
}

describe("the current school is never guessed between two schools", () => {
  test("without any child two schools leave the current school open", () => {
    const { window } = loadApp();
    seed(window, { children: [] });
    expect(window.eval("currentConnectionId()")).toBe("");
  });

  test("the school of the listed child counts even when no child is chosen yet", () => {
    const { window } = loadApp();
    seed(window, { children: [Object.assign({}, MIA, { key: `${TWO}:c7`, connection_id: TWO })], extra: "state.childId = null;" });
    expect(window.eval("currentConnectionId()")).toBe(TWO);
  });

  test("a single school stays implicit", () => {
    const { window } = loadApp();
    seed(window, { schools: 1, children: [] });
    expect(window.eval("currentConnectionId()")).toBe(ONE);
  });
});

describe("writing to a teacher asks for the school when two schools allow it", () => {
  test("the entry opens a school sheet with one row per school and no second primary button", () => {
    const { window } = loadApp();
    seed(window);
    stubFetch(window, answerMessenger);
    window.eval("startTeacherRoom()");
    const options = sheetOptions(window);
    expect(options.map((node) => node.querySelector("b").textContent)).toEqual(["Riverside Primary", "Hillview School"]);
    const scrim = window.eval("state.sheet()");
    expect(scrim.querySelectorAll(".btn:not(.ghost):not(.sheet-close)").length).toBe(0);
    expect(scrim.querySelector(".sheet-title, h2, h3").textContent).toBe(label(window, "schools.choose.title"));
    expect(window.eval("state.teacherRoom")).toBe(null);
  });

  test("search, children and the new room all go to the chosen second school", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = stubFetch(window, answerMessenger);
    window.eval("startTeacherRoom()");
    sheetOptions(window)[1].click();
    await settle();
    expect(window.eval("state.teacherRoom.connectionId")).toBe(TWO);
    window.eval("queueTeacherSearch('Zwe')");
    window.eval("window.clearTimeout(teacherSearchTimer); runTeacherSearch('Zwe')");
    await settle();
    window.eval(`chooseTeacher(${JSON.stringify(TEACHER)})`);
    window.eval(`state.teacherRoom.childIds = [${JSON.stringify(FORM_CHILD.id)}]`);
    await window.eval("submitTeacherRoom()");
    await settle();
    const paths = calls.map(([path]) => path);
    expect(paths).toContain(`api/messenger/room/teacher/children?connection=${TWO}`);
    expect(paths).toContain(`api/messenger/teachers?query=Zwe&connection=${TWO}`);
    const created = calls.find(([path]) => path === "api/messenger/room/teacher");
    expect(created[1].connection_id).toBe(TWO);
    expect(paths.filter((path) => path.startsWith("api/messenger") && path.includes(`connection=${ONE}`))).toEqual([]);
  });

  test("the review names the chosen school when two schools are set up", async () => {
    const { window } = loadApp();
    seed(window);
    stubFetch(window, answerMessenger);
    window.eval(`openTeacherRoom(${JSON.stringify(TWO)})`);
    await settle();
    window.eval(`chooseTeacher(${JSON.stringify(TEACHER)})`);
    expect(window.eval("teacherRoomReviewBody().textContent")).toContain("Hillview School");
  });

  test("a single allowing school starts the flow directly for that school", async () => {
    const { window } = loadApp();
    seed(window, { teacherSchools: [TWO] });
    const calls = stubFetch(window, answerMessenger);
    window.eval("startTeacherRoom()");
    await settle();
    expect(sheetOptions(window)).toEqual([]);
    expect(window.eval("state.teacherRoom.connectionId")).toBe(TWO);
    expect(calls.map(([path]) => path)).toContain(`api/messenger/room/teacher/children?connection=${TWO}`);
  });
});

describe("absences name their school", () => {
  test("without a child of either school the absence view offers one button to choose the school", async () => {
    const { window } = loadApp();
    seed(window, { children: [], extra: "state.view = 'absence';" });
    const calls = stubFetch(window, () => ({ entries: [], children: [], phones: [] }));
    const view = window.eval("absenceView()");
    expect(view.querySelectorAll(".btn").length).toBe(1);
    expect(view.textContent).toContain(label(window, "absence.school.text"));
    view.querySelector(".btn").click();
    sheetOptions(window)[1].click();
    window.eval("absenceView()");
    await settle();
    expect(calls.map(([path]) => path)).toContain(`api/absences?connection=${TWO}`);
    expect(calls.some(([path]) => path.startsWith("api/absences") && !path.includes(TWO))).toBe(false);
  });

  test("withdrawing sends the school of the loaded overview, not the first school", async () => {
    const { window } = loadApp();
    seed(window, { children: [], extra: `state.absenceSchool = ${JSON.stringify(TWO)};` });
    const calls = stubFetch(window, () => ({ ok: true }));
    window.eval(`
      state.absence = { data: { children: [{ id: 1, name: "Lena" }], rules: {} }, connectionId: ${JSON.stringify(TWO)} };
      openAbsenceSheet({ id: 7, kind: "leave", student_id: 1, label: "Beurlaubungsantrag", deletable: true });
    `);
    window.eval("state.sheet().querySelector('.sheet .btn.destructive').click()");
    await settle();
    window.eval("state.sheet().querySelector('.sheet .btn.destructive').click()");
    await settle();
    const withdrawn = calls.find(([path]) => path === "api/absences/delete");
    expect(withdrawn[1].connection_id).toBe(TWO);
  });
});

describe("the school row tells a refused child list apart", () => {
  test("a school whose account lists no children says so instead of zero profiles", () => {
    const { window } = loadApp();
    seed(window, { children: [MIA] });
    window.eval(`state.schools = state.schools.map((row) => Object.assign({}, row, { children_state: row.id === ${JSON.stringify(TWO)} ? "refused" : "listed" }))`);
    const rows = window.eval("connections().map(schoolRow)");
    expect(rows[1].querySelector(".val").textContent).toBe(label(window, "schools.children.refused"));
    expect(rows[0].querySelector(".val").textContent).not.toBe(label(window, "schools.children.refused"));
  });

  test("an unreadable child list is shown as a warning", () => {
    const { window } = loadApp();
    seed(window, { children: [MIA] });
    window.eval(`state.schools = state.schools.map((row) => Object.assign({}, row, { children_state: row.id === ${JSON.stringify(TWO)} ? "unreadable" : "listed" }))`);
    const row = window.eval("connections().map(schoolRow)")[1];
    expect(row.querySelector(".val.warn").textContent).toBe(label(window, "schools.children.unreadable"));
  });
});

describe("the greeting names its school", () => {
  test("the account name is asked from an explicit school", () => {
    const { window } = loadApp();
    seed(window, { children: [] });
    const calls = stubFetch(window, () => ({}));
    window.eval("loadRest()");
    expect(calls.map(([path]) => path)).toContain(`api/me?connection=${ONE}`);
  });
});

describe("checking the modules again names its schools", () => {
  const MERGED = { modules: { timetable: true, letters: true, pinboard: true, absences: true, conferences: true, messenger: true }, unsupported: [], unknown: [] };
  const SECOND_ONLY = { modules: { timetable: false, letters: true, pinboard: true, absences: true, conferences: true, messenger: true }, unsupported: [], unknown: [] };

  test("the school page checks its own school and keeps the merged modules of both schools", async () => {
    const { window } = loadApp();
    seed(window, { extra: `state.settingsSchoolId = ${JSON.stringify(TWO)};` });
    const calls = stubFetch(window, (path) => (path === "api/modules" ? MERGED : { ok: true, message_key: "api.modules.rechecked", modules: SECOND_ONLY }));
    await window.eval("recheckModules()");
    await settle();
    expect(calls.filter(([path]) => path === "api/modules/recheck").map(([, body]) => body.connection_id)).toEqual([TWO]);
    expect(window.eval("state.modules.available.timetable")).toBe(true);
  });

  test("without an open school page every school is checked, never only the first", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = stubFetch(window, (path) => (path === "api/modules" ? MERGED : { ok: true, message_key: "api.modules.rechecked", modules: SECOND_ONLY }));
    await window.eval("recheckModules()");
    await settle();
    expect(calls.filter(([path]) => path === "api/modules/recheck").map(([, body]) => body.connection_id)).toEqual([ONE, TWO]);
  });
});

describe("the sick note pdf names its school", () => {
  test("the pdf of the second school is asked from the second school", async () => {
    const { window } = loadApp();
    seed(window, { children: [] });
    window.URL.createObjectURL = () => "blob:mock-url";
    window.URL.revokeObjectURL = () => {};
    const requested = [];
    window.fetch = (url) => {
      requested.push(String(url));
      return Promise.resolve({ ok: true, headers: { get: () => "" }, blob: () => Promise.resolve(new window.Blob(["x"])) });
    };
    window.eval(`state.absence = { data: { children: [], rules: {} }, connectionId: ${JSON.stringify(TWO)} }`);
    const block = window.eval("sickNotePdfBlock({ id: 42, kind: 'sick' })");
    block.querySelector("button").click();
    await settle();
    expect(requested).toContain(`http://localhost/api/absences/sick-note-pdf?id=42&connection=${TWO}`);
  });
});

describe("checking every school reports every school", () => {
  const MERGED = { modules: { timetable: true, letters: true, pinboard: true, absences: true, conferences: true, messenger: true }, unsupported: [], unknown: [] };

  function answering(window, perSchool) {
    const calls = [];
    window.fetch = (url, options) => {
      const path = String(url).slice(String(url).indexOf("api/"));
      const body = options && options.body ? JSON.parse(options.body) : null;
      calls.push([path, body]);
      if (path === "api/modules") return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(MERGED) });
      const answer = perSchool[body.connection_id];
      if (answer instanceof Error) return Promise.reject(answer);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
    };
    return calls;
  }

  const OK = { ok: true, message_key: "api.modules.rechecked", modules: MERGED };
  const TOO_SOON = { ok: false, message_key: "api.modules.tooSoon", error: "rate_limited", modules: MERGED };

  test("a school that throws does not skip the next school and is named in the outcome", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = answering(window, { [ONE]: new Error("offline"), [TWO]: OK });
    await window.eval("recheckModules()");
    await settle();
    expect(calls.filter(([path]) => path === "api/modules/recheck").map(([, body]) => body.connection_id)).toEqual([ONE, TWO]);
    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.toast.message")).toContain("Riverside");
    expect(window.eval("state.toast.message")).not.toContain("Hillview");
  });

  test("a refusal of the first school is not hidden behind the success of the second", async () => {
    const { window } = loadApp();
    seed(window);
    answering(window, { [ONE]: TOO_SOON, [TWO]: OK });
    await window.eval("recheckModules()");
    await settle();
    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.toast.message")).toContain("Riverside");
  });

  test("when every school answers, the outcome is good", async () => {
    const { window } = loadApp();
    seed(window);
    answering(window, { [ONE]: OK, [TWO]: OK });
    await window.eval("recheckModules()");
    await settle();
    expect(window.eval("state.toast.kind")).toBe("good");
  });
});
