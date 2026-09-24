import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard } from "./loadCard.js";

const TIMETABLE_KEYS = [
  "lessons",
  "exams",
  "current_lesson",
  "next_lesson",
  "school_end_today",
  "next_school_day",
  "changes_today",
  "next_exam",
  "exams_upcoming",
  "timetable_last_updated",
  "school_day_today",
  "timetable_changed_today",
  "timetable_changed",
];

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a school without a timetable module", () => {
  it("shows a calm empty state in the today view instead of an error", async () => {
    const hass = makeHass({ withoutKeys: TIMETABLE_KEYS });
    const card = await mountCard({ view: "today", child: "alex" }, hass);
    const root = card.shadowRoot;
    expect(root.querySelector(".panel-head .section-label").textContent).toBe("Alex");
    expect(root.querySelector(".empty b").textContent).toBe("Diese Schule stellt keinen Stundenplan bereit.");
    expect(root.querySelector(".empty .ico")).not.toBeNull();
    expect(root.querySelector(".rows")).toBeNull();
    expect(hass.calls.api.length).toBe(0);
  });

  it("shows the same calm state in the week view", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, makeHass({ withoutKeys: TIMETABLE_KEYS }));
    const root = card.shadowRoot;
    expect(root.querySelector(".tt-child-head .who").textContent).toBe("Alex");
    expect(root.querySelector(".empty b").textContent).toBe("Diese Schule stellt keinen Stundenplan bereit.");
    expect(root.querySelector(".tt")).toBeNull();
    expect(root.querySelector(".legend")).toBeNull();
  });

  it("keeps the counts in the family view and says so per child", async () => {
    const card = await mountCard({ view: "family" }, makeHass({ withoutKeys: TIMETABLE_KEYS }));
    const root = card.shadowRoot;
    const members = [...root.querySelectorAll(".tt-child")];
    expect(members.length).toBe(2);
    for (const member of members) {
      expect(member.querySelector(".empty b").textContent).toBe("Diese Schule stellt keinen Stundenplan bereit.");
      expect(member.querySelectorAll(".counts .count").length).toBe(3);
    }
  });

  it("a missing letters sensor counts as zero, not as an error", async () => {
    const card = await mountCard({ view: "family" }, makeHass({ withoutKeys: ["unread_letters"] }));
    const root = card.shadowRoot;
    const counts = [...root.querySelectorAll(".tt-child")][0].querySelectorAll(".counts .count");
    expect(counts[0].textContent).toBe("Elternbriefe");
    expect(counts[0].querySelector(".badge")).toBeNull();
  });
});
