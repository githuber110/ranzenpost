const { test, expect } = require("@playwright/test");
const { goto, waitForLayoutSettled, checkHorizontalOverflow, checkElementsWithinViewport, checkControlsUsable } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const STEP_TIMEOUT = 15000;

const VIEWPORTS = [
  { name: "phone-360", width: 360, height: 740 },
  { name: "phone-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "panel-900", width: 900, height: 700 },
  { name: "laptop-1024", width: 1024, height: 768 },
  { name: "laptop-1366", width: 1366, height: 768 },
  { name: "desk-1920", width: 1920, height: 1080 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

let wizardSlot = 0;

function nextWizardKey() {
  wizardSlot += 1;
  return `live-fit-${process.pid}-${Date.now()}-${wizardSlot}`;
}

function wizardAnswer(page, step) {
  return page.waitForResponse(
    (response) => response.request().method() === "POST" && new URL(response.url()).pathname.endsWith(`/api/wizard/${step}`)
  );
}

async function expectUsable(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const problems = await checkControlsUsable(page);
  expect(problems, `${label}: ${JSON.stringify(problems)}`).toEqual([]);
}

async function openAddSchool(page) {
  await page.context().addCookies([{ name: "e2e_wizard", value: nextWizardKey(), url: BASE_URL }]);
  const restarted = await page.request.post(`${BASE_URL}/e2e/wizard/restart`);
  expect(restarted.ok()).toBe(true);
  await goto(page);
  await page.locator(".settings-entry").first().click();
  const name = await page.evaluate(() => t("schools.add"));
  const started = wizardAnswer(page, "start");
  await page.getByRole("button", { name, exact: true }).click();
  expect((await started).ok()).toBe(true);
  await expect(page.locator('input[name="url"]')).toBeVisible({ timeout: STEP_TIMEOUT });
  await waitForLayoutSettled(page);
}

const HEALTH_STATES = [
  { name: "sign in again", health: { configured: true, connection: "auth_failed", username: "parent.one", connection_id: "" } },
  { name: "school unreachable", health: { configured: true, connection: "network" } },
];

async function openWithHealth(page, health) {
  await page.route((url) => url.pathname.endsWith("/api/health"), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(health) })
  );
  await page.goto("/");
  await page.waitForSelector(".screen .wrap", { timeout: STEP_TIMEOUT });
  await waitForLayoutSettled(page);
}

for (const viewport of VIEWPORTS) {
  test.describe(`full page flows @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`adding a school can be used (${lang.key})`, async ({ page }) => {
          await openAddSchool(page);
          await expect(page.locator("#app")).toHaveAttribute("data-shell", "flow");
          await expectUsable(page, `${viewport.name}/${lang.key}/url step`);
          const card = await page.locator(".sw").boundingBox();
          expect(card.width, `${viewport.name}: setup card width`).toBeGreaterThanOrEqual(Math.min(400, viewport.width - 2));
          await page.locator('input[name="url"]').fill("myschool.example");
          const checked = wizardAnswer(page, "url");
          await page.locator(".sw-next").click();
          expect((await checked).ok()).toBe(true);
          await expect(page.locator('input[name="password"]')).toBeVisible({ timeout: STEP_TIMEOUT });
          await waitForLayoutSettled(page);
          await expectUsable(page, `${viewport.name}/${lang.key}/login step`);
        });

        for (const state of HEALTH_STATES) {
          test(`${state.name} fills a readable column (${lang.key})`, async ({ page }) => {
            await openWithHealth(page, state.health);
            await expect(page.locator("#app")).toHaveAttribute("data-shell", "flow");
            await expectUsable(page, `${viewport.name}/${lang.key}/${state.name}`);
            const column = await page.locator(".screen > .wrap").first().boundingBox();
            expect(column.width, `${viewport.name}: column width`).toBeGreaterThanOrEqual(Math.min(320, viewport.width - 2));
            expect(column.width, `${viewport.name}: column width`).toBeLessThanOrEqual(721);
          });
        }
      });
    }
  });
}
