import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LESSONS = "calendar.ranzenpost_alex_lessons";
const CHANGES = "sensor.ranzenpost_alex_changes_today";
const NEXT_DAY = { blocks: ["next_day"], children: ["alex"] };

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function lesson(uid, subject, start, end, extra = {}) {
  return {
    uid,
    summary: subject,
    description: "",
    location: "R1",
    start,
    end,
    all_day: false,
    cancelled: false,
    color: "#3366cc",
    subject_code: subject,
    subject,
    teacher: "",
    substitution: false,
    ...extra,
  };
}

function changes(list) {
  return { state: String(list.length), attributes: { changes: list } };
}

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

const FRIDAY_AND_MONDAY = [
  lesson("fri-1", "D", "2026-09-04T08:00:00+02:00", "2026-09-04T08:45:00+02:00"),
  lesson("mon-1", "MA", "2026-09-07T08:00:00+02:00", "2026-09-07T08:45:00+02:00", { teacher: "Stand-in", location: "R9", substitution: true }),
  lesson("mon-2", "EN", "2026-09-07T08:50:00+02:00", "2026-09-07T09:35:00+02:00", { cancelled: true, teacher: "Example", location: "R2" }),
];

describe("next school day block", () => {
  it("shows tomorrow with its lessons and exam under the label tomorrow", async () => {
    const card = await mountCard(NEXT_DAY, makeHass());
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Morgen"]);
    expect(texts(shown, ".panel-head .panel-meta")).toEqual(["Do., 03.09."]);
    expect(shown.querySelector(".rows.flat").dataset.day).toBe("2026-09-03");
    expect(texts(shown, ".row-title")).toEqual(["Biology"]);
    expect(shown.querySelector(".row .tag.exam")).not.toBeNull();
    expect(shown.querySelector(".row-when")).toBeNull();
    expect(shown.querySelector(".panel-link")).not.toBeNull();
  });

  it("skips the weekend, names the weekday and date and shows the substitutions of that day", async () => {
    freezeClock("2026-09-04T12:00:00Z");
    const card = await mountCard(NEXT_DAY, makeHass({ events: { [LESSONS]: FRIDAY_AND_MONDAY } }));
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Montag"]);
    expect(texts(shown, ".panel-head .panel-meta")).toEqual(["07.09.2026"]);
    expect(texts(shown, ".row-title")).toEqual(["MA", "EN"]);
    expect(texts(shown, ".row-sub")).toEqual(["Stand-in · R9", "Example · R2"]);
    expect(shown.querySelectorAll(".row")[0].querySelector(".tag.open").textContent).toBe("Vertretung");
    expect(shown.querySelectorAll(".row")[1].querySelector(".tag.no").textContent).toBe("Entfällt");
    const count = shown.querySelector(".panel-head .count");
    expect(count.textContent).toBe("2");
    expect(count.getAttribute("aria-label")).toBe("Änderungen: 2");
  });

  it("counts a fully cancelled day as the next school day", async () => {
    const lessons = [lesson("thu-1", "D", "2026-09-03T08:00:00+02:00", "2026-09-03T08:45:00+02:00", { cancelled: true })];
    const card = await mountCard(NEXT_DAY, makeHass({ events: { [LESSONS]: lessons } }));
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Morgen"]);
    expect(shown.querySelector(".row .tag.no")).not.toBeNull();
  });

  it("says honestly that the next school day is unknown and names the holiday that starts tomorrow", async () => {
    freezeClock("2026-10-11T10:00:00Z");
    const card = await mountCard(NEXT_DAY, makeHass());
    const shown = block(card.shadowRoot, "next_day");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Nächster Schultag"]);
    expect(texts(shown, ".row-note .dlg-text")).toEqual(["Autumn holidays", "Der nächste Schultag steht noch nicht im Stundenplan."]);
    expect(shown.querySelector(".row[data-uid]")).toBeNull();
  });

  it("asks the lessons four weeks ahead so a holiday week does not hide the next school day", async () => {
    const hass = makeHass();
    await mountCard(NEXT_DAY, hass);
    const call = apiCallsFor(hass, LESSONS).at(-1);
    const end = new Date(decodeURIComponent(/end=(.+)$/.exec(call.path)[1]));

    expect(end.toISOString()).toBe("2026-09-29T22:00:00.000Z");
  });

  it("is offered in the editor next to today", async () => {
    const editor = CardClass.getConfigElement();
    document.body.appendChild(editor);
    editor.setConfig({ blocks: ["today"] });
    editor.hass = makeHass();
    await editor.settled;

    const row = editor.shadowRoot.querySelector('.block-row[data-block="next_day"]');
    expect(row.querySelector(".block-name").textContent).toBe("Nächster Schultag");
    expect(row.querySelector(".hint").textContent).toBe("Stunden des nächsten Schultags mit Vertretungen und Ausfällen.");
  });
});

