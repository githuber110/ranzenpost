import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ENRICHED = [
  { service: "notify.mobile_app_test_phone", name: "Test Phone", name_source: "entity", category: "mobile" },
  { service: "notify.mobile_app_test_tablet", name: "Test Tablet", name_source: "device_tracker", category: "mobile" },
  { service: "notify.mobile_app_unnamed_device", name: null, name_source: null, category: "mobile" },
  { service: "notify.persistent_notification", name: null, name_source: null, category: "persistent" },
  { service: "notify.notify", name: null, name_source: null, category: "group" },
  { service: "notify.custom_webhook", name: null, name_source: null, category: "other" },
];

function openNotifySheet(services, { supervisor = true, config = {} } = {}) {
  const app = loadApp();
  app.window.eval(`
    state.config = ${JSON.stringify(Object.assign({ notify_services: [], notify_events: {} }, config))};
    state.notifyServices = ${JSON.stringify(services)};
    state.notifySupervisor = ${supervisor ? "true" : "false"};
    openSheet(notifySheet);
  `);
  return app;
}

function overlines(document) {
  return [...document.querySelectorAll(".section-head .overline")]
    .filter((node) => !node.closest("[hidden]"))
    .map((node) => node.textContent);
}

function rowsOf(document, category) {
  return [...document.querySelectorAll(`.notify-services-group[data-category="${category}"] .notify-row`)];
}

