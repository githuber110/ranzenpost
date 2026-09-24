import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

const FRONTEND = path.resolve(__dirname, "..");
const styles = fs.readFileSync(path.join(FRONTEND, "styles.css"), "utf8");
const wizardCss = fs.readFileSync(path.join(FRONTEND, "wizard.css"), "utf8");

const LETTERS = {
  tab: "current",
  letters: [
    { letter_id: "1", recipient_id: "2", title: "Sports day", unread: true },
    { letter_id: "3", recipient_id: "4", title: "Field trip", unread: false },
  ],
};

const PINBOARD = {
  folders: [],
  feed: [
    { id: 1, title: "Summer fair", text: "Text", unread: true },
    { id: 2, title: "Cake sale", text: "Text", unread: false },
  ],
};

const ROOMS = {
  self_user_id: "@me:example.test",
  can_write_to_teacher: true,
  rooms: [
    {
      room_id: "!a:example.test",
      name: "Class 3b",
      members: ["Ms. Behrend"],
      member_names: {},
      last_message: "See you tomorrow.",
      last_message_at: 1788336000000,
      unread_count: 2,
    },
  ],
};

const ABSENCE = {
  data: {
    children: [{ id: "c1", name: "Mia" }],
    rules: {},
    phones: [],
    entries: [
      { id: "a1", kind: "sick", from_date: "2099-01-10", till_date: "2099-01-11", deletable: true, student_id: "c1" },
    ],
  },
};

function useWidth(window, width) {
  const listeners = [];
  window.innerWidth = width;
  window.matchMedia = (query) => {
    const min = /\(min-width:\s*(\d+)px\)/.exec(query);
    const matches = min ? width >= Number(min[1]) : /orientation: portrait/.test(query);
    return {
      matches,
      media: query,
      addListener() {},
      removeListener() {},
      addEventListener(name, fn) { listeners.push(fn); },
      removeEventListener() {},
    };
  };
  return listeners;
}

function seed(window, extra) {
  window.eval(`
    state.config = {};
    state.children = [{ key: "c1", name: "Mia", class_name: "3b" }];
    state.childId = "c1";
    state.absence = ${JSON.stringify(ABSENCE)};
    state.letters = ${JSON.stringify(LETTERS)};
    state.pinboard = ${JSON.stringify(PINBOARD)};
    state.messengerRooms = ${JSON.stringify(ROOMS)};
    state.loadedAt = {};
    ${extra || ""}
  `);
}

function app(window) {
  return window.document.getElementById("app");
}

function boot(width, view, extra) {
  const { window } = loadApp();
  useWidth(window, width);
  seed(window, `state.view = ${JSON.stringify(view)}; ${extra || ""}`);
  window.eval("render()");
  return window;
}

describe("layout: width classification", () => {
  test("899 is a phone, 900 is wide, 1279 is wide, 1280 is a desk", () => {
    const { window } = loadApp();
    expect(window.eval("layoutModeFor(899)")).toBe("phone");
    expect(window.eval("layoutModeFor(900)")).toBe("wide");
    expect(window.eval("layoutModeFor(1279)")).toBe("wide");
    expect(window.eval("layoutModeFor(1280)")).toBe("desk");
  });

  test("layoutMode reads the two media queries", () => {
    const { window } = loadApp();
    useWidth(window, 390);
    expect(window.eval("layoutMode()")).toBe("phone");
    useWidth(window, 1024);
    expect(window.eval("layoutMode()")).toBe("wide");
    useWidth(window, 1440);
    expect(window.eval("layoutMode()")).toBe("desk");
  });
});

describe("layout: where a selection is shown", () => {
  test("a letter or a chat room is a page below the desk width and a pane on a desk", () => {
    const { window } = loadApp();
    const place = (kind, layout, view) => window.eval(`detailPlacement(${JSON.stringify(kind)}, ${JSON.stringify(layout)}, ${JSON.stringify(view)})`);
    expect(place("letter", "phone", "post")).toBe("page");
    expect(place("letter", "wide", "post")).toBe("page");
    expect(place("letter", "desk", "post")).toBe("pane");
    expect(place("room", "wide", "messenger")).toBe("page");
    expect(place("room", "desk", "messenger")).toBe("pane");
  });

  test("a pinboard post or an absence is a sheet below the desk width and a pane on a desk list view", () => {
    const { window } = loadApp();
    const place = (kind, layout, view) => window.eval(`detailPlacement(${JSON.stringify(kind)}, ${JSON.stringify(layout)}, ${JSON.stringify(view)})`);
    expect(place("post", "phone", "post")).toBe("sheet");
    expect(place("post", "wide", "post")).toBe("sheet");
    expect(place("post", "desk", "post")).toBe("pane");
    expect(place("post", "desk", "overview")).toBe("sheet");
    expect(place("absence", "desk", "absence")).toBe("pane");
    expect(place("absence", "desk", "overview")).toBe("sheet");
  });
});

