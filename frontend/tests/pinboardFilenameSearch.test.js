import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderPinboard(window, data) {
  const run = window.eval("(function (data) { state.pinboardSearch = ''; state.pinboard = data; return pinboardView(); })");
  return run(data);
}

function typeInto(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

describe("[C10] pinboard search: filenames + folder/column badges are in the haystack", () => {
  test("a search hitting only the attachment filename still finds the post (real Busplan case)", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        {
          id: 1,
          title: "Jahrgang 1",
          text: "Bitte beachten",
          column_title: "",
          unread: false,
          attachments: [{ filename: "Busplan_2026.pdf" }],
        },
        { id: 2, title: "Wandertag", text: "Wir gehen in den Wald", column_title: "", unread: false },
      ],
    };
    const view = renderPinboard(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "busplan");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Jahrgang 1");
  });

  test("when the hit is only in the filename, the row-sub shows the filename instead of the text preview", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        {
          id: 1,
          title: "Jahrgang 1",
          text: "Bitte beachten, es gibt Neuigkeiten",
          column_title: "",
          unread: false,
          attachments: [{ filename: "Busplan_2026.pdf" }],
        },
      ],
    };
    const view = renderPinboard(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "busplan");
    const sub = view.querySelector(".rows .row .row-sub");
    expect(sub.textContent).toBe("Busplan_2026.pdf");
    expect(sub.textContent).not.toContain("Bitte beachten");
  });

  test("when the query also matches the text, the row-sub keeps showing the text preview", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        {
          id: 1,
          title: "Jahrgang 1",
          text: "Bitte beachten den Busplan",
          column_title: "",
          unread: false,
          attachments: [{ filename: "Busplan_2026.pdf" }],
        },
      ],
    };
    const view = renderPinboard(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "busplan");
    const sub = view.querySelector(".rows .row .row-sub");
    expect(sub.textContent).toContain("Bitte beachten");
  });

  test("folder_title and column_title are searchable too", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        { id: 1, title: "Ohne Treffer", text: "nichts", folder_title: "Klasse 2b", column_title: "Wichtig", unread: false },
        { id: 2, title: "Auch ohne", text: "nichts", folder_title: "Klasse 3a", column_title: "Sonstiges", unread: false },
      ],
    };
    const view = renderPinboard(window, data);
    const input = view.querySelector(".search-input");
    typeInto(window, input, "wichtig");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Ohne Treffer");
  });
});
