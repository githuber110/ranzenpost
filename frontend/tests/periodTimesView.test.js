import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const BASE = [470, 520, 585, 635, 695, 745, 830, 880];
const clock = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
const GRID = BASE.map((start, index) => ({
  number: index + 1,
  start: clock(start),
  end: clock(start + 45),
  duration: 45,
  source: "iserv",
  iserv_start: clock(start),
  iserv_duration: 45,
  own_start: false,
  own_duration: false,
  added: false,
}));
const OK = { state: "ok", number: null, start: "", end: "" };
const SERIES = { interval: 1, date: "", from: "2026-09-01", until: "2027-06-30", holidays: false };
const ENTRIES = [
  Object.assign({ id: "p1", type: "pause", name: "Lunch", start: "13:15", duration: 35, end: "13:50", repeat: "daily", days: [0, 1, 2, 3, 4], child: "", child_key: "", status: OK }, SERIES),
  Object.assign({ id: "p2", type: "pause", name: "Room change", start: "13:10", duration: 5, end: "13:15", repeat: "daily", days: [0, 1, 2, 3, 4], child: "", child_key: "", status: OK }, SERIES),
  Object.assign({ id: "c1", type: "club", name: "Choir", start: "15:30", duration: 60, end: "16:30", repeat: "weekly", days: [2], child: "sam", child_key: `${ONE}:sam`, status: OK }, SERIES),
];
const PROFILES = {
  sam: { 0: [1, 2, 3, 4, 5, 6], 1: [1, 2, 3, 4, 5, 6, 7, 8], 2: [1, 2, 3, 4, 5], 3: [1, 2, 3, 4, 5, 6], 4: [1, 2, 3, 4, 5] },
  mika: { 0: [1, 2, 3, 4, 5, 6], 1: [1, 2, 3, 4, 5, 6], 2: [1, 2, 3, 4, 5, 6, 7], 3: [1, 2, 3, 4, 5, 6], 4: [1, 2, 3, 4, 5, 6] },
};

function view(overrides = {}) {
  return Object.assign({
    grid: GRID,
    entries: ENTRIES,
    profiles: PROFILES,
    today: "2026-09-23",
    until_max: "2027-06-30",
    summer_start: "2027-07-01",
    iserv_known: true,
    iserv_ends: true,
  }, overrides);
}

async function setup({ width = 390, data = view(), answer = null } = {}) {
  const { window } = loadApp();
  await settle();
  const calls = [];
  window.matchMedia = (query) => {
    const min = /\(min-width:\s*(\d+)px\)/.exec(query);
    return { matches: min ? width >= Number(min[1]) : false, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} };
  };
  window.fetch = (url, options) => {
    calls.push({ url: String(url), options: options || {} });
    const body = answer ? answer(String(url), options || {}) : Object.assign({ ok: true, message_key: "api.periods.saved" }, data);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  };
  window.eval(`
    state.config = { connections: [{ id: ${JSON.stringify(ONE)}, setup_complete: true, phones: [], subjects: {}, teachers: {}, period_times: ${JSON.stringify(Object.fromEntries(GRID.map((row) => [String(row.number), row.start])))} }], notify_services: [], notify_events: {} };
    state.children = [
      { key: ${JSON.stringify(`${ONE}:sam`)}, child_id: "sam", connection_id: ${JSON.stringify(ONE)}, name: "Sam Example", class_name: "5a" },
      { key: ${JSON.stringify(`${ONE}:mika`)}, child_id: "mika", connection_id: ${JSON.stringify(ONE)}, name: "Mika Example", class_name: "3b" },
    ];
    state.childId = ${JSON.stringify(`${ONE}:sam`)};
    state.periods = { ${JSON.stringify(ONE)}: ${JSON.stringify(data)} };
  `);
  return { window, calls, doc: window.document };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function settle() {
  for (let round = 0; round < 5; round += 1) await flush();
}

function openPage(window) {
  window.eval(`state.view = "settings"; state.periodsPage = { school: ${JSON.stringify(ONE)}, adjusting: false, returnSchool: null }; state.settingsPage = SETTINGS_PAGE_PERIODS; render();`);
}

