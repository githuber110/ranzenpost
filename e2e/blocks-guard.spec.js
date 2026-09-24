const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkTapTargets } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1440", width: 1440, height: 900 },
];
const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];
const OTHER_LANGUAGES = [
  { key: "en", locale: "en-US" },
  { key: "tr", locale: "tr-TR" },
  { key: "ru", locale: "ru-RU" },
  { key: "uk", locale: "uk-UA" },
];
const THEMES = ["light", "dark"];
const FONT_SIZES = [16, 20];
const ALL_BLOCKS = ["today", "next_lesson", "week", "letters", "noticeboard", "absences", "conferences", "holidays", "changes", "chat"];

let layoutSlot = 0;

async function gotoBlocks(page, lang, theme, fontSize) {
  layoutSlot += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_scenario", value: "two-children", url: BASE_URL },
    { name: "e2e_layout", value: `blocks-guard-${process.pid}-${Date.now()}-${layoutSlot}`, url: BASE_URL },
  ]);
  await page.request.post(`${BASE_URL}/api/config`, { data: { overview_blocks: ALL_BLOCKS.map((key) => ({ key })) } });
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  await goto(page);
  await page.waitForSelector(".overview", { timeout: 10000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 10000 }).catch(() => {});
  if (fontSize !== 16) {
    await page.addStyleTag({ content: `html { font-size: ${fontSize}px; }` });
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
  }
  await page.waitForTimeout(300);
}

async function renderedBlocks(page) {
  return page.evaluate(() => [...document.querySelectorAll(".overview .panel[data-block]")].map((panel) => panel.dataset.block));
}

async function assertBlockClean(page, block, label) {
  const inside = await page.evaluate((key) => {
    const panels = [...document.querySelectorAll(`.overview .panel[data-block="${key}"]`)];
    const screen = document.querySelector(".screen");
    const offenders = [];
    for (const panel of panels) {
      const box = panel.getBoundingClientRect();
      for (const node of panel.querySelectorAll("*")) {
        const style = getComputedStyle(node);
        if (style.display === "none" || style.visibility === "hidden") continue;
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) continue;
        if (node.closest(".chipbar") || node.closest(".tt-multi.scrolls")) continue;
        if (rect.left < box.left - 1 || rect.right > box.right + 1) {
          offenders.push({ tag: node.tagName, className: String(node.className), left: Math.round(rect.left - box.left), right: Math.round(rect.right - box.right) });
        }
      }
    }
    return { offenders: offenders.slice(0, 10), screenWide: screen.scrollWidth > screen.clientWidth + 1 };
  }, block);
  expect(inside.offenders, `${label}/${block}: content leaves its block: ${JSON.stringify(inside.offenders)}`).toEqual([]);
  expect(inside.screenWide, `${label}/${block}: the screen scrolls sideways`).toBe(false);
}

async function assertBlocksClean(page, label, theme) {
  const blocks = await renderedBlocks(page);
  expect([...new Set(blocks)].sort(), `${label}: not every catalogue block rendered`).toEqual([...ALL_BLOCKS].sort());
  if (theme) expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
  for (const block of [...new Set(blocks)]) {
    await page.evaluate((key) => {
      const panel = document.querySelector(`.overview .panel[data-block="${key}"]`);
      if (panel) panel.scrollIntoView({ block: "start" });
    }, block);
    await page.waitForTimeout(60);
    await assertBlockClean(page, block, label);
  }
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(await checkElementsWithinViewport(page), `${label}: elements outside the viewport`).toEqual([]);
  const tapOffenders = await checkTapTargets(page);
  expect(tapOffenders, `${label}: tap targets below 44px: ${JSON.stringify(tapOffenders)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    for (const theme of THEMES) {
      test.describe(`blocks guard ${viewport.name} ${lang.key} ${theme}`, () => {
        test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale, colorScheme: theme });

        for (const fontSize of FONT_SIZES) {
          test(`every rendered block stays inside its container at ${fontSize}px`, async ({ page }) => {
            await gotoBlocks(page, lang.key, theme, fontSize);
            await assertBlocksClean(page, `${viewport.name}/${lang.key}/${theme}/${fontSize}`, theme);
          });
        }
      });
    }
  }
}

for (const viewport of VIEWPORTS) {
  for (const lang of OTHER_LANGUAGES) {
    test.describe(`blocks guard ${viewport.name} ${lang.key} light`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale, colorScheme: "light" });

      test("every rendered block stays inside its container in this language, base theme/size", async ({ page }) => {
        await gotoBlocks(page, lang.key, "light", 16);
        await assertBlocksClean(page, `${viewport.name}/${lang.key}/light/16`, "light");
      });
    });
  }
}

test.describe("blocks guard: the empty modules render no block", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("with every module emptied the overview shows the calm empty state and no panel", async ({ page }) => {
    await page.context().clearCookies();
    await page.context().addCookies([
      { name: "e2e_lang", value: "de", url: BASE_URL },
      { name: "e2e_empty", value: "timetable,letters,pinboard,absences,conferences,messenger", url: BASE_URL },
    ]);
    await goto(page);
    await page.waitForSelector(".overview-empty", { timeout: 10000 });
    expect(await page.locator(".overview .panel").count()).toBe(0);
    expect(await page.locator(".error, .note").count()).toBe(0);
    const overflow = await checkHorizontalOverflow(page);
    expect(overflow.overflow).toBe(false);
    expect(await checkTapTargets(page)).toEqual([]);
  });
});

test.describe("blocks guard: a single block key can be emptied without touching its siblings", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  const cases = [
    { empty: "today", vanished: "today", stays: ["week", "next_lesson"] },
    { empty: "next_lesson", vanished: "next_lesson", stays: ["today", "week"] },
    { empty: "week", vanished: "week", stays: ["today"] },
    { empty: "changes", vanished: "changes", stays: ["today", "week"] },
    { empty: "holidays", vanished: "holidays", stays: ["today", "week"] },
    { empty: "noticeboard", vanished: "noticeboard", stays: ["letters"] },
    { empty: "absences", vanished: "absences", stays: ["today", "week"] },
    { empty: "conferences", vanished: "conferences", stays: ["today", "week"] },
    { empty: "letters", vanished: "letters", stays: ["today", "week"] },
    { empty: "chat", vanished: "chat", stays: ["today"] },
  ];

  for (const [index, scenario] of cases.entries()) {
    test(`emptying "${scenario.empty}" alone hides only that block`, async ({ page }) => {
      await page.context().clearCookies();
      await page.context().addCookies([
        { name: "e2e_lang", value: "de", url: BASE_URL },
        { name: "e2e_scenario", value: "two-children", url: BASE_URL },
        { name: "e2e_layout", value: `blocks-guard-single-${process.pid}-${Date.now()}-${index}`, url: BASE_URL },
        { name: "e2e_empty", value: scenario.empty, url: BASE_URL },
      ]);
      await page.request.post(`${BASE_URL}/api/config`, { data: { overview_blocks: ALL_BLOCKS.map((key) => ({ key })) } });
      const noon = new Date();
      noon.setHours(12, 0, 0, 0);
      await page.clock.setFixedTime(noon);
      await goto(page);
      await page.waitForSelector(".overview", { timeout: 10000 });
      await page.waitForSelector(".loading", { state: "detached", timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(300);
      const blocks = await renderedBlocks(page);
      expect(blocks, `${scenario.empty} should not render`).not.toContain(scenario.vanished);
      for (const key of scenario.stays) {
        expect(blocks, `${key} should still render while only ${scenario.empty} is empty`).toContain(key);
      }
    });
  }
});
