async function loadSchoolEvents() {
  const keep = !!(state.schoolEvents && !state.schoolEvents.error);
  const outcome = await reload("schoolEvents", () => getJson("api/school-events"), keep);
  if (!outcome) return;
  if (outcome.data) state.schoolEvents = outcome.data;
  else if (outcome.error) state.schoolEvents = { error: outcome.error };
  if (state.view === "overview" || state.view === "calendar") rerender();
}

function schoolEventRow(event) {
  const sub = schoolEventSub(event);
  const tag = schoolTag(event);
  return el("div", { class: "row read event-row" }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      tag ? el("div", { class: "row-tags" }, [tag]) : null,
      iservText("div", { class: "row-title" }, event.title || t("schoolEvents.untitled")),
      el("div", { class: "row-sub event-time" }, schoolEventTimeText(event)),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
  ]);
}

function schoolEventsView() {
  const view = el("div", {});
  const data = state.schoolEvents;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const events = upcomingSchoolEvents();
  if (data.error || listUnknown(data, events.length)) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("schoolEvents.error.title"), t("schoolEvents.error.text"), retryButton(() => { state.schoolEvents = null; rerender(); loadSchoolEvents(); })));
    return view;
  }
  const note = refreshFailureNote("schoolEvents");
  if (note) view.append(note);
  if (!events.length) {
    view.append(emptyBlock("upcoming", t("schoolEvents.empty.title"), t("schoolEvents.empty.text")));
    return view;
  }
  const days = [];
  for (const event of events) {
    const day = schoolEventDay(event);
    const last = days[days.length - 1];
    if (last && last.day === day) last.events.push(event);
    else days.push({ day, events: [event] });
  }
  for (const group of days) {
    view.append(el("section", { class: "event-day" }, [
      el("div", { class: "section-head" }, [el("span", { class: "overline" }, schoolEventDayHeading(group.day))]),
      el("div", { class: "rows" }, group.events.map(schoolEventRow)),
    ]));
  }
  return view;
}

function schoolEventDayHeading(day) {
  const date = parseIsoDay(day);
  return date ? dateFormatter({ weekday: "long", day: "numeric", month: "long" }).format(date) : day;
}

function schoolEventDay(event) {
  if (event.all_day) return parseIsoDay(event.start) ? String(event.start).slice(0, 10) : "";
  const moment = new Date(event.start);
  return Number.isNaN(moment.getTime()) ? "" : isoDate(moment);
}

function schoolEventLastDay(event) {
  const first = schoolEventDay(event);
  if (!event.all_day) return first;
  const end = parseIsoDay(event.end);
  if (!end) return first;
  const last = isoDate(addDays(end, -1));
  return last > first ? last : first;
}

function schoolEventEnded(event, now) {
  if (event.all_day) return schoolEventLastDay(event) < isoDate(now);
  const end = new Date(event.end || event.start);
  return !Number.isNaN(end.getTime()) && end.getTime() < now.getTime();
}

function upcomingSchoolEvents() {
  const list = state.schoolEvents && Array.isArray(state.schoolEvents.events) ? state.schoolEvents.events : [];
  const now = new Date();
  return list
    .filter((event) => event && schoolEventDay(event) && !schoolEventEnded(event, now))
    .sort((left, right) => schoolEventDay(left).localeCompare(schoolEventDay(right)) || String(left.start).localeCompare(String(right.start)));
}

const SCHOOL_EVENT_TIME = { hour: "2-digit", minute: "2-digit" };
const SCHOOL_EVENT_DATE_TIME = { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" };

function schoolEventTimeText(event) {
  if (event.all_day) {
    const last = schoolEventLastDay(event);
    return last > schoolEventDay(event) ? t("schoolEvents.allDay.until", { date: dateLabel(last) }) : t("schoolEvents.allDay");
  }
  const from = new Date(event.start);
  const to = event.end ? new Date(event.end) : null;
  if (!to || Number.isNaN(to.getTime()) || to.getTime() === from.getTime()) return formatTime(from);
  const sameDay = isoDate(from) === isoDate(to);
  const parts = sameDay ? SCHOOL_EVENT_TIME : SCHOOL_EVENT_DATE_TIME;
  return dateFormatter(parts).formatRange(from, to);
}

function schoolEventSub(event) {
  return [event.location, event.calendar].map((part) => String(part || "").trim()).filter(Boolean).join(" · ");
}
