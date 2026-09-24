import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const FRONTEND = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(FRONTEND, "styles.css"), "utf8");

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";
const SINCE = "2026-09-19T02:18:00+02:00";
const LAST_SUCCESS = "2026-09-19T01:48:00+02:00";

const CONNECTIONS = [
  { id: ONE, school_url: "https://gym-sued.example", school_name: "Gymnasium Süd", setup_complete: true, phones: [], period_times: { 1: "08:00" }, subjects: {}, teachers: {} },
  { id: TWO, school_url: "https://iserv.gs-nord.example", school_name: "Grundschule Nord", short_name: "GS Nord", setup_complete: true, phones: [], period_times: { 1: "07:45" }, subjects: {}, teachers: {} },
];

const CHILDREN = [
  { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, school: "Gymnasium Süd", name: "Mia Example", class_name: "7b" },
  { key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, school: "Grundschule Nord", name: "Tom Example", class_name: "3a" },
];

function schoolRow(id, status, extra) {
  return Object.assign(
    { id, name: id === ONE ? "Gymnasium Süd" : "Grundschule Nord", short_name: id === ONE ? "gym-sued" : "GS Nord", status, username: "parent", setup_complete: true, children: 1, since: null, last_success: null },
    extra || {}
  );
}

function seed(window, { schools = 1, status = "outage", view = "overview", extra = "" } = {}) {
  const connections = CONNECTIONS.slice(0, schools);
  const children = CHILDREN.filter((child) => connections.some((entry) => entry.id === child.connection_id));
  const rows = connections.map((entry, index) =>
    schoolRow(entry.id, index === 0 ? status : "ok", index === 0 ? { since: SINCE, last_success: LAST_SUCCESS } : {})
  );
  window.eval(`
    state.config = { connections: ${JSON.stringify(connections)}, language: "de", notify_services: [] };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(children[0].key)};
    state.schools = ${JSON.stringify(rows)};
    applySchoolStatus(state.schools);
    state.loadedAt = {};
    state.view = ${JSON.stringify(view)};
    state.timetable = { lessons: [], period_times: {}, error: "network" };
    ${extra}
  `);
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

function stubFetch(window, answer) {
  const calls = [];
  window.fetch = (url, options) => {
    const path = String(url).slice(String(url).indexOf("api/"));
    const body = options && options.body ? JSON.parse(options.body) : null;
    calls.push([path, body]);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(answer(path, body)) });
  };
  return calls;
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function settle(window) {
  for (let round = 0; round < 6; round += 1) await flush();
  window.eval("state.detached = false;");
}

