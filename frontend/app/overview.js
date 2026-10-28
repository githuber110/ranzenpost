function greeting(hours) {
  if (hours < 5) return t("overview.greeting.night");
  if (hours < 11) return t("overview.greeting.morning");
  if (hours < 18) return t("overview.greeting.day");
  return t("overview.greeting.evening");
}

const GREETING_NAME_MAX_CHARS = 30;

function buildGreetingName(forename) {
  const isTruncated = forename.length > GREETING_NAME_MAX_CHARS;
  const displayName = isTruncated ? `${forename.slice(0, GREETING_NAME_MAX_CHARS)}…` : forename;
  const attrs = { class: "greeting-name" };
  if (isTruncated) attrs.title = forename;
  return el("span", attrs, displayName);
}

function greetingHeadline(now, className) {
  const forename = state.me && state.me.forename;
  const children = [greeting(now.getHours())];
  if (forename) {
    children.push(t("overview.greeting.separator"));
    children.push(buildGreetingName(forename));
  }
  return el("h1", { class: className || "greeting" }, children);
}

function overviewWeekMonday(weekIdx) {
  return isoDate(startOfWeek(addDays(new Date(), 7 * weekIdx)));
}

function overviewStoredWeek(childId, weekIdx) {
  const byChild = state.overviewWeeks[childId];
  const stored = byChild ? byChild[weekIdx] || null : null;
  if (!stored) return null;
  const mondays = state.overviewWeekMondays[childId] || {};
  if (mondays[weekIdx] && mondays[weekIdx] !== overviewWeekMonday(weekIdx)) {
    delete byChild[weekIdx];
    delete mondays[weekIdx];
    return null;
  }
  return stored;
}

function overviewWeekFits(weekIdx) {
  return !state.timetableMonday || state.timetableMonday === overviewWeekMonday(weekIdx);
}

function overviewWeekData(childId, week) {
  const weekIdx = week || 0;
  const stored = overviewStoredWeek(childId, weekIdx);
  const current = weekIdx === (state.weekOffset || 0) && childId === state.childId ? state.timetable : null;
  const shown = current && overviewWeekFits(weekIdx) ? current : null;
  if (shown && (!shown.error || !stored || stored.error)) return shown;
  return stored;
}

function overviewCachedWeeks(childId) {
  const weeks = new Set([0]);
  for (const key of Object.keys(state.overviewWeeks[childId] || {})) weeks.add(Number(key));
  return [...weeks];
}

async function loadOverviewWeek(childId, week) {
  const weekIdx = week || 0;
  const key = `ovWeek:${childId}:${weekIdx}`;
  const monday = overviewWeekMonday(weekIdx);
  const stored = (state.overviewWeeks[childId] || {})[weekIdx];
  const keep = !!(stored && !stored.error);
  const outcome = await reload(
    key,
    () => getJson(`api/timetable?child=${encodeURIComponent(childId)}&week=${weekIdx}`),
    keep,
    connectionOfKey(childId)
  );
  if (!outcome) return;
  if (!state.overviewWeeks[childId]) state.overviewWeeks[childId] = {};
  if (!state.overviewWeekMondays[childId]) state.overviewWeekMondays[childId] = {};
  if (outcome.data) state.overviewWeeks[childId][weekIdx] = outcome.data;
  else if (outcome.error) state.overviewWeeks[childId][weekIdx] = failedWeek(outcome.error, outcome.body);
  if (outcome.data || outcome.error) state.overviewWeekMondays[childId][weekIdx] = monday;
  if (state.view === "overview" || state.view === "timetable") rerender();
}

const OVERVIEW_UPCOMING_DAYS = 14;
const OVERVIEW_MAX_PAGES = 4;
const OVERVIEW_MIN_BLOCKS_PER_PAGE = 3;
const OVERVIEW_ARROW_BAND = 56;
let overviewModel = null;
let overviewRelayoutBound = false;
let overviewTeachShown = false;

function overviewChildList() {
  if (state.children.length) return state.children;
  return [{ key: state.childId }];
}

function overviewActiveChild() {
  const list = overviewChildList();
  return (
    list.find((child) => child.key === state.overviewChildId)
    || list.find((child) => child.key === state.childId)
    || list[0]
  );
}

function overviewSelectChild(childId) {
  if (state.overviewChildId === childId) return;
  state.overviewChildId = childId;
  state._overviewAnchor = null;
  state._overviewNow = true;
  rerender();
}

function overviewOpenTimetable() {
  const child = overviewActiveChild();
  openTimetableOf(child && child.key ? child.key : "");
}

function overviewBlock(key, node, bracket, change) {
  if (node && node.dataset) node.dataset.block = key;
  return { key, node, bracket: bracket || null, change: !!change };
}

function overviewRestBlock(key, text) {
  return overviewBlock(key, plainCard(text));
}

function overviewLoadingBlock(key) {
  return overviewBlock(key, el("div", { class: "card" }, [loadingBlock()]));
}

function overviewFailureBlock(key, run) {
  if (anyOutage()) return overviewBlock(key, plainCard(t("outage.overview.text")));
  return overviewBlock(key, el("div", { class: "card overview-failed" }, [
    el("p", { class: "dlg-text", style: "margin:0 0 12px" }, t("overview.partial.failed")),
    retryButton(run),
  ]));
}

function overviewListRow(title, sub, meta, unread, onclick, tags) {
  const chips = (tags || []).filter(Boolean);
  return el("button", { class: unread ? "row" : "row read", type: "button", onclick }, [
    el("span", { class: "row-dot" }, unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      chips.length ? el("div", { class: "row-tags" }, chips) : null,
      iservText("div", { class: "row-title" }, title),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
    meta ? el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, meta)]) : null,
  ]);
}

function overviewAllRow(key, text, onclick) {
  return overviewBlock(key, el("button", { class: "row read row-all", type: "button", onclick }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [el("div", { class: "row-title" }, text)]),
    el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]),
  ]));
}

function overviewChapter(area, title, link) {
  return { area, title, link: link || null, meta: null, chips: null, bodyClass: "rows", blocks: [], loading: false, nowKey: null, count: 0, fresh: false, size: null };
}

function overviewRest(chapter, key, text) {
  chapter.bodyClass = "panel-rest";
  chapter.blocks = [overviewRestBlock(key, text)];
  return chapter;
}

function overviewChildHasChange(child) {
  const week = overviewWeekData(child.key, 0);
  if (!week || week.error || !Array.isArray(week.lessons)) return false;
  return todayLessons(week, weekdayIndex(new Date()))
    .some((lesson) => !!displayChangeKind(lesson, child.key));
}

function overviewChips(activeId) {
  const bar = el("div", { class: "chipbar overview-chips" });
  const list = overviewChildList();
  if (!list.length || !list[0].key) {
    bar.append(el("span", { class: "chip chip-skeleton" }), el("span", { class: "chip chip-skeleton" }));
    return bar;
  }
  for (const child of list) {
    const active = child.key === activeId;
    const marked = !active && overviewChildHasChange(child);
    bar.append(el("button", {
      class: "chip",
      type: "button",
      "aria-pressed": String(active),
      onclick: () => overviewSelectChild(child.key),
    }, [
      iservText("span", { class: "chip-label" }, childChipLabel(child)),
      marked ? el("span", { class: "chip-mark", "aria-hidden": "true" }) : null,
    ]));
  }
  return bar;
}

function overviewBracketJoins(first, second) {
  if (first.lessons.length !== 1 || second.lessons.length !== 1) return false;
  const left = first.lessons[0];
  const right = second.lessons[0];
  if (Number(second.period) !== Number(first.period) + 1) return false;
  if ((left.change_kind || "") !== (right.change_kind || "")) return false;
  const leftName = left.subject_label || left.subject_code || "";
  const rightName = right.subject_label || right.subject_code || "";
  return !!leftName && leftName === rightName;
}

function overviewBrackets(groups) {
  const keys = new Array(groups.length).fill(null);
  let start = 0;
  for (let index = 1; index <= groups.length; index += 1) {
    const joins = index < groups.length && overviewBracketJoins(groups[index - 1], groups[index]);
    if (joins) continue;
    if (index - start > 1) {
      const key = `bracket:${groups[start].period}`;
      for (let cursor = start; cursor < index; cursor += 1) keys[cursor] = key;
    }
    start = index;
  }
  return keys;
}

let overviewWakeAt = null;
let overviewBuiltOn = "";

function overviewWakeAtMinute(minutes) {
  if (minutes === null || minutes === undefined) return;
  const at = new Date();
  at.setHours(0, minutes, 0, 0);
  if (at.getTime() <= new Date().getTime()) return;
  if (!overviewWakeAt || at < overviewWakeAt) overviewWakeAt = at;
}

