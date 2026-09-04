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

const SEARCHABLE = [
  { service: "notify.mobile_app_a", name: "Device A", name_source: "entity", category: "mobile" },
  { service: "notify.mobile_app_b", name: "Device B", name_source: "entity", category: "mobile" },
  { service: "notify.mobile_app_c", name: "Device C", name_source: "entity", category: "mobile" },
  { service: "notify.notify", name: null, name_source: null, category: "group" },
  { service: "notify.custom_webhook_a", name: null, name_source: null, category: "other" },
  { service: "notify.custom_webhook_b", name: null, name_source: null, category: "other" },
];

function openNotifySheet(services, { supervisor = true, config = {} } = {}) {
  const app = loadApp();
  const supervisorLiteral = supervisor === null ? "null" : supervisor ? "true" : "false";
  app.window.eval(`
    state.config = ${JSON.stringify(Object.assign({ notify_services: [], notify_events: {} }, config))};
    state.notifyServices = ${JSON.stringify(services)};
    state.notifySupervisor = ${supervisorLiteral};
    openSheet(notifySheet);
  `);
  return app;
}

function openPicker(app) {
  app.document.querySelector(".notify-pick-open").click();
  return app;
}

function overlines(document) {
  return [...document.querySelectorAll(".section-head .overline")].map((node) => node.textContent);
}

function rowsOf(document, category) {
  return [...document.querySelectorAll(`.notify-services-group[data-category="${category}"] .notify-row`)];
}

function chipsOf(document) {
  return [...document.querySelectorAll(".notify-chip")];
}

