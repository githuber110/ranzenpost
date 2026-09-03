const { test, expect } = require("@playwright/test");
const { goto } = require("./helpers");

const LANGUAGES = [
  { key: "de", locale: "de-DE" },
  { key: "ru", locale: "ru-RU" },
  { key: "ar", locale: "ar" },
];

const VIEWPORTS = [
  { name: "320x568", width: 320, height: 568 },
  { name: "390x844", width: 390, height: 844 },
];

const ROOT_SIZES = [16, 20];
const SEPARATOR = String.fromCharCode(10);

const ALL_RULES = {
  sick_by_lesson: true,
  sick_comment: true,
  sick_cutoff: "07:30",
  sick_cutoff_message: "",
  duty_hint: "",
  leave_min_days: 3,
  daycare_min_days: 0,
  daycare_cutoff: "08:00",
  daycare_reason_required: true,
  daycare_custom_pickup: false,
  daycare_pickup_times: ["13:30", "14:30", "15:30"],
};

const NO_RULES = {
  sick_by_lesson: false,
  sick_comment: false,
  sick_cutoff: "",
  sick_cutoff_message: "",
  duty_hint: "",
  leave_min_days: 0,
  daycare_min_days: 0,
  daycare_cutoff: "",
  daycare_reason_required: false,
  daycare_custom_pickup: true,
  daycare_pickup_times: [],
};

function isoDay(offset) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const pad = (value) => String(value).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

function children(count) {
  const names = ["Mia Musterkind", "Ben Musterkind", "Alexandra Musterkind", "Konstantin Musterkind"];
  const classes = ["3b", "1a", "10c", "7d"];
  return Array.from({ length: count }, (unused, index) => ({
    id: `child-${index + 1}`,
    name: names[index],
    class_name: classes[index],
  }));
}

function payload({ rules, types, kids, targets }) {
  return {
    children: children(kids),
    types,
    deregister_options: targets,
    periods: Array.from({ length: 6 }, (unused, index) => ({ number: index + 1, name: `${index + 1}. Stunde` })),
    period_labels: Array.from({ length: 6 }, (unused, index) => ({
      number: index + 1,
      label: `${index + 1}. Stunde ${7 + index}:00 - ${7 + index}:45`,
    })),
    rules,
    day_options: {
      from: [
        { value: isoDay(0), label_key: "absence.day.today" },
        { value: isoDay(1), label_key: "absence.day.tomorrow" },
      ],
      till: Array.from({ length: 6 }, (unused, index) => ({ value: isoDay(index), label: "", label_key: "" })),
    },
    leave_min_days: rules.leave_min_days,
    entries: [],
    phones: [],
    notes: [],
  };
}

const CONFIGURATIONS = [
  {
    name: "max-4-kids",
    data: { rules: ALL_RULES, types: ["sick", "leave", "deregister", "daycare"], kids: 4, targets: ["bus", "lunch", "kindergarten"] },
  },
  {
    name: "min-1-kid",
    data: { rules: NO_RULES, types: ["sick"], kids: 1, targets: [] },
  },
  {
    name: "mid-2-kids",
    data: { rules: ALL_RULES, types: ["sick", "leave", "deregister"], kids: 2, targets: ["bus", "lunch"] },
  },
];

const WALKS = {
  sick: [
    { set: {}, steps: ["type", "child", "sickWhen", "sickHours", "review"] },
    { set: { hours_mode: "byLesson", from_period: "1", till_period: "6" }, steps: ["sickHours"] },
    { set: {}, steps: ["sickComment"] },
  ],
  leave: [
    { set: { body: "Begruendung" }, steps: ["type", "child", "leaveFrom", "leaveDayTime", "leaveSubject", "leaveBody", "review"] },
    { set: { duration: "more", body: "Begruendung" }, steps: ["leaveTill"] },
    { set: { time_mode: "custom", body: "Begruendung" }, steps: ["leaveTimes", "leaveDayTime"] },
    { set: { body: "Begruendung" }, steps: ["leaveAttachments"] },
  ],
  deregister: [
    { set: {}, steps: ["type", "child", "deregisterTarget", "deregisterWhen", "review"] },
    { set: { repeat: "weekly", repeat_until: isoDay(21) }, steps: ["repeatUntil"] },
  ],
  daycare: [
    { set: { reason: "Grund" }, steps: ["type", "child", "daycareKind", "daycareWhen", "daycareReason", "review"] },
    { set: { daycare_kind: "early_end", pickup_time: "13:30", reason: "Grund" }, steps: ["daycareKind"] },
    { set: { repeat: "weekly", repeat_until: isoDay(21), reason: "Grund" }, steps: ["repeatUntil"] },
  ],
};

