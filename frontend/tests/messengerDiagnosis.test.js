import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
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

function route(window, reply) {
  window.fetch = (input) => {
    const url = String(input);
    if (url.includes("api/messenger/rooms")) return reply();
    return jsonResponse({});
  };
}

async function failWith(window, body) {
  window.eval("state.view = 'messenger'; state.messengerRoom = null; state.messengerRooms = null;");
  route(window, () => jsonResponse(body));
  await window.eval("loadMessengerRooms()");
  await settle();
}

describe("[P228] the messenger says what actually went wrong", () => {
  test("a missing module is named as such instead of the generic card", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, {
      error: "network",
      message_key: "api.messenger.error.module",
      diagnosis: { stage: "module", status: 404 },
    });
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("api.messenger.error.module")'));
    expect(text).not.toContain(window.eval('t("messenger.error.text")'));
  });

  test("a refused sign-in is told apart from a missing module", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, {
      error: "network",
      message_key: "api.messenger.error.login",
      diagnosis: { stage: "login" },
    });
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("api.messenger.error.login")'));
    expect(text).not.toContain(window.eval('t("api.messenger.error.module")'));
  });

  test("without a message key the old wording still stands", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, { error: "network" });
    expect(document.getElementById("app").textContent).toContain(
      window.eval('t("messenger.error.text")')
    );
  });

  test("the diagnosis is reachable and carries the stage, not a secret", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, {
      error: "network",
      message_key: "api.messenger.error.bootstrap",
      diagnosis: { stage: "bootstrap", status: 200, marker_present: false, script_blocks: 3 },
    });
    const button = document.querySelector(".empty .tech-btn");
    expect(button).not.toBeNull();
    button.click();
    const sheet = document.querySelector(".sheet");
    expect(sheet.textContent).toContain("bootstrap");
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.script_blocks")'));
    expect(sheet.textContent).not.toContain("script_blocks");
    expect(sheet.textContent).not.toContain("marker_present");
  });

  test("[P228] the diagnosis reads as words, not as raw backend types", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, {
      error: "network",
      message_key: "api.messenger.error.bootstrap",
      diagnosis: { stage: "bootstrap", marker_present: false, continuation_hops: 2 },
    });
    document.querySelector(".empty .tech-btn").click();
    const sheet = document.querySelector(".sheet");
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.marker_present")'));
    expect(sheet.textContent).toContain(window.eval('t("common.no")'));
    expect(sheet.textContent).not.toContain("[object Object]");
    expect(sheet.textContent).not.toContain("false");
  });

  test("[P228] the retry keeps a visible loading state and owns up to a second failure", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, { error: "network", message_key: "api.messenger.error.network" });

    let release = null;
    route(window, () => new Promise((resolve) => { release = resolve; }));
    const retry = [...document.querySelectorAll("button")].find(
      (node) => node.textContent.trim() === window.eval('t("common.retry")')
    );
    expect(retry).toBeTruthy();
    retry.click();
    const during = document.getElementById("app").textContent;
    expect(during).toContain(window.eval('t("messenger.error.retrying")'));
    expect(during).toContain(window.eval('t("common.loading")'));

    release(jsonResponse({ error: "network", message_key: "api.messenger.error.network" }));
    await settle();
    await settle();
    const after = document.getElementById("app").textContent;
    expect(after).toContain(window.eval('t("messenger.error.retryFailed")'));
    expect(after).toContain(window.eval('t("api.messenger.error.network")'));
  });

  test("[P228] credentials IServ withheld are named, not sold as an unexpected answer", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    await failWith(window, {
      error: "network",
      message_key: "api.messenger.error.noCredentials",
      diagnosis: {
        stage: "no_credentials",
        page_credentials: "messenger_authentication is null",
        page_privileges: "canWriteToTeacher, isParent",
      },
    });
    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("api.messenger.error.noCredentials")'));
    expect(text).not.toContain(window.eval('t("api.messenger.error.bootstrap")'));

    document.querySelector(".empty .tech-btn").click();
    const sheet = document.querySelector(".sheet");
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.page_credentials")'));
    expect(sheet.textContent).toContain(window.eval('t("diagnosis.page_privileges")'));
    expect(sheet.textContent).not.toContain("page_credentials");
    expect(sheet.textContent).not.toContain("page_privileges");
  });

  test("[P228] a request that runs into the timeout is not sold as a network outage", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.view = 'messenger'; state.messengerRoom = null; state.messengerRooms = null;");
    route(window, () => {
      const failure = new Error("timed out");
      failure.name = "TimeoutError";
      return Promise.reject(failure);
    });
    await window.eval("loadMessengerRooms()");
    await settle();
    expect(document.getElementById("app").textContent).toContain(
      window.eval('t("api.messenger.error.timeout")')
    );
  });
});
