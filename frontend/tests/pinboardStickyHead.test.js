import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderPinboard(window, data) {
  const run = window.eval("(function (data) { state.pinboard = data; return pinboardView(); })");
  return run(data);
}

describe("[P113] pinboard header stays sticky", () => {
  test("chips sit inside the sticky head, title lives in the compact .header bar", () => {
    const { window } = loadApp();
    const data = {
      folders: [],
      feed: [{ id: 1, title: "Beitrag", text: "Text", column_title: "", unread: false }],
    };
    const view = renderPinboard(window, data);
    const head = view.querySelector(".list-head");
    expect(head).not.toBeNull();
    expect(head.querySelector(".page-title")).toBeNull();
    expect(head.querySelector(".chipbar")).not.toBeNull();
    expect(head.contains(view.querySelector(".rows"))).toBe(false);
    const bar = window.eval("header('pinboard')");
    expect(bar.querySelector(".header-title").textContent).not.toBe("");
  });
});
