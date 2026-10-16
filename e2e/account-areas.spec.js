const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, waitForSheetSettled } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
let slot = 0;

async function open(page, { lang = "de", theme = "light" } = {}) {
  slot += 1;
  const run = `${process.pid}-${Date.now()}-${slot}`;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_modules", value: "all", url: BASE_URL },
    { name: "e2e_mail", value: `on:${run}`, url: BASE_URL },
    { name: "e2e_account", value: `on:${run}`, url: BASE_URL },
  ]);
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  await goto(page);
}

async function noHandOff(page) {
  const offenders = await page.evaluate(() => [...document.querySelectorAll(".screen a, .pane-detail a, .sheet a")]
    .filter((link) => !link.closest(".body-html"))
    .filter((link) => String(link.getAttribute("href") || "").includes("/iserv/") || link.getAttribute("target") === "_blank")
    .map((link) => link.outerHTML));
  expect(offenders).toEqual([]);
}

async function expectInside(page) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
}

async function openFiles(page) {
  await openArea(page, "files");
  await page.waitForSelector(".files-view .files-rows .row", { timeout: 10000 });
}

async function openContacts(page) {
  await openArea(page, "contacts");
  await page.waitForSelector(".contacts-view .search-input", { timeout: 10000 });
}

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`account areas ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: 860 }, colorScheme: theme });

      test("files, contacts and the spam action look like the rest of the app", async ({ page }) => {
        await open(page, { theme });
        await openFiles(page);
        await expect(page.locator(".files-rows .row-title")).toHaveText(["Projekte", "Lesetagebuch.pdf", "Notizen.txt"]);
        await noHandOff(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/account-files-${width}-${theme}.png` });
        await page.locator(".files-folder").first().click();
        await page.waitForSelector(".files-rows .row-title:has-text('Plakat.png')", { timeout: 10000 });
        await page.screenshot({ path: `test-results/account-files-folder-${width}-${theme}.png` });
        await openContacts(page);
        await page.locator(".contacts-view .search-input").fill("beh");
        await page.waitForSelector(".contact-person", { timeout: 10000 });
        await expect(page.locator(".contact-person .row-title")).toHaveText(["Anna Behrens", "Tom Behrendt"]);
        await expectInside(page);
        await page.screenshot({ path: `test-results/account-contacts-${width}-${theme}.png` });
        await page.locator(".contact-person").first().click();
        await waitForSheetSettled(page);
        await page.screenshot({ path: `test-results/account-person-${width}-${theme}.png` });
        await page.locator(".sheet .sheet-close").click();
        await page.waitForSelector(".sheet", { state: "detached", timeout: 10000 });
        await page.locator(".contacts-tabs .chip[data-tab='mailinglist']").click();
        await page.waitForSelector(".mailing-list", { timeout: 10000 });
        await noHandOff(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/account-lists-${width}-${theme}.png` });
        await page.locator(".mailing-list").first().click();
        await page.waitForSelector(".sheet .list-addresses", { timeout: 10000 });
        await waitForSheetSettled(page);
        await page.screenshot({ path: `test-results/account-list-${width}-${theme}.png` });
        await page.locator(".sheet .sheet-close").click();
        await page.waitForSelector(".sheet", { state: "detached", timeout: 10000 });
        await openArea(page, "mail");
        await page.locator(".mail-compose-open").click();
        await page.waitForSelector(".mail-from-list", { timeout: 10000 });
        await expectInside(page);
        await page.screenshot({ path: `test-results/account-compose-${width}-${theme}.png` });
      });
    });
  }
}

test.describe("account areas right to left", () => {
  test.use({ viewport: { width: 390, height: 860 }, locale: "ar" });

  test("files and contacts mirror in Arabic and stay inside the screen", async ({ page }) => {
    await open(page, { lang: "ar" });
    await openFiles(page);
    expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe("rtl");
    await expectInside(page);
    await page.screenshot({ path: "test-results/account-files-rtl.png" });
    await openContacts(page);
    await page.locator(".contacts-view .search-input").fill("beh");
    await page.waitForSelector(".contact-person", { timeout: 10000 });
    await expectInside(page);
    await page.screenshot({ path: "test-results/account-contacts-rtl.png" });
  });
});

test.describe("an account with only files and mail", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("opens the app with both areas instead of the no-modules page", async ({ page }) => {
    slot += 1;
    const run = `${process.pid}-${Date.now()}-${slot}`;
    await page.context().clearCookies();
    await page.context().addCookies([
      { name: "e2e_lang", value: "de", url: BASE_URL },
      { name: "e2e_modules", value: "none", url: BASE_URL },
      { name: "e2e_mail", value: `on:${run}`, url: BASE_URL },
      { name: "e2e_account", value: `files:${run}`, url: BASE_URL },
    ]);
    await goto(page);
    await page.waitForSelector(".tabbar", { timeout: 10000 });
    await expect(page.locator(".modules-empty")).toHaveCount(0);
    await openFiles(page);
    await expect(page.locator(".files-rows .row-title").first()).toHaveText("Projekte");
    await openArea(page, "mail");
    await page.waitForSelector(".mail-view .mail-row", { timeout: 10000 });
    await page.screenshot({ path: "test-results/account-only-files-mail.png" });
    const areas = await page.evaluate(() => navigationAreas());
    expect(areas).toEqual(["mail", "files"]);
  });
});

test.describe("account areas write only after a confirmation", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("an upload goes through the preview and shows the new file afterwards", async ({ page }) => {
    await open(page);
    await openFiles(page);
    await page.locator(".files-upload").click();
    await waitForSheetSettled(page);
    await page.locator(".files-upload-input").setInputFiles({ name: "Brief.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
    await page.locator(".files-upload-next").click();
    await expect(page.locator(".sheet")).toContainText("Brief.pdf");
    await page.screenshot({ path: "test-results/account-upload-preview.png" });
    await page.locator(".files-upload-send").click();
    await page.waitForSelector(".files-rows .row-title:has-text('Brief.pdf')", { timeout: 10000 });
  });

  test("an upload into a group folder uses the same preview and shows the file afterwards", async ({ page }) => {
    await open(page);
    await openFiles(page);
    await page.locator(".files-roots .chip[data-root='groups']").click();
    await page.waitForSelector(".files-folder:has-text('Klasse 3b')", { timeout: 10000 });
    await expect(page.locator(".files-upload")).toHaveCount(0);
    await page.locator(".files-folder").first().click();
    await page.waitForSelector(".files-rows .row-title:has-text('Elternbrief.pdf')", { timeout: 10000 });
    await page.locator(".files-upload").click();
    await waitForSheetSettled(page);
    await page.locator(".files-upload-input").setInputFiles({ name: "Plan.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") });
    await page.locator(".files-upload-next").click();
    await expect(page.locator(".sheet")).toContainText("Klasse 3b");
    await page.screenshot({ path: "test-results/account-group-upload-preview.png" });
    await page.locator(".files-upload-send").click();
    await page.waitForSelector(".files-rows .row-title:has-text('Plan.pdf')", { timeout: 10000 });
  });

  test("a mailing list is imported and deleted with the confirmation", async ({ page }) => {
    await open(page);
    await openContacts(page);
    await page.locator(".contacts-tabs .chip[data-tab='mailinglist']").click();
    await page.waitForSelector(".mailing-list", { timeout: 10000 });
    await page.locator(".lists-import").click();
    await waitForSheetSettled(page);
    await page.locator(".lists-import-input").setInputFiles({ name: "Sportfest.txt", mimeType: "text/plain", buffer: Buffer.from("a@example.org\nb@example.org\n") });
    await page.locator(".lists-import-field").fill("Sportfest");
    await page.locator(".lists-import-next").click();
    await page.locator(".lists-import-send").click();
    await page.waitForSelector(".mailing-list .row-title:has-text('Sportfest')", { timeout: 10000 });
    await page.locator(".mailing-list", { hasText: "Elternrat 3b" }).click();
    await page.waitForSelector(".sheet .list-addresses", { timeout: 10000 });
    await page.locator(".list-delete").click();
    await page.locator(".sheet .btn.destructive").click();
    await expect(page.locator(".mailing-list", { hasText: "Elternrat 3b" })).toHaveCount(0, { timeout: 10000 });
  });

  test("recipients come from a mailing list only after picking them", async ({ page }) => {
    await open(page);
    await openArea(page, "mail");
    await page.locator(".mail-compose-open").click();
    await page.locator(".mail-from-list").click();
    await page.locator(".sheet .compose-list").first().click();
    await page.waitForSelector(".sheet .compose-list-pick", { timeout: 10000 });
    await waitForSheetSettled(page);
    await page.screenshot({ path: "test-results/account-compose-pick.png" });
    await page.locator(".sheet .compose-list-pick").nth(1).uncheck();
    await page.locator(".compose-list-add").click();
    await expect(page.locator(".mail-to")).toHaveValue("anna.behrens@school-one.example");
  });

  test("a mail goes to the junk folder after the confirmation and comes back with undo", async ({ page }) => {
    await open(page);
    await openArea(page, "mail");
    await page.waitForSelector(".mail-view .mail-row", { timeout: 10000 });
    const rows = await page.locator(".mail-row").count();
    await page.locator(".mail-row").first().click();
    await page.waitForSelector(".mail-act-spam", { timeout: 10000 });
    await page.locator(".mail-act-spam").click();
    await page.locator(".sheet .btn-stack .btn").first().click();
    await page.waitForSelector(".mail-spam-undo", { timeout: 10000 });
    await expect(page.locator(".mail-row")).toHaveCount(rows - 1);
    await page.screenshot({ path: "test-results/account-spam-undo.png" });
    await page.locator(".mail-spam-undo").click();
    await expect(page.locator(".mail-row")).toHaveCount(rows, { timeout: 10000 });
  });
});