describe("layout: the shell at each width", () => {
  test("a phone keeps the tab bar and gets neither a rail nor a pane", () => {
    const window = boot(390, "post");
    const root = app(window);
    expect(root.querySelector(".tabbar")).not.toBeNull();
    expect(root.querySelectorAll(".tabbar .tab")).toHaveLength(5);
    expect(root.querySelector(".rail")).toBeNull();
    expect(root.querySelector(".pane-detail")).toBeNull();
    expect(root.getAttribute("data-shell")).toBe("tabs");
    expect(Array.from(root.children).map((node) => node.className)).toEqual(["screen", "tabbar"]);
  });

  test("a wide screen swaps the tab bar for a rail with icons and labels and has no pane", () => {
    const window = boot(1024, "post");
    const root = app(window);
    expect(root.querySelector(".tabbar")).toBeNull();
    const rail = root.querySelector("nav.rail");
    expect(rail).not.toBeNull();
    const items = Array.from(rail.querySelectorAll(".rail-item"));
    expect(items).toHaveLength(6);
    expect(items.every((item) => item.querySelector(".ico-slot") && item.querySelector(".rail-label").textContent.trim())).toBe(true);
    expect(items[3].getAttribute("aria-current")).toBe("page");
    expect(root.querySelector(".pane-detail")).toBeNull();
    expect(root.getAttribute("data-shell")).toBe("rail");
    expect(root.getAttribute("data-view")).toBe("post");
  });

  test("a desk list view adds the detail pane with an empty hint", () => {
    const window = boot(1440, "post");
    const root = app(window);
    expect(root.querySelector("nav.rail")).not.toBeNull();
    const pane = root.querySelector(".pane-detail");
    expect(pane).not.toBeNull();
    expect(pane.querySelector(".pane-empty").textContent).toContain(window.eval("t('layout.detail.empty')"));
    expect(root.getAttribute("data-shell")).toBe("rail-pane");
  });

  test("a desk overview or timetable has no pane", () => {
    expect(app(boot(1440, "overview")).querySelector(".pane-detail")).toBeNull();
    expect(app(boot(1440, "timetable")).querySelector(".pane-detail")).toBeNull();
  });

  test("the rail carries the unread badge and the rail item switches the view through setView", () => {
    const window = boot(1024, "overview");
    const root = app(window);
    const items = Array.from(root.querySelectorAll(".rail-item"));
    expect(items[3].querySelector(".badge").textContent).toBe("2");
    items[3].click();
    expect(window.eval("state.view")).toBe("post");
    expect(app(window).querySelector('.rail-item[aria-current="page"] .rail-label').textContent).toBe(window.eval("t('nav.post')"));
  });

  test("a breakpoint change re-renders the shell", () => {
    const { window } = loadApp();
    const listeners = useWidth(window, 1024);
    seed(window, 'state.view = "post";');
    window.eval("render()");
    expect(app(window).querySelector(".rail")).not.toBeNull();
    useWidth(window, 390);
    for (const listener of listeners) listener({ matches: false });
    expect(app(window).querySelector(".rail")).toBeNull();
    expect(app(window).querySelector(".tabbar")).not.toBeNull();
  });
});

