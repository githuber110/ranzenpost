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

const TWO_PAGE_PDF = Buffer.from(
  "JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwg" +
  "L1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUiA0IDAgUl0gL0NvdW50IDIgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUg" +
  "L1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9G" +
  "MSA1IDAgUiA+PiA+PiAvQ29udGVudHMgNiAwIFIgPj4KZW5kb2JqCjQgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVu" +
  "dCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXSAvUmVzb3VyY2VzIDw8IC9Gb250IDw8IC9GMSA1IDAgUiA+PiA+" +
  "PiAvQ29udGVudHMgNyAwIFIgPj4KZW5kb2JqCjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9C" +
  "YXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iago2IDAgb2JqCjw8IC9MZW5ndGggMzkgPj4Kc3RyZWFtCkJUIC9GMSAy" +
  "NCBUZiA3MiA3MDAgVGQgKFBhZ2Ugb25lKSBUaiBFVAplbmRzdHJlYW0KZW5kb2JqCjcgMCBvYmoKPDwgL0xlbmd0aCAz" +
  "OSA+PgpzdHJlYW0KQlQgL0YxIDI0IFRmIDcyIDcwMCBUZCAoUGFnZSB0d28pIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoK" +
  "eHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDA5IDAwMDAwIG4gCjAwMDAwMDAwNTggMDAwMDAgbiAK" +
  "MDAwMDAwMDEyMSAwMDAwMCBuIAowMDAwMDAwMjQ3IDAwMDAwIG4gCjAwMDAwMDAzNzMgMDAwMDAgbiAKMDAwMDAwMDQ0" +
  "MyAwMDAwMCBuIAowMDAwMDAwNTMyIDAwMDAwIG4gCnRyYWlsZXIKPDwgL1NpemUgOCAvUm9vdCAxIDAgUiA+PgpzdGFy" +
  "dHhyZWYKNjIxCiUlRU9GCg==",
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

async function openPdfOverlay(page) {
  await page.route("**/api/e2e-test-file.pdf", (route) =>
    route.fulfill({ status: 200, contentType: "application/pdf", body: TWO_PAGE_PDF })
  );
  await page.evaluate(() => {
    const rows = attachmentRows([{ filename: "Elternbrief.pdf", url: "api/e2e-test-file.pdf" }]);
    rows.id = "e2e-attachment-rows";
    rows.style.position = "fixed";
    rows.style.inset = "0 0 auto 0";
    rows.style.zIndex = "45";
    rows.style.background = "var(--surface)";
    document.body.append(rows);
  });
  await page.locator("#e2e-attachment-rows .row").click();
  await page.waitForSelector(".viewer-overlay .viewer-pdf-wrap", { timeout: 4000 });
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

      test("[P216] a pdf renders every page in one scrolling column, fit to the viewport width", async ({ page }) => {
        await goto(page);
        await waitForContentSettled(page);
        await openPdfOverlay(page);

        await expect(page.locator(".viewer-overlay iframe")).toHaveCount(0);
        const column = page.locator(".pdfv-column");
        await expect(column).toBeVisible();
        await page.waitForSelector(".pdfv-page", { timeout: 10000 });
        const pages = await page.locator(".pdfv-page").count();
        expect(pages, `${viewport.name}/${lang.key}: both pages must exist, not just page one`).toBe(2);

        const columnBox = await column.boundingBox();
        expect(columnBox, `${viewport.name}/${lang.key}: column has no box`).toBeTruthy();
        expect(
          columnBox.width,
          `${viewport.name}/${lang.key}: column width ${columnBox.width} exceeds viewport ${viewport.width}`
        ).toBeLessThanOrEqual(viewport.width + 1);
        expect(
          columnBox.x,
          `${viewport.name}/${lang.key}: column x-offset ${columnBox.x} pushes content off-screen`
        ).toBeGreaterThanOrEqual(-1);

        const scrollable = await page.evaluate(() => {
          const wrap = document.querySelector(".viewer-pdf-wrap");
          return wrap ? { scrollHeight: wrap.scrollHeight, clientHeight: wrap.clientHeight } : null;
        });
        expect(scrollable, `${viewport.name}/${lang.key}: no scroll container`).toBeTruthy();

        const overflow = await checkHorizontalOverflow(page);
        expect(overflow.overflow, `${viewport.name}/${lang.key}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`).toBe(false);
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
