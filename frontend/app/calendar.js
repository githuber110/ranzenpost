const CALENDAR_COMPONENT_TIMETABLE = "timetable";
const CALENDAR_COMPONENT_SCHOOL_HOLIDAYS = "school_holidays";
const CALENDAR_COMPONENT_PUBLIC_HOLIDAYS = "public_holidays";
const CALENDAR_COMPONENT_MARKS = "marks";
const CALENDAR_COMPONENT_ABSENCES = "absences";
const CALENDAR_COMPONENT_OWN_ENTRIES = "own_entries";
const CALENDAR_COMPONENT_SCHOOL_EVENTS = "school_events";
const CALENDAR_SCHOOL_COMPONENTS = [
  CALENDAR_COMPONENT_SCHOOL_HOLIDAYS,
  CALENDAR_COMPONENT_PUBLIC_HOLIDAYS,
  CALENDAR_COMPONENT_SCHOOL_EVENTS,
];
const CALENDAR_COMPONENTS = [
  CALENDAR_COMPONENT_TIMETABLE,
  CALENDAR_COMPONENT_SCHOOL_HOLIDAYS,
  CALENDAR_COMPONENT_PUBLIC_HOLIDAYS,
  CALENDAR_COMPONENT_MARKS,
  CALENDAR_COMPONENT_ABSENCES,
  CALENDAR_COMPONENT_OWN_ENTRIES,
  CALENDAR_COMPONENT_SCHOOL_EVENTS,
];
const CALENDAR_DEFAULT_COLOR = "#135859";
const CALENDAR_DEFAULT_PORT = 8100;
const CALENDAR_MAX_LABEL_LENGTH = 60;
const CALENDAR_HOST_KEY = "calendarHost";
const CALENDAR_PORT_BUSY = "port";
const CALENDAR_RESUME_KEY = "calendarResumeSheet";
const CALENDAR_HOST_FALLBACK = "fallback";
const CALENDAR_RESTART_GRACE_MS = 3000;
const CALENDAR_RESTART_POLL_MS = 1000;
const CALENDAR_RESTART_MAX_TRIES = 40;
const CALENDAR_REMOTE_SUFFIX = ".ui.nabu.casa";
const CALENDAR_LOCAL_HOSTS = ["localhost", "127.0.0.1", "::1"];
const CALENDAR_SCHEME_WEB = "webcal";
const CALENDAR_SCHEME_PLAIN = "http";

function calendarIsRemoteSession() {
  return String(window.location.hostname || "").toLowerCase().endsWith(CALENDAR_REMOTE_SUFFIX);
}

function calendarDetectedHost() {
  const host = String(window.location.hostname || "");
  if (!host || CALENDAR_LOCAL_HOSTS.includes(host.toLowerCase())) return "";
  return calendarIsRemoteSession() ? "" : host;
}

function sanitizeCalendarHost(value) {
  let host = String(value || "").trim();
  if (!host) return "";
  const schemeEnd = host.indexOf("://");
  if (schemeEnd > 0) host = host.slice(schemeEnd + 3);
  host = host.split("/")[0].split("?")[0].split("#")[0];
  if (host.startsWith("[")) {
    const closing = host.indexOf("]");
    if (closing < 0) return "";
    host = host.slice(1, closing);
  } else if (host.split(":").length === 2) {
    host = host.split(":")[0];
  }
  return host.replace(/\.+$/, "").trim().toLowerCase();
}

function calendarHost() {
  const data = calendarData();
  const resolved = data ? sanitizeCalendarHost(data.host) : "";
  const stored = sanitizeCalendarHost(readStoredText(CALENDAR_HOST_KEY));
  if (data && data.host_source === CALENDAR_HOST_FALLBACK) {
    return calendarDetectedHost() || stored || resolved;
  }
  return resolved || calendarDetectedHost() || stored;
}

function calendarFetchText(subscription) {
  const stamp = Number(subscription && subscription.last_fetched_at) || 0;
  if (stamp > 0) return t("calendar.subscribe.fetched", { date: formatEpoch(stamp), when: relativeSince(stamp) });
  const since = Number(subscription && (subscription.watched_since || subscription.created_at)) || 0;
  if (since > 0) return t("calendar.subscribe.fetched.since", { date: formatEpoch(since) });
  return t("calendar.subscribe.fetched.never");
}

function calendarFetchLine(subscription) {
  return el("p", { class: "cal-hint cal-fetched" }, calendarFetchText(subscription));
}

function calendarHostForUrl(host) {
  return String(host || "").includes(":") ? `[${host}]` : host;
}

function calendarData() {
  return (state.calendar && state.calendar.data) || null;
}

function calendarPort() {
  const data = calendarData();
  const port = data ? Number(data.port) : 0;
  return Number.isInteger(port) && port > 0 ? port : CALENDAR_DEFAULT_PORT;
}

function calendarRegionSet(schoolId) {
  const data = calendarData();
  const regions = data && data.holiday_regions && typeof data.holiday_regions === "object" ? data.holiday_regions : {};
  const id = schoolId || currentConnectionId();
  if (id && Object.prototype.hasOwnProperty.call(regions, id)) return !!regions[id];
  return Object.values(regions).some(Boolean);
}

