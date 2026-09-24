import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const styles = fs.readFileSync(path.join(dirname, "..", "styles.css"), "utf8");

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

function rule(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(styles);
  return match ? match[2] : null;
}

const PHONE = { service: "notify.mobile_app_phone", name: "Phone", name_source: "entity", category: "mobile" };

function openNotify(services) {
  const app = loadApp();
  app.window.eval(`
    state.config = { notify_services: ${JSON.stringify(services)}, notify_events: {} };
    state.notifyServices = ${JSON.stringify([PHONE])};
    state.notifySupervisor = true;
    openSheet(notifySheet);
  `);
  return app;
}

describe("notification events wait for a device", () => {
  test("without a device the event switches are disabled and dimmed", () => {
    const { document } = openNotify([]);
    const group = document.querySelector(".notify-events");
    expect(group.classList.contains("off")).toBe(true);
    const checks = [...group.querySelectorAll("input[type=checkbox]")];
    expect(checks.length).toBeGreaterThan(0);
    expect(checks.every((check) => check.disabled)).toBe(true);
  });

  test("with a device they are enabled, and removing the last device disables them again", () => {
    const { document } = openNotify([PHONE.service]);
    const group = document.querySelector(".notify-events");
    expect(group.classList.contains("off")).toBe(false);
    expect([...group.querySelectorAll("input")].some((check) => check.disabled)).toBe(false);
    document.querySelector(".notify-chip").click();
    expect(group.classList.contains("off")).toBe(true);
    expect([...group.querySelectorAll("input")].every((check) => check.disabled)).toBe(true);
  });
});

describe("the holiday sheet explains itself before the long list", () => {
  test("the hint and the suggestion note come first, the source stays last", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = { connections: [{ id: "s1", holiday_region: "" }] };
      state.holidayRegions = [{ code: "DE-NI", name_key: "holidays.region.ni" }, { code: "DE-BY", name_key: "holidays.region.by" }];
      state.holidaySuggestion = { region: "DE-NI", confidence: "high", origin: "iserv_postal_code", origin_key: "holidays.suggestion.origin.iservPostalCode", reason: "" };
    `);
    const body = window.eval("holidayRegionSheet()").querySelector(".sheet-body");
    const children = [...body.children];
    expect(children[0].textContent).toBe(label(window, "holidays.settings.hint"));
    expect(children[1].textContent).toBe(label(window, "holidays.suggestion.confirm"));
    expect(children[2].classList.contains("opt-list")).toBe(true);
    expect(children[children.length - 1].textContent).toBe(label(window, "holidays.source"));
  });
});

describe("small settings polish", () => {
  test("the recheck action is a small link, not a full-width button", () => {
    const { window } = loadApp();
    const button = window.eval("modulesRecheckButton()");
    expect(button.classList.contains("link-btn")).toBe(true);
    expect(button.classList.contains("btn")).toBe(false);
    expect(rule(".link-btn")).toMatch(/min-height:\s*44px/);
  });

  test("course code and facts keep their gap in both directions", () => {
    expect(rule(".course-check .course-code")).toBeNull();
    expect(rule(".course-check > span")).toMatch(/column-gap:/);
  });

  test("the up and down buttons do not share hit area", () => {
    expect(rule(".order-btns")).toMatch(/gap:\s*var\(--s-4\)/);
    expect(rule(".order-btns .icon-btn::after")).toMatch(/inset:\s*-4px/);
  });
});

describe("the notification events explain why they wait", () => {
  const PHONE = { service: "notify.mobile_app_phone", name: "Phone", category: "mobile" };

  test("a one-line hint shows while no device is chosen and goes once one is", () => {
    const { window, document } = loadApp();
    window.eval(`
      state.config = { notify_services: [], notify_events: {} };
      state.notifyServices = ${JSON.stringify([PHONE])};
      state.notifySupervisor = true;
      openSheet(notifySheet);
    `);
    const hint = document.querySelector(".notify-events-hint");
    expect(hint.textContent).toBe(label(window, "settings.notify.events.needDevice"));
    expect(hint.hidden).toBe(false);
    expect(hint.nextElementSibling.classList.contains("notify-events")).toBe(true);
    expect([...document.querySelectorAll(".notify-events input")].every((check) => check.disabled)).toBe(true);
    window.eval(`state.sheetForm.services = [${JSON.stringify(PHONE.service)}]; rerender();`);
    expect(document.querySelector(".notify-events-hint").hidden).toBe(true);
    expect([...document.querySelectorAll(".notify-events input")].some((check) => check.disabled)).toBe(false);
  });
});
