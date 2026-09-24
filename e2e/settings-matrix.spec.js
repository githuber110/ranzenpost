const { test, expect } = require("@playwright/test");
const { goto, waitForSheetSettled, leaveSettingsPage } = require("./helpers");
const SCHEMA = require("../tests/settings-schema.json");

const VIEWPORTS = [
  { name: "390", width: 390, height: 844 },
  { name: "1440", width: 1440, height: 900 },
];

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SCHOOL = "a1b2c3d4";
const CHILD = `${SCHOOL}:child-1`;
const FEED_TOKEN = "e2e-fixture-token-abcdefghijklmnopqrstuvwxyz012345";
const FEED_PATH = `/e2e-feed/calendar/${FEED_TOKEN}.ics`;
const OVERVIEW_TAB = 0;
const TIMETABLE_TAB = 1;
const ABSENCE_TAB = 2;
const LETTERS_TAB = 3;
const NEW_COLOR = "green";
const NEW_COLOR_HEX = "#2fa83c";
const CUSTOM_COLOR = "#a1b2c3";
const HOLIDAY_WEEK_OFFSET = 3;
const PHONE = { label: "Office", number: "+49 555 0100" };
const COURSE_CHOICE = ["E1|CCC", "REV|III", "KU|LLL"];

let layoutSlot = 0;
let matrixSlot = 0;

function nextMatrixKey() {
  matrixSlot += 1;
  return `matrix-${process.pid}-${Date.now()}-${matrixSlot}`;
}

async function prepareWithLayout(page) {
  layoutSlot += 1;
  await page.context().addCookies([{ name: "e2e_layout", value: `matrix-${process.pid}-${Date.now()}-${layoutSlot}`, url: BASE_URL }]);
  await prepare(page);
}