function calendarSchoolEventsOn(schoolId) {
  const data = calendarData();
  const offered = data && data.school_events && typeof data.school_events === "object" ? data.school_events : {};
  return !!schoolId && offered[schoolId] === true && !moduleDisabled("calendar");
}

function calendarDraftSchool(draft) {
  return draft.schoolId || connectionOfKey(draft.childId);
}

function calendarDraftKey(draft) {
  return draft.childId || `school-${draft.schoolId}`;
}

function calendarFeedUrl(subscription, scheme) {
  const host = calendarHost();
  const path = (subscription && subscription.path) || "";
  if (!host || !path) return "";
  return `${scheme}://${calendarHostForUrl(host)}:${calendarPort()}${path}`;
}

async function loadCalendarSubscriptions() {
  try {
    const data = await getJson("api/calendar/subscriptions");
    const valid = data && typeof data === "object" && Array.isArray(data.subscriptions);
    state.calendar = { data: valid ? data : null, error: !valid };
  } catch (error) {
    state.calendar = { data: null, error: true };
  }
}

function calendarRequest(path, options) {
  return requestJson(path, options, "calendar.subscribe.failed");
}

function calendarPostRequest(path, body) {
  return calendarRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

function calendarSubscriptionPath(subscription, suffix) {
  return `api/calendar/subscriptions/${encodeURIComponent(subscription.id)}${suffix || ""}`;
}

async function openCalendarPage() {
  state.calendarFrom = state.view;
  state.calendar = null;
  state.calendarDraft = null;
  state.calendarQr = "";
  state.calendarBusy = "";
  state.calendarPortRestart = false;
  state.calendarRestarting = false;
  openSettingsPage(SETTINGS_PAGE_CALENDAR);
  await loadCalendarSubscriptions();
  if (calendarPageOpen()) rerender();
  watchCalendarPending();
}

function calendarPageOpen() {
  return state.view === "settings" && state.settingsPage === SETTINGS_PAGE_CALENDAR;
}

function closeCalendarPage() {
  const from = state.calendarFrom;
  state.calendarFrom = null;
  state.calendarDraft = null;
  state.calendarQr = "";
  if (from && from !== "settings" && viewAvailable(from)) {
    state.settingsPage = null;
    dropSheet();
    setView(from);
    return;
  }
  closeSettingsPage();
}

function calendarPageView() {
  const body = [noteBlock(t("calendar.subscribe.warning"))];
  const loaded = state.calendar;
  if (!loaded) body.push(loadingBlock());
  else if (loaded.error || !loaded.data) body.push(plainCard(t("calendar.subscribe.loadFailed")));
  else {
    const notice = calendarPortNotice(loaded.data);
    if (notice) body.push(notice);
    for (const node of calendarCards(loaded.data)) body.push(node);
  }
  return el("div", { class: "calendar-page" }, body);
}

function calendarRestartPanel() {
  if (state.calendarRestarting) {
    return el("div", { class: "cal-port cal-restart" }, [
      el("div", { class: "note" }, [
        el("span", { class: "spin" }),
        el("span", {}, t("calendar.subscribe.restart.running")),
      ]),
    ]);
  }
  return el("div", { class: "cal-port cal-restart" }, [
    el("p", { class: "cal-hint" }, t("calendar.subscribe.restart.hint")),
    el("button", {
      class: "btn cal-restart-go",
      type: "button",
      onclick: restartAddon,
    }, t("calendar.subscribe.restart.action")),
  ]);
}

let restartWatchToken = 0;

async function restartAddon() {
  if (state.calendarRestarting) return;
  state.calendarRestarting = true;
  writeStoredText(CALENDAR_RESUME_KEY, "1");
  restartWatchToken += 1;
  const token = restartWatchToken;
  rerender();
  awaitAddonReturn(0, token, false);
  let result = null;
  try {
    result = await postJson("api/calendar/restart", {});
  } catch (error) {
    return;
  }
  if (result && result.ok === false) abortAddonRestart(token, result);
}

function abortAddonRestart(token, result) {
  if (token !== restartWatchToken) return;
  restartWatchToken += 1;
  state.calendarRestarting = false;
  writeStoredText(CALENDAR_RESUME_KEY, "");
  rerender();
  toast(apiMessage(result, "api.calendar.error.restartFailed"), "bad");
}

function awaitAddonReturn(attempt, token, seenDown) {
  if (token !== restartWatchToken) return;
  if (attempt >= CALENDAR_RESTART_MAX_TRIES) {
    window.location.reload();
    return;
  }
  window.setTimeout(async () => {
    if (token !== restartWatchToken) return;
    let up = false;
    try {
      await getJson("api/health");
      up = true;
    } catch (error) {
      up = false;
    }
    if (token !== restartWatchToken) return;
    if (up && seenDown) {
      window.location.reload();
      return;
    }
    awaitAddonReturn(attempt + 1, token, seenDown || !up);
  }, attempt === 0 ? CALENDAR_RESTART_GRACE_MS : CALENDAR_RESTART_POLL_MS);
}

function resumeCalendarPage() {
  if (readStoredText(CALENDAR_RESUME_KEY) !== "1") return;
  writeStoredText(CALENDAR_RESUME_KEY, "");
  openCalendarPage();
}

function calendarPortNotice(data) {
  if (data.restart_pending || state.calendarPortRestart) return calendarRestartPanel();
  if (data.port_open) return null;
  if (!(data.subscriptions || []).some((entry) => !entry.online)) return null;
  if (!data.supervisor) return el("p", { class: "cal-hint" }, t("calendar.subscribe.port.manual", { port: String(calendarPort()) }));
  const busy = state.calendarBusy === CALENDAR_PORT_BUSY;
  const button = el("button", {
    class: "btn ghost slim cal-port-open",
    type: "button",
    disabled: busy ? "disabled" : null,
    onclick: openCalendarPort,
  }, busy ? [el("span", { class: "spin" }), t("calendar.subscribe.port.open")] : [t("calendar.subscribe.port.open")]);
  return el("div", { class: "cal-port" }, [
    el("p", { class: "cal-hint" }, t("calendar.subscribe.port.closed")),
    button,
  ]);
}

async function openCalendarPort() {
  if (state.calendarBusy) return;
  state.calendarBusy = CALENDAR_PORT_BUSY;
  rerender();
  let result = null;
  try {
    result = await postJson("api/calendar/port", {});
  } catch (error) {
    result = null;
  }
  state.calendarBusy = "";
  if (result && result.ok) {
    state.calendarPortRestart = !!result.restart_required;
    await loadCalendarSubscriptions();
    rerender();
    return;
  }
  rerender();
  toast(apiMessage(result, "api.calendar.error.portFailed"), "bad");
}

function calendarCards(data) {
  const subscriptions = Array.isArray(data.subscriptions) ? data.subscriptions : [];
  const cards = state.children.map((child) => {
    const found = subscriptions.find((entry) => entry.child_key === child.key) || null;
    return calendarChildCard(child, found);
  });
  for (const school of readySchools()) {
    const found = subscriptions.find((entry) => !entry.child_key && entry.school_id === school.id) || null;
    if (found || calendarSchoolWithoutChild(school.id)) cards.push(calendarSchoolCard(school.id, found));
  }
  return cards.length ? cards : [plainCard(t("overview.noChild"))];
}

function calendarSchoolWithoutChild(schoolId) {
  if (state.childrenRead !== true || state.childrenFailure) return false;
  return !state.children.some((child) => schoolOfChild(child) === schoolId);
}

function calendarSchoolName(schoolId) {
  return t("calendar.name", { name: schoolFullName(schoolId) });
}

function calendarSchoolCard(schoolId, subscription) {
  const card = el("div", { class: "cal-card cal-school-card" });
  card.append(iservText("span", { class: "overline" }, t("calendar.subscribe.forSchool", { name: schoolFullName(schoolId) })));
  card.append(el("p", { class: "cal-hint" }, t("calendar.subscribe.school.hint")));
  const draft = state.calendarDraft;
  if (draft && !draft.childId && draft.schoolId === schoolId) {
    card.append(calendarForm(draft));
    return card;
  }
  if (!subscription) {
    card.append(
      el("button", {
        class: "btn",
        type: "button",
        onclick: () => { state.calendarDraft = calendarSchoolDraft(schoolId); rerender(); },
      }, [icon("calendarAdd", 18), t("calendar.subscribe.create")])
    );
    return card;
  }
  for (const node of calendarSubscriptionBlock(subscription, null)) card.append(node);
  return card;
}

function calendarHolidayComponentChosen(draft) {
  return draft.components.includes(CALENDAR_COMPONENT_SCHOOL_HOLIDAYS) || draft.components.includes(CALENDAR_COMPONENT_PUBLIC_HOLIDAYS);
}

function calendarSchoolDraft(schoolId) {
  return {
    id: "",
    childId: "",
    schoolId,
    components: [CALENDAR_COMPONENT_SCHOOL_HOLIDAYS].concat(calendarSchoolEventsOn(schoolId) ? [CALENDAR_COMPONENT_SCHOOL_EVENTS] : []),
    label: "",
    placeholder: calendarSchoolName(schoolId),
    color: CALENDAR_DEFAULT_COLOR,
    online: false,
    error: "",
    busy: false,
  };
}

function calendarChildCard(child, subscription) {
  const card = el("div", { class: "cal-card" });
  card.append(iservText("span", { class: "overline" }, t("calendar.subscribe.forChild", { name: childChipLabel(child) })));
  const draft = state.calendarDraft;
  if (draft && draft.childId === child.key) {
    card.append(calendarForm(draft));
    return card;
  }
  if (!subscription) {
    card.append(
      el("button", {
        class: "btn",
        type: "button",
        onclick: () => { state.calendarDraft = calendarNewDraft(child); rerender(); },
      }, [icon("calendarAdd", 18), t("calendar.subscribe.create")])
    );
    return card;
  }
  for (const node of calendarSubscriptionBlock(subscription, child)) card.append(node);
  return card;
}

function calendarDefaultName(child) {
  const first = firstName(child && child.name);
  return first ? t("calendar.name", { name: first }) : t("calendar.name.fallback");
}

function calendarPlaceholderName(subscription, child) {
  return subscription.child_key ? calendarDefaultName(child) : calendarSchoolName(subscription.school_id);
}

function calendarSubscriptionName(subscription, child) {
  return subscription.label || calendarPlaceholderName(subscription, child);
}

function calendarNewDraft(child) {
  return {
    id: "",
    childId: child.key,
    components: [calendarRegionSet() ? CALENDAR_COMPONENT_TIMETABLE : CALENDAR_COMPONENT_SCHOOL_HOLIDAYS].concat(moduleOn("timetable") ? [CALENDAR_COMPONENT_OWN_ENTRIES] : []),
    label: "",
    placeholder: calendarDefaultName(child),
    color: CALENDAR_DEFAULT_COLOR,
    online: false,
    error: "",
    busy: false,
  };
}

function calendarEditDraft(subscription, child) {
  return {
    id: subscription.id,
    childId: subscription.child_key,
    schoolId: subscription.child_key ? "" : subscription.school_id || "",
    components: (subscription.components || []).slice(),
    label: subscription.label || "",
    placeholder: calendarPlaceholderName(subscription, child),
    color: subscription.color || CALENDAR_DEFAULT_COLOR,
    online: !!subscription.online,
    wasOnline: !!subscription.online,
    error: "",
    busy: false,
  };
}

const CALENDAR_INTERNET_READY = "ready";
const CALENDAR_INTERNET_CHECKING = "checking";
const CALENDAR_INTERNET_REASONS = {
  checking: "calendar.subscribe.variant.internet.checking",
  no_integration: "calendar.subscribe.variant.internet.noIntegration",
  update_integration: "calendar.subscribe.variant.internet.update",
  no_access: "calendar.subscribe.variant.internet.noAccess",
};

function calendarInternetReason() {
  const data = calendarData();
  const access = data && data.internet;
  if (access === CALENDAR_INTERNET_READY) return "";
  return CALENDAR_INTERNET_REASONS[access] || CALENDAR_INTERNET_REASONS.no_integration;
}

function calendarVariantOption(draft, online, refresh) {
  const reason = online && !draft.wasOnline ? calendarInternetReason() : "";
  const input = el("input", { type: "radio", name: `cal-variant-${calendarDraftKey(draft)}`, value: online ? "internet" : "local" });
  input.checked = draft.online === online;
  if (reason) input.disabled = true;
  input.addEventListener("change", () => {
    if (!input.checked) return;
    draft.online = online;
    refresh();
  });
  const key = online ? "internet" : "local";
  const reasonId = `cal-variant-reason-${calendarDraftKey(draft)}`;
  if (reason) input.setAttribute("aria-describedby", reasonId);
  return el("label", { class: reason ? "cell check cal-variant cal-variant-off" : "cell check cal-variant" }, [
    input,
    el("span", {}, [
      el("span", { class: "cal-variant-name" }, t(`calendar.subscribe.variant.${key}`)),
      el("small", { class: "cal-variant-hint" }, t(`calendar.subscribe.variant.${key}.hint`)),
      reason ? el("small", { class: "cal-variant-reason", id: reasonId }, t(reason)) : null,
    ]),
  ]);
}

function calendarVariantField(draft, refresh) {
  if (draft.online && !draft.wasOnline && calendarInternetReason()) draft.online = false;
  return el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("calendar.subscribe.variant")),
    el("div", { class: "field-group", role: "radiogroup", "aria-label": t("calendar.subscribe.variant") }, [
      calendarVariantOption(draft, false, refresh),
      calendarVariantOption(draft, true, refresh),
    ]),
  ]);
}

