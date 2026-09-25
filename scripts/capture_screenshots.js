const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const SCREENSHOT_DIR = path.join(ROOT, "docs", "screenshots");
const STATIC_PORT = process.env.CARD_HARNESS_PORT || "8377";
const FIXTURE_PORT = process.env.SCREENSHOT_E2E_PORT || "8198";
const CARD_EXTRA_DIR = process.env.CARD_EXTRA_DIR || "";
const CARD_EXTRA_VIEWS = [
  { file: "card-today.png", query: "view=today&child=alex&lang=de" },
  { file: "card-week.png", query: "view=week&child=alex&lang=de" },
];

const UI_LOCALE = "en-US";
const UI_LANGUAGE = "en";
const FIXTURE_LANGUAGE = "en";
const SHOWCASE_SCENARIO = "showcase";
const SCHOOL_TIMEZONE = "Europe/Berlin";
const SHOWCASE_TODAY_OFFSET = 2;
const FROZEN_HOUR = 9;
const FROZEN_MINUTE = 15;
const CARD_FROZEN_TIME = "2026-09-02T07:15:00Z";
const PHONE = { width: 390, height: 760 };
const DESKTOP = { width: 1440, height: 900 };
const DESKTOP_CROP_HEIGHT = 700;
const CARD_VIEWPORT = { width: 640, height: 700 };
const HERO_WORK_DIR = path.join(ROOT, "data-screenshots");
const HERO_CARD_QUERY = "blocks=today:compact,letters:compact,holidays&scene=showcase&names=Mia,Tom";
const HERO_CARD_SCALE = 2;
const HERO_VIEWPORT = { width: 1200, height: 700 };
const HERO_SCALE = 1.5;
const TAB = { overview: 0, timetable: 1, absence: 2, post: 3 };
const EXAM_CHILD_KEY = "a1b2c3d4:child-1";
const EXAM_DAY_OFFSET = 3;
const EXAM_PERIOD = 1;
const EXAM_SUBJECT = "MAT";
const EXAM_NAME = "Maths test";
const SETTLE_MS = 400;
const SHEET_SETTLE_MS = 600;

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function resolvePython() {
  const winVenv = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const posixVenv = path.join(ROOT, ".venv", "bin", "python");
  if (fs.existsSync(winVenv)) return winVenv;
  if (fs.existsSync(posixVenv)) return posixVenv;
  return process.platform === "win32" ? "python" : "python3";
}

function startStaticServer() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    const filePath = path.join(ROOT, decodeURIComponent(url.pathname));
    if (!filePath.startsWith(ROOT) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    const ext = path.extname(filePath);
    res.writeHead(200, { "Content-Type": CONTENT_TYPES[ext] || "application/octet-stream" });
    fs.createReadStream(filePath).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(Number(STATIC_PORT), "127.0.0.1", () => resolve(server));
  });
}

function startFixtureServer() {
  const dataDir = path.join(ROOT, "data-screenshots");
  fs.rmSync(dataDir, { recursive: true, force: true });
  const child = spawn(
    resolvePython(),
    ["-m", "uvicorn", "tests.e2e_fixture_app:create_server_app", "--factory", "--host", "127.0.0.1", "--port", FIXTURE_PORT],
    { cwd: path.join(ROOT, "backend"), env: { ...process.env, ISERV_E2E_DATA_DIR: dataDir } }
  );
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 30000;
    child.on("exit", (code) => {
      if (code) reject(new Error(`fixture server exited with code ${code}`));
    });
    (function poll() {
      http
        .get(`http://127.0.0.1:${FIXTURE_PORT}/`, (res) => {
          res.resume();
          resolve(child);
        })
        .on("error", () => {
          if (Date.now() > deadline) reject(new Error("fixture server did not start in time"));
          else setTimeout(poll, 300);
        });
    })();
  });
}

function isoDate(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function weekMonday() {
  const today = new Date();
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function dayOfWeek(offset) {
  const day = weekMonday();
  day.setDate(day.getDate() + offset);
  return day;
}

function zonedHour(epoch) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: SCHOOL_TIMEZONE, hour: "2-digit", hour12: false }).formatToParts(
    new Date(epoch)
  );
  return Number(parts.find((part) => part.type === "hour").value) % 24;
}

function frozenTime() {
  const day = dayOfWeek(SHOWCASE_TODAY_OFFSET);
  const guess = Date.UTC(day.getFullYear(), day.getMonth(), day.getDate(), FROZEN_HOUR, FROZEN_MINUTE);
  const shift = zonedHour(guess) - FROZEN_HOUR;
  return new Date(guess - shift * 3600000);
}

