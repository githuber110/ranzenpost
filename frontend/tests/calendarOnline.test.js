import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const base = JSON.parse(fs.readFileSync(path.resolve(dirname, "..", "i18n", "de.json"), "utf8"));
const CLOUD_URL = "https://hooks.nabu.casa/gAAAAABexample";

const LOCAL = {
  id: "sub-1",
  child_key: "c1",
  label: "3b",
  components: ["timetable"],
  color: "#135859",
  token: "token-1",
  path: "/calendar/token-1.ics",
  online: false,
  online_state: "off",
  online_url: "",
};
const INTERNET = { ...LOCAL, online: true, online_state: "ready", online_url: CLOUD_URL };

function setup({ internet = "ready", subscriptions = [LOCAL] } = {}) {
  const { window } = loadApp();
  const calls = [];
  window.eval("render = function () {};");
  window.eval('state.children = [{ key: "c1", name: "Mia", class_name: "3b" }]; state.childId = "c1";');
  evalWith(
    window,
    "state.calendar = { data: testArgs[0], error: false };",
    {
      subscriptions,
      components: ["timetable"],
      holiday_regions: { s1: "DE-NI" },
      port: 8100,
      host: "homeassistant.local",
      host_source: "config_entry",
      supervisor: true,
      port_open: true,
      internet,
    }
  );
  window.fetch = (url, options) => {
    calls.push({ url: String(url), options: options || {} });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ subscriptions }) });
  };
  return { window, calls };
}

function block(window, subscription) {
  const host = window.document.createElement("div");
  for (const node of evalWith(window, "calendarSubscriptionBlock(testArgs[0], state.children[0])", subscription)) host.append(node);
  return host;
}

function form(window, draftCode) {
  window.eval(`state.calendarDraft = ${draftCode};`);
  return window.eval("calendarForm(state.calendarDraft)");
}

function variants(node) {
  return [...node.querySelectorAll(".cal-variant input")];
}

describe("choosing where the calendar loads", () => {
  test("a new calendar offers local and internet, local first and chosen", () => {
    const { window } = setup();
    const node = form(window, "calendarNewDraft(state.children[0])");

    const [local, internet] = variants(node);
    expect(node.textContent).toContain(base["calendar.subscribe.variant.local.hint"]);
    expect(node.textContent).toContain(base["calendar.subscribe.variant.internet.hint"]);
    expect([local.checked, internet.checked, internet.disabled]).toEqual([true, false, false]);
  });

  test.each([
    ["no_access", "calendar.subscribe.variant.internet.noAccess"],
    ["no_integration", "calendar.subscribe.variant.internet.noIntegration"],
    ["update_integration", "calendar.subscribe.variant.internet.update"],
    [null, "calendar.subscribe.variant.internet.noIntegration"],
  ])("without access from outside (%s) internet is greyed out with its reason", (internet, reason) => {
    const { window } = setup({ internet });
    const node = form(window, "calendarNewDraft(state.children[0])");

    expect(variants(node)[1].disabled).toBe(true);
    expect(node.querySelector(".cal-variant-reason").textContent).toBe(base[reason]);
  });

  test("an internet calendar stays editable when the access is gone for now", () => {
    const { window } = setup({ internet: "no_access", subscriptions: [INTERNET] });
    const node = form(window, "calendarEditDraft(state.calendar.data.subscriptions[0], state.children[0])");

    const [local, internet] = variants(node);
    expect([local.checked, internet.checked, internet.disabled]).toEqual([false, true, false]);
  });

  test("the choice goes along when the calendar is created", async () => {
    const { window, calls } = setup();
    const node = form(window, "calendarNewDraft(state.children[0])");
    const internet = variants(node)[1];
    internet.checked = true;
    internet.dispatchEvent(new window.Event("change"));
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    const sent = calls.filter((entry) => entry.options.method === "POST");
    expect(JSON.parse(sent[0].options.body).online).toBe(true);
  });
});

