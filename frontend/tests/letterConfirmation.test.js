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

  test("a reply form the app does not know yet points to the in-app problem report, never to IServ", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), { confirmation: OPEN_CHOICE });
    expect(block.querySelector(".confirm-title").textContent).toBe(
      window.eval('t("letters.confirm.choiceTitle")')
    );
    expect(block.querySelector(".confirm-text").textContent).toBe(
      window.eval('t("letters.confirm.unsupportedText")')
    );
    expect(block.querySelectorAll("button").length).toBe(1);
    expect(block.querySelector("button.letter-confirm-report")).not.toBeNull();
    expect(block.querySelector("a")).toBeNull();
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

const CHOICE = {
  mode: "submit",
  multiple: false,
  options: [
    { id: "a1", label: "Zustimmen", selected: false },
    { id: "b2", label: "Ablehnen", selected: false },
  ],
};
const OPEN_ANSWER = { type: "confirmation", open: true, done: false, sendable: true, can_reply: false, confirmed_at: "", choice: CHOICE };

function openDetail(window, letter, confirmation) {
  window.eval("(function (letter, detail) { state.letters = { tab: 'current', letters: [letter] }; state.letterDetail = { letter, detail }; })")(
    letter,
    { body_html: "<p>x</p>", attachments: [], confirmation }
  );
}

function card(window) {
  return window.eval("letterConfirmationBlock(state.letterDetail.letter, state.letterDetail.detail)");
}

function answer(window, letter, choice, canReply, edit) {
  return window.eval("(function (letter, choice, canReply, edit) { return sendLetterAnswer(letter, choice, canReply, edit); })")(letter, choice, canReply, edit);
}

describe("a letter that asks for an answer", () => {
  test("shows each answer as an option and enables sending only after a choice", () => {
    const { window } = loadApp();
    const letter = letterWith(null);
    openDetail(window, letter, OPEN_ANSWER);
    const block = card(window);
    expect(Array.from(block.querySelectorAll(".opt.letter-choice")).map((node) => node.textContent)).toEqual(["Zustimmen", "Ablehnen"]);
    expect(block.querySelector(".letter-answer-send").disabled).toBe(true);
    block.querySelectorAll(".opt.letter-choice")[1].click();
    const after = card(window);
    expect(after.querySelectorAll(".opt.letter-choice")[1].getAttribute("aria-pressed")).toBe("true");
    expect(after.querySelector(".letter-answer-send").disabled).toBe(false);
    expect(after.querySelectorAll(".btn:not(.ghost)").length).toBe(1);
  });

  test("cancelling the question sends nothing", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true }, calls);
    const letter = letterWith(null);
    openDetail(window, letter, OPEN_ANSWER);
    card(window).querySelectorAll(".opt.letter-choice")[0].click();
    const pending = answer(window, letter, CHOICE, false, false);
    window.eval("state.onSheetClose()");
    await pending;
    expect(calls).toEqual([]);
  });

  test("confirming sends the chosen answer once and shows it as given", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true, message_key: "api.letters.confirm.answered", confirmed_at: "2026-09-03T14:05:00", answer: ["Ablehnen"] }, calls);
    const letter = letterWith(null);
    openDetail(window, letter, OPEN_ANSWER);
    card(window).querySelectorAll(".opt.letter-choice")[1].click();
    const pending = answer(window, letter, CHOICE, false, false);
    expect(window.eval("state.sheet().querySelector('.dlg-quote').textContent")).toBe("Ablehnen");
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    expect(calls.length).toBe(1);
    expect(calls[0].url).toContain("api/letters/confirm");
    expect(calls[0].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2", choices: ["b2"] });
    const done = card(window);
    expect(done.className).toContain("done");
    expect(done.querySelector(".letter-answer").textContent).toBe(window.eval('t("letters.confirm.answerText", { answer: "Ablehnen" })'));
    expect(done.querySelector(".opt")).toBeNull();
  });

  test("an answer the school did not take keeps the options for a new try", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: false, message_key: "api.letters.confirm.rejected", message: "nicht übernommen" }, calls);
    const letter = letterWith(null);
    openDetail(window, letter, OPEN_ANSWER);
    card(window).querySelectorAll(".opt.letter-choice")[0].click();
    const pending = answer(window, letter, CHOICE, false, false);
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    const block = card(window);
    expect(block.querySelector(".letter-answer-send").disabled).toBe(false);
    expect(block.querySelector(".letter-confirm-reload")).toBeNull();
    expect(block.textContent).toContain("nicht übernommen");
  });

  test("an unclear outcome offers to read the letter again inside the app", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: false, message_key: "api.letters.confirm.uncertain", message: "unklar" }, calls);
    const letter = letterWith(null);
    openDetail(window, letter, OPEN_ANSWER);
    card(window).querySelectorAll(".opt.letter-choice")[0].click();
    const pending = answer(window, letter, CHOICE, false, false);
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    expect(card(window).querySelector(".letter-confirm-reload")).not.toBeNull();
  });

  test("an editable answer loads the form and sends the change with the edit flag", async () => {
    const { window } = loadApp();
    const calls = [];
    const answers = {
      "api/letters/answer": { ok: true, choice: { mode: "radio", multiple: false, options: [{ id: "a1", label: "Ja", selected: true }, { id: "b2", label: "Nein", selected: false }] }, can_reply: true, text: "Gern" },
      "api/letters/confirm": { ok: true, message_key: "api.letters.edit.ok", confirmed_at: "2026-09-04T10:00:00", answer: ["Nein"] },
    };
    window.fetch = (url, options) => {
      const path = Object.keys(answers).find((key) => String(url).includes(key));
      if (path) calls.push({ url: String(url), body: options && options.body ? JSON.parse(options.body) : null });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(path ? answers[path] : {}) });
    };
    const letter = letterWith(null);
    openDetail(window, letter, { type: "answered", open: false, done: true, sendable: false, confirmed_at: "", editable: true });
    await window.eval("(function (letter) { return openAnswerEdit(letter); })")(letter);
    const editing = card(window);
    expect(editing.querySelectorAll(".opt.letter-choice")[0].getAttribute("aria-pressed")).toBe("true");
    expect(editing.querySelector("textarea").value).toBe("Gern");
    editing.querySelectorAll(".opt.letter-choice")[1].click();
    const choice = window.eval("state.letterDetail.letter.answerEdit.choice");
    const pending = answer(window, letter, choice, true, true);
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    expect(calls[0].url).toContain("api/letters/answer");
    expect(calls[1].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2", choices: ["b2"], text: "Gern", edit: true });
    const done = card(window);
    expect(done.querySelector(".letter-answer").textContent).toBe(window.eval('t("letters.confirm.answerText", { answer: "Nein" })'));
    expect(done.querySelector(".letter-answer-edit")).not.toBeNull();
  });

  test("the letter detail never links to the school website or opens a new tab", () => {
    const { window } = loadApp();
    const letter = letterWith(null);
    for (const confirmation of [OPEN_ANSWER, OPEN_CHOICE, OPEN_SEEN, DONE_SEEN]) {
      openDetail(window, letter, confirmation);
      const view = window.eval("letterDetailView()");
      for (const anchor of view.querySelectorAll("a[href]")) expect(anchor.getAttribute("href").includes("/iserv/")).toBe(false);
      expect(view.querySelector("[target=_blank]")).toBeNull();
    }
  });
});