function calendarComponents(draft) {
  const school = calendarDraftSchool(draft);
  const offered = draft.childId ? CALENDAR_COMPONENTS : CALENDAR_SCHOOL_COMPONENTS;
  return offered.filter((component) => {
    if (component === CALENDAR_COMPONENT_SCHOOL_EVENTS) return calendarSchoolEventsOn(school) || draft.components.includes(component);
    if (component === CALENDAR_COMPONENT_ABSENCES) return moduleOn("absences");
    if (component === CALENDAR_COMPONENT_MARKS || component === CALENDAR_COMPONENT_TIMETABLE || component === CALENDAR_COMPONENT_OWN_ENTRIES) return moduleOn("timetable");
    return true;
  });
}

function calendarComponentRow(draft, component, refresh) {
  const locked = component === CALENDAR_COMPONENT_TIMETABLE && !calendarRegionSet();
  const input = el("input", { type: "checkbox" });
  input.checked = draft.components.includes(component);
  if (locked) input.disabled = true;
  input.addEventListener("change", () => {
    const picked = draft.components.filter((name) => name !== component);
    if (input.checked) picked.push(component);
    draft.components = CALENDAR_COMPONENTS.filter((name) => picked.includes(name));
    draft.error = "";
    refresh();
  });
  return el("label", { class: locked ? "cell check cal-locked" : "cell check" }, [
    input,
    el("span", {}, [
      t(`calendar.subscribe.component.${component}`),
      el("small", {}, t(`calendar.subscribe.component.${component}.hint`)),
    ]),
  ]);
}