describe("a calendar on the page", () => {
  test("a local calendar spells no address out and offers add, copy and QR", () => {
    const { window } = setup();
    const node = block(window, LOCAL);

    expect(node.textContent).not.toContain("homeassistant.local");
    expect(node.querySelector(".cal-variant-tag").textContent).toBe(base["calendar.subscribe.variant.local"]);
    expect(node.querySelector(".cal-add")).not.toBeNull();
    expect(node.querySelector(".cal-copy")).not.toBeNull();
    expect(node.querySelectorAll(".btn:not(.ghost)")).toHaveLength(1);
  });

  test("an internet calendar hands its webcal address to the calendar app", () => {
    const { window } = setup({ subscriptions: [INTERNET] });
    window.eval("window.__handoff = null; handOffCalendarUrl = (url) => { window.__handoff = url; return true; };");
    const node = block(window, INTERNET);

    node.querySelector(".cal-add").click();

    expect(window.eval("window.__handoff")).toBe("webcal://hooks.nabu.casa/gAAAAABexample");
    expect(node.textContent).not.toContain("hooks.nabu.casa");
    expect(node.querySelector(".cal-variant-tag").textContent).toBe(base["calendar.subscribe.variant.internet"]);
  });

  test("copying an internet calendar hands over the https link", async () => {
    const { window } = setup({ subscriptions: [INTERNET] });
    const copied = [];
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (text) => { copied.push(text); return Promise.resolve(); } },
      configurable: true,
    });
    block(window, INTERNET).querySelector(".cal-copy").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(copied).toEqual([CLOUD_URL]);
  });

  test.each([
    ["pending", "calendar.subscribe.online.pending"],
    ["stalled", "calendar.subscribe.online.stalled"],
    ["no_integration", "calendar.subscribe.online.noIntegration"],
    ["unreachable", "calendar.subscribe.online.unreachable"],
    ["later", "calendar.subscribe.online.pending"],
  ])("an internet calendar that is %s says so instead of offering buttons", (status, key) => {
    const { window } = setup();
    const node = block(window, { ...INTERNET, online_state: status, online_url: "" });

    expect(node.querySelector(".cal-online-status").textContent).toBe(base[key]);
    expect(node.querySelector(".cal-add")).toBeNull();
    expect(node.querySelector(".cal-copy")).toBeNull();
  });

  test("the setup help fits the variant", () => {
    const { window } = setup();
    const local = block(window, LOCAL).querySelector(".cal-help").textContent;
    const internet = block(window, INTERNET).querySelector(".cal-help").textContent;

    expect(local).toContain(base["calendar.subscribe.help.localOnly"]);
    expect(local).not.toContain(base["calendar.subscribe.help.google"]);
    expect(internet).toContain(base["calendar.subscribe.help.google"]);
    expect(internet).toContain(base["calendar.subscribe.help.outlook"]);
  });

  test("editing, renewing and deleting sit in the menu", () => {
    const { window } = setup();
    const node = block(window, LOCAL);

    expect(node.textContent).not.toContain(base["calendar.subscribe.delete"]);
    node.querySelector(".cal-menu").click();
    const sheetText = window.eval("state.sheet()").textContent;

    expect(sheetText).toContain(base["calendar.subscribe.edit"]);
    expect(sheetText).toContain(base["calendar.subscribe.rotate"]);
    expect(sheetText).toContain(base["calendar.subscribe.delete"]);
  });
});

const IPHONE_APP_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
  + "(KHTML, like Gecko) Mobile/15E148 Home Assistant/2026.8 (io.robbie.HomeAssistant; build:1)";

describe("an internet calendar in the Home Assistant app", () => {
  test("copying on an iPhone hands over the webcal link so Safari subscribes", async () => {
    const { window } = setup({ subscriptions: [INTERNET] });
    Object.defineProperty(window.navigator, "userAgent", { value: IPHONE_APP_UA, configurable: true });
    const copied = [];
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (text) => { copied.push(text); return Promise.resolve(); } },
      configurable: true,
    });
    const node = block(window, INTERNET);
    node.querySelector(".cal-copy").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(copied).toEqual(["webcal://hooks.nabu.casa/gAAAAABexample"]);
    expect(node.querySelector(".cal-help").textContent).toContain(base["calendar.subscribe.help.appInternet"]);
    expect(node.querySelector(".cal-help").textContent).not.toContain(base["calendar.subscribe.help.app"]);
  });
});

