import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const qrJs = fs.readFileSync(path.join(frontendDir, "qr.js"), "utf8");
const wizardJs = fs.readFileSync(path.join(frontendDir, "wizard.js"), "utf8");
const SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
const URI = `otpauth://totp/IServ:parent?secret=${SECRET}&issuer=IServ`;

const START = {
  step: "connect",
  school_url: "https://myschool.example",
  has_2fa: true,
  needs_2fa_setup: true,
  verified_2fa: false,
  twofactor_setup: "start",
};
const CODE_STEP = { ...START, twofactor_setup: "code", setup_key: { secret: SECRET, uri: URI } };

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function label(window, key) {
  return evalWith(window, "t(testArgs[0])", key);
}

async function openWizard(first, answers = {}) {
  const { window, document } = loadApp();
  window.eval(qrJs);
  const posted = [];
  window.fetch = (requested, options) => {
    const where = String(requested);
    if (options && options.method === "POST") {
      posted.push({ where, body: options.body ? JSON.parse(options.body) : null });
      const key = Object.keys(answers).find((name) => where.endsWith(name));
      return jsonResponse(key ? answers[key] : first);
    }
    if (where.includes("api/wizard")) return jsonResponse(first);
    return Promise.reject(new Error("unexpected fetch " + where));
  };
  const app = document.getElementById("app");
  await flush();
  window.renderWizard(app, () => {});
  await flush();
  return { app, window, posted };
}

async function press(app) {
  app.querySelector(".sw-next").click();
  for (let round = 0; round < 4; round += 1) await flush();
}

describe("the first two-factor setup inside the app", () => {
  test("starting the setup asks the backend and then shows the key as QR code and text", async () => {
    const { app, window, posted } = await openWizard(START, { "api/wizard/twofactor/start": CODE_STEP });
    await press(app);
    expect(posted.map((entry) => entry.where.split("/api/")[1])).toEqual(["wizard/twofactor/start"]);
    expect(app.textContent).toContain(label(window, "wizard.setup.code.text"));
    const qr = app.querySelector(".wz-qr .cal-qr-frame");
    expect(qr.getAttribute("role")).toBe("img");
    expect(qr.getAttribute("aria-label")).toBe(label(window, "wizard.setup.qr.alt"));
    expect(qr.querySelector("svg path").getAttribute("d").length).toBeGreaterThan(100);
    const key = app.querySelector(".wz-key");
    expect(key.textContent).toBe("GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ");
    expect(key.getAttribute("dir")).toBe("ltr");
    expect(app.querySelector('input[name="code"]')).toBeTruthy();
    expect(app.querySelector(".sw-next").textContent).toContain(label(window, "wizard.setup.code.submit"));
  });

  test("the code goes to the setup confirmation once and a wrong code is named in the app", async () => {
    const rejected = { ...CODE_STEP, error: { code: "setup_rejected", message_key: "api.wizard.setup.rejected" } };
    const { app, window, posted } = await openWizard(CODE_STEP, { "api/wizard/twofactor/confirm": rejected });
    const input = app.querySelector('input[name="code"]');
    input.value = "000000";
    input.dispatchEvent(new window.Event("input"));
    await press(app);
    expect(posted).toHaveLength(1);
    expect(posted[0].where.endsWith("api/wizard/twofactor/confirm")).toBe(true);
    expect(posted[0].body).toEqual({ code: "000000" });
    expect(app.querySelector(".wz-error").textContent).toContain(label(window, "api.wizard.setup.rejected"));
    expect(app.querySelector(".wz-key")).toBeTruthy();
  });

  test("a finished setup continues with the usual connect step and says so", async () => {
    const done = { ...START, needs_2fa_setup: false, twofactor_setup: "done" };
    const { app, window } = await openWizard(done);
    expect(app.querySelector(".wz-good").textContent).toBe(label(window, "wizard.setup.done"));
    expect(app.textContent).toContain(label(window, "wizard.connect.text"));
    expect(app.querySelector('input[name="code"]')).toBeTruthy();
    expect(app.querySelector(".wz-key")).toBeNull();
  });

  test("an unclear answer offers only the check and never resends the code", async () => {
    const uncertain = {
      ...START,
      twofactor_setup: "uncertain",
      error: { code: "setup_uncertain", message_key: "api.wizard.setup.uncertain" },
    };
    const { app, window, posted } = await openWizard(uncertain, { "api/wizard/twofactor/check": START });
    expect(app.textContent).toContain(label(window, "wizard.setup.uncertain.text"));
    expect(app.querySelector(".wz-error").textContent).toContain(label(window, "api.wizard.setup.uncertain"));
    expect(app.querySelector('input[name="code"]')).toBeNull();
    expect(app.querySelector(".sw-next").textContent).toContain(label(window, "wizard.setup.check.button"));
    await press(app);
    expect(posted.map((entry) => entry.where.split("/api/")[1])).toEqual(["wizard/twofactor/check"]);
  });

  test("the setup step has one main button and never links to the school", async () => {
    for (const state of [START, CODE_STEP, { ...START, twofactor_setup: "uncertain" }]) {
      const { app } = await openWizard(state);
      expect(app.querySelectorAll(".sw-next")).toHaveLength(1);
      expect(app.querySelector("a[href]")).toBeNull();
      expect(app.querySelector("[target]")).toBeNull();
    }
    expect(wizardJs).not.toMatch(/target\s*[:=]\s*["']_blank/);
    expect(wizardJs).not.toMatch(/href\s*:/);
  });
});
