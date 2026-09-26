import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const MODULES = ["timetable", "letters", "pinboard", "absences", "conferences", "messenger"];
const ISSUE_URL = "https://github.com/githuber110/ranzenpost/issues/new?";
const REPORT = "# Ranzenpost report\n\n## Versions\n- Ranzenpost: 2609.02.00\n";
const FACTS = { app: "2609.02.00", home_assistant: "2026.9.1", iserv: "3.9.1" };
const BUNDLE_NAME = "ranzenpost-report.zip";
const DAY = 86400;

function seed(window, extra = "") {
  const available = {};
  for (const name of MODULES) available[name] = true;
  window.eval(`
    state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
    state.childId = "c1";
    state.me = { forename: "Alice" };
    state.config = { language: "de", notify_services: [], notify_events: {}, phones: [], period_times: {}, reported_modules: [], modules_card_hidden: {} };
    state.timetable = { lessons: [{ day_of_week: weekdayIndex(new Date()), period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
    state.overviewWeeks = {};
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.messengerRooms = { rooms: [] };
    state.modules = applyModules({
      modules: ${JSON.stringify(available)},
      unsupported: [{ segment: "calendar", slug: "calendar", label: "Kalender", name: "Kalender" }],
      unknown: [{ segment: "mail", label: "E-Mail" }],
      checked_at: 10,
      iserv_version: "3.9",
    });
    state.helpPage = false;
    state.helpReport = "";
    state.helpFacts = null;
    state.helpFailed = false;
    state.helpBundle = null;
    state.helpBundleFailed = false;
    ${extra}
  `);
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || null)})`);
}

function fakeFetch(window, calls, bundleOk = true) {
  window.URL.createObjectURL = () => "blob:report";
  window.URL.revokeObjectURL = () => {};
  window.fetch = (url, options) => {
    const target = String(url);
    calls.push({ url: target, options: options || {} });
    if (target.includes("api/diagnostics/report.zip")) {
      if (!bundleOk) return Promise.resolve({ ok: false, status: 500, headers: { get: () => "" }, json: () => Promise.resolve({}), text: () => Promise.resolve("") });
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: (name) => (name.toLowerCase() === "content-disposition" ? `attachment; filename="${BUNDLE_NAME}"` : "application/zip") },
        blob: () => Promise.resolve(new window.Blob(["zip"], { type: "application/zip" })),
      });
    }
    if (target.includes("api/diagnostics")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ report: REPORT, segments: ["calendar", "mail"], facts: FACTS }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ saved: true }) });
  };
}

function trackDownloads(window) {
  const downloads = [];
  window.HTMLAnchorElement.prototype.click = function click() {
    if (this.getAttribute("download")) downloads.push({ href: this.getAttribute("href"), download: this.getAttribute("download") });
  };
  return downloads;
}

async function settle(rounds = 8) {
  for (let round = 0; round < rounds; round += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

async function app() {
  const loaded = loadApp();
  await settle();
  return loaded;
}

function configPosts(calls) {
  return calls.filter((entry) => entry.url.includes("api/config") && entry.options.method === "POST").map((entry) => JSON.parse(entry.options.body));
}

describe("the overview card for modules Ranzenpost does not support yet", () => {
  test("is the first block of the first chapter, names the modules in the active language and offers show how and later", async () => {
    const { window } = await app();
    seed(window);
    const chapters = window.eval("overviewChapters()");
    expect(chapters[0].area).toBe("today");
    expect(chapters[0].blocks[0].key).toBe("modules:card");
    const view = window.eval("overviewView()");
    const card = view.querySelector(".module-card");
    expect(card).not.toBeNull();
    expect(card.closest(".panel").dataset.area).toBe("today");
    expect(card.getAttribute("role")).toBe("status");
    const names = `${label(window, "modules.catalogue.calendar")}, E-Mail`;
    expect(card.querySelector(".module-card-text").textContent).toBe(label(window, "help.card.text.other", { count: "2", names }));
    expect(card.querySelector(".module-card-show").textContent).toBe(label(window, "help.card.show"));
    expect(card.querySelector(".module-card-later").textContent).toBe(label(window, "help.card.later"));
    expect(card.querySelectorAll(".btn:not(.ghost)").length).toBe(1);
  });

  test("a single module uses the singular sentence", async () => {
    const { window } = await app();
    seed(window, `state.modules.unsupported = [];`);
    const card = window.eval("overviewView()").querySelector(".module-card");
    expect(card.querySelector(".module-card-text").textContent).toBe(label(window, "help.card.text.one", { count: "1", names: "E-Mail" }));
  });

  test("without unknown modules there is no card", async () => {
    const { window } = await app();
    seed(window, `state.modules.unsupported = []; state.modules.unknown = [];`);
    expect(window.eval("overviewView()").querySelector(".module-card")).toBeNull();
  });

  test("later hides the card for thirty days, stores that, and a new slug brings it back", async () => {
    const { window } = await app();
    seed(window, `state.view = "overview"; render();`);
    const calls = [];
    fakeFetch(window, calls);
    window.document.querySelector(".module-card-later").click();
    await settle();
    expect(window.document.querySelector(".module-card")).toBeNull();
    const hidden = window.eval("state.config.modules_card_hidden");
    const now = Math.floor(Date.now() / 1000);
    expect(hidden.until).toBeGreaterThan(now + 29 * DAY);
    expect(hidden.until).toBeLessThanOrEqual(now + 30 * DAY + 5);
    expect(hidden.segments).toEqual(["calendar", "mail"]);
    const posted = configPosts(calls);
    expect(posted.length).toBe(1);
    expect(posted[0].modules_card_hidden).toEqual(hidden);
    window.eval(`state.modules.unknown.push({ segment: "file", label: "Dateien" });`);
    expect(window.eval("overviewView()").querySelector(".module-card")).not.toBeNull();
    window.eval(`state.modules.unknown.pop(); state.config.modules_card_hidden.until = ${now - 1};`);
    expect(window.eval("overviewView()").querySelector(".module-card")).not.toBeNull();
  });

  test("reported slugs keep the card away until a new slug appears", async () => {
    const { window } = await app();
    seed(window, `state.config.reported_modules = ["calendar", "mail"];`);
    expect(window.eval("overviewView()").querySelector(".module-card")).toBeNull();
    window.eval(`state.modules.unknown.push({ segment: "file", label: "Dateien" });`);
    const card = window.eval("overviewView()").querySelector(".module-card");
    expect(card.querySelector(".module-card-text").textContent).toBe(label(window, "help.card.text.one", { count: "1", names: "Dateien" }));
  });

  test("show how opens the help page and back returns to the overview", async () => {
    const { window, document } = await app();
    seed(window, `state.view = "overview"; render();`);
    fakeFetch(window, []);
    document.querySelector(".module-card-show").click();
    expect(window.eval("state.view")).toBe("settings");
    expect(window.eval("state.helpPage")).toBe(true);
    expect(document.querySelector(".help-page")).not.toBeNull();
    expect(document.querySelector(".header-title").textContent).toBe(label(window, "help.title"));
    document.querySelector(".header-back").click();
    expect(window.eval("state.view")).toBe("overview");
    expect(window.eval("state.helpPage")).toBe(false);
  });
});

describe("the help page", () => {
  function openHelp(window, calls) {
    fakeFetch(window, calls || []);
    window.eval(`state.view = "settings"; state.helpPage = true; render();`);
  }

  test("explains the report, lists what it holds and never holds, loads the preview and prepares the file", async () => {
    const { window, document } = await app();
    seed(window);
    const calls = [];
    openHelp(window, calls);
    const page = document.querySelector(".help-page");
    const intro = [...page.querySelectorAll(".help-intro")].map((node) => node.textContent);
    expect(intro).toEqual([label(window, "help.intro.what"), label(window, "help.intro.not")]);
    const heads = [...page.querySelectorAll(".help-list .overline")].map((node) => node.textContent);
    expect(heads).toEqual([label(window, "help.contains.title"), label(window, "help.never.title")]);
    expect(page.querySelectorAll(".help-list")[0].querySelectorAll("li").length).toBe(5);
    expect(page.querySelectorAll(".help-list")[1].querySelectorAll("li").length).toBe(4);
    expect(page.querySelector(".help-structure")).toBeNull();
    expect(page.querySelector(".help-save").disabled).toBe(true);
    expect(page.querySelector(".help-copy").disabled).toBe(true);
    expect(page.querySelector(".help-preview-state").textContent).toContain(label(window, "help.loading"));
    await settle();
    const requests = calls.filter((entry) => entry.url.includes("api/diagnostics"));
    expect(requests.length).toBe(2);
    expect(requests[0].url).toContain("structure=1");
    expect(requests[1].url).toContain("api/diagnostics/report.zip");
    const preview = document.querySelector(".help-preview");
    expect(preview.tagName).toBe("PRE");
    expect(preview.getAttribute("dir")).toBe("ltr");
    expect(preview.textContent).toBe(REPORT);
    const save = document.querySelector(".help-save");
    expect(save.disabled).toBe(false);
    expect(save.textContent).toBe(label(window, "help.save"));
    expect(document.querySelector(".help-copy").disabled).toBe(false);
    expect(page.textContent).toContain(label(window, "help.account"));
    expect(page.textContent).toContain(label(window, "help.issue.hint"));
  });

  test("the save button says it is preparing while the file is built", async () => {
    const { window, document } = await app();
    seed(window, `state.helpReport = ${JSON.stringify(REPORT)};`);
    let release;
    window.URL.createObjectURL = () => "blob:report";
    window.fetch = () => new Promise((resolve) => { release = resolve; });
    window.eval(`state.view = "settings"; state.helpPage = true; render(); autoLoad("help:bundle", loadHelpBundle);`);
    const save = document.querySelector(".help-save");
    expect(save.disabled).toBe(true);
    expect(save.textContent).toBe(label(window, "help.preparing"));
    release({ ok: true, status: 200, headers: { get: () => "" }, blob: () => Promise.resolve(new window.Blob(["zip"])) });
    await settle();
    expect(document.querySelector(".help-save").textContent).toBe(label(window, "help.save"));
  });

  test("the action block has one loud button: save first, then the issue link and copy as quiet buttons", async () => {
    const { window, document } = await app();
    seed(window);
    openHelp(window, []);
    await settle();
    const actions = [...document.querySelectorAll(".help-actions > .btn")];
    expect(actions.map((node) => node.classList.contains("help-save") ? "save" : node.classList.contains("help-issue") ? "issue" : node.classList.contains("help-copy") ? "copy" : "other")).toEqual(["save", "issue", "copy"]);
    const loud = actions.filter((node) => !node.classList.contains("ghost"));
    expect(loud.length).toBe(1);
    expect(loud[0].classList.contains("help-save")).toBe(true);
  });

  test("the actions follow the short intro, the lists and the preview wait in a closed details block", async () => {
    const { window, document } = await app();
    seed(window);
    openHelp(window, []);
    await settle();
    const page = document.querySelector(".help-page");
    const order = [...page.children].map((node) => node.className);
    expect(order.slice(0, 3)).toEqual(["help-intro", "help-intro", "btn-stack help-actions"]);
    expect(page.querySelector(".help-save")).not.toBeNull();
    expect(page.querySelector(".help-account").textContent).toBe(label(window, "help.account"));
    expect(page.querySelector(".help-no-start").textContent).toBe(label(window, "help.noStart"));
    const details = page.querySelector("details.help-details");
    expect(details.open).toBe(false);
    expect(details.querySelector("summary").textContent).toBe(label(window, "help.details"));
    expect(details.querySelectorAll(".help-list").length).toBe(2);
    expect(details.querySelector(".help-preview").textContent).toBe(REPORT);
    expect(page.querySelector(":scope > .help-list, :scope > .help-preview")).toBeNull();
    details.open = true;
    details.dispatchEvent(new window.Event("toggle"));
    window.eval("rerender()");
    expect(document.querySelector("details.help-details").open).toBe(true);
  });

  test("save report downloads ranzenpost-report.zip, says to attach it, and remembers the reported slugs", async () => {
    const { window, document } = await app();
    seed(window);
    const calls = [];
    openHelp(window, calls);
    await settle();
    const downloads = trackDownloads(window);
    document.querySelector(".help-save").click();
    await settle();
    expect(downloads).toEqual([{ href: "blob:report", download: BUNDLE_NAME }]);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "help.saved"));
    expect(window.eval("state.config.reported_modules")).toEqual(["calendar", "mail"]);
    expect(configPosts(calls).length).toBe(1);
    expect(calls.filter((entry) => entry.url.includes("report.zip")).length).toBe(1);
  });

  test("a file that cannot be built is retried on save and then points to copying", async () => {
    const { window, document } = await app();
    seed(window);
    const calls = [];
    fakeFetch(window, calls, false);
    window.eval(`state.view = "settings"; state.helpPage = true; render();`);
    await settle();
    const save = document.querySelector(".help-save");
    expect(save.disabled).toBe(false);
    expect(save.textContent).toBe(label(window, "help.save"));
    const downloads = trackDownloads(window);
    save.click();
    await settle();
    expect(downloads).toEqual([]);
    expect(calls.filter((entry) => entry.url.includes("report.zip")).length).toBe(2);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "help.saveFailed"));
    expect(window.eval("state.config.reported_modules")).toEqual([]);
  });

  test("a failed report shows a calm message with a retry", async () => {
    const { window, document } = await app();
    seed(window);
    window.fetch = () => Promise.reject(new Error("offline"));
    window.eval(`state.view = "settings"; state.helpPage = true; render();`);
    await settle();
    expect(document.querySelector(".help-preview")).toBeNull();
    expect(document.querySelector(".help-preview-state").textContent).toContain(label(window, "help.failed"));
    expect(document.querySelector(".help-retry")).not.toBeNull();
    expect(document.querySelector(".error, .note")).toBeNull();
    const calls = [];
    fakeFetch(window, calls);
    document.querySelector(".help-retry").click();
    await settle();
    expect(document.querySelector(".help-preview").textContent).toBe(REPORT);
  });

  test("copy report writes the report to the clipboard, says so, and remembers the reported slugs", async () => {
    const { window, document } = await app();
    seed(window);
    const calls = [];
    const written = [];
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText: (text) => { written.push(text); return Promise.resolve(); } },
      configurable: true,
    });
    openHelp(window, calls);
    await settle();
    document.querySelector(".help-copy").click();
    await settle();
    expect(written).toEqual([REPORT]);
    expect(document.querySelector(".toast").textContent).toContain(label(window, "help.copied"));
    expect(window.eval("state.config.reported_modules")).toEqual(["calendar", "mail"]);
    const posted = configPosts(calls);
    expect(posted.length).toBe(1);
    expect(posted[0].reported_modules).toEqual(["calendar", "mail"]);
    expect(window.eval("moduleCardWanted()")).toBe(false);
    document.querySelector(".header-back").click();
    expect(document.querySelector(".module-card")).toBeNull();
  });

  test("a failed copy says so and does not mark anything as reported", async () => {
    const { window, document } = await app();
    seed(window);
    Object.defineProperty(window.navigator, "clipboard", { value: undefined, configurable: true });
    window.document.execCommand = () => false;
    openHelp(window, []);
    await settle();
    document.querySelector(".help-copy").click();
    await settle();
    expect(document.querySelector(".toast").textContent).toContain(label(window, "help.copyFailed"));
    expect(window.eval("state.config.reported_modules")).toEqual([]);
  });

  test("the GitHub link opens a prefilled issue in a new tab and remembers the reported slugs", async () => {
    const { window, document } = await app();
    seed(window);
    const calls = [];
    openHelp(window, calls);
    await settle();
    const link = document.querySelector(".help-issue");
    expect(link.tagName).toBe("A");
    expect(link.classList.contains("ghost")).toBe(true);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener");
    const href = link.getAttribute("href");
    expect(href.startsWith(ISSUE_URL)).toBe(true);
    const params = new window.URLSearchParams(href.slice(ISSUE_URL.length));
    expect(params.get("title")).toBe("Unsupported IServ modules: calendar, mail");
    const versions = label(window, "help.issue.versions", { app: "2609.02.00", home_assistant: "2026.9.1", iserv: "3.9.1" });
    expect(versions).toBe("Ranzenpost 2609.02.00, Home Assistant 2026.9.1, IServ 3.9.1");
    const question = label(window, "help.issue.moduleQuestion");
    expect(params.get("body")).toBe(`${question}\n\n${label(window, "help.issue.body", { versions })}`);
    expect(params.get("body").startsWith(question)).toBe(true);
    link.addEventListener("click", (event) => event.preventDefault());
    link.click();
    await settle();
    expect(window.eval("state.config.reported_modules")).toEqual(["calendar", "mail"]);
    expect(configPosts(calls).length).toBe(1);
  });

  test("the settings carry a report a problem row that opens the page and back returns to the settings", async () => {
    const { window, document } = await app();
    seed(window, `state.view = "settings"; render();`);
    fakeFetch(window, []);
    const row = [...document.querySelectorAll(".setting-row")].find((node) => node.textContent.includes(label(window, "help.row")));
    expect(row).not.toBeUndefined();
    row.click();
    expect(document.querySelector(".help-page")).not.toBeNull();
    document.querySelector(".header-back").click();
    expect(window.eval("state.view")).toBe("settings");
    expect(window.eval("state.helpPage")).toBe(false);
    expect(document.querySelector(".help-page")).toBeNull();
    expect(document.querySelector(".settings-group")).not.toBeNull();
  });

  test("every help text exists in every language bundle", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const dir = path.resolve("frontend/i18n");
    const base = JSON.parse(fs.readFileSync(path.join(dir, "de.json"), "utf8"));
    const keys = Object.keys(base).filter((key) => key.startsWith("help.") || key === "settings.section.help" || key === "settings.modules.report");
    expect(keys.length).toBeGreaterThan(30);
    for (const language of ["en", "ar", "tr", "ru", "uk"]) {
      const bundle = JSON.parse(fs.readFileSync(path.join(dir, `${language}.json`), "utf8"));
      for (const key of keys) {
        if (key.startsWith("help.card.text.")) continue;
        expect(bundle[key], `${language}:${key}`).toBeTruthy();
      }
      expect(bundle["help.card.text.other"], `${language}:help.card.text.other`).toBeTruthy();
    }
  });
});

describe("the troubleshooting report outside the settings", () => {
  test("the error notice saves the report and says where the log is", async () => {
    const { window } = await app();
    seed(window);
    const calls = [];
    fakeFetch(window, calls);
    const downloads = trackDownloads(window);
    window.eval(`renderNotice(detachedRoot(), "Titel", "Text", true)`);
    const button = window.document.querySelector("#app .report-save");
    expect(button.textContent).toBe(label(window, "help.report.save"));
    expect(button.classList.contains("ghost")).toBe(true);
    button.click();
    await settle();
    expect(downloads.map((entry) => entry.download)).toEqual([BUNDLE_NAME]);
    expect(window.document.querySelector("#app .report-status").textContent).toBe(label(window, "help.report.saved"));
  });

  test("a failed report points to the log in Home Assistant", async () => {
    const { window } = await app();
    seed(window);
    fakeFetch(window, [], false);
    window.eval(`renderNotice(detachedRoot(), "Titel", "Text", true)`);
    window.document.querySelector("#app .report-save").click();
    await settle();
    const status = window.document.querySelector("#app .report-status").textContent;
    expect(status).toBe(label(window, "help.report.failed"));
    expect(status).toContain("Ranzenpost");
  });

  test("the sign in again page offers the report too", async () => {
    const { window } = await app();
    seed(window);
    window.eval(`renderReconnect(detachedRoot(), "parent", "", "")`);
    expect(window.document.querySelector("#app .report-save")).not.toBeNull();
  });

  test("the report from an error page asks for no page structure, so it never signs in", async () => {
    const { window } = await app();
    seed(window);
    const calls = [];
    fakeFetch(window, calls);
    trackDownloads(window);
    window.eval(`renderNotice(detachedRoot(), "Titel", "Text", true)`);
    window.document.querySelector("#app .report-save").click();
    await settle();
    const bundle = calls.find((entry) => entry.url.includes("report.zip"));
    expect(bundle.url).toContain("structure=0");
  });

  test("a locked account shows the explanation and the password form only on request", async () => {
    const { window } = await app();
    seed(window);
    window.eval(`renderReconnect(detachedRoot(), "parent", "", "locked")`);
    const page = window.document.querySelector("#app");
    expect(page.querySelector("input[type=password]")).toBeNull();
    expect(page.textContent).toContain(label(window, "api.login.locked"));
    const reveal = page.querySelector(".locked-password-reveal");
    expect(reveal.textContent).toBe(label(window, "account.reconnect.lockedNewPassword"));
    reveal.click();
    expect(page.querySelector("input[type=password]")).not.toBeNull();
  });

  test("the settings row and the help page name the log", async () => {
    const { window } = await app();
    seed(window, `state.view = "settings";`);
    const row = window.eval("settingsView()").querySelector(".help-setting");
    expect(row.textContent).toContain(label(window, "help.row.hint"));
    const page = window.eval("helpPageView()");
    expect(page.querySelector(".help-no-start").textContent).toBe(label(window, "help.noStart"));
  });
});