describe("layout: letters", () => {
  test("on a desk a letter opens in the pane while the list stays, and the pane close button leaves the letter", () => {
    const window = boot(1440, "post", 'state.letterDetail = { letter: state.letters.letters[0], detail: { body_html: "<p>Hello</p>" }, origin: null };');
    const root = app(window);
    expect(root.querySelector(".screen .rows .row")).not.toBeNull();
    expect(root.querySelector(".screen .rows .row.open .row-title").textContent).toBe("Sports day");
    expect(root.querySelectorAll(".screen .rows .row.open")).toHaveLength(1);
    expect(root.querySelector(".screen .header-back")).toBeNull();
    expect(root.querySelector(".screen .header-title").textContent).toBe(window.eval("t('post.title')"));
    const pane = root.querySelector(".pane-detail");
    expect(pane.querySelector(".pane-title").textContent).toBe("Sports day");
    expect(pane.querySelector(".pane-body .body-html").textContent).toBe("Hello");
    expect(pane.querySelector(".pane-head .tech-btn")).not.toBeNull();
    pane.querySelector(".pane-close").click();
    expect(window.eval("state.letterDetail")).toBeNull();
    expect(app(window).querySelector(".pane-detail .pane-empty")).not.toBeNull();
  });

  test("on a wide screen a letter is still a full page with the back button", () => {
    const window = boot(1024, "post", 'state.letterDetail = { letter: state.letters.letters[0], detail: { body_html: "<p>Hello</p>" }, origin: null };');
    const root = app(window);
    expect(root.querySelector(".pane-detail")).toBeNull();
    expect(root.querySelector(".row.open")).toBeNull();
    expect(root.querySelector(".screen .header-back")).not.toBeNull();
    expect(root.querySelector(".screen .body-html").textContent).toBe("Hello");
    root.querySelector(".screen .header-back").click();
    expect(window.eval("state.letterDetail")).toBeNull();
  });
});

describe("layout: pinboard posts and absences", () => {
  test("on a desk a post lands in the pane, on a wide screen it is a dialog sheet", () => {
    const desk = boot(1440, "post", 'state.postTab = "pinboard";');
    desk.eval("openPost(state.pinboard.feed[0])");
    expect(desk.eval("state.detail && state.detail.kind")).toBe("post");
    expect(desk.eval("state.sheet")).toBeNull();
    const pane = app(desk).querySelector(".pane-detail");
    expect(pane.querySelector(".pane-title").textContent).toBe("Summer fair");
    expect(pane.querySelector(".pane-foot button")).not.toBeNull();
    pane.querySelector(".pane-close").click();
    expect(desk.eval("state.detail")).toBeNull();

    const wide = boot(1024, "post", 'state.postTab = "pinboard";');
    wide.eval("openPost(state.pinboard.feed[0])");
    expect(wide.eval("state.detail")).toBeNull();
    expect(wide.eval("typeof state.sheet")).toBe("function");
    const scrim = app(wide).querySelector(".scrim");
    expect(scrim.classList.contains("dialog")).toBe(true);
    expect(scrim.querySelector(".sheet .sheet-title").textContent).toBe("Summer fair");
  });

  test("a phone sheet carries no dialog modifier", () => {
    const phone = boot(390, "post", 'state.postTab = "pinboard";');
    phone.eval("openPost(state.pinboard.feed[0])");
    const scrim = app(phone).querySelector(".scrim");
    expect(scrim.className).toBe("scrim");
  });

  test("on a desk an absence lands in the pane and a view change clears it", () => {
    const desk = boot(1440, "absence");
    desk.eval("openAbsenceSheet(state.absence.data.entries[0])");
    expect(desk.eval("state.detail && state.detail.kind")).toBe("absence");
    const pane = app(desk).querySelector(".pane-detail");
    expect(pane.querySelector(".pane-body .fact-list, .pane-body .facts, .pane-body dl, .pane-body .fact")).not.toBeNull();
    desk.eval('setView("post")');
    expect(desk.eval("state.detail")).toBeNull();
  });

  test("a post opened from the overview on a desk stays a dialog sheet", () => {
    const desk = boot(1440, "overview");
    desk.eval("openPost(state.pinboard.feed[0])");
    expect(desk.eval("state.detail")).toBeNull();
    expect(app(desk).querySelector(".scrim.dialog")).not.toBeNull();
  });

  test("a pane detail that outlives the desk width falls back to a dialog sheet", () => {
    const { window } = loadApp();
    useWidth(window, 1440);
    seed(window, 'state.view = "post"; state.postTab = "pinboard";');
    window.eval("render(); openPost(state.pinboard.feed[0])");
    expect(app(window).querySelector(".pane-detail .pane-title")).not.toBeNull();
    useWidth(window, 1024);
    window.eval("render()");
    expect(app(window).querySelector(".pane-detail")).toBeNull();
    expect(app(window).querySelector(".scrim.dialog .sheet-title").textContent).toBe("Summer fair");
  });
});

