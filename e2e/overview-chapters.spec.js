const { test, expect } = require("@playwright/test");
const {
  goto,
  checkTapTargets,
  checkTapTargetOverlaps,
  checkLastRowReachable,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
} = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;

const AREAS = ["today", "letters", "pinboard", "upcoming"];
const MAX_PAGES = 4;
const MIN_BLOCKS_PER_PAGE = 3;

const FIXTURES = ["short-day", "long-day", "two-children", "two-long"];

async function gotoScenario(page, scenario, fontSize) {
  await page.context().clearCookies();
  if (scenario) {
    await page.context().addCookies([{ name: "e2e_scenario", value: scenario, url: BASE_URL }]);
  }
  await goto(page);
  await page.waitForSelector(".overview", { timeout: 10000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 10000 }).catch(() => {});
  if (fontSize && fontSize !== 16) {
    await page.addStyleTag({ content: `html { font-size: ${fontSize}px; }` });
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
  }
  await page.waitForTimeout(250);
}

async function inspect(page) {
  return page.evaluate(() => {
    const screen = document.querySelector(".screen");
    const container = screen && screen.querySelector(".overview");
    if (!container) return { present: false };
    const style = getComputedStyle(screen);
    const tabbar = document.querySelector(".tabbar");
    const arrowOf = (panel) => panel.querySelector(".panel-arrow-btn");
    return {
      present: true,
      snap: container.getAttribute("data-snap"),
      screenSnap: screen.getAttribute("data-snap"),
      snapType: style.scrollSnapType,
      panelHeight: parseFloat(style.getPropertyValue("--panel-h")) || 0,
      headings: container.querySelectorAll("h2.section-label").length,
      counters: container.querySelectorAll(".panel-counter").length,
      arrows: container.querySelectorAll(".panel-arrow-btn").length,
      tabbarTop: tabbar ? tabbar.getBoundingClientRect().top : 0,
      panels: [...container.querySelectorAll(".panel")].map((panel) => {
        const arrow = arrowOf(panel);
        const blocks = [...panel.querySelectorAll("[data-block]")];
        const last = blocks[blocks.length - 1];
        const rect = panel.getBoundingClientRect();
        return {
          area: panel.dataset.area,
          page: Number(panel.dataset.page),
          title: (panel.querySelector(".section-label") || {}).textContent || "",
          all: (panel.dataset.blocks || "").split(" ").filter(Boolean),
          blocks: blocks.map((node) => node.dataset.block),
          height: rect.height,
          bottom: rect.bottom,
          overflow: panel.scrollHeight - panel.clientHeight,
          headings: panel.querySelectorAll("h2.section-label").length,
          continued: panel.querySelectorAll("p.section-label.continued").length,
          counter: panel.querySelector(".panel-counter") ? panel.querySelector(".panel-counter").textContent : null,
          back: !!panel.querySelector(".panel-back"),
          label: panel.getAttribute("aria-label"),
          arrow: arrow ? arrow.dataset.arrow : null,
          arrowLabel: arrow ? arrow.getAttribute("aria-label") : null,
          lastBlockBottom: last ? last.getBoundingClientRect().bottom : null,
        };
      }),
    };
  });
}

function pagesOf(view, area) {
  return view.panels.filter((panel) => panel.area === area);
}

function assertCompleteness(view, label) {
  for (const area of AREAS) {
    const pages = pagesOf(view, area);
    expect(pages.length, `${label}/${area}: chapter missing`).toBeGreaterThan(0);
    const seen = pages.flatMap((panel) => panel.blocks);
    expect(seen, `${label}/${area}: blocks lost, doubled or reordered`).toEqual(pages[0].all);
    expect(new Set(seen).size, `${label}/${area}: a block sits on two pages`).toBe(seen.length);
    for (const panel of pages) {
      expect(panel.blocks.length, `${label}/${area}: empty page ${panel.page}`).toBeGreaterThan(0);
    }
  }
}

function assertBudget(view, label) {
  if (view.snap !== "on") return;
  expect(view.panelHeight, `${label}: no measured panel height`).toBeGreaterThan(0);
  for (const panel of view.panels) {
    expect(
      panel.height,
      `${label}/${panel.area} page ${panel.page}: ${panel.height}px exceeds the measured budget ${view.panelHeight}px`
    ).toBeLessThanOrEqual(view.panelHeight + 1);
    expect(
      panel.overflow,
      `${label}/${panel.area} page ${panel.page}: the page scrolls inside itself`
    ).toBeLessThanOrEqual(1);
  }
  for (const area of AREAS) {
    const pages = pagesOf(view, area);
    expect(pages.length, `${label}/${area}: more than ${MAX_PAGES} pages`).toBeLessThanOrEqual(MAX_PAGES);
    if (pages.length > 1) {
      for (const panel of pages.slice(0, -1)) {
        expect(
          panel.blocks.length,
          `${label}/${area} page ${panel.page}: fewer than ${MIN_BLOCKS_PER_PAGE} blocks, the cut should have switched off`
        ).toBeGreaterThanOrEqual(MIN_BLOCKS_PER_PAGE);
      }
    }
  }
}

