const { test, expect } = require("@playwright/test");
const { goto, openArea, checkHorizontalOverflow } = require("./helpers");

const BASE_URL = `http://127.0.0.1:${process.env.E2E_PORT || "8199"}`;

const VIEWPORTS = [
  { name: "360", width: 360, height: 800 },
  { name: "430", width: 430, height: 932 },
  { name: "768", width: 768, height: 1024 },
  { name: "1024", width: 1024, height: 768 },
  { name: "1440", width: 1440, height: 900 },
];
const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ar", locale: "ar" },
];
const SUBJECTS = [
  { key: "normal", cookies: [] },
  { key: "long", cookies: [{ name: "e2e_long_subjects", value: "1" }] },
];
const TIERS = { name: [72, 44], room: [96, 64], teacher: [128, 80] };
const EDGE = 1;
const MIN_NAME_PX = 12;
const MIN_DETAIL_PX = 11;

function reaches(box, [width, height]) {
  return box.width >= width && box.height >= height;
}

function nearEdge(box) {
  return Object.values(TIERS).some(([width, height]) => Math.abs(box.width - width) < EDGE || Math.abs(box.height - height) < EDGE);
}

async function tiles(page) {
  return page.locator(".tt .tt-cell[data-subject]:not(.compact)").evaluateAll((cells) =>
    cells.map((cell) => {
      const style = getComputedStyle(cell);
      const box = {
        width: cell.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
        height: cell.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom),
      };
      const outer = cell.getBoundingClientRect();
      const part = (selector) => {
        const node = cell.querySelector(selector);
        if (!node) return null;
        const shown = getComputedStyle(node).display !== "none";
        const rect = node.getBoundingClientRect();
        return {
          shown,
          inside: !shown || (rect.left >= outer.left - 1 && rect.right <= outer.right + 1 && rect.top >= outer.top - 1 && rect.bottom <= outer.bottom + 1),
          font: parseFloat(getComputedStyle(node).fontSize),
        };
      };
      return { box, sub: part(".sub"), name: part(".lname"), room: part(".lroom"), teacher: part(".lteacher"), label: cell.getAttribute("aria-label") };
    })
  );
}

for (const viewport of VIEWPORTS) {
  for (const lang of LANGUAGES) {
    for (const subjects of SUBJECTS) {
      test.describe(`lesson tiles ${viewport.name} ${lang.key} ${subjects.key}`, () => {
        test.use({ viewport: { width: viewport.width, height: viewport.height }, locale: lang.locale });

        test(`${viewport.name}/${lang.key}/${subjects.key} shows as much of each lesson as its tile holds`, async ({ page }) => {
          await page.context().addCookies([
            { name: "e2e_lang", value: lang.key, url: BASE_URL },
            ...subjects.cookies.map((cookie) => ({ ...cookie, url: BASE_URL })),
          ]);
          await goto(page);
          await openArea(page, "timetable");
          await page.waitForSelector(".tt .tt-cell[data-subject]");
          const label = `${viewport.name}/${lang.key}/${subjects.key}`;

          const overflow = await checkHorizontalOverflow(page);
          expect(overflow.overflow, `${label}: page scrolls sideways`).toBe(false);

          const found = await tiles(page);
          expect(found.length, `${label}: no lesson tiles`).toBeGreaterThan(0);
          for (const [index, tile] of found.entries()) {
            const where = `${label} tile ${index} ${JSON.stringify(tile.box)}`;
            expect(tile.label, `${where}: no accessible name`).toBeTruthy();
            for (const part of [tile.sub, tile.name, tile.room, tile.teacher]) {
              if (part) expect(part.inside, `${where}: text sticks out of its tile`).toBe(true);
            }
            if (nearEdge(tile.box)) continue;
            const named = reaches(tile.box, TIERS.name);
            expect(tile.name.shown, `${where}: name shown`).toBe(named);
            expect(tile.sub.shown, `${where}: code shown`).toBe(!named);
            if (tile.room) expect(tile.room.shown, `${where}: room shown`).toBe(reaches(tile.box, TIERS.room));
            if (tile.teacher) expect(tile.teacher.shown, `${where}: teacher shown`).toBe(reaches(tile.box, TIERS.teacher));
            if (tile.name.shown) expect(tile.name.font, `${where}: name font`).toBeGreaterThanOrEqual(MIN_NAME_PX);
            for (const part of [tile.room, tile.teacher]) {
              if (part && part.shown) expect(part.font, `${where}: detail font`).toBeGreaterThanOrEqual(MIN_DETAIL_PX);
            }
          }
          if (viewport.width >= 768) {
            expect(found.some((tile) => tile.name.shown), `${label}: no tile shows a subject name`).toBe(true);
          }
        });
      });
    }
  }
}

test.describe("cancelled lessons in large tiles", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("say Entfällt in the warning colour", async ({ page }) => {
    await page.context().addCookies([{ name: "e2e_timetable_source", value: "time-table-changes", url: BASE_URL }]);
    await goto(page);
    await openArea(page, "timetable");
    const label = page.locator(".tt .tt-cell.out .room").first();
    await expect(label).toBeVisible();
    const colours = await label.evaluate((node) => {
      const probe = document.createElement("span");
      probe.style.color = "var(--danger)";
      node.parentElement.appendChild(probe);
      const wanted = getComputedStyle(probe).color;
      probe.remove();
      return { shown: getComputedStyle(node).color, wanted };
    });
    expect(colours.shown).toBe(colours.wanted);
  });
});

test.describe("a marked lesson in a large tile", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("shows the mark in the tile's own text colour", async ({ page }) => {
    await goto(page);
    await openArea(page, "timetable");
    const cell = page.locator(".tt .tt-cell.subject[data-subject]:not(.compact):not(.marked)").first();
    const uid = await cell.getAttribute("aria-label");
    await cell.click();
    await page.locator(".sheet-foot .mark-add").click();
    await page.locator(".sheet-body .inp").fill("Vocabulary");
    await page.locator(".sheet-foot .btn").click();
    await expect(page.locator(".sheet")).toHaveCount(0);
    const marked = page.locator(".tt .tt-cell.subject.marked:not(.compact)").first();
    await expect(marked).toBeVisible();
    const look = await marked.evaluate((node) => {
      const flag = node.querySelector(".exam-flag");
      const icon = flag.querySelector("svg").getBoundingClientRect();
      return { flag: getComputedStyle(flag).color, ink: getComputedStyle(node).color, fill: getComputedStyle(node).backgroundColor, ring: getComputedStyle(node).boxShadow, size: Math.round(icon.width) };
    });
    expect(look.flag, `mark on ${uid}`).toBe(look.ink);
    expect(look.flag).not.toBe(look.fill);
    expect(look.ring).toContain(look.ink);
    expect(look.size).toBe(16);
  });
});
