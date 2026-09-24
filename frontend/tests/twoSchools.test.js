import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const FRONTEND = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(FRONTEND, "styles.css"), "utf8");

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

const CONNECTIONS = [
  { id: ONE, school_url: "https://gym-sued.example", school_name: "Gymnasium Süd", setup_complete: true, phones: [{ label: "Office", number: "0511" }], period_times: { 1: "08:00" }, subjects: {}, teachers: {} },
  { id: TWO, school_url: "https://iserv.gs-nord.example", school_name: "Grundschule Nord", short_name: "GS Nord", setup_complete: true, phones: [], period_times: { 1: "07:45", 2: "08:35" }, subjects: {}, teachers: {} },
];

const CHILDREN = [
  { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, school: "Gymnasium Süd", name: "Mia Example", class_name: "7b" },
  { key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, school: "Grundschule Nord", name: "Tom Example", class_name: "3a" },
  { key: `${TWO}:c3`, child_id: "c3", connection_id: TWO, school: "Grundschule Nord", name: "Lea Example", class_name: "1c" },
];

const SCHOOLS = [
  { id: ONE, name: "Gymnasium Süd", short_name: "gym-sued", status: "ok", username: "parent.one", setup_complete: true, children: 1 },
  { id: TWO, name: "Grundschule Nord", short_name: "GS Nord", status: "ok", username: "parent.two", setup_complete: true, children: 2 },
];

function useWidth(window, width) {
  window.innerWidth = width;
  window.matchMedia = (query) => {
    const min = /\(min-width:\s*(\d+)px\)/.exec(query);
    return {
      matches: min ? width >= Number(min[1]) : /orientation: portrait/.test(query),
      media: query,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    };
  };
}

function seed(window, { schools = 2, extra = "" } = {}) {
  const connections = CONNECTIONS.slice(0, schools);
  const children = CHILDREN.filter((child) => connections.some((entry) => entry.id === child.connection_id));
  window.eval(`
    state.config = { connections: ${JSON.stringify(connections)}, language: "de", notify_services: [] };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(children[0].key)};
    state.schools = ${JSON.stringify(SCHOOLS.slice(0, schools))};
    state.schoolStatus = { ${JSON.stringify(ONE)}: "ok", ${JSON.stringify(TWO)}: "ok" };
    state.loadedAt = {};
    ${extra}
  `);
}

function state(window) {
  return window.eval("state");
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

function stubFetch(window, answer) {
  const calls = [];
  window.fetch = (url, options) => {
    const path = String(url).slice(String(url).indexOf("api/"));
    const body = options && options.body ? JSON.parse(options.body) : null;
    calls.push([path, body]);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(answer(path, body)) });
  };
  return calls;
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function settle(window) {
  await flush();
  await flush();
  await flush();
  window.eval("state.detached = false;");
}

describe("short names tell two schools apart", () => {
  test("the short name defaults to the host without its top-level label and yields to the stored one", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('hostShortName("https://gym-sued.example")')).toBe("gym-sued");
    expect(window.eval('hostShortName("https://iserv.gs-nord.example:8443/iserv/")')).toBe("iserv.gs-nord");
    expect(window.eval('hostShortName("localhost")')).toBe("localhost");
    expect(window.eval('hostShortName("")')).toBe("");
    expect(window.eval(`schoolShortName(${JSON.stringify(ONE)})`)).toBe("gym-sued");
    expect(window.eval(`schoolShortName(${JSON.stringify(TWO)})`)).toBe("GS Nord");
    expect(window.eval(`schoolFullName(${JSON.stringify(TWO)})`)).toBe("Grundschule Nord");
    expect(window.eval('schoolShortName("nope")')).toBe("");
  });

  test("manySchools is false with one connection and true from two", () => {
    const { window } = loadApp();
    seed(window, { schools: 1 });
    expect(window.eval("manySchools()")).toBe(false);
    seed(window, { schools: 2 });
    expect(window.eval("manySchools()")).toBe(true);
  });
});

describe("school chips on rows, only from two schools", () => {
  const LETTER = { key: `${TWO}:l1:r1`, letter_id: "l1", recipient_id: "r1", connection_id: TWO, school: "Grundschule Nord", title: "Trip", child: "Lea Example", recipients: "1c", unread: true };
  const TILE = { id: 5, key: `${TWO}:5`, connection_id: TWO, school: "Grundschule Nord", title: "Fair", text: "Text", folder_title: "Board", column_title: "News", unread: true };
  const ROOM = { room_id: "!r:x", connection_id: TWO, school: "Grundschule Nord", name: "Class 1c", last_message: "Hi", last_message_at: 1788336000000, unread_count: 1 };

  test("a letter row carries the school chip first, grey, before class and child", () => {
    const { window } = loadApp();
    seed(window);
    const row = window.eval(`letterRow(${JSON.stringify(LETTER)})`);
    const tags = row.querySelectorAll(".row-tags .tag");
    expect(tags[0].className).toBe("tag school");
    expect(texts(tags)).toEqual(["GS Nord", "1c", "Lea"]);
  });

  test("a post row keeps its source badge after the school chip and a room row gets one too", () => {
    const { window } = loadApp();
    seed(window);
    const post = window.eval(`postRow(${JSON.stringify(TILE)}, false, "")`);
    expect(texts(post.querySelectorAll(".row-tags .tag"))).toEqual(["GS Nord", "Board", "News"]);
    const room = window.eval(`messengerRoomRow(${JSON.stringify(ROOM)})`);
    expect(texts(room.querySelectorAll(".row-tags .tag"))).toEqual(["GS Nord"]);
  });

  test("with one school no row carries a school chip", () => {
    const { window } = loadApp();
    seed(window, { schools: 1 });
    const letter = Object.assign({}, LETTER, { connection_id: ONE });
    expect(window.eval(`letterRow(${JSON.stringify(letter)})`).querySelector(".tag.school")).toBeNull();
    expect(window.eval(`postRow(${JSON.stringify(Object.assign({}, TILE, { connection_id: ONE }))}, false, "")`).querySelector(".tag.school")).toBeNull();
    expect(window.eval(`messengerRoomRow(${JSON.stringify(Object.assign({}, ROOM, { connection_id: ONE }))})`).querySelector(".row-tags")).toBeNull();
  });

  test("the school chip is neutral grey in the stylesheet", () => {
    expect(styles).toMatch(/\.tag\.school\s*{[^}]*background:\s*var\(--surface-2\)/);
  });
});

