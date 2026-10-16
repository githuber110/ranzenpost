import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

function pad(value) {
  return String(value).padStart(2, "0");
}

function dayOffset(offset) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const SCHOOL = "https://school.example";
const LONG_TITLE = "Write a report about the planned excursion to the river including all measurements and a drawing of the bridge";

function task(id, title, due, extra = {}) {
  return {
    id, title, start: "", start_text: "", due, due_text: due, tags: [], done: null, done_text: "", past: false,
    path: `/iserv/exercise/show/${id}`, extra: [],
    connection_id: "a1b2c3d4", school: "Riverside", ...extra,
  };
}

const LATER = task("2", "Poster", dayOffset(9), { tags: ["Art"] });
const SOONER = task("1", LONG_TITLE, dayOffset(2), { start: dayOffset(-1) });
const LATE = task("3", "Overdue sheet", dayOffset(-2));
const DONE = task("4", "Finished quiz", dayOffset(3), { done: true });
const PAST = task("5", "Old essay", dayOffset(-40), { past: true, done: true });
const NEWS = [
  { id: "general/2", title: "Library opens later", date: `${dayOffset(-1)}T09:30`, date_text: "", category: "General", category_slug: "general", summary: "From Monday at nine.", path: "/iserv/news/general/2", connection_id: "a1b2c3d4" },
  { id: "sport/1", title: "Sports day", date: "", date_text: "", category: "", category_slug: "sport", summary: "", path: "/iserv/news/sport/1", connection_id: "a1b2c3d4" },
];
const SCHOOLS = [{ connection_id: "a1b2c3d4", school: "Riverside", last_success: 1 }];

