import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function reply(body, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

const BODIES = [
  ["api/timetable", { lessons: [], period_times: {} }],
  ["api/holidays", { holidays: [] }],
  ["api/absences", { absences: [] }],
  ["api/marks", { marks: [] }],
  ["api/cancellations", { cancellations: [] }],
  ["api/letters", { letters: [] }],
  ["api/pinboard", { posts: [] }],
  ["api/conferences", { conferences: [] }],
  ["api/messenger/rooms", { rooms: [] }],
];

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await settle();
  window.clearTimeout(window.eval("bootWatchdog"));
}

function armApp(window, failing) {
  const seen = [];
  window.fetch = (input) => {
    const url = String(input);
    seen.push(url);
    if (failing && url.includes(failing)) return Promise.reject(new Error("boom"));
    for (const [fragment, body] of BODIES) {
      if (url.includes(fragment)) return reply(body);
    }
    return reply({});
  };
  window.eval(`
    state.children = [{ child_id: "c1", name: "Kind" }];
    state.childId = "c1";
    state.timetableAvailable = true;
    state.view = "absence";
    state.pinboard = { posts: [] };
    state.refreshFailed = { timetable: "network", pinboard: "network", absence: "network", marks: "network" };
  `);
  return seen;
}

async function pull(window) {
  await window.eval("refreshEverything()");
  await quiet(window);
}

describe("[P230] one pull refreshes the whole app, not just the tab you pulled in", () => {
  test("it asks every area, even though only the absence tab is open", async () => {
    const { window } = loadApp();
    await quiet(window);
    const seen = armApp(window, null);
    await pull(window);
    for (const [fragment] of BODIES) {
      expect(seen.some((url) => url.includes(fragment)), `never refreshed ${fragment}`).toBe(true);
    }
  });

  test("after a successful pull the stale note is gone in every tab", async () => {
    const { window } = loadApp();
    await quiet(window);
    armApp(window, null);
    await pull(window);
    expect(window.eval("JSON.stringify(state.refreshFailed)")).toBe("{}");
  });

  test("a partial failure stays honest: only the area that really failed keeps its note", async () => {
    const { window } = loadApp();
    await quiet(window);
    armApp(window, "api/pinboard");
    await pull(window);
    const left = JSON.parse(window.eval("JSON.stringify(state.refreshFailed)"));
    expect(Object.keys(left)).toEqual(["pinboard"]);
  });
});
