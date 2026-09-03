const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, waitForSheetSettled } = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "360", width: 360, height: 800 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function assertClean(overflow, offenders, label) {
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: elements sticking out of the viewport: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function assertScreenClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  const offenders = await checkElementsWithinViewport(page);
  assertClean(overflow, offenders, label);
}

async function openSettings(page) {
  await page.locator(".header-actions .settings-entry").click();
  await waitForContentSettled(page);
}

async function settingRow(page, key) {
  const label = await page.evaluate((name) => window.t(name), key);
  return page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: label }) });
}

for (const viewport of VIEWPORTS) {
  test.describe(`previously-uncovered sheets @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`subjects sheet + color dialog fit (${lang.key})`, async ({ page }) => {
          await goto(page);
          await openSettings(page);
          await (await settingRow(page, "settings.names")).click();
          await waitForSheetSettled(page);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/subjects-sheet`);

          await page.locator(".swatch-trigger").first().click();
          await expect(page.locator(".color-dialog")).toBeVisible();
          await assertScreenClean(page, `${viewport.name}/${lang.key}/color-dialog`);
        });

        test(`password sheet fits (${lang.key})`, async ({ page }) => {
          await goto(page);
          await openSettings(page);
          await (await settingRow(page, "settings.password")).click();
          await waitForSheetSettled(page);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/password-sheet`);
        });

        test(`pinboard folder sheet and post sheet fit (${lang.key})`, async ({ page }) => {
          await goto(page);
          await page.locator(".tabbar .tab").nth(4).click();
          await waitForContentSettled(page);

          await page.locator(".chipbar .chip").nth(2).click();
          await waitForSheetSettled(page);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/folder-sheet`);
          await page.locator(".sheet-close").click();
          await waitForContentSettled(page);

          const firstTile = page.locator(".row").first();
          await expect(firstTile).toBeVisible();
          await firstTile.click();
          await waitForSheetSettled(page);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/post-sheet`);
        });

        test(`letter detail page fits (${lang.key})`, async ({ page }) => {
          await goto(page);
          await page.locator(".tabbar .tab").nth(3).click();
          await waitForContentSettled(page);
          const firstLetter = page.locator(".row").first();
          await expect(firstLetter).toBeVisible();
          await firstLetter.click();
          await waitForContentSettled(page);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/letter-detail`);
        });
      });
    }
  });
}
