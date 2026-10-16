import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const i18nDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "i18n");
const STALE = "b2b6b8b0-1111-4a2a-9c3c-abcdef123456";
const OTHER = "c3c3c3c3-2222-4b2b-8d3d-abcdef654321";
const THIRD = "d4d4d4d4-3333-4c4c-9e4e-abcdef000003";
const CHILD = { child_id: "c1", name: "Alex" };
const SECOND = {
  step: "connect",
  school_url: "https://myschool.example",
  has_2fa: true,
  needs_2fa_setup: false,
  awaiting_confirm: true,
};
const CHILD_STEP = { step: "child", school_url: "https://myschool.example", has_2fa: true, connection_id: "c", stale_uuids: [STALE] };

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

function counted(window, key, count) {
  return evalWith(window, "tCount(testArgs[0], testArgs[1])", key, count);
}

function label(window, key, vars) {
  return evalWith(window, "t(testArgs[0], testArgs[1])", key, vars);
}

async function openWizard(first, answers = {}) {
  const { window, document } = loadApp();
  const posted = [];
  const bodies = [];
  window.fetch = (requested, options) => {
    const where = String(requested);
    if (options && options.method === "POST") {
      posted.push(where.split("/api/")[1]);
      bodies.push(options.body ? JSON.parse(options.body) : null);
      const key = Object.keys(answers).find((name) => where.endsWith(name));
      return jsonResponse(key ? answers[key] : first);
    }
    if (where.includes("api/children")) return jsonResponse([CHILD]);
    if (where.includes("api/wizard")) return jsonResponse(first);
    return Promise.reject(new Error("unexpected fetch " + where));
  };
  const app = document.getElementById("app");
  await flush();
  window.renderWizard(app, () => {});
  for (let round = 0; round < 4; round += 1) await flush();
  return { app, window, posted, bodies };
}

async function settle() {
  for (let round = 0; round < 4; round += 1) await flush();
}

