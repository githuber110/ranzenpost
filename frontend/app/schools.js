const SCHOOL_STATUS_OK = "ok";
const SCHOOL_STATUS_PENDING = "pending";
const SCHOOL_STATUS_REFRESH_MS = 30000;
const OUTAGE_STATUS_REFRESH_MS = 60000;
const SHORT_NAME_MAX_LENGTH = 30;
let schoolStatusRefreshAt = 0;

function manySchools() {
  return readySchools().length > 1;
}

function hostShortName(url) {
  let text = String(url || "").trim();
  if (text.includes("://")) text = text.split("://")[1];
  const host = text.split("/")[0].split("@").pop().split(":")[0];
  const labels = host.split(".").filter(Boolean);
  return (labels.length > 1 ? labels.slice(0, -1) : labels).join(".");
}

function schoolShortName(id) {
  const entry = connectionOf(id);
  if (!entry) return "";
  const own = String(entry.short_name || "").trim();
  return own || hostShortName(entry.school_url);
}

function schoolFullName(id) {
  const entry = connectionOf(id);
  if (!entry) return "";
  const name = [entry.label, entry.school_name].map((value) => String(value || "").trim()).find(Boolean);
  return name || hostShortName(entry.school_url) || entry.id;
}

function schoolSummary(id) {
  return (state.schools || []).find((entry) => entry && entry.id === id) || null;
}

function schoolOfChild(child) {
  if (!child) return "";
  return child.connection_id || connectionOfKey(child.key);
}

function schoolTagText(item) {
  return schoolShortName(item.connection_id) || String(item.school || "");
}

function schoolTag(item) {
  if (!manySchools() || !item || !item.connection_id) return null;
  const text = schoolTagText(item);
  return text ? iservText("span", { class: "tag school" }, text) : null;
}

function schoolStatus(id) {
  return (state.schoolStatus && state.schoolStatus[id]) || SCHOOL_STATUS_OK;
}

function applySchoolStatus(rows) {
  const next = {};
  const reasons = {};
  for (const row of rows || []) {
    if (!row || !row.id) continue;
    next[row.id] = row.status || SCHOOL_STATUS_OK;
    if (row.reason) reasons[row.id] = row.reason;
  }
  state.schoolStatus = next;
  state.schoolReasons = reasons;
}

function schoolReason(id) {
  return (state.schoolReasons && state.schoolReasons[id]) || "";
}

function schoolSessionMissing(id) {
  return schoolStatus(id) === ERROR_AUTH_FAILED && schoolReason(id) === REASON_SESSION_NOT_OPENED;
}

function schoolTroubled(id) {
  const status = schoolStatus(id);
  return status === ERROR_AUTH_FAILED || status === ERROR_NETWORK;
}

async function refreshOutageStatus() {
  if (!anyOutage()) return;
  if (Date.now() - schoolStatusRefreshAt < OUTAGE_STATUS_REFRESH_MS) return;
  await refreshSchoolStatus(true);
}

async function refreshSchoolStatus(force) {
  if (!force && Date.now() - schoolStatusRefreshAt < SCHOOL_STATUS_REFRESH_MS) return state.schoolStatus;
  schoolStatusRefreshAt = Date.now();
  try {
    const health = await getJson("api/health");
    state.schools = Array.isArray(health.connections) ? health.connections : state.schools;
    applySchoolStatus(health.connections);
  } catch (error) {
    return state.schoolStatus;
  }
  return state.schoolStatus;
}

