import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass, ownEntriesCalls } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("today view", () => {
  it("renders the lessons of the day as rows of the today chapter", async () => {
    const card = await mountCard({ view: "today", child: "alex" }, makeHass());
    const root = card.shadowRoot;
    const rows = [...root.querySelectorAll(".rows.flat .row[data-uid]")];

    expect(root.querySelector(".rows.flat").dataset.day).toBe("2026-09-02");
    expect(rows.map((node) => node.dataset.uid)).toEqual([
      "lesson-20260902-p1@sample",
      "lesson-20260902-p2@sample",
      "lesson-20260902-p4@sample",
    ]);
    expect(texts(root, ".row .row-title")).toEqual(["Maths", "English", "Art"]);
    expect(texts(root, ".row .row-sub")).toEqual(["Mrs Example, R101", "Mr Stand-in · R202", "Ms Brush · R303"]);
    expect(texts(root, ".row .row-meta")).toEqual(["09:00", "09:50", "11:40"]);
    expect(rows[0].getAttribute("aria-current")).toBe("true");
    expect(rows[0].querySelector(".row-when.now").textContent).toBe("Jetzt");
    expect(rows[1].querySelector(".row-when.next").textContent).toBe("Nächste");
    expect(rows[1].querySelector(".tag.open").textContent).toBe("Vertretung");
    expect(rows[2].querySelector(".tag.no").textContent).toBe("Entfällt");
    expect(rows[2].querySelector(".row-title").style.textDecoration).toBe("line-through");
    expect(rows[0].querySelector(".row-title").style.textDecoration).toBe("");
    expect(rows[0].querySelector(".row-dot i").style.background).toBe("rgb(51, 102, 204)");
    expect(rows[2].querySelector(".row-dot i").getAttribute("style")).toBeNull();
    expect(rows[0].querySelector(".row-title").getAttribute("dir")).toBe("auto");
    expect(root.querySelectorAll(".row.past")).toHaveLength(0);
  });

  it("puts the child, the date, the change count and the end of school around the list", async () => {
    const card = await mountCard({ view: "today", child: "alex" }, makeHass());
    const root = card.shadowRoot;

    expect(root.querySelector("ha-card").getAttribute("dir")).toBe("ltr");
    expect(root.querySelector("ha-card").getAttribute("lang")).toBe("de");
    expect(root.querySelector(".panel-head .section-label").textContent).toBe("Alex");
    expect(root.querySelector(".panel-head .panel-meta").textContent).toBe("Mi., 02.09.");
    expect(root.querySelector(".panel-head .badge").textContent).toBe("2");
    expect(root.querySelector(".row.row-note .dlg-text").textContent).toBe("Die letzte Stunde endet um 13:05.");
  });

  it("dims past lessons and says when the day is over", async () => {
    vi.setSystemTime(new Date("2026-09-02T12:00:00Z"));
    const card = await mountCard({ view: "today", child: "alex" }, makeHass());
    const root = card.shadowRoot;

    expect([...root.querySelectorAll(".row[data-uid]")].map((row) => row.classList.contains("past"))).toEqual([true, true, true]);
    expect(root.querySelector(".row-when")).toBeNull();
    expect(root.querySelector(".row.row-note .dlg-text").textContent).toBe("Der Unterricht ist für heute vorbei.");
  });

  it("prefers a configured title and accepts the device id as the child", async () => {
    const card = await mountCard({ view: "today", child: "device-1", title: "Schule" }, makeHass());

    expect(card.shadowRoot.querySelector(".section-label").textContent).toBe("Schule");
    expect(texts(card.shadowRoot, ".row .row-title")).toEqual(["Maths", "English", "Art"]);
  });

  it("shows the free note for a child without lessons today", async () => {
    const card = await mountCard({ view: "today", child: "kim" }, makeHass());
    const root = card.shadowRoot;

    expect(root.querySelectorAll(".row[data-uid]")).toHaveLength(0);
    expect(root.querySelector(".rows.flat .row.row-note .dlg-text").textContent).toBe("Heute ist schulfrei.");
    expect(root.querySelectorAll(".row-note")).toHaveLength(1);
  });

  it("names an unknown child and asks for one when none is configured", async () => {
    const unknown = await mountCard({ view: "today", child: "nobody" }, makeHass());
    expect(unknown.shadowRoot.querySelector(".empty b").textContent).toBe("Person „nobody“ nicht gefunden.");
    expect(unknown.shadowRoot.querySelector(".empty .ico-slot .ico")).not.toBeNull();

    const missing = await mountCard({ view: "today" }, makeHass());
    expect(missing.shadowRoot.querySelector(".empty b").textContent).toBe("Keine Person gewählt. Trage in der Karte „child“ ein.");
  });

  it("defaults to the today view and rejects an unknown view", async () => {
    const card = await mountCard({ child: "alex" }, makeHass());
    expect(card.shadowRoot.querySelectorAll(".row[data-uid]")).toHaveLength(3);

    const broken = document.createElement("ranzenpost-card");
    expect(() => broken.setConfig({ view: "month" })).toThrow(/today, week or family/);
  });

  it("tells when the calendar cannot be read", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const hass = makeHass();
    hass.callApi = async () => {
      throw new Error("boom");
    };
    const card = await mountCard({ view: "today", child: "alex" }, hass);

    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Nicht erreichbar");
    expect(card.shadowRoot.querySelector(".empty p").textContent).toBe("Ranzenpost ist gerade nicht erreichbar.");
  });

  it("follows the dark theme of Home Assistant and otherwise the system", async () => {
    const dark = await mountCard({ view: "today", child: "alex" }, { ...makeHass(), themes: { darkMode: true } });
    expect(dark.getAttribute("data-theme")).toBe("dark");

    const light = await mountCard({ view: "today", child: "alex" }, { ...makeHass(), themes: { darkMode: false } });
    expect(light.getAttribute("data-theme")).toBe("light");

    const system = await mountCard({ view: "today", child: "alex" }, makeHass());
    expect(system.hasAttribute("data-theme")).toBe(false);
    const style = system.shadowRoot.querySelector("style").textContent;
    expect(style).toContain(':host([data-theme="dark"]) { --bg: #0e1412;');
    expect(style).toContain('@media (prefers-color-scheme: dark) { :host(:not([data-theme="light"])) { --bg: #0e1412;');
    expect(style).toContain("--accent: #0e6b70;");
    expect(style).toContain("--accent: #4fbdba;");
    expect(style).toContain('--font-text: "Schibsted Grotesk", system-ui');
  });
});

