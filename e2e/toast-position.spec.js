const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

async function toastOffset(page) {
  await page.evaluate(() => toast("e2e probe toast"));
  const node = page.locator(".toast");
  await expect(node).toBeVisible();
  await page.waitForTimeout(300);
  return page.evaluate(() => {
    const box = document.querySelector(".toast").getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    return { left: box.left, right: width - box.right, width: box.width, viewport: width };
  });
}

for (const motion of ["no-preference", "reduce"]) {
  test(`toast stays centred with ${motion} motion`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: motion });
    await goto(page);
    const offset = await toastOffset(page);
    expect(offset.left).toBeGreaterThanOrEqual(0);
    expect(offset.right).toBeGreaterThanOrEqual(0);
    expect(offset.width).toBeLessThan(offset.viewport);
    expect(Math.abs(offset.left - offset.right)).toBeLessThanOrEqual(1);
  });
}
