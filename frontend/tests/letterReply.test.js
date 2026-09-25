import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const OPEN_SEEN = { type: "seen", open: true, done: false, sendable: true, can_reply: true, confirmed_at: "" };
const DONE_SEEN = { type: "seen", open: false, done: true, sendable: false, confirmed_at: "2026-09-03T14:05:00" };

function letter() {
  return { connection_id: "s1", letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false, confirmation: null };
}

function detailWith(extra) {
  return Object.assign({ body_html: "<p>x</p>", attachments: [], confirmation: null, reply: { available: true } }, extra || {});
}

function renderDetail(window, entry, detail) {
  return window.eval("(function (letter, detail) { state.letterDetail = { letter, detail }; return letterDetailView(); })")(
    entry,
    detail
  );
}

function stubFetch(window, answers, calls) {
  window.fetch = (url, options) => {
    calls.push({ url: String(url), body: JSON.parse(options.body) });
    const next = answers.length > 1 ? answers.shift() : answers[0];
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(next) });
  };
}

function openSheetNode(window) {
  return window.eval("state.sheet && state.sheet()");
}

function typeMessage(window, text) {
  const field = openSheetNode(window).querySelector("textarea.letter-reply-text");
  field.value = text;
  field.dispatchEvent(new window.Event("input"));
  return field;
}

