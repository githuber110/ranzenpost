import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const AUTUMN = {
  id: "p-autumn",
  kind: "school",
  type: "autumn",
  name: "Herbstferien",
  name_key: "holidays.period.autumn",
  start: "",
  end: "",
  groups: [],
  exception: false,
};

const UNITY = {
  id: "p-unity",
  kind: "public",
  type: "",
  name: "Tag der Deutschen Einheit",
  name_key: "",
  start: "",
  end: "",
  groups: [],
  exception: false,
};

function calendarDays(window) {
  return window.eval("Array.from({ length: 21 }, (_, i) => isoDate(addDays(weekMonday(), i)))");
}

function dayEntry(period, { free = true, overrides = true, weekend = false } = {}) {
  if (!period) {
    return {
      free: false,
      overrides_lessons: false,
      weekend,
      kind: "",
      type: "",
      name: "",
      name_key: "",
      period_id: "",
    };
  }
  return {
    free,
    overrides_lessons: overrides,
    weekend,
    kind: period.kind,
    type: period.type,
    name: period.name,
    name_key: period.name_key,
    period_id: period.id,
  };
}

function weekRow(start, coverage, overrides, freeDays, primary) {
  return {
    week: 1,
    iso_year: 2026,
    start,
    end: start,
    coverage,
    label_key: coverage === "full" ? "holidays.week.full" : "holidays.week.partial",
    school_days: 5,
    free_school_days: freeDays,
    override_school_days: overrides ? freeDays : 0,
    overrides_lessons: overrides,
    primary: primary || null,
    periods: primary ? [primary] : [],
  };
}

function apply(window, payload) {
  window.eval(`state.holidays = ${JSON.stringify(payload)};`);
}

function fullLessons() {
  const lessons = [];
  for (let day = 1; day <= 5; day += 1) {
    for (let period = 1; period <= 4; period += 1) {
      lessons.push({ day_of_week: day, period, subject_code: "MA", subject_label: "Mathe" });
    }
  }
  return lessons;
}

function renderGrid(window, lessons) {
  const run = window.eval(
    "(function (data) { state.childId = 'c1'; state.children = [{ child_id: 'c1' }]; return timetableGrid(data); })"
  );
  return run({ lessons, period_times: {} });
}

function renderView(window, data) {
  const run = window.eval(
    "(function (data) { state.childId = 'c1'; state.children = [{ child_id: 'c1' }]; state.timetable = data; return timetableView(); })"
  );
  return run(data);
}

function fullHolidayWeek(window, { overrides = true, stale = false, status = "ok" } = {}) {
  const iso = calendarDays(window);
  const days = {};
  iso.forEach((day, index) => {
    const weekend = index % 7 >= 5;
    const inside = index < 5;
    days[day] = inside ? dayEntry(AUTUMN, { overrides, weekend }) : dayEntry(null, { weekend });
  });
  const period = Object.assign({}, AUTUMN, { start: iso[0], end: iso[6] });
  return {
    region: "DE-NI",
    status,
    stale,
    days,
    weeks: [weekRow(iso[0], "full", overrides, 5, period)],
    periods: [period],
    iso,
  };
}

