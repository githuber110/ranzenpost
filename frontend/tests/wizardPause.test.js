import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const PAUSED = {
  step: "login",
  school_url: "https://myschool.example",
  error: { code: "paused", message_key: "api.wizard.pausedCredentials" },
};

async function open(states) {
  const { window, document } = loadApp();
  const calls = [];
  window.fetch = (path) => {
    calls.push(String(path));
    if (String(path).includes("api/wizard")) return jsonResponse(states.length > 1 ? states.shift() : states[0]);
    return Promise.reject(new Error("unexpected fetch " + path));
  };
  const app = document.getElementById("app");
  await flush();
  window.renderWizard(app, () => {});
  await flush();
  return { app, calls, window };
}

function type(app, name, value) {
  const field = app.querySelector(`input[name="${name}"]`);
  field.value = value;
  field.dispatchEvent(new field.ownerDocument.defaultView.Event("input", { bubbles: true }));
}

describe("wizard pause after wrong passwords", () => {
  test("stays on the form, names the reason and holds the button with a countdown", async () => {
    const { app } = await open([{ ...PAUSED, retry_in: 25 }]);
    expect(app.querySelector('input[name="password"]')).toBeTruthy();
    expect(app.querySelector(".wz-error-pause").textContent).toContain("Passwort stimmen nicht");
    expect(app.querySelector(".sw-next").getAttribute("aria-disabled")).toBe("true");
    expect(app.querySelector(".sw-status").textContent).toMatch(/^Weiter in 0:2[45]$/);
    expect([...app.querySelectorAll("button")].some((b) => b.textContent === "Neu starten")).toBe(true);
  });

  test("unlocks by itself when the wait is over and keeps what was typed", async () => {
    const { app, calls } = await open([{ ...PAUSED, retry_in: 1 }]);
    type(app, "username", "parent.one");
    type(app, "password", "secret");
    expect(app.querySelector(".sw-next").getAttribute("aria-disabled")).toBe("true");
    await wait(1300);
    expect(app.querySelector(".sw-next").getAttribute("aria-disabled")).toBe("false");
    expect(app.querySelector(".wz-error-pause")).toBeNull();
    expect(app.querySelector('input[name="password"]').value).toBe("secret");
    expect(calls.filter((path) => path.includes("api/wizard"))).toHaveLength(1);
  });

  test("a paused error without time left blocks nothing", async () => {
    const { app } = await open([PAUSED]);
    expect(app.querySelector(".wz-error-pause")).toBeNull();
    type(app, "username", "parent.one");
    type(app, "password", "secret");
    expect(app.querySelector(".sw-next").getAttribute("aria-disabled")).toBe("false");
  });
});