function noteSchoolFailure(connectionId, code, reason) {
  if (connectionId && connectionOf(connectionId)) {
    state.schoolStatus = Object.assign({}, state.schoolStatus, { [connectionId]: code });
    state.schoolReasons = Object.assign({}, state.schoolReasons, { [connectionId]: reason || "" });
    rerender();
    return;
  }
  refreshSchoolStatus(true).then(() => {
    const ready = readySchools();
    if (ready.length && ready.every((entry) => schoolStatus(entry.id) === ERROR_AUTH_FAILED)) {
      dropSheet();
      const rank = (entry) => loginReasonRank(schoolReason(entry.id));
      const chosen = ready.reduce((best, entry) => (rank(entry) < rank(best) ? entry : best), ready[0]);
      renderReconnect(detachedRoot(), state.account, chosen.id, schoolReason(chosen.id));
      return;
    }
    rerender();
  });
}

function noteUnavailableSchools(data) {
  const listed = data && Array.isArray(data.unavailable) ? data.unavailable : [];
  if (listed.length && manySchools()) refreshSchoolStatus(false).then(rerender);
}

function schoolStatusLabel(id) {
  const status = schoolStatus(id);
  if (schoolSessionMissing(id)) return t("connection.status.session");
  if (status === ERROR_AUTH_FAILED) return t("connection.status.authFailed");
  if (status === ERROR_NETWORK) return t("connection.status.network");
  if (status === ERROR_OUTAGE) {
    const since = formatIsoMoment(outageInfo(id).since);
    return since ? t("connection.status.outageSince", { time: since }) : t("connection.status.outage");
  }
  if (status === SCHOOL_STATUS_PENDING || status === ERROR_NOT_CONFIGURED) return t("connection.status.pending");
  return "";
}

function schoolDot(id) {
  const status = schoolStatus(id);
  const tone = status === SCHOOL_STATUS_OK ? "ok" : status === ERROR_OUTAGE ? "off" : "warn";
  return el("span", { class: `school-dot ${tone}`, "aria-hidden": "true" });
}

function schoolInOutage(id) {
  return !!id && schoolStatus(id) === ERROR_OUTAGE;
}

function outageSchools() {
  return readySchools().filter((entry) => schoolInOutage(entry.id));
}

function anyOutage() {
  return outageSchools().length > 0;
}

function outageInfo(id) {
  const row = schoolSummary(id) || {};
  return { since: row.since || null, lastSuccess: row.last_success || null };
}

function applyRetryAnswer(id, answer) {
  const rows = (state.schools || []).map((row) => (row && row.id === id
    ? Object.assign({}, row, { status: answer.status || row.status, reason: answer.reason || "", since: answer.since || null, last_success: answer.last_success || row.last_success || null })
    : row));
  state.schools = rows;
  applySchoolStatus(rows);
}

async function retrySchool(id) {
  if (state.outageRetrying) return;
  state.outageRetrying = id;
  state.outageNote = null;
  rerender();
  let answer = null;
  try {
    answer = await postJson(`api/connections/${encodeURIComponent(id)}/retry`, {});
  } catch (error) {
    answer = null;
  }
  state.outageRetrying = null;
  if (answer && answer.ok) applyRetryAnswer(id, answer);
  else if (answer) state.outageNote = { id, text: apiMessage(answer, "api.retry.tooSoon") };
  if (!schoolInOutage(id)) {
    await refreshEverything();
    return;
  }
  rerender();
}

function outageBannerRow(id) {
  const info = outageInfo(id);
  const lastUpdate = formatIsoMoment(info.lastSuccess);
  const text = manySchools() ? t("outage.banner.schoolText", { school: schoolFullName(id) }) : t("outage.banner.text");
  const lines = [
    iservText("p", { class: "outage-text" }, text),
    lastUpdate ? el("p", { class: "outage-stamp" }, t("outage.banner.lastUpdate", { time: lastUpdate })) : null,
    state.outageNote && state.outageNote.id === id ? el("p", { class: "outage-stamp" }, state.outageNote.text) : null,
  ];
  const busy = state.outageRetrying === id;
  const button = el("button", { class: "btn ghost slim", type: "button", onclick: () => retrySchool(id) },
    busy ? [el("span", { class: "spin" }), document.createTextNode(t("common.checking"))] : t("outage.banner.retry"));
  if (busy) button.disabled = true;
  return el("div", { class: "outage-row" }, [el("div", { class: "outage-body" }, lines), button]);
}

