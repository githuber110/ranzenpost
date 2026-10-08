import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function pad(value) {
  return String(value).padStart(2, "0");
}

function dayOffset(offset) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function stamp(offset, hour, minute = 0) {
  return `${dayOffset(offset)}T${pad(hour)}:${pad(minute)}:00`;
}

function event(uid, title, start, end, extra = {}) {
  return { uid, title, start, end, all_day: false, location: "", calendar: "School", category: "", description: "", connection_id: "a1b2c3d4", school: "Riverside Primary", ...extra };
}

const TIMED = event("t1", "Parents evening", stamp(2, 19), stamp(2, 21), { location: "Hall A" });
const ALL_DAY = event("d1", "Class trip", dayOffset(4), dayOffset(7), { all_day: true, location: "Forest camp", calendar: "Grade 4" });
const LONG = event("l1", "Information event about the planned reorganisation of the afternoon supervision and the lunch break for all grades", stamp(6, 8, 30), stamp(6, 10));

function seed(window, extra = "") {
  evalWith(window, `
    state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
    state.childId = "c1";
    state.childrenRead = true;
    state.me = { forename: "Alice" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.modules = applyModules({ modules: { calendar: true } });
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.messengerRooms = { rooms: [], can_write_to_teacher: true };
    ${extra}
  `);
}

function setEvents(window, events, extra = {}) {
  evalWith(window, "state.schoolEvents = Object.assign({ events: testArgs[0], unavailable: [] }, testArgs[1]);", events, extra);
}

function viewOf(window) {
  return window.eval("schoolEventsView()");
}

describe("the calendar module is confirmed only", () => {
  test("it is off by default and without a registry entry", () => {
    const { window } = loadApp();
    expect(window.eval("defaultModules().available.calendar")).toBe(false);
    expect(window.eval("applyModules(undefined).available.calendar")).toBe(false);
    expect(window.eval("applyModules({ modules: { letters: true } }).available.calendar")).toBe(false);
    expect(window.eval("applyModules({ modules: { calendar: true } }).available.calendar")).toBe(true);
    expect(window.eval("applyModules({ modules: { calendar: false } }).available.calendar")).toBe(false);
  });

  test("with the module off the area, the view and the chapter are gone", () => {
    const { window } = loadApp();
    seed(window, "state.modules = applyModules({ modules: {} });");
    setEvents(window, [TIMED]);
    expect(window.eval("moduleOn('calendar')")).toBe(false);
    expect(window.eval("viewAvailable('calendar')")).toBe(false);
    expect(window.eval("visibleViews().map((item) => item.key)")).not.toContain("calendar");
    expect(window.eval("schoolEventsChapter('normal')")).toBeNull();
  });

  test("with the module on the area joins the navigation", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("viewAvailable('calendar')")).toBe(true);
    expect(window.eval("visibleViews().map((item) => item.key)")).toContain("calendar");
  });

  test("a calendar-only account still gets a bar entry for it", () => {
    const { window } = loadApp();
    seed(window, "state.modules = applyModules({ modules: { timetable: false, letters: false, pinboard: false, absences: false, conferences: false, messenger: false, calendar: true } });");
    expect(window.eval("visibleViews().map((item) => item.key)")).toEqual(["overview", "calendar"]);
  });

  test("an account without a linked profile gets the block by default, the standard overview does not", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("enabledOverviewBlocks().map((entry) => entry.key)")).not.toContain("school_events");
    window.eval("state.children = []; state.childId = null;");
    expect(window.eval("enabledOverviewBlocks().map((entry) => entry.key)")).toEqual(["letters", "noticeboard", "conferences", "holidays", "chat", "school_events"]);
    expect(window.eval("visibleViews().map((item) => item.key)")).toContain("calendar");
  });
});

describe("the school events view", () => {
  test("empty list shows a neutral empty state", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, []);
    const view = viewOf(window);
    expect(view.querySelector(".empty b").textContent).toBe(evalWith(window, "t('schoolEvents.empty.title')"));
    expect(view.querySelectorAll(".event-row").length).toBe(0);
  });

  test("an error shows the error block with a retry button", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.schoolEvents = { error: 'network' };");
    const view = viewOf(window);
    expect(view.querySelector(".empty b").textContent).toBe(evalWith(window, "t('schoolEvents.error.title')"));
    expect(view.querySelector("button")).not.toBeNull();
  });

  test("before the first answer a loading block is shown", () => {
    const { window } = loadApp();
    seed(window);
    expect(viewOf(window).querySelector(".loading")).not.toBeNull();
  });

  test("events are grouped by day in date order with time, place and calendar", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [LONG, ALL_DAY, TIMED]);
    const view = viewOf(window);
    const days = [...view.querySelectorAll(".event-day")];
    expect(days.length).toBe(3);
    const titles = [...view.querySelectorAll(".event-row .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Parents evening", "Class trip", LONG.title]);
    const first = days[0].querySelectorAll(".row-sub");
    expect(first[0].textContent).toContain("19:00");
    expect(first[0].textContent).toContain("21:00");
    expect(first[1].textContent).toBe("Hall A · School");
  });

  test("an all-day event with an exclusive end shows the last day it covers", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [ALL_DAY]);
    const sub = viewOf(window).querySelector(".event-time").textContent;
    expect(sub).toBe(evalWith(window, "t('schoolEvents.allDay.until', { date: dateLabel(testArgs[0]) })", dayOffset(6)));
    setEvents(window, [event("d2", "Holiday", dayOffset(3), dayOffset(4), { all_day: true })]);
    expect(viewOf(window).querySelector(".event-time").textContent).toBe(evalWith(window, "t('schoolEvents.allDay')"));
  });

  test("an event without a place has no second line, a long title stays whole and is bidi-safe", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [LONG, event("n1", "No place", stamp(1, 9), stamp(1, 10), { calendar: "" })]);
    const rows = [...viewOf(window).querySelectorAll(".event-row")];
    expect(rows.find((row) => row.textContent.includes("No place")).querySelectorAll(".row-sub").length).toBe(1);
    const title = rows.find((row) => row.textContent.includes("Information event")).querySelector(".row-title");
    expect(title.textContent).toBe(LONG.title);
    expect(title.getAttribute("dir")).toBe("auto");
  });

  test("the school tag appears only with several schools", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [TIMED]);
    expect(viewOf(window).querySelector(".tag.school")).toBeNull();
    seed(window, "state.config.connections = [{ id: 'a1b2c3d4', setup_complete: true, short_name: 'Riverside' }, { id: 'b2c3d4e5', setup_complete: true, short_name: 'Hill' }];");
    setEvents(window, [TIMED]);
    expect(viewOf(window).querySelector(".tag.school")).not.toBeNull();
  });

  test("past events are dropped", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [event("p1", "Old", stamp(-3, 9), stamp(-3, 10)), event("p2", "Old trip", dayOffset(-5), dayOffset(-3), { all_day: true }), TIMED]);
    const titles = [...viewOf(window).querySelectorAll(".event-row .row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Parents evening"]);
  });
});

