const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkTapTargets } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SCHOOL_ONE = "a1b2c3d4";
const SCHOOL_TWO = "b2c3d4e5";

async function gotoTwoSchools(page) {
  await page.context().addCookies([{ name: "e2e_schools", value: "2", url: BASE_URL }]);
  await goto(page);
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(150);
}

async function childKeys(page) {
  return page.evaluate(() => state.children.map((child) => child.key));
}

async function openTab(page, index) {
  const rail = page.locator("nav.rail .rail-item");
  if (await rail.count()) {
    await rail.nth(index).click();
  } else {
    const tabs = page.locator(".tabbar .tab");
    const more = page.locator(".tabbar .tab-more");
    if (index >= (await tabs.count()) - 1 && (await more.count())) {
      await more.click();
      await page.waitForTimeout(200);
      await page.locator(".sheet .more-row").nth(index - ((await tabs.count()) - 1)).click();
    } else {
      await tabs.nth(index).click();
    }
  }
  await page.waitForTimeout(200);
}

async function openSettings(page) {
  await page.locator(".settings-entry").click();
  await page.waitForTimeout(200);
}

async function expectClean(page) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, JSON.stringify(overflow.offendingContainers)).toBe(false);
  const offenders = await checkTapTargets(page);
  expect(offenders, JSON.stringify(offenders)).toEqual([]);
}

async function todayPages(page) {
  return page.evaluate(() => {
    const screen = document.querySelector(".screen");
    const container = screen.querySelector(".overview");
    return {
      snap: container.getAttribute("data-snap"),
      panelHeight: parseFloat(getComputedStyle(screen).getPropertyValue("--panel-h")) || 0,
      panels: [...container.querySelectorAll('.panel[data-area="today"]')].map((panel) => ({
        height: panel.getBoundingClientRect().height,
        overflow: panel.scrollHeight - panel.clientHeight,
        chips: [...panel.querySelectorAll(".chipbar.overview-chips .chip")].map((chip) => chip.textContent),
        pressed: [...panel.querySelectorAll(".chipbar.overview-chips .chip")].map((chip) => chip.getAttribute("aria-pressed")),
        blocks: [...panel.querySelectorAll("[data-block]")].map((node) => node.dataset.block),
      })),
    };
  });
}

function blocksBelongTo(entries, childKey) {
  return entries.every((entry) => entry.blocks.every((key) => key.startsWith(`${childKey}:`) || key.startsWith("today:")));
}

function assertTodayFits(view) {
  expect(view.snap).toBe("on");
  expect(view.panelHeight).toBeGreaterThan(0);
  for (const entry of view.panels) {
    expect(entry.overflow, "the today page scrolls inside itself").toBeLessThanOrEqual(1);
    expect(entry.height, "the today page exceeds the measured budget").toBeLessThanOrEqual(view.panelHeight + 1);
  }
}