describe("the filter chip row appears once entries of two schools exist", () => {
  const LETTERS = [
    { key: `${ONE}:a:1`, letter_id: "a", recipient_id: "1", connection_id: ONE, title: "Sports", unread: true },
    { key: `${TWO}:b:1`, letter_id: "b", recipient_id: "1", connection_id: TWO, title: "Fair", unread: false },
  ];

  test("no bar when every entry comes from one school, a bar with All plus one chip per school otherwise", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval(`schoolFilterBar(${JSON.stringify([LETTERS[0]])}, "", () => {})`)).toBeNull();
    const bar = window.eval(`schoolFilterBar(${JSON.stringify(LETTERS)}, "", () => {})`);
    const chips = bar.querySelectorAll(".chip");
    expect(texts(chips)).toEqual([label(window, "schools.filter.all"), "gym-sued", "GS Nord"]);
    expect(chips[0].getAttribute("aria-pressed")).toBe("true");
    const active = window.eval(`schoolFilterBar(${JSON.stringify(LETTERS)}, ${JSON.stringify(TWO)}, () => {})`);
    expect(texts(active.querySelectorAll('.chip[aria-pressed="true"]'))).toEqual(["GS Nord"]);
  });

  test("filtering keeps only the chosen school's entries and a stale choice falls back to all", () => {
    const { window } = loadApp();
    seed(window);
    const kept = window.eval(`filterBySchool(${JSON.stringify(LETTERS)}, ${JSON.stringify(TWO)})`);
    expect(kept.map((entry) => entry.letter_id)).toEqual(["b"]);
    const all = window.eval(`filterBySchool(${JSON.stringify(LETTERS)}, "gone")`);
    expect(all.length).toBe(2);
  });

  test("the letters view shows the bar and filters its rows through the state", () => {
    const { window } = loadApp();
    seed(window, { extra: `state.letters = { tab: "current", letters: ${JSON.stringify(LETTERS)} }; state.postSchoolFilter = ${JSON.stringify(TWO)};` });
    const view = window.eval("lettersView(null)");
    expect(view.querySelector(".chipbar.school-filter")).not.toBeNull();
    expect(texts(view.querySelectorAll(".rows .row .row-title"))).toEqual(["Fair"]);
  });

  test("the pinboard and the chat views carry the bar as well", () => {
    const { window } = loadApp();
    const feed = [
      { id: 1, key: `${ONE}:1`, connection_id: ONE, title: "One", text: "t", unread: true },
      { id: 2, key: `${TWO}:2`, connection_id: TWO, title: "Two", text: "t", unread: true },
    ];
    const rooms = [
      { room_id: "!a:x", connection_id: ONE, name: "A", last_message_at: 1, unread_count: 0 },
      { room_id: "!b:x", connection_id: TWO, name: "B", last_message_at: 2, unread_count: 0 },
    ];
    seed(window, { extra: `state.pinboard = { folders: [], feed: ${JSON.stringify(feed)} }; state.messengerRooms = { rooms: ${JSON.stringify(rooms)}, can_write_to_teacher: false }; state.messengerSchoolFilter = ${JSON.stringify(ONE)};` });
    const pinboard = window.eval("pinboardView(null)");
    expect(pinboard.querySelector(".chipbar.school-filter")).not.toBeNull();
    expect(texts(pinboard.querySelectorAll(".rows .row .row-title"))).toEqual(["Two", "One"]);
    const messenger = window.eval("messengerView()");
    expect(messenger.querySelector(".chipbar.school-filter")).not.toBeNull();
    expect(texts(messenger.querySelectorAll(".rows .row .row-title"))).toEqual(["A"]);
  });
});

