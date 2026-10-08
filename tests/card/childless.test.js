import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const SCHOOL_BLOCKS = ["letters", "noticeboard", "conferences", "holidays"];
const ALL_BLOCKS = ["today", "next_lesson", "week", "absences", "changes", ...SCHOOL_BLOCKS];
const HOLIDAYS = "calendar.ranzenpost_school_holidays";

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function shownBlocks(card) {
  return [...card.shadowRoot.querySelectorAll(".block")].map((node) => node.dataset.block);
}

function rowsOf(card, block) {
  return texts(card.shadowRoot, `.block[data-block="${block}"] .row-title`);
}

async function push(card, hass) {
  card.hass = { ...hass };
  await card.settled;
}

describe("a school account without a child", () => {
  it("renders the school blocks from the school device", async () => {
    const hass = makeHass({ childless: true });
    const card = await mountCard({ blocks: ALL_BLOCKS }, hass);

    expect(shownBlocks(card)).toEqual(SCHOOL_BLOCKS);
    expect(rowsOf(card, "letters")).toEqual(["Field trip", "Photo day"]);
    expect(rowsOf(card, "noticeboard")).toEqual(["Lost and found"]);
    expect(rowsOf(card, "conferences")).toEqual(["Parent-teacher conference"]);
    expect(rowsOf(card, "holidays")).toEqual(["Autumn holidays"]);
    expect(card.shadowRoot.querySelectorAll(".tag")).toHaveLength(0);
    expect(card.shadowRoot.querySelector(".empty")).toBeNull();
    expect(apiCallsFor(hass, HOLIDAYS)).toHaveLength(1);
  });

  it("does not read the registry again while the account has no child", async () => {
    const hass = makeHass({ childless: true });
    const card = await mountCard({ blocks: SCHOOL_BLOCKS }, hass);
    const listings = () => hass.calls.ws.filter((message) => message.type === "config/entity_registry/list").length;

    vi.setSystemTime(new Date("2026-09-02T07:17:30Z"));
    await push(card, hass);
    vi.setSystemTime(new Date("2026-09-02T07:19:30Z"));
    await push(card, hass);

    expect(listings()).toBe(1);
  });

  it("does not read the registry again in the family view either", async () => {
    const hass = makeHass({ childless: true });
    const card = await mountCard({ view: "family" }, hass);
    const listings = () => hass.calls.ws.filter((message) => message.type === "config/entity_registry/list").length;

    vi.setSystemTime(new Date("2026-09-02T07:17:30Z"));
    await push(card, hass);

    expect(listings()).toBe(1);
  });

  it.each(["today", "week", "family"])("shows the school blocks in the old %s view instead of a missing profile", async (view) => {
    const hass = makeHass({ childless: true });
    const card = await mountCard({ view, child: "kim" }, hass);

    expect(shownBlocks(card)).toEqual(["letters", "noticeboard", "holidays"]);
    expect(rowsOf(card, "letters")).toEqual(["Field trip", "Photo day"]);
    expect(card.shadowRoot.querySelector(".empty")).toBeNull();
  });

  it("keeps the holidays of a school without a timetable module, as the app does", async () => {
    const base = makeHass({ childless: true });
    const connection = "sensor.ranzenpost_school_connection";
    const modules = { ...base.states[connection].attributes.modules, timetable: false };
    const hass = makeHass({
      childless: true,
      states: { [connection]: { ...base.states[connection], attributes: { ...base.states[connection].attributes, modules } } },
    });
    const card = await mountCard({ view: "family" }, hass);

    expect(shownBlocks(card)).toEqual(["letters", "noticeboard", "holidays"]);
    expect(rowsOf(card, "holidays")).toEqual(["Autumn holidays"]);
  });

  it("suggests school blocks for a new card", async () => {
    expect(await CardClass.getStubConfig(makeHass({ childless: true }))).toEqual({ blocks: ["letters", "noticeboard"] });
  });

  it("still names the missing profiles when the integration has no school either", async () => {
    const card = await mountCard({ blocks: SCHOOL_BLOCKS }, makeHass({ empty: true }));

    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Die Ranzenpost-Integration hat noch keine Profile.");
    expect(await CardClass.getStubConfig(makeHass({ empty: true }))).toEqual({ blocks: ["today", "next_lesson"] });
  });
});

describe("an account with children", () => {
  it("keeps reading the letters of the children and ignores the school sensors", async () => {
    const hass = makeHass({
      states: {
        "sensor.ranzenpost_school_unread_letters": {
          state: "1",
          attributes: { letters: [{ title: "Only on the school", sender: "", date: "", child: "" }] },
        },
      },
    });
    const card = await mountCard({ blocks: ["letters", "conferences"] }, hass);

    expect(rowsOf(card, "letters")).not.toContain("Only on the school");
    expect(rowsOf(card, "letters")).toContain("Field trip");
    expect(rowsOf(card, "conferences")).toEqual(["Parent-teacher conference"]);
  });

  it("shows the profile hint when the chosen children are not found", async () => {
    const card = await mountCard({ blocks: SCHOOL_BLOCKS, children: ["nobody"] }, makeHass({ childless: true }));

    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Die Ranzenpost-Integration hat noch keine Profile.");
  });
});
