import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function catalogue() {
  const { window } = loadApp();
  return window.RanzenpostBlocks;
}

describe("the block catalogue is one shared list with rules", () => {
  test("ten blocks, each with a module, an area, two limits and a default size", () => {
    const blocks = catalogue();
    expect(blocks.blockKeys()).toEqual(["today", "next_lesson", "week", "letters", "noticeboard", "absences", "conferences", "holidays", "changes", "chat"]);
    for (const block of blocks.BLOCK_CATALOGUE) {
      expect(blocks.AREA_MODULES[block.area]).toContain(block.module);
      expect(block.compact).toBeGreaterThanOrEqual(1);
      expect(block.normal).toBeGreaterThanOrEqual(block.compact);
      expect(blocks.SIZES).toContain(block.size);
    }
  });

  test("the limit follows the size and an unknown size falls back to the block default", () => {
    const blocks = catalogue();
    const letters = blocks.blockOf("letters");
    expect(blocks.limitOf(letters, "compact")).toBe(3);
    expect(blocks.limitOf(letters, "normal")).toBe(5);
    expect(blocks.limitOf(letters, "huge")).toBe(5);
    expect(blocks.sizeOf(letters, "compact")).toBe("compact");
  });

  test("shown items stop at the limit and say whether more exist", () => {
    const blocks = catalogue();
    const items = ["a", "b", "c", "d"];
    expect(blocks.shownItems(blocks.blockOf("absences"), "compact", items)).toEqual({ items: ["a", "b"], more: true });
    expect(blocks.shownItems(blocks.blockOf("absences"), "normal", items)).toEqual({ items, more: false });
    expect(blocks.hasContent([])).toBe(false);
    expect(blocks.hasContent(["x"])).toBe(true);
  });

  test("only blocks of modules the account has are offered, per surface", () => {
    const blocks = catalogue();
    const on = (name) => name === "timetable" || name === "messenger";
    expect(blocks.offeredBlocks(on).map((block) => block.key)).toEqual(["today", "next_lesson", "week", "holidays", "changes", "chat"]);
    expect(blocks.offeredBlocks(on, "card").map((block) => block.key)).toEqual(["today", "next_lesson", "week", "holidays", "changes"]);
  });

  test("the overview list drops unknown keys, duplicates and blocks that are not offered", () => {
    const blocks = catalogue();
    const offered = blocks.offeredBlocks((name) => name !== "messenger");
    const kept = blocks.normalizeOverviewBlocks([{ key: "chat" }, { key: "letters", size: "compact" }, "today", { key: "letters" }, { key: "nope" }], offered);
    expect(kept).toEqual([{ key: "letters", size: "compact" }, { key: "today", size: "normal" }]);
    expect(blocks.normalizeOverviewBlocks([], offered)).toEqual([]);
  });

  test("a missing overview list defaults to the six agreed blocks, filtered to what is offered", () => {
    const blocks = catalogue();
    const allOffered = blocks.offeredBlocks(() => true);
    expect(blocks.normalizeOverviewBlocks(null, allOffered).map((entry) => entry.key)).toEqual(["today", "letters", "noticeboard", "conferences", "changes", "chat"]);
    const withoutMessenger = blocks.offeredBlocks((name) => name !== "messenger");
    expect(blocks.normalizeOverviewBlocks(null, withoutMessenger).map((entry) => entry.key)).toEqual(["today", "letters", "noticeboard", "conferences", "changes"]);
  });

  test("hidden blocks are the offered ones that are not enabled", () => {
    const blocks = catalogue();
    const offered = blocks.offeredBlocks(() => true);
    const hidden = blocks.hiddenBlocks([{ key: "today", size: "normal" }, { key: "chat", size: "compact" }], offered);
    expect(hidden.map((block) => block.key)).toEqual(["next_lesson", "week", "letters", "noticeboard", "absences", "conferences", "holidays", "changes"]);
  });

  test("navigation keeps known areas in order and appends the missing ones", () => {
    const blocks = catalogue();
    expect(blocks.normalizeNavigation(["conferences", "nope", "post", "conferences"])).toEqual(["conferences", "post", "timetable", "absence", "messenger"]);
    expect(blocks.normalizeNavigation(undefined)).toEqual(blocks.DEFAULT_NAVIGATION);
  });

  test("moving a key swaps it with its neighbour and stops at the ends", () => {
    const blocks = catalogue();
    expect(blocks.moveKey(["a", "b", "c"], "c", -1)).toEqual(["a", "c", "b"]);
    expect(blocks.moveKey(["a", "b", "c"], "a", -1)).toEqual(["a", "b", "c"]);
    expect(blocks.moveKey(["a", "b", "c"], "a", 1)).toEqual(["b", "a", "c"]);
    expect(blocks.moveKey(["a", "b", "c"], "x", 1)).toEqual(["a", "b", "c"]);
  });
});

describe("the bottom bar never has more than five entries", () => {
  const areas = (count) => ["timetable", "absence", "post", "messenger", "conferences", "a", "b", "c", "d", "e"].slice(0, count);

  test("no module: the overview alone", () => {
    expect(catalogue().barLayout(areas(0))).toEqual({ bar: ["overview"], more: [] });
  });

  test("three modules: everything in the bar, no More", () => {
    expect(catalogue().barLayout(areas(3))).toEqual({ bar: ["overview", "timetable", "absence", "post"], more: [] });
  });

  test("four modules fill the five slots exactly", () => {
    expect(catalogue().barLayout(areas(4))).toEqual({ bar: ["overview", "timetable", "absence", "post", "messenger"], more: [] });
  });

  test("five modules: the first three plus More, the rest under More", () => {
    expect(catalogue().barLayout(areas(5))).toEqual({ bar: ["overview", "timetable", "absence", "post", "more"], more: ["messenger", "conferences"] });
  });

  test("six and ten modules keep five entries and grow the More list", () => {
    expect(catalogue().barLayout(areas(6)).bar).toHaveLength(5);
    expect(catalogue().barLayout(areas(6)).more).toEqual(["messenger", "conferences", "a"]);
    expect(catalogue().barLayout(areas(10)).bar).toEqual(["overview", "timetable", "absence", "post", "more"]);
    expect(catalogue().barLayout(areas(10)).more).toHaveLength(7);
  });

  test("a lowered limit keeps the same rule", () => {
    expect(catalogue().barLayout(areas(5), 3)).toEqual({ bar: ["overview", "timetable", "more"], more: ["absence", "post", "messenger", "conferences"] });
  });
});
