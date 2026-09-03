import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderPinboard(window, data) {
  const run = window.eval("(function (data) { state.pinboard = data; return pinboardView(); })");
  return run(data);
}

describe("[P98] pinboard sort hint", () => {
  test("shows a 'Neueste zuerst' overline above the feed", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [
        { id: 2, title: "B", column_title: "", unread: false },
        { id: 1, title: "A", column_title: "", unread: false },
      ],
    };
    const view = renderPinboard(window, data);
    expect(view.textContent).toContain("Neueste zuerst");
  });
});
