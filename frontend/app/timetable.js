async function loadTimetable() {
  const monday = isoDate(weekMonday());
  const timetable = await getJson(`api/timetable?child=${encodeURIComponent(state.childId)}&week=${state.weekOffset}`);
  const config = await getJson("api/config");
  return { timetable, config, monday };
}

function applyTimetable(loaded) {
  state.timetable = loaded.timetable;
  state.timetableMonday = loaded.monday || "";
  state.config = loaded.config;
}

function todayLessons(week, index) {
  const byPeriod = new Map();
  for (const lesson of week.lessons || []) {
    if (Number(lesson.day_of_week) !== index) continue;
    const period = Number(lesson.period);
    if (!byPeriod.has(period)) byPeriod.set(period, []);
    byPeriod.get(period).push(lesson);
  }
  return [...byPeriod.keys()].sort((a, b) => a - b).flatMap((period) => byPeriod.get(period));
}

function periodTimes(week, childId) {
  const config = childId ? connectionConfig(connectionOfKey(childId)) : currentConfig();
  return (week && week.period_times) || config.period_times || {};
}

function lessonRawTime(lesson, times) {
  if (!lesson) return "";
  const table = times || periodTimes(state.timetable);
  const chosen = String(table[String(lesson.period)] || "").trim();
  return chosen || String(lesson.start_time || "").trim();
}

function lessonTimeMinutes(lesson, times) {
  return timeMinutes(lessonRawTime(lesson, times));
}

function lessonTime(lesson, times) {
  const minutes = lessonTimeMinutes(lesson, times);
  return minutes === null ? "" : clockText(minutes);
}

function groupTodayLessons(lessons) {
  const order = [];
  const byPeriod = new Map();
  for (const lesson of lessons) {
    const period = Number(lesson.period);
    if (!byPeriod.has(period)) {
      byPeriod.set(period, []);
      order.push(period);
    }
    byPeriod.get(period).push(lesson);
  }
  return order.map((period) => ({ period, lessons: byPeriod.get(period) }));
}

function plainCard(text) {
  return el("div", { class: "card" }, [el("p", { class: "dlg-text", style: "margin:0" }, text)]);
}

function changeTag(kind) {
  if (!kind) return null;
  return el("span", { class: kind === "cancelled" ? "tag no" : "tag open" }, changeLabel(kind));
}

function rowClassNames(isPast) {
  return ["row", isPast ? "past" : ""].filter(Boolean).join(" ");
}

function markTag(mark) {
  if (!mark) return null;
  return el("span", { class: "tag exam" }, [
    el("span", { class: "ico-slot", html: iconSvg("exam", 11) }),
    iservText("span", {}, markLabel(mark)),
  ]);
}

function whenTag(when) {
  if (!when) return null;
  return el("span", { class: `row-when ${when}` }, t(when === "now" ? "overview.mark.now" : "overview.mark.next"));
}

function compactLessonTitle(lesson, kind) {
  const title = iservText("div", { class: "row-title" }, lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback"));
  if (kind === "cancelled") title.style.textDecoration = "line-through";
  return title;
}

function compactLesson(entry, isPast) {
  const lesson = entry.lesson;
  const kind = displayChangeKind(lesson, entry.childId);
  const dot = el("span", { class: "row-dot" }, [el("i", {})]);
  dot.firstChild.style.background = subjectDotColor(lesson);
  const sub = [lesson.room, teacherSurname(lesson)].filter(Boolean).join(" · ");
  const row = el("button", {
    class: rowClassNames(isPast),
    type: "button",
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId, overviewWeekLessons(entry.childId, lesson)),
  }, [
    dot,
    el("div", { class: "row-main" }, [compactLessonTitle(lesson, kind), sub ? iservText("div", { class: "row-sub" }, sub) : null, markTag(entry.mark)]),
    el("div", { class: "row-side" }, [
      whenTag(entry.when),
      el("span", { class: "row-meta" }, entry.time || periodShort(lesson.period)),
      changeTag(kind),
    ]),
  ]);
  if (entry.mark) row.classList.add("marked");
  return row;
}

function compactLessonPairItem(entry) {
  const lesson = entry.lesson;
  const kind = displayChangeKind(lesson, entry.childId);
  const dot = el("span", { class: "row-dot" }, [el("i", {})]);
  dot.firstChild.style.background = subjectDotColor(lesson);
  const sub = teacherSurname(lesson);
  const item = el("button", {
    class: "row-pair-item",
    type: "button",
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId, overviewWeekLessons(entry.childId, lesson)),
  }, [
    dot,
    el("div", { class: "row-main" }, [compactLessonTitle(lesson, kind), sub ? el("div", { class: "row-sub" }, sub) : null, markTag(entry.mark)]),
    changeTag(kind),
  ]);
  if (entry.mark) item.classList.add("marked");
  return item;
}

function compactCoursesRow(entries, isPast, courses) {
  const lessons = entries.map((entry) => entry.lesson);
  const childId = entries[0].childId;
  return el("button", {
    class: `${rowClassNames(isPast)} courses-row`,
    type: "button",
    onclick: () => openCoursesSheet(lessons, entries[0].time, childId, overviewWeekLessons(childId, lessons[0]), courses),
  }, [
    el("span", { class: "row-dot courses-dot" }, [el("i", {})]),
    el("div", { class: "row-main" }, [
      el("div", { class: "row-title" }, tCount("timetable.courses.parallel", lessons.length)),
      iservText("div", { class: "row-sub courses-codes" }, sortedCourseLessons(lessons).map((lesson) => lesson.subject_code || lesson.subject_label || "").join(", ")),
    ]),
    el("div", { class: "row-side" }, [
      whenTag(entries[0].when),
      el("span", { class: "row-meta" }, entries[0].time || periodShort(lessons[0].period)),
    ]),
  ]);
}