function outageBanner() {
  const schools = outageSchools();
  if (!schools.length) return null;
  return el("div", { class: "outage-banner", role: "status" }, schools.map((entry) => outageBannerRow(entry.id)));
}

function outageEmptyBlock() {
  const block = emptyBlock("info", t("outage.empty.title"), t("outage.empty.text"));
  block.classList.add("calm");
  return block;
}

function schoolIssueBanner(schoolIds) {
  if (!manySchools()) return null;
  const wanted = Array.isArray(schoolIds) ? schoolIds : connections().map((entry) => entry.id);
  const troubled = wanted.filter((id, index) => wanted.indexOf(id) === index && connectionOf(id) && schoolTroubled(id));
  if (!troubled.length) return null;
  return el("div", { class: "school-banner", role: "status" }, troubled.map((id) => {
    const key = schoolSessionMissing(id)
      ? "connection.banner.session"
      : schoolStatus(id) === ERROR_AUTH_FAILED
        ? "connection.banner.authFailed"
        : "connection.banner.network";
    return el("div", { class: "school-banner-row" }, [
      schoolDot(id),
      iservText("span", { class: "school-banner-text" }, t(key, { school: schoolFullName(id) })),
      el("button", { class: "btn ghost slim", type: "button", onclick: () => openSchoolPage(id) }, t("connection.banner.open")),
    ]);
  }));
}

function shownChildSchools() {
  if (timetableShowsAllChildren()) return state.children.map(schoolOfChild);
  return [currentConnectionId()];
}

function schoolsIn(items) {
  const present = new Set((items || []).map((item) => item && item.connection_id).filter(Boolean));
  return connections().map((entry) => entry.id).filter((id) => present.has(id));
}

function filterBySchool(items, current) {
  const list = items || [];
  if (!current || !schoolsIn(list).includes(current)) return list;
  return list.filter((item) => item && item.connection_id === current);
}

function schoolFilterBar(items, current, onSelect) {
  const ids = schoolsIn(items);
  if (ids.length < 2) return null;
  const active = ids.includes(current) ? current : "";
  const bar = el("div", { class: "chipbar school-filter" });
  bar.append(el("button", {
    class: "chip",
    type: "button",
    "aria-pressed": String(!active),
    onclick: () => onSelect(""),
  }, t("schools.filter.all")));
  for (const id of ids) {
    bar.append(el("button", {
      class: "chip",
      type: "button",
      "aria-pressed": String(active === id),
      onclick: () => onSelect(id),
    }, [iservText("span", { class: "chip-label" }, schoolShortName(id) || schoolFullName(id))]));
  }
  return bar;
}

function setPostSchoolFilter(id) {
  state.postSchoolFilter = id || "";
  rerender();
}

function setMessengerSchoolFilter(id) {
  state.messengerSchoolFilter = id || "";
  rerender();
}

function childPills(activeId, onSelect) {
  const bar = el("div", { class: "chipbar child-pills" });
  for (const child of state.children) {
    bar.append(el("button", {
      class: "chip",
      type: "button",
      "aria-pressed": String(child.key === activeId),
      onclick: () => onSelect(child.key),
    }, [iservText("span", { class: "chip-label" }, childPillLabel(child))]));
  }
  return bar;
}

function childPillsShown() {
  return manySchools() && state.children.length > 1;
}

function openSchoolPage(id) {
  if (!connectionOf(id)) return;
  const wasSettings = state.view === "settings";
  if (!wasSettings) state.settingsReturn = state.view;
  state.settingsSchoolId = id;
  dropSheet();
  if (wasSettings) {
    showSettingsChange();
    return;
  }
  setView("settings");
}

