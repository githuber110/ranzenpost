const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, waitForSheetSettled } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
let slot = 0;

async function open(page, { lang = "de", theme = "light", mode = "on" } = {}) {
  slot += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: lang, url: BASE_URL },
    { name: "e2e_modules", value: "all", url: BASE_URL },
    { name: "e2e_mail", value: `${mode}:${process.pid}-${Date.now()}-${slot}`, url: BASE_URL },
  ]);
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  await goto(page);
}

async function openMail(page) {
  await openArea(page, "mail");
  await page.waitForSelector(".mail-view .mail-row, .mail-view .empty", { timeout: 10000 });
}

async function noHandOff(page) {
  const offenders = await page.evaluate(() => [...document.querySelectorAll(".screen a, .pane-detail a")]
    .filter((link) => !link.closest(".body-html"))
    .filter((link) => String(link.getAttribute("href") || "").includes("/iserv/") || link.getAttribute("target") === "_blank")
    .map((link) => link.outerHTML));
  expect(offenders).toEqual([]);
}

async function expectInside(page) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
}

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`mail ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: 860 }, colorScheme: theme });

      test("the overview hint, the list, a mail and the compose page stay inside the app", async ({ page }) => {
        await open(page, { theme });
        const hint = page.locator(".mail-notice");
        await expect(hint).toBeVisible();
        await expect(hint.locator("a")).toHaveCount(0);
        await page.screenshot({ path: `test-results/mail-overview-${width}-${theme}.png` });
        await page.evaluate(() => document.querySelector(".screen").scrollTo(0, 0));
        await page.screenshot({ path: `test-results/mail-overview-top-${width}-${theme}.png` });
        await expect(hint.locator(".mail-notice-open").first()).toBeInViewport();
        await hint.locator(".mail-notice-open").first().click();
        await page.waitForSelector(".mail-view .mail-row", { timeout: 10000 });
        await expect(page.locator(".mail-folders .chip")).toHaveCount(7);
        await expect(page.locator(".mail-row").first()).not.toHaveClass(/read/);
        await noHandOff(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-list-${width}-${theme}.png`, fullPage: true });

        await page.locator('.mail-row[data-uid="7"]').click();
        await page.waitForSelector(".mail-detail .mail-body", { timeout: 10000 });
        await expect(page.locator(".mail-detail .mail-text")).toContainText("Das Training heute");
        await noHandOff(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-detail-${width}-${theme}.png`, fullPage: true });

        if (await page.locator(".header-back").count()) await page.locator(".header-back").click();
        await expect(page.locator(".mail-folders .chip").first().locator(".n")).toHaveText("1");
        await page.locator(".mail-compose-open").click();
        await page.waitForSelector(".mail-compose .mail-editor", { timeout: 10000 });
        await page.locator(".mail-compose .mail-to").fill("Klassenleitung <teacher@school-one.example>");
        await page.locator(".mail-compose .mail-subject-input").fill("Frage zum Ausflug");
        await page.locator(".mail-compose .mail-editor").fill("Hallo, kommt der Bus um acht?");
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-compose-${width}-${theme}.png`, fullPage: true });
        await page.locator(".mail-send").click();
        await page.waitForSelector(".sheet .mail-send-confirm", { timeout: 5000 });
        await waitForSheetSettled(page);
        await expect(page.locator(".sheet")).toContainText("teacher@school-one.example");
        await page.screenshot({ path: `test-results/mail-send-confirm-${width}-${theme}.png` });
        await page.locator(".sheet .btn.ghost").first().click();
      });

      test("the html mail with attachments, the folder sheet and the filter sheet", async ({ page }) => {
        await open(page, { theme });
        await openMail(page);
        await page.locator('.mail-row[data-uid="3"]').click();
        await page.waitForSelector(".mail-detail iframe.mail-frame", { timeout: 10000 });
        await expect(page.frameLocator("iframe.mail-frame").locator("b")).toHaveText("all");
        expect(await page.locator("iframe.mail-frame").getAttribute("sandbox")).toBe("allow-popups allow-popups-to-escape-sandbox");
        await expect(page.locator(".mail-detail .mail-receipt")).toBeVisible();
        await expect(page.locator(".mail-detail .rows .row")).toHaveCount(2);
        await noHandOff(page);
        await page.screenshot({ path: `test-results/mail-html-${width}-${theme}.png`, fullPage: true });
        if (await page.locator(".header-back").count()) await page.locator(".header-back").click();
        await page.locator(".mail-tools button", { hasText: /Ordner|Folders/ }).click();
        await page.waitForSelector(".sheet .mail-folder-row", { timeout: 5000 });
        await page.screenshot({ path: `test-results/mail-folders-${width}-${theme}.png` });
        await page.keyboard.press("Escape");
        await page.waitForTimeout(300);
        await page.locator(".mail-tools button", { hasText: /Filter/ }).click();
        await page.waitForSelector(".sheet .mail-filter-apply", { timeout: 5000 });
        await page.screenshot({ path: `test-results/mail-filter-${width}-${theme}.png` });
      });
    });
  }
}

