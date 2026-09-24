const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;

test("the empty state icon draws inside its round plate", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "e2e_modules", value: "none", url: BASE_URL }]);
  await goto(page);
  const icon = page.locator(".modules-empty .empty > .ico-slot > .ico").first();
  await expect(icon).toBeVisible();
  const box = await icon.evaluate((node) => {
    const style = getComputedStyle(node);
    return { width: node.getBoundingClientRect().width, padding: parseFloat(style.paddingInlineStart) };
  });
  expect(box.width).toBeGreaterThanOrEqual(60);
  expect(box.width - 2 * box.padding).toBeGreaterThan(box.padding);
});
