const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkTapTargets, waitForSheetSettled } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "1440", width: 1440, height: 900 },
];
const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

let slot = 0;

async function gotoSettings(page, lang, extraCookies = []) {
  slot += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_layout", value: `spec-${process.pid}-${Date.now()}-${slot}`, url: BASE_URL },
    ...extraCookies.map((cookie) => ({ ...cookie, url: BASE_URL })),
  ]);
  await goto(page);
  await page.waitForSelector(".overview", { timeout: 10000 });
  await page.locator(".header-actions .settings-entry").click();
  await page.waitForSelector(".layout-setting", { timeout: 8000 });
}

async function assertClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(await checkElementsWithinViewport(page), `${label}: elements outside the viewport`).toEqual([]);
  const offenders = await checkTapTargets(page);
  expect(offenders, `${label}: tap targets below 44px: ${JSON.stringify(offenders)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`layout settings ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("the overview page lists shown and hidden blocks, the info sheet opens, nothing overflows", async ({ page }) => {
        await gotoSettings(page, lang.key);
        await page.locator(".layout-setting").click();
        await page.waitForSelector(".blocks-page", { timeout: 8000 });
        const label = `${viewport.name}/${lang.key}/blocks`;
        expect(await page.locator(".blocks-page .settings-group").first().locator(".block-row").count()).toBe(6);
        expect(await page.locator(".blocks-page .block-row.off").count()).toBe(4);
        expect(await page.locator(".blocks-page .block-row.off").evaluateAll((rows) => rows.map((row) => row.dataset.block))).toEqual(["next_lesson", "week", "absences", "holidays"]);
        await assertClean(page, label);
        expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe(lang.key === "ar" ? "rtl" : "ltr");

        await page.locator('.block-row[data-block="today"] .info-btn').click();
        await waitForSheetSettled(page);
        await expect(page.locator(".sheet .block-facts")).toBeVisible();
        await assertClean(page, `${label}/info`);
        await page.locator(".sheet-close").click();
        await page.waitForTimeout(200);

        await page.locator('.block-row[data-block="noticeboard"] .switch').click();
        await page.waitForTimeout(300);
        expect(await page.locator(".blocks-page .block-row.off").evaluateAll((rows) => rows.map((row) => row.dataset.block))).toEqual(["next_lesson", "week", "noticeboard", "absences", "holidays"]);
        const config = await page.evaluate(() => fetch("api/config").then((response) => response.json()));
        expect(config.overview_blocks.map((entry) => entry.key)).not.toContain("noticeboard");
        expect(config.overview_blocks.length).toBe(5);
        await assertClean(page, `${label}/hidden`);
      });

      test("the arrows move a block and keep the focus on the pressed arrow", async ({ page }) => {
        await gotoSettings(page, lang.key);
        await page.locator(".layout-setting").click();
        await page.waitForSelector(".blocks-page", { timeout: 8000 });
        const shownRows = page.locator(".blocks-page .settings-group").first().locator(".block-row");
        const shownCount = await shownRows.count();
        expect(shownCount).toBeGreaterThan(0);
        await expect(shownRows.locator('.segment.mini[role="radiogroup"]')).toHaveCount(shownCount);
        await page.locator('.block-row[data-block="letters"] .order-btns [data-dir="up"]').click();
        await page.waitForTimeout(300);
        const keys = await page.locator(".blocks-page .settings-group").first().locator(".block-row").evaluateAll((rows) => rows.map((row) => row.dataset.block));
        expect(keys.slice(0, 2)).toEqual(["letters", "today"]);
        expect(await page.evaluate(() => document.activeElement && document.activeElement.closest(".block-row") && document.activeElement.closest(".block-row").dataset.block)).toBe("letters");
        expect(await page.locator('[aria-live="polite"]').textContent()).toContain(await page.evaluate(() => window.t("blocks.letters.title")));
        await page.locator('.block-row[data-block="letters"] .segment.mini [role="radio"]').first().click();
        await page.waitForTimeout(300);
        const config = await page.evaluate(() => fetch("api/config").then((response) => response.json()));
        expect(config.overview_blocks.find((entry) => entry.key === "letters").size).toBe("compact");
      });

      test("the block list gets a search field once it crosses the threshold, filters by name, RTL-friendly", async ({ page }) => {
        await gotoSettings(page, lang.key);
        await page.evaluate(() => { window.RanzenpostBlocks.BLOCK_SEARCH_FROM = 5; });
        await page.locator(".layout-setting").click();
        await page.waitForSelector(".blocks-page", { timeout: 8000 });
        const label = `${viewport.name}/${lang.key}/blocks-search`;
        await expect(page.locator(".blocks-page .search-field")).toBeVisible();
        expect(await page.evaluate(() => document.activeElement && document.activeElement.tagName)).not.toBe("INPUT");
        const chatName = await page.evaluate(() => window.t("blocks.chat.title"));
        await page.locator(".blocks-page .search-input").fill(chatName);
        await page.waitForTimeout(200);
        expect(await page.locator(".blocks-page .block-row").evaluateAll((rows) => rows.map((row) => row.dataset.block))).toEqual(["chat"]);
        await assertClean(page, label);
        await page.locator(".blocks-page .search-input").fill("zzz-nichts-passt-zzz");
        await page.waitForTimeout(200);
        expect(await page.locator(".blocks-page .block-row").count()).toBe(0);
        expect(await page.locator(".blocks-page .cal-hint").allTextContents()).toEqual([
          await page.evaluate(() => window.t("settings.blocks.search.empty")),
          await page.evaluate(() => window.t("settings.blocks.search.empty")),
        ]);
        await page.locator(".blocks-page .search-clear").click();
        await page.waitForTimeout(200);
        expect(await page.locator(".blocks-page .block-row").count()).toBe(10);
        expect(await page.evaluate(() => document.activeElement && document.activeElement.className)).toContain("search-input");
      });

      test("the navigation page shows the locked overview, the two bands and moves an area", async ({ page }) => {
        await gotoSettings(page, lang.key);
        await page.locator(".layout-setting").click();
        await page.waitForSelector(".app-layout-page .nav-page", { timeout: 8000 });
        const label = `${viewport.name}/${lang.key}/navigation`;
        const rows = await page.locator(".nav-rows > *").evaluateAll((nodes) => nodes.map((node) => node.dataset.band || node.dataset.area));
        expect(rows).toEqual(["bar", "overview", "timetable", "absence", "post", "more", "messenger", "conferences"]);
        await assertClean(page, label);
        await page.locator('.nav-row[data-area="messenger"] .order-btns [data-dir="up"]').click();
        await page.waitForTimeout(300);
        const moved = await page.locator(".nav-rows > *").evaluateAll((nodes) => nodes.map((node) => node.dataset.band || node.dataset.area));
        expect(moved).toEqual(["bar", "overview", "timetable", "absence", "messenger", "more", "post", "conferences"]);
        const config = await page.evaluate(() => fetch("api/config").then((response) => response.json()));
        expect(config.navigation).toEqual(["timetable", "absence", "messenger", "post", "conferences"]);
        if (viewport.width < 900) {
          const tabs = await page.locator(".tabbar .tab").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
          expect(tabs).toEqual(["overview", "timetable", "absence", "messenger", "more"]);
        } else {
          const rail = await page.locator(".rail .rail-item").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
          expect(rail).toEqual(["overview", "timetable", "absence", "messenger", "post", "conferences"]);
        }
        await assertClean(page, `${label}/moved`);
      });
    });
  }
}

