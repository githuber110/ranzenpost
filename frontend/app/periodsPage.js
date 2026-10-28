const SETTINGS_PAGE_PERIODS = "periods";
const SETTINGS_PAGE_ENTRY = "entry";
const SETTINGS_PAGES_IN_MAIN = [SETTINGS_PAGE_PERIODS, SETTINGS_PAGE_ENTRY];
const SETTINGS_DETAIL_HELP = "help";
const PERIOD_STEP = 5;
const PERIOD_SLIDER_LIMIT = 240;
const PERIOD_ADDED_GAP = 5;
const PERIOD_SHORT_LIMIT = 120;
const ENTRY_FALLBACK_START = 15 * 60;
const ENTRY_INTERVAL_MIN = 2;
const ENTRY_INTERVAL_MAX = 8;
const ENTRY_LOOKAHEAD_DAYS = 14;
const WEEK_DAY_INDEXES = [0, 1, 2, 3, 4, 5, 6];

function periodRules() {
  return window.RanzenpostPeriods;
}

function periodsData(id) {
  const box = state.periods && state.periods[id];
  if (!box) {
    if (id) autoLoad(`periods:${id}`, () => loadPeriods(id));
    return null;
  }
  return box;
}

function storePeriods(id, data) {
  state.periods = Object.assign({}, state.periods, { [id]: data });
}

async function loadPeriods(id) {
  let data;
  try {
    data = await getJson(`api/connections/${encodeURIComponent(id)}/periods`);
  } catch (error) {
    data = { failed: true };
  }
  storePeriods(id, data);
  rerender();
}

function periodsReady(data) {
  return !!(data && !data.failed && Array.isArray(data.grid) && Array.isArray(data.entries));
}

function periodChildren(id) {
  return state.children.filter((child) => schoolOfChild(child) === id);
}

function periodChildIds(id) {
  return periodChildren(id).map((child) => String(child.child_id || periodRules().rawChild(child.key)));
}

function periodChildOf(id, raw) {
  return periodChildren(id).find((child) => String(child.child_id || periodRules().rawChild(child.key)) === String(raw)) || null;
}

function clockLabel(minutes) {
  if (minutes === null || minutes === undefined) return "";
  return minutes >= periodRules().DAY_MINUTES ? t("periods.midnight") : clockText(minutes);
}

function rangeLabel(start, end) {
  return t("periods.range", { start: clockLabel(start), end: clockLabel(end) });
}

function durationLabel(minutes) {
  const value = Math.max(0, Math.round(minutes));
  if (value <= PERIOD_SHORT_LIMIT) return t("periods.duration.minutes", { minutes: formatNumber(value) });
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  return rest
    ? t("periods.duration.hoursMinutes", { hours: formatNumber(hours), minutes: formatNumber(rest) })
    : t("periods.duration.hours", { hours: formatNumber(hours) });
}

function lessonLabel(number) {
  return t("settings.periods.label", { number: formatNumber(number) });
}

function hhmm(minutes) {
  return periodRules().clockOf(Math.min(minutes, periodRules().DAY_MINUTES - 1));
}

function periodsSettingRow(id, config) {
  const data = state.periods && state.periods[id];
  const hits = periodsReady(data) ? data.entries.filter((entry) => entry.status && entry.status.state !== periodRules().STATE_OK).length : 0;
  return el("button", { class: "setting-row periods-setting", type: "button", onclick: () => openPeriodsPage(id) }, [
    el("span", { class: "lbl" }, t("settings.periods.sheet")),
    hits ? el("span", { class: "tag warn periods-hints" }, [icon("alert", 12), tCount("periods.hints", hits)]) : null,
    el("span", { class: "val" }, periodTimesLabel(config, id)),
    el("span", { class: "chev" }, [icon("chevron", 16)]),
  ]);
}

function openPeriodsPage(id) {
  state.periodsPage = { school: id, adjusting: false, returnSchool: state.settingsSchoolId || null };
  state.periodsDetail = null;
  storePeriods(id, null);
  openSettingsPage(SETTINGS_PAGE_PERIODS);
}

function closePeriodsPage() {
  const page = state.periodsPage;
  state.periodsPage = null;
  state.periodsDetail = null;
  state.settingsPage = null;
  dropSheet();
  if (page && page.returnSchool && connectionOf(page.returnSchool)) state.settingsSchoolId = page.returnSchool;
  state._scrollTop = true;
  render();
}

function periodsPaneActive() {
  if (layoutMode() !== "desk") return false;
  if (state.view === "settings" && state.settingsPage === SETTINGS_PAGE_PERIODS) return true;
  return state.view === "timetable" && !!state.periodsDetail;
}

function togglePeriodsAdjust() {
  const page = state.periodsPage;
  if (!page) return;
  page.adjusting = !page.adjusting;
  if (!page.adjusting && state.periodsDetail && state.periodsDetail.kind === "lesson") closePeriodsDetail();
  else rerender();
}

function periodsPageView() {
  const page = state.periodsPage;
  const view = el("div", { class: "periods-page" });
  if (!page) return view;
  const id = page.school;
  if (manySchools()) view.append(el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, schoolFullName(id))]));
  view.append(el("p", { class: "section-lead periods-intro" }, t("periods.intro")));
  const data = periodsData(id);
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  if (!periodsReady(data)) {
    view.append(emptyBlock("alert", t("periods.failed.title"), t("periods.failed.text"), retryButton(() => loadPeriods(id))));
    return view;
  }
  const affected = data.entries.filter((entry) => entry.status && entry.status.state !== periodRules().STATE_OK).length;
  if (affected) view.append(el("div", { class: "note periods-collisions" }, [icon("alert", 16), el("span", {}, tCount("periods.collisions", affected))]));
  if (data.iserv_known && !data.iserv_ends) view.append(el("div", { class: "note info periods-no-end" }, [icon("info", 16), el("span", {}, t("periods.noEnd"))]));
  if (data.rollover && data.rollover.count) view.append(periodsRolloverNote(id, data.rollover));
  view.append(periodsLessonBlock(id, data));
  view.append(periodsEntriesBlock(id, data));
  view.append(periodsHomeAssistantBlock(id));
  return view;
}

function periodsHomeAssistantBlock(id) {
  const on = connectionConfig(id).own_entries_ha === true;
  return el("section", { class: "settings-group spaced periods-ha" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("periods.ha.section"))]),
    el("div", { class: "rows" }, [
      el("div", { class: "periods-ha-row" }, [
        el("div", { class: "periods-ha-text" }, [el("b", {}, t("periods.ha.label")), el("small", {}, t("periods.ha.hint"))]),
        switchButton(on, t("periods.ha.label"), () => toggleOwnEntriesHa(id, !on)),
      ]),
    ]),
  ]);
}

