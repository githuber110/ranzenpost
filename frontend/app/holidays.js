const HOLIDAY_STATUS_OK = "ok";
const HOLIDAY_STATUS_UNKNOWN = "unknown";
const HOLIDAY_COVERAGE_FULL = "full";
const HOLIDAY_KIND_PUBLIC = "public";
const HOLIDAY_CONFIDENCE_HIGH = "high";
const HOLIDAY_SOURCE_LANGUAGE = "de";
const HOLIDAY_WINDOW_TRAIL_DAYS = 20;
const HOLIDAY_RESUME_SEARCH_DAYS = 28;
const HOLIDAY_SCHOOL_DAYS = 5;
const HOLIDAY_NAME_SIZES = [12, 11, 10];
const HOLIDAY_GLYPH_RATIO = 0.55;
const HOLIDAY_COLUMN_WIDTH = 44;
const HOLIDAY_COLUMN_GAP = 4;
const HOLIDAY_FIELD_PADDING = 8;
function holidayBox(id) {
  const boxes = state.holidays && typeof state.holidays === "object" ? state.holidays : {};
  const wanted = id || currentConnectionId();
  if (wanted && boxes[wanted]) return boxes[wanted];
  const ids = Object.keys(boxes);
  return ids.length === 1 ? boxes[ids[0]] : null;
}

function holidayData(id) {
  const data = holidayBox(id);
  return data && data.status === HOLIDAY_STATUS_OK ? data : null;
}

function holidayDay(iso, id) {
  const data = holidayData(id);
  return (data && data.days && data.days[iso]) || null;
}

function holidayWeek(mondayIso) {
  const data = holidayData();
  if (!data || !Array.isArray(data.weeks)) return null;
  return data.weeks.find((week) => week.start === mondayIso) || null;
}

function holidayPeriod(periodId, id) {
  const data = holidayData(id);
  if (!data || !periodId || !Array.isArray(data.periods)) return null;
  return data.periods.find((period) => period.id === periodId) || null;
}

function holidayName(entry) {
  if (!entry) return "";
  if (entry.name_key && hasMessage(entry.name_key)) return t(entry.name_key);
  return entry.name || "";
}

function holidayNameLang(entry) {
  if (!entry) return null;
  if (entry.name_key && hasMessage(entry.name_key)) return null;
  return entry.name ? HOLIDAY_SOURCE_LANGUAGE : null;
}

function holidayBlocksLessons(iso) {
  const day = holidayDay(iso);
  return !!(day && day.free && day.overrides_lessons);
}

function holidayIsUncertain(iso) {
  const day = holidayDay(iso);
  return !!(day && day.free && !day.overrides_lessons);
}

function holidayRegionLabel(code) {
  const parts = String(code || "").split("-");
  if (parts.length < 2 || !parts[1]) return "";
  const key = `holidays.region.${parts[1].toLowerCase()}`;
  return hasMessage(key) ? t(key) : String(code);
}

function holidayRegionOptionLabel(region) {
  if (region.name_key && hasMessage(region.name_key)) return t(region.name_key);
  return holidayRegionLabel(region.code) || String(region.code || "");
}

function holidayRangeLabel(period) {
  const start = period ? parseIsoDay(period.start) : null;
  const end = period ? parseIsoDay(period.end) : null;
  if (!start || !end) return "";
  return `${formatShortDate(start)} – ${formatShortDate(end)}`;
}

function holidayResumeDate(from) {
  const data = holidayData();
  if (!data || !data.days) return null;
  for (let offset = 0; offset < HOLIDAY_RESUME_SEARCH_DAYS; offset += 1) {
    const date = addDays(from, offset);
    const day = data.days[isoDate(date)];
    if (!day) return null;
    if (!day.free && !day.weekend) return date;
  }
  return null;
}

function holidayResumeFallback(period) {
  const end = period ? parseIsoDay(period.end) : null;
  if (!end) return null;
  let date = addDays(end, 1);
  while (weekdayIndex(date) > HOLIDAY_SCHOOL_DAYS) date = addDays(date, 1);
  return date;
}

