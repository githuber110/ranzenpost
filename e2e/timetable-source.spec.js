const { test, expect } = require("@playwright/test");
const { goto, openArea } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SOURCE_COOKIE = "e2e_timetable_source";
const WEEK_LESSONS = 6;

async function openTimetable(page, mode) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.context().clearCookies();
  await page.context().addCookies([{ name: SOURCE_COOKIE, value: mode, url: BASE_URL }]);
  await goto(page);
  await openArea(page, "timetable");
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
}

async function message(page, key) {
  return page.evaluate((name) => window.t(name), key);
}

test("a school that keeps its plan in the older time-table module shows its lessons", async ({ page }) => {
  await openTimetable(page, "time-table");
  const lessons = page.locator(".tt .tt-cell[data-subject]");
  await expect(lessons).toHaveCount(WEEK_LESSONS);
  await expect(page.locator(".tt .tt-cell[data-subject='KU']")).toHaveCount(1);
  await expect(page.getByText(await message(page, "timetable.empty.title"), { exact: true })).toHaveCount(0);
});

test("a week without lessons in either source shows the short hint", async ({ page }) => {
  await openTimetable(page, "empty");
  const hint = page.locator(".empty").filter({ hasText: await message(page, "timetable.empty.title") });
  await expect(hint).toBeVisible();
  await expect(hint).toContainText(await message(page, "timetable.empty.text"));
  await expect(page.locator(".tt")).toHaveCount(0);
});

test("room changes and cancellations of the older time-table module show in the week", async ({ page }) => {
  await openTimetable(page, "time-table-changes");
  await expect(page.locator(".tt .tt-cell[data-subject]")).toHaveCount(WEEK_LESSONS);
  await expect(page.locator(".tt .tt-cell.subbed[data-subject='D']")).toHaveCount(1);
  await expect(page.locator(".tt .tt-cell.out[data-subject='KU']")).toHaveCount(1);
  await page.locator(".tt .tt-cell.subbed[data-subject='D']").click();
  await expect(page.locator(".sheet")).toContainText("R305");
});
