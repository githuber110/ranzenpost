import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const MODULES = ["timetable", "letters", "pinboard", "absences", "conferences", "messenger"];
const ISSUE_URL = "https://github.com/githuber110/ranzenpost/issues/new?";
const ISSUE_BODY = "Attach the saved file ranzenpost-report.zip: drag it into this field. If you copied the report instead, paste it below.\n\n";
const ISSUE_QUESTION = "For each module in the title, one sentence: what should Ranzenpost do with it?";

function subsets() {
  const all = [];
  for (let mask = 0; mask < 1 << MODULES.length; mask += 1) {
    const chosen = {};
    MODULES.forEach((name, index) => { chosen[name] = Boolean(mask & (1 << index)); });
    all.push(chosen);
  }
  return all;
}

function expectedTabs(available) {
  const tabs = [];
  if (!MODULES.some((name) => available[name])) return tabs;
  tabs.push("overview");
  if (available.timetable) tabs.push("timetable");
  if (available.absences) tabs.push("absence");
  if (available.letters || available.pinboard) tabs.push("post");
  if (available.messenger) tabs.push("messenger");
  if (available.conferences) tabs.push("conferences");
  return tabs;
}

function expectedBar(keys) {
  if (keys.length <= 5) return keys;
  return keys.slice(0, 4).concat(["more"]);
}

