import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INGRESS_PATH, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const ALL_CARD_BLOCKS = ["today", "next_lesson", "week", "letters", "noticeboard", "absences", "conferences", "holidays", "changes"];

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function blocksOf(root) {
  return [...root.querySelectorAll(".block")].map((node) => node.dataset.block);
}

function withTheme(darkMode) {
  return { ...makeHass(), themes: { darkMode } };
}

describe("the card renders the chosen blocks in order", () => {
  for (const darkMode of [false, true]) {
    it(`renders every block once with content in ${darkMode ? "dark" : "light"} mode`, async () => {
      const card = await mountCard({ blocks: ALL_CARD_BLOCKS, children: ["alex"] }, withTheme(darkMode));
      const root = card.shadowRoot;
      expect(card.getAttribute("data-theme")).toBe(darkMode ? "dark" : "light");
      expect(blocksOf(root)).toEqual(ALL_CARD_BLOCKS);
      for (const block of root.querySelectorAll(".block")) {
        expect(block.querySelector(".panel-head .section-label"), block.dataset.block).not.toBeNull();
        expect(block.querySelector(".rows, .tt"), block.dataset.block).not.toBeNull();
        expect(block.querySelector(".panel-link").getAttribute("href")).toBe(INGRESS_PATH);
      }
      expect(root.querySelector('.block[data-block="today"] .panel-link').textContent).toBe("Zum Stundenplan");
      expect(root.querySelector('.block[data-block="letters"] .panel-link').textContent).toBe("Alle ansehen");
    });
  }

  it("keeps the configured order and skips blocks without content, head included", async () => {
    const hass = makeHass();
    hass.states["sensor.ranzenpost_alex_unread_posts"] = { ...hass.states["sensor.ranzenpost_alex_unread_posts"], state: "0", attributes: { posts: [] } };
    hass.states["sensor.ranzenpost_school_next_conference"] = { ...hass.states["sensor.ranzenpost_school_next_conference"], state: "unknown", attributes: {} };
    const card = await mountCard({ blocks: ["holidays", "noticeboard", "conferences", "letters"], children: ["alex"] }, hass);
    const root = card.shadowRoot;
    expect(blocksOf(root)).toEqual(["holidays", "letters"]);
    expect(root.textContent).not.toContain("Pinnwand");
    expect(root.textContent).not.toContain("Elternsprechtage");
  });

  it("stops at the item limit of the size and offers Show all into the app", async () => {
    const hass = makeHass();
    const letters = Array.from({ length: 7 }, (item, index) => ({ title: `Brief ${index + 1}`, sender: "Schule", date: "2026-09-01", child: "Alex" }));
    hass.states["sensor.ranzenpost_alex_unread_letters"] = { ...hass.states["sensor.ranzenpost_alex_unread_letters"], state: "7", attributes: { letters } };
    const compact = await mountCard({ blocks: [{ key: "letters", size: "compact" }], children: ["alex"] }, hass);
    const compactRoot = compact.shadowRoot;
    expect(compactRoot.querySelectorAll(".row.compact").length).toBe(3);
    expect(compactRoot.querySelector(".row-sub")).toBeNull();
    expect(compactRoot.querySelector(".row-all").getAttribute("href")).toBe(INGRESS_PATH);
    expect(compactRoot.querySelector(".panel-head .count.fresh").textContent).toBe("7");

    const normal = await mountCard({ blocks: ["letters"], children: ["alex"] }, hass);
    expect(normal.shadowRoot.querySelectorAll(".row:not(.row-all)").length).toBe(5);
    expect(texts(normal.shadowRoot, ".row-sub")[0]).toBe("Schule");
  });

  it("today in compact starts at the running lesson, normal keeps the end of school note", async () => {
    const compact = await mountCard({ blocks: [{ key: "today", size: "compact" }], children: ["alex"] }, makeHass());
    const compactRoot = compact.shadowRoot;
    expect(texts(compactRoot, ".row .row-title")).toEqual(["Maths", "English", "Art"]);
    expect(compactRoot.querySelector(".row-note")).toBeNull();
    const normal = await mountCard({ blocks: ["today"], children: ["alex"] }, makeHass());
    expect(normal.shadowRoot.querySelector(".row-note .dlg-text").textContent).toBe("Die letzte Stunde endet um 13:05.");
    expect(normal.shadowRoot.querySelector(".panel-head .count.fresh").textContent).toBe("2");
  });

  it("names the next lesson with day and time and the details in normal size", async () => {
    const card = await mountCard({ blocks: [{ key: "next_lesson", size: "normal" }], children: ["alex"] }, makeHass());
    const root = card.shadowRoot;
    expect(root.querySelector(".row-title").textContent).toBe("English");
    expect(root.querySelector(".row-meta").textContent).toBe("Heute · 09:50");
    expect(root.querySelector(".row-sub").textContent).toBe("R202 · Mr Stand-in · in 35 Minuten");
  });

  it("shows the holiday with the days to go and the conference with its date", async () => {
    const card = await mountCard({ blocks: ["holidays", "conferences"], children: ["alex"] }, makeHass());
    const root = card.shadowRoot;
    const holidays = root.querySelector('.block[data-block="holidays"]');
    expect(holidays.querySelector(".row-title").textContent).toBe("Autumn holidays");
    expect(holidays.querySelector(".row-meta").textContent).toBe("in 40 Tagen");
    const conferences = root.querySelector('.block[data-block="conferences"]');
    expect(conferences.querySelector(".row-title").textContent).toBe("Parent-teacher conference");
    expect(conferences.querySelector(".row-meta").textContent).toBe("05.11.");
    expect(conferences.querySelector(".row-sub").textContent).toBe("Parent-teacher conference · Main building");
  });

  it("lists the absences of the next fourteen days and today's changes with their kind", async () => {
    const card = await mountCard({ blocks: ["absences", { key: "changes", size: "compact" }], children: ["alex"] }, makeHass());
    const root = card.shadowRoot;
    const absences = root.querySelector('.block[data-block="absences"]');
    expect(absences.querySelector(".row-title").textContent).toBe("04.09.");
    expect(absences.querySelector(".row-sub").textContent).toBe("Sick note");
    const changes = root.querySelector('.block[data-block="changes"]');
    expect(texts(changes, ".row .row-title")).toEqual(["English", "Art"]);
    expect(texts(changes, ".row .tag")).toEqual(["Vertretung", "Entfällt"]);
    expect(changes.querySelectorAll(".row.compact").length).toBe(2);
  });

  it("renders the week grid and drops it when the week is empty", async () => {
    const card = await mountCard({ blocks: [{ key: "week", size: "compact" }], children: ["alex"] }, makeHass());
    expect(card.shadowRoot.querySelector('.block[data-block="week"] .tt.compact-cells')).not.toBeNull();
    const empty = await mountCard({ blocks: ["week"], children: ["kim"] }, makeHass());
    expect(empty.shadowRoot.querySelector(".block")).toBeNull();
  });

  it("groups child blocks per child and keeps the family-wide blocks once with child tags", async () => {
    const card = await mountCard({ blocks: ["today", "letters", "holidays"], title: "Familie" }, makeHass());
    const root = card.shadowRoot;
    expect(root.querySelector(".card-title").textContent).toBe("Familie");
    const members = [...root.querySelectorAll(".member")];
    expect(members.map((node) => node.dataset.child)).toEqual(["a1b2c3d4:child-1"]);
    expect(members[0].querySelector(".tt-child-head .who").textContent).toBe("Alex");
    expect(blocksOf(root)).toEqual(["today", "letters", "holidays"]);
    expect(texts(root, '.block[data-block="letters"] .row-tags .tag')).toEqual(["Alex", "Alex"]);
  });

  it("offers no block of a module the school lacks even when configured", async () => {
    const hass = makeHass();
    hass.states["sensor.ranzenpost_school_connection"].attributes.modules.letters = false;
    const card = await mountCard({ blocks: ["letters", "holidays"], children: ["alex"] }, hass);
    expect(blocksOf(card.shadowRoot)).toEqual(["holidays"]);
  });

  it("carries every block text in every language", async () => {
    const CardClass = customElements.get("ranzenpost-card");
    for (const language of Object.keys(CardClass.texts)) {
      for (const key of ALL_CARD_BLOCKS.concat(["chat"])) {
        expect(CardClass.texts[language][`block.${key}`], `${language}/${key}`).toBeTruthy();
        expect(CardClass.texts[language][`block.${key}.explain`], `${language}/${key}`).toBeTruthy();
      }
    }
  });
});
