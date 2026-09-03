const { test, expect } = require("@playwright/test");
const {
  goto,
  waitForSheetSettled,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
} = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

async function settingRow(page, key) {
  const label = await page.evaluate((name) => window.t(name), key);
  return page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: label }) });
}

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openSettings(page) {
  await page.locator(".header-actions .settings-entry").click();
  await waitForContentSettled(page);
}

async function assertClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  const offenders = await checkElementsWithinViewport(page);
  expect(
    overflow.overflow,
    `${label}: scrolling containers overflow: ${JSON.stringify(overflow.offendingContainers)}`
  ).toBe(false);
  expect(offenders, `${label}: elements stick out of the viewport: ${JSON.stringify(offenders)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  test.describe(`RTL (ar) settings sheets @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: "ar" });

    test("the password sheet does not pan into empty space in Arabic", async ({ page }) => {
      await goto(page);
      expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe("rtl");

      await openSettings(page);
      await (await settingRow(page, "settings.password")).click();
      await waitForSheetSettled(page);

      await assertClean(page, `rtl/${viewport.name}/password-sheet`);

      const panned = await page.evaluate(() => {
        const body = document.querySelector(".sheet-body");
        if (!body) return null;
        return { scrollWidth: body.scrollWidth, clientWidth: body.clientWidth };
      });
      expect(panned, "the password sheet has a scrollable body").not.toBeNull();
      expect(
        panned.scrollWidth,
        `the hidden username field pans the sheet sideways: ${JSON.stringify(panned)}`
      ).toBeLessThanOrEqual(panned.clientWidth + 1);

      const tapOffenders = await checkTapTargets(page);
      expect(tapOffenders, `rtl/${viewport.name}/password-sheet: ${JSON.stringify(tapOffenders)}`).toEqual([]);
    });

    test("the subject sheet and its colour dialog stay inside the screen in Arabic", async ({ page }) => {
      await goto(page);
      await openSettings(page);
      await (await settingRow(page, "settings.names")).click();
      await waitForSheetSettled(page);
      await assertClean(page, `rtl/${viewport.name}/subjects-sheet`);

      await page.locator(".swatch-trigger").first().click();
      await expect(page.locator(".color-dialog")).toBeVisible();
      await assertClean(page, `rtl/${viewport.name}/color-dialog`);

      const inside = await page.evaluate(
        () => !!document.querySelector(".scrim .color-dialog-scrim")
      );
      expect(inside, "the colour dialog hangs inside the sheet scrim").toBe(true);

      const tapOffenders = await checkTapTargets(page);
      expect(tapOffenders, `rtl/${viewport.name}/color-dialog: ${JSON.stringify(tapOffenders)}`).toEqual([]);
    });

    test("Arabic drops the letter spacing that would break the joined script", async ({ page }) => {
      await goto(page);
      const tracked = await page.evaluate(() => {
        const offenders = [];
        for (const node of document.querySelectorAll("body *")) {
          const style = getComputedStyle(node);
          const spacing = parseFloat(style.letterSpacing);
          if (!Number.isNaN(spacing) && Math.abs(spacing) > 0.01) {
            offenders.push(`${node.tagName}.${String(node.className || "")} ${style.letterSpacing}`);
          }
          if (style.textTransform === "uppercase") {
            offenders.push(`${node.tagName}.${String(node.className || "")} uppercase`);
          }
        }
        return offenders.slice(0, 10);
      });
      expect(tracked, `Arabic must not carry tracking: ${JSON.stringify(tracked)}`).toEqual([]);
    });
  });
}