function closeSchoolPage() {
  state.settingsSchoolId = null;
  dropSheet();
  showSettingsChange();
}

function schoolChildrenCount(id) {
  const listed = state.children.filter((child) => schoolOfChild(child) === id);
  if (listed.length) return listed.length;
  const entry = connectionOf(id);
  return entry && Array.isArray(entry.children) ? entry.children.length : 0;
}

function schoolChildrenValue(id) {
  const listState = (schoolSummary(id) || {}).children_state;
  if (listState === "unreadable") return el("span", { class: "val warn" }, t("schools.children.unreadable"));
  const listed = state.children.some((child) => schoolOfChild(child) === id);
  if (listState === "refused" && !listed) return el("span", { class: "val" }, t("schools.children.refused"));
  const count = schoolChildrenCount(id);
  if (!count && listState === "listed") return el("span", { class: "val" }, t("schools.children.none"));
  return el("span", { class: "val" }, tCount("schools.children", count));
}

function schoolRow(entry) {
  const id = entry.id;
  const status = schoolStatusLabel(id);
  const open = paneOpen() && state.settingsSchoolId === id;
  return el("button", {
    class: open ? "setting-row school-row open" : "setting-row school-row",
    type: "button",
    onclick: () => openSchoolPage(id),
  }, [
    schoolDot(id),
    iservText("span", { class: "lbl" }, schoolFullName(id)),
    status
      ? el("span", { class: schoolInOutage(id) ? "val" : "val warn" }, status)
      : schoolChildrenValue(id),
    el("span", { class: "chev" }, [icon("chevron", 16)]),
  ]);
}

function schoolsSection(first) {
  return el("section", { class: first ? "settings-group schools-block" : "settings-group spaced schools-block" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("schools.section"))]),
    el("div", { class: "rows" }, connections().map(schoolRow)),
  ]);
}

async function loadSettingsCalendar() {
  await loadCalendarSubscriptions();
  if (state.view === "settings" && !state.sheet) rerender();
}

function calendarAccessLabel() {
  const data = calendarData();
  const count = data ? data.subscriptions.length : 0;
  return count ? tCount("schools.calendar.count", count) : "";
}

function manySchoolsSettings(view, config) {
  view.append(displaySettingsSection(true));
  view.append(connectSettingsSection(config));
  view.append(schoolsSection(false));
  view.append(modulesSection(true));
  view.append(settingsSection("settings.section.account", false, [
    settingRow(t("schools.add"), "", startAddSchool, "add-school"),
    settingRow(t("schools.reset"), "", resetEverything, "destructive"),
  ]));
  view.append(helpSettingsSection());
  return view;
}

function schoolPageView() {
  return el("div", { class: "school-page" }, schoolPageSections(state.settingsSchoolId));
}

function schoolPageSections(id) {
  const summary = schoolSummary(id) || {};
  const account = [
    infoRow(t("schools.login"), summary.username || "", "login-row"),
    settingRow(t("settings.password"), "", () => openSheet(passwordSheet)),
  ];
  if (schoolStatus(id) === ERROR_AUTH_FAILED && schoolReason(id) === REASON_CODE_STEP_FAILED) {
    account.push(settingRow(t("account.reconnect.reset"), "", () => openSheet(() => resetSchoolSheet(id))));
  } else if (schoolStatus(id) === ERROR_AUTH_FAILED) {
    account.push(settingRow(t("connection.reconnect"), "", () => openSheet(() => reconnectSheet(id))));
  }
  account.push(settingRow(t("schools.disconnect"), "", () => disconnectSchool(id), "destructive"));
  const school = [settingRow(t("schools.shortName"), schoolShortName(id), () => openSheet(shortNameSheet))].concat(schoolSettingRows(id));
  return [
    settingsSection("settings.section.school", true, school),
    schoolModulesSection(id),
    settingsSection("settings.section.account", false, account),
  ];
}