describe("[P208] notification sheet: chip list + nested picker replace the old free-form form", () => {
  test("the deleted persistent-notification default row, free-text field and manual group are gone", () => {
    const { document } = openNotifySheet(ENRICHED);

    expect(document.querySelector(".notify-default-group")).toBeNull();
    expect(document.querySelector(".notify-advanced")).toBeNull();
    expect(document.querySelector(".notify-advanced-toggle")).toBeNull();
    expect(document.querySelector(".notify-manual-group")).toBeNull();
    expect(document.body.textContent).not.toContain("Mitteilung in Home Assistant");
    expect(document.body.textContent).not.toContain("Anderes Ziel hinzufügen");
  });

  test("the persistent category is filtered out of the picker options entirely", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);

    expect(app.document.querySelector('.notify-services-group[data-category="persistent"]')).toBeNull();
    expect(app.document.body.textContent).not.toContain("notify.persistent_notification");
  });

  test("with no target chosen the chip area shows the empty-state hint instead of chips", () => {
    const { document } = openNotifySheet(ENRICHED);

    expect(chipsOf(document).length).toBe(0);
    expect(document.querySelector(".notify-empty").textContent).toBe(
      "Noch kein Ziel gewählt – ohne Ziel wird nichts gesendet."
    );
  });

  test("chosen targets render as chips with the friendly name via notifyLabel", () => {
    const { document } = openNotifySheet(ENRICHED, {
      config: { notify_services: ["notify.mobile_app_test_phone", "notify.custom_webhook"] },
    });

    const chips = chipsOf(document);
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toContain("Test Phone");
    expect(chips[0].getAttribute("aria-label")).toBe("Test Phone entfernen");
    expect(chips[1].textContent).toContain("notify.custom_webhook");
  });

  test("clicking a chip removes that target from the draft", () => {
    const { window, document } = openNotifySheet(ENRICHED, {
      config: { notify_services: ["notify.mobile_app_test_phone", "notify.custom_webhook"] },
    });

    chipsOf(document)[0].click();

    expect(chipsOf(document).length).toBe(1);
    expect(chipsOf(document)[0].textContent).toContain("notify.custom_webhook");
    expect(window.eval("state.sheetForm.services")).toEqual(["notify.custom_webhook"]);
  });

  test("the picker groups options by category under their heading, each row shows friendly name and raw id", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);
    const { document } = app;

    const heads = overlines(document);
    expect(heads).toContain("Push aufs Handy");
    expect(heads).toContain("An alle Geräte");
    expect(heads).toContain("Weitere Dienste");

    expect(rowsOf(document, "mobile").length).toBe(3);
    expect(rowsOf(document, "group").length).toBe(1);
    expect(rowsOf(document, "other").length).toBe(1);

    const row = rowsOf(document, "mobile")[0];
    expect(row.querySelector("b").textContent).toBe("Test Phone");
    expect(row.querySelector(".notify-id").textContent).toBe("notify.mobile_app_test_phone");
  });

  test("keeps the technical id as the headline when Home Assistant reports no name", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);
    const row = rowsOf(app.document, "mobile")[2];

    expect(row.querySelector("b").textContent).toBe("notify.mobile_app_unnamed_device");
    expect(row.querySelector(".notify-id")).toBeNull();
  });

  test("checking a target in the picker adds it and is reflected back once the picker closes", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);

    rowsOf(app.document, "mobile")[1].querySelector("input[type=checkbox]").click();
    app.document.querySelector(".sheet-close").click();

    expect(chipsOf(app.document).length).toBe(1);
    expect(chipsOf(app.document)[0].textContent).toContain("Test Tablet");
    expect(app.window.eval("state.sheetForm.services")).toEqual(["notify.mobile_app_test_tablet"]);
  });

  test("[P208 follow-up] closing the picker is a plain go-back, not a discard-changes prompt", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);

    rowsOf(app.document, "mobile")[1].querySelector("input[type=checkbox]").click();
    app.document.querySelector(".sheet-close").click();

    expect(app.document.querySelector(".sheet-confirm")).toBeNull();
    expect(chipsOf(app.document).length).toBe(1);
    expect(chipsOf(app.document)[0].textContent).toContain("Test Tablet");
  });

  test("below the search threshold no search field is rendered", () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);

    expect(app.document.querySelector(".search-input")).toBeNull();
  });

  test("at the search threshold a search field is rendered", () => {
    const app = openNotifySheet(SEARCHABLE);
    openPicker(app);

    expect(app.document.querySelector(".search-input")).not.toBeNull();
  });

  test("every target carries its own test button that posts exactly that service", async () => {
    const app = openNotifySheet(ENRICHED);
    openPicker(app);
    const { window, document } = app;
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
    const app = openNotifySheet(ENRICHED);
    openPicker(app);
    const { window, document } = app;
    window.fetch = () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: false, message_key: "api.notify.failed" }) });

    document.querySelector("button.notify-test").click();
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.toast.message")).toBe("Senden fehlgeschlagen. Prüfe den Dienst-Namen.");
  });

  test("an unknown supervisor connection is explained instead of showing an empty box", () => {
    const { document } = openNotifySheet([], { supervisor: null });

    expect(document.querySelector(".note").textContent).toContain("Verbindung zu Home Assistant wird geprüft…");
    expect(document.querySelector(".notify-pick-open").disabled).toBe(true);
  });

  test("a missing supervisor connection is explained instead of showing an empty box", () => {
    const { document } = openNotifySheet([], { supervisor: false });

    const hint = [...document.querySelectorAll(".dlg-text")].find((node) =>
      node.textContent.includes("Die Geräte-Liste erscheint, sobald die App als Add-on in Home Assistant läuft.")
    );
    expect(hint).not.toBeUndefined();
    expect(document.querySelector(".notify-pick-open").disabled).toBe(true);
  });

  test("a reachable supervisor without push targets explains what is missing", () => {
    const { document } = openNotifySheet([], { supervisor: true });

    const hint = [...document.querySelectorAll(".dlg-text")].find((node) =>
      node.textContent.includes("Installiere die Home-Assistant-App auf dem Handy")
    );
    expect(hint).not.toBeUndefined();
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
    const app = openNotifySheet(ENRICHED, { config: { notify_services: ["notify.custom_webhook"] } });
    openPicker(app);
    const { window, document } = app;
    let posted = null;
    window.fetch = (url, options) => {
      if (String(url).includes("api/config") && options && options.method === "POST") {
        posted = JSON.parse(options.body);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      return Promise.reject(new Error("network disabled in tests"));
    };

    rowsOf(document, "mobile")[0].querySelector("input[type=checkbox]").click();
    document.querySelector(".sheet-close").click();
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

  test("[P208] no target at all now names the absence of a target, not the old Home Assistant default", () => {
    const { window } = openNotifySheet(ENRICHED);
    expect(window.eval("notifyServicesSummaryLabel([])")).toBe("Kein Ziel");
  });
});
