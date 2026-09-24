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

const LANGUAGES = [
  { key: "de", locale: "de-DE", rtl: false },
  { key: "ru", locale: "ru-RU", rtl: false },
  { key: "ar", locale: "ar-EG", rtl: true },
];

const TIMETABLE_TAB = 1;
const FEED_HOST = "homeassistant.local";

async function prepare(page) {
  await goto(page);
}

async function openCalendarPage(page) {
  await page.locator(".tabbar .tab").nth(TIMETABLE_TAB).click();
  await page.waitForTimeout(80);
  await page.locator(".header-actions .icon-btn").first().click();
  await page.waitForSelector(".calendar-page .cal-card", { timeout: 8000 });
}

async function assertClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);

  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: elements outside the viewport: ${JSON.stringify(outside)}`).toEqual([]);

  const undersized = await checkTapTargets(page);
  expect(undersized, `${label}: undersized tap targets: ${JSON.stringify(undersized)}`).toEqual([]);

  expect(await page.locator(".sheet").count(), `${label}: the subscription is a page, not a sheet`).toBe(0);
  await expect(page.locator(".header-back")).toBeVisible();
  await expect(page.locator(".header-title")).toHaveText(await page.evaluate(() => t("calendar.subscribe.title")));
}

for (const viewport of VIEWPORTS) {
  test.describe(`calendar subscription page @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const language of LANGUAGES) {
      test.describe(language.key, () => {
        test.use({ locale: language.locale });

        test(`opens from the timetable header and fits (${language.key})`, async ({ page }) => {
          await prepare(page);
          const direction = await page.evaluate(() => document.documentElement.getAttribute("dir"));
          expect(direction).toBe(language.rtl ? "rtl" : "ltr");

          await openCalendarPage(page);
          await expect(page.locator(".cal-card")).toBeVisible();
          await expect(page.locator(".cal-url")).toContainText(`${FEED_HOST}:8100/calendar/`);
          await expect(page.locator(".cal-url")).toHaveAttribute("dir", "ltr");
          await expect(page.locator("button.cal-add")).toBeVisible();
          await assertClean(page, `${viewport.name}/${language.key}/page`);
        });

        test(`stays contained with the QR code open (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarPage(page);
          await page.locator(".cal-qr-toggle").click();
          await page.waitForSelector(".cal-qr svg");
          await assertClean(page, `${viewport.name}/${language.key}/qr-open`);
        });

        test(`stays contained while the parts are being changed (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarPage(page);
          await page.locator(".cal-edit").click();
          await page.waitForSelector(".cal-swatches");
          await expect(page.locator(".cal-form .check")).toHaveCount(6);
          await assertClean(page, `${viewport.name}/${language.key}/edit-form`);
        });

        test(`asks for no address and shows no setup steps (${language.key})`, async ({ page }) => {
          await prepare(page);
          await openCalendarPage(page);
          await expect(page.locator(".cal-host")).toHaveCount(0);
          await expect(page.locator(".cal-setup-head")).toHaveCount(0);
          await expect(page.locator(".cal-webview")).toHaveCount(0);
          await assertClean(page, `${viewport.name}/${language.key}/no-setup`);
        });
      });
    }
  });
}

test.describe("calendar subscription page: writing actions", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the renew button opens a confirmation instead of acting straight away", async ({ page }) => {
    const rotateCalls = [];
    await page.route(/\/rotate$/, (route) => {
      rotateCalls.push(route.request().url());
      route.abort();
    });
    await prepare(page);
    await openCalendarPage(page);
    await page.locator(".cal-rotate").click();
    await waitForSheetSettled(page);
    await expect(page.locator(".sheet .btn.destructive")).toBeVisible();
    expect(rotateCalls).toEqual([]);
  });

  test("the restart is offered as a button and only fires on the click", async ({ page }) => {
    const restartCalls = [];
    await page.route("**/api/calendar/restart", (route) => {
      restartCalls.push(route.request().method());
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, restarting: true, message_key: "api.calendar.restart.accepted" }),
      });
    });
    await goto(page);
    await openCalendarPage(page);
    await expect(page.locator(".cal-restart-go")).toHaveCount(0);

    await page.evaluate(() => {
      window.location.reload = () => {};
      state.calendarPortRestart = true;
      rerender();
    });
    const button = page.locator(".cal-restart-go");
    await expect(button).toBeVisible();
    expect(restartCalls, "nothing may restart before the click").toEqual([]);
    await assertClean(page, "390/de/restart-offer");

    await button.click();
    await expect.poll(() => restartCalls.length).toBe(1);
    expect(restartCalls[0]).toBe("POST");
    await expect(page.locator(".cal-restart-go")).toHaveCount(0);
  });

  test("the address needs no input at all and carries exactly one port", async ({ page }) => {
    await goto(page);
    await openCalendarPage(page);
    await expect(page.locator(".cal-host")).toHaveCount(0);
    const url = await page.locator(".cal-url").first().textContent();
    expect(url).toContain(`${FEED_HOST}:8100/calendar/`);
    const authority = url.split("://")[1].split("/")[0];
    expect(authority).toBe(`${FEED_HOST}:8100`);
    await assertClean(page, "390/de/no-host-field");
  });
});
