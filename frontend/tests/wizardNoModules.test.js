import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function registry(available) {
  const modules = {};
  for (const name of ["timetable", "letters", "pinboard", "absences", "conferences", "messenger"]) modules[name] = available.includes(name);
  return { modules, unknown: [], checked_at: 10, iserv_version: "3.9" };
}

async function bootChildStep(app, window, available) {
  let skipCalled = false;
  window.fetch = (path) => {
    const url = String(path);
    if (url.includes("api/wizard/skip-child")) {
      skipCalled = true;
      return jsonResponse({ step: "done" });
    }
    if (url.includes("api/children")) return jsonResponse([]);
    if (url.includes("api/modules")) return jsonResponse(registry(available));
    if (url.includes("api/config")) return jsonResponse({});
    if (url.includes("api/wizard")) return jsonResponse({ step: "child", has_2fa: false });
    return Promise.reject(new Error("unexpected fetch " + path));
  };
  window.renderWizard(app, () => {});
  for (let round = 0; round < 4; round += 1) await flush();
  return () => skipCalled;
}

function label(window, key) {
  return window.eval(`t(${JSON.stringify(key)})`);
}

describe("the wizard child step without a child source", () => {
  test("letters without a timetable: calm text, no error, setup can finish", async () => {
    const { window, document } = loadApp();
    const app = document.getElementById("app");
    const skipped = await bootChildStep(app, window, ["letters", "pinboard"]);
    expect(app.querySelector(".wz-error")).toBeNull();
    expect(app.textContent).toContain(label(window, "wizard.child.none.modules"));
    expect(app.textContent).not.toContain(label(window, "wizard.child.none.text"));
    const finish = [...app.querySelectorAll("button")].find((b) => b.textContent === label(window, "wizard.child.none.finish"));
    expect(finish).toBeTruthy();
    finish.click();
    await flush();
    await flush();
    expect(skipped()).toBe(true);
  });

  test("no module at all: the empty-state text, no error, setup can finish", async () => {
    const { window, document } = loadApp();
    const app = document.getElementById("app");
    const skipped = await bootChildStep(app, window, []);
    expect(app.querySelector(".wz-error")).toBeNull();
    expect(app.textContent).toContain(label(window, "modules.empty.text"));
    const finish = [...app.querySelectorAll("button")].find((b) => b.textContent === label(window, "wizard.child.none.finish"));
    finish.click();
    await flush();
    await flush();
    expect(skipped()).toBe(true);
  });

  test("a timetable school without children keeps the school-facing text", async () => {
    const { window, document } = loadApp();
    const app = document.getElementById("app");
    await bootChildStep(app, window, ["timetable", "letters"]);
    expect(app.textContent).toContain(label(window, "wizard.child.none.text"));
  });
});
