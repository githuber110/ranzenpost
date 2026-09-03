import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function paginate(window, blocks, budget) {
  const run = window.eval("(function (blocks, budget) { return paginateBlocks(blocks, budget); })");
  return run(blocks, budget);
}

function rows(heights, bracket) {
  return heights.map((height, index) => ({ key: `k${index}`, height, bracket: bracket ? bracket[index] : null }));
}

const MEASURED = [70.5, 111.1, 151.7, 192.2];

describe("[P178] the page cut never splits a block and never loses one", () => {
  test("every block lands on exactly one page, in the original order", () => {
    const { window } = loadApp();
    const blocks = rows([70.5, 70.5, 111.1, 70.5, 192.2, 70.5, 151.7, 70.5]);
    const pages = paginate(window, blocks, 300);
    expect(pages.flat()).toEqual(blocks.map((block) => block.key));
    expect(new Set(pages.flat()).size).toBe(blocks.length);
  });

  test("no page ever exceeds the budget unless a single block already does", () => {
    const { window } = loadApp();
    const blocks = rows([70.5, 70.5, 111.1, 70.5, 192.2, 70.5, 151.7, 70.5]);
    for (const budget of [200, 300, 441, 530, 650, 805]) {
      const pages = paginate(window, blocks, budget);
      const byKey = new Map(blocks.map((block) => [block.key, block.height]));
      for (const page of pages) {
        const sum = page.reduce((total, key) => total + byKey.get(key), 0);
        expect(page.length).toBeGreaterThan(0);
        if (page.length > 1) expect(sum).toBeLessThanOrEqual(budget);
      }
    }
  });

  test("running twice over the same input yields identical page boundaries", () => {
    const { window } = loadApp();
    const blocks = rows([70.5, 151.7, 111.1, 70.5, 70.5, 192.2, 70.5]);
    expect(paginate(window, blocks, 380)).toEqual(paginate(window, blocks, 380));
  });

  test("a single block that is taller than the budget gets its own page instead of vanishing", () => {
    const { window } = loadApp();
    const pages = paginate(window, rows([70.5, 900, 70.5]), 300);
    expect(pages).toEqual([["k0"], ["k1"], ["k2"]]);
  });

  test("a budget smaller than every block still puts one block on every page", () => {
    const { window } = loadApp();
    const pages = paginate(window, rows(MEASURED), 10);
    expect(pages).toEqual([["k0"], ["k1"], ["k2"], ["k3"]]);
  });

  test("exactly one block is exactly one page", () => {
    const { window } = loadApp();
    expect(paginate(window, rows([70.5]), 441)).toEqual([["k0"]]);
  });

  test("a budget exactly equal to the block sum keeps everything on one page", () => {
    const { window } = loadApp();
    const heights = [70.5, 111.1, 151.7];
    expect(paginate(window, rows(heights), 333.3)).toEqual([["k0", "k1", "k2"]]);
  });

  test("one pixel less than the sum cuts before the last block, never inside it", () => {
    const { window } = loadApp();
    const heights = [70.5, 111.1, 151.7];
    expect(paginate(window, rows(heights), 332.3)).toEqual([["k0", "k1"], ["k2"]]);
  });

  test("an empty block list yields no page at all", () => {
    const { window } = loadApp();
    expect(paginate(window, [], 441)).toEqual([]);
  });
});

describe("[P178] the double-lesson bracket", () => {
  test("a bracket that would be split moves to the next page as a whole", () => {
    const { window } = loadApp();
    const blocks = rows([100, 100, 100, 100], [null, null, "b", "b"]);
    const pages = paginate(window, blocks, 250);
    expect(pages).toEqual([["k0", "k1"], ["k2", "k3"]]);
  });

  test("a bracket too tall for an empty page is cut like any other run", () => {
    const { window } = loadApp();
    const blocks = rows([100, 200, 200], [null, "b", "b"]);
    const pages = paginate(window, blocks, 250);
    expect(pages).toEqual([["k0"], ["k1"], ["k2"]]);
  });

  test("a bracket is pushed forward at most once, so the cut always terminates", () => {
    const { window } = loadApp();
    const blocks = rows([60, 60, 60, 60, 60, 60], [null, "b", "b", "b", null, null]);
    const pages = paginate(window, blocks, 180);
    expect(pages.flat()).toEqual(blocks.map((block) => block.key));
    expect(pages.length).toBeLessThanOrEqual(3);
  });

  test("a bracket that starts a page is never pushed, because that would empty the page", () => {
    const { window } = loadApp();
    const blocks = rows([200, 200], ["b", "b"]);
    const pages = paginate(window, blocks, 250);
    expect(pages).toEqual([["k0"], ["k1"]]);
  });
});