describe("[P153] holiday display: the calendar replaces lessons only where it may", () => {
  test("a fully covered week with overrides_lessons replaces the grid with one quiet holiday field", () => {
    const { window } = loadApp();
    const payload = fullHolidayWeek(window);
    apply(window, payload);
    const grid = renderGrid(window, fullLessons());
    const fields = grid.querySelectorAll(".tt-hol");
    expect(fields.length).toBe(1);
    expect(fields[0].classList.contains("full")).toBe(true);
    expect(fields[0].style.gridColumn).toBe("2 / span 5");
    expect(grid.querySelectorAll(".tt-hour").length).toBe(0);
    expect(grid.querySelectorAll(".tt-cell").length).toBe(0);
    expect(grid.querySelectorAll(".tt-head").length).toBe(5);
    expect(fields[0].querySelector(".name").textContent).toBe("Herbstferien");
    expect(fields[0].querySelector(".meta").textContent).toContain("Wieder Schule ab");
  });

  test("the same week without overrides_lessons keeps every IServ lesson on screen", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window, { overrides: false }));
    const grid = renderGrid(window, fullLessons());
    expect(grid.querySelectorAll(".tt-hol").length).toBe(0);
    expect(grid.querySelectorAll(".tt-cell.sub, .tt-cell").length).toBeGreaterThan(0);
    expect(grid.querySelectorAll(".tt-hour").length).toBe(4);
    expect(grid.querySelectorAll(".tt-head .n.off").length).toBe(5);
  });

  test("the uncertain state names itself in the stamp line instead of hiding lessons", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window, { overrides: false }));
    const view = renderView(window, { lessons: fullLessons(), period_times: {}, last_updated: "" });
    expect(view.querySelector(".tt-hol")).toBe(null);
    expect(view.querySelector(".legend")).not.toBe(null);
    expect(view.querySelector(".stamp").textContent).toContain("Ferientermine weichen je nach Schulform");
  });

  test("a load error always wins over the holiday field", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window));
    const view = renderView(window, { lessons: [], error: "network" });
    expect(view.querySelector(".tt-hol")).toBe(null);
    expect(view.querySelector(".empty")).not.toBe(null);
  });

  test("the full-week field drops the legend but keeps the stamp", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window));
    const view = renderView(window, { lessons: fullLessons(), period_times: {}, last_updated: "01.09.2026 08:00" });
    expect(view.querySelector(".tt-hol.full")).not.toBe(null);
    expect(view.querySelector(".legend")).toBe(null);
    expect(view.querySelector(".stamp")).not.toBe(null);
  });

  test("a stale cache adds one quiet sentence to the stamp, never a warning box", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window, { stale: true }));
    const view = renderView(window, { lessons: fullLessons(), period_times: {}, last_updated: "01.09.2026 08:00" });
    expect(view.querySelector(".stamp").textContent).toContain("Ferientermine aus dem lokalen Speicher.");
    expect(view.querySelector(".note")).toBe(null);
  });

  test("a stale cache stays silent in weeks that show no holiday at all", () => {
    const { window } = loadApp();
    const payload = fullHolidayWeek(window, { stale: true });
    for (const key of Object.keys(payload.days)) payload.days[key] = dayEntry(null);
    payload.weeks = [];
    apply(window, payload);
    const view = renderView(window, { lessons: fullLessons(), period_times: {}, last_updated: "01.09.2026 08:00" });
    expect(view.querySelector(".stamp").textContent).not.toContain("lokalen Speicher");
  });

  test("status unknown and status disabled render exactly the tree we render without a calendar", () => {
    const plain = loadApp();
    const reference = renderGrid(plain.window, fullLessons()).outerHTML;
    for (const status of ["unknown", "disabled"]) {
      const { window } = loadApp();
      apply(window, fullHolidayWeek(window, { status }));
      expect(renderGrid(window, fullLessons()).outerHTML).toBe(reference);
    }
  });
});