for (const viewport of [
  { name: "390", width: 390, height: 844 },
  { name: "1440", width: 1440, height: 900 },
]) {
  const desk = viewport.width >= 1280;

  test.describe(`two schools in one app @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("every child of both schools is loaded with its school key, ordered by first name and not by school", async ({ page }) => {
      await gotoTwoSchools(page);
      const keys = await childKeys(page);
      expect(keys).toEqual([`${SCHOOL_TWO}:child-3`, `${SCHOOL_ONE}:child-1`, `${SCHOOL_TWO}:child-1`]);
      const config = await page.evaluate(() => state.config.connections.map((entry) => entry.id));
      expect(config).toEqual([SCHOOL_ONE, SCHOOL_TWO]);
    });

    test("the overview shows one child at a time behind a chip row of first names, the school only on the shared name", async ({ page }) => {
      await gotoTwoSchools(page);
      const panel = page.locator('.panel[data-area="today"]').first();
      expect(await panel.locator(".today-child").count()).toBe(0);
      const chips = panel.locator(".chipbar.overview-chips .chip");
      await expect(chips).toHaveCount(3);
      expect(await chips.allTextContents()).toEqual(["Lena", "Mia · Riverside", "Mia · Hillview"]);
      expect(await chips.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-pressed")))).toEqual(["true", "false", "false"]);
      expect(await page.locator('.panel[data-area="today"] .chipbar.child-pills').count()).toBe(0);
      const before = await todayPages(page);
      expect(blocksBelongTo(before.panels, `${SCHOOL_TWO}:child-3`)).toBe(true);
      if (desk) {
        expect(before.snap).toBe("off");
        const overview = await page.locator(".overview").boundingBox();
        const today = await panel.boundingBox();
        expect(today.width).toBeLessThan(overview.width * 0.6);
        expect(await page.locator(".overview > .panel.panel-wide").count()).toBe(0);
      } else {
        assertTodayFits(before);
      }
      await chips.nth(2).click();
      await page.waitForTimeout(300);
      expect(await page.evaluate(() => state.overviewChildId)).toBe(`${SCHOOL_TWO}:child-1`);
      const after = await todayPages(page);
      expect(after.panels[0].pressed).toEqual(["false", "false", "true"]);
      expect(blocksBelongTo(after.panels, `${SCHOOL_TWO}:child-1`)).toBe(true);
      if (!desk) assertTodayFits(after);
      await page.locator('.panel[data-area="today"] .panel-link, .panel[data-area="today"] .chapter-head').first().click();
      await page.waitForTimeout(250);
      expect(await page.evaluate(() => [state.view, state.childId])).toEqual(["timetable", `${SCHOOL_TWO}:child-1`]);
      await openTab(page, 0);
      expect(await page.locator('.panel[data-area="today"] .chipbar.overview-chips .chip[aria-pressed="true"]').first().textContent()).toBe("Mia · Hillview");
      const letters = page.locator('.panel[data-area="letters"] .row-tags .tag.school');
      expect(await letters.count()).toBeGreaterThan(0);
      expect(await page.locator('.panel[data-area="letters"] .row').first().locator(".row-tags .tag").first().textContent()).toBe("Riverside");
      await expectClean(page);
    });

    test("the timetable carries one-line pills, or one column per child at desk, with the school only on the shared name", async ({ page }) => {
      const requested = [];
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (url.pathname.endsWith("/api/timetable")) requested.push(url.searchParams.get("child"));
      });
      await gotoTwoSchools(page);
      await openTab(page, 1);
      if (desk) {
        await expect(page.locator(".tt-multi .tt-child")).toHaveCount(3);
        expect(await page.locator(".tt-child-head .who").allTextContents()).toEqual(["Lena", "Mia", "Mia"]);
        expect(await page.locator(".tt-child-head .cls").allTextContents()).toEqual(["5a", "3b · Riverside", "7c · Hillview"]);
        expect(await page.locator(".tt-child-head .school").count()).toBe(0);
        expect(await page.locator(".tt-multi.scrolls").count()).toBe(0);
        await page.waitForTimeout(300);
      } else {
        const pills = page.locator(".chipbar.child-pills .chip");
        await expect(pills).toHaveCount(3);
        expect(await page.locator(".chipbar.child-pills .chip-child").count()).toBe(0);
        expect(await pills.allTextContents()).toEqual(["Lena · 5a", "Mia · 3b · Riverside", "Mia · 7c · Hillview"]);
        expect(await page.locator(".child-switch").count()).toBe(0);
        await pills.nth(1).click();
        await page.waitForTimeout(300);
        expect(await pills.nth(1).getAttribute("aria-pressed")).toBe("true");
      }
      expect(requested).toContain(`${SCHOOL_TWO}:child-3`);
      expect(requested).toContain(`${SCHOOL_ONE}:child-1`);
      expect(requested.every((value) => value && value.includes(":"))).toBe(true);
      await expectClean(page);
    });

    test("the absence view follows the pill to the other school and reloads its overview", async ({ page }) => {
      const requested = [];
      page.on("request", (request) => {
        const url = new URL(request.url());
        if (url.pathname.endsWith("/api/absences")) requested.push(url.searchParams.get("connection"));
      });
      await gotoTwoSchools(page);
      await openTab(page, 2);
      const pills = page.locator(".chipbar.child-pills .chip");
      await expect(pills).toHaveCount(3);
      await pills.nth(1).click();
      await page.waitForTimeout(400);
      expect(requested).toContain(SCHOOL_TWO);
      expect(requested).toContain(SCHOOL_ONE);
      expect(await page.evaluate(() => state.absence && state.absence.connectionId)).toBe(SCHOOL_ONE);
    });

    test("the post feed carries school chips and a filter row that narrows to one school", async ({ page }) => {
      await gotoTwoSchools(page);
      await openTab(page, 3);
      const filter = page.locator(".chipbar.school-filter .chip");
      await expect(filter).toHaveCount(3);
      expect(await filter.allTextContents()).toEqual([await page.evaluate(() => t("schools.filter.all")), "Riverside", "Hillview"]);
      const firstTags = page.locator(".rows .row").first().locator(".row-tags .tag");
      expect(await firstTags.first().textContent()).toBe("Riverside");
      await filter.nth(2).click();
      await page.waitForTimeout(200);
      await expect(page.locator(".rows .row")).toHaveCount(1);
      expect(await page.locator(".rows .row .row-tags .tag").first().textContent()).toBe("Hillview");
      await page.locator(".segment [role=tab]").nth(1).click();
      await page.waitForTimeout(200);
      await expect(page.locator(".chipbar.school-filter .chip")).toHaveCount(3);
      const postTags = await page.locator(".rows .row").first().locator(".row-tags .tag").allTextContents();
      expect(postTags[0]).toBe("Hillview");
      expect(postTags.length).toBeGreaterThan(1);
      await expectClean(page);
    });

    test("the chat list carries the school chip and the filter row", async ({ page }) => {
      await gotoTwoSchools(page);
      await openTab(page, 4);
      await expect(page.locator(".chipbar.school-filter .chip")).toHaveCount(3);
      expect(await page.locator(".rows .row .row-tags .tag.school").count()).toBeGreaterThan(1);
      await page.locator(".chipbar.school-filter .chip").nth(2).click();
      await page.waitForTimeout(200);
      await expect(page.locator(".rows .row")).toHaveCount(1);
    });

    test("the settings lead with the schools block, one row per school, and open the school page", async ({ page }) => {
      await gotoTwoSchools(page);
      await openSettings(page);
      const heads = await page.locator(".screen .settings-group .section-head .overline").allTextContents();
      expect(heads).toEqual(await page.evaluate(() => [
        t("settings.section.display"),
        t("settings.section.notifications"),
        t("schools.section"),
        t("settings.section.modules"),
        t("settings.section.account"),
        t("settings.section.help"),
      ]));
      await expect(page.locator(".screen .modules-block .module-row .switch")).toHaveCount(6);
      const rows = page.locator(".schools-block .school-row");
      await expect(rows).toHaveCount(2);
      expect(await rows.locator(".lbl").allTextContents()).toEqual(["Riverside Primary", "Hillview School"]);
      expect(await page.locator(".schools-block .btn").count()).toBe(0);
      await expect(page.locator(".screen .setting-row.add-school")).toHaveCount(1);
      await expectClean(page);
      await rows.nth(1).click();
      await page.waitForTimeout(250);
      if (desk) {
        await expect(page.locator(".pane-detail .school-page")).toBeVisible();
        expect(await page.locator(".pane-detail .pane-title").textContent()).toBe("Hillview School");
        expect(await rows.nth(1).evaluate((node) => node.classList.contains("open"))).toBe(true);
      } else {
        expect(await page.locator(".header-title").textContent()).toBe("Hillview School");
        await expect(page.locator(".header-back")).toBeVisible();
      }
      const labels = await page.locator(".school-page .setting-row .lbl").allTextContents();
      expect(labels).toContain(await page.evaluate(() => t("schools.shortName")));
      expect(labels).toContain(await page.evaluate(() => t("schools.disconnect")));
      await expect(page.locator(".school-page .module-row")).toHaveCount(0);
      await expect(page.locator(".school-page .modules-offered")).toBeVisible();
      await expectClean(page);
      await page.locator(".school-page .setting-row").filter({ hasText: await page.evaluate(() => t("schools.shortName")) }).click();
      await page.waitForTimeout(200);
      const input = page.locator(".sheet input.inp");
      await expect(input).toHaveValue("Hillview");
    });

    test("adding another school runs the wizard as a page and cancel returns to the settings", async ({ page }) => {
      await gotoTwoSchools(page);
      await openSettings(page);
      await page.locator(".screen .setting-row.add-school").click();
      await page.waitForTimeout(500);
      await expect(page.locator(".wz, .sw")).toBeVisible();
      const cancel = page.locator(".wz-nav.reset");
      expect(await cancel.textContent()).toBe(await page.evaluate(() => t("common.cancel")));
      await cancel.click();
      await page.waitForSelector(".screen", { state: "attached", timeout: 15000 });
      await page.waitForTimeout(400);
      await expect(page.locator(".schools-block .school-row")).toHaveCount(2);
    });
  });
}

test.describe("two schools in Arabic @ 390", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "ar" });

  test("pills, post filter, overview and settings mirror without horizontal overflow", async ({ page }) => {
    await gotoTwoSchools(page);
    expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe("rtl");
    await expect(page.locator('.panel[data-area="today"] .chipbar.overview-chips .chip').first()).toBeVisible();
    expect(await page.locator('.panel[data-area="today"]').first().locator(".chipbar.overview-chips .chip").count()).toBe(3);
    assertTodayFits(await todayPages(page));
    await expectClean(page);
    await openTab(page, 1);
    await expect(page.locator(".chipbar.child-pills .chip")).toHaveCount(3);
    await expectClean(page);
    await openTab(page, 3);
    await expect(page.locator(".chipbar.school-filter .chip")).toHaveCount(3);
    await expectClean(page);
    await openSettings(page);
    await expect(page.locator(".schools-block .school-row")).toHaveCount(2);
    const dot = await page.locator(".schools-block .school-row .school-dot").first().boundingBox();
    const chevron = await page.locator(".schools-block .school-row .chev").first().boundingBox();
    expect(dot.x).toBeGreaterThan(chevron.x);
    await expectClean(page);
    await page.locator(".schools-block .school-row").nth(0).click();
    await page.waitForTimeout(250);
    await expect(page.locator(".school-page")).toBeVisible();
    await expectClean(page);
  });
});
