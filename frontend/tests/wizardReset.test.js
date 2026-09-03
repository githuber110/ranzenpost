import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

describe("wizard reset confirmation", () => {
  test("clicking Neu starten shows an in-app panel instead of window.confirm", async () => {
    const { window, document } = loadApp();
    const confirmSpy = vi.fn();
    window.confirm = confirmSpy;
    window.fetch = (path) => {
      if (String(path).includes("api/wizard")) return jsonResponse({ step: "url" });
      return Promise.reject(new Error("unexpected fetch " + path));
    };

    const app = document.getElementById("app");
    await flush();
    window.renderWizard(app, () => {});
    await flush();

    const reset = [...app.querySelectorAll("button")].find((b) => b.textContent === "Neu starten");
    expect(reset).toBeTruthy();
    reset.click();

    expect(confirmSpy).not.toHaveBeenCalled();
    const panel = app.querySelector(".wz-confirm");
    expect(panel).toBeTruthy();
    expect(panel.textContent).toContain("Einrichtung neu starten");
    expect(panel.querySelector(".btn.destructive").textContent).toBe("Neu starten");
    expect(panel.querySelector(".btn.ghost").textContent).toBe("Abbrechen");
  });

  test("Abbrechen closes the panel without resetting", async () => {
    const { window, document } = loadApp();
    let resetCalled = false;
    window.fetch = (path) => {
      if (String(path).includes("api/wizard/reset")) {
        resetCalled = true;
        return jsonResponse({ step: "url" });
      }
      if (String(path).includes("api/wizard")) return jsonResponse({ step: "url" });
      return Promise.reject(new Error("unexpected fetch " + path));
    };

    const app = document.getElementById("app");
    await flush();
    window.renderWizard(app, () => {});
    await flush();

    [...app.querySelectorAll("button")].find((b) => b.textContent === "Neu starten").click();
    const panel = app.querySelector(".wz-confirm");
    panel.querySelector(".btn.ghost").click();

    expect(app.querySelector(".wz-confirm")).toBeNull();
    expect(resetCalled).toBe(false);
  });

  test("Neu starten in the panel triggers the reset request", async () => {
    const { window, document } = loadApp();
    let resetCalled = false;
    window.fetch = (path) => {
      if (String(path).includes("api/wizard/reset")) {
        resetCalled = true;
        return jsonResponse({ step: "url" });
      }
      if (String(path).includes("api/wizard")) return jsonResponse({ step: "url" });
      return Promise.reject(new Error("unexpected fetch " + path));
    };

    const app = document.getElementById("app");
    await flush();
    window.renderWizard(app, () => {});
    await flush();

    [...app.querySelectorAll("button")].find((b) => b.textContent === "Neu starten").click();
    const panel = app.querySelector(".wz-confirm");
    panel.querySelector(".btn.destructive").click();
    await flush();

    expect(resetCalled).toBe(true);
  });
});