describe("[P153] holiday display: partial weeks write the name out", () => {
  function partialWeek(window, { overrides = true, spanDays = 1 } = {}) {
    const iso = calendarDays(window);
    const days = {};
    iso.forEach((day, index) => {
      const weekend = index % 7 >= 5;
      const covered = index >= 3 && index < 3 + spanDays;
      days[day] = covered ? dayEntry(UNITY, { overrides, weekend }) : dayEntry(null, { weekend });
    });
    const period = Object.assign({}, UNITY, { start: iso[3], end: iso[3 + spanDays - 1] });
    for (const day of Object.keys(days)) {
      if (days[day].period_id === UNITY.id) days[day].period_id = period.id;
    }
    return {
      region: "DE-NI",
      status: "ok",
      stale: false,
      days,
      weeks: [weekRow(iso[0], "partial", false, spanDays, period)],
      periods: [period],
      iso,
    };
  }

  test("a single blocked day carries the full proper name, stepped down and hyphenated", () => {
    const { window } = loadApp();
    apply(window, partialWeek(window));
    const grid = renderGrid(window, fullLessons());
    const field = grid.querySelector(".tt-hol");
    expect(field).not.toBe(null);
    expect(field.querySelector(".name").textContent).toBe("Tag der Deutschen Einheit");
    expect(field.classList.contains("sz-2")).toBe(true);
    expect(field.classList.contains("brk")).toBe(true);
    expect(field.classList.contains("public")).toBe(true);
    expect(field.style.gridColumn).toBe("5 / span 1");
    expect(field.querySelector(".meta")).toBe(null);
  });

  test("two blocked days merge into one field that still fits without the smallest step", () => {
    const { window } = loadApp();
    apply(window, partialWeek(window, { spanDays: 2 }));
    const grid = renderGrid(window, fullLessons());
    const fields = grid.querySelectorAll(".tt-hol");
    expect(fields.length).toBe(1);
    expect(fields[0].style.gridColumn).toBe("5 / span 2");
    expect(fields[0].classList.contains("sz-2")).toBe(false);
    expect(fields[0].classList.contains("brk")).toBe(false);
    expect(fields[0].querySelector(".meta").textContent.length).toBeGreaterThan(0);
  });

  test("the remaining school days keep their lessons and the grid keeps its hour column", () => {
    const { window } = loadApp();
    apply(window, partialWeek(window));
    const grid = renderGrid(window, fullLessons());
    expect(grid.querySelectorAll(".tt-hour").length).toBe(4);
    const columns = [...grid.querySelectorAll(".tt-cell")].map((cell) => cell.style.gridColumn);
    expect(columns).not.toContain("5");
    expect(columns).toContain("2");
  });

  test("a blocked day without any name never draws a wordless grey box", () => {
    const { window } = loadApp();
    const payload = partialWeek(window);
    for (const key of Object.keys(payload.days)) {
      if (payload.days[key].free) {
        payload.days[key].name = "";
        payload.days[key].name_key = "";
        payload.days[key].kind = "";
      }
    }
    apply(window, payload);
    const field = renderGrid(window, fullLessons()).querySelector(".tt-hol");
    expect(field.querySelector(".name").textContent).toBe("Schulfrei");
  });
});

describe("[P153] holiday display: week picker and today card", () => {
  test("the week list marks holiday weeks and puts the date range first", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window));
    const rows = window.eval("weekSheet()").querySelectorAll(".opt");
    expect(rows.length).toBe(9);
    expect(rows[0].classList.contains("off")).toBe(true);
    const small = rows[0].querySelector("small");
    expect(small.className).toBe("one-line");
    expect(small.textContent).toContain("Herbstferien");
    expect(small.textContent.indexOf("Herbstferien")).toBeGreaterThan(small.textContent.indexOf("."));
    expect(rows[1].classList.contains("off")).toBe(false);
  });

  test("a partial week counts its free days from the backend instead of counting itself", () => {
    const { window } = loadApp();
    const payload = fullHolidayWeek(window);
    payload.weeks[0].coverage = "partial";
    payload.weeks[0].free_school_days = 2;
    payload.weeks[0].overrides_lessons = false;
    apply(window, payload);
    const small = window.eval("weekSheet()").querySelector(".opt small");
    expect(small.textContent).toContain("2 Tage frei");
  });

  test("changing the week never clears the holiday state", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window));
    window.eval("state.timetable = { lessons: [] }; setWeek(3);");
    expect(window.eval("state.timetable")).toBe(null);
    expect(window.eval("state.holidays && state.holidays.status")).toBe("ok");
  });

  test("today's card names the holiday instead of saying there is no school", () => {
    const { window } = loadApp();
    const payload = fullHolidayWeek(window);
    apply(window, payload);
    const card = window.eval(`holidayTodayCard(isoDate(weekMonday()), 6)`);
    expect(card).not.toBe(null);
    expect(card.querySelector("b").textContent).toBe("Herbstferien");
    expect(card.textContent).toContain("Wieder Schule ab");
  });

  test("today's card stands down when the source may not override the lessons", () => {
    const { window } = loadApp();
    apply(window, fullHolidayWeek(window, { overrides: false }));
    expect(window.eval("holidayTodayCard(isoDate(weekMonday()), 6)")).toBe(null);
  });

  test("a public holiday gets no back-to-school sentence", () => {
    const { window } = loadApp();
    const iso = calendarDays(window);
    const period = Object.assign({}, UNITY, { start: iso[0], end: iso[0] });
    const days = {};
    iso.forEach((day, index) => {
      days[day] = index === 0 ? dayEntry(period) : dayEntry(null, { weekend: index % 7 >= 5 });
    });
    apply(window, { region: "DE-NI", status: "ok", stale: false, days, weeks: [], periods: [period] });
    const card = window.eval("holidayTodayCard(isoDate(weekMonday()), 0)");
    expect(card.textContent).toContain("Tag der Deutschen Einheit");
    expect(card.textContent).toContain("Feiertag");
    expect(card.textContent).not.toContain("Wieder Schule");
  });
});

