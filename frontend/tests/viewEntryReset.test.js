import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

function prepare(window) {
  window.eval(`
    state.config = {};
    state.children = [];
    state.absence = { data: { children: [], rules: {} } };
    state.modules.available.timetable = true;
  `);
}

function views(window) {
  return window.eval('VIEWS.map((item) => item.key).concat(["settings"])');
}

function dirty(window) {
  window.eval(`
    state._overviewAnchor = "pin:9";
    state._overviewNow = false;
    state._overviewOrder = ["chat"];
    state._overviewPinboardOrder = ["9"];
    state.weekOffset = 3;
    state.spotlightSubject = "D";
    state.absenceHistoryOpen = true;
    state.postTab = "pinboard";
    state.lettersTab = "archive";
    state.lettersSelectMode = true;
    state.lettersSelected = ["1:2"];
    state.lettersSearch = "Sportfest";
    state.pinboardSelectMode = true;
    state.pinboardSelected = ["7"];
    state.pinboardSearch = "Fest";
    state.pinboardOnlyNew = true;
    state.pinboardFolder = "f1";
    state.messengerRoom = { room_id: "!r:s" };
    state.messengerSearch = "Frau";
    state.messengerRetrying = true;
    state.messengerRetryFailed = true;
  `);
}

function trackScrolling(window) {
  const values = new WeakMap();
  Object.defineProperty(window.Element.prototype, "scrollTop", {
    configurable: true,
    get() {
      return values.get(this) || 0;
    },
    set(value) {
      values.set(this, Number(value) || 0);
    },
  });
}

function screenScroll(window) {
  return window.eval("document.querySelector('.screen').scrollTop");
}

describe("every view is entered in a defined state", () => {
  test("every view the app can show declares its entry defaults", () => {
    const { window } = loadApp();
    const declared = window.eval("Object.keys(VIEW_ENTRY_DEFAULTS)").sort();
    expect(declared).toEqual([...views(window)].sort());
  });

  test("every declared default names a key the app state actually carries", () => {
    const { window } = loadApp();
    const unknown = window.eval(`
      Object.keys(VIEW_ENTRY_DEFAULTS)
        .flatMap((view) => Object.keys(VIEW_ENTRY_DEFAULTS[view]))
        .filter((key) => !(key in state))
    `);
    expect(unknown).toEqual([]);
  });

  test("entering any view from any other one wipes the sub-state it declares", () => {
    for (const target of views(loadApp().window)) {
      const { window } = loadApp();
      prepare(window);
      window.eval('state.view = "settings";');
      dirty(window);
      evalWith(window, "setView(testArgs[0])", target);
      const expected = evalWith(window, "VIEW_ENTRY_DEFAULTS[testArgs[0]]", target);
      for (const key of Object.keys(expected)) {
        expect({ view: target, key, value: evalWith(window, "state[testArgs[0]]", key) })
          .toEqual({ view: target, key, value: expected[key] });
      }
    }
  });

  test("entering any view lands at the top instead of restoring the remembered scroll", () => {
    for (const target of views(loadApp().window)) {
      const { window } = loadApp();
      prepare(window);
      trackScrolling(window);
      const origin = target === "settings" ? "overview" : "settings";
      evalWith(window, "state.view = testArgs[0]; render();", origin);
      window.eval("state._keepScroll = 480; state._scrollTop = false;");
      evalWith(window, "setView(testArgs[0])", target);
      expect({ view: target, top: screenScroll(window) }).toEqual({ view: target, top: 0 });
    }
  });

  test("the post tab always opens on the letters segment", () => {
    const { window } = loadApp();
    prepare(window);
    window.eval('state.view = "overview"; state.postTab = "pinboard"; setView("post");');
    expect(window.eval("state.postTab")).toBe("letters");
  });

  test("switching between letters and pinboard scrolls back to the top", () => {
    const { window } = loadApp();
    prepare(window);
    trackScrolling(window);
    window.eval('state.view = "post"; state.postTab = "letters"; render();');
    window.eval("state._keepScroll = 320; state._scrollTop = false;");
    window.eval('switchPostTab("pinboard");');
    expect(screenScroll(window)).toBe(0);
  });

  test("returning to the plan after a week swipe never shows another week under today's dates", () => {
    const { window } = loadApp();
    prepare(window);
    window.eval('state.view = "timetable"; state.weekOffset = 2; state.timetable = { lessons: [], period_times: {} };');
    window.eval('state.view = "overview"; setView("timetable");');
    expect(window.eval("state.weekOffset")).toBe(0);
    expect(window.eval("state.timetable")).toBe(null);
  });

  test("a jump from the overview into one segment keeps that segment", () => {
    const { window } = loadApp();
    prepare(window);
    window.eval('state.view = "overview"; openPostSegment("pinboard");');
    expect(window.eval("state.postTab")).toBe("pinboard");
  });

  test("the return from the overview keeps its anchor", () => {
    const { window } = loadApp();
    prepare(window);
    window.eval('state.view = "post"; state._overviewAnchor = "pin:9"; state._overviewNow = false;');
    window.eval('setView("overview", { keepAnchor: true });');
    expect(window.eval("state._overviewAnchor")).toBe("pin:9");
    expect(window.eval("state._overviewNow")).toBe(false);
  });

  test("a caller that asks to keep its state is left alone", () => {
    const { window } = loadApp();
    prepare(window);
    window.eval('state.view = "overview"; state.postTab = "pinboard";');
    window.eval('setView("post", { keepEntryState: true });');
    expect(window.eval("state.postTab")).toBe("pinboard");
  });
});
