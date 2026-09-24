const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  checkTapTargets,
  checkSheetContainment,
  waitForSheetSettled,
} = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;

const WIDE_MIN = 900;
const DESK_MIN = 1280;

function modeFor(width) {
  if (width >= DESK_MIN) return "desk";
  if (width >= WIDE_MIN) return "wide";
  return "phone";
}

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function expectClean(page, label) {
  const overflow = await checkHorizontalOverflow(page);
  expect(overflow.overflow, `${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth} ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  const outside = await checkElementsWithinViewport(page);
  expect(outside, `${label}: ${JSON.stringify(outside)}`).toEqual([]);
  const small = await checkTapTargets(page);
  expect(small, `${label}: ${JSON.stringify(small)}`).toEqual([]);
}

const AREA_VIEWS = ["overview", "timetable", "absence", "post", "messenger", "conferences"];

async function openArea(page, index) {
  const view = AREA_VIEWS[index];
  const direct = page.locator(`nav.rail .rail-item[data-view="${view}"], .tabbar .tab[data-view="${view}"]`);
  if (await direct.count()) {
    await direct.first().click();
  } else {
    await page.locator(".tabbar .tab-more").click();
    await page.waitForSelector(".sheet .more-row", { timeout: 5000 });
    await page.locator(`.sheet .more-row[data-area="${view}"]`).click();
  }
  await settled(page);
}

async function shellState(page) {
  return page.evaluate(() => {
    const app = document.getElementById("app");
    const rail = document.querySelector("nav.rail");
    const pane = document.querySelector(".pane-detail");
    const tabbar = document.querySelector(".tabbar");
    const box = (el) => (el ? el.getBoundingClientRect() : null);
    return {
      shell: app.getAttribute("data-shell"),
      appWidth: app.getBoundingClientRect().width,
      appMaxWidth: getComputedStyle(app).maxWidth,
      rail: box(rail),
      railItems: rail ? rail.querySelectorAll(".rail-item").length : 0,
      pane: box(pane),
      tabbar: box(tabbar),
      viewport: window.innerWidth,
    };
  });
}

test.describe("layout: the shell follows the viewport width", () => {
  test("tab bar below 900px, rail from 900px, detail pane from 1280px on a list view", async ({ page }) => {
    const width = page.viewportSize().width;
    const mode = modeFor(width);
    await goto(page);
    await settled(page);
    await openArea(page, 3);
    const shell = await shellState(page);
    if (mode === "phone") {
      expect(shell.shell).toBe("tabs");
      expect(shell.tabbar).not.toBeNull();
      expect(shell.rail).toBeNull();
      expect(shell.pane).toBeNull();
      expect(shell.appWidth).toBeLessThanOrEqual(480);
    } else {
      expect(shell.shell).toBe(mode === "desk" ? "rail-pane" : "rail");
      expect(shell.tabbar).toBeNull();
      expect(shell.rail).not.toBeNull();
      expect(shell.railItems).toBe(6);
      expect(shell.rail.height).toBeGreaterThan(page.viewportSize().height - 2);
      expect(shell.appWidth).toBe(width);
      if (mode === "desk") {
        expect(shell.pane).not.toBeNull();
        expect(Math.round(shell.pane.width)).toBe(420);
        expect(Math.round(shell.pane.right)).toBe(width);
      } else {
        expect(shell.pane).toBeNull();
      }
    }
    await expectClean(page, `${mode} post`);
  });

  test("the overview and the timetable never carry a pane, and the overview stops paging above the phone width", async ({ page }) => {
    const mode = modeFor(page.viewportSize().width);
    await goto(page);
    await settled(page);
    const overview = await page.evaluate(() => {
      const screen = document.querySelector(".screen");
      const container = document.querySelector(".overview");
      return {
        pane: !!document.querySelector(".pane-detail"),
        snap: screen.getAttribute("data-snap"),
        containerSnap: container ? container.getAttribute("data-snap") : null,
        arrows: document.querySelectorAll(".panel-arrow").length,
        columns: container ? getComputedStyle(container).gridTemplateColumns.split(" ").filter(Boolean).length : 0,
        panels: document.querySelectorAll(".overview .panel").length,
      };
    });
    expect(overview.pane).toBe(false);
    if (mode !== "phone") {
      expect(overview.snap).not.toBe("on");
      expect(overview.containerSnap).toBe("off");
      expect(overview.arrows).toBe(0);
      expect(overview.columns).toBe(mode === "desk" ? 4 : 2);
      expect(overview.panels).toBeGreaterThan(1);
    }
    await expectClean(page, `${mode} overview`);
    await openArea(page, 1);
    expect(await page.locator(".pane-detail").count()).toBe(0);
    await expectClean(page, `${mode} timetable`);
  });
});

test.describe("layout: a letter", () => {
  test("opens in the pane on a desk and as a page elsewhere, and the way back is the same function", async ({ page }) => {
    const mode = modeFor(page.viewportSize().width);
    await goto(page);
    await settled(page);
    await openArea(page, 3);
    const row = page.locator(".screen .rows .row").first();
    const title = (await row.locator(".row-title").first().textContent()).trim();
    await row.click();
    await settled(page);
    if (mode === "desk") {
      await expect(page.locator(".pane-detail .pane-title")).toHaveText(title);
      await expect(page.locator(".pane-detail .pane-body .body-html")).toBeVisible();
      await expect(page.locator(".screen .rows .row").first()).toBeVisible();
      expect(await page.locator(".screen .header-back").count()).toBe(0);
      await expectClean(page, "desk letter pane");
      await page.locator(".pane-detail .pane-close").click();
      await settled(page);
      await expect(page.locator(".pane-detail .pane-empty")).toBeVisible();
    } else {
      await expect(page.locator(".screen .header-back")).toBeVisible();
      await expect(page.locator(".screen .body-html")).toBeVisible();
      expect(await page.locator(".pane-detail").count()).toBe(0);
      await expectClean(page, `${mode} letter page`);
      await page.locator(".screen .header-back").click();
      await settled(page);
    }
    await expect(page.locator(".screen .rows .row").first()).toBeVisible();
    expect(await page.locator(".screen .body-html").count()).toBe(0);
  });
});

test.describe("layout: a pinboard post", () => {
  test("is a centred dialog from the wide width and lands in the pane on a desk", async ({ page }) => {
    const { width, height } = page.viewportSize();
    const mode = modeFor(width);
    await goto(page);
    await settled(page);
    await openArea(page, 3);
    await page.locator(".list-head .segment button").nth(1).click();
    await settled(page);
    await page.locator(".screen .rows .row").first().click();
    await settled(page);
    if (mode === "desk") {
      await expect(page.locator(".pane-detail .pane-title")).toBeVisible();
      await expect(page.locator(".pane-detail .pane-foot button")).toBeVisible();
      expect(await page.locator(".scrim").count()).toBe(0);
      await expectClean(page, "desk post pane");
      return;
    }
    await waitForSheetSettled(page);
    const scrim = page.locator(".scrim");
    const sheet = await page.locator(".scrim .sheet").boundingBox();
    const containment = await checkSheetContainment(page);
    expect(containment.fitsViewport).toBe(true);
    if (mode === "wide") {
      await expect(scrim).toHaveClass(/dialog/);
      expect(sheet.width).toBeLessThanOrEqual(560);
      expect(Math.abs(sheet.x + sheet.width / 2 - width / 2)).toBeLessThanOrEqual(2);
      expect(Math.abs(sheet.y + sheet.height / 2 - height / 2)).toBeLessThanOrEqual(2);
      expect(sheet.height).toBeLessThanOrEqual(height * 0.88 + 1);
    } else {
      await expect(scrim).not.toHaveClass(/dialog/);
      expect(Math.round(sheet.y + sheet.height)).toBe(height);
    }
    await expectClean(page, `${mode} post sheet`);
  });
});

test.describe("layout: a chat room", () => {
  test("opens beside the room list on a desk and as a full chat page elsewhere", async ({ page }) => {
    const mode = modeFor(page.viewportSize().width);
    await goto(page);
    await settled(page);
    await openArea(page, 4);
    await page.locator(".screen .rows .row").first().click();
    await settled(page);
    if (mode === "desk") {
      await expect(page.locator(".pane-detail .pane-body .chat .composer-input")).toBeVisible();
      await expect(page.locator(".screen .rows .row").first()).toBeVisible();
      expect(await page.locator(".screen.chat").count()).toBe(0);
      const pane = await page.locator(".pane-detail").boundingBox();
      const composer = await page.locator(".pane-detail .composer").boundingBox();
      expect(composer.y + composer.height).toBeLessThanOrEqual(pane.y + pane.height + 1);
      await expectClean(page, "desk chat pane");
      await page.locator(".pane-detail .pane-close").click();
      await settled(page);
      await expect(page.locator(".pane-detail .pane-empty")).toBeVisible();
    } else {
      await expect(page.locator(".screen.chat .composer-input")).toBeVisible();
      await expect(page.locator(".screen .header-back")).toBeVisible();
      expect(await page.locator(".pane-detail").count()).toBe(0);
      expect(await page.locator("nav.rail").count()).toBe(mode === "phone" ? 0 : 1);
      await expectClean(page, `${mode} chat page`);
    }
  });
});

test.describe("layout: two children in the timetable", () => {
  test("stand side by side on a desk and behind the child switch elsewhere", async ({ page }) => {
    const mode = modeFor(page.viewportSize().width);
    await page.context().addCookies([{ name: "e2e_scenario", value: "two-children", url: BASE_URL }]);
    await goto(page);
    await settled(page);
    await openArea(page, 1);
    await page.waitForSelector(".tt", { timeout: 10000 });
    await settled(page);
    if (mode === "desk") {
      const columns = page.locator(".tt-multi .tt-child");
      await expect(columns).toHaveCount(2);
      await expect(columns.nth(0).locator(".tt")).toBeVisible();
      await expect(columns.nth(1).locator(".tt")).toBeVisible();
      const first = await columns.nth(0).boundingBox();
      const second = await columns.nth(1).boundingBox();
      const rtl = await page.evaluate(() => document.documentElement.getAttribute("dir") === "rtl");
      if (rtl) expect(second.x + second.width).toBeLessThanOrEqual(first.x + 1);
      else expect(second.x).toBeGreaterThanOrEqual(first.x + first.width - 1);
      expect(await page.locator(".child-switch").count()).toBe(0);
      await expect(columns.nth(1).locator(".tt-child-head")).toContainText("Tom");
    } else {
      expect(await page.locator(".tt-multi").count()).toBe(0);
      await expect(page.locator(".tt")).toHaveCount(1);
      await expect(page.locator(".child-switch")).toBeVisible();
    }
    await expectClean(page, `${mode} two children`);
  });
});

test.describe("layout: right to left", () => {
  test.use({ locale: "ar" });

  test("the rail sits at the inline start and the pane at the inline end", async ({ page }) => {
    const width = page.viewportSize().width;
    const mode = modeFor(width);
    await goto(page);
    await settled(page);
    expect(await page.evaluate(() => document.documentElement.getAttribute("dir"))).toBe("rtl");
    await openArea(page, 3);
    const shell = await shellState(page);
    if (mode === "phone") {
      expect(shell.rail).toBeNull();
      expect(shell.tabbar).not.toBeNull();
    } else {
      expect(Math.round(shell.rail.right)).toBe(width);
      if (mode === "desk") {
        expect(Math.round(shell.pane.left)).toBe(0);
        await page.locator(".screen .rows .row").first().click();
        await settled(page);
        await expect(page.locator(".pane-detail .pane-title")).toBeVisible();
        const close = await page.locator(".pane-detail .pane-close").boundingBox();
        const title = await page.locator(".pane-detail .pane-title").boundingBox();
        expect(close.x).toBeGreaterThan(title.x);
      }
    }
    await expectClean(page, `${mode} rtl post`);
  });
});

test.describe("layout: large system fonts", () => {
  test("nothing is cut off with a 24px root font", async ({ page }) => {
    const mode = modeFor(page.viewportSize().width);
    test.skip(mode === "phone", "the phone layout is guarded by the responsive-guard specs");
    await goto(page);
    await settled(page);
    await page.addStyleTag({ content: "html { font-size: 24px; }" });
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await page.waitForTimeout(250);
    await expectClean(page, `${mode} big font overview`);
    for (const index of [1, 3, 4]) {
      await openArea(page, index);
      await expectClean(page, `${mode} big font area ${index}`);
    }
    if (mode !== "phone") {
      const clipped = await page.evaluate(() => {
        const rail = document.querySelector("nav.rail").getBoundingClientRect();
        return [...document.querySelectorAll(".rail-label")].filter((label) => {
          const box = label.getBoundingClientRect();
          return box.left < rail.left - 1 || box.right > rail.right + 1 || label.scrollWidth > label.clientWidth + 1;
        }).map((label) => label.textContent);
      });
      expect(clipped).toEqual([]);
    }
  });
});

test.describe("layout: a phone viewport inside every project", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("keeps the tab bar, the 480px shell cap and no rail", async ({ page }) => {
    await goto(page);
    await settled(page);
    const shell = await shellState(page);
    expect(shell.shell).toBe("tabs");
    expect(shell.tabbar).not.toBeNull();
    expect(shell.rail).toBeNull();
    expect(shell.pane).toBeNull();
    expect(shell.appMaxWidth).toBe("480px");
    expect(await page.locator(".tabbar .tab").count()).toBe(5);
    await openArea(page, 3);
    await page.locator(".screen .rows .row").first().click();
    await settled(page);
    await expect(page.locator(".screen .header-back")).toBeVisible();
    expect(await page.locator(".scrim.dialog").count()).toBe(0);
  });
});

for (const width of [899, 900, 1279, 1280]) {
  test.describe(`layout: the breakpoint edge at ${width}px`, () => {
    test.use({ viewport: { width, height: 800 } });

    test("lands on the expected shell", async ({ page }) => {
      const mode = modeFor(width);
      await goto(page);
      await settled(page);
      await openArea(page, 3);
      const shell = await shellState(page);
      expect(shell.shell).toBe(mode === "phone" ? "tabs" : mode === "wide" ? "rail" : "rail-pane");
      expect(shell.rail === null).toBe(mode === "phone");
      expect(shell.pane === null).toBe(mode !== "desk");
      await expectClean(page, `${width}px post`);
    });
  });
}