describe("refreshing while an internet calendar is set up", () => {
  function refreshing(window, answer) {
    let renders = 0;
    window.eval("render = function () { window.__renders = (window.__renders || 0) + 1; };");
    window.fetch = () => answer();
    return {
      run: () => window.eval("refreshCalendarPending()"),
      renders: () => window.eval("window.__renders || 0") + renders,
    };
  }

  test("a failed refresh keeps what is on screen", async () => {
    const { window } = setup({ subscriptions: [{ ...INTERNET, online_state: "pending", online_url: "" }] });
    const before = window.eval("JSON.stringify(state.calendar)");
    const probe = refreshing(window, () => Promise.reject(new TypeError("Failed to fetch")));

    expect(await probe.run()).toBe(false);
    expect(window.eval("JSON.stringify(state.calendar)")).toBe(before);
    expect(probe.renders()).toBe(0);
  });

  test("an unchanged answer renders nothing", async () => {
    const { window } = setup({ subscriptions: [{ ...INTERNET, online_state: "pending", online_url: "" }] });
    const same = window.eval("JSON.parse(JSON.stringify(state.calendar.data))");
    const probe = refreshing(window, () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(same) }));

    expect(await probe.run()).toBe(false);
    expect(probe.renders()).toBe(0);
  });

  test("a ready address is shown, but never under an open form", async () => {
    const { window } = setup({ subscriptions: [{ ...INTERNET, online_state: "pending", online_url: "" }] });
    const ready = window.eval("JSON.parse(JSON.stringify(state.calendar.data))");
    ready.subscriptions = [INTERNET];
    const probe = refreshing(window, () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ready) }));

    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    expect(await probe.run()).toBe(true);
    expect(probe.renders()).toBe(0);
    expect(window.eval("state.calendar.data.subscriptions[0].online_state")).toBe("ready");
  });
});

describe("switching an internet calendar back to local", () => {
  test("sends local and opens the port the local link needs", async () => {
    const { window, calls } = setup({ subscriptions: [INTERNET] });
    window.eval("state.calendar.data.port_open = false;");
    const node = form(window, "calendarEditDraft(state.calendar.data.subscriptions[0], state.children[0])");
    const local = variants(node)[0];
    local.checked = true;
    local.dispatchEvent(new window.Event("change"));
    const reloaded = { ...window.eval("JSON.parse(JSON.stringify(state.calendar.data))"), subscriptions: [LOCAL], port_open: false };
    window.fetch = (url, options) => {
      calls.push({ url: String(url), options: options || {} });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(reloaded) });
    };
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    const posts = calls.filter((entry) => entry.options.method === "POST");
    expect(JSON.parse(posts[0].options.body).online).toBe(false);
    expect(posts.some((entry) => entry.url.endsWith("api/calendar/port"))).toBe(true);
  });

  test("a colour change on a local calendar leaves the port alone", async () => {
    const { window, calls } = setup();
    window.eval("state.calendar.data.port_open = false;");
    form(window, "calendarEditDraft(state.calendar.data.subscriptions[0], state.children[0])");
    window.eval('state.calendarDraft.color = "#2486ed";');
    const reloaded = { ...window.eval("JSON.parse(JSON.stringify(state.calendar.data))"), port_open: false };
    window.fetch = (url, options) => {
      calls.push({ url: String(url), options: options || {} });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(reloaded) });
    };
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    expect(calls.some((entry) => entry.url.endsWith("api/calendar/port"))).toBe(false);
  });
});

describe("small edges", () => {
  test("the Mac app copies the webcal link too", async () => {
    const { window } = setup({ subscriptions: [INTERNET] });
    Object.defineProperty(window.navigator, "userAgent", {
      value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Home Assistant/2026.8",
      configurable: true,
    });
    const copied = [];
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (text) => { copied.push(text); return Promise.resolve(); } },
      configurable: true,
    });
    block(window, INTERNET).querySelector(".cal-copy").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(copied).toEqual(["webcal://hooks.nabu.casa/gAAAAABexample"]);
  });

  test("a checked access unlocks internet even in an open form", async () => {
    const { window } = setup({ internet: "checking" });
    expect(window.eval("calendarHasPending()")).toBe(true);
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    window.eval("render = function () { window.__renders = (window.__renders || 0) + 1; };");
    const ready = { ...window.eval("JSON.parse(JSON.stringify(state.calendar.data))"), internet: "ready" };
    window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ready) });

    expect(await window.eval("refreshCalendarPending()")).toBe(true);
    expect(window.eval("window.__renders || 0")).toBe(1);
    expect(window.eval("calendarHasPending()")).toBe(false);
  });
});
