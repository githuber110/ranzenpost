import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const SCHOOL = "a1b2c3d4";
const OWN = {
  path: "/iserv/file/-/Files",
  root: "own",
  entries: [
    { name: "Projekte", kind: "folder", path: "/iserv/file/-/Files/Projekte", size_text: "", type_text: "Ordner", modified: "2026-10-01T10:00", modified_text: "" },
    { name: "Lesetagebuch.pdf", kind: "file", path: "/iserv/file/-/Files/Lesetagebuch.pdf", size_text: "120 KB", type_text: "PDF-Dokument", modified: "2026-10-12T08:30", modified_text: "" },
  ],
  crumbs: [],
  location: "/Files",
  query: "",
  can_search: true,
  can_upload: true,
  upload_multiple: true,
  upload_accept: "",
};
const INNER = Object.assign({}, OWN, {
  path: "/iserv/file/-/Files/Projekte",
  entries: [{ name: "Plakat.png", kind: "file", path: "/iserv/file/-/Files/Projekte/Plakat.png", size_text: "340 KB", type_text: "PNG-Bild", modified: "", modified_text: "" }],
});
const PEOPLE = [{ name: "Anna Behrens", address: "anna.behrens@school.example", class_name: "3b", extra: [], path: "", book: "" }];
const LISTS = {
  lists: [{ id: "41", title: "Elternrat 3b", extra: [{ label: "Adressen", value: "2" }], has_detail: true, deletable: true }],
  labels: ["", "Titel", "Adressen"],
  can_import: true,
  import_fields: [{ name: "form[list][title]", label: "Titel", required: false, maxlength: "" }],
  import_accept: "",
  can_delete: true,
};

