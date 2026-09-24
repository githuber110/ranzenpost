import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("family view", () => {
  it("shows every child in a column with head, today, tomorrow, counts and the next holiday", async () => {
    const card = await mountCard({ view: "family" }, makeHass());
    const root = card.shadowRoot;
    const members = [...root.querySelectorAll(".tt-multi > .tt-child")];

    expect(root.querySelector("ha-card > .panel-head .section-label").textContent).toBe("Familie");
    expect(root.querySelector(".tt-multi").classList.contains("scrolls")).toBe(false);
    expect(members.map((node) => node.dataset.child)).toEqual(["a1b2c3d4:child-1", "a1b2c3d4:child-2"]);
    expect(texts(root, ".tt-child-head .who")).toEqual(["Alex", "Kim"]);
    expect(texts(root, ".tt-child-head .avatar")).toEqual(["A", "K"]);
    expect([...root.querySelectorAll(".tt-child-head .avatar")].map((node) => node.style.background)).toEqual([
      "rgb(14, 107, 112)",
      "rgb(122, 75, 156)",
    ]);
    expect(texts(members[0], ".panel-head .section-label")).toEqual(["Heute", "Morgen"]);
    expect(texts(members[0], ".panel-head .panel-meta")).toEqual(["Mi., 02.09.", "Do., 03.09."]);
    const alexDays = members[0].querySelectorAll(".rows.flat");
    expect([...alexDays].map((node) => node.dataset.day)).toEqual(["2026-09-02", "2026-09-03"]);
    expect(texts(alexDays[0], ".row-title")).toEqual(["Maths", "English", "Art"]);
    expect(texts(alexDays[1], ".row-title")).toEqual(["Biology"]);
    expect(alexDays[0].querySelector(".row-when.now").textContent).toBe("Jetzt");
    expect(alexDays[0].querySelectorAll(".row")[1].querySelector(".tag.open").textContent).toBe("Vertretung");
    expect(alexDays[0].querySelectorAll(".row")[2].querySelector(".tag.no").textContent).toBe("Entfällt");
    expect(alexDays[1].querySelector(".row").classList.contains("marked")).toBe(true);
    expect(alexDays[1].querySelector(".row .tag.exam").textContent).toBe("Prüfung");
    expect(alexDays[1].querySelector(".row-when")).toBeNull();
    expect(alexDays[0].querySelector(".row-note")).toBeNull();
    expect(texts(members[0], ".counts .count")).toEqual(["2Elternbriefe", "1Pinnwand", "2Änderungen"]);
    expect(texts(members[0], ".counts .badge")).toEqual(["2", "1", "2"]);
    expect(texts(members[1], ".counts .count")).toEqual(["Elternbriefe", "Pinnwand", "Änderungen"]);
    expect(members[1].querySelector(".counts .badge")).toBeNull();
    expect(texts(members[1], ".rows.flat .row-note .dlg-text")).toEqual(["Schulfrei", "Schulfrei"]);
    const holiday = root.querySelector("ha-card > .tt-hol.full");
    expect(holiday.querySelector(".ico-slot .ico")).not.toBeNull();
    expect(holiday.querySelector(".tt-hol-text .name").textContent).toBe("Autumn holidays");
    expect(holiday.querySelector(".tt-hol-text .meta").textContent).toBe("12.10. – 23.10.");
  });

  it("limits the columns to the listed children and the days to one", async () => {
    const card = await mountCard({ view: "family", children: ["kim"], days: 1, title: "Zuhause" }, makeHass());
    const root = card.shadowRoot;

    expect(root.querySelector("ha-card > .panel-head .section-label").textContent).toBe("Zuhause");
    expect(texts(root, ".tt-child-head .who")).toEqual(["Kim"]);
    expect(texts(root, ".tt-child .section-label")).toEqual(["Heute"]);
  });

  it("shows no holiday field when none is planned", async () => {
    const hass = makeHass({
      states: { "sensor.ranzenpost_school_next_holiday": { state: "none", attributes: {} } },
    });
    const card = await mountCard({ view: "family" }, hass);

    expect(card.shadowRoot.querySelector(".tt-hol")).toBeNull();
    expect(card.shadowRoot.querySelectorAll(".tt-child")).toHaveLength(2);
  });

  it("shows a badge with a plus beyond nine", async () => {
    const hass = makeHass({
      states: { "sensor.ranzenpost_alex_unread_letters": { state: "12", attributes: {} } },
    });
    const card = await mountCard({ view: "family" }, hass);

    expect(card.shadowRoot.querySelector(".counts .badge").textContent).toBe("9+");
  });
});
