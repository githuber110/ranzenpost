import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass, ownEntriesCalls } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard } from "./loadCard.js";

const LESSONS = "calendar.ranzenpost_alex_lessons";
const EXAMS = "calendar.ranzenpost_alex_exams";
const STAMP = "sensor.ranzenpost_alex_timetable_last_updated";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

async function push(card, hass) {
  card.hass = { ...hass };
  await card.settled;
}

describe("calendar cache", () => {
  it("answers a second card and repeated hass updates from the cache for five minutes", async () => {
    const hass = makeHass();
    const card = await mountCard({ view: "today", child: "alex" }, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(1);
    expect(apiCallsFor(hass, EXAMS)).toHaveLength(1);

    await push(card, hass);
    const twin = document.createElement("ranzenpost-card");
    twin.setConfig({ view: "today", child: "alex" });
    document.body.appendChild(twin);
    twin.hass = hass;
    await twin.settled;
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(1);
    expect(ownEntriesCalls(hass)).toHaveLength(1);
    expect(twin.shadowRoot.querySelectorAll(".row[data-uid]")).toHaveLength(3);

    vi.setSystemTime(new Date("2026-09-02T07:19:00Z"));
    await push(card, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(1);
    expect(ownEntriesCalls(hass)).toHaveLength(1);

    vi.setSystemTime(new Date("2026-09-02T07:20:30Z"));
    await push(card, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(2);
    expect(apiCallsFor(hass, EXAMS)).toHaveLength(2);
    expect(ownEntriesCalls(hass)).toHaveLength(2);
  });

  it("refetches as soon as the timetable of the child was updated", async () => {
    const hass = makeHass();
    const card = await mountCard({ view: "today", child: "alex" }, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(1);

    hass.states[STAMP] = { ...hass.states[STAMP], state: "2026-09-02T09:16:00+02:00" };
    await push(card, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(2);
    expect(ownEntriesCalls(hass)).toHaveLength(2);

    await push(card, hass);
    expect(apiCallsFor(hass, LESSONS)).toHaveLength(2);
  });

  it("discovers the entities once for all cards", async () => {
    const hass = makeHass();
    await mountCard({ view: "today", child: "alex" }, hass);
    const twin = document.createElement("ranzenpost-card");
    twin.setConfig({ view: "family" });
    document.body.appendChild(twin);
    twin.hass = hass;
    await twin.settled;

    expect(hass.calls.ws.map((message) => message.type).filter((type) => type.startsWith("config/")).sort()).toEqual([
      "config/device_registry/list",
      "config/entity_registry/list",
    ]);
  });

  it("looks at the registry again for a missing child, at most once a minute", async () => {
    const hass = makeHass();
    const card = await mountCard({ view: "today", child: "nobody" }, hass);
    const listings = () => hass.calls.ws.filter((message) => message.type === "config/entity_registry/list").length;
    expect(listings()).toBe(1);

    await push(card, hass);
    expect(listings()).toBe(1);

    vi.setSystemTime(new Date("2026-09-02T07:16:30Z"));
    await push(card, hass);
    expect(listings()).toBe(2);
    expect(card.shadowRoot.querySelector(".empty b").textContent).toContain("nobody");
  });

  it("moves the highlight along with the clock", async () => {
    const hass = makeHass();
    const card = await mountCard({ view: "today", child: "alex" }, hass);
    const current = () => card.shadowRoot.querySelector(".row[aria-current='true']");
    expect(current().dataset.uid).toBe("lesson-20260902-p1@sample");
    expect(current().querySelector(".row-when.now")).not.toBeNull();

    vi.setSystemTime(new Date("2026-09-02T08:00:00Z"));
    await push(card, hass);
    expect(current().dataset.uid).toBe("lesson-20260902-p2@sample");
    expect(card.shadowRoot.querySelector(".row-when.next")).toBeNull();
    expect(card.shadowRoot.querySelector(".row.past").dataset.uid).toBe("lesson-20260902-p1@sample");
  });
});
