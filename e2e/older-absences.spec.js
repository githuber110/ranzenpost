const path = require("path");
const { test, expect } = require("@playwright/test");
const { goto, checkHorizontalOverflow } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;
const SHOTS = process.env.OLDER_ABSENCE_SHOTS || "";

function olderOverview(entries) {
  return {
    source: "older_page",
    children: [{ id: "c-mia", name: "Mia Muster" }, { id: "c-tom", name: "Tom Beispiel" }],
    types: [],
    deregister_options: [],
    periods: [],
    period_labels: [],
    rules: {},
    day_options: { from: [], till: [] },
    leave_min_days: 0,
    entries: entries || [],
    export: true,
    withheld: 1,
    phones: [],
  };
}

const PENDING = {
  id: "older:pending:1", kind: "absence", source: "older_page", label_key: "absence.entry.kind.absence",
  from_date: "2126-10-20", till_date: "2126-10-20", student_id: "c-mia", status: "unconfirmed", unconfirmed: true,
  deletable: false, locked_reason_key: "api.absence.older.pending", technical: { id: "", created_at: "", class_code: "" },
};

function pendingOf(payload) {
  return Object.assign({}, PENDING, { student_id: payload.student_id, from_date: payload.from_date, till_date: payload.till_date });
}

const FORM = {
  profiles: [{ id: "c-mia", name: "Mia Muster" }, { id: "c-tom", name: "Tom Beispiel" }],
  profile_options: 2,
  till: true,
  times: false,
  whole_day: true,
  min: "",
  reason: { name: "absence[comment]", type: "textarea", label: "Kommentar", required: false, options: [] },
  kind: null,
  extras: [{ name: "absence[phone]", type: "text", label: "Telefon für Rückfragen", required: true, options: [] }],
};

async function openAbsences(page, theme, posted, interrupted) {
  await page.context().clearCookies();
  await page.context().addCookies([
    { name: "e2e_lang", value: "de", url: BASE_URL },
    { name: "e2e_modules", value: "all", url: BASE_URL },
  ]);
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem("theme", value);
    } catch (error) {}
  }, theme);
  let reported = false;
  await page.route("**/api/absences?**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(olderOverview(reported ? [pendingOf(posted[posted.length - 1])] : [])) })
  );
  await page.route("**/api/absences/older-form?**", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, form: FORM }) }));
  await page.route("**/api/absences", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    posted.push(route.request().postDataJSON());
    if (interrupted) return route.abort("timedout");
    reported = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: false, uncertain: true, message_key: "api.absence.older.uncertain" }) });
  });
  await goto(page, "/?view=absence");
  await expect(page.locator("#app")).toHaveAttribute("data-view", "absence", { timeout: 15000 });
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + ".png") });
}

async function noHandOff(page) {
  const links = await page.locator("main a[href], .sw a[href], .sheet a[href]").evaluateAll((nodes) =>
    nodes.map((node) => ({ href: node.getAttribute("href"), target: node.getAttribute("target") }))
  );
  expect(links.filter((link) => String(link.href || "").includes("/iserv/") || link.target === "_blank")).toEqual([]);
}

