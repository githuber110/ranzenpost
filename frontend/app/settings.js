function settingsView() {
  const config = state.config || {};
  const view = el("div", {});
  ensureHaStatus();
  const hint = updateHintBlock();
  if (hint) view.append(hint);
  if (manySchools()) return manySchoolsSettings(view, config);
  view.append(displaySettingsSection(true));
  view.append(connectSettingsSection(config));
  view.append(settingsSection("settings.section.school", false, schoolSettingRows(editingConnectionId())));
  view.append(modulesSection());
  view.append(settingsSection("settings.section.account", false, [
    settingRow(t("settings.password"), "", () => openSheet(passwordSheet)),
    settingRow(t("schools.add"), "", startAddSchool, "add-school"),
    settingRow(t("settings.disconnect"), "", disconnectAccount, "destructive"),
  ]));
  view.append(helpSettingsSection());
  return view;
}

function schoolSettingRows(id) {
  const config = connectionConfig(id);
  const rows = [settingRow(t("holidays.settings.title"), holidayRegionValueLabel(), () => openSheet(holidayRegionSheet))];
  if (moduleOn("timetable") && !noChildren()) {
    rows.push(periodsSettingRow(id, config));
    rows.push(settingRow(t("settings.names"), "", openNamesPage, "names-setting", SETTINGS_PAGE_NAMES));
    rows.push(...courseSettingRows(id));
  }
  if (moduleOn("absences") && !noChildren()) {
    rows.push(settingRow(t("settings.phones"), t("settings.phones.count", { count: formatNumber((config.phones || []).filter((p) => p.number).length) }), () => openSheet(phonesSheet)));
  }
  return rows;
}

function displaySettingsSection(first) {
  return settingsSection("settings.section.display", first, [
    settingRow(t("settings.language"), languageLabel(currentLanguageChoice()), () => openSheet(languageSheet)),
    settingRow(t("settings.theme"), themeLabel(state.theme), () => openSheet(themeSheet)),
    settingRow(t("settings.layout.title"), tCount("settings.blocks.value", enabledOverviewBlocks().length), () => openSettingsPage(SETTINGS_PAGE_LAYOUT), "layout-setting", SETTINGS_PAGE_LAYOUT),
  ]);
}

function connectSettingsSection(config) {
  ensureHaStatus();
  if (!state.calendar) autoLoad("calendarSettings", loadSettingsCalendar);
  return settingsSection("settings.section.notifications", false, [
    settingRow(t("settings.notify.sheet"), notifyServicesSummaryLabel(config.notify_services), () => openSheet(notifySheet), "notify-setting"),
    settingRow(t("schools.calendar.access"), calendarAccessLabel(), openCalendarPage, "calendar-setting", SETTINGS_PAGE_CALENDAR),
    settingRow(t("settings.ha.integration"), haRowValue(), openHomeAssistantSheet, "ha-setting"),
  ]);
}

function helpSettingsSection() {
  return settingsSection("settings.section.help", false, [
    settingRow(t("help.row"), t("help.row.hint"), openHelpPage, "help-setting", SETTINGS_DETAIL_HELP),
    settingRow(t("common.techDetails"), "", () => openSettingsPage(SETTINGS_PAGE_TECH), "tech-setting", SETTINGS_PAGE_TECH),
  ]);
}

function infoRow(label, value, variant) {
  return el("div", { class: variant ? `setting-row static ${variant}` : "setting-row static" }, [
    el("span", { class: "lbl" }, label),
    value ? iservText("span", { class: "val" }, value) : null,
  ]);
}

function settingsSection(labelKey, first, rows) {
  return el("section", { class: first ? "settings-group" : "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t(labelKey))]),
    el("div", { class: "rows" }, rows),
  ]);
}

function catalogueModuleName(entry) {
  const key = `modules.catalogue.${entry.slug}`;
  return hasMessage(key) ? t(key) : entry.name || entry.label || entry.segment;
}

function unknownModuleLabels() {
  return reportableUnsupported().map(catalogueModuleName)
    .concat(state.modules.unknown.map((entry) => entry.label || entry.segment));
}

function reportableUnsupported() {
  return state.modules.unsupported;
}

function moduleEntries() {
  return reportableUnsupported().concat(state.modules.unknown);
}

function moduleSegments() {
  return moduleEntries().map((entry) => entry.segment);
}

function moduleEntryName(entry) {
  return entry.slug ? catalogueModuleName(entry) : entry.label || entry.segment;
}

function reportedModuleSegments() {
  const listed = state.config && Array.isArray(state.config.reported_modules) ? state.config.reported_modules : [];
  return listed.map(String);
}

function unreportedModuleEntries() {
  const reported = new Set(reportedModuleSegments());
  return moduleEntries().filter((entry) => !reported.has(entry.segment));
}

const MODULE_CARD_HIDE_DAYS = 30;

function moduleCardHidden(entries) {
  const hidden = state.config && state.config.modules_card_hidden && typeof state.config.modules_card_hidden === "object"
    ? state.config.modules_card_hidden
    : {};
  const until = Number(hidden.until) || 0;
  if (until <= Date.now() / 1000) return false;
  const known = new Set(Array.isArray(hidden.segments) ? hidden.segments.map(String) : []);
  return entries.every((entry) => known.has(entry.segment));
}

function moduleCardWanted() {
  const entries = unreportedModuleEntries();
  return entries.length > 0 && !moduleCardHidden(entries);
}

function moduleIssueBody() {
  const body = helpIssueBody();
  return `${t("help.issue.moduleQuestion")}\n\n${body}`;
}

function moduleIssueUrl() {
  const segments = moduleSegments();
  const title = segments.length ? t("help.issue.title", { segments: segments.join(", ") }) : t("help.issue.titlePlain");
  const body = segments.length ? moduleIssueBody() : helpIssueBody();
  const params = new URLSearchParams({ title, body });
  return `${MODULE_ISSUE_URL}?${params.toString()}`;
}

function moduleCard(withLater) {
  const entries = unreportedModuleEntries();
  const names = entries.map(moduleEntryName).join(", ");
  const actions = [
    el("button", { class: "btn slim module-card-show", type: "button", onclick: openHelpPage }, t("help.card.show")),
  ];
  if (withLater) {
    actions.push(el("button", { class: "btn ghost slim module-card-later", type: "button", onclick: hideModuleCard }, t("help.card.later")));
  }
  return el("div", { class: "module-card", role: "status" }, [
    el("p", { class: "module-card-text" }, tCount("help.card.text", entries.length, { names })),
    el("div", { class: "module-card-actions" }, actions),
  ]);
}

async function persistModuleFlags() {
  const payload = {
    reported_modules: reportedModuleSegments(),
    modules_card_hidden: state.config && state.config.modules_card_hidden ? state.config.modules_card_hidden : {},
  };
  try {
    await postJson("api/config", payload);
  } catch (error) {
    toast(t("common.saveFailed"), "bad");
  }
}

async function hideModuleCard() {
  if (!state.config) state.config = {};
  state.config.modules_card_hidden = {
    until: Math.floor(Date.now() / 1000) + MODULE_CARD_HIDE_DAYS * 86400,
    segments: moduleSegments(),
  };
  rerender();
  await persistModuleFlags();
}

async function rememberReportedModules() {
  if (!state.config) state.config = {};
  const merged = reportedModuleSegments();
  for (const segment of moduleSegments()) {
    if (!merged.includes(segment)) merged.push(segment);
  }
  state.config.reported_modules = merged;
  await persistModuleFlags();
}

function modulesHelpBlock() {
  const parts = [];
  if (moduleEntries().length) {
    if (unreportedModuleEntries().length) parts.push(moduleCard(false));
    else {
      parts.push(
        el("p", { class: "cal-hint modules-unknown" }, t("settings.modules.unknown", { labels: unknownModuleLabels().join(", ") })),
        el("button", { class: "btn ghost slim modules-report", type: "button", onclick: openHelpPage }, [icon("info", 16), t("settings.modules.report")]),
      );
    }
  }
  if (!parts.length) return null;
  return el("div", { class: "modules-help-block" }, parts);
}

function openHelpPage() {
  const from = state.view;
  if (from !== "settings") {
    state.settingsReturn = from;
    setView("settings");
  }
  state.helpReturn = from;
  state.helpPage = true;
  state.helpDetailsOpen = false;
  state.settingsSchoolId = null;
  dropSheet();
  showSettingsChange();
}

