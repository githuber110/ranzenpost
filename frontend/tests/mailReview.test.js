import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const SCHOOL = "a1b2c3d4";
const OTHER = "b2c3d4e5";
const HOSTILE = '<p>Hi <b>there</b></p><img src="x" onerror="window.__pwned=1"><svg onload="window.__pwned=2"></svg><a href="javascript:window.__pwned=3">x</a><a href="https://example.org/">ok</a><!--><img src=y onerror="window.__pwned=4">-->';
const FOLDERS = [{ id: "INBOX", name: "INBOX", path: "INBOX", role: "inbox", unread: 1, total: 2, depth: 0, delimiter: "/" }];
const MESSAGES = [{ uid: "7", folder: "INBOX", subject: "Ausflug", message_id: "<trip-1@school.example>", from: [{ name: "Teacher", address: "t@school.example" }], to: [], cc: [], date: new Date().toISOString(), unread: false, flagged: false, answered: false, has_attachments: false, tags: [] }];
const DETAIL = { uid: "7", folder: "INBOX", subject: "Ausflug", message_id: "<trip-1@school.example>", from: [{ name: "Teacher", address: "t@school.example" }], to: [], cc: [], bcc: [], reply_to: [], date: new Date().toISOString(), unread: false, flagged: false, answered: false, tags: [], receipt_to: [{ name: "Teacher", address: "t@school.example" }], body_html: HOSTILE, body_text: "", attachments: [] };

