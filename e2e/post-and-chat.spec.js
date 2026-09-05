const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
} = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "360", width: 360, height: 800 },
  { name: "390", width: 390, height: 844 },
  { name: "414", width: 414, height: 896 },
  { name: "768", width: 768, height: 1024 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "en", locale: "en-US" },
  { key: "ar", locale: "ar", rtl: true },
  { key: "tr", locale: "tr-TR" },
  { key: "ru", locale: "ru-RU" },
  { key: "uk", locale: "uk-UA" },
];

const POST_TAB = 3;
const CHAT_TAB = 4;

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function expectClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(
    overflow.overflow,
    `${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`
  ).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const small = await checkTapTargets(page);
  expect(small, `${label}: ${JSON.stringify(small)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    const label = `${viewport.name}/${lang.key}`;

    test.describe(`[P198] tab bar and Post segment ${label}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("five tabs with badges fit, and the segment carries two counters", async ({ page }) => {
        await goto(page);
        await settled(page);
        await expect(page.locator(".tabbar .tab")).toHaveCount(5);
        await expect(page.locator(".tabbar .tab .badge")).not.toHaveCount(0);
        await expectClean(page, `${label} tab bar with badges`);

        const direction = await page.evaluate(() => document.documentElement.getAttribute("dir"));
        expect(direction === "rtl", `${label}: right to left mirroring`).toBe(!!lang.rtl);

        await page.locator(".tabbar .tab").nth(POST_TAB).click();
        await settled(page);
        const segment = page.locator(".list-head .segment button");
        await expect(segment).toHaveCount(2);
        await expect(segment.nth(0).locator(".seg-badge")).toBeVisible();
        await expectClean(page, `${label} post segment`);

        await segment.nth(1).click();
        await settled(page);
        await expect(page.locator(".chipbar .chip")).toHaveCount(3);
        await expectClean(page, `${label} post pinboard segment`);

        await page.locator(".tabbar .tab").nth(CHAT_TAB).click();
        await settled(page);
        await expect(page.locator(".rows .row")).not.toHaveCount(0);
        await expectClean(page, `${label} chat tab`);
      });
    });
  }
}

test.describe("[P198] the Post tab holds both areas", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("[P221] inbox and archive stand side by side and one tap switches", async ({ page }) => {
    await goto(page);
    await page.locator(".tabbar .tab").nth(POST_TAB).click();
    await settled(page);
    const chips = page.locator(".list-head .chipbar .chip");
    await expect(chips).toHaveCount(2);
    expect(await chips.nth(0).getAttribute("aria-selected")).toBe("true");
    expect(await chips.nth(1).getAttribute("aria-selected")).toBe("false");

    await chips.nth(1).click();
    await settled(page);
    await expect(page.locator(".sheet")).toHaveCount(0);
    expect(await page.locator(".list-head .chipbar .chip").nth(1).getAttribute("aria-selected")).toBe("true");

    await page.locator(".list-head .segment button").nth(1).click();
    await settled(page);
    await expect(page.locator(".sort-hint")).toBeVisible();
  });

  test("[P220] the post tab comes back on the letters segment", async ({ page }) => {
    await goto(page);
    await page.locator(".tabbar .tab").nth(POST_TAB).click();
    await settled(page);
    await page.locator(".list-head .segment button").nth(1).click();
    await settled(page);
    await page.locator(".tabbar .tab").nth(0).click();
    await settled(page);
    await page.locator(".tabbar .tab").nth(POST_TAB).click();
    await settled(page);
    expect(await page.locator(".list-head .segment button").nth(0).getAttribute("aria-selected")).toBe("true");
  });

  test("[P204] a noticeboard row on the overview opens in place and comes back to the overview", async ({ page }) => {
    await goto(page);
    await settled(page);
    await page.locator('.panel[data-area="pinboard"] [data-block] button, .panel[data-area="pinboard"] button[data-block]').first().click();
    await settled(page);
    await expect(page.locator(".sheet")).toBeVisible();
    await expect(page.locator(".list-head .segment")).toHaveCount(0);
    await page.locator(".sheet-close").click();
    await settled(page);
    await expect(page.locator('.panel[data-area="pinboard"]').first()).toBeVisible();
  });
});

test.describe("[P198] the chat chapter on the overview", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("an unread room shows up on the overview and leads straight into the room", async ({ page }) => {
    await goto(page);
    await settled(page);
    const panel = page.locator('.panel[data-area="messenger"]').first();
    await expect(panel).toHaveCount(1);
    await panel.locator("[data-block]").first().click();
    await settled(page);
    await expect(page.locator(".chat-log")).toBeVisible();
    await expect(page.locator(".tabbar")).toHaveCount(0);
  });
});
