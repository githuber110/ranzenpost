const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkControlsUsable } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const VIEWPORTS = [
  { name: "390", width: 390, height: 844, pane: false },
  { name: "1366", width: 1366, height: 768, pane: true },
];
const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];
const PAIRED_FIELD = 120;

let slot = 0;

function mondayIso() {
  const today = new Date();
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7));
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, "0")}-${String(monday.getDate()).padStart(2, "0")}`;
}

async function openPeriods(page, lang) {
  slot += 1;
  const key = `periods-${process.pid}-${Date.now()}-${slot}`;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_layout", value: key, url: BASE_URL },
    { name: "e2e_matrix", value: key, url: BASE_URL },
  ]);
  await page.request.post("/e2e/matrix/reset");
  await goto(page);
  await page.waitForSelector(".overview", { timeout: 10000 });
  await page.locator(".header-actions .settings-entry").click();
  await page.locator(".periods-setting").click();
  await page.waitForSelector(".periods-page .prow", { timeout: 8000 });
}

async function checkTopLayer(page, minFieldWidth) {
  await page.evaluate(() => {
    for (const bar of document.querySelectorAll(".tabbar")) {
      bar.style.visibility = "hidden";
      bar.setAttribute("data-usable-hidden", "bar");
    }
    const layers = document.querySelectorAll(".scrim");
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
  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 6000 });
  await page.evaluate(() => {
    for (const node of document.querySelectorAll(".screen, .pane-body, .sheet-body")) node.scrollTop = 0;
  });
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const problems = await checkTopLayer(page, minFieldWidth);
  expect(problems, `${label}: ${JSON.stringify(problems)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`lesson times ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("the page, the lesson editor and a new break stay usable and the break reaches the plan", async ({ page }) => {
        const label = `${viewport.name}/${lang.key}`;
        await openPeriods(page, lang.key);
        expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe(lang.key === "ar" ? "rtl" : "ltr");
        await expect(page.locator(".periods-page button.prow")).toHaveCount(0);
        await expect(page.locator(".pane-detail")).toHaveCount(viewport.pane ? 1 : 0);
        await expectUsable(page, `${label}/page`);
        await expect(page.locator(".periods-ha .switch")).toHaveAttribute("aria-checked", "false");

        await page.locator(".periods-adjust").click();
        await page.locator('.periods-page button.prow[data-period="2"]').click();
        const editor = viewport.pane ? page.locator(".pane-detail") : page.locator(".sheet");
        await expect(editor.locator(".periods-apply")).toBeVisible();
        await expect(editor.locator(".dur-range")).toBeVisible();
        await expectUsable(page, `${label}/lesson`, PAIRED_FIELD);
        if (viewport.pane) await page.locator(".pane-detail .pane-close").click();
        else await page.locator(".sheet .sheet-close").click();
        await expect(page.locator(".periods-apply")).toHaveCount(0);

        await page.locator(".periods-add-entry").click();
        const form = viewport.pane ? page.locator(".pane-detail") : page.locator(".entry-page");
        await expect(form.locator(".entry-name")).toBeVisible();
        await form.locator('.entry-type [data-value="pause"]').click();
        await form.locator(".entry-name").fill("Frühstück");
        await form.locator(".entry-from").fill(mondayIso());
        await expect(form.locator(".entry-save")).toBeEnabled();
        await expectUsable(page, `${label}/entry`, PAIRED_FIELD);
        await form.locator(".entry-save").click();
        await expect(page.locator(".periods-page .periods-entry")).toHaveCount(1);
        await expect(page.locator(".periods-page .periods-entry .row-title")).toHaveText("Frühstück");
        await expectUsable(page, `${label}/with-entry`);

        await page.locator(".periods-page .periods-entry").click();
        const detail = viewport.pane ? page.locator(".pane-detail") : page.locator(".sheet");
        await expect(detail.locator(".periods-edit")).toBeVisible();
        await expectUsable(page, `${label}/entry-detail`);
        if (viewport.pane) await page.locator(".pane-detail .pane-close").click();
        else await page.locator(".sheet .sheet-close").click();

        await page.locator(".header-back").click();
        await page.evaluate(() => setView("timetable"));
        await page.waitForSelector(".tt", { timeout: 8000 });
        if (await page.locator(".tt .tt-hour").count()) {
          await expect(page.locator(".tt .tt-strip").first()).toBeVisible();
        }
        await expect(page.locator(".plan-add")).toBeVisible();
        await expectUsable(page, `${label}/plan`);
      });
    });
  }
}