function seed(window, extra = "") {
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.me = { forename: "Sam" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.modules = applyModules({ modules: { tasks: true, news: true } });
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    ${extra}
  `);
}

function setLists(window, tasks, news) {
  evalWith(window, `
    state.tasks = { tasks: testArgs[0], schools: testArgs[2], unavailable: [] };
    state.news = { news: testArgs[1], schools: testArgs[2], unavailable: [] };
  `, tasks, news, SCHOOLS);
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

describe("tasks and news are confirmed-only modules", () => {
  test("both are off until the registry confirms them", () => {
    const { window } = loadApp();
    expect(window.eval("defaultModules().available.tasks")).toBe(false);
    expect(window.eval("defaultModules().available.news")).toBe(false);
    expect(window.eval("applyModules({ modules: { letters: true } }).available.tasks")).toBe(false);
    expect(window.eval("applyModules({ modules: { tasks: true, news: true } }).available.news")).toBe(true);
  });

  test("with the modules on both views join the navigation, with them off they and their chapters are gone", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [SOONER], NEWS);
    expect(window.eval("visibleViews().map((item) => item.key)")).toEqual(expect.arrayContaining(["tasks", "news"]));
    evalWith(window, "state.modules = applyModules({ modules: {} });");
    expect(window.eval("visibleViews().map((item) => item.key)")).not.toContain("tasks");
    expect(window.eval("tasksChapter('normal')")).toBeNull();
    expect(window.eval("newsChapter('normal')")).toBeNull();
  });

  test("a switched-off module hides its view even when IServ offers it", () => {
    const { window } = loadApp();
    seed(window, 'state.config.modules_disabled = ["news"];');
    expect(window.eval("viewAvailable('news')")).toBe(false);
    expect(window.eval("viewAvailable('tasks')")).toBe(true);
  });
});

describe("the tasks view", () => {
  test("open tasks come first by due date, done ones follow and past ones sit collapsed at the end", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [PAST, LATER, DONE, SOONER, LATE], []);
    const view = window.eval("tasksView()");
    const sections = view.querySelectorAll(".list-section");
    expect(texts(sections[0].querySelectorAll(".row-title"))).toEqual(["Overdue sheet", LONG_TITLE, "Poster"]);
    expect(texts(sections[1].querySelectorAll(".row-title"))).toEqual(["Finished quiz"]);
    const past = view.querySelector("details.list-past");
    expect(past.open).toBe(false);
    expect(texts(past.querySelectorAll(".row-title"))).toEqual(["Old essay"]);
    expect(past.querySelector("summary .overline").textContent).toBe("Vergangene Aufgaben");
    expect(past.querySelector("summary .count").textContent).toBe("1");
  });

  test("an opened past section stays open when the list reloads and closes again on the next visit", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [SOONER, PAST], []);
    const first = window.eval("tasksView()").querySelector("details.list-past");
    first.open = true;
    first.dispatchEvent(new window.Event("toggle"));
    expect(window.eval("tasksView()").querySelector("details.list-past").open).toBe(true);
    window.eval("applyViewEntryDefaults('tasks')");
    expect(window.eval("tasksView()").querySelector("details.list-past").open).toBe(false);
  });

  test("a row opens the task in the app, wraps its long title in its own direction and shows due date, start and tags", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [SOONER, LATER, LATE], []);
    const rows = window.eval("tasksView()").querySelectorAll(".list-row");
    const first = [...rows].find((row) => row.querySelector(".row-title").textContent === LONG_TITLE);
    expect(first.tagName).toBe("BUTTON");
    expect(first.getAttribute("href")).toBeNull();
    expect(first.querySelector(".row-title").getAttribute("dir")).toBe("auto");
    expect(first.querySelector(".row-sub").textContent).toMatch(/^Abgabe .+ · Start .+$/);
    const poster = [...rows].find((row) => row.querySelector(".row-title").textContent === "Poster");
    expect(texts(poster.querySelectorAll(".row-tags .tag"))).toEqual(["Art"]);
    const late = [...rows].find((row) => row.querySelector(".row-title").textContent === "Overdue sheet");
    expect(late.querySelector(".row-side .tag").textContent).toBe("Überfällig");
  });

  test("an empty list says so and offers no way out to IServ", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], []);
    const view = window.eval("tasksView()");
    expect(view.querySelector(".empty b").textContent).toBe("Keine Aufgaben");
    expect(view.querySelectorAll("a, .btn").length).toBe(0);
  });

  test("a task sheet shows its listed dates, state and further columns before its page is read", () => {
    const { window } = loadApp();
    seed(window);
    const task = Object.assign({}, SOONER, { done: false, tags: ["Maths"], extra: [{ label: "Lehrende", value: "Teacher B" }] });
    const parts = evalWith(window, "taskDetailParts(testArgs[0])", task);
    const body = window.document.createElement("div");
    body.append(...parts.body.filter(Boolean));
    expect(parts.title).toBe(LONG_TITLE);
    expect(body.querySelector(".row-meta").textContent).toMatch(/^Abgabe .+ · Start .+ · Offen$/);
    expect(texts(body.querySelectorAll(".row-tags .tag"))).toEqual(["Maths"]);
    expect(texts(body.querySelectorAll(".task-facts .field-label"))).toEqual(["Lehrende"]);
    expect(texts(body.querySelectorAll(".task-facts .fact"))).toEqual(["Teacher B"]);
    expect(body.textContent).not.toContain("noch nicht");
    expect(parts.foot).toBeNull();
  });

  test("a failed load offers a retry instead of an empty list", () => {
    const { window } = loadApp();
    seed(window, 'state.tasks = { error: "upstream" };');
    const view = window.eval("tasksView()");
    expect(view.querySelector(".empty b").textContent).toBe("Nicht erreichbar");
    expect(view.querySelectorAll(".btn").length).toBe(1);
  });

  test("the overview chapter lists only open tasks with one due date and no start", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [PAST, DONE, LATER, SOONER], []);
    const chapter = window.eval("tasksChapter('normal')");
    expect(chapter.count).toBe(2);
    const node = chapter.blocks[0].node;
    expect(node.querySelector(".row-sub")).toBeNull();
    expect(node.querySelectorAll(".row-meta").length).toBe(1);
    expect(chapter.blocks.map((block) => block.key)).toEqual(["task:a1b2c3d4:1", "task:a1b2c3d4:2", "tasks:all"]);
    setLists(window, [PAST, DONE], []);
    expect(window.eval("tasksChapter('normal')")).toBeNull();
  });
});

describe("the news view", () => {
  test("every item shows in IServ order with category, date and summary, with and without a date", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    const rows = window.eval("newsView()").querySelectorAll(".list-row");
    expect(texts([...rows].map((row) => row.querySelector(".row-title")))).toEqual(["Library opens later", "Sports day"]);
    expect(rows[0].querySelector(".row-sub").textContent).toMatch(/^General · .+\nFrom Monday at nine\.$/);
    expect(rows[1].querySelector(".row-sub").textContent).toBe("sport");
    expect(rows[0].tagName).toBe("BUTTON");
    expect(rows[0].getAttribute("href")).toBeNull();
  });

  test("the overview chapter shows the news", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    const chapter = window.eval("newsChapter('compact')");
    expect(chapter.count).toBe(2);
    expect(chapter.blocks.at(-1).key).toBe("news:all");
  });

  test("no news shows the empty state", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], []);
    expect(window.eval("newsView()").querySelector(".empty b").textContent).toBe("Keine News");
  });
});

describe("pushes for tasks and news can be switched off", () => {
  test("the notification settings offer a switch for each when the module is on", () => {
    const { window } = loadApp();
    seed(window);
    const events = window.eval("notifyEvents().map(([key]) => key)");
    expect(events).toEqual(expect.arrayContaining(["tasks", "news"]));
    evalWith(window, "state.modules = applyModules({ modules: {} });");
    expect(window.eval("notifyEvents().map(([key]) => key)")).not.toContain("tasks");
  });
});

const DETAIL = {
  text: ["03.10.2026 · General", "From Monday the library opens at nine.", "Bring your card."],
  images: [{ path: "/iserv/news/image/abc", label: "Front door" }],
  files: [{ path: "/iserv/file/download/info.pdf", label: "Opening hours" }],
  links: [{ url: "https://example.org/library", label: "" }, { path: "/iserv/news/general/3", label: "Bad" }],
};

describe("a list a school could not read", () => {
  test("with no entry from any school both views show the failure instead of an empty list", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, `
      state.tasks = { tasks: [], schools: [], unavailable: ["a1b2c3d4"] };
      state.news = { news: [], schools: [], unavailable: ["a1b2c3d4"] };
    `);
    expect(window.eval("tasksView()").querySelector(".empty b").textContent).toBe("Nicht erreichbar");
    expect(window.eval("newsView()").querySelector(".empty b").textContent).toBe("Nicht erreichbar");
    expect(window.eval("tasksChapter('normal').blocks.map((block) => block.key)")).toEqual(["tasks:failed"]);
    expect(window.eval("newsChapter('normal').blocks.map((block) => block.key)")).toEqual(["news:failed"]);
  });

  test("entries of the schools that answered still show", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.tasks = { tasks: testArgs[0], schools: testArgs[1], unavailable: ['other'] };", [SOONER], SCHOOLS);
    const view = window.eval("tasksView()");
    expect(view.querySelector(".empty")).toBeNull();
    expect(texts(view.querySelectorAll(".row-title"))).toContain(LONG_TITLE);
  });
});

describe("nothing hands the user off to IServ", () => {
  test("views, overview blocks and both detail sheets carry no link out and no new window", () => {
    const { window } = loadApp();
    seed(window);
    const schools = [
      { connection_id: "a1b2c3d4", school: "Riverside", last_success: 1 },
      { connection_id: "e5f6a7b8", school: "Hillside", last_success: 1 },
    ];
    evalWith(window, `
      state.tasks = { tasks: testArgs[0], schools: testArgs[2], unavailable: [] };
      state.news = { news: testArgs[1], schools: testArgs[2], unavailable: [] };
    `, [SOONER, DONE, PAST, LATE], [Object.assign({}, NEWS[0], { detail: DETAIL }), NEWS[1]], schools);
    const host = window.document.createElement("div");
    host.append(window.eval("tasksView()"), window.eval("newsView()"));
    for (const chapter of [window.eval("tasksChapter('normal')"), window.eval("newsChapter('normal')")]) {
      for (const block of chapter.blocks) host.append(block.node);
    }
    for (const parts of [
      evalWith(window, "taskDetailParts(testArgs[0])", SOONER),
      evalWith(window, "taskDetailParts(testArgs[0])", PAST),
      evalWith(window, "newsDetailParts(state.news.news[0])"),
    ]) {
      host.append(...parts.body.filter(Boolean), ...(parts.foot || []));
    }
    const out = [...host.querySelectorAll("[href], [target]")].map((node) => node.outerHTML.slice(0, 120));
    expect(out).toEqual([]);
    expect(host.textContent).not.toContain("In IServ öffnen");
    expect(host.querySelectorAll(".task-row").length).toBe(4);
  });
});

describe("a news item opens with its full text", () => {
  test("the sheet shows the text, files and images as attachments of the app and links as text", () => {
    const { window } = loadApp();
    seed(window);
    const parts = evalWith(window, "newsDetailParts(Object.assign({}, testArgs[0], { detail: testArgs[1] }))", NEWS[0], DETAIL);
    const body = window.document.createElement("div");
    body.append(...parts.body.filter(Boolean));
    expect(parts.title).toBe("Library opens later");
    expect(texts(body.querySelectorAll(".news-text p"))).toEqual(DETAIL.text);
    expect(body.querySelector(".news-text p").getAttribute("dir")).toBe("auto");
    expect(texts(body.querySelectorAll(".news-section .overline"))).toEqual(["Dateien", "Bilder", "Links"]);
    expect(body.querySelector(".news-text").classList.contains("body-html")).toBe(true);
    const attachments = [...body.querySelectorAll(".rows button.row")];
    expect(texts(attachments.map((row) => row.querySelector(".row-title")))).toEqual(["Opening hours", "Front door"]);
    expect(texts(body.querySelectorAll(".news-link .row-title"))).toEqual(["https://example.org/library", "Bad"]);
    expect(body.querySelectorAll("[href], [target]").length).toBe(0);
    expect(body.querySelector(".note")).toBeNull();
    expect(parts.foot).toBeNull();
  });

  test("a news attachment is fetched through Ranzenpost by item, kind and position", () => {
    const { window } = loadApp();
    seed(window);
    const files = evalWith(window, `(() => {
      const captured = [];
      const original = attachmentRows;
      attachmentRows = (list) => { captured.push(...list); return original(list); };
      newsDetailParts(Object.assign({}, testArgs[0], { detail: testArgs[1] }));
      attachmentRows = original;
      return captured;
    })()`, NEWS[0], DETAIL);
    expect(files).toEqual([
      { filename: "Opening hours", url: "api/news/file?connection=a1b2c3d4&item=general%2F2&kind=files&index=0" },
      { filename: "Front door", url: "api/news/file?connection=a1b2c3d4&item=general%2F2&kind=images&index=0" },
    ]);
  });

  test("without a read text the sheet shows the summary and says the full text is not read yet", () => {
    const { window } = loadApp();
    seed(window);
    for (const detail of [null, { unreadable: true }]) {
      const parts = evalWith(window, "newsDetailParts(Object.assign({}, testArgs[0], { detail: testArgs[1] }))", NEWS[0], detail);
      const body = window.document.createElement("div");
      body.append(...parts.body.filter(Boolean));
      expect(texts(body.querySelectorAll(".news-text p"))).toEqual(["From Monday at nine."]);
      expect(body.querySelector(".note").textContent).toBe("Den vollständigen Text hat Ranzenpost noch nicht gelesen.");
    }
  });

  test("a row and its overview entry open the sheet", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    window.eval("newsView()").querySelector(".news-row").click();
    expect(window.eval("!!state.sheet || !!state.detail")).toBe(true);
  });
});

const ARCHIVED = { id: "general/1", title: "Book fair", date: "2026-03-01", date_text: "", category: "General", category_slug: "general", summary: "Old news.", path: "/iserv/news/general/1", section: "archive", connection_id: "a1b2c3d4" };
const PACKAGE = { id: "iserv/5", title: "New calendar features", date: "2026-10-01", date_text: "", category: "", category_slug: "iserv", summary: "", path: "/iserv/news/iserv/5", section: "packages", connection_id: "a1b2c3d4" };

describe("news can be filtered and searched like in IServ", () => {
  test("the filter offers the sections the school links and every category of the current news", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    evalWith(window, "state.news.schools = [{ connection_id: 'a1b2c3d4', school: 'Riverside', last_success: 1, sections: ['archive', 'packages'] }];");
    const view = window.eval("newsView()");
    expect(texts(view.querySelectorAll(".news-row .row-title"))).toEqual(["Library opens later", "Sports day"]);
    expect(view.querySelector(".news-filter .chip-label").textContent).toBe("Aktuelle News");
    expect(window.eval("newsFilterOptions(currentNews()).map((option) => option.value)")).toEqual([
      "section:archive", "section:packages", "category:general", "category:sport",
    ]);
    window.eval("state.newsFilter = 'category:general'");
    const general = window.eval("newsView()");
    expect(texts(general.querySelectorAll(".news-row .row-title"))).toEqual(["Library opens later"]);
    expect(general.querySelector(".news-filter .chip-label").getAttribute("dir")).toBe("auto");
    expect(window.eval("newsChapter('normal').count")).toBe(2);
  });

  test("archive and package news load only when their filter is chosen and never reach the overview", async () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    evalWith(window, "state.news.schools = [{ connection_id: 'a1b2c3d4', school: 'Riverside', last_success: 1, sections: ['archive'] }];");
    const asked = [];
    window.fetch = (url) => {
      if (String(url).includes("/api/news/section")) asked.push(String(url));
      const body = String(url).includes("section/detail") ? { text: ["Old text."], files: [], images: [], links: [] } : { news: [ARCHIVED], section: "archive", unavailable: [] };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    };
    window.eval("newsView()");
    expect(asked).toEqual([]);
    window.eval("newsView()").querySelector(".news-filter").click();
    [...window.eval("state.sheet()").querySelectorAll(".news-filter-opt")].find((option) => option.textContent.startsWith("Archiv")).click();
    expect(asked).toEqual(["http://localhost/api/news/section?section=archive"]);
    expect(window.eval("newsView()").querySelector(".loading")).not.toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const archived = window.eval("newsView()");
    expect(texts(archived.querySelectorAll(".news-row .row-title"))).toEqual(["Book fair"]);
    expect(texts(archived.querySelectorAll(".news-row .tag"))).toEqual(["Archiv"]);
    window.eval("newsView()");
    expect(asked.length).toBe(1);
    expect(window.eval("newsChapter('normal').count")).toBe(2);
    archived.querySelector(".news-row").click();
    expect(asked[1]).toBe("http://localhost/api/news/section/detail?connection=a1b2c3d4&section=archive&item=general%2F1");
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
    const files = evalWith(window, "newsFileRows(testArgs[0], 'files', [{ label: 'A', path: '/iserv/a.pdf' }])", ARCHIVED);
    expect(files.querySelector("button")).not.toBeNull();
  });

  test("no current news still says so while the archive stays reachable through the filter", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], []);
    evalWith(window, "state.news.schools = [{ connection_id: 'a1b2c3d4', school: 'Riverside', last_success: 1, sections: ['archive'] }];");
    const view = window.eval("newsView()");
    expect(view.querySelector(".empty b").textContent).toBe("Keine News");
    expect(view.querySelector(".news-filter")).not.toBeNull();
  });

  test("the filter sheet sets the choice and an unknown choice falls back to current news", () => {
    const { window } = loadApp();
    seed(window);
    setLists(window, [], NEWS);
    evalWith(window, "state.news.schools = [{ connection_id: 'a1b2c3d4', school: 'Riverside', last_success: 1, sections: ['archive'] }];");
    window.fetch = () => new Promise(() => {});
    window.eval("newsView()").querySelector(".news-filter").click();
    const options = [...window.eval("state.sheet()").querySelectorAll(".news-filter-opt")];
    expect(texts(options.map((option) => option.querySelector("b")))).toEqual(["Aktuelle News", "Archiv", "General", "sport"]);
    options[1].click();
    expect(window.eval("state.newsFilter")).toBe("section:archive");
    window.eval("state.newsFilter = 'category:gone'");
    window.eval("newsView()");
    expect(window.eval("state.newsFilter")).toBe("");
  });

  test("the search looks through title, summary, category and the read text", () => {
    const { window } = loadApp();
    seed(window);
    const withText = Object.assign({}, NEWS[1], { detail: { text: ["Bring running shoes."], files: [], images: [], links: [] } });
    setLists(window, [], [NEWS[0], withText]);
    const view = window.eval("newsView()");
    const input = view.querySelector(".search-input");
    input.value = "SHOES";
    input.dispatchEvent(new window.Event("input"));
    expect(texts(view.querySelectorAll(".news-row .row-title"))).toEqual(["Sports day"]);
    expect(view.querySelector(".search-hits").textContent).toBe("1 Treffer");
    input.value = "nothing like this";
    input.dispatchEvent(new window.Event("input"));
    expect(view.querySelector(".empty b").textContent).toBe("Keine Treffer");
  });
});
