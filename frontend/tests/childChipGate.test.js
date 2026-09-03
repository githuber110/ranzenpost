import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderHeaderFor(window, view, childCount) {
  const run = window.eval(`
    (function (view, childCount) {
      state.children = childCount === 1
        ? [{ child_id: "c1", name: "Alice", class_name: "3b" }]
        : [
            { child_id: "c1", name: "Alice", class_name: "3b" },
            { child_id: "c2", name: "Bella", class_name: "1a" },
          ];
      state.childId = "c1";
      return header(view).outerHTML;
    })
  `);
  return run(view, childCount);
}

describe("[C15] [P92] child chip only where child context acts", () => {
  test("timetable view with >1 child renders the child-switch chip", () => {
    const { window } = loadApp();
    const html = renderHeaderFor(window, "timetable", 2);
    expect(html).toContain("child-switch");
    expect(html).toContain("Alice");
  });

  test("overview view with >1 child renders no chip", () => {
    const { window } = loadApp();
    const html = renderHeaderFor(window, "overview", 2);
    expect(html).not.toContain("child-switch");
  });

  test("letters/pinboard/conferences/settings views render no chip", () => {
    const { window } = loadApp();
    for (const view of ["letters", "pinboard", "conferences", "settings"]) {
      const html = renderHeaderFor(window, view, 2);
      expect(html).not.toContain("child-switch");
    }
  });

  test("exactly 1 child renders no chip anywhere, not even on timetable", () => {
    const { window } = loadApp();
    const html = renderHeaderFor(window, "timetable", 1);
    expect(html).not.toContain("child-switch");
  });
});

describe("[C15] letter card child tag gated on >1 child", () => {
  test("child tag hidden with a single child", () => {
    const { window } = loadApp();
    const run = window.eval(`
      (function () {
        state.children = [{ child_id: "c1", name: "Alice" }];
        return letterRow({ title: "Test", sender: "Frau X", child: "Alice", recipients: null, unread: false }).outerHTML;
      })
    `);
    const html = run();
    expect(html).not.toContain("tag soft");
  });

  test("child tag shown with more than one child", () => {
    const { window } = loadApp();
    const run = window.eval(`
      (function () {
        state.children = [{ child_id: "c1", name: "Alice" }, { child_id: "c2", name: "Bella" }];
        return letterRow({ title: "Test", sender: "Frau X", child: "Alice", recipients: null, unread: false }).outerHTML;
      })
    `);
    const html = run();
    expect(html).toContain("tag soft");
    expect(html).toContain("Alice");
  });
});