function schoolModules(id) {
  return (state.schoolModules && state.schoolModules[id]) || null;
}

async function loadSchoolModules(id) {
  let payload = null;
  try {
    payload = await getJson(`api/connections/${encodeURIComponent(id)}/modules`);
  } catch (error) {
    payload = null;
  }
  state.schoolModules = Object.assign({}, state.schoolModules, { [id]: payload ? applyModules(payload) : { error: true } });
  rerender();
}

async function recheckSchoolModules(id) {
  if (state.modulesRechecking) return;
  state.modulesRechecking = true;
  rerender();
  let result = null;
  try {
    result = await postJson(`api/connections/${encodeURIComponent(id)}/modules/recheck`, {});
  } catch (error) {
    result = null;
  }
  state.modulesRechecking = false;
  if (result && result.modules) {
    state.schoolModules = Object.assign({}, state.schoolModules, { [id]: applyModules(result.modules) });
    try {
      state.modules = applyModules(await getJson("api/modules"));
    } catch (error) {
      toast(t("common.refreshFailed"), "bad");
    }
  }
  if (result === null) toast(t("app.error.service.text"), "bad");
  else toast(apiMessage(result, "api.modules.rechecked"), result.ok ? "good" : "bad");
  rerender();
}

function schoolModulesSection(id) {
  const box = schoolModules(id);
  if (!box) autoLoad(`schoolModules:${id}`, () => loadSchoolModules(id));
  const block = el("div", { class: "modules-block" });
  if (!box) block.append(loadingBlock());
  else if (box.error) block.append(el("p", { class: "cal-hint modules-none" }, t("settings.modules.none")));
  else {
    const available = MODULE_NAMES.filter((name) => box.available[name]);
    block.append(available.length
      ? el("p", { class: "section-lead modules-offered" }, t("settings.modules.offered", { names: available.map((name) => t(`settings.modules.name.${name}`)).join(", ") }))
      : el("p", { class: "cal-hint modules-none" }, t("settings.modules.none")));
  }
  const busy = !!state.modulesRechecking;
  block.append(el("div", { class: "cal-action-row" }, [
    el("button", {
      class: "link-btn modules-recheck",
      type: "button",
      disabled: busy ? "disabled" : null,
      onclick: () => recheckSchoolModules(id),
    }, busy ? [el("span", { class: "spin" }), t("settings.modules.recheck")] : [icon("restore", 16), t("settings.modules.recheck")]),
  ]));
  const help = box && !box.error ? modulesHelpBlockFor(box) : null;
  if (help) block.append(help);
  return el("section", { class: "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.section.modules"))]),
    block,
  ]);
}

function modulesHelpBlockFor(registry) {
  const kept = state.modules;
  state.modules = registry;
  try {
    return modulesHelpBlock();
  } finally {
    state.modules = kept;
  }
}

function schoolMeOf(id) {
  const cache = state.schoolMe || {};
  return Object.prototype.hasOwnProperty.call(cache, id) ? cache[id] : null;
}

async function loadSchoolMe(id) {
  let data = {};
  try {
    data = await getJson(`api/me?connection=${encodeURIComponent(id)}`);
  } catch (error) {
    data = {};
  }
  state.schoolMe = Object.assign({}, state.schoolMe, { [id]: data && !data.error ? data : {} });
  if (state.settingsPage === SETTINGS_PAGE_TECH) rerender();
}

function techEntriesBlock(entries) {
  const rows = techRows(entries);
  return rows.length ? factList(rows) : el("p", { class: "dlg-text" }, t("common.techDetails.empty"));
}

function techSchoolBlock(id) {
  const data = schoolMeOf(id);
  if (!data) autoLoad(`schoolMe:${id}`, () => loadSchoolMe(id));
  return el("section", { class: "settings-group spaced tech-school", "data-school": id }, [
    el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, schoolFullName(id))]),
    data ? techEntriesBlock(meTechEntriesOf(data)) : loadingBlock(),
  ]);
}