function closeHelpPage() {
  state.helpPage = false;
  dropSheet();
  const target = state.helpReturn;
  state.helpReturn = null;
  if (target && target !== "settings" && viewAvailable(target)) {
    setView(target);
    return;
  }
  showSettingsChange();
}

const HELP_REPORT_PATH = "api/diagnostics?structure=1";
const HELP_BUNDLE_PATH = "api/diagnostics/report.zip";
const NOTICE_BUNDLE_PATH = "api/diagnostics/report.zip?structure=0";
const HELP_BUNDLE_NAME = "ranzenpost-report.zip";

function helpReport() {
  return state.helpReport || "";
}

function helpIssueBody() {
  const facts = state.helpFacts;
  const versions = facts
    ? t("help.issue.versions", { app: facts.app || "?", integration: facts.integration || "?", home_assistant: facts.home_assistant || "?", iserv: facts.iserv || "?" })
    : "";
  return t("help.issue.body", { versions }).trimStart();
}

async function loadHelpReport() {
  state.helpFailed = false;
  try {
    const data = await getJson(HELP_REPORT_PATH, requestSignal(UPLOAD_TIMEOUT_MS));
    state.helpReport = String(data && data.report ? data.report : "");
    state.helpFacts = data && data.facts && typeof data.facts === "object" ? data.facts : null;
    state.helpBundle = null;
    state.helpBundleFailed = false;
  } catch (error) {
    state.helpFailed = true;
  }
  if (state.helpPage) rerender();
  if (state.helpReport) autoLoad("help:bundle", loadHelpBundle);
}

async function loadHelpBundle() {
  state.helpBundleFailed = false;
  try {
    state.helpBundle = await fetchAppFile(HELP_BUNDLE_PATH, HELP_BUNDLE_NAME);
  } catch (error) {
    state.helpBundle = null;
    state.helpBundleFailed = true;
  }
  if (state.helpPage) rerender();
}

function helpList(titleKey, keys) {
  return el("section", { class: "help-list" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t(titleKey))]),
    el("ul", {}, keys.map((key) => el("li", {}, t(key)))),
  ]);
}

function helpPreviewState() {
  if (helpReport()) return null;
  if (state.helpFailed) {
    return el("div", { class: "help-preview-state" }, [
      el("p", { class: "dlg-text" }, t("help.failed")),
      el("button", { class: "btn ghost slim help-retry", type: "button", onclick: () => { state.helpFailed = false; rerender(); } }, t("common.retry")),
    ]);
  }
  autoLoad("help:report", loadHelpReport);
  return el("div", { class: "help-preview-state" }, [el("span", { class: "spin" }), el("span", {}, t("help.loading"))]);
}

async function saveHelpReport() {
  if (!state.helpBundle) await loadHelpBundle();
  const bundle = state.helpBundle;
  if (!bundle) {
    toast(t("help.saveFailed"), "bad");
    return;
  }
  await saveFile(bundle.blob, bundle.filename || HELP_BUNDLE_NAME);
  toast(t("help.saved"), "good");
  await rememberReportedModules();
}

async function copyHelpReport() {
  const report = helpReport();
  if (!report) return;
  const copied = await copyToClipboard(report);
  toast(t(copied ? "help.copied" : "help.copyFailed"), copied ? "good" : "bad");
  if (copied) await rememberReportedModules();
}

function helpBundlePreparing() {
  return !!helpReport() && !state.helpBundle && !state.helpBundleFailed;
}

function helpPageView() {
  const ready = !!helpReport();
  const preparing = helpBundlePreparing();
  ensureHaStatus();
  const outdated = appUpdateNotice();
  const saveClass = outdated ? "btn ghost help-save" : "btn help-save";
  const saveButton = el("button", { class: saveClass, type: "button", onclick: saveHelpReport }, [icon("download", 18), t(preparing ? "help.preparing" : "help.save")]);
  if (!ready || preparing) saveButton.disabled = true;
  const issueLink = el("a", { class: "btn ghost help-issue", href: moduleIssueUrl(), target: "_blank", rel: "noopener" }, [externalIcon(18), t("help.issue")]);
  issueLink.addEventListener("click", () => { rememberReportedModules(); });
  const copyButton = el("button", { class: "btn ghost slim help-copy", type: "button", onclick: copyHelpReport }, [icon("clip", 16), t("help.copy")]);
  if (!ready) copyButton.disabled = true;
  return el("div", { class: "help-page" }, [
    outdated ? helpUpdateWarning(outdated) : null,
    updateHintBlock(!!outdated),
    el("p", { class: "help-intro" }, t("help.intro.what")),
    el("p", { class: "help-intro" }, t("help.intro.not")),
    el("div", { class: "btn-stack help-actions" }, [saveButton, issueLink, copyButton]),
    helpPreviewState(),
    el("p", { class: "cal-hint" }, t("help.issue.hint")),
    el("p", { class: "cal-hint help-account" }, t("help.account")),
    el("p", { class: "cal-hint help-no-start" }, t("help.noStart")),
    helpDetails(),
  ]);
}

function helpDetails() {
  const report = helpReport();
  const details = el("details", { class: "help-details" }, [
    el("summary", { class: "help-details-summary" }, t("help.details")),
    helpList("help.contains.title", ["help.contains.versions", "help.contains.modules", "help.contains.structure", "help.contains.log", "help.contains.counts"]),
    helpList("help.never.title", ["help.never.names", "help.never.credentials", "help.never.contents", "help.never.address"]),
    report ? el("pre", { class: "help-preview", dir: "ltr", tabindex: "0", "aria-label": t("help.preview.label") }, report) : null,
  ]);
  details.open = !!state.helpDetailsOpen;
  details.addEventListener("toggle", () => { state.helpDetailsOpen = details.open; });
  return details;
}

function schoolNameList(ids) {
  return localList(ids.map((id) => schoolShortName(id) || schoolFullName(id)).filter(Boolean));
}

function localList(names) {
  try {
    return new Intl.ListFormat(currentLanguage(), { style: "long", type: "conjunction" }).format(names);
  } catch (error) {
    return names.join(", ");
  }
}

function recheckOutcomeToast(outcomes) {
  const failed = outcomes.filter((outcome) => !outcome.result || !outcome.result.ok);
  if (!failed.length) {
    toast(apiMessage(outcomes[0].result, "api.modules.rechecked"), "good");
    return;
  }
  if (outcomes.length > 1 && failed.length < outcomes.length) {
    toast(t("settings.modules.recheckPartial", { schools: schoolNameList(failed.map((outcome) => outcome.id)) }), "bad");
    return;
  }
  const first = failed[0].result;
  toast(first === null ? t("app.error.service.text") : apiMessage(first, "api.modules.rechecked"), "bad");
}

function recheckTarget() {
  if (state.settingsSchoolId && connectionOf(state.settingsSchoolId)) return state.settingsSchoolId;
  return manySchools() ? "" : editingConnectionId();
}

async function recheckModules() {
  if (state.modulesRechecking) return;
  state.modulesRechecking = true;
  rerender();
  const target = recheckTarget();
  const ids = target ? [target] : readySchools().map((entry) => entry.id);
  const outcomes = [];
  for (const id of ids.length ? ids : [""]) {
    let result = null;
    try {
      result = await postJson("api/modules/recheck", { connection_id: id });
    } catch (error) {
      result = null;
    }
    outcomes.push({ id, result });
  }
  const answered = outcomes.filter((outcome) => outcome.result && outcome.result.modules);
  let modules = answered.length ? answered[answered.length - 1].result.modules : null;
  if (answered.length && manySchools()) {
    try {
      modules = await getJson("api/modules");
    } catch (error) {
      modules = null;
    }
  }
  state.modulesRechecking = false;
  if (modules) state.modules = applyModules(modules);
  recheckOutcomeToast(outcomes);
  rerender();
}

function modulesRecheckButton() {
  const busy = !!state.modulesRechecking;
  return el("button", {
    class: "link-btn modules-recheck",
    type: "button",
    disabled: busy ? "disabled" : null,
    onclick: recheckModules,
  }, busy ? [el("span", { class: "spin" }), t("settings.modules.recheck")] : [icon("restore", 16), t("settings.modules.recheck")]);
}

const SETTINGS_PAGE_LAYOUT = "layout";
const SETTINGS_PAGE_TECH = "tech";
const SETTINGS_PAGE_COURSES = "courses";
const SETTINGS_PAGE_CALENDAR = "calendar";
const SETTINGS_PAGE_NAMES = "names";
let focusAfterRenderSelector = null;

