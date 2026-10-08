import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INGRESS_PATH, apiCallsFor, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const SCHOOL_EVENTS = "calendar.ranzenpost_school_school_events";

function timed(uid, summary, start, end, location = "") {
  return { uid, summary, description: "", location, start, end, all_day: false, cancelled: false, color: "" };
}

function allDay(uid, summary, start, end) {
  return { uid, summary, description: "", location: "", start, end, all_day: true, cancelled: false, color: "" };
}

function shownBlocks(card) {
  return [...card.shadowRoot.querySelectorAll(".block")].map((node) => node.dataset.block);
}

function part(card, selector) {
  return texts(card.shadowRoot, `.block[data-block="school_events"] ${selector}`);
}

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

async function offeredInEditor(hass) {
  document.body.innerHTML = "";
  const editor = CardClass.getConfigElement();
  document.body.appendChild(editor);
  editor.setConfig({ blocks: ["today"] });
  editor.hass = hass;
  await editor.settled;
  return [...editor.shadowRoot.querySelectorAll('input[name="blocks"]')].map((input) => input.value);
}

afterEach(() => {
  vi.useRealTimers();
});

describe("the school events block", () => {
  it("opens the app's school events view from its head", async () => {
    const hass = makeHass({ schoolEvents: true });
    const card = await mountCard({ blocks: [{ key: "school_events", size: "normal" }], children: ["alex"] }, hass);
    const link = card.shadowRoot.querySelector('.block[data-block="school_events"] .panel-link');
    expect(link.getAttribute("href")).toBe(`${INGRESS_PATH}?view=calendar`);
  });

  it("lists the next timed and all-day events with date, time and location", async () => {
    const hass = makeHass({ schoolEvents: true });
    const card = await mountCard({ blocks: [{ key: "school_events", size: "normal" }], children: ["alex"] }, hass);

    expect(shownBlocks(card)).toEqual(["school_events"]);
    expect(part(card, ".row-title")).toEqual(["Parents evening", "Sports day"]);
    const [evening, sports] = part(card, ".row-sub");
    expect(evening).toContain("04.09.");
    expect(evening).toContain("18:00 – 19:30");
    expect(evening).toContain("Hall");
    expect(sports).toContain("10.09.");
    expect(sports).not.toContain("11.09.");
    expect(sports).not.toContain(":");
    expect(part(card, ".row-meta")).toHaveLength(2);
    expect(card.shadowRoot.querySelectorAll('.block[data-block="school_events"] .tag')).toHaveLength(0);
    const calls = apiCallsFor(hass, SCHOOL_EVENTS);
    expect(calls).toHaveLength(1);
    expect(decodeURIComponent(calls[0].path)).toContain("start=2026-09-01T22:00:00.000Z&end=2026-10-31T23:00:00.000Z");
  });

  it("shows a multi-day all-day event up to its last day and drops what is already over", async () => {
    const events = [
      timed("over", "Morning assembly", "2026-09-02T07:00:00+02:00", "2026-09-02T08:00:00+02:00"),
      allDay("yesterday", "Project day", "2026-09-01", "2026-09-02"),
      timed("later", "Choir", "2026-09-02T15:00:00+02:00", "2026-09-02T16:00:00+02:00", "Music room"),
      allDay("trip", "Class trip", "2026-09-14", "2026-09-17"),
    ];
    const hass = makeHass({ schoolEvents: true, events: { [SCHOOL_EVENTS]: events } });
    const card = await mountCard({ blocks: [{ key: "school_events", size: "normal" }], children: ["alex"] }, hass);

    expect(part(card, ".row-title")).toEqual(["Choir", "Class trip"]);
    const [choir, trip] = part(card, ".row-sub");
    expect(choir).toContain("15:00 – 16:00");
    expect(choir).toContain("Music room");
    expect(trip).toBe("14.09. – 16.09.");
    expect(part(card, ".row-meta")[0]).toBe("Heute");
  });

  it("keeps the compact rows to the title and the day", async () => {
    const card = await mountCard({ blocks: [{ key: "school_events", size: "compact" }], children: ["alex"] }, makeHass({ schoolEvents: true }));
    expect(part(card, ".row-title")).toEqual(["Parents evening", "Sports day"]);
    expect(part(card, ".row-sub")).toEqual([]);
  });

  it("renders nothing without events", async () => {
    const hass = makeHass({ schoolEvents: true, events: { [SCHOOL_EVENTS]: [] } });
    const card = await mountCard({ blocks: ["today", "school_events"], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual(["today"]);
  });

  it("asks for nothing and renders nothing while the school has no calendar module", async () => {
    const hass = makeHass();
    const card = await mountCard({ blocks: ["today", "school_events"], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual(["today"]);
    expect(apiCallsFor(hass, SCHOOL_EVENTS)).toHaveLength(0);
  });

  it("is offered in the editor only where the school has the calendar module", async () => {
    expect(await offeredInEditor(makeHass({ schoolEvents: true }))).toContain("school_events");
    expect(await offeredInEditor(makeHass())).not.toContain("school_events");
  });

  it("reads the school calendar for an account without a child", async () => {
    const hass = makeHass({ childless: true, schoolEvents: true });
    const card = await mountCard({ blocks: ["school_events", "holidays"] }, hass);
    expect(shownBlocks(card)).toEqual(["school_events", "holidays"]);
    expect(part(card, ".row-title")).toEqual(["Parents evening", "Sports day"]);
    expect(card.shadowRoot.querySelectorAll('.block[data-block="school_events"] .tag')).toHaveLength(0);
  });

  it("tags every event with its school when there are several schools", async () => {
    const hass = makeHass({ twoSchools: true, schoolEvents: true });
    const card = await mountCard({ blocks: ["school_events"] }, hass);
    expect(part(card, ".row-title")).toEqual(["Parents evening", "Parents evening", "Sports day", "Sports day"]);
    expect(part(card, ".tag")).toEqual(["Sample School", "Other School", "Sample School", "Other School"]);
    expect(apiCallsFor(hass, SCHOOL_EVENTS)).toHaveLength(1);
    expect(apiCallsFor(hass, "calendar.ranzenpost_school_other_school_school_events")).toHaveLength(1);
  });
});