describe("pills name the child by first name and class, the school only on a shared first name", () => {
  test("one-line pills in the order of the children, in the timetable and the absence view", () => {
    const { window } = loadApp();
    seed(window);
    const bar = window.eval(`childPills(${JSON.stringify(`${TWO}:c1`)}, () => {})`);
    const pills = bar.querySelectorAll(".chip");
    expect(pills.length).toBe(3);
    expect(bar.querySelector(".chip-child")).toBeNull();
    expect(texts(pills)).toEqual(["Mia · 7b", "Tom · 3a", "Lea · 1c"]);
    expect(bar.querySelector(".chip .cls")).toBeNull();
    expect([...pills].map((pill) => pill.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);
  });

  test("two children with the same first name at different schools get the short name after the class, the others not", () => {
    const { window } = loadApp();
    seed(window, { extra: `state.children.push({ key: "b2c3d4e5:c7", connection_id: "b2c3d4e5", school: "Grundschule Nord", name: "Mia Other", class_name: "2a" });` });
    const bar = window.eval("childPills(state.childId, () => {})");
    expect(texts(bar.querySelectorAll(".chip"))).toEqual(["Mia · 7b · gym-sued", "Tom · 3a", "Lea · 1c", "Mia · 2a · GS Nord"]);
    expect(window.eval(`childPillLabel(state.children[0])`)).toBe(window.eval('t("child.labelWithSchool", { label: t("child.nameWithClass", { name: "Mia", class: "7b" }), school: "gym-sued" })'));
  });

  test("the two-line pill variant is gone from the stylesheet", () => {
    expect(styles).not.toMatch(/\.chip\.chip-child/);
  });

  test("the timetable view shows the pill row instead of the header switch from two schools, not with one", () => {
    const { window } = loadApp();
    seed(window, { extra: 'state.view = "timetable"; state.timetable = { lessons: [], period_times: {} };' });
    expect(window.eval('timetableView().querySelector(".chipbar.child-pills")')).not.toBeNull();
    expect(window.eval('header("timetable").querySelector(".child-switch")')).toBeNull();
    expect(window.eval('header("timetable").querySelector(".header-title").textContent')).toBe(label(window, "timetable.title"));
    seed(window, { schools: 1, extra: 'state.children.push({ key: "a1b2c3d4:c9", connection_id: "a1b2c3d4", name: "Ben", class_name: "5a" }); state.timetable = { lessons: [], period_times: {} };' });
    expect(window.eval('timetableView().querySelector(".chipbar.child-pills")')).toBeNull();
    expect(window.eval('header("timetable").querySelector(".child-switch")')).not.toBeNull();
  });

  test("switching the child of another school drops the absences so they reload for that school", async () => {
    const { window } = loadApp();
    seed(window, { extra: `state.view = "absence"; state.absence = { data: { entries: [], children: [] }, connectionId: ${JSON.stringify(ONE)} }; state.timetable = { lessons: [] };` });
    await settle(window);
    const calls = stubFetch(window, (path) => (path.startsWith("api/absences") ? { entries: [], children: [], phones: [] } : { lessons: [], connections: state(window).config.connections }));
    window.eval(`selectChild(${JSON.stringify(`${TWO}:c1`)})`);
    expect(window.eval("state.childId")).toBe(`${TWO}:c1`);
    expect(calls.some(([path]) => path === `api/absences?connection=${TWO}`)).toBe(true);
    window.eval(`state.absence = { data: { entries: [] }, connectionId: ${JSON.stringify(ONE)} }`);
    expect(window.eval("absenceView().querySelector('.spinner, .spin, .loading')")).not.toBeNull();
  });

  test("the desk child head shows first name and class on one line, the school only on a shared first name, and four children share the width", () => {
    const { window } = loadApp();
    useWidth(window, 1440);
    seed(window, { extra: 'state.children.push({ key: "b2c3d4e5:c4", connection_id: "b2c3d4e5", name: "Mia Other", class_name: "2a" }); state.view = "timetable"; state.timetable = { lessons: [], period_times: {} }; state.overviewWeeks = {};' });
    window.eval("render()");
    const root = window.document.getElementById("app");
    const heads = root.querySelectorAll(".tt-child-head");
    expect(heads.length).toBe(4);
    expect([...heads].map((head) => head.querySelector(".who").textContent)).toEqual(["Mia", "Tom", "Lea", "Mia"]);
    expect([...heads].map((head) => head.querySelector(".cls").textContent)).toEqual(["7b · gym-sued", "3a", "1c", "2a · GS Nord"]);
    expect(root.querySelector(".tt-child-head .school")).toBeNull();
    expect(root.querySelector(".tt-multi").classList.contains("scrolls")).toBe(false);
    window.eval('state.children.push({ key: "b2c3d4e5:c5", connection_id: "b2c3d4e5", name: "Eva", class_name: "4b" }); render();');
    expect(root.querySelector(".tt-multi").classList.contains("scrolls")).toBe(true);
    expect(styles).toMatch(/\.tt-multi\.scrolls\s*{[^}]*grid-auto-columns:\s*calc\(\(100% - 3 \* var\(--s-6\)\) \/ 4\)/);
  });

  test("the timetable grid ends at the last period of the shown week", () => {
    const { window } = loadApp();
    seed(window);
    const grid = window.eval(`timetableGrid({ lessons: [
      { day_of_week: 1, period: 1, subject_code: "D" },
      { day_of_week: 3, period: 3, subject_code: "M" },
    ], period_times: {} }, ${JSON.stringify(`${ONE}:c1`)})`);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(3);
  });
});

describe("the settings with one school stay as they were, plus one row", () => {
  test("one school: the account group carries the add-school row before disconnect and no schools block", () => {
    const { window } = loadApp();
    seed(window, { schools: 1 });
    const view = window.eval("settingsView()");
    expect(view.querySelector(".schools-block")).toBeNull();
    const account = [...view.querySelectorAll(".settings-group")].find((group) => group.querySelector(".overline").textContent === label(window, "settings.section.account"));
    expect(texts(account.querySelectorAll(".setting-row .lbl"))).toEqual([
      label(window, "settings.password"),
      label(window, "schools.add"),
      label(window, "settings.disconnect"),
    ]);
  });

  test("two schools: the groups follow the single-school order, the schools block takes the school place, adding a school is an account row", () => {
    const { window } = loadApp();
    seed(window, { extra: `state.schoolStatus[${JSON.stringify(TWO)}] = "auth_failed";` });
    const view = window.eval("settingsView()");
    const heads = texts(view.querySelectorAll(".settings-group .section-head .overline"));
    expect(heads).toEqual([
      label(window, "settings.section.display"),
      label(window, "settings.section.notifications"),
      label(window, "schools.section"),
      label(window, "settings.section.modules"),
      label(window, "settings.section.account"),
      label(window, "settings.section.help"),
    ]);
    const rows = view.querySelectorAll(".schools-block .setting-row.school-row");
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector(".lbl").textContent).toBe("Gymnasium Süd");
    expect(rows[0].querySelector(".val").textContent).toBe(window.eval('tCount("schools.children", 1)'));
    expect(rows[0].querySelector(".school-dot").classList.contains("ok")).toBe(true);
    expect(rows[1].querySelector(".val").textContent).toBe(label(window, "connection.status.authFailed"));
    expect(rows[1].querySelector(".val").classList.contains("warn")).toBe(true);
    expect(rows[1].querySelector(".school-dot").classList.contains("warn")).toBe(true);
    expect(view.querySelectorAll(".schools-block .btn").length).toBe(0);
    expect(view.querySelector(".btn.add-school")).toBeNull();
    expect(view.querySelector(".setting-row.add-school")).not.toBeNull();
    const account = view.querySelectorAll(".settings-group")[4];
    expect(texts(account.querySelectorAll(".setting-row .lbl"))).toEqual([label(window, "schools.add"), label(window, "schools.reset")]);
    expect(account.querySelector(".setting-row.destructive .lbl").textContent).toBe(label(window, "schools.reset"));
  });

  test("the calendar group names the port state once the subscriptions are loaded", () => {
    const { window } = loadApp();
    seed(window, { extra: "state.calendar = { data: { port: 8199, port_open: true, subscriptions: [] } };" });
    const view = window.eval("settingsView()");
    const row = [...view.querySelectorAll(".setting-row")].find((node) => node.querySelector(".lbl").textContent === label(window, "schools.calendar.access"));
    expect(row.querySelector(".val").textContent).toBe(label(window, "schools.calendar.portOpen", { port: "8199" }));
  });
});