function goToPreview(window, text) {
  typeMessage(window, text);
  openSheetNode(window).querySelector("button.letter-reply-next").click();
  return openSheetNode(window);
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("the reply action on a letter", () => {
  test("a recognised reply form offers one quiet action", () => {
    const { window } = loadApp();
    const view = renderDetail(window, letter(), detailWith());
    const actions = view.querySelectorAll(".letter-reply-action");
    expect(actions.length).toBe(1);
    expect(actions[0].className).toContain("ghost");
    expect(actions[0].textContent).toBe(window.eval('t("letters.reply.action")'));
  });

  test("also after a confirmation made in the app", () => {
    const { window } = loadApp();
    const view = renderDetail(window, letter(), detailWith({ confirmation: DONE_SEEN }));
    expect(view.querySelector(".letter-reply-action")).not.toBeNull();
  });

  test("no action without a recognised form", () => {
    const { window } = loadApp();
    expect(renderDetail(window, letter(), detailWith({ reply: null })).querySelector(".letter-reply-action")).toBeNull();
    expect(renderDetail(window, letter(), detailWith({ reply: {} })).querySelector(".letter-reply-action")).toBeNull();
    expect(renderDetail(window, letter(), detailWith({ reply: { available: "yes" } })).querySelector(".letter-reply-action")).toBeNull();
    expect(renderDetail(window, letter(), detailWith({ reply: undefined })).querySelector(".letter-reply-action")).toBeNull();
  });

  test("no separate action while the confirmation is still open", () => {
    const { window } = loadApp();
    const view = renderDetail(window, letter(), detailWith({ confirmation: OPEN_SEEN }));
    expect(view.querySelector(".letter-reply-action")).toBeNull();
    expect(view.querySelector("button.confirm-action")).not.toBeNull();
  });
});

describe("writing a message to the school", () => {
  test("the sheet asks for text first and offers only the preview as its main button", () => {
    const { window } = loadApp();
    window.eval("openLetterReply")(letter());
    const node = openSheetNode(window);
    expect(node.querySelector(".sheet-title").textContent).toBe(window.eval('t("letters.reply.title")'));
    const buttons = node.querySelectorAll(".sheet-foot button");
    expect(buttons.length).toBe(1);
    expect(buttons[0].className).toBe("btn letter-reply-next");
    expect(buttons[0].disabled).toBe(true);
    expect(node.querySelector("textarea.letter-reply-text").getAttribute("maxlength")).toBe("4000");
  });

  test("blank text never reaches the preview", () => {
    const { window } = loadApp();
    window.eval("openLetterReply")(letter());
    typeMessage(window, "   ");
    openSheetNode(window).querySelector("button.letter-reply-next").click();
    expect(openSheetNode(window).querySelector("textarea.letter-reply-text")).not.toBeNull();
    expect(openSheetNode(window).querySelector(".letter-reply-quote")).toBeNull();
  });

  test("the preview shows the trimmed text and sends nothing on its own", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true }], calls);
    window.eval("openLetterReply")(letter());
    const preview = goToPreview(window, "  Wir kommen gern.  ");
    await settle();
    expect(preview.querySelector(".letter-reply-quote").textContent).toBe("Wir kommen gern.");
    expect(preview.querySelector(".dlg-text").textContent).toBe(window.eval('t("letters.reply.previewText")'));
    expect(preview.querySelectorAll(".sheet-foot button:not(.ghost)").length).toBe(1);
    expect(calls).toEqual([]);
  });

  test("editing goes back with the text kept", () => {
    const { window } = loadApp();
    window.eval("openLetterReply")(letter());
    goToPreview(window, "Hallo").querySelector("button.letter-reply-edit").click();
    expect(openSheetNode(window).querySelector("textarea.letter-reply-text").value).toBe("Hallo");
  });

  test("closing the sheet sends nothing", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true }], calls);
    window.eval("openLetterReply")(letter());
    goToPreview(window, "Hallo");
    window.eval("discardSheet()");
    await settle();
    expect(window.eval("state.sheet")).toBeNull();
    expect(calls).toEqual([]);
  });

  test("sending posts once with the explicit confirmation and a request id, then closes", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true, message_key: "api.letters.reply.ok" }], calls);
    window.eval("openLetterReply")(letter());
    const send = goToPreview(window, " Wir kommen gern. ").querySelector("button.letter-reply-send");
    send.click();
    send.click();
    await settle();
    await settle();
    expect(calls.length).toBe(1);
    expect(calls[0].url).toContain("api/letters/reply");
    const body = calls[0].body;
    expect(body.request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(body).toEqual({
      connection_id: "s1",
      letter_id: "1",
      recipient_id: "2",
      text: "Wir kommen gern.",
      request_id: body.request_id,
      confirmed: true,
    });
    expect(window.eval("state.sheet")).toBeNull();
    expect(window.eval("state.toast.message")).toBe(window.eval('t("letters.reply.sent")'));
    expect(window.eval("state.toast.kind")).toBe("good");
  });

  test("a refusal keeps the preview with the reason, and a retry reuses the same request id", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: false, message_key: "api.letters.reply.upstream", message_vars: { status: 500 } }, { ok: true }], calls);
    window.eval("openLetterReply")(letter());
    goToPreview(window, "Hallo").querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    const after = openSheetNode(window);
    expect(after.querySelector(".letter-reply-quote").textContent).toBe("Hallo");
    expect(after.textContent).toContain(window.eval('t("api.letters.reply.upstream", { status: 500 })'));
    after.querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    expect(calls.length).toBe(2);
    expect(calls[1].body.request_id).toBe(calls[0].body.request_id);
    expect(window.eval("state.sheet")).toBeNull();
  });

  test("a lost or timed out request says the outcome is unclear and keeps the same request id", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [new TypeError("offline"), { ok: true }], calls);
    window.eval("openLetterReply")(letter());
    goToPreview(window, "Hallo").querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    const after = openSheetNode(window);
    expect(after).not.toBeNull();
    const unclear = window.eval('t("api.letters.reply.uncertain")');
    expect(after.textContent).toContain(unclear);
    expect(window.eval("state.toast.message")).toBe(unclear);
    after.querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    expect(calls.length).toBe(2);
    expect(calls[1].body.request_id).toBe(calls[0].body.request_id);
  });

  test("the send waits longer than an ordinary request because the school needs two round trips", async () => {
    const { window } = loadApp();
    const waits = [];
    window.AbortSignal = { timeout: (ms) => ({ ms }) };
    window.fetch = (url, options) => {
      if (String(url).includes("api/letters/reply")) waits.push(options.signal && options.signal.ms);
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
    };
    window.eval("openLetterReply")(letter());
    goToPreview(window, "Hallo").querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    expect(waits).toEqual([window.eval("LETTER_REPLY_TIMEOUT_MS")]);
    expect(waits[0]).toBeGreaterThanOrEqual(90000);
  });

  test("opening the action again starts a new message with a new request id", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true }], calls);
    const entry = letter();
    window.eval("openLetterReply")(entry);
    goToPreview(window, "Eins").querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    window.eval("openLetterReply")(entry);
    expect(openSheetNode(window).querySelector("textarea.letter-reply-text").value).toBe("");
    goToPreview(window, "Zwei").querySelector("button.letter-reply-send").click();
    await settle();
    await settle();
    expect(calls.length).toBe(2);
    expect(calls[1].body.request_id).not.toBe(calls[0].body.request_id);
  });
});
