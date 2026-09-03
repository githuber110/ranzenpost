import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderLetters(window, tab, data) {
  const run = window.eval("(function (tab, data) { state.lettersTab = tab; state.letters = data; return lettersView(); })");
  return run(tab, data);
}

describe("[P112] letters header + toolbar stay sticky", () => {
  test("current tab: segment and toolbar row sit inside the sticky head, title lives in the compact .header bar", () => {
    const { window } = loadApp();
    const data = { tab: "current", letters: [{ letter_id: "1", recipient_id: "2", title: "Infobrief", unread: true }] };
    const view = renderLetters(window, "current", data);
    const head = view.querySelector(".list-head");
    expect(head).not.toBeNull();
    expect(head.querySelector(".page-title")).toBeNull();
    expect(head.querySelector(".segment[role='tablist']")).not.toBeNull();
    expect(head.querySelector(".section-head .letters-tools")).not.toBeNull();
    expect(view.querySelector(".rows")).not.toBeNull();
    expect(head.contains(view.querySelector(".rows"))).toBe(false);
    const bar = window.eval("header('letters')");
    expect(bar.querySelector(".header-title").textContent).not.toBe("");
  });

  test("archive tab: page title and segment still sit inside the sticky head", () => {
    const { window } = loadApp();
    const data = { tab: "archive", letters: [{ letter_id: "1", recipient_id: "2", title: "Altbrief", unread: false }] };
    const view = renderLetters(window, "archive", data);
    const head = view.querySelector(".list-head");
    expect(head).not.toBeNull();
    expect(head.querySelector(".segment[role='tablist']")).not.toBeNull();
    expect(head.querySelector(".section-head .letters-tools")).not.toBeNull();
  });
});