describe("the school page", () => {
  test("tapping a school row opens the full page with its three groups and the rows act on that school", () => {
    const { window } = loadApp();
    seed(window, { extra: 'state.view = "settings";' });
    window.eval("render()");
    const root = window.document.getElementById("app");
    root.querySelectorAll(".school-row")[1].click();
    expect(window.eval("state.settingsSchoolId")).toBe(TWO);
    expect(window.eval("editingConnectionId()")).toBe(TWO);
    expect(root.querySelector(".header-title").textContent).toBe("Grundschule Nord");
    expect(root.querySelector(".header-back")).not.toBeNull();
    const heads = texts(root.querySelectorAll(".school-page .settings-group .section-head .overline"));
    expect(heads).toEqual([
      label(window, "settings.section.school"),
      label(window, "settings.section.modules"),
      label(window, "settings.section.account"),
    ]);
    const rows = texts(root.querySelectorAll(".school-page .setting-row .lbl"));
    expect(rows).toEqual([
      label(window, "schools.shortName"),
      label(window, "holidays.settings.title"),
      label(window, "settings.periods.sheet"),
      label(window, "settings.names"),
      label(window, "settings.phones"),
      label(window, "schools.login"),
      label(window, "settings.password"),
      label(window, "schools.disconnect"),
    ]);
    const values = texts(root.querySelectorAll(".school-page .setting-row .val"));
    expect(values).toContain("parent.two");
    expect(values).toContain("GS Nord");
    expect(values).toContain(window.eval('tCount("settings.periods.count", 2)'));
    expect(root.querySelector(".school-page .setting-row.destructive .lbl").textContent).toBe(label(window, "schools.disconnect"));
    expect(root.querySelector(".school-page .modules-recheck")).not.toBeNull();
    expect(root.querySelector(".school-page .module-row")).toBeNull();
    root.querySelector(".header-back").click();
    expect(window.eval("state.settingsSchoolId")).toBeNull();
    expect(root.querySelector(".header-title").textContent).toBe(label(window, "settings.title"));
  });

  test("a school that needs a login shows the reconnect row and the sheet posts the repair with that school's id", async () => {
    const { window } = loadApp();
    seed(window, { extra: `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)}; state.schoolStatus[${JSON.stringify(TWO)}] = "auth_failed";` });
    window.eval("render()");
    const root = window.document.getElementById("app");
    const row = [...root.querySelectorAll(".school-page .setting-row")].find((node) => node.querySelector(".lbl").textContent === label(window, "connection.reconnect"));
    expect(row).toBeTruthy();
    await settle(window);
    const calls = stubFetch(window, (path) => (path === "api/health"
      ? { connections: [{ id: ONE, status: "ok" }, { id: TWO, status: "ok" }] }
      : { ok: true, lessons: [], connections: state(window).config.connections, entries: [] }));
    row.click();
    const sheet = root.querySelector(".sheet");
    expect(sheet).not.toBeNull();
    sheet.querySelector('input[type="password"]').value = "secret-pass";
    sheet.querySelector('input[type="password"]').dispatchEvent(new window.Event("input"));
    sheet.querySelector(".sheet-foot .btn, .btn[type=submit]").click();
    await flush();
    await flush();
    expect(calls.filter(([path]) => path === "api/password/repair")).toEqual([["api/password/repair", { password: "secret-pass", connection_id: TWO }]]);
    expect(calls.some(([path]) => path === "api/health")).toBe(true);
    expect(window.eval(`state.schoolStatus[${JSON.stringify(TWO)}]`)).toBe("ok");
  });

  test("a school whose code IServ refused offers the new setup of that school and never the password sheet", async () => {
    const { window } = loadApp();
    seed(window, {
      extra: `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)}; state.schoolStatus[${JSON.stringify(TWO)}] = "auth_failed"; state.schoolReasons = { ${JSON.stringify(TWO)}: "code_step_failed" };`,
    });
    window.eval("render()");
    const root = window.document.getElementById("app");
    const labels = texts(root.querySelectorAll(".school-page .setting-row .lbl"));
    expect(labels).not.toContain(label(window, "connection.reconnect"));
    const row = [...root.querySelectorAll(".school-page .setting-row")].find((node) => node.querySelector(".lbl").textContent === label(window, "account.reconnect.reset"));
    expect(row).toBeTruthy();
    await settle(window);
    const calls = stubFetch(window, (path) => (path === "api/wizard/reset" ? { step: "url" } : { ok: true }));
    row.click();
    const sheet = root.querySelector(".sheet");
    expect(sheet).not.toBeNull();
    expect(sheet.querySelector('input[type="password"]')).toBeNull();
    expect(sheet.textContent).toContain(label(window, "api.login.twofactor"));
    expect(sheet.textContent).toContain(label(window, "account.reconnect.resetNote"));
    const main = [...sheet.querySelectorAll("button.btn")].filter((button) => !button.classList.contains("ghost"));
    expect(main).toHaveLength(1);
    expect(main[0].textContent).toBe(label(window, "account.reconnect.reset"));
    main[0].click();
    await flush();
    await flush();
    expect(calls.filter(([path]) => path === "api/wizard/reset")).toEqual([["api/wizard/reset", { connection_id: TWO }]]);
    expect(calls.some(([path]) => path === "api/password/repair")).toBe(false);
  });

  test("the short name sheet saves through the school's connection route", async () => {
    const { window } = loadApp();
    seed(window, { extra: `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)};` });
    window.eval(`
      state.persisted = [];
      persistTo = async (path, payload) => { state.persisted.push([path, payload]); return { ok: true }; };
      openSheet(shortNameSheet);
    `);
    const root = window.document.getElementById("app");
    const input = root.querySelector(".sheet input.inp");
    expect(input.value).toBe("GS Nord");
    input.value = "  Nord  ";
    input.dispatchEvent(new window.Event("input"));
    root.querySelector(".sheet .btn").click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("state.persisted")).toEqual([[`api/connections/${TWO}`, { short_name: "Nord" }]]);
    expect(window.eval(`schoolShortName(${JSON.stringify(TWO)})`)).toBe("Nord");
  });

  test("at desk the school page lives in the detail pane and the open row is marked", () => {
    const { window } = loadApp();
    useWidth(window, 1440);
    seed(window, { extra: `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(ONE)};` });
    window.eval("render()");
    const root = window.document.getElementById("app");
    expect(root.getAttribute("data-shell")).toBe("rail-pane");
    expect(root.querySelector(".pane-detail .school-page")).not.toBeNull();
    expect(root.querySelector(".pane-detail .pane-title").textContent).toBe("Gymnasium Süd");
    expect(root.querySelector(".screen .school-page")).toBeNull();
    expect(root.querySelectorAll(".school-row")[0].classList.contains("open")).toBe(true);
    expect(root.querySelectorAll(".school-row")[1].classList.contains("open")).toBe(false);
    seed(window, { schools: 1, extra: 'state.view = "settings"; state.settingsSchoolId = null;' });
    window.eval("render()");
    expect(root.getAttribute("data-shell")).toBe("rail-pane");
    expect(root.querySelector(".pane-detail .pane-empty")).not.toBeNull();
  });

  test("disconnecting one school calls its own route and keeps the app running when another remains", async () => {
    const { window } = loadApp();
    seed(window, { extra: `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)};` });
    const remaining = [CONNECTIONS[0]];
    await settle(window);
    const calls = stubFetch(window, (path) => {
      if (path === "api/config") return { connections: remaining };
      if (path === "api/children") return [CHILDREN[0]];
      if (path === "api/health") return { connections: [{ id: ONE, status: "ok" }] };
      return { ok: true, removed: true, lessons: [], entries: [], letters: [], feed: [], folders: [], rooms: [], items: [] };
    });
    const run = window.eval(`disconnectSchool(${JSON.stringify(TWO)})`);
    await flush();
    window.document.querySelector(".sheet-confirm .btn.destructive, .sheet .btn.destructive").click();
    await run;
    expect(calls.map(([path]) => path)).toContain(`api/connections/${TWO}/disconnect`);
    expect(window.eval("state.settingsSchoolId")).toBeNull();
    expect(window.eval("state.config.connections.length")).toBe(1);
    expect(window.eval("state.detached")).toBe(false);
    expect(window.document.querySelector("#app .screen")).not.toBeNull();
  });
});