describe("[P178] a lonely last page is filled from the page before it", () => {
  test("eight rows over two pages end up split, not seven against one", () => {
    const { window } = loadApp();
    const heights = [70.5, 90.8, 70.5, 70.5, 70.5, 70.5, 90.8, 74.6];
    const pages = paginate(window, rows(heights), 599);
    expect(pages.map((page) => page.length)).toEqual([5, 3]);
    expect(pages.flat()).toEqual(rows(heights).map((block) => block.key));
  });

  test("balancing never leaves an earlier page below three blocks", () => {
    const { window } = loadApp();
    const pages = paginate(window, rows([91, 91, 91, 68]), 319);
    expect(pages.map((page) => page.length)).toEqual([3, 1]);
  });

  test("balancing never pushes a page over the budget", () => {
    const { window } = loadApp();
    const blocks = rows([60, 60, 60, 60, 60, 200]);
    const pages = paginate(window, blocks, 320);
    const byKey = new Map(blocks.map((block) => [block.key, block.height]));
    for (const page of pages) {
      expect(page.reduce((sum, key) => sum + byKey.get(key), 0)).toBeLessThanOrEqual(320);
    }
    expect(pages.flat()).toEqual(blocks.map((block) => block.key));
  });

  test("balancing stays deterministic", () => {
    const { window } = loadApp();
    const blocks = rows([70.5, 90.8, 70.5, 70.5, 70.5, 70.5, 90.8, 74.6]);
    expect(paginate(window, blocks, 599)).toEqual(paginate(window, blocks, 599));
  });
});

describe("[P178] brackets are derived from the timetable, not guessed", () => {
  function brackets(window, groups) {
    const run = window.eval("(function (groups) { return overviewBrackets(groups); })");
    return run(groups);
  }

  const lesson = (period, subject, change) => ({
    period,
    lessons: [{ period, subject_label: subject, change_kind: change || "" }],
  });

  test("two consecutive periods of the same subject form one bracket", () => {
    const { window } = loadApp();
    const keys = brackets(window, [lesson(1, "Mathe"), lesson(2, "Mathe"), lesson(3, "Deutsch")]);
    expect(keys[0]).toBe(keys[1]);
    expect(keys[0]).not.toBeNull();
    expect(keys[2]).toBeNull();
  });

  test("a gap in the period numbers breaks the bracket", () => {
    const { window } = loadApp();
    const keys = brackets(window, [lesson(1, "Mathe"), lesson(3, "Mathe")]);
    expect(keys).toEqual([null, null]);
  });

  test("a different change kind breaks the bracket", () => {
    const { window } = loadApp();
    const keys = brackets(window, [lesson(1, "Mathe"), lesson(2, "Mathe", "cancelled")]);
    expect(keys).toEqual([null, null]);
  });

  test("a shared slot with two parallel lessons is unsplittable on its own and never bracketed", () => {
    const { window } = loadApp();
    const pair = { period: 2, lessons: [{ period: 2, subject_label: "Mathe" }, { period: 2, subject_label: "Team" }] };
    const keys = brackets(window, [lesson(1, "Mathe"), pair]);
    expect(keys).toEqual([null, null]);
  });
});

describe("[P178] the anchor follows the content, never a page number", () => {
  function buildScreen(window, layout) {
    return window.eval(`
      (function (layout) {
        const screen = document.createElement("div");
        screen.className = "screen";
        const overview = document.createElement("div");
        overview.className = "overview";
        for (const page of layout) {
          const panel = document.createElement("section");
          panel.className = "panel";
          panel.dataset.area = page.area;
          for (const key of page.keys) {
            const block = document.createElement("div");
            block.dataset.block = key;
            panel.append(block);
          }
          overview.append(panel);
        }
        screen.append(overview);
        document.body.append(screen);
        return screen;
      })
    `)(layout);
  }

  const CHAPTERS = [{ area: "today", blocks: [{ key: "c1:1" }, { key: "c1:2" }, { key: "c1:3" }, { key: "c1:4" }] }];

  function pick(window, screen, chapters, anchor) {
    return window.eval("(function (s, c, a) { return overviewAnchorPanel(s, c, a); })")(screen, chapters, anchor);
  }

  test("the page holding the anchor block wins, even if it is no longer that page's first block", () => {
    const { window } = loadApp();
    const screen = buildScreen(window, [
      { area: "today", keys: ["c1:1", "c1:2"] },
      { area: "today", keys: ["c1:3", "c1:4"] },
      { area: "letters", keys: ["letter:a"] },
    ]);
    const panel = pick(window, screen, CHAPTERS, { area: "today", blockKey: "c1:4" });
    expect(panel.dataset.area).toBe("today");
    expect([...panel.querySelectorAll("[data-block]")].map((node) => node.dataset.block)).toContain("c1:4");
  });

  test("a vanished block falls forward to the next block that is still there", () => {
    const { window } = loadApp();
    const screen = buildScreen(window, [
      { area: "today", keys: ["c1:1"] },
      { area: "today", keys: ["c1:4"] },
    ]);
    const chapters = [{ area: "today", blocks: [{ key: "c1:2" }, { key: "c1:4" }] }];
    const panel = pick(window, screen, chapters, { area: "today", blockKey: "c1:2" });
    expect([...panel.querySelectorAll("[data-block]")].map((node) => node.dataset.block)).toEqual(["c1:4"]);
  });

  test("with nothing left to follow it lands on page one of the same chapter, never another chapter", () => {
    const { window } = loadApp();
    const screen = buildScreen(window, [
      { area: "today", keys: ["c1:1"] },
      { area: "letters", keys: ["letter:a"] },
      { area: "letters", keys: ["letter:b"] },
    ]);
    const panel = pick(window, screen, [{ area: "letters", blocks: [] }], { area: "letters", blockKey: "gone" });
    expect(panel.dataset.area).toBe("letters");
    expect([...panel.querySelectorAll("[data-block]")].map((node) => node.dataset.block)).toEqual(["letter:a"]);
  });

  test("a chapter with no block key at all lands on its first page", () => {
    const { window } = loadApp();
    const screen = buildScreen(window, [
      { area: "today", keys: ["c1:1"] },
      { area: "pinboard", keys: ["post:1"] },
    ]);
    const panel = pick(window, screen, CHAPTERS, { area: "pinboard", blockKey: null });
    expect(panel.dataset.area).toBe("pinboard");
  });
});

