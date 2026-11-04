const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const SHOTS = process.env.CONFERENCE_SHOTS || "";

let run = 0;

async function start(page, theme) {
  run += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: "de", url: BASE_URL },
    { name: "e2e_conference", value: `booking-${process.pid}-${Date.now()}-${run}`, url: BASE_URL },
  ]);
  if (theme) {
    await page.addInitScript((value) => {
      try {
        window.localStorage.setItem("theme", value);
      } catch (error) {}
    }, theme);
  }
  await goto(page);
  await openArea(page, "conferences");
  await page.locator("button.conference-row", { hasText: "17.11.2026" }).click();
  await expect(page.locator(".conference-host").first()).toBeVisible();
}

async function expectFits(page, label) {
  const [overflow, offenders] = await Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

function recordPosts(page) {
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/conferences/booking")) posts.push(request.postDataJSON());
  });
  return posts;
}

async function openTeacherTime(page, teacher, time) {
  await page.locator(".conference-host", { hasText: teacher }).click();
  await page.locator(".conference-slot.is-free", { hasText: time }).click();
}

test.describe("booking a parent-teacher appointment", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const theme of ["light", "dark"]) {
    test(`the booking path fits the phone in ${theme}`, async ({ page }) => {
      await start(page, theme);
      await expectFits(page, "teachers");
      await shot(page, `booking-${theme}-teachers`);
      await page.locator(".conference-host", { hasText: "Frau Muster" }).click();
      await expect(page.locator(".conference-slot").first()).toBeVisible();
      await expectFits(page, "times");
      await shot(page, `booking-${theme}-times`);
      await page.locator(".conference-slot.is-free", { hasText: "15:20" }).click();
      await expect(page.locator(".conference-submit")).toBeVisible();
      await page.locator(".conference-choice").first().locator("input").check();
      await shot(page, `booking-${theme}-child`);
      await page.locator(".conference-submit").click();
      await page.locator(".sheet .btn-stack .btn:not(.ghost)").click();
      await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin ist gebucht.");
      await expectFits(page, "booked");
      await shot(page, `booking-${theme}-booked`);
    });
  }

  test("booking, changing and cancelling each ask first and send once", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page);
    await openTeacherTime(page, "Frau Muster", "15:20");
    await page.locator(".conference-choice").first().locator("input").check();
    await page.locator(".conference-submit").click();
    expect(posts.length).toBe(0);
    await page.locator(".sheet .btn-stack .btn:not(.ghost)").click();
    await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin ist gebucht.");
    expect(posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ action: "book", slot: "slot-2", host: "host-1", children: ["kim.muster"], confirmed: true });
    await expect(page.locator(".conference-row", { hasText: "15:20" }).first()).toContainText("Kim Muster");

    await page.locator(".conference-row-actions .btn", { hasText: "Personen ändern" }).click();
    await page.locator(".conference-choice").nth(1).locator("input").check();
    await page.locator(".conference-submit").click();
    await page.locator(".sheet .btn-stack .btn:not(.ghost)").click();
    await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin ist geändert.");
    expect(posts[1]).toMatchObject({ action: "change", children: expect.arrayContaining(["kim.muster", "lou.muster"]) });
    await expect(page.locator(".conference-row", { hasText: "15:20" }).first()).toContainText("Lou Muster");

    await page.locator(".conference-row-actions .btn", { hasText: "Absagen" }).click();
    expect(posts.length).toBe(2);
    await page.locator(".sheet .btn-stack .btn:not(.ghost)").click();
    await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin ist abgesagt.");
    expect(posts[2]).toMatchObject({ action: "cancel" });
    await expect(page.locator(".conference-row-actions")).toHaveCount(0);
  });

  test("a time another family booked cannot be chosen and nothing links to the school", async ({ page }) => {
    await start(page);
    await page.locator(".conference-host", { hasText: "Frau Muster" }).click();
    await expect(page.locator(".conference-slot", { hasText: "15:00" }).first()).toBeDisabled();
    await expect(page.locator(".conference-slot", { hasText: "15:00" }).first()).toContainText("belegt");
    const links = await page.evaluate(() => [...document.querySelectorAll("a[href]")].map((node) => node.getAttribute("href")).filter((href) => href.includes("/iserv")));
    expect(links).toEqual([]);
  });
});
