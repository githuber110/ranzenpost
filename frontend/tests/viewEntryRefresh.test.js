import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const MINUTE = 60 * 1000;

function prepared(setup) {
  const { window } = loadApp();
  window.eval(`
    window.__calls = [];
    loadPinboard = () => { window.__calls.push("pinboard"); return Promise.resolve(); };
    loadLetters = (tab) => { window.__calls.push("letters:" + tab); return Promise.resolve(); };
    loadConferences = () => { window.__calls.push("conferences"); return Promise.resolve(); };
    loadAbsences = () => { window.__calls.push("absence"); return Promise.resolve(); };
    loadMessengerRooms = () => { window.__calls.push("messenger"); return Promise.resolve(); };
    ${setup || ""}
  `);
  return window;
}

async function tick(window) {
  await new Promise((resolve) => window.setTimeout(resolve, 0));
}

describe("[P256] reload records when a piece of data was last fetched", () => {
  test("a successful load writes the moment down", async () => {
    const { window } = loadApp();
    await window.eval(`reload("probe", () => Promise.resolve({ ok: true }), false)`);
    const stamp = window.eval("state.loadedAt.probe");
    expect(stamp).toBeGreaterThan(Date.now() - 5000);
  });

  test("a failed load leaves the old moment alone", async () => {
    const { window } = loadApp();
    await window.eval(`reload("probe", () => Promise.reject(new Error("down")), false)`);
    expect(window.eval("state.loadedAt.probe")).toBeUndefined();
  });
});

describe("[P256] opening a view fetches it fresh when what it shows is old", () => {
  test("a pinboard fetched long ago is fetched again", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "pinboard";
      state.loadedAt.pinboard = Date.now() - 3 * ${MINUTE};
    `);
    window.eval("revalidateActiveView()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual(["pinboard"]);
  });

  test("a pinboard fetched a moment ago is left as it is", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "pinboard";
      state.loadedAt.pinboard = Date.now() - 10 * 1000;
    `);
    window.eval("revalidateActiveView()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual([]);
  });

  test("data that was never fetched is left to the first load", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "pinboard";
    `);
    window.eval("revalidateActiveView()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual([]);
  });

  test("the letters segment fetches the letters of the open tab", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "letters";
      state.lettersTab = "current";
      state.loadedAt[lettersLoadKey("current")] = Date.now() - 3 * ${MINUTE};
    `);
    window.eval("revalidateActiveView()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual(["letters:current"]);
  });

  test("an open sheet is never disturbed by it", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "pinboard";
      state.loadedAt.pinboard = Date.now() - 3 * ${MINUTE};
      state.sheet = () => document.createElement("div");
    `);
    window.eval("revalidateActiveView()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual([]);
  });

  test("entering a view and switching between letters and pinboard both ask for it", () => {
    const { window } = loadApp();
    expect(window.eval("String(setView)")).toContain("revalidateActiveView()");
    expect(window.eval("String(switchPostTab)")).toContain("revalidateActiveView()");
  });
});

describe("[P256] a refresh held back by an open sheet is not lost", () => {
  test("coming back with a sheet open remembers the refresh and runs it once the sheet is gone", async () => {
    const window = prepared(`
      state.view = "post";
      state.postTab = "pinboard";
      state.sheet = () => document.createElement("div");
      lastVisibilityRefreshAt = Date.now() - 6 * ${MINUTE};
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      setupVisibilityRefresh();
    `);
    window.document.dispatchEvent(new window.Event("visibilitychange"));
    await tick(window);
    expect(window.eval("window.__calls")).toEqual([]);
    expect(window.eval("state.refreshDeferred")).toBe(true);
    window.eval("state.sheet = null; flushDeferredRefresh()");
    await tick(window);
    expect(window.eval("window.__calls")).toEqual(["pinboard"]);
    expect(window.eval("state.refreshDeferred")).toBe(false);
  });

  test("every render gives a held-back refresh its chance", () => {
    const { window } = loadApp();
    expect(window.eval("String(render)")).toContain("flushDeferredRefresh()");
  });
});

describe("[P256] the window inside Home Assistant getting the focus counts as coming back", () => {
  test("a focus event past the threshold refreshes the open view", async () => {
    const window = prepared(`
      state.view = "conferences";
      lastVisibilityRefreshAt = Date.now() - 6 * ${MINUTE};
      Object.defineProperty(document, "hidden", { value: false, configurable: true });
      setupVisibilityRefresh();
    `);
    window.dispatchEvent(new window.Event("focus"));
    await tick(window);
    expect(window.eval("window.__calls")).toEqual(["conferences"]);
  });
});
