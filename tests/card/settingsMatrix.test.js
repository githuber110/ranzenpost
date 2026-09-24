import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SCHEMA from "../settings-schema.json";
import { CHILDREN, INGRESS_PATH, lessonsOf, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LESSONS_ALEX = "calendar.ranzenpost_alex_lessons";
const EXAMS_ALEX = "calendar.ranzenpost_alex_exams";
const HOLIDAYS_SCHOOL = "calendar.ranzenpost_school_holidays";
const HOLIDAY_STATE = "sensor.ranzenpost_school_next_holiday";
const LETTERS_STATE = "sensor.ranzenpost_alex_unread_letters";
const CHANGES_STATE = "sensor.ranzenpost_alex_changes_today";

const MATHS_UID = "lesson-20260902-p1@sample";
const SPORT_UID = "lesson-20260904-p1@sample";

const TODAY = { view: "today", child: "alex" };
const WEEK = { view: "week", child: "alex" };
const FAMILY = { view: "family" };
const SHIFTED = { start: "2026-09-02T10:00:00+02:00", end: "2026-09-02T10:45:00+02:00" };
const TWO_BLOCKS = { blocks: [{ key: "today", size: "normal" }, { key: "letters", size: "normal" }], children: ["alex"] };

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function lessonsWith(uid, patch) {
  return clone(lessonsOf(CHILDREN[0].id)).map((lesson) => (lesson.uid === uid ? { ...lesson, ...patch } : lesson));
}

function changesWith(entries) {
  return { state: String(entries.length), attributes: { changes: entries } };
}

function withLessons(uid, patch) {
  return () => makeHass({ events: { [LESSONS_ALEX]: lessonsWith(uid, patch) } });
}

function allDay(uid, summary, start, end) {
  return { uid, summary, description: "", location: "", start, end, all_day: true, cancelled: false, color: "", subject_code: "", subject: "" };
}

function mathsExam() {
  return [
    {
      uid: "exam-mark-test@sample",
      summary: "Exam: Maths",
      description: "",
      location: "",
      start: "2026-09-02T09:00:00+02:00",
      end: "2026-09-02T09:45:00+02:00",
      all_day: false,
      cancelled: false,
      color: "",
      subject_code: "MA",
      subject: "Maths",
    },
  ];
}

function mathsCancelled() {
  return makeHass({
    states: {
      [CHANGES_STATE]: changesWith([
        { start: "2026-09-02T09:00:00+02:00", teacher: "", room: "", cancelled: true, substitution: false },
      ]),
    },
  });
}

function noChanges() {
  return makeHass({ states: { [CHANGES_STATE]: changesWith([]) } });
}

function cellOf(root, uid) {
  return root.querySelector(`.tt-cell[data-uid="${uid}"]`);
}

function rowOf(root, uid) {
  return root.querySelector(`.row[data-uid="${uid}"]`);
}

function blockKeys(root) {
  return [...root.querySelectorAll(".block")].map((node) => node.dataset.block);
}

function lettersCount(root) {
  const counts = [...root.querySelectorAll(".tt-child")][0].querySelectorAll(".counts .count");
  return [...counts].find((node) => node.textContent.includes("Elternbriefe"));
}

const OWN_ALEX = "calendar.ranzenpost_alex_own_entries";

const MATRIX = [
  {
    name: "own_entries_ha",
    surface: "today own entries",
    keys: ["own_entries_ha", "own_entries"],
    stages: [
      { config: TODAY, hass: () => makeHass({ ownEntryList: true }), check: (root) => expect(texts(root, ".row.own .row-title")).toEqual(["Chess club"]) },
      {
        config: TODAY,
        hass: () => makeHass({ ownEntries: true, ownEntryList: true }),
        check: (root) => {
          expect(texts(root, ".row.own .row-title")).toEqual(["Chess club"]);
          expect(texts(root, ".row-title").indexOf("Chess club")).toBeGreaterThan(texts(root, ".row-title").indexOf("Maths"));
        },
      },
      {
        config: TODAY,
        hass: () => makeHass({ ownEntries: true, events: { [OWN_ALEX]: [] } }),
        check: (root) => expect(root.querySelector(".row.own")).toBeNull(),
      },
    ],
  },
  {
    name: "period_time",
    surface: "today row time",
    keys: ["period_times"],
    stages: [
      { config: TODAY, hass: () => makeHass(), check: (root) => expect(texts(root, ".row .row-meta")[0]).toBe("09:00") },
      {
        config: TODAY,
        hass: withLessons(MATHS_UID, SHIFTED),
        check: (root) => {
          expect(texts(root, ".row .row-meta")).toContain("10:00");
          expect(texts(root, ".row .row-meta")).not.toContain("09:00");
        },
      },
    ],
  },
  {
    name: "period_time",
    surface: "week cell",
    keys: ["period_times"],
    stages: [
      { config: WEEK, hass: () => makeHass(), check: (root) => expect(cellOf(root, MATHS_UID).style.gridRow).toBe("3") },
      { config: WEEK, hass: withLessons(MATHS_UID, SHIFTED), check: (root) => expect(cellOf(root, MATHS_UID).style.gridRow).toBe("4") },
    ],
  },
  {
    name: "subject_name",
    surface: "today row title",
    keys: ["subjects"],
    stages: [
      { config: TODAY, hass: () => makeHass(), check: (root) => expect(texts(root, ".row .row-title")).toContain("Maths") },
      {
        config: TODAY,
        hass: withLessons(MATHS_UID, { subject: "Applied Mathematics" }),
        check: (root) => {
          expect(texts(root, ".row .row-title")).toContain("Applied Mathematics");
          expect(texts(root, ".row .row-title")).not.toContain("Maths");
        },
      },
    ],
  },
  {
    name: "subject_name",
    surface: "week cell label",
    keys: ["subjects"],
    stages: [
      { config: WEEK, hass: () => makeHass(), check: (root) => expect(cellOf(root, SPORT_UID).querySelector(".sub").textContent).toBe("Sport") },
      {
        config: WEEK,
        hass: withLessons(SPORT_UID, { subject: "Physical Education" }),
        check: (root) => expect(cellOf(root, SPORT_UID).querySelector(".sub").textContent).toBe("Physical Education"),
      },
    ],
  },
  {
    name: "subject_code",
    surface: "week cell",
    keys: ["subjects"],
    stages: [
      { config: WEEK, hass: () => makeHass(), check: (root) => expect(cellOf(root, MATHS_UID).querySelector(".sub").textContent).toBe("MA") },
      {
        config: WEEK,
        hass: withLessons(MATHS_UID, { subject_code: "MATH" }),
        check: (root) => expect(cellOf(root, MATHS_UID).querySelector(".sub").textContent).toBe("MATH"),
      },
    ],
  },
  {
    name: "subject_colour",
    surface: "today row-dot",
    keys: ["subjects"],
    stages: [
      {
        config: TODAY,
        hass: () => makeHass(),
        check: (root) => expect(rowOf(root, MATHS_UID).querySelector(".row-dot i").style.background).toBe("rgb(51, 102, 204)"),
      },
      {
        config: TODAY,
        hass: withLessons(MATHS_UID, { color: "#ff0000" }),
        check: (root) => expect(rowOf(root, MATHS_UID).querySelector(".row-dot i").style.background).toBe("rgb(255, 0, 0)"),
      },
    ],
  },
  {
    name: "subject_colour",
    surface: "week cell colour",
    keys: ["subjects"],
    stages: [
      {
        config: WEEK,
        hass: () => makeHass(),
        check: (root) => {
          const baseCell = cellOf(root, MATHS_UID);
          expect(baseCell.style.getPropertyValue("--subject-cell-fill")).toBe("#3366cc");
          expect(baseCell.style.getPropertyValue("--subject-bar")).toBe("#a3bae8");
        },
      },
      {
        config: WEEK,
        hass: withLessons(MATHS_UID, { color: "#ff0000" }),
        check: (root) => {
          const changedCell = cellOf(root, MATHS_UID);
          expect(changedCell.style.getPropertyValue("--subject-cell-fill")).toBe("#ff0000");
          expect(changedCell.style.getPropertyValue("--subject-cell-ink")).toBe("#000000");
          expect(changedCell.style.getPropertyValue("--subject-bar")).toBe("#730000");
        },
      },
    ],
  },
  {
    name: "teacher_name",
    surface: "today row-sub",
    keys: ["teachers"],
    stages: [
      { config: TODAY, hass: () => makeHass(), check: (root) => expect(texts(root, ".row .row-sub")).toContain("Mrs Example, R101") },
      {
        config: TODAY,
        hass: withLessons(MATHS_UID, { description: "Mrs New Teacher, R101" }),
        check: (root) => {
          expect(texts(root, ".row .row-sub")).toContain("Mrs New Teacher, R101");
          expect(texts(root, ".row .row-sub")).not.toContain("Mrs Example, R101");
        },
      },
    ],
  },
  {
    name: "holiday_region",
    surface: "week holiday field",
    keys: ["holiday_region"],
    stages: [
      { config: WEEK, hass: () => makeHass(), check: (root) => expect(root.querySelector(".tt-hol")).toBeNull() },
      {
        config: WEEK,
        hass: () => makeHass({ events: { [HOLIDAYS_SCHOOL]: [allDay("holiday-region-test@sample", "Whitsun holidays", "2026-09-03", "2026-09-05")] } }),
        check: (root) => {
          const field = root.querySelector(".tt-hol");
          expect(field).not.toBeNull();
          expect(field.querySelector(".name").textContent).toBe("Whitsun holidays");
        },
      },
    ],
  },
  {
    name: "holiday_region",
    surface: "family holiday text",
    keys: ["holiday_region"],
    stages: [
      {
        config: FAMILY,
        hass: () => makeHass(),
        check: (root) => expect(root.querySelector("ha-card > .tt-hol.full").querySelector(".name").textContent).toBe("Autumn holidays"),
      },
      {
        config: FAMILY,
        hass: () => makeHass({
          states: { [HOLIDAY_STATE]: { state: "Whitsun holidays", attributes: { start: "2027-05-17", end: "2027-05-21" } } },
        }),
        check: (root) => {
          const changedHoliday = root.querySelector("ha-card > .tt-hol.full");
          expect(changedHoliday.querySelector(".name").textContent).toBe("Whitsun holidays");
          expect(changedHoliday.querySelector(".meta").textContent).toContain("17.05.");
        },
      },
    ],
  },
  {
    name: "language",
    surface: "card texts",
    keys: [],
    stages: [
      { config: TODAY, hass: () => makeHass({ language: "de" }), check: (root) => expect(texts(root, ".tag")).toContain("Vertretung") },
      {
        config: TODAY,
        hass: () => makeHass({ language: "en" }),
        check: (root) => {
          expect(texts(root, ".tag")).toContain("Substitute");
          expect(texts(root, ".tag")).not.toContain("Vertretung");
        },
      },
    ],
  },
  {
    name: "school_name",
    surface: "section labels with two schools",
    keys: ["label"],
    stages: [
      { config: TODAY, hass: () => makeHass(), check: (root) => expect(root.querySelector(".panel-head .section-label").textContent).toBe("Alex") },
      {
        config: TODAY,
        hass: () => makeHass({ twoSchools: true }),
        check: (root) => expect(root.querySelector(".panel-head .section-label").textContent).toBe("Alex (Sample School)"),
      },
    ],
  },
  {
    name: "exam_mark",
    surface: "today marker",
    keys: [],
    stages: [
      { config: TODAY, hass: () => makeHass(), check: (root) => expect(rowOf(root, MATHS_UID).classList.contains("marked")).toBe(false) },
      {
        config: TODAY,
        hass: () => makeHass({ events: { [EXAMS_ALEX]: mathsExam() } }),
        check: (root) => {
          const markedRow = rowOf(root, MATHS_UID);
          expect(markedRow.classList.contains("marked")).toBe(true);
          expect(markedRow.querySelector(".tag.exam")).not.toBeNull();
        },
      },
      {
        config: TODAY,
        hass: () => makeHass({ events: { [EXAMS_ALEX]: [] } }),
        check: (root) => {
          const removedRow = rowOf(root, MATHS_UID);
          expect(removedRow.classList.contains("marked")).toBe(false);
          expect(removedRow.querySelector(".tag.exam")).toBeNull();
        },
      },
    ],
  },
  {
    name: "exam_mark",
    surface: "week cell",
    keys: [],
    stages: [
      {
        config: WEEK,
        hass: () => makeHass({ events: { [EXAMS_ALEX]: mathsExam() } }),
        check: (root) => {
          const markedCell = cellOf(root, MATHS_UID);
          expect(markedCell.classList.contains("marked")).toBe(true);
          expect(markedCell.querySelector(".exam-flag")).not.toBeNull();
        },
      },
      {
        config: WEEK,
        hass: () => makeHass({ events: { [EXAMS_ALEX]: [] } }),
        check: (root) => {
          const removedCell = cellOf(root, MATHS_UID);
          expect(removedCell.classList.contains("marked")).toBe(false);
          expect(removedCell.querySelector(".exam-flag")).toBeNull();
        },
      },
    ],
  },
  {
    name: "lesson_cancelled",
    surface: "today tag and strike",
    keys: [],
    stages: [
      {
        config: TODAY,
        hass: () => makeHass(),
        check: (root) => {
          const baseRow = rowOf(root, MATHS_UID);
          expect(baseRow.querySelector(".tag.no")).toBeNull();
          expect(baseRow.querySelector(".row-title").style.textDecoration).toBe("");
        },
      },
      {
        config: TODAY,
        hass: mathsCancelled,
        check: (root) => {
          const cancelledRow = rowOf(root, MATHS_UID);
          expect(cancelledRow.querySelector(".tag.no")).not.toBeNull();
          expect(cancelledRow.querySelector(".row-title").style.textDecoration).toBe("line-through");
        },
      },
      {
        config: TODAY,
        hass: noChanges,
        check: (root) => {
          const undoneRow = rowOf(root, MATHS_UID);
          expect(undoneRow.querySelector(".tag.no")).toBeNull();
          expect(undoneRow.querySelector(".row-title").style.textDecoration).toBe("");
        },
      },
    ],
  },
  {
    name: "lesson_cancelled",
    surface: "week cell class",
    keys: [],
    stages: [
      { config: WEEK, hass: mathsCancelled, check: (root) => expect(cellOf(root, MATHS_UID).classList.contains("out")).toBe(true) },
      { config: WEEK, hass: noChanges, check: (root) => expect(cellOf(root, MATHS_UID).classList.contains("out")).toBe(false) },
    ],
  },
  {
    name: "letter_archived",
    surface: "family counts badge",
    keys: [],
    stages: [
      { config: FAMILY, hass: () => makeHass(), check: (root) => expect(lettersCount(root).querySelector(".badge").textContent).toBe("2") },
      {
        config: FAMILY,
        hass: () => makeHass({ states: { [LETTERS_STATE]: { state: "0", attributes: { letters: [] } } } }),
        check: (root) => expect(lettersCount(root).querySelector(".badge")).toBeNull(),
      },
    ],
  },
  {
    name: "overview_blocks",
    surface: "card blocks render in the configured order",
    keys: [],
    stages: [
      {
        config: { blocks: [{ key: "letters", size: "normal" }, { key: "today", size: "normal" }], children: ["alex"] },
        hass: () => makeHass(),
        check: (root) => expect(blockKeys(root)).toEqual(["letters", "today"]),
      },
      { config: TWO_BLOCKS, hass: () => makeHass(), check: (root) => expect(blockKeys(root)).toEqual(["today", "letters"]) },
    ],
  },
  {
    name: "modules_disabled",
    surface: "card offers no block of the disabled module",
    keys: ["modules_disabled"],
    stages: [
      { config: TWO_BLOCKS, hass: () => makeHass(), check: (root) => expect(blockKeys(root)).toEqual(["today", "letters"]) },
      {
        config: TWO_BLOCKS,
        hass: () => makeHass({
          states: {
            "sensor.ranzenpost_school_connection": {
              state: "ok",
              attributes: {
                modules: { timetable: false, letters: true, pinboard: true, absences: true, conferences: true, messenger: true },
                modules_disabled: ["timetable"],
                ingress_path: INGRESS_PATH,
              },
            },
          },
        }),
        check: (root) => expect(blockKeys(root)).toEqual(["letters"]),
      },
    ],
  },
  {
    name: "child_switch",
    surface: "today label and rows",
    keys: [],
    stages: [
      {
        config: TODAY,
        hass: () => makeHass(),
        check: (root) => {
          expect(root.querySelector(".panel-head .section-label").textContent).toBe("Alex");
          expect(texts(root, ".row-title")).toEqual(["Maths", "English", "Art"]);
        },
      },
      {
        config: { view: "today", child: "kim" },
        hass: () => makeHass(),
        check: (root) => {
          expect(root.querySelector(".panel-head .section-label").textContent).toBe("Kim");
          expect(texts(root, ".row-title")).toEqual([]);
        },
      },
    ],
  },
];

const ROWS = [
  "period_time",
  "subject_name",
  "subject_code",
  "subject_colour",
  "teacher_name",
  "holiday_region",
  "language",
  "school_name",
  "exam_mark",
  "lesson_cancelled",
  "absence_report",
  "letter_archived",
  "notification_targets",
  "calendar_subscription",
  "passphrase",
  "theme",
  "child_switch",
  "school_filter_chips",
  "overview_blocks",
  "modules_disabled",
  "navigation",
  "school_phone_numbers",
  "own_entries_ha",
];

const EXEMPT = {
  absence_report:
    "the card never requests the absences calendar and never reads open_absences; _plan only pushes requests for the lessons and exams calendars and the own entries",
  notification_targets: "notification targets/events are HA automation config, never read by the card",
  calendar_subscription: "ICS subscription rotate/delete/components are add-on setup pages, not rendered by the card",
  passphrase: "the encryption passphrase stays in the backend store and never reaches the card",
  theme: "the card only reads hass.themes.darkMode; the app's own data-theme setting never reaches hass",
  school_filter_chips: "school filter chips are a settings-page concept; the card has no filter UI",
  navigation: "bottom bar/rail order is an app-only setting; the card has its own fixed blocks list, not a navigation bar",
  school_phone_numbers: "phone numbers are shown on the app's contact page, never passed to card entities",
};

const EXEMPT_KEYS = {
  period_grid: "lesson durations reach the card through the lesson times the backend computes (backend matrix row period_duration)",
  language: "the card follows hass.locale/hass.language; the app's language setting never reaches Home Assistant (HA matrix exemption language)",
  notify_services: "notification targets route the add-on's push, the integration never exposes them to the card",
  notify_events: "notification events route the add-on's push, the integration never exposes them to the card",
  phones: "phone numbers are shown in the app's absence view, never passed to card entities",
  short_name: "the short name labels the app's chips; the integration names schools after the label, so the card never sees it",
  overview_blocks: "the app's overview layout never reaches Home Assistant; the card orders its own card-config blocks (row overview_blocks)",
  navigation: "bottom bar/rail order is an app-only setting; the card has no navigation bar",
  reported_modules: "bookkeeping of the app's unknown-module card, never passed to Home Assistant",
  modules_card_hidden: "bookkeeping of the app's unknown-module card, never passed to Home Assistant",
  course_filters: "applied in the backend before the lessons calendar is built (backend matrix row course_filter); the card renders that calendar as the subject rows show",
};

describe("settings and actions propagation matrix", () => {
  for (const row of MATRIX) {
    it(`${row.name} -> ${row.surface}`, async () => {
      for (const [index, stage] of row.stages.entries()) {
        if (index) CardClass.resetCaches();
        const card = await mountCard(stage.config, stage.hass());
        stage.check(card.shadowRoot);
      }
    });
  }

  it("covers or exempts every row of the settings matrix", () => {
    for (const row of ROWS) {
      const covered = MATRIX.some((entry) => entry.name === row);
      const exempt = Object.prototype.hasOwnProperty.call(EXEMPT, row);
      expect(covered || exempt, row).toBe(true);
    }
    for (const row of Object.keys(EXEMPT)) {
      expect(ROWS, row).toContain(row);
    }
  });

  it("gives every config key of the schema a card row or a reason", () => {
    const covered = new Set(MATRIX.flatMap((row) => row.keys));
    const exempt = { ...SCHEMA.internal, ...EXEMPT_KEYS };
    expect(SCHEMA.keys.filter((key) => !covered.has(key) && !(key in exempt))).toEqual([]);
    expect(Object.keys(exempt).filter((key) => !SCHEMA.keys.includes(key))).toEqual([]);
    expect([...covered].filter((key) => key in exempt)).toEqual([]);
    expect(Object.values(exempt).filter((reason) => !reason.trim())).toEqual([]);
  });

  it("names every row after a matrix row and gives it at least two stages", () => {
    for (const row of MATRIX) {
      expect(ROWS, row.name).toContain(row.name);
      expect(row.stages.length, `${row.name} -> ${row.surface}`).toBeGreaterThan(1);
    }
    const titles = MATRIX.map((row) => `${row.name} -> ${row.surface}`);
    expect(new Set(titles).size).toBe(titles.length);
  });
});
