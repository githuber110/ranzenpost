import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass, ownEntriesCalls } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LESSONS = "calendar.ranzenpost_alex_lessons";
const KIM_LESSONS = "calendar.ranzenpost_kim_lessons";
const OWN = "calendar.ranzenpost_alex_own_entries";
const SCHOOL_EVENTS = "calendar.ranzenpost_school_school_events";
const DAY_MS = 24 * 60 * 60 * 1000;

beforeEach(async () => {
  freezeClock();
  await loadCard();
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

function strictOwnEntries(hass) {
  const original = hass.callWS.bind(hass);
  hass.callWS = async (message) => {
    if (message.type === "ranzenpost/own_entries") {
      const days = (Date.parse(message.end) - Date.parse(message.start)) / DAY_MS;
      if (days > 31) throw Object.assign(new Error("the range must run forward and span at most 31 days"), { code: "bad_range" });
    }
    return original(message);
  };
  return hass;
}

function own(uid, summary, start, end) {
  return { uid, summary, description: "", location: "", start, end, all_day: false, cancelled: false, color: "", subject_code: "", subject: "", kind: "own_entries" };
}

function failing(hass, entityIds) {
  const original = hass.callApi.bind(hass);
  hass.callApi = async (method, path) => {
    if (entityIds.some((entityId) => path.startsWith(`calendars/${entityId}?`))) throw new Error("calendar not found");
    return original(method, path);
  };
  return hass;
}

describe("own entries never ask for more days than the server allows", () => {
  it("splits the range of a Friday with week and next school day and shows every block", async () => {
    freezeClock("2026-09-04T10:00:00Z");
    const lessons = [
      { ...own("fri-1", "Sport", "2026-09-04T08:00:00+02:00", "2026-09-04T09:30:00+02:00"), kind: "", subject: "Sport", subject_code: "SP" },
      { ...own("mon-1", "Maths", "2026-09-07T08:00:00+02:00", "2026-09-07T08:45:00+02:00"), kind: "", subject: "Maths", subject_code: "MA" },
    ];
    const events = { [LESSONS]: lessons, [OWN]: [own("own-fri", "Choir", "2026-09-04T15:00:00+02:00", "2026-09-04T16:00:00+02:00"), own("own-mon", "Swim", "2026-09-07T16:00:00+02:00", "2026-09-07T17:00:00+02:00")] };
    const hass = strictOwnEntries(makeHass({ ownEntries: true, events }));
    const card = await mountCard({ blocks: ["today", "week", "next_day"], children: ["alex"] }, hass);
    const root = card.shadowRoot;
    const calls = ownEntriesCalls(hass);

    expect(calls.length).toBeGreaterThan(1);
    for (const call of calls) expect((Date.parse(call.end) - Date.parse(call.start)) / DAY_MS).toBeLessThanOrEqual(31);
    expect(calls[0].start).toBe("2026-08-31");
    expect(calls.at(-1).end).toBe("2026-10-02");
    expect(root.querySelector(".empty")).toBeNull();
    expect([...root.querySelectorAll(".block")].map((node) => node.dataset.block)).toEqual(["today", "week", "next_day"]);
    expect(texts(block(root, "today"), ".row.own .row-title")).toEqual(["Choir"]);
    expect(texts(block(root, "next_day"), ".row.own .row-title")).toEqual(["Swim"]);
  });
});

describe("a failing calendar only touches its own block", () => {
  it("keeps the blocks of the sibling and the family blocks when one lessons calendar fails", async () => {
    const kimLesson = { ...own("kim-1", "Music", "2026-09-02T10:00:00+02:00", "2026-09-02T10:45:00+02:00"), kind: "", subject: "Music", subject_code: "MU" };
    const hass = failing(makeHass({ events: { [KIM_LESSONS]: [kimLesson] } }), [LESSONS]);
    const card = await mountCard({ blocks: ["today", "letters"], children: ["alex", "kim"] }, hass);
    const root = card.shadowRoot;
    const alex = root.querySelector('.member[data-child$="child-1"]');
    const kim = root.querySelector('.member[data-child$="child-2"]');

    expect(root.querySelector(".empty")).toBeNull();
    expect(texts(alex, ".row-note .dlg-text")).toEqual(["Konnte gerade nicht geladen werden."]);
    expect(alex.querySelector(".row[data-uid]")).toBeNull();
    expect(texts(kim, ".row[data-uid] .row-title")).toEqual(["Music"]);
    expect(block(root, "letters")).not.toBeNull();
  });

  it("says the school events failed and keeps the today block", async () => {
    const hass = failing(makeHass({ schoolEvents: true }), [SCHOOL_EVENTS]);
    const card = await mountCard({ blocks: ["today", "school_events"], children: ["alex"] }, hass);
    const root = card.shadowRoot;

    expect(texts(block(root, "today"), ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
    expect(texts(block(root, "school_events"), ".row-note .dlg-text")).toEqual(["Konnte gerade nicht geladen werden."]);
  });

  it("shows the lessons and names the gap when only the exams calendar fails", async () => {
    const hass = failing(makeHass(), ["calendar.ranzenpost_alex_exams"]);
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, hass);
    const shown = block(card.shadowRoot, "today");

    expect(texts(shown, ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
    expect(texts(shown, ".row-note .dlg-text").at(-1)).toBe("Einige Einträge konnten gerade nicht geladen werden.");
  });
});

describe("the entity registry", () => {
  function withRegistry(hass, change) {
    const original = hass.callWS.bind(hass);
    hass.callWS = async (message) => {
      const result = await original(message);
      return message.type === "config/entity_registry/list" ? change(result) : result;
    };
    return hass;
  }

  const listings = (hass) => hass.calls.ws.filter((message) => message.type === "config/entity_registry/list").length;

  it("skips disabled entities", async () => {
    const hass = withRegistry(makeHass(), (entries) => entries.map((entry) => (entry.entity_id === KIM_LESSONS ? { ...entry, disabled_by: "user" } : entry)));
    await mountCard({ blocks: ["today"], children: ["alex", "kim"] }, hass);

    expect(apiCallsFor(hass, KIM_LESSONS)).toEqual([]);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(1);
  });

  it("looks again when a configured entity was renamed", async () => {
    const renamed = "calendar.ranzenpost_alex_school_lessons";
    let rename = false;
    const base = makeHass({ events: { [renamed]: [] } });
    const hass = withRegistry(base, (entries) => entries.map((entry) => (rename && entry.entity_id === LESSONS ? { ...entry, entity_id: renamed } : entry)));
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, hass);
    expect(listings(hass)).toBe(1);

    rename = true;
    hass.states[renamed] = { ...hass.states[LESSONS], entity_id: renamed };
    delete hass.states[LESSONS];
    vi.setSystemTime(new Date("2026-09-02T07:16:30Z"));
    card.hass = { ...hass };
    await card.settled;

    expect(listings(hass)).toBe(2);
    expect(apiCallsFor(hass, renamed)).toHaveLength(1);
  });

  it("looks again when Home Assistant lists a new Ranzenpost entity", async () => {
    const hass = makeHass();
    const card = await mountCard({ blocks: ["today"] }, hass);
    expect(listings(hass)).toBe(1);

    vi.setSystemTime(new Date("2026-09-02T07:16:30Z"));
    card.hass = { ...hass, entities: { "sensor.ranzenpost_robin_next_lesson": { entity_id: "sensor.ranzenpost_robin_next_lesson", platform: "ranzenpost" } } };
    await card.settled;
    expect(listings(hass)).toBe(2);
  });

  it("stays with the known registry while nothing changed", async () => {
    const hass = makeHass();
    const card = await mountCard({ blocks: ["today"] }, hass);

    vi.setSystemTime(new Date("2026-09-02T07:16:30Z"));
    card.hass = { ...hass, entities: { [LESSONS]: { entity_id: LESSONS, platform: "ranzenpost" } } };
    await card.settled;
    expect(listings(hass)).toBe(1);
  });
});