function overviewTick() {
  if (state.view !== "overview" || document.hidden || hasOpenFormGuard()) return;
  if (overviewBuiltOn && overviewBuiltOn !== isoDate(new Date())) {
    overviewBuiltOn = "";
    Promise.resolve(refreshActiveView()).catch(routeOrIgnoreBackgroundFailure);
    return;
  }
  if (overviewWakeAt && new Date().getTime() >= overviewWakeAt.getTime()) {
    overviewWakeAt = null;
    rerender();
  }
}

function lessonEndMinutes(start, period, school) {
  if (start === null) return null;
  const box = school ? periodsData(school) : null;
  if (periodsReady(box)) {
    const row = periodRules().gridRows(box.grid).find((item) => item.number === Number(period) && item.start === start);
    if (row && row.end > start) return row.end;
  }
  return start + LESSON_MINUTES;
}

function lessonSlotStatus(start, end, minutesNow) {
  if (start === null) return "unknown";
  if (minutesNow >= end) return "past";
  return minutesNow >= start ? "now" : "future";
}

function todayTimeline(groups, times, childId, minutesNow) {
  const school = connectionOfKey(childId);
  const starts = groups.map((group) => lessonTimeMinutes(group.lessons[0], times));
  const ends = starts.map((start, index) => lessonEndMinutes(start, groups[index].period, school));
  const teaching = groups.map((group) =>
    group.lessons.some((lesson) => !lessonDropped(lesson, childId)));
  const statuses = starts.map((start, index) => lessonSlotStatus(start, ends[index], minutesNow));
  for (const value of starts.concat(ends)) if (value !== null && value > minutesNow) overviewWakeAtMinute(value);
  let nowIndex = -1;
  let nextIndex = -1;
  groups.forEach((group, index) => {
    if (!teaching[index]) return;
    if (nowIndex < 0 && statuses[index] === "now") nowIndex = index;
    if (nextIndex < 0 && statuses[index] === "future") nextIndex = index;
  });
  const taught = ends.filter((end, index) => teaching[index]);
  const complete = taught.length > 0 && taught.every((end) => end !== null);
  const schoolEnd = complete ? Math.max(...taught) : null;
  const dayOver = taught.length === 0 || (schoolEnd !== null && minutesNow >= schoolEnd);
  return {
    statuses,
    nowIndex,
    nextIndex: nowIndex < 0 && !dayOver ? nextIndex : -1,
    schoolEnd,
    dayOver,
  };
}

function todayWithoutSchool(child, week, now) {
  const lessons = todayLessons(week, weekdayIndex(now));
  if (!lessons.length || holidayTodayCard(isoDate(now), lessons.length, schoolOfChild(child))) return true;
  return lessons.every((lesson) => lessonDropped(lesson, child.key));
}

function todayDayOver(child, week, now) {
  if (todayWithoutSchool(child, week, now)) return true;
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const lessons = todayLessons(week, weekdayIndex(now));
  return todayTimeline(groupTodayLessons(lessons), periodTimes(week, child.key), child.key, minutesNow).dayOver;
}

function todayChapter(size, entry) {
  const compact = size === layoutBlocks().SIZE_COMPACT;
  const turn = entry && entry.switch ? entry.switch : "";
  const chapter = overviewChapter("today", t("overview.today"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  const now = new Date();
  chapter.meta = formatWeekdayDay(now);
  if (!moduleOn("timetable") || noChildren()) return null;
  if (state.childrenFailure) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewBlock("today:childrenfailed", childrenFailureCard())];
    return chapter;
  }
  if (!state.children.length && !state.childId && !state.timetable) {
    return overviewRest(chapter, "today:nochild", t("overview.noChild"));
  }
  if (turn && turn !== layoutBlocks().SWITCH_END) {
    if (now.getHours() * 60 + now.getMinutes() >= timeMinutes(turn)) return nextDayChapterAs("today", size);
    overviewWakeAtMinute(timeMinutes(turn));
  }
  const child = overviewActiveChild();
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  const week = overviewWeekData(child.key, 0);
  if (!week) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("today:loading")];
    chapter.loading = true;
    return chapter;
  }
  if (timetableRefused(week)) return overviewRest(chapter, "today:refused", t(TIMETABLE_REFUSED_KEY));
  if (week.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("today:failed", () => loadOverviewWeek(child.key, 0))];
    return chapter;
  }
  if (!Array.isArray(week.lessons)) return overviewRest(chapter, "today:unreachable", t("overview.timetable.unreachable"));
  if (turn && (turn === layoutBlocks().SWITCH_END ? todayDayOver(child, week, now) : todayWithoutSchool(child, week, now))) {
    return nextDayChapterAs("today", size);
  }
  const index = weekdayIndex(now);
  const lessons = todayLessons(week, index);
  const holiday = holidayTodayCard(isoDate(now), lessons.length, schoolOfChild(child));
  if (holiday) return todayHolidayChapter(chapter, child, isoDate(now), week, lessons.length);
  if (!lessons.length) return todayFreeChapter(chapter, child, isoDate(now));
  const times = periodTimes(week, child.key);
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const groups = groupTodayLessons(lessons);
  const brackets = overviewBrackets(groups);
  const timeline = todayTimeline(groups, times, child.key, minutesNow);
  chapter.bodyClass = "rows flat";
  chapter.size = size;
  const todayIso = isoDate(now);
  for (const node of todayLeadingRows(child.key, todayIso)) {
    chapter.blocks.push(overviewBlock(node.key, node.node));
  }
  const firstLessonIndex = chapter.blocks.length;
  const limit = layoutBlocks().limitOf(layoutBlocks().blockOf("today"), size);
  let shown = 0;
  groups.forEach((group, position) => {
    const isNow = position === timeline.nowIndex;
    const isPast = timeline.statuses[position] === "past";
    if (compact && isPast) return;
    if (shown >= limit) return;
    shown += 1;
    const entries = group.lessons.map((lesson) => ({
      lesson,
      time: lessonTime(lesson, times),
      minutes: lessonTimeMinutes(lesson, times),
      childId: child.key,
      mark: markAt(child.key, lessonIso(lesson), lesson.period, lesson),
    }));
    entries[0].when = isNow ? "now" : position === timeline.nextIndex ? "next" : null;
    const node = entries.length >= COURSE_CELL_MIN
      ? compactCoursesRow(entries, isPast, week.courses)
      : entries.length > 1
        ? compactLessonPair(entries, isPast)
        : compactLesson(entries[0], isPast);
    if (isNow) node.setAttribute("aria-current", "true");
    const changed = group.lessons.some((lesson) => !!displayChangeKind(lesson, child.key));
    chapter.blocks.push(Object.assign(overviewBlock(`${child.key}:${group.period}`, node, brackets[position], changed), { sortTime: entries[0].minutes }));
  });
  const ownToday = todayOwnBlocks(child.key, todayIso, week).filter((block) => !(compact && block.node.classList.contains("past")));
  if (ownToday.length) chapter.blocks.push(...mergeByTime(chapter.blocks.splice(firstLessonIndex), ownToday));
  const note = todayNoteRow(child.key, timeline);
  if (note) chapter.blocks.push(note);
  const nextOwn = todayNextBlock(child.key, todayIso);
  if (nextOwn) chapter.blocks.push(nextOwn);
  chapter.count = groups.length;
  const anchor = timeline.nowIndex >= 0 ? timeline.nowIndex : timeline.nextIndex;
  if (anchor >= 0 && chapter.blocks.some((block) => block.key === `${child.key}:${groups[anchor].period}`)) {
    chapter.nowKey = `${child.key}:${groups[anchor].period}`;
  } else {
    chapter.nowKey = (timeline.dayOver ? chapter.blocks[chapter.blocks.length - 1] : chapter.blocks[firstLessonIndex] || chapter.blocks[0]).key;
  }
  return chapter;
}

function todayHolidayChapter(chapter, child, iso, week, lessonCount) {
  const key = `today:holiday:${child.key}`;
  const own = todayOwnBlocks(child.key, iso, week);
  if (!own.length) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewBlock(key, holidayTodayCard(iso, lessonCount, schoolOfChild(child)))];
    return chapter;
  }
  chapter.bodyClass = "rows flat";
  chapter.blocks = [overviewBlock(key, el("div", { class: "row row-note today-holiday" }, [
    el("div", { class: "row-main" }, holidayTodayLines(iso, lessonCount, schoolOfChild(child))),
  ]))];
  chapter.blocks.push(...own);
  const next = todayNextBlock(child.key, iso);
  if (next) chapter.blocks.push(next);
  chapter.nowKey = key;
  return chapter;
}

function todayNoteRow(childId, timeline) {
  if (timeline.dayOver) return overviewNoteBlock(`${childId}:dayOver`, t("overview.dayOver"));
  if (timeline.schoolEnd === null) return null;
  return overviewNoteBlock(`${childId}:schoolEnd`, t("overview.schoolEnds", { time: clockText(timeline.schoolEnd) }));
}