async function toggleOwnEntriesHa(id, on) {
  focusAfterRender(".periods-ha .switch");
  const result = await persistConnection(id, { own_entries_ha: on });
  rerender();
  announceSave(result);
}

function periodsRolloverNote(id, rollover) {
  const busy = state.periodsBusy === `rollover:${id}`;
  return el("div", { class: "note info periods-rollover" }, [
    icon("info", 16),
    el("div", { class: "periods-rollover-main" }, [
      el("span", {}, tCount("periods.rollover.note", rollover.count, { date: dateLabel(rollover.until) })),
      el("small", {}, t("periods.rollover.range", { from: dateLabel(rollover.from), to: dateLabel(rollover.to) })),
      el("button", {
        class: "btn slim periods-rollover-go",
        type: "button",
        disabled: busy ? "" : null,
        "aria-busy": busy ? "true" : null,
        onclick: () => rollOverEntries(id),
      }, t("periods.rollover.action")),
    ]),
  ]);
}

async function rollOverEntries(id) {
  if (state.periodsBusy) return;
  state.periodsBusy = `rollover:${id}`;
  rerender();
  const data = await periodsRequest(id, "own-entries/rollover", "POST");
  state.periodsBusy = "";
  rerender();
  if (data) toast(apiMessage(data, "common.saved"));
}

function periodsLeadText(data) {
  const grid = data.grid;
  if (!grid.length) return t("periods.lead.empty");
  const changed = grid.filter((row) => row.own_start || row.own_duration || row.added).length;
  if (changed) return tCount("periods.lead.custom", grid.length, { changed: formatNumber(changed) });
  return data.iserv_ends ? tCount("periods.lead.iserv", grid.length) : tCount("periods.lead.standard", grid.length);
}

function periodsLessonBlock(id, data) {
  const page = state.periodsPage;
  const grid = data.grid;
  const changed = grid.some((row) => row.own_start || row.own_duration || row.added);
  const list = el("div", { class: "rows periods-list" });
  list.append(el("div", { class: "periods-lead" }, [
    el("div", { class: "periods-lead-main" }, [
      el("b", {}, changed ? t("settings.periods.custom") : t("settings.periods.asIserv")),
      el("small", {}, periodsLeadText(data)),
    ]),
    el("button", {
      class: "btn ghost slim periods-adjust",
      type: "button",
      "aria-pressed": String(!!page.adjusting),
      onclick: togglePeriodsAdjust,
    }, page.adjusting ? t("periods.done") : t("settings.periods.edit")),
  ]));
  grid.forEach((row, index) => {
    list.append(periodLessonRow(id, row));
    const gap = grid[index + 1] ? periodGapRow(id, data, row, grid[index + 1]) : null;
    if (gap) list.append(gap);
  });
  if (page.adjusting) list.append(addLessonRow(id, grid));
  const block = el("section", { class: "settings-group periods-lessons" }, [list]);
  if (page.adjusting && grid.some((row) => row.own_start || row.own_duration)) {
    block.append(el("div", { class: "periods-links" }, [
      el("button", { class: "link-btn periods-reset-all", type: "button", onclick: () => resetAllLessons(id) }, [icon("restore", 16), t("periods.resetAll")]),
      el("span", { class: "hint" }, t("periods.resetAll.hint")),
    ]));
  }
  return block;
}

function lessonSourceNode(row) {
  const P = periodRules();
  if (row.added) return el("small", { class: "own" }, t("periods.own.lesson"));
  if (row.source === "saved") return el("small", {}, t("periods.source.saved"));
  const source = row.source === "standard" ? t("periods.source.standardShort") : t("periods.source.iservShort");
  const iservStart = P.minutesOf(row.iserv_start);
  if (row.own_start && row.own_duration) {
    return el("small", { class: "own" }, t("periods.own.both", { range: rangeLabel(iservStart, iservStart + row.iserv_duration) }));
  }
  if (row.own_duration) return el("small", { class: "own" }, t("periods.own.duration", { source, duration: durationLabel(row.iserv_duration) }));
  if (row.own_start) return el("small", { class: "own" }, t("periods.own.start", { time: clockLabel(iservStart) }));
  return el("small", {}, row.source === "standard" ? t("periods.source.standard", { duration: durationLabel(row.duration) }) : t("periods.source.iserv"));
}

function periodDetailIs(kind, key) {
  const detail = state.periodsDetail;
  if (!detail || detail.kind !== kind) return false;
  return kind === "lesson" ? detail.number === key : detail.id === key;
}

function periodLessonRow(id, row) {
  const P = periodRules();
  const adjusting = !!(state.periodsPage && state.periodsPage.adjusting);
  const start = P.minutesOf(row.start);
  const end = row.end === "24:00" ? P.DAY_MINUTES : P.minutesOf(row.end);
  const classes = ["prow"];
  if (periodDetailIs("lesson", row.number)) classes.push("sel");
  const attrs = { class: classes.join(" "), "data-period": String(row.number) };
  if (adjusting) {
    attrs.type = "button";
    attrs.onclick = () => openLessonEditor(id, row.number);
  }
  return el(adjusting ? "button" : "div", attrs, [
    el("span", { class: row.added ? "pnum own" : "pnum" }, formatNumber(row.number)),
    el("span", { class: "pmain" }, [el("b", {}, rangeLabel(start, end)), lessonSourceNode(row)]),
    el("span", { class: row.own_duration || row.added ? "pdur own" : "pdur" }, durationLabel(row.duration)),
    adjusting ? el("span", { class: "chev" }, [icon("chevron", 16)]) : null,
  ]);
}

function periodGapRow(id, data, row, next) {
  const P = periodRules();
  const end = P.minutesOf(row.end);
  const nextStart = P.minutesOf(next.start);
  if (end === null || nextStart === null || nextStart <= end) return null;
  const start = P.minutesOf(row.start);
  const pauses = data.entries.filter((entry) => entry.type === P.TYPE_PAUSE && P.startOf(entry) >= start && P.startOf(entry) < nextStart);
  if (pauses.length) {
    const warn = pauses.some((entry) => entry.status && entry.status.state !== P.STATE_OK);
    const parts = pauses.map((entry) => {
      const status = entry.status || {};
      if (status.state === P.STATE_HIDDEN) return `${entry.name} · ${t("periods.tag.hidden", { number: formatNumber(status.number) })}`;
      if (status.state === P.STATE_CUT) return `${entry.name} · ${durationLabel(P.minutesOf(status.end) - P.minutesOf(status.start))}`;
      return `${entry.name} · ${durationLabel(entry.duration)}`;
    });
    return el("div", { class: warn ? "pgap named warn" : "pgap named" }, [iservText("span", { class: "gl" }, parts.join(" · "))]);
  }
  return el("button", {
    class: "pgap",
    type: "button",
    "data-gap": String(end),
    onclick: () => openEntryForm({ school: id, type: P.TYPE_PAUSE, start: end }),
  }, [
    el("span", { class: "gl" }, t("periods.gap.free", { duration: durationLabel(nextStart - end) })),
    el("span", { class: "ga" }, [icon("plus", 14), t("periods.gap.add")]),
  ]);
}

