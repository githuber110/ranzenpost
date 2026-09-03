const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport, checkTapTargets } = require("./helpers");

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
  { key: "ar", locale: "ar" },
];

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const TINY_JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=",
  "base64"
);

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openImageOverlay(page) {
  await page.route("**/api/e2e-test-image.jpg", (route) =>
    route.fulfill({ status: 200, contentType: "image/jpeg", body: TINY_JPEG })
  );
  await page.evaluate(() => {
    const rows = attachmentRows([{ filename: "Klassenfoto.jpg", url: "api/e2e-test-image.jpg" }]);
    rows.id = "e2e-attachment-rows";
    rows.style.position = "fixed";
    rows.style.inset = "0 0 auto 0";
    rows.style.zIndex = "45";
    rows.style.background = "var(--surface)";
    document.body.append(rows);
  });
  await page.locator("#e2e-attachment-rows .row").click();
  await page.waitForSelector(".viewer-overlay");
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`[P197] file viewer overlay ${viewport.name}/${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("opens for an image without horizontal overflow or elements outside the viewport", async ({ page }) => {
        await goto(page);
        await waitForContentSettled(page);
        await openImageOverlay(page);

        const overlay = page.locator(".viewer-overlay");
        await expect(overlay).toBeVisible();
        await expect(page.locator(".viewer-img")).toHaveAttribute("src", /^blob:/);

        const overflow = await checkHorizontalOverflow(page);
        const offenders = await checkElementsWithinViewport(page);
        expect(overflow.overflow, `${viewport.name}/${lang.key}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`).toBe(false);
        expect(offenders, `${viewport.name}/${lang.key}: ${JSON.stringify(offenders)}`).toEqual([]);

        const tapOffenders = await checkTapTargets(page);
        expect(tapOffenders, `${viewport.name}/${lang.key}: ${JSON.stringify(tapOffenders)}`).toEqual([]);
      });

      test("the close button carries a 44px hit target and closes the overlay", async ({ page }) => {
        await goto(page);
        await waitForContentSettled(page);
        await openImageOverlay(page);

        const close = page.locator(".viewer-close");
        const box = await close.boundingBox();
        expect(box, `${viewport.name}/${lang.key}: close button has no box`).toBeTruthy();
        expect(box.width, `${viewport.name}/${lang.key}: close width`).toBeGreaterThanOrEqual(44);
        expect(box.height, `${viewport.name}/${lang.key}: close height`).toBeGreaterThanOrEqual(44);

        await close.click();
        await expect(page.locator(".viewer-overlay")).toHaveCount(0);
      });

      test("Escape closes the overlay and returns focus to the attachment row", async ({ page }) => {
        await goto(page);
        await waitForContentSettled(page);
        await openImageOverlay(page);

        await page.keyboard.press("Escape");
        await expect(page.locator(".viewer-overlay")).toHaveCount(0);
        await expect(page.locator("#e2e-attachment-rows .row")).toBeFocused();
      });
    });
  }
}
