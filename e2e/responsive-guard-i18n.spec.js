const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  waitForSheetSettled,
  checkLastRowReachable,
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
  { key: "ar", locale: "ar" },
  { key: "tr", locale: "tr-TR" },
  { key: "ru", locale: "ru-RU" },
  { key: "uk", locale: "uk-UA" },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function collectOverflow(page) {
  return Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]).then(
    ([overflow, offenders]) => ({ overflow, offenders })
  );
}

function assertClean(result, label, failures) {
  if (result.overflow.overflow) {
    failures.push(`${label}: scrollWidth ${result.overflow.scrollWidth} > clientWidth ${result.overflow.clientWidth}`);
  }
  if (result.offenders.length) {
    failures.push(`${label}: elements sticking out: ${JSON.stringify(result.offenders)}`);
  }
}

async function goBack(page) {
  const headerBack = page.locator(".header-back");
  if (await headerBack.count()) {
    await headerBack.first().click();
    return;
  }
  await page.locator(".list-head button").first().click();
}

async function enterLetterSelectMode(page, row) {
  const box = await row.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(600);
  await page.mouse.up();
}

function assertReachable(result, label, failures) {
  if (!result.present) {
    failures.push(`${label}: select-bar or last row not found`);
    return;
  }
  if (!result.fullyScrolled) {
    failures.push(`${label}: could not scroll to the end of the list`);
  }
  if (result.covered) {
    failures.push(`${label}: last row is covered by the select-bar: ${JSON.stringify(result)}`);
  }
}

for (const viewport of VIEWPORTS) {
  test.describe(`i18n responsive guard @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`letters/pinboard multi-select bars and all absence types fit (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);

          await page.locator(".tabbar .tab").nth(3).click();
          await waitForContentSettled(page);
          const firstRow = page.locator(".row").first();
          await expect(firstRow).toBeVisible();
          await enterLetterSelectMode(page, firstRow);
          await expect(page.locator(".select-bar")).toBeVisible();
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/letters-select-bar`, failures);
          assertReachable(
            await checkLastRowReachable(page, ".row"),
            `${viewport.name}/${lang.key}/letters-select-bar-last-row`,
            failures
          );

          await page.locator(".tabbar .tab").nth(4).click();
          await waitForContentSettled(page);
          const pinboardSelectToggle = page.locator(".letters-tools button").first();
          await pinboardSelectToggle.click();
          await waitForContentSettled(page);
          const firstTile = page.locator(".row").first();
          await expect(firstTile).toBeVisible();
          await firstTile.click();
          await expect(page.locator(".select-bar")).toBeVisible();
          assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/pinboard-select-bar`, failures);
          assertReachable(
            await checkLastRowReachable(page, ".row"),
            `${viewport.name}/${lang.key}/pinboard-select-bar-last-row`,
            failures
          );

          await page.locator(".tabbar .tab").nth(2).click();
          await waitForContentSettled(page);

          await page.locator(".btn").first().click();
          await page.waitForSelector(".sw-content");
          await waitForContentSettled(page);
          for (const type of ["sick", "leave", "deregister", "daycare"]) {
            await page.evaluate((key) => {
              state.absenceForm.type = key;
              absenceFlow.render();
            }, type);
            await waitForContentSettled(page);
            assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/absence-type-${type}`, failures);
          }
          await page.evaluate(() => {
            closeAbsenceForm();
            render();
          });
          await waitForContentSettled(page);

          expect(failures, failures.join("\n")).toEqual([]);
        });
      });
    }
  });
}

const MAX_HEADER_HEIGHT = 96;

async function headerFits(page, label, failures) {
  const rect = await page.evaluate(() => {
    const bar = document.querySelector(".header");
    return bar ? bar.getBoundingClientRect() : null;
  });
  if (!rect) {
    failures.push(`${label}: .header not found`);
    return;
  }
  if (rect.height > MAX_HEADER_HEIGHT) {
    failures.push(`${label}: .header is ${rect.height}px tall (title wrapped instead of staying level with the gear?)`);
  }
  assertClean(await collectOverflow(page), label, failures);
}

for (const viewport of VIEWPORTS) {
  test.describe(`[P155] compact header @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`screen title stays level with the settings gear, no overflow (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);

          await headerFits(page, `${viewport.name}/${lang.key}/overview`, failures);

          await page.locator(".tabbar .tab").nth(1).click();
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/timetable`, failures);

          await page.locator(".tabbar .tab").nth(2).click();
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/absence`, failures);
          await page.evaluate(() => window.startAbsenceForm("sick"));
          await waitForContentSettled(page);
          await expect(page.locator(".sw-head .sw-back")).toBeVisible();
          await expect(page.locator(".sw-foot .sw-next")).toBeVisible();
          await expect(page.locator(".tabbar")).toHaveCount(0);
          await page.evaluate(() => {
            closeAbsenceForm();
            render();
          });
          await waitForContentSettled(page);

          await page.locator(".tabbar .tab").nth(3).click();
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/letters`, failures);
          const firstLetterRow = page.locator(".row").first();
          if (await firstLetterRow.count()) {
            await firstLetterRow.click();
            await waitForContentSettled(page);
            await headerFits(page, `${viewport.name}/${lang.key}/letters-detail`, failures);
            await expect(page.locator(".header-back")).toBeVisible();
          }

          await page.locator(".tabbar .tab").nth(4).click();
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/pinboard`, failures);

          await page.evaluate(() => window.setView("conferences"));
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/conferences`, failures);
          await expect(page.locator(".header-back")).toBeVisible();

          await page.locator(".header-actions .icon-btn").first().click();
          await waitForContentSettled(page);
          await headerFits(page, `${viewport.name}/${lang.key}/settings`, failures);
          await expect(page.locator(".header-back")).toBeVisible();
          await expect(page.locator(".wrap .list-head")).toHaveCount(0);
          const settingsGap = await page.evaluate(() => {
            const bar = document.querySelector(".header");
            const first = document.querySelector(".wrap .settings-group");
            if (!bar || !first) return null;
            return Math.round(first.getBoundingClientRect().top - bar.getBoundingClientRect().bottom);
          });
          if (settingsGap === null) failures.push(`${viewport.name}/${lang.key}/settings: header or first group missing`);
          else if (settingsGap > 32) failures.push(`${viewport.name}/${lang.key}/settings: ${settingsGap}px of empty space under the header`);

          expect(failures, failures.join("\n")).toEqual([]);
        });
      });
    }
  });
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`notify sheet @ ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("notification targets with long device names fit", async ({ page }) => {
        const failures = [];
        await goto(page);

        await page.locator(".header-actions .icon-btn").first().click();
        await waitForContentSettled(page);
        await page.locator(".setting-row.notify-setting").click();
        await waitForSheetSettled(page);
        await expect(page.locator(".notify-services-group").first()).toBeVisible();
        assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/notify-sheet`, failures);

        await page.locator(".notify-advanced-toggle").click();
        await expect(page.locator(".notify-advanced")).toBeVisible();
        assertClean(await collectOverflow(page), `${viewport.name}/${lang.key}/notify-advanced`, failures);

        expect(failures, failures.join("\n")).toEqual([]);
      });
    });
  }
}
