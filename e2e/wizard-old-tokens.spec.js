const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

let wizardSlot = 0;

async function text(page, key, count) {
  return page.evaluate(([name, value]) => (value === undefined ? t(name) : tCount(name, value)), [key, count]);
}

async function textWith(page, key, vars) {
  return page.evaluate(([name, values]) => t(name, values), [key, vars]);
}

async function openCodeStep(page) {
  wizardSlot += 1;
  await page.context().addCookies([
    { name: "e2e_wizard", value: `live-old-${process.pid}-${Date.now()}-${wizardSlot}`, url: BASE_URL },
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
  await page.locator('input[name="password"]').fill("stale-2fa");
  const signedIn = page.waitForResponse((response) => response.url().includes("api/wizard/login"));
  await page.locator(".sw-next").click();
  await signedIn;
  await expect(page.locator('input[name="code"]')).toBeVisible();
}

async function enterCode(page, code) {
  await page.locator('input[name="code"]').fill(code);
  const answered = page.waitForResponse((response) => response.url().includes("api/wizard/connect"));
  await page.locator(".sw-next").click();
  await answered;
  await page.waitForTimeout(100);
}

async function registerAgain(page) {
  const back = page.waitForResponse((response) => response.url().includes("api/wizard/back"));
  await page.locator(".sw-head .sw-back").click();
  await back;
  await expect(page.locator('input[name="code"]')).toBeVisible();
  await enterCode(page, "345678");
  await enterCode(page, "456789");
}

async function confirmRemoval(page, path) {
  const answered = page.waitForResponse((response) => response.url().includes(path));
  await page.locator(".sw-confirm .btn.destructive").click();
  await answered;
}

async function noHandOff(page) {
  await expect(page.locator('a[href*="/iserv"]')).toHaveCount(0);
  await expect(page.locator('[target="_blank"]')).toHaveCount(0);
}

async function shownDate(page, iso) {
  return page.evaluate(
    (day) => new Intl.DateTimeFormat(document.documentElement.lang || undefined, { dateStyle: "medium" }).format(new Date(`${day}T12:00:00`)),
    iso
  );
}

test.describe("old entries and an unconfirmed registration", () => {
  test("entries of other installs are only listed and removed one by one after a warning", async ({ page }) => {
    await openCodeStep(page);
    await enterCode(page, "123456");
    await expect(page.locator(".wz-warn")).toHaveText(await text(page, "wizard.connect.staleTokens", 2));
    await enterCode(page, "234567");
    await expect(page.locator(".wz-stale .wz-warn")).toHaveCount(0);
    await expect(page.locator(".wz-token-intro")).toHaveText(await text(page, "wizard.stale.other.text", 2));
    await expect(page.locator(".wz-token")).toHaveCount(2);
    const day = await shownDate(page, "2026-09-01");
    await expect(page.locator(".wz-token").first().locator(".wz-token-date")).toHaveText(await textWith(page, "wizard.stale.other.created", { date: day }));
    await noHandOff(page);
    await page.locator(".wz-token-remove").first().click();
    await expect(page.locator(".sw-confirm")).toContainText(
      await textWith(page, "wizard.stale.other.confirmDated", { name: "ISERV-Connector", date: day })
    );
    await confirmRemoval(page, "api/wizard/other-tokens/remove");
    await expect(page.locator(".wz-good")).toHaveText(await text(page, "wizard.stale.done", 1));
    await expect(page.locator(".wz-token")).toHaveCount(1);
  });

  test("the earlier entry of this connection is removed with one confirmation", async ({ page }) => {
    await openCodeStep(page);
    await enterCode(page, "123456");
    await enterCode(page, "234567");
    await expect(page.locator(".wz-token")).toHaveCount(2);
    await registerAgain(page);
    await expect(page.locator(".wz-stale .wz-warn")).toHaveText(await text(page, "wizard.stale.own.text"));
    await expect(page.locator(".wz-token")).toHaveCount(2);
    await page.getByRole("button", { name: await text(page, "wizard.stale.own.remove"), exact: true }).click();
    await expect(page.locator(".sw-confirm")).toContainText(await text(page, "wizard.stale.own.confirm"));
    await confirmRemoval(page, "api/wizard/stale-tokens/remove");
    await expect(page.locator(".wz-good")).toHaveText(await text(page, "wizard.stale.done", 1));
    await expect(page.locator(".wz-stale .wz-warn")).toHaveCount(0);
    await expect(page.locator(".wz-token")).toHaveCount(2);
  });

  test("an unconfirmed registration is checked again from the app", async ({ page }) => {
    await openCodeStep(page);
    await enterCode(page, "123456");
    await enterCode(page, "222222");
    await expect(page.locator(".wz-error")).toContainText(await text(page, "api.twofactor.unconfirmed"));
    const check = page.getByRole("button", { name: await text(page, "wizard.registration.check"), exact: true });
    const answered = page.waitForResponse((response) => response.url().includes("api/wizard/registration/check"));
    await check.click();
    await answered;
    await expect(page.locator(".wz-stale .wz-token")).toHaveCount(2);
  });
});

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`old entries look ${theme} ${width}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });
      test.setTimeout(120000);

      test("code step, unconfirmed, offer, confirmations and result", async ({ page }) => {
        await page.addInitScript((value) => {
          try {
            window.localStorage.setItem("theme", value);
          } catch (error) {}
        }, theme);
        await openCodeStep(page);
        expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
        await enterCode(page, "123456");
        await page.screenshot({ path: `test-results/old-tokens-code-${theme}-${width}.png`, fullPage: true });
        await enterCode(page, "222222");
        await page.screenshot({ path: `test-results/old-tokens-unconfirmed-${theme}-${width}.png`, fullPage: true });
        await page.getByRole("button", { name: await text(page, "wizard.registration.check"), exact: true }).click();
        await expect(page.locator(".wz-token")).toHaveCount(2);
        await registerAgain(page);
        await expect(page.locator(".wz-stale .wz-warn")).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
        await page.screenshot({ path: `test-results/old-tokens-offer-${theme}-${width}.png`, fullPage: true });
        await page.locator(".wz-token-remove").first().click();
        await expect(page.locator(".sw-confirm")).toBeVisible();
        await page.screenshot({ path: `test-results/old-tokens-confirm-other-${theme}-${width}.png`, fullPage: true });
        await page.locator(".sw-confirm .btn.ghost").click();
        await page.getByRole("button", { name: await text(page, "wizard.stale.own.remove"), exact: true }).click();
        await expect(page.locator(".sw-confirm")).toBeVisible();
        await page.screenshot({ path: `test-results/old-tokens-confirm-${theme}-${width}.png`, fullPage: true });
        await page.locator(".sw-confirm .btn.destructive").click();
        await expect(page.locator(".wz-good")).toBeVisible();
        await page.screenshot({ path: `test-results/old-tokens-done-${theme}-${width}.png`, fullPage: true });
      });
    });
  }
}