describe("adding another school runs the wizard as a page and cancels back to the settings", () => {
  test("start posts wizard/start and mounts the wizard with a cancel action, cancel posts wizard/cancel and boots", async () => {
    const { window } = loadApp();
    seed(window, { extra: 'state.view = "settings";' });
    await settle(window);
    const calls = stubFetch(window, (path) => {
      if (path === "api/wizard/start" || path === "api/wizard") return { step: "url" };
      if (path === "api/wizard/cancel") return { step: "done" };
      if (path === "api/health") return { configured: true, connection: "ok", language: "de", connections: [], modules: {} };
      if (path === "api/config") return { connections: CONNECTIONS };
      if (path === "api/children") return CHILDREN;
      return { lessons: [], entries: [], letters: [], feed: [], folders: [], rooms: [], items: [], services: [] };
    });
    window.eval(`renderWizard = (container, onDone, options) => { state.wizardOptions = options; container.replaceChildren(el("div", { class: "wz" })); };`);
    await window.eval("startAddSchool()");
    expect(calls.map(([path]) => path)).toEqual(["api/wizard/start"]);
    expect(window.eval("state.detached")).toBe(true);
    expect(window.eval("typeof state.wizardOptions.onCancel")).toBe("function");
    expect(window.document.querySelector("#app .wz")).not.toBeNull();
    await window.eval("state.wizardOptions.onCancel()");
    expect(calls.map(([path]) => path).slice(0, 3)).toEqual(["api/wizard/start", "api/wizard/cancel", "api/health"]);
    expect(window.eval("state.detached")).toBe(false);
    expect(window.eval("state.view")).toBe("settings");
    expect(window.document.querySelector("#app .screen")).not.toBeNull();
  });

  test("the wizard offers Cancel instead of Restart when it adds a school", async () => {
    const { window } = loadApp();
    let cancelled = 0;
    await settle(window);
    stubFetch(window, () => ({ step: "url" }));
    const container = window.document.createElement("div");
    window.document.body.append(container);
    window.renderWizard(container, () => {}, { onCancel: () => { cancelled += 1; } });
    return new Promise((resolve) => setTimeout(resolve, 0)).then(() => {
      const nav = container.querySelector(".wz-nav.reset");
      expect(nav).not.toBeNull();
      expect(nav.textContent).toBe(label(window, "common.cancel"));
      nav.click();
      expect(cancelled).toBe(1);
    });
  });
});

