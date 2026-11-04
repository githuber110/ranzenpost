import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const SCHOOL = "a1b2c3d4";
const NO_MODULES = { connection_id: SCHOOL, file: false, addressbook: false, mailinglist: false, print: false, "course-selection": false, videoconference: false, poll: false, todo: false };

function offered(window, extra) {
  evalWith(window, "state.accountModules = [testArgs[0]]", Object.assign({}, NO_MODULES, extra));
}

function answerWith(window, answers, asked) {
  window.fetch = (input) => {
    const target = String(input);
    if (!target.includes("api/module-pages/page")) return new Promise(() => {});
    asked.push(target);
    const next = answers.shift();
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(next) });
  };
}

function openArea(window) {
  window.eval("state.view = 'modulepages'; state.modulePageStack = [];");
  return window.eval("modulePagesView()");
}

async function openPage(window, slug, answers, asked) {
  answerWith(window, answers, asked);
  evalWith(window, "state.view = 'modulepages'; state.modulePageStack = []; openModulePage(testArgs[0])", { slug, connection_id: SCHOOL, title: "Titel" });
  await settle();
  await settle();
  return window.eval("modulePagesView()");
}

describe("the area for the other modules", () => {
  test("it appears only for a school that lists one of them", () => {
    const { window } = loadApp();
    offered(window, {});
    expect(window.eval("navigationAreas()")).not.toContain("modulepages");
    offered(window, { poll: true });
    expect(window.eval("navigationAreas()")).toContain("modulepages");
  });

  test("it lists exactly the modules the school offers", () => {
    const { window } = loadApp();
    offered(window, { print: true, todo: true });
    const titles = [...openArea(window).querySelectorAll(".row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Drucken", "To-do"]);
  });

  test("every module has a name in the settings", () => {
    const { window } = loadApp();
    for (const name of window.eval("MODULE_PAGE_NAMES")) {
      const key = `settings.modules.name.${name}`;
      expect(evalWith(window, "t(testArgs[0])", key)).not.toBe(key);
    }
  });
});

