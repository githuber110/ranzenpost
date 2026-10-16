const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const KEY_TEXT = "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ";

let wizardSlot = 0;

async function text(page, key) {
  return page.evaluate((name) => t(name), key);
}

async function openForcedSetup(page) {
  wizardSlot += 1;
  await page.context().addCookies([
    { name: "e2e_wizard", value: `live-setup-${process.pid}-${Date.now()}-${wizardSlot}`, url: BASE_URL },
  ]);
  await page.request.post(`${BASE_URL}/e2e/wizard/restart`);
  await goto(page);
  await page.locator(".settings-entry").click();
  await page.waitForTimeout(200);
  await page.getByRole("button", { name: await text(page, "schools.add"), exact: true }).click();
  await page.locator('input[name="url"]').fill("myschool.example");
  await page.locator(".sw-next").click();
  await expect(page.locator('input[name="username"]')).toBeVisible({ timeout: 15000 });
  await page.locator('input[name="username"]').fill("parent.one");
  await page.locator('input[name="password"]').fill("forced-2fa");
  const signedIn = page.waitForResponse((response) => response.url().includes("api/wizard/login"));
  await page.locator(".sw-next").click();
  await signedIn;
  await expect(page.locator(".wz-sub")).toHaveText(await text(page, "wizard.setup.start.text"));
}

async function send(page, path) {
  const answered = page.waitForResponse((response) => response.url().includes(path));
  await page.locator(".sw-next").click();
  await answered;
  await page.waitForTimeout(100);
}

async function enterCode(page, code, path) {
  await page.locator('input[name="code"]').fill(code);
  await send(page, path);
}

async function noHandOff(page) {
  await expect(page.locator('a[href*="/iserv"]')).toHaveCount(0);
  await expect(page.locator('[target="_blank"]')).toHaveCount(0);
}

test.describe("first two-factor setup inside the app", () => {
  test("key as QR code and text, a wrong code named, then the usual connect", async ({ page }) => {
    await openForcedSetup(page);
    await noHandOff(page);
    await send(page, "api/wizard/twofactor/start");
    await expect(page.locator(".wz-key")).toHaveText(KEY_TEXT);
    await expect(page.locator(".wz-qr svg")).toBeVisible();
    await noHandOff(page);

    await enterCode(page, "000000", "api/wizard/twofactor/confirm");
    await expect(page.locator(".wz-error")).toHaveText(await text(page, "api.wizard.setup.rejected"));
    await expect(page.locator(".wz-key")).toHaveText(KEY_TEXT);

    await enterCode(page, "123456", "api/wizard/twofactor/confirm");
    await expect(page.locator(".wz-good")).toHaveText(await text(page, "wizard.setup.done"));
    await expect(page.locator(".wz-key")).toHaveCount(0);
    await expect(page.locator(".wz-error")).toHaveCount(0);

    await enterCode(page, "234567", "api/wizard/connect");
    await expect(page.locator(".sw-question")).toHaveText(await text(page, "wizard.connect.second.title"));
    await enterCode(page, "345678", "api/wizard/connect");
    await expect(page.locator('input[name="code"]')).toHaveCount(0);
  });

  test("an unclear answer offers the check, which finds the active setup", async ({ page }) => {
    await openForcedSetup(page);
    await send(page, "api/wizard/twofactor/start");
    await enterCode(page, "111111", "api/wizard/twofactor/confirm");
    await expect(page.locator(".wz-sub")).toHaveText(await text(page, "wizard.setup.uncertain.text"));
    await expect(page.locator(".wz-error")).toContainText(await text(page, "api.wizard.setup.uncertain"));
    await expect(page.locator('input[name="code"]')).toHaveCount(0);
    await expect(page.locator(".sw-next")).toContainText(await text(page, "wizard.setup.check.button"));
    await send(page, "api/wizard/twofactor/check");
    await expect(page.locator(".wz-good")).toHaveText(await text(page, "wizard.setup.done"));
  });
});

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`two-factor setup look ${theme} ${width}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });
      test.setTimeout(120000);

      test("start, key and uncertain views", async ({ page }) => {
        await page.addInitScript((value) => {
          try {
            window.localStorage.setItem("theme", value);
          } catch (error) {}
        }, theme);
        await openForcedSetup(page);
        expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
        await page.screenshot({ path: `test-results/twofactor-setup-start-${theme}-${width}.png`, fullPage: true });
        await send(page, "api/wizard/twofactor/start");
        await expect(page.locator(".wz-key")).toHaveText(KEY_TEXT);
        const frame = await page.locator(".wz-qr .cal-qr-frame").boundingBox();
        expect(frame.width).toBeGreaterThan(120);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
        await page.screenshot({ path: `test-results/twofactor-setup-key-${theme}-${width}.png`, fullPage: true });
        await enterCode(page, "000000", "api/wizard/twofactor/confirm");
        await page.screenshot({ path: `test-results/twofactor-setup-rejected-${theme}-${width}.png`, fullPage: true });
        await enterCode(page, "123456", "api/wizard/twofactor/confirm");
        await expect(page.locator(".wz-good")).toBeVisible();
        await page.screenshot({ path: `test-results/twofactor-setup-done-${theme}-${width}.png`, fullPage: true });
      });
    });
  }
}