function techDetailsPageView() {
  const view = el("div", { class: "tech-page" }, [el("p", { class: "section-lead tech-lead" }, t("common.techDetails.text"))]);
  if (!manySchools()) {
    view.append(techEntriesBlock(meTechEntries()));
    return view;
  }
  for (const entry of connections()) view.append(techSchoolBlock(entry.id));
  return view;
}

function meTechEntriesOf(me) {
  const kept = state.me;
  state.me = me || {};
  try {
    return meTechEntries();
  } finally {
    state.me = kept;
  }
}

function cleanShortName(value) {
  return String(value || "").trim().split(/\s+/).filter(Boolean).join(" ").slice(0, SHORT_NAME_MAX_LENGTH);
}

function shortNameSheet() {
  const id = editingConnectionId();
  const draft = sheetState(() => ({ short_name: schoolShortName(id) }));
  const input = el("input", {
    class: "inp",
    type: "text",
    maxlength: String(SHORT_NAME_MAX_LENGTH),
    value: draft.short_name,
    placeholder: hostShortName(connectionConfig(id).school_url),
    "aria-label": t("schools.shortName"),
  });
  input.addEventListener("input", () => { draft.short_name = input.value; });
  const body = [
    el("p", { class: "dlg-text" }, t("schools.shortName.text")),
    el("label", { class: "field" }, [el("span", { class: "lbl" }, t("schools.shortName")), input]),
  ];
  return sheet(t("schools.shortName.sheet"), body, [saveSheet(() => ({ short_name: cleanShortName(draft.short_name) }))]);
}

function reconnectSheet(id) {
  const summary = schoolSummary(id) || {};
  const draft = sheetState(() => ({ password: "" }));
  const account = el("input", {
    class: "visually-hidden",
    type: "text",
    name: "username",
    autocomplete: "username",
    dir: "ltr",
    value: summary.username || "",
    readonly: "readonly",
    tabindex: "-1",
    "aria-hidden": "true",
  });
  const hint = el("span", { class: "err", style: "display:block;margin:-8px 0 16px" }, "");
  const input = el("input", {
    class: "inp",
    type: "password",
    name: "password",
    autocomplete: "current-password",
    placeholder: t("account.reconnect.passwordPlaceholder"),
    "aria-label": t("account.reconnect.passwordLabel"),
  });
  input.addEventListener("input", () => { draft.password = input.value; hint.textContent = ""; });
  const button = el("button", { class: "btn", type: "submit" }, t("account.reconnect.submit"));
  const run = async () => {
    if (!draft.password) {
      hint.textContent = t("account.reconnect.missingPassword");
      return;
    }
    button.disabled = true;
    button.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.checking")));
    try {
      const result = await postJson("api/password/repair", { password: draft.password, connection_id: id });
      if (result && result.ok) {
        resetSheetForm();
        closeSheet();
        await refreshSchoolStatus(true);
        toast(t("connection.reconnect.done"));
        refreshEverything();
        return;
      }
      hint.textContent = apiMessage(result, "account.reconnect.failed");
    } catch (error) {
      hint.textContent = t("account.reconnect.offline");
    }
    button.disabled = false;
    button.replaceChildren(document.createTextNode(t("account.reconnect.submit")));
  };
  const form = el("form", { class: "stack-form" }, [
    account,
    el("label", { class: "field" }, [el("span", { class: "lbl" }, t("account.reconnect.passwordLabel")), input]),
    hint,
  ]);
  form.addEventListener("submit", (event) => { event.preventDefault(); run(); });
  button.addEventListener("click", (event) => { event.preventDefault(); run(); });
  return sheet(t("connection.reconnect.sheet"), [
    iservText("p", { class: "dlg-text" }, schoolFullName(id)),
    el("p", { class: "dlg-text" }, t("account.reconnect.text")),
    form,
  ], [button]);
}

