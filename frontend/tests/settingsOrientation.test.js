import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[C17] settings orientation: remembers where it was opened from", () => {
  test("gear tap from timetable stores the origin, settings back returns there", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.children = [];
        state.absence = { data: { children: [], rules: {} } };
        state.view = "timetable";
        const gear = header("timetable").querySelector('.icon-btn[aria-label="Einstellungen"]');
        gear.click();
        const viewAfterGear = state.view;
        state.config = {};
        const backBtn = header("settings").querySelector(".icon-btn[aria-label='Zurück']");
        backBtn.click();
        return { viewAfterGear, viewAfterBack: state.view };
      })()
    `);
    expect(result.viewAfterGear).toBe("settings");
    expect(result.viewAfterBack).toBe("timetable");
  });

  test("no stored origin falls back to overview", () => {
    const { window } = loadApp();
    const result = window.eval(`
      (function () {
        state.config = {};
        state.settingsReturn = null;
        setView("settings");
        const backBtn = header("settings").querySelector(".icon-btn[aria-label='Zurück']");
        backBtn.click();
        return state.view;
      })()
    `);
    expect(result).toBe("overview");
  });

  test("the settings gear itself is hidden while already on the settings view", () => {
    const { window } = loadApp();
    const gear = window.eval(`header("settings").querySelector('.icon-btn[aria-label="Einstellungen"]')`);
    expect(gear).toBeNull();
  });

  test("the gear is shown on every other view", () => {
    const { window } = loadApp();
    for (const view of ["overview", "timetable", "absence", "letters", "pinboard", "conferences"]) {
      const gear = window.eval(`header(${JSON.stringify(view)}).querySelector('.icon-btn[aria-label="Einstellungen"]')`);
      expect(gear).not.toBeNull();
    }
  });
});

describe("[P188] the settings wear the same compact head as every other screen", () => {
  test("the title and the back arrow live in the header bar, level with the action row", () => {
    const { window } = loadApp();
    const head = window.eval(`header("settings")`);
    const title = head.querySelector(".header-title-row .header-title");
    expect(title.textContent).toBe(window.eval(`t("settings.title")`));
    expect(head.querySelector(".header-title-row .header-back")).not.toBeNull();
  });

  test("the settings body carries no second head of its own", () => {
    const { window } = loadApp();
    const view = window.eval(`(function () { state.config = {}; return settingsView(); })()`);
    expect(view.querySelector(".list-head")).toBeNull();
    expect(view.querySelector(".page-title")).toBeNull();
    expect(view.firstElementChild.className).toBe("settings-group");
  });

  test("the old subpage head is gone for good", () => {
    const { window } = loadApp();
    expect(window.eval(`typeof subpageHead`)).toBe("undefined");
  });
});

describe("[C17] Elternsprechtage: the Uebersicht tab stays aria-current", () => {
  test("conferences view keeps the overview tab marked current, settings has none active", () => {
    const { window } = loadApp();
    const conferencesTab = window.eval(`
      (function () {
        state.view = "conferences";
        const bar = tabbar();
        const overviewBtn = [...bar.querySelectorAll(".tab")][0];
        return overviewBtn.getAttribute("aria-current");
      })()
    `);
    expect(conferencesTab).toBe("page");

    const settingsActive = window.eval(`
      (function () {
        state.view = "settings";
        const bar = tabbar();
        return [...bar.querySelectorAll(".tab")].some((btn) => btn.getAttribute("aria-current") === "page");
      })()
    `);
    expect(settingsActive).toBe(false);
  });
});