function addLessonRow(id, grid) {
  const P = periodRules();
  const last = grid[grid.length - 1];
  const start = last ? P.minutesOf(last.end) + PERIOD_ADDED_GAP : 8 * 60;
  const number = last ? last.number + 1 : 1;
  if (start + P.DEFAULT_MINUTES > P.DAY_MINUTES) return null;
  return el("button", { class: "setting-row periods-add-lesson", type: "button", onclick: () => addLesson(id, start) }, [
    el("span", { class: "lbl" }, [icon("plus", 16), t("periods.addLesson", { number: formatNumber(number) })]),
    el("span", { class: "val" }, t("periods.from", { time: clockLabel(start) })),
  ]);
}

function sortedEntries(entries) {
  const P = periodRules();
  return entries.slice().sort((a, b) => (P.startOf(a) || 0) - (P.startOf(b) || 0) || String(a.name).localeCompare(String(b.name)));
}

function periodsEntriesBlock(id, data) {
  const list = el("div", { class: "rows periods-entries" });
  if (!data.entries.length) list.append(el("div", { class: "row row-note" }, [el("p", { class: "dlg-text periods-empty" }, t("periods.entries.empty"))]));
  for (const entry of sortedEntries(data.entries)) list.append(entryListRow(id, entry));
  list.append(el("button", { class: "setting-row periods-add-entry", type: "button", onclick: () => openEntryForm({ school: id }) }, [
    el("span", { class: "lbl" }, [icon("plus", 16), t("periods.entries.add")]),
  ]));
  return el("section", { class: "settings-group spaced periods-entries-block" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("periods.entries"))]),
    list,
  ]);
}

function entryTypeLabel(type) {
  const P = periodRules();
  return t(`periods.entry.type.${P.TYPES.includes(type) ? type : P.TYPE_APPOINTMENT}`);
}

function entryRepeatShort(entry) {
  const P = periodRules();
  if (entry.repeat === P.REPEAT_ONCE) return isoLabel(entry.date);
  if (entry.repeat === P.REPEAT_DAILY) return t("periods.range", { start: weekdayLabel(0), end: weekdayLabel(4) });
  const days = (entry.days || []).map(weekdayLabel).join(", ");
  return entry.repeat === P.REPEAT_WEEKS ? `${t("periods.repeat.weeksShort", { weeks: formatNumber(entry.interval) })} · ${days}` : days;
}

function entryForShort(id, entry) {
  if (!entry.child) return t("periods.for.all");
  const child = periodChildOf(id, entry.child);
  return child ? childFirstName(child) : t("periods.for.all");
}

function entryStatusTag(entry) {
  const P = periodRules();
  const status = entry.status || {};
  if (status.state === P.STATE_HIDDEN) return el("span", { class: "tag warn" }, [icon("alert", 12), t("periods.tag.hidden", { number: formatNumber(status.number) })]);
  if (status.state === P.STATE_CUT) return el("span", { class: "tag warn" }, t("periods.tag.cut", { duration: durationLabel(P.minutesOf(status.end) - P.minutesOf(status.start)) }));
  return null;
}

function entryListRow(id, entry) {
  const P = periodRules();
  const start = P.startOf(entry);
  return el("button", {
    class: periodDetailIs("entry", entry.id) ? "row periods-entry open" : "row periods-entry",
    type: "button",
    "data-entry": entry.id,
    onclick: () => openEntryDetail(id, entry.id),
  }, [
    el("span", { class: "row-dot" }, [el("i", { class: "ring" })]),
    el("span", { class: "row-main" }, [
      iservText("span", { class: "row-title" }, entry.name),
      el("span", { class: "row-sub" }, [entryTypeLabel(entry.type), entryRepeatShort(entry), entryForShort(id, entry)].join(" · ")),
    ]),
    el("span", { class: "row-side" }, [el("span", { class: "row-meta" }, rangeLabel(start, start + entry.duration)), entryStatusTag(entry)]),
  ]);
}

function openPeriodsDetail(detail) {
  state.periodsDetail = detail;
  if (periodsPaneActive()) {
    dropSheet();
    rerender();
    return;
  }
  if (detail.kind === "form" && layoutMode() === "phone") {
    dropSheet();
    openEntryPage();
    return;
  }
  openSheet(periodsDetailSheet, () => {
    state.periodsDetail = null;
    rerender();
  });
}

function periodsDetailSheet() {
  const parts = periodsDetailParts();
  return sheet(parts.title, parts.body, parts.foot);
}

function closePeriodsDetail() {
  const onPage = state.view === "settings" && state.settingsPage === SETTINGS_PAGE_ENTRY;
  state.periodsDetail = null;
  if (state.sheet === periodsDetailSheet) dropSheet();
  if (onPage) return closeEntryPage();
  rerender();
  return null;
}

function openEntryPage() {
  state.entryReturn = { view: state.view, page: state.settingsPage };
  openSettingsPage(SETTINGS_PAGE_ENTRY);
}

function closeEntryPage() {
  const back = state.entryReturn || {};
  state.entryReturn = null;
  state.periodsDetail = null;
  if (back.page === SETTINGS_PAGE_PERIODS && state.periodsPage) {
    state.settingsPage = SETTINGS_PAGE_PERIODS;
    state._scrollTop = true;
    render();
    return;
  }
  state.settingsPage = null;
  if (back.view && back.view !== "settings" && viewAvailable(back.view)) {
    setView(back.view);
    return;
  }
  render();
}

function periodsDetailParts() {
  const detail = state.periodsDetail;
  const empty = { title: t("settings.periods.sheet"), body: [], foot: null, onClose: closePeriodsDetail, chat: false, extra: null };
  if (!detail) return empty;
  const data = periodsData(detail.school);
  if (!periodsReady(data)) return Object.assign(empty, { body: [loadingBlock()] });
  const parts = detail.kind === "lesson" ? lessonEditorParts(detail, data)
    : detail.kind === "entry" ? entryDetailParts(detail, data)
      : entryFormParts(detail, data);
  return Object.assign(empty, parts || {});
}

