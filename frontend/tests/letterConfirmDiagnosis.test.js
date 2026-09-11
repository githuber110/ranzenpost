import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const OPEN = { type: "seen", open: true, done: false, sendable: true, confirmed_at: "" };
const FACT_KEYS = [
  "confirmation_marks",
  "confirmation_disabled",
  "confirmation_button",
  "confirmation_fields",
  "confirmation_submits",
  "page_notices",
  "post_status",
  "post_path",
  "post_redirects",
  "response_notices",
  "after_marks",
  "after_disabled",
  "after_button",
];

function letter() {
  return { letter_id: "l1", recipient_id: "r1", title: "Brief", confirmation: Object.assign({}, OPEN) };
}

function answer(window, payload) {
  window.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
}

function card(window, entry, detail) {
  return window.eval("(function (l, d) { return letterConfirmationBlock(l, d); })")(entry, detail);
}

describe("[P257] the confirmation card can show what the school server did", () => {
  test("an open read receipt offers the form's technical details", () => {
    const { window } = loadApp();
    const detail = { confirmation: OPEN, confirmation_evidence: { confirmation_marks: ["SEEN"], confirmation_submits: 1 } };
    expect(card(window, letter(), detail).querySelector(".tech-btn")).not.toBeNull();
  });

  test("without evidence there is no details button", () => {
    const { window } = loadApp();
    expect(card(window, letter(), { confirmation: OPEN }).querySelector(".tech-btn")).toBeNull();
  });

  test("a failed send keeps its message on the card with the answer behind the details button", async () => {
    const { window } = loadApp();
    const entry = letter();
    window.eval("confirmAction = () => Promise.resolve(true);");
    answer(window, {
      ok: false,
      message_key: "api.letters.confirm.rejected",
      diagnosis: { post_status: 200, after_disabled: true },
    });
    await window.eval("(function (l) { return confirmLetterRead(l); })")(entry);
    expect(entry.confirmationFailure).toBeTruthy();
    const node = card(window, entry, { confirmation: OPEN });
    expect(node.textContent).toContain(window.eval("t('api.letters.confirm.rejected')"));
    expect(node.querySelector(".tech-btn")).not.toBeNull();
  });

  test("a send that went through clears an earlier failure", async () => {
    const { window } = loadApp();
    const entry = letter();
    entry.confirmationFailure = { message: "x", diagnosis: null };
    window.eval("confirmAction = () => Promise.resolve(true);");
    answer(window, { ok: true, confirmed_at: "2026-09-11T10:00:00" });
    await window.eval("(function (l) { return confirmLetterRead(l); })")(entry);
    expect(entry.confirmationFailure).toBeNull();
    expect(entry.confirmation.done).toBe(true);
  });

  test("every fact carries a label in the reader's language", () => {
    const { window } = loadApp();
    for (const key of FACT_KEYS) expect(window.eval(`diagnosisLabel("${key}")`)).not.toBe(key);
  });
});
