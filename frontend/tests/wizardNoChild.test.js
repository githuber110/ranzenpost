import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

describe("[P137] wizard: child step with 0 children", () => {
  test("shows the explanation screen instead of hanging, and finishes setup", async () => {
    const { window, document } = loadApp();
    let skipCalled = false;
    window.fetch = (path) => {
      const url = String(path);
      if (url.includes("api/wizard/skip-child")) {
        skipCalled = true;
        return jsonResponse({ step: "done" });
      }
      if (url.includes("api/children")) return jsonResponse([]);
      if (url.includes("api/config")) return jsonResponse({});
      if (url.includes("api/wizard")) return jsonResponse({ step: "child", has_2fa: false });
      return Promise.reject(new Error("unexpected fetch " + path));
    };

    const app = document.getElementById("app");
    let done = false;
    window.renderWizard(app, () => { done = true; });
    await flush();
    await flush();

    expect(app.textContent).toContain("Deinem Konto ist kein Kind zugeordnet — bitte wende dich an die Schule.");

    const finishButton = [...app.querySelectorAll("button")].find((b) => b.textContent === "Einrichtung abschließen");
    expect(finishButton).toBeTruthy();
    finishButton.click();
    await flush();
    await flush();

    expect(skipCalled).toBe(true);

    const skipPhones = [...app.querySelectorAll("button")].find((b) => b.textContent === "Überspringen");
    expect(skipPhones).toBeTruthy();
    skipPhones.click();

    expect(done).toBe(true);
  });
});
