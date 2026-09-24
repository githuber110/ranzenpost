import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const OPEN_SEEN = { type: "seen", open: true, done: false, sendable: true, confirmed_at: "" };
const OPEN_CHOICE = { type: "confirmation", open: true, done: false, sendable: false, confirmed_at: "" };
const DONE_SEEN = { type: "seen", open: false, done: true, sendable: false, confirmed_at: "2026-09-03T14:05:00" };

function letterWith(confirmation, extra) {
  return Object.assign(
    { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false, confirmation },
    extra || {}
  );
}

function renderRow(window, letter) {
  return window.eval("(function (letter) { return letterRow(letter); })")(letter);
}

function renderBlock(window, letter, detail) {
  return window.eval("(function (letter, detail) { return letterConfirmationBlock(letter, detail); })")(
    letter,
    detail || null
  );
}

function stubFetch(window, payload, calls) {
  window.fetch = (url, options) => {
    calls.push({ url: String(url), body: JSON.parse(options.body) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
  };
}

describe("letter list marks an open read confirmation", () => {
  test("a letter with an open confirmation carries the marker tag", () => {
    const { window } = loadApp();
    const row = renderRow(window, letterWith(OPEN_SEEN, { recipients: "Klasse 2B" }));
    const tags = Array.from(row.querySelectorAll(".row-tags .tag")).map((tag) => tag.textContent);
    expect(tags).toContain(window.eval('t("letters.confirm.badge")'));
    expect(row.querySelector(".tag.confirm")).not.toBeNull();
  });

  test("the marker appears even when the letter has no other tags", () => {
    const { window } = loadApp();
    const row = renderRow(window, letterWith(OPEN_SEEN));
    expect(row.querySelector(".tag.confirm")).not.toBeNull();
  });

  test("no marker without a confirmation and none once it is done", () => {
    const { window } = loadApp();
    expect(renderRow(window, letterWith(null)).querySelector(".tag.confirm")).toBeNull();
    expect(renderRow(window, letterWith(DONE_SEEN)).querySelector(".tag.confirm")).toBeNull();
  });

  test("a read letter with an open confirmation still counts for the tab badge", () => {
    const { window } = loadApp();
    const count = window.eval(
      "(function (letters) { state.letters = { tab: 'current', letters }; return badgeCount('post'); })"
    )([letterWith(OPEN_SEEN), letterWith(null)]);
    expect(count).toBe(1);
  });

  test("the overview chapter lists a read letter that still waits for a confirmation", () => {
    const { window } = loadApp();
    const blocks = window.eval(
      "(function (letters) { state.letters = { tab: 'current', letters }; return lettersChapter().blocks.map((b) => b.key); })"
    )([letterWith(OPEN_SEEN)]);
    expect(blocks).toContain("letter:1:2");
  });
});

describe("letter detail shows the confirmation block", () => {
  test("an open read confirmation offers the confirm button", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), { confirmation: OPEN_SEEN });
    expect(block).not.toBeNull();
    expect(block.querySelector(".confirm-title").textContent).toBe(window.eval('t("letters.confirm.title")'));
    expect(block.querySelector("button.confirm-action")).not.toBeNull();
  });

  test("accept/decline is shown honestly and offers no send button", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), { confirmation: OPEN_CHOICE });
    expect(block.querySelector(".confirm-title").textContent).toBe(
      window.eval('t("letters.confirm.choiceTitle")')
    );
    expect(block.querySelector(".confirm-text").textContent).toBe(
      window.eval('t("letters.confirm.choiceText")')
    );
    expect(block.querySelector("button")).toBeNull();
  });

  test("a letter without a confirmation renders no block", () => {
    const { window } = loadApp();
    expect(renderBlock(window, letterWith(null), { confirmation: null })).toBeNull();
  });

  test("a finished confirmation shows the timestamp instead of a button", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), { confirmation: DONE_SEEN });
    expect(block.className).toContain("done");
    expect(block.querySelector("button")).toBeNull();
    expect(block.querySelector(".confirm-text").textContent).toContain("03.09.2026");
  });

  test("a finished confirmation without a timestamp falls back to plain wording", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), {
      confirmation: { type: "seen", open: false, done: true, sendable: false, confirmed_at: "" },
    });
    expect(block.querySelector(".confirm-text").textContent).toBe(
      window.eval('t("letters.confirm.doneText")')
    );
  });
});

