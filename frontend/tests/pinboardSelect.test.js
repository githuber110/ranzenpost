import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function pinboardData() {
  return {
    folders: [],
    feed: [
      { id: 1, title: "Sportfest", text: "Details zum Sportfest", unread: true },
      { id: 2, title: "Elternabend", text: "Einladung", unread: false },
    ],
  };
}

describe("[P128] pinboard: Auswählen/Fertig toggle in the sticky toolbar", () => {
  function renderPinboard(window, data) {
    const run = window.eval("(function (data) { state.pinboard = data; return pinboardView(); })");
    return run(data);
  }

  test("[P156] Auswählen button is present, disappears in multi-select, and the sticky bar's round button ends selection", () => {
    const { window } = loadApp();
    const data = pinboardData();
    const view = renderPinboard(window, data);
    const toolsButtons = Array.from(view.querySelectorAll(".letters-tools button")).map((b) => b.textContent);
    expect(toolsButtons).toContain("Auswählen");
    expect(window.eval("state.pinboardSelectMode")).toBe(false);

    window.eval("togglePinboardSelectMode()");
    expect(window.eval("state.pinboardSelectMode")).toBe(true);
    const viewAfter = renderPinboard(window, data);
    const toolsButtonsAfter = Array.from(viewAfter.querySelectorAll(".letters-tools button")).map((b) => b.textContent);
    expect(toolsButtonsAfter).not.toContain("Fertig");
    expect(toolsButtonsAfter).not.toContain("Auswählen");
    expect(viewAfter.querySelector(".select-bar-cancel")).not.toBeNull();

    window.eval("exitPinboardSelectMode()");
    expect(window.eval("state.pinboardSelectMode")).toBe(false);
  });
});

describe("[P128] pinboard: long-press enters select mode", () => {
  test("enterPinboardSelectMode turns on select mode with the pressed tile selected", () => {
    const { window } = loadApp();
    window.eval(`
      state.pinboard = ${JSON.stringify(pinboardData())};
      enterPinboardSelectMode(1);
    `);
    expect(window.eval("state.pinboardSelectMode")).toBe(true);
    expect(window.eval("state.pinboardSelected")).toEqual([1]);
  });
});

describe("[P128] pinboard: bulk actions are exactly Gelesen/Ungelesen markieren", () => {
  test("the selection bar offers only 'Gelesen markieren' and 'Ungelesen markieren', no archive option", () => {
    const { window } = loadApp();
    window.eval(`
      state.pinboardSelectMode = true;
      state.pinboardSelected = [1];
    `);
    const bar = window.eval("pinboardSelectionBar()");
    const buttons = Array.from(bar.querySelectorAll(".select-bar-actions button")).map((b) => b.textContent);
    expect(buttons).toEqual(["Gelesen markieren", "Ungelesen markieren"]);
    expect(buttons.some((text) => text.toLowerCase().includes("archiv"))).toBe(false);
  });
});

describe("[P128] pinboard: bulk mark read/unread calls the seen API with the right tile_ids", () => {
  test("bulkMarkPinboardRead posts tile_ids with unseen:false", async () => {
    const { window } = loadApp();
    const calls = [];
    window.fetch = (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
    };
    window.eval(`
      state.pinboard = ${JSON.stringify(pinboardData())};
      state.pinboardSelectMode = true;
      state.pinboardSelected = [1, 2];
    `);
    await window.eval("bulkMarkPinboardRead()");
    expect(calls[0].url).toBe("http://localhost/api/pinboard/seen");
    expect(calls[0].body).toEqual({ tile_ids: [1, 2], unseen: false });
    expect(window.eval("state.pinboardSelectMode")).toBe(false);
    expect(window.eval("state.pinboardSelected")).toEqual([]);
  });

  test("bulkMarkPinboardUnread posts tile_ids with unseen:true", async () => {
    const { window } = loadApp();
    const calls = [];
    window.fetch = (url, opts) => {
      calls.push({ url, body: JSON.parse(opts.body) });
      return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
    };
    window.eval(`
      state.pinboard = ${JSON.stringify(pinboardData())};
      state.pinboardSelectMode = true;
      state.pinboardSelected = [1];
    `);
    await window.eval("bulkMarkPinboardUnread()");
    expect(calls[0].url).toBe("http://localhost/api/pinboard/seen");
    expect(calls[0].body).toEqual({ tile_ids: [1], unseen: true });
  });
});

describe("[P128] pinboard: view-entry reset via setView", () => {
  test("multi-select is switched off after navigating away and back", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "pinboard";
      state.pinboardSelectMode = true;
      state.pinboardSelected = [1];
      setView("overview");
      setView("pinboard");
    `);
    expect(window.eval("state.pinboardSelectMode")).toBe(false);
    expect(window.eval("state.pinboardSelected")).toEqual([]);
  });

  test("a typed search query is cleared after navigating away and back", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "pinboard";
      state.pinboardSearch = "Sportfest";
      setView("overview");
      setView("pinboard");
    `);
    expect(window.eval("state.pinboardSearch")).toBe("");
  });
});