function compactLessonPair(entries, isPast) {
  const time = entries[0].time;
  const items = entries.map((entry) => compactLessonPairItem(entry));
  return el("div", { class: rowClassNames(isPast) }, [
    el("div", { class: "row-pair" }, items),
    el("div", { class: "row-side" }, [
      whenTag(entries[0].when),
      el("span", { class: "row-meta" }, time || periodShort(entries[0].lesson.period)),
    ]),
  ]);
}

function timetableView() {
  const view = el("div", {});
  if (!moduleOn("timetable")) {
    view.append(emptyBlock("timetable", t("timetable.locked.title"), t("timetable.locked.text")));
    return view;
  }
  if (state.childrenFailure) {
    view.append(childrenFailureCard());
    return view;
  }
  if (!state.children.length && !state.childId && !state.timetable) {
    view.append(plainCard(t("overview.noChild")));
    return view;
  }
  if (childPillsShown() && !timetableShowsAllChildren()) view.append(childPills(state.childId, selectChild));
  const banner = schoolIssueBanner(shownChildSchools());
  if (banner) view.append(banner);
  view.append(weekBar());
  if (timetableShowsAllChildren()) return timetableAllChildrenView(view);
  const data = state.timetable;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  if (timetableRefused(data)) {
    view.append(timetableRefusedBlock());
    return view;
  }
  if (data.error || !Array.isArray(data.lessons)) {
    view.append(schoolInOutage(currentConnectionId())
      ? outageEmptyBlock()
      : emptyBlock("alert", t("timetable.error.title"), t("timetable.error.text"), retryButton(() => { state.timetable = null; rerender(); reloadTimetable(); })));
    return view;
  }
  const monday = weekMonday();
  const fullWeek = holidayFullWeek(monday, data);
  if (noLessonsListed(data, monday) && !ownEntriesKept(state.childId)) {
    view.append(noLessonsBlock());
    const note = refreshFailureNote("timetable");
    if (note) view.append(note);
    return view;
  }
  if (noLessonsListed(data, monday)) view.append(noteBlock(t("timetable.empty.text")));
  view.append(el("div", { class: "tt-frame" }, [
    weekSwipeHint(-1, "tt-edge-prev"),
    timetableGrid(data),
    weekSwipeHint(1, "tt-edge-next"),
  ]));
  if (!fullWeek) {
    view.append(
      el("div", { class: "legend" }, [
        legendItem("var(--warn)", t("timetable.legend.changed"), true),
        legendSymbol("var(--danger)", t("timetable.legend.cancelled"), "×"),
        ...movedLegendItems(data),
        ...planLegendItems(data, state.childId),
      ])
    );
  }
  const stamp = timetableStamp(data, monday, !!fullWeek);
  if (stamp) view.append(stamp);
  const timetableNote = refreshFailureNote("timetable");
  if (timetableNote) view.append(timetableNote);
  return view;
}

function failedWeek(code, body) {
  return { lessons: [], error: code, message_key: (body && body.message_key) || "" };
}

function timetableRefused(data) {
  return !!data && data.message_key === TIMETABLE_REFUSED_KEY;
}

function timetableRefusedBlock() {
  return emptyBlock("timetable", t("timetable.refused.title"), t(TIMETABLE_REFUSED_KEY));
}

function noLessonsListed(data, monday) {
  return !!data && data.no_lessons === true && Array.isArray(data.lessons) && !holidayFullWeek(monday, data);
}

function ownEntriesKept(owner) {
  const school = connectionOfKey(owner);
  const box = school ? periodsData(school) : null;
  return !!(periodsReady(box) && box.entries.length);
}

function noLessonsBlock() {
  return emptyBlock("timetable", t("timetable.empty.title"), t("timetable.empty.text"));
}

function timetableShowsAllChildren() {
  return layoutMode() === "desk" && moduleOn("timetable") && state.children.length > 1;
}

function siblingWeekLoads() {
  if (!timetableShowsAllChildren()) return [];
  return state.children
    .filter((child) => child.key !== state.childId)
    .map((child) => loadOverviewWeek(child.key, state.weekOffset));
}

function childWeekData(childId) {
  if (childId === state.childId) return state.timetable;
  return overviewWeekData(childId, state.weekOffset);
}

function childAvatar(child) {
  const avatar = iservText("span", { class: "avatar" }, (childFirstName(child) || "?").trim().charAt(0).toUpperCase());
  avatar.style.background = childColor(child.key);
  return avatar;
}

function childClassLabel(child) {
  const className = child.class_name || "";
  const school = childSchoolSuffix(child);
  if (!className) return school;
  return school ? t("child.labelWithSchool", { label: className, school }) : className;
}

function timetableChildHead(child) {
  const detail = childClassLabel(child);
  return el("div", { class: "tt-child-head" }, [
    childAvatar(child),
    el("span", { class: "tt-child-text" }, [
      iservText("span", { class: "who" }, childShortName(child)),
      detail ? iservText("span", { class: "cls" }, detail) : null,
    ]),
  ]);
}

