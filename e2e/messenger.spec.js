const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
} = require("./helpers");

const LANGUAGES = [
  { key: "de", locale: "de-DE", rtl: false },
  { key: "ru", locale: "ru-RU", rtl: false },
  { key: "ar", locale: "ar", rtl: true },
];

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const KEYBOARD_HEIGHT = 420;
const FORBIDDEN_ROUTES = ["read_markers", "/receipt/"];

async function watchForbiddenRoutes(page) {
  const seen = [];
  page.on("request", (request) => {
    const url = request.url();
    if (FORBIDDEN_ROUTES.some((fragment) => url.includes(fragment))) seen.push(url);
  });
  return seen;
}

async function openMessenger(page) {
  await page.locator(".tabbar .tab").nth(4).click();
  await page.waitForSelector(".rows .row", { timeout: 8000 });
}

async function openFirstRoom(page) {
  await page.locator(".rows .row").first().click();
  await page.waitForSelector(".chat-log .chat-msg", { timeout: 8000 });
}

async function expectClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(
    overflow.overflow,
    `${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth} ${JSON.stringify(overflow.offendingContainers)}`
  ).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const small = await checkTapTargets(page);
  expect(small, `${label}: ${JSON.stringify(small)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    const label = `${viewport.name}/${lang.key}`;

    test.describe(`[P198] messenger ${label}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("the room list fits, filters and keeps its hit areas", async ({ page }) => {
        await goto(page);
        await openMessenger(page);

        await expect(page.locator(".rows .row")).toHaveCount(2);
        await expect(page.locator(".rows .row").first().locator(".badge")).toBeVisible();
        await expectClean(page, `${label} room list`);

        await page.locator(".search-input").fill("Sekretariat");
        await expect(page.locator(".rows .row")).toHaveCount(1);
        await page.locator(".search-clear").click();
        await expect(page.locator(".rows .row")).toHaveCount(2);
        await expectClean(page, `${label} filtered list`);
      });

      test("the room shows both sides on the right edge and never asks for a read marker", async ({ page }) => {
        const forbidden = await watchForbiddenRoutes(page);
        await goto(page);
        await openMessenger(page);
        await openFirstRoom(page);

        await expect(page.locator(".chat-msg.mine")).not.toHaveCount(0);
        await expect(page.locator(".chat-msg:not(.mine) .chat-from")).not.toHaveCount(0);
        await expect(page.locator(".chat-system")).not.toHaveCount(0);
        await expect(page.locator(".composer-input")).toBeVisible();
        await expect(page.locator(".tabbar")).toHaveCount(0);

        const mine = await page.locator(".chat-msg.mine").first().boundingBox();
        const theirs = await page.locator(".chat-msg:not(.mine)").first().boundingBox();
        if (lang.rtl) {
          expect(mine.x, `${label}: own post must sit on the left in right-to-left`).toBeLessThan(theirs.x);
        } else {
          expect(mine.x, `${label}: own post must sit on the right`).toBeGreaterThan(theirs.x);
        }

        await expectClean(page, `${label} room`);
        expect(forbidden, `${label}: the client must never mark anything as read`).toEqual([]);
      });

      test("the older button loads the previous page on top", async ({ page }) => {
        await goto(page);
        await openMessenger(page);
        await openFirstRoom(page);

        const entries = page.locator(".chat-log .chat-msg, .chat-log .chat-system");
        const before = await entries.count();
        await page.locator(".chat-older-btn").dispatchEvent("click");
        await expect(page.locator(".chat-older-btn")).toHaveCount(0);
        await expect
          .poll(() => entries.count(), { message: `${label}: older page must add entries` })
          .toBeGreaterThan(before);
        await expectClean(page, `${label} room after paging`);
      });

      test("scrolling to the top pulls the older page in without a tap", async ({ page }) => {
        await goto(page);
        await openMessenger(page);
        await openFirstRoom(page);
        await page.setViewportSize({ width: viewport.width, height: KEYBOARD_HEIGHT });
        await page.waitForTimeout(120);

        const log = page.locator(".chat-log");
        const scrollable = await log.evaluate((node) => node.scrollHeight > node.clientHeight + 1);
        expect(scrollable, `${label}: the fixture history must overflow the short log`).toBe(true);
        const entries = page.locator(".chat-log .chat-msg, .chat-log .chat-system");
        const before = await entries.count();
        await log.evaluate((node) => { node.scrollTop = node.scrollHeight; });
        await page.waitForTimeout(60);
        await log.evaluate((node) => { node.scrollTop = 0; });
        await expect(page.locator(".chat-older-btn")).toHaveCount(0);
        await expect
          .poll(() => entries.count(), { message: `${label}: scrolling up must add entries` })
          .toBeGreaterThan(before);
      });

      test("the input grows, and it stays reachable when the keyboard takes the lower half", async ({ page }) => {
        await goto(page);
        await openMessenger(page);
        await openFirstRoom(page);

        const input = page.locator(".composer-input");
        const oneLine = (await input.boundingBox()).height;
        await input.fill("Zeile eins\nZeile zwei\nZeile drei\nZeile vier\nZeile fuenf\nZeile sechs");
        const grown = (await input.boundingBox()).height;
        expect(grown, `${label}: the input must grow`).toBeGreaterThan(oneLine);
        expect(grown, `${label}: the input must stop growing at its cap`).toBeLessThanOrEqual(140);
        const scrolls = await input.evaluate((node) => node.scrollHeight > node.clientHeight + 1);
        expect(scrolls, `${label}: past the cap the input scrolls inside itself`).toBe(true);

        await page.setViewportSize({ width: viewport.width, height: KEYBOARD_HEIGHT });
        await page.waitForTimeout(120);
        const composer = await page.locator(".composer").boundingBox();
        expect(composer.y + composer.height, `${label}: composer bottom in the compact case`).toBeLessThanOrEqual(KEYBOARD_HEIGHT + 1);
        const log = await page.locator(".chat-log").boundingBox();
        expect(log.height, `${label}: the log keeps room in the compact case`).toBeGreaterThan(0);
        await expectClean(page, `${label} room with the keyboard open`);
      });
    });
  }
}