describe("an IServ outage is shown as a calm state, never as a login problem", () => {
  test.each(["overview", "timetable", "absence", "post", "messenger"])("the %s view carries the outage banner with the last update", (view) => {
    const { window } = loadApp();
    seed(window, { view });
    window.eval("render()");
    const banner = window.document.querySelector("#app .outage-banner");
    expect(banner).not.toBeNull();
    expect(banner.getAttribute("role")).toBe("status");
    expect(banner.textContent).toContain(label(window, "outage.banner.text"));
    expect(banner.textContent).toContain(label(window, "outage.banner.lastUpdate", { time: window.eval(`formatIsoMoment(${JSON.stringify(LAST_SUCCESS)})`) }));
    expect(banner.querySelector(".btn").textContent).toBe(label(window, "outage.banner.retry"));
    expect(window.document.querySelector("#app .toast")).toBeNull();
  });

  test("the overview carries the banner inside its first chapter and calm chapter cards without a retry", () => {
    const { window } = loadApp();
    seed(window, { view: "overview", extra: 'state.letters = { error: "network", tab: "current" }; state.pinboard = { error: "network" };' });
    window.eval("render()");
    const overview = window.document.querySelector("#app .overview");
    expect(overview.querySelector(".outage-banner")).not.toBeNull();
    expect(window.document.querySelector("#app .wrap > .outage-banner")).toBeNull();
    expect(overview.querySelector(".overview-failed")).toBeNull();
    expect(overview.textContent).toContain(label(window, "outage.overview.text"));
    expect(overview.textContent).not.toContain(label(window, "overview.partial.failed"));
  });

  test("the settings view stays without the banner", () => {
    const { window } = loadApp();
    seed(window, { view: "settings" });
    window.eval("render()");
    expect(window.document.querySelector("#app .outage-banner")).toBeNull();
  });

  test("the conferences area carries the banner like every other area and a calm empty state instead of the error", () => {
    const { window } = loadApp();
    seed(window, { view: "conferences", extra: 'state.conferences = { error: "network" };' });
    window.eval("render()");
    expect(window.document.querySelector("#app .wrap > .outage-banner")).not.toBeNull();
    expect(window.document.querySelector("#app .empty.calm")).not.toBeNull();
    expect(window.document.body.textContent).not.toContain(label(window, "conferences.error.title"));
  });

  test("a reachable school shows no banner", () => {
    const { window } = loadApp();
    seed(window, { status: "ok" });
    window.eval("render()");
    expect(window.document.querySelector("#app .outage-banner")).toBeNull();
  });

  test("the banner is styled as a note, not as a warning, and only with logical properties", () => {
    const rule = /\.outage-banner\s*\{([^}]*)\}/.exec(styles);
    expect(rule).not.toBeNull();
    expect(rule[1]).not.toMatch(/--warn|--danger|--bad/);
    expect(styles).not.toMatch(/\.outage-banner[^{]*\{[^}]*(margin|padding|border)-(left|right)/);
  });

  test("with two schools the banner names the school that is down", () => {
    const { window } = loadApp();
    seed(window, { schools: 2 });
    window.eval("render()");
    const banner = window.document.querySelector("#app .outage-banner");
    expect(banner.textContent).toContain(label(window, "outage.banner.schoolText", { school: "Gymnasium Süd" }));
    expect(banner.textContent).not.toContain("Grundschule Nord");
  });

  test("the failed views show the calm outage block instead of the alert block", () => {
    const { window } = loadApp();
    seed(window, { view: "timetable" });
    const view = window.eval("timetableView()");
    expect(view.textContent).toContain(label(window, "outage.empty.title"));
    expect(view.textContent).not.toContain(label(window, "timetable.error.title"));
    expect(view.querySelector(".empty.calm")).not.toBeNull();
    window.eval(`state.letters = { error: "network", tab: "current" }; state.pinboard = { error: "network" }; state.absence = { error: "network", connectionId: ${JSON.stringify(ONE)} }; state.messengerRooms = { error: "network" };`);
    expect(window.eval("postView().textContent")).toContain(label(window, "outage.empty.title"));
    expect(window.eval("absenceView().textContent")).toContain(label(window, "outage.empty.title"));
    expect(window.eval("messengerView().textContent")).toContain(label(window, "outage.empty.title"));
    expect(window.eval(`refreshFailureNote("timetable")`)).toBeNull();
  });

  test("the same failures keep their alert block once the school answers again", () => {
    const { window } = loadApp();
    seed(window, { view: "timetable", status: "ok" });
    const view = window.eval("timetableView()");
    expect(view.textContent).toContain(label(window, "timetable.error.title"));
    expect(view.textContent).not.toContain(label(window, "outage.empty.title"));
  });

  test("the schools block shows the school as unreachable with the time and no warning colour", () => {
    const { window } = loadApp();
    seed(window, { view: "settings", schools: 2 });
    window.eval("render()");
    const row = window.document.querySelector("#app .school-row");
    expect(row).not.toBeNull();
    expect(row.textContent).toContain(label(window, "connection.status.outageSince", { time: window.eval(`formatIsoMoment(${JSON.stringify(SINCE)})`) }));
    expect(row.querySelector(".val.warn")).toBeNull();
    expect(row.querySelector(".school-dot.warn")).toBeNull();
  });

  test("a retry posts once for the school and the banner disappears when the school answers", async () => {
    const { window } = loadApp();
    seed(window);
    await settle(window);
    const calls = stubFetch(window, (path) => {
      if (path === `api/connections/${ONE}/retry`) return { ok: true, status: "ok", since: null, last_success: SINCE, message_key: "api.retry.done" };
      if (path === "api/health") return { configured: true, connection: "ok", language: "de", connections: [schoolRow(ONE, "ok")], modules: {} };
      return { lessons: [], entries: [], letters: [], feed: [], folders: [], rooms: [], items: [], services: [] };
    });
    window.eval("render()");
    window.document.querySelector("#app .outage-banner .btn").click();
    await settle(window);
    expect(calls.filter(([path]) => path === `api/connections/${ONE}/retry`)).toHaveLength(1);
    expect(window.eval(`schoolStatus(${JSON.stringify(ONE)})`)).toBe("ok");
    expect(window.document.querySelector("#app .outage-banner")).toBeNull();
    expect(window.document.querySelector("#app .toast")).toBeNull();
  });

  test("a retry that is too soon shows the answer inside the banner, not as a toast", async () => {
    const { window } = loadApp();
    seed(window);
    await settle(window);
    stubFetch(window, () => ({ ok: false, error: "rate_limited", message_key: "api.retry.tooSoon", message: "" }));
    window.eval("render()");
    window.document.querySelector("#app .outage-banner .btn").click();
    await settle(window);
    const banner = window.document.querySelector("#app .outage-banner");
    expect(banner).not.toBeNull();
    expect(banner.textContent).toContain(label(window, "api.retry.tooSoon"));
    expect(window.document.querySelector("#app .toast")).toBeNull();
  });
});

