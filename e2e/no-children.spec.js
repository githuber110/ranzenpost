const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const WIDTHS = [390, 1024];

async function open(page, width) {
  await page.setViewportSize({ width, height: 844 });
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: "de", url: BASE_URL },
    { name: "e2e_modules", value: "all", url: BASE_URL },
    { name: "e2e_scenario", value: "no-children", url: BASE_URL },
  ]);
  await goto(page);
  await page.waitForTimeout(300);
}

async function navViews(page) {
  const shown = await page.evaluate(() => [...document.querySelectorAll(".tabbar .tab, nav.rail .rail-item")].map((node) => node.dataset.view).filter(Boolean));
  const more = page.locator(".tabbar .tab-more");
  if (!(await more.count())) return shown;
  await more.click();
  await page.waitForSelector(".sheet .more-row", { timeout: 5000 });
  const hidden = await page.locator(".sheet .more-row").evaluateAll((nodes) => nodes.map((node) => node.dataset.area));
  await page.locator(".sheet-close").click();
  await page.waitForSelector(".scrim", { state: "detached", timeout: 5000 });
  return shown.concat(hidden);
}

for (const width of WIDTHS) {
  test.describe(`an account without a linked profile at ${width}px`, () => {
    test("offers the school areas and never the timetable or absences", async ({ page }) => {
      await open(page, width);
      const views = await navViews(page);
      expect(views).toContain("overview");
      expect(views).toContain("post");
      expect(views).toContain("calendar");
      expect(views).not.toContain("timetable");
      expect(views).not.toContain("absence");
      expect(await page.locator(".panel[data-area='today']").count()).toBe(0);
      expect(await page.locator(".error").count()).toBe(0);
      const overflow = await checkHorizontalOverflow(page);
      expect(overflow.overflow, JSON.stringify(overflow)).toBe(false);
      expect(await checkElementsWithinViewport(page)).toEqual([]);
    });

    test("keeps the settings free of timetable and sick note rows", async ({ page }) => {
      await open(page, width);
      await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
      await page.waitForTimeout(200);
      const labels = await page.locator(".setting-row .lbl").allTextContents();
      for (const hidden of ["Telefonnummern", "Fächer & Lehrkräfte", "Stundenzeiten"]) expect(labels).not.toContain(hidden);
      expect(labels).toContain("Ferienkalender");
    });
  });
}
