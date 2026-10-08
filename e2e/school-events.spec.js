const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

async function open(page, lang, extraCookies = []) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "e2e_lang", value: lang, url: BASE_URL }, { name: "e2e_modules", value: "all", url: BASE_URL }, ...extraCookies]);
  await goto(page);
  await openArea(page, "calendar");
  await page.waitForSelector(".event-row, .empty", { timeout: 10000 });
}

for (const width of [320, 390, 1024]) {
  for (const lang of ["de", "ar"]) {
    test.describe(`school events ${width} ${lang}`, () => {
      test.use({ viewport: { width, height: 800 } });

      test("the days list the events and nothing leaves the screen", async ({ page }) => {
        await open(page, lang);
        expect(await page.locator(".event-day").count()).toBeGreaterThanOrEqual(3);
        const long = page.locator(".event-row .row-title", { hasText: "Information event" });
        await expect(long).toBeVisible();
        const box = await long.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
        const overflow = await checkHorizontalOverflow(page);
        expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
        await page.screenshot({ path: `test-results/school-events-${width}-${lang}.png`, fullPage: true });
      });
    });
  }
}

test.describe("school events empty", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "en-US" });

  test("an emptied calendar shows the neutral empty state", async ({ page }) => {
    await open(page, "en", [{ name: "e2e_empty", value: "calendar", url: BASE_URL }]);
    await expect(page.locator(".empty b")).toHaveText("No upcoming events");
    expect(await page.locator(".event-row").count()).toBe(0);
  });
});