function stepper(label, value, onStep, canLower, canRaise, name, onType) {
  const shown = onType ? stepperTimeInput(label, value, onType) : el("span", { class: "val", "aria-label": label }, value);
  return el("div", { class: `stepper ${name}` }, [
    el("button", { class: "sbtn", type: "button", "aria-label": t("periods.earlier", { minutes: formatNumber(PERIOD_STEP) }), disabled: canLower ? null : "disabled", onclick: () => onStep(-PERIOD_STEP) }, [icon("minus", 18)]),
    shown,
    el("button", { class: "sbtn", type: "button", "aria-label": t("periods.later", { minutes: formatNumber(PERIOD_STEP) }), disabled: canRaise ? null : "disabled", onclick: () => onStep(PERIOD_STEP) }, [icon("plus", 18)]),
  ]);
}

function stepperTimeInput(label, minutes, onType) {
  const input = el("input", { class: "val val-time", type: "time", step: "60", dir: "ltr", value: hhmm(minutes), "aria-label": label });
  input.addEventListener("change", () => {
    const chosen = periodRules().minutesOf(input.value);
    if (chosen === null) {
      input.value = hhmm(minutes);
      return;
    }
    onType(chosen);
  });
  return input;
}

function durationField(options) {
  const { value, max, start, maxText, onPick, name } = options;
  const P = periodRules();
  const limit = Math.max(1, max);
  const shown = Math.max(1, Math.min(value, limit));
  const sliderMax = Math.max(Math.min(limit, PERIOD_SLIDER_LIMIT), Math.min(PERIOD_STEP, limit));
  const sliderMin = Math.min(PERIOD_STEP, sliderMax);
  const big = el("span", { class: "dur-big" }, durationLabel(shown));
  const endText = el("span", { class: "dur-end" }, t("periods.until", { time: clockLabel(start + shown) }));
  const minutes = el("input", { class: "inp small dur-minutes", type: "number", inputmode: "numeric", min: "1", max: String(limit), step: String(PERIOD_STEP), value: String(shown), "aria-label": t("periods.field.minutes") });
  const end = el("input", { class: "inp small dur-endtime", type: "time", step: "300", value: hhmm(start + shown), "aria-label": t("periods.field.end") });
  const slider = el("input", { class: "range dur-range", type: "range", min: String(sliderMin), max: String(sliderMax), step: String(PERIOD_STEP), value: String(Math.min(shown, sliderMax)), "aria-label": t("periods.field.duration") });
  const clamp = (raw) => {
    const number = Math.round(Number(raw));
    if (!Number.isFinite(number)) return shown;
    return Math.max(1, Math.min(limit, number));
  };
  const live = (next) => {
    big.textContent = durationLabel(next);
    endText.textContent = t("periods.until", { time: clockLabel(start + next) });
    minutes.value = String(next);
    end.value = hhmm(start + next);
  };
  slider.addEventListener("input", () => {
    const next = clamp(slider.value);
    live(next);
    onPick(next, false);
  });
  slider.addEventListener("change", () => onPick(clamp(slider.value), true));
  minutes.addEventListener("change", () => onPick(clamp(minutes.value), true));
  end.addEventListener("change", () => {
    const chosen = P.minutesOf(end.value);
    onPick(chosen === null ? shown : clamp(chosen - start), true);
  });
  return el("div", { class: `field dur-field ${name || ""}` }, [
    el("span", { class: "lbl" }, t("periods.field.duration")),
    el("div", { class: "dur-top" }, [big, endText]),
    slider,
    el("div", { class: "dur-scale" }, [el("span", {}, durationLabel(sliderMin)), el("b", {}, durationLabel(sliderMax))]),
    el("div", { class: "dur-inputs" }, [
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.minutes")), minutes]),
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.end")), end]),
    ]),
    el("div", { class: "maxline" }, [icon("today", 14), el("span", {}, maxText)]),
  ]);
}

function lessonNeighbours(data, number) {
  const grid = data.grid;
  const index = grid.findIndex((row) => row.number === number);
  return { row: grid[index] || null, prev: index > 0 ? grid[index - 1] : null, next: index >= 0 ? grid[index + 1] || null : null };
}

function openLessonEditor(id, number) {
  const data = periodsData(id);
  if (!periodsReady(data)) return;
  const { row } = lessonNeighbours(data, number);
  if (!row) return;
  openPeriodsDetail({ kind: "lesson", school: id, number, start: periodRules().minutesOf(row.start), duration: row.duration });
}

function lessonConsequences(detail, data) {
  const P = periodRules();
  const rows = P.gridRows(data.grid);
  const trial = rows.map((row) => (row.number === detail.number ? Object.assign({}, row, { start: detail.start, end: Math.min(detail.start + detail.duration, P.DAY_MINUTES) }) : row));
  const children = periodChildIds(detail.school);
  const lines = [];
  for (const entry of data.entries) {
    const before = P.entryStatus(entry, rows, data.profiles, children);
    const after = P.entryStatus(entry, trial, data.profiles, children);
    if (after.state === P.STATE_HIDDEN && before.state !== P.STATE_HIDDEN) {
      lines.push(t("periods.consequence.hidden", { name: entry.name, number: formatNumber(after.number) }));
    } else if (after.state === P.STATE_CUT && (before.state !== P.STATE_CUT || before.start !== after.start || before.end !== after.end)) {
      lines.push(t("periods.consequence.cut", { name: entry.name, range: rangeLabel(after.start, after.end) }));
    }
  }
  return lines;
}

