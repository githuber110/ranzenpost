const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..");
const ORIGIN = "http://card.harness";
const CARD_FROZEN_TIME = "2026-09-02T07:15:00Z";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json" };
const WIDTHS = [320, 390];
const LANGUAGES = ["de", "ar"];

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

async function mountEditor(page) {
  await page.evaluate(async () => {
    const card = document.querySelector("ranzenpost-card");
    card.remove();
    const editor = customElements.get("ranzenpost-card").getConfigElement();
    editor.setConfig({ blocks: ["today", { key: "letters", size: "compact" }, "holidays"], children: ["alex"] });
    document.body.appendChild(editor);
    editor.hass = card.hass;
    await editor.settled;
  });
}

async function layoutFaults(page) {
  return page.evaluate(() => {
    const root = document.querySelector("ranzenpost-card-editor").shadowRoot;
    const faults = [];
    const width = document.documentElement.clientWidth;
    for (const node of root.querySelectorAll("*")) {
      const box = node.getBoundingClientRect();
      if (!box.width) continue;
      if (box.left < -1 || box.right > width + 1) faults.push(`outside: ${node.className || node.tagName}`);
    }
    for (const row of root.querySelectorAll(".block-row")) {
      const frame = row.getBoundingClientRect();
      if (frame.height < 44) faults.push(`short row: ${row.dataset.block}`);
      for (const part of row.querySelectorAll(".block-pick, .block-tools, .order-move, select")) {
        const box = part.getBoundingClientRect();
        if (box.left < frame.left - 1 || box.right > frame.right + 1) faults.push(`sticks out: ${row.dataset.block} ${part.className || part.tagName}`);
      }
      const pick = row.querySelector(".block-pick").getBoundingClientRect();
      const tools = row.querySelector(".block-tools");
      if (tools) {
        const box = tools.getBoundingClientRect();
        const overlap = Math.min(pick.right, box.right) - Math.max(pick.left, box.left) > 1 && Math.min(pick.bottom, box.bottom) - Math.max(pick.top, box.top) > 1;
        if (overlap) faults.push(`tools cover the name: ${row.dataset.block}`);
      }
    }
    for (const button of root.querySelectorAll(".order-move")) {
      const box = button.getBoundingClientRect();
      if (box.width < 40 || box.height < 40) faults.push(`small move button: ${button.dataset.block}`);
    }
    return faults;
  });
}

for (const width of WIDTHS) {
  for (const lang of LANGUAGES) {
    test(`card editor keeps every block row in one piece at ${width}px in ${lang}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await serveRepository(page);
      await page.clock.install({ time: new Date(CARD_FROZEN_TIME) });
      await page.goto(`${ORIGIN}/scripts/card-harness.html?blocks=today&lang=${lang}${lang === "ar" ? "&dir=rtl" : ""}`);
      await page.waitForSelector("body[data-ready='true']", { timeout: 15000 });
      await mountEditor(page);
      const editor = page.locator("ranzenpost-card-editor");
      await expect(editor.locator(".block-row.on")).toHaveCount(3);
      await expect(editor.locator(".children")).toBeVisible();
      expect(await layoutFaults(page)).toEqual([]);

      await editor.locator('.block-row.on[data-block="holidays"] .order-move[data-move="up"]').click();
      await expect(editor.locator(".block-row.on").nth(1)).toHaveAttribute("data-block", "holidays");
      await editor.locator('input[name="blocks"][value="week"]').check();
      await expect(editor.locator(".block-row.on")).toHaveCount(4);
      expect(await layoutFaults(page)).toEqual([]);
    });
  }
}