async function installPayload(page, data) {
  const body = JSON.stringify(payload(data));
  await page.route("**/api/absences", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({ status: 200, contentType: "application/json", body });
  });
}

async function setRootFont(page, size) {
  await page.addStyleTag({ content: `html { font-size: ${size}px !important; }` });
}

async function forceSafeAreas(page) {
  await page.addStyleTag({ content: ":root { --safe-t: 47px; --safe-b: 34px; }" });
}

async function openWizard(page, type, kids) {
  return page.evaluate(
    ({ type, kids }) => {
      state.view = "absence";
      startAbsenceForm(type);
      state.absenceForm.student_id = String(state.absence.data.children[kids - 1].id);
      absenceFlow.render();
      return absenceCurrentPath();
    },
    { type, kids }
  );
}

async function setCompact(page, on) {
  await page.evaluate((on) => {
    const root = document.querySelector(".sw");
    if (root) root.classList.toggle("compact", on);
  }, on);
}

async function measureStep(page, stepId, patch) {
  return page.evaluate(
    async ({ stepId, patch }) => {
      Object.assign(state.absenceForm, patch || {});
      absenceFlow.render();
      absenceFlow.go(stepId);
      await new Promise((resolve) => requestAnimationFrame(() => resolve()));
      const root = document.querySelector(".sw");
      if (!root) return { missing: true, stepId };
      const content = root.querySelector(".sw-content");
      const body = root.querySelector(".sw-body");
      const progress = root.querySelector(".sw-progress");
      const next = root.querySelector(".sw-next");
      const page = document.scrollingElement || document.documentElement;
      const rect = next.getBoundingClientRect();
      return {
        stepId,
        reached: root.getAttribute("data-step"),
        contentOverflow: content.scrollHeight - content.clientHeight,
        bodyOverflow: body.scrollHeight - body.clientHeight,
        progressOverflow: progress.scrollWidth - progress.clientWidth,
        pageOverflow: page.scrollWidth - page.clientWidth,
        rootOverflow: root.scrollHeight - root.clientHeight,
        nextTop: Math.round(rect.top),
        nextBottom: Math.round(rect.bottom),
        nextHeight: Math.round(rect.height),
        viewport: window.innerHeight,
      };
    },
    { stepId, patch }
  );
}

function judge(result, label, failures) {
  if (result.missing) {
    failures.push(`${label}: wizard shell not mounted`);
    return;
  }
  if (result.reached !== result.stepId) {
    failures.push(`${label}: wizard refused the step, landed on ${result.reached}`);
    return;
  }
  if (result.contentOverflow > 1) failures.push(`${label}: step area scrolls by ${result.contentOverflow}px`);
  if (result.bodyOverflow > 1) failures.push(`${label}: step body scrolls by ${result.bodyOverflow}px`);
  if (result.progressOverflow > 1) failures.push(`${label}: progress row overflows by ${result.progressOverflow}px`);
  if (result.pageOverflow > 1) failures.push(`${label}: page scrolls sideways by ${result.pageOverflow}px`);
  if (result.rootOverflow > 1) failures.push(`${label}: wizard shell scrolls by ${result.rootOverflow}px`);
  if (result.nextHeight < 44) failures.push(`${label}: next button is only ${result.nextHeight}px tall`);
  if (result.nextBottom > result.viewport + 1) {
    failures.push(`${label}: next button ends at ${result.nextBottom}px, viewport is ${result.viewport}px`);
  }
  if (result.nextTop < -1) failures.push(`${label}: next button starts above the viewport at ${result.nextTop}px`);
}

for (const viewport of VIEWPORTS) {
  for (const size of ROOT_SIZES) {
    test.describe(`wizard fit @ ${viewport.name} / ${size}px root`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height } });

      for (const language of LANGUAGES) {
        test.describe(language.key, () => {
          test.use({ locale: language.locale });

          test(`every absence wizard step fits without scrolling (${language.key})`, async ({ page }) => {
            const failures = [];
            for (const configuration of CONFIGURATIONS) {
              await installPayload(page, configuration.data);
              await goto(page);
              await setRootFont(page, size);
              await page.evaluate(() => document.fonts.ready);

              for (const type of configuration.data.types) {
                const path = await openWizard(page, type, configuration.data.kids);
                for (const walk of WALKS[type]) {
                  for (const stepId of walk.steps) {
                    const inPath = path.includes(stepId);
                    const conditional = walk.set && Object.keys(walk.set).length > 0;
                    if (!inPath && !conditional && stepId !== "sickComment" && stepId !== "leaveAttachments") continue;
                    if (stepId === "type" && !path.includes("type")) continue;
                    if (stepId === "child" && !path.includes("child")) continue;
                    if (stepId === "daycareReason" && !path.includes("daycareReason")) continue;
                    if (stepId === "sickComment" && !configuration.data.rules.sick_comment) continue;
                    if (stepId === "sickPeriods" && !configuration.data.rules.sick_by_lesson) continue;
                    if (stepId === "deregisterTarget" && configuration.data.targets.length === 1) continue;
                    const label = `${language.key}/${viewport.name}/${size}px/${configuration.name}/${type}/${stepId}`;
                    judge(await measureStep(page, stepId, walk.set), label, failures);
                  }
                }
              }
            }
            expect(failures, failures.join("\n")).toEqual([]);
          });
        });
      }
    });
  }
}