function overviewNoteBlock(key, text) {
  return overviewBlock(key, el("div", { class: "row row-note" }, [
    el("p", { class: "dlg-text", style: "margin:0" }, text),
  ]));
}

function todayFreeChapter(chapter, child, iso) {
  const leading = todayLeadingRows(child.key, iso);
  const own = todayOwnBlocks(child.key, iso, overviewWeekData(child.key, 0));
  if (!leading.length && !own.length) return null;
  chapter.bodyClass = "rows flat";
  chapter.blocks = leading.map((row) => overviewBlock(row.key, row.node));
  chapter.blocks.push(overviewBlock(
    `${child.key}:free`,
    el("div", { class: "row row-note" }, [el("p", { class: "dlg-text", style: "margin:0" }, t("overview.noSchool"))])
  ));
  chapter.blocks.push(...own);
  chapter.nowKey = chapter.blocks[0].key;
  return chapter;
}

function absenceOfChild(entry, childId, school) {
  const child = state.children.find((item) => item.key === childId);
  if (!child) return false;
  const childSchool = connectionOfKey(childId);
  if (school && childSchool && school !== childSchool) return false;
  if (entry.student_id === null || entry.student_id === undefined || entry.student_id === "") {
    return state.children.filter((item) => connectionOfKey(item.key) === childSchool).length === 1;
  }
  return child.student_id !== null && child.student_id !== undefined && String(child.student_id) === String(entry.student_id);
}

function todayAbsences(childId, iso) {
  const box = state.absence;
  const entries = box && box.data && Array.isArray(box.data.entries) ? box.data.entries : [];
  return entries.filter((entry) => {
    if (!absenceOfChild(entry, childId, box.connectionId || "")) return false;
    if (entry.status && entry.status !== ABSENCE_STATUS_ACCEPTED) return false;
    const from = String(entry.from_date || "");
    const till = String(entry.till_date || from);
    return !!from && from <= iso && iso <= till;
  });
}

function absenceTodayRow(entry) {
  const from = showDate(entry.from_date);
  const till = showDate(entry.till_date || entry.from_date);
  const sub = [absenceTypeLabel(entry.kind), from === till ? from : dateRange(from, till)].filter(Boolean).join(" · ");
  return el("div", { class: "row row-note row-absence" }, [
    el("span", { class: "row-dot" }, [icon("absence", 16)]),
    el("div", { class: "row-main" }, [
      el("div", { class: "row-title" }, t("overview.absence.title")),
      sub ? el("div", { class: "row-sub" }, sub) : null,
    ]),
  ]);
}

function markCheckRow(mark, childId) {
  const keys = MARK_CLARIFY_KEYS[mark.state];
  return el("button", {
    class: "row row-check",
    type: "button",
    onclick: () => openMarkSheet(mark, childId),
  }, [
    el("span", { class: "row-dot" }, [icon("alert", 16)]),
    el("div", { class: "row-main" }, [
      el("div", { class: "row-title" }, t("marks.today.needsCheck")),
      iservText("div", { class: "row-sub" }, [markLabel(mark), t(keys.title)].join(" · ")),
    ]),
    el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]),
  ]);
}

function todayLeadingRows(childId, iso) {
  const rows = [];
  for (const entry of todayAbsences(childId, iso)) {
    rows.push({ key: `${childId}:absence:${entry.id || entry.from_date}`, node: absenceTodayRow(entry) });
  }
  for (const mark of marksOfDay(childId, iso)) {
    if (!markNeedsCheck(mark)) continue;
    rows.push({ key: `${childId}:markCheck:${mark.id}`, node: markCheckRow(mark, childId) });
  }
  return rows;
}

function chapterRows(chapter, size, block, items, build, allRow) {
  const shown = layoutBlocks().shownItems(block, size, items);
  chapter.count = items.length;
  chapter.size = size;
  chapter.blocks = shown.items.map(build);
  if (allRow) chapter.blocks.push(allRow);
  return chapter;
}

function compactRow(title, meta, unread, onclick) {
  return el("button", { class: unread ? "row compact" : "row compact read", type: "button", onclick }, [
    el("span", { class: "row-dot" }, unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, title)]),
    meta ? el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, meta)]) : null,
  ]);
}

function sizedRow(size, title, sub, meta, unread, onclick, tags) {
  if (size === layoutBlocks().SIZE_COMPACT) return compactRow(title, meta, unread, onclick);
  return overviewListRow(title, sub, meta, unread, onclick, tags);
}

function childTag(child) {
  if (!child || state.children.length < 2) return null;
  return iservText("span", { class: "tag child" }, childShortName(child));
}

function lettersChapter(size) {
  if (!moduleOn("letters")) return null;
  const block = layoutBlocks().blockOf("letters");
  const chapter = overviewChapter("letters", t("blocks.letters.title"), {
    label: t("overview.viewAll"),
    onclick: () => openPostSegment("letters"),
  });
  const data = state.letters;
  if (!data || (!data.error && data.tab && data.tab !== LETTERS_TAB_CURRENT)) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("letters:loading")];
    chapter.loading = true;
    autoLoad(lettersLoadKey(LETTERS_TAB_CURRENT), () => loadLetters(LETTERS_TAB_CURRENT));
    return chapter;
  }
  if (data.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("letters:failed", () => loadLetters(LETTERS_TAB_CURRENT))];
    return chapter;
  }
  const unread = (data.letters || []).filter((letter) => letter.unread || letterConfirmationOpen(letter));
  if (!unread.length) return null;
  chapter.fresh = true;
  return chapterRows(chapter, size, block, unread, (letter) => overviewBlock(
    `letter:${letterKey(letter)}`,
    sizedRow(
      size,
      letter.title || t("letters.untitled"),
      letter.sender || "",
      letter.published ? showDate(letter.published) : "",
      true,
      () => openLetterFromOverview(letter),
      letterTagNodes(letter)
    )
  ), overviewAllRow("letters:all", t("overview.all.letters"), () => openPostSegment("letters")));
}

function overviewPostTitle(tile) {
  const preview = stripHtml(tile.text).slice(0, 140);
  if (tile.title && tile.title !== "...") return tile.title;
  return preview.split(". ")[0] || t("pinboard.post.fallback");
}

function pinboardChapter(size) {
  if (!moduleOn("pinboard")) return null;
  const block = layoutBlocks().blockOf("noticeboard");
  const chapter = overviewChapter("noticeboard", t("blocks.noticeboard.title"), {
    label: t("overview.viewAll"),
    onclick: () => openPostSegment("pinboard"),
  });
  const data = state.pinboard;
  if (!data) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("pinboard:loading")];
    chapter.loading = true;
    return chapter;
  }
  if (data.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("pinboard:failed", loadPinboard)];
    return chapter;
  }
  const fresh = freezePinboardOrder(data.feed || []).filter((tile) => tile.unread);
  if (!fresh.length) return null;
  chapter.fresh = true;
  return chapterRows(chapter, size, block, fresh, (tile) => overviewBlock(
    `post:${tileKey(tile)}`,
    sizedRow(size, overviewPostTitle(tile), tile.folder_title || "", "", true, () => openPost(tile), [schoolTag(tile)])
  ), overviewAllRow("pinboard:all", t("overview.all.pinboard"), () => openPostSegment("pinboard")));
}

function messengerChapter(size) {
  if (!moduleOn("messenger")) return null;
  const block = layoutBlocks().blockOf("chat");
  const data = state.messengerRooms;
  if (!data) return null;
  if (data.error) {
    const failed = overviewChapter("chat", t("blocks.chat.title"), null);
    failed.bodyClass = "panel-rest";
    failed.blocks = [overviewFailureBlock("messenger:failed", () => {
      state.messengerRooms = null;
      loadMessengerRooms();
    })];
    return failed;
  }
  const unread = (data.rooms || []).filter((room) => Number(room.unread_count) > 0);
  if (!unread.length) return null;
  const chapter = overviewChapter("chat", t("blocks.chat.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("messenger"),
  });
  chapter.fresh = true;
  return chapterRows(chapter, size, block, unread, (room) => overviewBlock(
    `chat:${room.room_id}`,
    sizedRow(
      size,
      room.name || t("messenger.title"),
      tCount("overview.messenger.count", Number(room.unread_count)),
      size === layoutBlocks().SIZE_COMPACT ? badgeText(Number(room.unread_count)) : messengerStamp(room.last_message_at),
      true,
      () => openMessengerRoomFromOverview(room),
      [schoolTag(room)]
    )
  ), overviewAllRow("chat:all", t("overview.all.messenger"), () => setView("messenger")));
}

function openMessengerRoomFromOverview(room) {
  setView("messenger");
  openMessengerRoom(room);
}

function overviewConferenceCells(item) {
  return (item.cells || []).map((cell) => String(cell || "").trim()).filter(Boolean);
}