describe("today block that switches to the next school day", () => {
  it("keeps today until the switch is set", async () => {
    freezeClock("2026-09-02T18:00:00Z");
    const card = await mountCard({ blocks: ["today"], children: ["alex"] }, makeHass());

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);
  });

  it("switches after the last held lesson has ended", async () => {
    const config = { blocks: [{ key: "today", switch: "end" }], children: ["alex"] };
    let card = await mountCard(config, makeHass());
    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);

    freezeClock("2026-09-02T09:00:00Z");
    CardClass.resetCaches();
    card = await mountCard(config, makeHass());
    const shown = block(card.shadowRoot, "today");
    expect(texts(shown, ".panel-head .section-label")).toEqual(["Morgen"]);
    expect(texts(shown, ".row-title")).toEqual(["Biology"]);
  });

  it("switches from the chosen time on", async () => {
    const config = { blocks: [{ key: "today", switch: "15:00" }], children: ["alex"] };
    freezeClock("2026-09-02T12:59:00Z");
    let card = await mountCard(config, makeHass());
    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);

    freezeClock("2026-09-02T13:00:00Z");
    CardClass.resetCaches();
    card = await mountCard(config, makeHass());
    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Morgen"]);
  });

  it("reads a time that a YAML 1.1 loader turned into minutes", async () => {
    freezeClock("2026-09-02T13:00:00Z");
    const card = await mountCard({ blocks: [{ key: "today", switch: 900 }], children: ["alex"] }, makeHass());

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Morgen"]);
  });

  it("switches after the last lesson even when today carries an all-day notice", async () => {
    freezeClock("2026-09-02T12:00:00Z");
    const notice = { uid: "notice", summary: "Notice", description: "", location: "", start: "2026-09-02", end: "2026-09-03", all_day: true, cancelled: false, color: "", substitution: false };
    const lessons = [
      lesson("wed-1", "D", "2026-09-02T08:00:00+02:00", "2026-09-02T08:45:00+02:00"),
      notice,
      lesson("thu-1", "MA", "2026-09-03T08:00:00+02:00", "2026-09-03T08:45:00+02:00"),
    ];
    const card = await mountCard({ blocks: [{ key: "today", switch: "end" }], children: ["alex"] }, makeHass({ events: { [LESSONS]: lessons } }));

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Morgen"]);
  });

  it("ignores a switch value it does not understand", async () => {
    freezeClock("2026-09-02T20:00:00Z");
    const card = await mountCard({ blocks: [{ key: "today", switch: "25:00" }], children: ["alex"] }, makeHass());

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);
  });

  it("lets the editor choose off, after the last lesson or a time", async () => {
    const editor = CardClass.getConfigElement();
    document.body.appendChild(editor);
    editor.setConfig({ blocks: ["today", "letters"] });
    editor.hass = makeHass();
    await editor.settled;
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
    const set = (selector, value) => {
      const field = editor.shadowRoot.querySelector(selector);
      field.value = value;
      field.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    };

    expect(editor.shadowRoot.querySelector("select[name=switch_today]").value).toBe("off");
    expect(editor.shadowRoot.querySelector('.block-row[data-block="letters"] select[name=switch_today]')).toBeNull();
    set("select[name=switch_today]", "end");
    expect(emitted.at(-1).blocks).toEqual([{ key: "today", switch: "end" }, "letters"]);
    set("select[name=switch_today]", "time");
    expect(emitted.at(-1).blocks).toEqual([{ key: "today", switch: "15:00" }, "letters"]);
    const field = editor.shadowRoot.querySelector("input[name=switch_time_today]");
    set("input[name=switch_time_today]", "16:30");
    expect(emitted.at(-1).blocks).toEqual([{ key: "today", switch: "16:30" }, "letters"]);
    expect(editor.shadowRoot.querySelector("input[name=switch_time_today]")).toBe(field);
    expect(editor.shadowRoot.querySelector("input[name=switch_time_today]").getAttribute("aria-label")).toBe("Uhrzeit für Heute");
    set("select[name=switch_today]", "off");
    expect(emitted.at(-1).blocks).toEqual(["today", "letters"]);
    expect(editor.shadowRoot.querySelector("input[name=switch_time_today]")).toBeNull();
  });
});

