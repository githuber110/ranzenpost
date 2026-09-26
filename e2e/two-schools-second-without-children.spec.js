const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, checkTapTargets } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SCHOOL_ONE = "a1b2c3d4";
const SCHOOL_TWO = "b2c3d4e5";
const PROGRESS_RAIL = "sw-dot";

async function gotoSchools(page) {
  await page.context().addCookies([{ name: "e2e_schools", value: "2-empty", url: BASE_URL }]);
  await goto(page);
  await page.waitForTimeout(150);
}

function watch(page, fragment) {
  const seen = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith(fragment)) seen.push({ connection: url.searchParams.get("connection"), body: request.postData() });
  });
  return seen;
}

async function expectClean(page) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
  const offenders = (await checkTapTargets(page)).filter((offender) => !String(offender.className).includes(PROGRESS_RAIL));
  expect(offenders, JSON.stringify(offenders)).toEqual([]);
}

test.describe("two schools, the second lists no profiles for this account", () => {
  test("only the first school lists children and the school row names the refused list", async ({ page }) => {
    await gotoSchools(page);
    const keys = await page.evaluate(() => state.children.map((child) => child.key));
    expect(keys.length).toBeGreaterThan(0);
    expect(keys.every((key) => key.startsWith(`${SCHOOL_ONE}:`))).toBe(true);
    await page.locator(".settings-entry").click();
    await page.waitForTimeout(300);
    const rows = page.locator(".schools-block .school-row");
    await expect(rows).toHaveCount(2);
    const refused = await page.evaluate(() => t("schools.children.refused"));
    await expect(rows.nth(1).locator(".val")).toHaveText(refused);
    await expectClean(page);
  });

  test("the chat list carries the room of the second school", async ({ page }) => {
    await gotoSchools(page);
    await openArea(page, "messenger");
    await page.waitForSelector(".rows .row", { timeout: 8000 });
    const second = page.locator(".rows .row", { hasText: "Klassenleitung 5a" });
    await expect(second).toHaveCount(1);
    await expect(second.locator(".tag.school")).toHaveText("Hillview");
  });

  test("writing to a teacher asks for the school and searches the chosen second school", async ({ page }) => {
    const searches = watch(page, "/api/messenger/teachers");
    const children = watch(page, "/api/messenger/room/teacher/children");
    await gotoSchools(page);
    await openArea(page, "messenger");
    await page.waitForSelector(".rows .row", { timeout: 8000 });
    await page.locator(".list-actions .btn").click();
    const options = page.locator(".sheet .school-choice .opt");
    await expect(options).toHaveCount(2);
    await expect(options.nth(1).locator("b")).toHaveText("Hillview School");
    await expectClean(page);
    await options.nth(1).click();
    await page.waitForSelector(".sw-content");
    await page.locator(".sw-body .search-input").fill("Zweig");
    await page.waitForSelector(".sw-results .opt", { timeout: 8000 });
    await expect(page.locator(".sw-results .opt").first()).toContainText("Fr. Zweig");
    expect(searches.length).toBeGreaterThan(0);
    expect(searches.every((entry) => entry.connection === SCHOOL_TWO)).toBe(true);
    expect(children.map((entry) => entry.connection)).toEqual([SCHOOL_TWO]);
    await page.locator(".sw-results .opt").first().click();
    await page.locator(".sw-next").dispatchEvent("click");
    await page.waitForTimeout(80);
    await page.locator(".sw-next").dispatchEvent("click");
    await page.waitForTimeout(80);
    await expect(page.locator(".create-name")).toBeVisible();
    await expect(page.locator(".sw-review")).toContainText("Hillview School");
    await expectClean(page);
  });

  test("a teacher search without a school is refused instead of reaching the first school", async ({ page }) => {
    await gotoSchools(page);
    const body = await page.evaluate(async () => (await fetch("api/messenger/teachers?query=Zwe")).json());
    expect(body.message_key).toBe("api.school.required");
  });

  test("the letters of the second school are listed with their school", async ({ page }) => {
    await gotoSchools(page);
    await openArea(page, "post");
    await page.waitForSelector(".rows .row", { timeout: 8000 });
    const tags = await page.locator(".rows .row .row-tags .tag.school").allTextContents();
    expect(tags).toContain("Hillview");
    expect(tags).toContain("Riverside");
  });

  test("the absence entry follows the listed child and never asks the second school without one", async ({ page }) => {
    const requested = watch(page, "/api/absences");
    await gotoSchools(page);
    await openArea(page, "absence");
    await page.waitForTimeout(400);
    expect(requested.length).toBeGreaterThan(0);
    expect(requested.every((entry) => entry.connection === SCHOOL_ONE)).toBe(true);
    await expect(page.locator(".screen .empty .btn")).toHaveCount(0);
    expect(await page.evaluate(() => state.absence && state.absence.connectionId)).toBe(SCHOOL_ONE);
    await expectClean(page);
  });
});