function lessonEditorParts(detail, data) {
  const P = periodRules();
  const { row, prev, next } = lessonNeighbours(data, detail.number);
  if (!row) return null;
  const minStart = prev ? P.minutesOf(prev.end) : 0;
  const maxEnd = next ? P.minutesOf(next.start) : P.DAY_MINUTES;
  const maxDuration = Math.max(1, maxEnd - detail.start);
  const iservStart = P.minutesOf(row.iserv_start);
  const reference = row.added ? t("periods.own.lesson")
    : row.source === "saved" ? t("periods.source.saved")
      : row.source === "standard" ? t("periods.lesson.standard", { time: clockLabel(iservStart) })
      : t("periods.lesson.iserv", { range: rangeLabel(iservStart, iservStart + row.iserv_duration) });
  const body = [el("p", { class: "dlg-text periods-reference" }, reference)];
  const step = (delta) => {
    detail.start += delta;
    if (detail.start + detail.duration > maxEnd) detail.duration = Math.max(1, maxEnd - detail.start);
    rerender();
  };
  body.push(el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("periods.field.start")),
    stepper(t("periods.field.start"), clockLabel(detail.start), step, detail.start - PERIOD_STEP >= minStart, detail.start + 2 * PERIOD_STEP <= maxEnd, "lesson-start"),
    el("span", { class: "hint" }, prev ? t("periods.earliest", { time: clockLabel(minStart), what: lessonLabel(prev.number) }) : t("periods.earliest.none")),
  ]));
  body.push(durationField({
    value: detail.duration,
    max: maxDuration,
    start: detail.start,
    maxText: next ? t("periods.max.until", { duration: durationLabel(maxDuration), what: lessonLabel(next.number) }) : t("periods.max.midnight", { duration: durationLabel(maxDuration) }),
    onPick: (value, commit) => {
      detail.duration = value;
      if (commit) rerender();
    },
    name: "lesson-duration",
  }));
  const lines = lessonConsequences(detail, data);
  if (lines.length) {
    body.push(el("div", { class: "note periods-consequences" }, [icon("alert", 16), el("span", {}, [el("b", {}, t("periods.consequence.title")), ...lines.map((line) => el("span", { class: "line" }, line))])]));
  }
  const links = [];
  const differs = iservStart !== null && (detail.start !== iservStart || detail.duration !== row.iserv_duration);
  if (differs) {
    links.push(el("button", { class: "link-btn periods-iserv-value", type: "button", onclick: () => { detail.start = iservStart; detail.duration = row.iserv_duration; rerender(); } }, [icon("restore", 16), row.source === "standard" ? t("periods.standardValue") : t("periods.iservValue")]));
  }
  if (row.added) {
    links.push(el("button", { class: "link-btn danger periods-remove-lesson", type: "button", onclick: () => removeLesson(detail.school, row.number) }, [icon("trash", 16), t("periods.removeLesson")]));
  }
  if (links.length) body.push(el("div", { class: "periods-links" }, links));
  return {
    title: lessonLabel(row.number),
    body,
    foot: [el("button", { class: "btn periods-apply", type: "button", onclick: () => saveLesson(detail) }, t("periods.apply"))],
  };
}

async function periodsRequest(id, path, method, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const outcome = await jsonRequest(`api/connections/${encodeURIComponent(id)}/${path}`, options, "periods.error.failed");
  if (!outcome.ok) {
    toast(outcome.message, "bad");
    return null;
  }
  storePeriods(id, outcome.data);
  return outcome.data;
}

async function refreshAfterGridChange() {
  state.timetable = null;
  state.overviewWeeks = {};
  state.overviewWeekMondays = {};
  try {
    state.config = await getJson("api/config");
  } catch (error) {
    return;
  }
  reloadTimetable();
}

async function saveLesson(detail) {
  const data = await periodsRequest(detail.school, `periods/lessons/${detail.number}`, "POST", { start: periodRules().clockOf(detail.start), duration: detail.duration });
  if (!data) return;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
  refreshAfterGridChange();
}

async function addLesson(id, start) {
  const data = await periodsRequest(id, "periods/lessons", "POST", { start: periodRules().clockOf(start), duration: periodRules().DEFAULT_MINUTES });
  if (!data) return;
  toast(apiMessage(data, "common.saved"));
  refreshAfterGridChange();
  if (data.number) openLessonEditor(id, data.number);
  else rerender();
}

async function removeLesson(id, number) {
  const data = await periodsRequest(id, `periods/lessons/${number}`, "DELETE");
  if (!data) return;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
  refreshAfterGridChange();
}

async function resetLesson(id, number) {
  const data = await periodsRequest(id, `periods/lessons/${number}/reset`, "POST");
  if (!data) return;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
  refreshAfterGridChange();
}

async function resetAllLessons(id) {
  const data = await periodsRequest(id, "periods/reset", "POST");
  if (!data) return;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
  refreshAfterGridChange();
}

function openEntryDetail(id, entryId) {
  openPeriodsDetail({ kind: "entry", school: id, id: entryId });
}

function entryRepeatLong(entry) {
  const P = periodRules();
  if (entry.repeat === P.REPEAT_ONCE) return t("periods.repeat.onceOn", { date: isoLabel(entry.date) });
  const word = entry.repeat === P.REPEAT_DAILY ? t("periods.repeat.dailyWord")
    : entry.repeat === P.REPEAT_WEEKS ? t("periods.repeat.weeksWord", { weeks: formatNumber(entry.interval) })
      : t("periods.repeat.weeklyWord");
  return t("periods.repeat.until", { repeat: `${word} · ${entryRepeatShort(entry)}`, date: dateLabel(entry.until) });
}

function entryForLong(id, entry) {
  if (!entry.child) return t("periods.for.allNamed", { names: periodChildren(id).map(childFirstName).join(", ") });
  const child = periodChildOf(id, entry.child);
  return child ? t("periods.for.only", { name: childFirstName(child) }) : t("periods.for.all");
}

function entryDetailParts(detail, data) {
  const P = periodRules();
  const entry = data.entries.find((item) => item.id === detail.id);
  if (!entry) return null;
  const status = entry.status || {};
  const body = [];
  if (status.state === P.STATE_HIDDEN) body.push(el("div", { class: "note periods-status" }, [icon("alert", 16), el("span", {}, t("periods.status.hidden", { number: formatNumber(status.number) }))]));
  if (status.state === P.STATE_CUT) body.push(el("div", { class: "note periods-status" }, [icon("alert", 16), el("span", {}, t("periods.status.cut", { range: rangeLabel(P.minutesOf(status.start), P.minutesOf(status.end)), number: formatNumber(status.number) }))]));
  const start = P.startOf(entry);
  const facts = [
    [t("periods.entry.type"), entryTypeLabel(entry.type)],
    [t("periods.detail.time"), `${rangeLabel(start, start + entry.duration)} · ${durationLabel(entry.duration)}`],
    [t("periods.field.repeat"), entryRepeatLong(entry)],
    [t("periods.field.for"), entryForLong(detail.school, entry)],
  ];
  if (entry.repeat !== P.REPEAT_ONCE) facts.push([t("periods.detail.holidays"), entry.holidays ? t("periods.holidays.yes") : t("periods.holidays.no")]);
  body.push(el("div", { class: "rows periods-facts" }, facts.map(([label, value]) => el("div", { class: "kv" }, [el("span", { class: "k" }, label), iservText("span", { class: "v" }, value)]))));
  if (entry.repeat !== P.REPEAT_ONCE) body.push(el("p", { class: "hint periods-no-exceptions" }, t("periods.noExceptions")));
  const foot = [el("button", {
    class: "btn periods-edit",
    type: "button",
    onclick: () => openEntryForm({ school: detail.school, entry }),
  }, status.state && status.state !== P.STATE_OK ? t("periods.fixTime") : t("periods.edit"))];
  const lesson = status.number ? data.grid.find((row) => row.number === status.number) : null;
  if (lesson && (lesson.own_start || lesson.own_duration)) {
    foot.push(el("button", { class: "link-btn periods-reset-lesson", type: "button", onclick: () => resetLesson(detail.school, lesson.number) }, [icon("restore", 16), t("periods.resetLesson", { number: formatNumber(lesson.number) })]));
  }
  foot.push(el("button", { class: "link-btn danger periods-delete", type: "button", onclick: () => deleteEntry(detail.school, entry) }, [icon("trash", 16), entry.repeat === P.REPEAT_ONCE ? t("periods.deleteEntry") : t("periods.deleteSeries")]));
  return { title: entry.name, body, foot: [el("div", { class: "btn-stack" }, foot)] };
}

