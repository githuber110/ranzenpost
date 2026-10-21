import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const SCHOOL_ID = "a1b2c3d4";
const SCHOOLS = [{ connection_id: SCHOOL_ID, school: "Riverside", last_success: 1 }];

function forum(id, title, category, unread, extra = {}) {
  return {
    id, title, description: "", category, unread, last_post: "Pausen · heute 09:40", last_post_date: "",
    path: `/iserv/forum/${id}`, extra: [{ label: "Themen", value: "4" }], connection_id: SCHOOL_ID, ...extra,
  };
}

const FORUMS = [
  forum("4101", "Schulhof", "Allgemeine Foren", 3, { description: "Fragen und Antworten" }),
  forum("4102", "Bibliothek", "Allgemeine Foren", 0),
  forum("4103", "Klasse 7b", "Gruppenforen", 12),
];

const FILTERS = [
  { value: "visible", label: "Sichtbare", default: true },
  { value: "hidden", label: "Ausgeblendete", default: false },
];

function text(id, title, owner, changed, tags, filters) {
  return { id, title, owner, changed, changed_text: "", created: "", created_text: "", tags, path: `/iserv/etherpad/${id}`, filters, connection_id: SCHOOL_ID };
}

const TEXTS = [
  text("p1", "Protokoll Klassenrat", "Kim Muster", "2026-10-07T10:15", ["Klasse 7b"], ["visible"]),
  text("p2", "Ideen Schulfest", "Förderverein", "2026-10-09T08:00", ["Fest"], ["visible"]),
  text("p3", "Alte Leseliste", "Bibliothek", "2026-08-01T08:00", [], ["hidden"]),
];

const SCREENS = [
  { id: "1201", title: "Eingangshalle", path: "/iserv/infodisplay/show/1201", connection_id: SCHOOL_ID },
  { id: "1202", title: "Mensa", path: "/iserv/infodisplay/show/1202", connection_id: SCHOOL_ID },
];

function board(id, title, owner, created, changed) {
  return { id, title, owner, created, created_text: "", changed, changed_text: "", path: `/iserv/excalidraw/${id}`, connection_id: SCHOOL_ID };
}

const BOARDS = [
  board("b1", "Klassenfahrt", "Schülerrat", "2026-09-20T08:30", ""),
  board("b2", "Bruchrechnen", "Kim Muster", "2026-10-01T08:30", "2026-10-20T16:45"),
];

