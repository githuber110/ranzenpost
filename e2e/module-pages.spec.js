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
    { name: "e2e_account", value: `pages:${process.pid}-${run}`, url: BASE_URL },
  ]);
  if (theme) {
    await page.addInitScript((value) => {
      try {
        window.localStorage.setItem("theme", value);
      } catch (error) {}
    }, theme);
  }
  await goto(page);
  await openArea(page, "modulepages");
  await expect(page.locator("button.conference-row").first()).toBeVisible();
}

async function expectFits(page, label) {
  const [overflow, offenders] = await Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

function noWrites(page) {
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/api/module-pages")) writes.push(request.url());
  });
  return writes;
}

test.describe("the other modules of a school", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const theme of ["light", "dark"]) {
    test(`each module fits the phone in ${theme}`, async ({ page }) => {
      const writes = noWrites(page);
      await start(page, theme);
      await expectFits(page, "list");
      await shot(page, `modules-${theme}-list`);
      const names = ["Drucken", "Kurswahlen", "Videokonferenzen", "Umfragen", "To-do"];
      for (const name of names) {
        await page.locator("button.conference-row", { hasText: name }).click();
        await expect(page.locator(".conference-text.muted").last()).toBeVisible();
        await expectFits(page, name);
        await shot(page, `modules-${theme}-${name}`);
        await page.locator(".header-back").click();
      }
      expect(writes).toEqual([]);
    });
  }

  test("a course selection opens from its list and offers nothing to send", async ({ page }) => {
    await start(page);
    await page.locator("button.conference-row", { hasText: "Kurswahlen" }).click();
    await page.locator("button.conference-row", { hasText: "Wahlpflicht 2027" }).click();
    await expect(page.getByText("Bitte bis 30.11.2026 wählen.")).toBeVisible();
    await expect(page.locator(".conference-page form, .conference-page select, .conference-page input")).toHaveCount(0);
  });

  test("a video room shows who is there and has no way to join", async ({ page }) => {
    await start(page);
    await page.locator("button.conference-row", { hasText: "Videokonferenzen" }).click();
    await expect(page.getByText("Klassenraum 4a")).toBeVisible();
    await expect(page.getByText("Beitreten")).toHaveCount(0);
  });
});
