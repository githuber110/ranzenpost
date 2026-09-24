const { test, expect } = require("@playwright/test");
const {
  goto,
  waitForSheetSettled,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkSheetContainment,
} = require("./helpers");

test.describe.configure({ mode: "serial" });

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const CHILD = "a1b2c3d4:child-1";
const TIMETABLE_TAB = 1;
const OVERVIEW_TAB = 0;
const CHOSEN = ["E1|CCC", "REV|III", "KU|LLL"];

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(120);
}

async function text(page, key, vars) {
  return page.evaluate(([name, values]) => window.t(name, values || {}), [key, vars || null]);
}

async function useCourses(page) {
  await page.context().addCookies([{ name: "e2e_courses", value: "1", url: BASE_URL }]);
  const reset = await page.request.post("/api/timetable/courses", { data: { child: CHILD, chosen: null } });
  expect(reset.ok()).toBe(true);
}

async function openTab(page, index) {
  const rail = page.locator("nav.rail .rail-item");
  if (await rail.count()) await rail.nth(index).click();
  else await page.locator(".tabbar .tab").nth(index).click();
  await settled(page);
}

function isWeekday() {
  const day = new Date().getDay();
  return day >= 1 && day <= 5;
}

function sixCourses(page) {
  return page.locator(".tt-cell.courses").filter({ has: page.locator(".sub", { hasText: /^\D*6\D*$|^٦$/ }) }).first();
}

async function expectFits(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(await checkElementsWithinViewport(page), label).toEqual([]);
  expect(await checkTapTargets(page), label).toEqual([]);
}

test.afterAll(async ({ request }) => {
  await request.post("/api/timetable/courses", { data: { child: CHILD, chosen: null }, headers: { Cookie: "e2e_courses=1" } });
});

