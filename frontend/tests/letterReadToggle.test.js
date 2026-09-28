import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

describe("letters: opening marks read", () => {
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

describe("letters: unread mirrors IServ exactly, no mark-unread UI", () => {
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

describe("letters: Auswählen/Fertig toggle in the sticky toolbar", () => {
  function renderLetters(window, tab, data) {
    const run = window.eval("(function (tab, data) { state.lettersTab = tab; state.letters = data; return lettersView(); })");
    return run(tab, data);
  }

  test("Auswählen button is present, disappears in multi-select, and the sticky bar's round button ends selection", () => {
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

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function slowLetters(window) {
  const pending = {};
  window.fetch = (url) => {
    const target = new URL(String(url));
    if (!target.pathname.endsWith("api/letters/detail")) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    const id = target.searchParams.get("letter_id");
    return new Promise((resolve) => {
      pending[id] = () => resolve({ ok: true, status: 200, json: () => Promise.resolve({ body_html: `<p>${id}</p>`, attachments: [] }) });
    });
  };
  return pending;
}

async function booted() {
  const { window } = loadApp();
  for (let round = 0; round < 6; round += 1) await tick();
  window.clearTimeout(window.eval("bootWatchdog"));
  window.eval('state.detached = false; state.view = "post"; state.lettersTab = "current";');
  return window;
}

describe("letters: a detail that arrives late", () => {
  test("opening a second letter while the first loads keeps the second", async () => {
    const window = await booted();
    const pending = slowLetters(window);
    const first = evalWith(window, "openLetter(testArgs[0])", { letter_id: "A", recipient_id: "r", title: "A", unread: false });
    const second = evalWith(window, "openLetter(testArgs[0])", { letter_id: "B", recipient_id: "r", title: "B", unread: false });
    await tick();
    pending.B();
    await second;
    pending.A();
    await first;
    expect(window.eval("state.letterDetail.letter.letter_id")).toBe("B");
    expect(window.eval("state.letterDetail.detail.body_html")).toBe("<p>B</p>");
  });

  test("going back while a letter loads does not open it again", async () => {
    const window = await booted();
    const pending = slowLetters(window);
    const open = evalWith(window, "openLetter(testArgs[0])", { letter_id: "A", recipient_id: "r", title: "A", unread: false });
    await tick();
    window.eval("leaveLetterDetail()");
    pending.A();
    await open;
    expect(window.eval("state.letterDetail")).toBe(null);
  });
});

describe("letters: one request at a time for an unread letter", () => {
  test("the letter is marked seen only after its detail arrived, never at the same time", async () => {
    const window = await booted();
    const calls = [];
    let release;
    window.fetch = (url) => {
      const path = new URL(String(url)).pathname;
      calls.push(path.split("/").slice(-2).join("/"));
      if (path.endsWith("api/letters/detail")) {
        return new Promise((resolve) => {
          release = () => resolve({ ok: true, status: 200, json: () => Promise.resolve({ body_html: "<p>A</p>", attachments: [] }) });
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ read: 1 }) });
    };
    const letter = evalWith(window, "state.letters = { tab: 'current', letters: [testArgs[0]] }; state.letters.letters[0]", { letter_id: "A", recipient_id: "r", title: "A", unread: true });
    const open = evalWith(window, "openLetter(state.letters.letters[0])");
    await tick();
    expect(calls).toEqual(["letters/detail"]);
    expect(letter.unread).toBe(false);
    release();
    await open;
    expect(calls).toEqual(["letters/detail", "letters/seen"]);
  });

  test("a detail that fails puts the unread mark back and marks nothing", async () => {
    const window = await booted();
    const calls = [];
    window.fetch = (url) => {
      calls.push(new URL(String(url)).pathname.split("/").slice(-2).join("/"));
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ error: "upstream" }) });
    };
    const letter = evalWith(window, "state.letters = { tab: 'current', letters: [testArgs[0]] }; state.letters.letters[0]", { letter_id: "A", recipient_id: "r", title: "A", unread: true });
    await evalWith(window, "openLetter(state.letters.letters[0])");
    expect(calls).toEqual(["letters/detail"]);
    expect(letter.unread).toBe(true);
  });
});

describe("letters: the same unread letter opened twice", () => {
  function twoOpens(window) {
    const calls = [];
    const answers = [];
    window.fetch = (url) => {
      const path = new URL(String(url)).pathname;
      calls.push(path.split("/").slice(-2).join("/"));
      if (path.endsWith("api/letters/detail")) return new Promise((resolve) => answers.push(resolve));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ read: 1 }) });
    };
    const letter = evalWith(window, "state.letters = { tab: 'current', letters: [testArgs[0]] }; state.letters.letters[0]", { letter_id: "A", recipient_id: "r", title: "A", unread: true });
    const first = evalWith(window, "openLetter(state.letters.letters[0])");
    const second = evalWith(window, "openLetter(state.letters.letters[0])");
    const failed = { ok: false, status: 500, json: () => Promise.resolve({ error: "upstream" }) };
    const arrived = { ok: true, status: 200, json: () => Promise.resolve({ body_html: "<p>A</p>", attachments: [] }) };
    return { calls, answers, letter, first, second, failed, arrived };
  }

  test("a failed first open does not bring the unread mark back after the second open succeeded", async () => {
    const window = await booted();
    const run = twoOpens(window);
    await tick();
    run.answers[0](run.failed);
    await run.first;
    run.answers[1](run.arrived);
    await run.second;
    await tick();
    expect(run.letter.unread).toBe(false);
    expect(run.calls).toEqual(["letters/detail", "letters/detail", "letters/seen"]);
  });

  test("a first open that fails after the second one succeeded leaves the letter read", async () => {
    const window = await booted();
    const run = twoOpens(window);
    await tick();
    run.answers[1](run.arrived);
    await run.second;
    run.answers[0](run.failed);
    await run.first;
    await tick();
    expect(run.letter.unread).toBe(false);
    expect(run.calls).toEqual(["letters/detail", "letters/detail", "letters/seen"]);
  });

  test("when both opens fail the letter is unread again and nothing is marked", async () => {
    const window = await booted();
    const run = twoOpens(window);
    await tick();
    run.answers[0](run.failed);
    await run.first;
    expect(run.letter.unread).toBe(false);
    run.answers[1](run.failed);
    await run.second;
    expect(run.letter.unread).toBe(true);
    expect(run.calls).toEqual(["letters/detail", "letters/detail"]);
  });
});
