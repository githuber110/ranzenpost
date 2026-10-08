const { test, expect } = require("@playwright/test");
const { goto, waitForSheetSettled } = require("./helpers");

const LAYOUTS = [
  { name: "phone", viewport: { width: 390, height: 844 }, scrim: "scrim", rise: "rise" },
  { name: "dialog", viewport: { width: 1024, height: 768 }, scrim: "scrim dialog", rise: "pop" },
];

function sheetMotion(page) {
  return page.evaluate(() => {
    const sheet = document.querySelector(".sheet");
    const scrim = sheet.parentElement;
    return {
      scrim: scrim.className,
      sheet: sheet.className,
      sheetAnimation: getComputedStyle(sheet).animationName,
      scrimAnimation: getComputedStyle(scrim).animationName,
      running: sheet.getAnimations().length + scrim.getAnimations().length,
    };
  });
}

for (const layout of LAYOUTS) {
  test.describe(`an open sheet stays put when the app repaints it (${layout.name})`, () => {
    test.use({ viewport: layout.viewport });

    test("the sheet slides in when it opens and not again on a repaint", async ({ page }) => {
      await goto(page);
      await page.evaluate(() => openSheet(languageSheet));
      const opened = await sheetMotion(page);
      expect(opened.scrim).toBe(layout.scrim);
      expect(opened.sheet).toBe("sheet");
      expect(opened.sheetAnimation).toBe(layout.rise);
      await waitForSheetSettled(page);

      await page.evaluate(() => {
        window.firstSheet = document.querySelector(".sheet");
        rerender();
      });
      expect(await page.evaluate(() => document.querySelector(".sheet") !== window.firstSheet)).toBe(true);
      expect(await sheetMotion(page)).toEqual({
        scrim: `${layout.scrim} shown`,
        sheet: "sheet shown",
        sheetAnimation: "none",
        scrimAnimation: "none",
        running: 0,
      });
    });
  });
}