test.describe("parallel courses @ 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("an unchosen plan shows courses cells, the sheet lists every course and hints at the choice", async ({ page }) => {
    await useCourses(page);
    await goto(page);
    await openTab(page, TIMETABLE_TAB);
    const cells = page.locator(".tt-cell.courses");
    await expect(cells.first()).toBeVisible();
    expect(await cells.count()).toBeGreaterThanOrEqual(2);
    await expect(page.locator(".tt-stack").first()).toBeVisible();
    await sixCourses(page).click();
    await waitForSheetSettled(page);
    await expect(page.locator(".sheet .course-row")).toHaveCount(6);
    await expect(page.locator(".sheet .courses-hint")).toContainText("Mia");
    await expect(page.locator(".sheet .courses-open")).toHaveText(await text(page, "timetable.courses.choose"));
    if (isWeekday()) {
      await page.locator(".sheet-close").click();
      await openTab(page, OVERVIEW_TAB);
      await expect(page.locator('.panel[data-area="today"] .courses-row').first()).toBeVisible();
    }
  });

  test("the first visit ticks every course, saving right away hides nothing, an empty choice asks first", async ({ page }) => {
    await useCourses(page);
    await goto(page);
    await openTab(page, TIMETABLE_TAB);
    await sixCourses(page).click();
    await waitForSheetSettled(page);
    await page.locator(".sheet .courses-open").click();
    await settled(page);
    await expect(page.locator(".course-check")).toHaveCount(11);
    await expect(page.locator(".course-pick:checked")).toHaveCount(11);
    await page.locator(".courses-save").click();
    await settled(page);
    await expect(page.locator(".tt")).toBeVisible();
    await expect(page.locator(".tt-cell.courses").first()).toBeVisible();
    await expect(page.locator(".tt-stack").first()).toBeVisible();
    const kept = await (await page.request.get(`/api/timetable?child=${encodeURIComponent(CHILD)}`)).json();
    expect(kept.courses.chosen).toBe(true);
    expect(kept.courses.hidden).toBe(0);

    await sixCourses(page).click();
    await waitForSheetSettled(page);
    await page.locator(".sheet .courses-open").click();
    await settled(page);
    await expect(page.locator(".course-pick:checked")).toHaveCount(11);
    for (const input of await page.locator(".course-pick").all()) await input.uncheck();
    await page.locator(".courses-save").click();
    await waitForSheetSettled(page);
    await expect(page.locator(".sheet .sheet-title")).toHaveText(await text(page, "courses.page.emptyTitle"));
    await page.locator(".sheet .btn-stack .btn.ghost").click();
    await expect(page.locator(".sheet")).toHaveCount(0);
    await expect(page.locator(".courses-question")).toBeVisible();
    const unchanged = await (await page.request.get(`/api/timetable?child=${encodeURIComponent(CHILD)}`)).json();
    expect(unchanged.courses.hidden).toBe(0);
    const refused = await page.request.post("/api/timetable/courses", { data: { child: CHILD, chosen: [], known: ["E1|CCC"] } });
    expect(refused.status()).toBe(400);

    await page.locator(".courses-save").click();
    await waitForSheetSettled(page);
    await page.locator(".sheet .btn-stack .btn.destructive").click();
    await settled(page);
    await expect(page.locator(".tt")).toBeVisible();
    const emptied = await (await page.request.get(`/api/timetable?child=${encodeURIComponent(CHILD)}`)).json();
    expect(emptied.courses.hidden).toBeGreaterThan(0);
    await expect(page.locator(".tt-cell.courses")).toHaveCount(0);
  });

  test("choosing courses leaves only those in the grid, the today card, the API and the settings row", async ({ page }) => {
    await useCourses(page);
    await goto(page);
    await openTab(page, TIMETABLE_TAB);
    await sixCourses(page).click();
    await waitForSheetSettled(page);
    await page.locator(".sheet .courses-open").click();
    await settled(page);
    await expect(page.locator(".courses-question")).toHaveText(await text(page, "courses.page.question", { name: "Mia" }));
    await expect(page.locator(".course-check")).toHaveCount(11);
    const search = page.locator(".courses-page .search-input");
    await search.fill("Kranich");
    await expect(page.locator(".course-check")).toHaveCount(1);
    await search.fill("");
    for (const input of await page.locator(".course-pick").all()) await input.uncheck();
    for (const key of CHOSEN) await page.locator(`.course-check[data-course="${key}"] input`).check();
    await page.locator(".courses-save").click();
    await settled(page);
    await expect(page.locator(".tt")).toBeVisible();
    await expect(page.locator(".tt-cell.courses")).toHaveCount(0);
    await expect(page.locator(".tt-stack")).toHaveCount(0);
    await expect(page.locator('.tt-cell[data-subject="E1"]').first()).toBeVisible();
    await expect(page.locator('.tt-cell[data-subject="E2"]')).toHaveCount(0);

    const data = await (await page.request.get(`/api/timetable?child=${encodeURIComponent(CHILD)}`)).json();
    const byPeriod = (period) => [...new Set(data.lessons.filter((lesson) => lesson.period === period).map((lesson) => lesson.subject_code))];
    expect(byPeriod(3)).toEqual(["E1"]);
    expect(byPeriod(4)).toEqual(["REV"]);
    expect(byPeriod(5)).toEqual(["KU"]);
    expect(data.courses.chosen).toBe(true);

    if (isWeekday()) {
      await openTab(page, OVERVIEW_TAB);
      await expect(page.locator('.panel[data-area="today"] .courses-row')).toHaveCount(0);
    }
    await page.locator(".settings-entry").first().click();
    await settled(page);
    const row = page.locator(".setting-row.courses-setting");
    await expect(row).toHaveCount(1);
    await expect(row.locator(".val")).toHaveText(await text(page, "settings.courses.chosen.other", { count: "3" }));
    await row.click();
    await settled(page);
    const checked = await page.locator(".course-pick:checked").evaluateAll((inputs) => inputs.map((input) => input.value).sort());
    expect(checked).toEqual([...CHOSEN].sort());
  });
});

for (const variant of [
  { name: "de 320", locale: "de-DE", dir: "ltr" },
  { name: "ar 320", locale: "ar", dir: "rtl" },
]) {
  test.describe(`parallel courses fit @ ${variant.name}`, () => {
    test.use({ viewport: { width: 320, height: 800 }, locale: variant.locale });

    test("grid, courses sheet and course page fit without horizontal scroll", async ({ page }) => {
      await useCourses(page);
      await goto(page);
      expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe(variant.dir);
      await openTab(page, TIMETABLE_TAB);
      await expect(page.locator(".tt-cell.courses").first()).toBeVisible();
      await expectFits(page, `${variant.name} grid`);
      await page.locator(".tt-cell.courses").first().click();
      await waitForSheetSettled(page);
      const sheet = await checkSheetContainment(page);
      expect(sheet.fitsViewport, `${variant.name} sheet`).toBe(true);
      expect(!sheet.overflows || sheet.scrollable, `${variant.name} sheet scroll`).toBe(true);
      await expectFits(page, `${variant.name} sheet`);
      await page.locator(".sheet .courses-open").click();
      await settled(page);
      await expect(page.locator(".course-check").first()).toBeVisible();
      await expectFits(page, `${variant.name} course page`);
    });
  });
}