test.describe("the More sheet and the module switches @ 390", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("More lists the areas beyond the bar with their badges and opens them", async ({ page }) => {
    await page.context().clearCookies();
    await page.context().addCookies([{ name: "e2e_lang", value: "de", url: BASE_URL }]);
    await goto(page);
    await page.waitForSelector(".overview", { timeout: 10000 });
    const tabs = await page.locator(".tabbar .tab").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
    expect(tabs).toEqual(["overview", "timetable", "absence", "post", "more"]);
    await expect(page.locator(".tabbar .tab-more .badge")).toHaveText("3");
    await page.locator(".tabbar .tab-more").click();
    await waitForSheetSettled(page);
    const rows = await page.locator(".sheet .more-row").evaluateAll((nodes) => nodes.map((node) => node.dataset.area));
    expect(rows).toEqual(["messenger", "conferences"]);
    await expect(page.locator('.sheet .more-row[data-area="messenger"] .badge')).toHaveText("3");
    await assertClean(page, "390/more-sheet");
    await page.locator('.sheet .more-row[data-area="conferences"]').click();
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => state.view)).toBe("conferences");
    expect(await page.locator(".sheet").count()).toBe(0);
    expect(await page.locator(".tabbar .tab-more").getAttribute("aria-current")).toBe("page");
  });

  test("a lowered bar limit folds more areas under More", async ({ page }) => {
    await page.context().clearCookies();
    await page.context().addCookies([
      { name: "e2e_lang", value: "de", url: BASE_URL },
      { name: "e2e_bar_limit", value: "3", url: BASE_URL },
    ]);
    await goto(page);
    await page.waitForSelector(".overview", { timeout: 10000 });
    const tabs = await page.locator(".tabbar .tab").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
    expect(tabs).toEqual(["overview", "timetable", "more"]);
    await page.locator(".tabbar .tab-more").click();
    await waitForSheetSettled(page);
    const rows = await page.locator(".sheet .more-row").evaluateAll((nodes) => nodes.map((node) => node.dataset.area));
    expect(rows).toEqual(["absence", "post", "messenger", "conferences"]);
    await assertClean(page, "390/more-sheet-limit-3");
  });

  test("switching a module off removes it from the bar, the overview and the settings rows", async ({ page }) => {
    await gotoSettings(page, "de");
    await page.locator('.module-row[data-module="timetable"] .switch').click();
    await page.waitForTimeout(400);
    expect(await page.locator('.module-row[data-module="timetable"] .switch').getAttribute("aria-checked")).toBe("false");
    const labels = await page.locator(".setting-row .lbl").allTextContents();
    expect(labels).not.toContain("Fächer & Lehrkräfte");
    const tabs = await page.locator(".tabbar .tab").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
    expect(tabs).toEqual(["overview", "absence", "post", "messenger", "conferences"]);
    await page.locator(".layout-setting").click();
    await page.waitForSelector(".blocks-page", { timeout: 8000 });
    const shownKeys = await page.locator(".blocks-page .settings-group").first().locator(".block-row").evaluateAll((rows) => rows.map((row) => row.dataset.block));
    const hiddenKeys = await page.locator(".blocks-page .settings-group").nth(1).locator(".block-row").evaluateAll((rows) => rows.map((row) => row.dataset.block));
    expect(shownKeys).toEqual(["letters", "noticeboard", "conferences", "chat"]);
    expect(hiddenKeys).toEqual(["absences"]);
    await page.locator(".header-back").click();
    await page.locator(".header-back").click();
    await page.waitForSelector(".overview", { timeout: 8000 });
    const blocks = await page.locator(".overview .panel[data-block]").evaluateAll((panels) => panels.map((panel) => panel.dataset.block));
    expect(blocks.filter((key) => ["today", "next_lesson", "week", "holidays", "changes"].includes(key))).toEqual([]);
    const config = await page.evaluate(() => fetch("api/config").then((response) => response.json()));
    expect(config.modules_disabled).toEqual(["timetable"]);
  });
});
