import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LETTERS = "sensor.ranzenpost_alex_unread_letters";
const KIM_LETTERS = "sensor.ranzenpost_kim_unread_letters";
const CHANGES = "sensor.ranzenpost_alex_changes_today";
const ABSENCES = "sensor.ranzenpost_alex_open_absences";
const NEXT_LESSON = "sensor.ranzenpost_alex_next_lesson";
const TASKS = "sensor.ranzenpost_school_open_tasks";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

const FIELD_TRIP = { title: "Field trip", sender: "Mrs Example", date: "2026-09-01", child: "" };
const PHOTO_DAY = { title: "Photo day", sender: "Head Office", date: "2026-08-28", child: "" };

describe("list counters", () => {
  it("count what the sensor counts, not the shortened list, and name the number", async () => {
    const hass = makeHass({ states: { [LETTERS]: { state: "14", attributes: { letters: [FIELD_TRIP, PHOTO_DAY] } } } });
    const card = await mountCard({ blocks: [{ key: "letters", size: "compact" }], children: ["alex"] }, hass);
    const shown = block(card.shadowRoot, "letters");
    const count = shown.querySelector(".panel-head .count");

    expect(count.textContent).toBe("14");
    expect(count.getAttribute("aria-label")).toBe("Elternbriefe: 14");
    expect(shown.querySelector(".row-all")).not.toBeNull();
  });

  it("subtract a letter that two profiles share", async () => {
    const hass = makeHass({
      states: {
        [LETTERS]: { state: "2", attributes: { letters: [FIELD_TRIP, PHOTO_DAY] } },
        [KIM_LETTERS]: { state: "1", attributes: { letters: [FIELD_TRIP] } },
      },
    });
    const card = await mountCard({ blocks: ["letters"] }, hass);

    expect(block(card.shadowRoot, "letters").querySelector(".panel-head .count").textContent).toBe("2");
  });

  it("count the school lists from their sensor", async () => {
    const hass = makeHass({ schoolLists: true });
    hass.states[TASKS] = { ...hass.states[TASKS], state: "12" };
    const card = await mountCard({ blocks: ["tasks"], children: ["alex"] }, hass);

    expect(block(card.shadowRoot, "tasks").querySelector(".panel-head .count").textContent).toBe("12");
  });
});

describe("unknown is not empty", () => {
  it("shows an unknown change count instead of none", async () => {
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, makeHass({ states: { [CHANGES]: { state: "unavailable", attributes: {} } } }));
    const count = block(card.shadowRoot, "today").querySelector(".panel-head .count");

    expect(count.textContent).toBe("?");
    expect(count.getAttribute("aria-label")).toBe("Änderungen: unbekannt");
  });

  it("marks unknown counts of the family view instead of zero", async () => {
    const card = await mountCard({ view: "family", children: ["alex"] }, makeHass({ states: { [LETTERS]: { state: "unknown", attributes: {} } } }));
    const letters = card.shadowRoot.querySelector(".counts .count");

    expect(letters.dataset.count).toBe("unknown");
    expect(letters.querySelector(".badge.unknown").getAttribute("aria-label")).toBe("Elternbriefe: unbekannt");
  });

  it("keeps the letters block with a note when its sensor is unavailable", async () => {
    const card = await mountCard({ blocks: ["letters"], children: ["alex"] }, makeHass({ states: { [LETTERS]: { state: "unavailable", attributes: {} } } }));
    const shown = block(card.shadowRoot, "letters");

    expect(shown.querySelector(".panel-head .count").textContent).toBe("?");
    expect(texts(shown, ".row-note .dlg-text")).toEqual(["Konnte gerade nicht geladen werden."]);
  });
});

describe("profiles that no longer exist", () => {
  it("names the missing profile instead of saying there are none", async () => {
    const card = await mountCard({ blocks: ["today"], children: ["anna"] }, makeHass());

    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Profil „anna“ nicht gefunden.");
  });

  it("names the missing profile next to the profiles that still exist", async () => {
    const card = await mountCard({ blocks: ["today"], children: ["alex", "anna"] }, makeHass());
    const root = card.shadowRoot;

    expect(texts(root, ".card-note")).toEqual(["Profil „anna“ nicht gefunden."]);
    expect(texts(block(root, "today"), ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
  });

  it("names the missing profile in the family view", async () => {
    const card = await mountCard({ view: "family", children: ["anna"] }, makeHass());

    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Profil „anna“ nicht gefunden.");
  });
});

describe("block order with several profiles", () => {
  it("keeps a family block above the profile blocks when it comes first", async () => {
    const card = await mountCard({ blocks: ["letters", "today", "holidays"] }, makeHass());
    const order = [...card.shadowRoot.querySelectorAll(".block, .family")].filter((node) => !node.closest(".family") || node.classList.contains("family"));

    expect(order.map((node) => node.dataset.block || "family")).toEqual(["letters", "family", "holidays"]);
  });
});

describe("next lesson countdown", () => {
  it("counts from the start of the lesson and not from the attribute of the last poll", async () => {
    const hass = makeHass();
    hass.states[NEXT_LESSON] = { ...hass.states[NEXT_LESSON], attributes: { ...hass.states[NEXT_LESSON].attributes, minutes_until: 0 } };
    const card = await mountCard({ blocks: [{ key: "next_lesson", size: "normal" }], children: ["alex"] }, hass);

    expect(block(card.shadowRoot, "next_lesson").querySelector(".row-sub").textContent).toBe("R202 · Mr Stand-in · in 35 Minuten");
  });
});

describe("profile names inside the profile column", () => {
  it("does not repeat the profile in absences and changes", async () => {
    const card = await mountCard({ blocks: ["absences", "changes"] }, makeHass());
    const member = card.shadowRoot.querySelector('.member[data-child$="child-1"]');

    expect(texts(block(member, "absences"), ".row-title")).toEqual(["04.09."]);
    expect(texts(block(member, "changes"), ".row-tags .tag")).toEqual([]);
  });
});

describe("repainting", () => {
  it("keeps the page untouched when a new minute changes nothing", async () => {
    const hass = makeHass();
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, hass);
    const before = card.shadowRoot.querySelector("ha-card");

    vi.setSystemTime(new Date("2026-09-02T07:16:00Z"));
    card.hass = { ...hass };
    await card.settled;

    expect(card.shadowRoot.querySelector("ha-card")).toBe(before);
  });
});

describe("absences without a sensor value", () => {
  it("say they are unknown", async () => {
    const card = await mountCard({ blocks: ["absences"], children: ["alex"] }, makeHass({ states: { [ABSENCES]: { state: "unavailable", attributes: {} } } }));

    expect(block(card.shadowRoot, "absences").querySelector(".panel-head .count").textContent).toBe("?");
  });
});