async function deleteEntry(id, entry) {
  const sure = await confirmAction({
    title: entry.repeat === periodRules().REPEAT_ONCE ? t("periods.deleteEntry") : t("periods.deleteSeries"),
    text: t("periods.delete.text", { name: entry.name }),
    confirmLabel: t("periods.delete.confirm"),
    destructive: true,
  });
  if (!sure) {
    if (state.periodsDetail && !periodsPaneActive()) openPeriodsDetail(state.periodsDetail);
    return;
  }
  const data = await periodsRequest(id, `own-entries/${encodeURIComponent(entry.id)}`, "DELETE");
  if (!data) return;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
}

function entryContextDay(options) {
  if (options.date) return options.date;
  const today = isoDate(new Date());
  if (state.view !== "timetable") return today;
  const monday = weekMonday();
  const days = Array.from({ length: HOLIDAY_SCHOOL_DAYS }, (_, index) => isoDate(addDays(monday, index)));
  return days.includes(today) ? today : days[0];
}

function lastLessonEnd(id, childKey, iso) {
  const P = periodRules();
  const data = periodsData(id);
  const week = childKey ? overviewWeekData(childKey, state.view === "timetable" ? state.weekOffset || 0 : 0) : null;
  if (!periodsReady(data) || !week || !Array.isArray(week.lessons)) return null;
  const periods = P.regularPeriods(week.lessons)[iso] || [];
  const spans = P.spansFor(P.gridRows(data.grid), periods);
  return spans.length ? spans[spans.length - 1][1] : null;
}

function newEntryForm(options, data) {
  const P = periodRules();
  const type = options.type || P.TYPE_CLUB;
  const today = data.today || isoDate(new Date());
  const day = entryContextDay(options);
  const effectiveDay = day < today ? today : day;
  const childKey = options.child || state.childId;
  const child = childKey && connectionOfKey(childKey) === options.school ? P.rawChild(childKey) : "";
  const fallbackChild = periodChildIds(options.school)[0] || "";
  const start = options.start !== undefined ? options.start : lastLessonEnd(options.school, childKey, day) || ENTRY_FALLBACK_START;
  const form = {
    mode: "new",
    id: "",
    school: options.school,
    type,
    name: type === P.TYPE_PAUSE ? entryTypeLabel(P.TYPE_PAUSE) : "",
    start: Math.min(start, P.DAY_MINUTES - 1),
    duration: 0,
    repeat: P.REPEAT_WEEKLY,
    days: [Math.min(6, Math.max(0, P.weekdayOf(effectiveDay) || 0))],
    interval: ENTRY_INTERVAL_MIN,
    date: effectiveDay,
    from: effectiveDay,
    until: effectiveDay,
    holidays: false,
    child: child || fallbackChild,
    note: "",
    untilClamped: false,
    returnTo: options.fromPlan ? "timetable" : "",
  };
  applyEntryTypeDefaults(form, type, childKey && child ? child : fallbackChild);
  return form;
}

function defaultEntryChild(id) {
  const P = periodRules();
  if (state.childId && connectionOfKey(state.childId) === id) return P.rawChild(state.childId);
  return periodChildIds(id)[0] || "";
}

function applyEntryTypeDefaults(form, type, child) {
  const P = periodRules();
  form.type = type;
  if (type === P.TYPE_PAUSE) {
    form.repeat = P.REPEAT_DAILY;
    form.child = "";
  } else if (type === P.TYPE_CLUB) {
    form.repeat = P.REPEAT_WEEKLY;
    form.child = child || form.child;
  } else {
    form.repeat = P.REPEAT_ONCE;
    form.child = child || form.child;
  }
}

function entryTiming(form) {
  const candidate = entryCandidate(form);
  return JSON.stringify(["start", "duration", "repeat", "days", "interval", "date", "from", "until", "child"].map((key) => candidate[key]));
}

function entryUntouched(form) {
  return form.mode === "edit" && !!form.timing && entryTiming(form) === form.timing;
}

function editEntryForm(entry, id, data) {
  return {
    mode: "edit",
    id: entry.id,
    school: id,
    type: entry.type,
    name: entry.name,
    start: periodRules().startOf(entry),
    duration: entry.duration,
    repeat: entry.repeat,
    days: (entry.days || []).slice(),
    interval: entry.interval && entry.interval >= ENTRY_INTERVAL_MIN ? entry.interval : ENTRY_INTERVAL_MIN,
    date: entry.date || data.today,
    from: entry.from || data.today,
    until: entry.until || data.until_max,
    fromMin: entry.from_min || "",
    untilMax: entry.until_max || "",
    holidays: !!entry.holidays,
    child: entry.child || "",
    note: "",
    untilClamped: false,
    returnTo: "",
  };
}

function openEntryForm(options) {
  const id = options.school;
  const data = periodsData(id);
  if (!periodsReady(data)) {
    toast(t("periods.failed.title"), "bad");
    return;
  }
  const form = options.entry ? editEntryForm(options.entry, id, data) : newEntryForm(options, data);
  if (options.entry) form.timing = entryTiming(form);
  else form.duration = periodRules().defaultDuration(entryLimits(form, data).max);
  openPeriodsDetail({ kind: "form", school: id, form });
}

