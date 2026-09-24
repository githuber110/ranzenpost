const fs = require("fs");
const zlib = require("zlib");
const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const WIDTHS = [390, 1024];
const ALL_MODULES = "timetable,letters,pinboard,absences,conferences,messenger";
const ISSUE_URL = "https://github.com/githuber110/ranzenpost/issues/new?";
const FIXTURE_WORDS = ["Musterkind", "Riverside", "Hillview", "school-one.example", "parent.one", "Langenscheidt"];
const BUNDLE_NAME = "ranzenpost-report.zip";
const CENTRAL_END = Buffer.from([0x50, 0x4b, 0x05, 0x06]);

function unzip(buffer) {
  const files = {};
  const end = buffer.lastIndexOf(CENTRAL_END);
  const count = buffer.readUInt16LE(end + 10);
  let offset = buffer.readUInt32LE(end + 16);
  for (let index = 0; index < count; index += 1) {
    const method = buffer.readUInt16LE(offset + 10);
    const size = buffer.readUInt32LE(offset + 20);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    const local = buffer.readUInt32LE(offset + 42);
    const name = buffer.toString("utf8", offset + 46, offset + 46 + nameLength);
    const start = local + 30 + buffer.readUInt16LE(local + 26) + buffer.readUInt16LE(local + 28);
    const data = buffer.subarray(start, start + size);
    files[name] = (method === 8 ? zlib.inflateRawSync(data) : data).toString("utf8");
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return files;
}

test.describe.configure({ mode: "serial" });

let matrixSlot = 0;

function nextMatrixKey() {
  matrixSlot += 1;
  return `help-report-${process.pid}-${Date.now()}-${matrixSlot}`;
}

async function open(page, width) {
  await page.setViewportSize({ width, height: 844 });
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_modules", value: ALL_MODULES, url: BASE_URL },
    { name: "e2e_reports", value: "1", url: BASE_URL },
    { name: "e2e_matrix", value: nextMatrixKey(), url: BASE_URL },
  ]);
  await page.request.post(`${BASE_URL}/api/config`, { data: { reported_modules: [], modules_card_hidden: {} } });
  await goto(page);
  await page.waitForTimeout(150);
}

async function reload(page) {
  await goto(page);
  await page.waitForTimeout(150);
}