describe("one failing school does not take the whole app down", () => {
  test("an auth failure of one school is noted on that school and the app keeps rendering", () => {
    const { window } = loadApp();
    seed(window, { extra: 'state.view = "timetable";' });
    window.eval(`
      state.rendered = 0;
      renderReconnect = () => { state.reconnectShown = true; };
      rerender = () => { state.rendered += 1; };
    `);
    const handled = window.eval(`handleApiFailure(apiError("auth_failed", {}), ${JSON.stringify(TWO)})`);
    expect(handled).toBe(false);
    expect(window.eval(`state.schoolStatus[${JSON.stringify(TWO)}]`)).toBe("auth_failed");
    expect(window.eval("!!state.reconnectShown")).toBe(false);
    expect(window.eval("state.detached")).toBe(false);
  });

  test("with one school the auth failure still routes to the reconnect page", () => {
    const { window } = loadApp();
    seed(window, { schools: 1 });
    window.eval("renderReconnect = () => { state.reconnectShown = true; };");
    expect(window.eval('handleApiFailure(apiError("auth_failed", {}))')).toBe(true);
    expect(window.eval("state.reconnectShown")).toBe(true);
  });

  test("the banner names the failing school on views that include it and leads to its page", () => {
    const { window } = loadApp();
    seed(window, { extra: `state.schoolStatus[${JSON.stringify(TWO)}] = "auth_failed"; state.view = "timetable"; state.timetable = { lessons: [], period_times: {} };` });
    expect(window.eval(`schoolIssueBanner([${JSON.stringify(ONE)}])`)).toBeNull();
    const banner = window.eval(`schoolIssueBanner([${JSON.stringify(ONE)}, ${JSON.stringify(TWO)}])`);
    expect(banner.textContent).toContain(label(window, "connection.banner.authFailed", { school: "Grundschule Nord" }));
    expect(window.eval("timetableView().querySelector('.school-banner')")).toBeNull();
    window.eval(`state.childId = ${JSON.stringify(`${TWO}:c1`)};`);
    expect(window.eval("timetableView().querySelector('.school-banner')")).not.toBeNull();
    window.eval("render()");
    const root = window.document.getElementById("app");
    root.querySelector(".school-banner .btn").click();
    expect(window.eval("state.view")).toBe("settings");
    expect(window.eval("state.settingsSchoolId")).toBe(TWO);
    expect(window.eval("state.settingsReturn")).toBe("timetable");
  });

  test("a school whose sign-in opened no session says so and not that a login is needed", () => {
    const { window } = loadApp();
    seed(window);
    window.eval(`applySchoolStatus([{ id: ${JSON.stringify(ONE)}, status: "ok" }, { id: ${JSON.stringify(TWO)}, status: "auth_failed", reason: "session_not_opened" }])`);
    const banner = window.eval(`schoolIssueBanner([${JSON.stringify(ONE)}, ${JSON.stringify(TWO)}])`);
    expect(banner.textContent).toContain(label(window, "connection.banner.session", { school: "Grundschule Nord" }));
    expect(banner.textContent).not.toContain(label(window, "connection.banner.authFailed", { school: "Grundschule Nord" }));
    expect(window.eval(`schoolStatusLabel(${JSON.stringify(TWO)})`)).toBe(label(window, "connection.status.session"));
    window.eval(`applySchoolStatus([{ id: ${JSON.stringify(TWO)}, status: "auth_failed", reason: "bad_credentials" }])`);
    expect(window.eval(`schoolStatusLabel(${JSON.stringify(TWO)})`)).toBe(label(window, "connection.status.authFailed"));
  });

  test("when every school fails to sign in the reconnect page names the reason of the first one", async () => {
    const { window } = loadApp();
    seed(window);
    const failing = SCHOOLS.map((entry) => ({ ...entry, status: "auth_failed", reason: "session_not_opened" }));
    stubFetch(window, (path) => (path.startsWith("api/health") ? { connections: failing } : {}));
    window.eval("renderReconnect = (root, account, id, reason) => { state.reconnectReason = reason; };");
    window.eval(`noteSchoolFailure("", "auth_failed")`);
    await settle(window);
    expect(window.eval("state.reconnectReason")).toBe("session_not_opened");
  });

  test("with mixed reasons the reconnect page goes to the school that needs a new password", async () => {
    const { window } = loadApp();
    seed(window);
    const failing = [
      { ...SCHOOLS[0], status: "auth_failed", reason: "session_not_opened" },
      { ...SCHOOLS[1], status: "auth_failed", reason: "bad_credentials" },
    ];
    stubFetch(window, (path) => (path.startsWith("api/health") ? { connections: failing } : {}));
    window.eval("renderReconnect = (root, account, id, reason) => { state.reconnectTo = [id, reason]; };");
    window.eval(`noteSchoolFailure("", "auth_failed")`);
    await settle(window);
    expect(window.eval("state.reconnectTo")).toEqual([TWO, "bad_credentials"]);
  });

  test("with mixed reasons a password problem comes before a refused code and a refused code before a missing session", async () => {
    for (const [first, second, wanted] of [
      ["code_step_failed", "bad_credentials", [TWO, "bad_credentials"]],
      ["session_not_opened", "code_step_failed", [TWO, "code_step_failed"]],
      ["code_step_failed", "session_not_opened", [ONE, "code_step_failed"]],
      ["locked", "code_step_failed", [ONE, "locked"]],
    ]) {
      const { window } = loadApp();
      seed(window);
      const failing = [
        { ...SCHOOLS[0], status: "auth_failed", reason: first },
        { ...SCHOOLS[1], status: "auth_failed", reason: second },
      ];
      stubFetch(window, (path) => (path.startsWith("api/health") ? { connections: failing } : {}));
      window.eval("renderReconnect = (root, account, id, reason) => { state.reconnectTo = [id, reason]; };");
      window.eval(`noteSchoolFailure("", "auth_failed")`);
      await settle(window);
      expect(window.eval("state.reconnectTo")).toEqual(wanted);
    }
  });

  test("a retry answer replaces the reason the school had before", () => {
    const { window } = loadApp();
    seed(window);
    window.eval(`applySchoolStatus([{ id: ${JSON.stringify(TWO)}, status: "auth_failed", reason: "session_not_opened" }])`);
    window.eval(`state.schools = [{ id: ${JSON.stringify(TWO)}, status: "auth_failed", reason: "session_not_opened" }]`);
    window.eval(`applyRetryAnswer(${JSON.stringify(TWO)}, { ok: true, status: "auth_failed", reason: "bad_credentials" })`);
    expect(window.eval(`schoolReason(${JSON.stringify(TWO)})`)).toBe("bad_credentials");
    expect(window.eval(`schoolStatusLabel(${JSON.stringify(TWO)})`)).toBe(label(window, "connection.status.authFailed"));
    window.eval(`applyRetryAnswer(${JSON.stringify(TWO)}, { ok: true, status: "ok" })`);
    expect(window.eval(`schoolReason(${JSON.stringify(TWO)})`)).toBe("");
  });

  test("health at boot seeds the per-school status", () => {
    const { window } = loadApp();
    seed(window);
    window.eval(`applySchoolStatus([{ id: ${JSON.stringify(ONE)}, status: "ok" }, { id: ${JSON.stringify(TWO)}, status: "network" }])`);
    expect(window.eval(`schoolStatus(${JSON.stringify(TWO)})`)).toBe("network");
    expect(window.eval("troubledSchools().map((entry) => entry.id)")).toEqual([TWO]);
  });
});