describe("[P153] holiday settings: a suggestion is shown, never stored", () => {
  function prepare(window, region) {
    window.eval(`
      state.config = { holiday_region: ${JSON.stringify(region)} };
      state.holidayRegions = [
        { code: "DE-NI", name_key: "holidays.region.ni" },
        { code: "DE-BY", name_key: "holidays.region.by" },
        { code: "DE-MV", name_key: "holidays.region.mv" }
      ];
      state.holidaySuggestion = {
        region: "DE-NI",
        confidence: "high",
        origin: "iserv_postal_code",
        origin_key: "holidays.suggestion.origin.iservPostalCode",
        reason: ""
      };
    `);
  }

  test("the suggested state leads the list, is badged, and is not marked as chosen", () => {
    const { window } = loadApp();
    prepare(window, "");
    const rows = window.eval("holidayRegionSheet()").querySelectorAll(".opt");
    expect(rows[0].querySelector("b").textContent).toBe("Kein Ferienkalender");
    expect(rows[1].classList.contains("suggested")).toBe(true);
    expect(rows[1].querySelector("b").textContent).toBe("Niedersachsen");
    expect(rows[1].querySelector(".opt-badge").textContent).toBe("Vorschlag");
    expect(rows[1].getAttribute("aria-pressed")).toBe("false");
    expect(rows[1].querySelector("small").textContent).toContain("Postleitzahl");
    expect(window.eval("state.config.holiday_region")).toBe("");
  });

  test("the settings row keeps saying 'off' while a suggestion is only offered", () => {
    const { window } = loadApp();
    prepare(window, "");
    expect(window.eval("holidayRegionValueLabel()")).toBe("Kein Ferienkalender");
  });

  test("once a state is stored the suggestion disappears and the stored row is pressed", () => {
    const { window } = loadApp();
    prepare(window, "DE-BY");
    const rows = window.eval("holidayRegionSheet()").querySelectorAll(".opt");
    expect([...rows].some((row) => row.classList.contains("suggested"))).toBe(false);
    const pressed = [...rows].filter((row) => row.getAttribute("aria-pressed") === "true");
    expect(pressed.length).toBe(1);
    expect(pressed[0].querySelector("b").textContent).toBe("Bayern");
  });

  test("a stored state without usable data says so in the settings row", () => {
    const { window } = loadApp();
    prepare(window, "DE-NI");
    window.eval('state.holidays = { status: "unknown", stale: false, days: {}, weeks: [], periods: [] };');
    expect(window.eval("holidayRegionValueLabel()")).toBe("Niedersachsen · keine Daten");
  });
});
