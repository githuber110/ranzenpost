import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function single(window, connection = {}, extra = "") {
  window.eval(`
    state.config = { connections: [Object.assign({ id: ${JSON.stringify(ONE)}, setup_complete: true, phones: [], subjects: {}, teachers: {} }, ${JSON.stringify(connection)})], notify_services: [], notify_events: {} };
    state.children = [{ key: ${JSON.stringify(`${ONE}:c1`)}, child_id: "c1", connection_id: ${JSON.stringify(ONE)}, name: "Mia Example", class_name: "7b" }];
    state.childId = ${JSON.stringify(`${ONE}:c1`)};
    state.me = { forename: "Alex", username: "alex.example", email: "alex@example.invalid", is_active: true };
    ${extra}
  `);
}

function two(window, extra = "") {
  window.eval(`
    state.config = { connections: [
      { id: ${JSON.stringify(ONE)}, school_name: "School One", setup_complete: true, phones: [], subjects: {}, teachers: {} },
      { id: ${JSON.stringify(TWO)}, school_name: "School Two", setup_complete: true, phones: [], subjects: {}, teachers: {} },
    ], notify_services: [], notify_events: {} };
    state.children = [
      { key: ${JSON.stringify(`${ONE}:c1`)}, child_id: "c1", connection_id: ${JSON.stringify(ONE)}, name: "Mia Example", class_name: "7b" },
      { key: ${JSON.stringify(`${TWO}:c1`)}, child_id: "c1", connection_id: ${JSON.stringify(TWO)}, name: "Tom Example", class_name: "3a" },
    ];
    state.childId = ${JSON.stringify(`${ONE}:c1`)};
    state.schools = [
      { id: ${JSON.stringify(ONE)}, name: "School One", status: "ok", username: "parent.one", setup_complete: true },
      { id: ${JSON.stringify(TWO)}, name: "School Two", status: "ok", username: "parent.two", setup_complete: true },
    ];
    state.schoolStatus = { ${JSON.stringify(ONE)}: "ok", ${JSON.stringify(TWO)}: "ok" };
    ${extra}
  `);
}

function rowCounts(root) {
  return [...root.querySelectorAll(".settings-group")].map((group) => ({
    head: group.querySelector(".section-head .overline").textContent,
    rows: group.querySelectorAll(".setting-row, .module-row").length,
  }));
}

describe("the settings list has no group with a single row", () => {
  test("one school, two schools and the school page", () => {
    const { window } = loadApp();
    single(window);
    const lonely = (root) => rowCounts(root).filter((entry) => entry.rows === 1);
    expect(lonely(window.eval("settingsView()"))).toEqual([]);
    two(window);
    expect(lonely(window.eval("settingsView()"))).toEqual([]);
    const page = window.eval(`el("div", {}, schoolPageSections(${JSON.stringify(TWO)}))`);
    expect(lonely(page)).toEqual([]);
  });

  test("the calendar subscription has a row next to push and Home Assistant in single-school mode too", () => {
    const { window } = loadApp();
    single(window);
    window.eval('state.calendar = { data: { port: 8199, port_open: true, subscriptions: [] } }; state.view = "settings"; render();');
    const row = window.document.querySelector(".calendar-setting");
    expect(row.closest(".settings-group").querySelector(".overline").textContent).toBe(label(window, "settings.section.notifications"));
    expect(row.querySelector(".val").textContent).toBe(label(window, "schools.calendar.portOpen"));
    row.click();
    expect(window.eval("state.settingsPage")).toBe("calendar");
    expect(window.eval("state.sheet")).toBe(null);
  });
});

describe("the module switches are shared and listed once under Areas", () => {
  test("two schools: one switch block in the list, none on a school page", () => {
    const { window } = loadApp();
    two(window);
    const view = window.eval("settingsView()");
    const blocks = [...view.querySelectorAll(".modules-block")];
    expect(blocks.length).toBe(1);
    expect(blocks[0].closest(".settings-group").querySelector(".overline").textContent).toBe(label(window, "settings.section.modules"));
    expect(blocks[0].querySelector(".section-lead").textContent).toBe(label(window, "settings.modules.leadAll"));
    const page = window.eval(`el("div", {}, schoolPageSections(${JSON.stringify(TWO)}))`);
    expect(page.querySelector(".module-row")).toBeNull();
    expect(page.querySelector(".modules-recheck").classList.contains("link-btn")).toBe(true);
  });
});

describe("raw account data lives under Help as technical details", () => {
  test("no profile row in the account group; Help opens a full page with the fields", () => {
    const { window } = loadApp();
    single(window);
    window.eval('state.view = "settings"; render();');
    const doc = window.document;
    const help = [...doc.querySelectorAll(".settings-group")].find((group) => group.querySelector(".overline").textContent === label(window, "settings.section.help"));
    expect(texts(help.querySelectorAll(".setting-row .lbl"))).toEqual([label(window, "help.row"), label(window, "common.techDetails")]);
    help.querySelector(".tech-setting").click();
    expect(window.eval("state.settingsPage")).toBe("tech");
    expect(window.eval("state.sheet")).toBeNull();
    expect(doc.querySelector(".header-title").textContent).toBe(label(window, "common.techDetails"));
    const page = doc.querySelector(".tech-page");
    expect(page.querySelector(".tech-lead").textContent).toBe(label(window, "common.techDetails.text"));
    expect(page.textContent).toContain("alex.example");
    expect(page.textContent).toContain(label(window, "settings.user.tech.email"));
    doc.querySelector(".header-back").click();
    expect(window.eval("state.settingsPage")).toBe(null);
  });

  test("with two schools the page loads the data of each school into its own group", async () => {
    const { window } = loadApp();
    for (let round = 0; round < 8; round += 1) await tick();
    two(window);
    const asked = [];
    window.fetch = (url) => {
      const target = String(url);
      asked.push(target);
      const id = target.includes(TWO) ? "parent.two" : "parent.one";
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ username: id }) });
    };
    window.eval('state.view = "settings"; state.settingsPage = "tech"; render();');
    await tick();
    await tick();
    await tick();
    const groups = [...window.document.querySelectorAll(".tech-page .tech-school")];
    expect(groups.map((group) => group.dataset.school)).toEqual([ONE, TWO]);
    expect(texts(window.document.querySelectorAll(".tech-page .tech-school .overline"))).toEqual(["School One", "School Two"]);
    expect(groups[0].textContent).toContain("parent.one");
    expect(groups[1].textContent).toContain("parent.two");
    expect(asked.filter((url) => url.includes("api/me?connection=")).length).toBe(2);
  });

  test("the login row of a school page shows the user name and opens nothing", () => {
    const { window } = loadApp();
    two(window, `state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)};`);
    window.eval("render()");
    const row = window.document.querySelector(".school-page .login-row");
    expect(row.tagName).toBe("DIV");
    expect(row.querySelector(".lbl").textContent).toBe(label(window, "schools.login"));
    expect(row.querySelector(".val").textContent).toBe("parent.two");
    expect(row.querySelector(".chev")).toBeNull();
    row.click();
    expect(window.eval("state.sheet")).toBeNull();
  });
});