for (const theme of ["light", "dark"]) {
  for (const width of [390, 1024]) {
    test.describe(`older absence report ${theme} ${width}px`, () => {
      test.use({ viewport: { width, height: 844 }, colorScheme: theme });

      test("reports an absence in the app without sending anyone to IServ", async ({ page }) => {
        const posted = [];
        await openAbsences(page, theme, posted);
        await expect(page.locator("a.absence-older-open")).toHaveCount(0);
        await expect(page.getByText("Einige Einträge passen zu keinem Profil", { exact: false })).toBeVisible();
        await expect(page.getByText("Aktuelle, zukünftige und vergangene Meldungen erscheinen hier.")).toBeVisible();
        await expect(page.getByText("Vergangene Krankmeldungen blendet IServ", { exact: false })).toHaveCount(0);
        await expect(page.getByRole("button", { name: "Als CSV exportieren" })).toBeVisible();
        await noHandOff(page);
        await shot(page, `list-${theme}-${width}`);
        await page.getByRole("button", { name: "Abwesenheit melden" }).click();
        await expect(page.locator(".sw-question")).toBeVisible();
        await shot(page, `child-${theme}-${width}`);
        await page.locator(".sw-body .opt").filter({ hasText: "Tom" }).click();
        await page.locator(".sw-next").click();
        await expect(page.locator(".sw-body input[type=date]")).toBeVisible();
        await shot(page, `when-${theme}-${width}`);
        await page.locator(".sw-next").click();
        await page.locator(".sw-body textarea").fill("Fieber");
        await shot(page, `reason-${theme}-${width}`);
        await page.locator(".sw-next").click();
        await page.locator(".sw-body input.inp").fill("0123 456");
        await shot(page, `details-${theme}-${width}`);
        await page.locator(".sw-next").click();
        await expect(page.locator(".sw-facts")).toContainText("Fieber");
        await expect(page.locator(".sw-facts")).toContainText("0123 456");
        await noHandOff(page);
        await shot(page, `review-${theme}-${width}`);
        await page.locator(".sw-next").click();
        await expect.poll(() => posted.length).toBe(1);
        expect(posted[0]).toMatchObject({ type: "absence", student_id: "c-tom", whole_day: true, reason: "Fieber", extra: { "absence[phone]": "0123 456" } });
        await expect(page.locator(".sw-question")).toHaveCount(0);
        await expect(page.locator(".row .tag.warn")).toHaveText("Unbestätigt");
        await noHandOff(page);
        await shot(page, `unconfirmed-${theme}-${width}`);
        const overflow = await checkHorizontalOverflow(page);
        expect(overflow.overflow, JSON.stringify(overflow)).toBe(false);
      });

      test("a send that breaks off stays unconfirmed and cannot be sent twice", async ({ page }) => {
        const posted = [];
        await openAbsences(page, theme, posted, true);
        const send = async () => {
          await page.getByRole("button", { name: "Abwesenheit melden" }).click();
          await page.locator(".sw-body .opt").filter({ hasText: "Mia" }).click();
          await page.locator(".sw-next").click();
          await page.locator(".sw-next").click();
          await page.locator(".sw-next").click();
          await page.locator(".sw-body input.inp").fill("0123");
          await page.locator(".sw-next").click();
          await page.locator(".sw-next").click();
        };
        await send();
        await expect.poll(() => posted.length).toBe(1);
        await expect(page.locator(".sw-question")).toHaveCount(0);
        await expect(page.locator(".row .tag.warn")).toHaveText("Unbestätigt");
        await shot(page, `interrupted-${theme}-${width}`);
        await send();
        await expect(page.getByText("Noch einmal senden?")).toBeVisible();
        await shot(page, `send-again-${theme}-${width}`);
        await page.locator(".btn-stack .btn.ghost").click();
        await expect(page.locator(".sw-status")).toContainText("schon eine Meldung da oder unterwegs");
        expect(posted.length).toBe(1);
        await noHandOff(page);
      });

      test("the school app sick note flow for comparison", async ({ page }) => {
        test.skip(!SHOTS, "comparison screenshots only");
        await page.context().clearCookies();
        await page.context().addCookies([
          { name: "e2e_lang", value: "de", url: BASE_URL },
          { name: "e2e_modules", value: "all", url: BASE_URL },
        ]);
        await page.addInitScript((value) => {
          try {
            window.localStorage.setItem("theme", value);
          } catch (error) {}
        }, theme);
        await goto(page, "/?view=absence");
        await page.getByRole("button", { name: "Abwesenheit melden" }).click();
        await expect(page.locator(".sw-question")).toBeVisible();
        await shot(page, `sick-first-${theme}-${width}`);
      });
    });
  }
}
