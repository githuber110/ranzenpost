import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function linkFor(query, modules = {}) {
  const { window } = loadApp({ url: `http://localhost/${query}` });
  window.testModules = modules;
  window.eval("state.modules = applyModules({ modules: window.testModules });");
  return window.eval("startLink()");
}

describe("the app opens where a link from the card points", () => {
  test("a timetable link opens the timetable", () => {
    expect(linkFor("?view=timetable")).toEqual({ view: "timetable", segment: null });
  });

  test("a pinboard link opens the post view on the pinboard", () => {
    expect(linkFor("?view=post&segment=pinboard")).toEqual({ view: "post", segment: "pinboard" });
  });

  test("unknown views, areas and segments are ignored", () => {
    expect(linkFor("?view=settings")).toBeNull();
    expect(linkFor("?view=nowhere")).toBeNull();
    expect(linkFor("?view=post&segment=archive")).toEqual({ view: "post", segment: null });
  });

  test("a view whose module the school lacks is not opened", () => {
    expect(linkFor("?view=conferences", { conferences: false })).toBeNull();
  });

  test("without a link the app starts as before", () => {
    expect(linkFor("")).toBeNull();
  });

  async function waitingLink(moved) {
    const { window } = loadApp({ url: "http://localhost/?view=modulepages" });
    window.fetch = () => Promise.resolve({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({ schools: [{ connection_id: "a1", todo: true }] }),
    });
    window.eval("state.modules = applyModules({ modules: {} }); state.accountModules = null; state.view = 'overview';");
    expect(window.eval("startLink()")).toBeNull();
    window.eval("state.startLinkWaits = 'overview';");
    if (moved) window.eval("state.view = 'timetable';");
    await window.eval("loadAccountModules()");
    return window.eval("state.view");
  }

  test("a link to the other modules opens once the school's modules are known", async () => {
    expect(await waitingLink(false)).toBe("modulepages");
  });

  test("the waiting link does not pull someone away who already moved on", async () => {
    expect(await waitingLink(true)).toBe("timetable");
  });

  test("following a timetable link switches the view", () => {
    const { window } = loadApp({ url: "http://localhost/?view=timetable" });
    window.eval("state.modules = applyModules({ modules: {} }); followStartLink(startLink());");
    expect(window.eval("state.view")).toBe("timetable");
  });
});
