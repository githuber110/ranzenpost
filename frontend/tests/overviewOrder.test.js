import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function order(window, areas, counts) {
  return window.eval(
    `orderOverviewAreas(${JSON.stringify(areas)}, ${JSON.stringify(counts)})`
  );
}

describe("[P217] orderOverviewAreas is a pure sort: today first, then fresh areas, then the rest", () => {
  test("everything read leaves the base order unchanged", () => {
    const { window } = loadApp();
    const areas = ["today", "upcoming", "letters", "pinboard", "messenger"];
    const counts = { upcoming: 0, letters: 0, pinboard: 0, messenger: 0 };
    expect(order(window, areas, counts)).toEqual(areas);
  });

  test("one area with new items moves directly behind today", () => {
    const { window } = loadApp();
    const areas = ["today", "upcoming", "letters", "pinboard", "messenger"];
    const counts = { upcoming: 0, letters: 3, pinboard: 0, messenger: 0 };
    expect(order(window, areas, counts)).toEqual(["today", "letters", "upcoming", "pinboard", "messenger"]);
  });

  test("several areas with new items keep their base order among themselves", () => {
    const { window } = loadApp();
    const areas = ["today", "upcoming", "letters", "pinboard", "messenger"];
    const counts = { upcoming: 0, letters: 0, pinboard: 2, messenger: 1 };
    expect(order(window, areas, counts)).toEqual(["today", "pinboard", "messenger", "upcoming", "letters"]);
  });

  test("today never moves, even if it somehow carried a count", () => {
    const { window } = loadApp();
    const areas = ["today", "upcoming", "letters", "pinboard", "messenger"];
    const counts = { today: 5, upcoming: 0, letters: 0, pinboard: 0, messenger: 0 };
    expect(order(window, areas, counts)).toEqual(areas);
  });

  test("an area missing from the counts map is treated as zero", () => {
    const { window } = loadApp();
    const areas = ["today", "upcoming", "letters", "pinboard", "messenger"];
    const counts = { letters: 2 };
    expect(order(window, areas, counts)).toEqual(["today", "letters", "upcoming", "pinboard", "messenger"]);
  });
});

describe("[P217] overviewNewCount reuses the same counters as the tab badges", () => {
  function seed(window) {
    window.eval(`
      state.children = [{ child_id: "c1", name: "Alice", class_name: "3b" }];
      state.letters = { tab: "current", letters: [{ letter_id: "1", recipient_id: "r", title: "A", unread: true }] };
      state.pinboard = { folders: [], feed: [{ id: 1, title: "B", text: "", unread: true }] };
      state.messengerRooms = { rooms: [{ room_id: "!a:x", name: "R", unread_count: 4 }] };
    `);
  }

  test("today and upcoming are always zero", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('overviewNewCount("today")')).toBe(0);
    expect(window.eval('overviewNewCount("upcoming")')).toBe(0);
  });

  test("letters, pinboard and messenger match their tab badge counters exactly", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('overviewNewCount("letters")')).toBe(window.eval("lettersUnreadCount()"));
    expect(window.eval('overviewNewCount("pinboard")')).toBe(window.eval("pinboardUnreadCount()"));
    expect(window.eval('overviewNewCount("messenger")')).toBe(window.eval("messengerUnreadTotal()"));
    expect(window.eval('overviewNewCount("letters")')).toBe(1);
    expect(window.eval('overviewNewCount("pinboard")')).toBe(1);
    expect(window.eval('overviewNewCount("messenger")')).toBe(4);
  });
});

describe("[P217] the section peek arrow badge", () => {
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