for (const width of WIDTHS) {
  test.describe(`the module card and the help page at ${width}px`, () => {
    test("the overview shows the card with the fixture's unknown modules and both buttons", async ({ page }) => {
      await open(page, width);
      const card = page.locator(".overview .panel .module-card");
      await expect(card).toBeVisible();
      await expect(card).toContainText("E-Mail");
      await expect(card).toContainText("Videokonferenzen");
      await expect(card).toContainText("2 Module");
      await expect(card.locator(".module-card-show")).toHaveText("Zeig mir wie");
      await expect(card.locator(".module-card-later")).toHaveText("Später");
      expect(await page.locator(".error, .note, .toast").count()).toBe(0);
      const box = await card.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    });

    test("show how opens the help page, the report renders, copy works and the card is gone after copy and after reload", async ({ page, context }) => {
      await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE_URL });
      await open(page, width);
      await page.locator(".module-card-show").click();
      await expect(page.locator(".help-page")).toBeVisible();
      await expect(page.locator(".header-title")).toHaveText("Problem melden");
      await expect(page.locator(".help-page")).toContainText("Das steht drin");
      await expect(page.locator(".help-page")).toContainText("Das steht nie drin");
      expect(await page.locator(".help-structure").count()).toBe(0);
      await expect(page.locator("details.help-details")).not.toHaveAttribute("open", "");
      await page.locator(".help-details > summary").click();
      const preview = page.locator(".help-preview");
      await expect(preview).toBeVisible({ timeout: 20000 });
      await expect(preview).toContainText("# Ranzenpost report");
      await expect(preview).toContainText("## Log");
      await expect(preview).toContainText("videoconference");
      const shown = await preview.textContent();
      for (const word of FIXTURE_WORDS) expect(shown.toLowerCase()).not.toContain(word.toLowerCase());
      const issue = page.locator("a.help-issue");
      expect((await issue.getAttribute("href")).startsWith(ISSUE_URL)).toBe(true);
      expect(await issue.getAttribute("target")).toBe("_blank");
      await expect(page.locator(".help-copy")).toBeEnabled();
      await page.locator(".help-copy").click();
      await expect(page.locator(".toast")).toContainText("Bericht kopiert");
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(copied.startsWith("# Ranzenpost report")).toBe(true);
      expect(copied).toContain("### Page structure");
      await page.waitForTimeout(200);
      await page.locator(".header-back").click();
      await page.waitForTimeout(100);
      expect(await page.locator(".module-card").count()).toBe(0);
      await reload(page);
      expect(await page.locator(".module-card").count()).toBe(0);
      await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
      await page.waitForTimeout(100);
      await expect(page.locator(".modules-block .modules-report")).toBeVisible();
      expect(await page.locator(".modules-block .module-card").count()).toBe(0);
    });

    test("save report downloads ranzenpost-report.zip with the report and the log, both free of fixture names", async ({ page }) => {
      await page.addInitScript(() => { delete window.showSaveFilePicker; });
      await open(page, width);
      await page.locator(".module-card-show").click();
      await expect(page.locator(".help-preview")).toContainText("### Page structure", { timeout: 20000 });
      const save = page.locator(".help-save");
      await expect(save).toBeEnabled({ timeout: 20000 });
      await expect(save).toHaveText("Bericht speichern");
      expect(await page.locator(".help-actions > .btn:not(.ghost)").count()).toBe(1);
      const [download] = await Promise.all([page.waitForEvent("download"), save.click()]);
      expect(download.suggestedFilename()).toBe(BUNDLE_NAME);
      await expect(page.locator(".toast")).toContainText("Bericht gespeichert");
      const files = unzip(fs.readFileSync(await download.path()));
      expect(Object.keys(files).sort()).toEqual(["log.txt", "report.md"]);
      expect(files["report.md"].startsWith("# Ranzenpost report")).toBe(true);
      expect(files["report.md"]).toContain("### Page structure");
      expect(files["report.md"]).toContain("videoconference");
      expect(files["report.md"]).toContain("- Full log: log.txt in ranzenpost-report.zip");
      expect(files["report.md"]).toContain("| timetable-legacy |");
      expect(files["log.txt"].startsWith("# Ranzenpost log\n- Covered: ")).toBe(true);
      for (const text of [files["report.md"], files["log.txt"]]) {
        for (const word of FIXTURE_WORDS) expect(text.toLowerCase()).not.toContain(word.toLowerCase());
      }
      const issue = new URL(await page.locator("a.help-issue").getAttribute("href"));
      expect(issue.searchParams.get("body")).toContain("Attach the saved file ranzenpost-report.zip");
      expect(issue.searchParams.get("body")).toContain("IServ 3.9.1");
      await page.waitForTimeout(200);
      await page.locator(".header-back").click();
      await page.waitForTimeout(100);
      expect(await page.locator(".module-card").count()).toBe(0);
    });

    test("later hides the card, also after a reload, and the settings still carry the card without later", async ({ page }) => {
      await open(page, width);
      await page.locator(".module-card-later").click();
      await page.waitForTimeout(200);
      expect(await page.locator(".module-card").count()).toBe(0);
      await reload(page);
      expect(await page.locator(".overview .module-card").count()).toBe(0);
      await page.getByRole("button", { name: "Einstellungen", exact: true }).click();
      await page.waitForTimeout(100);
      const card = page.locator(".modules-block .module-card");
      await expect(card).toBeVisible();
      expect(await card.locator(".module-card-later").count()).toBe(0);
      await expect(page.locator(".setting-row.help-setting")).toHaveText(/Problem melden/);
      await page.locator(".setting-row.help-setting").click();
      await expect(page.locator(".help-page")).toBeVisible();
      await page.locator(".header-back").click();
      await expect(page.locator(".settings-group").first()).toBeVisible();
    });
  });
}
