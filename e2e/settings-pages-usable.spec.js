const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkControlsUsable, waitForSheetSettled, leaveSettingsPage } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "1366", width: 1366, height: 768 },
];
const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];
const SHORT_FIELD = 44;

let slot = 0;

async function withSchoolTimes(page) {
  await page.route((url) => url.pathname.endsWith("/api/timetable"), async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    const config = await (await page.request.get("/api/config")).json();
    const stored = (config.connections || [])[0] || {};
    await route.fulfill({ response, json: Object.assign({}, body, { school_period_times: stored.period_times || {} }) });
  });
}

async function openSettingsList(page, lang) {
  slot += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_layout", value: `usable-${process.pid}-${Date.now()}-${slot}`, url: BASE_URL },
  ]);
  await withSchoolTimes(page);
  await goto(page);
  await page.waitForSelector(".overview", { timeout: 10000 });
  await page.locator(".header-actions .settings-entry").click();
  await page.waitForSelector(".layout-setting", { timeout: 8000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
}

async function checkTopLayer(page, minFieldWidth) {
  await page.evaluate(() => {
    for (const bar of document.querySelectorAll(".tabbar")) {
      bar.style.visibility = "hidden";
      bar.setAttribute("data-usable-hidden", "bar");
    }
    const layers = document.querySelectorAll(".scrim, .color-dialog-scrim");
    let node = layers.length ? layers[layers.length - 1] : null;
    while (node && node !== document.body) {
      for (const sibling of node.parentElement.children) {
        if (sibling === node || sibling.hasAttribute("inert")) continue;
        sibling.setAttribute("inert", "");
        sibling.setAttribute("data-usable-hidden", "inert");
      }
      node = node.parentElement;
    }
  });
  const problems = await checkControlsUsable(page, minFieldWidth);
  await page.evaluate(() => {
    for (const node of document.querySelectorAll("[data-usable-hidden]")) {
      if (node.getAttribute("data-usable-hidden") === "inert") node.removeAttribute("inert");
      else node.style.visibility = "";
      node.removeAttribute("data-usable-hidden");
    }
  });
  return problems;
}

async function expectUsable(page, label, minFieldWidth) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const problems = await checkTopLayer(page, minFieldWidth);
  expect(problems, `${label}: ${JSON.stringify(problems)}`).toEqual([]);
}

async function back(page) {
  await leaveSettingsPage(page);
  await page.waitForSelector(".layout-setting", { timeout: 8000 });
}

async function closeSheet(page) {
  await page.locator(".sheet .sheet-close").first().click();
  await expect(page.locator(".sheet")).toHaveCount(0);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`reworked settings pages ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("the list, the app layout page and the technical details page stay usable", async ({ page }) => {
        const label = `${viewport.name}/${lang.key}`;
        await openSettingsList(page, lang.key);
        expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe(lang.key === "ar" ? "rtl" : "ltr");
        await expectUsable(page, `${label}/list`);

        await page.locator(".layout-setting").click();
        await page.waitForSelector(".app-layout-page .nav-page", { timeout: 8000 });
        expect(await page.locator(".app-layout-page .layout-part").evaluateAll((parts) => parts.map((part) => part.dataset.part))).toEqual(["overview", "navigation"]);
        const shown = page.locator('.layout-part[data-part="overview"] .block-row:not(.off)');
        await expect(shown.locator('.segment.mini[role="radiogroup"]')).toHaveCount(await shown.count());
        await expectUsable(page, `${label}/app-layout`);
        await back(page);

        await page.locator(".tech-setting").click();
        await expect(page.locator(".tech-page .field-group")).toBeVisible();
        await expectUsable(page, `${label}/tech-details`);
        await back(page);

        await page.locator(".calendar-setting").click();
        await page.waitForSelector(".calendar-page .cal-card", { timeout: 8000 });
        await expect(page.locator(".sheet")).toHaveCount(0);
        await expectUsable(page, `${label}/calendar`);
      });

      test("lesson times, subjects and the notification sheet stay usable in their new states", async ({ page }) => {
        const label = `${viewport.name}/${lang.key}`;
        await openSettingsList(page, lang.key);

        await expect(page.locator(".periods-setting .val")).toHaveText(await page.evaluate(() => t("settings.periods.asIserv")));
        await page.locator(".periods-setting").click();
        await page.waitForSelector(".periods-page .prow", { timeout: 8000 });
        await expect(page.locator(".periods-page button.prow")).toHaveCount(0);
        await expectUsable(page, `${label}/periods-view`);
        await page.locator(".periods-adjust").click();
        await expect(page.locator(".periods-page button.prow").first()).toBeVisible();
        await expectUsable(page, `${label}/periods-edit`);
        await back(page);

        await page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: await page.evaluate(() => t("settings.names")) }) }).click();
        await page.waitForSelector(".names-page .names-block", { timeout: 8000 });
        await expect(page.locator(".sheet")).toHaveCount(0);
        await expect(page.locator(".names-page .subject-code-input").first()).toBeHidden();
        await expectUsable(page, `${label}/names`);
        await page.locator(".names-page .subject-code-toggle").first().click();
        await expect(page.locator(".names-page .subject-code-input").first()).toBeFocused();
        await expectUsable(page, `${label}/names-code-open`, SHORT_FIELD);
        await page.locator(".names-page .swatch-trigger").first().click();
        await expect(page.locator(".color-dialog")).toBeVisible();
        await expect(page.locator(".color-dialog .colour-hex")).toBeHidden();
        await expectUsable(page, `${label}/colour`);
        await page.locator(".color-dialog .colour-own-toggle").click();
        await expect(page.locator(".color-dialog .colour-hex")).toBeVisible();
        await expectUsable(page, `${label}/colour-own`, SHORT_FIELD);
        await page.locator(".color-dialog .sheet-close").click();
        await back(page);

        await page.locator(".notify-setting").click();
        await waitForSheetSettled(page);
        await expect(page.locator(".sheet .notify-events-hint")).toBeVisible();
        await expectUsable(page, `${label}/notify`);
      });
    });
  }
}