function calendarLabelField(draft) {
  const input = el("input", {
    class: "inp",
    type: "text",
    value: draft.label,
    placeholder: draft.placeholder,
    autocomplete: "off",
    maxlength: String(CALENDAR_MAX_LABEL_LENGTH),
    "aria-label": t("calendar.subscribe.label"),
  });
  input.addEventListener("input", () => { draft.label = input.value; });
  return el("label", { class: "field" }, [
    el("span", { class: "lbl" }, t("calendar.subscribe.label")),
    input,
    el("span", { class: "hint" }, t("calendar.subscribe.label.hint", { name: draft.placeholder })),
  ]);
}

function calendarColorField(draft, refresh) {
  const swatches = CALENDAR_COLORS.map((color) => {
    const dot = el("span", { class: "cal-swatch-dot" });
    dot.style.background = color;
    return el("button", {
      class: "cal-swatch",
      type: "button",
      "aria-label": color,
      "data-color": color,
      "aria-pressed": String(draft.color === color),
      onclick: () => { draft.color = color; refresh(); },
    }, [dot]);
  });
  return el("div", { class: "field" }, [
    el("span", { class: "lbl" }, t("calendar.subscribe.color")),
    el("div", { class: "cal-swatches" }, swatches),
    el("span", { class: "hint" }, t("calendar.subscribe.color.hint")),
  ]);
}