function seed(window, available, extra = "") {
  window.eval(`
    state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
    state.childId = "c1";
    state.me = { forename: "Alice" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.timetable = { lessons: [], period_times: {} };
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.messengerRooms = { rooms: [] };
    state.modules = applyModules({ modules: ${JSON.stringify(available)}, unknown: [], checked_at: 10, iserv_version: "3.9" });
    ${extra}
  `);
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || null)})`);
}

function all(overrides = {}) {
  const available = {};
  for (const name of MODULES) available[name] = true;
  return { ...available, ...overrides };
}

describe("the module registry decides which views exist", () => {
  test("the tab bar and the rail show exactly the views of the available modules, for every subset", () => {
    const { window } = loadApp();
    for (const available of subsets()) {
      seed(window, available);
      const keys = window.eval("visibleViews().map((item) => item.key)");
      expect(keys, JSON.stringify(available)).toEqual(expectedTabs(available));
      const bar = window.eval("tabbar()");
      const rail = window.eval("rail()");
      if (!keys.length) {
        expect(bar).toBeNull();
        expect(rail).toBeNull();
        continue;
      }
      const entries = expectedBar(keys);
      expect(bar.querySelectorAll(".tab").length).toBe(entries.length);
      expect(bar.querySelectorAll(".tab-more").length).toBe(entries.includes("more") ? 1 : 0);
      expect(bar.style.getPropertyValue("--tabs")).toBe(String(entries.length));
      expect(rail.querySelectorAll(".rail-item").length).toBe(keys.length);
    }
  });

  test("a health payload without a registry shows every module, a partial one fills the gaps", () => {
    const { window } = loadApp();
    expect(window.eval("applyModules(undefined).available")).toEqual(all());
    expect(window.eval("applyModules({ modules: { letters: false } }).available")).toEqual(all({ letters: false }));
    const parsed = window.eval("applyModules({ modules: {}, unknown: [{ segment: 'mail', label: 'E-Mail' }, { label: 'x' }], checked_at: 7, iserv_version: '3.9.1' })");
    expect(parsed.unknown).toEqual([{ segment: "mail", label: "E-Mail" }]);
    expect(parsed.checkedAt).toBe(7);
    expect(parsed.iservVersion).toBe("3.9.1");
  });

  test("the overview drops the chapters of missing modules", () => {
    const { window } = loadApp();
    const content = `
      state.overviewWeeks = {};
      state.timetable = { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
      state.letters = { tab: "current", letters: [{ letter_id: "l1", recipient_id: "r1", title: "Brief", unread: true }] };
      state.pinboard = { folders: [], feed: [{ id: "p1", unread: true, title: "Neu" }] };
      state.messengerRooms = { rooms: [{ room_id: "!a:x", name: "R", unread_count: 4 }] };
      state.config.overview_blocks = [{ key: "today" }, { key: "letters" }, { key: "noticeboard" }, { key: "chat" }];
    `;
    const areasFor = (available) => {
      seed(window, available, content);
      return window.eval("overviewChapters().map((chapter) => chapter.area)");
    };
    expect(areasFor(all())).toEqual(["today", "letters", "noticeboard", "chat"]);
    expect(areasFor(all({ timetable: false }))).toEqual(["letters", "noticeboard", "chat"]);
    expect(areasFor(all({ letters: false }))).toEqual(["today", "noticeboard", "chat"]);
    expect(areasFor(all({ pinboard: false }))).toEqual(["today", "letters", "chat"]);
    expect(areasFor(all({ messenger: false }))).toEqual(["today", "letters", "noticeboard"]);
    seed(window, all({ conferences: false, absences: false }), "state.conferences = null; state.absence = null;");
    expect(window.eval("conferencesChapter('normal')")).toBeNull();
    expect(window.eval("absencesChapter('normal')")).toBeNull();
  });

  test("the post view shows only the segment that exists and no segment bar for a single one", () => {
    const { window } = loadApp();
    seed(window, all());
    expect(window.eval("postView()").querySelectorAll(".segment button").length).toBe(2);
    seed(window, all({ letters: false }), "state.postTab = 'letters';");
    const pinboardOnly = window.eval("postView()");
    expect(pinboardOnly.querySelector(".segment")).toBeNull();
    expect(window.eval("postSegmentIs('pinboard')")).toBe(true);
    seed(window, all({ pinboard: false }), "state.postTab = 'pinboard';");
    expect(window.eval("postView()").querySelector(".segment")).toBeNull();
    expect(window.eval("postSegmentIs('letters')")).toBe(true);
  });

  test("the timetable views, the exam marks and the calendar feed follow the timetable module", () => {
    const { window } = loadApp();
    seed(window, all({ timetable: false }));
    expect(window.eval("todayChapter()")).toBeNull();
    expect(window.eval("timetableShowsAllChildren()")).toBe(false);
    const header = window.eval("header('timetable')");
    expect(header.querySelector("[aria-label='" + label(window, "calendar.subscribe.open") + "']")).toBeNull();
  });
});

describe("the settings follow the modules", () => {
  test("names and period rows leave with the timetable, the absences calendar toggle leaves with absences", () => {
    const { window } = loadApp();
    seed(window, all());
    const rows = (view) => [...view.querySelectorAll(".setting-row .lbl")].map((node) => node.textContent);
    expect(rows(window.eval("settingsView()"))).toContain(label(window, "settings.names"));
    expect(rows(window.eval("settingsView()"))).toContain(label(window, "settings.periods.sheet"));
    seed(window, all({ timetable: false }));
    expect(rows(window.eval("settingsView()"))).not.toContain(label(window, "settings.names"));
    expect(rows(window.eval("settingsView()"))).not.toContain(label(window, "settings.periods.sheet"));
    expect(rows(window.eval("settingsView()"))).toContain(label(window, "settings.phones"));

    seed(window, all());
    expect(window.eval("calendarComponents()")).toContain("absences");
    expect(window.eval("calendarComponents()")).toContain("marks");
    seed(window, all({ absences: false }));
    expect(window.eval("calendarComponents()")).not.toContain("absences");
    expect(window.eval("calendarComponents()")).toContain("marks");
  });

  test("notification toggles exist only for available modules, outage stays regardless", () => {
    const { window } = loadApp();
    seed(window, all({ letters: false, conferences: false }));
    expect(window.eval("notifyEvents().map((entry) => entry[0])")).toEqual(["timetable", "pinboard", "outage"]);
    seed(window, all());
    expect(window.eval("notifyEvents().map((entry) => entry[0])")).toEqual([
      "timetable",
      "letters",
      "pinboard",
      "conferences",
      "outage",
    ]);
  });

  test("the IServ modules block lists available modules with a switch and no help block without unknown modules", () => {
    const { window } = loadApp();
    seed(window, all({ absences: false, messenger: false }));
    const view = window.eval("settingsView()");
    const heads = [...view.querySelectorAll(".settings-group .section-head .overline")].map((node) => node.textContent);
    expect(heads).toContain(label(window, "settings.section.modules"));
    const block = view.querySelector(".modules-block");
    const names = [...block.querySelectorAll(".module-row .lbl")].map((node) => node.textContent);
    expect(names).toEqual([
      label(window, "settings.modules.name.timetable"),
      label(window, "settings.modules.name.letters"),
      label(window, "settings.modules.name.pinboard"),
      label(window, "settings.modules.name.conferences"),
    ]);
    expect(block.querySelectorAll(".module-row .switch[aria-checked='true']").length).toBe(4);
    expect(block.querySelector(".modules-help")).toBeNull();
    expect(view.querySelector(".error, .note")).toBeNull();
  });

  test("unreported unknown modules bring the card with one button into the help page and no later button", () => {
    const { window } = loadApp();
    seed(window, all(), `
      state.modules.unknown = [{ segment: "mail", label: "E-Mail" }, { segment: "file", label: "Dateien" }];
      state.modules.iservVersion = "3.9.1";
      state.appVersion = "2609.01.31";
    `);
    const block = window.eval("settingsView()").querySelector(".modules-block");
    const card = block.querySelector(".module-card");
    expect(card).not.toBeNull();
    expect(card.querySelector(".module-card-text").textContent).toBe(
      label(window, "help.card.text.other", { count: "2", names: "E-Mail, Dateien" })
    );
    expect(block.querySelectorAll(".btn:not(.ghost)").length).toBe(1);
    expect(card.querySelector(".module-card-later")).toBeNull();
    expect(block.querySelector(".modules-unknown")).toBeNull();
    card.querySelector(".module-card-show").click();
    expect(window.eval("state.helpPage")).toBe(true);
    expect(window.eval("state.view")).toBe("settings");
  });

  test("the issue link carries the segments in the title and asks for the saved report file", () => {
    const { window } = loadApp();
    seed(window, all(), `state.modules.unknown = [{ segment: "mail", label: "E-Mail" }]; state.modules.iservVersion = ""; state.appVersion = "";`);
    const href = window.eval("moduleIssueUrl()");
    expect(href.startsWith(ISSUE_URL)).toBe(true);
    const params = new window.URLSearchParams(href.slice(ISSUE_URL.length));
    expect([...params.keys()].sort()).toEqual(["body", "title"]);
    expect(params.get("title")).toBe("Unsupported IServ modules: mail");
    expect(params.get("body")).toBe(`${ISSUE_QUESTION}\n\n${ISSUE_BODY}`);
    seed(window, all());
    const plain = new window.URLSearchParams(window.eval("moduleIssueUrl()").slice(ISSUE_URL.length));
    expect(plain.get("title")).toBe("Ranzenpost report");
    expect(plain.get("body")).toBe(ISSUE_BODY);
  });

  test("a documented module the app does not support is named in the active language on the card and by its segment in the issue title", () => {
    const { window } = loadApp();
    seed(window, all(), `
      state.modules.unsupported = [
        { segment: "dsa-classregister", slug: "dsa-classregister", label: "Klassenbuch", name: "Klassenbuch" },
        { segment: "calendar", slug: "calendar", label: "Kalender", name: "Kalender" },
      ];
      state.modules.unknown = [{ segment: "mystery", label: "Mystery" }];
      state.modules.iservVersion = "3.9.1";
      state.appVersion = "2609.02.00";
    `);
    const block = window.eval("settingsView()").querySelector(".modules-block");
    const names = [label(window, "modules.catalogue.dsa-classregister"), label(window, "modules.catalogue.calendar"), "Mystery"];
    expect(block.querySelector(".module-card-text").textContent).toBe(
      label(window, "help.card.text.other", { count: "3", names: names.join(", ") })
    );
    const params = new window.URLSearchParams(window.eval("moduleIssueUrl()").slice(ISSUE_URL.length));
    expect(params.get("title")).toBe("Unsupported IServ modules: dsa-classregister, calendar, mystery");
  });

  test("reported modules turn the card into a calm hint with a ghost button into the help page", () => {
    const { window } = loadApp();
    seed(window, all(), `
      state.modules.unknown = [{ segment: "mail", label: "E-Mail" }];
      state.config.reported_modules = ["mail"];
    `);
    const block = window.eval("settingsView()").querySelector(".modules-block");
    expect(block.querySelector(".module-card")).toBeNull();
    expect(block.querySelector(".modules-unknown").textContent).toBe(label(window, "settings.modules.unknown", { labels: "E-Mail" }));
    const button = block.querySelector(".modules-report");
    expect(button.classList.contains("ghost")).toBe(true);
    expect(button.textContent).toContain(label(window, "settings.modules.report"));
    expect(block.querySelectorAll(".btn:not(.ghost)").length).toBe(0);
    button.click();
    expect(window.eval("state.helpPage")).toBe(true);
  });

  test("the card appears for documented modules alone and every catalogue slug has a name in every language", () => {
    const { window } = loadApp();
    seed(window, all(), `state.modules.unsupported = [{ segment: "calendar", slug: "calendar", label: "Kalender", name: "Kalender" }];`);
    expect(window.eval("settingsView()").querySelector(".module-card")).not.toBeNull();
    const parsed = window.eval("applyModules({ modules: {}, unsupported: [{ segment: 'calendar' }, { label: 'x' }], unknown: [] })");
    expect(parsed.unsupported).toEqual([{ segment: "calendar", slug: "calendar", label: "calendar", name: "calendar" }]);
    expect(window.eval("catalogueModuleName({ segment: 'odd', slug: 'odd', label: 'Odd', name: 'Official' })")).toBe("Official");
  });
});

describe("an account without any module", () => {
  const none = all(Object.fromEntries(MODULES.map((name) => [name, false])));

  test("renders one calm screen with the text, the help block, no tab bar and a way into the settings", () => {
    const { window, document } = loadApp();
    seed(window, none, `state.modules.unknown = [{ segment: "mail", label: "E-Mail" }]; state.view = "overview"; render();`);
    const app = document.querySelector("#app");
    expect(app.querySelector(".tabbar")).toBeNull();
    expect(app.querySelector(".rail")).toBeNull();
    const screen = app.querySelector(".modules-empty");
    expect(screen).not.toBeNull();
    expect(screen.textContent).toContain(label(window, "modules.empty.title"));
    expect(screen.textContent).toContain(label(window, "modules.empty.text"));
    expect(screen.querySelector(".module-card")).not.toBeNull();
    expect(app.querySelector(".error, .note, .toast.bad, .overview-failed")).toBeNull();
    expect(app.querySelector(".settings-entry")).not.toBeNull();
    app.querySelector(".settings-entry").click();
    expect(window.eval("state.view")).toBe("settings");
    expect(document.querySelector(".settings-group")).not.toBeNull();
    expect(document.querySelector(".tabbar")).toBeNull();
  });

  test("without unknown modules the empty screen carries no help block", () => {
    const { window, document } = loadApp();
    seed(window, none, `state.view = "overview"; render();`);
    const screen = document.querySelector(".modules-empty");
    expect(screen.querySelector(".module-card")).toBeNull();
    expect(screen.querySelector(".btn")).toBeNull();
  });

  test("a view of a missing module falls back to the overview", () => {
    const { window } = loadApp();
    seed(window, all({ messenger: false }), `state.view = "messenger";`);
    window.eval("revalidateView()");
    expect(window.eval("state.view")).toBe("overview");
    seed(window, all(), `state.view = "messenger";`);
    window.eval("revalidateView()");
    expect(window.eval("state.view")).toBe("messenger");
    seed(window, none, `state.view = "settings";`);
    window.eval("revalidateView()");
    expect(window.eval("state.view")).toBe("settings");
  });
});

describe("loading skips missing modules", () => {
  test("loadRest never requests a missing module", async () => {
    const { window } = loadApp();
    seed(window, all({ letters: false, pinboard: false, conferences: false, absences: false, messenger: false }));
    const calls = [];
    window.fetch = (url) => {
      calls.push(String(url));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    };
    window.eval("loadRest()");
    await new Promise((resolve) => setTimeout(resolve, 0));
    const hit = (part) => calls.some((url) => url.includes(part));
    expect(hit("api/letters")).toBe(false);
    expect(hit("api/pinboard")).toBe(false);
    expect(hit("api/conferences")).toBe(false);
    expect(hit("api/absences")).toBe(false);
    expect(hit("api/messenger")).toBe(false);
    expect(hit("api/me")).toBe(true);
    expect(hit("api/marks")).toBe(true);
  });

  test("loadRest leaves the exam marks and cancellations alone without a timetable", async () => {
    const { window } = loadApp();
    seed(window, all({ timetable: false }));
    const calls = [];
    window.fetch = (url) => {
      calls.push(String(url));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    };
    window.eval("loadRest()");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(calls.some((url) => url.includes("api/marks"))).toBe(false);
    expect(calls.some((url) => url.includes("api/cancellations"))).toBe(false);
    expect(calls.some((url) => url.includes("api/letters"))).toBe(true);
  });
});

async function settled() {
  const app = loadApp();
  for (let round = 0; round < 8; round += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  return app;
}

describe("the IServ modules block can check again", () => {
  test("one small link posts the recheck, applies the answer and reports", async () => {
    const { window, document } = await settled();
    seed(window, all({ letters: false }), `state.view = "settings"; render();`);
    const calls = [];
    window.fetch = (url, options) => {
      calls.push({ url: String(url), options: options || {} });
      if (String(url).includes("api/modules/recheck")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
          ok: true,
          message_key: "api.modules.rechecked",
          modules: { modules: { letters: true }, unknown: [], checked_at: 20, iserv_version: "3.9" },
        }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    };
    const button = document.querySelector(".modules-block .modules-recheck");
    expect(button).not.toBeNull();
    expect(button.classList.contains("link-btn")).toBe(true);
    expect(button.textContent).toContain(label(window, "settings.modules.recheck"));
    expect(document.querySelectorAll(".modules-block .btn:not(.ghost)").length).toBe(0);
    button.click();
    for (let round = 0; round < 6; round += 1) await new Promise((resolve) => setTimeout(resolve, 0));
    const posts = calls.filter((entry) => entry.url.includes("api/modules/recheck"));
    expect(posts.length).toBe(1);
    expect(posts[0].options.method).toBe("POST");
    expect(window.eval("moduleOn('letters')")).toBe(true);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "api.modules.rechecked"));
    const names = [...document.querySelectorAll(".modules-block .module-row .lbl")].map((node) => node.textContent);
    expect(names).toContain(label(window, "settings.modules.name.letters"));
  });

  test("a rate-limited answer keeps the registry and says so calmly", async () => {
    const { window, document } = await settled();
    seed(window, all({ letters: false }), `state.view = "settings"; render();`);
    window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
      ok: false,
      error: "rate_limited",
      message_key: "api.modules.tooSoon",
      modules: { modules: { letters: false }, unknown: [], checked_at: 20, iserv_version: "3.9" },
    }) });
    document.querySelector(".modules-block .modules-recheck").click();
    for (let round = 0; round < 6; round += 1) await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("moduleOn('letters')")).toBe(false);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "api.modules.tooSoon"));
    expect(document.querySelector(".error")).toBeNull();
  });
});

describe("an account whose modules need no child", () => {
  test("the overview shows the letters and the noticeboard without a child and without a no-child message", () => {
    const { window } = loadApp();
    seed(window, all({ timetable: false, absences: false, messenger: false }), `
      state.children = [];
      state.childId = null;
      state.timetable = null;
      state.overviewWeeks = {};
    `);
    window.eval(`
      state.letters = { tab: "current", letters: [{ letter_id: "l1", recipient_id: "r1", title: "Brief", unread: true }] };
      state.pinboard = { folders: [], feed: [{ id: "p1", unread: true, title: "Neu" }] };
    `);
    const view = window.eval("overviewView()");
    const areas = [...view.querySelectorAll(".panel")].map((panel) => panel.dataset.area);
    expect(areas).toEqual(["letters", "noticeboard"]);
    expect(view.textContent).not.toContain(label(window, "overview.noChild"));
    expect(view.querySelector(".overview-failed")).toBeNull();
  });
});