describe("a page of a module", () => {
  test("a table row shows its cells with their headers and nothing to act on", async () => {
    const { window } = loadApp();
    const page = { module: "print", page: "a".repeat(24), title: "Drucken", notices: [], blocks: [{
      kind: "table",
      caption: "",
      headers: ["Name", "Status"],
      rows: [{ cells: ["Brief.pdf", "Gedruckt"], links: [] }],
    }] };
    const view = await openPage(window, "print", [page], []);
    expect(view.querySelector(".row-title").textContent).toBe("Brief.pdf");
    expect(view.querySelector(".conference-line").textContent).toBe("Status: Gedruckt");
    expect(view.querySelector("button.row")).toBeNull();
    expect(view.querySelector("form, input, select, a[href]")).toBeNull();
    expect(view.textContent).toContain("Ändern geht in dieser Ansicht noch nicht");
  });

  test("a row with a link opens the next page in the same module and the back step returns", async () => {
    const { window } = loadApp();
    const asked = [];
    const list = { module: "course-selection", page: "a".repeat(24), title: "Kurswahlen", notices: [], blocks: [{
      kind: "table",
      caption: "",
      headers: ["Titel"],
      rows: [{ cells: ["Wahlpflicht"], links: [{ label: "Wahlpflicht", page: "b".repeat(24) }] }],
    }] };
    const detail = { module: "course-selection", page: "b".repeat(24), title: "Wahlpflicht", notices: [], blocks: [{ kind: "text", text: "Bitte wählen." }] };
    const view = await openPage(window, "course-selection", [list, detail], asked);
    view.querySelector("button.row").click();
    await settle();
    await settle();
    expect(asked[1]).toContain(`page=${"b".repeat(24)}`);
    expect(asked[1]).toContain(`connection=${SCHOOL}`);
    expect(asked[1]).toContain("module=course-selection");
    expect(window.eval("modulePagesHeader().text")).toBe("Wahlpflicht");
    expect(window.eval("modulePagesView()").textContent).toContain("Bitte wählen.");
    window.eval("leaveModulePage()");
    expect(window.eval("modulePagesHeader().text")).toBe("Kurswahlen");
  });

  test("open and done to-dos are apart and a due date is shown", async () => {
    const { window } = loadApp();
    const page = { module: "todo", page: "", title: "", notices: [], blocks: [{
      kind: "tasks",
      open: [{ id: "t1", summary: "Sportzeug", description: "Für Freitag", date: "2026-11-20", time: "12:00" }],
      done: [{ id: "t2", summary: "Buch", description: "", date: "", time: "" }],
    }] };
    const view = await openPage(window, "todo", [page], []);
    const titles = [...view.querySelectorAll(".row-title")].map((node) => node.textContent);
    expect(titles).toEqual(["Sportzeug", "Buch"]);
    expect(view.querySelector(".conference-line").textContent).toContain("20.11.");
    expect(view.querySelector(".conference-line").textContent).toContain("12:00");
    expect(view.textContent).toContain("Erledigt");
  });

  test("an empty to-do list says so and a page without content is a failure", async () => {
    const { window } = loadApp();
    const todo = { module: "todo", page: "", title: "", notices: [], blocks: [{ kind: "tasks", open: [], done: [] }] };
    expect((await openPage(window, "todo", [todo], [])).querySelector(".empty b").textContent).toBe("Keine To-dos");
    const blank = { module: "poll", page: "a".repeat(24), title: "Umfragen", notices: [], blocks: [] };
    const failed = await openPage(window, "poll", [blank], []);
    expect(failed.querySelector(".empty b").textContent).toBe("Seite nicht geladen");
    expect(failed.textContent).toContain("noch nicht lesen");
  });

  test("a page with hidden inputs says so", async () => {
    const { window } = loadApp();
    const page = { module: "poll", page: "a".repeat(24), title: "Wahl", notices: [], hidden_forms: 1, blocks: [] };
    const view = await openPage(window, "poll", [page], []);
    expect(view.querySelector(".empty")).toBeNull();
    expect(view.textContent).toContain("Eingaben, die die App noch nicht zeigt");
    const table = { kind: "table", caption: "", headers: ["Titel"], rows: [] };
    const empty = await openPage(window, "poll", [Object.assign({}, page, { blocks: [table] })], []);
    expect(empty.textContent).not.toContain("Keine Einträge");
  });

  test("a failed refresh keeps what was already read", async () => {
    const { window } = loadApp();
    const asked = [];
    const page = { module: "poll", page: "a".repeat(24), title: "Umfragen", notices: [], blocks: [{ kind: "text", text: "Keine Umfragen" }] };
    await openPage(window, "poll", [page, new Error("down")], asked);
    window.eval("refreshModulePage()");
    await settle();
    await settle();
    expect(asked.length).toBe(2);
    const refreshed = window.eval("modulePagesView()");
    expect(refreshed.textContent).toContain("Keine Umfragen");
    expect(refreshed.textContent).toContain("ließ sich gerade nicht lesen");
  });

  test("a failure with a reason of the school shows that reason", async () => {
    const { window } = loadApp();
    const refused = Object.assign(new Error("refused"), { body: { message_key: "api.modulePages.refused" } });
    const view = await openPage(window, "print", [refused], []);
    expect(view.textContent).toContain("nicht frei");
  });

  test("a failed read shows an error, not an empty page, and can be retried", async () => {
    const { window } = loadApp();
    const page = { module: "poll", page: "a".repeat(24), title: "Umfragen", notices: [], blocks: [{ kind: "text", text: "Keine Umfragen" }] };
    const answers = [new Error("down"), page];
    const view = await openPage(window, "poll", answers, []);
    expect(view.querySelector(".empty b").textContent).toBe("Seite nicht geladen");
    view.querySelector(".empty button").click();
    await settle();
    await settle();
    expect(window.eval("modulePagesView()").textContent).toContain("Keine Umfragen");
  });
});