function focusAfterRender(selector) {
  focusAfterRenderSelector = selector;
}

function focusSelectorOf(node) {
  if (!node || !node.closest) return null;
  const row = node.closest(".block-row, .nav-row, .module-row");
  if (!row) return null;
  const owner = row.dataset.block ? `.block-row[data-block="${row.dataset.block}"]`
    : row.dataset.area ? `.nav-row[data-area="${row.dataset.area}"]`
      : row.dataset.module ? `.module-row[data-module="${row.dataset.module}"]` : null;
  if (!owner) return null;
  if (node.classList.contains("switch")) return `${owner} .switch`;
  if (node.classList.contains("info-btn")) return `${owner} .info-btn`;
  if (node.dataset.dir) return `${owner} .order-btns [data-dir="${node.dataset.dir}"]`;
  if (node.getAttribute("role") === "radio") return `${owner} [role="radio"][aria-checked="true"]`;
  return node === row ? owner : null;
}

function rememberFocusForRender() {
  if (focusAfterRenderSelector) return;
  focusAfterRenderSelector = focusSelectorOf(document.activeElement);
}

function applyFocusAfterRender() {
  if (!focusAfterRenderSelector) return;
  const target = root().querySelector(focusAfterRenderSelector);
  focusAfterRenderSelector = null;
  if (target && typeof target.focus === "function") target.focus();
}

function showSettingsChange() {
  if (settingsPaneActive()) {
    rerender();
    return;
  }
  state._scrollTop = true;
  render();
}

function openSettingsPage(page) {
  if (state.view !== "settings") {
    state.settingsReturn = state.view;
    setView("settings");
  }
  state.settingsPage = page;
  state.settingsSchoolId = null;
  state.helpPage = false;
  dropSheet();
  state.layoutAnnouncement = "";
  showSettingsChange();
}

function closeSettingsPage() {
  state.settingsPage = null;
  dropSheet();
  showSettingsChange();
}

function settingsPageTitle(page) {
  if (page === SETTINGS_PAGE_PERIODS) return t("settings.periods.sheet");
  if (page === SETTINGS_PAGE_ENTRY) return entryPageTitle();
  if (page === SETTINGS_PAGE_COURSES) return t("courses.page.title");
  if (page === SETTINGS_PAGE_CALENDAR) return t("calendar.subscribe.title");
  if (page === SETTINGS_PAGE_NAMES) return t("settings.names.sheet");
  if (page === SETTINGS_PAGE_TECH) return t("common.techDetails");
  return t("settings.layout.title");
}

function settingsPageView() {
  if (state.settingsPage === SETTINGS_PAGE_PERIODS) return periodsPageView();
  if (state.settingsPage === SETTINGS_PAGE_ENTRY) return entryPageView();
  if (state.settingsPage === SETTINGS_PAGE_COURSES) return coursesPageView();
  if (state.settingsPage === SETTINGS_PAGE_TECH) return techDetailsPageView();
  if (state.settingsPage === SETTINGS_PAGE_CALENDAR) return calendarPageView();
  if (state.settingsPage === SETTINGS_PAGE_NAMES) return namesPageView();
  return layoutSettingsPage();
}

function settingsPageBack() {
  if (state.settingsPage === SETTINGS_PAGE_COURSES) return closeCoursesPage();
  if (state.settingsPage === SETTINGS_PAGE_CALENDAR) return closeCalendarPage();
  if (state.settingsPage === SETTINGS_PAGE_NAMES) return leavePageForm(closeNamesPage);
  if (state.settingsPage === SETTINGS_PAGE_PERIODS) return closePeriodsPage();
  if (state.settingsPage === SETTINGS_PAGE_ENTRY) return closeEntryPage();
  return closeSettingsPage();
}

function childCourseFilter(child) {
  const entry = connectionOf(schoolOfChild(child));
  const filters = entry && entry.course_filters && typeof entry.course_filters === "object" ? entry.course_filters : {};
  const connectionId = connectionOfKey(child.key);
  const raw = connectionId ? String(child.key).slice(connectionId.length + 1) : String(child.child_id || "");
  const filter = filters[raw];
  return filter && Array.isArray(filter.chosen) ? filter : null;
}

function childCourseInfo(child) {
  const week = overviewWeekData(child.key, 0);
  return week && week.courses ? week.courses : null;
}

function childHasCourses(child) {
  const info = childCourseInfo(child);
  return !!childCourseFilter(child) || !!(info && info.parallel > 0);
}

function courseSettingValue(child) {
  const filter = childCourseFilter(child);
  return filter ? tCount("settings.courses.chosen", filter.chosen.length) : t("settings.courses.all");
}

function courseSettingRows(connectionId) {
  return state.children
    .filter((child) => schoolOfChild(child) === connectionId && childHasCourses(child))
    .map((child) => settingRow(
      t("settings.courses.row", { name: childFirstName(child) }),
      courseSettingValue(child),
      () => openCoursesPage(child.key),
      "courses-setting",
      `${SETTINGS_PAGE_COURSES}:${child.key}`
    ));
}

function openCoursesPage(childKey) {
  const from = state.view;
  state.coursesPage = { child: childKey, data: null, failed: false, draft: null, search: "", saving: false, from, schoolId: state.settingsSchoolId };
  openSettingsPage(SETTINGS_PAGE_COURSES);
}

function closeCoursesPage() {
  const from = state.coursesPage && state.coursesPage.from;
  const schoolId = state.coursesPage && state.coursesPage.schoolId;
  state.coursesPage = null;
  if (from && from !== "settings" && viewAvailable(from)) {
    state.settingsPage = null;
    dropSheet();
    setView(from);
    return;
  }
  if (schoolId && connectionOf(schoolId)) state.settingsSchoolId = schoolId;
  closeSettingsPage();
}

async function loadCoursePage() {
  const page = state.coursesPage;
  if (!page) return;
  const key = page.child;
  let data = null;
  try {
    data = await getJson(`api/timetable/courses?child=${encodeURIComponent(key)}`);
  } catch (error) {
    data = null;
  }
  const current = state.coursesPage;
  if (!current || current.child !== key) return;
  if (data && Array.isArray(data.courses)) current.data = data;
  else current.failed = true;
  rerender();
}

function courseSearchText(entry) {
  return [entry.group, entry.subject_code, entry.subject_label, entry.teacher_label, entry.teacher_code, ...(entry.rooms || [])]
    .join(" ")
    .toLocaleLowerCase();
}

function courseCheck(entry, page) {
  const input = el("input", { type: "checkbox", class: "course-pick", value: entry.key });
  input.checked = page.draft.includes(entry.key);
  input.addEventListener("change", () => {
    const rest = page.draft.filter((key) => key !== entry.key);
    page.draft = input.checked ? rest.concat(entry.key) : rest;
  });
  const facts = [entry.teacher_label, (entry.rooms || []).join(", ")].filter(Boolean).join(" · ");
  const notes = [entry.new ? t("courses.page.new") : "", entry.count ? "" : t("courses.page.notSeen")].filter(Boolean).join(" · ");
  return el("label", { class: "check course-check", "data-course": entry.key }, [
    input,
    el("span", {}, [
      iservText("b", { class: "course-code" }, entry.subject_code),
      facts ? iservText("span", { class: "course-facts" }, facts) : null,
      notes ? el("small", {}, notes) : null,
    ]),
  ]);
}

function renderCourseGroups(list, entries, page) {
  const query = String(page.search || "").trim().toLocaleLowerCase();
  const shown = entries.filter((entry) => !query || courseSearchText(entry).includes(query));
  const groups = new Map();
  for (const entry of shown) {
    if (!groups.has(entry.group)) groups.set(entry.group, []);
    groups.get(entry.group).push(entry);
  }
  const blocks = [...groups.entries()].map(([group, items]) => el("section", { class: "courses-group" }, [
    el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, group)]),
    el("div", { class: "courses-rows" }, items.map((entry) => courseCheck(entry, page))),
  ]));
  list.replaceChildren(...(blocks.length ? blocks : [el("p", { class: "dlg-text" }, t("courses.page.noMatch"))]));
}

