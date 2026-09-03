import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function startForm(window, type, data) {
  const run = window.eval(
    "(function (type, data) { state.absence = { data }; startAbsenceForm(type); return state.absenceForm; })"
  );
  return run(type, data);
}

describe("[C05] dirty-guard: leaving an absence form without changes never prompts", () => {
  test("back-tap with untouched defaults calls after() immediately, no confirm sheet", () => {
    const { window } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], rules: {}, deregister_options: ["bus"] });
    const calledAfter = window.eval(`
      (function () {
        let called = false;
        leaveAbsenceForm(() => { called = true; });
        return { called, sheetOpen: !!state.sheet };
      })()
    `);
    expect(calledAfter.called).toBe(true);
    expect(calledAfter.sheetOpen).toBe(false);
  });

  test("back-tap after editing a field opens a confirm sheet and does NOT call after() yet", () => {
    const { window } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], rules: {}, deregister_options: ["bus"] });
    const result = window.eval(`
      (function () {
        state.absenceForm.date = "2099-01-01";
        let called = false;
        leaveAbsenceForm(() => { called = true; });
        return { called, sheetOpen: !!state.sheet };
      })()
    `);
    expect(result.called).toBe(false);
    expect(result.sheetOpen).toBe(true);
  });

  test("confirming the discard dialog then calls after()", async () => {
    const { window } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], rules: {}, deregister_options: ["bus"] });
    const run = window.eval(`
      (function () {
        state.absenceForm.date = "2099-01-01";
        let called = false;
        leaveAbsenceForm(() => { called = true; });
        const confirmBtn = document.querySelector(".sheet .btn.destructive");
        confirmBtn.click();
        return new Promise((resolve) => setTimeout(() => resolve(called), 0));
      })()
    `);
    expect(await run).toBe(true);
  });

  test("cancelling the discard dialog does NOT call after(), form stays open", async () => {
    const { window } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], rules: {}, deregister_options: ["bus"] });
    const run = window.eval(`
      (function () {
        state.absenceForm.date = "2099-01-01";
        let called = false;
        leaveAbsenceForm(() => { called = true; });
        const cancelBtn = document.querySelector(".sheet .btn.ghost");
        cancelBtn.click();
        return new Promise((resolve) => setTimeout(() => resolve({ called, formStillOpen: !!state.absenceForm }), 0));
      })()
    `);
    const result = await run;
    expect(result.called).toBe(false);
    expect(result.formStillOpen).toBe(true);
  });
});

describe("[C05] the wizard replaces the screen shell: no tab bar, own header", () => {
  test("render() mounts the wizard node alone, without .screen and without .tabbar", () => {
    const { window, document } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] });
    const app = document.getElementById("app");
    expect(app.querySelector(".sw")).not.toBeNull();
    expect(app.querySelector(".tabbar")).toBeNull();
    expect(app.querySelector(".screen")).toBeNull();
  });

  test("the wizard header carries its own back and exit buttons", () => {
    const { window, document } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] });
    const head = document.getElementById("app").querySelector(".sw-head");
    expect(head.querySelector(".sw-back").getAttribute("aria-label")).toBe("Ein Schritt zurück");
    expect(head.querySelector(".sw-head-actions button").getAttribute("aria-label")).toBe("Meldung abbrechen");
    expect(head.querySelector(".sw-title").textContent).toBe("Abmeldung");
  });

  test("header('absence') is back to the plain list title once the wizard owns the form", () => {
    const { window } = loadApp();
    startForm(window, "deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] });
    const bar = window.eval("header('absence')");
    expect(bar.querySelector(".header-title").textContent).toBe("Abwesenheit");
    expect(bar.querySelector(".icon-btn.header-back")).toBeNull();
  });

  test("conferencesView no longer renders its own back + title (header() carries it)", () => {
    const { window } = loadApp();
    const view = window.eval("(function () { state.conferences = { items: [] }; return conferencesView(); })()");
    expect(view.querySelector(".icon-btn[aria-label='Zurück']")).toBeNull();
  });

  test("header('conferences') wraps back + title for the conferences view", () => {
    const { window } = loadApp();
    const bar = window.eval("(function () { state.conferences = { items: [] }; return header('conferences'); })()");
    const row = bar.querySelector(".header-title-row");
    expect(row).not.toBeNull();
    expect(row.querySelector(".icon-btn.header-back[aria-label='Zurück']")).not.toBeNull();
  });

  test("settingsView wraps back + title in .list-head", () => {
    const { window } = loadApp();
    const view = window.eval("(function () { state.config = {}; return settingsView(); })()");
    const head = view.querySelector(".list-head");
    expect(head).not.toBeNull();
  });
});
