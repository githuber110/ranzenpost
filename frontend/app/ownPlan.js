function planAddButton() {
  return el("button", {
    class: "icon-btn plan-add",
    type: "button",
    "aria-label": t("periods.entries.add"),
    onclick: () => openEntryForm({ school: currentConnectionId(), child: state.childId, fromPlan: true }),
  }, [icon("plus", 18)]);
}

function planFreeCell(owner, iso, period) {
  const school = connectionOfKey(owner);
  const data = school ? state.periods && state.periods[school] : null;
  if (!periodsReady(data)) return el("div", { class: "tt-cell free" });
  const row = data.grid.find((item) => item.number === period);
  if (!row) return el("div", { class: "tt-cell free" });
  const start = periodRules().minutesOf(row.start);
  const day = parseIsoDay(iso);
  return el("button", {
    class: "tt-cell free tt-free-slot",
    type: "button",
    "aria-label": t("periods.freeSlot", { day: day ? formatWeekdayShort(day) : iso, time: clockLabel(start) }),
    onclick: () => openEntryForm({ school, child: owner, date: iso, start, fromPlan: true }),
  });
}

const PLAN_WEEK_DAYS = 7;

function planWeekendEntries(owner, monday) {
  const P = periodRules();
  const school = connectionOfKey(owner);
  const box = school ? periodsData(school) : null;
  if (!periodsReady(box) || !box.entries.length) return [];
  const child = P.rawChild(owner);
  const found = [];
  for (let day = HOLIDAY_SCHOOL_DAYS; day < PLAN_WEEK_DAYS; day += 1) {
    const iso = isoDate(addDays(monday, day));
    const holiday = holidayDay(iso, school);
    const shown = P.resolveDay(box.entries, [], iso, child, !!(holiday && holiday.free))
      .some((item) => item.state !== P.STATE_HIDDEN && item.entry.type !== P.TYPE_PAUSE);
    if (shown) found.push(day);
  }
  return found;
}

function planWeekDays(owner, monday) {
  const weekend = planWeekendEntries(owner, monday);
  return weekend.length ? Math.max(...weekend) + 1 : HOLIDAY_SCHOOL_DAYS;
}

function ownPlanLayout(data, owner, monday, blocked, periods, firstLine) {
  const P = periodRules();
  const school = connectionOfKey(owner);
  const box = school ? periodsData(school) : null;
  if (!periodsReady(box) || !box.entries.length) return null;
  const rows = P.gridRows(box.grid);
  const regular = P.regularPeriods(data.lessons);
  const child = P.rawChild(owner);
  const groups = new Map();
  const first = firstLine || 2;
  let any = false;
  for (let day = 0; day < blocked.length; day += 1) {
    const iso = isoDate(addDays(monday, day));
    const holiday = holidayDay(iso, school);
    const spans = blocked[day] ? [] : P.spansFor(rows, regular[iso] || []);
    for (const item of P.resolveDay(box.entries, spans, iso, child, !!(blocked[day] || (holiday && holiday.free)))) {
      if (item.state === P.STATE_HIDDEN) continue;
      if ((blocked[day] || day >= HOLIDAY_SCHOOL_DAYS) && item.entry.type === P.TYPE_PAUSE) continue;
      any = true;
      const kind = item.entry.type === P.TYPE_PAUSE ? "strip" : "own";
      const start = P.startOf(item.entry);
      const key = `${kind}:${start}`;
      if (!groups.has(key)) groups.set(key, { kind, start, cells: new Map() });
      const cells = groups.get(key).cells;
      if (!cells.has(day)) cells.set(day, item);
    }
  }
  if (!any) return null;
  const starts = new Map(rows.map((row) => [row.number, row.start]));
  const order = [];
  let previous = -1;
  for (const period of periods) {
    const known = starts.get(period);
    const key = known === undefined ? previous + 0.001 : known;
    previous = key;
    order.push({ kind: "lesson", period, key });
  }
  for (const group of groups.values()) order.push({ kind: group.kind, group, key: group.start });
  order.sort((a, b) => a.key - b.key || (a.kind === "lesson" ? -1 : b.kind === "lesson" ? 1 : 0));
  const rowOf = new Map();
  const nodes = [];
  order.forEach((item, index) => {
    const line = index + first;
    if (item.kind === "lesson") {
      rowOf.set(item.period, line);
      return;
    }
    nodes.push(...(item.kind === "strip" ? planStripNodes(school, item.group, line) : planOwnNodes(school, item.group, line, blocked)));
  });
  return { rowOf, nodes, total: order.length };
}

function planStripNodes(school, group, line) {
  const P = periodRules();
  const items = [...group.cells.values()];
  const names = [...new Set(items.map((item) => item.entry.name))];
  const cut = items.find((item) => item.state === P.STATE_CUT);
  const shown = cut || items[0];
  return [
    el("div", { class: "tt-stime", style: `grid-column:1;grid-row:${line}` }, clockLabel(group.start)),
    el("button", {
      class: cut ? "tt-strip cut" : "tt-strip",
      type: "button",
      style: `grid-column:2 / span ${HOLIDAY_SCHOOL_DAYS};grid-row:${line}`,
      "data-entry": shown.entry.id,
      onclick: () => openEntryDetail(school, shown.entry.id),
    }, [iservText("span", {}, [...names, durationLabel(shown.end - shown.start)].join(" · "))]),
  ];
}

