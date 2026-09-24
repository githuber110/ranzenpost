const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, checkTapTargets } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "1024", width: 1024, height: 768 },
];

const VIEW_AREAS = ["timetable", "absence", "post", "messenger", "conferences"];

async function gotoOutage(page) {
  await page.context().addCookies([{ name: "e2e_outage", value: "1", url: BASE_URL }]);
  await goto(page);
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(150);
}

async function openTab(page, index) {
  const rail = page.locator("nav.rail .rail-item");
  if (await rail.count()) await rail.nth(index).click();
  else await page.locator(".tabbar .tab").nth(index).click();
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(150);
}

async function expectCalmOutage(page, label) {
  const banner = page.locator(".outage-banner");
  await expect(banner, label).toBeVisible();
  await expect(banner, label).toContainText(await page.evaluate(() => t("outage.banner.text")));
  await expect(banner, label).toContainText(await page.evaluate(() => t("outage.banner.lastUpdate", { time: "" }).trim().split(" ")[0]));
  await expect(banner.locator(".btn"), label).toHaveText(await page.evaluate(() => t("outage.banner.retry")));
  const reconnectTitle = await page.evaluate(() => t("account.reconnect.title"));
  await expect(page.locator("#app"), label).not.toContainText(reconnectTitle);
  await expect(page.locator("input[type=password]"), label).toHaveCount(0);
  await expect(page.locator(".toast"), label).toHaveCount(0);
  const alertTitles = await page.evaluate(() =>
    ["timetable", "letters", "pinboard", "absence", "messenger", "conferences"].map((view) => t(`${view}.error.title`))
  );
  for (const title of alertTitles) await expect(page.locator("#app"), label).not.toContainText(title);
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const offenders = await checkTapTargets(page);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

for (const viewport of VIEWPORTS) {
  test(`an IServ outage shows the calm banner on every view and never the reconnect page at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await gotoOutage(page);
    expect(await page.evaluate(() => state.schoolStatus)).toEqual({ a1b2c3d4: "outage" });
    await expectCalmOutage(page, `${viewport.name} overview`);
    for (const view of VIEW_AREAS) {
      await openArea(page, view);
      await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
      await page.waitForTimeout(150);
      await expectCalmOutage(page, `${viewport.name} area ${view}`);
    }
    await openTab(page, 0);
    await expectCalmOutage(page, `${viewport.name} overview again`);
  });
}