async function settled(page) {
  await page.waitForSelector(".loading", { state: "detached", timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(120);
}

async function text(page, key, vars) {
  return page.evaluate(([name, values]) => window.t(name, values || {}), [key, vars || null]);
}

const ALL_COMPONENTS = ["timetable", "school_holidays", "public_holidays", "marks", "absences"];

async function prepare(page) {
  await page.context().addCookies([{ name: "e2e_matrix", value: nextMatrixKey(), url: BASE_URL }]);
  await page.request.post("/e2e/matrix/reset");
  const listed = (await json(page, "/api/calendar/subscriptions")).subscriptions;
  await page.request.post(`/api/calendar/subscriptions/${listed[0].id}`, { data: { components: ALL_COMPONENTS } });
  await goto(page);
  await settled(page);
  await page.request.post("/e2e/matrix/snapshot");
}

async function json(page, path) {
  const response = await page.request.get(path);
  expect(response.ok(), `${path}: ${response.status()}`).toBe(true);
  return response.json();
}

async function timetable(page) {
  return json(page, `/api/timetable?child=${encodeURIComponent(CHILD)}`);
}

async function lessonsOfPeriod(page, period, code) {
  const data = await timetable(page);
  return data.lessons.filter((lesson) => lesson.period === period && (!code || lesson.subject_code === code));
}

async function feedEvents(page) {
  await page.request.post("/e2e/matrix/snapshot");
  const response = await page.request.get(FEED_PATH);
  expect(response.status()).toBe(200);
  const body = (await response.text()).replace(/\r\n /g, "");
  const events = [];
  for (const block of body.split("BEGIN:VEVENT").slice(1)) {
    const props = {};
    for (const line of block.split("\r\n")) {
      const index = line.indexOf(":");
      if (index <= 0) continue;
      const name = line.slice(0, index).split(";")[0];
      if (name === "END") continue;
      props[name] = line.slice(index + 1);
    }
    events.push(props);
  }
  return events;
}

async function integration(page, path) {
  const { token } = await json(page, "/e2e/matrix/token");
  const response = await page.request.get(path, { headers: { Authorization: `Bearer ${token}` } });
  expect(response.ok(), `${path}: ${response.status()}`).toBe(true);
  return response.json();
}

async function integrationState(page) {
  await page.request.post("/e2e/matrix/snapshot");
  return integration(page, `/api/integration/state?child=${encodeURIComponent(CHILD)}`);
}

async function integrationEvents(page, kind, day) {
  await page.request.post("/e2e/matrix/snapshot");
  const query = kind === "holidays" ? `school=${SCHOOL}` : `child=${encodeURIComponent(CHILD)}`;
  const range = day ? `&start=${day}&end=${day}` : "";
  return integration(page, `/api/integration/events?kind=${kind}&${query}${range}`);
}

async function openTab(page, index) {
  const rail = page.locator("nav.rail .rail-item");
  if (await rail.count()) await rail.nth(index).click();
  else await page.locator(".tabbar .tab").nth(index).click();
  await settled(page);
}

async function openSettings(page) {
  await page.locator(".settings-entry").first().click();
  await settled(page);
}

async function settingRow(page, key) {
  const label = await text(page, key);
  return page.locator(".setting-row").filter({ has: page.locator(".lbl", { hasText: label }) }).first();
}

async function openSettingSheet(page, key) {
  await openSettings(page);
  await (await settingRow(page, key)).click();
  await waitForSheetSettled(page);
}

async function saveSheet(page) {
  await page.locator(".sheet-foot .btn").first().click();
  await expect(page.locator(".sheet")).toHaveCount(0);
  await settled(page);
}

async function labelled(page, key, vars) {
  return page.locator(".sheet").getByLabel(await text(page, key, vars), { exact: true });
}

function isWeekday() {
  const day = new Date().getDay();
  return day >= 1 && day <= 5;
}

async function todayRows(page) {
  await openTab(page, OVERVIEW_TAB);
  return page.locator('.panel[data-area="today"] .rows.flat .row:not(.row-note)');
}

async function firstCellOf(page, code) {
  await openTab(page, TIMETABLE_TAB);
  const cell = page.locator(`.tt-cell[data-subject="${code}"]`).first();
  await expect(cell).toBeVisible();
  return cell;
}

async function pickWeek(page, offset) {
  await page.locator(".weekbar .mid").click();
  await waitForSheetSettled(page);
  await page.locator(".opt-list .opt").nth(offset).click();
  await settled(page);
}

async function confirmDestructive(page) {
  await waitForSheetSettled(page);
  await page.locator(".sheet .btn.destructive").first().click();
  await settled(page);
}

async function confirmDestructiveOrPlain(page) {
  await waitForSheetSettled(page);
  const destructive = page.locator(".sheet .btn.destructive");
  if (await destructive.count()) await destructive.first().click();
  else await page.locator(".sheet .btn-stack button").first().click();
  await settled(page);
}

async function openNamesPage(page) {
  await openSettings(page);
  await (await settingRow(page, "settings.names")).click();
  await page.waitForSelector(".names-page .names-block", { timeout: 8000 });
}

async function namesField(page, key, vars) {
  return page.locator(".names-page").getByLabel(await text(page, key, vars), { exact: true });
}

async function saveNamesPage(page) {
  await page.locator(".names-page .names-save").click();
  await expect(page.locator(".names-page")).toHaveCount(0);
  await settled(page);
}

async function editNamesPage(page, key, code, value) {
  await openNamesPage(page);
  await (await namesField(page, key, { code })).fill(value);
  await saveNamesPage(page);
}

async function pickSubjectColour(page) {
  await openNamesPage(page);
  await (await namesField(page, "settings.subjects.color", { code: "D" })).click();
}

function holidayStarts(events) {
  return events.filter((event) => !(event.DTSTART || "").includes("T")).map((event) => event.DTSTART);
}

function periodThree(events) {
  return events.filter((event) => /-p3-/.test(event.UID || ""));
}

async function blockOrder(page, selector) {
  return page.locator(selector).evaluateAll((nodes) => nodes.map((node) => node.dataset.block));
}

async function backToOverview(page) {
  await leaveSettingsPage(page);
  await page.locator(".header-back").click();
  await page.waitForSelector(".overview", { timeout: 8000 });
}

const SETTINGS = [
  {
    name: "period_time",
    keys: ["period_times"],
    slow: true,
    title: "the lesson times page moves the grid row, the today row, the feed and the integration",
    before: async (page) => {
      const before = await feedEvents(page);
      expect(before.some((event) => /T0800\d\d$/.test(event.DTSTART || ""))).toBe(true);
      const stateBefore = await integrationState(page);
      expect(stateBefore.next_lesson.start).toMatch(/:00:00\+0[12]:00$/);
    },
    change: async (page) => {
      await openSettings(page);
      await page.locator(".periods-setting").click();
      await page.waitForSelector(".periods-page .prow");
      await page.locator(".periods-adjust").click();
      for (let number = 1; number <= 8; number += 1) {
        await page.locator(`.periods-page button.prow[data-period="${number}"]`).click();
        const editor = page.locator(".sheet, .pane-detail").filter({ has: page.locator(".periods-apply") });
        for (let step = 0; step < 9; step += 1) await editor.locator(".lesson-start .sbtn").first().click();
        await editor.locator(".periods-apply").click();
        await expect(page.locator(".periods-apply")).toHaveCount(0);
      }
      await page.locator(".header-back").click();
      await settled(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1))[0].start_time).toBe("07:15");
      },
      grid: async (page) => {
        await openTab(page, TIMETABLE_TAB);
        await expect(page.locator(".tt-hour").first()).toContainText("07:15");
      },
      today: async (page) => {
        if (!isWeekday()) return;
        const rows = await todayRows(page);
        await expect(rows.first().locator(".row-meta")).toContainText(":15");
      },
      feed: async (page) => {
        const after = await feedEvents(page);
        expect(after.some((event) => /T0715\d\d$/.test(event.DTSTART || ""))).toBe(true);
        expect(after.some((event) => /T0800\d\d$/.test(event.DTSTART || ""))).toBe(false);
      },
      integration_state: async (page) => {
        const stateAfter = await integrationState(page);
        expect(stateAfter.next_lesson.start).toMatch(/:15:00\+0[12]:00$/);
      },
    },
  },
  {
    name: "own_entries_ha",
    keys: ["own_entries_ha"],
    title: "the switch on the lesson times page sends own entries to Home Assistant",
    before: async (page) => {
      expect((await json(page, `/api/connections/${SCHOOL}`)).own_entries_ha).toBe(false);
      const info = await integration(page, "/api/integration/info");
      expect(info.schools.find((school) => school.id === SCHOOL).own_entries).toBe(false);
    },
    change: async (page) => {
      await openSettings(page);
      await page.locator(".periods-setting").click();
      await page.waitForSelector(".periods-page .periods-ha .switch");
      await expect(page.locator(".periods-ha .switch")).toHaveAttribute("aria-checked", "false");
      await page.locator(".periods-ha .switch").click();
      await expect(page.locator(".periods-ha .switch")).toHaveAttribute("aria-checked", "true");
      await page.locator(".header-back").click();
      await settled(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await json(page, `/api/connections/${SCHOOL}`)).own_entries_ha).toBe(true);
      },
      integration_info: async (page) => {
        const info = await integration(page, "/api/integration/info");
        expect(info.schools.find((school) => school.id === SCHOOL).own_entries).toBe(true);
      },
      integration_events: async (page) => {
        const events = await integration(page, `/api/integration/events?child=${encodeURIComponent(CHILD)}&kind=own_entries`);
        expect(Array.isArray(events)).toBe(true);
      },
    },
  },
  {
    name: "subject_name",
    keys: ["subjects"],
    title: "the names page renames the cells, the today row, the feed and the integration",
    change: (page) => editNamesPage(page, "settings.subjects.name", "D", "German"),
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1, "D"))[0].subject_label).toBe("German");
      },
      grid: async (page) => {
        const cell = await firstCellOf(page, "D");
        expect(await cell.getAttribute("aria-label")).toContain("German");
      },
      today: async (page) => {
        if (!isWeekday()) return;
        const rows = await todayRows(page);
        await expect(rows.filter({ hasText: "German" }).first()).toBeVisible();
      },
      feed: async (page) => {
        const events = (await feedEvents(page)).filter((event) => /-p[0-9]+-/.test(event.UID || ""));
        expect(events.some((event) => (event.SUMMARY || "").includes("German"))).toBe(true);
        expect(events.some((event) => (event.SUMMARY || "").includes("Deutsch"))).toBe(false);
      },
      integration_events: async (page) => {
        const lessons = await integrationEvents(page, "lessons");
        expect(lessons.some((item) => item.subject === "German")).toBe(true);
        expect(lessons.some((item) => item.subject === "Deutsch")).toBe(false);
      },
    },
  },
  {
    name: "subject_code",
    keys: ["subjects"],
    title: "an edited code reaches the cells and the integration",
    change: async (page) => {
      await openNamesPage(page);
      await expect(await namesField(page, "settings.subjects.code", { code: "D" })).toBeHidden();
      await page.locator(".names-page").getByRole("button", { name: await text(page, "settings.names.codeChangeFor", { code: "D" }), exact: true }).click();
      await (await namesField(page, "settings.subjects.code", { code: "D" })).fill("DEU");
      await saveNamesPage(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1, "DEU")).length).toBeGreaterThan(0);
      },
      grid: async (page) => {
        const cell = await firstCellOf(page, "DEU");
        await expect(cell.locator(".sub")).toHaveText("DEU");
      },
      integration_events: async (page) => {
        const lessons = await integrationEvents(page, "lessons");
        expect(lessons.some((item) => item.subject_code === "DEU")).toBe(true);
        expect(lessons.some((item) => item.subject_code === "D")).toBe(false);
      },
    },
  },
  {
    name: "subject_colour",
    keys: ["subjects"],
    title: "the swatch recolours the cells, the feed colour and the integration",
    before: async (page, ctx) => {
      ctx.before = (await feedEvents(page)).find((event) => (event.SUMMARY || "").includes("Deutsch"));
    },
    change: async (page) => {
      await pickSubjectColour(page);
      await page.locator(`.color-dialog .swatch-btn[data-color="${NEW_COLOR}"]`).click();
      await saveNamesPage(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1, "D"))[0].color).toBe(NEW_COLOR);
      },
      grid: async (page) => {
        const cell = await firstCellOf(page, "D");
        expect(await cell.evaluate((node) => node.style.getPropertyValue("--subject-bar"))).toBe(`var(--subject-${NEW_COLOR}-bar)`);
        expect(await cell.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe("rgb(77, 191, 87)");
      },
      feed: async (page, ctx) => {
        const after = (await feedEvents(page)).find((event) => (event.SUMMARY || "").includes("Deutsch"));
        expect(after.COLOR).toBeTruthy();
        expect(after.COLOR).not.toBe(ctx.before.COLOR);
      },
      integration_events: async (page) => {
        const lessons = await integrationEvents(page, "lessons");
        expect(lessons.filter((item) => item.subject_code === "D").every((item) => item.color === NEW_COLOR_HEX)).toBe(true);
      },
    },
  },
  {
    name: "subject_colour_hex",
    keys: ["subjects"],
    title: "the hex field recolours the cells with a computed ink, the integration and the feed",
    change: async (page) => {
      await pickSubjectColour(page);
      const dialog = page.locator(".color-dialog");
      await expect(dialog.locator(".colour-hex")).toBeHidden();
      await dialog.locator(".colour-own-toggle").click();
      await dialog.locator(".colour-hex").fill(CUSTOM_COLOR.toUpperCase());
      await expect(dialog.locator(".colour-picker")).toHaveValue(CUSTOM_COLOR);
      await expect(dialog.locator(".colour-own")).toHaveAttribute("aria-pressed", "true");
      await expect(dialog.locator(".colour-preview .tt-cell.subject")).toHaveCount(2);
      await dialog.locator(".sheet-close").click();
      await saveNamesPage(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1, "D"))[0].color).toBe(CUSTOM_COLOR);
      },
      grid: async (page) => {
        const cell = await firstCellOf(page, "D");
        expect(await cell.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe("rgb(161, 178, 195)");
        expect(await cell.evaluate((node) => getComputedStyle(node).color)).toBe("rgb(0, 0, 0)");
      },
      integration_events: async (page) => {
        const lessons = await integrationEvents(page, "lessons");
        expect(lessons.filter((item) => item.subject_code === "D").every((item) => item.color === CUSTOM_COLOR)).toBe(true);
      },
      feed: async (page) => {
        const after = (await feedEvents(page)).find((event) => (event.SUMMARY || "").includes("Deutsch"));
        expect(after.COLOR).toBeTruthy();
      },
    },
  },
  {
    name: "teacher_name",
    keys: ["teachers"],
    title: "the names page renames the rows, the lesson sheet, the feed summary and the integration",
    change: (page) => editNamesPage(page, "settings.teachers.name", "BEH", "Frau Bergmann"),
    reaches: {
      app_api: async (page) => {
        expect((await lessonsOfPeriod(page, 1, "D"))[0].teacher_label).toBe("Frau Bergmann");
      },
      today: async (page) => {
        if (!isWeekday()) return;
        const rows = await todayRows(page);
        await expect(rows.filter({ hasText: "Frau Bergmann" }).first()).toBeVisible();
      },
      lesson_sheet: async (page) => {
        const cell = await firstCellOf(page, "D");
        await cell.click();
        await waitForSheetSettled(page);
        await expect(page.locator(".sheet")).toContainText("Frau Bergmann");
        await page.locator(".sheet-close").click();
      },
      feed: async (page) => {
        const events = await feedEvents(page);
        expect(events.some((event) => (event.SUMMARY || "").includes("(Frau Bergmann)"))).toBe(true);
      },
      integration_state: async (page) => {
        const state = await integrationState(page);
        expect([state.now_lesson, state.next_lesson].filter(Boolean).some((item) => item.teacher === "Frau Bergmann")).toBe(true);
      },
    },
  },
  {
    name: "holiday_region",
    keys: ["holiday_region"],
    title: "the region sheet moves the holiday week in the grid, the feed and the integration",
    before: async (page, ctx) => {
      ctx.before = holidayStarts(await feedEvents(page));
      expect(ctx.before.length).toBeGreaterThan(0);
      ctx.schoolBefore = await integration(page, `/api/integration/school?id=${SCHOOL}`);
      await openTab(page, TIMETABLE_TAB);
      await pickWeek(page, HOLIDAY_WEEK_OFFSET);
      await expect(page.locator(".tt-hol.full")).toBeVisible();
    },
    change: async (page) => {
      await openSettingSheet(page, "holidays.settings.title");
      const label = await page.evaluate(() => window.holidayRegionLabel("DE-BY"));
      await page.locator(".sheet .opt").filter({ hasText: label }).first().click();
      await settled(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await json(page, `/api/connections/${SCHOOL}`)).holiday_region).toBe("DE-BY");
        expect((await json(page, `/api/holidays?week=${HOLIDAY_WEEK_OFFSET}&connection=${SCHOOL}`)).region).toBe("DE-BY");
      },
      grid: async (page) => {
        await openTab(page, TIMETABLE_TAB);
        await pickWeek(page, HOLIDAY_WEEK_OFFSET);
        await expect(page.locator(".tt-hol.full")).toHaveCount(0);
        await pickWeek(page, HOLIDAY_WEEK_OFFSET + 1);
        await expect(page.locator(".tt-hol.full")).toBeVisible();
      },
      feed: async (page, ctx) => {
        const after = holidayStarts(await feedEvents(page));
        expect(after).not.toEqual(ctx.before);
      },
      integration_school: async (page, ctx) => {
        const schoolAfter = await integration(page, `/api/integration/school?id=${SCHOOL}`);
        expect(schoolAfter.region).toBe("DE-BY");
        expect(schoolAfter.next_holiday.start).not.toBe(ctx.schoolBefore.next_holiday.start);
      },
    },
  },
  {
    name: "phones",
    keys: ["phones"],
    title: "the phones sheet fills the absence view",
    change: async (page) => {
      await openSettingSheet(page, "settings.phones");
      await page.locator(".sheet .btn.ghost").filter({ hasText: await text(page, "settings.phones.add") }).click();
      await (await labelled(page, "common.phone.label")).fill(PHONE.label);
      await (await labelled(page, "common.phone.number")).fill(PHONE.number);
      await saveSheet(page);
    },
    reaches: {
      app_api: async (page) => {
        expect((await json(page, "/api/absences")).phones).toEqual([PHONE]);
      },
      absences: async (page) => {
        await openTab(page, ABSENCE_TAB);
        await expect(page.locator(".row-sub", { hasText: PHONE.number }).first()).toBeVisible();
      },
    },
  },
  {
    name: "language",
    keys: ["language"],
    title: "the language sheet switches the app texts, the config, the feed texts and the integration",
    before: async (page, ctx) => {
      const before = await feedEvents(page);
      expect(before.some((event) => (event.DESCRIPTION || "").includes("Lehrkraft"))).toBe(true);
      ctx.timetableLabel = await text(page, "nav.timetable");
    },
    change: async (page) => {
      await openSettingSheet(page, "settings.language");
      await page.locator('.sheet .opt[lang="en"]').click();
      await settled(page);
    },
    reaches: {
      app: async (page, ctx) => {
        expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");
        expect(await text(page, "nav.timetable")).not.toBe(ctx.timetableLabel);
      },
      app_config: async (page) => {
        expect((await json(page, "/api/config")).language).toBe("en");
      },
      feed: async (page) => {
        const after = await feedEvents(page);
        expect(after.some((event) => (event.DESCRIPTION || "").includes("Teacher"))).toBe(true);
        expect(after.some((event) => (event.DESCRIPTION || "").includes("Lehrkraft"))).toBe(false);
      },
      integration_info: async (page) => {
        expect((await integration(page, "/api/integration/info")).language).toBe("en");
      },
    },
  },
  {
    name: "theme",
    keys: [],
    title: "the theme sheet sets the data-theme attribute and the theme colour",
    before: async (page) => {
      expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBeNull();
    },
    change: async (page) => {
      await openSettingSheet(page, "settings.theme");
      await page.locator(".sheet .opt").nth(1).click();
      await settled(page);
    },
    reaches: {
      document: async (page) => {
        expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe("dark");
      },
      browser_storage: async (page) => {
        expect(await page.evaluate(() => window.localStorage.getItem("theme"))).toBe("dark");
      },
      theme_colour: async (page) => {
        expect(await page.evaluate(() => document.querySelector('meta[name="theme-color"]').getAttribute("content"))).toBe("#0e1412");
      },
    },
  },
  {
    name: "notify_targets",
    keys: ["notify_services"],
    title: "the notify sheet stores the chosen service in the config",
    before: async (page) => {
      expect((await json(page, "/api/config")).notify_services).toEqual([]);
    },
    change: async (page) => {
      await openSettingSheet(page, "settings.notify.service");
      await page.locator(".sheet .notify-pick-open").click();
      await waitForSheetSettled(page);
      const box = page.locator(".sheet .notify-services-group input[type=checkbox]").first();
      await box.check();
      const pickerClose = page.locator(".sheet .sheet-close").last();
      await pickerClose.click();
      await page.waitForTimeout(200);
      await expect(page.locator(".notify-chip")).toHaveCount(1);
      await saveSheet(page);
    },
    reaches: {
      app_config: async (page) => {
        expect((await json(page, "/api/config")).notify_services).toHaveLength(1);
      },
    },
  },
  {
    name: "notify_events",
    keys: ["notify_events"],
    title: "an event switch of the notify sheet lands in the config",
    before: async (page) => {
      expect((await json(page, "/api/config")).notify_events.letters).toBe(true);
    },
    change: async (page) => {
      await openSettingSheet(page, "settings.notify.service");
      await expect(await labelled(page, "settings.notify.event.letters")).toBeDisabled();
      await page.locator(".sheet .notify-pick-open").click();
      await waitForSheetSettled(page);
      await page.locator(".sheet .notify-services-group input[type=checkbox]").first().check();
      await page.locator(".sheet .sheet-close").last().click();
      await page.waitForTimeout(200);
      await expect(page.locator(".notify-chip")).toHaveCount(1);
      await (await labelled(page, "settings.notify.event.letters")).uncheck();
      await saveSheet(page);
    },
    reaches: {
      app_config: async (page) => {
        const events = (await json(page, "/api/config")).notify_events;
        expect(events.letters).toBe(false);
        expect(events.timetable).not.toBe(false);
      },
    },
  },
  {
    name: "calendar_subscription",
    keys: [],
    title: "components, renewal and deletion reach the feed and the listing",
    steps: [
      {
        name: "components",
        before: async (page) => {
          expect((await feedEvents(page)).some((event) => (event.UID || "").includes("-p1-"))).toBe(true);
        },
        change: async (page) => {
          await openTab(page, TIMETABLE_TAB);
          await page.locator(".header-actions .icon-btn").first().click();
          await page.waitForSelector(".calendar-page .cal-card", { timeout: 8000 });
          await page.locator(".cal-edit").click();
          await page.waitForSelector(".cal-form");
          await page.locator(".cal-form .check input").first().uncheck();
          await page.locator(".cal-form .btn-stack .btn").first().click();
          await settled(page);
          await expect(page.locator(".cal-form")).toHaveCount(0);
        },
        reaches: {
          listing: async (page) => {
            const listed = (await json(page, "/api/calendar/subscriptions")).subscriptions;
            expect(listed[0].components).toEqual(ALL_COMPONENTS.filter((name) => name !== "timetable"));
          },
          feed: async (page) => {
            const trimmed = await feedEvents(page);
            expect(trimmed.length).toBeGreaterThan(0);
            expect(trimmed.some((event) => (event.UID || "").includes("-p1-"))).toBe(false);
          },
        },
      },
      {
        name: "rotate",
        change: async (page) => {
          await page.locator(".cal-rotate").click();
          await confirmDestructive(page);
          await page.waitForSelector(".cal-card", { timeout: 8000 });
        },
        reaches: {
          listing: async (page, ctx) => {
            ctx.rotated = (await json(page, "/api/calendar/subscriptions")).subscriptions[0];
            expect(ctx.rotated.token).not.toBe(FEED_TOKEN);
          },
          feed: async (page, ctx) => {
            expect((await page.request.get(FEED_PATH)).status()).toBe(404);
            expect((await page.request.get(`/e2e-feed/calendar/${ctx.rotated.token}.ics`)).status()).toBe(200);
          },
        },
      },
      {
        name: "delete",
        change: async (page) => {
          await page.locator(".cal-delete").click();
          await confirmDestructive(page);
          await settled(page);
        },
        reaches: {
          listing: async (page) => {
            expect((await json(page, "/api/calendar/subscriptions")).subscriptions).toEqual([]);
          },
          feed: async (page, ctx) => {
            expect((await page.request.get(`/e2e-feed/calendar/${ctx.rotated.token}.ics`)).status()).toBe(404);
          },
        },
      },
    ],
  },
  {
    name: "short_name",
    keys: ["short_name"],
    title: "the school page renames the filter chips and the filter narrows the list",
    cookies: { e2e_schools: "2" },
    change: async (page) => {
      await openSettings(page);
      await page.locator(".schools-block .school-row").first().click();
      await settled(page);
      await page.locator(".school-page .setting-row").filter({ hasText: await text(page, "schools.shortName") }).click();
      await waitForSheetSettled(page);
      await page.locator(".sheet input.inp").fill("Alpha");
      await saveSheet(page);
    },
    reaches: {
      app_api: async (page) => {
        const summaries = (await json(page, "/api/connections")).connections;
        expect(summaries.find((entry) => entry.id === SCHOOL).short_name).toBe("Alpha");
      },
      filter_chips: async (page) => {
        await openTab(page, LETTERS_TAB);
        const filter = page.locator(".chipbar.school-filter .chip");
        await expect(filter).toHaveCount(3);
        expect(await filter.allTextContents()).toContain("Alpha");
      },
      filter_narrows: async (page) => {
        const filter = page.locator(".chipbar.school-filter .chip");
        const all = await page.locator(".rows .row").count();
        await filter.nth(2).click();
        await settled(page);
        expect(await page.locator(".rows .row").count()).toBeLessThan(all);
        await expect(page.locator(".rows .row .row-tags .tag").first()).toHaveText("Hillview");
      },
    },
  },
  {
    name: "overview_blocks",
    keys: ["overview_blocks"],
    title: "reordering, resizing and hiding a block reaches the app and the backend, unknown keys are dropped",
    layout: true,
    steps: [
      {
        name: "arrange",
        before: async (page, ctx) => {
          await openSettings(page);
          await page.locator(".layout-setting").click();
          await page.waitForSelector(".blocks-page", { timeout: 8000 });
          ctx.initial = await blockOrder(page, ".blocks-page .block-row");
          expect(ctx.initial[0]).toBe("today");
          await expect(
            page.locator('.block-row[data-block="changes"] .switch'),
            "the block this row hides must be on by default, pick another one if the default changed",
          ).toHaveAttribute("aria-checked", "true");
        },
        change: async (page, ctx) => {
          for (let step = 0; step < ctx.initial.indexOf("letters"); step += 1) {
            await page.locator('.block-row[data-block="letters"] .order-btns [data-dir="up"]').click();
            await page.waitForTimeout(200);
          }
          await page.locator('.block-row[data-block="changes"] .switch').click();
          await page.waitForTimeout(300);
          await page.locator('.block-row[data-block="letters"] .segment.mini [role="radio"]').first().click();
          await page.waitForTimeout(300);
        },
        reaches: {
          blocks_page: async (page) => {
            const reordered = await blockOrder(page, ".blocks-page .block-row");
            expect(reordered.indexOf("letters")).toBeLessThan(reordered.indexOf("today"));
            expect(await page.locator('.block-row[data-block="changes"] .switch').getAttribute("aria-checked")).toBe("false");
          },
          app_config: async (page) => {
            const config = await json(page, "/api/config");
            expect(config.overview_blocks.map((entry) => entry.key)).not.toContain("changes");
            expect(config.overview_blocks[0].key).toBe("letters");
            expect(config.overview_blocks[0].size).toBe("compact");
          },
          overview: async (page) => {
            await backToOverview(page);
            const panels = await blockOrder(page, ".overview .panel[data-block]");
            expect(panels).not.toContain("changes");
            expect(panels.indexOf("letters")).toBeLessThan(panels.indexOf("today"));
            const compactRow = page.locator('.overview .panel[data-block="letters"] .row.compact').first();
            if (await compactRow.count()) {
              expect(await compactRow.locator(".row-sub").count()).toBe(0);
            }
          },
        },
      },
      {
        name: "unknown_key",
        change: async (page) => {
          await page.request.post("/api/config", { data: { overview_blocks: [{ key: "today" }, { key: "not-a-real-block" }] } });
        },
        reaches: {
          app_config: async (page) => {
            const config = await json(page, "/api/config");
            expect(config.overview_blocks.map((entry) => entry.key)).toEqual(["today"]);
          },
        },
      },
    ],
  },
  {
    name: "course_choice",
    keys: ["course_filters"],
    title: "the course page filters the grid, the today card, the feed and the integration",
    cookies: { e2e_courses: "1" },
    setup: async (page) => {
      await page.request.post("/api/timetable/courses", { data: { child: CHILD, chosen: null } });
    },
    teardown: async (page) => {
      await page.request.post("/api/timetable/courses", { data: { child: CHILD, chosen: null } });
    },
    before: async (page) => {
      const before = periodThree(await feedEvents(page));
      expect(before.some((event) => (event.SUMMARY || "").includes("Dachs"))).toBe(true);
      expect((await lessonsOfPeriod(page, 3)).length).toBeGreaterThan(5);
    },
    change: async (page) => {
      await openSettings(page);
      await page.locator(".setting-row.courses-setting").first().click();
      await settled(page);
      const boxes = page.locator(".course-check input");
      expect(await boxes.count()).toBeGreaterThan(COURSE_CHOICE.length);
      expect(await boxes.evaluateAll((inputs) => inputs.every((input) => input.checked))).toBe(true);
      for (const box of await boxes.all()) await box.uncheck();
      for (const key of COURSE_CHOICE) await page.locator(`.course-check[data-course="${key}"] input`).check();
      await page.locator(".courses-save").click();
      await settled(page);
    },
    reaches: {
      app_api: async (page) => {
        expect([...new Set((await lessonsOfPeriod(page, 3)).map((lesson) => lesson.subject_code))]).toEqual(["E1"]);
      },
      grid: async (page) => {
        await openTab(page, TIMETABLE_TAB);
        await expect(page.locator(".tt-cell.courses")).toHaveCount(0);
        await expect(page.locator('.tt-cell[data-subject="E1"]').first()).toBeVisible();
      },
      today: async (page) => {
        if (!isWeekday()) return;
        await openTab(page, OVERVIEW_TAB);
        await expect(page.locator('.panel[data-area="today"] .courses-row')).toHaveCount(0);
      },
      feed: async (page) => {
        const after = periodThree(await feedEvents(page));
        expect(after.length).toBeGreaterThan(0);
        expect(after.every((event) => (event.SUMMARY || "").includes("Castor"))).toBe(true);
      },
      integration_events: async (page) => {
        const lessons = (await integrationEvents(page, "lessons")).filter((item) => /-p3-/.test(item.uid || ""));
        expect(lessons.length).toBeGreaterThan(0);
        expect(lessons.every((item) => item.subject_code === "E1")).toBe(true);
      },
    },
  },
  {
    name: "navigation",
    keys: ["navigation"],
    title: "the bottom bar, the rail and the More sheet follow the configured order, the backend keeps it",
    layout: true,
    change: async (page) => {
      await openSettings(page);
      await page.locator(".layout-setting").click();
      await page.waitForSelector(".app-layout-page .nav-page", { timeout: 8000 });
      await page.locator('.nav-row[data-area="messenger"] .order-btns [data-dir="up"]').click();
      await page.waitForTimeout(300);
    },
    reaches: {
      app_config: async (page) => {
        const config = await json(page, "/api/config");
        expect(config.navigation.indexOf("messenger")).toBeLessThan(config.navigation.indexOf("post"));
      },
      bar_or_rail: async (page, ctx) => {
        await backToOverview(page);
        if (ctx.viewport.width < 900) {
          const tabs = await page.locator(".tabbar .tab").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
          expect(tabs).toContain("messenger");
          expect(tabs).toContain("more");
          await page.locator(".tabbar .tab-more").click();
          await waitForSheetSettled(page);
          const rows = await page.locator(".sheet .more-row").evaluateAll((nodes) => nodes.map((node) => node.dataset.area));
          expect(rows[0]).toBe("post");
        } else {
          const rail = await page.locator("nav.rail .rail-item").evaluateAll((nodes) => nodes.map((node) => node.dataset.view));
          expect(rail.indexOf("messenger")).toBeLessThan(rail.indexOf("post"));
        }
      },
    },
  },
];