function calendarMoreOptions(draft, refresh) {
  const details = el("details", { class: "help-details cal-more" }, [
    el("summary", { class: "help-details-summary" }, t("calendar.subscribe.more")),
    calendarLabelField(draft),
    calendarColorField(draft, refresh),
  ]);
  details.open = !!draft.moreOpen;
  details.addEventListener("toggle", () => { draft.moreOpen = details.open; });
  return details;
}

function calendarForm(draft) {
  const wrap = el("div", { class: "cal-form" });
  const problem = el("span", { class: "cal-error" });
  const submit = el("button", { class: "btn", type: "button" });
  const refresh = () => calendarFormRefresh(draft, wrap, problem, submit);
  wrap.append(el("span", { class: "lbl cal-form-lbl" }, t("calendar.subscribe.components")));
  wrap.append(el("div", { class: "field-group" }, calendarComponents(draft).map((component) => calendarComponentRow(draft, component, refresh))));
  if (draft.childId && !calendarRegionSet()) {
    wrap.append(el("p", { class: "cal-hint" }, t("calendar.subscribe.region.locked")));
    wrap.append(el("button", { class: "btn ghost slim", type: "button", onclick: openCalendarRegionSetting }, t("calendar.subscribe.region.open")));
  } else if (!draft.childId && calendarHolidayComponentChosen(draft) && !calendarRegionSet(draft.schoolId)) {
    wrap.append(el("p", { class: "cal-hint" }, t("calendar.subscribe.school.region")));
    wrap.append(el("button", { class: "btn ghost slim", type: "button", onclick: openCalendarRegionSetting }, t("calendar.subscribe.region.open")));
  }
  wrap.append(problem);
  wrap.append(calendarVariantField(draft, refresh));
  wrap.append(calendarMoreOptions(draft, refresh));
  submit.addEventListener("click", () => submitCalendarDraft(draft));
  wrap.append(el("div", { class: "btn-stack" }, [
    submit,
    el("button", {
      class: "btn ghost",
      type: "button",
      disabled: draft.busy ? "disabled" : null,
      onclick: () => { state.calendarDraft = null; rerender(); },
    }, t("common.cancel")),
  ]));
  refresh();
  return wrap;
}

function calendarFormRefresh(draft, wrap, problem, submit) {
  const empty = !draft.components.length;
  const message = draft.error || (empty ? t("api.calendar.error.components") : "");
  problem.textContent = message;
  problem.hidden = !message;
  submit.disabled = draft.busy || empty;
  submit.setAttribute("aria-disabled", String(draft.busy || empty));
  submit.replaceChildren(
    ...(draft.busy
      ? [el("span", { class: "spin" }), document.createTextNode(t("common.saving"))]
      : [document.createTextNode(t(draft.id ? "common.save" : "calendar.subscribe.create"))])
  );
  for (const swatch of wrap.querySelectorAll(".cal-swatch")) {
    swatch.setAttribute("aria-pressed", String(swatch.getAttribute("data-color") === draft.color));
  }
}

function openCalendarRegionSetting() {
  state.calendarDraft = null;
  state.calendarFrom = null;
  if (state.view !== "settings") {
    state.settingsReturn = state.view;
    setView("settings");
  }
  state.settingsPage = null;
  state._scrollTop = true;
  openSheet(holidayRegionSheet);
}

async function submitCalendarDraft(draft) {
  if (draft.busy) return;
  if (!draft.components.length) {
    draft.error = t("api.calendar.error.components");
    rerender();
    return;
  }
  draft.busy = true;
  draft.error = "";
  rerender();
  const payload = {
    ...(draft.childId ? { child_key: draft.childId } : { school_id: draft.schoolId }),
    components: draft.components,
    label: draft.label,
    color: draft.color,
    online: !!draft.online,
  };
  const result = draft.id
    ? await calendarPostRequest(`api/calendar/subscriptions/${encodeURIComponent(draft.id)}`, payload)
    : await calendarPostRequest("api/calendar/subscriptions", payload);
  draft.busy = false;
  if (!result.ok) {
    draft.error = result.message;
    rerender();
    return;
  }
  const wasUpdate = !!draft.id;
  state.calendarDraft = null;
  await loadCalendarSubscriptions();
  rerender();
  toast(t(wasUpdate ? "common.saved" : "calendar.subscribe.created"));
  if (!draft.online && (!wasUpdate || draft.wasOnline)) await autoOpenCalendarPort();
  watchCalendarPending();
}

