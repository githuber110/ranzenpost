const { test, expect } = require("@playwright/test");
const { goto, checkTapTargets, checkTapTargetOverlaps, checkLastRowReachable } = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

const VIEWS = [
  { key: "overview", tabIndex: null },
  { key: "timetable", tabIndex: 1 },
  { key: "absence", tabIndex: 2 },
  { key: "letters", tabIndex: 3 },
  { key: "pinboard", tabIndex: 4 },
];

async function assertNoOverlapOrCoverage(page, label) {
  const overlapOffenders = await checkTapTargetOverlaps(page);
  expect(overlapOffenders, `${label}: tap targets without a dead zone between them: ${JSON.stringify(overlapOffenders)}`).toEqual([]);

  const reach = await checkLastRowReachable(page, ".row");
  if (reach.present) {
    expect(reach.fullyScrolled, `${label}: could not scroll to the end of the list`).toBe(true);
    expect(reach.covered, `${label}: last row stays covered by ${JSON.stringify(reach.coveringElements)} even scrolled to the end`).toBe(false);
  }
}

for (const viewport of VIEWPORTS) {
  test.describe(`real tap-target geometry @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const view of VIEWS) {
      test(`${view.key}: no undersized targets, no unrelated targets overlapping`, async ({ page }) => {
        await goto(page);
        if (view.tabIndex !== null) {
          await page.locator(".tabbar .tab").nth(view.tabIndex).click();
          await waitForContentSettled(page);
        }

        const sizeOffenders = await checkTapTargets(page);
        expect(sizeOffenders, `${viewport.name}/${view.key}: undersized tap targets: ${JSON.stringify(sizeOffenders)}`).toEqual([]);

        await assertNoOverlapOrCoverage(page, `${viewport.name}/${view.key}`);
      });
    }

    test("other fixed overlays (sheet, select-bar, toast) don't produce the same false positive", async ({ page }) => {
      await goto(page);

      await page.locator(".tabbar .tab").nth(2).click();
      await waitForContentSettled(page);
      await page.locator(".btn").first().click();
      await page.waitForSelector(".sw-content");
      await page.waitForTimeout(200);
      await assertNoOverlapOrCoverage(page, `${viewport.name}/absence-wizard-open`);
      await page.evaluate(() => {
        closeAbsenceForm();
        render();
      });
      await waitForContentSettled(page);

      await page.locator(".tabbar .tab").nth(3).click();
      await waitForContentSettled(page);
      const firstRow = page.locator(".row").first();
      const box = await firstRow.boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.waitForTimeout(600);
      await page.mouse.up();
      await page.waitForTimeout(200);
      await assertNoOverlapOrCoverage(page, `${viewport.name}/letters-select-bar-open`);

      await page.evaluate(() => toast("e2e probe toast"));
      await page.waitForTimeout(150);
      await assertNoOverlapOrCoverage(page, `${viewport.name}/toast-visible`);
    });
  });
}
