import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

const CONFIRM_TEXT =
  "Zugangsdaten und 2FA-Token werden aus dieser App gelöscht. Die App versucht außerdem, den Sicherheits-Token in IServ zu entfernen — klappt das nicht, bleibt er dort bestehen und lässt sich unter Einstellungen → Zwei-Faktor selbst löschen.";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
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
});