const CALENDAR_PENDING_POLL_MS = 10000;
const CALENDAR_PENDING_MAX_POLLS = 30;
let calendarPendingWatch = 0;

function calendarHasPending() {
  const data = calendarData();
  if (!data) return false;
  if (data.internet === CALENDAR_INTERNET_CHECKING) return true;
  return (data.subscriptions || []).some((entry) => entry.online && calendarOnlineStatus(entry) === CALENDAR_ONLINE_PENDING);
}

function watchCalendarPending(round = 0) {
  calendarPendingWatch += 1;
  const watch = calendarPendingWatch;
  if (!calendarHasPending() || round >= CALENDAR_PENDING_MAX_POLLS) return;
  window.setTimeout(async () => {
    if (watch !== calendarPendingWatch || !calendarPageOpen()) return;
    await refreshCalendarPending();
    if (watch !== calendarPendingWatch || !calendarPageOpen()) return;
    watchCalendarPending(round + 1);
  }, CALENDAR_PENDING_POLL_MS);
}

async function refreshCalendarPending() {
  let fresh = null;
  try {
    fresh = await getJson("api/calendar/subscriptions");
  } catch (error) {
    return false;
  }
  const current = calendarData();
  if (!current || !fresh || typeof fresh !== "object" || !Array.isArray(fresh.subscriptions)) return false;
  if (JSON.stringify(current) === JSON.stringify(fresh)) return false;
  const accessChanged = current.internet !== fresh.internet;
  state.calendar = { data: fresh, error: false };
  if ((!state.calendarDraft || accessChanged) && !state.sheet) rerender();
  return true;
}

async function autoOpenCalendarPort() {
  const data = calendarData();
  if (!data || data.port_open || !data.supervisor) return;
  await openCalendarPort();
}

function calendarSubscriptionBlock(subscription, child) {
  const nodes = [];
  const dot = el("span", { class: "cal-dot" });
  dot.style.background = subscription.color || CALENDAR_DEFAULT_COLOR;
  nodes.push(el("div", { class: "cal-name-row" }, [
    dot,
    el("b", { class: "cal-name" }, calendarSubscriptionName(subscription, child)),
    el("span", { class: "tag cal-variant-tag" }, t(subscription.online ? "calendar.subscribe.variant.internet" : "calendar.subscribe.variant.local")),
    calendarMenuButton(subscription, child),
  ]));
  const parts = (subscription.components || []).map((component) =>
    el("span", { class: "tag" }, t(`calendar.subscribe.component.${component}`))
  );
  if (parts.length) nodes.push(el("div", { class: "cal-parts" }, parts));
  for (const node of calendarActions(subscription)) nodes.push(node);
  return nodes;
}

const CALENDAR_HANDOFF_VERDICT_MS = 2000;

function handOffCalendarUrl(feedUrl) {
  try {
    const link = el("a", { href: feedUrl, rel: "noopener" });
    document.body.append(link);
    link.click();
    link.remove();
    return true;
  } catch (error) {
    toast(t("calendar.subscribe.add.failed"), "bad");
    return false;
  }
}

function pageStillHasTheUser() {
  if (document.hidden) return false;
  return typeof document.hasFocus !== "function" || document.hasFocus();
}

function watchCalendarHandOff(subscription) {
  window.setTimeout(() => {
    if (!pageStillHasTheUser()) return;
    state.calendarHandOffStalled = subscription.id;
    rerender();
  }, CALENDAR_HANDOFF_VERDICT_MS);
}

function subscribeToCalendar(subscription, feedUrl) {
  state.calendarHandOffStalled = null;
  if (!handOffCalendarUrl(feedUrl)) return;
  watchCalendarHandOff(subscription);
}

const CALENDAR_SUBSCRIBE_QUERY = "subscribe=1";

function calendarSubscribeUrl(plainUrl) {
  return plainUrl ? `${plainUrl}?${CALENDAR_SUBSCRIBE_QUERY}` : "";
}

function openCalendarInBrowser(subscription, url) {
  state.calendarHandOffStalled = null;
  try {
    const link = el("a", { href: url, target: "_blank", rel: "noopener" });
    document.body.append(link);
    link.click();
    link.remove();
  } catch (error) {
    toast(t("calendar.subscribe.add.failed"), "bad");
    return;
  }
  watchCalendarHandOff(subscription);
}

function calendarBrowserButton(subscription, url) {
  return el("button", {
    class: "btn cal-add cal-open-browser",
    type: "button",
    onclick: () => openCalendarInBrowser(subscription, url),
  }, [icon("calendarAdd", 18), t("calendar.subscribe.add")]);
}

