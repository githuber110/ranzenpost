const { test, expect } = require("@playwright/test");
const {
  goto,
  waitForSheetSettled,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkSheetContainment,
} = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE", rtl: false },
  { key: "ru", locale: "ru-RU", rtl: false },
  { key: "ar", locale: "ar-EG", rtl: true },
];

const TIMETABLE_TAB = 1;
const FEED_HOST = "homeassistant.local";

async function prepare(page) {
  await page.addInitScript((host) => {
    try {
      window.localStorage.setItem("calendarHost", host);
    } catch (error) {}
  }, FEED_HOST);
  await goto(page);
}

async function openCalendarSheet(page) {
  await page.locator(".tabbar .tab").nth(TIMETABLE_TAB).click();
  await page.waitForTimeout(80);
  await page.locator(".header-actions .icon-btn").first().click();
  await page.waitForSelector(".cal-card", { timeout: 8000 });
  await waitForSheetSettled(page);
}

async function assertClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);

  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: elements outside the viewport: ${JSON.stringify(outside)}`).toEqual([]);

  const undersized = await checkTapTargets(page);
  expect(undersized, `${label}: undersized tap targets: ${JSON.stringify(undersized)}`).toEqual([]);

  const containment = await checkSheetContainment(page);
  expect(containment.present, `${label}: no sheet on screen`).toBe(true);
  expect(containment.fitsViewport, `${label}: sheet taller than the viewport`).toBe(true);
  expect(containment.scrollable, `${label}: sheet body does not scroll internally`).toBe(true);
}

for (const viewport of VIEWPORTS) {
  test.describe(`calendar subscription sheet @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const language of LANGUAGES) {
      test.describe(language.key, () => {
        test.use({ locale: language.locale });

        test(`opens from the timetable header and fits (${language.key})`, async ({ page }) => {
          await prepare(page);
          const direction = await page.evaluate(() => document.documentElement.getAttribute("dir"));
          expect(direction).toBe(language.rtl ? "rtl" : "ltr");

          await openCalendarSheet(page);
          await expect(page.locator(".cal-card")).toBeVisible();
          await expect(page.locator(".cal-url")).toContainText(`${FEED_HOST}:8100/calendar/`);
          await expect(page.locator(".cal-url")).toHaveAttribute("dir", "ltr");
          await expect(page.locator("a.cal-add")).toHaveAttribute("href", /^webcal:/);
          await assertClean(page, `${viewport.name}/${language.key}/sheet`);
        });

        test(`stays contained with the QR code open (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarSheet(page);
          await page.locator(".cal-qr-toggle").click();
          await page.waitForSelector(".cal-qr svg");
          await waitForSheetSettled(page);
          await assertClean(page, `${viewport.name}/${language.key}/qr-open`);
        });

        test(`stays contained while the parts are being changed (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarSheet(page);
          await page.locator(".cal-edit").click();
          await page.waitForSelector(".cal-swatches");
          await waitForSheetSettled(page);
          await expect(page.locator(".cal-form .check")).toHaveCount(5);
          await assertClean(page, `${viewport.name}/${language.key}/edit-form`);
        });

        test(`stays contained with the setup steps collapsed (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarSheet(page);
          await expect(page.locator(".cal-setup-head")).toHaveAttribute("aria-expanded", "true");
          await page.locator(".cal-setup-head").click();
          await expect(page.locator(".cal-setup-head")).toHaveAttribute("aria-expanded", "false");
          await expect(page.locator(".cal-steps")).toHaveCount(0);
          await waitForSheetSettled(page);
          await assertClean(page, `${viewport.name}/${language.key}/setup-collapsed`);
        });
      });
    }
  });
}

test.describe("calendar subscription sheet: writing actions", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the renew button opens a confirmation instead of acting straight away", async ({ page }) => {
    const rotateCalls = [];
    await page.route(/\/rotate$/, (route) => {
      rotateCalls.push(route.request().url());
      route.abort();
    });
    await prepare(page);
    await openCalendarSheet(page);
    await page.locator(".cal-rotate").click();
    await waitForSheetSettled(page);
    await expect(page.locator(".sheet .btn.destructive")).toBeVisible();
    expect(rotateCalls).toEqual([]);
  });

  test("without a stored host the address is withheld and the host field is offered", async ({ page }) => {
    await goto(page);
    await openCalendarSheet(page);
    await expect(page.locator(".cal-url")).toHaveCount(0);
    await expect(page.locator("a.cal-add")).toHaveCount(0);
    await expect(page.locator(".cal-host input")).toBeVisible();
    await assertClean(page, "390/de/no-host");
  });
});