describe("parallel lessons at the same time", () => {
  const G = lesson("p6-0", "G", "2026-09-02T12:10:00+02:00", "2026-09-02T12:55:00+02:00", { location: "A3.07", color: "#22d3ee" });
  const GB = lesson("p6-1", "GB", "2026-09-02T12:10:00+02:00", "2026-09-02T12:55:00+02:00", { location: "B1.01", color: "#ff69b4" });
  const TODAY = { blocks: ["today"], children: ["alex"] };
  const cancelled = (code, room) => ({ start: "2026-09-02T12:10:00+02:00", subject: code, subject_code: code, teacher: "", room, cancelled: true, substitution: false });

  it("keeps each subject when both are cancelled", async () => {
    const hass = makeHass({
      events: { [LESSONS]: [{ ...G, cancelled: true }, { ...GB, cancelled: true }] },
      states: { [CHANGES]: changes([cancelled("G", "A3.07"), cancelled("GB", "B1.01")]) },
    });
    const card = await mountCard(TODAY, hass);
    const shown = block(card.shadowRoot, "today");

    expect(texts(shown, ".row-title")).toEqual(["G", "GB"]);
    expect(texts(shown, ".row-sub")).toEqual(["A3.07", "B1.01"]);
    expect(shown.querySelectorAll(".tag.no")).toHaveLength(2);
  });

  it("cancels only the lesson whose change names it, also for an older app without substitution field", async () => {
    const older = ({ substitution, ...rest }) => rest;
    const hass = makeHass({
      events: { [LESSONS]: [older(G), older(GB)] },
      states: { [CHANGES]: changes([cancelled("GB", "B1.01")]) },
    });
    const card = await mountCard(TODAY, hass);
    const rows = [...block(card.shadowRoot, "today").querySelectorAll(".row[data-uid]")];

    expect(rows.map((row) => row.querySelector(".row-title").textContent)).toEqual(["G", "GB"]);
    expect(rows[0].querySelector(".tag.no")).toBeNull();
    expect(rows[1].querySelector(".tag.no")).not.toBeNull();
  });

  it("leaves an ambiguous change unmatched instead of copying it to both lessons", async () => {
    const older = ({ substitution, ...rest }) => rest;
    const ambiguous = { start: "2026-09-02T12:10:00+02:00", subject: "X", subject_code: "", teacher: "Other", room: "Z9", cancelled: true, substitution: false };
    const hass = makeHass({ events: { [LESSONS]: [older(G), older(GB)] }, states: { [CHANGES]: changes([ambiguous]) } });
    const card = await mountCard(TODAY, hass);
    const shown = block(card.shadowRoot, "today");

    expect(texts(shown, ".row-title")).toEqual(["G", "GB"]);
    expect(shown.querySelectorAll(".tag.no")).toHaveLength(0);
  });

  it("shows the room of a normal lesson instead of the first line of its description", async () => {
    const hass = makeHass({ events: { [LESSONS]: [{ ...G, description: "Datum: 02.09.2026\nZeit: 12:10" }] }, states: { [CHANGES]: changes([]) } });
    const card = await mountCard(TODAY, hass);

    expect(texts(block(card.shadowRoot, "today"), ".row-sub")).toEqual(["A3.07"]);
  });
});