describe("the module switches are global, so they live once in the list of every school", () => {
  test("two schools: the settings list carries the switches with the every-school sentence, the school page only names what the school offers", () => {
    const { window } = loadApp();
    seed(window, { extra: 'state.view = "settings"; state.schoolModules = { [' + JSON.stringify(TWO) + ']: applyModules({ modules: { timetable: true, letters: true, pinboard: false, absences: false, conferences: false, messenger: false } }) };' });
    window.eval("render()");
    const root = window.document.getElementById("app");
    const block = root.querySelector(".screen .modules-block");
    expect(block.querySelector(".section-lead").textContent).toBe(label(window, "settings.modules.leadAll"));
    expect(block.querySelectorAll(".module-row .switch").length).toBeGreaterThan(0);
    expect(block.querySelector(".modules-recheck")).toBeNull();
    root.querySelectorAll(".school-row")[1].click();
    const page = root.querySelector(".school-page");
    expect(page.querySelector(".module-row")).toBeNull();
    expect(page.querySelector(".switch")).toBeNull();
    const names = [label(window, "settings.modules.name.timetable"), label(window, "settings.modules.name.letters")].join(", ");
    expect(page.querySelector(".modules-offered").textContent).toBe(label(window, "settings.modules.offered", { names }));
    expect(page.querySelector(".modules-recheck")).not.toBeNull();
  });

  test("one school: the list keeps the plain sentence and the recheck button", () => {
    const { window } = loadApp();
    seed(window, { schools: 1 });
    const block = window.eval("settingsView()").querySelector(".modules-block");
    expect(block.querySelector(".section-lead").textContent).toBe(label(window, "settings.modules.lead"));
    expect(block.querySelector(".modules-recheck")).not.toBeNull();
  });
});