function overviewConferenceDate(cells) {
  for (const cell of cells) {
    const parsed = conferenceCellDate(cell);
    if (parsed) return isoDate(parsed);
  }
  return "";
}

function conferenceEntries(todayIso) {
  const rows = [];
  (state.conferences.items || []).forEach((item, index) => {
    const cells = overviewConferenceCells(item);
    if (!cells.length) return;
    const day = overviewConferenceDate(cells);
    if (day && day < todayIso) return;
    rows.push({ key: `conference:${day || index}:${index}`, day, title: cells[0], sub: cells.slice(1, 4).join(" · "), connection_id: item.connection_id || "", item });
  });
  rows.sort((left, right) => (left.day || "9999-12-31").localeCompare(right.day || "9999-12-31"));
  return rows;
}

function conferencesChapter(size) {
  if (!moduleOn("conferences")) return null;
  const block = layoutBlocks().blockOf("conferences");
  const data = state.conferences;
  if (!data) return null;
  const chapter = overviewChapter("conferences", t("blocks.conferences.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("conferences"),
  });
  if (data.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("conferences:failed", loadConferences)];
    return chapter;
  }
  const rows = conferenceEntries(isoDate(new Date()));
  if (!rows.length) return null;
  return chapterRows(chapter, size, block, rows, (row) => overviewBlock(
    row.key,
    sizedRow(size, row.title, row.sub, row.day ? showDate(row.day) : "", false, () => (row.item.page ? openConferenceFromOverview(row.item) : setView("conferences")), [schoolTag(row)])
  ), overviewAllRow("conferences:all", t("overview.all.conferences"), () => setView("conferences")));
}

function schoolEventsChapter(size) {
  if (!moduleOn("calendar")) return null;
  const block = layoutBlocks().blockOf("school_events");
  const data = state.schoolEvents;
  if (!data) return null;
  const chapter = overviewChapter("school_events", t("blocks.school_events.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("calendar"),
  });
  const rows = upcomingSchoolEvents();
  if (data.error || listUnknown(data, rows.length)) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("school_events:failed", loadSchoolEvents)];
    return chapter;
  }
  if (!rows.length) return listPartlyUnknown(data) ? overviewListFailure(chapter, "school_events", loadSchoolEvents) : null;
  return withPartialNote(chapterRows(chapter, size, block, rows, (event) => overviewBlock(
    `school_event:${event.connection_id || ""}:${event.uid}`,
    sizedRow(
      size,
      event.title || t("schoolEvents.untitled"),
      schoolEventSub(event),
      event.all_day ? isoLabel(schoolEventDay(event)) : `${formatWeekdayDay(new Date(event.start))} ${formatTime(new Date(event.start))}`,
      false,
      () => setView("calendar"),
      [schoolTag(event)]
    )
  ), overviewAllRow("school_events:all", t("overview.all.school_events"), () => setView("calendar"))), "school_events", data);
}

function overviewListFailure(chapter, key, load) {
  chapter.bodyClass = "panel-rest";
  chapter.blocks = [overviewFailureBlock(`${key}:failed`, load)];
  return chapter;
}

function withPartialNote(chapter, key, data) {
  if (listPartlyUnknown(data)) chapter.blocks.push(overviewNoteBlock(`${key}:partial`, t("overview.partial.school")));
  return chapter;
}

function tasksChapter(size) {
  if (!moduleOn("tasks")) return null;
  const block = layoutBlocks().blockOf("tasks");
  const data = state.tasks;
  if (!data) return null;
  const chapter = overviewChapter("tasks", t("blocks.tasks.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("tasks"),
  });
  if (data.error || listUnknown(data, listedTasks().length)) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("tasks:failed", loadTasks)];
    return chapter;
  }
  const rows = openTasks();
  if (!rows.length) return listPartlyUnknown(data) ? overviewListFailure(chapter, "tasks", loadTasks) : null;
  return withPartialNote(chapterRows(chapter, size, block, rows, (task) => overviewBlock(
    `task:${task.connection_id || ""}:${task.id}`,
    sizedRow(
      size,
      task.title || t("tasks.untitled"),
      "",
      task.due ? listMoment(task.due, task.due_text) : "",
      false,
      () => openTask(task),
      [schoolTag(task)]
    )
  ), overviewAllRow("tasks:all", t("overview.all.tasks"), () => setView("tasks"))), "tasks", data);
}

function newsChapter(size) {
  if (!moduleOn("news")) return null;
  const block = layoutBlocks().blockOf("news");
  const data = state.news;
  if (!data) return null;
  const chapter = overviewChapter("news", t("blocks.news.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("news"),
  });
  if (data.error || listUnknown(data, listedNews().length)) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("news:failed", loadNews)];
    return chapter;
  }
  const rows = currentNews();
  if (!rows.length) return listPartlyUnknown(data) ? overviewListFailure(chapter, "news", loadNews) : null;
  return withPartialNote(chapterRows(chapter, size, block, rows, (item) => overviewBlock(
    `news:${item.connection_id || ""}:${item.id}`,
    sizedRow(
      size,
      item.title || t("news.untitled"),
      String(item.category || item.category_slug || ""),
      item.date ? listMoment(item.date, item.date_text) : "",
      false,
      () => openNews(item),
      [schoolTag(item)]
    )
  ), overviewAllRow("news:all", t("overview.all.news"), () => setView("news"))), "news", data);
}

function absenceEntries(todayIso, limitIso) {
  const box = state.absence;
  const entries = box && box.data && Array.isArray(box.data.entries) ? box.data.entries : [];
  const rows = [];
  for (const entry of entries) {
    const from = entry.from_date || entry.till_date || "";
    const till = entry.till_date || entry.from_date || "";
    if (!till || till < todayIso) continue;
    if (from && from > limitIso) continue;
    rows.push(entry);
  }
  rows.sort((left, right) => String(left.from_date || "").localeCompare(String(right.from_date || "")));
  return rows;
}

function absenceStatusLabel(entry) {
  const key = `absence.status.${entry.status || ""}`;
  return entry.status && hasMessage(key) ? t(key) : "";
}

function absencesChapter(size) {
  if (!moduleOn("absences")) return null;
  const block = layoutBlocks().blockOf("absences");
  const box = state.absence;
  if (!box) return null;
  const chapter = overviewChapter("absences", t("blocks.absences.title"), {
    label: t("overview.viewAll"),
    onclick: () => setView("absence"),
  });
  if (box.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("absences:failed", loadAbsences)];
    return chapter;
  }
  const now = new Date();
  const rows = absenceEntries(isoDate(now), isoDate(addDays(now, OVERVIEW_UPCOMING_DAYS)));
  if (!rows.length) return null;
  return chapterRows(chapter, size, block, rows, (entry) => {
    const child = absenceChildName(entry);
    const title = child ? t("blocks.absences.row", { child, dates: absenceDates(entry) }) : absenceDates(entry);
    const sub = [absenceEntryLabel(entry), absenceStatusLabel(entry)].filter(Boolean).join(" · ");
    return overviewBlock(
      `absence:${entry.id}`,
      sizedRow(size, title, sub, "", false, () => setView("absence"), [schoolTag({ connection_id: box.connectionId || "" })])
    );
  }, overviewAllRow("absences:all", t("overview.all.absences"), () => setView("absence")));
}

function daysUntilLabel(days) {
  try {
    return new Intl.RelativeTimeFormat(currentLanguage(), { numeric: "auto" }).format(days, "day");
  } catch (error) {
    return formatNumber(days);
  }
}

function holidayEntries(todayIso) {
  const rows = [];
  const boxes = state.holidays && typeof state.holidays === "object" ? state.holidays : {};
  for (const id of Object.keys(boxes)) {
    const data = holidayData(id);
    if (!data || !Array.isArray(data.periods)) continue;
    for (const period of data.periods) {
      if (!period || !period.end || period.end < todayIso) continue;
      rows.push({ period, connection_id: id, key: `holiday:${id}:${period.id}` });
    }
  }
  rows.sort((left, right) => String(left.period.start).localeCompare(String(right.period.start)));
  return rows;
}

function holidaysChapter(size) {
  if (!(moduleOn("timetable") || noChildren()) || !state.holidays) return null;
  const block = layoutBlocks().blockOf("holidays");
  const todayIso = isoDate(new Date());
  const rows = holidayEntries(todayIso);
  if (!rows.length) return null;
  const chapter = overviewChapter("holidays", t("blocks.holidays.title"), null);
  const today = parseIsoDay(todayIso);
  return chapterRows(chapter, size, block, rows, (row) => {
    const start = parseIsoDay(row.period.start);
    const days = start ? Math.round((start - today) / 86400000) : 0;
    const meta = days > 0 ? daysUntilLabel(days) : t("holidays.day.free");
    const range = row.period.start === row.period.end ? showDate(row.period.start) : dateRange(showDate(row.period.start), showDate(row.period.end));
    return overviewBlock(
      row.key,
      sizedRow(size, holidayName(row.period), range, meta, false, () => openSheet(holidayRegionSheet), [schoolTag(row)])
    );
  }, null);
}