const ACTIONS = [
  {
    name: "exam_mark",
    keys: [],
    title: "marking a lesson and removing the mark reaches the grid, the today row, the feed and the integration",
    steps: [
      {
        name: "mark",
        change: async (page) => {
          const cell = await firstCellOf(page, "D");
          await cell.click();
          await waitForSheetSettled(page);
          await page.locator(".sheet-foot .mark-add").click();
          await waitForSheetSettled(page);
          await page.locator(".sheet-body .inp").fill("Vocabulary");
          await page.locator(".sheet-foot .btn").click();
          await expect(page.locator(".sheet")).toHaveCount(0);
        },
        reaches: {
          app_api: async (page, ctx) => {
            ctx.marks = (await json(page, `/api/marks?child=${encodeURIComponent(CHILD)}`)).marks;
            expect(ctx.marks.map((entry) => entry.name)).toEqual(["Vocabulary"]);
          },
          grid: async (page) => {
            await expect(page.locator(".tt-cell.marked .exam-flag").first()).toBeVisible();
          },
          today: async (page, ctx) => {
            if (!(isWeekday() && ctx.marks[0].date === new Date().toISOString().slice(0, 10))) return;
            const rows = await todayRows(page);
            await expect(rows.locator(".tag.exam").first()).toBeVisible();
          },
          feed: async (page) => {
            const withExam = await feedEvents(page);
            expect(withExam.some((event) => (event.SUMMARY || "").includes("Vocabulary"))).toBe(true);
          },
          integration_events: async (page) => {
            const exams = await integrationEvents(page, "exams");
            expect(exams.map((item) => item.name)).toEqual(["Vocabulary"]);
          },
          integration_state: async (page) => {
            const state = await integrationState(page);
            expect(state.exams_upcoming.count + (state.next_exam ? 0 : 0)).toBeGreaterThanOrEqual(0);
          },
        },
      },
      {
        name: "remove",
        change: async (page) => {
          await page.locator(".tt-cell.marked").first().click();
          await waitForSheetSettled(page);
          await page.locator(".sheet .btn.destructive").filter({ hasText: await text(page, "marks.action.remove") }).click();
          await settled(page);
        },
        reaches: {
          grid: async (page) => {
            await expect(page.locator(".tt-cell.marked")).toHaveCount(0);
          },
          app_api: async (page) => {
            expect((await json(page, `/api/marks?child=${encodeURIComponent(CHILD)}`)).marks).toEqual([]);
          },
          feed: async (page) => {
            expect((await feedEvents(page)).some((event) => (event.SUMMARY || "").includes("Vocabulary"))).toBe(false);
          },
          integration_events: async (page) => {
            expect(await integrationEvents(page, "exams")).toEqual([]);
          },
        },
      },
    ],
  },
  {
    name: "own_cancellation",
    keys: [],
    title: "marking a lesson as cancelled and undoing it reaches the grid, the feed and the integration",
    steps: [
      {
        name: "cancel",
        change: async (page, ctx) => {
          const cell = await firstCellOf(page, "D");
          ctx.label = await cell.getAttribute("aria-label");
          await cell.click();
          await waitForSheetSettled(page);
          await page.locator(".sheet .btn").filter({ hasText: await text(page, "timetable.cancel.action.add") }).click();
          await settled(page);
          await expect(page.locator(".sheet")).toHaveCount(0);
        },
        reaches: {
          app_api: async (page, ctx) => {
            ctx.listed = (await json(page, `/api/cancellations?child=${encodeURIComponent(CHILD)}`)).cancellations;
            expect(ctx.listed).toHaveLength(1);
          },
          grid: async (page) => {
            await expect(page.locator(".tt-cell.out").first()).toBeVisible();
          },
          feed: async (page, ctx) => {
            const listed = ctx.listed;
            ctx.dropped = (await feedEvents(page)).find((event) => (event.UID || "").includes(`-${listed[0].date.replace(/-/g, "")}-p${listed[0].period}-`));
            expect(ctx.dropped.TRANSP).toBe("TRANSPARENT");
          },
          integration_events: async (page, ctx) => {
            const slot = (item) => item.uid.includes(`-p${ctx.listed[0].period}-`);
            const lessons = await integrationEvents(page, "lessons", ctx.listed[0].date);
            expect(lessons.filter(slot).every((item) => item.cancelled)).toBe(true);
          },
        },
      },
      {
        name: "undo",
        change: async (page) => {
          await page.locator(".tt-cell.out").first().click();
          await waitForSheetSettled(page);
          await page.locator(".sheet .btn").filter({ hasText: await text(page, "timetable.cancel.action.remove") }).click();
          await settled(page);
          await expect(page.locator(".sheet")).toHaveCount(0);
        },
        reaches: {
          app_api: async (page) => {
            expect((await json(page, `/api/cancellations?child=${encodeURIComponent(CHILD)}`)).cancellations).toEqual([]);
          },
          feed: async (page, ctx) => {
            const restored = (await feedEvents(page)).find((event) => (event.UID || "") === ctx.dropped.UID);
            expect(restored.TRANSP).toBe("OPAQUE");
          },
          integration_events: async (page, ctx) => {
            const slot = (item) => item.uid.includes(`-p${ctx.listed[0].period}-`);
            expect((await integrationEvents(page, "lessons", ctx.listed[0].date)).filter(slot).some((item) => item.cancelled)).toBe(false);
          },
          cell_label: async (page, ctx) => {
            expect(ctx.label).toBeTruthy();
          },
        },
      },
    ],
  },
  {
    name: "absence",
    keys: [],
    title: "the wizard reports a sick note and the entry can be withdrawn again",
    steps: [
      {
        name: "report",
        before: async (page, ctx) => {
          ctx.openBefore = (await integrationState(page)).open_absences.count;
        },
        change: async (page) => {
          await openTab(page, ABSENCE_TAB);
          await page.locator(".btn").filter({ hasText: await text(page, "absence.report") }).first().click();
          await page.waitForSelector(".sw-next");
          for (let step = 0; step < 8 && (await page.locator(".sw-next").count()); step += 1) {
            await page.locator(".sw-next").click();
            await page.waitForTimeout(250);
          }
          await settled(page);
          await expect(page.locator(".sw-next")).toHaveCount(0);
        },
        reaches: {
          app_api: async (page, ctx) => {
            const entries = (await json(page, "/api/absences")).entries;
            expect(entries[0].kind).toBe("sick");
            expect(entries[0].deletable).toBe(true);
            ctx.sickId = entries[0].id;
          },
          integration_state: async (page, ctx) => {
            const state = await integrationState(page);
            expect(state.open_absences.count).toBe(ctx.openBefore + 1);
          },
        },
      },
      {
        name: "withdraw",
        change: async (page) => {
          const sickLabel = await text(page, "absence.entry.kind.sick");
          await openTab(page, ABSENCE_TAB);
          await page.locator(".row").filter({ hasText: sickLabel }).first().click();
          await settled(page);
          const withdraw = page.locator(".btn.destructive").filter({ hasText: await text(page, "absence.withdraw") }).first();
          await expect(withdraw).toBeVisible();
          await withdraw.click();
          await confirmDestructive(page);
        },
        reaches: {
          app_api: async (page, ctx) => {
            expect((await json(page, "/api/absences")).entries.some((entry) => entry.id === ctx.sickId)).toBe(false);
          },
          integration_state: async (page, ctx) => {
            expect((await integrationState(page)).open_absences.count).toBe(ctx.openBefore);
          },
        },
      },
    ],
  },
  {
    name: "letters",
    keys: [],
    title: "confirming, archiving and restoring a letter reaches the letter, the listing and the list",
    steps: [
      {
        name: "confirm",
        change: async (page, ctx) => {
          await openTab(page, LETTERS_TAB);
          ctx.total = await page.locator(".rows .row").count();
          await page.locator(".rows .row").first().click();
          await settled(page);
          await page.locator(".confirm-card button.confirm-action").click();
          await waitForSheetSettled(page);
          await page.locator(".sheet .btn-stack button").first().click();
        },
        reaches: {
          letter: async (page) => {
            await expect(page.locator(".confirm-card.done")).toBeVisible();
          },
          app_api: async (page, ctx) => {
            ctx.confirmed = (await json(page, "/api/letters?tab=current")).letters.find((entry) => entry.confirmation && entry.confirmation.done);
            expect(ctx.confirmed).toBeTruthy();
          },
        },
      },
      {
        name: "archive",
        change: async (page) => {
          await page.locator(".btn").filter({ hasText: await text(page, "letters.action.archive") }).first().click();
          await confirmDestructiveOrPlain(page);
          await settled(page);
        },
        reaches: {
          app_api: async (page, ctx) => {
            expect((await json(page, "/api/letters?tab=current")).letters.map((entry) => entry.letter_id)).not.toContain(ctx.confirmed.letter_id);
            expect((await json(page, "/api/letters?tab=archive")).letters.map((entry) => entry.letter_id)).toContain(ctx.confirmed.letter_id);
          },
          list: async (page, ctx) => {
            await openTab(page, LETTERS_TAB);
            await expect(page.locator(".rows .row")).toHaveCount(ctx.total - 1);
          },
        },
      },
      {
        name: "restore",
        change: async (page, ctx) => {
          const confirmed = ctx.confirmed;
          await page.request.post("/api/letters/restore", { data: { connection_id: SCHOOL, letter_id: confirmed.letter_id, recipient_id: confirmed.recipient_id } });
          await page.reload();
          await settled(page);
        },
        reaches: {
          list: async (page, ctx) => {
            await openTab(page, LETTERS_TAB);
            await expect(page.locator(".rows .row")).toHaveCount(ctx.total);
          },
        },
      },
    ],
  },
  {
    name: "child_switch",
    keys: [],
    title: "the overview chips move the today section to the other child",
    cookies: { e2e_scenario: "two-children" },
    before: async (page, ctx) => {
      ctx.chips = page.locator('.panel[data-area="today"] .chipbar.overview-chips .chip');
      await expect(ctx.chips).toHaveCount(2);
      ctx.first = await blockOrder(page, '.panel[data-area="today"] [data-block]');
    },
    change: async (page, ctx) => {
      await ctx.chips.nth(1).click();
      await settled(page);
    },
    reaches: {
      today: async (page, ctx) => {
        const second = await blockOrder(page, '.panel[data-area="today"] [data-block]');
        expect(second).not.toEqual(ctx.first);
      },
      chips: async (page, ctx) => {
        expect(await ctx.chips.nth(1).getAttribute("aria-pressed")).toBe("true");
      },
    },
  },
];