test.describe("mail behaviour", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("opening an unread mail marks it read and lowers the counts, the list alone does not", async ({ page }) => {
    await open(page);
    await openMail(page);
    const seen = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/mail/seen")) seen.push(request.postDataJSON());
    });
    await page.waitForTimeout(500);
    expect(seen).toEqual([]);
    await page.locator('.mail-row[data-uid="6"]').click();
    await page.waitForSelector(".mail-detail .mail-body", { timeout: 10000 });
    await expect.poll(() => seen.length).toBe(1);
    expect(seen[0]).toMatchObject({ folder: "INBOX", uid: "6" });
    await page.locator(".header-back").click();
    await expect(page.locator('.mail-row[data-uid="6"]')).toHaveClass(/read/);
    await expect(page.locator(".mail-folders .chip").first().locator(".n")).toHaveText("1");
  });

  test("sending asks first and the sent mail is filed", async ({ page }) => {
    await open(page);
    await openMail(page);
    await page.locator(".mail-compose-open").click();
    await page.waitForSelector(".mail-compose .mail-editor", { timeout: 10000 });
    await page.locator(".mail-compose .mail-to").fill("teacher@school-one.example");
    await page.locator(".mail-compose .mail-subject-input").fill("Frage");
    await page.locator(".mail-compose .mail-editor").fill("Hallo");
    const sends = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/mail/send")) sends.push(request.url());
    });
    await page.locator(".mail-send").click();
    await page.waitForSelector(".sheet", { timeout: 5000 });
    expect(sends).toEqual([]);
    await page.locator(".sheet .mail-send-confirm").click();
    await expect.poll(() => sends.length).toBe(1);
    await page.waitForSelector(".mail-view", { timeout: 10000 });
    await page.locator('.mail-folders .chip[data-folder="Sent"]').click();
    await expect(page.locator(".mail-row .mail-subject", { hasText: "Frage" })).toHaveCount(1);
  });

  test("a refused mailbox sign-in shows its reason and no empty list", async ({ page }) => {
    await open(page, { mode: "refused" });
    await openArea(page, "mail");
    await page.waitForSelector(".mail-view .empty", { timeout: 10000 });
    await expect(page.locator(".mail-view .empty b")).toHaveText("Anmeldung am Postfach abgelehnt");
    await expect(page.locator(".mail-view .mail-row")).toHaveCount(0);
  });
});

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`mail settings ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: 860 }, colorScheme: theme });

      test("settings pages, the out-of-office form, filter rules and tags", async ({ page }) => {
        await open(page, { theme });
        await openMail(page);
        await expect(page.locator('.mail-row[data-uid="3"] .mail-tag')).toHaveText("Wichtig");
        await page.locator(".mail-settings-open").click();
        await page.waitForSelector(".mail-settings .mail-setting-page", { timeout: 10000 });
        await expect(page.locator(".mail-setting-page")).toHaveCount(5);
        await noHandOff(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-settings-${width}-${theme}.png`, fullPage: true });

        await page.locator('.mail-setting-page[data-kind="vacation"]').click();
        await page.waitForSelector(".mail-setting-form", { timeout: 10000 });
        await page.locator('.mail-setting-field[data-name="vacation[subject]"] input').fill("Bin unterwegs");
        await page.locator('.mail-setting-field[data-name="vacation[enabled]"] input').check();
        await page.locator(".mail-setting-save").click();
        await page.waitForSelector(".sheet", { timeout: 5000 });
        await page.locator(".sheet .btn:not(.ghost)").first().click();
        await expect(page.locator(".mail-setting-saved")).toBeVisible({ timeout: 10000 });
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-vacation-${width}-${theme}.png`, fullPage: true });

        await page.locator(".header-back").click();
        await page.locator('.mail-setting-page[data-kind="filter"]').click();
        await page.waitForSelector(".mail-rule", { timeout: 10000 });
        await page.locator(".mail-rule-add").click();
        await expect(page.locator(".mail-rule")).toHaveCount(2);
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-rules-${width}-${theme}.png`, fullPage: true });
      });
    });
  }
}