describe("layout: chat rooms", () => {
  test("on a desk a room opens in the pane next to the room list", () => {
    const desk = boot(1440, "messenger");
    desk.eval("openMessengerRoom(state.messengerRooms.rooms[0])");
    const root = app(desk);
    expect(root.querySelector(".screen").classList.contains("chat")).toBe(false);
    expect(root.querySelector(".screen .rows .row")).not.toBeNull();
    expect(root.querySelector(".screen .rows .row.open")).not.toBeNull();
    const pane = root.querySelector(".pane-detail");
    expect(pane.querySelector(".pane-body .chat")).not.toBeNull();
    expect(pane.querySelector(".pane-body .composer")).not.toBeNull();
    expect(pane.querySelector(".pane-title").textContent).toBe("Class 3b");
    pane.querySelector(".pane-close").click();
    expect(desk.eval("state.messengerRoom")).toBeNull();
  });

  test("on a wide screen a room is a full chat page and keeps the rail", () => {
    const wide = boot(1024, "messenger");
    wide.eval("openMessengerRoom(state.messengerRooms.rooms[0])");
    const root = app(wide);
    expect(root.querySelector(".screen").classList.contains("chat")).toBe(true);
    expect(root.querySelector(".screen .header-back")).not.toBeNull();
    expect(root.querySelector(".rail")).not.toBeNull();
    expect(root.querySelector(".pane-detail")).toBeNull();
  });

  test("on a phone a room hides the tab bar as before", () => {
    const phone = boot(390, "messenger");
    phone.eval("openMessengerRoom(state.messengerRooms.rooms[0])");
    const root = app(phone);
    expect(root.querySelector(".tabbar")).toBeNull();
    expect(root.querySelector(".screen").classList.contains("chat")).toBe(true);
  });
});

describe("layout: timetable children side by side", () => {
  const TWO = `
    state.children = [
      { key: "c1", name: "Mia", class_name: "3b" },
      { key: "c2", name: "Tom", class_name: "1a" },
    ];
    state.timetable = { lessons: [{ day_of_week: 1, period: 1, subject_code: "DE" }], period_times: {} };
    state.overviewWeeks = { c2: { 0: { lessons: [{ day_of_week: 2, period: 1, subject_code: "MA" }] } } };
  `;

  test("a desk shows one grid per child with the child's name and no child switch", () => {
    const desk = boot(1440, "timetable", TWO);
    const root = app(desk);
    const columns = root.querySelectorAll(".tt-multi .tt-child");
    expect(columns).toHaveLength(2);
    expect(columns[0].querySelector(".tt-child-head").textContent).toContain("Mia");
    expect(columns[1].querySelector(".tt-child-head").textContent).toContain("Tom");
    expect(columns[0].querySelector(".tt .tt-cell .sub").textContent).toBe("DE");
    expect(columns[1].querySelector(".tt .tt-cell .sub").textContent).toBe("MA");
    expect(root.querySelector(".child-switch")).toBeNull();
    expect(root.querySelector(".header-title").textContent).toBe(desk.eval("t('timetable.title')"));
    expect(root.querySelector(".tt-multi").classList.contains("scrolls")).toBe(false);
  });

  test("a wide screen keeps one grid and the child switch", () => {
    const wide = boot(1024, "timetable", TWO);
    const root = app(wide);
    expect(root.querySelector(".tt-multi")).toBeNull();
    expect(root.querySelectorAll(".tt")).toHaveLength(1);
    expect(root.querySelector(".child-switch")).not.toBeNull();
  });

  test("four children share the width, from five the columns scroll sideways", () => {
    const desk = boot(1440, "timetable", `
      ${TWO}
      state.children.push({ key: "c3", name: "Ida", class_name: "2c" }, { key: "c4", name: "Ben", class_name: "4a" });
    `);
    expect(app(desk).querySelector(".tt-multi").classList.contains("scrolls")).toBe(false);
    expect(app(desk).querySelectorAll(".tt-child")).toHaveLength(4);
    desk.eval('state.children.push({ key: "c5", name: "Eva", class_name: "1b" }); render();');
    expect(app(desk).querySelector(".tt-multi").classList.contains("scrolls")).toBe(true);
    expect(app(desk).querySelectorAll(".tt-child")).toHaveLength(5);
  });

  test("a child without data shows the loading block in its column", () => {
    const desk = boot(1440, "timetable", `${TWO} state.overviewWeeks = {};`);
    const columns = app(desk).querySelectorAll(".tt-child");
    expect(columns[1].querySelector(".loading")).not.toBeNull();
  });

  test("a refresh of the desk timetable also reloads the other children's week", () => {
    const desk = boot(1440, "timetable", `${TWO} loadOverviewWeek = (childId, week) => Promise.resolve({ childId, week });`);
    desk.eval("state.weekOffset = 2;");
    expect(desk.eval("siblingWeekLoads().length")).toBe(1);
    const wide = boot(1024, "timetable", `${TWO} loadOverviewWeek = (childId, week) => Promise.resolve({ childId, week });`);
    expect(wide.eval("siblingWeekLoads().length")).toBe(0);
  });

  test("a lesson in another child's column opens the sheet for that child", () => {
    const desk = boot(1440, "timetable", TWO);
    const cell = app(desk).querySelectorAll(".tt-child")[1].querySelector(".tt-cell:not(.free)");
    cell.click();
    expect(desk.eval("typeof state.sheet")).toBe("function");
  });
});