test.describe("wizard fit with the iOS safe areas biting", () => {
  test.use({ viewport: { width: 320, height: 568 } });

  for (const language of LANGUAGES) {
    test.describe(language.key, () => {
      test.use({ locale: language.locale });

      test(`the prepared compensation keeps every step scroll-free (${language.key})`, async ({ page }) => {
        const failures = [];
        await installPayload(page, CONFIGURATIONS[0].data);
        await goto(page);
        await setRootFont(page, 20);
        await forceSafeAreas(page);
        await page.evaluate(() => document.fonts.ready);
        let compensated = 0;
        for (const type of CONFIGURATIONS[0].data.types) {
          const path = await openWizard(page, type, CONFIGURATIONS[0].data.kids);
          for (const walk of WALKS[type]) {
            for (const stepId of walk.steps) {
              if (stepId === "child" && !path.includes("child")) continue;
              const label = `safe-area/${language.key}/${type}/${stepId}`;
              judge(await measureStep(page, stepId, walk.set), label, failures);
              if (await page.evaluate(() => document.querySelector(".sw").classList.contains("tight"))) {
                compensated += 1;
              }
            }
          }
        }
        expect(failures, failures.join(SEPARATOR)).toEqual([]);
        expect(compensated).toBeGreaterThanOrEqual(0);
      });
    });
  }

  test.describe("ru", () => {
    test.use({ locale: "ru-RU" });

    test("the compensation really engages where the budget runs out, and only there", async ({ page }) => {
      await installPayload(page, CONFIGURATIONS[0].data);
      await goto(page);
      await setRootFont(page, 20);
      await page.evaluate(() => document.fonts.ready);

      const relaxed = await tightFlags(page);
      expect(relaxed).toEqual({ sickWhen: false, sickHours: false, review: false });

      await forceSafeAreas(page);
      const squeezed = await tightFlags(page);
      expect(squeezed.sickWhen).toBe(true);
      expect(squeezed.sickHours).toBe(false);
    });
  });
});

async function tightFlags(page) {
  await openWizard(page, "sick", CONFIGURATIONS[0].data.kids);
  const flags = {};
  for (const stepId of ["sickWhen", "sickHours", "review"]) {
    await measureStep(page, stepId, {});
    flags[stepId] = await page.evaluate(() => document.querySelector(".sw").classList.contains("tight"));
  }
  return flags;
}

test.describe("wizard fit with an open keyboard", () => {
  test.use({ viewport: { width: 320, height: 308 }, locale: "de-DE" });

  test("every text step still fits when the keyboard eats the screen", async ({ page }) => {
    const failures = [];
    await installPayload(page, CONFIGURATIONS[0].data);
    await goto(page);
    await setRootFont(page, 20);
    const cases = [
      ["sick", ["sickComment"]],
      ["leave", ["leaveSubject", "leaveBody", "leaveAttachments"]],
      ["daycare", ["daycareReason"]],
    ];
    for (const [type, steps] of cases) {
      await openWizard(page, type, CONFIGURATIONS[0].data.kids);
      for (const stepId of steps) {
        await measureStep(page, stepId, { body: "Begruendung", reason: "Grund" });
        await setCompact(page, true);
        judge(await measureStep(page, stepId, { body: "Begruendung", reason: "Grund" }), `compact/${type}/${stepId}`, failures);
      }
    }
    expect(failures, failures.join(SEPARATOR)).toEqual([]);
  });
});

