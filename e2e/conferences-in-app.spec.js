const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const SHOTS = process.env.CONFERENCE_SHOTS || "";

let run = 0;

async function start(page, theme, prefix) {
  run += 1;
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: "de", url: BASE_URL },
    { name: "e2e_conference", value: `${prefix || ""}conf-${process.pid}-${Date.now()}-${run}`, url: BASE_URL },
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
  await page.waitForSelector(".conference-row", { timeout: 10000 });
}

async function settled(page) {
  await page.waitForSelector(".conference-page .loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

async function openTeacher(page) {
  await page.locator("button.conference-row").first().click();
  await expect(page.locator(".header-title")).toHaveText("Elternsprechtag Herbst");
  await page.locator("button.conference-row", { hasText: "Frau Muster" }).click();
  await expect(page.locator(".header-title")).toHaveText("Frau Muster");
  await settled(page);
}

async function noSchoolLinks(page) {
  const found = await page.evaluate(() => ({
    iserv: [...document.querySelectorAll("a[href]")].map((node) => node.getAttribute("href")).filter((href) => href.includes("/iserv/")),
    blank: document.querySelectorAll('[target="_blank"]').length,
  }));
  expect(found).toEqual({ iserv: [], blank: 0 });
}

async function expectFits(page, label) {
  const [overflow, offenders] = await Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function choose(page, slot, child) {
  await page.locator(".conference-choice", { hasText: slot }).locator("input").check();
  if (child) await page.locator(".conference-form select.sel").selectOption({ label: child });
}

async function sendForm(page, posts) {
  await page.locator(".conference-form .btn.conference-submit").first().click();
  const sheet = page.locator(".sheet");
  await expect(sheet).toBeVisible();
  expect(posts.length).toBe(0);
  await sheet.locator(".btn-stack .btn:not(.ghost)").click();
  await expect(page.locator(".conference-outcome")).toBeVisible();
}

function recordPosts(page) {
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/conferences/submit")) posts.push(request.postDataJSON());
  });
  return posts;
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test.describe("parent-teacher conferences inside the app", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the list and the pages carry no link to the school server", async ({ page }) => {
    await start(page);
    await noSchoolLinks(page);
    await openTeacher(page);
    await noSchoolLinks(page);
    await expectFits(page, "teacher page");
  });

  test("booking asks first, sends once and shows the page read again", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page);
    await openTeacher(page);
    await choose(page, "14:00 - 14:10", "Kim");
    await sendForm(page, posts);
    await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin wurde gebucht.");
    expect(posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ confirmed: true, values: { "booking[slot]": "101", "booking[child]": "501" } });
    await expect(page.locator(".conference-choice", { hasText: "14:00 - 14:10" }).locator("input")).toBeDisabled();
    await page.locator(".header-back").click();
    await expect(page.locator(".conference-row", { hasText: "Frau Muster" }).first()).toContainText("14:00 - 14:10");
    await noSchoolLinks(page);
  });

  test("a validation error of the school is shown on the form and nothing is booked", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page);
    await openTeacher(page);
    await choose(page, "14:00 - 14:10", "");
    await sendForm(page, posts);
    await expect(page.locator(".conference-outcome.bad")).toBeVisible();
    await expect(page.locator(".conference-form .note.bad")).toHaveCount(1);
    await expect(page.locator(".conference-form .note.bad")).toContainText("Das Formular enthält Fehler.");
    await expect(page.locator(".conference-form .field .err")).toHaveText("Bitte wählen Sie ein Kind aus.");
    await expect(page.locator(".conference-choice", { hasText: "14:00 - 14:10" }).locator("input")).toBeEnabled();
    expect(posts.length).toBe(1);
  });

  test("an unclear answer is shown as unclear and never sent again by itself", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page);
    await openTeacher(page);
    await choose(page, "14:20 - 14:30", "Kim");
    await sendForm(page, posts);
    const outcome = page.locator(".conference-outcome");
    await expect(outcome).not.toHaveClass(/good|bad/);
    await expect(outcome).toContainText("Unklar");
    await page.waitForTimeout(500);
    expect(posts.length).toBe(1);
  });

  test("a booking is cancelled with a destructive confirmation", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page);
    await openTeacher(page);
    await choose(page, "14:00 - 14:10", "Kim");
    await sendForm(page, posts);
    await page.locator(".header-back").click();
    await settled(page);
    await page.locator(".conference-row-actions .btn", { hasText: "Absagen" }).click();
    const sheet = page.locator(".sheet");
    await expect(sheet.locator(".btn.destructive")).toBeVisible();
    await sheet.locator(".btn.destructive").click();
    await expect(page.locator(".conference-outcome.good")).toContainText("Der Termin wurde abgesagt.");
    await expect(page.locator(".conference-row-actions")).toHaveCount(0);
    expect(posts.length).toBe(2);
  });
});

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`conference screens ${theme} ${width}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });

      test(`list, detail, form and outcome fit (${theme} ${width})`, async ({ page }) => {
        const posts = recordPosts(page);
        await start(page, theme);
        expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);
        await shot(page, `${theme}-${width}-list`);
        await page.locator("button.conference-row").first().click();
        await settled(page);
        await expectFits(page, `${theme}/${width}/detail`);
        await shot(page, `${theme}-${width}-detail`);
        await page.locator("button.conference-row", { hasText: "Frau Muster" }).click();
        await settled(page);
        await expectFits(page, `${theme}/${width}/form`);
        await shot(page, `${theme}-${width}-form`);
        await choose(page, "14:00 - 14:10", "Kim");
        await sendForm(page, posts);
        await expectFits(page, `${theme}/${width}/outcome`);
        await shot(page, `${theme}-${width}-outcome`);
      });
    });
  }
}

test.describe("a child choice without a known profile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("says so and offers no send button", async ({ page }) => {
    const posts = recordPosts(page);
    await start(page, null, "unmatched-");
    await openTeacher(page);
    await expect(page.locator(".conference-no-profile")).toBeVisible();
    await expect(page.locator(".conference-form .conference-submit")).toHaveCount(0);
    await expect(page.locator(".conference-form select.sel option")).toHaveCount(1);
    expect(posts.length).toBe(0);
  });
});

async function openNotifySheet(page) {
  await page.locator(".header-actions .settings-entry").click();
  await page.waitForTimeout(200);
  await page.locator(".setting-row.notify-setting").click();
  await expect(page.locator(".sheet")).toBeVisible();
  await page.waitForTimeout(300);
}

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`conference profile note and switches ${theme} ${width}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme: theme });

      test(`the note and the switch list fit (${theme} ${width})`, async ({ page }) => {
        await start(page, theme, "unmatched-");
        await openTeacher(page);
        await expect(page.locator(".conference-no-profile")).toBeVisible();
        await expectFits(page, `${theme}/${width}/no-profile`);
        await shot(page, `${theme}-${width}-no-profile`);
        await page.locator(".header-back").click();
        await page.locator(".header-back").click();
        await openNotifySheet(page);
        const sheet = page.locator(".sheet");
        await expect(sheet).toContainText("Erinnerung drei Tage vor dem Sprechtag");
        await expectFits(page, `${theme}/${width}/notify-switches`);
        await sheet.locator("input[type=checkbox]").last().scrollIntoViewIfNeeded();
        await shot(page, `${theme}-${width}-notify-switches`);
      });
    });
  }
}
