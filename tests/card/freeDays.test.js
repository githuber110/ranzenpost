import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LESSONS = "calendar.ranzenpost_alex_lessons";

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

function holiday(summary, start, end) {
  return { uid: `${summary}@sample`, summary, description: "", location: "", start, end, all_day: true, cancelled: false, color: "" };
}

function lesson(uid, subject, start, end) {
  return { uid, summary: subject, description: "", location: "R1", start, end, all_day: false, cancelled: false, color: "#3366cc", subject_code: subject, subject, teacher: "" };
}

const MONDAY = [lesson("mon-1", "MA", "2026-09-07T08:00:00+02:00", "2026-09-07T08:45:00+02:00")];

describe("week block in a holiday week", () => {
  it("shows the holiday field instead of disappearing", async () => {
    freezeClock("2026-10-14T08:00:00Z");
    const card = await mountCard({ blocks: ["week"], children: ["alex"] }, makeHass());
    const shown = block(card.shadowRoot, "week");

    expect(shown).not.toBeNull();
    expect(texts(shown, ".tt-hol.full .name")).toEqual(["Autumn holidays"]);
  });
});

describe("today block on a day without held lessons", () => {
  for (const mode of ["15:00", "end"]) {
    it(`switches to the next school day right away on a Saturday with switch ${mode}`, async () => {
      freezeClock("2026-09-05T06:00:00Z");
      const card = await mountCard({ blocks: [{ key: "today", switch: mode }], children: ["alex"] }, makeHass({ events: { [LESSONS]: MONDAY } }));
      const shown = block(card.shadowRoot, "today");

      expect(texts(shown, ".panel-head .section-label")).toEqual(["Montag"]);
      expect(texts(shown, ".row[data-uid] .row-title")).toEqual(["MA"]);
    });
  }

  it("switches in the morning of a fully cancelled day", async () => {
    freezeClock("2026-09-04T05:00:00Z");
    const lessons = [{ ...lesson("fri-1", "D", "2026-09-04T08:00:00+02:00", "2026-09-04T08:45:00+02:00"), cancelled: true }, ...MONDAY];
    const card = await mountCard({ blocks: [{ key: "today", switch: "15:00" }], children: ["alex"] }, makeHass({ events: { [LESSONS]: lessons } }));

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Montag"]);
  });

  it("keeps today on a school day before the chosen time", async () => {
    freezeClock("2026-09-04T05:00:00Z");
    const lessons = [lesson("fri-1", "D", "2026-09-04T08:00:00+02:00", "2026-09-04T08:45:00+02:00"), ...MONDAY];
    const card = await mountCard({ blocks: [{ key: "today", switch: "15:00" }], children: ["alex"] }, makeHass({ events: { [LESSONS]: lessons } }));

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);
  });
});

describe("next school day beyond the window", () => {
  it("names the coming holiday that the holiday data covers", async () => {
    freezeClock("2026-10-09T10:00:00Z");
    const card = await mountCard({ blocks: ["next_day"], children: ["alex"] }, makeHass({ events: { [LESSONS]: [] } }));
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".row-note .dlg-text")).toEqual(["Autumn holidays · 12.10. – 23.10.", "Der nächste Schultag steht noch nicht im Stundenplan."]);
  });
});

describe("holiday block dates", () => {
  const events = {
    holidays: [holiday("Tag der Deutschen Einheit", "2026-10-03", "2026-10-04"), holiday("Autumn holidays", "2026-10-12", "2026-10-24")],
  };

  it("names a single free day once instead of as a range", async () => {
    const card = await mountCard({ blocks: [{ key: "holidays", size: "normal" }], children: ["alex"] }, makeHass({ events }));
    const shown = block(card.shadowRoot, "holidays");

    expect(texts(shown, ".row-sub")).toEqual(["Sa., 03.10.", "12.10. – 23.10."]);
  });

  it("says until when running holidays last instead of today", async () => {
    freezeClock("2026-10-14T08:00:00Z");
    const card = await mountCard({ blocks: [{ key: "holidays", size: "normal" }], children: ["alex"] }, makeHass({ events }));
    const shown = block(card.shadowRoot, "holidays");

    expect(texts(shown, ".row-title")).toEqual(["Autumn holidays"]);
    expect(texts(shown, ".row-meta")).toEqual(["bis 23.10."]);
  });
});