describe("[P178] the now anchor and what survives a rerender", () => {
  const SEED = `
    state.children = [{ child_id: "c1", name: "Alice" }];
    state.childId = "c1";
    state.weekOffset = 0;
    state.me = { forename: "Alice" };
    state.letters = { letters: [] };
    state.pinboard = { folders: [], feed: [] };
    state.conferences = { items: [] };
    state.absence = { data: { entries: [], children: [] } };
    state.config = { period_times: { 1: "08:00", 2: "08:50", 3: "09:50" } };
    state.timetable = {
      lessons: [
        { day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" },
        { day_of_week: 2, period: 2, start_time: "08:50", subject_code: "M" },
        { day_of_week: 2, period: 3, start_time: "09:50", subject_code: "E" },
      ],
      period_times: {},
    };
  `;

  function todayChapterAt(window, iso) {
    return window.eval(`
      (function (fixedIso) {
        ${SEED}
        window.__realDate = Date;
        function FixedDate(...args) {
          if (args.length === 0) return new window.__realDate(fixedIso);
          return new window.__realDate(...args);
        }
        FixedDate.prototype = window.__realDate.prototype;
        Date = FixedDate;
        const chapter = todayChapter();
        Date = window.__realDate;
        return { nowKey: chapter.nowKey, keys: chapter.blocks.map((block) => block.key) };
      })
    `)(iso);
  }

  test("during the second lesson the now anchor points at that lesson's block", () => {
    const { window } = loadApp();
    expect(todayChapterAt(window, "2026-09-01T09:00:00").nowKey).toBe("c1:2");
  });

  test("before the school day the now anchor points at the first upcoming lesson", () => {
    const { window } = loadApp();
    expect(todayChapterAt(window, "2026-09-01T06:00:00").nowKey).toBe("c1:1");
  });

  test("after the last lesson the now anchor points at the last block of the chapter", () => {
    const { window } = loadApp();
    const chapter = todayChapterAt(window, "2026-09-01T20:00:00");
    expect(chapter.nowKey).toBe(chapter.keys[chapter.keys.length - 1]);
  });

  test("past lessons keep their block, so nothing is thrown away over the day", () => {
    const { window } = loadApp();
    expect(todayChapterAt(window, "2026-09-01T11:00:00").keys).toContain("c1:1");
  });

  test("the anchor survives a rerender: the same block keys come back in the same order", () => {
    const { window } = loadApp();
    const first = todayChapterAt(window, "2026-09-01T09:00:00");
    const second = todayChapterAt(window, "2026-09-01T09:00:00");
    expect(second.keys).toEqual(first.keys);
    expect(second.nowKey).toBe(first.nowKey);
  });

  test("without measured heights the overview refuses to snap and stays a plain scroll list", () => {
    const { window } = loadApp();
    const snap = window.eval(`
      (function () {
        ${SEED}
        state.view = "overview";
        render();
        const screen = document.querySelector(".screen");
        return {
          screen: screen.getAttribute("data-snap"),
          overview: screen.querySelector(".overview").getAttribute("data-snap"),
          arrows: screen.querySelectorAll(".panel-arrow-btn").length,
          counters: screen.querySelectorAll(".panel-counter").length,
        };
      })()
    `);
    expect(snap.screen).toBeNull();
    expect(snap.overview).toBe("off");
    expect(snap.arrows).toBe(0);
    expect(snap.counters).toBe(0);
  });
});