function calendarHandOffStalledBlock() {
  return el("div", { class: "cal-webview cal-stalled" }, [
    el("span", { class: "overline" }, t("calendar.subscribe.add.stalled.title")),
    el("p", { class: "cal-hint" }, t("calendar.subscribe.add.stalled.text")),
  ]);
}

function calendarAddButton(subscription, feedUrl) {
  return el("button", {
    class: "btn cal-add",
    type: "button",
    onclick: () => subscribeToCalendar(subscription, feedUrl),
  }, [icon("calendarAdd", 18), t("calendar.subscribe.add")]);
}

const WEBVIEW_UA_MARKERS = ["homeassistant", "home assistant", "; wv)"];

function isApplePlatform() {
  const agent = String(navigator.userAgent || "").toLowerCase();
  return agent.includes("iphone") || agent.includes("ipad") || agent.includes("ipod") || agent.includes("macintosh");
}

function isEmbeddedWebView() {
  const agent = String(navigator.userAgent || "").toLowerCase();
  if (WEBVIEW_UA_MARKERS.some((marker) => agent.includes(marker))) return true;
  if (window.externalApp) return true;
  const handlers = window.webkit && window.webkit.messageHandlers;
  if (handlers && (handlers.externalBus || handlers.getExternalAuth)) return true;
  const appleTouch = /\b(iphone|ipad|ipod)\b/.test(agent)
    || (agent.includes("macintosh") && Number(navigator.maxTouchPoints || 0) > 1);
  return appleTouch && agent.includes("applewebkit") && !agent.includes("safari/");
}

function calendarLinks(subscription) {
  if (!subscription.online) {
    return {
      web: calendarFeedUrl(subscription, CALENDAR_SCHEME_WEB),
      plain: calendarFeedUrl(subscription, CALENDAR_SCHEME_PLAIN),
      local: true,
    };
  }
  if (calendarOnlineStatus(subscription) !== CALENDAR_ONLINE_READY) return { web: "", plain: "", local: false };
  const plain = String(subscription.online_url || "");
  return { web: plain.replace(/^https?:/, `${CALENDAR_SCHEME_WEB}:`), plain, local: false };
}

function calendarActions(subscription) {
  const nodes = [];
  if (subscription.online && calendarOnlineStatus(subscription) !== CALENDAR_ONLINE_READY) {
    const status = calendarOnlineStatus(subscription);
    nodes.push(el("p", { class: "cal-hint cal-online-status" }, [
      status === CALENDAR_ONLINE_PENDING ? el("span", { class: "spin" }) : null,
      t(CALENDAR_ONLINE_TEXTS[status]),
    ]));
    return nodes;
  }
  const links = calendarLinks(subscription);
  if (!links.plain) {
    nodes.push(el("p", { class: "cal-hint" }, t("calendar.subscribe.host.missing")));
    return nodes;
  }
  const embedded = isEmbeddedWebView();
  if (embedded) {
    nodes.push(calendarBrowserButton(subscription, links.local ? calendarSubscribeUrl(links.plain) : links.web));
  } else {
    nodes.push(calendarAddButton(subscription, links.web));
  }
  if (state.calendarHandOffStalled === subscription.id) nodes.push(calendarHandOffStalledBlock());
  const row = el("div", { class: "cal-action-row" }, [calendarCopyButton(calendarCopiedUrl(links, embedded))]);
  if (typeof qrMatrix === "function") row.append(calendarQrButton(subscription));
  nodes.push(row);
  if (state.calendarQr === subscription.id) {
    const panel = calendarQrPanel(links.web);
    if (panel) nodes.push(panel);
  }
  nodes.push(calendarFetchLine(subscription));
  nodes.push(calendarHelp(subscription));
  return nodes;
}

function calendarCopiedUrl(links, embedded) {
  if (!embedded) return links.plain;
  if (links.local) return calendarSubscribeUrl(links.plain);
  return isApplePlatform() ? links.web : links.plain;
}

function calendarHelp(subscription) {
  const keys = subscription.online
    ? ["apple", "androidInternet", "google", "outlook"]
    : ["apple", "android", "localOnly"];
  if (isEmbeddedWebView()) keys.push(subscription.online ? "appInternet" : "app");
  const details = el("details", { class: "help-details cal-help" }, [
    el("summary", { class: "help-details-summary" }, t("calendar.subscribe.help.title")),
    el("ul", { class: "cal-help-list" }, keys.map((key) => el("li", {}, t(`calendar.subscribe.help.${key}`)))),
  ]);
  details.open = state.calendarHelpOpen === subscription.id;
  details.addEventListener("toggle", () => {
    if (details.open) state.calendarHelpOpen = subscription.id;
    else if (state.calendarHelpOpen === subscription.id) state.calendarHelpOpen = "";
  });
  return details;
}

function calendarMenuButton(subscription, child) {
  return el("button", {
    class: "icon-btn cal-menu",
    type: "button",
    "aria-label": t("calendar.subscribe.menu"),
    disabled: state.calendarBusy ? "disabled" : null,
    onclick: () => openSheet(() => calendarMenuSheet(subscription, child)),
  }, [icon("more", 18)]);
}

