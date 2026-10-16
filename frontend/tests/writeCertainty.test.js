import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

async function settle(window, ticks = 12) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function json(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function timedOut(window) {
  const error = new window.Error("late");
  error.name = "TimeoutError";
  return Promise.reject(error);
}

function changePassword(window, document) {
  window.eval("openSheet(passwordSheet); render();");
  const inputs = Array.from(document.querySelectorAll("input[type=password]"));
  inputs[0].value = "old-pass";
  inputs[1].value = "new-pass-123";
  inputs[2].value = "new-pass-123";
  for (const input of inputs) input.dispatchEvent(new window.Event("input"));
  window.eval("state.sheet()").querySelector("button[type=submit]").click();
  return settle(window);
}

describe("a password change with an unclear outcome", () => {
  test("waits long for the answer and calls a timeout unclear instead of failed", async () => {
    const { window, document } = loadApp();
    const timeouts = [];
    window.AbortSignal.timeout = (ms) => {
      timeouts.push(ms);
      return new window.AbortController().signal;
    };
    window.fetch = (url) => (new URL(String(url)).pathname === "/api/password" ? timedOut(window) : Promise.reject(new Error("offline")));
    await changePassword(window, document);
    expect(Math.max(...timeouts)).toBeGreaterThanOrEqual(60000);
    expect(window.eval("state.toast.message")).toBe(window.t("settings.password.unclear"));
    expect(window.eval("state.sheet")).toBeFalsy();
  });

  test("an unclear answer from the app closes the form so nobody changes it twice", async () => {
    const { window, document } = loadApp();
    window.fetch = (url) => (new URL(String(url)).pathname === "/api/password"
      ? json({ ok: false, uncertain: true, message_key: "api.password.unclear" })
      : Promise.reject(new Error("offline")));
    await changePassword(window, document);
    expect(window.eval("state.toast.message")).toBe(window.t("api.password.unclear"));
    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.sheet")).toBeFalsy();
  });
});

function sickData(window) {
  const day = window.eval("isoDate(new Date())");
  return {
    children: [{ id: 1, name: "Mia" }],
    types: ["sick"],
    rules: {},
    entries: [],
    day_options: { from: [{ value: day, label: "Heute" }], till: [{ value: day, label: "Heute" }] },
    period_labels: [{ number: 1, label: "1. Stunde" }],
  };
}

function absenceRig(answer) {
  const { window, document } = loadApp();
  const posts = [];
  const timeouts = [];
  window.AbortSignal.timeout = (ms) => {
    timeouts.push(ms);
    return new window.AbortController().signal;
  };
  window.fetch = (url, options) => {
    const path = new URL(String(url)).pathname;
    if (path === "/api/absences" && options && options.method === "POST") {
      const body = JSON.parse(options.body);
      posts.push(body);
      return answer(body, posts.length);
    }
    if (path === "/api/absences") return json(sickData(window));
    return Promise.reject(new Error("offline"));
  };
  const wz = openWizard(window, "sick", sickData(window));
  return { window, document, posts, timeouts, wz };
}

async function sendReview(window, wz) {
  while (wz.step !== "review") wz.nextButton.click();
  wz.nextButton.click();
  await settle(window);
}

describe("a school app absence report with an unclear outcome", () => {
  test("a browser timeout says unclear, closes the form and the report carries a request id", async () => {
    const rig = absenceRig(() => timedOut(rig.window));
    await sendReview(rig.window, rig.wz);
    expect(rig.posts).toHaveLength(1);
    expect(rig.posts[0].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(Math.max(...rig.timeouts)).toBeGreaterThanOrEqual(60000);
    expect(rig.window.eval("state.toast.message")).toBe(rig.window.t("absence.older.sendUnclear"));
    expect(rig.window.eval("state.absenceForm")).toBeNull();
  });

  test("an unclear answer from the app is shown as unclear, never as failed", async () => {
    const rig = absenceRig(() => json({ ok: false, uncertain: true, message_key: "api.absence.sendUnclear" }));
    await sendReview(rig.window, rig.wz);
    expect(rig.window.eval("state.toast.message")).toBe(rig.window.t("api.absence.sendUnclear"));
    expect(rig.window.eval("state.absenceForm")).toBeNull();
  });

  test("a report the school already has is sent again only on an explicit yes with a new request id", async () => {
    const rig = absenceRig((body) => json(body.send_again ? { ok: true, message_key: "api.absence.sent.sick" } : { ok: false, already_sent: true, message_key: "api.absence.older.alreadySent" }));
    await sendReview(rig.window, rig.wz);
    expect(rig.posts).toHaveLength(1);
    rig.window.eval("state.sheet()").querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle(rig.window);
    expect(rig.posts).toHaveLength(2);
    expect(rig.posts[1].send_again).toBe(true);
    expect(rig.posts[1].request_id).not.toBe(rig.posts[0].request_id);
    expect(rig.window.eval("state.absenceForm")).toBeNull();
  });

  test("a retry after a plain failure keeps the request id so the app never sends it twice", async () => {
    const rig = absenceRig(() => Promise.reject(new TypeError("offline")));
    await sendReview(rig.window, rig.wz);
    rig.wz.nextButton.click();
    await settle(rig.window);
    expect(rig.posts).toHaveLength(2);
    expect(rig.posts[0].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(rig.posts[1].request_id).toBe(rig.posts[0].request_id);
  });
});

describe("a school app withdrawal with an unclear outcome", () => {
  test("waits long and calls a timeout unclear instead of failed", async () => {
    const { window } = loadApp();
    const timeouts = [];
    window.AbortSignal.timeout = (ms) => {
      timeouts.push(ms);
      return new window.AbortController().signal;
    };
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/absences/delete") return timedOut(window);
      if (path === "/api/absences") return json(sickData(window));
      return Promise.reject(new Error("offline"));
    };
    evalWith(window, "state.absence = { data: testArgs[0] }", sickData(window));
    window.eval("withdrawAbsence")({ id: 42, kind: "leave", target: "", student_id: 1, label: "Antrag", deletable: true });
    await settle(window);
    window.eval("state.sheet()").querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle(window);
    expect(Math.max(...timeouts)).toBeGreaterThanOrEqual(60000);
    expect(window.eval("state.toast.message")).toBe(window.t("api.absence.withdrawUnclear"));
  });
});
