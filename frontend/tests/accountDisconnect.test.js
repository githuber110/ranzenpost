import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

const CONFIRM_TEXT =
  "Zugangsdaten und Sicherheits-Token werden aus dieser App gelöscht. Die App entfernt auch ihren Sicherheits-Token in IServ. Klappt das nicht, kannst du es erneut versuchen.";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

async function until(check) {
  for (let round = 0; round < 50 && !check(); round += 1) await flush();
}

function openSheetNode(window) {
  return window.eval("state.sheet ? state.sheet() : null");
}

function renderSettings(window) {
  window.eval(`
    state.config = {};
    state.view = "settings";
    render();
  `);
}

function disconnectRow(app) {
  return [...app.querySelectorAll("button.setting-row")].find((b) => b.textContent.includes("Verbindung trennen"));
}

describe("account disconnect", () => {
  test("Verbindung trennen exists in Konto and opens an in-app confirmation, not window.confirm", () => {
    const { window, document } = loadApp();
    const confirmSpy = vi.fn();
    window.confirm = confirmSpy;
    renderSettings(window);

    const app = document.getElementById("app");
    const row = disconnectRow(app);
    expect(row).toBeTruthy();
    row.click();

    expect(confirmSpy).not.toHaveBeenCalled();
    const sheet = app.querySelector(".sheet");
    expect(sheet).toBeTruthy();
    expect(sheet.textContent).toContain(CONFIRM_TEXT);
  });

  test("Abbrechen closes the confirmation without calling the disconnect endpoint", async () => {
    const { window, document } = loadApp();
    let called = false;
    window.fetch = (path) => {
      if (String(path).includes("api/account/disconnect")) {
        called = true;
        return jsonResponse({});
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    renderSettings(window);

    const app = document.getElementById("app");
    disconnectRow(app).click();
    const sheet = app.querySelector(".sheet");
    sheet.querySelector(".btn.ghost").click();
    await flush();

    expect(app.querySelector(".sheet")).toBeNull();
    expect(called).toBe(false);
  });

  test("Verbindung trennen sends the disconnect request", async () => {
    const { window, document } = loadApp();
    let called = false;
    window.fetch = (path) => {
      if (String(path).includes("api/account/disconnect")) {
        called = true;
        return jsonResponse({ attempted: true, removed: true, message: "2FA-Token in IServ entfernt." });
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    renderSettings(window);

    const app = document.getElementById("app");
    disconnectRow(app).click();
    const sheet = app.querySelector(".sheet");
    sheet.querySelector(".btn.destructive").click();
    await flush();

    expect(called).toBe(true);
  });

  test("a token that stays in IServ keeps the connection and offers a retry and disconnecting anyway in the app", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    const answers = [
      { attempted: true, removed: false, disconnected: false, retryable: true, message_key: "api.disconnect.failed", message: "nicht entfernt" },
      { attempted: true, removed: false, disconnected: false, retryable: true, message_key: "api.disconnect.failed", message: "nicht entfernt" },
      { attempted: true, removed: false, disconnected: true, message_key: "api.disconnect.forced", message: "getrennt" },
    ];
    window.fetch = (path, options) => {
      if (String(path).includes("api/account/disconnect")) {
        bodies.push(JSON.parse(options.body));
        return jsonResponse(answers.shift());
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    window.boot = () => {};
    renderSettings(window);

    const app = document.getElementById("app");
    disconnectRow(app).click();
    app.querySelector(".sheet .btn.destructive").click();
    await until(() => openSheetNode(window) && openSheetNode(window).querySelector(".token-retry"));
    let sheet = openSheetNode(window);
    expect(sheet.textContent).toContain("nicht entfernt");
    expect(sheet.querySelectorAll(".btn:not(.ghost)").length).toBe(1);
    expect(sheet.querySelector("a")).toBeNull();
    sheet.querySelector(".token-retry").click();
    await until(() => bodies.length === 2 && openSheetNode(window) && openSheetNode(window).querySelector(".token-force"));
    sheet = openSheetNode(window);
    sheet.querySelector(".token-force").click();
    await until(() => bodies.length === 3 && !openSheetNode(window));

    expect(bodies.map((body) => body.force === true)).toEqual([false, false, true]);
    expect(openSheetNode(window)).toBeNull();
  });

  test("closing the retry question leaves the school connected and sends nothing more", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    window.fetch = (path, options) => {
      if (String(path).includes("api/account/disconnect")) {
        bodies.push(JSON.parse(options.body));
        return jsonResponse({ attempted: true, removed: false, disconnected: false, retryable: true, message_key: "api.disconnect.failed", message: "nicht entfernt" });
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    let booted = false;
    window.boot = () => { booted = true; };
    renderSettings(window);

    const app = document.getElementById("app");
    disconnectRow(app).click();
    app.querySelector(".sheet .btn.destructive").click();
    await until(() => openSheetNode(window) && openSheetNode(window).querySelector(".token-retry"));
    window.eval("state.onSheetClose()");
    await until(() => !openSheetNode(window));
    for (let round = 0; round < 5; round += 1) await flush();

    expect(bodies.length).toBe(1);
    expect(booted).toBe(false);
  });
});

describe("disconnect waits for the school and lets the user pick the token", () => {
  function disconnectFetch(window, answers, bodies, waits, config) {
    window.AbortSignal = { timeout: (ms) => ({ ms }) };
    window.fetch = (path, options) => {
      if (String(path).includes("api/account/disconnect")) {
        bodies.push(JSON.parse(options.body));
        waits.push(options.signal && options.signal.ms);
        const next = answers.shift();
        return next instanceof Error ? Promise.reject(next) : jsonResponse(next);
      }
      if (String(path).includes("api/config")) return jsonResponse(config || { connections: [] });
      return Promise.reject(new Error("unexpected fetch " + path));
    };
  }

  async function start(window, document) {
    renderSettings(window);
    const app = document.getElementById("app");
    disconnectRow(app).click();
    app.querySelector(".sheet .btn.destructive").click();
    return app;
  }

  test("the request may wait as long as a letter answer and shows that it runs", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    const waits = [];
    disconnectFetch(window, [new Promise(() => {})], bodies, waits);
    window.boot = () => {};
    await start(window, document);
    await until(() => bodies.length === 1);
    expect(waits[0]).toBeGreaterThanOrEqual(90000);
    expect(openSheetNode(window).querySelector(".disconnect-progress")).not.toBeNull();
  });

  test("a timed out request reads the state again instead of saying it failed", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    disconnectFetch(window, [new Error("timeout")], bodies, [], { connections: [{ id: "a1b2c3d4" }] });
    window.boot = () => {};
    window.eval("state.config = { connections: [{ id: 'a1b2c3d4' }] }; state.settingsSchoolId = null;");
    await start(window, document);
    await until(() => openSheetNode(window) && openSheetNode(window).querySelector(".token-retry"));
    expect(openSheetNode(window).textContent).toContain(window.eval('t("settings.disconnect.unclear")'));
  });

  test("a timed out request whose school is gone counts as disconnected", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    disconnectFetch(window, [new Error("timeout")], bodies, [], { connections: [] });
    let booted = false;
    window.boot = () => { booted = true; };
    const timers = window.setTimeout;
    window.setTimeout = (callback, ms) => (ms === 900 ? callback() : timers(callback, ms));
    await start(window, document);
    await until(() => booted);
    expect(booted).toBe(true);
    expect(window.eval("state.toast && state.toast.message")).toBe(window.eval('t("settings.disconnect.done")'));
  });

  test("tokens to choose from are listed and the chosen one is sent, without a retry that cannot work", async () => {
    const { window, document } = loadApp();
    const bodies = [];
    const tokens = [{ id: "uuid-1", name: "ISERV-Connector", created: "" }, { id: "uuid-2", name: "ISERV-Connector", created: "01.09.2026" }];
    disconnectFetch(window, [
      { attempted: false, removed: false, disconnected: false, retryable: false, message_key: "api.disconnect.choose", tokens },
      { attempted: true, removed: true, disconnected: true, message_key: "api.disconnect.removed" },
    ], bodies, []);
    window.boot = () => {};
    await start(window, document);
    await until(() => openSheetNode(window) && openSheetNode(window).querySelector(".token-choice"));
    const sheet = openSheetNode(window);
    expect(sheet.querySelectorAll(".token-choice").length).toBe(2);
    expect(sheet.querySelector(".token-retry")).toBeNull();
    sheet.querySelectorAll(".token-choice")[1].click();
    await until(() => bodies.length === 2);
    expect(bodies[1].token_id).toBe("uuid-2");
  });
});