function seed(window) {
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.me = { forename: "Sam" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.modules = applyModules({ modules: { forums: true, texts: true, infodisplay: true, whiteboards: true } });
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.forums = { forums: testArgs[0], schools: [Object.assign({}, testArgs[3][0], { mark_read: true })], unavailable: [] };
    state.texts = { texts: testArgs[1], schools: [Object.assign({}, testArgs[3][0], { filters: testArgs[4] })], unavailable: [] };
    state.infodisplay = { infodisplay: testArgs[2], schools: testArgs[3], unavailable: [] };
    state.whiteboards = { whiteboards: testArgs[5], schools: testArgs[3], unavailable: [] };
  `, FORUMS, TEXTS, SCREENS, SCHOOLS, FILTERS, BOARDS);
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

function answer(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body), headers: { get: () => "" } });
}

async function settle() {
  for (let round = 0; round < 4; round += 1) await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("forums, texts and info screens are confirmed-only account modules", () => {
  test("they stay off until the registry confirms them and then join the navigation", () => {
    const { window } = loadApp();
    expect(window.eval("defaultModules().available.forums")).toBe(false);
    expect(window.eval("defaultModules().available.texts")).toBe(false);
    expect(window.eval("defaultModules().available.infodisplay")).toBe(false);
    expect(window.eval("defaultModules().available.whiteboards")).toBe(false);
    seed(window);
    expect(window.eval("visibleViews().map((item) => item.key)")).toEqual(expect.arrayContaining(["forums", "texts", "infodisplay", "whiteboards"]));
    evalWith(window, "state.modules = applyModules({ modules: {} });");
    expect(window.eval("visibleViews().map((item) => item.key)")).not.toContain("forums");
    expect(window.eval("forumsChapter('normal')")).toBeNull();
    expect(window.eval("textsChapter('normal')")).toBeNull();
    expect(window.eval("infodisplayChapter('normal')")).toBeNull();
    expect(window.eval("whiteboardsChapter('normal')")).toBeNull();
  });
});

describe("the forum list", () => {
  test("groups forums by section, shows unread counts and links nowhere outside the app", () => {
    const { window } = loadApp();
    seed(window);
    const view = window.eval("forumsView()");
    expect(texts(view.querySelectorAll(".list-section > .section-head .overline"))).toEqual(["Allgemeine Foren", "Gruppenforen"]);
    expect(texts(view.querySelectorAll(".forum-row .row-title"))).toEqual(["Schulhof", "Bibliothek", "Klasse 7b"]);
    expect(texts(view.querySelectorAll(".forum-row .forum-unread"))).toEqual(["3 neu", "12 neu"]);
    expect(view.querySelector(".forum-row .row-sub").textContent).toBe("Fragen und Antworten\nThemen: 4 · Letzter Beitrag: Pausen · heute 09:40");
    expect([...view.querySelectorAll(".forum-row")].map((row) => row.classList.contains("read"))).toEqual([false, true, false]);
    expect(view.querySelector(".forums-head .overline").textContent).toBe("15 ungelesen");
    expect(view.querySelector(".forum-read").textContent).toBe("Alle als gelesen");
    expect(view.querySelector(".forum-row .row-title").getAttribute("dir")).toBe("auto");
    expect(view.querySelector("a[href*='/iserv/']")).toBeNull();
  });

  test("without unread posts there is no mark-read button and the overview leaves the block out", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.forums.forums.forEach((entry) => { entry.unread = 0; });");
    expect(window.eval("forumsView()").querySelector(".forum-read")).toBeNull();
    expect(window.eval("forumsView()").querySelector(".forums-head .overline").textContent).toBe("3 Foren");
    expect(window.eval("forumsChapter('normal')")).toBeNull();
  });

  test("the overview shows only forums with unread posts", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = window.eval("forumsChapter('normal')");
    expect(chapter.count).toBe(2);
    expect(texts(chapter.blocks.map((block) => block.node).filter((node) => node.querySelector(".row-meta")).map((node) => node.querySelector(".row-title")))).toEqual(["Schulhof", "Klasse 7b"]);
  });

  test("an unknown count stays without a number and a failed list says so", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.forums.forums[0].unread = null;");
    expect(texts(window.eval("forumsView()").querySelectorAll(".forum-unread"))).toEqual(["12 neu"]);
    evalWith(window, "state.forums = { error: 'network' };");
    expect(window.eval("forumsView()").querySelector(".empty b").textContent).toBe("Nicht erreichbar");
    evalWith(window, "state.forums = { forums: [], schools: [], unavailable: [] };");
    expect(window.eval("forumsView()").querySelector(".empty b").textContent).toBe("Keine Foren");
  });

  test("marking everything read asks first, sends nothing on cancel and reloads the list after the confirmation", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    window.fetch = (url, options = {}) => {
      if (String(url).includes("api/forums")) calls.push({ url: String(url), method: options.method || "GET", body: options.body });
      if (String(url).includes("api/forums/read")) return answer({ ok: true, message_key: "api.forums.read.done", outcome: "done" });
      if (String(url).includes("api/forums")) return answer({ forums: [], schools: SCHOOLS, unavailable: [] });
      return new Promise(() => {});
    };
    window.eval("state.view = 'forums'; render();");
    window.document.querySelector(".forum-read").click();
    expect(window.document.querySelector(".scrim .sheet-title").textContent).toBe("Alles als gelesen markieren?");
    expect(window.document.querySelector(".scrim .dlg-text").textContent).toBe("IServ markiert dann alle Beiträge in allen Foren als gelesen. Das lässt sich nicht zurücknehmen.");
    window.document.querySelector(".scrim .btn.ghost").click();
    await settle();
    expect(calls).toEqual([]);
    window.document.querySelector(".forum-read").click();
    window.document.querySelector(".scrim .btn:not(.ghost)").click();
    await settle();
    expect(calls[0].url).toBe("http://localhost/api/forums/read");
    expect(JSON.parse(calls[0].body)).toEqual({ connection_id: SCHOOL_ID, confirmed: true });
    expect(calls[1].url).toBe("http://localhost/api/forums");
  });
});

describe("marking forums read when the outcome is open", () => {
  test("the button is hidden where IServ offers no mark-read form or the app does not know", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.forums.schools[0].mark_read = false;");
    expect(window.eval("forumsView()").querySelector(".forum-read")).toBeNull();
    evalWith(window, "delete state.forums.schools[0].mark_read;");
    expect(window.eval("forumsView()").querySelector(".forum-read")).toBeNull();
  });

  test("the request may take as long as the school needs to send and read again", () => {
    const { window } = loadApp();
    expect(window.eval("FORUM_READ_TIMEOUT_MS")).toBeGreaterThanOrEqual(180000);
  });

  test("a lost answer says the outcome is open instead of failed and reads the forums again", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    window.fetch = (url, options = {}) => {
      if (!String(url).includes("api/forums")) return new Promise(() => {});
      calls.push(String(url));
      if (String(url).includes("api/forums/read")) return Promise.reject(new TypeError("Failed to fetch"));
      return answer({ forums: [], schools: SCHOOLS, unavailable: [] });
    };
    window.eval("state.view = 'forums'; render();");
    window.document.querySelector(".forum-read").click();
    window.document.querySelector(".scrim .btn:not(.ghost)").click();
    await settle();
    expect(window.eval("state.toast && state.toast.message")).toBe(window.t("api.forums.read.uncertain"));
    expect(calls).toEqual(["http://localhost/api/forums/read", "http://localhost/api/forums"]);
  });
});

describe("a list Ranzenpost cannot read yet", () => {
  test("shows a calm note with the problem report hint, not an error, and leaves the overview block out", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, `
      state.forums = { forums: [], schools: [], unavailable: [testArgs[0]], unreadable: [testArgs[0]] };
      state.texts = { texts: [], schools: [], unavailable: [testArgs[0]], unreadable: [testArgs[0]] };
      state.infodisplay = { infodisplay: [], schools: [], unavailable: [testArgs[0]], unreadable: [testArgs[0]] };
      state.whiteboards = { whiteboards: [], schools: [], unavailable: [testArgs[0]], unreadable: [testArgs[0]] };
    `, SCHOOL_ID);
    for (const name of ["forumsView", "textsView", "infodisplayView", "whiteboardsView"]) {
      const view = window.eval(`${name}()`);
      expect(view.querySelector(".empty b").textContent).toBe(window.t("accountLists.unreadable.title"));
      expect(view.querySelector(".empty p").textContent).toBe(window.t("accountLists.unreadable.text"));
      expect(view.querySelector(".empty b").textContent).not.toBe("Nicht erreichbar");
    }
    expect(window.eval("forumsChapter('normal')")).toBeNull();
    expect(window.eval("textsChapter('normal')")).toBeNull();
    expect(window.eval("infodisplayChapter('normal')")).toBeNull();
    expect(window.eval("whiteboardsChapter('normal')")).toBeNull();
  });

  test("an unreachable school still shows the error", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.forums = { forums: [], schools: [], unavailable: [testArgs[0]], unreadable: [] };", SCHOOL_ID);
    expect(window.eval("forumsView()").querySelector(".empty b").textContent).toBe("Nicht erreichbar");
  });
});

describe("the text list", () => {
  test("shows the selection IServ shows first, newest change first, with owner and tags", () => {
    const { window } = loadApp();
    seed(window);
    const view = window.eval("textsView()");
    expect(texts(view.querySelectorAll(".text-row .row-title"))).toEqual(["Ideen Schulfest", "Protokoll Klassenrat"]);
    expect(view.querySelector(".text-row .row-sub").textContent).toContain("Förderverein · Geändert");
    expect(texts(view.querySelectorAll(".text-row .tag"))).toEqual(["Fest", "Klasse 7b"]);
    expect(view.querySelector("a[href*='/iserv/']")).toBeNull();
  });

  test("the filter sheet offers the IServ selections and the tags, hidden texts appear with their selection", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("textsView()").querySelector(".texts-filter").click();
    const options = [...window.eval("state.sheet()").querySelectorAll(".texts-filter-opt")];
    expect(texts(options.map((option) => option.querySelector("b")))).toEqual(["Sichtbare Texte", "Sichtbare", "Ausgeblendete", "Fest", "Klasse 7b"]);
    options[2].click();
    expect(window.eval("state.textsFilter")).toBe("filter:hidden");
    expect(texts(window.eval("textsView()").querySelectorAll(".text-row .row-title"))).toEqual(["Alte Leseliste"]);
    window.eval("state.textsFilter = 'tag:Fest'");
    expect(texts(window.eval("textsView()").querySelectorAll(".text-row .row-title"))).toEqual(["Ideen Schulfest"]);
    window.eval("state.textsFilter = 'filter:gone'");
    window.eval("textsView()");
    expect(window.eval("state.textsFilter")).toBe("");
  });

  test("the search reads title, owner and tags", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("state.textsSearch = 'muster'");
    const view = window.eval("textsView()");
    expect(texts(view.querySelectorAll(".text-row .row-title"))).toEqual(["Protokoll Klassenrat"]);
    expect(view.querySelector(".search-hits").textContent).toBe("1 Treffer");
  });

  test("the overview lists the selection IServ shows first", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("textsChapter('normal').count")).toBe(2);
  });
});

describe("the info screen list", () => {
  test("lists every screen by name and says when there is none", () => {
    const { window } = loadApp();
    seed(window);
    expect(texts(window.eval("infodisplayView()").querySelectorAll(".screen-row .row-title"))).toEqual(["Eingangshalle", "Mensa"]);
    expect(window.eval("infodisplayChapter('normal').count")).toBe(2);
    evalWith(window, "state.infodisplay = { infodisplay: [], schools: [], unavailable: [] };");
    expect(window.eval("infodisplayView()").querySelector(".empty b").textContent).toBe("Keine Infobildschirme");
  });
});

describe("the whiteboard list", () => {
  test("lists every whiteboard newest change first with owner and both dates and links nowhere", () => {
    const { window } = loadApp();
    seed(window);
    const view = window.eval("whiteboardsView()");
    expect(texts(view.querySelectorAll(".whiteboard-row .row-title"))).toEqual(["Bruchrechnen", "Klassenfahrt"]);
    const subs = texts(view.querySelectorAll(".whiteboard-row .row-sub"));
    expect(subs[0]).toMatch(/^Kim Muster · Erstellt .+ · Geändert .+$/);
    expect(subs[1]).toMatch(/^Schülerrat · Erstellt [^·]+$/);
    expect(subs[0]).toContain(window.eval("listMoment('2026-10-20T16:45', '')"));
    expect(view.querySelector("[href], [target]")).toBeNull();
    expect(view.querySelector(".whiteboard-row button")).toBeNull();
  });

  test("feeds the overview chapter and says when there is none, unknown stays an error", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("whiteboardsChapter('normal').count")).toBe(2);
    evalWith(window, "state.whiteboards = { whiteboards: [], schools: [], unavailable: [] };");
    expect(window.eval("whiteboardsView()").querySelector(".empty b").textContent).toBe("Keine Tafeln");
    expect(window.eval("whiteboardsChapter('normal')")).toBeNull();
    evalWith(window, "state.whiteboards = { whiteboards: [], schools: [], unavailable: [testArgs[0]], unreadable: [] };", SCHOOL_ID);
    expect(window.eval("whiteboardsView()").querySelector(".empty b").textContent).toBe("Nicht erreichbar");
  });

  test("an untitled whiteboard gets a name in every language", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "state.whiteboards = { whiteboards: [Object.assign({}, testArgs[0], { title: '' })], schools: [], unavailable: [] };", BOARDS[0]);
    expect(window.eval("whiteboardsView()").querySelector(".row-title").textContent).toBe("Tafel ohne Titel");
  });
});