function assertReachable(view, label) {
  if (view.snap !== "on") return;
  for (const panel of view.panels) {
    if (panel.lastBlockBottom === null) continue;
    expect(
      panel.lastBlockBottom,
      `${label}/${panel.area} page ${panel.page}: the last row runs past the page`
    ).toBeLessThanOrEqual(panel.bottom + 1);
  }
}

function assertStructure(view, label) {
  expect(view.headings, `${label}: the heading rotor must hold exactly four entries`).toBe(4);
  for (const area of AREAS) {
    const pages = pagesOf(view, area);
    expect(pages[0].headings, `${label}/${area}: page one carries no h2`).toBe(1);
    for (const panel of pages.slice(1)) {
      expect(panel.headings, `${label}/${area} page ${panel.page}: a second h2 in the same chapter`).toBe(0);
      expect(panel.continued, `${label}/${area} page ${panel.page}: the continued title is missing`).toBe(1);
    }
  }
}

function assertArrows(view, label) {
  if (view.snap !== "on") {
    expect(view.arrows, `${label}: arrows must disappear when the cut is off`).toBe(0);
    expect(view.counters, `${label}: counters must disappear when the cut is off`).toBe(0);
    return;
  }
  const panels = view.panels;
  panels.forEach((panel, index) => {
    const pages = pagesOf(view, panel.area);
    const isLastPage = panel.page === pages.length - 1;
    const isLastPanel = index === panels.length - 1;
    if (isLastPanel) {
      expect(panel.arrow, `${label}: the very last page must carry no arrow`).toBeNull();
      return;
    }
    expect(panel.arrow, `${label}/${panel.area} page ${panel.page}: wrong arrow kind`).toBe(isLastPage ? "area" : "page");
    const nextTitle = panels[index + 1].title;
    if (isLastPage) {
      expect(panel.arrowLabel, `${label}: the chapter arrow must name its target`).toContain(nextTitle);
    } else {
      expect(panel.arrowLabel, `${label}: the page arrow must not name a chapter`).not.toContain(nextTitle);
    }
  });
  for (const area of AREAS) {
    const pages = pagesOf(view, area);
    for (const panel of pages) {
      if (pages.length > 1) expect(panel.counter, `${label}/${area}: missing page counter`).toBeTruthy();
      else expect(panel.counter, `${label}/${area}: a 1/1 counter must not appear`).toBeNull();
    }
  }
  expect(panels[0].back, `${label}: the very first page must not offer a way back`).toBe(false);
  for (const panel of panels.slice(1)) {
    expect(panel.back, `${label}: every page but the first offers the way back`).toBe(true);
  }
}

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
  { key: "ar", locale: "ar" },
];

const VIEWPORTS = [
  { name: "320x568", width: 320, height: 568 },
  { name: "390x844", width: 390, height: 844 },
];

for (const language of LANGUAGES) {
  for (const viewport of VIEWPORTS) {
    for (const fontSize of [16, 20]) {
      test.describe(`overview chapters ${language.key} ${viewport.name} @${fontSize}px`, () => {
        test.use({
          viewport: { width: viewport.width, height: viewport.height },
          locale: language.locale,
        });

        test("every page fits its measured budget and every block sits on exactly one page", async ({ page }) => {
          for (const fixture of FIXTURES) {
            const label = `${language.key}/${viewport.name}/${fontSize}/${fixture}`;
            await gotoScenario(page, fixture, fontSize);
            const view = await inspect(page);
            expect(view.present, `${label}: no overview`).toBe(true);
            expect(view.panels.map((panel) => panel.area).filter((area, index, all) => all.indexOf(area) === index))
              .toEqual(AREAS);
            assertCompleteness(view, label);
            assertBudget(view, label);
            assertReachable(view, label);
            assertStructure(view, label);
            assertArrows(view, label);
          }
        });
      });
    }
  }
}

