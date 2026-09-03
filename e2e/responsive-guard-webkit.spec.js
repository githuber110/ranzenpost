const { test, expect, devices } = require("@playwright/test");
const { goto, checkHorizontalOverflow, checkElementsWithinViewport } = require("./helpers");

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
];

function deviceUse(name) {
  const { defaultBrowserType, ...rest } = devices[name];
  return rest;
}

const DEVICES = [
  { name: "iPhone SE (small)", use: {} },
  { name: "iPhone 14 Pro Max (large)", use: deviceUse("iPhone 14 Pro Max") },
];

async function waitForContentSettled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(80);
}

function assertClean(overflow, offenders, label) {
  expect(overflow.overflow, `${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`).toBe(false);
  expect(offenders, `${label}: elements sticking out of the viewport: ${JSON.stringify(offenders)}`).toEqual([]);
}

async function goBack(page) {
  const headerBack = page.locator(".header-back");
  if (await headerBack.count()) {
    await headerBack.first().click();
    return;
  }
  await page.locator(".list-head button").first().click();
}

const DATE_STEPS = [
  { type: "sick", step: "sickWhen", patch: {} },
  { type: "sick", step: "sickHours", patch: { hours_mode: "byLesson", from_period: "1", till_period: "6" } },
  { type: "leave", step: "leaveFrom", patch: { body: "Text" } },
  { type: "leave", step: "leaveTill", patch: { duration: "more", body: "Text" } },
  { type: "leave", step: "leaveDayTime", patch: { time_mode: "custom", body: "Text" } },
  { type: "deregister", step: "deregisterWhen", patch: {} },
  { type: "deregister", step: "repeatUntil", patch: { repeat: "weekly" } },
  { type: "daycare", step: "daycareKind", patch: { daycare_kind: "early_end", pickup_time: "13:30", reason: "Grund" } },
  { type: "daycare", step: "daycareWhen", patch: { reason: "Grund" } },
];

async function openStep(page, entry) {
  return page.evaluate(
    ({ type, step, patch }) => {
      startAbsenceForm(type);
      Object.assign(state.absenceForm, patch || {});
      absenceFlow.render();
      absenceFlow.go(step);
      return absenceFlow.current();
    },
    entry
  );
}

async function measureFields(page) {
  return page.evaluate(() => {
    const body = document.querySelector(".sw-body");
    if (!body) return null;
    const frame = body.getBoundingClientRect();
    const offenders = [];
    body.querySelectorAll("input, select, textarea, .opt-row").forEach((node) => {
      const rect = node.getBoundingClientRect();
      const overhang = Math.round(Math.max(rect.right - frame.right, frame.left - rect.left));
      if (overhang > 1) {
        offenders.push({
          what: node.getAttribute("type") || (typeof node.className === "string" ? node.className : node.tagName.toLowerCase()),
          overhang,
          width: Math.round(rect.width),
          frameWidth: Math.round(frame.width),
        });
      }
    });
    return offenders;
  });
}

for (const device of DEVICES) {
  test.describe(`WebKit real-engine guard @ ${device.name}`, () => {
    test.use(device.use);

    for (const lang of LANGUAGES) {
      test.describe(lang.key, () => {
        test.use({ locale: lang.locale });

        test(`all four absence types fit natively (${lang.key})`, async ({ page }) => {
          await goto(page);
          await page.locator(".tabbar .tab").nth(2).click();
          await waitForContentSettled(page);

          await page.locator(".btn").first().click();
          await page.waitForSelector(".sw-content");
          await page.waitForTimeout(150);
          for (const type of ["sick", "leave", "deregister", "daycare"]) {
            await page.evaluate((key) => {
              state.absenceForm.type = key;
              absenceFlow.render();
            }, type);
            await waitForContentSettled(page);

            const overflow = await checkHorizontalOverflow(page);
            const offenders = await checkElementsWithinViewport(page);
            assertClean(overflow, offenders, `${device.name}/${lang.key}/absence-type-${type}`);
          }
        });

        test(`[P193] every wizard step with a date or time field stays inside the screen (${lang.key})`, async ({ page }) => {
          const failures = [];
          await goto(page);
          await page.locator(".tabbar .tab").nth(2).click();
          await waitForContentSettled(page);
          await page.locator(".btn").first().click();
          await page.waitForSelector(".sw-content");
          await page.waitForTimeout(150);

          for (const entry of DATE_STEPS) {
            const label = `${device.name}/${lang.key}/${entry.type}/${entry.step}`;
            const reached = await openStep(page, entry);
            await waitForContentSettled(page);
            if (reached !== entry.step) {
              failures.push(`${label}: wizard refused the step, landed on ${reached}`);
              continue;
            }
            const fields = await measureFields(page);
            if (fields === null) {
              failures.push(`${label}: wizard body not mounted`);
              continue;
            }
            if (fields.length) failures.push(`${label}: fields wider than their frame: ${JSON.stringify(fields)}`);
            const overflow = await checkHorizontalOverflow(page);
            if (overflow.overflow) {
              failures.push(`${label}: scrollWidth ${overflow.scrollWidth} > clientWidth ${overflow.clientWidth}`);
            }
            const offenders = await checkElementsWithinViewport(page);
            if (offenders.length) failures.push(`${label}: elements sticking out: ${JSON.stringify(offenders)}`);
          }

          expect(failures, failures.join("\n")).toEqual([]);
        });
      });
    }
  });
}