describe("settings on a desk keep the list and open pages beside it", () => {
  function desk(schools, width = 1440) {
    const { window } = loadApp();
    useWidth(window, width);
    seed(window, { schools, extra: 'state.view = "settings"; state.settingsSchoolId = null;' });
    window.eval("render()");
    return { window, root: window.document.getElementById("app") };
  }

  test("one school: a page opens in the pane, the list stays and marks its row, closing empties the pane", () => {
    const { window, root } = desk(1);
    expect(root.getAttribute("data-shell")).toBe("rail-pane");
    expect(root.querySelector(".pane-detail .pane-empty").textContent).toBe(label(window, "settings.pane.empty"));
    root.querySelector(".screen .layout-setting").click();
    expect(root.querySelector(".pane-detail .pane-title").textContent).toBe(label(window, "settings.layout.title"));
    expect(root.querySelector(".pane-detail .app-layout-page")).not.toBeNull();
    expect(root.querySelector(".screen .app-layout-page")).toBeNull();
    expect(root.querySelector(".screen .layout-setting").classList.contains("open")).toBe(true);
    expect(root.querySelector(".screen .header-title").textContent).toBe(label(window, "settings.title"));
    root.querySelector(".pane-detail .pane-close").click();
    expect(state(window).settingsPage).toBeNull();
    expect(root.querySelector(".pane-detail .pane-empty")).not.toBeNull();
    expect(root.querySelector(".screen .layout-setting").classList.contains("open")).toBe(false);
  });

  test("the help page and the technical details open in the pane as well", () => {
    const { window, root } = desk(1);
    root.querySelector(".screen .help-setting").click();
    expect(root.querySelector(".pane-detail .help-page")).not.toBeNull();
    expect(root.querySelector(".pane-detail .pane-title").textContent).toBe(label(window, "help.title"));
    expect(root.querySelector(".screen .help-setting").classList.contains("open")).toBe(true);
    root.querySelector(".screen .tech-setting").click();
    expect(state(window).helpPage).toBe(false);
    expect(root.querySelector(".pane-detail .pane-title").textContent).toBe(label(window, "common.techDetails"));
    expect(root.querySelector(".screen .tech-setting").classList.contains("open")).toBe(true);
  });

  test("the lesson times page keeps its own list and editor layout", () => {
    const { root } = desk(1);
    root.querySelector(".screen .periods-setting").click();
    expect(root.querySelector(".screen .periods-page")).not.toBeNull();
    expect(root.querySelector(".screen .header-back")).not.toBeNull();
    expect(root.querySelector(".pane-detail .periods-page")).toBeNull();
  });

  test("below the desk width a page still replaces the list", () => {
    const { root } = desk(1, 1100);
    expect(root.getAttribute("data-shell")).toBe("rail");
    root.querySelector(".screen .layout-setting").click();
    expect(root.querySelector(".pane-detail")).toBeNull();
    expect(root.querySelector(".screen .app-layout-page")).not.toBeNull();
    expect(root.querySelector(".screen .header-back")).not.toBeNull();
  });

  test("two schools: a page opened from the school page returns to it when closed", () => {
    const { window, root } = desk(2);
    root.querySelectorAll(".school-row")[0].click();
    root.querySelector(".pane-detail .names-setting").click();
    expect(root.querySelector(".pane-detail .pane-title").textContent).toBe(label(window, "settings.names.sheet"));
    expect(root.querySelector(".screen .school-row")).not.toBeNull();
    root.querySelector(".pane-detail .pane-close").click();
    expect(state(window).settingsSchoolId).toBe(ONE);
    expect(root.querySelector(".pane-detail .school-page")).not.toBeNull();
    window.eval("openCoursesPage(state.children[0].key)");
    expect(root.querySelector(".pane-detail .courses-page")).not.toBeNull();
    expect(root.querySelector(".screen .school-row")).not.toBeNull();
    root.querySelector(".pane-detail .pane-close").click();
    expect(root.querySelector(".pane-detail .school-page")).not.toBeNull();
  });
});
