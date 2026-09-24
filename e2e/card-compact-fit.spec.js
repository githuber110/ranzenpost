const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..");
const ORIGIN = "http://card.harness";
const CARD_FROZEN_TIME = "2026-09-02T07:15:00Z";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json" };
const WIDTHS = [360, 480, 640, 900];
const LANGUAGES = ["en", "de", "ar"];
const LAYOUTS = [
  "blocks=today:compact,next_lesson:compact,letters:compact&second=lessons",
  "blocks=today,letters,holidays&second=lessons",
  "blocks=today:compact,next_lesson:compact&children=alex",
  "blocks=today:compact,letters:compact,holidays&scene=showcase&names=Mia,Tom",
];

async function serveRepository(page) {
  await page.route((url) => url.origin === ORIGIN, async (route) => {
    const url = new URL(route.request().url());
    const file = path.join(ROOT, decodeURIComponent(url.pathname));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      await route.fulfill({ status: 404, body: "" });
      return;
    }
    await route.fulfill({ path: file, contentType: TYPES[path.extname(file)] || "application/octet-stream" });
  });
}

async function clippedTitles(page) {
  return page.evaluate(() => {
    const root = document.querySelector("ranzenpost-card").shadowRoot;
    return [...root.querySelectorAll(".row-title, .row-meta, .tag")]
      .filter((node) => node.getClientRects().length)
      .filter((node) => node.scrollWidth > node.clientWidth + 1 && getComputedStyle(node).textOverflow !== "ellipsis")
      .map((node) => node.textContent.trim());
  });
}

for (const width of WIDTHS) {
  for (const lang of LANGUAGES) {
    for (const layout of LAYOUTS) {
      test(`card rows keep every word readable at ${width}px in ${lang} (${layout})`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await serveRepository(page);
        await page.clock.install({ time: new Date(CARD_FROZEN_TIME) });
        await page.goto(`${ORIGIN}/scripts/card-harness.html?${layout}&lang=${lang}${lang === "ar" ? "&dir=rtl" : ""}`);
        await page.waitForSelector("body[data-ready='true']", { timeout: 15000 });
        await page.evaluate(() => document.fonts.ready);
        expect(await page.locator("ranzenpost-card .row").count()).toBeGreaterThan(0);
        expect(await clippedTitles(page)).toEqual([]);
      });
    }
  }
}