async function saveCoursePage() {
  const page = state.coursesPage;
  if (!page || !page.data || page.saving) return;
  const known = page.data.courses.map((entry) => entry.key);
  const payload = { child: page.child, chosen: page.draft, known };
  if (!page.draft.length && known.length) {
    const confirmed = await confirmAction({
      title: t("courses.page.emptyTitle"),
      text: t("courses.page.emptyText"),
      confirmLabel: t("courses.page.emptyConfirm"),
      destructive: true,
    });
    if (!confirmed || state.coursesPage !== page || page.saving) return;
    payload.confirm_empty = true;
  }
  page.saving = true;
  rerender();
  const result = await persistTo("api/timetable/courses", payload);
  page.saving = false;
  if (!result.ok && !result.handled) {
    toast(result.message || t("common.saveFailed"), "bad");
    rerender();
    return;
  }
  announceSave(result, "api.courses.saved");
  if (state.coursesPage === page) closeCoursesPage();
}

function coursesPageView() {
  const page = state.coursesPage;
  const view = el("div", { class: "courses-page" });
  if (!page) return view;
  view.append(el("h2", { class: "courses-question" }, t("courses.page.question", { name: courseChildName(page.child) })));
  if (page.failed) {
    view.append(el("p", { class: "dlg-text" }, t("courses.page.failed")));
    view.append(el("button", {
      class: "btn ghost slim courses-retry",
      type: "button",
      onclick: () => { page.failed = false; rerender(); },
    }, t("common.retry")));
    return view;
  }
  if (!page.data) {
    autoLoad(`courses:${page.child}`, loadCoursePage);
    view.append(el("div", { class: "help-preview-state" }, [el("span", { class: "spin" })]));
    return view;
  }
  const entries = page.data.courses;
  if (!entries.length) {
    view.append(el("p", { class: "dlg-text courses-empty" }, t("courses.page.empty")));
    return view;
  }
  if (!page.draft) page.draft = entries.filter((entry) => !page.data.chosen || entry.chosen).map((entry) => entry.key);
  view.append(el("p", { class: "cal-hint courses-intro" }, t("courses.page.intro")));
  const fresh = entries.filter((entry) => entry.new).length;
  if (fresh) view.append(noteBlock(tCount("courses.page.newHint", fresh)));
  const list = el("div", { class: "courses-groups" });
  if (entries.length > COURSE_SEARCH_FROM) {
    view.append(searchField(page.search, t("courses.page.search"), (value) => {
      page.search = value;
      renderCourseGroups(list, entries, page);
    }));
  }
  renderCourseGroups(list, entries, page);
  view.append(list);
  const save = el("button", {
    class: "btn courses-save",
    type: "button",
    disabled: page.saving ? "disabled" : null,
    onclick: saveCoursePage,
  }, page.saving ? [el("span", { class: "spin" }), t("common.saving")] : t("common.save"));
  view.append(el("div", { class: "btn-stack courses-actions" }, [save]));
  return view;
}

const HA_INSTALL_URL = "https://my.home-assistant.io/redirect/hacs_repository/?owner=githuber110&repository=ranzenpost&category=integration";

let haStatusRequest = 0;

async function loadHaStatus(force) {
  if (state.haStatusLoading && !force) return;
  haStatusRequest += 1;
  const request = haStatusRequest;
  state.haStatusLoading = true;
  let loaded;
  try {
    loaded = { data: await getJson("api/integration-status"), error: false };
  } catch (error) {
    loaded = { data: null, error: true };
  }
  if (request !== haStatusRequest) return;
  state.haStatus = loaded;
  state.haStatusLoading = false;
  rerender();
}

function haRowValue() {
  const loaded = state.haStatus && state.haStatus.data;
  if (!loaded) return "";
  if (pendingUpdates().length) return t("settings.ha.status.update");
  return t(loaded.connected ? "settings.ha.status.connected" : "settings.ha.status.disconnected");
}

const UPDATE_STEPS = ["app", "integration", "restart"];

function pendingUpdates() {
  const data = state.haStatus && state.haStatus.data;
  const listed = data && Array.isArray(data.updates) ? data.updates : [];
  return UPDATE_STEPS.filter((step) => listed.includes(step));
}

function ensureHaStatus() {
  if (state.haStatus === null && !state.haStatusLoading) loadHaStatus();
}

const HA_REPAIRS_PATH = "/config/repairs";
const HA_REPAIRS_REDIRECT = "https://my.home-assistant.io/redirect/repairs/";
const HA_UPDATES_PATH = "/config/updates";
const HA_UPDATES_REDIRECT = "https://my.home-assistant.io/redirect/updates/";
const HA_APP_PATH = "/hassio/addon/";
const HA_APP_REDIRECT = "https://my.home-assistant.io/redirect/supervisor_addon/?addon=";
const APP_SLUG_PATTERN = /^[a-z0-9_]+$/;

function embeddedInHomeAssistant() {
  try {
    return window.self !== window.top;
  } catch (error) {
    return true;
  }
}

function homeAssistantLink(path, redirect, label, className) {
  if (embeddedInHomeAssistant()) return el("a", { class: className, href: path, target: "_top" }, label);
  return el("a", { class: className, href: redirect, target: "_blank", rel: "noopener" }, [externalIcon(18), label]);
}

function integrationTarget(data, step) {
  const installed = String(data.integration_installed || "");
  const loaded = String(data.integration_version || "");
  const restartPending = pendingUpdates().includes("restart");
  return step === "restart" || !restartPending ? loaded : installed || loaded;
}

function appUpdateNotice() {
  const data = state.haStatus && state.haStatus.data;
  if (!data) return null;
  const app = String(data.app_version || state.appVersion || "");
  const store = data.app_update && typeof data.app_update === "object" ? data.app_update : {};
  if (store.state === "newer" && store.latest) {
    const slug = APP_SLUG_PATTERN.test(String(store.slug || "")) ? String(store.slug) : "";
    return { kind: "store", app, latest: String(store.latest), slug };
  }
  if (pendingUpdates().includes("app")) return { kind: "repair", app, integration: integrationTarget(data, "app") };
  return null;
}

function appUpdateTitle(notice) {
  return notice.kind === "store" ? t("settings.update.store.title", { latest: notice.latest }) : t("settings.update.app.title");
}

function appUpdateText(notice) {
  if (notice.kind === "store") return t("settings.update.store.text", { app: notice.app, latest: notice.latest });
  return t("settings.update.app.text", { app: notice.app, integration: notice.integration, installed: "" });
}

function appUpdateButton(notice, className) {
  if (notice.kind === "repair") {
    return homeAssistantLink(HA_REPAIRS_PATH, HA_REPAIRS_REDIRECT, t("settings.update.app.open"), ["btn", className, "update-open-repairs"].filter(Boolean).join(" "));
  }
  const path = notice.slug ? `${HA_APP_PATH}${notice.slug}/info` : HA_UPDATES_PATH;
  const redirect = notice.slug ? `${HA_APP_REDIRECT}${notice.slug}` : HA_UPDATES_REDIRECT;
  return homeAssistantLink(path, redirect, t("settings.update.store.open"), ["btn", className, "update-open-app"].filter(Boolean).join(" "));
}

function updateStepText(step, data) {
  const app = String(data.app_version || state.appVersion || "");
  const integration = integrationTarget(data, step);
  const installed = String(data.integration_installed || "");
  if (step === "integration" && !integration) return t("settings.update.integration.older", { app });
  return t(`settings.update.${step}.text`, { app, integration, installed });
}

function appUpdateStep(notice) {
  return el("div", { class: "update-step update-app" }, [
    el("b", { class: "update-title" }, appUpdateTitle(notice)),
    el("p", { class: "update-text" }, appUpdateText(notice)),
    appUpdateButton(notice, "slim"),
  ]);
}

function updateHintBlock(withoutApp) {
  const notice = withoutApp ? null : appUpdateNotice();
  const steps = pendingUpdates().filter((step) => step !== "app");
  if (!notice && !steps.length) return null;
  const data = state.haStatus.data;
  const blocks = steps.map((step) => el("div", { class: `update-step update-${step}` }, [
    el("b", { class: "update-title" }, t(`settings.update.${step}.title`)),
    el("p", { class: "update-text" }, updateStepText(step, data)),
  ]));
  if (notice) blocks.unshift(appUpdateStep(notice));
  return el("section", { class: "update-hint", role: "status" }, blocks);
}

function appUpdateBanner() {
  ensureHaStatus();
  const notice = appUpdateNotice();
  if (!notice) return null;
  const text = notice.kind === "store"
    ? t("overview.update.store", { app: notice.app, latest: notice.latest })
    : t("overview.update.app", { app: notice.app, integration: notice.integration });
  return el("div", { class: "update-notice", role: "status" }, [el("div", { class: "update-notice-row" }, [
    el("span", { class: "update-notice-text" }, text),
    appUpdateButton(notice, "slim"),
  ])]);
}

