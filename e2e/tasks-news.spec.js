const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

async function open(page, lang, area, extraCookies = []) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "e2e_lang", value: lang, url: BASE_URL }, { name: "e2e_modules", value: "all", url: BASE_URL }, ...extraCookies]);
  await goto(page);
  await openArea(page, area);
  await page.waitForSelector(".school-list .list-row, .school-list .empty", { timeout: 10000 });
}

async function expectInside(page, locator, width) {
  const box = await locator.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
}

for (const width of [320, 390, 1024]) {
  for (const lang of ["de", "ar"]) {
    test.describe(`tasks and news ${width} ${lang}`, () => {
      test.use({ viewport: { width, height: 800 } });

      test("the tasks view lists open tasks first, keeps past ones collapsed and nothing leaves the screen", async ({ page }) => {
        await open(page, lang, "tasks");
        const sections = page.locator(".school-list .list-section");
        await expect(sections.first().locator(".row-title").first()).toHaveText("Reading log");
        const long = page.locator(".list-row .row-title", { hasText: "Write a report about the planned excursion" });
        await expect(long).toBeVisible();
        expect(await long.getAttribute("dir")).toBe("auto");
        const lines = await long.evaluate((node) => Math.round(node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight)));
        expect(lines).toBeGreaterThan(1);
        await expect(page.locator("details.list-past")).not.toHaveAttribute("open", "");
        await expect(page.locator("details.list-past .list-row")).toBeHidden();
        await page.locator("details.list-past > summary").click();
        await expect(page.locator("details.list-past .list-row .row-title")).toHaveText("Poem by heart");
        expect(await page.locator(".school-list [href], .school-list [target]").count()).toBe(0);
        await expectInside(page, long, width);
        await expectInside(page, page.locator("details.list-past > summary"), width);
        await page.screenshot({ path: `test-results/tasks-${width}-${lang}.png`, fullPage: true });
      });

      test("the news view lists every item with and without a date", async ({ page }) => {
        await open(page, lang, "news");
        const rows = page.locator(".school-list .list-row");
        await expect(rows).toHaveCount(2);
        await expect(rows.nth(1).locator(".row-title")).toHaveText("Sports day");
        const long = rows.first().locator(".row-title");
        await expectInside(page, long, width);
        await page.screenshot({ path: `test-results/news-${width}-${lang}.png`, fullPage: true });
      });

      test("a news item opens with its full text and its file inside the app", async ({ page }) => {
        await open(page, lang, "news");
        await page.locator(".school-list .news-row").first().click();
        const text = page.locator(".sheet .news-text p");
        await expect(text).toHaveCount(3);
        await expect(text.nth(1)).toContainText("staff meeting");
        const file = page.locator(".sheet button.row", { hasText: "opening-hours-for-the-whole-school-year.pdf" });
        await expect(file).toBeVisible();
        expect(await page.locator(".sheet [href], .sheet [target], .school-list [href], .school-list [target]").count()).toBe(0);
        await expectInside(page, text.nth(1), width);
        await expectInside(page, file, width);
        await page.screenshot({ path: `test-results/news-detail-${width}-${lang}.png`, fullPage: true });
      });

      test("a task opens with its dates inside the app", async ({ page }) => {
        await open(page, lang, "tasks");
        await page.locator(".school-list .task-row").first().click();
        await expect(page.locator(".sheet .sheet-title")).toHaveText("Reading log");
        await expect(page.locator(".sheet .row-meta")).toContainText("13.10.2026");
        expect(await page.locator(".sheet [href], .sheet [target]").count()).toBe(0);
        await expectInside(page, page.locator(".sheet .row-meta"), width);
      });

      test("a task opens with its page, files and hand-in inside the app", async ({ page }) => {
        await open(page, lang, "tasks");
        const asked = [];
        page.on("request", (request) => asked.push(request.url()));
        await page.locator(".school-list .task-row", { hasText: "Worksheet fractions" }).click();
        await expect(page.locator(".sheet .news-text p").first()).toHaveText("Solve the exercises 1 to 4 on page 12.");
        expect(asked.filter((url) => url.includes("/api/tasks/detail")).length).toBe(1);
        const files = page.locator(".sheet button.row .row-title");
        await expect(files).toHaveText(["worksheet-fractions-with-a-very-long-name-for-the-whole-class.pdf", "page-12.jpg"]);
        await expect(page.locator(".sheet .task-actions .btn")).toHaveCount(4);
        await expect(page.locator(".sheet .task-actions .btn:not(.ghost)")).toHaveCount(1);
        expect(await page.locator(".sheet [href], .sheet [target]").count()).toBe(0);
        await expectInside(page, files.first(), width);
        await expectInside(page, page.locator(".sheet .task-actions"), width);
        await page.screenshot({ path: `test-results/task-detail-${width}-${lang}.png`, fullPage: true });
      });
    });
  }
}

