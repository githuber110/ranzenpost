const path = require("path");
const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const SHOTS = path.join(__dirname, "..", "test-results", "disconnect-token-shots");
const TOKENS = [
  { id: "11111111-2222-4333-8444-555555555551", name: "ISERV-Connector", created: "" },
  { id: "11111111-2222-4333-8444-555555555552", name: "ISERV-Connector", created: "01.09.2026" },
];

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`disconnect token choice ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: width === 390 ? 844 : 768 }, locale: "de-DE", colorScheme: theme });

      test(`the token list is chosen inside the app (${width} ${theme})`, async ({ page }) => {
        const bodies = [];
        await page.route("**/api/account/disconnect", async (route) => {
          bodies.push(route.request().postDataJSON());
          await route.fulfill({
            json: { attempted: false, removed: false, disconnected: false, retryable: false, message_key: "api.disconnect.choose", tokens: TOKENS },
          });
        });
        await page.addInitScript((value) => {
          try {
            window.localStorage.setItem("theme", value);
          } catch (error) {}
        }, theme);
        await goto(page);
        await page.locator(".header-actions .settings-entry").first().click();
        await page.locator("button.setting-row", { hasText: "Verbindung trennen" }).first().click();
        await page.locator(".sheet .btn.destructive").click();
        const sheet = page.locator(".sheet");
        await expect(sheet.locator(".token-choice")).toHaveCount(2);
        await expect(sheet.locator(".token-retry")).toHaveCount(0);
        expect(await sheet.locator("a[href]").count()).toBe(0);
        await page.screenshot({ path: path.join(SHOTS, `choose-${width}-${theme}.png`) });
        expect(bodies.length).toBe(1);
      });
    });
  }
}