function holidayResumeLabel(from, period) {
  const date = holidayResumeDate(from) || holidayResumeFallback(period);
  if (!date) return "";
  return t("holidays.week.resume", {
    date: t("holidays.date.weekday", { weekday: formatWeekdayShort(date), date: formatShortDate(date) }),
  });
}

function holidayFieldSizing(name, span) {
  const width = span * HOLIDAY_COLUMN_WIDTH + (span - 1) * HOLIDAY_COLUMN_GAP - HOLIDAY_FIELD_PADDING;
  const longest = String(name || "")
    .split(/\s+/)
    .reduce((max, word) => Math.max(max, word.length), 0);
  for (let step = 0; step < HOLIDAY_NAME_SIZES.length; step += 1) {
    if (longest <= width / (HOLIDAY_NAME_SIZES[step] * HOLIDAY_GLYPH_RATIO)) return { step, force: false };
  }
  return { step: HOLIDAY_NAME_SIZES.length - 1, force: true };
}

function holidayFullWeek(monday, data) {
  if (!data || data.error || !Array.isArray(data.lessons)) return null;
  const week = holidayWeek(isoDate(monday));
  if (!week || week.coverage !== HOLIDAY_COVERAGE_FULL || !week.overrides_lessons) return null;
  return week;
}

function holidayWeekLabel(week) {
  const primary = week ? week.primary : null;
  const name = holidayName(primary);
  if (name) return name;
  if (week && week.label_key && hasMessage(week.label_key)) return t(week.label_key);
  return t("holidays.week.full");
}

function holidayWeekSummary(week) {
  if (!week) return "";
  if (week.coverage === HOLIDAY_COVERAGE_FULL) return holidayWeekLabel(week);
  if (week.free_school_days > 0) return tCount("holidays.week.freeDays", week.free_school_days);
  return "";
}

function holidaySheet(entry, title) {
  const period = entry && entry.period_id ? holidayPeriod(entry.period_id) : entry;
  const kind = (entry && entry.kind) || (period && period.kind) || "";
  const facts = [[t("holidays.fact.kind"), kind === HOLIDAY_KIND_PUBLIC ? t("holidays.day.public") : t("holidays.kind.school")]];
  const range = holidayRangeLabel(period);
  if (range) facts.push([t("holidays.fact.range"), range]);
  const region = holidayRegionLabel(currentConfig().holiday_region);
  if (region) facts.push([t("holidays.fact.region"), region]);
  return sheet(title, [factList(facts), el("p", { class: "sheet-hint" }, t("holidays.source"))]);
}

function holidayFullField(week, monday) {
  const primary = week.primary || null;
  const name = holidayWeekLabel(week);
  const classes = ["tt-hol", "full"];
  if (primary && primary.kind === HOLIDAY_KIND_PUBLIC) classes.push("public");
  const meta = holidayResumeLabel(monday, primary) || holidayRangeLabel(primary);
  return el("button", {
    class: classes.join(" "),
    type: "button",
    "aria-label": t("holidays.aria.field", { name }),
    style: "grid-column:2 / span 5;grid-row:2",
    onclick: () => openSheet(() => holidaySheet(primary, name)),
  }, [
    icon("upcoming", 20),
    el("span", { class: "tt-hol-text" }, [
      el("span", { class: "name", lang: holidayNameLang(primary) }, name),
      meta ? el("span", { class: "meta" }, meta) : null,
    ]),
  ]);
}

function holidayRunMeta(entry, monday) {
  const period = holidayPeriod(entry.period_id);
  if (!period) return "";
  const friday = isoDate(addDays(monday, HOLIDAY_SCHOOL_DAYS - 1));
  const mondayIso = isoDate(monday);
  const end = parseIsoDay(period.end);
  const start = parseIsoDay(period.start);
  if (end && period.end <= friday) return t("holidays.field.until", { date: formatShortDate(end) });
  if (start && period.start >= mondayIso) return t("holidays.field.from", { date: formatShortDate(start) });
  return holidayRangeLabel(period);
}

