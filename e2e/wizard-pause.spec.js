const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const RIGHT_PASSWORD = "right-password";

let wizardSlot = 0;

function nextWizardKey() {
  wizardSlot += 1;
  return `live-${process.pid}-${Date.now()}-${wizardSlot}`;
}

async function addSchool(page) {
  const name = await page.evaluate(() => t("schools.add"));
  await page.getByRole("button", { name, exact: true }).click();
}

async function openLiveWizard(page) {
  await page.context().addCookies([{ name: "e2e_wizard", value: nextWizardKey(), url: BASE_URL }]);
  await page.request.post(`${BASE_URL}/e2e/wizard/restart`);
  await page.clock.install();
  await goto(page);
  await page.locator(".settings-entry").click();
  await page.waitForTimeout(200);
  await addSchool(page);
  await expect(page.locator('input[name="url"]')).toBeVisible();
  await page.locator('input[name="url"]').fill("myschool.example");
  await page.locator(".sw-next").click();
  await expect(page.locator('input[name="password"]')).toBeVisible();
}

async function login(page, password) {
  await page.locator('input[name="username"]').fill("parent.one");
  await page.locator('input[name="password"]').fill(password);
  const answered = page.waitForResponse((response) => response.url().includes("api/wizard/login"));
  await page.locator(".sw-next").click();
  await answered;
  await page.waitForTimeout(100);
}

async function countdown(page, time) {
  return page.evaluate((value) => t("wizard.wait.countdown", { time: value }), time);
}

async function passTime(page, seconds) {
  await page.request.post(`${BASE_URL}/e2e/wizard/advance?seconds=${seconds}`);
  await page.clock.fastForward(seconds * 1000);
}

test.describe("setup wait after wrong passwords", () => {
  test("two wrong tries never wait, the third waits half a minute on the form itself", async ({ page }) => {
    await openLiveWizard(page);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await login(page, "wrong-password");
      await expect(page.locator(".wz-error")).toBeVisible();
      await expect(page.locator(".wz-error-pause")).toHaveCount(0);
      await expect(page.locator(".sw-status")).not.toHaveText(/\d:\d\d/);
    }
    await login(page, "wrong-password");
    await expect(page.locator(".wz-error-pause")).toHaveText(await page.evaluate(() => t("api.wizard.pausedCredentials")));
    await expect(page.locator(".sw-next")).toHaveAttribute("aria-disabled", "true");
    await expect(page.locator(".sw-status")).toHaveText(await countdown(page, "0:30"));
    await expect(page.locator(".wz-nav.reset")).toBeVisible();
    await page.locator('input[name="password"]').fill(RIGHT_PASSWORD);
    await expect(page.locator(".sw-next")).toHaveAttribute("aria-disabled", "true");

    await passTime(page, 31);
    await expect(page.locator(".sw-next")).toHaveAttribute("aria-disabled", "false");
    await expect(page.locator(".wz-error-pause")).toHaveCount(0);

    await login(page, RIGHT_PASSWORD);
    await expect(page.locator('input[name="password"]')).toHaveCount(0);
  });

  test("a further wrong try waits a little longer", async ({ page }) => {
    await openLiveWizard(page);
    for (let attempt = 0; attempt < 3; attempt += 1) await login(page, "wrong-password");
    await passTime(page, 31);
    await expect(page.locator(".wz-error-pause")).toHaveCount(0);
    await login(page, "wrong-password");
    await expect(page.locator(".sw-status")).toHaveText(await countdown(page, "1:00"));
  });

  test("a reload during the wait still shows the form and not a dead end", async ({ page }) => {
    await openLiveWizard(page);
    for (let attempt = 0; attempt < 3; attempt += 1) await login(page, "wrong-password");
    await page.request.post(`${BASE_URL}/e2e/wizard/advance?seconds=31`);
    await page.reload();
    await page.waitForTimeout(300);
    const settings = page.locator(".settings-entry");
    if (await settings.count()) {
      await settings.click();
      await page.waitForTimeout(200);
      await addSchool(page);
    }
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator(".wz-error-pause")).toHaveCount(0);
  });
});

async function text(page, key) {
  return page.evaluate((name) => t(name), key);
}

test.describe("setup names why IServ refused the sign-in", () => {
  test("a blocked default password is named and never starts a wait", async ({ page }) => {
    await openLiveWizard(page);
    for (let attempt = 0; attempt < 4; attempt += 1) await login(page, "default-password");
    await expect(page.locator(".wz-error")).toContainText(await text(page, "api.lockout.defaultPassword"));
    await expect(page.locator(".wz-error-pause")).toHaveCount(0);
    await page.locator('input[name="password"]').fill(RIGHT_PASSWORD);
    await expect(page.locator(".sw-next")).toHaveAttribute("aria-disabled", "false");
  });

  test("an unknown account is named", async ({ page }) => {
    await openLiveWizard(page);
    await login(page, "unknown-account");
    await expect(page.locator(".wz-error")).toContainText(await text(page, "api.lockout.unknownAccount"));
    await expect(page.locator('input[name="password"]')).toBeVisible();
  });

  test("a forced two-factor setup leads to the code step with an explanation, not an error", async ({ page }) => {
    await openLiveWizard(page);
    await login(page, "forced-2fa");
    await expect(page.locator('input[name="code"]')).toBeVisible();
    await expect(page.locator(".wz-sub")).toHaveText(await text(page, "wizard.connect.setupRequired"));
    await expect(page.locator(".wz-error")).toHaveCount(0);
    await page.locator('input[name="code"]').fill("123456");
    const answered = page.waitForResponse((response) => response.url().includes("api/wizard/connect"));
    await page.locator(".sw-next").click();
    await answered;
    await expect(page.locator(".wz-error")).toContainText(await text(page, "api.wizard.twofactorSetupPending"));
    await expect(page.locator(".wz-error-pause")).toHaveCount(0);
    await expect(page.locator(".wz-sub")).toHaveText(await text(page, "wizard.connect.setupRequired"));
  });
});
