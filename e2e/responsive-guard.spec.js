const { test, expect } = require("@playwright/test");
const {
  goto,
  openArea,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkSheetContainment,
  waitForSheetSettled,
} = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

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
  { key: "post-letters", tabIndex: 3 },
  { key: "post-pinboard", tabIndex: 3, segment: 1 },
  { key: "chat", area: "messenger" },
  { key: "more-sheet", tabIndex: 4 },
  { key: "settings", gear: true },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openView(page, view) {
  if (view.gear) {
    await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
  } else if (view.area) {
    await openArea(page, view.area);
    await waitForContentSettled(page);
  } else {
    await page.locator(".tabbar .tab").nth(view.tabIndex).click();
    await waitForContentSettled(page);
    if (view.segment !== undefined) {
      await page.locator(".list-head .segment button").nth(view.segment).click();
    }
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
      const notifyRow = page.locator(".setting-row.notify-setting");
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

      await page.locator(".notify-pick-open").click();
      await expect(page.locator(".notify-services-group").first()).toBeVisible();
      await waitForSheetSettled(page);

      const openOverflow = await checkHorizontalOverflow(page);
      const openOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(openOverflow, openOffenders, `${viewport.name}/notify-picker`);
      assertTapTargets(await checkTapTargets(page), `${viewport.name}/notify-picker`);
    });

    test("technical details page under Help stays within the viewport", async ({ page }) => {
      await goto(page);
      await openView(page, { key: "settings", gear: true });
      await page.locator(".setting-row.tech-setting").click();
      await expect(page.locator(".tech-page .field-group")).toBeVisible();
      expect(await page.locator(".sheet").count()).toBe(0);

      const overflow = await checkHorizontalOverflow(page);
      const elementOffenders = await checkElementsWithinViewport(page);
      assertNoStructuralOverflow(overflow, elementOffenders, `${viewport.name}/tech-details-page`);

      const tapOffenders = await checkTapTargets(page);
      assertTapTargets(tapOffenders, `${viewport.name}/tech-details-page`);
    });
  });
}

const LONG_SUBJECT_VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];
const LONG_SUBJECT_LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

for (const viewport of LONG_SUBJECT_VIEWPORTS) {
  for (const lang of LONG_SUBJECT_LANGUAGES) {
    test.describe(`timetable with subjects IServ only sent as long names ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test(`${viewport.name}/${lang.key} shows the derived codes without overflow or clipping without a way to the full name`, async ({ page }) => {
        await page.context().addCookies([
          { name: "e2e_long_subjects", value: "1", url: BASE_URL },
          { name: "e2e_lang", value: lang.key, url: BASE_URL },
        ]);
        await goto(page);
        await openView(page, { key: "timetable", tabIndex: 1 });

        const label = `${viewport.name}/${lang.key}/timetable-long-subjects`;
        const overflow = await checkHorizontalOverflow(page);
        const elementOffenders = await checkElementsWithinViewport(page);
        assertNoStructuralOverflow(overflow, elementOffenders, label);

        const cells = page.locator(".tt-cell[data-subject]");
        const cellCount = await cells.count();
        expect(cellCount).toBeGreaterThan(0);

        const cellTexts = await page.locator(".tt-cell .sub").allTextContents();
        for (const text of cellTexts) {
          expect(text.length).toBeLessThanOrEqual(4);
        }

        for (let index = 0; index < cellCount; index += 1) {
          const cell = cells.nth(index);
          const ariaLabel = await cell.getAttribute("aria-label");
          expect(ariaLabel, `${label}: cell ${index} has no accessible name for the full subject`).toBeTruthy();
          expect(ariaLabel.length, `${label}: cell ${index} aria-label is as short as the clipped code`).toBeGreaterThan(4);

          const fit = await cell.evaluate((node) => {
            const sub = node.querySelector(".sub");
            return { cell: node.scrollWidth - node.clientWidth, sub: sub ? sub.scrollWidth - sub.clientWidth : 0 };
          });
          expect(fit.cell, `${label}: cell ${index} content overflows its box`).toBeLessThanOrEqual(0);
          expect(fit.sub, `${label}: cell ${index} subject code overflows its box`).toBeLessThanOrEqual(0);
        }

        await cells.first().click();
        await page.waitForSelector(".sheet .fact", { timeout: 5000 });
        const subjectFact = await page.locator(".sheet .fact").first().innerText();
        expect(subjectFact.length, `${label}: the opened lesson sheet does not carry the full subject name`).toBeGreaterThan(4);
      });
    });
  }
}
