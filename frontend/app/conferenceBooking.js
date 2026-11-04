const CONFERENCE_BOOKING_SEARCH_FROM = 8;
const CONFERENCE_BOOKING_OPEN = "open";
const CONFERENCE_BOOKING_BEFORE = "before";
const CONFERENCE_BOOKING_AFTER = "after";

function conferenceBookingDay(iso) {
  const date = parseAnyDate(iso);
  if (!date) return "";
  return t("conferences.booking.day", { weekday: formatWeekdayShort(date), date: formatShortDate(date) });
}

function conferenceBookingTime(item) {
  return t("conferences.booking.time", { begin: item.begin, end: item.end });
}

function conferenceBookingWhen(iso, item) {
  const day = conferenceBookingDay(iso);
  const time = item.begin ? conferenceBookingTime(item) : "";
  return day && time ? t("conferences.booking.when", { day, time }) : day || time;
}

function conferencePickedNames(booking, selected) {
  return booking.children.filter((child) => selected.has(child.id)).map((child) => child.name).join(", ");
}

function conferenceBookingOpen(booking) {
  const closed = booking.window.state === CONFERENCE_BOOKING_BEFORE || booking.window.state === CONFERENCE_BOOKING_AFTER;
  return !closed && booking.children.length > 0;
}

function conferenceBookingWindowNote(booking) {
  const { state: windowState, begin, end } = booking.window;
  const day = (iso) => {
    const date = parseAnyDate(iso);
    return date ? formatShortDate(date) : "";
  };
  if (windowState === CONFERENCE_BOOKING_OPEN) return end ? t("conferences.booking.window.open", { date: day(end) }) : "";
  if (windowState === CONFERENCE_BOOKING_BEFORE) return begin ? t("conferences.booking.window.before", { date: day(begin) }) : "";
  return windowState === CONFERENCE_BOOKING_AFTER ? t("conferences.booking.window.after") : "";
}

function conferenceSlotTaken(booking, host, slot) {
  return booking.taken.some((entry) => entry.slot === slot.id && entry.host === host.id);
}

function conferenceSlotMine(booking, host, slot) {
  return booking.mine.some((entry) => entry.slot === slot.id && entry.host === host.id);
}

function conferenceHostFree(booking, host) {
  return booking.days.reduce((count, day) => count + day.slots.filter((slot) => !slot.closed && !conferenceSlotTaken(booking, host, slot)).length, 0);
}

function conferenceBookedRow(entry, item) {
  const when = conferenceBookingWhen(item.date, item);
  const children = item.children.map((child) => child.name).filter(Boolean).join(", ");
  const main = el("div", { class: "row-main" }, [
    when ? el("div", { class: "row-title" }, when) : null,
    el("div", { class: "row-sub conference-lines" }, [item.teacher, item.location, children].filter(Boolean).map((text) => iservText("span", { class: "conference-line" }, text))),
  ]);
  if (item.editable) main.append(el("div", { class: "conference-row-actions" }, conferenceBookedActions(entry, item, when)));
  return el("div", { class: "row read conference-row" }, [el("span", { class: "row-dot" }), main]);
}

function conferenceBookedActions(entry, item, when) {
  const booking = entry.data.booking;
  const busy = entry.sending !== null ? "" : null;
  const buttons = [];
  if (booking.children.length > 1) {
    buttons.push(el("button", {
      class: "btn ghost slim",
      type: "button",
      disabled: busy,
      onclick: () => openSheet(() => conferenceChildSheet(entry, {
        title: t("conferences.booking.change"),
        lines: [item.teacher, when],
        action: "change",
        chosen: item.children.map((child) => child.id),
        values: { booking: item.id },
      })),
    }, t("conferences.booking.change")));
  }
  buttons.push(el("button", {
    class: "btn ghost slim",
    type: "button",
    disabled: busy,
    onclick: () => sendConferenceBooking(entry, "cancel", { booking: item.id }, [item.teacher, when]),
  }, t("conferences.booking.cancel")));
  return buttons;
}

