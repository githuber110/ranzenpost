import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
const NEW_TOKEN = "ZYXWVUTSRQPONMLKJIHGFEDCBA9876543210zyxwvut";
const INSTALL_URL =
  "https://my.home-assistant.io/redirect/hacs_repository/?owner=githuber110&repository=ranzenpost&category=integration";

function status(overrides = {}) {
  return { connected: true, last_request: "2026-09-02T08:10:00+02:00", token: TOKEN, port: 8099, ...overrides };
}

async function setup({ answer = status(), rotated = { ok: true, message_key: "api.integration.token.rotated", token: NEW_TOKEN } } = {}) {
  const app = loadApp();
  const { window } = app;
  const calls = [];
  for (let round = 0; round < 8; round += 1) await tick();
  window.eval("state.config = { notify_services: [], notify_events: {} };");
  window.fetch = (url, options) => {
    const target = String(url);
    calls.push({ url: target, options: options || {} });
    if (target.includes("api/integration-status/rotate")) {
      answer = status({ token: rotated.token || TOKEN });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(rotated) });
    }
    if (target.includes("api/integration-status")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
    }
    return Promise.reject(new Error(`unexpected request ${target}`));
  };
  return { ...app, calls };
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || null)})`);
}

async function openSheet(app) {
  await app.window.eval("openHomeAssistantSheet()");
  return app.document.querySelector(".sheet");
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("the settings carry a Home Assistant block", () => {
  test("the integration row sits last in the notifications and Home Assistant group", async () => {
    const { window } = await setup();
    const view = window.eval("settingsView()");
    const heads = [...view.querySelectorAll(".settings-group .section-head .overline")].map((node) => node.textContent);

    expect(heads[1]).toBe(label(window, "settings.section.notifications"));
    const rows = [...view.querySelectorAll(".settings-group")[1].querySelectorAll(".setting-row .lbl")].map((node) => node.textContent);
    expect(rows).toEqual([label(window, "settings.notify.service"), label(window, "schools.calendar.access"), label(window, "settings.ha.integration")]);
  });

  test("the row shows the connection state once the status is known", async () => {
    const { window } = await setup();
    window.eval("settingsView()");
    await tick();
    await tick();

    const view = window.eval("settingsView()");
    const value = view.querySelector(".ha-setting .val");
    expect(value.textContent).toBe(label(window, "settings.ha.status.connected"));
  });
});

describe("the Home Assistant sheet", () => {
  test("shows the connection, the last request, the token and the install link", async () => {
    const app = await setup();
    const { window } = app;
    const sheet = await openSheet(app);

    expect(sheet.querySelector(".sheet-title").textContent).toBe(label(window, "settings.ha.sheet"));
    expect(sheet.querySelector(".ha-status").textContent).toContain(label(window, "settings.ha.status.connected"));
    expect(sheet.querySelector(".ha-status").classList.contains("connected")).toBe(true);
    expect(sheet.querySelector(".ha-status-time").textContent).toBe(
      label(window, "settings.ha.status.lastRequest", { time: window.eval(`formatIsoMoment("2026-09-02T08:10:00+02:00")`) })
    );
    const input = sheet.querySelector(".ha-token");
    expect(input.value).toBe(TOKEN);
    expect(input.getAttribute("type")).toBe("password");
    expect(input.getAttribute("readonly")).toBe("readonly");
    expect(input.getAttribute("dir")).toBe("ltr");
    expect(sheet.textContent).toContain(label(window, "settings.ha.text"));
    const install = sheet.querySelector("a.ha-install");
    expect(install.getAttribute("href")).toBe(INSTALL_URL);
    expect(install.getAttribute("target")).toBe("_blank");
    expect(install.getAttribute("rel")).toBe("noopener");
    expect(install.textContent).toContain(label(window, "settings.ha.install"));
  });

  function primaries(sheet) {
    return [...sheet.querySelectorAll(".sheet-body .btn, .sheet-foot .btn")].filter(
      (node) => !node.classList.contains("ghost") && !node.classList.contains("destructive")
    );
  }

  test("while not connected the install link is the only filled button", async () => {
    const app = await setup({ answer: status({ connected: false, last_request: null }) });
    const sheet = await openSheet(app);

    const filled = primaries(sheet);
    expect(filled.length).toBe(1);
    expect(filled[0].classList.contains("ha-install")).toBe(true);
    expect(sheet.querySelector(".ha-copy").classList.contains("ghost")).toBe(true);
    expect(sheet.querySelector(".ha-rotate").classList.contains("ghost")).toBe(true);
  });

  test("once connected the install link steps back to a ghost button", async () => {
    const app = await setup();
    const sheet = await openSheet(app);

    expect(primaries(sheet)).toEqual([]);
    expect(sheet.querySelector("a.ha-install").classList.contains("ghost")).toBe(true);
  });

  test("the intro is two sentences and the install link carries the external-link icon", async () => {
    const app = await setup();
    const { window } = app;
    const sheet = await openSheet(app);

    const intro = label(window, "settings.ha.text");
    expect(intro.split(/[.!?](?:\s|$)/).filter((part) => part.trim()).length).toBeLessThanOrEqual(2);
    const install = sheet.querySelector("a.ha-install");
    expect(install.querySelector(".ico-external")).not.toBeNull();
    expect(install.querySelector('.ico-external path[d="M10.6 13.4 20 4"]')).not.toBeNull();
    expect(window.eval("ICON_SHAPES.external")).not.toBe(window.eval("ICON_SHAPES.open"));
  });

  test("a disconnected integration says so without a time", async () => {
    const app = await setup({ answer: status({ connected: false, last_request: null }) });
    const { window } = app;
    const sheet = await openSheet(app);

    expect(sheet.querySelector(".ha-status").textContent).toContain(label(window, "settings.ha.status.disconnected"));
    expect(sheet.querySelector(".ha-status").classList.contains("connected")).toBe(false);
    expect(sheet.querySelector(".ha-status-time")).toBeNull();
    expect(sheet.querySelector(".ha-token").value).toBe(TOKEN);
  });

  test("a failed status load shows the load error and no token", async () => {
    const app = await setup();
    app.window.fetch = () => Promise.reject(new Error("down"));
    const { window } = app;
    const sheet = await openSheet(app);

    expect(sheet.textContent).toContain(label(window, "settings.ha.loadFailed"));
    expect(sheet.querySelector(".ha-token")).toBeNull();
    expect(sheet.querySelector("a.ha-install")).not.toBeNull();
  });

  test("the token stays hidden until the reveal button is pressed and hides again on the next press", async () => {
    const app = await setup();
    const { window } = app;
    const sheet = await openSheet(app);
    const input = sheet.querySelector(".ha-token");
    const reveal = sheet.querySelector(".ha-reveal");

    expect(reveal.textContent).toContain(label(window, "settings.ha.token.reveal"));
    expect(reveal.classList.contains("ghost")).toBe(true);
    expect(reveal.getAttribute("aria-pressed")).toBe("false");
    expect(sheet.querySelectorAll(".ha-reveal").length).toBe(1);

    reveal.click();
    expect(input.getAttribute("type")).toBe("text");
    expect(reveal.getAttribute("aria-pressed")).toBe("true");

    reveal.click();
    expect(input.getAttribute("type")).toBe("password");
    expect(reveal.getAttribute("aria-pressed")).toBe("false");
  });

  test("copy puts the token on the clipboard and says so", async () => {
    const app = await setup();
    const { window, document } = app;
    const copied = [];
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (text) => { copied.push(text); return Promise.resolve(); } },
      configurable: true,
    });
    await openSheet(app);

    document.querySelector(".ha-copy").click();
    await tick();
    await tick();

    expect(copied).toEqual([TOKEN]);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "settings.ha.token.copied"));
  });

  test("regenerate asks first, then posts, reopens the sheet with the new token and reports", async () => {
    const app = await setup();
    const { window, document, calls } = app;
    await openSheet(app);

    document.querySelector(".ha-rotate").click();
    await tick();

    const confirm = document.querySelector(".sheet");
    expect(confirm.querySelector(".sheet-title").textContent).toBe(label(window, "settings.ha.rotate.title"));
    expect(confirm.textContent).toContain(label(window, "settings.ha.rotate.text"));
    expect(calls.filter((entry) => entry.url.includes("/rotate")).length).toBe(0);

    confirm.querySelector(".btn.destructive").click();
    for (let round = 0; round < 6; round += 1) await tick();

    const posts = calls.filter((entry) => entry.url.includes("api/integration-status/rotate"));
    expect(posts.length).toBe(1);
    expect(posts[0].options.method).toBe("POST");
    const sheet = document.querySelector(".sheet");
    expect(sheet.querySelector(".sheet-title").textContent).toBe(label(window, "settings.ha.sheet"));
    expect(sheet.querySelector(".ha-token").value).toBe(NEW_TOKEN);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "api.integration.token.rotated"));
  });

  test("cancelling the question leaves the token alone", async () => {
    const app = await setup();
    const { window, document, calls } = app;
    await openSheet(app);

    document.querySelector(".ha-rotate").click();
    await tick();
    document.querySelector(".sheet .btn.ghost").click();
    for (let round = 0; round < 4; round += 1) await tick();

    expect(calls.filter((entry) => entry.url.includes("/rotate")).length).toBe(0);
    const sheet = document.querySelector(".sheet");
    expect(sheet.querySelector(".sheet-title").textContent).toBe(label(window, "settings.ha.sheet"));
    expect(sheet.querySelector(".ha-token").value).toBe(TOKEN);
  });
});
