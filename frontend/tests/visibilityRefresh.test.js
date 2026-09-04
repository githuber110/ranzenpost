import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[C04] visibility refresh: app does not age in the background", () => {
  test("a visibilitychange event is skipped while a sheet is open", () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "post";
      state.postTab = "pinboard";
      state.sheet = () => document.createElement("div");
      lastVisibilityRefreshAt = Date.now() - 6 * 60 * 1000;
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      setupVisibilityRefresh();
    `);
    window.document.dispatchEvent(new window.Event("visibilitychange"));
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("refreshActiveView is skipped while an absence form is open", () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadAbsences = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "absence";
      state.absenceForm = { type: "sick" };
    `);
    window.eval("if (!hasOpenFormGuard()) refreshActiveView();");
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("refreshActiveView is skipped while a letter is open in detail view", () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadLetters = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "letters";
      state.letterDetail = { letter: {}, detail: {} };
    `);
    window.eval("if (!hasOpenFormGuard()) refreshActiveView();");
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("refreshActiveView calls the load function matching the active view when nothing is open", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "post";
      state.postTab = "pinboard";
    `);
    await window.eval("refreshActiveView()");
    expect(window.eval("window.__calls")).toBe(1);
  });

  test("a visibilitychange event past the 5-minute threshold triggers a silent reload", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadConferences = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "conferences";
      lastVisibilityRefreshAt = Date.now() - 6 * 60 * 1000;
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      setupVisibilityRefresh();
    `);
    window.document.dispatchEvent(new window.Event("visibilitychange"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(1);
  });

  test("a visibilitychange event inside the 5-minute threshold does nothing", () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadConferences = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "conferences";
      lastVisibilityRefreshAt = Date.now();
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      setupVisibilityRefresh();
    `);
    window.document.dispatchEvent(new window.Event("visibilitychange"));
    expect(window.eval("window.__calls")).toBe(0);
  });
});
