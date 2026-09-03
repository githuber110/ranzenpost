const { test, expect, devices } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
];

function deviceUse(name) {
  const { defaultBrowserType, ...rest } = devices[name];
  return rest;
}

const DEVICES = [
  { name: "iPhone SE (small)", use: {} },
  { name: "iPhone 14 Pro Max (large)", use: deviceUse("iPhone 14 Pro Max") },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function assertClean(overflow, offenders, label) {
  expect(overflow.overflow, `${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`).toBe(false);
  expect(offenders, `${label}: elements sticking out of the viewport: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function goBack(page) {
  const headerBack = page.locator(".header-back");
  if (await headerBack.count()) {
    await headerBack.first().click();
    return;
  }
  await page.locator(".list-head button").first().click();
}

for (const device of DEVICES) {
  test.describe(`WebKit real-engine guard @ ${device.name}`, () => {
    test.use(device.use);

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`all four absence types fit natively (${lang.key})`, async ({ page }) => {
          await goto(page);
          await page.locator(".tabbar .tab").nth(2).click();
          await waitForContentSettled(page);

          await page.locator(".btn").first().click();
          await page.waitForSelector(".sw-content");
          await page.waitForTimeout(150);
          for (const type of ["sick", "leave", "deregister", "daycare"]) {
            await page.evaluate((key) => {
              state.absenceForm.type = key;
              absenceFlow.render();
            }, type);
            await waitForContentSettled(page);

            const overflow = await checkHorizontalOverflow(page);
            const offenders = await checkElementsWithinViewport(page);
            assertClean(overflow, offenders, `${device.name}/${lang.key}/absence-type-${type}`);
          }
        });
      });
    }
  });
}