function entryCandidate(form) {
  const P = periodRules();
  return {
    id: form.id || "",
    type: form.type,
    name: form.name,
    start: P.clockOf(form.start),
    duration: form.duration,
    repeat: form.repeat,
    days: form.repeat === P.REPEAT_DAILY ? P.SCHOOL_DAYS.slice() : form.repeat === P.REPEAT_ONCE ? [] : form.days.slice().sort((a, b) => a - b),
    interval: form.repeat === P.REPEAT_WEEKS ? form.interval : 1,
    date: form.repeat === P.REPEAT_ONCE ? form.date : "",
    from: form.repeat === P.REPEAT_ONCE ? "" : form.from,
    until: form.repeat === P.REPEAT_ONCE ? "" : form.until,
    holidays: form.repeat === P.REPEAT_ONCE ? true : form.holidays,
    child: form.child,
  };
}

function entryLimits(form, data) {
  const P = periodRules();
  return P.limits(entryCandidate(form), data.entries, P.gridRows(data.grid), data.profiles, periodChildIds(form.school));
}

function blockLabel(block) {
  return block.number ? lessonLabel(block.number) : block.entry ? block.entry.name : "";
}

function entryProblem(form, limitsFound) {
  if (limitsFound.noDays) return t("periods.problem.days");
  if (form.repeat !== periodRules().REPEAT_ONCE && !periodRules().occurrenceDays(entryCandidate(form)).length) return t("periods.problem.empty");
  if (limitsFound.conflict && !entryUntouched(form)) {
    return t("periods.problem.conflict", { day: weekdayLabel(limitsFound.conflict.weekday), time: clockLabel(form.start), what: blockLabel(limitsFound.conflict.block) });
  }
  if (!String(form.name || "").trim()) return t("periods.problem.name");
  return "";
}

function segmentPick(options, value, onPick, name) {
  return el("div", { class: `segment periods-segment ${name}`, role: "radiogroup" }, options.map(([key, label]) => el("button", {
    type: "button",
    role: "radio",
    "aria-checked": String(value === key),
    "aria-selected": String(value === key),
    "data-value": String(key),
    onclick: () => onPick(key),
  }, [iservText("span", { class: "seg-label" }, label)])));
}

function entryFormParts(detail, data) {
  const P = periodRules();
  const form = detail.form;
  const found = entryLimits(form, data);
  if (!entryUntouched(form) && found.max >= 1 && form.duration > found.max) {
    form.duration = found.max;
    form.note = t("periods.clamped", { duration: durationLabel(found.max) });
  }
  const refit = () => {
    const again = entryLimits(form, data);
    if (!entryUntouched(form) && again.max >= 1 && form.duration > again.max) {
      form.duration = again.max;
      form.note = t("periods.clamped", { duration: durationLabel(again.max) });
    }
    rerender();
  };
  const body = [];
  body.push(el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("periods.entry.type")),
    segmentPick(P.TYPES.map((type) => [type, entryTypeLabel(type)]), form.type, (type) => {
      const hadDefault = !form.name || form.name === entryTypeLabel(P.TYPE_PAUSE);
      applyEntryTypeDefaults(form, type, form.child || defaultEntryChild(form.school));
      if (hadDefault) form.name = type === P.TYPE_PAUSE ? entryTypeLabel(P.TYPE_PAUSE) : "";
      form.duration = P.defaultDuration(entryLimits(form, data).max);
      form.note = "";
      rerender();
    }, "entry-type"),
  ]));
  const name = el("input", { class: "inp entry-name", type: "text", value: form.name, maxlength: "60", placeholder: t(`periods.placeholder.${form.type}`), "aria-label": t("periods.field.name") });
  name.addEventListener("input", () => {
    form.name = name.value;
    const button = root().querySelector(".entry-save");
    if (button) button.disabled = !!entryProblem(form, entryLimits(form, data));
  });
  body.push(el("label", { class: "field" }, [el("span", { class: "lbl" }, t("periods.field.name")), name]));
  const earliest = found.minWhat
    ? t("periods.earliest", { time: clockLabel(found.minStart), what: `${found.weekdays.length > 1 ? `${weekdayLabel(found.minWhat.weekday)} ` : ""}${blockLabel(found.minWhat.block)}` })
    : t("periods.earliest.none");
  body.push(el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("periods.field.start")),
    stepper(t("periods.field.start"), form.start, (delta) => { form.start += delta; form.note = ""; refit(); }, form.start - PERIOD_STEP >= found.minStart, found.max > PERIOD_STEP && form.start + 2 * PERIOD_STEP <= P.DAY_MINUTES, "entry-start", (chosen) => {
      form.start = Math.max(found.minStart, Math.min(chosen, P.DAY_MINUTES - PERIOD_STEP));
      form.note = form.start !== chosen ? t("periods.clamped.start", { time: clockLabel(form.start) }) : "";
      refit();
    }),
    el("span", { class: "hint" }, earliest),
  ]));
  const maxText = found.limit
    ? t("periods.max.until", { duration: durationLabel(found.max), what: `${weekdayLabel(found.limit.weekday)} ${blockLabel(found.limit.block)} ${clockLabel(found.limit.block.start)}` })
    : t("periods.max.midnight", { duration: durationLabel(found.max) });
  const durationMax = entryUntouched(form) ? Math.max(found.max, form.duration) : Math.max(found.max, 1);
  body.push(durationField({
    value: Math.max(1, Math.min(form.duration, durationMax)),
    max: durationMax,
    start: form.start,
    maxText,
    onPick: (value, commit) => {
      form.duration = value;
      form.note = "";
      if (commit) rerender();
    },
    name: "entry-duration",
  }));
  if (form.note) body.push(el("p", { class: "hint periods-note" }, form.note));
  const repeat = [segmentPick([
    [P.REPEAT_ONCE, t("periods.repeat.once")],
    [P.REPEAT_DAILY, t("periods.repeat.daily")],
    [P.REPEAT_WEEKLY, t("periods.repeat.weekly")],
    [P.REPEAT_WEEKS, t("periods.repeat.weeks")],
  ], form.repeat, (value) => {
    form.repeat = value;
    if ((value === P.REPEAT_WEEKLY || value === P.REPEAT_WEEKS) && !form.days.length) form.days = [P.weekdayOf(form.date) || 0];
    refit();
  }, "entry-repeat")];
  if (form.repeat === P.REPEAT_DAILY) {
    repeat.push(el("div", { class: "days" }, P.SCHOOL_DAYS.map((day) => el("button", { type: "button", "aria-pressed": "true", disabled: "disabled" }, weekdayLabel(day)))));
    repeat.push(el("span", { class: "hint" }, t("periods.repeat.dailyHint")));
  }
  if (form.repeat === P.REPEAT_WEEKLY || form.repeat === P.REPEAT_WEEKS) {
    repeat.push(el("div", { class: "days entry-days" }, WEEK_DAY_INDEXES.map((day) => el("button", {
      type: "button",
      "aria-pressed": String(form.days.includes(day)),
      "data-day": String(day),
      onclick: () => {
        form.days = form.days.includes(day) ? form.days.filter((item) => item !== day) : form.days.concat(day);
        refit();
      },
    }, weekdayLabel(day)))));
  }
  if (form.repeat === P.REPEAT_WEEKS) {
    repeat.push(el("div", { class: "stepper entry-interval" }, [
      el("span", { class: "flabel" }, t("periods.repeat.every")),
      el("button", { class: "sbtn", type: "button", "aria-label": t("periods.repeat.fewer"), disabled: form.interval > ENTRY_INTERVAL_MIN ? null : "disabled", onclick: () => { form.interval -= 1; rerender(); } }, [icon("minus", 18)]),
      el("span", { class: "val" }, t("periods.repeat.weeksCount", { weeks: formatNumber(form.interval) })),
      el("button", { class: "sbtn", type: "button", "aria-label": t("periods.repeat.more"), disabled: form.interval < ENTRY_INTERVAL_MAX ? null : "disabled", onclick: () => { form.interval += 1; rerender(); } }, [icon("plus", 18)]),
    ]));
  }
  body.push(el("div", { class: "field" }, [el("span", { class: "lbl" }, t("periods.field.repeat")), ...repeat]));
  body.push(entryDateFields(form, data, refit));
  const kids = periodChildren(form.school);
  if (kids.length > 1) {
    const options = [["", t("periods.for.allNamed", { names: kids.map(childFirstName).join(", ") })]]
      .concat(kids.map((child) => [String(child.child_id || P.rawChild(child.key)), childFirstName(child)]));
    body.push(el("div", { class: "field" }, [
      el("span", { class: "lbl" }, t("periods.field.for")),
      segmentPick(options, form.child, (value) => { form.child = value; refit(); }, "entry-for"),
    ]));
  }
  body.push(el("p", { class: "hint periods-horizon" }, t("periods.horizon")));
  const problem = entryProblem(form, found);
  const foot = [];
  if (problem) foot.push(el("p", { class: "hint warn periods-problem" }, problem));
  foot.push(el("button", {
    class: "btn entry-save",
    type: "button",
    disabled: problem ? "disabled" : null,
    onclick: () => saveEntry(detail),
  }, form.mode === "edit" ? t("common.save") : t("periods.entry.add")));
  return { title: form.mode === "edit" ? t("periods.entry.edit") : t("periods.entry.new"), body, foot };
}

