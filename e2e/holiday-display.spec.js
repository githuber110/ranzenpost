const { test, expect } = require("@playwright/test");
const {
  goto,
  checkHorizontalOverflow,
  checkElementsWithinViewport,
  waitForSheetSettled,
  checkSheetContainment,
  checkLastRowReachable,
} = require("./helpers");

const VIEWPORTS = [
  { name: "320", width: 320, height: 800 },
  { name: "390", width: 390, height: 844 },
];

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
  { key: "ar", locale: "ar" },
];

const FULL_WEEK_OFFSET = 3;
const SINGLE_DAY_OFFSET = 5;

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function assertClean(overflow, offenders, label, failures) {
  if (overflow.overflow) {
    failures.push(`${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth} ${JSON.stringify(overflow.offendingContainers)}`);
  }
  if (offenders.length) {
    failures.push(`${label}: elements sticking out: ${JSON.stringify(offenders)}`);
  }
}

async function assertScreenClean(page, label, failures) {
  assertClean(await checkHorizontalOverflow(page), await checkElementsWithinViewport(page), label, failures);
}

async function holidayFields(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll(".tt-hol")].map((field) => {
      const name = field.querySelector(".name");
      return {
        cls: field.className,
        text: (name ? name.textContent : "").slice(0, 48),
        clippedX: field.scrollWidth > field.clientWidth + 1,
        clippedY: field.scrollHeight > field.clientHeight + 1,
        nameClippedX: name ? name.scrollWidth > name.clientWidth + 1 : false,
      };
    })
  );
}

function assertFieldsIntact(fields, label, failures, expected) {
  if (fields.length !== expected) {
    failures.push(`${label}: expected ${expected} holiday field(s), found ${fields.length}`);
    return;
  }
  for (const field of fields) {
    if (!field.text.trim()) failures.push(`${label}: a holiday field carries no word at all`);
    if (field.clippedX || field.nameClippedX) failures.push(`${label}: holiday name is cut off sideways: ${JSON.stringify(field)}`);
    if (field.clippedY) failures.push(`${label}: holiday name is cut off vertically: ${JSON.stringify(field)}`);
  }
}

async function openTimetable(page) {
  await page.locator(".tabbar .tab").nth(1).click();
  await waitForContentSettled(page);
}

async function pickWeek(page, offset) {
  await page.locator(".weekbar .mid").click();
  await waitForSheetSettled(page);
  await page.locator(".opt-list .opt").nth(offset).click();
  await waitForContentSettled(page);
}

for (const viewport of VIEWPORTS) {
  test.describe(`[P153] holiday display stays inside the screen @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`a full holiday week replaces the grid without overflowing (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await openTimetable(page);
          await pickWeek(page, FULL_WEEK_OFFSET);

          await expect(page.locator(".tt-hol.full")).toBeVisible();
          await expect(page.locator(".legend")).toHaveCount(0);
          await expect(page.locator(".tt-head")).toHaveCount(5);
          await expect(page.locator(".tt-hour")).toHaveCount(0);
          assertFieldsIntact(await holidayFields(page), `${viewport.name}/${lang.key}/full-week`, failures, 1);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/full-week`, failures);

          expect(failures, failures.join("\n")).toEqual([]);
        });

        test(`a single blocked day writes its long name out without clipping (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await openTimetable(page);
          await pickWeek(page, SINGLE_DAY_OFFSET);

          await expect(page.locator(".tt-hol")).toHaveCount(1);
          await expect(page.locator(".legend")).toHaveCount(1);
          const fields = await holidayFields(page);
          assertFieldsIntact(fields, `${viewport.name}/${lang.key}/single-day`, failures, 1);
          if (fields.length && !fields[0].text.includes("Einheit")) {
            failures.push(`${viewport.name}/${lang.key}/single-day: proper name was shortened to "${fields[0].text}"`);
          }
          await assertScreenClean(page, `${viewport.name}/${lang.key}/single-day`, failures);

          expect(failures, failures.join("\n")).toEqual([]);
        });

        test(`the week picker marks holiday weeks without bursting its rows (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await openTimetable(page);
          await page.locator(".weekbar .mid").click();
          await waitForSheetSettled(page);

          await expect(page.locator(".opt-list .opt")).toHaveCount(9);
          await expect(page.locator(".opt-list .opt.off")).toHaveCount(1);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/week-sheet`, failures);
          const containment = await checkSheetContainment(page);
          if (!containment.fitsViewport) failures.push(`${viewport.name}/${lang.key}/week-sheet: sheet taller than the viewport`);
          if (containment.overflows && !containment.scrollable) {
            failures.push(`${viewport.name}/${lang.key}/week-sheet: sheet overflows without scrolling`);
          }

          expect(failures, failures.join("\n")).toEqual([]);
        });

        test(`the state picker holds seventeen rows and stays reachable (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await page.locator(".header-actions .icon-btn").first().click();
          await waitForContentSettled(page);

          const rowLabel = await page.evaluate(() => window.t("holidays.settings.title"));
          const row = page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: rowLabel }) });
          await expect(row).toHaveCount(1);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/settings-row`, failures);

          await row.click();
          await waitForSheetSettled(page);
          await expect(page.locator(".sheet .opt-list .opt")).toHaveCount(17);
          await assertScreenClean(page, `${viewport.name}/${lang.key}/region-sheet`, failures);
          const containment = await checkSheetContainment(page);
          if (!containment.fitsViewport) failures.push(`${viewport.name}/${lang.key}/region-sheet: sheet taller than the viewport`);
          if (containment.overflows && !containment.scrollable) {
            failures.push(`${viewport.name}/${lang.key}/region-sheet: sheet overflows without scrolling`);
          }
          const reachable = await checkLastRowReachable(page, ".sheet .opt-list .opt");
          if (reachable.present && reachable.covered) {
            failures.push(`${viewport.name}/${lang.key}/region-sheet: last row is covered: ${JSON.stringify(reachable.coveringElements)}`);
          }

          expect(failures, failures.join("\n")).toEqual([]);
        });
      });
    }
  });
}