function overviewWeekDate(weekIdx, dayOfWeek) {
  return addDays(startOfWeek(addDays(new Date(), 7 * weekIdx)), Number(dayOfWeek) - 1);
}

function overviewLessonsAhead(child, todayIso, limitIso) {
  const found = [];
  for (const weekIdx of [0, 1]) {
    const week = overviewWeekData(child.key, weekIdx);
    if (!week || week.error || !Array.isArray(week.lessons)) continue;
    for (const lesson of week.lessons) {
      const date = overviewWeekDate(weekIdx, lesson.day_of_week);
      const iso = isoDate(date);
      if (iso < todayIso || iso > limitIso) continue;
      if (holidayQuietsLessons(holidayDay(iso, schoolOfChild(child)))) continue;
      found.push({ lesson, iso, date, child, week });
    }
  }
  found.sort((left, right) => left.iso.localeCompare(right.iso) || Number(left.lesson.period) - Number(right.lesson.period));
  return found;
}

function ensureOverviewWeeks(children, weeks) {
  for (const child of children) {
    for (const weekIdx of weeks) {
      if (!overviewWeekData(child.key, weekIdx)) autoLoad(`ovWeek:${child.key}:${weekIdx}`, () => loadOverviewWeek(child.key, weekIdx));
    }
  }
}

function lessonDayLabel(iso, date) {
  if (iso === isoDate(new Date())) return t("blocks.day.today");
  if (iso === isoDate(addDays(new Date(), 1))) return t("blocks.day.tomorrow");
  return formatWeekdayDay(date);
}

function lessonMinutesAhead(entry, start, now) {
  const dayGap = Math.round((entry.date.getTime() - addDays(now, 0).getTime()) / 86400000);
  return dayGap * 1440 + start - (now.getHours() * 60 + now.getMinutes());
}

function nextLessonChapter(size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const block = layoutBlocks().blockOf("next_lesson");
  const child = overviewActiveChild();
  ensureOverviewWeeks([child], [0, 1]);
  const now = new Date();
  const todayIso = isoDate(now);
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const upcoming = overviewLessonsAhead(child, todayIso, isoDate(addDays(now, 7))).filter((entry) => {
    if (lessonDropped(entry.lesson, child.key)) return false;
    if (entry.iso !== todayIso) return true;
    const start = lessonTimeMinutes(entry.lesson, periodTimes(entry.week, child.key));
    return start !== null && start > minutesNow;
  });
  const weeks = overviewWeeksState(child, [0, 1]);
  if (upcoming.length && upcoming[0].iso === todayIso) overviewWakeAtMinute(lessonTimeMinutes(upcoming[0].lesson, periodTimes(upcoming[0].week, child.key)));
  if (!upcoming.length && !weeks.failed && !weeks.refused) return null;
  const chapter = overviewChapter("next_lesson", t("blocks.next_lesson.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  if (!upcoming.length) {
    if (weeks.refused) return overviewRest(chapter, "next_lesson:refused", t(TIMETABLE_REFUSED_KEY));
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("next_lesson:failed", () => loadOverviewWeek(child.key, weeks.weekIdx))];
    return chapter;
  }
  chapterRows(chapter, size, block, upcoming, (entry) => {
    const time = lessonTime(entry.lesson, periodTimes(entry.week, child.key));
    const start = lessonTimeMinutes(entry.lesson, periodTimes(entry.week, child.key));
    const minutes = start === null || entry.iso !== todayIso ? null : lessonMinutesAhead(entry, start, now);
    const details = [entry.lesson.room || "", teacherSurname(entry.lesson), minutes !== null && minutes > 0 ? minutesUntilLabel(minutes) : ""].filter(Boolean).join(" · ");
    return overviewBlock(
      `next:${child.key}:${entry.iso}:${entry.lesson.period}`,
      sizedRow(
        size,
        entry.lesson.subject_label || entry.lesson.subject_code || t("timetable.lesson.fallback"),
        details,
        `${lessonDayLabel(entry.iso, entry.date)} · ${time || periodShort(entry.lesson.period)}`,
        false,
        () => openTimetableOf(child.key, entry.iso),
        []
      )
    );
  }, null);
  const note = holidayNoteBlock("next_lesson:holidays", schoolOfChild(child), [upcoming[0].iso]);
  if (note) chapter.blocks.push(note);
  chapter.count = 0;
  return chapter;
}

const NEXT_DAY_WEEKS = 5;

function nextSchoolDay(child, todayIso) {
  for (let weekIdx = 0; weekIdx < NEXT_DAY_WEEKS; weekIdx += 1) {
    const week = overviewWeekData(child.key, weekIdx);
    if (!week) {
      ensureOverviewWeeks([child], [weekIdx]);
      return { pending: true };
    }
    if (timetableRefused(week)) return { refused: true };
    if (week.error) return { failed: true, weekIdx };
    if (!Array.isArray(week.lessons)) return { unreachable: true };
    const days = [...new Set(week.lessons.map((lesson) => Number(lesson.day_of_week)))].sort((left, right) => left - right);
    for (const day of days) {
      const date = overviewWeekDate(weekIdx, day);
      const iso = isoDate(date);
      if (iso <= todayIso) continue;
      const lessons = todayLessons(week, day);
      if (holidayQuietsLessons(holidayDay(iso, schoolOfChild(child)))) continue;
      return { iso, date, week, lessons };
    }
  }
  return { unknown: true };
}

function nextDayHead(found, now) {
  if (found.iso === isoDate(addDays(now, 1))) return { title: t("blocks.day.tomorrow"), meta: formatWeekdayDay(found.date) };
  return { title: formatWeekdayLong(found.date), meta: dateLabel(found.iso) };
}

function nextDayChapter(size) {
  return nextDayChapterAs("next_day", size);
}

function nextDayChapterAs(key, size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const child = overviewActiveChild();
  const now = new Date();
  const found = nextSchoolDay(child, isoDate(now));
  const head = found.iso ? nextDayHead(found, now) : { title: t("blocks.next_day.title"), meta: "" };
  const chapter = overviewChapter(key, head.title, {
    label: t("overview.toTimetable"),
    onclick: () => openTimetableOf(child.key, found.iso || ""),
  });
  chapter.meta = head.meta;
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  if (found.pending) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock(`${key}:loading`)];
    chapter.loading = true;
    return chapter;
  }
  if (found.refused) return overviewRest(chapter, `${key}:refused`, t(TIMETABLE_REFUSED_KEY));
  if (found.unreachable) return overviewRest(chapter, `${key}:unreachable`, t("overview.timetable.unreachable"));
  if (found.failed) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock(`${key}:failed`, () => loadOverviewWeek(child.key, found.weekIdx))];
    return chapter;
  }
  if (found.unknown) {
    const holiday = holidayTodayCard(isoDate(addDays(now, 1)), 0, schoolOfChild(child));
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [holiday ? overviewBlock(`${key}:holiday`, holiday) : null, overviewRestBlock(`${key}:unknown`, t("overview.nextDay.unknown"))].filter(Boolean);
    return chapter;
  }
  const times = periodTimes(found.week, child.key);
  const groups = groupTodayLessons(found.lessons);
  const brackets = overviewBrackets(groups);
  const limit = layoutBlocks().limitOf(layoutBlocks().blockOf(key), size);
  chapter.bodyClass = "rows flat";
  chapter.size = size;
  groups.slice(0, limit).forEach((group, position) => {
    const entries = group.lessons.map((lesson) => ({
      lesson,
      time: lessonTime(lesson, times),
      minutes: lessonTimeMinutes(lesson, times),
      childId: child.key,
      mark: markAt(child.key, lessonIso(lesson), lesson.period, lesson),
    }));
    entries[0].when = null;
    const node = entries.length >= COURSE_CELL_MIN
      ? compactCoursesRow(entries, false, found.week.courses)
      : entries.length > 1
        ? compactLessonPair(entries, false)
        : compactLesson(entries[0], false);
    const changed = group.lessons.some((lesson) => !!displayChangeKind(lesson, child.key));
    chapter.blocks.push(Object.assign(overviewBlock(`${key}:${child.key}:${group.period}`, node, brackets[position], changed), { sortTime: entries[0].minutes }));
  });
  const own = todayOwnItems(child.key, found.iso, found.week).map((item) => Object.assign(overviewBlock(`${key}:${child.key}:own:${item.entry.id}`, todayOwnRow(item, -1)), { sortTime: item.start }));
  if (own.length) chapter.blocks = mergeByTime(chapter.blocks, own);
  const note = holidayNoteBlock(`${key}:holidays`, schoolOfChild(child), [found.iso]);
  if (note) chapter.blocks.push(note);
  chapter.count = found.lessons.filter((lesson) => !!displayChangeKind(lesson, child.key)).length;
  chapter.nowKey = chapter.blocks[0] ? chapter.blocks[0].key : null;
  return chapter;
}