describe("the school events chapter", () => {
  test("it lists the next events and links to the view", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [TIMED, ALL_DAY, LONG]);
    const chapter = window.eval("schoolEventsChapter('normal')");
    expect(chapter.area).toBe("school_events");
    expect(chapter.count).toBe(3);
    expect(chapter.blocks.length).toBe(4);
  });

  test("the size limits the rows", () => {
    const { window } = loadApp();
    seed(window);
    setEvents(window, [TIMED, ALL_DAY, LONG]);
    expect(window.eval("schoolEventsChapter('compact')").blocks.length).toBe(3);
    setEvents(window, [TIMED, ALL_DAY, LONG, event("x", "Fourth", stamp(8, 9), stamp(8, 10))]);
    expect(window.eval("schoolEventsChapter('compact')").blocks.length).toBe(3);
  });

  test("no events and no answer yet show no chapter, an error shows the retry block", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("schoolEventsChapter('normal')")).toBeNull();
    setEvents(window, []);
    expect(window.eval("schoolEventsChapter('normal')")).toBeNull();
    evalWith(window, "state.schoolEvents = { error: 'network' };");
    expect(window.eval("schoolEventsChapter('normal')").blocks.length).toBe(1);
  });

  test("the overview renders it when the block is switched on", () => {
    const { window } = loadApp();
    seed(window, "state.config.overview_blocks = [{ key: 'school_events', size: 'normal' }];");
    setEvents(window, [TIMED]);
    const panels = [...window.eval("overviewView()").querySelectorAll(".panel")].map((panel) => panel.dataset.area);
    expect(panels).toEqual(["school_events"]);
  });
});

describe("the school events loader", () => {
  test("it asks the route and keeps the answer", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    window.fetch = (input) => {
      calls.push(String(input));
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve({ events: [TIMED], unavailable: [] }) });
    };
    await window.eval("loadSchoolEvents()");
    await settle();
    expect(calls.some((url) => url.includes("api/school-events"))).toBe(true);
    expect(window.eval("state.schoolEvents.events.length")).toBe(1);
  });

  test("a failing route stores the error object the view shows", async () => {
    const { window } = loadApp();
    seed(window);
    window.fetch = () => Promise.resolve({ ok: false, status: 502, headers: { get: () => "application/json" }, json: () => Promise.resolve({ ok: false, message_key: "api.error" }) });
    await window.eval("loadSchoolEvents()");
    await settle();
    expect(window.eval("!!state.schoolEvents.error")).toBe(true);
  });
});

describe("the time range of a school event", () => {
  test("uses the locale's own range format on one day and across days", async () => {
    const { loadApp } = await import("./loadApp.js");
    const { window } = loadApp();
    const sameDay = window.eval(`schoolEventTimeText({ start: "2026-10-12T18:00:00+02:00", end: "2026-10-12T19:30:00+02:00", all_day: false })`);
    const expectedSameDay = window.eval(`dateFormatter({ hour: "2-digit", minute: "2-digit" }).formatRange(new Date("2026-10-12T18:00:00+02:00"), new Date("2026-10-12T19:30:00+02:00"))`);
    expect(sameDay).toBe(expectedSameDay);
    expect(sameDay).toContain(window.eval(`formatTime(new Date("2026-10-12T19:30:00+02:00"))`));
    const twoDays = window.eval(`schoolEventTimeText({ start: "2026-10-12T18:00:00+02:00", end: "2026-10-13T10:00:00+02:00", all_day: false })`);
    const dayOf = (iso) => window.eval(`dateFormatter({ day: "2-digit", month: "2-digit" }).format(new Date("${iso}"))`);
    expect(twoDays).toContain(dayOf("2026-10-12T18:00:00+02:00"));
    expect(twoDays).toContain(dayOf("2026-10-13T10:00:00+02:00"));
  });
});
