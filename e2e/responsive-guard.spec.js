const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkSheetContainment,
  waitForSheetSettled,
} = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "360", width: 360, height: 800 },
  { name: "390", width: 390, height: 844 },
  { name: "430", width: 430, height: 932 },
  { name: "740x360-landscape", width: 740, height: 360 },
];

const VIEWS = [
  { key: "overview", tabIndex: 0 },
  { key: "timetable", tabIndex: 1 },
  { key: "absence", tabIndex: 2 },
  { key: "letters", tabIndex: 3 },
  { key: "pinboard", tabIndex: 4 },
  { key: "settings", gear: true },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openView(page, view) {
  if (view.gear) {
    await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
  } else {
    await page.locator(".tabbar .tab").nth(view.tabIndex).click();
  }
  await waitForContentSettled(page);
}

function assertNoStructuralOverflow(overflow, elementOffenders, label) {
  expect(overflow.overflow, `${label}: document.scrollingElement.scrollWidth (${overflow.scrollWidth}) exceeds clientWidth (${overflow.clientWidth})`).toBe(false);
  expect(elementOffenders, `${label}: elements sticking out of the viewport: ${JSON.stringify(elementOffenders)}`).toEqual([]);
}

function assertTapTargets(offenders, label) {
  expect(offenders, `${label}: tap targets below 44px effective hit area: ${JSON.stringify(offenders)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  test.describe(`viewport ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const view of VIEWS) {
      test(`${view.key} has no horizontal overflow and no undersized tap targets`, async ({ page }) => {
        await goto(page);
        await openView(page, view);

        const overflow = await checkHorizontalOverflow(page);
        const elementOffenders = await checkElementsWithinViewport(page);
        assertNoStructuralOverflow(overflow, elementOffenders, `${viewport.name}/${view.key}`);

        const tapOffenders = await checkTapTargets(page);
        assertTapTargets(tapOffenders, `${viewport.name}/${view.key}`);
      });
    }

    test("absence wizard type step stays within the viewport without scrolling", async ({ page }) => {
      await goto(page);
      await openView(page, { key: "absence", tabIndex: 2 });
      await page.getByRole("button", { name: /Abwesenheit melden/ }).click();
      await page.waitForSelector(".sw-content");
      await page.waitForTimeout(120);

      const overflow = await checkHorizontalOverflow(page);
      const elementOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(overflow, elementOffenders, `${viewport.name}/absence-wizard-type`);

      const fits = await page.evaluate(() => {
        const content = document.querySelector(".sw-content");
        const next = document.querySelector(".sw-next");
        return {
          present: !!content,
          overflow: content.scrollHeight - content.clientHeight,
          nextVisible: next.getBoundingClientRect().bottom <= window.innerHeight + 1,
        };
      });
      expect(fits.present).toBe(true);
      expect(fits.overflow).toBeLessThanOrEqual(1);
      expect(fits.nextVisible).toBe(true);

      const tapOffenders = await checkTapTargets(page);
      assertTapTargets(tapOffenders, `${viewport.name}/absence-wizard-type`);
    });

    test("settings notify sheet with many rows stays within the viewport and is fully visible or scrollable", async ({ page }) => {
      await goto(page);
      await openView(page, { key: "settings", gear: true });
      const notifyRow = page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: "Dienst" }) });
      await notifyRow.click();
      await waitForSheetSettled(page);

      const overflow = await checkHorizontalOverflow(page);
      const elementOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(overflow, elementOffenders, `${viewport.name}/notify-sheet`);

      const containment = await checkSheetContainment(page);
      expect(containment.present).toBe(true);
      expect(containment.fitsViewport).toBe(true);
      if (containment.overflows) expect(containment.scrollable).toBe(true);

      const tapOffenders = await checkTapTargets(page);
      assertTapTargets(tapOffenders, `${viewport.name}/notify-sheet`);

      await page.locator(".notify-advanced-toggle").click();
      await expect(page.locator(".notify-advanced")).toBeVisible();

      const openOverflow = await checkHorizontalOverflow(page);
      const openOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(openOverflow, openOffenders, `${viewport.name}/notify-sheet-advanced`);
      assertTapTargets(await checkTapTargets(page), `${viewport.name}/notify-sheet-advanced`);
    });

    test("technical details sheet stays within the viewport and is fully visible or scrollable", async ({ page }) => {
      await goto(page);
      await openView(page, { key: "settings", gear: true });
      const profileRow = page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: "Profil" }) });
      await profileRow.click();
      await waitForSheetSettled(page);

      const overflow = await checkHorizontalOverflow(page);
      const elementOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(overflow, elementOffenders, `${viewport.name}/tech-details-sheet`);

      const containment = await checkSheetContainment(page);
      expect(containment.present).toBe(true);
      expect(containment.fitsViewport).toBe(true);
      if (containment.overflows) expect(containment.scrollable).toBe(true);

      const tapOffenders = await checkTapTargets(page);
      assertTapTargets(tapOffenders, `${viewport.name}/tech-details-sheet`);
    });
  });
}