function conferenceSlotButton(entry, host, day, slot) {
  const booking = entry.data.booking;
  const mine = conferenceSlotMine(booking, host, slot);
  const taken = !mine && conferenceSlotTaken(booking, host, slot);
  const free = !mine && !taken && !slot.closed && conferenceBookingOpen(booking) && entry.sending === null;
  const status = mine ? t("conferences.booking.booked") : taken ? t("conferences.booking.taken") : slot.closed ? t("conferences.booking.closed") : "";
  const classes = ["conference-slot"];
  if (mine) classes.push("is-mine");
  if (free) classes.push("is-free");
  return el("button", {
    class: classes.join(" "),
    type: "button",
    disabled: free ? null : "",
    onclick: free ? () => chooseConferenceSlot(entry, host, day, slot) : null,
  }, [
    el("span", { class: "conference-slot-time" }, conferenceBookingTime(slot)),
    status ? el("span", { class: "conference-slot-state" }, status) : null,
  ]);
}

function conferenceTeacherSheet(entry, host) {
  const booking = entry.data.booking;
  const nodes = [];
  if (host.location) nodes.push(iservText("p", { class: "conference-text muted" }, host.location));
  for (const day of booking.days) {
    nodes.push(el("div", { class: "section-head conference-head" }, [el("span", { class: "overline" }, conferenceBookingDay(day.date))]));
    nodes.push(el("div", { class: "conference-slots" }, day.slots.map((slot) => conferenceSlotButton(entry, host, day, slot))));
  }
  return sheet(host.name, nodes, []);
}

function chooseConferenceSlot(entry, host, day, slot) {
  const booking = entry.data.booking;
  const lines = [host.name, conferenceBookingWhen(day.date, slot)];
  const values = { slot: slot.id, host: host.id };
  if (booking.children.length === 1) {
    dropSheet();
    sendConferenceBooking(entry, "book", Object.assign(values, { children: [booking.children[0].id] }), lines.concat([booking.children[0].name]));
    return;
  }
  openSheet(() => conferenceChildSheet(entry, { title: t("conferences.booking.book"), lines, action: "book", chosen: [], values }));
}

function conferenceChildSheet(entry, choice) {
  const booking = entry.data.booking;
  if (!choice.selected) choice.selected = new Set(choice.chosen);
  const send = el("button", {
    class: "btn conference-submit",
    type: "button",
    disabled: choice.selected.size ? null : "",
    onclick: () => {
      const names = conferencePickedNames(booking, choice.selected);
      dropSheet();
      sendConferenceBooking(entry, choice.action, Object.assign({}, choice.values, { children: [...choice.selected] }), choice.lines.concat([names]));
    },
  }, choice.title);
  const boxes = booking.children.map((child) => {
    const box = el("input", { type: "checkbox" });
    box.checked = choice.selected.has(child.id);
    box.addEventListener("change", () => {
      if (box.checked) choice.selected.add(child.id);
      else choice.selected.delete(child.id);
      send.disabled = !choice.selected.size;
    });
    return el("label", { class: "cell check conference-choice" }, [box, iservText("span", {}, child.name)]);
  });
  const nodes = choice.lines.filter(Boolean).map((line) => iservText("p", { class: "conference-text" }, line));
  nodes.push(el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("conferences.booking.children")),
    el("div", { class: "field-group", role: "group", "aria-label": t("conferences.booking.children") }, boxes),
  ]));
  return sheet(choice.title, nodes, [el("div", { class: "btn-stack" }, [send])]);
}

function conferenceHostRow(entry, host) {
  const booking = entry.data.booking;
  const free = conferenceHostFree(booking, host);
  const count = free ? tCount("conferences.booking.free", free) : t("conferences.booking.none");
  const sub = [host.location, conferenceBookingOpen(booking) ? count : ""].filter(Boolean).join(" · ");
  return el("button", {
    class: "row read conference-row conference-host",
    type: "button",
    onclick: () => openSheet(() => conferenceTeacherSheet(entry, host)),
  }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, host.short ? t("conferences.booking.teacher", { name: host.name, short: host.short }) : host.name),
      iservText("div", { class: "row-sub" }, sub),
    ]),
    el("div", { class: "row-side" }, [el("span", { class: "ico-slot chev-next", html: iconSvg("chevron", 16) })]),
  ]);
}