function tr(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

function atDay(window, iso, run) {
  return window.eval(`
    (function () {
      const RealDate = Date;
      function FixedDate(...args) { return args.length ? new RealDate(...args) : new RealDate(${JSON.stringify(iso)}); }
      FixedDate.prototype = RealDate.prototype;
      FixedDate.now = () => new RealDate(${JSON.stringify(iso)}).getTime();
      FixedDate.UTC = RealDate.UTC;
      Date = FixedDate;
      try { return (${run})(); } finally { Date = RealDate; }
    })
  `)();
}


describe("lesson times page", () => {
  test("the settings row opens the page, which reads as in IServ until Customise", async () => {
    const { window, doc } = await setup();
    window.eval('state.view = "settings"; render();');
    const row = doc.querySelector(".periods-setting");
    expect(row.querySelector(".lbl").textContent).toBe(tr(window, "settings.periods.sheet"));
    window.eval("state.periods = { [" + JSON.stringify(ONE) + "]: " + JSON.stringify(view()) + " };");
    window.eval(`state.periodsPage = { school: ${JSON.stringify(ONE)}, adjusting: false, returnSchool: null }; state.settingsPage = SETTINGS_PAGE_PERIODS; render();`);
    expect(doc.querySelectorAll(".periods-list .prow")).toHaveLength(8);
    expect(doc.querySelectorAll("button.prow")).toHaveLength(0);
    expect(doc.querySelector(".periods-lead b").textContent).toBe(tr(window, "settings.periods.asIserv"));
    expect(doc.querySelector(".periods-lead small").textContent).toBe(window.eval('tCount("periods.lead.iserv", 8)'));
    doc.querySelector(".periods-adjust").click();
    expect(doc.querySelectorAll("button.prow")).toHaveLength(8);
    expect(doc.querySelector(".periods-add-lesson").textContent).toContain(tr(window, "periods.addLesson", { number: "9" }));
  });

  test("gaps without a break offer an entry and gaps with breaks name them", async () => {
    const { window, doc } = await setup();
    openPage(window);
    const named = [...doc.querySelectorAll(".pgap.named")].map((node) => node.textContent);
    expect(named.some((text) => text.includes("Lunch") && text.includes("Room change"))).toBe(true);
    const free = doc.querySelector("button.pgap");
    expect(free.getAttribute("data-gap")).toBe(String(470 + 45));
    free.click();
    const form = window.eval("state.periodsDetail.form");
    expect(form.type).toBe("pause");
    expect(form.repeat).toBe("daily");
    expect(form.child).toBe("");
    expect(form.start).toBe(515);
    expect(window.eval("state.settingsPage")).toBe("entry");
  });

  test("a collision reads as a note with a counter and a tag on the entry, nothing disappears", async () => {
    const hidden = ENTRIES.map((entry) => (entry.id === "p2" ? Object.assign({}, entry, { status: { state: "hidden", number: 6, start: "", end: "" } }) : entry));
    const { window, doc } = await setup({ data: view({ entries: hidden }) });
    openPage(window);
    expect(doc.querySelector(".periods-collisions").textContent).toBe(window.eval('tCount("periods.collisions", 1)'));
    const row = doc.querySelector('.periods-entry[data-entry="p2"]');
    expect(row.querySelector(".tag.warn").textContent).toBe(tr(window, "periods.tag.hidden", { number: "6" }));
    expect(doc.querySelectorAll(".periods-entry")).toHaveLength(3);
  });

  test("four weeks before the series end a note offers one button that copies them into the new school year", async () => {
    const rollover = { count: 2, until: "2027-06-30", from: "2027-08-12", to: "2028-07-05" };
    const moved = view({ rollover: null, message_key: "api.ownEntries.rolledOver", message_vars: { count: 2, skipped: 0 } });
    const { window, doc, calls } = await setup({ data: view({ rollover }), answer: (url) => (url.includes("rollover") ? Object.assign({ ok: true }, moved) : view({ rollover })) });
    openPage(window);
    const note = doc.querySelector(".periods-rollover");
    expect(note.textContent).toContain(window.eval(`tCount("periods.rollover.note", 2, { date: dateLabel("2027-06-30") })`));
    expect(note.textContent).toContain(tr(window, "periods.rollover.range", { from: window.eval('dateLabel("2027-08-12")'), to: window.eval('dateLabel("2028-07-05")') }));
    expect(note.querySelectorAll("button")).toHaveLength(1);
    note.querySelector("button").click();
    await settle();
    const call = calls.find((item) => item.url.includes("own-entries/rollover"));
    expect(call.options.method).toBe("POST");
    expect(doc.querySelector(".periods-rollover")).toBeNull();
    expect(doc.body.textContent).toContain(tr(window, "api.ownEntries.rolledOver", { count: 2 }));
  });

  test("the Home Assistant switch starts off and saves the school setting", async () => {
    let shared = false;
    const config = () => ({ connections: [{ id: ONE, setup_complete: true, phones: [], subjects: {}, teachers: {}, period_times: {}, own_entries_ha: shared }], notify_services: [], notify_events: {} });
    const { window, doc, calls } = await setup({
      answer: (url, options) => {
        if (url.endsWith(`api/connections/${ONE}`) && options.method === "POST") {
          shared = JSON.parse(options.body).own_entries_ha;
          return { saved: true };
        }
        if (url.endsWith("api/config")) return config();
        return view();
      },
    });
    openPage(window);
    const toggle = () => doc.querySelector(".periods-ha .switch");
    expect(toggle().getAttribute("aria-checked")).toBe("false");
    expect(toggle().getAttribute("aria-label")).toBe(tr(window, "periods.ha.label"));
    expect(doc.querySelector(".periods-ha").textContent).toContain(tr(window, "periods.ha.hint"));
    toggle().click();
    await settle();
    const saved = calls.find((call) => call.url.endsWith(`api/connections/${ONE}`) && call.options.method === "POST");
    expect(JSON.parse(saved.options.body)).toEqual({ own_entries_ha: true });
    expect(toggle().getAttribute("aria-checked")).toBe("true");
  });

  test("without series near their end there is no rollover note", async () => {
    const { window, doc } = await setup({ data: view({ rollover: null }) });
    openPage(window);
    expect(doc.querySelector(".periods-rollover")).toBeNull();
  });

  test("only the start from IServ tells that each lesson lasts the standard 45 minutes", async () => {
    const standard = GRID.map((row) => Object.assign({}, row, { source: "standard" }));
    const { window, doc } = await setup({ data: view({ grid: standard, iserv_ends: false }) });
    openPage(window);
    expect(doc.querySelector(".periods-no-end").textContent).toBe(tr(window, "periods.noEnd"));
  });
});

describe("lesson editor", () => {
  test("a longer sixth lesson shows its consequences and saves start and duration", async () => {
    const { window, doc, calls } = await setup();
    openPage(window);
    doc.querySelector(".periods-adjust").click();
    doc.querySelector('button.prow[data-period="6"]').click();
    const sheet = () => doc.querySelector(".sheet");
    expect(sheet().querySelector(".sheet-title").textContent).toBe(tr(window, "settings.periods.label", { number: "6" }));
    const minutes = sheet().querySelector(".dur-minutes");
    minutes.value = "60";
    minutes.dispatchEvent(new window.Event("change"));
    const note = sheet().querySelector(".periods-consequences").textContent;
    expect(note).toContain(tr(window, "periods.consequence.hidden", { name: "Room change", number: "6" }));
    expect(note).toContain("Lunch");
    expect(sheet().querySelector(".periods-iserv-value")).not.toBeNull();
    sheet().querySelector(".periods-apply").click();
    await flush();
    const write = calls.find((call) => call.options.method === "POST");
    expect(write.url).toMatch(new RegExp(`api/connections/${ONE}/periods/lessons/6$`));
    expect(JSON.parse(write.options.body)).toEqual({ start: "12:25", duration: 60 });
  });

  test("the start stepper stops at the end of the lesson before", async () => {
    const { window, doc } = await setup();
    openPage(window);
    doc.querySelector(".periods-adjust").click();
    doc.querySelector('button.prow[data-period="2"]').click();
    const buttons = doc.querySelectorAll(".sheet .lesson-start .sbtn");
    buttons[0].click();
    expect(window.eval("state.periodsDetail.start")).toBe(515);
    expect(doc.querySelectorAll(".sheet .lesson-start .sbtn")[0].disabled).toBe(true);
  });
});

describe("entry editor", () => {
  test("the plus in the plan opens a full page on the phone with the club defaults", async () => {
    const { window, doc } = await setup();
    window.eval('state.view = "timetable"; state.timetable = { lessons: [], period_times: {} }; render();');
    atDay(window, "2026-09-23T09:30:00", "() => { document.querySelector('.plan-add').click(); }");
    expect(window.eval("state.settingsPage")).toBe("entry");
    const form = window.eval("state.periodsDetail.form");
    expect(form.type).toBe("club");
    expect(form.repeat).toBe("weekly");
    expect(form.child).toBe("sam");
    expect(form.from).toBe("2026-09-23");
    expect(form.until).toBe("2026-09-23");
    expect(doc.querySelector(".entry-save").disabled).toBe(true);
    expect(doc.querySelector(".periods-problem").textContent).toBe(tr(window, "periods.problem.name"));
  });

  test("a new entry from the plan tap on a day lands from and until on that day only", async () => {
    const { window, doc } = await setup();
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "pause", start: 14 * 60, date: "2026-09-24" })`);
    const form = window.eval("state.periodsDetail.form");
    expect(form.repeat).toBe("daily");
    expect(form.from).toBe("2026-09-24");
    expect(form.until).toBe("2026-09-24");
    const hint = doc.querySelector(".entry-single-day .hint");
    expect(hint.textContent).toBe(tr(window, "periods.range.singleDay"));
    const summerButton = doc.querySelector(".entry-until-summer");
    expect(summerButton.textContent).toBe(tr(window, "periods.range.untilSummer"));
    summerButton.click();
    expect(window.eval("state.periodsDetail.form.until")).toBe("2027-06-30");
    expect(doc.querySelector(".entry-single-day")).toBeNull();
  });

  test("a new appointment from settings also starts from = until = today, once by default", async () => {
    const { window, doc } = await setup();
    atDay(window, "2026-09-23T09:30:00", `() => { openEntryForm({ school: ${JSON.stringify(ONE)}, type: "appointment" }); }`);
    const form = window.eval("state.periodsDetail.form");
    expect(form.repeat).toBe("once");
    expect(form.date).toBe("2026-09-23");
    expect(form.from).toBe("2026-09-23");
    expect(form.until).toBe("2026-09-23");
    expect(doc.querySelector(".entry-single-day")).toBeNull();
  });

  test("the limit names what ends the entry and the duration controls move together", async () => {
    const { window, doc } = await setup();
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "club", start: 14 * 60, date: "2026-09-23" })`);
    const form = () => window.eval("state.periodsDetail.form");
    expect(form().days).toEqual([2]);
    expect(doc.querySelector(".entry-duration .maxline").textContent).toContain("Choir");
    expect(form().duration).toBe(90);
    const slider = doc.querySelector(".entry-duration .dur-range");
    slider.value = "30";
    slider.dispatchEvent(new window.Event("input"));
    expect(doc.querySelector(".entry-duration .dur-minutes").value).toBe("30");
    expect(doc.querySelector(".entry-duration .dur-endtime").value).toBe("14:30");
    const end = doc.querySelector(".entry-duration .dur-endtime");
    end.value = "15:10";
    end.dispatchEvent(new window.Event("change"));
    expect(form().duration).toBe(70);
    const minutes = doc.querySelector(".entry-duration .dur-minutes");
    minutes.value = "500";
    minutes.dispatchEvent(new window.Event("change"));
    expect(form().duration).toBe(90);
  });

  test("adding Wednesday for a Tuesday afternoon club hits the choir and a lesson blocks the start", async () => {
    const { window, doc } = await setup();
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "club", start: 16 * 60, date: "2026-09-29" })`);
    expect(window.eval("state.periodsDetail.form.days")).toEqual([1]);
    doc.querySelector(".entry-until-summer").click();
    doc.querySelector('.entry-days [data-day="2"]').click();
    expect(doc.querySelector(".periods-problem").textContent).toBe(tr(window, "periods.problem.conflict", { day: window.eval("weekdayLabel(2)"), time: window.eval("clockLabel(960)"), what: "Choir" }));
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "club", start: 14 * 60, date: "2026-09-29" })`);
    expect(doc.querySelector(".periods-problem").textContent).toContain(tr(window, "settings.periods.label", { number: "7" }));
  });

  test("a break defaults to every school day for everyone and the once repetition hides the holiday tick", async () => {
    const { window, doc } = await setup();
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)} })`);
    doc.querySelector('.entry-type [data-value="pause"]').click();
    let form = window.eval("state.periodsDetail.form");
    expect(form.repeat).toBe("daily");
    expect(form.child).toBe("");
    expect(form.name).toBe(tr(window, "periods.entry.type.pause"));
    expect(doc.querySelector(".entry-holidays")).not.toBeNull();
    doc.querySelector('.entry-repeat [data-value="once"]').click();
    expect(doc.querySelector(".entry-holidays")).toBeNull();
    doc.querySelector('.entry-type [data-value="appointment"]').click();
    form = window.eval("state.periodsDetail.form");
    expect(form.child).toBe("sam");
    expect(form.name).toBe("");
  });

  test("saving posts the entry and returns to the plan", async () => {
    const { window, doc, calls } = await setup();
    window.eval('state.view = "timetable"; state.timetable = { lessons: [], period_times: {} }; render();');
    atDay(window, "2026-09-23T09:30:00", "() => { document.querySelector('.plan-add').click(); }");
    const name = doc.querySelector(".entry-name");
    name.value = "Chess";
    name.dispatchEvent(new window.Event("input"));
    expect(doc.querySelector(".entry-save").disabled).toBe(false);
    doc.querySelector(".entry-save").click();
    await flush();
    await flush();
    const write = calls.find((call) => call.options.method === "POST");
    expect(write.url).toMatch(new RegExp(`api/connections/${ONE}/own-entries$`));
    const payload = JSON.parse(write.options.body);
    expect(payload).toMatchObject({ type: "club", name: "Chess", repeat: "weekly", child: "sam", holidays: false, from: "2026-09-23", until: "2026-09-23" });
    expect(payload.id).toBeUndefined();
    expect(window.eval("state.view")).toBe("timetable");
    expect(window.eval("state.periodsDetail")).toBeNull();
  });

  test("a refused entry keeps the form open and shows the reason", async () => {
    const { window, doc } = await setup({ answer: (url, options) => (options.method === "POST" ? { ok: false, message_key: "api.ownEntries.error.taken", message_vars: { name: "Choir" } } : view()) });
    window.fetch = (url, options) => Promise.resolve({ ok: !(options && options.method === "POST"), status: options && options.method === "POST" ? 400 : 200, json: () => Promise.resolve(options && options.method === "POST" ? { ok: false, message_key: "api.ownEntries.error.taken", message_vars: { name: "Choir" } } : view()) });
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "club", start: 17 * 60 })`);
    const name = doc.querySelector(".entry-name");
    name.value = "Chess";
    name.dispatchEvent(new window.Event("input"));
    doc.querySelector(".entry-save").click();
    await flush();
    await flush();
    expect(window.eval("state.periodsDetail.kind")).toBe("form");
    expect(window.eval("state.toast.message")).toBe(tr(window, "api.ownEntries.error.taken", { name: "Choir" }));
  });

  test("deleting a series asks first, a cancel returns to the entry and a confirm sends the delete", async () => {
    const { window, doc, calls } = await setup();
    openPage(window);
    doc.querySelector('.periods-entry[data-entry="p1"]').click();
    expect(doc.querySelector(".sheet .sheet-title").textContent).toBe("Lunch");
    doc.querySelector(".sheet .periods-delete").click();
    doc.querySelector(".sheet .btn.ghost").click();
    await flush();
    await flush();
    expect(doc.querySelector(".sheet .sheet-title").textContent).toBe("Lunch");
    doc.querySelector(".sheet .periods-delete").click();
    doc.querySelector(".sheet .btn.destructive").click();
    await flush();
    await flush();
    const removal = calls.find((call) => call.options.method === "DELETE");
    expect(removal.url).toMatch(new RegExp(`api/connections/${ONE}/own-entries/p1$`));
    expect(window.eval("state.periodsDetail")).toBeNull();
    expect(doc.querySelector(".sheet")).toBeNull();
  });

  test("renaming an entry a longer lesson cuts keeps its time and can be saved", async () => {
    const long = GRID.map((row) => (row.number === 5 ? Object.assign({}, row, { end: "13:05", duration: 90, own_duration: true }) : row));
    const late = Object.assign({}, ENTRIES[2], { id: "c2", start: "12:30", end: "13:30", duration: 60, days: [2], status: { state: "cut", number: 5, start: "13:05", end: "13:30" } });
    const { window, doc } = await setup({ data: view({ grid: long, entries: [late] }) });
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, entry: state.periods[${JSON.stringify(ONE)}].entries[0] })`);
    const name = doc.querySelector(".entry-name");
    name.value = "Choir two";
    name.dispatchEvent(new window.Event("input"));
    expect(doc.querySelector(".entry-save").disabled).toBe(false);
    expect(window.eval("state.periodsDetail.form.duration")).toBe(60);
    doc.querySelectorAll(".entry-start .sbtn")[1].click();
    expect(doc.querySelector(".periods-problem").textContent).toContain(tr(window, "settings.periods.label", { number: "5" }));
  });

  test("a copy in the next school year keeps its dates inside that year", async () => {
    const copy = Object.assign({}, ENTRIES[2], { id: "c9", from: "2027-08-12", until: "2028-07-05", from_min: "2027-07-01", until_max: "2028-07-05" });
    const { window, doc } = await setup({ data: view({ entries: [ENTRIES[2], copy] }) });
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, entry: state.periods[${JSON.stringify(ONE)}].entries[1] })`);
    const from = doc.querySelector(".entry-from");
    const until = doc.querySelector(".entry-until");
    expect([from.value, from.min, from.max, until.value, until.max]).toEqual(["2027-08-12", "2027-07-01", "2028-07-05", "2028-07-05", "2028-07-05"]);
    until.value = "2028-07-20";
    until.dispatchEvent(new window.Event("change"));
    expect(window.eval("state.periodsDetail.form.until")).toBe("2028-07-05");
    expect(doc.querySelector(".entry-range .hint.warn").textContent).toBe(tr(window, "periods.until.clampedPlain", { date: window.eval('dateLabel("2028-07-05")') }));
    const moved = doc.querySelector(".entry-from");
    moved.value = "2027-06-01";
    moved.dispatchEvent(new window.Event("change"));
    expect(window.eval("state.periodsDetail.form.from")).toBe("2027-07-01");
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, entry: state.periods[${JSON.stringify(ONE)}].entries[0] })`);
    const plain = doc.querySelector(".entry-from");
    expect([plain.hasAttribute("min"), plain.max, doc.querySelector(".entry-until").max]).toEqual([false, "2027-06-30", "2027-06-30"]);
  });

  test("a series without a single date explains itself", async () => {
    const { window, doc } = await setup();
    window.eval(`openEntryForm({ school: ${JSON.stringify(ONE)}, type: "club", start: 17 * 60, date: "2026-09-23" })`);
    window.eval('state.periodsDetail.form.from = "2026-09-21"; state.periodsDetail.form.until = "2026-09-25"; state.periodsDetail.form.days = [6]; rerender();');
    expect(doc.querySelector(".periods-problem").textContent).toBe(tr(window, "periods.problem.empty"));
  });

  test("a start saved before IServ times were known reads as saved, not as an own lesson", async () => {
    const saved = GRID.map((row) => (row.number === 3 ? Object.assign({}, row, { source: "saved", iserv_start: "", iserv_duration: null }) : row));
    const { window, doc } = await setup({ data: view({ grid: saved }) });
    openPage(window);
    const row = doc.querySelector('.prow[data-period="3"]');
    expect(row.querySelector("small").textContent).toBe(tr(window, "periods.source.saved"));
    expect(row.querySelector(".pnum").classList.contains("own")).toBe(false);
  });

  test("at laptop width the editor opens in the detail pane next to the page", async () => {
    const { window, doc } = await setup({ width: 1366 });
    openPage(window);
    expect(doc.querySelector(".pane-detail .pane-empty").textContent).toBe(tr(window, "periods.pane.empty"));
    doc.querySelector('.periods-entry[data-entry="c1"]').click();
    expect(doc.querySelector(".sheet")).toBeNull();
    expect(doc.querySelector(".pane-detail .pane-title").textContent).toBe("Choir");
    expect(doc.querySelector('.periods-entry[data-entry="c1"]').classList.contains("open")).toBe(true);
    doc.querySelector(".pane-detail .periods-edit").click();
    expect(doc.querySelector(".pane-detail .entry-name").value).toBe("Choir");
    expect(window.eval("state.settingsPage")).toBe("periods");
  });
});

describe("plan and today", () => {
  function week() {
    const lessons = [];
    const days = ["21.09.2026", "22.09.2026", "23.09.2026", "24.09.2026", "25.09.2026"];
    const counts = [6, 8, 5, 6, 5];
    days.forEach((date, index) => {
      for (let period = 1; period <= counts[index]; period += 1) {
        lessons.push({ date, day_of_week: index + 1, period, start_time: clock(BASE[period - 1]), end_time: clock(BASE[period - 1] + 45), subject_code: "D", subject_label: "Deutsch", change_kind: "" });
      }
    });
    return { lessons, period_times: {}, start_date: "21.09.2026", end_date: "25.09.2026" };
  }

  test("breaks become thin separators and the choir its own row on Wednesday only", async () => {
    const { window } = await setup();
    const grid = atDay(window, "2026-09-23T09:30:00", `() => { state.weekOffset = 0; return timetableGrid(${JSON.stringify(week())}, ${JSON.stringify(`${ONE}:sam`)}); }`);
    const strips = [...grid.querySelectorAll(".tt-strip")].map((node) => node.textContent);
    expect(strips.some((text) => text.includes("Lunch"))).toBe(true);
    const own = [...grid.querySelectorAll(".tt-own")];
    expect(own).toHaveLength(1);
    expect(own[0].style.gridColumn).toBe("4");
    const hours = [...grid.querySelectorAll(".tt-hour:not(.own)")].map((node) => Number(node.style.gridRow));
    expect(hours).toEqual([...hours].sort((a, b) => a - b));
    expect(hours[7] - hours[5]).toBeGreaterThan(2);
    const free = grid.querySelector(".tt-free-slot");
    expect(free).not.toBeNull();
  });

  test("tapping a free slot starts an entry at that lesson on that day", async () => {
    const { window, doc } = await setup();
    const grid = atDay(window, "2026-09-23T09:30:00", `() => { state.weekOffset = 0; return timetableGrid(${JSON.stringify(week())}, ${JSON.stringify(`${ONE}:sam`)}); }`);
    doc.body.append(grid);
    const slot = [...grid.querySelectorAll(".tt-free-slot")].find((node) => node.style.gridColumn === "4");
    atDay(window, "2026-09-23T09:30:00", "() => { document.querySelector('.tt-free-slot[style*=\"grid-column: 4\"]').click(); }");
    const form = window.eval("state.periodsDetail.form");
    expect(slot).toBeDefined();
    expect(form.date).toBe("2026-09-23");
    expect(form.start).toBe(BASE[5]);
  });

  const RIDING = Object.assign({ id: "r1", type: "club", name: "Riding", start: "08:00", duration: 60, end: "09:00", repeat: "weekly", days: [2], child: "sam", child_key: `${ONE}:sam`, status: OK }, SERIES, { holidays: true });
  const TICKED_BREAK = Object.assign({ id: "p3", type: "pause", name: "Walk", start: "09:30", duration: 10, end: "09:40", repeat: "daily", days: [0, 1, 2, 3, 4], child: "", child_key: "", status: OK }, SERIES, { holidays: true });
  const AUTUMN = { id: "h1", kind: "school", type: "autumn", name: "Herbstferien", name_key: "", start: "2026-09-21", end: "2026-09-25" };

  function holidayDay(free) {
    return free
      ? { free: true, overrides_lessons: true, weekend: false, kind: "school", type: "autumn", name: "Herbstferien", name_key: "", period_id: "h1" }
      : { free: false, overrides_lessons: false, weekend: false, kind: "", type: "", name: "", name_key: "", period_id: "" };
  }

  function holidays(window, freeDays, fullWeek) {
    const days = {};
    for (let offset = 0; offset < 7; offset += 1) {
      const iso = `2026-09-${String(21 + offset).padStart(2, "0")}`;
      days[iso] = holidayDay(freeDays.includes(iso));
    }
    const weeks = [{ week: 39, iso_year: 2026, start: "2026-09-21", end: "2026-09-27", coverage: fullWeek ? "full" : "partial", label_key: "holidays.week.partial", school_days: 5, free_school_days: freeDays.length, override_school_days: freeDays.length, overrides_lessons: true, primary: AUTUMN, periods: [AUTUMN] }];
    window.eval(`state.holidays = { ${JSON.stringify(ONE)}: ${JSON.stringify({ status: "ok", stale: false, days, weeks, periods: [AUTUMN] })} };`);
  }

  test("on a holiday the plan keeps ticked clubs over the holiday field and drops the rest", async () => {
    const { window } = await setup({ data: view({ entries: ENTRIES.concat([RIDING, TICKED_BREAK]) }) });
    holidays(window, ["2026-09-23"], false);
    const grid = atDay(window, "2026-09-22T09:30:00", `() => { state.weekOffset = 0; return timetableGrid(${JSON.stringify(week())}, ${JSON.stringify(`${ONE}:sam`)}); }`);
    const own = [...grid.querySelectorAll(".tt-own")];
    expect(own.map((node) => node.dataset.entry)).toEqual(["r1"]);
    expect(own[0].classList.contains("on-hol")).toBe(true);
    expect(own[0].style.gridColumn).toBe("4");
    expect(own[0].textContent).toContain("08:00");
    expect(grid.querySelector(".tt-hol")).not.toBeNull();
    expect([...grid.querySelectorAll(".tt-strip")].some((node) => node.textContent.includes("Walk"))).toBe(true);
  });

  test("a whole holiday week still lists the ticked clubs under the holiday field", async () => {
    const { window } = await setup({ data: view({ entries: ENTRIES.concat([RIDING]) }) });
    holidays(window, ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"], true);
    const grid = atDay(window, "2026-09-22T09:30:00", `() => { state.weekOffset = 0; return timetableGrid(${JSON.stringify(week())}, ${JSON.stringify(`${ONE}:sam`)}); }`);
    expect(grid.querySelector(".tt-hol.full")).not.toBeNull();
    const own = [...grid.querySelectorAll(".tt-own")];
    expect(own.map((node) => node.dataset.entry)).toEqual(["r1"]);
    expect(Number(own[0].style.gridRow)).toBeGreaterThanOrEqual(3);
    expect(grid.querySelectorAll(".tt-strip")).toHaveLength(0);
  });

  test("today on a holiday shows the holiday and the ticked clubs only", async () => {
    const { window } = await setup({ data: view({ entries: ENTRIES.concat([RIDING]) }) });
    holidays(window, ["2026-09-23"], false);
    const chapter = atDay(window, "2026-09-23T07:00:00", `() => { state.weekOffset = 0; state.timetable = ${JSON.stringify(week())}; return todayChapter("normal"); }`);
    const keys = chapter.blocks.map((block) => block.key);
    expect(keys[0]).toBe(`today:holiday:${ONE}:sam`);
    expect(chapter.blocks[0].node.textContent).toContain("Herbstferien");
    expect(keys).toContain(`${ONE}:sam:own:r1`);
    expect(keys.some((key) => key.includes(":own:c1"))).toBe(false);
    expect(chapter.nowKey).toBe(keys[0]);
    const riding = chapter.blocks.find((block) => block.key === `${ONE}:sam:own:r1`);
    expect(riding.node.textContent).toContain("08:00");
  });

  test("today on a holiday without ticked entries stays the plain holiday card", async () => {
    const { window } = await setup();
    holidays(window, ["2026-09-23"], false);
    const chapter = atDay(window, "2026-09-23T07:00:00", `() => { state.weekOffset = 0; state.timetable = ${JSON.stringify(week())}; return todayChapter("normal"); }`);
    expect(chapter.bodyClass).toBe("panel-rest");
    expect(chapter.blocks).toHaveLength(1);
    expect(chapter.blocks[0].node.classList.contains("card")).toBe(true);
  });

  test("today lists the choir between the lessons' end and shows the next appointment", async () => {
    const { window } = await setup({ data: view({ entries: ENTRIES.concat([Object.assign({ id: "a1", type: "appointment", name: "Dentist", start: "16:00", duration: 30, end: "16:30", repeat: "once", days: [], interval: 1, date: "2026-09-24", from: "", until: "", holidays: true, child: "sam", child_key: `${ONE}:sam`, status: OK })]) }) });
    const chapter = atDay(window, "2026-09-23T09:30:00", `() => { state.weekOffset = 0; state.timetable = ${JSON.stringify(week())}; return todayChapter("normal"); }`);
    const keys = chapter.blocks.map((block) => block.key);
    const own = keys.indexOf(`${ONE}:sam:own:c1`);
    expect(own).toBeGreaterThan(keys.indexOf(`${ONE}:sam:5`));
    expect(keys.some((key) => key.includes(":own:p1"))).toBe(false);
    const next = chapter.blocks.find((block) => block.key === `${ONE}:sam:own-next`);
    expect(next.node.textContent).toContain("Dentist");
    expect(next.node.textContent).toContain(tr(window, "periods.today.tomorrow"));
  });
});
