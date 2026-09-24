const { test, expect } = require("@playwright/test");
const { goto, openArea } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1440", width: 1440, height: 900 },
];
const LANGUAGES = [
  { key: "en", locale: "en-US" },
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];

let slot = 0;

async function openShowcaseWeek(page, lang) {
  slot += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_scenario", value: "showcase", url: BASE_URL },
    { name: "e2e_layout", value: `own-fit-${process.pid}-${Date.now()}-${slot}`, url: BASE_URL },
  ]);
  await goto(page);
  await openArea(page, "timetable");
  await page.waitForSelector(".tt-own", { timeout: 10000 });
  await page.evaluate(() => document.fonts.ready);
}

async function clippedEntries(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll(".tt-own")]
      .filter((cell) => cell.getClientRects().length)
      .filter((cell) => {
        const box = cell.getBoundingClientRect();
        return [...cell.children].some((part) => {
          const inner = part.getBoundingClientRect();
          return inner.top < box.top - 1 || inner.bottom > box.bottom + 1 || part.scrollHeight > part.clientHeight + 1;
        });
      })
      .map((cell) => cell.getAttribute("aria-label"))
  );
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    test.describe(`own entries in the week ${viewport.name} ${lang.key}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

      test("every own entry shows its name and time without cutting them", async ({ page }) => {
        await openShowcaseWeek(page, lang.key);
        expect(await page.locator(".tt-own").count()).toBeGreaterThan(0);
        expect(await clippedEntries(page)).toEqual([]);
      });
    });
  }
}