function helpUpdateWarning(notice) {
  return el("section", { class: "update-hint help-update-first", role: "status" }, [
    el("div", { class: "update-step update-app" }, [
      el("b", { class: "update-title" }, appUpdateTitle(notice)),
      el("p", { class: "update-text" }, t("help.update.first")),
      appUpdateButton(notice, ""),
    ]),
  ]);
}

async function openHomeAssistantSheet() {
  state.haStatus = null;
  state.haBusy = false;
  openSheet(homeAssistantSheet);
  await loadHaStatus(true);
}

function homeAssistantSheet() {
  const body = [el("p", { class: "cal-hint" }, t("settings.ha.text"))];
  const loaded = state.haStatus;
  if (!loaded) body.push(loadingBlock());
  else if (loaded.error || !loaded.data) body.push(plainCard(t("settings.ha.loadFailed")));
  else {
    body.push(haStatusBlock(loaded.data));
    const hint = updateHintBlock();
    if (hint) body.push(hint);
    body.push(haTokenBlock(loaded.data));
  }
  body.push(haInstallBlock());
  return sheet(t("settings.ha.sheet"), body);
}

function haStatusBlock(data) {
  const connected = !!data.connected;
  const block = el("div", { class: connected ? "ha-status connected" : "ha-status" }, [
    el("div", { class: "ha-status-line" }, [
      el("span", { class: "ha-status-dot", "aria-hidden": "true" }),
      el("b", {}, t(connected ? "settings.ha.status.connected" : "settings.ha.status.disconnected")),
    ]),
  ]);
  if (data.last_request) {
    block.append(el("span", { class: "ha-status-time" }, t("settings.ha.status.lastRequest", { time: formatIsoMoment(data.last_request) })));
  } else {
    block.append(el("span", { class: "ha-status-hint" }, t("settings.ha.status.never")));
  }
  return block;
}

function haTokenBlock(data) {
  const token = data.token || "";
  const input = el("input", {
    class: "inp ha-token",
    type: "password",
    value: token,
    readonly: "readonly",
    dir: "ltr",
    spellcheck: "false",
    autocomplete: "off",
    "aria-label": t("settings.ha.token"),
  });
  input.addEventListener("focus", () => input.select());
  const reveal = el("button", { class: "btn ghost slim ha-reveal", type: "button", "aria-pressed": "false" }, t("settings.ha.token.reveal"));
  reveal.addEventListener("click", () => {
    const shown = input.getAttribute("type") === "password";
    input.setAttribute("type", shown ? "text" : "password");
    reveal.setAttribute("aria-pressed", String(shown));
  });
  const copy = el("button", { class: "btn ghost slim ha-copy", type: "button" }, [icon("clip", 16), t("settings.ha.token.copy")]);
  copy.addEventListener("click", async () => {
    const copied = await copyToClipboard(token);
    toast(t(copied ? "settings.ha.token.copied" : "settings.ha.token.copyFailed"), copied ? "good" : "bad");
  });
  const rotate = el("button", {
    class: "btn ghost slim ha-rotate",
    type: "button",
    disabled: state.haBusy ? "disabled" : null,
    onclick: rotateIntegrationToken,
  }, state.haBusy ? [el("span", { class: "spin" }), t("settings.ha.rotate")] : [t("settings.ha.rotate")]);
  return el("div", { class: "ha-token-block" }, [
    el("span", { class: "overline" }, t("settings.ha.token")),
    input,
    el("div", { class: "cal-action-row" }, [reveal, copy, rotate]),
    el("p", { class: "cal-hint" }, t("settings.ha.token.hint")),
  ]);
}

function haConnected() {
  return !!(state.haStatus && state.haStatus.data && state.haStatus.data.connected);
}

function haInstallBlock() {
  const kind = haConnected() ? "btn ghost ha-install" : "btn ha-install";
  return el("div", { class: "ha-install-block" }, [
    el("a", { class: kind, href: HA_INSTALL_URL, target: "_blank", rel: "noopener" }, [externalIcon(18), t("settings.ha.install")]),
    el("p", { class: "cal-hint" }, t("settings.ha.install.hint")),
  ]);
}

async function rotateIntegrationToken() {
  if (state.haBusy) return;
  const ok = await confirmAction({
    title: t("settings.ha.rotate.title"),
    text: t("settings.ha.rotate.text"),
    confirmLabel: t("settings.ha.rotate.confirm"),
    destructive: true,
  });
  openSheet(homeAssistantSheet);
  if (!ok) return;
  state.haBusy = true;
  rerender();
  let result = null;
  try {
    result = await postJson("api/integration-status/rotate", {});
  } catch (error) {
    result = null;
  }
  state.haBusy = false;
  if (!result || result.ok === false) {
    rerender();
    toast(apiMessage(result, "settings.ha.rotate.failed"), "bad");
    return;
  }
  state.haStatus = null;
  await loadHaStatus(true);
  toast(apiMessage(result, "api.integration.token.rotated"));
}


const DISCONNECT_TIMEOUT_MS = 90000;
const PASSWORD_TIMEOUT_MS = 120000;

function disconnectTokens(result) {
  return Array.isArray(result && result.tokens) ? result.tokens.filter((token) => token && typeof token.id === "string" && token.id) : [];
}

function tokenOption(token, finish) {
  return el("button", { class: "opt token-choice", type: "button", onclick: () => finish({ token: token.id }) }, [
    el("span", {}, [
      el("b", { dir: "auto" }, token.name || token.id),
      token.created ? el("small", { dir: "auto" }, t("settings.disconnect.created", { date: token.created })) : null,
    ]),
  ]);
}

function askTokenRetry(result) {
  const tokens = disconnectTokens(result);
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      dropSheet();
      rerender();
      resolve(value);
    };
    const actions = [];
    if (!tokens.length && result.retryable) {
      actions.push(el("button", { class: "btn token-retry", type: "button", onclick: () => finish({}) }, t("common.retry")));
    }
    actions.push(el("button", { class: "btn ghost token-force", type: "button", onclick: () => finish({ force: true }) }, t("settings.disconnect.force")));
    const body = [el("p", { class: "dlg-text" }, apiMessage(result, "settings.disconnect.failed"))];
    if (tokens.length) body.push(el("div", { class: "opt-list token-choices" }, tokens.map((token) => tokenOption(token, finish))));
    openSheet(
      () => sheet(t(tokens.length ? "settings.disconnect.chooseTitle" : "settings.disconnect.retryTitle"), body, [el("div", { class: "btn-stack" }, actions)]),
      () => finish(null)
    );
  });
}

function showDisconnecting() {
  openSheet(() => sheet(t("settings.disconnect.title"), [
    el("p", { class: "dlg-text disconnect-progress", role: "status" }, [el("span", { class: "spin" }), t("settings.disconnect.running")]),
  ], []));
}

async function disconnectStateAfterTimeout(connectionId) {
  const config = await getJson("api/config");
  const listed = Array.isArray(config && config.connections) ? config.connections.filter((entry) => entry && entry.id) : [];
  const still = connectionId ? listed.some((entry) => entry.id === connectionId) : listed.length > 0;
  if (!still) return { disconnected: true, attempted: false, removed: false, message_key: "settings.disconnect.done" };
  return { disconnected: false, attempted: true, removed: false, retryable: true, message_key: "settings.disconnect.unclear" };
}

async function disconnectRequest(path, body, connectionId) {
  showDisconnecting();
  try {
    return await postJson(path, body, DISCONNECT_TIMEOUT_MS);
  } catch (error) {
    return await disconnectStateAfterTimeout(connectionId);
  } finally {
    dropSheet();
    rerender();
  }
}

async function disconnectWithRetry(path, body, connectionId) {
  let extra = {};
  for (;;) {
    const result = await disconnectRequest(path, Object.assign({}, body, extra), connectionId);
    if (!result || result.disconnected !== false) return result;
    const choice = await askTokenRetry(result);
    if (!choice) return result;
    extra = choice.force ? { force: true } : choice.token ? { token_id: choice.token } : {};
  }
}

function disconnectGood(result) {
  return !result || result.removed === true || !result.attempted;
}