test.describe("mail settings behaviour", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("a new filter rule is saved through the form and read back", async ({ page }) => {
    await open(page);
    await openMail(page);
    await page.locator(".mail-settings-open").click();
    await page.locator('.mail-setting-page[data-kind="filter"]').click();
    await page.waitForSelector(".mail-rule", { timeout: 10000 });
    await page.locator(".mail-rule-add").click();
    const added = page.locator(".mail-rule").nth(1);
    await added.locator('[data-name="filter[rules][1][name]"] input').fill("Spam");
    await added.locator('[data-name="filter[rules][1][value]"] input').fill("Gewinn");
    await added.locator('[data-name="filter[rules][1][action]"] select').selectOption("discard");
    await page.locator(".mail-setting-save").click();
    await page.locator(".sheet .btn:not(.ghost)").first().click();
    await expect(page.locator(".mail-setting-saved")).toBeVisible({ timeout: 10000 });
    await expect(page.locator(".mail-rule")).toHaveCount(2);
  });

  test("the tag sheet sets a tag on a mail", async ({ page }) => {
    await open(page);
    await openMail(page);
    await page.locator('.mail-row[data-uid="5"]').click();
    await page.waitForSelector(".mail-detail .mail-body", { timeout: 10000 });
    await page.locator(".mail-act-more").click();
    await page.locator(".sheet .mail-tags").click();
    await page.waitForSelector('.sheet .mail-tag-check[data-tag="$label2"]', { timeout: 5000 });
    await waitForSheetSettled(page);
    await page.screenshot({ path: "test-results/mail-tags-390.png" });
    await page.locator('.sheet .mail-tag-check[data-tag="$label2"]').check();
    await expect(page.locator('.sheet .mail-tag-check[data-tag="$label2"]')).toBeChecked();
  });
});

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`mail event ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: 860 }, colorScheme: theme });

      test("a calendar entry from a mail is prefilled, confirmed and found in the calendar", async ({ page }) => {
        await open(page, { theme });
        await openMail(page);
        await page.locator('.mail-row[data-uid="4"]').click();
        await page.waitForSelector(".mail-detail .mail-body", { timeout: 10000 });
        await page.locator(".mail-act-more").click();
        await page.locator(".sheet .mail-event").click();
        await page.waitForSelector('.sheet [data-name="event[subject]"] input', { timeout: 10000 });
        await expect(page.locator('.sheet [data-name="event[subject]"] input')).toHaveValue("Elternabend");
        await expect(page.locator('.sheet [data-name="event[description]"] textarea')).toHaveValue(/Elternabend findet am Dienstag/);
        await page.locator('.sheet [data-name="event[startDate]"] input').fill("2026-10-27");
        await page.locator('.sheet [data-name="event[startTime]"] input').fill("19:00");
        await page.locator('.sheet [data-name="event[calendar]"] select').selectOption("/eltern.3b/calendar");
        await waitForSheetSettled(page);
        await expectInside(page);
        await page.screenshot({ path: `test-results/mail-event-${width}-${theme}.png` });
        await page.locator(".sheet .mail-event-save").click();
        await page.locator(".sheet .btn:not(.ghost):not(.mail-event-save)").first().click();
        await expect(page.locator(".toast")).toContainText("Termin gespeichert", { timeout: 10000 });
      });
    });
  }
}

test.describe("mail signature per address", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("switching the sender inserts that address's default signature", async ({ page }) => {
    await open(page);
    await openMail(page);
    await page.locator(".mail-compose-open").click();
    await page.waitForSelector(".mail-compose select.mail-from", { timeout: 10000 });
    await page.locator(".mail-compose select.mail-from").selectOption("elternrat@school-one.example");
    await page.waitForTimeout(500);
    await expect(page.locator(".mail-editor .mail-signature")).toHaveCount(0);
    await page.locator(".mail-compose select.mail-from").selectOption("alexa.muster@school-one.example");
    await expect(page.locator(".mail-editor .mail-signature")).toContainText("Viele Grüße", { timeout: 10000 });
  });
});

test.describe("mail attachments stay inert", () => {
  test.use({ viewport: { width: 390, height: 860 } });

  test("a script or page attachment can never run in the app", async ({ page }) => {
    await open(page);
    await openMail(page);
    const url = (part) => `api/mail/attachment?connection=a1b2c3d4&folder=INBOX&uid=2&part=${part}`;
    const answer = await page.request.get(`${BASE_URL}/${url(2)}`);
    expect(answer.headers()["content-type"]).toContain("application/octet-stream");
    expect(answer.headers()["content-security-policy"]).toBe("sandbox; default-src 'none'");
    await page.evaluate((source) => new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = source;
      script.onload = resolve;
      script.onerror = resolve;
      document.head.append(script);
    }), url(2));
    await page.evaluate((source) => new Promise((resolve) => {
      const frame = document.createElement("iframe");
      frame.src = source;
      frame.onload = resolve;
      frame.onerror = resolve;
      document.body.append(frame);
      setTimeout(resolve, 1500);
    }), url(3));
    await page.waitForTimeout(500);
    expect(await page.evaluate(() => window.__mailScript)).toBeUndefined();
  });
});
