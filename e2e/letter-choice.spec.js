const path = require("path");
const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const CHOICE_LETTER = "Elternsprechtag";
const SHOTS = path.join(__dirname, "..", "test-results", "letter-choice-shots");

async function settle(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(120);
}

async function openChoiceLetter(page) {
  await openArea(page, "post");
  await settle(page);
  await page.locator(".rows .row", { hasText: CHOICE_LETTER }).first().click();
  await settle(page);
  await expect(page.locator(".confirm-card .opt.letter-choice").first()).toBeVisible();
}

async function expectFits(page, label) {
  const [overflow, offenders] = await Promise.all([checkHorizontalOverflow(page), checkElementsWithinViewport(page)]);
  expect(overflow.overflow, `${label}: ${JSON.stringify(overflow.offendingContainers)}`).toBe(false);
  expect(offenders, `${label}: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function expectNoHandOff(page) {
  const links = await page.locator(".screen a[href]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")));
  expect(links.filter((href) => href.includes("/iserv/"))).toEqual([]);
  const tabs = await page.locator(".screen [target=_blank]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href") || ""));
  expect(tabs.filter((href) => !["https:" + "/" + "/github.com/", "https:" + "/" + "/my.home-assistant.io/"].some((start) => href.startsWith(start)))).toEqual([]);
}

test.describe("a letter that asks for an answer @ 390", () => {
  test.use({ viewport: { width: 390, height: 844 }, locale: "de-DE" });

  test("the answer is chosen, confirmed and shown inside the app", async ({ page }) => {
    const posts = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/letters/confirm")) posts.push(request.postDataJSON());
    });
    await goto(page);
    await openChoiceLetter(page);
    const block = page.locator(".confirm-card");
    await expect(block.locator(".opt.letter-choice")).toHaveText(["Zustimmen", "Ablehnen"]);
    await expect(block.locator(".letter-answer-send")).toBeDisabled();
    await expectNoHandOff(page);
    await expectFits(page, "choice-open");

    await block.locator(".opt.letter-choice", { hasText: "Ablehnen" }).click();
    await expect(block.locator(".letter-answer-send")).toBeEnabled();
    await block.locator(".letter-answer-send").click();
    const sheet = page.locator(".sheet");
    await expect(sheet.locator(".dlg-quote")).toHaveText("Ablehnen");
    expect(posts).toEqual([]);
    await sheet.locator(".btn-stack button").first().click();

    await expect(page.locator(".confirm-card.done .letter-answer")).toContainText("Ablehnen");
    await expect(page.locator(".confirm-card .opt.letter-choice")).toHaveCount(0);
    expect(posts.length).toBe(1);
    expect(posts[0].choices.length).toBe(1);
    await expectNoHandOff(page);
    await expectFits(page, "choice-done");
  });
});

for (const width of [390, 1024]) {
  for (const theme of ["light", "dark"]) {
    test.describe(`letter answer screenshots ${width} ${theme}`, () => {
      test.use({ viewport: { width, height: width === 390 ? 844 : 768 }, locale: "de-DE", colorScheme: theme });

      test(`choice card and settings modules (${width} ${theme})`, async ({ page }) => {
        await page.addInitScript((value) => {
          try {
            window.localStorage.setItem("theme", value);
          } catch (error) {}
        }, theme);
        await goto(page);
        await openChoiceLetter(page);
        await page.locator(".confirm-card .opt.letter-choice").first().click();
        await page.locator(".confirm-card").scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(SHOTS, `choice-${width}-${theme}.png`) });
        await expectNoHandOff(page);
        await page.locator(".header-actions .settings-entry").first().click();
        await settle(page);
        const modules = page.locator(".modules-block");
        if (await modules.count()) {
          await modules.first().scrollIntoViewIfNeeded();
          await page.screenshot({ path: path.join(SHOTS, `settings-modules-${width}-${theme}.png`) });
        }
        await expectNoHandOff(page);
      });
    });
  }
}