describe("review fixes for answers", () => {
  test("a choice letter known only from the list never offers the read button", () => {
    const { window } = loadApp();
    const listed = { type: "confirmation", open: true, done: false, sendable: true, can_reply: false, confirmed_at: "" };
    const block = renderBlock(window, letterWith(listed), { confirmation: null });
    expect(block.querySelector("button.confirm-action:not(.ghost)")).toBeNull();
    expect(block.textContent).not.toContain(window.eval('t("letters.confirm.action")'));
    expect(block.querySelector(".letter-confirm-reload")).not.toBeNull();
  });

  test("an edit that empties the text sends an empty text and the question says so", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, { ok: true, message_key: "api.letters.edit.ok", confirmed_at: "2026-09-04T10:00:00", answer: [] }, calls);
    const letter = letterWith(null);
    openDetail(window, letter, { type: "answered", open: false, done: true, sendable: false, confirmed_at: "", editable: true });
    letter.answerEdit = { choice: null, can_reply: true };
    letter.replyDraft = "   ";
    const pending = answer(window, letter, null, true, true);
    expect(window.eval("state.sheet().querySelector('.dlg-quote').textContent")).toBe(window.eval('t("letters.confirm.emptyText")'));
    window.eval("state.sheet().querySelectorAll('.btn-stack button')[0]").click();
    await pending;
    expect(calls[0].body).toEqual({ connection_id: "", letter_id: "1", recipient_id: "2", text: "", edit: true });
  });

  test("several answers are joined the way the language writes lists", () => {
    const { window } = loadApp();
    const block = renderBlock(window, letterWith(null), {
      confirmation: { type: "confirmation", open: false, done: true, sendable: false, confirmed_at: "", answer: ["Kuchen", "Getraenke", "Aufbau"] },
    });
    const expected = new Intl.ListFormat("de", { style: "long", type: "conjunction" }).format(["Kuchen", "Getraenke", "Aufbau"]);
    expect(block.querySelector(".letter-answer").textContent).toBe(window.t("letters.confirm.answerText", { answer: expected }));
  });

  test("a failure note appears once on every kind of card", () => {
    const { window } = loadApp();
    const letter = letterWith(null);
    letter.confirmationFailure = { message: "Nur einmal" };
    for (const confirmation of [OPEN_ANSWER, DONE_SEEN, OPEN_SEEN]) {
      openDetail(window, letter, confirmation);
      expect(card(window).textContent.split("Nur einmal").length - 1).toBe(1);
    }
  });
});