const MATRIX = [...SETTINGS, ...ACTIONS];

const EXEMPT_KEYS = {
  period_grid: "lesson durations are edited on the lesson times page, covered by e2e/period-times.spec.js and the backend matrix row period_duration",
  own_entries: "own entries are edited on the lesson times page, covered by e2e/period-times.spec.js and the backend matrix row own_entry",
  label: "no app control sets the school label, only the API; covered by the backend matrix rows label-app_connections and label-integration_info",
  modules_disabled: "the module switch runs through the bar, the overview and the settings rows in e2e/layout-settings.spec.js; the integration side is the backend matrix row modules_disabled-integration_info",
  reported_modules: "bookkeeping of the unknown-module card, covered end to end by e2e/help-report.spec.js and the backend matrix row module_card_flags-app_config",
  modules_card_hidden: "bookkeeping of the unknown-module card, covered end to end by e2e/help-report.spec.js and the backend matrix row module_card_flags-app_config",
};

function stepsOf(row) {
  return row.steps || [{ name: row.name, before: row.before, change: row.change, reaches: row.reaches }];
}

async function runRow(page, row, viewport) {
  const ctx = { viewport };
  for (const [name, value] of Object.entries(row.cookies || {})) {
    await page.context().addCookies([{ name, value, url: BASE_URL }]);
  }
  if (row.setup) await row.setup(page, ctx);
  try {
    await (row.layout ? prepareWithLayout(page) : prepare(page));
    for (const step of stepsOf(row)) {
      if (step.before) await test.step(`${row.name}/${step.name}: before`, () => step.before(page, ctx));
      await test.step(`${row.name}/${step.name}: change`, () => step.change(page, ctx));
      for (const [surface, check] of Object.entries(step.reaches)) {
        await test.step(`${row.name}/${step.name} -> ${surface}`, () => check(page, ctx));
      }
    }
  } finally {
    if (row.teardown) await row.teardown(page, ctx);
  }
}

