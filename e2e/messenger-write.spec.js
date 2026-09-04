const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
} = require("./helpers");

const CHAT_TAB = 4;
const RECEIPT_ROUTES = ["read_markers", "/receipt/", "api/messenger/read"];
const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;

test.beforeEach(async ({ page }) => {
  await page.context().addCookies([{ name: "e2e_room_writes", value: "1", url: BASE_URL }]);
});

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

async function tapNext(page) {
  await page.locator(".sw-next").dispatchEvent("click");
  await page.waitForTimeout(80);
}

function watchReceipts(page) {
  const seen = [];
  page.on("request", (request) => {
    const url = request.url();
    if (RECEIPT_ROUTES.some((fragment) => url.includes(fragment))) seen.push(url);
  });
  return seen;
}

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openChat(page) {
  await page.locator(".tabbar .tab").nth(CHAT_TAB).click();
  await page.waitForSelector(".rows .row", { timeout: 8000 });
}

const PROGRESS_RAIL = "sw-dot";

async function expectClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: horizontal overflow`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const small = (await checkTapTargets(page)).filter(
    (offender) => !String(offender.className).includes(PROGRESS_RAIL)
  );
  expect(small, `${label}: ${JSON.stringify(small)}`).toEqual([]);
}

test.describe("[P198] the deliberate read marker", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("nothing is marked until the button is tapped, and then exactly once", async ({ page }) => {
    const seen = watchReceipts(page);
    await goto(page);
    await openChat(page);
    expect(seen, "browsing the list must not mark anything").toEqual([]);

    await page.locator(".rows .row").first().click();
    await page.waitForSelector(".chat-log .chat-msg", { timeout: 8000 });
    await page.waitForTimeout(200);
    expect(seen, "opening a room must not mark anything").toEqual([]);

    const button = page.locator(".messenger-read");
    await expect(button).toBeVisible();
    await button.click();
    await page.waitForTimeout(400);
    expect(seen.length, `exactly one marker request: ${JSON.stringify(seen)}`).toBe(1);
    expect(seen[0]).toContain("api/messenger/read");
    await expect(page.locator(".messenger-read")).toHaveCount(0);
  });

  test("a room without anything unread offers no marker at all", async ({ page }) => {
    const seen = watchReceipts(page);
    await goto(page);
    await openChat(page);
    await page.locator(".rows .row").nth(1).click();
    await page.waitForSelector(".chat-log", { timeout: 8000 });
    await expect(page.locator(".messenger-read")).toHaveCount(0);
    expect(seen).toEqual([]);
  });
});

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    const label = `${viewport.name}/${lang.key}`;

    test.describe(`[P198] the teacher room wizard ${label}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("search, summary and creation land in the new room without a second POST", async ({ page }) => {
        const posts = [];
        page.on("request", (request) => {
          if (request.method() === "POST" && request.url().includes("api/messenger/room/teacher")) {
            posts.push(request.url());
          }
        });
        await goto(page);
        await openChat(page);

        await page.locator(".list-actions .btn").click();
        await page.waitForSelector(".sw-content");
        await expectClean(page, `${label} wizard step teacher`);

        await page.locator(".sw-body .search-input").fill("Osterkamp");
        await page.waitForSelector(".sw-results .opt", { timeout: 8000 });
        await expectClean(page, `${label} wizard hits`);
        await page.locator(".sw-results .opt").first().click();

        await tapNext(page);
        await expect(page.locator(".sw-body input[type=checkbox]")).toHaveCount(1);
        expect(await page.locator(".sw-body input[type=checkbox]").isChecked()).toBe(false);
        await expectClean(page, `${label} wizard parents`);

        await tapNext(page);
        await expect(page.locator(".create-name")).toBeVisible();
        await expectClean(page, `${label} wizard summary`);

        await page.evaluate(() => {
          const button = document.querySelector(".sw-next");
          button.click();
          button.click();
        });
        await page.waitForSelector(".chat-log", { timeout: 12000 });
        expect(posts.length, `exactly one create request: ${JSON.stringify(posts)}`).toBe(1);
      });

      test("a teacher who already has a room brings the duplicate warning first", async ({ page }) => {
        await goto(page);
        await openChat(page);
        await page.locator(".list-actions .btn").click();
        await page.waitForSelector(".sw-content");
        await page.locator(".sw-body .search-input").fill("Behrend");
        await page.waitForSelector(".sw-results .opt", { timeout: 8000 });
        await page.locator(".sw-results .opt").first().click();
        await tapNext(page);
        await tapNext(page);
        await expect(page.locator(".create-name")).toBeVisible();
        await expectClean(page, `${label} wizard duplicate`);
        await page.locator(".sw-body .btn").click();
        await page.waitForSelector(".chat-log", { timeout: 8000 });
      });

      test("an empty search never sends a request and never blocks the way out", async ({ page }) => {
        const searches = [];
        page.on("request", (request) => {
          if (request.url().includes("api/messenger/teachers")) searches.push(request.url());
        });
        await goto(page);
        await openChat(page);
        await page.locator(".list-actions .btn").click();
        await page.waitForSelector(".sw-content");
        await page.locator(".sw-body .search-input").fill("   ");
        await page.waitForTimeout(500);
        expect(searches).toEqual([]);
        await tapNext(page);
        await expect(page.locator(".sw-status")).toHaveText(/.+/);
        await page.locator(".sw-head-actions .icon-btn").click();
        await expect(page.locator(".tabbar")).toHaveCount(1);
      });
    });
  }
}
