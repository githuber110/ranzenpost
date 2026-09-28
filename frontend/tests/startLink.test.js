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

  test("following a timetable link switches the view", () => {
    const { window } = loadApp({ url: "http://localhost/?view=timetable" });
    window.eval("state.modules = applyModules({ modules: {} }); followStartLink(startLink());");
    expect(window.eval("state.view")).toBe("timetable");
  });
});
