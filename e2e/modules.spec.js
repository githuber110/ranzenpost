const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const WIDTHS = [390, 1024];

async function gotoWithModules(page, modules, width) {
  await page.setViewportSize({ width, height: 844 });
  await page.context().clearCookies();
  if (modules) {
    await page.context().addCookies([{ name: "e2e_modules", value: modules, url: BASE_URL }]);
  }
  const noon = new Date();
  noon.setHours(12, 0, 0, 0);
  await page.clock.setFixedTime(noon);
  await goto(page);
  await page.waitForTimeout(150);
}

async function navLabels(page) {
  return page.evaluate(() => {
    const items = document.querySelectorAll(".tabbar .tab span:not(.badge):not(.ico-slot), .rail .rail-label");
    return [...items].map((node) => node.textContent.trim()).filter(Boolean);
  });
}

for (const width of WIDTHS) {
  test.describe(`modules at ${width}px`, () => {
    test("every module gives every area, the phone folds the rest under More", async ({ page }) => {
      await gotoWithModules(page, "", width);
      const expected = width < 900
        ? ["Übersicht", "Plan", "Abwesenheit", "Post", "Mehr"]
        : ["Übersicht", "Plan", "Abwesenheit", "Post", "Chat", "Sprechtage"];
      expect(await navLabels(page)).toEqual(expected);
    });

    test("only the tabs of the available modules are shown", async ({ page }) => {
      await gotoWithModules(page, "timetable,letters", width);
      expect(await navLabels(page)).toEqual(["Übersicht", "Plan", "Post"]);
      expect(await page.locator(".panel[data-area='noticeboard']").count()).toBe(0);
      expect(await page.locator(".panel[data-area='letters']").count()).toBe(1);
      expect(await page.locator(".panel[data-area='today']").count()).toBe(1);
      expect(await page.locator(".error, .note").count()).toBe(0);
    });

    test("without the timetable the plan tab, the today chapter and its settings rows are absent", async ({ page }) => {
      await gotoWithModules(page, "letters,pinboard", width);
      expect(await navLabels(page)).toEqual(["Übersicht", "Post"]);
      expect(await page.locator(".panel[data-area='today']").count()).toBe(0);
      expect(await page.locator(".error, .note").count()).toBe(0);

      await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
      await page.waitForTimeout(100);
      const rows = await page.locator(".modules-block .module-row .lbl").allTextContents();
      expect(rows).toEqual(["Elternbriefe", "Pinnwand"]);
      const card = page.locator(".modules-block .module-card");
      await expect(card).toBeVisible();
      await expect(card).toContainText("E-Mail");
      await expect(card.locator(".module-card-show")).toHaveText("Zeig mir wie");
      expect(await card.locator(".module-card-later").count()).toBe(0);
      const labels = await page.locator(".setting-row .lbl").allTextContents();
      expect(labels).not.toContain("Fächer & Lehrkräfte");
      expect(labels).toContain("Telefonnummern");

      await page.locator(".modules-block .modules-recheck").click();
      await expect(page.locator(".toast")).toContainText("Module neu geprüft.");
      expect(await page.locator(".modules-block .btn:not(.ghost)").count()).toBe(1);
    });

    test("no module at all gives one calm screen with a way into the settings", async ({ page }) => {
      await gotoWithModules(page, "none", width);
      await page.waitForSelector(".modules-empty", { timeout: 10000 });
      expect(await page.locator(".tabbar").count()).toBe(0);
      expect(await page.locator(".rail").count()).toBe(0);
      await expect(page.locator(".modules-empty")).toContainText("Hier gibt es noch nichts zu sehen");
      await expect(page.locator(".modules-empty .module-card")).toBeVisible();
      expect(await page.locator(".error, .note, .toast").count()).toBe(0);
      const overflow = await page.evaluate(() => {
        const root = document.scrollingElement || document.documentElement;
        return root.scrollWidth > root.clientWidth + 1;
      });
      expect(overflow).toBe(false);

      await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
      await page.waitForTimeout(100);
      await expect(page.locator(".settings-group").first()).toBeVisible();
      await expect(page.locator(".modules-block .modules-none")).toBeVisible();
      expect(await page.locator(".tabbar").count()).toBe(0);
    });
  });
}