function resetSchoolSheet(id) {
  const hint = el("span", { class: "err", style: "display:block;margin:-8px 0 16px" }, "");
  const button = el("button", { class: "btn destructive", type: "button" }, t("account.reconnect.reset"));
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.pleaseWait")));
    if (await resetSchoolSetup(id)) return;
    hint.textContent = t("account.reconnect.resetFailed");
    button.disabled = false;
    button.replaceChildren(document.createTextNode(t("account.reconnect.reset")));
  });
  return sheet(t("account.reconnect.reset"), [
    iservText("p", { class: "dlg-text" }, schoolFullName(id)),
    el("p", { class: "dlg-text" }, t("api.login.twofactor")),
    el("p", { class: "dlg-text" }, t("account.reconnect.resetNote")),
    hint,
  ], [button]);
}

async function reloadConnections() {
  state.config = await getJson("api/config");
  await loadChildren();
  await refreshSchoolStatus(true);
}

async function disconnectSchool(id) {
  const ok = await confirmAction({
    title: t("schools.disconnect.title"),
    text: t("schools.disconnect.text", { school: schoolFullName(id) }),
    confirmLabel: t("settings.disconnect.confirm"),
    destructive: true,
  });
  if (!ok) return;
  let message = t("settings.disconnect.done");
  let good = true;
  try {
    const result = await disconnectWithRetry(`api/connections/${encodeURIComponent(id)}/disconnect`, {}, id);
    if (result && result.disconnected === false) {
      toast(apiMessage(result, "settings.disconnect.failed"), "bad");
      return;
    }
    if (result && (result.message_key || result.message)) message = apiMessage(result);
    good = disconnectGood(result);
  } catch (error) {
    good = false;
    message = t("settings.disconnect.failed");
  }
  toast(message, good ? "good" : "bad");
  state.settingsSchoolId = null;
  state.schoolModules = null;
  state.absence = null;
  state.overviewWeeks = {};
  state.overviewWeekMondays = {};
  try {
    await reloadConnections();
  } catch (error) {
    window.setTimeout(boot, 900);
    return;
  }
  if (!readySchools().length) {
    window.setTimeout(boot, 900);
    return;
  }
  state.timetable = null;
  await refreshEverything();
}

async function resetEverything() {
  const ok = await confirmAction({
    title: t("schools.reset.title"),
    text: t("schools.reset.text"),
    confirmLabel: t("schools.reset.confirm"),
    destructive: true,
  });
  if (!ok) return;
  let good = true;
  const kept = [];
  for (const entry of connections()) {
    try {
      const result = await postJson(`api/connections/${encodeURIComponent(entry.id)}/disconnect`, {});
      if (result && result.disconnected === false) kept.push(schoolFullName(entry.id));
    } catch (error) {
      good = false;
    }
  }
  if (kept.length) {
    toast(t("settings.disconnect.kept", { schools: localList(kept) }), "bad");
  } else {
    toast(good ? t("settings.disconnect.done") : t("settings.disconnect.failed"), good ? "good" : "bad");
  }
  window.setTimeout(boot, 900);
}

async function startAddSchool() {
  dropSheet();
  try {
    await postJson("api/wizard/start", {});
  } catch (error) {
    toast(t("app.error.service.text"), "bad");
    return;
  }
  state.addingSchool = true;
  renderWizard(detachedRoot(), finishAddSchool, { onCancel: cancelAddSchool });
}

async function finishAddSchool() {
  state.addingSchool = false;
  state.settingsSchoolId = null;
  state.schoolModules = null;
  state.view = "settings";
  await boot();
}

async function cancelAddSchool() {
  try {
    await postJson("api/wizard/cancel", {});
  } catch (error) {
    toast(t("app.error.service.text"), "bad");
  }
  state.addingSchool = false;
  state.view = "settings";
  await boot();
}
