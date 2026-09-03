import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[C01] letters: opening marks read", () => {
  test("openLetter marks the letter read optimistically before the fetch settles", () => {
    const { window } = loadApp();
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: true };
    const run = window.eval("(function (letter) { return openLetter(letter); })");
    run(letter);
    expect(letter.unread).toBe(false);
  });

  test("openLetter leaves an already-read letter untouched (no seen call)", () => {
    const { window } = loadApp();
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false };
    const run = window.eval("(function (letter) { return openLetter(letter); })");
    run(letter);
    expect(letter.unread).toBe(false);
  });
});

describe("[P126] letters: unread mirrors IServ exactly, no mark-unread UI", () => {
  test("there is no markLetterUnread function left in the app", () => {
    const { window } = loadApp();
    expect(window.eval("typeof markLetterUnread")).toBe("undefined");
  });

  test("letterDetailView offers no 'Als ungelesen markieren' button outside the archive", () => {
    const { window } = loadApp();
    window.eval(
      "state.letterDetail = { letter: { letter_id: '1', recipient_id: '2', title: 'Infobrief', unread: false }, detail: { body_html: '<p>x</p>', attachments: [] } };" +
        "state.lettersTab = 'current';"
    );
    const view = window.eval("letterDetailView()");
    const buttons = Array.from(view.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons.some((text) => text.includes("ungelesen"))).toBe(false);
  });

  test("letterDetailView offers no 'Als ungelesen markieren' button in the archive tab either", () => {
    const { window } = loadApp();
    window.eval(
      "state.letterDetail = { letter: { letter_id: '1', recipient_id: '2', title: 'Infobrief', unread: false }, detail: { body_html: '<p>x</p>', attachments: [] } };" +
        "state.lettersTab = 'archive';"
    );
    const view = window.eval("letterDetailView()");
    const buttons = Array.from(view.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons.some((text) => text.includes("ungelesen"))).toBe(false);
  });

  test("the swipe-menu letter actions sheet never offers an unread option", () => {
    const { window } = loadApp();
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false };
    window.eval("state.lettersTab = 'current';");
    const run = window.eval("(function (letter) { return letterActionsSheet(letter); })");
    const sheetEl = run(letter);
    const buttons = Array.from(sheetEl.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons.some((text) => text.includes("ungelesen"))).toBe(false);
  });
});

describe("[P126] letters: Auswählen/Fertig toggle in the sticky toolbar", () => {
  function renderLetters(window, tab, data) {
    const run = window.eval("(function (tab, data) { state.lettersTab = tab; state.letters = data; return lettersView(); })");
    return run(tab, data);
  }

  test("[P156] Auswählen button is present, disappears in multi-select, and the sticky bar's round button ends selection", () => {
    const { window } = loadApp();
    const data = { tab: "current", letters: [{ letter_id: "1", recipient_id: "2", title: "Infobrief", unread: true }] };
    const view = renderLetters(window, "current", data);
    const toolsButtons = Array.from(view.querySelectorAll(".letters-tools button")).map((b) => b.textContent);
    expect(toolsButtons).toContain("Auswählen");
    expect(window.eval("state.lettersSelectMode")).toBe(false);

    window.eval("toggleLetterSelectMode()");
    expect(window.eval("state.lettersSelectMode")).toBe(true);
    const viewAfter = renderLetters(window, "current", data);
    const toolsButtonsAfter = Array.from(viewAfter.querySelectorAll(".letters-tools button")).map((b) => b.textContent);
    expect(toolsButtonsAfter).not.toContain("Fertig");
    expect(toolsButtonsAfter).not.toContain("Auswählen");
    expect(viewAfter.querySelector(".select-bar-cancel")).not.toBeNull();

    window.eval("exitLetterSelectMode()");
    expect(window.eval("state.lettersSelectMode")).toBe(false);
  });
});