describe("confirming asks first and never fires on its own", () => {
  test("cancelling the question sends nothing", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(OPEN_SEEN);
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    expect(window.eval("!!state.sheet")).toBe(true);
    window.eval("state.onSheetClose()");
    await pending;
    expect(calls).toEqual([]);
    expect(letter.confirmation.done).toBe(false);
  });

  test("confirming posts once and flips the letter to done", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true, confirmed_at: "2026-09-03T14:05:00" }, calls);
    const letter = letterWith(OPEN_SEEN);
    window.eval("(function (letter) { state.letters = { tab: 'current', letters: [letter] }; })")(letter);
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    const confirmButton = window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]");
    confirmButton.click();
    await pending;
    expect(calls.length).toBe(1);
    expect(calls[0].url).toContain("api/letters/confirm");
    expect(calls[0].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2" });
    expect(letter.confirmation).toEqual({
      type: "seen",
      open: false,
      done: true,
      sendable: false,
      confirmed_at: "2026-09-03T14:05:00",
    });
    expect(window.eval("state.letters.letters[0].confirmation.done")).toBe(true);
  });

  test("a refused confirmation keeps the open state and shows the reason from the backend", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: false, message_key: "api.letters.confirm.rejected" }, calls);
    const letter = letterWith(OPEN_SEEN);
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    expect(calls.length).toBe(1);
    expect(letter.confirmation.open).toBe(true);
    expect(letter.confirmation.done).toBe(false);
    expect(window.eval("state.toast && state.toast.message")).toBe(
      window.eval('t("api.letters.confirm.rejected")')
    );
  });
});

describe("marking read stops lying about letters that still need a confirmation", () => {
  function seenReply(window, body) {
    window.fetch = () =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve(body),
      });
  }

  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  test("a single blocked letter says so instead of claiming success", async () => {
    const { window } = loadApp();
    seenReply(window, { read: 0, blocked: 1 });
    await window.eval("markLetterRead({ letter_id: '1', recipient_id: '2' })");
    await settle();
    expect(window.eval("state.toast.message")).toBe(window.eval("t('letters.toast.blocked')"));
    expect(window.eval("state.toast.kind")).toBe("bad");
  });

  test("a mixed batch names both halves", async () => {
    const { window } = loadApp();
    seenReply(window, { read: 2, blocked: 1 });
    await window.eval("markAllLettersRead()");
    await settle();
    expect(window.eval("state.toast.message")).toBe(
      window.eval("t('letters.toast.markedPartial', { read: '2', blocked: '1' })")
    );
    expect(window.eval("state.toast.kind")).toBe("good");
  });

  test("a clean batch keeps the old wording", async () => {
    const { window } = loadApp();
    seenReply(window, { read: 3, blocked: 0 });
    await window.eval("markAllLettersRead()");
    await settle();
    expect(window.eval("state.toast.message")).toBe(
      window.eval("t('letters.toast.marked', { count: '3' })")
    );
  });

  test("the swipe menu offers the confirmation instead of a mark that cannot work", () => {
    const { window } = loadApp();
    const blocked = window.eval(
      "(function (letter) { state.lettersTab = 'current'; return letterActionsSheet(letter); })"
    )({ letter_id: "1", recipient_id: "2", title: "Infobrief", unread: true, confirmation: { type: "seen", open: true } });
    expect(blocked.textContent).toContain(window.eval("t('letters.action.confirmFirst')"));
    expect(blocked.textContent).not.toContain(window.eval("t('letters.action.markRead')"));
    const plain = window.eval(
      "(function (letter) { state.lettersTab = 'current'; return letterActionsSheet(letter); })"
    )({ letter_id: "1", recipient_id: "2", title: "Infobrief", unread: true });
    expect(plain.textContent).toContain(window.eval("t('letters.action.markRead')"));
  });

  test("an optimistic read is taken back when the server reports it blocked", async () => {
    const { window } = loadApp();
    seenReply(window, { read: 0, blocked: 1 });
    const letter = window.eval(
      "(function () { const l = { letter_id: '1', recipient_id: '2', unread: true }; markLetterSeen(l); return l; })"
    )();
    expect(letter.unread).toBe(false);
    await settle();
    await settle();
    expect(letter.unread).toBe(true);
  });
});