describe("layout: overview paging stops above the phone width", () => {
  const CHAPTERS = `
    [{ area: "today", title: "Today", blocks: [{ key: "a", node: null }, { key: "b", node: null }, { key: "c", node: null }] }]
  `;
  const MEASURES = "[{ heights: [100, 100, 100], frame: 40 }]";

  test("the same measurements page on a phone and refuse to on a wide portrait tablet", () => {
    const { window } = loadApp();
    useWidth(window, 390);
    expect(window.eval(`overviewPlan(${CHAPTERS}, ${MEASURES}, 400)`)).not.toBeNull();
    useWidth(window, 1024);
    expect(window.eval(`overviewPlan(${CHAPTERS}, ${MEASURES}, 400)`)).toBeNull();
    useWidth(window, 1440);
    expect(window.eval(`overviewPlan(${CHAPTERS}, ${MEASURES}, 400)`)).toBeNull();
  });
});

describe("layout: the stylesheet carries the two breakpoints", () => {
  const wideBlock = styles.slice(styles.indexOf("@media (min-width: 900px)"));
  const deskBlock = styles.slice(styles.indexOf("@media (min-width: 1280px)"));

  test("both breakpoints exist and only the wide one lifts the shell cap", () => {
    expect(styles).toContain("@media (min-width: 900px)");
    expect(styles).toContain("@media (min-width: 1280px)");
    const before = styles.slice(0, styles.indexOf("@media (min-width: 900px)"));
    expect(before).not.toContain(".rail");
    expect(before).not.toContain(".pane-detail");
    expect(wideBlock).toMatch(/\.app\s*{[^}]*max-width:\s*none/);
  });

  test("the pane is 420px wide and the dialog sheet is capped at 560px and 88dvh", () => {
    expect(deskBlock).toMatch(/\.pane-detail\s*{[^}]*inline-size:\s*420px/);
    expect(styles).toMatch(/\.scrim\.dialog\s*>\s*\.sheet\s*{[^}]*max-width:\s*560px/);
    expect(styles).toMatch(/\.sheet\s*{[^}]*max-height:\s*88dvh/);
    expect(wizardCss).toMatch(/@media \(min-width: 900px\)[\s\S]*\.sw\s*{[^}]*max-inline-size:\s*560px/);
  });

  test("the overview is a 2x2 grid at wide and four columns at desk, the timetable columns scroll from five children", () => {
    expect(wideBlock).toMatch(/\.overview\s*{[^}]*grid-template-columns:\s*repeat\(2,/);
    expect(deskBlock).toMatch(/\.overview\s*{[^}]*grid-template-columns:\s*repeat\(4,/);
    expect(deskBlock).toMatch(/\.tt-multi\.scrolls\s*{[^}]*overflow-x:\s*auto/);
  });

  test("no physical direction sneaks into the new rules", () => {
    const fresh = styles.slice(styles.indexOf("@media (min-width: 900px)"));
    expect(fresh).not.toMatch(/(?<![\w-])(margin|padding|border)-(left|right)\s*:/);
    expect(fresh).not.toMatch(/(?<![\w-])(left|right)\s*:/);
    expect(fresh).not.toMatch(/text-align\s*:\s*(left|right)/);
  });
});