async function disconnectAccount() {
  const ok = await confirmAction({
    title: t("settings.disconnect.title"),
    text: t("settings.disconnect.text"),
    confirmLabel: t("settings.disconnect.confirm"),
    destructive: true,
  });
  if (!ok) return;
  let message = t("settings.disconnect.done");
  let good = true;
  try {
    const result = await disconnectWithRetry("api/account/disconnect", { connection_id: editingConnectionId() }, editingConnectionId());
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
  window.setTimeout(boot, 900);
}

function meTechEntries() {
  const me = state.me || {};
  return [
    { label: t("settings.user.tech.id"), value: me.id, kind: "text" },
    { label: t("settings.user.tech.surname"), value: me.surname, kind: "text" },
    { label: t("settings.user.tech.username"), value: me.username, kind: "text" },
    { label: t("settings.user.tech.email"), value: me.email, kind: "text" },
    { label: t("settings.user.tech.externalId"), value: me.external_id, kind: "text" },
    { label: t("settings.user.tech.active"), value: me.is_active, kind: "bool" },
    { label: t("settings.user.tech.activated"), value: me.is_activated, kind: "bool" },
    { label: t("settings.user.tech.reRegistration"), value: me.needs_re_registration, kind: "bool" },
    { label: t("settings.user.tech.inPreparation"), value: me.in_preparation, kind: "bool" },
    { label: t("settings.user.tech.webUser"), value: me.is_web_user, kind: "bool" },
    { label: t("settings.user.tech.guardian"), value: me.is_guardian, kind: "bool" },
    { label: t("settings.user.tech.mainTeacher"), value: me.is_main_teacher, kind: "bool" },
    { label: t("settings.user.tech.roles"), value: (me.roles || []).join(", "), kind: "text" },
    { label: t("settings.user.tech.emailNotify"), value: me.is_notified_by_email, kind: "bool" },
    { label: t("settings.user.tech.serialPrint"), value: me.is_receiver_of_serial_print, kind: "bool" },
    { label: t("settings.user.tech.newsletter"), value: me.is_newsletter_receiver, kind: "bool" },
    { label: t("settings.user.tech.devices"), value: me.has_active_devices, kind: "bool" },
    { label: t("settings.user.tech.twoFactor"), value: me.has_2nd_factor_active, kind: "bool" },
    { label: t("settings.user.tech.parentPin"), value: me.has_restricted_access_pin, kind: "bool" },
    { label: t("settings.user.tech.createdAt"), value: me.created_at, kind: "epoch" },
    { label: t("settings.user.tech.updatedAt"), value: me.updated_at, kind: "epoch" },
    { label: t("settings.user.tech.schoolName"), value: me.school_name, kind: "text" },
    { label: t("settings.user.tech.schoolAddress"), value: me.school_address, kind: "text" },
  ];
}

function usablePeriodTimes(times) {
  return times && typeof times === "object" && Object.keys(times).length ? times : null;
}

function schoolPeriodTimes(id) {
  const target = id || editingConnectionId();
  const many = manySchools();
  const current = currentChild();
  if (!many || (current && schoolOfChild(current) === target)) {
    const own = usablePeriodTimes(state.timetable && state.timetable.school_period_times);
    if (own) return own;
  }
  for (const child of state.children) {
    if (many && schoolOfChild(child) !== target) continue;
    const week = overviewWeekData(child.key, 0);
    const times = usablePeriodTimes(week && week.school_period_times);
    if (times) return times;
  }
  return {};
}

function customPeriodNumbers(times, school) {
  return Object.keys(times || {})
    .filter((key) => times[key] && times[key] !== school[key])
    .map(Number)
    .filter((number) => Number.isInteger(number) && number >= 0)
    .sort((a, b) => a - b);
}

function periodTimesLabel(config, id) {
  const school = schoolPeriodTimes(id);
  if (!Object.keys(school).length) return tCount("settings.periods.count", Object.keys(config.period_times || {}).length);
  return t(customPeriodNumbers(config.period_times, school).length ? "settings.periods.custom" : "settings.periods.asIserv");
}

function themeLabel(value) {
  return t(`settings.theme.${THEMES.includes(value) ? value : DEFAULT_THEME}.label`);
}

function themeSheet() {
  return sheet(t("settings.theme.sheet"), [
    el("div", { class: "opt-list" }, THEMES.map((key) =>
      el("button", {
        class: "opt",
        type: "button",
        "aria-pressed": String(state.theme === key),
        onclick: () => { setTheme(key); closeSheet(); },
      }, [el("span", {}, [el("b", {}, t(`settings.theme.${key}.label`)), el("small", {}, t(`settings.theme.${key}.hint`))])])
    )),
  ]);
}

function holidayRegionValueLabel() {
  const code = editingConfig().holiday_region || "";
  if (!code) return t("holidays.settings.off");
  const name = holidayRegionLabel(code) || code;
  const box = holidayBox(editingConnectionId());
  if (box && box.status === HOLIDAY_STATUS_UNKNOWN) {
    return t("holidays.settings.valueUnknown", { region: name });
  }
  return name;
}

function holidaySortedRegions(regions, suggestion) {
  const list = regions.slice().sort((a, b) =>
    holidayRegionOptionLabel(a).localeCompare(holidayRegionOptionLabel(b), currentLanguage())
  );
  const hit = suggestion ? list.find((region) => region.code === suggestion) : null;
  if (!hit) return list;
  return [hit].concat(list.filter((region) => region.code !== suggestion));
}

function holidayRegionOption(region, current, suggestion) {
  const code = region.code || "";
  const suggested = !!code && code === suggestion && !current;
  const info = state.holidaySuggestion;
  const inner = [el("b", {}, code ? holidayRegionOptionLabel(region) : t("holidays.settings.off"))];
  if (suggested && info && info.origin_key && hasMessage(info.origin_key)) {
    inner.push(el("small", {}, t(info.origin_key)));
  }
  return el("button", {
    class: suggested ? "opt suggested" : "opt",
    type: "button",
    "aria-pressed": String(code === current),
    onclick: () => { closeSheet(); selectHolidayRegion(code); },
  }, [
    el("span", {}, inner),
    suggested ? el("span", { class: "opt-badge" }, t("holidays.suggestion.label")) : null,
  ]);
}

function holidayRegionSheet() {
  if (state.holidayRegions === null) autoLoad("holidayRegions", loadHolidayRegions);
  if (state.holidaySuggestion === null) autoLoad("holidaySuggestion", loadHolidaySuggestion);
  const current = editingConfig().holiday_region || "";
  const regions = state.holidayRegions || [];
  const suggestion = current ? "" : holidaySuggestionCode();
  const rows = [holidayRegionOption({ code: "" }, current, suggestion)];
  for (const region of holidaySortedRegions(regions, suggestion)) {
    rows.push(holidayRegionOption(region, current, suggestion));
  }
  const body = [el("p", { class: "dlg-text holiday-lead" }, t("holidays.settings.hint"))];
  if (suggestion) body.push(el("p", { class: "dlg-text holiday-lead" }, t("holidays.suggestion.confirm")));
  body.push(el("div", { class: "opt-list" }, rows));
  if (!regions.length) body.push(loadingBlock());
  body.push(el("p", { class: "sheet-hint" }, t("holidays.source")));
  return sheet(t("holidays.settings.sheet"), body);
}

async function selectHolidayRegion(code) {
  const config = editingConfig();
  if ((config.holiday_region || "") === (code || "")) return;
  const result = await persistConnection(editingConnectionId(), { holiday_region: code || "" });
  if (result.ok) await loadHolidays();
  announceSave(result);
}

function languageLabel(choice) {
  const value = LANGUAGE_CHOICES.includes(choice) ? choice : "system";
  return t(`language.${value}`);
}

function languageSheet() {
  const current = currentLanguageChoice();
  return sheet(t("settings.language.sheet"), [
    el("div", { class: "opt-list" }, LANGUAGE_CHOICES.map((key) =>
      el("button", {
        class: "opt",
        type: "button",
        lang: key === "system" ? null : key,
        "aria-pressed": String(current === key),
        onclick: () => { closeSheet(); selectLanguage(key); },
      }, [
        el("span", {}, [
          el("b", {}, t(`language.${key}`)),
          key === "system" ? el("small", {}, t("language.system.hint")) : null,
        ]),
      ])
    )),
  ]);
}

async function selectLanguage(choice) {
  if (choice === currentLanguageChoice()) return;
  await applyLanguageChoice(choice);
  render();
  if (!state.config) return;
  state.config.language = currentLanguageChoice();
  const result = await persistConfig();
  rememberLanguageChoice(currentLanguageChoice(), !!(result.ok || result.handled));
  if (!result.ok && !result.handled) toast(result.message, "bad");
}

function notifyOptions() {
  return (state.notifyServices || [])
    .map((entry) => (typeof entry === "string" ? { service: entry, name: null, category: null } : entry))
    .filter((entry) => entry && typeof entry.service === "string" && entry.service);
}

function notifyOption(service) {
  return notifyOptions().find((entry) => entry.service === service) || null;
}

function notifyName(service) {
  const entry = notifyOption(service);
  return entry && entry.name ? entry.name : "";
}

function notifyLabel(service) {
  return notifyName(service) || service;
}

function notifyServicesSummaryLabel(services) {
  const list = services || [];
  if (!list.length) return t("settings.notify.summary.none");
  if (list.length === 1) return notifyLabel(list[0]);
  return t("settings.notify.summary.more", {
    name: notifyLabel(list[0]),
    count: formatNumber(list.length - 1),
  });
}

function settingRow(label, value, onclick, variant, page) {
  const base = variant ? `setting-row ${variant}` : "setting-row";
  return el("button", { class: page ? openRowClass(base, "settings-page", page) : base, type: "button", onclick }, [
    el("span", { class: "lbl" }, label),
    value ? el("span", { class: "val" }, value) : null,
    el("span", { class: "chev" }, [icon("chevron", 16)]),
  ]);
}

function saveSheet(apply) {
  const button = el("button", { class: "btn", type: "button" }, t("common.save"));
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.saving")));
    const patch = apply();
    const result = patch && typeof patch === "object" ? await persistConnection(editingConnectionId(), patch) : await persistConfig();
    resetSheetForm();
    closeSheet();
    announceSave(result);
  });
  return button;
}