describe("a message to the school with the confirmation", () => {
  const REPLYABLE = Object.assign({}, OPEN_SEEN, { can_reply: true });

  test("only a letter whose form has a message field offers the field", () => {
    const { window } = loadApp();
    expect(renderBlock(window, letterWith(REPLYABLE)).querySelector("textarea.confirm-message")).not.toBeNull();
    expect(renderBlock(window, letterWith(OPEN_SEEN)).querySelector("textarea.confirm-message")).toBeNull();
    expect(renderBlock(window, letterWith(DONE_SEEN)).querySelector("textarea.confirm-message")).toBeNull();
  });

  test("the question shows the message and the post carries it", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true, confirmed_at: "2026-09-03T14:05:00" }, calls);
    const letter = letterWith(REPLYABLE);
    const field = renderBlock(window, letter).querySelector("textarea.confirm-message");
    field.value = "  Danke, wir kommen.  ";
    field.dispatchEvent(new window.Event("input"));
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    const sheet = window.eval("state.sheet()");
    expect(sheet.textContent).toContain("Danke, wir kommen.");
    sheet.querySelectorAll(".btn-stack button")[0].click();
    await pending;
    expect(calls[0].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2", text: "Danke, wir kommen." });
    expect(letter.replyDraft).toBe("");
  });

  test("an empty message sends the confirmation exactly as before", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(REPLYABLE, { replyDraft: "   " });
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    window.eval("state.sheet()").querySelectorAll(".btn-stack button")[0].click();
    await pending;
    expect(calls[0].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2" });
  });
});

describe("a message to the school is sent once and only where the letter takes one", () => {
  test("a second tap while sending does nothing", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(Object.assign({}, OPEN_SEEN, { can_reply: true }), { replyDraft: "Hallo" });
    const first = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    window.eval("state.sheet()").querySelectorAll(".btn-stack button")[0].click();
    await Promise.resolve();
    expect(letter.confirming).toBe(true);
    const second = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    expect(window.eval("!!state.sheet")).toBe(false);
    await Promise.all([first, second]);
    expect(calls.length).toBe(1);
    expect(letter.confirming).toBe(false);
  });

  test("a draft is not sent when the letter no longer takes a message", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(OPEN_SEEN, { replyDraft: "Hallo" });
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    expect(window.eval("state.sheet()").querySelector(".dlg-quote")).toBeNull();
    window.eval("state.sheet()").querySelectorAll(".btn-stack button")[0].click();
    await pending;
    expect(calls[0].body.text).toBeUndefined();
  });

  test("the message is quoted on its own, direction taken from the text", () => {
    const { window } = loadApp();
    const letter = letterWith(Object.assign({}, OPEN_SEEN, { can_reply: true }), { replyDraft: "شكرا\nسنحضر" });
    window.eval("(function (letter) { confirmLetterRead(letter); })")(letter);
    const quote = window.eval("state.sheet()").querySelector(".dlg-quote");
    expect(quote.getAttribute("dir")).toBe("auto");
    expect(quote.textContent).toBe("شكرا\nسنحضر");
  });
});

describe("the open letter decides whether a message goes along", () => {
  test("a reply field known only from the opened letter still sends the message", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(OPEN_SEEN, { replyDraft: "Danke" });
    const detail = { confirmation: Object.assign({}, OPEN_SEEN, { can_reply: true }) };
    window.eval("(function (letter, detail) { state.letterDetail = { letter, detail }; })")(letter, detail);
    const pending = window.eval("(function (letter) { return confirmLetterRead(letter); })")(letter);
    expect(window.eval("state.sheet()").querySelector(".dlg-quote").textContent).toBe("Danke");
    window.eval("state.sheet()").querySelectorAll(".btn-stack button")[0].click();
    await pending;
    expect(calls[0].body.text).toBe("Danke");
  });
});
