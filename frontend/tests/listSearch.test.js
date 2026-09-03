import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderPinboard(window, data) {
  const run = window.eval("(function (data) { state.pinboardSearch = ''; state.pinboard = data; return pinboardView(); })");
  return run(data);
}

function renderLetters(window, data) {
  const run = window.eval("(function (data) { state.lettersSearch = ''; state.lettersTab = 'current'; state.letters = data; return lettersView(); })");
  return run(data);
}

function typeInto(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

describe("[P114] pinboard full-text search", () => {
  test("typing filters the feed by title+text, clearing restores it, matching is case-insensitive", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        { id: 1, title: "Elternabend", text: "Bitte kommt zahlreich", column_title: "", unread: false },
        { id: 2, title: "Wandertag", text: "Wir gehen in den Wald", column_title: "", unread: false },
      ],
    };
    const view = renderPinboard(window, data);
    expect(view.querySelectorAll(".rows .row").length).toBe(2);

    const input = view.querySelector(".search-input");
    typeInto(window, input, "WALD");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Wandertag");

    typeInto(window, input, "");
    expect(view.querySelectorAll(".rows .row").length).toBe(2);
  });

  test("clear button empties the field and restores the full feed", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        { id: 1, title: "Elternabend", text: "Bitte kommt zahlreich", column_title: "", unread: false },
        { id: 2, title: "Wandertag", text: "Wir gehen in den Wald", column_title: "", unread: false },
      ],
    };
    const view = renderPinboard(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "wandertag");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    view.querySelector(".search-clear").dispatchEvent(new window.Event("click", { bubbles: true }));
    expect(input.value).toBe("");
    expect(view.querySelectorAll(".rows .row").length).toBe(2);
  });
});

describe("[P114] letters full-text search", () => {
  test("typing filters by title+sender+child, clearing restores it, matching is case-insensitive", () => {
    const { window } = loadApp();
    const data = {
      tab: "current",
      letters: [
        { letter_id: "1", recipient_id: "a", title: "Infobrief Sportfest", sender: "Frau Muster", unread: true },
        { letter_id: "2", recipient_id: "b", title: "Elternsprechtag", sender: "Herr Beispiel", unread: false },
      ],
    };
    const view = renderLetters(window, data);
    expect(view.querySelectorAll(".rows .row").length).toBe(2);

    const input = view.querySelector(".search-input");
    typeInto(window, input, "SPORTFEST");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Infobrief Sportfest");

    typeInto(window, input, "");
    expect(view.querySelectorAll(".rows .row").length).toBe(2);
  });
});

describe("[P115] letters search matches body text and attachment filenames", () => {
  test("matches on body text that is not in title/sender/badges", () => {
    const { window } = loadApp();
    const data = {
      tab: "current",
      letters: [
        { letter_id: "1", recipient_id: "a", title: "Infobrief", sender: "Frau Muster", body_text: "Bitte denkt an die Schwimmsachen", unread: true },
        { letter_id: "2", recipient_id: "b", title: "Elternsprechtag", sender: "Herr Beispiel", body_text: "Termine ab Montag", unread: false },
      ],
    };
    const view = renderLetters(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "SCHWIMMSACHEN");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Infobrief");
  });

  test("matches on an attachment filename that is not in title/sender/badges", () => {
    const { window } = loadApp();
    const data = {
      tab: "current",
      letters: [
        {
          letter_id: "1",
          recipient_id: "a",
          title: "Infobrief",
          sender: "Frau Muster",
          attachments: [{ filename: "einladung-sommerfest.pdf", url: "api/letters/attachment/x" }],
          unread: true,
        },
        { letter_id: "2", recipient_id: "b", title: "Elternsprechtag", sender: "Herr Beispiel", unread: false },
      ],
    };
    const view = renderLetters(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "sommerfest");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Infobrief");
  });
});