function holidayRunField(entry, monday, index, span, maxPeriod) {
  const name = holidayName(entry) || (entry.kind === HOLIDAY_KIND_PUBLIC ? t("holidays.day.public") : t("holidays.day.free"));
  if (!name) return null;
  const sizing = holidayFieldSizing(name, span);
  const classes = ["tt-hol"];
  if (entry.kind === HOLIDAY_KIND_PUBLIC) classes.push("public");
  if (sizing.step) classes.push(`sz-${sizing.step}`);
  if (sizing.force) classes.push("brk");
  const meta = span > 1 ? holidayRunMeta(entry, monday) : "";
  return el("button", {
    class: classes.join(" "),
    type: "button",
    "aria-label": t("holidays.aria.field", { name }),
    style: `grid-column:${index + 2} / span ${span};grid-row:2 / span ${maxPeriod}`,
    onclick: () => openSheet(() => holidaySheet(entry, name)),
  }, [
    el("span", { class: "name", lang: holidayNameLang(entry) }, name),
    meta ? el("span", { class: "meta" }, meta) : null,
  ]);
}

function holidayRunFields(monday, blocked, maxPeriod) {
  const fields = [];
  let index = 0;
  while (index < HOLIDAY_SCHOOL_DAYS) {
    if (!blocked[index]) {
      index += 1;
      continue;
    }
    const entry = holidayDay(isoDate(addDays(monday, index)));
    let last = index;
    while (last + 1 < HOLIDAY_SCHOOL_DAYS && blocked[last + 1]) {
      const next = holidayDay(isoDate(addDays(monday, last + 1)));
      if (!next || !entry || next.period_id !== entry.period_id) break;
      last += 1;
    }
    if (entry) {
      const field = holidayRunField(entry, monday, index, last - index + 1, maxPeriod);
      if (field) fields.push(field);
    }
    index = last + 1;
  }
  return fields;
}

function holidayTodayLines(iso, lessonCount, id) {
  const day = holidayDay(iso, id);
  if (!day || !day.free) return null;
  if (lessonCount && !day.overrides_lessons) return null;
  const name = holidayName(day);
  if (!name) return null;
  const date = parseIsoDay(iso);
  const detail = day.kind === HOLIDAY_KIND_PUBLIC
    ? t("holidays.day.public")
    : (date ? holidayResumeLabel(date, holidayPeriod(day.period_id, id)) : "");
  return [
    el("p", { class: "dlg-text", style: "margin:0" }, [el("b", { lang: holidayNameLang(day) }, name)]),
    detail ? el("p", { class: "dlg-text", style: "margin:4px 0 0" }, detail) : null,
  ];
}

function holidayTodayCard(iso, lessonCount, id) {
  const lines = holidayTodayLines(iso, lessonCount, id);
  return lines ? el("div", { class: "card" }, lines) : null;
}

async function loadHolidays() {
  const monday = startOfWeek(new Date());
  const start = isoDate(addDays(monday, 7 * WEEK_MIN));
  const end = isoDate(addDays(monday, 7 * WEEK_MAX + HOLIDAY_WINDOW_TRAIL_DAYS));
  const ids = readySchools().map((entry) => entry.id);
  if (!ids.length) ids.push("");
  const boxes = {};
  await Promise.all(ids.map(async (id) => {
    try {
      const query = id ? `&connection=${encodeURIComponent(id)}` : "";
      const data = await getJson(`api/holidays?start=${start}&end=${end}${query}`);
      boxes[id] = data && typeof data === "object" ? data : null;
    } catch (error) {
      boxes[id] = null;
    }
  }));
  state.holidays = boxes;
}

async function loadHolidayRegions() {
  try {
    const data = await getJson("api/holidays/regions");
    state.holidayRegions = (data && data.regions) || [];
  } catch (error) {
    state.holidayRegions = [];
  }
  rerender();
}

async function loadHolidaySuggestion() {
  try {
    const data = await getJson(`api/holidays/region-suggestion?connection=${encodeURIComponent(editingConnectionId())}`);
    state.holidaySuggestion = data && typeof data === "object" ? data : null;
  } catch (error) {
    state.holidaySuggestion = null;
  }
  rerender();
}

function holidaySuggestionCode() {
  const suggestion = state.holidaySuggestion;
  if (!suggestion || suggestion.confidence !== HOLIDAY_CONFIDENCE_HIGH) return "";
  return suggestion.region || "";
}
