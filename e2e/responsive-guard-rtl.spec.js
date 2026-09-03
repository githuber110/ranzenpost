const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkTapTargets } = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "360", width: 360, height: 800 },
  { name: "390", width: 390, height: 844 },
  { name: "430", width: 430, height: 932 },
  { name: "740x360-landscape", width: 740, height: 360 },
];

const VIEWS = [
  { key: "overview", tab: null },
  { key: "timetable", tab: 1 },
  { key: "absence", tab: 2 },
  { key: "letters", tab: 3 },
  { key: "pinboard", tab: 4 },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

for (const viewport of VIEWPORTS) {
  test.describe(`RTL (ar) viewport ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: "ar" });

    test("boots in RTL and every tab has no horizontal overflow or undersized tap targets", async ({ page }) => {
      await goto(page);
      const dir = await page.evaluate(() => document.documentElement.getAttribute("dir"));
      expect(dir).toBe("rtl");

      const tabs = page.locator(".tabbar .tab");
      const count = await tabs.count();
      expect(count).toBeGreaterThan(0);

      for (const view of VIEWS) {
        if (view.tab !== null) {
          if (view.tab >= count) continue;
          await tabs.nth(view.tab).click();
          await waitForContentSettled(page);
        }

        const overflow = await checkHorizontalOverflow(page);
        const elementOffenders = await checkElementsWithinViewport(page);
        expect(overflow.overflow, `RTL ${viewport.name}/${view.key}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`).toBe(false);
        expect(elementOffenders, `RTL ${viewport.name}/${view.key}: ${JSON.stringify(elementOffenders)}`).toEqual([]);

        const tapOffenders = await checkTapTargets(page);
        expect(tapOffenders, `RTL ${viewport.name}/${view.key}: ${JSON.stringify(tapOffenders)}`).toEqual([]);
      }
    });
  });
}