describe("the reconnect page is reserved for a rejected login", () => {
  test("an outage status never routes to the reconnect page, with one school or with two", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("renderReconnect = () => { state.reconnectShown = true; };");
    expect(window.eval('handleApiFailure(apiError("outage", {}))')).toBe(false);
    expect(window.eval('handleApiFailure(apiError("network", {}))')).toBe(false);
    expect(window.eval("!!state.reconnectShown")).toBe(false);
    seed(window, { schools: 2 });
    expect(window.eval(`handleApiFailure(apiError("outage", {}), ${JSON.stringify(ONE)})`)).toBe(false);
    expect(window.eval("!!state.reconnectShown")).toBe(false);
    expect(window.eval("state.detached")).toBe(false);
  });

  test("a school in outage does not count as one that needs a login when another school fails", async () => {
    const { window } = loadApp();
    seed(window, { schools: 2 });
    await settle(window);
    stubFetch(window, () => ({ configured: true, connection: "ok", language: "de", connections: [schoolRow(ONE, "outage"), schoolRow(TWO, "auth_failed")], modules: {} }));
    window.eval("renderReconnect = () => { state.reconnectShown = true; };");
    window.eval("noteSchoolFailure('', 'auth_failed')");
    await settle(window);
    expect(window.eval("!!state.reconnectShown")).toBe(false);
  });

  test("boot with the whole connection in outage renders the app with the banner instead of a notice", async () => {
    const { window } = loadApp();
    await settle(window);
    stubFetch(window, (path) => {
      if (path === "api/health") return { configured: true, connection: "outage", username: "parent", language: "de", connections: [schoolRow(ONE, "outage", { since: SINCE, last_success: LAST_SUCCESS })], modules: {}, version: "1" };
      if (path === "api/config") return { connections: CONNECTIONS.slice(0, 1), language: "de", notify_services: [] };
      if (path === "api/children") return CHILDREN.slice(0, 1).map((child) => Object.assign({}, child, { unavailable: true }));
      if (path === "api/timetable" || path.startsWith("api/timetable?")) return { error: "network", message_key: "api.outage", message: "" };
      return { error: "network", message_key: "api.outage", message: "" };
    });
    window.eval("renderReconnect = () => { state.reconnectShown = true; };");
    await window.eval("bootOnce()");
    await settle(window);
    expect(window.eval("!!state.reconnectShown")).toBe(false);
    expect(window.document.querySelector("#app .outage-banner")).not.toBeNull();
    expect(window.document.querySelector("#app .screen")).not.toBeNull();
    expect(window.document.getElementById("app").textContent).not.toContain(label(window, "app.error.unreachable.title"));
    expect(window.document.getElementById("app").textContent).not.toContain(label(window, "account.reconnect.title"));
  });
});

describe("coming back to the app while a school is unreachable", () => {
  test("focus and pull to refresh ask for the school status at most once a minute", async () => {
    const { window } = loadApp();
    seed(window);
    await settle(window);
    const calls = stubFetch(window, (path) => {
      if (path === "api/health") return { configured: true, connection: "outage", language: "de", connections: [schoolRow(ONE, "outage", { since: SINCE })], modules: {} };
      if (path === "api/config") return { connections: CONNECTIONS.slice(0, 1), language: "de", notify_services: [] };
      return { lessons: [], entries: [], letters: [], feed: [], folders: [], rooms: [], items: [], services: [] };
    });
    const health = () => calls.filter(([path]) => path === "api/health").length;
    window.eval("schoolStatusRefreshAt = 0;");
    await window.eval("refreshActiveView()");
    await window.eval("refreshEverything()");
    await window.eval("refreshActiveView()");
    await settle(window);
    expect(health()).toBe(1);
    window.eval("schoolStatusRefreshAt = Date.now() - 61000;");
    await window.eval("refreshActiveView()");
    await settle(window);
    expect(health()).toBe(2);
  });
});