describe("own entries", () => {
  const fresh = async (config, hass) => {
    customElements.get("ranzenpost-card").resetCaches();
    return mountCard(config, hass);
  };
  const OWN = "calendar.ranzenpost_alex_own_entries";
  const HOLIDAY = "calendar.ranzenpost_school_holidays";
  const own = (uid, summary, start, end) => ({ uid, summary, description: "", location: "", start, end, all_day: false, cancelled: false, color: "", subject_code: "", subject: "", kind: "own_entries" });

  it("show without the Home Assistant calendar and never read that calendar", async () => {
    for (const ownEntries of [false, true]) {
      const hass = makeHass({ ownEntries, ownEntryList: true });
      const card = await fresh({ view: "today", child: "alex" }, hass);
      expect(texts(card.shadowRoot, ".row.own .row-title")).toEqual(["Chess club"]);
      expect(apiCallsFor(hass, OWN)).toEqual([]);
      expect(ownEntriesCalls(hass)).toEqual([{ type: "ranzenpost/own_entries", device_id: "device-1", start: "2026-09-02", end: "2026-09-03" }]);
    }
  });

  it("are not asked for a child without a timetable", async () => {
    const hass = makeHass({ withoutKeys: ["lessons"], ownEntryList: true });
    const card = await fresh({ view: "today", child: "alex" }, hass);
    expect(card.shadowRoot.querySelector(".row.own")).toBeNull();
    expect(ownEntriesCalls(hass)).toEqual([]);
  });

  it("that cannot be read show the card as unreachable instead of a day without entries", async () => {
    const card = await fresh({ view: "today", child: "alex" }, makeHass({ ownEntriesError: true }));
    expect(card.shadowRoot.querySelector(".row.own")).toBeNull();
    expect(card.shadowRoot.querySelector(".empty b").textContent).toBe("Nicht erreichbar");
  });

  it("join the time line of today by their start and read like the app", async () => {
    const hass = makeHass({ ownEntries: true, events: { [OWN]: [own("own-early", "Swim", "2026-09-02T08:00:00+02:00", "2026-09-02T08:30:00+02:00"), own("own-late", "Chess club", "2026-09-02T15:00:00+02:00", "2026-09-02T16:00:00+02:00")] } });
    const card = await fresh({ view: "today", child: "alex" }, hass);
    const root = card.shadowRoot;
    expect(texts(root, ".row[data-uid] .row-title")).toEqual(["Swim", "Maths", "English", "Art", "Chess club"]);
    const chess = root.querySelector('.row.own[data-uid="own-late"]');
    expect(chess.querySelector(".row-sub").textContent).toBe("Eigener Eintrag · bis 16:00");
    expect(chess.querySelector(".row-meta").textContent).toBe("15:00");
    expect(chess.querySelector(".row-dot i").classList.contains("ring")).toBe(true);
    expect(root.querySelector('.row.own[data-uid="own-early"]').classList.contains("past")).toBe(true);
    expect(root.querySelector(".row.row-note .dlg-text").textContent).toBe("Die letzte Stunde endet um 13:05.");
  });

  it("show on a holiday below the holiday and on a free day below the free note", async () => {
    const holiday = { uid: "holiday-today", summary: "Herbstferien", description: "", location: "", start: "2026-09-02", end: "2026-09-03", all_day: true, cancelled: false, color: "" };
    const events = { [OWN]: [own("own-hol", "Riding", "2026-09-02T10:00:00+02:00", "2026-09-02T11:00:00+02:00")], "calendar.ranzenpost_alex_lessons": [], [HOLIDAY]: [holiday] };
    const card = await fresh({ view: "today", child: "alex" }, makeHass({ ownEntries: true, events }));
    const root = card.shadowRoot;
    expect(texts(root, ".rows.flat .row-note .dlg-text")).toEqual(["Herbstferien"]);
    expect(texts(root, ".row.own .row-title")).toEqual(["Riding"]);
    const free = await fresh({ view: "today", child: "alex" }, makeHass({ ownEntries: true, events: { [OWN]: events[OWN], "calendar.ranzenpost_alex_lessons": [], [HOLIDAY]: [] } }));
    expect(texts(free.shadowRoot, ".rows.flat .row-note .dlg-text")).toEqual(["Heute ist schulfrei."]);
    expect(texts(free.shadowRoot, ".row.own .row-title")).toEqual(["Riding"]);
  });

  it("fill the today block, and the compact block drops what is over", async () => {
    const events = { [OWN]: [own("own-early", "Swim", "2026-09-02T08:00:00+02:00", "2026-09-02T08:30:00+02:00"), own("own-late", "Chess club", "2026-09-02T15:00:00+02:00", "2026-09-02T16:00:00+02:00")] };
    const normal = await fresh({ blocks: ["today"], children: ["alex"] }, makeHass({ ownEntries: true, events }));
    expect(texts(normal.shadowRoot, ".row.own .row-title")).toEqual(["Swim", "Chess club"]);
    const compact = await fresh({ blocks: [{ key: "today", size: "compact" }], children: ["alex"] }, makeHass({ ownEntries: true, events }));
    expect(texts(compact.shadowRoot, ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
    const weekOnly = await fresh({ view: "week", child: "alex" }, makeHass({ ownEntries: true, events }));
    expect(weekOnly.shadowRoot.querySelector(".row.own")).toBeNull();
  });

  it("show in the block on a weekend day that has own entries only", async () => {
    vi.setSystemTime(new Date("2026-09-05T08:00:00Z"));
    const events = { [OWN]: [own("own-sat", "Football", "2026-09-05T11:00:00+02:00", "2026-09-05T12:30:00+02:00")] };
    const card = await fresh({ blocks: ["today"], children: ["alex"] }, makeHass({ ownEntries: true, events }));
    expect(texts(card.shadowRoot, ".row.own .row-title")).toEqual(["Football"]);
    const without = await fresh({ blocks: ["today"], children: ["alex"] }, makeHass({ ownEntries: true, events: { [OWN]: [] } }));
    expect(without.shadowRoot.querySelector(".row.own")).toBeNull();
  });
});
