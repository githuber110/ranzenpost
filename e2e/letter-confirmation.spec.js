const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
  { key: "ar", locale: "ar" },
];

const LETTERS_TAB = 3;

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function collectOverflow(page) {
  return Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]).then(
    ([overflow, offenders]) => ({ overflow, offenders })
  );
}

function assertClean(result, label, failures) {
  if (result.overflow.overflow) {
    failures.push(
      `${label}: scrollWidth ${result.overflow.scrollWidth} > clientWidth ${result.overflow.clientWidth}`
    );
  }
  if (result.offenders.length) {
    failures.push(`${label}: elements sticking out: ${JSON.stringify(result.offenders)}`);
  }
}

async function openLetters(page) {
  await page.locator(".tabbar .tab").nth(LETTERS_TAB).click();
  await waitForContentSettled(page);
}

for (const viewport of VIEWPORTS) {
  test.describe(`[P195] letter confirmation @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`open confirmation marks the row and fits the detail block (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await openLetters(page);

          await expect(page.locator(".row .tag.confirm").first()).toBeVisible();
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/letters-list`, failures);

          await page.locator(".row").first().click();
          await waitForContentSettled(page);

          const block = page.locator(".confirm-card");
          await expect(block).toBeVisible();
          await expect(block.locator("button.confirm-action")).toBeVisible();
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/letter-confirm-block`, failures);

          expect(failures, failures.join("\n")).toEqual([]);
        });

        test(`the confirm button asks first and reports the result (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await openLetters(page);
          await page.locator(".row").first().click();
          await waitForContentSettled(page);

          await page.locator(".confirm-card button.confirm-action").click();
          const sheet = page.locator(".sheet");
          await expect(sheet).toBeVisible();
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/letter-confirm-sheet`, failures);

          await sheet.locator(".btn-stack button").first().click();
          await expect(page.locator(".toast")).toBeVisible();
          await expect(page.locator(".confirm-card.done")).toBeVisible();
          await expect(page.locator(".confirm-card button.confirm-action")).toHaveCount(0);
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/letter-confirm-done`, failures);

          expect(failures, failures.join("\n")).toEqual([]);
        });

        test(`an accept/decline letter offers no send button (${lang.key})`, async ({ page }) => {
          await goto(page);
          await openLetters(page);
          await page.locator(".row").nth(1).click();
          await waitForContentSettled(page);

          const block = page.locator(".confirm-card");
          await expect(block).toBeVisible();
          await expect(block.locator("button")).toHaveCount(0);
        });
      });
    }
  });
}
