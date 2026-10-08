import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const CHILD = { key: "c1", name: "Alice", class_name: "3b" };

function seed(window, extra = "", arg = null) {
  evalWith(window, `
    state.children = [];
    state.childId = null;
    state.childrenFailure = null;
    state.childrenRead = true;
    state.me = { forename: "Alice" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.timetable = null;
    state.overviewWeeks = {};
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.messengerRooms = { rooms: [], can_write_to_teacher: true };
    state.holidays = { "": { status: "ok", kind: "school", weeks: [], periods: [{ id: "h1", kind: "school", name: "Autumn break", start: "2099-10-01", end: "2099-10-12" }], days: {} } };
    ${extra}
  `, arg);
}

function label(window, key) {
  return evalWith(window, "t(testArgs[0])", key);
}

function areas(window) {
  return [...window.eval("overviewView()").querySelectorAll(".panel")].map((panel) => panel.dataset.area);
}

describe("an account without a linked profile", () => {
  test("the timetable and absence tabs are gone, the rest stays", () => {
    const { window } = loadApp();
    seed(window);
    const keys = window.eval("visibleViews().map((item) => item.key)");
    expect(keys).toEqual(["overview", "post", "messenger", "conferences"]);
    expect(window.eval("viewAvailable('timetable')")).toBe(false);
    expect(window.eval("viewAvailable('absence')")).toBe(false);
  });

  test("a stored timetable view falls back to the overview", () => {
    const { window } = loadApp();
    seed(window, "state.view = 'timetable';");
    window.eval("revalidateView()");
    expect(window.eval("state.view")).toBe("overview");
  });

  test("the overview has no today chapter and no no-person text, and shows the holidays by default", () => {
    const { window } = loadApp();
    seed(window);
    const shown = areas(window);
    expect(shown).not.toContain("today");
    expect(shown).toContain("holidays");
    expect(window.eval("overviewView()").textContent).not.toContain(label(window, "overview.noChild"));
  });

  test("blocks that need a profile are not offered, holidays are", () => {
    const { window } = loadApp();
    seed(window);
    const offered = window.eval("offeredBlocks().map((block) => block.key)");
    expect(offered).toContain("holidays");
    for (const key of ["today", "next_lesson", "week", "absences", "changes"]) expect(offered).not.toContain(key);
  });

  test("a saved layout without holidays is respected", () => {
    const { window } = loadApp();
    seed(window, "state.config.overview_blocks = [{ key: 'letters', size: 'normal' }];");
    expect(areas(window)).not.toContain("holidays");
  });

  test("the school settings hide period times, names, courses and the phone numbers for sick notes", () => {
    const { window } = loadApp();
    seed(window);
    const text = window.eval("schoolSettingRows('').map((row) => row.textContent).join('|')");
    expect(text).not.toContain(label(window, "settings.periods.sheet"));
    expect(text).not.toContain(label(window, "settings.names"));
    expect(text).not.toContain(label(window, "settings.phones"));
    expect(text).toContain(label(window, "holidays.settings.title"));
  });

  test("the messenger offers no new room with a teacher", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("teacherRoomEntry('btn')")).toBeNull();
  });

  test("the school list says no linked profile instead of counting zero", () => {
    const { window } = loadApp();
    seed(window, "state.schools = [{ id: 's1', children_state: 'listed' }];");
    expect(window.eval("schoolChildrenValue('s1')").textContent).toBe(label(window, "schools.children.none"));
  });

  test("the school list keeps the warning when the list could not be read", () => {
    const { window } = loadApp();
    seed(window, "state.schools = [{ id: 's1', children_state: 'unreadable' }];");
    expect(window.eval("schoolChildrenValue('s1')").textContent).toBe(label(window, "schools.children.unreadable"));
  });
});

describe("an account whose child list is unknown or failed", () => {
  test("nothing is hidden before the list was read", () => {
    const { window } = loadApp();
    seed(window, "state.childrenRead = false;");
    expect(window.eval("noChildren()")).toBe(false);
    expect(window.eval("visibleViews().map((item) => item.key)")).toContain("timetable");
    expect(window.eval("visibleViews().map((item) => item.key)")).toContain("absence");
  });

  test("a failed list keeps the tabs, the failure card and the teacher entry", () => {
    const { window } = loadApp();
    seed(window, "state.childrenFailure = { error: 'network' };");
    expect(window.eval("noChildren()")).toBe(false);
    expect(window.eval("visibleViews().map((item) => item.key)")).toContain("timetable");
    expect(window.eval("overviewView()").querySelector(".overview-failed")).not.toBeNull();
    expect(window.eval("teacherRoomEntry('btn')")).not.toBeNull();
  });
});

describe("an account with a child", () => {
  test("keeps every tab, the today chapter and the default blocks", () => {
    const { window } = loadApp();
    seed(window, "state.children = [testArgs[0]]; state.childId = 'c1'; state.timetable = { lessons: [], period_times: {} };", CHILD);
    expect(window.eval("noChildren()")).toBe(false);
    expect(window.eval("visibleViews().map((item) => item.key)")).toEqual(["overview", "timetable", "absence", "post", "messenger", "conferences"]);
    expect(window.eval("enabledOverviewBlocks().map((entry) => entry.key)")).toEqual(["today", "letters", "noticeboard", "conferences", "changes", "chat"]);
    expect(window.eval("teacherRoomEntry('btn')")).not.toBeNull();
    const text = window.eval("schoolSettingRows('').map((row) => row.textContent).join('|')");
    expect(text).toContain(label(window, "settings.names"));
  });
});
