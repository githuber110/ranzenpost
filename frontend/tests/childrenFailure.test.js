import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await settle();
  window.clearTimeout(window.eval("bootWatchdog"));
}

const CHILD = {
  child_id: "c1",
  name: "Kim",
  class_name: "3b",
  student_id: "s1",
  class_full: "3b",
  class_code: "3b",
};

const UPSTREAM_FAILURE = {
  error: "network",
  message_key: "api.children.unreadable",
  diagnosis: { status: 200, child_select: false, login_form: true },
};

function routeChildren(window, reply) {
  window.fetch = (input) => {
    const url = String(input);
    if (url.includes("api/children")) return reply();
    if (url.includes("api/health")) {
      return jsonResponse({ configured: true, connection: "ok", username: "parent", language: "de" });
    }
    if (url.includes("api/timetable-availability")) return jsonResponse({ available: true });
    return jsonResponse({});
  };
}

async function bootWith(reply) {
  const app = loadApp();
  await quiet(app.window);
  routeChildren(app.window, reply);
  await app.window.eval("loadChildren()");
  await settle();
  return app;
}

describe("[P236] a child list that could not be loaded is not sold as an empty selection", () => {
  test("the overview names the upstream reason instead of saying no child is selected", async () => {
    const { window, document } = await bootWith(() => jsonResponse(UPSTREAM_FAILURE));
    window.eval("state.view = 'overview'; rerender();");
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("api.children.unreadable")'));
    expect(text).not.toContain(window.eval('t("overview.noChild")'));
  });

  test("the timetable says the same thing rather than a different one", async () => {
    const { window, document } = await bootWith(() => jsonResponse(UPSTREAM_FAILURE));
    window.eval("state.view = 'timetable'; rerender();");
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("api.children.unreadable")'));
    expect(text).not.toContain(window.eval('t("overview.noChild")'));
  });

  test("the reason is reachable in detail without leaking the page", async () => {
    const { window, document } = await bootWith(() => jsonResponse(UPSTREAM_FAILURE));
    window.eval("state.view = 'overview'; rerender();");
    document.querySelector(".tech-btn").click();
    const sheet = document.querySelector(".sheet");
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.child_select")'));
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.login_form")'));
    expect(sheet.textContent).not.toContain("child_select");
  });

  test("a failure without a wording of its own still says the list could not be loaded", async () => {
    const { window, document } = await bootWith(() => jsonResponse({ error: "network" }));
    window.eval("state.view = 'overview'; rerender();");
    expect(document.getElementById("app").textContent).toContain(
      window.eval('t("overview.children.failed")')
    );
  });

  test("an account that really has no child keeps the old wording", async () => {
    const { window, document } = await bootWith(() => jsonResponse([]));
    window.eval("state.view = 'overview'; rerender();");
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("overview.noChild")'));
    expect(text).not.toContain(window.eval('t("overview.children.failed")'));
  });

  test("retrying clears the message once the list arrives", async () => {
    const { window, document } = await bootWith(() => jsonResponse(UPSTREAM_FAILURE));
    window.eval("state.view = 'overview'; rerender();");
    const retry = [...document.querySelectorAll("button")].find(
      (node) => node.textContent.trim() === window.eval('t("common.retry")')
    );
    expect(retry).toBeTruthy();

    routeChildren(window, () => jsonResponse([CHILD]));
    retry.click();
    for (let round = 0; round < 8; round += 1) await settle();

    expect(window.eval("state.childrenFailure")).toBeNull();
    expect(window.eval("state.childId")).toBe("c1");
    expect(document.getElementById("app").textContent).not.toContain(
      window.eval('t("api.children.unreadable")')
    );
  });

  test("pulling to refresh fetches the child list again after it failed", async () => {
    const { window } = await bootWith(() => jsonResponse(UPSTREAM_FAILURE));
    expect(window.eval("state.children.length")).toBe(0);

    routeChildren(window, () => jsonResponse([CHILD]));
    await window.eval("refreshEverything()");
    for (let round = 0; round < 4; round += 1) await settle();

    expect(window.eval("state.childrenFailure")).toBeNull();
    expect(window.eval("state.children.length")).toBe(1);
  });

  test("a working list never leaves a failure behind", async () => {
    const { window } = await bootWith(() => jsonResponse([CHILD]));
    expect(window.eval("state.childrenFailure")).toBeNull();
    expect(window.eval("state.childId")).toBe("c1");
  });
});
