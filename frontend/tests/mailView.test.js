import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const SCHOOL = "a1b2c3d4";
const NOW = new Date();
const TODAY_ISO = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate(), 9, 30).toISOString();
const OLDER_ISO = new Date(NOW.getFullYear(), NOW.getMonth(), NOW.getDate() - 9, 8, 0).toISOString();
const FOLDERS = [
  { id: "INBOX", name: "INBOX", path: "INBOX", role: "inbox", unread: 1, total: 2, depth: 0, delimiter: "/" },
  { id: "Sent", name: "Sent", path: "Sent", role: "sent", unread: 0, total: 1, depth: 0, delimiter: "/" },
  { id: "Trash", name: "Trash", path: "Trash", role: "trash", unread: 0, total: 0, depth: 0, delimiter: "/" },
  { id: "Elternrat", name: "Elternrat", path: "Elternrat", role: "folder", unread: null, total: null, depth: 0, delimiter: "/" },
];
const MESSAGES = [
  { uid: "9", folder: "INBOX", subject: "Rückmeldung", from: [{ name: "Office", address: "office@school.example" }], to: [], cc: [], date: TODAY_ISO, unread: true, flagged: false, answered: false, has_attachments: false, tags: [] },
  { uid: "7", folder: "INBOX", subject: "Ausflug am Freitag", from: [{ name: "Class Teacher", address: "teacher@school.example" }], to: [], cc: [], date: OLDER_ISO, unread: false, flagged: true, answered: true, has_attachments: true, tags: ["Wichtig"] },
];
const DETAIL = {
  uid: "7",
  folder: "INBOX",
  subject: "Ausflug am Freitag",
  from: [{ name: "Class Teacher", address: "teacher@school.example" }],
  to: [{ name: "A", address: "a@school.example" }, { name: "B", address: "b@school.example" }, { name: "C", address: "c@school.example" }, { name: "D", address: "d@school.example" }],
  cc: [], bcc: [], reply_to: [], sender: [],
  date: OLDER_ISO,
  unread: false, flagged: true, answered: true, draft: false, tags: [],
  receipt_to: [{ name: "Class Teacher", address: "teacher@school.example" }],
  message_id: "<trip-1@school.example>",
  body_html: '<p>Hello <b>all</b> <a href="https://example.org/trip" rel="noopener noreferrer" target="_blank">Trip</a></p>',
  body_text: "",
  attachments: [{ id: "3", filename: "Elternbrief.pdf", mimetype: "application/pdf", size: 10, inline: false }],
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
    if (body && typeof body === "string") body = JSON.parse(body);
    else if (body && typeof body.get === "function") body = JSON.parse(body.get("data"));
    asked.push({ url, method, body });
    if (url.endsWith("api/mail")) return response({ schools: [{ connection_id: SCHOOL, school: "Riverside", unread: 1 }] });
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
    state.mail = [{ connection_id: "a1b2c3d4", school: "Riverside", unread: 1 }];
    ${extra}
  `);
}

const DEFAULT_ANSWERS = [
  ["api/mail/folders", { folders: FOLDERS }],
  ["api/mail/messages", { messages: MESSAGES, total: 2, more: false }],
  ["api/mail/message?", DETAIL],
  ["api/mail/seen", { ok: true, folder: "INBOX", unread: 0, total: 2, unread_mail: 0 }],
];

async function settle(window, rounds = 6) {
  for (let index = 0; index < rounds; index += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

async function openMailView(window, answers = DEFAULT_ANSWERS) {
  const asked = router(window, answers);
  await settle(window, 12);
  seed(window);
  window.eval('setView("mail")');
  await settle(window);
  window.eval("render()");
  return asked;
}

function app(window) {
  return window.document.querySelector("#app");
}

function noHandOff(node) {
  const links = [...node.querySelectorAll("a")].filter((link) => !link.closest(".body-html"));
  for (const link of links) {
    expect(link.getAttribute("href") || "").not.toContain("/iserv/");
    expect(link.getAttribute("target")).toBeNull();
  }
  expect(node.textContent).not.toContain("In IServ öffnen");
}

describe("the overview hint opens the mail inside the app", () => {
  test("names the count and opens the mail area for that school instead of linking to IServ", async () => {
    const { window } = loadApp();
    router(window, DEFAULT_ANSWERS);
    seed(window);
    const overview = window.eval("overviewView()");
    const notice = overview.querySelector(".mail-notice");
    expect(notice.textContent).toContain(evalWith(window, "tCount('mail.unread', 1)"));
    expect(notice.querySelector("a")).toBeNull();
    noHandOff(notice);
    notice.querySelector(".mail-notice-open").click();
    await settle(window);
    expect(window.eval("state.view")).toBe("mail");
    expect(window.eval("state.mailSchool")).toBe(SCHOOL);
  });

  test("the mail area is offered only when a school lists mail and carries the unread badge", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("navigationAreas()")).toContain("mail");
    expect(window.eval("badgeCount('mail')")).toBe(1);
    evalWith(window, "state.mail = []");
    expect(window.eval("navigationAreas()")).not.toContain("mail");
  });
});

describe("the mail list", () => {
  test("shows folders with unread counts and mails grouped by day, unread marked", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window);
    const root = app(window);
    const chips = [...root.querySelectorAll(".mail-folders .chip")];
    expect(chips.map((chip) => chip.getAttribute("data-folder"))).toEqual(["INBOX", "Sent", "Trash", "Elternrat"]);
    expect(chips[0].textContent).toContain(evalWith(window, "t('mail.folder.inbox')"));
    expect(chips[0].querySelector(".n").textContent).toBe("1");
    const days = [...root.querySelectorAll(".mail-day .overline")].map((node) => node.textContent);
    expect(days[0]).toBe(evalWith(window, "t('mail.day.today')"));
    expect(days.length).toBe(2);
    const rows = [...root.querySelectorAll(".mail-row")];
    expect(rows.map((row) => row.getAttribute("data-uid"))).toEqual(["9", "7"]);
    expect(rows[0].classList.contains("read")).toBe(false);
    expect(rows[0].querySelector(".row-dot i")).not.toBeNull();
    expect(rows[1].classList.contains("read")).toBe(true);
    expect(rows[1].querySelector(".mail-star.on")).not.toBeNull();
    noHandOff(root);
    expect(asked.some((call) => call.url.includes("api/mail/messages") && call.url.includes("folder=INBOX"))).toBe(true);
    expect(asked.some((call) => call.url.includes("api/mail/seen"))).toBe(false);
  });

  test("a refused mailbox sign-in is an unknown state with its reason, never an empty list", async () => {
    const { window } = loadApp();
    await openMailView(window, [["api/mail/folders", { error: "network", message_key: "api.mail.signInRefused", message: "x" }]]);
    const root = app(window);
    expect(root.querySelector(".mail-row")).toBeNull();
    expect(root.textContent).toContain(evalWith(window, "t('mail.error.signInTitle')"));
    expect(root.textContent).not.toContain(evalWith(window, "t('mail.empty.title')"));
    expect(root.querySelector(".empty .btn")).not.toBeNull();
  });

  test("a failing list is an unknown state with a retry, never empty", async () => {
    const { window } = loadApp();
    await openMailView(window, [["api/mail/folders", { folders: FOLDERS }], ["api/mail/messages", { error: "network", message_key: "api.mail.unreachable", message: "x" }]]);
    const root = app(window);
    expect(root.textContent).toContain(evalWith(window, "t('mail.error.title')"));
    expect(root.textContent).not.toContain(evalWith(window, "t('mail.empty.title')"));
  });

  test("an unknown count is not shown as zero mails", () => {
    const { window } = loadApp();
    router(window, []);
    seed(window, "state.mail = null; state.mailCountsError = { error: 'network', body: null };");
    window.eval('state.view = "mail"; render()');
    expect(app(window).textContent).toContain(evalWith(window, "t('mail.error.title')"));
  });
});

describe("opening a mail", () => {
  test("an unread mail is marked read once its detail arrived, a read one is not marked again", async () => {
    const { window } = loadApp();
    const unreadDetail = Object.assign({}, DETAIL, { uid: "9", unread: true, receipt_to: [] });
    const asked = await openMailView(window, [
      ["api/mail/folders", { folders: FOLDERS }],
      ["api/mail/messages", { messages: MESSAGES, total: 2, more: false }],
      ["uid=9", unreadDetail],
      ["uid=7", DETAIL],
      ["api/mail/seen", { ok: true, folder: "INBOX", unread: 0, total: 2, unread_mail: 0 }],
    ]);
    app(window).querySelector('.mail-row[data-uid="9"]').click();
    await settle(window);
    const seen = asked.filter((call) => call.url.includes("api/mail/seen"));
    expect(seen.length).toBe(1);
    expect(seen[0].body).toMatchObject({ connection_id: SCHOOL, folder: "INBOX", uid: "9" });
    expect(window.eval("state.mail[0].unread")).toBe(0);
    window.eval("leaveMailDetail()");
    window.eval("render()");
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    expect(asked.filter((call) => call.url.includes("api/mail/seen")).length).toBe(1);
  });

  test("the detail shows sender, collapsed recipients, the body, attachments through the app and no hand-off", async () => {
    const { window } = loadApp();
    await openMailView(window);
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    const root = app(window);
    expect(root.querySelector(".mail-from").textContent).toContain("teacher@school.example");
    expect(root.querySelector(".mail-to .mail-addr-more").textContent).toBe("Alle zeigen (1 weitere Person)");
    expect(root.querySelector(".mail-to").textContent).not.toContain("d@school.example");
    const frame = root.querySelector("iframe.mail-frame");
    expect(frame.getAttribute("sandbox")).toBe("allow-popups allow-popups-to-escape-sandbox");
    expect(frame.getAttribute("src")).toBe("api/mail/body?connection=a1b2c3d4&folder=INBOX&uid=7&theme=light");
    expect(root.innerHTML).not.toContain("<b>all</b>");
    expect(root.querySelector(".mail-receipt")).not.toBeNull();
    const attachment = window.eval("mailAttachmentFiles(state.mailDetail.detail, 'INBOX', state.mailDetail.connection)")[0];
    expect(attachment.url).toBe("api/mail/attachment?connection=a1b2c3d4&folder=INBOX&uid=7&part=3");
    noHandOff(root);
  });

  test("the text view replaces the formatted body", async () => {
    const { window } = loadApp();
    await openMailView(window);
    app(window).querySelector('.mail-row[data-uid="7"]').click();
    await settle(window);
    window.eval("state.mailShowText = true; render()");
    const text = app(window).querySelector(".mail-text");
    expect(text.textContent).toContain("Hello all");
    expect(app(window).querySelector("iframe.mail-frame")).toBeNull();
  });
});

describe("changing mails", () => {
  test("moving to the trash happens directly but deleting from the trash asks first", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([["api/mail/trash", { ok: true, moved: ["7"], left: [], folder: "INBOX" }]]));
    window.eval('mailTrash([{ uid: "7", folder: "INBOX" }])');
    await settle(window);
    const first = asked.filter((call) => call.url.includes("api/mail/trash"));
    expect(first.length).toBe(1);
    expect(first[0].body.confirmed).toBeUndefined();
    window.eval('mailTrash([{ uid: "4", folder: "Trash" }])');
    await settle(window);
    expect(asked.filter((call) => call.url.includes("api/mail/trash")).length).toBe(1);
    expect(app(window).querySelector(".sheet")).not.toBeNull();
  });

  test("flags go to the flag route with the chosen mails", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([["api/mail/flag", { ok: true, folder: "INBOX", unread: 1, total: 2 }]]));
    window.eval('mailBulkFlag([{ uid: "9", folder: "INBOX" }, { uid: "7", folder: "INBOX" }], "flagged", true)');
    await settle(window);
    const call = asked.find((entry) => entry.url.includes("api/mail/flag"));
    expect(call.body).toEqual({ connection_id: SCHOOL, folder: "INBOX", uids: ["9", "7"], flag: "flagged", on: true });
  });
});

describe("writing a mail", () => {
  test("a reply starts prefilled and sending asks for a confirmation before anything leaves", async () => {
    const { window } = loadApp();
    const start = {
      mode: "reply", senders: [{ name: "Sam", address: "sam@school.example" }, { name: "", address: "office@school.example" }],
      to: [{ name: "Teacher, Class", address: "teacher@school.example" }], cc: [], bcc: [],
      subject: "Re: Ausflug am Freitag", text: "Hello all", html: "<p>Hello all</p>", attachments: [],
      source: { folder: "INBOX", uid: "7" }, original: { from: DETAIL.from, date: DETAIL.date, subject: DETAIL.subject, to: [] },
      in_reply_to: "<trip-1@school.example>", references: "<trip-1@school.example>",
    };
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([["api/mail/compose", start], ["api/mail/send", { ok: true, sent: true, saved: true }]]));
    window.eval('openMailCompose("reply", { uid: "7", folder: "INBOX" })');
    await settle(window);
    const root = app(window);
    expect([...root.querySelectorAll("select.mail-from option")].map((option) => option.textContent)).toEqual(["Sam <sam@school.example>", "office@school.example"]);
    expect(root.querySelector(".mail-to").value).toBe('"Teacher, Class" <teacher@school.example>');
    expect(root.querySelector(".mail-subject-input").value).toBe("Re: Ausflug am Freitag");
    expect(root.querySelector(".mail-editor blockquote")).not.toBeNull();
    root.querySelector(".mail-send").click();
    await settle(window);
    expect(asked.some((call) => call.url.includes("api/mail/send"))).toBe(false);
    const confirm = app(window).querySelector(".sheet .btn");
    expect(confirm).not.toBeNull();
    window.eval("state.sheet = null");
  });

  test("the address parser keeps quoted names with commas and reports invalid ones", () => {
    const { window } = loadApp();
    const parsed = window.eval('parseMailAddresses(\'"Teacher, Class" <t@school.example>; office@school.example, nope\')');
    expect(parsed.found).toEqual([{ name: "Teacher, Class", address: "t@school.example" }, { name: "", address: "office@school.example" }]);
    expect(parsed.invalid).toEqual(["nope"]);
  });
});

const SETTINGS_PAGE = {
  path: "/iserv/mail/settings/vacation", kind: "vacation", title: "Abwesenheitsnotiz", forms: [{
    index: 0, name: "vacation", title: "", method: "post", has_token: true, collections: [],
    fields: [
      { name: "vacation[enabled]", kind: "checkbox", label: "", choices: [{ value: "1", label: "Aktiv", checked: false }], required: false, disabled: false },
      { name: "vacation[subject]", kind: "text", label: "Betreff", value: "", required: false, disabled: false },
    ],
  }],
};

describe("mail settings through the IServ forms", () => {
  test("lists the settings pages, renders a form and saves only after a confirmation", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([
      ["api/mail/settings/page", (body) => (body ? { ok: true, verified: true, errors: [], unconfirmed: [], form: null } : SETTINGS_PAGE)],
      ["api/mail/settings", { pages: [{ path: "/iserv/mail/settings/vacation", kind: "vacation", title: "Abwesenheitsnotiz", forms: 1, guessed: false }], unknown: false }],
      ["api/mail/account", { account: { page_size: 25, tags: [], flags: {}, auto_archive: [], display_name: "", addresses: [], lookup: false } }],
    ]));
    window.eval("openMailSettings()");
    await settle(window);
    const row = app(window).querySelector(".mail-setting-page");
    expect(row.textContent).toContain("Abwesenheitsnotiz");
    row.click();
    await settle(window);
    const subject = app(window).querySelector('.mail-setting-field[data-name="vacation[subject]"] input');
    subject.value = "Bin weg";
    subject.dispatchEvent(new window.Event("input"));
    const box = app(window).querySelector('.mail-setting-field[data-name="vacation[enabled]"] input');
    box.checked = true;
    box.dispatchEvent(new window.Event("change"));
    app(window).querySelector(".mail-setting-save").click();
    await settle(window);
    expect(asked.some((call) => call.method === "POST" && call.url.includes("api/mail/settings/page"))).toBe(false);
    expect(app(window).querySelector(".sheet")).not.toBeNull();
    const confirm = [...app(window).querySelectorAll(".sheet .btn")].find((button) => !button.classList.contains("ghost"));
    confirm.click();
    await settle(window, 20);
    const save = asked.find((call) => call.method === "POST" && call.url.includes("api/mail/settings/page"));
    expect(save.body).toEqual({
      connection_id: SCHOOL, path: "/iserv/mail/settings/vacation", form: 0,
      values: { "vacation[enabled]": ["1"], "vacation[subject]": "Bin weg" },
      fields: ["vacation[enabled]", "vacation[subject]"], confirmed: true,
    });
    expect(app(window).querySelector(".mail-setting-saved")).not.toBeNull();
  });

  test("tags from the account show with their name in the list", async () => {
    const { window } = loadApp();
    const tagged = MESSAGES.map((entry) => Object.assign({}, entry, { tags: entry.uid === "7" ? ["$label1"] : [] }));
    await openMailView(window, [
      ["api/mail/account", { account: { page_size: 25, tags: [{ id: "$label1", name: "Wichtig", color: "#d33" }], flags: {}, auto_archive: [], display_name: "", addresses: [], lookup: true } }],
      ["api/mail/folders", { folders: FOLDERS }],
      ["api/mail/messages", { messages: tagged, total: 2, more: false }],
    ]);
    const chip = app(window).querySelector('.mail-row[data-uid="7"] .mail-tag');
    expect(chip.textContent).toBe("Wichtig");
    expect(chip.querySelector(".mail-tag-dot").style.background).not.toBe("");
  });

  test("the page size from IServ is asked for", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([["api/mail/account", { account: { page_size: 25, tags: [], flags: {}, auto_archive: [], display_name: "", addresses: [], lookup: false } }]]));
    window.eval("state.mailList = null; loadMailList(false)");
    await settle(window);
    expect(asked.some((call) => call.url.includes("api/mail/messages") && call.url.includes("limit=25"))).toBe(true);
  });

  test("typing a name offers recipients from the school lookup", async () => {
    const { window } = loadApp();
    const start = { mode: "new", senders: [{ name: "", address: "sam@school.example" }], to: [], cc: [], bcc: [], subject: "", text: "", attachments: [] };
    await openMailView(window, DEFAULT_ANSWERS.concat([
      ["api/mail/compose", start],
      ["api/mail/recipients", { recipients: [{ name: "Eltern 3b", address: "eltern.3b@school.example", group: true }], lookup: true }],
    ]));
    window.eval('openMailCompose("new")');
    await settle(window);
    const input = app(window).querySelector(".mail-compose .mail-to");
    input.value = "Elt";
    input.dispatchEvent(new window.Event("input"));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    await settle(window);
    const suggestion = app(window).querySelector(".mail-suggestion");
    expect(suggestion.textContent).toContain("eltern.3b@school.example");
    suggestion.click();
    expect(input.value).toBe("Eltern 3b <eltern.3b@school.example>, ");
  });
});

const EVENT_FORM = {
  path: "/iserv/calendar/create", subject: "Ausflug am Freitag",
  form: {
    index: 0, name: "event", title: "", method: "post", has_token: true, collections: [],
    fields: [
      { name: "event[subject]", kind: "text", label: "Titel", value: "", required: true, disabled: false },
      { name: "event[calendar]", kind: "select", label: "Kalender", value: "/a/home", options: [{ value: "/a/home", label: "Mein Kalender", selected: false }, { value: "/e/cal", label: "Eltern 3b", selected: false }], multiple: false, required: false, disabled: false },
      { name: "event[startDate]", kind: "date", label: "Beginn", value: "", required: true, disabled: false },
      { name: "event[description]", kind: "textarea", label: "Beschreibung", value: "", required: false, disabled: false },
    ],
  },
  prefill: { "event[subject]": "Ausflug am Freitag", "event[description]": "Hello all" },
  check: "c0ffee00c0ffee00",
};

describe("a calendar entry from a mail", () => {
  test("the sheet is prefilled from the mail and saves only after a confirmation", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([
      ["api/mail/event", (body) => (body ? { ok: true, verified: true, errors: [], event: { title: "Ausflug am Freitag", start: "2026-10-23", calendar: "Eltern 3b" } } : EVENT_FORM)],
    ]));
    window.eval('openSheet(() => mailEventSheet({ uid: "7", folder: "INBOX" }, { uid: "7", folder: "INBOX" }))');
    await settle(window, 12);
    const root = app(window);
    expect(root.querySelector('.sheet [data-name="event[subject]"] input').value).toBe("Ausflug am Freitag");
    expect(root.querySelector('.sheet [data-name="event[description]"] textarea').value).toBe("Hello all");
    const day = root.querySelector('.sheet [data-name="event[startDate]"] input');
    day.value = "2026-10-23";
    day.dispatchEvent(new window.Event("input"));
    const calendar = root.querySelector('.sheet [data-name="event[calendar]"] select');
    calendar.value = "/e/cal";
    calendar.dispatchEvent(new window.Event("change"));
    root.querySelector(".sheet .mail-event-save").click();
    await settle(window);
    expect(asked.some((call) => call.method === "POST" && call.url.includes("api/mail/event"))).toBe(false);
    const confirm = [...app(window).querySelectorAll(".sheet .btn")].find((button) => !button.classList.contains("ghost") && !button.classList.contains("mail-event-save"));
    confirm.click();
    await settle(window, 20);
    const save = asked.find((call) => call.method === "POST" && call.url.includes("api/mail/event"));
    expect(save.body.values).toEqual({ "event[subject]": "Ausflug am Freitag", "event[calendar]": "/e/cal", "event[startDate]": "2026-10-23", "event[description]": "Hello all" });
    expect(save.body.confirmed).toBe(true);
    expect(save.body.check).toBe("c0ffee00c0ffee00");
    expect(save.body.request_id).toMatch(/^[0-9a-f]{32}$/);
  });

  test("an unclear save keeps its request id so saving again cannot create a second entry", async () => {
    const { window } = loadApp();
    const asked = await openMailView(window, DEFAULT_ANSWERS.concat([
      ["api/mail/event", (body) => (body ? { ok: false, state: "uncertain", verified: false, errors: [], event: null, message_key: "api.mail.event.uncertain" } : EVENT_FORM)],
    ]));
    const saveOnce = async () => {
      window.eval('openSheet(() => mailEventSheet({ uid: "7", folder: "INBOX" }, { uid: "7", folder: "INBOX" }))');
      await settle(window, 12);
      app(window).querySelector(".sheet .mail-event-save").click();
      await settle(window);
      [...app(window).querySelectorAll(".sheet .btn")].find((button) => !button.classList.contains("ghost") && !button.classList.contains("mail-event-save")).click();
      await settle(window, 20);
    };
    await saveOnce();
    expect(window.eval("JSON.stringify(state.toast)")).toContain(evalWith(window, "t('mail.event.unconfirmed')"));
    await saveOnce();
    const saves = asked.filter((call) => call.method === "POST" && call.url.includes("api/mail/event"));
    expect(saves).toHaveLength(2);
    expect(saves[0].body.request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(saves[1].body.request_id).toBe(saves[0].body.request_id);
  });

  test("the default signature of an address is found in the signature form", () => {
    const { window } = loadApp();
    const form = {
      fields: [
        { name: "signature[text]", kind: "textarea", value: "Gruß" },
        { name: "signature[default]", kind: "select", multiple: false, value: "elternrat@school.example", options: [{ value: "a@school.example" }, { value: "elternrat@school.example" }] },
      ],
    };
    expect(evalWith(window, "signatureAddress(testArgs[0], testArgs[0].fields[0])", form)).toBe("elternrat@school.example");
    expect(evalWith(window, "signatureAddress(testArgs[0], testArgs[0].fields[0])", { fields: [form.fields[0]] })).toBe("");
  });
});