function weekChapter(size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const child = overviewActiveChild();
  ensureOverviewWeeks([child], [0]);
  const week = overviewWeekData(child.key, 0);
  const chapter = overviewChapter("week", t("blocks.week.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  if (!week) {
    chapter.bodyClass = "panel-rest";
    chapter.loading = true;
    chapter.blocks = [overviewLoadingBlock("week:loading")];
    return chapter;
  }
  if (timetableRefused(week)) return overviewRest(chapter, "week:refused", t(TIMETABLE_REFUSED_KEY));
  if (week.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("week:failed", () => loadOverviewWeek(child.key, 0))];
    return chapter;
  }
  if (!Array.isArray(week.lessons)) return overviewRest(chapter, "week:unreachable", t("overview.timetable.unreachable"));
  if (!week.lessons.length && !holidayFullWeek(startOfWeek(new Date()), week, schoolOfChild(child))) return null;
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  chapter.size = size;
  chapter.count = 0;
  chapter.bodyClass = size === layoutBlocks().SIZE_COMPACT ? "tt-block tt-compact" : "tt-block";
  chapter.blocks = [overviewBlock(`week:${child.key}`, timetableGrid(week, child.key, { monday: startOfWeek(new Date()), swipe: false }))];
  return chapter;
}

function overviewWeekIndexOf(iso) {
  const date = parseIsoDay(iso);
  if (!date) return 0;
  return Math.round((startOfWeek(date).getTime() - startOfWeek(new Date()).getTime()) / (7 * 86400000));
}

function openTimetableOf(childKey, iso) {
  const options = iso ? { week: overviewWeekIndexOf(iso) } : undefined;
  if (childKey && childKey !== state.childId) {
    state.childId = childKey;
    state.timetable = null;
    setView("timetable", options);
    reloadTimetable();
    return;
  }
  setView("timetable", options);
}

function holidaysUnsure(school) {
  const boxes = state.holidays;
  if (!boxes || typeof boxes !== "object") return false;
  const ids = Object.keys(boxes);
  const key = ids.includes(school) ? school : ids.length === 1 ? ids[0] : null;
  if (key === null) return false;
  const box = boxes[key];
  return !box || box.status === HOLIDAY_STATUS_UNKNOWN;
}

function holidayNoteBlock(key, school, isos) {
  if (holidaysUnsure(school)) return overviewNoteBlock(key, t("overview.holidays.unknown"));
  const day = isos.map((iso) => (holidayIsUncertain(iso, school) ? holidayDay(iso, school) : null)).find(Boolean);
  if (!day) return null;
  const name = holidayName(day) || t(day.kind === HOLIDAY_KIND_PUBLIC ? "holidays.day.public" : "holidays.day.free");
  return overviewNoteBlock(key, t("overview.holidays.maybeFree", { name }));
}

function overviewWeeksState(child, weeks) {
  for (const weekIdx of weeks) {
    const week = overviewWeekData(child.key, weekIdx);
    if (!week) return { pending: true };
    if (timetableRefused(week)) return { refused: true };
    if (week.error) return { failed: true, weekIdx };
  }
  return {};
}