function response(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function router(window, answers, hold) {
  const asked = [];
  window.fetch = (input, options) => {
    const url = String(input);
    let body = options && options.body;
    if (body && typeof body === "string") body = JSON.parse(body);
    else if (body && typeof body.get === "function") body = JSON.parse(body.get("data"));
    asked.push({ url, method: (options && options.method) || "GET", body });
    if (url.endsWith("api/mail")) return response({ schools: [{ connection_id: SCHOOL, school: "One", unread: 1 }, { connection_id: OTHER, school: "Two", unread: 0 }] });
    if (hold && url.includes(hold.pattern)) return hold.promise.then(() => response(hold.body));
    for (const [pattern, answer] of answers) if (url.includes(pattern)) return response(typeof answer === "function" ? answer(body, url) : answer);
    return response({});
  };
  return asked;
}

async function settle(window, rounds = 12) {
  for (let index = 0; index < rounds; index += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function app(window) {
  return window.document.querySelector("#app");
}

async function start(window, answers, hold) {
  const asked = router(window, answers, hold);
  await settle(window);
  evalWith(window, `
    state.detached = false;
    state.children = []; state.childrenRead = true; state.me = { forename: "Sam" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {}, connections: [{ id: testArgs[0], label: "One", setup_complete: true }, { id: testArgs[1], label: "Two", setup_complete: true }] };
    state.modules = applyModules({ modules: {} });
    state.letters = { letters: [] }; state.pinboard = { folders: [], feed: [] }; state.conferences = { items: [] };
    state.messengerRooms = { rooms: [], can_write_to_teacher: false }; state.holidays = {};
    state.mail = [{ connection_id: testArgs[0], school: "One", unread: 1 }, { connection_id: testArgs[1], school: "Two", unread: 0 }];
    state.mailSchool = testArgs[0];
  `, SCHOOL, OTHER);
  window.eval('setView("mail")');
  await settle(window);
  return asked;
}

const BASE = [
  ["api/mail/account", { account: { page_size: 25, tags: [], flags: {}, auto_archive: [], display_name: "", addresses: [], lookup: false } }],
  ["api/mail/folders", { folders: FOLDERS }],
  ["api/mail/messages", { messages: MESSAGES, total: 1, more: false }],
  ["api/mail/message?", DETAIL],
];

function confirmButton(window) {
  return [...app(window).querySelectorAll(".sheet .btn")].find((button) => !button.classList.contains("ghost"));
}

describe("mail content never runs in the app", () => {
  test("the body is a sandboxed frame and hostile markup never reaches the app document", async () => {
    const { window } = loadApp();
    await start(window, BASE);
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    const frame = app(window).querySelector("iframe.mail-frame");
    const sandbox = frame.getAttribute("sandbox");
    expect(sandbox).not.toContain("allow-scripts");
    expect(sandbox).not.toContain("allow-same-origin");
    expect(app(window).innerHTML).not.toContain("onerror");
    expect(window.__pwned).toBeUndefined();
  });

  test("the safe copy keeps text and plain formatting but no handlers, images or script links", () => {
    const { window } = loadApp();
    const html = evalWith(window, "(() => { const box = document.createElement('div'); box.append(safeMailNodes(testArgs[0])); return box.innerHTML; })()", HOSTILE);
    expect(html).toContain("<b>there</b>");
    expect(html).toContain('href="https://example.org/"');
    expect(html).not.toMatch(/onerror|onload|javascript:|<img|<svg/);
  });

  test("a reopened draft puts no raw mail markup into the editor", async () => {
    const { window } = loadApp();
    const draft = { mode: "draft", senders: [{ name: "", address: "sam@school.example" }], to: [], cc: [], bcc: [], subject: "x", text: "", html: HOSTILE, attachments: [], draft: { folder: "Drafts", uid: "4" }, source: { folder: "Drafts", uid: "4" } };
    await start(window, BASE.concat([["api/mail/compose", draft]]));
    window.eval('openMailCompose("draft", { uid: "4", folder: "Drafts" })');
    await settle(window);
    const editor = app(window).querySelector(".mail-editor");
    expect(editor.innerHTML).toContain("<b>there</b>");
    expect(editor.innerHTML).not.toMatch(/onerror|onload|javascript:|<img|<svg/);
    expect(window.__pwned).toBeUndefined();
  });

  test("a reply quotes the mail as text", async () => {
    const { window } = loadApp();
    const reply = { mode: "reply", senders: [{ name: "", address: "sam@school.example" }], to: [], cc: [], subject: "Re: x", text: "", html: HOSTILE, attachments: [], source: { folder: "INBOX", uid: "7" }, original: { from: DETAIL.from, date: DETAIL.date } };
    await start(window, BASE.concat([["api/mail/compose", reply]]));
    window.eval('openMailCompose("reply", { uid: "7", folder: "INBOX" })');
    await settle(window);
    const quote = app(window).querySelector(".mail-editor blockquote");
    expect(quote.textContent).toContain("Hi there");
    expect(quote.querySelector("b, a, img")).toBeNull();
  });

  test("printing builds a print view instead of downloading the mail as html", async () => {
    const { window } = loadApp();
    await start(window, BASE);
    const printed = [];
    window.eval("printInFrame = (blob) => { window.__printed = (window.__printed || 0) + 1; return Promise.resolve(true); }");
    window.eval("downloadBlob = () => { throw new Error('downloaded'); }");
    evalWith(window, "printMail(testArgs[0])", DETAIL);
    await settle(window);
    expect(window.__printed).toBe(1);
    const page = evalWith(window, "mailPrintPage(testArgs[0])", DETAIL);
    expect(page).toContain("<b>there</b>");
    expect(page).not.toMatch(/onerror|onload|javascript:|<img|<svg/);
    expect(printed.length).toBe(0);
  });
});

describe("the open mail stays with its school", () => {
  test("switching the school closes the open mail and later actions keep the original school", async () => {
    const { window } = loadApp();
    const asked = await start(window, BASE.concat([["api/mail/flag", { ok: true, folder: "INBOX", unread: 1, total: 1 }]]));
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    const entry = window.eval("state.mailDetail.entry");
    expect(entry.connection).toBe(SCHOOL);
    window.eval(`setMailSchool("${OTHER}")`);
    await settle(window);
    expect(window.eval("state.mailDetail")).toBeNull();
    evalWith(window, "mailBulkFlag([testArgs[0]], 'flagged', true)", entry);
    await settle(window);
    const flag = asked.find((call) => call.url.includes("api/mail/flag"));
    expect(flag.body.connection_id).toBe(SCHOOL);
    expect(flag.body.expect).toEqual({ 7: "<trip-1@school.example>" });
  });
});

describe("sending", () => {
  const COMPOSE = { mode: "new", senders: [{ name: "", address: "sam@school.example" }], to: [], cc: [], bcc: [], subject: "", text: "", attachments: [] };

  async function compose(window, extra, hold) {
    const asked = await start(window, (extra || []).concat(BASE, [["api/mail/compose", COMPOSE]]), hold);
    window.eval('openMailCompose("new")');
    await settle(window);
    const fill = (selector, value) => {
      const node = app(window).querySelector(selector);
      node.value = value;
      node.dispatchEvent(new window.Event("input"));
    };
    return { asked, fill };
  }

  test("the confirmation names recipients, copies, blind copies, groups and attachments", async () => {
    const { window } = loadApp();
    const { fill } = await compose(window);
    window.eval("state.mailCompose.groups['eltern.3b@school.example'] = 'Eltern 3b'");
    window.eval("state.mailCompose.attachments = [{ id: '2', filename: 'Brief.pdf' }]; state.pageForm.carry = ['2']; state.pageForm.showCopies = true; render()");
    await settle(window);
    fill(".mail-compose .mail-to", "Teacher <t@school.example>, eltern.3b@school.example");
    fill(".mail-compose .mail-cc", "office@school.example");
    fill(".mail-compose .mail-bcc", "quiet@school.example");
    window.eval("sendMail()");
    await settle(window);
    const text = app(window).querySelector(".sheet").textContent;
    for (const part of ["Teacher <t@school.example>", "Gruppe Eltern 3b", "office@school.example", "quiet@school.example", "Brief.pdf"]) expect(text).toContain(part);
  });

  test("a send waits for a draft save in flight and uses the newest draft", async () => {
    const { window } = loadApp();
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const hold = { pattern: "api/mail/draft", promise: gate, body: { ok: true, draft: { folder: "Drafts", uid: "12" }, source: { folder: "Drafts", uid: "12" }, attachments: [] } };
    const { asked, fill } = await compose(window, [["api/mail/send", { ok: true, sent: true, saved: true, refused: [] }]], hold);
    fill(".mail-compose .mail-to", "t@school.example");
    window.eval("saveMailDraft(true)");
    window.eval("sendMail()");
    await settle(window);
    expect(app(window).querySelector(".sheet")).toBeNull();
    release();
    await settle(window, 20);
    app(window).querySelector(".sheet .mail-send-confirm").click();
    await settle(window, 20);
    const send = asked.find((call) => call.url.includes("api/mail/send"));
    expect(send.body.draft).toEqual({ folder: "Drafts", uid: "12" });
  });

  test("addresses the mail server refused are listed after sending", async () => {
    const { window } = loadApp();
    const { fill } = await compose(window, [["api/mail/send", { ok: true, sent: true, saved: true, refused: ["quiet@school.example"] }]]);
    fill(".mail-compose .mail-to", "t@school.example");
    window.eval("sendMail()");
    await settle(window);
    app(window).querySelector(".sheet .mail-send-confirm").click();
    await settle(window, 20);
    expect(app(window).querySelector(".sheet .mail-refused").textContent).toContain("quiet@school.example");
  });

  test("the send state is reset when a sign-in problem takes over", async () => {
    const { window } = loadApp();
    const { fill } = await compose(window, [["api/mail/send", () => { throw new Error("offline"); }]]);
    fill(".mail-compose .mail-to", "t@school.example");
    window.eval("handleApiFailure = () => true;");
    window.eval("sendMail()");
    await settle(window);
    app(window).querySelector(".sheet .mail-send-confirm").click();
    await settle(window, 20);
    expect(window.eval("state.mailCompose.sending")).toBe(false);
  });

  test("a saved draft takes over its attachments so the next save keeps them", async () => {
    const { window } = loadApp();
    const { asked, fill } = await compose(window, [["api/mail/draft", { ok: true, draft: { folder: "Drafts", uid: "12" }, source: { folder: "Drafts", uid: "12" }, attachments: [{ id: "2", filename: "Brief.pdf" }] }]]);
    fill(".mail-compose .mail-to", "t@school.example");
    window.eval("state.mailComposeFiles = [new File(['x'], 'Brief.pdf')]");
    await window.eval("saveMailDraft(false)");
    await settle(window);
    expect(window.eval("state.mailCompose.source")).toEqual({ folder: "Drafts", uid: "12" });
    expect(window.eval("state.pageForm.carry")).toEqual(["2"]);
    expect(window.eval("state.mailComposeFiles.length")).toBe(0);
    await window.eval("saveMailDraft(false)");
    const saves = asked.filter((call) => call.url.includes("api/mail/draft"));
    expect(saves[1].body.source).toEqual({ folder: "Drafts", uid: "12" });
    expect(saves[1].body.carry).toEqual(["2"]);
  });
});

describe("read receipts", () => {
  test("the confirmation shows the receipt address and the request carries an id", async () => {
    const { window } = loadApp();
    const asked = await start(window, BASE.concat([["api/mail/receipt", { ok: true, sent: true }]]));
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    app(window).querySelector(".mail-receipt-send").click();
    await settle(window);
    expect(app(window).querySelector(".sheet").textContent).toContain("t@school.example");
    confirmButton(window).click();
    await settle(window, 20);
    const call = asked.find((entry) => entry.url.includes("api/mail/receipt"));
    expect(call.body.request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(call.body.connection_id).toBe(SCHOOL);
  });
});