function entryDateFields(form, data, refit) {
  const P = periodRules();
  const today = data.today || isoDate(new Date());
  if (form.repeat === P.REPEAT_ONCE) {
    const input = el("input", { class: "inp entry-date", type: "date", value: form.date, min: today, max: data.until_max, "aria-label": t("periods.field.date") });
    input.addEventListener("change", () => {
      if (!input.value) return;
      form.date = input.value > data.until_max ? data.until_max : input.value < today ? today : input.value;
      refit();
    });
    return el("label", { class: "field" }, [el("span", { class: "lbl" }, t("periods.field.date")), input]);
  }
  const limit = form.untilMax || data.until_max;
  const floor = form.fromMin || "";
  const from = el("input", { class: "inp entry-from", type: "date", value: form.from, min: floor || null, max: limit, "aria-label": t("periods.field.from") });
  const until = el("input", { class: "inp entry-until", type: "date", value: form.until, min: form.from, max: limit, "aria-label": t("periods.field.until") });
  from.addEventListener("change", () => {
    if (!from.value) return;
    form.from = from.value > limit ? limit : floor && from.value < floor ? floor : from.value;
    if (form.until < form.from) form.until = form.from;
    refit();
  });
  until.addEventListener("change", () => {
    const value = until.value;
    form.untilClamped = !!value && value > limit;
    form.until = !value || value > limit ? limit : value < form.from ? form.from : value;
    refit();
  });
  const summer = form.untilMax ? "" : data.summer_start;
  const hint = form.untilClamped
    ? summer ? t("periods.until.clamped", { date: dateLabel(summer) }) : t("periods.until.clampedPlain", { date: dateLabel(limit) })
    : summer ? t("periods.until.hint", { date: dateLabel(summer) }) : t("periods.until.hintPlain", { date: dateLabel(limit) });
  const holidays = el("input", { type: "checkbox", class: "entry-holidays" });
  holidays.checked = !!form.holidays;
  holidays.addEventListener("change", () => { form.holidays = holidays.checked; });
  const parts = [
    el("div", { class: "two" }, [
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.from")), from]),
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.until")), until]),
    ]),
  ];
  if (form.from && form.from === form.until) {
    parts.push(el("div", { class: "entry-single-day" }, [
      el("span", { class: "hint" }, t("periods.range.singleDay")),
      el("button", {
        class: "link-btn entry-until-summer",
        type: "button",
        onclick: () => {
          form.until = limit;
          form.untilClamped = false;
          refit();
        },
      }, t("periods.range.untilSummer")),
    ]));
  }
  parts.push(el("span", { class: form.untilClamped ? "hint warn" : "hint" }, hint));
  parts.push(el("label", { class: "check entry-holidays-check" }, [holidays, el("span", {}, [t("periods.holidays"), el("small", {}, t("periods.holidays.hint"))])]));
  return el("div", { class: "field entry-range" }, parts);
}

async function saveEntry(detail) {
  const form = detail.form;
  const candidate = entryCandidate(form);
  const payload = Object.assign({}, candidate, { name: String(form.name || "").trim() });
  delete payload.id;
  const path = form.mode === "edit" ? `own-entries/${encodeURIComponent(form.id)}` : "own-entries";
  const data = await periodsRequest(form.school, path, "POST", payload);
  if (!data) return;
  const back = form.returnTo;
  closePeriodsDetail();
  toast(apiMessage(data, "common.saved"));
  if (back && state.view !== back && viewAvailable(back)) setView(back);
}

function entryPageView() {
  const detail = state.periodsDetail;
  const view = el("div", { class: "entry-page" });
  if (!detail) return view;
  const parts = periodsDetailParts();
  for (const node of parts.body) view.append(node);
  if (parts.foot) view.append(el("div", { class: "entry-page-foot" }, parts.foot));
  return view;
}

function entryPageTitle() {
  const detail = state.periodsDetail;
  if (!detail || detail.kind !== "form") return t("periods.entry.new");
  return detail.form.mode === "edit" ? t("periods.entry.edit") : t("periods.entry.new");
}