const GLOBAL_CONFIG_KEYS = ["language", "notify_services", "notify_events", "reported_modules", "modules_card_hidden"];

function globalConfigPayload() {
  const config = state.config || {};
  const payload = {};
  for (const key of GLOBAL_CONFIG_KEYS) {
    if (key in config) payload[key] = config[key];
  }
  return payload;
}

async function persistTo(path, payload) {
  const outcome = await postJsonSafe(path, payload, "common.saveFailed");
  if (!outcome.ok) return outcome;
  state.timetable = null;
  state.overviewWeeks = {};
  state.overviewWeekMondays = {};
  state.absence = null;
  try {
    state.config = await getJson("api/config");
  } catch (error) {
    if (handleApiFailure(error)) return { ok: false, handled: true };
    return { ok: true, message: t("settings.save.reloadFailed"), reloadFailed: true };
  }
  reloadTimetable();
  return { ok: true };
}

function announceSave(result, savedKey = "common.saved") {
  if (result.handled) return;
  toast(result.message || t(savedKey), result.ok && !result.reloadFailed ? "good" : "bad");
}

async function persistConfig() {
  return persistTo("api/config", globalConfigPayload());
}

async function persistConnection(id, patch) {
  const target = id || editingConnectionId();
  const entry = connectionOf(target);
  if (entry) Object.assign(entry, patch);
  return persistTo(`api/connections/${encodeURIComponent(target)}`, patch);
}

function phonesRowIsHalfFilled(entry) {
  const hasLabel = !!(entry.label && entry.label.trim());
  const hasNumber = !!(entry.number && entry.number.trim());
  return hasLabel !== hasNumber;
}

function phonesRowIsEmpty(entry) {
  return !(entry.label && entry.label.trim()) && !(entry.number && entry.number.trim());
}

function phonesSheet() {
  const phones = sheetState(() => copy(Array.isArray(editingConfig().phones) ? editingConfig().phones : []));
  const host = el("div", { class: "phones-list" });
  const err = el("div", { class: "err", style: "margin:0 0 8px" }, "");
  const save = el("button", { class: "btn phones-save", type: "button" }, t("common.save"));
  const syncSave = () => {
    save.disabled = !isSheetFormDirty();
  };
  const draw = () => {
    const group = el("div", { class: "field-group" });
    phones.forEach((row, index) => {
      const label = iservText("input", {
        class: "inp",
        type: "text",
        value: row.label || "",
        placeholder: t("common.phone.label"),
        autocomplete: "organization",
        "aria-label": t("common.phone.label"),
      });
      label.addEventListener("input", () => { row.label = label.value; err.textContent = ""; syncSave(); });
      const number = iservText("input", {
        class: "inp",
        type: "tel",
        inputmode: "tel",
        autocomplete: "tel",
        value: row.number || "",
        placeholder: t("common.phone.number"),
        "aria-label": t("common.phone.number"),
      });
      number.addEventListener("input", () => { row.number = number.value; err.textContent = ""; syncSave(); });
      const remove = el("button", {
        class: "btn ghost slim",
        type: "button",
        onclick: () => { phones.splice(index, 1); draw(); },
      }, [icon("trash", 16), t("settings.phones.remove")]);
      group.append(el("div", { class: "cell stack" }, [label, number, remove]));
    });
    host.replaceChildren(phones.length ? group : el("p", { class: "cal-hint phones-empty" }, t("settings.phones.empty")));
    syncSave();
  };
  draw();
  save.addEventListener("click", async () => {
    if (phones.some(phonesRowIsHalfFilled)) {
      err.textContent = t("settings.phones.error");
      return;
    }
    save.disabled = true;
    save.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.saving")));
    const result = await persistConnection(editingConnectionId(), { phones: phones.filter((entry) => !phonesRowIsEmpty(entry)) });
    resetSheetForm();
    closeSheet();
    announceSave(result);
  });
  return sheet(t("settings.phones.sheet"), [
    el("p", { class: "dlg-text" }, t("settings.phones.text")),
    host,
    el("button", { class: "btn ghost phones-add", type: "button", onclick: () => { phones.push({ label: "", number: "" }); draw(); } }, [icon("plus", 16), t("settings.phones.add")]),
    err,
  ], [save]);
}

const NOTIFY_EVENTS = [
  ["timetable", "settings.notify.event.timetable"],
  ["letters", "settings.notify.event.letters"],
  ["pinboard", "settings.notify.event.pinboard"],
  ["conferences", "settings.notify.event.conferences"],
  ["conference_booking_open", "settings.notify.event.conferenceBookingOpen"],
  ["conference_cancelled", "settings.notify.event.conferenceCancelled"],
  ["conference_reminder", "settings.notify.event.conferenceReminder"],
  ["conference_booking_reminder", "settings.notify.event.conferenceBookingReminder"],
  ["messenger", "settings.notify.event.messenger"],
  ["tasks", "settings.notify.event.tasks"],
  ["news", "settings.notify.event.news"],
  ["forums", "settings.notify.event.forums"],
  ["texts", "settings.notify.event.texts"],
  ["outage", "settings.notify.event.outage"],
];

const NOTIFY_EVENT_MODULES = {
  conference_booking_open: "conferences",
  conference_cancelled: "conferences",
  conference_reminder: "conferences",
  conference_booking_reminder: "conferences",
};

function notifyEvents() {
  return NOTIFY_EVENTS.filter(([key]) => moduleOn(NOTIFY_EVENT_MODULES[key] || key));
}

const NOTIFY_CATEGORY_ORDER = ["mobile", "group", "other"];

const NOTIFY_CATEGORY_KEYS = {
  mobile: "settings.notify.category.mobile",
  group: "settings.notify.category.group",
  other: "settings.notify.category.other",
};

function notifyCategoryKey(category) {
  return NOTIFY_CATEGORY_KEYS[category] || NOTIFY_CATEGORY_KEYS.other;
}

function notifySectionHead(key) {
  return el("div", { class: "section-head notify-head" }, [el("span", { class: "overline" }, t(key))]);
}

const NOTIFY_SEARCH_THRESHOLD = 6;