function planOwnNodes(school, group, line, blocked) {
  const P = periodRules();
  const nodes = [el("div", { class: "tt-hour own", style: `grid-column:1;grid-row:${line}` }, [el("span", {}, clockLabel(group.start))])];
  for (let day = 0; day < blocked.length; day += 1) {
    const item = group.cells.get(day);
    const place = `grid-column:${day + 2};grid-row:${line}`;
    if (!item) {
      if (!blocked[day]) nodes.push(el("div", { class: "tt-void", style: place }));
      continue;
    }
    const classes = ["tt-own"];
    if (item.state === P.STATE_CUT) classes.push("cut");
    if (blocked[day]) classes.push("on-hol");
    nodes.push(el("button", {
      class: classes.join(" "),
      type: "button",
      style: place,
      "data-entry": item.entry.id,
      "aria-label": `${item.entry.name}, ${rangeLabel(item.start, item.end)}`,
      onclick: () => openEntryDetail(school, item.entry.id),
    }, [iservText("span", { class: "sub" }, item.entry.name), el("span", { class: "room" }, rangeLabel(item.start, item.end))]));
  }
  return nodes;
}

function planLegendItems(data, owner) {
  const school = connectionOfKey(owner);
  const box = school ? state.periods && state.periods[school] : null;
  if (!periodsReady(box) || !box.entries.length) return [];
  return [
    el("span", { class: "legend-item" }, [el("i", { class: "lg-strip" }), t("periods.legend.pause")]),
    el("span", { class: "legend-item" }, [el("i", { class: "lg-own" }), t("periods.legend.own")]),
  ];
}

function todayOwnItems(childKey, iso, week) {
  const P = periodRules();
  const school = connectionOfKey(childKey);
  const box = school ? periodsData(school) : null;
  if (!periodsReady(box) || !box.entries.length) return [];
  const holiday = holidayDay(iso, school);
  const periods = holidayQuietsLessons(holiday) ? [] : P.regularPeriods((week && week.lessons) || [])[iso] || [];
  const spans = P.spansFor(P.gridRows(box.grid), periods);
  return P.resolveDay(box.entries, spans, iso, P.rawChild(childKey), !!(holiday && holiday.free))
    .filter((item) => item.state !== P.STATE_HIDDEN && item.entry.type !== P.TYPE_PAUSE)
    .map((item) => Object.assign({ school }, item));
}

function todayOwnRow(item, minutesNow) {
  const past = item.end <= minutesNow;
  return el("button", {
    class: past ? "row own-today past" : "row own-today",
    type: "button",
    "data-entry": item.entry.id,
    onclick: () => openEntryDetail(item.school, item.entry.id),
  }, [
    el("span", { class: "row-dot" }, [el("i", { class: "ring" })]),
    el("span", { class: "row-main" }, [
      iservText("span", { class: "row-title" }, item.entry.name),
      el("span", { class: "row-sub" }, t("periods.today.until", { time: clockLabel(item.end) })),
    ]),
    el("span", { class: "row-side" }, [el("span", { class: "row-meta" }, clockLabel(item.start))]),
  ]);
}

function nextOwnAppointment(childKey, fromIso) {
  const P = periodRules();
  const school = connectionOfKey(childKey);
  const box = school ? periodsData(school) : null;
  if (!periodsReady(box) || !box.entries.length) return null;
  const rows = P.gridRows(box.grid);
  const days = P.profileDays(box.profiles, P.rawChild(childKey)) || {};
  for (let offset = 1; offset <= ENTRY_LOOKAHEAD_DAYS; offset += 1) {
    const iso = P.addDaysIso(fromIso, offset);
    const holiday = holidayDay(iso, school);
    const spans = holidayQuietsLessons(holiday) ? [] : P.spansFor(rows, days[P.weekdayOf(iso)] || []);
    const found = P.resolveDay(box.entries, spans, iso, P.rawChild(childKey), !!(holiday && holiday.free))
      .filter((item) => item.state !== P.STATE_HIDDEN && item.entry.type !== P.TYPE_PAUSE);
    if (found.length) return Object.assign({ school, iso, offset }, found[0]);
  }
  return null;
}

function nextOwnRow(next) {
  const day = parseIsoDay(next.iso);
  return el("button", {
    class: "row next-own",
    type: "button",
    "data-entry": next.entry.id,
    onclick: () => openEntryDetail(next.school, next.entry.id),
  }, [
    el("span", { class: "row-dot" }, [el("i", { class: "ring" })]),
    el("span", { class: "row-main" }, [
      el("span", { class: "overline" }, t("periods.today.next")),
      iservText("span", { class: "row-title" }, next.entry.name),
      el("span", { class: "row-sub" }, [isoLabel(next.iso), rangeLabel(next.start, next.end)].join(" · ")),
    ]),
    el("span", { class: "row-side" }, [el("span", { class: "row-meta" }, next.offset === 1 ? t("periods.today.tomorrow") : day ? formatWeekdayShort(day) : "")]),
  ]);
}

function todayOwnBlocks(childKey, iso, week) {
  const now = new Date();
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  return todayOwnItems(childKey, iso, week).map((item) => Object.assign(overviewBlock(`${childKey}:own:${item.entry.id}`, todayOwnRow(item, minutesNow)), { sortTime: item.start }));
}

function mergeByTime(lessons, own) {
  const merged = [];
  const waiting = own.slice().sort((a, b) => a.sortTime - b.sortTime);
  for (const block of lessons) {
    if (typeof block.sortTime === "number") {
      while (waiting.length && waiting[0].sortTime < block.sortTime) merged.push(waiting.shift());
    }
    merged.push(block);
  }
  return merged.concat(waiting);
}

function holidayQuietsLessons(holiday) {
  return !!(holiday && holiday.free && holiday.overrides_lessons);
}

function todayNextBlock(childKey, iso) {
  const next = nextOwnAppointment(childKey, iso);
  return next ? overviewBlock(`${childKey}:own-next`, nextOwnRow(next)) : null;
}