test.describe("overview chapters: hit areas and reachability @ 320x568", () => {
  test.use({ viewport: { width: 320, height: 568 } });

  for (const fixture of FIXTURES) {
    test(`${fixture}: no undersized or colliding tap target, last row stays free`, async ({ page }) => {
      await gotoScenario(page, fixture, 16);

      const sizeOffenders = await checkTapTargets(page);
      expect(sizeOffenders, `${fixture}: undersized tap targets: ${JSON.stringify(sizeOffenders)}`).toEqual([]);

      const overlaps = await checkTapTargetOverlaps(page);
      expect(overlaps, `${fixture}: overlapping tap targets: ${JSON.stringify(overlaps)}`).toEqual([]);

      const reach = await checkLastRowReachable(page, ".row");
      expect(reach.present).toBe(true);
      expect(reach.fullyScrolled, `${fixture}: the last snap point is not the end of the scroll range`).toBe(true);
      expect(reach.covered, `${fixture}: last row covered by ${JSON.stringify(reach.coveringElements)}`).toBe(false);

      const overflow = await checkHorizontalOverflow(page);
      expect(overflow.overflow, `${fixture}: horizontal overflow`).toBe(false);
      expect(await checkElementsWithinViewport(page)).toEqual([]);
    });
  }
});

test.describe("overview chapters: the cut switches itself off @ 320x568", () => {
  test.use({ viewport: { width: 320, height: 568 } });

  test("a two-page chapter really happens on a small screen with a long day", async ({ page }) => {
    await gotoScenario(page, "long-day", 16);
    const view = await inspect(page);
    expect(view.snap).toBe("on");
    expect(view.snapType).toContain("mandatory");
    expect(pagesOf(view, "today").length).toBeGreaterThan(1);
    expect(view.counters).toBeGreaterThan(0);
  });

  test("at 28px system type the cut gives up and the overview scrolls freely again", async ({ page }) => {
    await gotoScenario(page, "two-long", 28);
    const view = await inspect(page);
    expect(view.snap).toBe("off");
    expect(view.screenSnap).toBeNull();
    expect(view.snapType === "none" || view.snapType === "").toBe(true);
    expect(view.arrows).toBe(0);
    expect(view.counters).toBe(0);
    assertCompleteness(view, "two-long/28px");
    assertStructure(view, "two-long/28px");
  });

  test("the twelve entry cap holds and the trailing row leads into the tab", async ({ page }) => {
    await gotoScenario(page, "full-cap", 16);
    const view = await inspect(page);
    const letters = pagesOf(view, "letters")[0].all;
    expect(letters.length).toBe(13);
    expect(letters[letters.length - 1]).toBe("letters:all");
    const pinboard = pagesOf(view, "pinboard")[0].all;
    expect(pinboard.length).toBe(13);
    expect(pinboard[pinboard.length - 1]).toBe("pinboard:all");
  });
});

test.describe("overview chapters: landscape keeps free scrolling", () => {
  test.use({ viewport: { width: 740, height: 360 } });

  test("no snapping, no arrows, no counters, and nothing missing", async ({ page }) => {
    await gotoScenario(page, "long-day", 16);
    const view = await inspect(page);
    expect(view.snap).toBe("off");
    expect(view.arrows).toBe(0);
    expect(view.counters).toBe(0);
    assertCompleteness(view, "landscape");
    assertStructure(view, "landscape");
  });
});

test.describe("overview chapters: the child pills carry the day @ 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("two children give two pills, and the second one takes over the chapter", async ({ page }) => {
    await gotoScenario(page, "two-children", 16);
    const pills = page.locator('.panel[data-area="today"] .overview-pills .chip');
    expect(await pills.count()).toBeGreaterThanOrEqual(2);
    const before = await page.locator('.panel[data-area="today"] [data-block]').first().getAttribute("data-block");
    await pills.nth(1).click();
    await page.waitForTimeout(250);
    expect(await pills.nth(1).getAttribute("aria-pressed")).toBe("true");
    const after = await page.locator('.panel[data-area="today"] [data-block]').first().getAttribute("data-block");
    expect(after.startsWith("child-2:")).toBe(true);
    expect(after).not.toBe(before);
    const view = await inspect(page);
    assertCompleteness(view, "two-children/after-switch");
    assertStructure(view, "two-children/after-switch");
  });

  test("the arrow steps exactly one page and the way back returns to it", async ({ page }) => {
    await gotoScenario(page, "long-day", 16);
    const view = await inspect(page);
    test.skip(view.snap !== "on", "the cut is off on this device");
    await page.evaluate(() => { document.querySelector(".screen").scrollTop = 0; });
    await page.waitForTimeout(200);
    const before = await page.evaluate(() => document.querySelector(".screen").scrollTop);
    expect(before).toBeLessThanOrEqual(2);
    await page.locator(".panel-arrow-btn").first().click();
    await page.waitForTimeout(900);
    const after = await page.evaluate(() => document.querySelector(".screen").scrollTop);
    expect(after).toBeGreaterThan(before);
    expect(Math.abs(after - view.panelHeight)).toBeLessThanOrEqual(2);
    await page.locator(".panel-back").first().click();
    await page.waitForTimeout(900);
    expect(await page.evaluate(() => document.querySelector(".screen").scrollTop)).toBeLessThanOrEqual(2);
  });
});
