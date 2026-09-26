const { test, expect } = require("@playwright/test");
const { goto, openArea } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SOURCE_COOKIE = "e2e_timetable_source";
const WEEK_LESSONS = 6;
const MOVED_WEEK_LESSONS = 41;
const PARALLEL_GROUPS = 2;
const COURSES_PER_GROUP = 3;

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

test("a school app that refuses the timetable still shows the week of the time-table module with every change marked", async ({ page }) => {
  await openTimetable(page, "school-app-refused");
  const parallelGroups = page.locator(".tt .tt-cell.courses");
  await expect(parallelGroups).toHaveCount(PARALLEL_GROUPS);
  await expect(parallelGroups.filter({ hasText: String(COURSES_PER_GROUP) })).toHaveCount(PARALLEL_GROUPS);
  await expect(page.locator(".tt .tt-cell[data-subject]")).toHaveCount(MOVED_WEEK_LESSONS - PARALLEL_GROUPS * COURSES_PER_GROUP);
  await expect(page.locator(".tt .tt-cell.courses.subbed")).toHaveCount(2);
  await expect(page.locator(".tt .tt-cell.out")).toHaveCount(2);
  await expect(page.locator(".tt .tt-cell.subbed:not(.courses)")).toHaveCount(3);
  await expect(page.locator(".tt .tt-cell.subbed[data-subject='Bio']")).toHaveCount(1);
  await expect(page.getByText(await message(page, "timetable.empty.title"), { exact: true })).toHaveCount(0);
  await expect(page.locator(".tt")).not.toContainText("null");
});

test("the moved lessons of the week show at both places, and the note of the school at its lesson", async ({ page }) => {
  await openTimetable(page, "school-app-refused");
  await expect(page.locator(".tt .tt-cell.moved")).toHaveCount(4);
  await expect(page.locator(".tt .tt-cell.out.moved[data-subject='L'] .room")).toHaveText("auf Do 5");
  await expect(page.locator(".tt .tt-cell.subbed.moved[data-subject='L'] .room")).toHaveText("von Di 6");
  await expect(page.locator(".tt .tt-cell.out.moved[data-subject='M'] .room")).toHaveText("auf Mo 4");
  await expect(page.locator(".tt .tt-cell.subbed.moved[data-subject='M'] .room")).toHaveText("von Fr 6");
  await expect(page.locator(".tt .tt-cell .note-flag")).toHaveCount(1);
  await expect(page.locator(".legend")).toContainText(await message(page, "timetable.change.moved"));
  await page.locator(".tt .tt-cell.out.moved[data-subject='L']").click();
  const sheet = page.locator(".sheet");
  await expect(sheet.locator(".banner.moved")).toContainText("Donnerstag");
  await expect(sheet.locator(".change-note")).toHaveText("Material mitbringen");
});

test("a substitute whose teacher the school hides says so in the lesson sheet", async ({ page }) => {
  await openTimetable(page, "school-app-refused");
  await page.locator(".tt .tt-cell.subbed[data-subject='Bio']").click();
  const sheet = page.locator(".sheet");
  await expect(sheet.locator(".banner")).toContainText(await message(page, "timetable.banner.hiddenTeacher"));
  await expect(sheet).toContainText(await message(page, "timetable.teacher.hidden"));
});