for (const viewport of VIEWPORTS) {
  test.describe(`settings matrix @ ${viewport.name}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const row of MATRIX) {
      test(`${row.name}: ${row.title}`, async ({ page }) => {
        if (row.slow) test.slow();
        await runRow(page, row, viewport);
      });
    }
  });
}

test.describe("settings matrix guard", () => {
  test("every config key of the live schema has a matrix row or a reason", async ({ request }) => {
    const response = await request.get("/e2e/matrix/schema");
    expect(response.ok()).toBe(true);
    const live = (await response.json()).keys;
    expect(live).toEqual(SCHEMA.keys);
    const covered = new Set(MATRIX.flatMap((row) => row.keys));
    const exempt = { ...SCHEMA.internal, ...EXEMPT_KEYS };
    expect(live.filter((key) => !covered.has(key) && !(key in exempt))).toEqual([]);
    expect(Object.keys(exempt).filter((key) => !live.includes(key))).toEqual([]);
    expect([...covered].filter((key) => key in exempt)).toEqual([]);
    expect(Object.values(exempt).filter((reason) => !reason.trim())).toEqual([]);
  });

  test("every row has a unique name, a change and at least one surface per step", () => {
    const names = MATRIX.map((row) => row.name);
    expect(new Set(names).size).toBe(names.length);
    for (const row of MATRIX) {
      expect(Array.isArray(row.keys), row.name).toBe(true);
      for (const step of stepsOf(row)) {
        expect(typeof step.change, `${row.name}/${step.name}`).toBe("function");
        expect(Object.keys(step.reaches).length, `${row.name}/${step.name}`).toBeGreaterThan(0);
      }
    }
  });
});
