const { test, expect } = require("@playwright/test");
const {
  goto,
  waitForSheetSettled,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
} = require("./helpers");

test.describe.configure({ mode: "serial" });

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE", rtl: false },
  { key: "ru", locale: "ru-RU", rtl: false },
  { key: "ar", locale: "ar-EG", rtl: true },
];

const TIMETABLE_TAB = 1;

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function clearMarks(page) {
  await page.evaluate(async () => {
    const base = new URL("api/marks", document.baseURI).toString();
    const listed = await fetch(base).then((response) => response.json());
    for (const entry of listed.marks || []) {
      await fetch(`${base}/${entry.id}`, { method: "DELETE" });
    }
  });
}

async function text(page, key) {
  return page.evaluate((name) => window.t(name), key);
}

async function assertNoOverflow(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: elements outside the viewport: ${JSON.stringify(outside)}`).toEqual([]);
}

async function assertTapTargets(page, label) {
  const undersized = await checkTapTargets(page);
  expect(undersized, `${label}: undersized tap targets: ${JSON.stringify(undersized)}`).toEqual([]);
}

async function openTimetable(page) {
  await page.locator(".tabbar .tab").nth(TIMETABLE_TAB).click();
  await settled(page);
}

async function settingRow(page, key) {
  const label = await text(page, key);
  return page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: label }) });
}

for (const viewport of VIEWPORTS) {
  test.describe(`exam marks @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const language of LANGUAGES) {
      test.describe(language.key, () => {
        test.use({ locale: language.locale });

        test(`marking a lesson stays inside the screen (${language.key})`, async ({ page }) => {
          const tag = `${viewport.name}/${language.key}`;
          await goto(page);
          await clearMarks(page);
          expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe(
            language.rtl ? "rtl" : "ltr"
          );

          try {
            await openTimetable(page);
            await page.locator(".tt-cell:not(.free)").first().click();
            await waitForSheetSettled(page);
            await assertNoOverflow(page, `${tag}/lesson-sheet`);
            await assertTapTargets(page, `${tag}/lesson-sheet`);

            const add = page.locator(".sheet-foot .mark-add");
            await expect(add).toBeVisible();
            await add.click();
            await waitForSheetSettled(page);
            await expect(page.locator(".mark-context")).toBeVisible();
            await assertNoOverflow(page, `${tag}/mark-form`);
            await assertTapTargets(page, `${tag}/mark-form`);

            await page.locator(".sheet-body .inp").fill("Diktat");
            await page.locator(".sheet-foot .btn").click();
            await expect(page.locator(".sheet")).toHaveCount(0);

            const marked = page.locator(".tt-cell.marked");
            await expect(marked.first()).toBeVisible();
            await expect(marked.first().locator(".exam-flag")).toBeVisible();
            await assertNoOverflow(page, `${tag}/grid-marked`);

            await marked.first().click();
            await waitForSheetSettled(page);
            await expect(page.locator(".mark-panel .mark-name")).toHaveText("Diktat");
            await assertNoOverflow(page, `${tag}/marked-sheet`);
            await assertTapTargets(page, `${tag}/marked-sheet`);

            await page.locator(".sheet-close").click();
            await settled(page);
            await page.locator(".tabbar .tab").nth(0).click();
            await settled(page);
            await expect(page.locator(".rows.flat .tag.exam").first()).toBeVisible();
            await assertNoOverflow(page, `${tag}/overview-marked`);
          } finally {
            await clearMarks(page);
          }
        });

        test(`the top level of the settings never pans sideways (${language.key})`, async ({ page }) => {
          const tag = `${viewport.name}/${language.key}`;
          await goto(page);
          await page.locator(".header-actions .settings-entry").click();
          await settled(page);

          await expect(page.locator(".settings-group")).toHaveCount(4);
          await expect(page.locator(".setting-row")).toHaveCount(10);
          await assertNoOverflow(page, `${tag}/settings`);
          await assertTapTargets(page, `${tag}/settings`);

          await (await settingRow(page, "settings.names")).click();
          await waitForSheetSettled(page);
          await expect(page.locator(".names-block")).toHaveCount(2);
          await assertNoOverflow(page, `${tag}/names-sheet`);
          await assertTapTargets(page, `${tag}/names-sheet`);
        });
      });
    }
  });
}
