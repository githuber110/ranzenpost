const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const LETTERS_TAB = 3;
const REPLY_LETTER = "Tierpark";
const CONFIRMED_LETTER = "Hausordnung";
const MESSAGE = "Wir kommen gern mit.";

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openLetter(page, title) {
  await page.locator(".tabbar .tab").nth(LETTERS_TAB).click();
  await waitForContentSettled(page);
  await page.locator(".rows .row", { hasText: title }).click();
  await waitForContentSettled(page);
}

async function expectFits(page, label) {
  const [overflow, offenders] = await Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

test.describe("message to the school on a confirmed letter @ 320", () => {
  test.use({ viewport: { width: 320, height: 800 } });

  for (const lang of LANGUAGES) {
    test.describe(lang.key, () => {
      test.use({ locale: lang.locale });

      test(`a confirmed letter with a reply form sends one message after the preview (${lang.key})`, async ({ page }) => {
        const posts = [];
        page.on("request", (request) => {
          if (request.method() === "POST" && request.url().includes("/api/letters/reply")) posts.push(request.postDataJSON());
        });
        await goto(page);
        await openLetter(page, REPLY_LETTER);

        await expect(page.locator(".confirm-card.done")).toBeVisible();
        const action = page.locator(".letter-reply-action");
        await expect(action).toHaveCount(1);
        await expect(action).toHaveClass(/ghost/);
        await expectFits(page, `${lang.key}/letter-with-reply`);

        await action.click();
        const sheet = page.locator(".sheet");
        await expect(sheet).toBeVisible();
        await expect(sheet.locator(".letter-reply-next")).toBeDisabled();
        await sheet.locator("textarea.letter-reply-text").fill(`  ${MESSAGE}  `);
        await sheet.locator(".letter-reply-next").click();

        await expect(sheet.locator(".letter-reply-quote")).toHaveText(MESSAGE);
        await expectFits(page, `${lang.key}/letter-reply-preview`);
        expect(posts).toEqual([]);

        await sheet.locator(".letter-reply-send").dblclick();
        await expect(page.locator(".sheet")).toHaveCount(0);
        const sent = await page.evaluate(() => t("letters.reply.sent"));
        await expect(page.locator(".toast")).toContainText(sent);

        expect(posts.length).toBe(1);
        expect(posts[0].text).toBe(MESSAGE);
        expect(posts[0].confirmed).toBe(true);
        expect(posts[0].request_id).toMatch(/^[0-9a-f]{32}$/);
      });

      test(`a confirmed letter without a reply form shows no action (${lang.key})`, async ({ page }) => {
        await goto(page);
        await openLetter(page, CONFIRMED_LETTER);

        await expect(page.locator(".confirm-card.done")).toBeVisible();
        await expect(page.locator(".letter-reply-action")).toHaveCount(0);
      });
    });
  }
});