describe("[P154] notification sheet presents real targets instead of raw entity ids", () => {
  test("groups the discovered targets by category, each under its own heading", () => {
    const { document } = openNotifySheet(ENRICHED);

    const heads = overlines(document);
    expect(heads).toContain("Wohin?");
    expect(heads).toContain("Push aufs Handy");
    expect(heads).toContain("In Home Assistant");
    expect(heads).toContain("An alle Geräte");
    expect(heads).toContain("Weitere Dienste");
    expect(heads).toContain("Wobei benachrichtigen?");

    expect(rowsOf(document, "mobile").length).toBe(3);
    expect(rowsOf(document, "persistent").length).toBe(1);
    expect(rowsOf(document, "group").length).toBe(1);
    expect(rowsOf(document, "other").length).toBe(1);
  });

  test("shows the friendly name as the headline and the technical id underneath it", () => {
    const { document } = openNotifySheet(ENRICHED);
    const row = rowsOf(document, "mobile")[0];

    expect(row.querySelector("b").textContent).toBe("Test Phone");
    expect(row.querySelector(".notify-id").textContent).toBe("notify.mobile_app_test_phone");
  });

  test("keeps the technical id as the headline when Home Assistant reports no name", () => {
    const { document } = openNotifySheet(ENRICHED);
    const row = rowsOf(document, "mobile")[2];

    expect(row.querySelector("b").textContent).toBe("notify.mobile_app_unnamed_device");
    expect(row.querySelector(".notify-id")).toBeNull();
  });

  test("the fixed Home Assistant default row stays selectable next to the discovered targets", () => {
    const { window, document } = openNotifySheet(ENRICHED);
    const defaultRow = document.querySelector(".notify-default-group .notify-row");
    expect(defaultRow.textContent).toContain("Mitteilung in Home Assistant (Standard)");

    defaultRow.querySelector("input[type=checkbox]").click();
    rowsOf(document, "mobile")[1].querySelector("input[type=checkbox]").click();

    expect(window.eval("state.sheetForm.services")).toEqual([
      "persistent_notification.create",
      "notify.mobile_app_test_tablet",
    ]);
  });

  test("every target carries its own test button that posts exactly that service", async () => {
    const { window, document } = openNotifySheet(ENRICHED);
    const calls = [];
    let release = null;
    window.fetch = (url, options) => {
      calls.push({ url: String(url), body: JSON.parse(options.body) });
      return new Promise((resolve) => {
        release = () => resolve({ ok: true, json: () => Promise.resolve({ ok: true, message_key: "api.notify.sent" }) });
      });
    };

    const button = rowsOf(document, "mobile")[1].querySelector("button.notify-test");
    expect(button.textContent).toBe("Test");
    button.click();

    expect(calls.length).toBe(1);
    expect(calls[0].url).toContain("api/notify-test");
    expect(calls[0].body.service).toBe("notify.mobile_app_test_tablet");
    expect(calls[0].body.language).toBe("de");
    expect(button.disabled).toBe(true);
    expect(button.querySelector(".spin")).not.toBeNull();

    button.click();
    expect(calls.length).toBe(1);

    release();
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(window.eval("state.toast.kind")).toBe("good");
    expect(window.eval("state.toast.message")).toBe("Testbenachrichtigung gesendet.");
  });

  test("a failing test reports the backend message instead of pretending success", async () => {
    const { window, document } = openNotifySheet(ENRICHED);
    window.fetch = () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: false, message_key: "api.notify.failed" }) });

    document.querySelector(".notify-default-group button.notify-test").click();
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.toast.message")).toBe("Senden fehlgeschlagen. Prüfe den Dienst-Namen.");
  });

  test("the free text field is a collapsed fallback that only opens on demand", () => {
    const { document } = openNotifySheet(ENRICHED);
    const panel = document.querySelector(".notify-advanced");
    const toggle = document.querySelector(".notify-advanced-toggle");

    expect(panel.hidden).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toContain("Anderes Ziel hinzufügen");

    toggle.click();

    expect(panel.hidden).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.querySelector(".dlg-text").textContent).toContain("notify.my_service");
  });

  test("a manually added target becomes its own removable group", () => {
    const { window, document } = openNotifySheet(ENRICHED);
    document.querySelector(".notify-advanced-toggle").click();

    const input = document.querySelector('.notify-advanced input[aria-label="Entität hinzufügen"]');
    const addButton = [...document.querySelectorAll(".notify-advanced button")].find((node) =>
      node.textContent.includes("Entität hinzufügen")
    );
    input.value = "notify.custom_device";
    addButton.click();

    const group = document.querySelector(".notify-manual-group");
    expect(group.hidden).toBe(false);
    expect(overlines(document)).toContain("Selbst hinzugefügt");
    expect(group.textContent).toContain("notify.custom_device");
    expect(window.eval("state.sheetForm.services")).toEqual(["notify.custom_device"]);
    expect(group.querySelector("button.notify-test")).not.toBeNull();

    group.querySelector("button.notify-remove").click();

    expect(document.querySelector(".notify-manual-group").hidden).toBe(true);
    expect(window.eval("state.sheetForm.services")).toEqual([]);
  });

  test("a missing supervisor connection is explained instead of showing an empty box", () => {
    const { document } = openNotifySheet([], { supervisor: false });

    const hint = [...document.querySelectorAll(".dlg-text")].find((node) =>
      node.textContent.includes("Die Geräte-Liste erscheint, sobald die App als Add-on in Home Assistant läuft.")
    );
    expect(hint).not.toBeUndefined();
    expect(document.querySelectorAll(".notify-services-group").length).toBe(0);
    expect(document.querySelectorAll(".notify-default-group .notify-row").length).toBe(1);
  });

  test("a reachable supervisor without push targets explains what is missing", () => {
    const { document } = openNotifySheet([], { supervisor: true });

    const hint = [...document.querySelectorAll(".dlg-text")].find((node) =>
      node.textContent.includes("Installiere die Home-Assistant-App auf dem Handy")
    );
    expect(hint).not.toBeUndefined();
    expect(document.querySelectorAll(".notify-services-group").length).toBe(0);
  });

  test("the event section keeps all four events switched on by default", () => {
    const { window, document } = openNotifySheet(ENRICHED);
    const groups = [...document.querySelectorAll(".field-group")];
    const eventGroup = groups[groups.length - 1];
    const checks = [...eventGroup.querySelectorAll("input[type=checkbox]")];

    expect(checks.length).toBe(4);
    expect(checks.every((check) => check.checked)).toBe(true);
    expect(eventGroup.textContent).toContain("Stundenplan-Änderungen");
    expect(window.eval("state.sheetForm.events")).toEqual({});
  });

  test("saving sends every selected target to the config API", () => {
    const { window, document } = openNotifySheet(ENRICHED, { config: { notify_services: ["notify.custom_webhook"] } });
    let posted = null;
    window.fetch = (url, options) => {
      if (String(url).includes("api/config") && options && options.method === "POST") {
        posted = JSON.parse(options.body);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      return Promise.reject(new Error("network disabled in tests"));
    };

    rowsOf(document, "mobile")[0].querySelector("input[type=checkbox]").click();
    document.querySelector(".sheet-foot button").click();

    return new Promise((resolve) => window.setTimeout(resolve, 0)).then(() => {
      expect(posted.notify_services.sort()).toEqual(
        ["notify.custom_webhook", "notify.mobile_app_test_phone"].sort()
      );
    });
  });
});

describe("[P154] the settings row names the device instead of counting services", () => {
  test("a single target shows its friendly name", () => {
    const { window } = openNotifySheet(ENRICHED);
    const label = window.eval(
      'notifyServicesSummaryLabel(["notify.mobile_app_test_phone"])'
    );
    expect(label).toBe("Test Phone");
  });

  test("several targets show the first device plus the number of further ones", () => {
    const { window } = openNotifySheet(ENRICHED);
    const label = window.eval(
      'notifyServicesSummaryLabel(["notify.mobile_app_test_phone", "notify.notify", "notify.custom_webhook"])'
    );
    expect(label).toBe("Test Phone +2");
  });

  test("an unknown target falls back to its technical id", () => {
    const { window } = openNotifySheet(ENRICHED);
    expect(window.eval('notifyServicesSummaryLabel(["notify.something_else"])')).toBe("notify.something_else");
  });

  test("no target at all still names the Home Assistant default", () => {
    const { window } = openNotifySheet(ENRICHED);
    expect(window.eval("notifyServicesSummaryLabel([])")).toBe("Home Assistant");
  });
});