function changesChapter(size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const block = layoutBlocks().blockOf("changes");
  ensureOverviewWeeks(state.children, [0, 1]);
  const now = new Date();
  const rows = [];
  const missing = [];
  for (const child of state.children) {
    const weeks = overviewWeeksState(child, [0, 1]);
    if (weeks.failed || weeks.pending) missing.push({ child, weeks });
    for (const entry of overviewLessonsAhead(child, isoDate(now), isoDate(addDays(now, OVERVIEW_UPCOMING_DAYS)))) {
      const kind = displayChangeKind(entry.lesson, child.key);
      if (kind) rows.push(Object.assign({ kind }, entry));
    }
  }
  rows.sort((left, right) => left.iso.localeCompare(right.iso) || Number(left.lesson.period) - Number(right.lesson.period));
  const failed = missing.find((entry) => entry.weeks.failed);
  if (!rows.length && !failed) return null;
  const chapter = overviewChapter("changes", t("blocks.changes.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  if (!rows.length) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("changes:failed", () => loadOverviewWeek(failed.child.key, failed.weeks.weekIdx))];
    return chapter;
  }
  const notes = [];
  if (failed) notes.push(overviewNoteBlock("changes:partial", t("overview.changes.partial", { name: childShortName(failed.child) })));
  const unsure = state.children.map(schoolOfChild).find((school) => holidaysUnsure(school));
  if (unsure !== undefined) notes.push(holidayNoteBlock("changes:holidays", unsure, []));
  chapterRows(chapter, size, block, rows, (entry) => {
    const lesson = entry.lesson;
    const title = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
    const who = entry.kind === "cancelled" ? "" : [teacherSurname(lesson), lesson.room].filter(Boolean).join(" ");
    const moved = lessonMove(lesson, entry.kind);
    const detail = [periodShort(lesson.period), lessonTime(lesson, periodTimes(entry.week, entry.child.key)), who, moved ? moveCellLabel(moved) : ""].filter(Boolean).join(" · ");
    const node = sizedRow(size, title, detail, lessonDayLabel(entry.iso, entry.date), false, () => openTimetableOf(entry.child.key, entry.iso), [
      childTag(entry.child),
      schoolTag({ connection_id: connectionOfKey(entry.child.key) }),
    ]);
    const slot = size === layoutBlocks().SIZE_COMPACT ? node.querySelector(".row-side") : node.querySelector(".row-main");
    slot.append(changeTag(entry.kind));
    return overviewBlock(`change:${entry.child.key}:${entry.iso}:${lesson.period}`, node, null, true);
  }, null);
  chapter.blocks.push(...notes.filter(Boolean));
  return chapter;
}

const BLOCK_CHAPTERS = {
  today: todayChapter,
  next_day: nextDayChapter,
  next_lesson: nextLessonChapter,
  week: weekChapter,
  letters: lettersChapter,
  noticeboard: pinboardChapter,
  absences: absencesChapter,
  conferences: conferencesChapter,
  school_events: schoolEventsChapter,
  tasks: tasksChapter,
  news: newsChapter,
  forums: (size) => forumsChapter(size),
  texts: (size) => textsChapter(size),
  infodisplay: (size) => infodisplayChapter(size),
  whiteboards: (size) => whiteboardsChapter(size),
  holidays: holidaysChapter,
  changes: changesChapter,
  chat: messengerChapter,
};

function overviewChapters() {
  overviewWakeAt = null;
  overviewBuiltOn = isoDate(new Date());
  const chapters = [];
  for (const entry of enabledOverviewBlocks()) {
    const build = BLOCK_CHAPTERS[entry.key];
    const chapter = build ? build(entry.size, entry) : null;
    if (chapter) chapters.push(chapter);
  }
  if (chapters.length && moduleCardWanted()) {
    chapters[0].blocks = [overviewBlock("modules:card", moduleCard(true)), ...chapters[0].blocks];
  }
  if (chapters.length && anyOutage()) {
    chapters[0].blocks = [overviewBlock("outage:banner", outageBanner()), ...chapters[0].blocks];
  }
  return chapters;
}

function overviewNewCount(area) {
  if (area === "letters") return lettersUnreadCount();
  if (area === "noticeboard") return pinboardUnreadCount();
  if (area === "chat") return messengerUnreadTotal();
  return 0;
}

function freezePinboardOrder(feed) {
  const frozen = state._overviewPinboardOrder;
  if (!frozen) {
    const unread = feed.filter((tile) => tile.unread);
    const seen = feed.filter((tile) => !tile.unread);
    const order = unread.concat(seen);
    state._overviewPinboardOrder = order.map(tileKey);
    return order;
  }
  const rank = (tile) => {
    const index = frozen.indexOf(tileKey(tile));
    return index < 0 ? frozen.length : index;
  };
  return feed
    .map((tile, index) => ({ tile, index }))
    .sort((left, right) => rank(left.tile) - rank(right.tile) || left.index - right.index)
    .map((entry) => entry.tile);
}

function chapterCount(chapter) {
  const count = Number(chapter.count) || 0;
  if (!count) return null;
  return el("span", { class: chapter.fresh ? "count fresh" : "count" }, chapter.fresh ? t("blocks.count.fresh", { count: formatNumber(count) }) : formatNumber(count));
}

function chapterHead(chapter) {
  const inner = [
    el("h2", { class: "section-label" }, chapter.title),
    chapter.meta ? el("span", { class: "panel-meta" }, chapter.meta) : null,
    chapterCount(chapter),
    chapter.link ? el("span", { class: "chev chev-next" }, [icon("chevron", 16)]) : null,
  ];
  if (!chapter.link) return el("div", { class: "chapter-head static" }, inner);
  return el("button", { class: "chapter-head", type: "button", "aria-label": chapter.link.label, onclick: chapter.link.onclick }, inner);
}

function overviewPanelHead(chapter, pageIndex, pageCount, panelIndex) {
  if (layoutMode() !== "phone") return chapterHead(chapter);
  const head = el("div", { class: "panel-head" });
  const first = pageIndex === 0;
  const counter = pageCount > 1
    ? t("overview.page.counter", { current: formatNumber(pageIndex + 1), total: formatNumber(pageCount) })
    : "";
  if (panelIndex > 0) {
    head.append(el("button", {
      class: "icon-btn panel-back",
      type: "button",
      "aria-label": first && chapter.previousTitle
        ? t("overview.page.backArea", { area: chapter.previousTitle })
        : t("overview.page.back", {
          area: chapter.title,
          current: formatNumber(Math.max(pageIndex, 1)),
          total: formatNumber(pageCount),
        }),
      onclick: (event) => overviewStep(-1, event.currentTarget.closest(".panel")),
    }, [el("span", { class: "ico-slot chev-up", html: iconSvg("chevron", 18) })]));
  }
  head.append(first
    ? el("h2", { class: "section-label" }, chapter.title)
    : el("p", { class: "section-label continued" }, chapter.title));
  if (chapter.meta) head.append(el("span", { class: "panel-meta" }, chapter.meta));
  if (counter) head.append(el("span", { class: "panel-counter" }, counter));
  if (chapter.link) {
    head.append(el("button", { class: "panel-link", type: "button", onclick: chapter.link.onclick }, chapter.link.label));
  }
  return head;
}

function overviewPanelArrow(chapter, pageIndex, pageCount, next, changesAhead) {
  const last = pageIndex === pageCount - 1;
  if (last && !next) return null;
  const current = formatNumber(pageIndex + 2);
  const total = formatNumber(pageCount);
  const fresh = last && next ? Number(next.count) || 0 : 0;
  const label = last
    ? (fresh
      ? tCount("overview.arrow.areaNew", fresh, { area: next.title })
      : t("overview.arrow.area", { area: next.title }))
    : changesAhead
      ? tCount("overview.arrow.pageChanges", changesAhead, { current, total })
      : t("overview.arrow.page", { current, total });
  const button = el("button", {
    class: "panel-arrow-btn",
    type: "button",
    "data-arrow": last ? "area" : "page",
    "aria-label": label,
    onclick: (event) => overviewStep(1, event.currentTarget.closest(".panel")),
  }, [
    el("span", { class: "ico-slot", html: iconSvg("chevron", 18) }),
    last ? el("span", { class: "panel-arrow-name" }, next.title) : null,
    fresh ? el("span", { class: "badge panel-arrow-badge", "aria-hidden": "true" }, badgeText(fresh)) : null,
    !last && changesAhead ? el("span", { class: "panel-arrow-dot", "aria-hidden": "true" }) : null,
  ]);
  return el("div", { class: "panel-arrow" }, [button]);
}

function overviewPanel(chapter, pageIndex, pageCount, blocks, panelIndex, nextTitle, snap, changesAhead) {
  const label = pageCount > 1
    ? t("overview.page.label", {
      area: chapter.title,
      current: formatNumber(pageIndex + 1),
      total: formatNumber(pageCount),
    })
    : chapter.title;
  const panel = el("section", {
    class: "panel",
    role: "group",
    tabindex: "-1",
    "data-area": chapter.area,
    "data-block": chapter.area,
    "data-page": String(pageIndex),
    "aria-label": label,
  });
  panel.dataset.blocks = chapter.blocks.map((block) => block.key).join(" ");
  panel.append(overviewPanelHead(chapter, pageIndex, pageCount, snap ? panelIndex : 0));
  if (chapter.chips) panel.append(overviewChips(chapter.chips.active));
  const body = el("div", { class: chapter.bodyClass });
  for (const block of blocks) body.append(block.node);
  panel.append(body);
  if (!snap) return panel;
  const arrow = overviewPanelArrow(chapter, pageIndex, pageCount, nextTitle, changesAhead);
  if (arrow) {
    panel.setAttribute("data-arrow", arrow.firstChild.getAttribute("data-arrow"));
    panel.append(arrow);
  }
  return panel;
}

function paginateBlocks(blocks, budget) {
  const limit = Math.max(1, budget);
  const pages = [];
  const moved = {};
  let page = [];
  let used = 0;
  let index = 0;
  while (index < blocks.length) {
    const block = blocks[index];
    if (!page.length) {
      page.push(index);
      used = block.height;
      index += 1;
      continue;
    }
    if (used + block.height <= limit) {
      page.push(index);
      used += block.height;
      index += 1;
      continue;
    }
    const bracket = block.bracket;
    if (bracket && !moved[bracket]) {
      let start = index;
      while (start > 0 && blocks[start - 1].bracket === bracket) start -= 1;
      let span = 0;
      for (let cursor = start; cursor < blocks.length && blocks[cursor].bracket === bracket; cursor += 1) {
        span += blocks[cursor].height;
      }
      if (start < index && page[0] < start && span <= limit) {
        moved[bracket] = true;
        while (page.length && page[page.length - 1] >= start) used -= blocks[page.pop()].height;
        index = start;
      }
    }
    pages.push(page);
    page = [];
    used = 0;
  }
  if (page.length) pages.push(page);
  balancePages(pages, blocks, limit);
  return pages.map((entries) => entries.map((position) => blocks[position].key));
}

function pageWeight(page, blocks) {
  return page.reduce((total, position) => total + blocks[position].height, 0);
}

function balancePages(pages, blocks, limit) {
  for (let index = pages.length - 1; index > 0; index -= 1) {
    const page = pages[index];
    const before = pages[index - 1];
    while (before.length - 1 >= OVERVIEW_MIN_BLOCKS_PER_PAGE) {
      const moving = blocks[before[before.length - 1]].height;
      if (pageWeight(page, blocks) + moving > limit) break;
      if (pageWeight(before, blocks) - moving < pageWeight(page, blocks) + moving) break;
      page.unshift(before.pop());
    }
  }
}

function overviewPortrait() {
  if (typeof window.matchMedia === "function") {
    const query = window.matchMedia("(orientation: portrait)");
    if (query && typeof query.matches === "boolean") return query.matches;
  }
  return window.innerHeight >= window.innerWidth;
}

function overviewPanelHeight(screen) {
  const bar = root().querySelector(".tabbar");
  const head = screen.querySelector(".header");
  if (!bar || !head) return 0;
  return screen.clientHeight - head.getBoundingClientRect().height - bar.getBoundingClientRect().height;
}

function overviewFlatten(container, chapters) {
  container.setAttribute("data-snap", "off");
  const panels = chapters.map((chapter, index) => overviewPanel(chapter, 0, 1, chapter.blocks, index, null, false, 0));
  container.replaceChildren(...panels);
  return panels;
}

function overviewMeasure(panels, chapters) {
  return panels.map((panel, index) => {
    const heights = chapters[index].blocks.map((block) => block.node.getBoundingClientRect().height);
    const content = heights.reduce((sum, value) => sum + value, 0);
    return { heights, frame: panel.getBoundingClientRect().height - content + OVERVIEW_ARROW_BAND };
  });
}

function overviewPlan(chapters, measures, panelHeight) {
  if (!(panelHeight > 0) || !overviewPortrait() || layoutMode() !== "phone") return null;
  const plan = [];
  for (let index = 0; index < chapters.length; index += 1) {
    const measure = measures[index];
    const blocks = chapters[index].blocks.map((block, position) => ({
      key: block.key,
      height: measure.heights[position],
      bracket: block.bracket,
    }));
    if (!blocks.length || blocks.some((block) => !(block.height > 0))) return null;
    const budget = panelHeight - measure.frame;
    if (budget < 1) return null;
    const pages = paginateBlocks(blocks, budget);
    if (pages.length > OVERVIEW_MAX_PAGES) return null;
    if (pages.length > 1 && pages.slice(0, -1).some((page) => page.length < OVERVIEW_MIN_BLOCKS_PER_PAGE)) return null;
    plan.push(pages);
  }
  return plan;
}

function overviewChangesAhead(chapter, pages, pageIndex) {
  const ahead = new Set();
  for (let index = pageIndex + 1; index < pages.length; index += 1) {
    for (const key of pages[index]) ahead.add(key);
  }
  return chapter.blocks.filter((block) => block.change && ahead.has(block.key)).length;
}

function overviewBuild(container, chapters, plan) {
  container.setAttribute("data-snap", "on");
  const panels = [];
  let panelIndex = 0;
  chapters.forEach((chapter, chapterIndex) => {
    const pages = plan[chapterIndex];
    const byKey = new Map(chapter.blocks.map((block) => [block.key, block]));
    const following = chapters[chapterIndex + 1] || null;
    chapter.previousTitle = chapterIndex > 0 ? chapters[chapterIndex - 1].title : "";
    const nextTitle = following
      ? { title: following.title, count: overviewNewCount(following.area) }
      : null;
    pages.forEach((keys, pageIndex) => {
      const last = pageIndex === pages.length - 1;
      panels.push(overviewPanel(
        chapter,
        pageIndex,
        pages.length,
        keys.map((key) => byKey.get(key)),
        panelIndex,
        last ? nextTitle : null,
        true,
        last ? 0 : overviewChangesAhead(chapter, pages, pageIndex)
      ));
      panelIndex += 1;
    });
  });
  container.replaceChildren(...panels);
  if (!overviewTeachShown) {
    const first = panels[0] && panels[0].querySelector(".panel-arrow-btn");
    if (first) {
      first.classList.add("teach");
      overviewTeachShown = true;
    }
  }
  return panels;
}

function overviewScreen() {
  const app = root();
  if (!app) return null;
  const screen = app.querySelector(".screen");
  return screen && screen.querySelector(".overview") ? screen : null;
}

function overviewPanelTop(screen, panel) {
  const head = screen.querySelector(".header");
  const offset = head ? head.getBoundingClientRect().height : 0;
  return panel.getBoundingClientRect().top - screen.getBoundingClientRect().top + screen.scrollTop - offset;
}

function overviewPanelAt(screen) {
  const panels = [...screen.querySelectorAll(".overview .panel")];
  if (!panels.length) return null;
  let best = panels[0];
  let bestDelta = Infinity;
  for (const panel of panels) {
    const delta = Math.abs(overviewPanelTop(screen, panel) - screen.scrollTop);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = panel;
    }
  }
  return best;
}

