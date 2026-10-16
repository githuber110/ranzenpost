import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const SCHOOL = "a1b2c3d4";
const FOLDERS = [
  { id: "INBOX", name: "INBOX", path: "INBOX", role: "inbox", unread: 0, total: 2, depth: 0, delimiter: "/" },
  { id: "Unerwuenscht", name: "Unerwuenscht", path: "Unerwuenscht", role: "junk", junk: true, unread: 0, total: 0, depth: 0, delimiter: "/" },
];
const NAMED_ONLY = [
  { id: "INBOX", name: "INBOX", path: "INBOX", role: "inbox", junk: false, unread: 0, total: 2, depth: 0, delimiter: "/" },
  { id: "Spam", name: "Spam", path: "Spam", role: "junk", junk: false, unread: 0, total: 0, depth: 0, delimiter: "/" },
];
const MESSAGES = [
  { uid: "7", folder: "INBOX", subject: "Gewinnspiel", message_id: "<win@else.example>", from: [{ name: "Shop", address: "shop@else.example" }], to: [], cc: [], date: new Date().toISOString(), unread: false, flagged: false, answered: false, has_attachments: false, tags: [] },
];

function response(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function router(window, answers) {
  const asked = [];
  window.fetch = (input, options) => {
    const url = String(input);
    const body = options && typeof options.body === "string" ? JSON.parse(options.body) : null;
    asked.push({ url, body });
    if (url.endsWith("api/mail")) return response({ schools: [{ connection_id: SCHOOL, school: "Riverside", unread: 0 }] });
    for (const [pattern, answer] of answers) {
      if (url.includes(pattern)) return response(answer);
    }
    return response({});
  };
  return asked;
}

async function settle(window, rounds = 8) {
  for (let index = 0; index < rounds; index += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function openMail(window, answers, folders) {
  const asked = router(window, answers);
  await settle(window, 12);
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {}, connections: [{ id: "a1b2c3d4", label: "Riverside", setup_complete: true }] };
    state.modules = applyModules({ modules: {} });
    state.holidays = {};
    state.mail = [{ connection_id: "a1b2c3d4", school: "Riverside", unread: 0 }];
    state.mailAccount = { a1b2c3d4: { page_size: 40, tags: [] } };
    state.mailFolders = { a1b2c3d4: { folders: testArgs[0] } };
  `, folders || FOLDERS);
  window.eval('setView("mail")');
  await settle(window);
  window.eval("render()");
  return asked;
}

function confirmButton(window) {
  return window.eval("state.sheet()").querySelector(".btn-stack button");
}

describe("mark as spam", () => {
  test("asks first, moves with the confirmation and can be undone by moving back", async () => {
    const { window } = loadApp();
    const asked = await openMail(window, [
      ["api/mail/folders", { folders: FOLDERS }],
      ["api/mail/messages", { messages: MESSAGES, total: 1, more: false }],
      ["api/mail/spam", { ok: true, folder: "INBOX", moved: ["7"], left: [], junk: "Unerwuenscht", restore: { folder: "Unerwuenscht", uids: ["101"], target: "INBOX" }, unread: 0, total: 1 }],
      ["api/mail/move", { ok: true, folder: "Unerwuenscht", moved: ["101"], left: [] }],
    ]);
    window.eval('mailSpam([{ uid: "7", folder: "INBOX", message_id: "<win@else.example>" }])');
    await settle(window);
    expect(asked.some((entry) => entry.url.includes("api/mail/spam"))).toBe(false);
    confirmButton(window).click();
    await settle(window);
    const sent = asked.find((entry) => entry.url.includes("api/mail/spam"));
    expect(sent.body).toEqual({ connection_id: SCHOOL, folder: "INBOX", uids: ["7"], expect: { 7: "<win@else.example>" }, confirmed: true });
    expect(window.eval("state.view")).toBe("mail");
    const undo = window.eval("mailView()").querySelector(".mail-spam-undo");
    expect(undo).not.toBeNull();
    undo.click();
    await settle(window);
    const back = asked.find((entry) => entry.url.includes("api/mail/move"));
    expect(back.body).toEqual({ connection_id: SCHOOL, folder: "Unerwuenscht", uids: ["101"], target: "INBOX" });
    expect(window.eval("mailView()").querySelector(".mail-spam-undo")).toBeNull();
  });

  test("a mail in the junk folder offers the way back to the inbox instead", async () => {
    const { window } = loadApp();
    const asked = await openMail(window, [
      ["api/mail/folders", { folders: FOLDERS }],
      ["api/mail/messages", { messages: [], total: 0, more: false }],
      ["api/mail/move", { ok: true, folder: "Unerwuenscht", moved: ["5"], left: [] }],
    ]);
    const tools = evalWith(window, "mailDetailActions({ uid: '5', folder: 'Unerwuenscht' }, { folder: 'Unerwuenscht', uid: '5' })");
    expect(tools.querySelector(".mail-act-spam")).toBeNull();
    tools.querySelector(".mail-act-notspam").click();
    await settle(window);
    const moved = asked.find((entry) => entry.url.includes("api/mail/move"));
    expect(moved.body.target).toBe("INBOX");
    expect(moved.body.folder).toBe("Unerwuenscht");
  });
});

describe("a spam move the browser gives up on", () => {
  test("waits longer than the mail server and then says the outcome is unclear", async () => {
    const { window } = loadApp();
    const seen = [];
    window.AbortSignal.timeout = (ms) => {
      seen.push(ms);
      return undefined;
    };
    await openMail(window, [["api/mail/folders", { folders: FOLDERS }], ["api/mail/messages", { messages: MESSAGES, total: 1, more: false }]]);
    const plain = window.fetch;
    window.fetch = (input, options) => {
      if (!String(input).includes("api/mail/spam")) return plain(input, options);
      const failure = new Error("timed out");
      failure.name = "TimeoutError";
      return Promise.reject(failure);
    };
    window.eval('mailSpam([{ uid: "7", folder: "INBOX" }])');
    await settle(window);
    seen.length = 0;
    confirmButton(window).click();
    await settle(window);
    expect(Math.max(...seen)).toBeGreaterThanOrEqual(120000);
    expect(window.eval("state.toast && state.toast.message")).toBe(window.eval("t('mail.spam.unclear')"));
  });
});

describe("the spam actions follow the folder the server flags", () => {
  test("a folder only named like junk offers neither spam nor not spam", async () => {
    const { window } = loadApp();
    await openMail(window, [["api/mail/folders", { folders: NAMED_ONLY }], ["api/mail/messages", { messages: [], total: 0, more: false }]], NAMED_ONLY);
    const inInbox = evalWith(window, "mailDetailActions({ uid: '5', folder: 'INBOX' }, { folder: 'INBOX', uid: '5' })");
    expect(inInbox.querySelector(".mail-act-spam")).toBeNull();
    const inSpam = evalWith(window, "mailDetailActions({ uid: '5', folder: 'Spam' }, { folder: 'Spam', uid: '5' })");
    expect(inSpam.querySelector(".mail-act-notspam")).toBeNull();
  });
});
