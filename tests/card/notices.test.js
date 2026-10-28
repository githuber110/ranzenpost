import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fixture, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LESSONS = "calendar.ranzenpost_alex_lessons";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function notice(uid, summary, description, day, next) {
  return { uid, summary, description, location: "", start: day, end: next, all_day: true, cancelled: false, color: "" };
}

function lesson(uid, subject, start, end) {
  return { uid, summary: subject, description: "", location: "R1", start, end, all_day: false, cancelled: false, color: "#3366cc", subject_code: subject, subject, teacher: "" };
}

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

const STALE = notice("tag-notice-stale@sample", "Ranzenpost: keine neuen Daten", "Seit 01.09.2026 10:00 kamen keine neuen Daten.", "2026-09-02", "2026-09-03");
const NO_DATA = notice("tag-notice-nodata@sample", "Ranzenpost: noch keine Daten", "Es wurden noch keine Stundenplandaten geholt.", "2026-09-02", "2026-09-03");
const UNSCHEDULED = notice("tag-20260903-unscheduled@sample", "Stunden ohne Uhrzeit", "Für diese Stunden liefert IServ keine Startzeit:\nMaths", "2026-09-03", "2026-09-04");

describe("all-day notices in the lessons calendar", () => {
  it("show as a note with their own text and never as a lesson at midnight", async () => {
    const hass = makeHass({ events: { [LESSONS]: [...fixture("events_lessons"), STALE] } });
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, hass);
    const shown = block(card.shadowRoot, "today");

    expect(texts(shown, ".row[data-uid] .row-title")).toEqual(["Maths", "Art"]);
    expect(texts(shown, ".row-meta")).not.toContain("00:00");
    expect(shown.querySelector('.row[aria-current="true"]').dataset.uid).toBe("lesson-20260902-p1@sample");
    const note = shown.querySelector(".row-note.notice");
    expect(note.querySelector("b").textContent).toBe("Ranzenpost: keine neuen Daten");
    expect(note.textContent).toContain("Seit 01.09.2026 10:00 kamen keine neuen Daten.");
  });

  it("explain a day without data instead of calling it free", async () => {
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, makeHass({ events: { [LESSONS]: [NO_DATA] } }));
    const shown = block(card.shadowRoot, "today");

    expect(shown.querySelector(".row[data-uid]")).toBeNull();
    expect(texts(shown, ".row-note b")).toEqual(["Ranzenpost: noch keine Daten"]);
    expect(shown.textContent).not.toContain("Heute ist schulfrei.");
  });

  it("never make a day the next school day", async () => {
    const lessons = [UNSCHEDULED, lesson("fri-1", "Sport", "2026-09-04T08:00:00+02:00", "2026-09-04T09:30:00+02:00")];
    const card = await mountCard({ blocks: ["next_day"], children: ["alex"] }, makeHass({ events: { [LESSONS]: lessons } }));
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Freitag"]);
    expect(texts(shown, ".row[data-uid] .row-title")).toEqual(["Sport"]);
  });

  it("stay out of the week grid", async () => {
    const hass = makeHass({ events: { [LESSONS]: [...fixture("events_lessons"), STALE, UNSCHEDULED] } });
    const card = await mountCard({ blocks: ["week"], children: ["alex"] }, hass);
    const shown = block(card.shadowRoot, "week");

    expect(texts(shown, ".tt-hour b")).not.toContain("00:00");
    expect(shown.querySelector('[data-uid="tag-notice-stale@sample"]')).toBeNull();
  });

  it("show in the family view above the lessons of the day", async () => {
    const hass = makeHass({ events: { [LESSONS]: [...fixture("events_lessons"), STALE] } });
    const card = await mountCard({ view: "family", children: ["alex"] }, hass);
    const member = card.shadowRoot.querySelector(".tt-child");

    expect(texts(member, ".row-note.notice b")).toEqual(["Ranzenpost: keine neuen Daten"]);
    expect(texts(member, ".rows.flat")[0]).not.toContain("00:00");
  });
});