function notifyPickerSheet(draft, options, testButton, onChange) {
  let query = "";
  const listHost = el("div", {});
  const hitCount = el("span", { class: "search-hits" });
  const matches = (entry) => {
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return `${entry.name || ""} ${entry.service}`.toLowerCase().includes(needle);
  };
  const drawList = () => {
    const shown = options.filter(matches);
    hitCount.textContent = query.trim() ? tCount("common.hits", shown.length) : "";
    if (!shown.length) {
      listHost.replaceChildren(emptyBlock("search", t("settings.notify.picker.emptyTitle"), t("settings.notify.picker.emptyText")));
      return;
    }
    const blocks = [];
    for (const category of NOTIFY_CATEGORY_ORDER) {
      const entries = shown.filter((entry) => (entry.category || "other") === category);
      if (!entries.length) continue;
      blocks.push(notifySectionHead(notifyCategoryKey(category)));
      blocks.push(el("div", { class: "field-group notify-services-group", "data-category": category },
        entries.map((entry) => {
          const label = entry.name || entry.service;
          const check = el("input", { type: "checkbox" });
          check.checked = draft.services.includes(entry.service);
          check.addEventListener("change", () => {
            draft.services = check.checked
              ? draft.services.concat(entry.service).filter((value, index, all) => all.indexOf(value) === index)
              : draft.services.filter((value) => value !== entry.service);
            onChange();
          });
          return el("div", { class: "cell notify-row" }, [
            el("label", { class: "check notify-pick" }, [
              check,
              el("span", { class: "notify-text" }, [
                iservText("b", {}, label),
                entry.name ? el("small", { class: "notify-id", dir: "ltr" }, entry.service) : null,
              ]),
            ]),
            testButton(entry.service, label),
          ]);
        })
      ));
    }
    listHost.replaceChildren(...blocks);
  };
  drawList();
  const body = [];
  if (options.length >= NOTIFY_SEARCH_THRESHOLD) {
    body.push(searchField("", t("settings.notify.picker.search"), (value) => {
      query = value;
      drawList();
    }, hitCount));
  }
  body.push(listHost);
  return sheet(t("settings.notify.picker.sheet"), body);
}

function notifySheet() {
  const draft = sheetState(() => ({
    services: copy(state.config.notify_services || []),
    events: copy(state.config.notify_events || {}),
    testing: null,
  }));
  const options = notifyOptions().filter((entry) => entry.category !== "persistent");
  const supervisorKnown = state.notifySupervisor !== null;
  const supervisorOk = state.notifySupervisor === true;

  const toggleService = (value, checked) => {
    draft.services = checked
      ? draft.services.concat(value).filter((entry, index, all) => all.indexOf(entry) === index)
      : draft.services.filter((entry) => entry !== value);
  };

  const testButton = (service, label) => {
    const button = el("button", {
      class: "btn ghost slim notify-test",
      type: "button",
      "aria-label": t("settings.notify.test.label", { name: label }),
    }, t("settings.notify.test"));
    const busy = () => {
      button.disabled = true;
      button.replaceChildren(el("span", { class: "spin" }));
    };
    const ready = () => {
      button.disabled = false;
      button.replaceChildren(document.createTextNode(t("settings.notify.test")));
    };
    if (draft.testing === service) busy();
    button.addEventListener("click", async () => {
      if (draft.testing) return;
      draft.testing = service;
      busy();
      let result = null;
      try {
        result = await postJson("api/notify-test", { service, language: currentLanguage() });
      } catch (error) {
        result = null;
      }
      draft.testing = null;
      ready();
      if (result === null) {
        toast(t("settings.notify.testUnreachable"), "bad");
        return;
      }
      toast(apiMessage(result, "api.notify.failed"), result.ok ? "good" : "bad");
    });
    return button;
  };

  const chipsHost = el("div", { class: "chipbar notify-chips" });
  const eventChecks = [];
  const eventGroup = el("div", { class: "field-group notify-events" });
  const eventHint = el("p", { class: "cal-hint notify-events-hint" }, t("settings.notify.events.needDevice"));
  const syncEvents = () => {
    const off = !draft.services.length;
    eventGroup.classList.toggle("off", off);
    eventHint.hidden = !off;
    for (const check of eventChecks) check.disabled = off;
  };
  const drawChips = () => {
    syncEvents();
    if (!draft.services.length) {
      chipsHost.replaceChildren(el("p", { class: "dlg-text notify-empty" }, t("settings.notify.targets.empty")));
      return;
    }
    chipsHost.replaceChildren(...draft.services.map((service) => {
      const label = notifyLabel(service);
      return el("button", {
        class: "chip notify-chip",
        type: "button",
        "aria-label": t("settings.notify.targets.remove", { name: label }),
        onclick: () => {
          toggleService(service, false);
          drawChips();
        },
      }, [iservText("span", {}, label), el("span", { class: "ico-slot", html: iconSvg("close", 14) })]);
    }));
  };
  drawChips();

  const openPicker = () => openNestedSheet(() => notifyPickerSheet(draft, options, testButton, drawChips));
  const pickButton = el("button", {
    class: "btn ghost slim notify-pick-open",
    type: "button",
    disabled: options.length ? null : "disabled",
    onclick: openPicker,
  }, [icon("plus", 16), t("settings.notify.targets.add")]);

  let emptyHint = null;
  if (!supervisorKnown) {
    emptyHint = el("div", { class: "note" }, [
      el("span", { class: "spin" }),
      el("span", {}, t("settings.notify.checking")),
      retryButton(() => { state.notifyServices = []; loadNotifyServices(); }),
    ]);
  } else if (!supervisorOk) emptyHint = el("p", { class: "dlg-text" }, t("settings.notify.noSupervisor"));
  else if (!options.length) emptyHint = el("p", { class: "dlg-text" }, t("settings.notify.noTargets"));

  const body = [
    notifySectionHead("settings.notify.targets"),
    chipsHost,
    pickButton,
    emptyHint,
    notifySectionHead("settings.notify.events"),
    eventHint,
    eventGroup,
  ];
  eventGroup.append(...notifyEvents().map(([key, label]) => {
    const check = el("input", { type: "checkbox" });
    check.checked = draft.events[key] !== false;
    check.addEventListener("change", () => { draft.events[key] = check.checked; });
    eventChecks.push(check);
    return el("label", { class: "cell check" }, [check, el("span", {}, t(label))]);
  }));
  syncEvents();
  return sheet(t("settings.notify.sheet"), body, [saveSheet(() => {
    state.config.notify_services = draft.services;
    state.config.notify_events = draft.events;
  })]);
}

function passwordSheet() {
  const draft = sheetState(() => ({ current: "", next: "", repeat: "" }));
  const account = el("input", {
    class: "visually-hidden",
    type: "text",
    name: "username",
    autocomplete: "username",
    dir: "ltr",
    value: (schoolSummary(editingConnectionId()) || {}).username || state.account || "",
    readonly: "readonly",
    tabindex: "-1",
    "aria-hidden": "true",
  });
  const field = (key, label, complete) => {
    const input = el("input", {
      class: "inp",
      type: "password",
      name: key === "current" ? "current-password" : "new-password",
      autocomplete: complete,
      value: draft[key],
      "aria-label": label,
    });
    input.addEventListener("input", () => { draft[key] = input.value; hint.textContent = ""; });
    return { input, node: el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]) };
  };
  const hint = el("span", { class: "err", style: "display:block;margin:-8px 0 16px" }, "");
  const current = field("current", t("settings.password.current"), "current-password");
  const next = field("next", t("settings.password.new"), "new-password");
  const repeat = field("repeat", t("settings.password.repeat"), "new-password");
  const button = el("button", { class: "btn", type: "submit" }, t("settings.password.submit"));
  const form = el("form", { class: "stack-form" }, [
    account,
    current.node,
    next.node,
    repeat.node,
    hint,
  ]);
  const run = async () => {
    if (draft.next !== draft.repeat) {
      hint.textContent = t("settings.password.mismatch");
      return;
    }
    if (!draft.current || !draft.next) {
      hint.textContent = t("settings.password.incomplete");
      return;
    }
    button.disabled = true;
    button.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.changing")));
    try {
      const result = await postJson("api/password", { current: draft.current, new: draft.next, connection_id: editingConnectionId() }, PASSWORD_TIMEOUT_MS);
      if (result && (result.ok || result.uncertain)) {
        resetSheetForm();
        closeSheet();
        toast(apiMessage(result, "settings.password.done"), result.ok ? "good" : "bad");
        return;
      }
      toast(apiMessage(result, "settings.password.failed"), "bad");
    } catch (error) {
      if (isTimeoutError(error)) {
        resetSheetForm();
        closeSheet();
        toast(t("settings.password.unclear"), "bad");
        return;
      }
      toast(t("settings.password.failed"), "bad");
    }
    button.disabled = false;
    button.replaceChildren(document.createTextNode(t("settings.password.submit")));
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); run(); });
  button.addEventListener("click", (event) => { event.preventDefault(); run(); });
  return sheet(t("settings.password.sheet"), [
    el("p", { class: "dlg-text" }, t("settings.password.text")),
    form,
  ], [button]);
}
