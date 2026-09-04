import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P127] letters: view-entry reset via setView", () => {
  test("leaving Archiv and returning through the view switch lands back on Aktuell", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.lettersTab = "archive";
      setView("overview");
      setView("post");
    `);
    expect(window.eval("state.lettersTab")).toBe("current");
  });

  test("multi-select is switched off after navigating away and back", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "post";
      state.lettersSelectMode = true;
      state.lettersSelected = ["1:2"];
      setView("overview");
      setView("post");
    `);
    expect(window.eval("state.lettersSelectMode")).toBe(false);
    expect(window.eval("state.lettersSelected")).toEqual([]);
  });

  test("a typed search query is cleared after navigating away and back", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "post";
      state.lettersSearch = "Sportfest";
      setView("overview");
      setView("post");
    `);
    expect(window.eval("state.lettersSearch")).toBe("");
  });

  test("switching tabs within the letters view does not reset selection or search", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "post";
      state.lettersTab = "current";
      state.lettersSearch = "Sportfest";
      state.letters = { tab: "archive", letters: [] };
      setLettersFolder("archive");
    `);
    expect(window.eval("state.lettersTab")).toBe("archive");
    expect(window.eval("state.lettersSearch")).toBe("Sportfest");
  });
});