function conferenceHostNodes(entry) {
  const hosts = entry.data.booking.hosts;
  if (!hosts.length) return [el("p", { class: "conference-text muted" }, t("conferences.booking.noHosts"))];
  const rows = (query) => {
    const wanted = query.trim().toLocaleLowerCase();
    return hosts.filter((host) => `${host.name} ${host.short}`.toLocaleLowerCase().includes(wanted)).map((host) => conferenceHostRow(entry, host));
  };
  const list = el("div", { class: "rows" }, rows(entry.bookingSearch || ""));
  if (hosts.length < CONFERENCE_BOOKING_SEARCH_FROM) return [list];
  const search = el("input", {
    class: "inp conference-search",
    type: "search",
    dir: "auto",
    placeholder: t("conferences.booking.search"),
    "aria-label": t("conferences.booking.search"),
  });
  search.value = entry.bookingSearch || "";
  search.addEventListener("input", () => {
    entry.bookingSearch = search.value;
    list.replaceChildren(...rows(search.value));
  });
  return [search, list];
}

function conferenceBookingNodes(entry) {
  const booking = entry.data.booking;
  const nodes = [];
  if (booking.description) nodes.push(iservText("p", { class: "conference-text" }, booking.description));
  const windowNote = conferenceBookingWindowNote(booking);
  if (windowNote) nodes.push(el("p", { class: "conference-text muted" }, windowNote));
  if (entry.sending !== null) nodes.push(el("div", { class: "note info", role: "status" }, [el("span", { class: "spin" }), el("span", {}, t("conferences.booking.sending"))]));
  if (booking.mine.length) {
    nodes.push(el("div", { class: "section-head conference-head" }, [el("span", { class: "overline" }, t("conferences.booking.mine"))]));
    nodes.push(el("div", { class: "rows" }, booking.mine.map((item) => conferenceBookedRow(entry, item))));
  }
  if (booking.profiles_missing) nodes.push(conferenceNoProfileNote());
  nodes.push(el("div", { class: "section-head conference-head" }, [el("span", { class: "overline" }, t("conferences.booking.choose"))]));
  nodes.push(...conferenceHostNodes(entry));
  return nodes;
}

function conferenceBookingConfirm(action, lines) {
  return confirmAction({
    title: t(`conferences.booking.confirm.${action}.title`),
    text: t(`conferences.booking.confirm.${action}.text`),
    quote: lines.filter(Boolean).join("\n"),
    confirmLabel: t(`conferences.booking.confirm.${action}.send`),
    destructive: action === "cancel",
  });
}

async function sendConferenceBooking(entry, action, values, lines) {
  if (entry.sending !== null) return;
  const ok = await conferenceBookingConfirm(action, lines);
  if (!ok) return;
  entry.sending = action;
  entry.outcome = null;
  rerender();
  let result = null;
  try {
    result = await postJson("api/conferences/booking", Object.assign({
      connection_id: entry.connection_id,
      page: entry.page,
      action,
      request_id: newConferenceRequestId(),
      confirmed: true,
    }, values), CONFERENCE_SUBMIT_TIMEOUT_MS);
  } catch (error) {
    entry.sending = null;
    if (handleApiFailure(error, entry.connection_id)) return;
    entry.outcome = { tone: "warn", text: t("api.conferences.submit.uncertain") };
    toast(entry.outcome.text, "bad");
    rerender();
    loadConferencePage(entry);
    return;
  }
  entry.sending = null;
  applyConferenceBookingResult(entry, result || {});
}

function applyConferenceBookingResult(entry, result) {
  entry.loadTicket = (entry.loadTicket || 0) + 1;
  if (result.page) {
    entry.data = result.page;
    if (result.page.page) entry.page = result.page.page;
  }
  const text = apiMessage(result, "api.conferences.submit.uncertain");
  const tone = result.ok ? "good" : result.state === "uncertain" ? "warn" : "bad";
  entry.outcome = { tone, text, details: result.ok ? [] : result.errors || [], diagnosis: result.ok ? null : result.diagnosis || null };
  toast(text, result.ok ? "good" : "bad");
  loadConferences(CONFERENCES_TAB_CURRENT);
  state._scrollTop = true;
  rerender();
  if (!result.page) loadConferencePage(entry);
}
