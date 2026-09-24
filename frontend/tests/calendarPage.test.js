import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

const SUBSCRIPTION = {
  id: "sub-1",
  child_key: `${ONE}:c1`,
  label: "7b",
  components: ["timetable"],
  color: "#135859",
  token: "token-1",
  path: "/calendar/token-1.ics",
};

function payload(subscriptions) {
  return {
    subscriptions,
    components: ["timetable", "school_holidays"],
    holiday_regions: { [ONE]: "DE-NI" },
    port: 8100,
    host: "ha.example",
    host_source: "config_entry",
    supervisor: true,
    port_open: true,
  };
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

async function quiet(window) {
  for (let round = 0; round < 6; round += 1) await tick();
  window.clearTimeout(window.eval("bootWatchdog"));
  window.eval("state.detached = false;");
}

async function prepare(window, { many = false, subscriptions = [SUBSCRIPTION] } = {}) {
  await quiet(window);
  const connections = [{ id: ONE, school_name: "School One", setup_complete: true, phones: [], subjects: {}, teachers: {} }];
  const children = [{ key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, name: "Mia Example", class_name: "7b" }];
  if (many) {
    connections.push({ id: TWO, school_name: "School Two", setup_complete: true, phones: [], subjects: {}, teachers: {} });
    children.push({ key: `${TWO}:c1`, child_id: "c1", connection_id: TWO, name: "Tom Example", class_name: "3a" });
  }
  window.eval(`
    state.config = { connections: ${JSON.stringify(connections)}, notify_services: [], notify_events: {} };
    state.children = ${JSON.stringify(children)};
    state.childId = ${JSON.stringify(`${ONE}:c1`)};
    state.schools = ${JSON.stringify(connections.map((entry) => ({ id: entry.id, name: entry.school_name, status: "ok", setup_complete: true })))};
    state.haStatus = { data: { connected: true }, error: false };
  `);
  window.fetch = (url) => {
    const target = String(url);
    if (target.includes("api/calendar/subscriptions")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload(subscriptions)) });
    }
    return Promise.reject(new Error(`unexpected request ${target}`));
  };
}

function filledButtons(node) {
  return [...node.querySelectorAll(".btn")].filter(
    (button) => !button.classList.contains("ghost") && !button.classList.contains("destructive")
  );
}

describe("the calendar subscription is a full settings page", () => {
  for (const many of [false, true]) {
    test(`the settings row opens the page with the back button (${many ? "two schools" : "one school"})`, async () => {
      const { window, document } = loadApp();
      await prepare(window, { many });
      window.eval('state.view = "settings"; render();');
      document.querySelector(".calendar-setting").click();
      await tick();
      await tick();

      expect(window.eval("state.settingsPage")).toBe("calendar");
      expect(window.eval("state.sheet")).toBe(null);
      expect(document.querySelector(".scrim")).toBeNull();
      expect(document.querySelector(".calendar-page .cal-card")).not.toBeNull();
      expect(document.querySelector(".header-title").textContent).toBe(label(window, "calendar.subscribe.title"));
      document.querySelector(".header-back").click();
      expect(window.eval("state.settingsPage")).toBe(null);
      expect(window.eval("state.view")).toBe("settings");
      expect(document.querySelector(".calendar-setting")).not.toBeNull();
    });
  }

  test("the timetable header icon opens the same page and back returns to the timetable", async () => {
    const { window, document } = loadApp();
    await prepare(window);
    window.eval('state.view = "timetable"; state.timetable = { lessons: [], period_times: {} }; render();');
    document.querySelector(`.header-actions .icon-btn[aria-label="${label(window, "calendar.subscribe.open")}"]`).click();
    await tick();
    await tick();

    expect(window.eval("state.view")).toBe("settings");
    expect(window.eval("state.settingsPage")).toBe("calendar");
    expect(document.querySelector(".calendar-page")).not.toBeNull();
    document.querySelector(".header-back").click();
    expect(window.eval("state.view")).toBe("timetable");
    expect(window.eval("state.settingsPage")).toBe(null);
  });

  test("every child card carries at most one filled button in each state", async () => {
    const { window } = loadApp();
    await prepare(window, { many: true });
    window.eval(`state.calendar = { data: ${JSON.stringify(payload([SUBSCRIPTION]))}, error: false };`);
    const created = window.eval("calendarPageView()");
    const cards = [...created.querySelectorAll(".cal-card")];
    expect(cards.length).toBe(2);
    expect(filledButtons(cards[0]).map((node) => node.classList.contains("cal-add"))).toEqual([true]);
    expect(filledButtons(cards[1]).map((node) => node.textContent)).toEqual([label(window, "calendar.subscribe.create")]);

    window.eval("state.calendarDraft = calendarEditDraft(state.calendar.data.subscriptions[0], state.children[0]);");
    const editing = window.eval("calendarPageView()");
    expect(filledButtons(editing.querySelectorAll(".cal-card")[0]).length).toBe(1);
  });

  test("a confirmation over the page leaves the page in place instead of reopening a sheet", async () => {
    const { window } = loadApp();
    await prepare(window);
    window.eval(`state.calendar = { data: ${JSON.stringify(payload([SUBSCRIPTION]))}, error: false }; state.view = "settings"; state.settingsPage = "calendar"; render();`);
    const pending = window.eval(`rotateCalendarSubscription(${JSON.stringify(SUBSCRIPTION)})`);
    const dialog = window.document.querySelector(".sheet");
    [...dialog.querySelectorAll("button")].find((node) => node.textContent === label(window, "common.cancel")).click();
    await pending;

    expect(window.eval("state.sheet")).toBe(null);
    expect(window.eval("state.settingsPage")).toBe("calendar");
    expect(window.document.querySelector(".calendar-page")).not.toBeNull();
  });

  test("choosing the holiday region leaves the page for the settings list with the region sheet", async () => {
    const { window } = loadApp();
    await prepare(window);
    window.eval('state.view = "settings"; state.settingsPage = "calendar"; openCalendarRegionSetting();');
    expect(window.eval("state.settingsPage")).toBe(null);
    expect(window.eval("state.sheet === holidayRegionSheet")).toBe(true);
  });
});