function response(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function router(window, answers) {
  const asked = [];
  window.fetch = (input, options) => {
    const url = String(input);
    const method = (options && options.method) || "GET";
    let body = options && options.body;
    let files = [];
    if (body && typeof body === "string") body = JSON.parse(body);
    else if (body && typeof body.get === "function") {
      files = body.getAll("files").map((file) => file.name);
      body = JSON.parse(body.get("data"));
    }
    asked.push({ url, method, body, files });
    if (url.endsWith("api/account-modules")) return response({ schools: [{ connection_id: SCHOOL, school: "Riverside", file: true, addressbook: true, mailinglist: true }] });
    if (url.endsWith("api/mail")) return response({ schools: [{ connection_id: SCHOOL, school: "Riverside", unread: 0 }] });
    for (const [pattern, answer] of answers) {
      if (url.includes(pattern)) return response(typeof answer === "function" ? answer(body, url) : answer);
    }
    return response({});
  };
  return asked;
}

function seed(window, extra = "") {
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.me = { forename: "Sam" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {}, connections: [{ id: "a1b2c3d4", label: "Riverside", setup_complete: true }] };
    state.modules = applyModules({ modules: {} });
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.messengerRooms = { rooms: [], can_write_to_teacher: false };
    state.holidays = {};
    state.detached = false;
    state.mail = [{ connection_id: "a1b2c3d4", school: "Riverside", unread: 0 }];
    state.accountModules = [{ connection_id: "a1b2c3d4", school: "Riverside", file: true, addressbook: true, mailinglist: true }];
    ${extra}
  `);
}

async function settle(window, rounds = 8) {
  for (let index = 0; index < rounds; index += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function openArea(window, view, answers) {
  const asked = router(window, answers);
  await settle(window, 12);
  seed(window);
  window.eval(`setView("${view}")`);
  await settle(window);
  window.eval("render()");
  return asked;
}

function app(window) {
  return window.document.querySelector("#app");
}

function sheetButton(window, text) {
  return [...window.document.querySelectorAll(".sheet button")].find((button) => button.textContent.includes(text));
}

function noHandOff(node) {
  for (const link of node.querySelectorAll("a")) {
    expect(link.getAttribute("href") || "").not.toContain("/iserv/");
    expect(link.getAttribute("target")).toBeNull();
  }
}

describe("the account areas are offered by the schools that list them", () => {
  test("files and contacts show up only for a school that lists the module", () => {
    const { window } = loadApp();
    router(window, []);
    seed(window);
    expect(window.eval("navigationAreas()")).toEqual(expect.arrayContaining(["files", "contacts"]));
    evalWith(window, "state.accountModules = [{ connection_id: 'a1b2c3d4', file: false, addressbook: false, mailinglist: true }]");
    expect(window.eval("navigationAreas()")).not.toContain("files");
    expect(window.eval("navigationAreas()")).toContain("contacts");
    evalWith(window, "state.accountModules = []");
    expect(window.eval("navigationAreas()")).not.toContain("contacts");
  });
});

describe("an account whose areas all come from outside the standard modules", () => {
  const ALL_OFF = "{ modules: { timetable: false, letters: false, pinboard: false, absences: false, conferences: false, messenger: false, calendar: false, tasks: false, news: false } }";

  test("files and mail alone open the app instead of the no-modules page", () => {
    const { window } = loadApp();
    router(window, []);
    seed(window, `state.modules = applyModules(${ALL_OFF}); state.accountModules = [{ connection_id: "a1b2c3d4", file: true, addressbook: false, mailinglist: false }];`);
    expect(window.eval("anyModuleOn()")).toBe(true);
    expect(window.eval("navigationAreas()")).toEqual(["mail", "files"]);
    window.eval('setView("files"); render()');
    expect(window.eval("state.view")).toBe("files");
    expect(app(window).querySelector(".modules-empty")).toBeNull();
    expect(app(window).querySelector(".tabbar")).not.toBeNull();
  });

  test("without any offered area the no-modules page stays", () => {
    const { window } = loadApp();
    router(window, []);
    seed(window, `state.modules = applyModules(${ALL_OFF}); state.accountModules = []; state.mail = [];`);
    expect(window.eval("anyModuleOn()")).toBe(false);
    window.eval("render()");
    expect(app(window).querySelector(".modules-empty")).not.toBeNull();
  });
});

describe("the files area", () => {
  test("lists folders and files, opens a folder in the app and goes back", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "files", [["api/files?", (body, url) => (url.includes("Projekte") ? INNER : OWN)]]);
    await settle(window);
    window.eval("render()");
    const rows = [...app(window).querySelectorAll(".files-rows .row-title")].map((node) => node.textContent);
    expect(rows).toEqual(["Projekte", "Lesetagebuch.pdf"]);
    noHandOff(app(window));
    const first = asked.find((entry) => entry.url.includes("api/files?"));
    expect(first.url).toContain("connection=a1b2c3d4");
    app(window).querySelector(".files-folder").click();
    await settle(window);
    window.eval("render()");
    const inner = asked.filter((entry) => entry.url.includes("api/files?")).pop();
    expect(decodeURIComponent(inner.url)).toContain("path=/iserv/file/-/Files/Projekte");
    expect([...app(window).querySelectorAll(".files-rows .row-title")].map((node) => node.textContent)).toEqual(["Plakat.png"]);
    expect(window.eval("filesHeader().onBack")).toBeTruthy();
    window.eval("filesHeader().onBack()");
    await settle(window);
    expect(window.eval("filesPath()")).toBe("own");
  });

  test("a file opens through the app's own file route", async () => {
    const { window } = loadApp();
    await openArea(window, "files", [["api/files?", OWN]]);
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".files-file").click();
    const open = sheetButton(window, window.eval("t('attachment.action.open')"));
    expect(open).toBeTruthy();
    expect(evalWith(window, "filesFileRow(testArgs[0], 'a1b2c3d4')", OWN.entries[1]).outerHTML).not.toContain("/iserv/");
  });

  test("an upload needs the preview step and sends the confirmation with the folder", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "files", [
      ["api/files?", OWN],
      ["api/files/upload", { ok: true, message_key: "api.files.upload.done", outcome: "done", listing: Object.assign({}, OWN, { entries: OWN.entries.concat([{ name: "Brief.pdf", kind: "file", path: "/iserv/file/-/Files/Brief.pdf" }]) }) }],
    ]);
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".files-upload").click();
    evalWith(window, "state.filesUpload.files = [new File(['hi'], 'Brief.pdf', { type: 'application/pdf' })]; rerender()");
    expect(asked.some((entry) => entry.url.includes("api/files/upload"))).toBe(false);
    window.document.querySelector(".files-upload-next").click();
    expect(window.document.querySelector(".sheet").textContent).toContain("Brief.pdf");
    window.document.querySelector(".files-upload-send").click();
    await settle(window);
    const sent = asked.find((entry) => entry.url.includes("api/files/upload"));
    expect(sent.body).toEqual({ connection_id: SCHOOL, path: "own", confirmed: true });
    expect(sent.files).toEqual(["Brief.pdf"]);
    window.eval("render()");
    expect([...app(window).querySelectorAll(".files-rows .row-title")].map((node) => node.textContent)).toContain("Brief.pdf");
  });

  test("the search runs in the folder first and in all folders on request", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "files", [["api/files/search", Object.assign({}, INNER, { query: "plakat" })], ["api/files?", OWN]]);
    await settle(window);
    window.eval("render()");
    const input = app(window).querySelector(".search-input");
    input.value = "plakat";
    input.dispatchEvent(new window.Event("input"));
    expect(app(window).querySelector(".files-search-all").hidden).toBe(false);
    app(window).querySelector(".files-search-all").click();
    await settle(window);
    const search = asked.find((entry) => entry.url.includes("api/files/search"));
    expect(search.url).toContain("q=plakat");
    expect(search.url).toContain("connection=a1b2c3d4");
  });
});

describe("the contacts area", () => {
  test("searches the address book on demand and writes a mail from a person", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "contacts", [
      ["api/addressbook/search", { people: PEOPLE, query: "beh" }],
      ["api/mail/compose", { mode: "new", senders: [{ name: "Sam", address: "sam@school.example" }] }],
    ]);
    const input = app(window).querySelector(".search-input");
    input.value = "beh";
    input.dispatchEvent(new window.Event("input"));
    await new Promise((resolve) => window.setTimeout(resolve, 450));
    await settle(window);
    window.eval("render()");
    const search = asked.find((entry) => entry.url.includes("api/addressbook/search"));
    expect(search.url).toContain("q=beh");
    expect(search.url).toContain("connection=a1b2c3d4");
    const row = app(window).querySelector(".contact-person");
    expect(row.textContent).toContain("Anna Behrens");
    row.click();
    window.document.querySelector(".contact-write").click();
    await settle(window, 12);
    expect(window.eval("state.view")).toBe("mail");
    expect(window.eval("state.pageForm.to")).toBe("Anna Behrens <anna.behrens@school.example>");
  });

  test("a mailing list shows its addresses and is deleted only after the confirmation", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "contacts", [
      ["api/mailinglists/detail", { id: "41", title: "Elternrat 3b", addresses: ["a@example.org", "b@example.org"], read: true }],
      ["api/mailinglists/delete", { ok: true, message_key: "api.lists.delete.done", outcome: "done", overview: Object.assign({}, LISTS, { lists: [] }) }],
      ["api/mailinglists", LISTS],
    ]);
    window.eval("setContactsTab('mailinglist')");
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".mailing-list").click();
    await settle(window);
    expect(window.document.querySelector(".sheet .list-addresses").textContent).toContain("b@example.org");
    window.document.querySelector(".list-delete").click();
    await settle(window);
    expect(asked.some((entry) => entry.url.includes("api/mailinglists/delete"))).toBe(false);
    sheetButton(window, window.eval("t('lists.delete.confirm')")).click();
    await settle(window);
    const sent = asked.find((entry) => entry.url.includes("api/mailinglists/delete"));
    expect(sent.body).toEqual({ connection_id: SCHOOL, list_id: "41", confirmed: true });
    window.eval("render()");
    expect(app(window).querySelector(".mailing-list")).toBeNull();
  });

  test("a list import is sent with the file and the typed title after the preview", async () => {
    const { window } = loadApp();
    const asked = await openArea(window, "contacts", [
      ["api/mailinglists/import", { ok: true, message_key: "api.lists.import.done", outcome: "done", overview: LISTS }],
      ["api/mailinglists", LISTS],
    ]);
    window.eval("setContactsTab('mailinglist')");
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".lists-import").click();
    evalWith(window, "state.listImport.file = new File(['a@example.org'], 'Sportfest.txt', { type: 'text/plain' }); state.listImport.values['form[list][title]'] = 'Sportfest'; rerender()");
    window.document.querySelector(".lists-import-next").click();
    window.document.querySelector(".lists-import-send").click();
    await settle(window);
    const sent = asked.find((entry) => entry.url.includes("api/mailinglists/import"));
    expect(sent.body).toEqual({ connection_id: SCHOOL, values: { "form[list][title]": "Sportfest" }, confirmed: true });
    expect(sent.files).toEqual(["Sportfest.txt"]);
  });
});

function timeoutRecorder(window) {
  const seen = [];
  window.AbortSignal.timeout = (ms) => {
    seen.push(ms);
    return undefined;
  };
  return seen;
}

function timeoutError() {
  const failure = new Error("timed out");
  failure.name = "TimeoutError";
  return Promise.reject(failure);
}

describe("a write the browser gives up on", () => {
  test("an upload waits longer than the server and then shows the unclear state without a second send", async () => {
    const { window } = loadApp();
    const seen = timeoutRecorder(window);
    const asked = await openArea(window, "files", [["api/files?", OWN]]);
    const plain = window.fetch;
    window.fetch = (input, options) => (String(input).includes("api/files/upload") ? (asked.push({ url: String(input) }), timeoutError()) : plain(input, options));
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".files-upload").click();
    evalWith(window, "state.filesUpload.files = [new File(['hi'], 'Brief.pdf', { type: 'application/pdf' })]; rerender()");
    window.document.querySelector(".files-upload-next").click();
    const before = asked.filter((entry) => entry.url.includes("api/files?")).length;
    seen.length = 0;
    window.document.querySelector(".files-upload-send").click();
    await settle(window);
    expect(Math.max(...seen)).toBeGreaterThanOrEqual(400000);
    window.eval("rerender()");
    const sheet = window.document.querySelector(".sheet");
    expect(sheet.textContent).toContain(window.eval("t('files.upload.timeout')"));
    expect(window.document.querySelector(".files-upload-send")).toBeNull();
    expect(asked.filter((entry) => entry.url.includes("api/files?")).length).toBeGreaterThan(before);
  });

  test("an import waits longer than the server and then shows the unclear state without a second send", async () => {
    const { window } = loadApp();
    const seen = timeoutRecorder(window);
    const asked = await openArea(window, "contacts", [["api/mailinglists", LISTS]]);
    const plain = window.fetch;
    window.fetch = (input, options) => (String(input).includes("api/mailinglists/import") ? timeoutError() : plain(input, options));
    window.eval("setContactsTab('mailinglist')");
    await settle(window);
    window.eval("render()");
    app(window).querySelector(".lists-import").click();
    evalWith(window, "state.listImport.file = new File(['a@example.org'], 'Chor.txt', { type: 'text/plain' }); rerender()");
    window.document.querySelector(".lists-import-next").click();
    const before = asked.filter((entry) => entry.url.includes("api/mailinglists?")).length;
    seen.length = 0;
    window.document.querySelector(".lists-import-send").click();
    await settle(window);
    expect(Math.max(...seen)).toBeGreaterThanOrEqual(200000);
    window.eval("rerender()");
    expect(window.document.querySelector(".sheet").textContent).toContain(window.eval("t('lists.import.timeout')"));
    expect(window.document.querySelector(".lists-import-send")).toBeNull();
    expect(asked.filter((entry) => entry.url.includes("api/mailinglists?")).length).toBeGreaterThan(before);
  });

  test("a delete waits for both school answers and an abort reads the lists again", async () => {
    const { window } = loadApp();
    const seen = timeoutRecorder(window);
    const asked = await openArea(window, "contacts", [
      ["api/mailinglists/detail", { id: "41", title: "Elternrat 3b", addresses: [], read: true }],
      ["api/mailinglists", LISTS],
    ]);
    const plain = window.fetch;
    window.fetch = (input, options) => (String(input).includes("api/mailinglists/delete") ? timeoutError() : plain(input, options));
    window.eval("setContactsTab('mailinglist')");
    await settle(window);
    window.eval("render()");
    const before = asked.filter((entry) => entry.url.includes("api/mailinglists?")).length;
    window.eval("deleteMailingList(testArgs = { id: '41', title: 'Elternrat 3b' }, 'a1b2c3d4')");
    await settle(window);
    seen.length = 0;
    window.eval("state.sheet()").querySelector(".btn-stack button").click();
    await settle(window);
    expect(Math.max(...seen)).toBeGreaterThanOrEqual(240000);
    expect(window.eval("state.toast && state.toast.message")).toBe(window.eval("t('lists.delete.timeout')"));
    expect(asked.filter((entry) => entry.url.includes("api/mailinglists?")).length).toBeGreaterThan(before);
  });
});