async function themed(page, theme) {
  await page.context().clearCookies();
  await page.context().addCookies([{ name: "e2e_lang", value: "de", url: BASE_URL }, { name: "e2e_modules", value: "all", url: BASE_URL }]);
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  await goto(page);
  expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
}

async function openTask(page, title, theme) {
  await themed(page, theme);
  await openArea(page, "tasks");
  await page.waitForSelector(".school-list .list-row", { timeout: 10000 });
  if (title === "Poem by heart") await page.locator("details.list-past > summary").click();
  await page.locator(".school-list .task-row", { hasText: title }).click();
  await page.waitForSelector(".sheet .news-text p", { timeout: 10000 });
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
}

async function handIn(page, name) {
  await page.locator(".sheet .task-act-upload").click();
  await page.locator(".sheet .task-upload-input").setInputFiles([{ name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") }]);
  await page.locator(".sheet .task-upload-next").click();
  await page.locator(".sheet .task-upload-send").click();
}

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`task detail ${theme} ${width}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });

      test("feedback and the own hand-in show in the app", async ({ page }) => {
        await openTask(page, "Vocabulary test", theme);
        await expect(page.locator(".sheet .section-head .overline")).toHaveText(["Abgabe", "Rückmeldung"]);
        await expect(page.locator(".sheet .task-facts .fact")).toHaveText(["Teacher B"]);
        await expect(page.locator(".sheet button.row .row-title")).toHaveText(["corrections.pdf"]);
        await expect(page.locator(".sheet .task-act-undo")).toBeVisible();
        expect(await page.locator(".sheet [href], .sheet [target]").count()).toBe(0);
        await page.screenshot({ path: `test-results/task-feedback-${theme}-${width}.png`, fullPage: true });
      });

      test("handing in files asks first, shows the files again and reports the result", async ({ page }) => {
        await openTask(page, "Worksheet fractions", theme);
        await page.screenshot({ path: `test-results/task-open-${theme}-${width}.png`, fullPage: true });
        await page.locator(".sheet .task-act-upload").click();
        await expect(page.locator(".sheet .task-upload-next")).toBeDisabled();
        await page.locator(".sheet .task-upload-input").setInputFiles([{ name: "essay.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") }]);
        await expect(page.locator(".sheet .row-title")).toHaveText(["essay.pdf"]);
        await page.screenshot({ path: `test-results/task-upload-${theme}-${width}.png`, fullPage: true });
        await page.locator(".sheet .task-upload-next").click();
        const sent = [];
        page.on("request", (request) => {
          if (request.url().includes("/api/tasks/act")) sent.push(request.method());
        });
        await page.locator(".sheet .task-upload-send").click();
        await expect(page.locator(".sheet .task-outcome.info")).toBeVisible();
        await expect(page.locator(".sheet button.row .row-title", { hasText: "essay.pdf" })).toBeVisible();
        expect(sent).toEqual(["POST"]);
        await page.screenshot({ path: `test-results/task-handed-in-${theme}-${width}.png`, fullPage: true });
      });

      test("a refused hand-in shows the reason of the school and an unclear one says so", async ({ page }) => {
        await openTask(page, "Worksheet fractions", theme);
        await handIn(page, "rejected.pdf");
        await expect(page.locator(".sheet .task-outcome-error")).toHaveText("The file type is not allowed.");
        await page.waitForTimeout(500);
        await page.screenshot({ path: `test-results/task-refused-${theme}-${width}.png`, fullPage: true });
        await handIn(page, "unclear.pdf");
        await expect(page.locator(".sheet .task-outcome-text > span")).toHaveText("Unklar, ob die Schule die Änderung übernommen hat. Unten steht, was die Aufgabenseite jetzt zeigt.");
      });

      test("a text is handed in after a preview", async ({ page }) => {
        await openTask(page, "Worksheet fractions", theme);
        await page.locator(".sheet .task-act-text").click();
        await page.locator(".sheet textarea").fill("Exercise 1: three quarters");
        await page.locator(".sheet .task-text-next").click();
        await expect(page.locator(".sheet .task-text-quote")).toHaveText("Exercise 1: three quarters");
        await page.screenshot({ path: `test-results/task-text-${theme}-${width}.png`, fullPage: true });
        await page.locator(".sheet .task-text-send").click();
        await expect(page.locator(".sheet .task-own-text p")).toHaveText(["Exercise 1: three quarters"]);
      });

      test("a past task shows feedback and the model solution and offers no hand-in", async ({ page }) => {
        await openTask(page, "Poem by heart", theme);
        await expect(page.locator(".sheet .section-head .overline")).toHaveText(["Abgabe", "Rückmeldung", "Musterlösung"]);
        await expect(page.locator(".sheet .task-actions")).toHaveCount(0);
        await expect(page.locator(".sheet .sheet-hint")).toHaveText("IServ bietet bei dieser Aufgabe gerade keine Abgabe an.");
      });

      test("news can be filtered by archive and category and searched", async ({ page }) => {
        await themed(page, theme);
        await openArea(page, "news");
        await page.waitForSelector(".school-list .news-row", { timeout: 10000 });
        await expect(page.locator(".news-row .row-title")).toHaveCount(2);
        await page.screenshot({ path: `test-results/news-filter-${theme}-${width}.png`, fullPage: true });
        await page.locator(".news-filter").click();
        await page.locator(".sheet").getByRole("button", { name: "Archiv", exact: true }).click();
        await expect(page.locator(".news-row .row-title")).toHaveText(["Book fair last spring"]);
        await page.locator(".news-filter").click();
        await page.locator(".sheet .news-filter-opt", { hasText: "Aktuelle News" }).click();
        await page.locator(".news-head .search-input").fill("staff meeting");
        await expect(page.locator(".news-row .row-title")).toHaveCount(1);
        await expect(page.locator(".search-hits")).toHaveText("1 Treffer");
        expect(await page.locator(".school-list [href], .school-list [target]").count()).toBe(0);
        const overflow = await checkHorizontalOverflow(page);
        expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
      });
    });
  }
}

test.describe("tasks and news on the overview and empty", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "en-US" });

  test("both chapters show on the overview and lead to their views", async ({ page }) => {
    await page.context().clearCookies();
    await page.context().addCookies([{ name: "e2e_lang", value: "en", url: BASE_URL }, { name: "e2e_modules", value: "all", url: BASE_URL }]);
    await goto(page);
    await page.evaluate(() => {
      state.config.overview_blocks = [{ key: "tasks", size: "normal" }, { key: "news", size: "normal" }];
      rerender();
    });
    await expect(page.locator('[data-block="task:a1b2c3d4:3"]')).toBeVisible();
    await expect(page.locator('[data-block="news:a1b2c3d4:general/12"]')).toBeVisible();
    await page.locator('[data-block="tasks:all"]').click();
    await expect(page.locator(".school-list .list-row").first()).toBeVisible();
  });

  test("emptied lists show the neutral empty states", async ({ page }) => {
    await open(page, "en", "tasks", [{ name: "e2e_empty", value: "tasks,news", url: BASE_URL }]);
    await expect(page.locator(".school-list .empty b")).toHaveText("No tasks");
    await openArea(page, "news");
    await expect(page.locator(".school-list .empty b")).toHaveText("No news");
  });
});