function rememberOverviewAnchor() {
  const screen = overviewScreen();
  if (!screen || screen.getAttribute("data-snap") !== "on") return;
  if (screen.scrollTop < 2) {
    state._overviewAnchor = null;
    return;
  }
  const panel = overviewPanelAt(screen);
  if (!panel) return;
  const block = panel.querySelector("[data-block]");
  state._overviewAnchor = { area: panel.dataset.area, blockKey: block ? block.dataset.block : null };
}

function overviewPanelHolding(panels, key) {
  return panels.find((panel) => [...panel.querySelectorAll("[data-block]")].some((node) => node.dataset.block === key));
}

function overviewAnchorPanel(screen, chapters, anchor) {
  const panels = [...screen.querySelectorAll(".overview .panel")].filter((panel) => panel.dataset.area === anchor.area);
  if (!panels.length) return null;
  if (!anchor.blockKey) return panels[0];
  const direct = overviewPanelHolding(panels, anchor.blockKey);
  if (direct) return direct;
  const chapter = chapters.find((entry) => entry.area === anchor.area);
  if (chapter) {
    const keys = chapter.blocks.map((block) => block.key);
    for (let index = keys.indexOf(anchor.blockKey) + 1; index > 0 && index < keys.length; index += 1) {
      const found = overviewPanelHolding(panels, keys[index]);
      if (found) return found;
    }
  }
  return panels[0];
}

function applyOverviewAnchor(screen, chapters) {
  const today = chapters.find((chapter) => chapter.area === "today") || null;
  if (state._overviewNow && today && today.nowKey) {
    state._overviewAnchor = { area: "today", blockKey: today.nowKey };
    state._overviewNow = false;
  }
  const anchor = state._overviewAnchor;
  if (!anchor) return;
  const panel = overviewAnchorPanel(screen, chapters, anchor);
  if (panel) screen.scrollTop = overviewPanelTop(screen, panel);
}

function overviewStep(direction, from) {
  const screen = overviewScreen();
  if (!screen) return;
  const panels = [...screen.querySelectorAll(".overview .panel")];
  const current = from && panels.indexOf(from) >= 0 ? from : overviewPanelAt(screen);
  const index = panels.indexOf(current) + direction;
  if (index < 0 || index >= panels.length) return;
  const behavior = typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  screen.scrollTo({ top: overviewPanelTop(screen, panels[index]), behavior });
}

function applyOverviewPagination() {
  if (state.view !== "overview" || !overviewModel) return;
  const app = root();
  const screen = app && app.querySelector(".screen");
  const container = screen && screen.querySelector(".overview");
  if (!container) return;
  const chapters = overviewModel.chapters;
  const panels = overviewFlatten(container, chapters);
  const panelHeight = overviewPanelHeight(screen);
  const plan = overviewPlan(chapters, overviewMeasure(panels, chapters), panelHeight);
  overviewModel.plan = plan;
  overviewModel.panelHeight = panelHeight;
  if (!plan) {
    screen.removeAttribute("data-snap");
    screen.style.removeProperty("--panel-h");
    return;
  }
  overviewBuild(container, chapters, plan);
  const bar = root().querySelector(".tabbar");
  const head = screen.querySelector(".header");
  screen.setAttribute("data-snap", "on");
  screen.style.setProperty("--panel-h", `${panelHeight}px`);
  screen.style.setProperty("--overview-pad-b", `${bar.getBoundingClientRect().height}px`);
  screen.style.setProperty("--overview-pad-t", `${head.getBoundingClientRect().height}px`);
  applyOverviewAnchor(screen, chapters);
}

function setupOverviewRelayout() {
  if (overviewRelayoutBound) return;
  overviewRelayoutBound = true;
  const relayout = () => {
    if (state.view !== "overview") return;
    rememberOverviewAnchor();
    applyOverviewPagination();
  };
  window.addEventListener("resize", relayout);
  window.addEventListener("orientationchange", relayout);
  if (window.visualViewport) window.visualViewport.addEventListener("resize", relayout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout, relayout);
  if (typeof ResizeObserver === "function") {
    const observer = new ResizeObserver(relayout);
    observer.observe(document.documentElement);
  }
}

function overviewFocusIn(event) {
  const screen = overviewScreen();
  if (!screen || screen.getAttribute("data-snap") !== "on") return;
  const panel = event.target && event.target.closest ? event.target.closest(".panel") : null;
  if (!panel) return;
  const top = overviewPanelTop(screen, panel);
  if (Math.abs(top - screen.scrollTop) < 2) return;
  screen.scrollTop = top;
}

function overviewView() {
  setupOverviewRelayout();
  for (const child of moduleOn("timetable") ? state.children : []) {
    if (!overviewWeekData(child.key, 0)) {
      autoLoad(`ovWeek:${child.key}:0`, () => loadOverviewWeek(child.key, 0));
    }
  }
  if (!state.absence && moduleOn("absences")) autoLoad("absence", loadAbsences);
  const chapters = overviewChapters();
  overviewModel = { chapters, plan: null, panelHeight: 0 };
  const container = el("div", { class: "overview", "data-snap": "off" });
  container.addEventListener("focusin", overviewFocusIn);
  if (!chapters.length) {
    const empty = [];
    if (anyOutage()) empty.push(outageBanner());
    if (moduleCardWanted()) empty.push(moduleCard(true));
    empty.push(overviewEmptyState());
    return el("div", { class: "overview-host" }, [schoolIssueBanner(), appUpdateBanner(), mailNotice(), ...empty].filter(Boolean));
  }
  overviewFlatten(container, chapters);
  const notices = [schoolIssueBanner(), appUpdateBanner(), mailNotice()].filter(Boolean);
  if (!notices.length) return container;
  return el("div", { class: "overview-host" }, [...notices, container]);
}

async function loadMailCounts() {
  const outcome = await reload("mail", () => getJson("api/mail"), Array.isArray(state.mail));
  if (!outcome) return;
  if (outcome.data) {
    state.mail = Array.isArray(outcome.data.schools) ? outcome.data.schools : [];
    state.mailCountsError = null;
  } else if (outcome.error) {
    state.mailCountsError = outcome;
  }
  if (state.view === "overview" || state.view === "mail") rerender();
}

function openMailOf(connectionId) {
  state.mailSchool = connectionId || "";
  state.mailFolder = "";
  state.mailList = null;
  setView("mail");
}

function mailNotice() {
  const listed = Array.isArray(state.mail) ? state.mail : [];
  const unread = listed.filter((entry) => Number(entry.unread) > 0);
  if (!unread.length) return null;
  return el("div", { class: "mail-notice", role: "status" }, unread.map((entry) => el("div", { class: "mail-notice-row" }, [
    iservText("span", { class: "mail-notice-text" }, manySchools()
      ? tCount("mail.schoolUnread", Number(entry.unread), { school: schoolFullName(entry.connection_id) || entry.school || "" })
      : tCount("mail.unread", Number(entry.unread))),
    el("button", { class: "btn ghost slim mail-notice-open", type: "button", onclick: () => openMailOf(entry.connection_id) }, [icon("letters", 16), t("mail.show")]),
  ])));
}