describe("old ISERV-Connector entries and an unconfirmed registration", () => {
  test("the code step says the app can remove old entries, or that they do no harm", async () => {
    let opened = await openWizard({ ...SECOND, stale_tokens: 2, stale_removable: 2 });
    expect(opened.app.querySelector(".wz-warn").textContent).toBe(counted(opened.window, "wizard.connect.staleTokens", 2));
    opened = await openWizard({ ...SECOND, stale_tokens: 2, stale_removable: 0 });
    expect(opened.app.querySelector(".wz-warn").textContent).toBe(counted(opened.window, "wizard.connect.staleKept", 2));
  });

  test("the earlier entry of this connection is removed with one confirmation", async () => {
    const removed = { ...CHILD_STEP, stale_uuids: undefined, stale_removed: 1 };
    const { app, window, posted } = await openWizard(CHILD_STEP, { "api/wizard/stale-tokens/remove": removed });
    expect(app.querySelector(".wz-stale .wz-warn").textContent).toBe(label(window, "wizard.stale.own.text"));
    expect(app.querySelector(".wz-child")).toBeTruthy();
    expect(app.querySelector(".wz-tokens")).toBeNull();
    const remove = app.querySelector(".wz-stale .wz-skip");
    expect(remove.textContent).toBe(label(window, "wizard.stale.own.remove"));
    remove.click();
    const panel = app.querySelector(".sw-confirm");
    expect(panel.textContent).toContain(label(window, "wizard.stale.own.confirm"));
    panel.querySelector(".btn.ghost").click();
    expect(app.querySelector(".sw-confirm")).toBeNull();
    expect(posted).toEqual([]);
    remove.click();
    app.querySelector(".sw-confirm .btn.destructive").click();
    expect(app.querySelector(".wz-stale [role=status]").textContent).toBe(counted(window, "wizard.stale.busy", 2));
    await settle();
    expect(posted).toEqual(["wizard/stale-tokens/remove"]);
    expect(app.querySelector(".wz-good").textContent).toBe(counted(window, "wizard.stale.done", 1));
    expect(app.querySelector(".wz-stale")).toBeNull();
  });

  test("other entries are listed with their date and removed one by one after a clear warning", async () => {
    const tokens = [
      { uuid: OTHER, name: "ISERV-Connector", created: "2026-09-01" },
      { uuid: THIRD, name: "ISERV-Connector", created: "" },
    ];
    const state = { ...CHILD_STEP, stale_uuids: undefined, other_tokens: tokens };
    const after = { ...state, other_tokens: [tokens[1]], stale_removed: 1 };
    const { app, window, posted, bodies } = await openWizard(state, { "api/wizard/other-tokens/remove": after });
    expect(app.querySelector(".wz-stale .wz-warn")).toBeNull();
    expect(app.querySelector(".wz-token-intro").textContent).toBe(counted(window, "wizard.stale.other.text", 2));
    const rows = app.querySelectorAll(".wz-token");
    expect(rows.length).toBe(2);
    const day = new Intl.DateTimeFormat(window.document.documentElement.lang || undefined, { dateStyle: "medium" }).format(new Date("2026-09-01T12:00:00"));
    expect(rows[0].querySelector(".wz-token-name").textContent).toBe("ISERV-Connector");
    expect(rows[0].querySelector(".wz-token-date").textContent).toBe(label(window, "wizard.stale.other.created", { date: day }));
    expect(rows[1].querySelector(".wz-token-date")).toBeNull();
    rows[1].querySelector(".wz-token-remove").click();
    expect(app.querySelector(".sw-confirm").textContent).toContain(label(window, "wizard.stale.other.confirm", { name: "ISERV-Connector" }));
    app.querySelector(".sw-confirm .btn.ghost").click();
    rows[0].querySelector(".wz-token-remove").click();
    expect(app.querySelector(".sw-confirm").textContent).toContain(label(window, "wizard.stale.other.confirmDated", { name: "ISERV-Connector", date: day }));
    expect(posted).toEqual([]);
    app.querySelector(".sw-confirm .btn.destructive").click();
    expect(app.querySelector(".wz-stale [role=status]").textContent).toBe(counted(window, "wizard.stale.busy", 2));
    await settle();
    expect(posted).toEqual(["wizard/other-tokens/remove"]);
    expect(bodies).toEqual([{ uuid: OTHER, confirmed: true }]);
    expect(app.querySelectorAll(".wz-token").length).toBe(1);
    expect(app.querySelector(".wz-good").textContent).toBe(counted(window, "wizard.stale.done", 1));
  });

  test("a sign-in pause from a removal is shown next to the entries", async () => {
    const paused = { ...CHILD_STEP, retry_in: 120, error: { code: "paused", message_key: "api.wizard.pausedRateLimited" } };
    const { app, window } = await openWizard(paused);
    expect(app.querySelector(".wz-stale .wz-error").textContent).toBe(label(window, "api.wizard.pausedRateLimited"));
  });

  test("a failed removal is named next to the offer", async () => {
    const failed = { ...CHILD_STEP, error: { code: "stale_failed", message_key: "api.wizard.stale.failed" } };
    const { app, window } = await openWizard(failed);
    expect(app.querySelector(".wz-stale .wz-error").textContent).toBe(label(window, "api.wizard.stale.failed"));
    expect(app.querySelector(".wz-stale .wz-skip")).toBeTruthy();
  });

  test("an unconfirmed registration offers a check in the app next to a fresh code", async () => {
    const state = {
      ...SECOND,
      awaiting_confirm: undefined,
      registration_unconfirmed: true,
      error: { code: "unconfirmed", message_key: "api.twofactor.unconfirmed" },
    };
    const { app, window, posted } = await openWizard(state, { "api/wizard/registration/check": CHILD_STEP });
    expect(app.querySelector(".wz-error").textContent).toContain(label(window, "api.twofactor.unconfirmed"));
    expect(app.querySelector('input[name="code"]')).toBeTruthy();
    const check = [...app.querySelectorAll(".wz-skip")].find((button) => button.textContent === label(window, "wizard.registration.check"));
    check.click();
    await settle();
    expect(posted).toEqual(["wizard/registration/check"]);
    expect(app.querySelector(".wz-stale")).toBeTruthy();
  });

  test("no two-factor text sends anyone to IServ any more", () => {
    const keys = /^(wizard\.connect\.stale|wizard\.stale\.|api\.twofactor\.unconfirmed|account\.reconnect\.resetNote|wizard\.setup\.|api\.wizard\.setup\.|api\.wizard\.twofactorSetupPending)/;
    const handOff = [/Einstellungen\s*→/, /Settings\s*→/, /im Browser/i, /in the browser/i, /kannst du (dort|in IServ)/, /you can delete/i, /in IServ (unter|nachsehen)/, /check under/i];
    for (const lang of ["de", "en", "ar", "tr", "ru", "uk"]) {
      const messages = JSON.parse(fs.readFileSync(path.join(i18nDir, `${lang}.json`), "utf8"));
      for (const [key, value] of Object.entries(messages)) {
        if (!keys.test(key)) continue;
        for (const pattern of handOff) expect(`${lang} ${key}: ${value}`).not.toMatch(pattern);
        expect(`${lang} ${key}: ${value}`).not.toMatch(/Einstellungen|Sicherheit \(|الإعدادات ثم الأمان/);
      }
    }
  });
});