function fixtureCookie(name, value) {
  return { name, value, url: `http://127.0.0.1:${FIXTURE_PORT}` };
}

async function appContext(browser, options) {
  const context = await browser.newContext({
    viewport: options.viewport,
    deviceScaleFactor: options.scale,
    locale: UI_LOCALE,
    timezoneId: SCHOOL_TIMEZONE,
    colorScheme: options.dark ? "dark" : "light",
  });
  if (options.dark) await context.addInitScript(() => window.localStorage.setItem("theme", "dark"));
  const cookies = [fixtureCookie("e2e_lang", FIXTURE_LANGUAGE)];
  for (const [name, value] of Object.entries(options.cookies || {})) cookies.push(fixtureCookie(name, value));
  await context.addCookies(cookies);
  return context;
}

async function openApp(context) {
  const page = await context.newPage();
  await page.clock.install({ time: frozenTime() });
  await page.goto(`http://127.0.0.1:${FIXTURE_PORT}/`);
  await page.waitForSelector(".screen", { state: "attached", timeout: 15000 });
  await page.waitForSelector(".loading", { state: "detached", timeout: 15000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  const language = await page.evaluate(() => document.documentElement.getAttribute("lang"));
  if (language !== UI_LANGUAGE) throw new Error(`app language is ${language}, expected ${UI_LANGUAGE}`);
  return page;
}

async function openTab(page, index) {
  const rail = page.locator("nav.rail .rail-item");
  if (await rail.count()) await rail.nth(index).click();
  else await page.locator(".tabbar .tab").nth(index).click();
  await page.waitForSelector(".loading", { state: "detached", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(SETTLE_MS);
}

async function ensureExamMark(page) {
  const wanted = { child_key: EXAM_CHILD_KEY, date: isoDate(dayOfWeek(EXAM_DAY_OFFSET)), period: EXAM_PERIOD, subject_code: EXAM_SUBJECT, name: EXAM_NAME };
  const outcome = await page.evaluate(async (mark) => {
    const base = new URL("api/marks", document.baseURI).toString();
    const listed = await fetch(base).then((response) => response.json());
    const present = (listed.marks || []).some(
      (entry) => entry.child_key === mark.child_key && entry.date === mark.date && Number(entry.period) === mark.period
    );
    if (present) return { ok: true };
    const response = await fetch(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mark) });
    return { ok: response.ok, status: response.status };
  }, wanted);
  if (!outcome.ok) throw new Error(`exam mark was refused with status ${outcome.status}`);
  await page.reload();
  await page.waitForSelector(".loading", { state: "detached", timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(SETTLE_MS);
}

async function phoneShot(browser, file, options, drive) {
  const context = await appContext(browser, { viewport: PHONE, scale: 2, dark: options.dark, cookies: options.cookies });
  const page = await openApp(context);
  await drive(page);
  await page.screenshot({ path: path.join(options.dir || SCREENSHOT_DIR, file) });
  await context.close();
}

async function driveOverview(page) {
  await openTab(page, TAB.overview);
  const chips = page.locator(".chipbar .chip");
  if (await chips.count()) await chips.first().click();
  await page.waitForTimeout(SETTLE_MS);
}

async function driveTimetableOwnEntries(page) {
  await ensureExamMark(page);
  await openTab(page, TAB.timetable);
  await page.waitForSelector(".tt-cell.marked", { timeout: 10000 });
  await page.waitForSelector(".tt-strip", { timeout: 10000 });
  await page.waitForSelector(".tt-own", { timeout: 10000 });
  await page.waitForTimeout(SETTLE_MS);
}

async function driveAbsenceReview(page) {
  await openTab(page, TAB.absence);
  await page.getByRole("button", { name: await page.evaluate(() => window.t("absence.report")), exact: true }).click();
  await page.waitForSelector(".sw-content", { timeout: 10000 });
  await page.getByRole("button", { name: await page.evaluate(() => window.t("absence.type.sick.label")), exact: true }).click();
  await page.waitForTimeout(SETTLE_MS);
  for (let step = 0; step < 3; step += 1) {
    await page.locator(".sw-next").click();
    await page.waitForTimeout(SETTLE_MS);
  }
  await page.waitForSelector(".sw-facts", { timeout: 10000 });
  await page.waitForTimeout(SETTLE_MS);
}

async function driveTwoSchoolsPost(page) {
  await openTab(page, TAB.post);
  await page.waitForSelector(".chipbar.school-filter", { timeout: 15000 });
  await page.waitForTimeout(SETTLE_MS);
}

async function capturePhoneScreens(browser) {
  const showcase = { e2e_scenario: SHOWCASE_SCENARIO };
  for (const dark of [false, true]) {
    const suffix = dark ? "-dark" : "";
    await phoneShot(browser, `overview-today${suffix}.png`, { dark, cookies: showcase }, driveOverview);
    await phoneShot(browser, `hero-phone${suffix}.png`, { dark, cookies: showcase, dir: HERO_WORK_DIR }, driveTimetableOwnEntries);
    await phoneShot(browser, `absence-wizard-review${suffix}.png`, { dark, cookies: showcase }, driveAbsenceReview);
    await phoneShot(browser, `two-schools-post${suffix}.png`, { dark, cookies: { e2e_schools: "2" } }, driveTwoSchoolsPost);
  }
}

async function captureDesktopTimetable(browser) {
  const context = await appContext(browser, { viewport: DESKTOP, scale: 1, dark: false, cookies: { e2e_scenario: SHOWCASE_SCENARIO } });
  const page = await openApp(context);
  await openTab(page, TAB.timetable);
  await page.waitForSelector(".tt-multi", { timeout: 10000 });
  await page.waitForTimeout(SETTLE_MS);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "desktop-timetable.png"),
    clip: { x: 0, y: 0, width: DESKTOP.width, height: DESKTOP_CROP_HEIGHT },
  });
  await context.close();
}

async function captureCard(browser, query, file, dark, scale = 1, time = CARD_FROZEN_TIME) {
  const page = await browser.newPage({ viewport: CARD_VIEWPORT, deviceScaleFactor: scale, colorScheme: dark ? "dark" : "light" });
  await page.clock.install({ time: new Date(time) });
  await page.goto(`http://127.0.0.1:${STATIC_PORT}/scripts/card-harness.html?${query}`);
  await page.waitForSelector("body[data-ready='true']", { timeout: 10000 });
  await page.evaluate(() => document.fonts.ready);
  const card = page.locator("ranzenpost-card");
  await card.screenshot({ path: file });
  await page.close();
}

async function captureHeroCards(browser) {
  fs.mkdirSync(HERO_WORK_DIR, { recursive: true });
  const query = `${HERO_CARD_QUERY}&today=${isoDate(dayOfWeek(SHOWCASE_TODAY_OFFSET))}`;
  await captureCard(browser, query, path.join(HERO_WORK_DIR, "hero-card.png"), false, HERO_CARD_SCALE, frozenTime());
  await captureCard(browser, `${query}&theme=dark`, path.join(HERO_WORK_DIR, "hero-card-dark.png"), true, HERO_CARD_SCALE, frozenTime());
}

async function composeHero(browser) {
  for (const dark of [false, true]) {
    const page = await browser.newPage({ viewport: HERO_VIEWPORT, deviceScaleFactor: HERO_SCALE, colorScheme: dark ? "dark" : "light" });
    await page.goto(`http://127.0.0.1:${STATIC_PORT}/scripts/readme-hero.html${dark ? "?theme=dark" : ""}`);
    await page.waitForSelector("body[data-ready='true'], body[data-error]", { timeout: 10000 });
    const failure = await page.evaluate(() => document.body.getAttribute("data-error"));
    if (failure) throw new Error(failure);
    await page.locator(".stage").screenshot({ path: path.join(SCREENSHOT_DIR, `hero${dark ? "-dark" : ""}.png`), omitBackground: true });
    await page.close();
  }
}

async function captureCardExtras(browser) {
  if (!CARD_EXTRA_DIR) return;
  fs.mkdirSync(CARD_EXTRA_DIR, { recursive: true });
  for (const view of CARD_EXTRA_VIEWS) {
    await captureCard(browser, view.query, path.join(CARD_EXTRA_DIR, view.file), false);
  }
}

async function main() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const staticServer = await startStaticServer();
  const fixtureServer = await startFixtureServer();
  const browser = await chromium.launch();
  try {
    await captureHeroCards(browser);
    await captureCardExtras(browser);
    await captureDesktopTimetable(browser);
    await capturePhoneScreens(browser);
    await composeHero(browser);
  } finally {
    await browser.close();
    fixtureServer.kill();
    staticServer.close();
  }
  const written = fs.readdirSync(SCREENSHOT_DIR).filter((name) => name.endsWith(".png")).sort();
  console.log(`wrote ${written.length} files to docs/screenshots: ${written.join(", ")}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