function calendarMenuSheet(subscription, child) {
  return sheet(calendarSubscriptionName(subscription, child), [el("div", { class: "rows flat" }, [
    letterActionRow("settings", t("calendar.subscribe.edit"), () => {
      closeSheet();
      state.calendarDraft = calendarEditDraft(subscription, child);
      rerender();
    }),
    letterActionRow("restore", t("calendar.subscribe.rotate"), () => { closeSheet(); rotateCalendarSubscription(subscription); }),
    letterActionRow("trash", t("calendar.subscribe.delete"), () => { closeSheet(); revokeCalendarSubscription(subscription); }),
  ])]);
}

const CALENDAR_ONLINE_READY = "ready";
const CALENDAR_ONLINE_PENDING = "pending";
const CALENDAR_ONLINE_TEXTS = {
  pending: "calendar.subscribe.online.pending",
  stalled: "calendar.subscribe.online.stalled",
  no_integration: "calendar.subscribe.online.noIntegration",
  unreachable: "calendar.subscribe.online.unreachable",
};

function calendarOnlineStatus(subscription) {
  const status = subscription.online_state;
  if (status === CALENDAR_ONLINE_READY) return subscription.online_url ? CALENDAR_ONLINE_READY : CALENDAR_ONLINE_PENDING;
  return Object.prototype.hasOwnProperty.call(CALENDAR_ONLINE_TEXTS, status) ? status : CALENDAR_ONLINE_PENDING;
}

function calendarCopyButton(url) {
  const button = el("button", {
    class: "btn ghost slim cal-copy",
    type: "button",
    disabled: url ? null : "disabled",
  }, [icon("clip", 16), t("calendar.subscribe.copy")]);
  button.addEventListener("click", async () => {
    const copied = await copyToClipboard(url);
    toast(t(copied ? "calendar.subscribe.copied" : "calendar.subscribe.copyFailed"), copied ? "good" : "bad");
  });
  return button;
}

function clipboardApiCopy(text) {
  if (!(navigator.clipboard && navigator.clipboard.writeText)) return Promise.resolve(false);
  return navigator.clipboard.writeText(text).then(() => true, () => false);
}

async function copyToClipboard(text) {
  if (await clipboardApiCopy(text)) return true;
  try {
    const sink = el("textarea", { class: "cal-copy-sink", "aria-hidden": "true", tabindex: "-1" });
    sink.value = text;
    document.body.append(sink);
    sink.select();
    const done = document.execCommand("copy");
    sink.remove();
    return !!done;
  } catch (error) {
    return false;
  }
}

function calendarQrButton(subscription) {
  const open = state.calendarQr === subscription.id;
  return el("button", {
    class: "btn ghost slim cal-qr-toggle",
    type: "button",
    "aria-expanded": String(open),
    onclick: () => { state.calendarQr = open ? "" : subscription.id; rerender(); },
  }, [icon("qr", 16), t(open ? "calendar.subscribe.qr.hide" : "calendar.subscribe.qr.show")]);
}

function calendarActionKey(action, subscription) {
  return `${action}:${subscription.id}`;
}

function calendarQrPanel(url) {
  if (typeof qrMatrix !== "function") return null;
  const matrix = qrMatrix(url);
  if (!matrix) return null;
  const span = qrCanvasSize(matrix);
  const markup = `<svg viewBox="0 0 ${span} ${span}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect width="${span}" height="${span}" fill="#ffffff"/><path d="${qrPathData(matrix)}" fill="#101917"/></svg>`;
  return el("div", { class: "cal-qr" }, [
    el("div", { class: "cal-qr-frame", role: "img", "aria-label": t("calendar.subscribe.qr.alt"), html: markup }),
    el("p", { class: "cal-hint" }, t("calendar.subscribe.qr.hint")),
  ]);
}

async function runCalendarAction(key, request, doneKey) {
  if (state.calendarBusy) return;
  state.calendarBusy = key;
  rerender();
  const result = await request();
  state.calendarBusy = "";
  if (!result.ok) {
    rerender();
    toast(result.message, "bad");
    return;
  }
  await loadCalendarSubscriptions();
  rerender();
  toast(t(doneKey));
  watchCalendarPending();
}

async function rotateCalendarSubscription(subscription) {
  if (state.calendarBusy) return;
  const ok = await confirmAction({
    title: t("calendar.subscribe.rotate.title"),
    text: t("calendar.subscribe.rotate.text"),
    confirmLabel: t("calendar.subscribe.rotate.confirm"),
    destructive: true,
  });
  if (!ok) return;
  await runCalendarAction(
    calendarActionKey("rotate", subscription),
    () => calendarPostRequest(calendarSubscriptionPath(subscription, "/rotate"), {}),
    "calendar.subscribe.rotate.done"
  );
}

async function revokeCalendarSubscription(subscription) {
  if (state.calendarBusy) return;
  const ok = await confirmAction({
    title: t("calendar.subscribe.delete.title"),
    text: t("calendar.subscribe.delete.text"),
    confirmLabel: t("calendar.subscribe.delete.confirm"),
    destructive: true,
  });
  if (!ok) return;
  state.calendarQr = "";
  await runCalendarAction(
    calendarActionKey("revoke", subscription),
    () => calendarRequest(calendarSubscriptionPath(subscription), { method: "DELETE" }),
    "calendar.subscribe.delete.done"
  );
}
