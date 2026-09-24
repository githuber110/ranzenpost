import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("the overview order is the user's, orderOverviewAreas is gone", () => {
  test("no freshness sort survives in the app", () => {
    const { window } = loadApp();
    expect(window.eval("typeof orderOverviewAreas")).toBe("undefined");
    expect(window.eval("typeof applyOverviewOrder")).toBe("undefined");
  });
});

describe("overviewNewCount reuses the same counters as the tab badges", () => {
  function seed(window) {
    window.eval(`
      state.children = [{ key: "c1", name: "Alice", class_name: "3b" }];
      state.letters = { tab: "current", letters: [{ letter_id: "1", recipient_id: "r", title: "A", unread: true }] };
      state.pinboard = { folders: [], feed: [{ id: 1, title: "B", text: "", unread: true }] };
      state.messengerRooms = { rooms: [{ room_id: "!a:x", name: "R", unread_count: 4 }] };
    `);
  }

  test("today and absences are always zero", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('overviewNewCount("today")')).toBe(0);
    expect(window.eval('overviewNewCount("absences")')).toBe(0);
  });

  test("letters, pinboard and messenger match their tab badge counters exactly", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('overviewNewCount("letters")')).toBe(window.eval("lettersUnreadCount()"));
    expect(window.eval('overviewNewCount("noticeboard")')).toBe(window.eval("pinboardUnreadCount()"));
    expect(window.eval('overviewNewCount("chat")')).toBe(window.eval("messengerUnreadTotal()"));
    expect(window.eval('overviewNewCount("letters")')).toBe(1);
    expect(window.eval('overviewNewCount("noticeboard")')).toBe(1);
    expect(window.eval('overviewNewCount("chat")')).toBe(4);
  });
});

describe("the section peek arrow badge", () => {
  test("no badge when the next section has nothing new", () => {
    const { window } = loadApp();
    const arrow = window.eval(
      '(function () { return overviewPanelArrow(null, 0, 1, { title: "Pinnwand", count: 0 }, 0); })()'
    );
    expect(arrow.querySelector(".badge.panel-arrow-badge")).toBeNull();
    const button = arrow.querySelector("button");
    expect(button.getAttribute("aria-label")).toBe(window.eval('t("overview.arrow.area", { area: "Pinnwand" })'));
  });

  test("badge with the fresh count appears when the next section has something new", () => {
    const { window } = loadApp();
    const arrow = window.eval(
      '(function () { return overviewPanelArrow(null, 0, 1, { title: "Pinnwand", count: 3 }, 0); })()'
    );
    const badge = arrow.querySelector(".badge.panel-arrow-badge");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe(window.eval("badgeText(3)"));
    expect(badge.getAttribute("aria-hidden")).toBe("true");
  });

  test("the aria-label pluralises through tCount(overview.arrow.areaNew)", () => {
    const { window } = loadApp();
    const one = window.eval(
      '(function () { return overviewPanelArrow(null, 0, 1, { title: "Pinnwand", count: 1 }, 0); })()'
    );
    expect(one.querySelector("button").getAttribute("aria-label")).toBe(
      window.eval('tCount("overview.arrow.areaNew", 1, { area: "Pinnwand" })')
    );
    const many = window.eval(
      '(function () { return overviewPanelArrow(null, 0, 1, { title: "Pinnwand", count: 2 }, 0); })()'
    );
    expect(many.querySelector("button").getAttribute("aria-label")).toBe(
      window.eval('tCount("overview.arrow.areaNew", 2, { area: "Pinnwand" })')
    );
    expect(one.querySelector("button").getAttribute("aria-label")).not.toBe(
      many.querySelector("button").getAttribute("aria-label")
    );
  });
});
