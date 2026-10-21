const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

async function open(page, lang, area, theme = "light", extraCookies = []) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "e2e_lang", value: lang, url: BASE_URL }, { name: "e2e_modules", value: "all", url: BASE_URL }, ...extraCookies]);
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  await goto(page);
  await openArea(page, area);
  await page.waitForSelector(["calendar", "post", "overview"].includes(area) ? ".row, .empty" : ".school-list .list-row, .school-list .empty", { timeout: 10000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 10000 }).catch(() => {});
}

async function expectInside(page, locator, width) {
  const box = await locator.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
}

async function nothingLeavesTheApp(page) {
  expect(await page.locator(".school-list [href], .school-list [target], .sheet [href], .sheet [target]").count()).toBe(0);
}

for (const width of [390, 1024]) {
  for (const lang of ["de", "ar"]) {
    test.describe(`forums, texts and info screens ${width} ${lang}`, () => {
      test.use({ viewport: { width, height: 800 } });

      test("the forum view groups forums, shows unread posts and marks everything read after a confirmation", async ({ page }) => {
        await open(page, lang, "forums", "light", [{ name: "e2e_forum_run", value: `forum-${process.pid}-${Date.now()}-${width}-${lang}`, url: BASE_URL }]);
        await expect(page.locator(".school-list .list-section")).toHaveCount(2);
        const rows = page.locator(".school-list .forum-row");
        await expect(rows).toHaveCount(3);
        await expect(rows.first().locator(".row-title")).toHaveText("School yard");
        await expect(page.locator(".school-list .forum-unread")).toHaveCount(2);
        const long = page.locator(".forum-row .row-title", { hasText: "Library and reading club" });
        expect(await long.getAttribute("dir")).toBe("auto");
        await nothingLeavesTheApp(page);
        await expectInside(page, long, width);
        await expectInside(page, page.locator(".forum-read"), width);
        await page.locator(".forum-read").click();
        await expect(page.locator(".sheet .sheet-title")).toBeVisible();
        await page.locator(".sheet .btn.ghost").click();
        await expect(page.locator(".school-list .forum-unread")).toHaveCount(2);
        await page.locator(".forum-read").click();
        await page.locator(".sheet .btn:not(.ghost)").click();
        await expect(page.locator(".school-list .forum-unread")).toHaveCount(0);
        await expect(page.locator(".forum-read")).toHaveCount(0);
      });

      test("the text view shows the visible texts first and the hidden ones through the IServ filter", async ({ page }) => {
        await open(page, lang, "texts");
        const rows = page.locator(".school-list .text-row");
        await expect(rows).toHaveCount(2);
        await expect(rows.first().locator(".row-title")).toHaveText("Minutes of the class council");
        await page.locator(".texts-filter").click();
        await page.locator(".sheet .texts-filter-opt", { hasText: "Hidden" }).click();
        await expect(rows).toHaveCount(1);
        await expect(rows.first().locator(".row-title")).toHaveText("Old reading list");
        await nothingLeavesTheApp(page);
        await expectInside(page, page.locator(".texts-filter"), width);
      });

      test("the info screen view lists every screen", async ({ page }) => {
        await open(page, lang, "infodisplay");
        await expect(page.locator(".school-list .screen-row .row-title")).toHaveText(["Entrance hall", "Canteen"]);
        await nothingLeavesTheApp(page);
      });

      test("the whiteboard view lists every whiteboard with owner and dates and says when there is none", async ({ page }) => {
        await open(page, lang, "whiteboards");
        const rows = page.locator(".school-list .whiteboard-row");
        await expect(rows.locator(".row-title")).toHaveText(["Fractions practice", "Ideas for the class trip with a long title that needs two lines on a phone"]);
        await expect(rows.first().locator(".row-sub")).toContainText("Class teacher");
        await expect(page.locator(".school-list .whiteboard-row button")).toHaveCount(0);
        await nothingLeavesTheApp(page);
        await expectInside(page, rows.nth(1).locator(".row-title"), width);
        await open(page, lang, "whiteboards", "light", [{ name: "e2e_empty", value: "whiteboards", url: BASE_URL }]);
        await expect(page.locator(".school-list .whiteboard-row")).toHaveCount(0);
        await expect(page.locator(".school-list .empty b")).toHaveCount(1);
      });
    });
  }
}

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`forum, text and info screen look ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });

      test("every view next to the school events view", async ({ page }) => {
        for (const area of ["forums", "texts", "infodisplay", "whiteboards", "calendar", "post", "overview"]) {
          await open(page, "de", area, theme);
          expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
          await page.screenshot({ path: `test-results/look-${area}-${width}-${theme}.png`, fullPage: true });
          if (area === "forums") {
            await open(page, "de", "forums", theme, [{ name: "e2e_empty", value: "forums_unreadable", url: BASE_URL }]);
            await expect(page.locator(".school-list .empty b")).toHaveText("Noch nicht lesbar");
            await page.screenshot({ path: `test-results/look-forums-unreadable-${width}-${theme}.png`, fullPage: true });
          }
          if (area === "overview") {
            const forum = page.locator('[data-block^="forum:"]').first();
            await expect(forum).toBeVisible();
            await forum.scrollIntoViewIfNeeded();
            await page.screenshot({ path: `test-results/look-overview-forums-${width}-${theme}.png` });
          }
        }
      });
    });
  }
}