test.describe("wizard fit in landscape", () => {
  test.use({ viewport: { width: 568, height: 320 }, locale: "de-DE" });

  test("only the two plain choice lists may scroll inside their own frame", async ({ page }) => {
    const failures = [];
    await installPayload(page, CONFIGURATIONS[0].data);
    await goto(page);
    await setRootFont(page, 20);
    const listSteps = ["type", "child"];
    for (const type of ["sick", "leave", "deregister", "daycare"]) {
      await openWizard(page, type, CONFIGURATIONS[0].data.kids);
      for (const walk of WALKS[type]) {
        for (const stepId of walk.steps) {
          const label = `landscape/${type}/${stepId}`;
          const result = await measureStep(page, stepId, walk.set);
          if (listSteps.includes(stepId)) {
            if (result.progressOverflow > 1) failures.push(`${label}: progress row overflows`);
            if (result.pageOverflow > 1) failures.push(`${label}: page scrolls sideways`);
            if (result.nextBottom > result.viewport + 1) failures.push(`${label}: next button is out of sight`);
            continue;
          }
          judge(result, label, failures);
        }
      }
    }
    expect(failures, failures.join("\n")).toEqual([]);
  });
});

const LONG_DUTY_HINT =
  "Meldepflichtig sind unter anderem Masern, Keuchhusten, Scharlach und Windpocken. " +
  "Bitte melde solche Erkrankungen zusaetzlich telefonisch im Sekretariat, damit die Schule " +
  "die anderen Familien rechtzeitig informieren kann.";

async function clippedTexts(page, selector) {
  return page.evaluate((scopeSelector) => {
    const scope = document.querySelector(scopeSelector);
    if (!scope) return null;
    const out = [];
    scope.querySelectorAll("*").forEach((node) => {
      if (node.children.length) return;
      const text = (node.textContent || "").trim();
      if (!text) return;
      const style = getComputedStyle(node);
      const clamped = style.webkitLineClamp && style.webkitLineClamp !== "none";
      const clipped =
        (style.textOverflow === "ellipsis" && node.scrollWidth > node.clientWidth + 1) ||
        (clamped && node.scrollHeight > node.clientHeight + 1);
      if (!clipped) return;
      if (node.closest("button, a, summary, [role='button']")) return;
      out.push({ text: text.slice(0, 60), clientWidth: node.clientWidth, scrollWidth: node.scrollWidth });
    });
    return out;
  }, selector);
}

test.describe("[P192] no text on the review page is cut off without a way to the whole of it", () => {
  test.use({ viewport: { width: 320, height: 568 } });

  for (const language of LANGUAGES) {
    test.describe(language.key, () => {
      test.use({ locale: language.locale });

      test(`review pages keep every value reachable (${language.key})`, async ({ page }) => {
        const failures = [];
        const data = {
          rules: Object.assign({}, ALL_RULES, { duty_hint: LONG_DUTY_HINT }),
          types: ["sick", "leave", "deregister", "daycare"],
          kids: 2,
          targets: ["bus", "lunch"],
        };
        await installPayload(page, data);
        await goto(page);
        await setRootFont(page, 20);
        await page.evaluate(() => document.fonts.ready);

        for (const type of data.types) {
          await openWizard(page, type, data.kids);
          const result = await measureStep(page, "review", {
            body: "Begruendung",
            reason: "Ein sehr ausfuehrlich begruendeter Grund fuer die Abmeldung von der Betreuung",
            subject: "Ein sehr langer Betreff, der in eine einzeilige Zeile niemals hineinpasst",
            comment: "Ein langer Kommentar, der die Zeile der Pruefen-Karte deutlich ueberschreitet",
          });
          judge(result, `${language.key}/review/${type}`, failures);
          const clipped = await clippedTexts(page, ".sw-body");
          if (clipped === null) failures.push(`${language.key}/review/${type}: wizard body missing`);
          else if (clipped.length) {
            failures.push(`${language.key}/review/${type}: cut off with no way to the full text: ${JSON.stringify(clipped)}`);
          }
        }

        await openWizard(page, "sick", data.kids);
        await measureStep(page, "review", {});
        await page.locator(".sw-duty-more").click();
        await page.waitForSelector(".sheet-body");
        const duty = await page.evaluate(() => {
          const paragraph = document.querySelector(".sheet-body p");
          const body = document.querySelector(".sheet-body");
          return {
            text: paragraph ? paragraph.textContent : "",
            clippedHeight: paragraph ? paragraph.scrollHeight - paragraph.clientHeight : 0,
            scrollable: body ? body.scrollHeight <= body.clientHeight + 1 || getComputedStyle(body).overflowY !== "visible" : false,
          };
        });
        if (duty.text !== LONG_DUTY_HINT) failures.push(`${language.key}/duty: the sheet shows "${duty.text}"`);
        if (duty.clippedHeight > 1) failures.push(`${language.key}/duty: the legal text is clipped by ${duty.clippedHeight}px`);
        if (!duty.scrollable) failures.push(`${language.key}/duty: the sheet neither fits nor scrolls`);

        expect(failures, failures.join(SEPARATOR)).toEqual([]);
      });
    });
  }
});
