import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

async function prepare(window, { many = false } = {}) {
  for (let round = 0; round < 6; round += 1) await tick();
  window.clearTimeout(window.eval("bootWatchdog"));
  const connections = [
    { id: ONE, school_name: "School One", setup_complete: true, phones: [], subjects: { D: { label: "Deutsch", color: "" } }, teachers: { BEH: { label: "" } } },
  ];
  const children = [{ key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, name: "Mia Example", class_name: "7b" }];
  if (many) {
    connections.push({ id: TWO, school_name: "School Two", setup_complete: true, phones: [], subjects: { M: { label: "Mathe", color: "" } }, teachers: {} });
    children.push({ key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, name: "Tom Example", class_name: "3a" });
  }
  window.eval(`
    state.detached = false;
    state.config = { connections: ${JSON.stringify(connections)}, notify_services: [], notify_events: {} };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(`${ONE}:c1`)};
    state.schools = ${JSON.stringify(connections.map((entry) => ({ id: entry.id, name: entry.school_name, status: "ok", setup_complete: true })))};
    state.haStatus = { data: { connected: true }, error: false };
    state.calendar = { data: { port: 8100, port_open: true, subscriptions: [] }, error: false };
  `);
  const posts = [];
  window.fetch = (url, options) => {
    const target = String(url);
    if (options && options.method === "POST") {
      posts.push({ url: target, body: JSON.parse(options.body) });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    }
    if (target.includes("api/config")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(window.eval("state.config")) });
    }
    return Promise.reject(new Error(`unexpected request ${target}`));
  };
  return posts;
}

function type(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input"));
}

function button(document, text) {
  return [...document.querySelectorAll("button")].find((node) => node.textContent === text);
}

describe("subjects and teachers are a full settings page", () => {
  test("the settings row opens the page with a back button, no sheet", async () => {
    const { window, document } = loadApp();
    await prepare(window);
    window.eval('state.view = "settings"; render();');
    document.querySelector(".names-setting").click();

    expect(window.eval("state.settingsPage")).toBe("names");
    expect(window.eval("state.sheet")).toBe(null);
    expect(document.querySelector(".scrim")).toBeNull();
    expect(document.querySelector(".header-title").textContent).toBe(label(window, "settings.names.sheet"));
    expect(document.querySelectorAll(".names-page .names-block").length).toBe(2);
    expect(document.querySelector(".names-page .names-save")).not.toBeNull();
    document.querySelector(".header-back").click();
    expect(window.eval("state.settingsPage")).toBe(null);
    expect(document.querySelector(".names-setting")).not.toBeNull();
  });

  test("opened from a school page it edits that school and goes back to it", async () => {
    const { window, document } = loadApp();
    const posts = await prepare(window, { many: true });
    window.eval(`state.view = "settings"; state.settingsSchoolId = ${JSON.stringify(TWO)}; render();`);
    document.querySelector(".names-setting").click();

    expect(window.eval("state.settingsPage")).toBe("names");
    const input = document.querySelector(".names-page .subject-name input");
    expect(input.value).toBe("Mathe");
    type(window, input, "Mathematik");
    document.querySelector(".names-save").click();
    for (let round = 0; round < 6; round += 1) await tick();

    expect(posts.map((entry) => entry.url)).toEqual([expect.stringContaining(`api/connections/${TWO}`)]);
    expect(posts[0].body.subjects.M.label).toBe("Mathematik");
    expect(window.eval("state.settingsPage")).toBe(null);
    expect(window.eval("state.settingsSchoolId")).toBe(TWO);
    expect(window.eval("state.pageForm")).toBe(null);
  });

  test("leaving with unsaved changes asks first; keep holds the draft, discard drops it", async () => {
    const { window, document } = loadApp();
    const posts = await prepare(window);
    window.eval('state.view = "settings"; render(); openNamesPage();');
    type(window, document.querySelector(".names-page .subject-name input"), "Deutsch LK");
    expect(window.eval("isPageFormDirty()")).toBe(true);

    document.querySelector(".header-back").click();
    expect(document.querySelector(".sheet-title").textContent).toBe(label(window, "sheet.discard.title"));
    button(document, label(window, "common.cancel")).click();
    await tick();
    expect(window.eval("state.settingsPage")).toBe("names");
    expect(window.eval("state.pageForm.subjects.D.label")).toBe("Deutsch LK");
    expect(document.querySelector(".names-page .subject-name input").value).toBe("Deutsch LK");

    document.querySelector(".header-back").click();
    button(document, label(window, "sheet.discard.confirm")).click();
    await tick();
    expect(window.eval("state.settingsPage")).toBe(null);
    expect(window.eval("state.pageForm")).toBe(null);
    expect(posts).toEqual([]);
  });

  test("switching the area with unsaved changes asks too, a clean page just leaves", async () => {
    const { window, document } = loadApp();
    await prepare(window);
    window.eval('state.view = "settings"; render(); openNamesPage();');
    type(window, document.querySelector(".names-page .subject-name input"), "Deutsch LK");
    window.eval('setView("overview");');
    expect(window.eval("state.view")).toBe("settings");
    expect(document.querySelector(".sheet-title").textContent).toBe(label(window, "sheet.discard.title"));
    button(document, label(window, "sheet.discard.confirm")).click();
    await tick();
    expect(window.eval("state.view")).toBe("overview");

    window.eval('state.view = "settings"; state.settingsPage = null; render(); openNamesPage();');
    window.eval('setView("overview");');
    expect(window.eval("state.view")).toBe("overview");
    expect(window.eval("state.sheet")).toBe(null);
  });

  test("a new visit starts from the stored names, not from an old draft", async () => {
    const { window, document } = loadApp();
    await prepare(window);
    window.eval('state.view = "settings"; render(); openNamesPage();');
    type(window, document.querySelector(".names-page .subject-name input"), "Deutsch LK");
    document.querySelector(".header-back").click();
    button(document, label(window, "sheet.discard.confirm")).click();
    await tick();
    window.eval("openNamesPage();");
    expect(document.querySelector(".names-page .subject-name input").value).toBe("Deutsch");
  });
});