function timetableChildColumn(child) {
  const column = el("div", { class: "tt-child", "data-child": child.key }, [timetableChildHead(child)]);
  const data = childWeekData(child.key);
  if (!data) {
    if (child.key !== state.childId) {
      autoLoad(`ovWeek:${child.key}:${state.weekOffset}`, () => loadOverviewWeek(child.key, state.weekOffset));
    }
    column.append(loadingBlock());
    return column;
  }
  if (timetableRefused(data)) {
    column.append(timetableRefusedBlock());
    return column;
  }
  if (data.error || !Array.isArray(data.lessons)) {
    column.append(emptyBlock("alert", t("timetable.error.title"), t("timetable.error.text"), retryButton(() => {
      if (child.key === state.childId) {
        state.timetable = null;
        rerender();
        reloadTimetable();
        return;
      }
      loadOverviewWeek(child.key, state.weekOffset);
    })));
    return column;
  }
  if (noLessonsListed(data, weekMonday()) && !ownEntriesKept(child.key)) {
    column.append(noLessonsBlock());
    return column;
  }
  column.append(timetableGrid(data, child.key));
  return column;
}

function timetableAllChildrenView(view) {
  const monday = weekMonday();
  const scrolls = state.children.length >= TIMETABLE_SCROLL_FROM;
  const columns = el("div", { class: scrolls ? "tt-multi scrolls" : "tt-multi" }, state.children.map(timetableChildColumn));
  view.append(el("div", { class: "tt-frame" }, [
    weekSwipeHint(-1, "tt-edge-prev"),
    columns,
    weekSwipeHint(1, "tt-edge-next"),
  ]));
  const data = state.timetable;
  const fullWeek = data && Array.isArray(data.lessons) ? holidayFullWeek(monday, data) : null;
  if (!fullWeek) {
    view.append(
      el("div", { class: "legend" }, [
        legendItem("var(--warn)", t("timetable.legend.changed"), true),
        legendSymbol("var(--danger)", t("timetable.legend.cancelled"), "×"),
      ])
    );
  }
  if (data && Array.isArray(data.lessons)) {
    const stamp = timetableStamp(data, monday, !!fullWeek);
    if (stamp) view.append(stamp);
  }
  const timetableNote = refreshFailureNote("timetable");
  if (timetableNote) view.append(timetableNote);
  return view;
}

function timetableStamp(data, monday, fullWeek) {
  const parts = [];
  if (data.last_updated) parts.push(t("timetable.stand", { time: showDateTime(data.last_updated) }));
  let shown = fullWeek;
  let uncertain = false;
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    const iso = isoDate(addDays(monday, day));
    if (holidayBlocksLessons(iso)) shown = true;
    if (holidayIsUncertain(iso)) uncertain = true;
  }
  const box = holidayBox();
  if (shown && box && box.stale) parts.push(t("holidays.status.stale"));
  if (uncertain) parts.push(t("holidays.day.uncertain"));
  if (!parts.length) return null;
  return el("div", { class: "stamp" }, parts.join(" · "));
}

function movedLegendItems(data) {
  const lessons = data && Array.isArray(data.lessons) ? data.lessons : [];
  const moved = lessons.some((lesson) => lessonMove(lesson, lesson.change_kind));
  return moved ? [legendItem("var(--moved)", t("timetable.change.moved"), true)] : [];
}

function legendItem(color, text, dot) {
  const dash = el("i", { class: dot ? "dot" : undefined });
  dash.style.background = color;
  return el("span", {}, [dash, el("span", {}, text)]);
}

function legendSymbol(color, text, symbol) {
  const mark = el("i", { class: "sym" }, symbol);
  mark.style.color = color;
  return el("span", {}, [mark, el("span", {}, text)]);
}

function weekMonday() {
  return startOfWeek(addDays(new Date(), 7 * state.weekOffset));
}

function weekBar() {
  const monday = weekMonday();
  return el("div", { class: "weekbar" }, [
    el("button", {
      class: "nav",
      type: "button",
      "aria-label": t("timetable.week.prev"),
      disabled: state.weekOffset <= WEEK_MIN ? "disabled" : null,
      onclick: () => shiftWeek(-1),
    }, [el("span", { class: "ico-slot chev-prev", html: iconSvg("chevron", 20) })]),
    el("button", { class: "mid", type: "button", onclick: () => openSheet(weekSheet) }, [
      el("b", {}, t("timetable.week.label", { week: formatNumber(isoWeek(monday)) })),
      el("span", {}, dateRange(formatShortDate(monday), formatShortDate(addDays(monday, 4)))),
    ]),
    el("button", {
      class: "nav",
      type: "button",
      "aria-label": t("timetable.week.next"),
      disabled: state.weekOffset >= WEEK_MAX ? "disabled" : null,
      onclick: () => shiftWeek(1),
    }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 20) })]),
  ]);
}

function weekSheet() {
  const rows = [];
  for (let offset = WEEK_MIN; offset <= WEEK_MAX; offset += 1) {
    const monday = startOfWeek(addDays(new Date(), 7 * offset));
    const week = holidayWeek(isoDate(monday));
    const range = dateRange(formatShortDate(monday), formatShortDate(addDays(monday, 4)));
    const summary = holidayWeekSummary(week);
    rows.push(
      el("button", {
        class: week && week.coverage === HOLIDAY_COVERAGE_FULL ? "opt off" : "opt",
        type: "button",
        "aria-pressed": String(offset === state.weekOffset),
        onclick: () => { closeSheet(); setWeek(offset); },
      }, [
        el("span", {}, [
          el("b", {}, t(offset === 0 ? "timetable.week.current" : "timetable.week.label", { week: formatNumber(isoWeek(monday)) })),
          el("small", { class: "one-line" }, summary ? t("common.pair", { first: range, second: summary }) : range),
        ]),
      ])
    );
  }
  return sheet(t("timetable.week.sheet"), [el("div", { class: "opt-list" }, rows)]);
}

function shiftWeek(step) {
  setWeek(Math.max(WEEK_MIN, Math.min(WEEK_MAX, state.weekOffset + step)));
}

async function setWeek(offset) {
  if (offset === state.weekOffset) return;
  state.weekOffset = offset;
  state.timetable = null;
  rerender();
  await reloadTimetable();
}

async function reloadTimetable() {
  const keep = !!(state.timetable && !state.timetable.error && Array.isArray(state.timetable.lessons));
  let loaded = null;
  const outcome = await reload("timetable", async () => {
    loaded = await loadTimetable();
    return loaded.timetable;
  }, keep, currentConnectionId());
  if (!outcome) return;
  if (outcome.error) state.timetable = failedWeek(outcome.error, outcome.body);
  else if (outcome.data) applyTimetable(loaded);
  rerender();
}

function timetableGrid(data, childId, options) {
  const opts = options || {};
  const owner = childId || state.childId;
  const school = connectionOfKey(owner) || currentConnectionId();
  const weekLessons = Array.isArray(data.lessons) ? data.lessons : [];
  const times = periodTimes(data, owner);
  const monday = opts.monday || weekMonday();
  const todayIso = isoDate(new Date());
  const fullWeek = holidayFullWeek(monday, data, school);
  const blocked = [];
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    blocked.push(!!fullWeek || holidayBlocksLessons(isoDate(addDays(monday, day)), school));
  }
  const dayCount = planWeekDays(owner, monday);
  const columns = blocked.concat(Array.from({ length: dayCount - HOLIDAY_SCHOOL_DAYS }, () => false));
  const grid = el("div", { class: state.spotlightSubject ? "tt spotlight" : "tt" });
  if (dayCount > HOLIDAY_SCHOOL_DAYS) {
    grid.classList.add("tt-weekend");
    grid.style.gridTemplateColumns = `30px repeat(${dayCount}, 1fr)`;
  }
  grid.addEventListener("keydown", spotlightEscape);
  if (opts.swipe !== false) setupWeekSwipe(grid);
  grid.append(el("div", { style: "grid-column:1;grid-row:1" }));
  for (let day = 0; day < dayCount; day += 1) {
    const date = addDays(monday, day);
    const entry = holidayDay(isoDate(date), school);
    grid.append(
      el("div", {
        class: isoDate(date) === todayIso ? "tt-head today" : "tt-head",
        style: `grid-column:${day + 2};grid-row:1`,
      }, [
        el("span", { class: "d" }, formatWeekdayShort(date)),
        el("span", { class: entry && entry.free ? "n off" : "n" }, formatDayNumber(date)),
      ])
    );
  }
  if (fullWeek) {
    grid.append(holidayFullField(fullWeek, monday, school));
    const own = ownPlanLayout(data, owner, monday, columns.map((_, day) => day < HOLIDAY_SCHOOL_DAYS), [], 3);
    if (own) for (const node of own.nodes) grid.append(node);
    return grid;
  }
  const visible = data.lessons.filter((lesson) => {
    const day = Number(lesson.day_of_week);
    return !(day >= 1 && day <= HOLIDAY_SCHOOL_DAYS && blocked[day - 1]);
  });
  const periodsWithLessons = visible
    .filter((lesson) => lesson.period !== null && lesson.period !== undefined && lesson.period !== "")
    .map((lesson) => Number(lesson.period))
    .filter((n) => Number.isInteger(n) && n >= 0);
  const maxPeriod = periodsWithLessons.length ? Math.max(...periodsWithLessons) : 5;
  const firstPeriod = periodsWithLessons.includes(0) ? 0 : 1;
  const rows = Array.from({ length: Math.max(0, maxPeriod - firstPeriod + 1) }, (_, index) => index + firstPeriod);
  const own = ownPlanLayout(data, owner, monday, columns, rows);
  const lineOf = (period) => (own ? own.rowOf.get(period) : period - firstPeriod + 2);
  const byKey = new Map();
  for (const lesson of visible) {
    const key = `${lesson.day_of_week}:${lesson.period}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(lesson);
  }
  for (const period of rows) {
    grid.append(
      el("div", { class: "tt-hour", style: `grid-column:1;grid-row:${lineOf(period)}` }, [
        el("b", {}, formatNumber(period)),
        times[String(period)] ? el("span", {}, clockOf(times[String(period)])) : null,
      ])
    );
    for (let day = 1; day <= HOLIDAY_SCHOOL_DAYS; day += 1) {
      if (blocked[day - 1]) continue;
      const lessons = byKey.get(`${day}:${period}`) || [];
      const cell = lessons.length ? gridCell(lessons, clockOf(times[String(period)]), owner, weekLessons, data.courses) : planFreeCell(owner, isoDate(addDays(monday, day - 1)), period);
      cell.style.gridColumn = String(day + 1);
      cell.style.gridRow = String(lineOf(period));
      grid.append(cell);
    }
  }
  if (own) for (const node of own.nodes) grid.append(node);
  for (const field of holidayRunFields(monday, blocked, own ? own.total : rows.length, school)) grid.append(field);
  return grid;
}

const SWIPE_MIN_DISTANCE = 48;
const SWIPE_AXIS_RATIO = 1.6;
const SWIPE_AXIS_MIN = 12;

function documentIsRtl() {
  return RTL_LANGUAGES.includes(currentLanguage());
}

function weekStepForDelta(deltaX) {
  const backwards = documentIsRtl() ? deltaX < 0 : deltaX > 0;
  return backwards ? -1 : 1;
}

function canShiftWeek(step) {
  const target = state.weekOffset + step;
  return target >= WEEK_MIN && target <= WEEK_MAX;
}

function setupWeekSwipe(grid) {
  let startX = 0;
  let startY = 0;
  let tracking = false;
  grid.addEventListener("touchstart", (event) => {
    if (event.touches.length !== 1) {
      tracking = false;
      return;
    }
    startX = event.touches[0].clientX;
    startY = event.touches[0].clientY;
    tracking = true;
  }, { passive: true });
  grid.addEventListener("touchmove", (event) => {
    if (!tracking || event.touches.length !== 1) return;
    const deltaY = Math.abs(event.touches[0].clientY - startY);
    const deltaX = Math.abs(event.touches[0].clientX - startX);
    if (Math.max(deltaX, deltaY) < SWIPE_AXIS_MIN) return;
    if (deltaY > deltaX * SWIPE_AXIS_RATIO) tracking = false;
  }, { passive: true });
  grid.addEventListener("touchend", (event) => {
    if (!tracking) return;
    tracking = false;
    const touch = event.changedTouches && event.changedTouches[0];
    if (!touch) return;
    const deltaX = touch.clientX - startX;
    const deltaY = touch.clientY - startY;
    if (Math.abs(deltaX) < SWIPE_MIN_DISTANCE) return;
    if (Math.abs(deltaX) < Math.abs(deltaY) * SWIPE_AXIS_RATIO) return;
    const step = weekStepForDelta(deltaX);
    if (!canShiftWeek(step)) return;
    shiftWeek(step);
  }, { passive: true });
}

function weekSwipeHint(step, className) {
  if (!canShiftWeek(step)) return null;
  return el("span", {
    class: `tt-edge ${className}`,
    "aria-hidden": "true",
  }, [el("span", { class: "ico-slot", html: iconSvg("chevron", 16) })]);
}

function lessonSubjectKey(lesson) {
  return String(lesson.subject_code || lesson.subject_label || "");
}

const SPOTLIGHT_HOLD_MS = 450;
const SPOTLIGHT_HOLD_SLOP = 10;
let spotlightHoldTimer = null;
let spotlightHoldFired = false;

function setSpotlight(subject) {
  const next = subject || null;
  if (state.spotlightSubject === next) return;
  state.spotlightSubject = next;
  applySpotlight();
}

function cancelSpotlightHold() {
  if (spotlightHoldTimer === null) return;
  window.clearTimeout(spotlightHoldTimer);
  spotlightHoldTimer = null;
}

function beginSpotlightHold(subject) {
  cancelSpotlightHold();
  if (!subject) return;
  spotlightHoldTimer = window.setTimeout(() => {
    spotlightHoldTimer = null;
    spotlightHoldFired = true;
    setSpotlight(subject);
  }, SPOTLIGHT_HOLD_MS);
}

function spotlightPointerDown() {
  spotlightHoldFired = false;
}

function spotlightSwallowTap(event) {
  if (spotlightHoldFired) {
    spotlightHoldFired = false;
    event.stopPropagation();
    event.preventDefault();
    return;
  }
  if (!state.spotlightSubject) return;
  event.stopPropagation();
  event.preventDefault();
  setSpotlight(null);
}

function bindSpotlightHold(cell, subject) {
  if (!subject) return;
  let startX = 0;
  let startY = 0;
  cell.addEventListener("pointerdown", (event) => {
    if (event.button) return;
    startX = event.clientX;
    startY = event.clientY;
    beginSpotlightHold(subject);
  });
  cell.addEventListener("pointerup", cancelSpotlightHold);
  cell.addEventListener("pointermove", (event) => {
    if (Math.abs(event.clientX - startX) > SPOTLIGHT_HOLD_SLOP
      || Math.abs(event.clientY - startY) > SPOTLIGHT_HOLD_SLOP) cancelSpotlightHold();
  });
  cell.addEventListener("pointercancel", cancelSpotlightHold);
  cell.addEventListener("pointerleave", cancelSpotlightHold);
  cell.addEventListener("contextmenu", (event) => event.preventDefault());
}

function spotlightWorthwhile(subject, weekLessons) {
  return !!subject && weekSubjectOccurrences(subject, weekLessons || timetableWeekLessons()).length > 1;
}

function spotlightSheetAction(lesson, weekLessons) {
  if (state.view !== "timetable") return null;
  const subject = lessonSubjectKey(lesson);
  if (!subject || weekSubjectOccurrences(subject, weekLessons).length < 2) return null;
  return iservText("button", {
    class: "btn ghost",
    type: "button",
    onclick: () => { setSpotlight(subject); discardSheet(); },
  }, t("timetable.spotlight.action", { subject: lesson.subject_label || lesson.subject_code || subject }));
}

function applySpotlight() {
  const grid = root() && root().querySelector(".tt");
  if (!grid) return;
  const subject = state.spotlightSubject;
  grid.classList.toggle("spotlight", !!subject);
  for (const cell of grid.querySelectorAll(".tt-cell")) {
    cell.classList.toggle("spot", !!subject && cell.dataset.subject === subject);
  }
}

function spotlightEscape(event) {
  if (event.key !== "Escape" || !state.spotlightSubject) return;
  event.stopPropagation();
  setSpotlight(null);
}

function timetableWeekLessons() {
  const data = state.timetable;
  return data && Array.isArray(data.lessons) ? data.lessons : [];
}

function overviewWeekLessons(childId, lesson) {
  const date = parseIsoDay(lessonIso(lesson));
  const weekIdx = date ? Math.round((startOfWeek(date).getTime() - startOfWeek(new Date()).getTime()) / (7 * 86400000)) : 0;
  const week = overviewWeekData(childId, Math.max(0, weekIdx));
  return week && Array.isArray(week.lessons) ? week.lessons : [];
}

function weekSubjectOccurrences(subject, weekLessons, childId) {
  const owner = childId || state.childId;
  const school = connectionOfKey(owner) || currentConnectionId();
  return (weekLessons || [])
    .filter((lesson) => lessonSubjectKey(lesson) === subject
      && displayChangeKind(lesson, owner) !== "cancelled"
      && !holidayBlocksLessons(lessonIso(lesson), school))
    .sort((left, right) =>
      Number(left.day_of_week) - Number(right.day_of_week) || Number(left.period) - Number(right.period));
}

function lessonWeekPosition(lesson, weekLessons, childId) {
  const subject = lessonSubjectKey(lesson);
  if (!subject) return null;
  const occurrences = weekSubjectOccurrences(subject, weekLessons, childId);
  const total = occurrences.length;
  if (total < 1) return null;
  const position = occurrences.findIndex((entry) =>
    Number(entry.day_of_week) === Number(lesson.day_of_week) && Number(entry.period) === Number(lesson.period)) + 1;
  if (position < 1) return null;
  return { position, total };
}

const COURSE_CELL_MIN = 3;
const COURSE_SEARCH_FROM = 8;

function courseChild(key) {
  return state.children.find((child) => child.key === key) || null;
}

function courseChildName(key) {
  const child = courseChild(key);
  return child ? childFirstName(child) : "";
}

function coursesCell(lessons, time, childId, weekLessons, courses) {
  const count = lessons.length;
  const changed = lessons.some((lesson) => !!displayChangeKind(lesson, childId));
  return el("button", {
    class: changed ? "tt-cell courses subbed" : "tt-cell courses",
    type: "button",
    "aria-label": tCount("timetable.courses.parallel", count),
    onclick: () => openCoursesSheet(lessons, time, childId, weekLessons, courses),
  }, [
    changed ? el("span", { class: "bar" }) : null,
    el("span", { class: "sub" }, formatNumber(count)),
    el("span", { class: "courses-label" }, tCount("timetable.courses.cell", count)),
  ]);
}

function openCoursesSheet(lessons, time, childId, weekLessons, courses) {
  openSheet(() => coursesSheet(lessons, time, childId, weekLessons, courses));
}

function sortedCourseLessons(lessons) {
  return lessons.slice().sort((left, right) =>
    String(left.subject_label || left.subject_code || "").localeCompare(String(right.subject_label || right.subject_code || ""), currentLanguage(), { numeric: true, sensitivity: "base" })
    || String(left.teacher_label || "").localeCompare(String(right.teacher_label || ""), currentLanguage(), { sensitivity: "base" }));
}

function courseLessonRow(lesson, time, childId, weekLessons) {
  const kind = displayChangeKind(lesson, childId);
  const dot = el("span", { class: "row-dot" }, [el("i", {})]);
  dot.firstChild.style.background = subjectDotColor(lesson);
  const facts = [lesson.teacher_label || lesson.teacher_code, lesson.room].filter(Boolean).join(" · ");
  return el("button", {
    class: "row course-row",
    type: "button",
    onclick: () => openLessonSheet(lesson, time, childId, weekLessons),
  }, [
    dot,
    el("div", { class: "row-main" }, [compactLessonTitle(lesson, kind), facts ? iservText("div", { class: "row-sub" }, facts) : null]),
    changeTag(kind),
  ]);
}

function coursesSheet(lessons, time, childId, weekLessons, courses) {
  const chosen = !!(courses && courses.chosen);
  const body = [el("p", { class: "lesson-week-count" }, lessonPeriodFact(lessons[0], time))];
  if (!chosen) body.push(el("p", { class: "dlg-text courses-hint" }, t("timetable.courses.hint", { name: courseChildName(childId) })));
  body.push(el("div", { class: "rows courses-list" }, sortedCourseLessons(lessons).map((lesson) => courseLessonRow(lesson, time, childId, weekLessons))));
  const action = el("button", {
    class: chosen ? "btn ghost courses-open" : "btn courses-open",
    type: "button",
    onclick: () => openCoursesPage(childId),
  }, t(chosen ? "timetable.courses.change" : "timetable.courses.choose"));
  return sheet(tCount("timetable.courses.parallel", lessons.length), body, [el("div", { class: "btn-stack" }, [action])]);
}

function gridCell(lessons, time, childId, weekLessons, courses) {
  if (lessons.length >= COURSE_CELL_MIN) return coursesCell(lessons, time, childId, weekLessons, courses);
  if (lessons.length === 1) return lessonCell(lessons[0], time, false, childId, weekLessons);
  return el(
    "div",
    { class: "tt-stack" },
    lessons.map((lesson) => lessonCell(lesson, time, true, childId, weekLessons))
  );
}

function moveSlot(move, long, origin) {
  const date = parseAnyDate(move && move.date);
  if (!date || move.period === null || move.period === undefined || move.period === "") return "";
  const end = Number(move.period_end || move.period);
  const ranged = end !== Number(move.period);
  const vars = {
    day: long ? formatWeekdayDate(move.date) : formatWeekdayShort(date),
    period: formatNumber(Number(move.period)),
    end: formatNumber(end),
  };
  const base = origin ? "timetable.move.fromSlotLong" : "timetable.move.slotLong";
  const key = long
    ? ranged ? `${base}Range` : base
    : ranged ? "timetable.move.slotRange" : "timetable.move.slot";
  return t(key, vars);
}

function isMove(move) {
  return !!move && typeof move === "object";
}

function lessonMove(lesson, kind) {
  if (!lesson || !kind) return null;
  if (kind === "cancelled") {
    return lesson.change_kind === "cancelled" && isMove(lesson.moved_to) ? { to: true, move: lesson.moved_to } : null;
  }
  return isMove(lesson.moved_from) ? { to: false, move: lesson.moved_from } : null;
}

function moveCellLabel(moved) {
  const slot = moveSlot(moved.move, false);
  if (!slot) return t(moved.to ? "timetable.cell.movedAway" : "timetable.cell.movedHere");
  return t(moved.to ? "timetable.cell.movedTo" : "timetable.cell.movedFrom", { slot });
}

function moveBannerText(moved) {
  const slot = moveSlot(moved.move, true, !moved.to);
  if (!slot) return t(moved.to ? "timetable.banner.movedAway" : "timetable.banner.movedHere");
  return t(moved.to ? "timetable.banner.movedTo" : "timetable.banner.movedFrom", { slot });
}

function bareChange(lesson, kind) {
  return kind === "changed" && lesson.change_kind === "changed" && lesson.no_details === true;
}

function changeNoteOf(lesson) {
  return String((lesson && lesson.change_note) || "").trim();
}

function lessonCell(lesson, time, compact, childId, weekLessons) {
  const owner = childId || state.childId;
  const week = weekLessons || timetableWeekLessons();
  const kind = displayChangeKind(lesson, owner);
  const mark = markOfLesson(lesson, owner);
  const moved = lessonMove(lesson, kind);
  const note = kind ? changeNoteOf(lesson) : "";
  const base = kind === "cancelled" ? "tt-cell out" : kind ? "tt-cell subbed" : "tt-cell";
  const shown = moved ? `${base} moved` : base;
  const roomLabel = moved
    ? moveCellLabel(moved)
    : bareChange(lesson, kind) ? t("timetable.cell.school")
    : kind === "cancelled" ? t("timetable.change.cancelled") : kind === "changed" ? t("timetable.cell.substitute") : "";
  const subject = lessonSubjectKey(lesson);
  const code = lesson.subject_code || lesson.subject_label || "?";
  const surname = compact ? "" : teacherSurname(lesson);
  const room = compact || roomLabel ? "" : lesson.room || "";
  const pairedRoom = !compact && kind === "changed" && !moved && lesson.room ? lesson.room : "";
  const cell = el("button", {
    class: compact ? `${shown} compact` : shown,
    type: "button",
    "data-subject": subject || null,
    "aria-label": lessonAriaLabel(lesson, kind, mark, moved, note),
    onclick: () => openLessonSheet(lesson, time, owner, week),
  }, [
    kind && kind !== "cancelled" ? el("span", { class: "bar" }) : null,
    iservText("span", { class: "sub" }, code),
    compact ? null : iservText("span", { class: "lname" }, lesson.subject_label || code),
    roomLabel ? el("span", { class: pairedRoom ? "room paired" : "room" }, roomLabel) : null,
    pairedRoom ? iservText("span", { class: "lroom paired" }, t("common.pair", { first: roomLabel, second: pairedRoom })) : null,
    room ? iservText("span", { class: "lroom" }, room) : null,
    surname ? iservText("span", { class: "lteacher" }, surname) : null,
    note ? el("span", { class: "note-flag", html: iconSvg("info", 11) }) : null,
    mark ? el("span", { class: "exam-flag", html: iconSvg("exam") }) : null,
  ]);
  if (mark) cell.classList.add("marked");
  if (subject && subject === state.spotlightSubject) cell.classList.add("spot");
  bindSpotlightHold(cell, spotlightWorthwhile(subject, week) ? subject : null);
  if (!kind) paintSubjectCell(cell, subjectColor(lesson));
  return cell;
}

function lessonAriaLabel(lesson, kind, mark, moved, note) {
  const subject = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
  let base = kind
    ? t("timetable.aria.lessonChange", { subject, change: bareChange(lesson, kind) ? t("timetable.change.school") : changeLabel(kind) })
    : t("timetable.aria.lesson", { subject });
  if (moved) base = t("timetable.aria.lessonChange", { subject: base, change: moveCellLabel(moved) });
  if (note) base = t("timetable.aria.lessonChange", { subject: base, change: t("timetable.aria.note", { note }) });
  return mark ? `${base} · ${t("marks.aria.marked", { name: markLabel(mark) })}` : base;
}

const FIELD_KEYS = {
  subject: "timetable.field.subject",
  teacher: "timetable.field.teacher",
  room: "timetable.field.room",
  class: "timetable.field.class",
};
const FIELD_VALUES = {
  subject: (lesson) => lesson.subject_label || lesson.subject_code || "",
  teacher: (lesson) => lesson.teacher_label || lesson.teacher_code || (lesson.teacher_hidden ? t("timetable.teacher.hidden") : ""),
  room: (lesson) => lesson.room || "",
  class: (lesson) => lesson.classes || "",
};

const BANNER_KEYS = {
  cancelled: "timetable.banner.cancelled",
  added: "timetable.banner.added",
};

function bannerKey(lesson, kind) {
  if (BANNER_KEYS[kind]) return BANNER_KEYS[kind];
  if (lesson.teacher_hidden) return "timetable.banner.hiddenTeacher";
  return bareChange(lesson, kind) ? "timetable.banner.school" : "timetable.banner.changed";
}

function changeBanner(lesson) {
  const kind = lesson.change_kind;
  if (!kind) return null;
  const moved = lessonMove(lesson, kind);
  const dot = el("span", { class: `mark ${kind}` });
  const text = moved ? moveBannerText(moved) : t(bannerKey(lesson, kind));
  const label = moved ? t("timetable.change.moved") : bareChange(lesson, kind) ? t("timetable.change.school") : changeLabel(kind);
  return el("div", { class: moved ? `banner ${kind} moved` : `banner ${kind}` }, [dot, el("b", {}, label), el("span", {}, text)]);
}

function changeNoteBlock(lesson) {
  const note = lesson.change_kind ? changeNoteOf(lesson) : "";
  if (!note) return [];
  return [
    el("div", { class: "section-head", style: "margin-top:16px" }, [el("span", { class: "overline" }, t("timetable.schoolNote"))]),
    iservText("p", { class: "dlg-text change-note" }, note),
  ];
}

function changeDetails(lesson) {
  const fields = lesson.changed_fields || [];
  if (!fields.length) return null;
  const previous = lesson.previous || {};
  const rows = fields
    .filter((name) => FIELD_KEYS[name])
    .map((name) => {
      const before = previous[name] || t("common.none");
      const after = FIELD_VALUES[name](lesson) || t("common.none");
      return el("div", { class: "cell" }, [
        el("div", { class: "field-label" }, t(FIELD_KEYS[name])),
        el("div", { class: "swap" }, [
          el("s", {}, before),
          el("span", { class: "arrow" }, "→"),
          el("b", {}, after),
        ]),
      ]);
    });
  if (!rows.length) return null;
  return el("div", { class: "field-group" }, rows);
}

function lessonPeriodFact(lesson, time) {
  if (lesson.period === null || lesson.period === undefined || lesson.period === "") return t("common.none");
  const vars = { period: formatNumber(lesson.period), time };
  return t(time ? "timetable.fact.periodValueTime" : "timetable.fact.periodValue", vars);
}

function openLessonSheet(lesson, time, childId, weekLessons) {
  const week = weekLessons || [];
  openSheet(() => lessonSheet(lesson, time, markChildOf(childId), week));
}

function lessonSheet(lesson, time, childId, weekLessons) {
  const facts = [
    [t("timetable.field.subject"), lesson.subject_label || lesson.subject_code || t("common.none")],
    [t("timetable.fact.period"), lessonPeriodFact(lesson, time)],
    [t("timetable.field.room"), lesson.room || t("common.none")],
    [t("timetable.field.teacher"), lesson.teacher_label || lesson.teacher_code || t(lesson.teacher_hidden ? "timetable.teacher.hidden" : "common.none")],
  ];
  if (lesson.date) facts.splice(1, 0, [t("timetable.fact.day"), showDate(lesson.date)]);
  if (lesson.is_class_teacher) facts.push([t("timetable.fact.role"), t("timetable.fact.classTeacher")]);
  const mark = markOfLesson(lesson, childId);
  const cancellation = cancellationOfLesson(lesson, childId);
  const body = [];
  const weekPosition = lessonWeekPosition(lesson, weekLessons, childId);
  if (weekPosition) {
    body.push(el("p", { class: "lesson-week-count" }, tCount("timetable.lesson.weekCount", weekPosition.total, {
      position: formatNumber(weekPosition.position),
      total: formatNumber(weekPosition.total),
    })));
  }
  const banner = changeBanner(lesson);
  if (banner) body.push(banner);
  body.push(...changeNoteBlock(lesson));
  if (cancellation) body.push(cancellationPanel());
  if (mark) body.push(markPanel(mark, childId, lesson, time));
  const details = changeDetails(lesson);
  if (details) {
    body.push(el("div", { class: "section-head", style: "margin-top:16px" }, [el("span", { class: "overline" }, t("timetable.changes.title"))]));
    body.push(details);
    body.push(el("div", { class: "section-head", style: "margin-top:20px" }, [el("span", { class: "overline" }, t("timetable.lesson.section"))]));
  }
  body.push(factList(facts));
  const title = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
  return sheet(title, body, lessonSheetFoot(mark, cancellation, childId, lesson, time, weekLessons));
}

function lessonSheetFoot(mark, cancellation, childId, lesson, time, weekLessons) {
  const actions = [];
  const spotlight = spotlightSheetAction(lesson, weekLessons);
  if (spotlight) actions.push(spotlight);
  if (markLessonAnchor(lesson, childId)) {
    if (!mark) actions.push(markAddButton(childId, lesson, time));
    else {
      actions.push(el("button", { class: "btn ghost", type: "button", onclick: () => openMarkForm(childId, lesson, time, mark) }, t("marks.action.rename")));
      if (!markNeedsCheck(mark)) {
        actions.push(el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.action.remove")));
      }
    }
    actions.push(cancellationAction(cancellation, childId, lesson));
  }
  if (!actions.length) return null;
  return [el("div", { class: "btn-stack" }, actions)];
}

function cancellationAction(cancellation, childId, lesson) {
  if (cancellation) {
    return el("button", {
      class: "btn ghost",
      type: "button",
      onclick: () => removeCancellation(cancellation),
    }, t("timetable.cancel.action.remove"));
  }
  return el("button", {
    class: "btn ghost destructive",
    type: "button",
    onclick: () => addCancellation(childId, lesson),
  }, t("timetable.cancel.action.add"));
}
