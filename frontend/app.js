if (window.self !== window.top) document.documentElement.setAttribute("data-embedded", "1");

const CHILD_COLORS = ["#0e6b70", "#7a4b9c", "#b4602a", "#2f6b3a", "#9c3b5e", "#3a5a9c"];
const SUBJECT_COLOR_NAMES = RanzenpostColour.NAMES;
const NEUTRAL_COLOR_NAMES = ["white", "grey", "black"];
const CALENDAR_COLORS = RanzenpostColour.PALETTE.filter((entry) => !NEUTRAL_COLOR_NAMES.includes(entry.name)).map((entry) => entry.base);
const COLOR_SOURCE_USER = "user";
const COLOR_SOURCE_AUTO = "auto";
const WEEK_MIN = 0;
const WEEK_MAX = 8;
const LESSON_MINUTES = 45;
const PULL_AXIS_RATIO = 1;
const OVERVIEW_ORIGIN = "overview";
const LETTERS_TAB_CURRENT = "current";
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024;

const CALENDAR_COMPONENT_TIMETABLE = "timetable";
const CALENDAR_COMPONENT_SCHOOL_HOLIDAYS = "school_holidays";
const CALENDAR_COMPONENT_PUBLIC_HOLIDAYS = "public_holidays";
const CALENDAR_COMPONENT_MARKS = "marks";
const CALENDAR_COMPONENT_ABSENCES = "absences";
const CALENDAR_COMPONENT_OWN_ENTRIES = "own_entries";
const CALENDAR_COMPONENTS = [
  CALENDAR_COMPONENT_TIMETABLE,
  CALENDAR_COMPONENT_SCHOOL_HOLIDAYS,
  CALENDAR_COMPONENT_PUBLIC_HOLIDAYS,
  CALENDAR_COMPONENT_MARKS,
  CALENDAR_COMPONENT_ABSENCES,
  CALENDAR_COMPONENT_OWN_ENTRIES,
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

const MARK_NAMES_KEY = "markNames";
const MARK_NAME_CHIPS = 12;
const MARK_MAX_NAME_LENGTH = 60;
const MARK_STATE_SUBSTITUTED = "substituted";
const MARK_STATE_FOREIGN = "foreign";
const MARK_STATE_CANCELLED = "cancelled";
const MARK_STATE_ORPHANED = "orphaned";
const MARK_CLARIFY_KEYS = {
  cancelled: { title: "marks.clarify.cancelled.title", text: "marks.clarify.cancelled.text" },
  foreign: { title: "marks.clarify.foreign.title", text: "marks.clarify.foreign.text" },
  orphaned: { title: "marks.clarify.orphaned.title", text: "marks.clarify.orphaned.text" },
};
const ABSENCE_STATUS_ACCEPTED = "accepted";

const {
  BASE_LANGUAGE,
  LANGUAGES,
  LANGUAGE_CHOICES,
  RTL_LANGUAGES,
  createLanguageLoader,
} = window.RanzenpostI18n;
var {
  formatTemplate,
  t,
  hasMessage,
  pluralCategory,
  tCount,
  setLanguageBundle,
  languageChoices,
  currentLanguageChoice,
  currentLanguage,
  formatNumber,
  dateFormatter,
  relativeFormatter,
} = window.RanzenpostI18n;

const {
  ERROR_NETWORK,
  ERROR_AUTH_FAILED,
  ERROR_NOT_CONFIGURED,
  ERROR_OUTAGE,
  REASON_TWOFACTOR_SETUP,
  REASON_LOCKED,
  REASON_SESSION_NOT_OPENED,
  REASON_CODE_STEP_FAILED,
  LOGIN_REASON_KEYS,
  UPLOAD_TIMEOUT_MS,
  apiError,
  errorCode,
  loginReasonOf,
  loginReasonRank,
  isTimeoutError,
  createApi,
} = window.RanzenpostApi;
const requests = createApi({
  fetch: (...args) => window.fetch(...args),
  base: document.baseURI || window.location.href,
  t: (key, vars) => t(key, vars),
  abortSignal: () => window.AbortSignal,
  formData: () => new FormData(),
});
var { apiMessage } = requests;
const { apiUrl, requestSignal, getJson, postJson, postFormData } = requests;

const languageLoader = createLanguageLoader({ getJson: (path) => getJson(path), page: document, agent: navigator });
const { loadBaseLanguage } = languageLoader;
var { resolveLanguage, applyLanguageChoice } = languageLoader;

const {
  addDays,
  weekdayIndex,
  startOfWeek,
  isoDate,
  isoWeek,
  parseAnyDate,
  parseIsoDay,
  timeMinutes,
  createFormat,
} = window.RanzenpostFormat;
const formats = createFormat({
  dateFormatter: (options) => dateFormatter(options),
  relativeFormatter: () => relativeFormatter(),
  currentLanguage: () => currentLanguage(),
  formatNumber: (value) => formatNumber(value),
  now: () => new Date(),
  nowMs: () => Date.now(),
});
const {
  showDate,
  formatEpoch,
  formatShortDate,
  formatTime,
  formatWeekdayShort,
  formatDayNumber,
  formatWeekdayDay,
  formatWeekdayDate,
  showDateTime,
  showTimestamp,
  formatIsoMoment,
  clockText,
  clockOf,
  weekdayLabel,
  isoLabel,
  dateLabel,
  relativeSince,
  minutesUntilLabel,
} = formats;

const { ICON_SHAPES, iconSvg, createDom } = window.RanzenpostDom;
const dom = createDom({ page: document });
const { el, iservText, icon, externalIcon } = dom;
const { createToast, createSheets } = window.RanzenpostShell;
const { createStore } = window.RanzenpostStore;

const VIEWS = [
  { key: "overview", label: "nav.overview", icon: "overview" },
  { key: "timetable", label: "nav.timetable", icon: "timetable" },
  { key: "absence", label: "nav.absence", icon: "absence" },
  { key: "post", label: "nav.post", icon: "inbox" },
  { key: "messenger", label: "nav.messenger", icon: "messages" },
  { key: "conferences", label: "nav.conferences", icon: "conferences" },
];
const VIEW_BY_KEY = Object.fromEntries(VIEWS.map((item) => [item.key, item]));
const MORE_VIEW = { key: "more", label: "nav.more", icon: "more" };

const MODULE_NAMES = ["timetable", "letters", "pinboard", "absences", "conferences", "messenger"];
const VIEW_MODULES = {
  overview: [],
  timetable: ["timetable"],
  absence: ["absences"],
  post: ["letters", "pinboard"],
  messenger: ["messenger"],
  conferences: ["conferences"],
  settings: [],
};
const MODULE_ISSUE_URL = "https://github.com/githuber110/ranzenpost/issues/new";

function defaultModules() {
  const available = {};
  for (const name of MODULE_NAMES) available[name] = true;
  return { available, unsupported: [], unknown: [], checkedAt: 0, iservVersion: "" };
}

function applyModules(payload) {
  const parsed = defaultModules();
  const data = payload && typeof payload === "object" ? payload : {};
  const flags = data.modules && typeof data.modules === "object" ? data.modules : {};
  for (const name of MODULE_NAMES) parsed.available[name] = flags[name] !== false;
  parsed.unsupported = (Array.isArray(data.unsupported) ? data.unsupported : [])
    .filter((entry) => entry && typeof entry.segment === "string" && entry.segment)
    .map((entry) => ({
      segment: entry.segment,
      slug: String(entry.slug || entry.segment),
      label: String(entry.label || entry.segment),
      name: String(entry.name || entry.label || entry.segment),
    }));
  parsed.unknown = (Array.isArray(data.unknown) ? data.unknown : [])
    .filter((entry) => entry && typeof entry.segment === "string" && entry.segment)
    .map((entry) => ({ segment: entry.segment, label: String(entry.label || entry.segment) }));
  parsed.checkedAt = Number(data.checked_at) || 0;
  parsed.iservVersion = String(data.iserv_version || "");
  return parsed;
}

function modulesDisabled() {
  const listed = state.config && Array.isArray(state.config.modules_disabled) ? state.config.modules_disabled : [];
  return listed.filter((name) => MODULE_NAMES.includes(name));
}

function moduleAvailable(name) {
  return state.modules.available[name] !== false;
}

function moduleDisabled(name) {
  return modulesDisabled().includes(name);
}

function moduleOn(name) {
  return moduleAvailable(name) && !moduleDisabled(name);
}

function layoutBlocks() {
  return window.RanzenpostBlocks;
}

function offeredBlocks(surface) {
  return layoutBlocks().offeredBlocks(moduleOn, surface);
}

function enabledOverviewBlocks() {
  const raw = state.config && Array.isArray(state.config.overview_blocks) ? state.config.overview_blocks : null;
  return layoutBlocks().normalizeOverviewBlocks(raw, offeredBlocks());
}

function hiddenOverviewBlocks() {
  return layoutBlocks().hiddenBlocks(enabledOverviewBlocks(), offeredBlocks());
}

function navigationAreas() {
  const raw = state.config && Array.isArray(state.config.navigation) ? state.config.navigation : null;
  return layoutBlocks().normalizeNavigation(raw).filter((area) => VIEW_BY_KEY[area] && viewAvailable(area));
}

function navigationBarLimit() {
  const match = /(?:^|;\s*)e2e_bar_limit=(\d+)/.exec(document.cookie || "");
  return match ? Number(match[1]) : layoutBlocks().BAR_LIMIT;
}

function navigationLayout() {
  return layoutBlocks().barLayout(navigationAreas(), navigationBarLimit());
}

function areaLabel(key) {
  return key === "overview" ? t("nav.overview") : t(VIEW_BY_KEY[key].label);
}

function anyModuleOn() {
  return MODULE_NAMES.some(moduleOn);
}

function viewAvailable(key) {
  if (key === "settings") return true;
  if (!anyModuleOn()) return key === "overview";
  const needs = VIEW_MODULES[key] || [];
  return !needs.length || needs.some(moduleOn);
}

function visibleViews() {
  return anyModuleOn() ? [VIEW_BY_KEY.overview].concat(navigationAreas().map((area) => VIEW_BY_KEY[area])) : [];
}

function revalidateView() {
  if (!viewAvailable(state.view)) state.view = "overview";
}

const LAYOUT_WIDE_MIN = 900;
const LAYOUT_DESK_MIN = 1280;
const LAYOUT_QUERIES = [`(min-width: ${LAYOUT_DESK_MIN}px)`, `(min-width: ${LAYOUT_WIDE_MIN}px)`];
const PANE_VIEWS = ["post", "messenger", "absence"];
const PAGE_DETAILS = ["letter", "room"];
const TIMETABLE_SCROLL_FROM = 5;
let layoutWatchBound = false;

function layoutModeFor(width) {
  if (width >= LAYOUT_DESK_MIN) return "desk";
  if (width >= LAYOUT_WIDE_MIN) return "wide";
  return "phone";
}

function layoutMode() {
  if (typeof window.matchMedia !== "function") return layoutModeFor(window.innerWidth || 0);
  if (window.matchMedia(LAYOUT_QUERIES[0]).matches) return "desk";
  if (window.matchMedia(LAYOUT_QUERIES[1]).matches) return "wide";
  return "phone";
}

function detailPlacement(kind, layout, view) {
  if (layout === "desk" && PANE_VIEWS.includes(view)) return "pane";
  return PAGE_DETAILS.includes(kind) ? "page" : "sheet";
}

function paneOpen() {
  if (periodsPaneActive()) return true;
  if (layoutMode() !== "desk") return false;
  return PANE_VIEWS.includes(state.view) || settingsPaneActive();
}

function settingsPaneActive() {
  if (state.view !== "settings" || layoutMode() !== "desk") return false;
  return !SETTINGS_PAGES_IN_MAIN.includes(state.settingsPage);
}

function settingsPageDetailId() {
  if (state.helpPage) return SETTINGS_DETAIL_HELP;
  if (state.settingsPage === SETTINGS_PAGE_COURSES && state.coursesPage) return `${SETTINGS_PAGE_COURSES}:${state.coursesPage.child}`;
  return state.settingsPage || "";
}

function currentDetail() {
  if (periodsPaneActive()) return state.periodsDetail ? { kind: "periods" } : null;
  if (state.view === "settings") {
    const page = settingsPageDetailId();
    if (page) return { kind: "settings-page", id: page };
    return state.settingsSchoolId ? { kind: "school", id: state.settingsSchoolId } : null;
  }
  if (state.view === "post" && state.letterDetail) return { kind: "letter", letter: state.letterDetail.letter };
  if (state.view === "messenger" && state.messengerRoom) return { kind: "room", room: state.messengerRoom };
  return state.detail;
}

function openDetail(detail) {
  state.detail = detail;
  rerender();
}

function closeDetail() {
  state.detail = null;
  rerender();
}

function detailIsOpen(kind, id) {
  if (!paneOpen()) return false;
  const detail = currentDetail();
  if (!detail || detail.kind !== kind) return false;
  if (kind === "letter") return letterKey(detail.letter) === id;
  if (kind === "room") return detail.room.room_id === id;
  if (kind === "post") return tileKey(detail.tile) === id;
  if (kind === "school" || kind === "settings-page") return detail.id === id;
  return detail.entry.id === id;
}

function openRowClass(base, kind, id) {
  return detailIsOpen(kind, id) ? `${base} open` : base;
}

function setupLayoutWatch() {
  if (layoutWatchBound || typeof window.matchMedia !== "function") return;
  layoutWatchBound = true;
  for (const query of LAYOUT_QUERIES) {
    const media = window.matchMedia(query);
    if (media && typeof media.addEventListener === "function") media.addEventListener("change", () => rerender());
  }
}

const CHANGE_KEYS = {
  cancelled: "timetable.change.cancelled",
  changed: "timetable.change.changed",
  added: "timetable.change.added",
};

const ABSENCE_TYPES = {
  sick: { label: "absence.type.sick.label", hint: "absence.type.sick.hint", icon: "absence" },
  leave: { label: "absence.type.leave.label", hint: "absence.type.leave.hint", icon: "letters" },
  deregister: { label: "absence.type.deregister.label", hint: "absence.type.deregister.hint", icon: "upcoming" },
  daycare: { label: "absence.type.daycare.label", hint: "absence.type.daycare.hint", icon: "today" },
};

const TARGET_KEYS = {
  bus: "absence.target.bus",
  lunch: "absence.target.lunch",
  kindergarten: "absence.target.kindergarten",
};
const STATUS_TAGS = {
  open: ["open", "absence.status.open"],
  accepted: ["ok", "absence.status.accepted"],
  rejected: ["no", "absence.status.rejected"],
};

function changeLabel(kind) {
  return CHANGE_KEYS[kind] ? t(CHANGE_KEYS[kind]) : t("timetable.change.generic");
}

function absenceTypeLabel(type) {
  return ABSENCE_TYPES[type] ? t(ABSENCE_TYPES[type].label) : "";
}

function targetLabel(target) {
  return TARGET_KEYS[target] ? t(TARGET_KEYS[target]) : target;
}

const state = {
  calendarHandOffStalled: null,
  haStatus: null,
  haStatusLoading: false,
  haBusy: false,
  config: null,
  me: null,
  notifyServices: [],
  notifySupervisor: null,
  children: [],
  childrenFailure: null,
  childrenRetrying: false,
  childId: null,
  overviewChildId: null,
  view: "overview",
  sheet: null,
  toast: null,
  timetable: null,
  modules: defaultModules(),
  appVersion: "",
  weekOffset: 0,
  spotlightSubject: null,
  marks: null,
  cancellations: null,
  holidays: null,
  holidayRegions: null,
  holidaySuggestion: null,
  overviewWeeks: {},
  _overviewAnchor: null,
  _overviewPinboardOrder: null,
  _overviewNow: true,
  _scrollTop: false,
  pinboard: null,
  pinboardFolder: null,
  pinboardOnlyNew: false,
  pinboardSearch: "",
  pinboardSelectMode: false,
  pinboardSelected: [],
  letters: null,
  lettersTab: "current",
  lettersUnread: 0,
  lettersSelectMode: false,
  lettersSelected: [],
  lettersSearch: "",
  letterDetail: null,
  postTab: "letters",
  messengerRooms: null,
  messengerRetrying: false,
  messengerRetryFailed: false,
  messengerSearch: "",
  messengerRoom: null,
  teacherRoom: null,
  absence: null,
  absenceForm: null,
  absenceFormDefault: null,
  absenceHistoryOpen: false,
  conferences: null,
  theme: "light",
  account: "",
  onSheetClose: null,
  settingsReturn: null,
  sheetForm: null,
  calendar: null,
  calendarDraft: null,
  calendarFrom: null,
  namesPage: null,
  pageForm: null,
  pageFormDefault: null,
  calendarQr: "",
  calendarPortRestart: false,
  calendarRestarting: false,
  calendarBusy: "",
  loads: {},
  loadedAt: {},
  refreshDeferred: false,
  pending: {},
  refreshFailed: {},
  bulkProgress: null,
  sheetFocused: false,
  colorDialogClose: null,
  sheetFormDefault: null,
  sheetDiscardAsk: false,
  detached: false,
  fileViewer: null,
  fileViewerFocused: false,
  detail: null,
  schools: [],
  schoolStatus: {},
  schoolReasons: {},
  schoolModules: null,
  schoolMe: null,
  settingsSchoolId: null,
  helpPage: false,
  settingsPage: null,
  blocksSearch: "",
  coursesPage: null,
  layoutAnnouncement: "",
  helpReturn: null,
  helpReport: "",
  helpFacts: null,
  helpFailed: false,
  helpBundle: null,
  helpBundleFailed: false,
  addingSchool: false,
  postSchoolFilter: "",
  messengerSchoolFilter: "",
};
const stateStore = createStore(state);

const OUTAGE_VIEWS = ["overview", "timetable", "absence", "post", "messenger", "conferences"];
const BOOT_TIMEOUT_MS = 25000;

function hashIndex(text, length) {
  let sum = 0;
  for (const char of String(text || "")) sum = (sum * 31 + char.charCodeAt(0)) % 100003;
  return sum % length;
}

function childColor(childId) {
  const index = state.children.findIndex((c) => c.key === childId);
  return CHILD_COLORS[(index < 0 ? 0 : index) % CHILD_COLORS.length];
}

function subjectColor(lesson) {
  return lesson.color || SUBJECT_COLOR_NAMES[hashIndex(lesson.subject_code || lesson.subject_label, SUBJECT_COLOR_NAMES.length)];
}

function subjectDotColor(lesson) {
  return RanzenpostColour.resolve(subjectColor(lesson)).hex;
}

function paintSubjectCell(cell, value) {
  const vars = RanzenpostColour.cellVars(value);
  if (!vars) return;
  cell.classList.add("subject", "subject-bar");
  cell.style.setProperty("--subject-cell-fill", vars.fill);
  cell.style.setProperty("--subject-cell-ink", vars.ink);
  cell.style.setProperty("--subject-bar", vars.bar);
}

const htmlParser = new DOMParser();

function stripHtml(html) {
  const text = String(html || "");
  if (!text) return "";
  const doc = htmlParser.parseFromString(text, "text/html");
  return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
}

const THEMES = ["light", "dark", "system"];
const DEFAULT_THEME = "system";

function readTheme() {
  try {
    const value = window.localStorage.getItem("theme");
    return THEMES.includes(value) ? value : DEFAULT_THEME;
  } catch (error) {
    return DEFAULT_THEME;
  }
}

function readCachedForename() {
  try {
    return window.localStorage.getItem("meForename") || "";
  } catch (error) {
    return "";
  }
}

function writeCachedForename(value) {
  try {
    if (value) window.localStorage.setItem("meForename", value);
    else window.localStorage.removeItem("meForename");
  } catch (error) {}
}

const LANGUAGE_PENDING_KEY = "languagePending";

function rememberLanguageChoice(choice, saved) {
  writeStoredText(LANGUAGE_PENDING_KEY, saved ? "" : choice);
}

function readStoredText(key) {
  try {
    return window.localStorage.getItem(key) || "";
  } catch (error) {
    return "";
  }
}

function writeStoredText(key, value) {
  try {
    if (value) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch (error) {}
}

const THEME_COLORS = { light: "#e4eae8", dark: "#0e1412" };

function applyThemeColorMeta(value) {
  const lightMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]');
  const darkMeta = document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]');
  if (!lightMeta || !darkMeta) return;
  const forced = value === "light" || value === "dark" ? THEME_COLORS[value] : null;
  lightMeta.setAttribute("content", forced || THEME_COLORS.light);
  darkMeta.setAttribute("content", forced || THEME_COLORS.dark);
}

function applyTheme(value) {
  if (value === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", value);
  applyThemeColorMeta(value);
}

function setTheme(value) {
  state.theme = value;
  applyTheme(value);
  try {
    window.localStorage.setItem("theme", value);
  } catch (error) {}
}

function root() {
  return document.getElementById("app");
}

function detachedRoot() {
  state.detached = true;
  const app = root();
  shellAttributes(app, "flow");
  return app;
}

function sheetScrollTop() {
  const body = root().querySelector(".sheet-body");
  return body ? body.scrollTop : 0;
}

function restoreSheetScroll(offset) {
  if (!offset) return;
  const body = root().querySelector(".sheet-body");
  if (body) body.scrollTop = offset;
}

function shellAttributes(app, shell) {
  app.setAttribute("data-shell", shell);
  app.setAttribute("data-view", state.view);
}

function render() {
  if (state.detached) return;
  flushDeferredRefresh();
  setupLayoutWatch();
  rememberFocusForRender();
  const app = root();
  closeColorDialog();
  const keptSheetScroll = sheetScrollTop();
  const layout = layoutMode();
  const pane = paneOpen();
  revalidateView();
  shellAttributes(app, !anyModuleOn() ? "bare" : layout === "phone" ? "tabs" : pane ? "rail-pane" : "rail");
  if (state.detail && !pane) {
    placeSheet(detailSheetFactory(state.detail));
    state.detail = null;
  }
  if (state.absenceForm && absenceFlow) {
    shellAttributes(app, "flow");
    const wizard = [absenceFlow.node];
    if (state.sheet) wizard.push(state.sheet());
    if (state.toast) wizard.push(toastNode());
    app.replaceChildren(...wizard);
    syncFileViewer();
    restoreSheetScroll(keptSheetScroll);
    return;
  }
  if (state.teacherRoom && teacherRoomFlow) {
    shellAttributes(app, "flow");
    const wizard = [teacherRoomFlow.node];
    if (state.sheet) wizard.push(state.sheet());
    if (state.toast) wizard.push(toastNode());
    app.replaceChildren(...wizard);
    syncFileViewer();
    restoreSheetScroll(keptSheetScroll);
    return;
  }
  const hasSelectBar = state.view === "post" && (postSegmentIs("letters")
    ? state.lettersSelectMode
    : state.pinboardSelectMode);
  const chat = inMessengerRoom() && !pane;
  const screen = el("div", { class: chat ? "screen chat" : hasSelectBar ? "screen has-select-bar" : "screen" });
  screen.append(header(state.view));
  const bannerAbove = OUTAGE_VIEWS.includes(state.view) && state.view !== "overview";
  screen.append(el("div", { class: "wrap" }, [bannerAbove ? outageBanner() : null, viewFor(state.view)]));
  screen.addEventListener("scroll", () => {
    const bar = screen.querySelector(".header");
    if (bar) bar.classList.toggle("scrolled", screen.scrollTop > 4);
  });
  if (state.view === "timetable") {
    screen.addEventListener("pointerdown", spotlightPointerDown, true);
    screen.addEventListener("click", spotlightSwallowTap, true);
  }
  if (!chat) setupPullToRefresh(screen);
  const nodes = (layout === "phone"
    ? (chat ? [screen] : [screen, tabbar()])
    : (pane ? [rail(), screen, detailPaneNode()] : [rail(), screen])).filter(Boolean);
  if (state.sheet) nodes.push(state.sheet());
  if (state.toast) nodes.push(toastNode());
  app.replaceChildren(...nodes);
  syncFileViewer();
  restoreSheetScroll(keptSheetScroll);
  if (state._keepScroll) {
    screen.scrollTop = state._keepScroll;
    state._keepScroll = 0;
  }
  if (state._scrollTop) {
    state._scrollTop = false;
    screen.scrollTop = 0;
  }
  applyOverviewPagination();
  applyFocusAfterRender();
  if (chat) {
    setupChatViewport();
    applyChatViewport();
  }
}

function rerender() {
  const screen = root().querySelector(".screen");
  if (state.view === "overview") rememberOverviewAnchor();
  state._keepScroll = screen ? screen.scrollTop : 0;
  render();
}

function absenceFormSignature(form) {
  if (!form) return "";
  const rest = Object.assign({}, form);
  delete rest.attachments;
  const files = (form.attachments || []).map((file) => `${file.name}:${file.size}`);
  return JSON.stringify([rest, files]);
}

function isAbsenceFormDirty() {
  if (!state.absenceForm || !state.absenceFormDefault) return false;
  return absenceFormSignature(state.absenceForm) !== absenceFormSignature(state.absenceFormDefault);
}

function leaveAbsenceForm(after) {
  if (!isAbsenceFormDirty()) {
    after();
    return;
  }
  confirmAction({
    title: t("absence.discard.title"),
    text: t("absence.discard.text"),
    confirmLabel: t("absence.discard.confirm"),
    destructive: true,
  }).then((ok) => { if (ok) after(); });
}

function pageState(build) {
  if (!state.pageForm) {
    state.pageForm = build();
    state.pageFormDefault = copy(state.pageForm);
  }
  return state.pageForm;
}

function isPageFormDirty() {
  if (!state.pageForm || !state.pageFormDefault) return false;
  return JSON.stringify(state.pageForm) !== JSON.stringify(state.pageFormDefault);
}

function discardPageForm() {
  state.pageForm = null;
  state.pageFormDefault = null;
}

function leavePageForm(after) {
  if (!isPageFormDirty()) {
    discardPageForm();
    after();
    return;
  }
  confirmAction({
    title: t("sheet.discard.title"),
    text: t("sheet.discard.text"),
    confirmLabel: t("sheet.discard.confirm"),
    destructive: true,
  }).then((ok) => {
    if (!ok) return;
    discardPageForm();
    after();
  });
}

function leaveDirtyForms(after) {
  leaveAbsenceForm(() => leavePageForm(after));
}

const ALL_VIEWS = VIEWS.map((item) => item.key).concat(["settings"]);

const VIEW_ENTRY_DEFAULTS = {
  overview: {
    _overviewAnchor: null,
    _overviewNow: true,
    _overviewPinboardOrder: null,
  },
  timetable: {
    weekOffset: 0,
    spotlightSubject: null,
  },
  absence: {
    absenceHistoryOpen: false,
  },
  post: {
    postTab: "letters",
    lettersTab: "current",
    lettersSelectMode: false,
    lettersSelected: [],
    lettersSearch: "",
    pinboardSelectMode: false,
    pinboardSelected: [],
    pinboardSearch: "",
    pinboardOnlyNew: false,
    pinboardFolder: null,
  },
  messenger: {
    messengerRoom: null,
    messengerSearch: "",
    messengerRetrying: false,
    messengerRetryFailed: false,
  },
  conferences: {},
  settings: { helpPage: false, settingsPage: null, blocksSearch: "" },
};

function postSegmentIs(segment) {
  if (!moduleOn("letters")) return segment === "pinboard";
  if (!moduleOn("pinboard")) return segment === "letters";
  return state.postTab === segment;
}

function applyViewEntryDefaults(name) {
  const defaults = VIEW_ENTRY_DEFAULTS[name];
  if (!defaults) return;
  for (const key of Object.keys(defaults)) {
    const value = defaults[key];
    state[key] = Array.isArray(value) ? value.slice() : value;
  }
}

function enterView(name, options) {
  const opts = options || {};
  state._keepScroll = 0;
  state._scrollTop = true;
  if (opts.keepEntryState) return;
  if (name === "overview" && opts.keepAnchor) return;
  const weekBefore = state.weekOffset;
  applyViewEntryDefaults(name);
  if (name === "post" && opts.segment) state.postTab = opts.segment;
  if (name === "timetable" && weekBefore !== state.weekOffset) {
    state.timetable = null;
    reloadTimetable();
  }
}

function setView(name, options) {
  leaveDirtyForms(() => {
    const changed = state.view !== name;
    state.view = name;
    dropSheet();
    state.letterDetail = null;
    state.detail = null;
    state.spotlightSubject = null;
    stopMessengerPoll();
    discardFileViewer();
    closeAbsenceForm();
    closeTeacherRoom();
    if (changed) enterView(name, options);
    render();
    revalidateActiveView();
  });
}

function copy(value) {
  return JSON.parse(JSON.stringify(value === undefined ? null : value));
}

const pageTimers = { set: (run, ms) => window.setTimeout(run, ms), clear: (id) => window.clearTimeout(id) };

const sheets = createSheets({
  slot: { read: (key) => stateStore.get(key), write: (key, value) => stateStore.set(key, value) },
  layout: () => layoutMode(),
  t: (...args) => t(...args),
  dom,
  timers: pageTimers,
  rerender: () => rerender(),
});
const {
  openSheet,
  discardSheet,
  closeSheet,
  isSheetFormDirty,
  sheetState,
  sheet,
  openNestedSheet,
  askConfirmation,
  placeSheet,
  dropSheet,
  resetSheetForm,
} = sheets;
const confirmAction = (options) => new Promise((resolve) => askConfirmation(options, resolve));

const toasts = createToast({
  slot: { read: () => stateStore.get("toast"), write: (value) => stateStore.set("toast", value) },
  timers: pageTimers,
  rerender: () => rerender(),
  dom,
});
const { toast, toastNode } = toasts;

function currentChild() {
  return state.children.find((c) => c.key === state.childId) || state.children[0] || null;
}

function connections() {
  const list = state.config && Array.isArray(state.config.connections) ? state.config.connections : [];
  return list.filter((entry) => entry && entry.id);
}

function readySchools() {
  return connections().filter((entry) => entry.setup_complete !== false);
}

function connectionOf(id) {
  return connections().find((entry) => entry.id === id) || null;
}

function connectionOfKey(key) {
  const value = String(key || "");
  const cut = value.indexOf(":");
  return cut > 0 ? value.slice(0, cut) : "";
}

function currentConnectionId() {
  const fromChild = connectionOfKey(state.childId);
  if (fromChild) return fromChild;
  const first = readySchools()[0] || connections()[0];
  return first ? first.id : "";
}

function connectionConfig(id) {
  return connectionOf(id) || {};
}

function currentConfig() {
  return connectionConfig(currentConnectionId());
}

function editingConnectionId() {
  if (state.settingsSchoolId && connectionOf(state.settingsSchoolId)) return state.settingsSchoolId;
  return currentConnectionId();
}

function editingConfig() {
  return connectionConfig(editingConnectionId());
}

function headerTitleFor(view) {
  const child = currentChild();
  const many = state.children.length > 1;
  if (view === "timetable") {
    if (child && many && !timetableShowsAllChildren() && !manySchools()) return null;
    return { text: t("timetable.title") };
  }
  if (view === "absence") return { text: t("absence.title") };
  if (view === "post") {
    if (state.letterDetail && !paneOpen()) {
      const { letter } = state.letterDetail;
      return {
        text: letter.title || t("letters.detail.title"),
        onBack: leaveLetterDetail,
        extra: techDetailsButton(letterTechEntries(letter)),
      };
    }
    return { text: t("post.title") };
  }
  if (view === "messenger") {
    if (state.messengerRoom && !paneOpen()) return { node: messengerRoomHeadTitle(), onBack: closeMessengerRoom };
    return { text: t("messenger.title") };
  }
  if (view === "conferences") return { text: t("conferences.title") };
  if (view === "settings") {
    if (settingsPaneActive()) return { text: t("settings.title"), onBack: () => setView(state.settingsReturn || "overview") };
    if (state.helpPage) return { text: t("help.title"), onBack: closeHelpPage };
    if (state.settingsPage) return { text: settingsPageTitle(state.settingsPage), onBack: settingsPageBack };
    if (state.settingsSchoolId && !paneOpen()) return { text: schoolFullName(state.settingsSchoolId), onBack: closeSchoolPage };
    return {
      text: t("settings.title"),
      onBack: () => setView(state.settingsReturn || "overview"),
    };
  }
  if (view === "overview") return { node: greetingHeadline(new Date(), "header-title greeting-head") };
  return null;
}

function headerTitleNode(meta) {
  const row = el("div", { class: "header-title-row" });
  if (meta.onBack) {
    row.append(el("button", {
      class: "icon-btn header-back",
      type: "button",
      "aria-label": t("common.back"),
      onclick: meta.onBack,
    }, [icon("back", 18)]));
  }
  row.append(meta.node || el("h1", { class: "header-title" }, meta.text));
  if (meta.extra) row.append(meta.extra);
  return row;
}

function header(view) {
  const bar = el("div", { class: "header" });
  const meta = headerTitleFor(view);
  bar.append(meta ? headerTitleNode(meta) : el("span", {}));
  const actions = [];
  const child = currentChild();
  const many = state.children.length > 1;
  if (child && view === "timetable" && many && !timetableShowsAllChildren() && !manySchools()) {
    const detail = childClassLabel(child);
    actions.push(
      el("button", {
        class: "child-switch",
        type: "button",
        "aria-label": t("child.switch"),
        onclick: () => openSheet(childSheet),
      }, [
        childAvatar(child),
        el("span", {}, [
          iservText("span", { class: "who" }, childShortName(child)),
          detail ? iservText("span", { class: "cls" }, detail) : null,
        ]),
        icon("chevron", 16),
      ])
    );
  }
  if (view === "timetable" && moduleOn("timetable")) {
    actions.push(el("button", {
      class: "icon-btn",
      type: "button",
      "aria-label": t("calendar.subscribe.open"),
      onclick: openCalendarPage,
    }, [icon("calendarAdd", 18)]));
    actions.push(planAddButton());
  }
  if (view === "messenger" && messengerRoomUnread() && !paneOpen()) actions.push(messengerReadButton());
  if (view !== "settings") {
    actions.push(el("button", {
      class: "icon-btn settings-entry",
      type: "button",
      "aria-label": t("nav.settings"),
      onclick: () => {
        if (state.view !== "settings") state.settingsReturn = state.view;
        setView("settings");
      },
    }, [icon("settings", 18)]));
  }
  bar.append(el("div", { class: "header-actions" }, actions));
  return bar;
}

function childTechEntries(c) {
  return [
    { label: t("child.tech.childId"), value: c.child_id, kind: "text" },
    { label: t("child.tech.studentId"), value: c.student_id, kind: "text" },
    { label: t("child.tech.classFull"), value: c.class_full, kind: "text" },
    { label: t("child.tech.classCode"), value: c.class_code, kind: "text" },
  ];
}

function childOption(c) {
  const className = c.class_name || "";
  const avatar = childAvatar(c);
  const lines = [iservText("b", {}, childLabelWithSchool(c, childShortName(c)))];
  if (className) lines.push(iservText("small", {}, t("child.class", { name: className })));
  return el("div", { class: "opt", "aria-pressed": String(c.key === state.childId) }, [
    el("button", {
      class: "opt-main",
      type: "button",
      onclick: () => selectChild(c.key),
    }, [avatar, el("span", {}, lines)]),
    techDetailsButton(childTechEntries(c)),
  ]);
}

function childSheet() {
  const options = state.children.map(childOption);
  return sheet(t("child.sheet"), [el("div", { class: "opt-list" }, options)]);
}

async function selectChild(childId) {
  dropSheet();
  if (childId === state.childId) return rerender();
  const before = currentConnectionId();
  state.childId = childId;
  state.timetable = null;
  if (currentConnectionId() !== before) state.absence = null;
  rerender();
  await reloadTimetable();
}

function navEntry(className, item, count, current, onclick, extra) {
  const label = t(item.label);
  return el("button", Object.assign({
    class: className,
    type: "button",
    "data-view": item.key,
    "aria-label": count ? t("nav.unread", { area: label, count: formatNumber(count) }) : null,
    "aria-current": current ? "page" : null,
    onclick,
  }, extra || {}), [
    icon(item.icon, 22),
    el("span", { class: className.startsWith("tab") ? "tab-label" : "rail-label" }, label),
    count ? el("span", { class: "badge", "aria-hidden": "true" }, badgeText(count)) : null,
  ]);
}

function tabbar() {
  if (!anyModuleOn()) return null;
  const layout = navigationLayout();
  const bar = el("nav", { class: "tabbar", "aria-label": t("nav.aria") });
  bar.style.setProperty("--tabs", String(layout.bar.length));
  for (const key of layout.bar) {
    if (key === MORE_VIEW.key) {
      const hiddenCount = layout.more.reduce((sum, area) => sum + badgeCount(area), 0);
      bar.append(navEntry("tab tab-more", MORE_VIEW, hiddenCount, layout.more.includes(state.view), () => openSheet(moreSheet), {
        "aria-haspopup": "dialog",
      }));
      continue;
    }
    bar.append(navEntry("tab", VIEW_BY_KEY[key], badgeCount(key), state.view === key, () => setView(key)));
  }
  return bar;
}

function moreSheet() {
  const layout = navigationLayout();
  const rows = layout.more.map((area) => {
    const item = VIEW_BY_KEY[area];
    const count = badgeCount(area);
    return el("button", {
      class: "setting-row more-row",
      type: "button",
      "data-area": area,
      "aria-current": state.view === area ? "page" : null,
      onclick: () => setView(area),
    }, [
      el("span", { class: "nav-ico" }, [icon(item.icon, 22)]),
      el("span", { class: "lbl" }, t(item.label)),
      count ? el("span", { class: "badge", "aria-hidden": "true" }, badgeText(count)) : null,
      el("span", { class: "chev" }, [icon("chevron", 16)]),
    ]);
  });
  return sheet(t("nav.more"), [
    el("div", { class: "rows" }, rows),
    el("p", { class: "sheet-hint sheet-foot-hint" }, t("nav.more.hint")),
  ]);
}

function rail() {
  const items = visibleViews();
  if (!items.length) return null;
  const nav = el("nav", { class: "rail", "aria-label": t("nav.aria") });
  for (const item of items) {
    nav.append(navEntry("rail-item", item, badgeCount(item.key), state.view === item.key, () => setView(item.key)));
  }
  return nav;
}

function detailParts(detail) {
  if (detail.kind === "periods") return periodsDetailParts();
  if (detail.kind === "letter") {
    const letter = detail.letter;
    return {
      title: letter.title || t("letters.detail.title"),
      extra: techDetailsButton(letterTechEntries(letter)),
      body: [letterDetailView()],
      foot: null,
      onClose: leaveLetterDetail,
      chat: false,
    };
  }
  if (detail.kind === "room") {
    return {
      title: detail.room.name || t("messenger.title"),
      extra: messengerRoomUnread() ? messengerReadButton() : null,
      body: [messengerRoomView()],
      foot: null,
      onClose: closeMessengerRoom,
      chat: true,
    };
  }
  if (detail.kind === "settings-page") {
    const help = detail.id === SETTINGS_DETAIL_HELP;
    return {
      title: help ? t("help.title") : settingsPageTitle(state.settingsPage),
      extra: null,
      body: [help ? helpPageView() : settingsPageView()],
      foot: null,
      onClose: help ? closeHelpPage : settingsPageBack,
      chat: false,
    };
  }
  if (detail.kind === "school") {
    return {
      title: schoolFullName(detail.id),
      extra: null,
      body: [schoolPageView()],
      foot: null,
      onClose: closeSchoolPage,
      chat: false,
    };
  }
  const parts = detail.kind === "absence" ? absenceDetailParts(detail.entry) : postDetailParts(detail.tile);
  return Object.assign({ onClose: closeDetail, chat: false }, parts);
}

function detailSheetFactory(detail) {
  return () => {
    const parts = detailParts(detail);
    return sheet(parts.title, parts.body, parts.foot, parts.extra);
  };
}

function emptyPaneNode() {
  if (periodsPaneActive()) return el("div", { class: "pane-empty" }, [icon("today", 40), el("p", {}, t("periods.pane.empty"))]);
  if (settingsPaneActive()) return el("div", { class: "pane-empty" }, [icon("settings", 40), el("p", {}, t("settings.pane.empty"))]);
  return el("div", { class: "pane-empty" }, [icon("inbox", 40), el("p", {}, t("layout.detail.empty"))]);
}

function detailPaneNode() {
  const pane = el("aside", { class: "pane-detail", "aria-label": t("layout.detail.aria") });
  const detail = currentDetail();
  if (!detail) {
    pane.append(emptyPaneNode());
    return pane;
  }
  const parts = detailParts(detail);
  pane.append(el("div", { class: "pane-head" }, [
    el("button", {
      class: "icon-btn pane-close",
      type: "button",
      "aria-label": t("common.close"),
      onclick: parts.onClose,
    }, [icon("close", 18)]),
    iservText("h2", { class: "pane-title" }, parts.title),
    parts.extra ? el("div", { class: "pane-head-actions" }, [parts.extra]) : null,
  ]));
  pane.append(el("div", { class: parts.chat ? "pane-body chat-host" : "pane-body" }, parts.body));
  if (parts.foot) pane.append(el("div", { class: "pane-foot" }, parts.foot));
  return pane;
}

function badgeText(count) {
  return count > 9 ? t("common.badge.overflow", { count: formatNumber(9) }) : formatNumber(count);
}

function periodShort(period) {
  return t("common.period.short", { number: formatNumber(period) });
}

function dateRange(from, till) {
  return t("common.dateRange", { from, till });
}

function lettersUnreadCount() {
  const data = state.letters;
  if (data && !data.error && data.tab === LETTERS_TAB_CURRENT) {
    state.lettersUnread = (data.letters || []).filter(
      (entry) => entry.unread || letterConfirmationOpen(entry)
    ).length;
  }
  return Number(state.lettersUnread) || 0;
}

function pinboardUnreadCount() {
  const data = state.pinboard;
  if (!data || data.error) return 0;
  return (data.feed || []).filter((tile) => tile.unread).length;
}

function badgeCount(key) {
  if (key === "post") return lettersUnreadCount() + pinboardUnreadCount();
  if (key === "messenger") return messengerUnreadTotal();
  return 0;
}

function loadingBlock() {
  return el("div", { class: "loading" }, t("common.loading"));
}

function emptyBlock(iconName, title, text, action) {
  return el("div", { class: "empty" }, [icon(iconName), el("b", {}, title), el("p", {}, text), action || null]);
}

function noteBlock(text) {
  return el("div", { class: "note" }, [icon("alert", 16), el("span", {}, text)]);
}

function searchField(value, placeholder, onInput, hitNode) {
  const input = el("input", {
    class: "search-input",
    type: "search",
    value: value || "",
    placeholder,
    autocomplete: "off",
    autocapitalize: "none",
    spellcheck: "false",
    enterkeyhint: "search",
    "aria-label": placeholder,
  });
  const clear = el("button", { class: "search-clear", type: "button", "aria-label": t("common.search.clear") }, [icon("close", 14)]);
  clear.hidden = !(value || "");
  input.addEventListener("input", () => {
    clear.hidden = !input.value;
    onInput(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") input.blur();
  });
  clear.addEventListener("click", () => {
    input.value = "";
    clear.hidden = true;
    input.focus();
    onInput("");
  });
  return el("div", { class: "search-field" }, [icon("search", 16), input, clear, hitNode || null]);
}

function factList(facts) {
  return el("div", { class: "field-group" }, facts.map(([label, value]) =>
    el("div", { class: "cell" }, [
      el("div", { class: "field-label" }, label),
      iservText("div", { class: "fact" }, value),
    ])
  ));
}

const DISPOSITION_FILENAME_PATTERN = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i;

function filenameFromDisposition(header) {
  const match = DISPOSITION_FILENAME_PATTERN.exec(header || "");
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch (error) {
    return match[1];
  }
}

async function responseUserMessage(response) {
  if (!(response.headers.get("content-type") || "").includes("json")) return "";
  try {
    return apiMessage(await response.json(), "");
  } catch (error) {
    return "";
  }
}

const IMAGE_EXTENSION_PATTERN = /\.(png|jpe?g|gif|webp|bmp|avif|heic|heif)$/i;
const IMAGE_TYPE_PATTERN = /^image\/(png|jpeg|gif|webp|bmp|avif|heic|heif)\b/i;
const PDF_EXTENSION_PATTERN = /\.pdf$/i;
const PDF_TYPE_PATTERN = /^application\/pdf\b/i;
const OPAQUE_TYPES = ["", "application/octet-stream", "binary/octet-stream"];
const DOWNLOAD_REVOKE_DELAY = 4000;
const VIEWER_ZOOM_MAX = 5;
const VIEWER_DOUBLE_TAP_MS = 320;
const VIEWER_DOUBLE_TAP_SLOP = 24;

function fileKind(filename, type) {
  const mime = String(type || "").split(";")[0].trim().toLowerCase();
  if (IMAGE_TYPE_PATTERN.test(mime)) return "image";
  if (PDF_TYPE_PATTERN.test(mime)) return "pdf";
  if (!OPAQUE_TYPES.includes(mime)) return "download";
  if (IMAGE_EXTENSION_PATTERN.test(filename || "")) return "image";
  if (PDF_EXTENSION_PATTERN.test(filename || "")) return "pdf";
  return "download";
}

function downloadBlob(objectUrl, filename) {
  const link = el("a", { href: objectUrl, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), DOWNLOAD_REVOKE_DELAY);
}

function openFileViewer(kind, objectUrl, filename, triggerEl, blob) {
  state.fileViewer = { kind, url: objectUrl, filename, blob: blob || null, trigger: triggerEl || null, pdfSettled: false };
  state.fileViewerFocused = false;
  rerender();
}

function discardFileViewer() {
  const current = state.fileViewer;
  if (!current) return;
  state.fileViewer = null;
  unmountFileViewer();
  if (typeof current.pdfCleanup === "function") current.pdfCleanup();
  URL.revokeObjectURL(current.url);
}

function closeFileViewer() {
  const current = state.fileViewer;
  if (!current) return;
  discardFileViewer();
  rerender();
  if (current.trigger && typeof current.trigger.focus === "function") current.trigger.focus();
}

function pdfViewerFailed(viewer) {
  if (state.fileViewer !== viewer || viewer.pdfSettled) return;
  viewer.pdfSettled = true;
  state.fileViewer = null;
  unmountFileViewer();
  if (typeof viewer.pdfCleanup === "function") viewer.pdfCleanup();
  rerender();
  if (viewer.trigger && typeof viewer.trigger.focus === "function") viewer.trigger.focus();
  toast(t("common.filePreviewUnavailable"), "good");
  downloadBlob(viewer.url, viewer.filename);
}

function pdfViewerLoaded(viewer) {
  if (state.fileViewer !== viewer) return;
  viewer.pdfSettled = true;
}

async function fetchAppFile(path, fallbackFilename) {
  const response = await fetch(apiUrl(path));
  if (!response.ok) {
    const failure = new Error("http " + response.status);
    failure.userMessage = await responseUserMessage(response);
    throw failure;
  }
  const filename = filenameFromDisposition(response.headers.get("content-disposition")) || fallbackFilename;
  const blob = await response.blob();
  return { blob, filename };
}

async function openAppFile(path, fallbackFilename, triggerEl) {
  const { blob, filename } = await fetchAppFile(path, fallbackFilename);
  const objectUrl = URL.createObjectURL(blob);
  const kind = fileKind(filename, blob.type);
  if (kind === "image" || kind === "pdf") {
    openFileViewer(kind, objectUrl, filename, triggerEl, blob);
    return;
  }
  downloadBlob(objectUrl, filename);
}

const PRINT_FRAME_RELEASE_MS = 60000;

function coarsePointer() {
  return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
}

function shareableFile(blob, filename) {
  if (typeof File !== "function" || !navigator.share || !navigator.canShare) return null;
  const file = new File([blob], filename || t("common.attachment"), { type: blob.type || "" });
  return navigator.canShare({ files: [file] }) ? file : null;
}

async function shareFile(file, filename) {
  try {
    await navigator.share({ files: [file], title: filename });
    return true;
  } catch (error) {
    return !!(error && error.name === "AbortError");
  }
}

async function saveFile(blob, filename) {
  const file = coarsePointer() ? shareableFile(blob, filename) : null;
  if (file && (await shareFile(file, filename))) return;
  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({ suggestedName: filename });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      toast(t("common.saved"));
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
  }
  downloadBlob(URL.createObjectURL(blob), filename);
}

function printDocumentFor(blob, filename) {
  const kind = fileKind(filename, blob.type);
  if (kind === "pdf") return blob;
  if (kind !== "image") return null;
  const picture = URL.createObjectURL(blob);
  const page = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(filename)}</title>` +
    `<style>html,body{margin:0}img{max-width:100%;max-height:100vh}</style></head>` +
    `<body><img src="${picture}" alt=""></body></html>`;
  return new Blob([page], { type: "text/html" });
}

function printInFrame(source) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(source);
    const frame = el("iframe", { class: "print-frame", src: url, "aria-hidden": "true", tabindex: "-1" });
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      window.setTimeout(() => {
        frame.remove();
        URL.revokeObjectURL(url);
      }, PRINT_FRAME_RELEASE_MS);
      resolve(ok);
    };
    frame.addEventListener("load", () => {
      const run = () => {
        try {
          frame.contentWindow.focus();
          frame.contentWindow.print();
          finish(true);
        } catch (error) {
          finish(false);
        }
      };
      const picture = frame.contentDocument && frame.contentDocument.querySelector("img");
      if (picture && !picture.complete) {
        picture.addEventListener("load", run, { once: true });
        picture.addEventListener("error", () => finish(false), { once: true });
        return;
      }
      run();
    });
    frame.addEventListener("error", () => finish(false));
    document.body.append(frame);
  });
}

async function printFile(blob, filename) {
  const document_ = printDocumentFor(blob, filename);
  if (!document_) {
    toast(t("attachment.print.unsupported"), "bad");
    downloadBlob(URL.createObjectURL(blob), filename);
    return;
  }
  if (coarsePointer()) {
    const file = shareableFile(blob, filename);
    if (file && (await shareFile(file, filename))) return;
  }
  if (!(await printInFrame(document_))) toast(t("attachment.print.failed"), "bad");
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function pointDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function attachImageViewerGestures(img) {
  const pointers = new Map();
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let startDistance = 0;
  let startScale = 1;
  let panStart = null;
  let lastTapTime = 0;
  let lastTapPoint = null;

  function applyTransform() {
    img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
  }

  function resetZoom() {
    scale = 1;
    translateX = 0;
    translateY = 0;
    applyTransform();
  }

  function toggleZoom() {
    if (scale > 1) resetZoom();
    else {
      scale = 2.5;
      applyTransform();
    }
  }

  img.addEventListener("pointerdown", (event) => {
    img.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      panStart = { x: event.clientX - translateX, y: event.clientY - translateY };
    } else if (pointers.size === 2) {
      const points = [...pointers.values()];
      startDistance = pointDistance(points[0], points[1]);
      startScale = scale;
      panStart = null;
    }
  });

  img.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const points = [...pointers.values()];
      const newDistance = pointDistance(points[0], points[1]);
      if (startDistance > 0) {
        scale = Math.min(Math.max(startScale * (newDistance / startDistance), 1), VIEWER_ZOOM_MAX);
        applyTransform();
      }
    } else if (pointers.size === 1 && panStart && scale > 1) {
      translateX = event.clientX - panStart.x;
      translateY = event.clientY - panStart.y;
      applyTransform();
    }
  });

  function endPointer(event) {
    const wasSingle = pointers.size === 1;
    const point = pointers.get(event.pointerId);
    pointers.delete(event.pointerId);
    if (pointers.size === 0) {
      panStart = null;
      if (scale < 1) resetZoom();
      if (wasSingle && point) {
        const now = Date.now();
        if (now - lastTapTime < VIEWER_DOUBLE_TAP_MS && lastTapPoint && pointDistance(point, lastTapPoint) < VIEWER_DOUBLE_TAP_SLOP) {
          toggleZoom();
          lastTapTime = 0;
          lastTapPoint = null;
        } else {
          lastTapTime = now;
          lastTapPoint = point;
        }
      }
    } else if (pointers.size === 1) {
      const [remaining] = [...pointers.values()];
      panStart = { x: remaining.x - translateX, y: remaining.y - translateY };
    }
  }

  img.addEventListener("pointerup", endPointer);
  img.addEventListener("pointercancel", endPointer);
}

function fileViewerImage(viewer) {
  const img = el("img", {
    src: viewer.url,
    alt: viewer.filename || t("common.attachment"),
    class: "viewer-img",
    draggable: "false",
  });
  attachImageViewerGestures(img);
  return img;
}

function pdfViewerBytes(blob) {
  if (!blob || typeof blob.arrayBuffer !== "function") return null;
  return blob.arrayBuffer();
}

function fileViewerPdf(viewer) {
  if (!viewer.pdfView) {
    const view = window.PdfViewer.create({
      url: viewer.url,
      data: pdfViewerBytes(viewer.blob),
      onError: () => pdfViewerFailed(viewer),
    });
    view.ready.then((outcome) => {
      if (outcome && outcome.ok) pdfViewerLoaded(viewer);
    });
    viewer.pdfView = view;
    viewer.pdfCleanup = () => {
      viewer.pdfView = null;
      view.destroy();
    };
  }
  return el("div", { class: "viewer-pdf-wrap" }, [viewer.pdfView.node]);
}

let mountedFileViewer = null;

function syncFileViewer() {
  const wanted = state.fileViewer;
  if (!wanted) {
    unmountFileViewer();
    return;
  }
  if (mountedFileViewer && mountedFileViewer.viewer === wanted) return;
  unmountFileViewer();
  const node = fileViewerNode();
  if (!node) return;
  mountedFileViewer = { viewer: wanted, node };
  document.body.append(node);
}

function unmountFileViewer() {
  if (!mountedFileViewer) return;
  mountedFileViewer.node.remove();
  mountedFileViewer = null;
}

function trapViewerFocus(event, overlay) {
  const focusable = [...overlay.querySelectorAll("button, [tabindex]")].filter((node) => !node.disabled);
  if (!focusable.length) return;
  event.preventDefault();
  const current = focusable.indexOf(document.activeElement);
  const step = event.shiftKey ? -1 : 1;
  const next = current < 0 ? 0 : (current + step + focusable.length) % focusable.length;
  focusable[next].focus();
}

function viewerSave(viewer) {
  if (!viewer || !viewer.blob) return Promise.resolve();
  return saveFile(viewer.blob, viewer.filename);
}

function viewerPrint(viewer) {
  if (!viewer || !viewer.blob) return Promise.resolve();
  return printFile(viewer.blob, viewer.filename);
}

function viewerButton(className, iconName, label, onclick) {
  return el("button", { class: className, type: "button", "aria-label": label, title: label, onclick }, [icon(iconName, 20)]);
}

function closeViewerMenu(overlay) {
  const menu = overlay.querySelector(".viewer-menu");
  if (menu) menu.remove();
}

function openViewerMenu(overlay, viewer, x, y) {
  closeViewerMenu(overlay);
  const menu = el("div", { class: "viewer-menu", role: "menu" }, [
    el("button", { class: "viewer-menu-item viewer-menu-save", type: "button", role: "menuitem", onclick: () => { closeViewerMenu(overlay); viewerSave(viewer); } }, [icon("download", 16), el("span", {}, t("attachment.action.save"))]),
    el("button", { class: "viewer-menu-item viewer-menu-print", type: "button", role: "menuitem", onclick: () => { closeViewerMenu(overlay); viewerPrint(viewer); } }, [icon("print", 16), el("span", {}, t("attachment.action.print"))]),
  ]);
  menu.style.insetInlineStart = `${Math.max(0, x)}px`;
  menu.style.insetBlockStart = `${Math.max(0, y)}px`;
  overlay.append(menu);
  const first = menu.querySelector("button");
  if (first) first.focus();
}

function fileViewerNode() {
  const viewer = state.fileViewer;
  if (!viewer) return null;
  const body = viewer.kind === "image" ? fileViewerImage(viewer) : fileViewerPdf(viewer);
  const stage = el("div", { class: "viewer-stage" }, [body]);
  const overlay = el(
    "div",
    { class: "viewer-overlay", role: "dialog", "aria-modal": "true", "aria-label": viewer.filename || t("common.attachment") },
    [
      stage,
      el("div", { class: "viewer-actions" }, [
        viewerButton("viewer-btn viewer-save", "download", t("attachment.action.save"), () => viewerSave(viewer)),
        viewerButton("viewer-btn viewer-print", "print", t("attachment.action.print"), () => viewerPrint(viewer)),
        viewerButton("viewer-btn viewer-close", "close", t("common.close"), closeFileViewer),
      ]),
    ]
  );
  stage.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    const box = overlay.getBoundingClientRect();
    openViewerMenu(overlay, viewer, event.clientX - box.left, event.clientY - box.top);
  });
  overlay.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".viewer-menu")) closeViewerMenu(overlay);
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (overlay.querySelector(".viewer-menu")) {
        closeViewerMenu(overlay);
        return;
      }
      closeFileViewer();
    } else if (event.key === "Tab") {
      trapViewerFocus(event, overlay);
    }
  });
  window.setTimeout(() => {
    if (state.fileViewerFocused) return;
    const close = overlay.querySelector(".viewer-close");
    if (close) close.focus();
    state.fileViewerFocused = true;
  }, 0);
  return overlay;
}

function fileName(file) {
  return file.filename || "";
}

function attachmentRowContent(filename) {
  return [
    el("span", { class: "row-dot" }, [icon("clip", 14)]),
    el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, filename || t("common.attachment"))]),
  ];
}

function attachmentActionRow(className, iconName, label, onclick) {
  return el("button", { type: "button", class: `row ${className}`, onclick }, [
    el("span", { class: "row-dot" }, [icon(iconName, 14)]),
    el("div", { class: "row-main" }, [el("div", { class: "row-title full" }, label)]),
  ]);
}

async function runAttachmentAction(action, file, filename, trigger) {
  try {
    if (action === "open") {
      await openAppFile(file.url, filename, trigger);
      return;
    }
    const loaded = await fetchAppFile(file.url, filename);
    if (action === "save") await saveFile(loaded.blob, loaded.filename);
    else await printFile(loaded.blob, loaded.filename);
  } catch (error) {
    toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
  }
}

function attachmentActionsSheet(file, trigger) {
  const filename = file.filename || t("common.attachment");
  const choose = (action) => () => {
    discardSheet();
    runAttachmentAction(action, file, filename, trigger);
  };
  return sheet(filename, [
    el("div", { class: "rows" }, [
      attachmentActionRow("attach-open", "open", t("attachment.action.open"), choose("open")),
      attachmentActionRow("attach-save", "download", t("attachment.action.save"), choose("save")),
      attachmentActionRow("attach-print", "print", t("attachment.action.print"), choose("print")),
    ]),
  ]);
}

function attachmentButton(file) {
  const filename = file.filename || t("common.attachment");
  const button = el(
    "button",
    { type: "button", class: "row read" },
    attachmentRowContent(filename)
  );
  button.addEventListener("click", () => {
    openNestedSheet(() => attachmentActionsSheet(file, button));
  });
  return button;
}

function attachmentRows(files) {
  const rows = el("div", { class: "rows" });
  for (const file of files) {
    rows.append(
      file.url ? attachmentButton(file) : el("div", { class: "row read disabled" }, attachmentRowContent(fileName(file)))
    );
  }
  return rows;
}

function techValue(entry) {
  if (entry.kind === "bool") return entry.value ? t("common.yes") : t("common.no");
  if (entry.kind === "epoch") return formatEpoch(entry.value);
  return entry.value;
}

function techRows(entries) {
  return (entries || [])
    .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== "")
    .map((entry) => [entry.label, techValue(entry)])
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
}

function techDetailsSheet(entries) {
  const rows = techRows(entries);
  const body = [
    el("p", { class: "dlg-text" }, t("common.techDetails.text")),
    rows.length ? factList(rows) : el("p", { class: "dlg-text" }, t("common.techDetails.empty")),
  ];
  return sheet([icon("info", 16), el("span", {}, t("common.techDetails"))], body);
}

function techDetailsButton(entries) {
  return el("button", {
    class: "tech-btn",
    type: "button",
    "aria-label": t("common.techDetails"),
    onclick: (event) => {
      if (event) event.stopPropagation();
      openNestedSheet(() => techDetailsSheet(entries));
    },
  }, [icon("info", 16)]);
}

let bootWatchdog = 0;

async function boot() {
  state.detached = false;
  window.clearTimeout(bootWatchdog);
  bootWatchdog = window.setTimeout(() => {
    renderNotice(detachedRoot(), t("app.error.service.title"), t("app.error.service.text"), true);
  }, BOOT_TIMEOUT_MS);
  try {
    await bootOnce();
  } finally {
    window.clearTimeout(bootWatchdog);
  }
}

async function bootOnce() {
  const app = root();
  state.theme = readTheme();
  applyTheme(state.theme);
  state.me = { forename: readCachedForename() };
  await loadBaseLanguage();
  try {
    const health = await getJson("api/health");
    await applyLanguageChoice(readStoredText(LANGUAGE_PENDING_KEY) || health.language);
    if (!health.configured) return renderWizard(detachedRoot(), boot);
    if (health.connection === "auth_failed") {
      return renderReconnect(detachedRoot(), health.username || "", health.connection_id || "", health.auth_reason || "");
    }
    if (health.connection === "network") {
      return renderNotice(detachedRoot(), t("app.error.unreachable.title"), t("app.error.unreachable.text"), true);
    }
    state.account = health.username || "";
    state.schools = Array.isArray(health.connections) ? health.connections : [];
    applySchoolStatus(health.connections);
    state.modules = applyModules(health.modules);
    state.appVersion = String(health.version || "");
    state.config = await getJson("api/config");
    await loadChildren();
    if (state.childId && moduleOn("timetable")) {
      try {
        await loadTimetable();
      } catch (error) {
        if (handleApiFailure(error)) return;
        state.timetable = { lessons: [], error: errorCode(error) };
      }
    }
    render();
    loadRest();
    setupVisibilityRefresh();
    resumeCalendarPage();
  } catch (error) {
    if (handleApiFailure(error)) return;
    renderNotice(detachedRoot(), t("app.error.service.title"), t("app.error.service.text"), true);
  }
}

async function loadChildren() {
  let answer = null;
  try {
    answer = await getJson("api/children");
  } catch (error) {
    const code = errorCode(error);
    if (code === ERROR_AUTH_FAILED || code === ERROR_NOT_CONFIGURED) throw error;
    state.childrenFailure = (error && error.body) || { error: code };
    state.children = [];
    state.childId = null;
    return;
  }
  const list = Array.isArray(answer) ? answer : [];
  state.childrenFailure = null;
  state.children = list;
  state.childId = list.length ? list[0].key : null;
}

function childrenFailureText() {
  const failure = state.childrenFailure;
  if (failure && failure.message_key) return t(failure.message_key, failure.message_vars);
  return t("overview.children.failed");
}

function childrenFailureCard() {
  const entries = diagnosisEntries(state.childrenFailure && state.childrenFailure.diagnosis);
  return el("div", { class: "card overview-failed" }, [
    el("p", { class: "dlg-text", style: "margin:0 0 12px" }, childrenFailureText()),
    state.childrenRetrying ? loadingBlock() : retryButton(retryChildren),
    entries.length ? techDetailsButton(entries) : null,
  ]);
}

async function retryChildren() {
  if (state.childrenRetrying) return;
  state.childrenRetrying = true;
  rerender();
  try {
    await loadChildren();
  } catch (error) {
    if (handleApiFailure(error)) return;
    state.childrenFailure = { error: errorCode(error) };
  }
  state.childrenRetrying = false;
  if (state.children.length) {
    await refreshEverything();
    return;
  }
  rerender();
}

function routeOrIgnoreBackgroundFailure(error) {
  handleApiFailure(error);
}

async function loadNotifyServices() {
  const outcome = await reload("notifyServices", () => getJson("api/notify-services"), false);
  if (!outcome) return;
  if (outcome.data) {
    state.notifyServices = outcome.data.services || [];
    state.notifySupervisor = !!outcome.data.supervisor;
  } else {
    state.notifyServices = [];
    state.notifySupervisor = null;
  }
  rerender();
}

function loadRest() {
  getJson("api/me").then((data) => {
    state.me = data && !data.error ? data : {};
    writeCachedForename(state.me.forename || "");
    rerender();
  }).catch(routeOrIgnoreBackgroundFailure);
  loadNotifyServices();
  loadHolidays().then(rerender).catch(routeOrIgnoreBackgroundFailure);
  if (moduleOn("letters")) loadLetters("current");
  if (moduleOn("pinboard")) loadPinboard();
  if (moduleOn("conferences")) loadConferences();
  if (moduleOn("timetable")) {
    loadMarks();
    loadCancellations();
  }
  if (moduleOn("absences")) loadAbsences();
  if (moduleOn("messenger")) loadMessengerRooms();
}

const VISIBILITY_REFRESH_MS = 5 * 60 * 1000;
let lastVisibilityRefreshAt = Date.now();

function hasOpenFormGuard() {
  return !!(state.sheet || state.detail || state.absenceForm || state.teacherRoom || state.letterDetail);
}

const VIEW_STALE_MS = 2 * 60 * 1000;

function activeViewLoadKeys() {
  switch (state.view) {
    case "post":
      return [postSegmentIs("letters") ? lettersLoadKey(state.lettersTab) : "pinboard"];
    case "messenger":
      return [MESSENGER_LOAD_KEY];
    case "conferences":
      return ["conferences"];
    case "absence":
      return ["absence"];
    case "timetable":
      return ["timetable", "marks", "cancellations"];
    case "overview":
      return ["pinboard", lettersLoadKey(state.lettersTab), "marks", "cancellations", "absence", "conferences", MESSENGER_LOAD_KEY];
    default:
      return [];
  }
}

function activeViewIsStale() {
  const now = Date.now();
  return activeViewLoadKeys().some((key) => {
    const stamp = Number(state.loadedAt[key]) || 0;
    return stamp > 0 && now - stamp > VIEW_STALE_MS;
  });
}

function revalidateActiveView() {
  if (hasOpenFormGuard()) return;
  if (!activeViewIsStale()) return;
  Promise.resolve(refreshActiveView()).catch(routeOrIgnoreBackgroundFailure);
}

function flushDeferredRefresh() {
  if (!state.refreshDeferred || document.hidden || hasOpenFormGuard()) return;
  state.refreshDeferred = false;
  window.setTimeout(() => {
    Promise.resolve(refreshActiveView()).catch(routeOrIgnoreBackgroundFailure);
  }, 0);
}

function setupVisibilityRefresh() {
  const maybeRefresh = () => {
    if (document.hidden) return;
    if (Date.now() - lastVisibilityRefreshAt < VISIBILITY_REFRESH_MS) return;
    if (hasOpenFormGuard()) {
      state.refreshDeferred = true;
      return;
    }
    refreshActiveView();
  };
  document.addEventListener("visibilitychange", maybeRefresh);
  window.addEventListener("pageshow", maybeRefresh);
  window.addEventListener("focus", maybeRefresh);
}

async function refreshActiveView() {
  lastVisibilityRefreshAt = Date.now();
  await refreshOutageStatus();
  switch (state.view) {
    case "overview": {
      await Promise.all([
        ...state.children.map((child) => loadOverviewWeek(child.key, 0)),
        loadHolidays(),
        loadAbsences(),
        loadMarks(),
        loadCancellations(),
        loadLetters(state.lettersTab),
        loadPinboard(),
        loadConferences(),
        loadMessengerRooms(),
      ]);
      rerender();
      break;
    }
    case "timetable":
      await Promise.all([loadHolidays(), loadMarks(), loadCancellations(), reloadTimetable(), ...siblingWeekLoads()]);
      rerender();
      break;
    case "absence":
      await loadAbsences();
      break;
    case "post":
      await (postSegmentIs("letters") ? loadLetters(state.lettersTab) : loadPinboard());
      break;
    case "messenger":
      await loadMessengerRooms();
      if (state.messengerRoom) await loadMessengerHistory();
      break;
    case "conferences":
      await loadConferences();
      break;
    default:
      rerender();
  }
}

async function refreshEverything() {
  lastVisibilityRefreshAt = Date.now();
  await refreshOutageStatus();
  if (state.childrenFailure) {
    try {
      await loadChildren();
    } catch (error) {
      routeOrIgnoreBackgroundFailure(error);
    }
  }
  const jobs = [loadHolidays()];
  if (moduleOn("timetable")) {
    jobs.push(...state.children.map((child) => loadOverviewWeek(child.key, 0)));
    jobs.push(loadMarks(), loadCancellations(), reloadTimetable());
  }
  if (moduleOn("absences")) jobs.push(loadAbsences());
  if (moduleOn("letters")) jobs.push(loadLetters(state.lettersTab));
  if (moduleOn("pinboard")) jobs.push(loadPinboard());
  if (moduleOn("conferences")) jobs.push(loadConferences());
  if (moduleOn("messenger")) jobs.push(loadMessengerRooms());
  if (state.messengerRoom) jobs.push(loadMessengerHistory());
  await Promise.all(jobs);
  rerender();
}

const PULL_REFRESH_THRESHOLD = 70;
const PULL_REFRESH_MAX = 90;

function pullIndicator() {
  return el("div", { class: "pull-indicator" }, [el("span", { class: "spin" })]);
}

function setupPullToRefresh(screen) {
  let startY = 0;
  let startX = 0;
  let tracking = false;
  let armed = false;
  let refreshing = false;
  let indicator = null;

  const cleanup = () => {
    tracking = false;
    armed = false;
    screen.style.removeProperty("scroll-snap-type");
    if (indicator) {
      indicator.remove();
      indicator = null;
    }
  };

  screen.addEventListener("touchstart", (event) => {
    if (refreshing || event.touches.length !== 1) return;
    if (hasOpenFormGuard() || screen.scrollTop > 1) return;
    tracking = true;
    armed = false;
    screen.style.setProperty("scroll-snap-type", "none");
    startY = event.touches[0].clientY;
    startX = event.touches[0].clientX;
  });

  screen.addEventListener("touchmove", (event) => {
    if (!tracking || refreshing) return;
    const dy = event.touches[0].clientY - startY;
    const dx = Math.abs(event.touches[0].clientX - startX);
    if (dy <= 0 || screen.scrollTop > 1) {
      cleanup();
      return;
    }
    if (dx > dy * PULL_AXIS_RATIO) {
      cleanup();
      return;
    }
    if (!indicator) {
      indicator = pullIndicator();
      screen.prepend(indicator);
    }
    armed = dy > PULL_REFRESH_THRESHOLD;
    indicator.classList.toggle("armed", armed);
    indicator.style.height = `${Math.min(dy, PULL_REFRESH_MAX)}px`;
  });

  const finish = () => {
    if (!tracking) return;
    tracking = false;
    if (armed && indicator) {
      refreshing = true;
      indicator.style.height = `${PULL_REFRESH_THRESHOLD}px`;
      Promise.resolve(refreshEverything()).finally(() => {
        refreshing = false;
        cleanup();
      });
    } else {
      cleanup();
    }
  };

  screen.addEventListener("touchend", finish);
  screen.addEventListener("touchcancel", cleanup);
}

function renderNotice(app, title, text, retry) {
  app.replaceChildren(
    el("div", { class: "screen" }, [
      el("div", { class: "wrap" }, [
        emptyBlock("alert", title, text, retry ? retryButton(boot) : null),
        reportSaveBlock(),
      ]),
    ])
  );
}

function reportSaveBlock() {
  const status = el("p", { class: "cal-hint report-status", role: "status" });
  const button = el("button", { class: "btn ghost slim report-save", type: "button" }, [
    icon("download", 16),
    t("help.report.save"),
  ]);
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = t("help.preparing");
    try {
      const bundle = await fetchAppFile(NOTICE_BUNDLE_PATH, HELP_BUNDLE_NAME);
      await saveFile(bundle.blob, bundle.filename || HELP_BUNDLE_NAME);
      status.textContent = t("help.report.saved");
    } catch (error) {
      status.textContent = t("help.report.failed");
    }
    button.disabled = false;
  });
  return el("div", { class: "report-save-block" }, [button, status]);
}

function lockedPasswordReveal(form) {
  const holder = el("div", { class: "locked-password" });
  const reveal = el("button", { class: "btn ghost slim locked-password-reveal", type: "button" }, t("account.reconnect.lockedNewPassword"));
  reveal.addEventListener("click", () => holder.replaceChildren(form));
  holder.append(reveal);
  return holder;
}

async function resetSchoolSetup(connectionId) {
  try {
    await postJson("api/wizard/reset", { connection_id: connectionId || "" });
  } catch (error) {
    return false;
  }
  dropSheet();
  renderWizard(detachedRoot(), boot);
  return true;
}

function renderReconnect(app, username, connectionId, reason) {
  const account = el("input", {
    class: "inp",
    type: "text",
    name: "username",
    autocomplete: "username",
    dir: "ltr",
    value: username || "",
    readonly: "readonly",
    "aria-label": t("common.username"),
  });
  const input = el("input", {
    class: "inp",
    type: "password",
    name: "password",
    autocomplete: "current-password",
    placeholder: t("account.reconnect.passwordPlaceholder"),
    "aria-label": t("account.reconnect.passwordPlaceholder"),
  });
  const message = el("p", { class: "dlg-text", style: "margin:12px 0 0" }, "");
  const save = el("button", { class: "btn", type: "submit" }, t("account.reconnect.submit"));
  save.addEventListener("click", async () => {
    if (!input.value) {
      message.textContent = t("account.reconnect.missingPassword");
      return;
    }
    save.disabled = true;
    save.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.checking")));
    try {
      const result = await postJson("api/password/repair", { password: input.value, connection_id: connectionId || "" });
      if (result && result.ok) return boot();
      message.textContent = apiMessage(result, "account.reconnect.failed");
    } catch (error) {
      message.textContent = t("account.reconnect.offline");
    }
    save.disabled = false;
    save.replaceChildren(document.createTextNode(t("account.reconnect.submit")));
  });
  const form = el("form", { class: "stack-form" }, [
    username ? el("label", { class: "field" }, [el("span", { class: "lbl" }, t("common.username")), account]) : account,
    el("label", { class: "field" }, [el("span", { class: "lbl" }, t("account.reconnect.passwordLabel")), input]),
    save,
  ]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  const setupNeeded = reason === REASON_TWOFACTOR_SETUP;
  const codeRefused = reason === REASON_CODE_STEP_FAILED;
  const setupFirst = setupNeeded || codeRefused;
  const locked = reason === REASON_LOCKED;
  const setupKey = codeRefused ? "account.reconnect.reset" : "account.reconnect.setupTwofactor";
  const setup = el("button", { class: "btn", type: "button" }, t(setupKey));
  const wrap = el("div", { class: "wrap" }, [
    el("h1", { class: "page-title", style: "margin-top:28px" }, t("account.reconnect.title")),
    el("p", { class: "dlg-text reconnect-reason" }, t(LOGIN_REASON_KEYS[reason] || "account.reconnect.text")),
    setupFirst ? setup : locked ? lockedPasswordReveal(form) : form,
    message,
    setupFirst ? null : el("p", { class: "dlg-text", style: "margin-top:28px" }, t("account.reconnect.resetText")),
    reportSaveBlock(),
  ]);
  const runReset = async (panel, confirmButton) => {
    confirmButton.disabled = true;
    confirmButton.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.pleaseWait")));
    if (await resetSchoolSetup(connectionId)) return;
    panel.remove();
    message.textContent = t("account.reconnect.resetFailed");
  };
  const askReset = (actionKey, noteKey) => {
    if (wrap.querySelector(".sheet-confirm")) return;
    const confirmButton = el("button", { class: "btn destructive", type: "button" }, t(actionKey));
    const panel = el("div", {
      class: "sheet-confirm",
      role: "alertdialog",
      "aria-modal": "true",
      "aria-label": t(actionKey),
    }, [
      el("p", { class: "dlg-text" }, t(noteKey)),
      el("div", { class: "btn-stack" }, [
        confirmButton,
        el("button", { class: "btn ghost", type: "button", onclick: () => panel.remove() }, t("common.cancel")),
      ]),
    ]);
    confirmButton.addEventListener("click", () => runReset(panel, confirmButton));
    wrap.append(panel);
  };
  const askFullReset = () => askReset("account.reconnect.reset", "account.reconnect.resetNote");
  setup.addEventListener("click", codeRefused ? askFullReset : () => askReset(setupKey, "account.reconnect.setupNote"));
  if (!setupFirst) wrap.append(el("button", { class: "btn ghost", type: "button", onclick: askFullReset }, t("account.reconnect.reset")));
  app.replaceChildren(el("div", { class: "screen" }, [wrap]));
}

async function loadTimetable() {
  state.timetable = await getJson(`api/timetable?child=${encodeURIComponent(state.childId)}&week=${state.weekOffset}`);
  state.config = await getJson("api/config");
}

function viewFor(view) {
  if (!anyModuleOn() && view !== "settings") return noModulesView();
  switch (view) {
    case "timetable": return timetableView();
    case "absence": return absenceView();
    case "post": return state.letterDetail && !paneOpen() ? letterDetailView() : postView();
    case "messenger": return state.messengerRoom && !paneOpen() ? messengerRoomView() : messengerView();
    case "conferences": return conferencesView();
    case "settings": return settingsPaneActive() ? settingsView() : state.helpPage ? helpPageView() : state.settingsPage ? settingsPageView() : state.settingsSchoolId && !paneOpen() ? schoolPageView() : settingsView();
    default: return overviewView();
  }
}

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

function overviewWeekData(childId, week) {
  const weekIdx = week || 0;
  const sameWeek = weekIdx === (state.weekOffset || 0);
  if (weekIdx === 0 && sameWeek && childId === state.childId && state.timetable) return state.timetable;
  const byChild = state.overviewWeeks[childId];
  return byChild ? byChild[weekIdx] || null : null;
}

async function loadOverviewWeek(childId, week) {
  const weekIdx = week || 0;
  const key = `ovWeek:${childId}:${weekIdx}`;
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
  if (outcome.data) state.overviewWeeks[childId][weekIdx] = outcome.data;
  else if (outcome.error) state.overviewWeeks[childId][weekIdx] = { lessons: [], error: outcome.error };
  if (state.view === "overview" || state.view === "timetable") rerender();
}

const OVERVIEW_ENTRY_CAP = 12;
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

function firstName(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const given = text.includes(",") ? text.split(",").pop() : text;
  return given.trim().split(/\s+/)[0] || "";
}

function teacherSurname(lesson) {
  if (!lesson) return "";
  return lesson.teacher_surname || lesson.teacher_label || lesson.teacher_code || "";
}

function childFirstName(child) {
  return firstName(child && child.name) || String((child && child.name) || "");
}

function childNameKey(child) {
  return childFirstName(child).toLocaleLowerCase();
}

function childNameSharedWith(child, sameSchool) {
  const key = childNameKey(child);
  if (!key) return false;
  const school = schoolOfChild(child);
  return state.children.some((other) =>
    other !== child && other.key !== child.key && childNameKey(other) === key && (schoolOfChild(other) === school) === sameSchool);
}

function childShortName(child) {
  const name = childFirstName(child);
  return childNameSharedWith(child, true) ? String(child.name || "") || name : name;
}

function childSchoolSuffix(child) {
  if (!childNameSharedWith(child, false)) return "";
  const school = schoolOfChild(child);
  return schoolShortName(school) || String(child.school || "");
}

function childLabelWithSchool(child, label) {
  const school = childSchoolSuffix(child);
  return school ? t("child.labelWithSchool", { label, school }) : label;
}

function childChipLabel(child) {
  const name = childShortName(child);
  if (!name) return child.class_name || t("child.sheet");
  return childLabelWithSchool(child, name);
}

function childPillLabel(child) {
  const name = childShortName(child);
  const className = child.class_name || "";
  const label = name && className ? t("child.nameWithClass", { name, class: className }) : name || className || t("child.sheet");
  return childLabelWithSchool(child, label);
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

function lessonSlotStatus(start, minutesNow) {
  if (start === null) return "unknown";
  if (minutesNow >= start + LESSON_MINUTES) return "past";
  return minutesNow >= start ? "now" : "future";
}

function todayTimeline(groups, times, childId, minutesNow) {
  const starts = groups.map((group) => lessonTimeMinutes(group.lessons[0], times));
  const teaching = groups.map((group) =>
    group.lessons.some((lesson) => !lessonDropped(lesson, childId)));
  const statuses = starts.map((start) => lessonSlotStatus(start, minutesNow));
  let nowIndex = -1;
  let nextIndex = -1;
  groups.forEach((group, index) => {
    if (!teaching[index]) return;
    if (nowIndex < 0 && statuses[index] === "now") nowIndex = index;
    if (nextIndex < 0 && statuses[index] === "future") nextIndex = index;
  });
  const taught = starts.filter((start, index) => teaching[index]);
  const complete = taught.length > 0 && taught.every((start) => start !== null);
  const schoolEnd = complete ? Math.max(...taught) + LESSON_MINUTES : null;
  const dayOver = taught.length === 0 || (schoolEnd !== null && minutesNow >= schoolEnd);
  return {
    statuses,
    nowIndex,
    nextIndex: nowIndex < 0 && !dayOver ? nextIndex : -1,
    schoolEnd,
    dayOver,
  };
}

function todayChapter(size) {
  const compact = size === layoutBlocks().SIZE_COMPACT;
  const chapter = overviewChapter("today", t("overview.today"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  const now = new Date();
  chapter.meta = formatWeekdayDay(now);
  if (!moduleOn("timetable")) return null;
  if (state.childrenFailure) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewBlock("today:childrenfailed", childrenFailureCard())];
    return chapter;
  }
  if (!state.children.length && !state.childId && !state.timetable) {
    return overviewRest(chapter, "today:nochild", t("overview.noChild"));
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
  if (week.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("today:failed", () => loadOverviewWeek(child.key, 0))];
    return chapter;
  }
  if (!Array.isArray(week.lessons)) return overviewRest(chapter, "today:unreachable", t("overview.timetable.unreachable"));
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
      mark: markAt(child.key, lessonIso(lesson), lesson.period),
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

function todayAbsences(childId, iso) {
  const box = state.absence;
  const entries = box && box.data && Array.isArray(box.data.entries) ? box.data.entries : [];
  return entries.filter((entry) => {
    if (childId && entry.student_id && entry.student_id !== childId) return false;
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
    const parsed = parseAnyDate(cell);
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
    rows.push({ key: `conference:${day || index}:${index}`, day, title: cells[0], sub: cells.slice(1, 4).join(" · "), connection_id: item.connection_id || "" });
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
    sizedRow(size, row.title, row.sub, row.day ? showDate(row.day) : "", false, () => setView("conferences"), [schoolTag(row)])
  ), overviewAllRow("conferences:all", t("overview.all.conferences"), () => setView("conferences")));
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
  if (!moduleOn("timetable") || !state.holidays) return null;
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
    const range = dateRange(showDate(row.period.start), showDate(row.period.end));
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
  if (!upcoming.length) return null;
  const chapter = overviewChapter("next_lesson", t("blocks.next_lesson.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  chapterRows(chapter, size, block, upcoming, (entry) => {
    const time = lessonTime(entry.lesson, periodTimes(entry.week, child.key));
    const start = lessonTimeMinutes(entry.lesson, periodTimes(entry.week, child.key));
    const minutes = start === null ? null : lessonMinutesAhead(entry, start, now);
    const details = [entry.lesson.room || "", teacherSurname(entry.lesson), minutes !== null && minutes > 0 ? minutesUntilLabel(minutes) : ""].filter(Boolean).join(" · ");
    return overviewBlock(
      `next:${child.key}:${entry.iso}:${entry.lesson.period}`,
      sizedRow(
        size,
        entry.lesson.subject_label || entry.lesson.subject_code || t("timetable.lesson.fallback"),
        details,
        `${lessonDayLabel(entry.iso, entry.date)} · ${time || periodShort(entry.lesson.period)}`,
        false,
        overviewOpenTimetable,
        []
      )
    );
  }, null);
  chapter.count = 0;
  return chapter;
}

function weekChapter(size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const child = overviewActiveChild();
  ensureOverviewWeeks([child], [0]);
  const week = overviewWeekData(child.key, 0);
  if (!week || week.error || !Array.isArray(week.lessons) || !week.lessons.length) return null;
  const chapter = overviewChapter("week", t("blocks.week.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  if (state.children.length !== 1) chapter.chips = { active: child.key };
  chapter.size = size;
  chapter.count = 0;
  chapter.bodyClass = size === layoutBlocks().SIZE_COMPACT ? "tt-block tt-compact" : "tt-block";
  chapter.blocks = [overviewBlock(`week:${child.key}`, timetableGrid(week, child.key, { monday: startOfWeek(new Date()), swipe: false }))];
  return chapter;
}

function openTimetableOf(childKey) {
  if (childKey && childKey !== state.childId) {
    state.childId = childKey;
    state.timetable = null;
    setView("timetable");
    reloadTimetable();
    return;
  }
  setView("timetable");
}

function changesChapter(size) {
  if (!moduleOn("timetable") || !state.children.length) return null;
  const block = layoutBlocks().blockOf("changes");
  ensureOverviewWeeks(state.children, [0, 1]);
  const now = new Date();
  const rows = [];
  for (const child of state.children) {
    for (const entry of overviewLessonsAhead(child, isoDate(now), isoDate(addDays(now, OVERVIEW_UPCOMING_DAYS)))) {
      const kind = displayChangeKind(entry.lesson, child.key);
      if (kind) rows.push(Object.assign({ kind }, entry));
    }
  }
  if (!rows.length) return null;
  const chapter = overviewChapter("changes", t("blocks.changes.title"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  chapter.fresh = true;
  return chapterRows(chapter, size, block, rows, (entry) => {
    const lesson = entry.lesson;
    const title = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
    const who = entry.kind === "cancelled" ? "" : [teacherSurname(lesson), lesson.room].filter(Boolean).join(" ");
    const detail = [periodShort(lesson.period), lessonTime(lesson, periodTimes(entry.week, entry.child.key)), who].filter(Boolean).join(" · ");
    const node = sizedRow(size, title, detail, lessonDayLabel(entry.iso, entry.date), false, () => openTimetableOf(entry.child.key), [
      childTag(entry.child),
      schoolTag({ connection_id: connectionOfKey(entry.child.key) }),
    ]);
    const slot = size === layoutBlocks().SIZE_COMPACT ? node.querySelector(".row-side") : node.querySelector(".row-main");
    slot.append(changeTag(entry.kind));
    return overviewBlock(`change:${entry.child.key}:${entry.iso}:${lesson.period}`, node, null, true);
  }, null);
}

const BLOCK_CHAPTERS = {
  today: todayChapter,
  next_lesson: nextLessonChapter,
  week: weekChapter,
  letters: lettersChapter,
  noticeboard: pinboardChapter,
  absences: absencesChapter,
  conferences: conferencesChapter,
  holidays: holidaysChapter,
  changes: changesChapter,
  chat: messengerChapter,
};

function overviewChapters() {
  const chapters = [];
  for (const entry of enabledOverviewBlocks()) {
    const build = BLOCK_CHAPTERS[entry.key];
    const chapter = build ? build(entry.size) : null;
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
      "aria-label": t("overview.page.back", {
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
    const banner = schoolIssueBanner();
    return el("div", { class: "overview-host" }, [banner, ...empty]);
  }
  overviewFlatten(container, chapters);
  const banner = schoolIssueBanner();
  if (!banner) return container;
  return el("div", { class: "overview-host" }, [banner, container]);
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

function overviewToday(size) {
  const chapter = todayChapter(size);
  return chapter ? overviewPanel(chapter, 0, 1, chapter.blocks, 0, null, false, 0) : null;
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
  const sub = teacherSurname(lesson);
  const row = el("button", {
    class: rowClassNames(isPast),
    type: "button",
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId, overviewWeekLessons(entry.childId)),
  }, [
    dot,
    el("div", { class: "row-main" }, [compactLessonTitle(lesson, kind), sub ? el("div", { class: "row-sub" }, sub) : null, markTag(entry.mark)]),
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
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId, overviewWeekLessons(entry.childId)),
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
    onclick: () => openCoursesSheet(lessons, entries[0].time, childId, overviewWeekLessons(childId), courses),
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
  if (data.error || !Array.isArray(data.lessons)) {
    view.append(schoolInOutage(currentConnectionId())
      ? outageEmptyBlock()
      : emptyBlock("alert", t("timetable.error.title"), t("timetable.error.text"), retryButton(() => { state.timetable = null; rerender(); reloadTimetable(); })));
    return view;
  }
  const monday = weekMonday();
  const fullWeek = holidayFullWeek(monday, data);
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
  const outcome = await reload("timetable", () => loadTimetable(), keep, currentConnectionId());
  if (!outcome) return;
  if (outcome.error) state.timetable = { lessons: [], error: outcome.error };
  rerender();
}

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
  const schemeEnd = host.indexOf(":" + "//");
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

function calendarRegionSet() {
  const data = calendarData();
  const regions = data && data.holiday_regions && typeof data.holiday_regions === "object" ? data.holiday_regions : {};
  const id = currentConnectionId();
  if (id && Object.prototype.hasOwnProperty.call(regions, id)) return !!regions[id];
  return Object.values(regions).some(Boolean);
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

async function calendarRequest(path, options) {
  try {
    const response = await fetch(apiUrl(path), options);
    const body = await response.json().catch(() => null);
    if (response.ok) return { ok: true, data: body };
    return { ok: false, message: apiMessage(body, "calendar.subscribe.failed") };
  } catch (error) {
    return { ok: false, message: t("calendar.subscribe.failed") };
  }
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
  body.push(el("p", { class: "cal-hint" }, t(calendarIsRemoteSession() ? "calendar.subscribe.reach.remote" : "calendar.subscribe.reach")));
  const loaded = state.calendar;
  if (!loaded) body.push(loadingBlock());
  else if (loaded.error || !loaded.data) body.push(plainCard(t("calendar.subscribe.loadFailed")));
  else {
    const notice = calendarPortNotice(loaded.data);
    if (notice) body.push(notice);
    for (const node of calendarChildCards(loaded.data)) body.push(node);
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
  if (!(data.subscriptions || []).length) return null;
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

function calendarChildCards(data) {
  const subscriptions = Array.isArray(data.subscriptions) ? data.subscriptions : [];
  if (!state.children.length) return [plainCard(t("overview.noChild"))];
  return state.children.map((child) => {
    const found = subscriptions.find((entry) => entry.child_key === child.key) || null;
    return calendarChildCard(child, found);
  });
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

function calendarNewDraft(child) {
  return {
    id: "",
    childId: child.key,
    components: [calendarRegionSet() ? CALENDAR_COMPONENT_TIMETABLE : CALENDAR_COMPONENT_SCHOOL_HOLIDAYS].concat(moduleOn("timetable") ? [CALENDAR_COMPONENT_OWN_ENTRIES] : []),
    label: "",
    placeholder: calendarDefaultName(child),
    color: CALENDAR_DEFAULT_COLOR,
    error: "",
    busy: false,
  };
}

function calendarEditDraft(subscription, child) {
  return {
    id: subscription.id,
    childId: subscription.child_key,
    components: (subscription.components || []).slice(),
    label: subscription.label || "",
    placeholder: calendarDefaultName(child),
    color: subscription.color || CALENDAR_DEFAULT_COLOR,
    error: "",
    busy: false,
  };
}

function calendarComponents() {
  return CALENDAR_COMPONENTS.filter((component) => {
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

function calendarForm(draft) {
  const wrap = el("div", { class: "cal-form" });
  const problem = el("span", { class: "cal-error" });
  const submit = el("button", { class: "btn", type: "button" });
  const refresh = () => calendarFormRefresh(draft, wrap, problem, submit);
  wrap.append(el("span", { class: "lbl cal-form-lbl" }, t("calendar.subscribe.components")));
  wrap.append(el("div", { class: "field-group" }, calendarComponents().map((component) => calendarComponentRow(draft, component, refresh))));
  if (!calendarRegionSet()) {
    wrap.append(el("p", { class: "cal-hint" }, t("calendar.subscribe.region.locked")));
    wrap.append(el("button", { class: "btn ghost slim", type: "button", onclick: openCalendarRegionSetting }, t("calendar.subscribe.region.open")));
  }
  wrap.append(problem);
  wrap.append(calendarLabelField(draft));
  wrap.append(calendarColorField(draft, refresh));
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
    child_key: draft.childId,
    components: draft.components,
    label: draft.label,
    color: draft.color,
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
  if (!wasUpdate) await autoOpenCalendarPort();
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
    el("b", { class: "cal-name" }, subscription.label || calendarDefaultName(child)),
  ]));
  const parts = (subscription.components || []).map((component) =>
    el("span", { class: "tag" }, t(`calendar.subscribe.component.${component}`))
  );
  if (parts.length) nodes.push(el("div", { class: "cal-parts" }, parts));
  const host = calendarHost();
  if (!host) nodes.push(el("p", { class: "cal-hint" }, t("calendar.subscribe.host.missing")));
  else nodes.push(el("code", { class: "cal-url", dir: "ltr" }, calendarFeedUrl(subscription, CALENDAR_SCHEME_PLAIN)));
  nodes.push(calendarFetchLine(subscription));
  nodes.push(el("p", { class: "cal-hint cal-refresh" }, t(isApplePlatform() ? "calendar.subscribe.refresh.apple" : "calendar.subscribe.refresh")));
  for (const node of calendarActions(subscription, child)) nodes.push(node);
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

function isApplePlatform() {
  const agent = String(navigator.userAgent || "").toLowerCase();
  return agent.includes("iphone") || agent.includes("ipad") || agent.includes("ipod")
    || (agent.includes("macintosh") && Number(navigator.maxTouchPoints || 0) > 1);
}

function calendarWebViewSteps() {
  const firstStep = isApplePlatform()
    ? "calendar.subscribe.webview.step1"
    : "calendar.subscribe.webview.step1Other";
  return el("div", { class: "cal-webview" }, [
    el("span", { class: "overline" }, t("calendar.subscribe.webview.title")),
    el("ol", { class: "cal-step-list" }, [
      el("li", {}, t(firstStep)),
      el("li", {}, t("calendar.subscribe.webview.step2")),
    ]),
    el("p", { class: "cal-hint" }, t("calendar.subscribe.webview.hint")),
    el("p", { class: "cal-hint cal-import-hint" }, t("calendar.subscribe.importHint")),
  ]);
}

function calendarActions(subscription, child) {
  const nodes = [];
  const feedUrl = calendarFeedUrl(subscription, CALENDAR_SCHEME_WEB);
  const plainUrl = calendarFeedUrl(subscription, CALENDAR_SCHEME_PLAIN);
  const busy = !!state.calendarBusy;
  const embedded = isEmbeddedWebView();
  if (embedded && plainUrl) {
    nodes.push(calendarBrowserButton(subscription, calendarSubscribeUrl(plainUrl)));
    nodes.push(calendarWebViewSteps());
  } else if (embedded) {
    nodes.push(noteBlock(t("calendar.subscribe.host.missing")));
  } else if (feedUrl) {
    nodes.push(calendarAddButton(subscription, feedUrl));
  }
  if (state.calendarHandOffStalled === subscription.id) nodes.push(calendarHandOffStalledBlock());
  const row = el("div", { class: "cal-action-row" });
  if (!embedded) row.append(calendarCopyButton(plainUrl));
  else if (plainUrl) row.append(calendarCopyButton(calendarSubscribeUrl(plainUrl)));
  if (typeof qrMatrix === "function" && feedUrl) row.append(calendarQrButton(subscription));
  if (row.childNodes.length) nodes.push(row);
  if (state.calendarQr === subscription.id && feedUrl) {
    const panel = calendarQrPanel(feedUrl);
    if (panel) nodes.push(panel);
  }
  const rotating = state.calendarBusy === calendarActionKey("rotate", subscription);
  const revoking = state.calendarBusy === calendarActionKey("revoke", subscription);
  nodes.push(el("div", { class: "cal-action-row" }, [
    el("button", {
      class: "btn ghost slim cal-edit",
      type: "button",
      disabled: busy ? "disabled" : null,
      onclick: () => { state.calendarDraft = calendarEditDraft(subscription, child); rerender(); },
    }, t("calendar.subscribe.edit")),
    el("button", {
      class: "btn ghost slim cal-rotate",
      type: "button",
      disabled: busy ? "disabled" : null,
      onclick: () => rotateCalendarSubscription(subscription),
    }, rotating ? [el("span", { class: "spin" }), t("calendar.subscribe.rotate")] : [t("calendar.subscribe.rotate")]),
  ]));
  nodes.push(el("button", {
    class: "btn destructive slim cal-delete",
    type: "button",
    disabled: busy ? "disabled" : null,
    onclick: () => revokeCalendarSubscription(subscription),
  }, revoking ? [el("span", { class: "spin" }), t("calendar.subscribe.delete")] : [icon("trash", 16), t("calendar.subscribe.delete")]));
  return nodes;
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

function timetableGrid(data, childId, options) {
  const opts = options || {};
  const owner = childId || state.childId;
  const weekLessons = Array.isArray(data.lessons) ? data.lessons : [];
  const times = periodTimes(data);
  const monday = opts.monday || weekMonday();
  const todayIso = isoDate(new Date());
  const fullWeek = holidayFullWeek(monday, data);
  const blocked = [];
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    blocked.push(!!fullWeek || holidayBlocksLessons(isoDate(addDays(monday, day))));
  }
  const grid = el("div", { class: state.spotlightSubject ? "tt spotlight" : "tt" });
  grid.addEventListener("keydown", spotlightEscape);
  if (opts.swipe !== false) setupWeekSwipe(grid);
  grid.append(el("div", { style: "grid-column:1;grid-row:1" }));
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    const date = addDays(monday, day);
    const entry = holidayDay(isoDate(date));
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
    grid.append(holidayFullField(fullWeek, monday));
    const own = ownPlanLayout(data, owner, monday, blocked.map(() => true), [], 3);
    if (own) for (const node of own.nodes) grid.append(node);
    return grid;
  }
  const visible = data.lessons.filter((lesson) => {
    const day = Number(lesson.day_of_week);
    return !(day >= 1 && day <= HOLIDAY_SCHOOL_DAYS && blocked[day - 1]);
  });
  const periodsWithLessons = visible
    .map((lesson) => Number(lesson.period))
    .filter((n) => Number.isInteger(n) && n > 0);
  const maxPeriod = periodsWithLessons.length ? Math.max(...periodsWithLessons) : 5;
  const rows = Array.from({ length: maxPeriod }, (_, index) => index + 1);
  const own = ownPlanLayout(data, owner, monday, blocked, rows);
  const lineOf = (period) => (own ? own.rowOf.get(period) : period + 1);
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
  for (const field of holidayRunFields(monday, blocked, own ? own.total : maxPeriod)) grid.append(field);
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

function overviewWeekLessons(childId) {
  const week = overviewWeekData(childId, 0);
  return week && Array.isArray(week.lessons) ? week.lessons : [];
}

function weekSubjectOccurrences(subject, weekLessons) {
  return (weekLessons || [])
    .filter((lesson) => lessonSubjectKey(lesson) === subject
      && displayChangeKind(lesson, state.childId) !== "cancelled"
      && !holidayBlocksLessons(lessonIso(lesson)))
    .sort((left, right) =>
      Number(left.day_of_week) - Number(right.day_of_week) || Number(left.period) - Number(right.period));
}

function lessonWeekPosition(lesson, weekLessons) {
  const subject = lessonSubjectKey(lesson);
  if (!subject) return null;
  const occurrences = weekSubjectOccurrences(subject, weekLessons);
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

function lessonCell(lesson, time, compact, childId, weekLessons) {
  const owner = childId || state.childId;
  const week = weekLessons || timetableWeekLessons();
  const kind = displayChangeKind(lesson, owner);
  const mark = markOfLesson(lesson, owner);
  const base = kind === "cancelled" ? "tt-cell out" : kind ? "tt-cell subbed" : "tt-cell";
  const roomLabel = kind === "cancelled" ? t("timetable.change.cancelled") : kind === "changed" ? t("timetable.cell.substitute") : "";
  const subject = lessonSubjectKey(lesson);
  const cell = el("button", {
    class: compact ? `${base} compact` : base,
    type: "button",
    "data-subject": subject || null,
    "aria-label": lessonAriaLabel(lesson, kind, mark),
    onclick: () => openLessonSheet(lesson, time, owner, week),
  }, [
    kind && kind !== "cancelled" ? el("span", { class: "bar" }) : null,
    iservText("span", { class: "sub" }, lesson.subject_code || lesson.subject_label || "?"),
    roomLabel ? el("span", { class: "room" }, roomLabel) : null,
    mark ? el("span", { class: "exam-flag", html: iconSvg("exam", 11) }) : null,
  ]);
  if (mark) cell.classList.add("marked");
  if (subject && subject === state.spotlightSubject) cell.classList.add("spot");
  bindSpotlightHold(cell, spotlightWorthwhile(subject, week) ? subject : null);
  if (!kind) paintSubjectCell(cell, subjectColor(lesson));
  return cell;
}

function lessonAriaLabel(lesson, kind, mark) {
  const subject = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
  const base = kind
    ? t("timetable.aria.lessonChange", { subject, change: changeLabel(kind) })
    : t("timetable.aria.lesson", { subject });
  return mark ? `${base} · ${t("marks.aria.marked", { name: markLabel(mark) })}` : base;
}

const FIELD_KEYS = { subject: "timetable.field.subject", teacher: "timetable.field.teacher", room: "timetable.field.room" };
const FIELD_VALUES = {
  subject: (lesson) => lesson.subject_label || lesson.subject_code || "",
  teacher: (lesson) => lesson.teacher_label || lesson.teacher_code || "",
  room: (lesson) => lesson.room || "",
};

function changeBanner(lesson) {
  const kind = lesson.change_kind;
  if (!kind) return null;
  const dot = el("span", { class: `mark ${kind}` });
  const text =
    kind === "cancelled"
      ? t("timetable.banner.cancelled")
      : kind === "added"
        ? t("timetable.banner.added")
        : t("timetable.banner.changed");
  return el("div", { class: `banner ${kind}` }, [dot, el("b", {}, changeLabel(kind)), el("span", {}, text)]);
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
  if (!lesson.period) return t("common.none");
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
    [t("timetable.field.teacher"), lesson.teacher_label || lesson.teacher_code || t("common.none")],
  ];
  if (lesson.date) facts.splice(1, 0, [t("timetable.fact.day"), showDate(lesson.date)]);
  if (lesson.is_class_teacher) facts.push([t("timetable.fact.role"), t("timetable.fact.classTeacher")]);
  const mark = markOfLesson(lesson, childId);
  const cancellation = cancellationOfLesson(lesson, childId);
  const body = [];
  const weekPosition = lessonWeekPosition(lesson, weekLessons);
  if (weekPosition) {
    body.push(el("p", { class: "lesson-week-count" }, tCount("timetable.lesson.weekCount", weekPosition.total, {
      position: formatNumber(weekPosition.position),
      total: formatNumber(weekPosition.total),
    })));
  }
  const banner = changeBanner(lesson);
  if (banner) body.push(banner);
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

function markAddButton(childId, lesson, time) {
  return el("button", { class: "btn mark-add", type: "button", onclick: () => openMarkForm(childId, lesson, time, null) }, [
    icon("plus", 18),
    el("span", {}, t("marks.action.add")),
  ]);
}

function markChildOf(childId) {
  return childId || state.childId || "";
}

function markList() {
  const box = state.marks;
  return box && box.data && Array.isArray(box.data.marks) ? box.data.marks : [];
}

async function loadMarks() {
  const keep = !!(state.marks && !state.marks.error);
  const outcome = await reload("marks", () => getJson("api/marks"), keep);
  if (!outcome) return;
  if (outcome.data) state.marks = { data: outcome.data };
  else if (outcome.error) state.marks = { error: outcome.error };
  rerender();
}

function lessonIso(lesson) {
  const parsed = parseAnyDate(lesson && lesson.date);
  return parsed ? isoDate(parsed) : "";
}

function markAt(childId, iso, period) {
  if (!childId || !iso) return null;
  return markList().find(
    (entry) => entry.child_key === childId && entry.date === iso && Number(entry.period) === Number(period)
  ) || null;
}

function cancellationList() {
  const box = state.cancellations;
  return box && box.data && Array.isArray(box.data.cancellations) ? box.data.cancellations : [];
}

async function loadCancellations() {
  const keep = !!(state.cancellations && !state.cancellations.error);
  const outcome = await reload("cancellations", () => getJson("api/cancellations"), keep);
  if (!outcome) return;
  if (outcome.data) state.cancellations = { data: outcome.data };
  else if (outcome.error) state.cancellations = { error: outcome.error };
  rerender();
}

function cancellationAt(childId, iso, period) {
  if (!childId || !iso) return null;
  return cancellationList().find(
    (entry) => entry.child_key === childId && entry.date === iso && Number(entry.period) === Number(period)
  ) || null;
}

function cancellationOfLesson(lesson, childId) {
  return cancellationAt(markChildOf(childId), lessonIso(lesson), lesson && lesson.period);
}

function lessonDropped(lesson, childId) {
  return lesson.change_kind === "cancelled" || !!cancellationOfLesson(lesson, childId);
}

function displayChangeKind(lesson, childId) {
  if (lesson.change_kind) return lesson.change_kind;
  return cancellationOfLesson(lesson, childId) ? "cancelled" : "";
}

function cancellationRequest(path, options) {
  return jsonRequest(path, options, "timetable.cancel.error");
}

async function runCancellationAction(request, doneKey) {
  const outcome = await request();
  if (!outcome.ok) {
    toast(outcome.message, "bad");
    return false;
  }
  discardSheet();
  await loadCancellations();
  toast(t(doneKey));
  return true;
}

function addCancellation(childId, lesson) {
  const anchor = markLessonAnchor(lesson, markChildOf(childId));
  if (!anchor) return Promise.resolve(false);
  return runCancellationAction(
    () => cancellationRequest("api/cancellations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ child_key: anchor.child_key, date: anchor.date, period: anchor.period }),
    }),
    "timetable.cancel.toast.saved"
  );
}

function removeCancellation(cancellation) {
  return runCancellationAction(
    () => cancellationRequest(`api/cancellations/${encodeURIComponent(cancellation.id)}`, { method: "DELETE" }),
    "timetable.cancel.toast.removed"
  );
}

function cancellationPanel() {
  return el("div", { class: "mark-clarify", role: "group", "aria-label": t("timetable.cancel.title") }, [
    el("div", { class: "mark-clarify-head" }, [icon("alert", 16), el("b", {}, t("timetable.cancel.title"))]),
    el("p", { class: "mark-clarify-text" }, t("timetable.cancel.hint")),
  ]);
}

function markLessonAnchor(lesson, childId) {
  const iso = lessonIso(lesson);
  if (!iso || !childId) return null;
  const period = Number(lesson.period);
  if (!Number.isInteger(period) || period <= 0) return null;
  const subject = lesson.subject_code || lesson.subject_label || "";
  return subject ? { child_key: childId, date: iso, period, subject_code: subject } : null;
}

function markOfLesson(lesson, childId) {
  return markAt(markChildOf(childId), lessonIso(lesson), lesson && lesson.period);
}

function markLabel(mark) {
  return (mark && mark.name) || t("marks.default");
}

function markSubjectLabel(mark) {
  const code = (mark && mark.subject_code) || "";
  const subjects = connectionConfig(connectionOfKey(mark && mark.child_key) || currentConnectionId()).subjects || {};
  const stored = subjects[code];
  return (stored && stored.label) || code;
}

function markNeedsCheck(mark) {
  return !!(mark && MARK_CLARIFY_KEYS[mark.state]);
}

function marksOfDay(childId, iso) {
  return markList().filter((entry) => entry.child_key === childId && entry.date === iso);
}

function markNameHistory() {
  try {
    const parsed = JSON.parse(readStoredText(MARK_NAMES_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value) => typeof value === "string" && value.trim()).slice(0, MARK_NAME_CHIPS);
  } catch (error) {
    return [];
  }
}

function storeMarkNames(names) {
  writeStoredText(MARK_NAMES_KEY, names.length ? JSON.stringify(names) : "");
}

function rememberMarkName(name) {
  const text = String(name || "").trim();
  if (!text) return;
  storeMarkNames([text].concat(markNameHistory().filter((value) => value !== text)).slice(0, MARK_NAME_CHIPS));
}

function forgetMarkName(name) {
  storeMarkNames(markNameHistory().filter((value) => value !== name));
}

function markPanel(mark, childId, lesson, time) {
  const rows = [
    el("div", { class: "cell mark-cell" }, [
      el("div", { class: "cell-head" }, [icon("exam", 16), el("span", { class: "field-label" }, t("marks.default"))]),
      iservText("div", { class: "mark-name" }, markLabel(mark)),
      mark.state === MARK_STATE_SUBSTITUTED
        ? el("p", { class: "mark-note" }, t("marks.state.substituted"))
        : null,
    ]),
  ];
  const panel = el("div", { class: "field-group mark-panel" }, rows);
  const clarify = markClarifyPanel(mark, childId, lesson, time);
  if (!clarify) return panel;
  return el("div", { class: "mark-block" }, [panel, clarify]);
}

function markClarifyPanel(mark, childId, lesson, time) {
  const keys = MARK_CLARIFY_KEYS[mark.state];
  if (!keys) return null;
  return el("div", { class: "mark-clarify", role: "group", "aria-label": t(keys.title) }, [
    el("div", { class: "mark-clarify-head" }, [icon("alert", 16), el("b", {}, t(keys.title))]),
    el("p", { class: "mark-clarify-text" }, t(keys.text)),
    el("div", { class: "btn-stack" }, [
      el("button", { class: "btn ghost", type: "button", onclick: keepMark }, t("marks.clarify.keep")),
      el("button", { class: "btn ghost", type: "button", onclick: () => openMarkMove(mark, childId) }, t("marks.clarify.move")),
      el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.clarify.remove")),
    ]),
  ]);
}

function openMarkSheet(mark, childId) {
  openSheet(() => markSheet(mark, markChildOf(childId)));
}

function markSheet(mark, childId) {
  const body = [
    el("p", { class: "dlg-text" }, t("marks.origin", {
      subject: markSubjectLabel(mark),
      period: formatNumber(mark.period),
    })),
  ];
  const clarify = markClarifyPanel(mark, childId, null, "");
  if (clarify) body.push(clarify);
  const foot = clarify
    ? null
    : [
      el("div", { class: "btn-stack" }, [
        el("button", { class: "btn ghost", type: "button", onclick: () => openMarkForm(childId, null, "", mark) }, t("marks.action.rename")),
        el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.action.remove")),
      ]),
    ];
  return sheet(markLabel(mark), body, foot);
}

function markDayLessons(childId, iso) {
  const weeks = [];
  if (state.timetable && childId === state.childId) weeks.push(state.timetable);
  const byChild = state.overviewWeeks[childId] || {};
  for (const key of Object.keys(byChild)) weeks.push(byChild[key]);
  const seen = new Set();
  const found = [];
  for (const week of weeks) {
    for (const lesson of (week && week.lessons) || []) {
      if (lessonIso(lesson) !== iso) continue;
      const key = `${lesson.period}:${lesson.subject_code}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(lesson);
    }
  }
  return found.sort((first, second) => Number(first.period) - Number(second.period));
}

function markMoveTargets(mark, childId) {
  return markDayLessons(childId, mark.date).filter((lesson) => {
    if (Number(lesson.period) === Number(mark.period)) return false;
    if (displayChangeKind(lesson, childId) === MARK_STATE_CANCELLED) return false;
    if (!markLessonAnchor(lesson, childId)) return false;
    return !markAt(childId, mark.date, lesson.period);
  });
}

function openMarkMove(mark, childId) {
  openSheet(() => markMoveSheet(mark, markChildOf(childId)));
}

function markMoveSheet(mark, childId) {
  const targets = markMoveTargets(mark, childId);
  if (!targets.length) return sheet(t("marks.move.title"), [el("p", { class: "dlg-text" }, t("marks.move.empty"))]);
  const rows = targets.map((lesson) => {
    const label = t("marks.move.option", {
      period: formatNumber(lesson.period),
      subject: lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback"),
    });
    return el("button", { class: "row mark-target", type: "button", onclick: () => moveMark(mark, lesson) }, [
      el("span", { class: "row-dot" }, [el("i", {})]),
      el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, label)]),
      el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, lessonTime(lesson) || periodShort(lesson.period))]),
    ]);
  });
  return sheet(t("marks.move.title"), [el("div", { class: "rows" }, rows)]);
}

function jsonRequest(path, options, fallbackKey) {
  return fetch(apiUrl(path), options)
    .then((response) => response.json().catch(() => null).then((body) => ({ response, body })))
    .then(({ response, body }) => {
      if (response.ok) return { ok: true, data: body };
      return { ok: false, message: apiMessage(body, fallbackKey) };
    })
    .catch(() => ({ ok: false, message: t(fallbackKey) }));
}

function markRequest(path, options) {
  return jsonRequest(path, options, "marks.error.failed");
}

function markPost(path, body) {
  return markRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

async function runMarkAction(request, doneKey) {
  const outcome = await request();
  if (!outcome.ok) {
    toast(outcome.message, "bad");
    return false;
  }
  discardSheet();
  await loadMarks();
  toast(t(doneKey));
  return true;
}

function keepMark() {
  discardSheet();
  toast(t("marks.clarify.kept"));
}

function removeMark(mark) {
  return runMarkAction(
    () => markRequest(`api/marks/${encodeURIComponent(mark.id)}`, { method: "DELETE" }),
    "marks.toast.removed"
  );
}

function moveMark(mark, lesson) {
  return runMarkAction(
    () => markPost(`api/marks/${encodeURIComponent(mark.id)}`, {
      period: Number(lesson.period),
      subject_code: lesson.subject_code || lesson.subject_label || "",
    }),
    "marks.toast.moved"
  );
}

function openMarkForm(childId, lesson, time, mark) {
  openSheet(() => markFormSheet(markChildOf(childId), lesson, time, mark));
}

function markFormContext(lesson, time, mark) {
  if (lesson) {
    const parts = [
      lesson.date ? showDate(lesson.date) : "",
      lessonPeriodFact(lesson, time),
      lesson.subject_label || lesson.subject_code || "",
      lesson.room ? t("timetable.room", { room: lesson.room }) : "",
    ];
    return parts.filter(Boolean).join(" · ");
  }
  return [showDate(mark.date), t("timetable.fact.periodValue", { period: formatNumber(mark.period) }), markSubjectLabel(mark)]
    .filter(Boolean)
    .join(" · ");
}

function markFormSheet(childId, lesson, time, mark) {
  const form = sheetState(() => ({ name: mark ? mark.name || "" : "" }));
  const input = el("input", {
    class: "inp",
    type: "text",
    value: form.name,
    placeholder: t("marks.form.placeholder"),
    autocomplete: "off",
    maxlength: String(MARK_MAX_NAME_LENGTH),
    "aria-label": t("marks.form.name"),
  });
  input.addEventListener("input", () => { form.name = input.value; });
  const submit = () => saveMark(childId, lesson, mark, form.name);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  });
  const body = [
    iservText("p", { class: "mark-context" }, markFormContext(lesson, time, mark)),
    markNameChips(form, input),
    el("div", { class: "field" }, [input]),
    el("p", { class: "mark-note" }, t("marks.form.hint")),
  ];
  const foot = [el("button", { class: "btn", type: "button", onclick: submit }, t(mark ? "common.save" : "marks.form.submit"))];
  window.setTimeout(() => { if (input.isConnected) input.focus(); }, 0);
  return sheet(t("marks.action.add"), body, foot);
}

function markNameChips(form, input) {
  const names = markNameHistory();
  if (!names.length) return null;
  const block = el("div", { class: "mark-chips" });
  const row = el("div", { class: "chip-row" });
  const entry = (name) => {
    const fill = el("button", {
      class: "chip mark-chip",
      type: "button",
      onclick: () => {
        form.name = name;
        input.value = name;
        input.focus();
      },
    }, [iservText("span", { class: "chip-label" }, name)]);
    const remove = el("button", {
      class: "mark-chip-remove",
      type: "button",
      "aria-label": t("marks.form.recentRemove", { name }),
    }, [icon("close", 14)]);
    const holder = el("div", { class: "mark-recent" }, [fill, remove]);
    remove.addEventListener("click", () => {
      forgetMarkName(name);
      const next = holder.nextElementSibling || holder.previousElementSibling;
      holder.remove();
      if (next) {
        next.querySelector(".mark-chip-remove").focus();
        return;
      }
      block.remove();
      input.focus();
    });
    return holder;
  };
  row.append(...names.map(entry));
  block.append(el("span", { class: "overline" }, t("marks.form.recent")), row);
  return block;
}

async function saveMark(childId, lesson, mark, name) {
  const anchor = mark ? null : markLessonAnchor(lesson, childId);
  if (!mark && !anchor) return false;
  const done = mark ? await runMarkAction(
    () => markPost(`api/marks/${encodeURIComponent(mark.id)}`, { name }),
    "marks.toast.updated"
  ) : await runMarkAction(
    () => markPost("api/marks", Object.assign({}, anchor, { name })),
    "marks.toast.saved"
  );
  if (done) rememberMarkName(name);
  return done;
}

function lettersLoadKey(tab) {
  return `letters:${tab}`;
}

async function loadLetters(tab) {
  const current = state.letters;
  const keep = !!(current && !current.error && current.tab === tab);
  const outcome = await reload(
    lettersLoadKey(tab),
    () => getJson(`api/letters?tab=${encodeURIComponent(tab)}`),
    keep
  );
  if (!outcome) return;
  if (outcome.data) state.letters = { letters: outcome.data.letters || [], tab };
  else if (outcome.error) state.letters = { error: outcome.error, tab };
  rerender();
}

function autoLoad(key, run) {
  if (state.pending[key]) return;
  state.pending[key] = true;
  run().finally(() => { state.pending[key] = false; });
}

function handleApiFailure(error, connectionId) {
  const code = errorCode(error);
  if (code === ERROR_AUTH_FAILED) {
    if (manySchools()) {
      noteSchoolFailure(connectionId, code, loginReasonOf(error));
      return false;
    }
    dropSheet();
    renderReconnect(detachedRoot(), state.account, connectionId || "", loginReasonOf(error));
    return true;
  }
  if (code === ERROR_NOT_CONFIGURED) {
    dropSheet();
    renderWizard(detachedRoot(), boot);
    return true;
  }
  return false;
}

async function reload(key, run, keepOnFailure, connectionId) {
  const ticket = nextLoad(key);
  try {
    const data = await run();
    if (!isCurrentLoad(key, ticket)) return null;
    state.loadedAt[key] = Date.now();
    delete state.refreshFailed[key];
    noteUnavailableSchools(data);
    return { data };
  } catch (error) {
    if (handleApiFailure(error, connectionId)) return null;
    if (!isCurrentLoad(key, ticket)) return null;
    const code = errorCode(error);
    if (keepOnFailure) {
      state.refreshFailed[key] = code;
      return { kept: true };
    }
    delete state.refreshFailed[key];
    return { error: code, body: (error && error.body) || null, timedOut: isTimeoutError(error) };
  }
}

function refreshFailureNote(key) {
  if (!state.refreshFailed[key] || anyOutage()) return null;
  return el("div", { class: "stamp warn", role: "status" }, t("common.refreshFailed"));
}

function retryButton(run) {
  const button = el("button", { class: "btn", type: "button", "aria-busy": "false" }, t("common.retry"));
  button.addEventListener("click", () => {
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.loading")));
    run();
  });
  return button;
}

function nextLoad(key) {
  state.loads[key] = (state.loads[key] || 0) + 1;
  return state.loads[key];
}

function isCurrentLoad(key, ticket) {
  return state.loads[key] === ticket;
}

function matchesLetterQuery(letter, query) {
  const haystack = [
    letter.title,
    letter.sender,
    letter.child,
    letter.recipients,
    stripHtml(letter.body_text || ""),
    ...(letter.attachments || []).map((attachment) => attachment.filename || ""),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function postView() {
  const lead = postSegment();
  return postSegmentIs("pinboard") ? pinboardView(lead) : lettersView(lead);
}

function postSegment() {
  if (!moduleOn("letters") || !moduleOn("pinboard")) return null;
  return el("div", { class: "segment", role: "tablist" }, [
    segmentButton(t("post.segment.letters"), postSegmentIs("letters"), lettersUnreadCount(), () =>
      switchPostTab("letters")
    ),
    segmentButton(t("post.segment.pinboard"), postSegmentIs("pinboard"), pinboardUnreadCount(), () =>
      switchPostTab("pinboard")
    ),
  ]);
}

function switchPostTab(segment) {
  if (postSegmentIs(segment)) return;
  state.postTab = segment;
  state.lettersSelectMode = false;
  state.lettersSelected = [];
  state.pinboardSelectMode = false;
  state.pinboardSelected = [];
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
  revalidateActiveView();
}

function openPostSegment(segment) {
  setView("post", { segment });
}

function lettersFolderChip(tab, iconName, label, count) {
  const chip = el("button", {
    class: "chip",
    type: "button",
    role: "tab",
    "aria-selected": String(state.lettersTab === tab),
    onclick: () => openLettersFolder(tab),
  }, [icon(iconName, 14), el("span", {}, label)]);
  if (count) chip.append(el("span", { class: "n" }, formatNumber(count)));
  return chip;
}

function lettersFolderRow() {
  return el("div", { class: "chipbar segmented", role: "tablist" }, [
    lettersFolderChip("current", "inbox", t("letters.folder.current"), lettersUnreadCount()),
    lettersFolderChip("archive", "archive", t("letters.folder.archive"), 0),
  ]);
}

function openLettersFolder(tab) {
  if (tab === state.lettersTab) return;
  setLettersFolder(tab);
  state._keepScroll = 0;
  state._scrollTop = true;
  render();
}

function lettersView(lead) {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  if (lead) head.append(lead);
  head.append(lettersFolderRow());
  view.append(head);
  const data = state.letters;
  if (!data || data.tab !== state.lettersTab) {
    autoLoad(lettersLoadKey(state.lettersTab), () => loadLetters(state.lettersTab));
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("letters.error.title"), t("letters.error.text"), retryButton(() => { state.letters = null; rerender(); })));
    return view;
  }
  const letters = data.letters || [];
  if (!letters.length) {
    view.append(
      state.lettersTab === "archive"
        ? emptyBlock("archive", t("letters.empty.archiveTitle"), t("letters.empty.archiveText"))
        : emptyBlock("inbox", t("letters.empty.title"), t("letters.empty.text"))
    );
    return view;
  }
  const unread = letters.filter((entry) => entry.unread).length;
  head.append(
    el("div", { class: "section-head" }, [
      el(
        "span",
        { class: "overline" },
        unread && state.lettersTab === "current" ? t("letters.unread", { count: formatNumber(unread) }) : tCount("letters.count", letters.length)
      ),
      el("div", { class: "letters-tools" }, [
        unread && state.lettersTab === "current" && !state.lettersSelectMode
          ? el("button", { type: "button", onclick: markAllLettersRead }, t("letters.markAllRead"))
          : null,
        state.lettersSelectMode ? null : el("button", { type: "button", onclick: toggleLetterSelectMode }, t("common.select")),
      ]),
    ])
  );
  const note = refreshFailureNote(lettersLoadKey(state.lettersTab));
  if (note) head.append(note);
  const schoolBar = schoolFilterBar(letters, state.postSchoolFilter, setPostSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  const hitCount = el("span", { class: "search-hits" });
  const rowsHost = el("div", {});
  function renderLetterRows() {
    const query = (state.lettersSearch || "").trim().toLowerCase();
    const bySchool = filterBySchool(letters, state.postSchoolFilter);
    const filtered = query ? bySchool.filter((letter) => matchesLetterQuery(letter, query)) : bySchool;
    keepSelectionVisible(state.lettersSelected, filtered.map(letterKey));
    hitCount.textContent = query ? tCount("common.hits", filtered.length) : "";
    const nodes = [];
    if (!filtered.length) {
      nodes.push(emptyBlock("search", t("letters.search.emptyTitle"), t("letters.search.emptyText")));
    } else {
      const rows = el("div", { class: "rows" });
      for (const letter of filtered) rows.append(letterRow(letter));
      nodes.push(rows);
    }
    if (state.lettersSelectMode) nodes.push(letterSelectionBar());
    rowsHost.replaceChildren(...nodes);
  }
  head.append(searchField(state.lettersSearch, t("letters.search.placeholder"), (value) => {
    state.lettersSearch = value;
    renderLetterRows();
  }, hitCount));
  view.append(rowsHost);
  renderLetterRows();
  return view;
}

function letterKey(letter) {
  if (letter.key) return letter.key;
  const prefix = letter.connection_id ? `${letter.connection_id}:` : "";
  return `${prefix}${letter.letter_id}:${letter.recipient_id}`;
}

function letterIdentity(letter) {
  return { connection_id: letter.connection_id || "", letter_id: letter.letter_id, recipient_id: letter.recipient_id };
}

function tileKey(tile) {
  return tile.key || String(tile.id);
}

function folderKey(folder) {
  return folder.key || String(folder.id);
}

function letterConfirmation(source) {
  const info = source && source.confirmation;
  return info && typeof info === "object" ? info : null;
}

function letterConfirmationOpen(letter) {
  const info = letterConfirmation(letter);
  return !!(info && info.open);
}

function createSelectionController(modeKey, selectedKey) {
  return {
    toggleMode() {
      state[modeKey] = !state[modeKey];
      state[selectedKey] = [];
      rerender();
    },
    enter(key) {
      if (state[modeKey]) return;
      state[modeKey] = true;
      state[selectedKey] = [key];
      if (navigator.vibrate) navigator.vibrate(12);
      rerender();
    },
    exit() {
      state[modeKey] = false;
      state[selectedKey] = [];
      rerender();
    },
    toggleItem(key) {
      const idx = state[selectedKey].indexOf(key);
      if (idx === -1) state[selectedKey].push(key);
      else state[selectedKey].splice(idx, 1);
      rerender();
    },
  };
}

function bulkLabel(count) {
  const progress = state.bulkProgress;
  if (!progress) return tCount("common.selected", count);
  return t("common.bulkProgress", {
    done: formatNumber(progress.done),
    total: formatNumber(progress.total),
  });
}

function selectionBar(count, onCancel, actions) {
  const busy = !!state.bulkProgress;
  return el("div", { class: "select-bar", "aria-busy": busy ? "true" : "false" }, [
    el("div", { class: "select-bar-info" }, [
      el("button", {
        class: "select-bar-cancel",
        type: "button",
        disabled: busy ? "disabled" : null,
        "aria-label": t("common.selection.end"),
        onclick: onCancel,
      }, [icon("close", 16)]),
      el("span", { role: busy ? "status" : null }, bulkLabel(count)),
    ]),
    el("div", { class: "select-bar-actions" }, actions),
  ]);
}

async function runBulk(targets, step) {
  if (state.bulkProgress) return null;
  let done = 0;
  const failed = [];
  state.bulkProgress = { done: 0, total: targets.length };
  rerender();
  for (const target of targets) {
    try {
      if (await step(target)) done += 1;
      else failed.push(target);
    } catch (error) {
      if (handleApiFailure(error)) {
        state.bulkProgress = null;
        return null;
      }
      failed.push(target);
    }
    state.bulkProgress = { done: done + failed.length, total: targets.length };
    rerender();
  }
  state.bulkProgress = null;
  return { done, failed };
}

function bulkFailureNames(failed) {
  const names = failed.map((letter) => letter.title || t("letters.fallback")).filter(Boolean);
  return names.slice(0, 3).join(", ");
}

const letterSelection = createSelectionController("lettersSelectMode", "lettersSelected");

function toggleLetterSelectMode() {
  letterSelection.toggleMode();
}

function enterLetterSelectMode(key) {
  letterSelection.enter(key);
}

function exitLetterSelectMode() {
  letterSelection.exit();
}

function toggleLetterSelected(key) {
  letterSelection.toggleItem(key);
}

function keepSelectionVisible(selected, visibleKeys) {
  if (!selected || !selected.length) return selected;
  const allowed = new Set(visibleKeys);
  for (let index = selected.length - 1; index >= 0; index -= 1) {
    if (!allowed.has(selected[index])) selected.splice(index, 1);
  }
  return selected;
}

function selectedLetterObjects() {
  const data = state.letters;
  if (!data || !data.letters) return [];
  const keys = new Set(state.lettersSelected);
  return data.letters.filter((letter) => keys.has(letterKey(letter)));
}

function letterSelectionBar() {
  const count = state.lettersSelected.length;
  const isArchive = state.lettersTab === "archive";
  const disabled = count === 0 ? "disabled" : null;
  const buttons = isArchive
    ? [el("button", { class: "btn slim ghost", type: "button", disabled, onclick: bulkRestoreLetters }, [icon("restore", 16), t("letters.action.restore")])]
    : [
        el("button", { class: "btn slim ghost", type: "button", disabled, onclick: bulkMarkLettersRead }, [icon("check", 16), t("letters.action.read")]),
        el("button", { class: "btn slim ghost", type: "button", disabled, onclick: bulkArchiveLetters }, [icon("archive", 16), t("letters.action.archive")]),
      ];
  return selectionBar(count, exitLetterSelectMode, buttons);
}

function markReadOutcome(result, singleKey) {
  const read = Number(result && result.read) || 0;
  const blocked = Number(result && result.blocked) || 0;
  if (blocked && !read) {
    return [t(singleKey && blocked === 1 ? "letters.toast.blocked" : "letters.toast.markedPartial", {
      read: formatNumber(read),
      blocked: formatNumber(blocked),
    }), "bad"];
  }
  if (blocked) {
    return [t("letters.toast.markedPartial", { read: formatNumber(read), blocked: formatNumber(blocked) }), "good"];
  }
  if (!read) return [t("letters.toast.nothingToMark"), "good"];
  return [singleKey ? t("letters.toast.markedSingle") : t("letters.toast.marked", { count: formatNumber(read) }), "good"];
}

async function bulkMarkLettersRead() {
  const keys = state.lettersSelected.slice();
  if (!keys.length) return;
  try {
    const result = await postJson("api/letters/seen", { keys });
    toast(...markReadOutcome(result, false));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

async function bulkArchiveLetters() {
  const targets = selectedLetterObjects();
  if (!targets.length) return;
  const ok = await confirmAction({
    title: tCount("letters.archive.confirmTitle", targets.length),
    text: t("letters.archive.confirmText"),
    confirmLabel: t("letters.action.archive"),
  });
  if (!ok) return;
  const outcome = await runBulk(targets, async (letter) => {
    const result = await postJson("api/letters/archive", letterIdentity(letter));
    return !!(result && result.ok);
  });
  if (!outcome) return;
  toast(
    outcome.failed.length === 0
      ? tCount("letters.toast.archived", outcome.done)
      : t("letters.toast.archivedPartial", {
          done: formatNumber(outcome.done),
          total: formatNumber(targets.length),
          names: bulkFailureNames(outcome.failed),
        }),
    outcome.done ? "good" : "bad"
  );
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

async function bulkRestoreLetters() {
  const targets = selectedLetterObjects();
  if (!targets.length) return;
  const outcome = await runBulk(targets, async (letter) => {
    const result = await postJson("api/letters/restore", letterIdentity(letter));
    return !!(result && result.ok);
  });
  if (!outcome) return;
  toast(
    outcome.failed.length === 0
      ? tCount("letters.toast.restored", outcome.done)
      : t("letters.toast.restoredPartial", {
          done: formatNumber(outcome.done),
          total: formatNumber(targets.length),
          names: bulkFailureNames(outcome.failed),
        }),
    outcome.done ? "good" : "bad"
  );
  exitLetterSelectMode();
  state.letters = null;
  rerender();
}

function letterActionsSheet(letter) {
  const isArchive = state.lettersTab === "archive";
  const rows = [];
  if (!isArchive && letterConfirmationOpen(letter)) {
    rows.push(letterActionRow("alert", t("letters.action.confirmFirst"), () => { closeSheet(); openLetter(letter); }));
  } else if (!isArchive && letter.unread) {
    rows.push(letterActionRow("check", t("letters.action.markRead"), () => { closeSheet(); markLetterRead(letter); }));
  }
  if (isArchive) {
    rows.push(letterActionRow("restore", t("letters.action.restore"), () => { closeSheet(); restoreLetter(letter); }));
  } else {
    rows.push(letterActionRow("archive", t("letters.action.archive"), () => { closeSheet(); archiveLetter(letter); }));
  }
  return sheet(letter.title || t("letters.fallback"), [el("div", { class: "rows flat" }, rows)]);
}

function letterActionRow(iconName, label, onclick) {
  return el("button", { class: "row", type: "button", onclick }, [
    el("span", { class: "row-dot" }, [icon(iconName, 18)]),
    el("div", { class: "row-main" }, [el("div", { class: "row-title" }, label)]),
  ]);
}

async function markLetterRead(letter) {
  try {
    const result = await postJson("api/letters/seen", { keys: [letterKey(letter)] });
    toast(...markReadOutcome(result, true));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  state.letters = null;
  rerender();
}

function attachLetterSwipe(row, swipe, letter) {
  let startX = 0;
  let startY = 0;
  let decided = null;
  let pointerId = null;
  let longPressTimer = 0;
  row.style.touchAction = "pan-y";
  const clearLongPress = () => {
    window.clearTimeout(longPressTimer);
    longPressTimer = 0;
  };
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    pointerId = event.pointerId;
    startX = event.clientX;
    startY = event.clientY;
    decided = null;
    longPressTimer = window.setTimeout(() => {
      if (decided === null) enterLetterSelectMode(letterKey(letter));
    }, 480);
  });
  row.addEventListener("pointermove", (event) => {
    if (event.pointerId !== pointerId) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!decided && (Math.abs(dx) > 10 || Math.abs(dy) > 10)) {
      decided = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
      clearLongPress();
      if (decided === "x") {
        swipe.wasSwipe = true;
        row.classList.add("swiping");
      }
    }
    if (decided === "x") event.preventDefault();
  });
  const finish = (event) => {
    if (event.pointerId !== pointerId) return;
    clearLongPress();
    row.classList.remove("swiping");
    if (decided === "x" && Math.abs(event.clientX - startX) > 46) {
      openSheet(() => letterActionsSheet(letter));
    }
    pointerId = null;
    decided = null;
  };
  row.addEventListener("pointerup", finish);
  row.addEventListener("pointercancel", () => {
    clearLongPress();
    row.classList.remove("swiping");
    pointerId = null;
    decided = null;
  });
}

function segmentButton(text, selected, count, onclick) {
  const button = el("button", {
    type: "button",
    role: "tab",
    "aria-selected": String(selected),
    "aria-label": count ? t("post.segment.unread", { area: text, count: formatNumber(count) }) : null,
    onclick,
  }, [el("span", { class: "seg-label" }, text)]);
  if (count) button.append(el("span", { class: "badge seg-badge", "aria-hidden": "true" }, badgeText(count)));
  return button;
}

function setLettersFolder(tab) {
  if (tab === state.lettersTab) return;
  state.lettersTab = tab;
  state.letters = null;
  state.lettersSelectMode = false;
  state.lettersSelected = [];
}

function letterChildTag(letter) {
  const name = firstName(letter && letter.child);
  return name ? iservText("span", { class: "tag child" }, name) : null;
}

function letterClassTag(letter) {
  return letter && letter.recipients ? iservText("span", { class: "tag" }, letter.recipients) : null;
}

function letterConfirmTag(letter) {
  return letterConfirmationOpen(letter)
    ? el("span", { class: "tag confirm" }, t("letters.confirm.badge"))
    : null;
}

function letterTagNodes(letter) {
  return [schoolTag(letter), letterConfirmTag(letter), letterClassTag(letter), letterChildTag(letter)].filter(Boolean);
}

function letterRow(letter) {
  const key = letterKey(letter);
  const selectMode = state.lettersSelectMode;
  const selected = state.lettersSelected.includes(key);
  const sub = letter.sender || "";
  const swipe = { wasSwipe: false };
  const chips = letterTagNodes(letter);
  const tags = chips.length ? el("div", { class: "row-tags" }, chips) : null;
  const row = el("button", {
    class: openRowClass(`row${letter.unread ? "" : " read"}${selected ? " selected" : ""}`, "letter", key),
    type: "button",
    onclick: () => {
      if (swipe.wasSwipe) {
        swipe.wasSwipe = false;
        return;
      }
      if (selectMode) toggleLetterSelected(key);
      else openLetter(letter);
    },
  }, [
    selectMode
      ? el("span", { class: `row-check${selected ? " on" : ""}` }, selected ? [icon("check", 14)] : [])
      : el("span", { class: "row-dot" }, letter.unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags,
      iservText("div", { class: "row-title" }, letter.title || t("letters.untitled")),
      sub ? el("div", { class: "row-sub" }, sub) : null,
    ]),
    el("div", { class: "row-side" }, [
      letter.published ? el("span", { class: "row-meta" }, showDate(letter.published)) : null,
      (letter.attachments || []).length ? el("span", { class: "row-clip" }, [icon("clip", 14)]) : null,
    ]),
  ]);
  if (!selectMode) attachLetterSwipe(row, swipe, letter);
  return row;
}

async function markAllLettersRead() {
  try {
    const result = await postJson("api/letters/seen", { all: true });
    toast(...markReadOutcome(result, false));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  state.letters = null;
  rerender();
}

function restoreUnreadMark(letter) {
  letter.unread = true;
  if (state.view === "post" && postSegmentIs("letters")) rerender();
}

function markLetterSeen(letter) {
  letter.unread = false;
  postJson("api/letters/seen", { keys: [letterKey(letter)] })
    .then((result) => {
      if (result && Number(result.read) > 0) return;
      restoreUnreadMark(letter);
    })
    .catch((error) => {
      restoreUnreadMark(letter);
      routeOrIgnoreBackgroundFailure(error);
    });
}

function openLetterFromOverview(letter) {
  rememberOverviewAnchor();
  setView("post", { segment: "letters" });
  openLetter(letter, OVERVIEW_ORIGIN);
}

function leaveLetterDetail() {
  const origin = state.letterDetail && state.letterDetail.origin;
  state.letterDetail = null;
  if (origin === OVERVIEW_ORIGIN) setView("overview", { keepAnchor: true });
  else rerender();
  loadLetters(state.lettersTab);
}

async function openLetter(letter, origin) {
  state.letterDetail = { letter, loading: true, origin: origin || null };
  dropSheet();
  if (letter.unread) markLetterSeen(letter);
  render();
  try {
    const detail = await getJson(
      `api/letters/detail?letter_id=${encodeURIComponent(letter.letter_id)}&recipient_id=${encodeURIComponent(letter.recipient_id)}&connection=${encodeURIComponent(letter.connection_id || "")}`
    );
    state.letterDetail = { letter, detail, origin: origin || null };
  } catch (error) {
    if (handleApiFailure(error)) return;
    state.letterDetail = { letter, error: errorCode(error), origin: origin || null };
  }
  rerender();
}

function letterTechEntries(letter) {
  return [
    { label: t("letters.tech.letterId"), value: letter.letter_id, kind: "text" },
    { label: t("letters.tech.recipientId"), value: letter.recipient_id, kind: "text" },
    { label: t("letters.tech.additionalSenders"), value: letter.additional_senders, kind: "text" },
    { label: t("letters.tech.recipients"), value: letter.recipients, kind: "text" },
  ];
}

function letterDetailView() {
  const { letter, detail, loading, error } = state.letterDetail;
  const view = el("div", {});
  const chips = letterTagNodes(letter);
  if (chips.length) view.append(el("div", { class: "row-tags" }, chips));
  const meta = [letter.sender || "", letter.published ? showDate(letter.published) : ""].filter(Boolean).join(" · ");
  if (meta) view.append(el("div", { class: "row-meta", style: "margin:0 0 20px" }, meta));
  if (loading) {
    view.append(loadingBlock());
    return view;
  }
  if (error || !detail) {
    view.append(emptyBlock("alert", t("letters.detail.errorTitle"), t("letters.detail.errorText"), retryButton(() => openLetter(letter, state.letterDetail && state.letterDetail.origin))));
    return view;
  }
  view.append(el("div", { class: "card" }, [el("div", { class: "body-html", dir: "auto", html: detail.body_html || "" })]));
  const attachments = detail.attachments || [];
  if (attachments.length) {
    view.append(el("div", { class: "section-head", style: "margin-top:24px" }, [el("span", { class: "overline" }, t("common.attachments"))]));
    view.append(attachmentRows(attachments));
  }
  const confirmBlock = letterConfirmationBlock(letter, detail);
  if (confirmBlock) view.append(confirmBlock);
  view.append(
    el("div", { style: "margin-top:24px; display:flex; gap:12px; flex-wrap:wrap" }, [
      state.lettersTab === "archive"
        ? el("button", { class: "btn ghost", type: "button", onclick: () => restoreLetter(letter) }, [icon("restore", 18), t("letters.action.restore")])
        : el("button", { class: "btn ghost", type: "button", onclick: () => archiveLetter(letter) }, [icon("archive", 18), t("letters.action.archive")]),
    ])
  );
  return view;
}

const LETTER_REPLY_MAX_LENGTH = 4000;

function letterConfirmationBlock(letter, detail) {
  const info = letterConfirmation(detail) || letterConfirmation(letter);
  if (!info || !info.type) return null;
  if (info.done) {
    return el("div", { class: "card confirm-card done" }, [
      el("div", { class: "confirm-head" }, [
        el("span", { class: "confirm-mark" }, [icon("check", 16)]),
        el("span", { class: "confirm-title" }, t("letters.confirm.doneTitle")),
      ]),
      el(
        "p",
        { class: "confirm-text" },
        info.confirmed_at
          ? t("letters.confirm.doneAt", { when: showTimestamp(info.confirmed_at) })
          : t("letters.confirm.doneText")
      ),
    ]);
  }
  if (!info.open) return null;
  const sendable = !!info.sendable;
  const card = el("div", { class: "card confirm-card" }, [
    el("div", { class: "confirm-head" }, [
      el("span", { class: "confirm-mark" }, [icon("check", 16)]),
      el(
        "span",
        { class: "confirm-title" },
        sendable ? t("letters.confirm.title") : t("letters.confirm.choiceTitle")
      ),
    ]),
    el(
      "p",
      { class: "confirm-text" },
      sendable ? t("letters.confirm.text") : t("letters.confirm.choiceText")
    ),
    sendable && info.can_reply ? letterReplyField(letter) : null,
    sendable
      ? el("button", { class: "btn confirm-action", type: "button", disabled: letter && letter.confirming ? "" : null, onclick: () => confirmLetterRead(letter) }, [
          icon("check", 18),
          t("letters.confirm.action"),
        ])
      : null,
  ]);
  const failure = letter && letter.confirmationFailure;
  if (failure && failure.message) card.append(noteBlock(failure.message));
  const facts = [
    ...diagnosisEntries(failure && failure.diagnosis),
    ...diagnosisEntries(detail && detail.confirmation_evidence),
  ];
  if (facts.length) card.append(techDetailsButton(facts));
  return card;
}

function applyLetterConfirmed(letter, stamp) {
  const done = { type: "seen", open: false, done: true, sendable: false, confirmed_at: stamp || "" };
  letter.confirmation = done;
  const detail = state.letterDetail && state.letterDetail.detail;
  if (detail) detail.confirmation = done;
  const list = state.letters && state.letters.letters;
  const key = letterKey(letter);
  if (list) {
    for (const entry of list) {
      if (letterKey(entry) === key) entry.confirmation = done;
    }
  }
}

function letterReplyField(letter) {
  const field = el("textarea", {
    class: "inp confirm-message",
    dir: "auto",
    rows: "3",
    maxlength: String(LETTER_REPLY_MAX_LENGTH),
    "aria-label": t("letters.confirm.messageLabel"),
  });
  field.value = letter.replyDraft || "";
  field.addEventListener("input", () => {
    letter.replyDraft = field.value;
  });
  return el("label", { class: "field confirm-message-field" }, [
    el("span", { class: "lbl" }, t("letters.confirm.messageLabel")),
    field,
  ]);
}

function openLetterDetailOf(letter) {
  const open = state.letterDetail;
  if (!open || !open.detail || !open.letter || letterKey(open.letter) !== letterKey(letter)) return null;
  return open.detail;
}

async function confirmLetterRead(letter) {
  if (letter.confirming) return;
  const info = letterConfirmation(openLetterDetailOf(letter)) || letterConfirmation(letter) || {};
  const message = info.can_reply ? String(letter.replyDraft || "").trim() : "";
  const ok = await confirmAction({
    title: t("letters.confirm.sheetTitle"),
    text: message ? t("letters.confirm.sheetTextWithMessage") : t("letters.confirm.sheetText"),
    quote: message,
    confirmLabel: t("letters.confirm.action"),
  });
  if (!ok) return;
  letter.confirming = true;
  rerender();
  try {
    const body = message ? Object.assign({}, letterIdentity(letter), { text: message }) : letterIdentity(letter);
    const result = await postJson("api/letters/confirm", body);
    if (result && result.ok) {
      letter.confirmationFailure = null;
      letter.replyDraft = "";
      applyLetterConfirmed(letter, result.confirmed_at || "");
      toast(t("letters.confirm.sent"), "good");
    } else {
      const message = apiMessage(result, "letters.confirm.failed");
      letter.confirmationFailure = { message, diagnosis: (result && result.diagnosis) || null };
      toast(message, "bad");
    }
  } catch (error) {
    letter.confirming = false;
    if (handleApiFailure(error)) return;
    toast(t("letters.confirm.failed"), "bad");
  }
  letter.confirming = false;
  rerender();
}

async function archiveLetter(letter) {
  const ok = await confirmAction({
    title: t("letters.archive.singleTitle"),
    text: t("letters.archive.singleText"),
    confirmLabel: t("letters.action.archive"),
  });
  if (!ok) return;
  try {
    const result = await postJson("api/letters/archive", letterIdentity(letter));
    if (result && result.ok) {
      toast(t("letters.toast.archivedSingle"));
      state.letterDetail = null;
      state.letters = null;
    } else {
      toast(t("letters.toast.archiveFailed"), "bad");
    }
  } catch (error) {
    toast(t("letters.toast.archiveFailed"), "bad");
  }
  rerender();
}

async function restoreLetter(letter) {
  try {
    const result = await postJson("api/letters/restore", letterIdentity(letter));
    if (result && result.ok) {
      toast(t("letters.toast.restoredSingle"));
      state.letterDetail = null;
      state.letters = null;
    } else {
      toast(t("letters.toast.restoreFailed"), "bad");
    }
  } catch (error) {
    toast(t("letters.toast.restoreFailed"), "bad");
  }
  rerender();
}

async function loadPinboard() {
  const keep = !!(state.pinboard && !state.pinboard.error);
  const outcome = await reload("pinboard", () => getJson("api/pinboard"), keep);
  if (!outcome) return;
  if (outcome.data) state.pinboard = outcome.data;
  else if (outcome.error) state.pinboard = { error: outcome.error };
  rerender();
}

function matchesTileQuery(tile, query) {
  const haystack = [
    tile.title || "",
    stripHtml(tile.text || ""),
    tile.folder_title || "",
    tile.column_title || "",
    ...(tile.attachments || []).map((attachment) => attachment.filename || ""),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function pinboardView(lead) {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  if (lead) head.append(lead);
  view.append(head);
  const data = state.pinboard;
  if (!data) {
    autoLoad("pinboard", loadPinboard);
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("pinboard.error.title"), t("pinboard.error.text"), retryButton(() => { state.pinboard = null; rerender(); })));
    return view;
  }
  const pinboardNote = refreshFailureNote("pinboard");
  if (pinboardNote) head.append(pinboardNote);
  const folders = data.folders || [];
  const unread = (data.feed || []).filter((tile) => tile.unread).length;
  const folder = state.pinboardFolder ? folders.find((f) => folderKey(f) === state.pinboardFolder) : null;
  head.append(
    el("div", { class: "chipbar" }, [
      el("button", { class: "chip", type: "button", "aria-pressed": String(!state.pinboardOnlyNew), onclick: () => setPinboardFilter(false) }, t("pinboard.filter.all")),
      el("button", { class: "chip", type: "button", "aria-pressed": String(state.pinboardOnlyNew), onclick: () => setPinboardFilter(true) }, [
        el("span", {}, t("pinboard.filter.new")),
        unread ? el("span", { class: "n" }, formatNumber(unread)) : null,
      ]),
      el("button", { class: "chip chip-filter", type: "button", "aria-pressed": String(!!folder), onclick: () => openSheet(folderSheet) }, [
        icon("filter", 14),
        folder
          ? iservText("span", { class: "chip-label" }, folder.title || t("pinboard.folder.fallback"))
          : el("span", { class: "chip-label" }, t("pinboard.folder.all")),
      ]),
    ])
  );
  const schoolBar = schoolFilterBar(data.feed || [], state.postSchoolFilter, setPostSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  head.append(
    el("div", { class: "section-head" }, [
      el("span", { class: "overline" }, unread ? t("pinboard.unread", { count: formatNumber(unread) }) : tCount("pinboard.count", (data.feed || []).length)),
      el("div", { class: "letters-tools" }, [
        state.pinboardSelectMode ? null : el("button", { type: "button", onclick: togglePinboardSelectMode }, t("common.select")),
      ]),
    ])
  );
  const hitCount = el("span", { class: "search-hits" });
  const bodyHost = el("div", {});
  function renderPinboardBody() {
    const query = (state.pinboardSearch || "").trim().toLowerCase();
    const nodes = [];
    if (folder) {
      nodes.push(
        el("div", { class: "section-head" }, [
          iservText("span", { class: "overline" }, folder.title),
          el("button", { type: "button", onclick: () => { state.pinboardFolder = null; rerender(); } }, t("pinboard.folder.leave")),
        ])
      );
      const folderAttachments = folder.attachments || [];
      if (folderAttachments.length) {
        const rows = attachmentRows(folderAttachments);
        rows.style.marginBottom = "16px";
        nodes.push(rows);
      }
    }
    const tiles = pinboardTiles(data, folder, query);
    keepSelectionVisible(state.pinboardSelected, tiles.map(tileKey));
    hitCount.textContent = query ? tCount("common.hits", tiles.length) : "";
    if (!tiles.length) {
      nodes.push(
        query
          ? emptyBlock("search", t("pinboard.search.emptyTitle"), t("pinboard.search.emptyText"))
          : state.pinboardOnlyNew
          ? emptyBlock("check", t("pinboard.empty.newTitle"), t("pinboard.empty.newText"))
          : emptyBlock("pinboard", t("pinboard.empty.title"), t("pinboard.empty.text"))
      );
      bodyHost.replaceChildren(...nodes);
      return;
    }
    if (unread && state.pinboardOnlyNew && !query) {
      nodes.push(
        el("div", { class: "section-head" }, [
          el("span", { class: "overline" }, t("pinboard.unread", { count: formatNumber(unread) })),
          el("button", { type: "button", onclick: markAllPostsRead }, t("pinboard.markAllRead")),
        ])
      );
    }
    if (!folder) {
      nodes.push(el("div", { class: "sort-hint" }, t("pinboard.sortHint")));
      const rows = el("div", { class: "rows" });
      for (const tile of tiles) rows.append(postRow(tile, false, query));
      nodes.push(rows);
      if (state.pinboardSelectMode) nodes.push(pinboardSelectionBar());
      bodyHost.replaceChildren(...nodes);
      return;
    }
    let lastGroup = null;
    let rows = null;
    for (const tile of tiles) {
      const label = tile.column_title || "";
      if (label !== lastGroup || !rows) {
        lastGroup = label;
        if (label) nodes.push(el("div", { class: "section-head", style: "margin-top:20px" }, [el("span", { class: "overline" }, label)]));
        rows = el("div", { class: "rows" });
        nodes.push(rows);
      }
      rows.append(postRow(tile, true, query));
    }
    if (state.pinboardSelectMode) nodes.push(pinboardSelectionBar());
    bodyHost.replaceChildren(...nodes);
  }
  head.append(searchField(state.pinboardSearch, t("pinboard.search.placeholder"), (value) => {
    state.pinboardSearch = value;
    renderPinboardBody();
  }, hitCount));
  view.append(bodyHost);
  renderPinboardBody();
  return view;
}

function pinboardTiles(data, folder, query) {
  let tiles = folder ? (folder.columns || []).flatMap((column) => column.tiles || []) : filterBySchool(data.feed || [], state.postSchoolFilter).slice();
  if (state.pinboardOnlyNew) tiles = tiles.filter((tile) => tile.unread);
  if (query) tiles = tiles.filter((tile) => matchesTileQuery(tile, query));
  if (!folder) tiles.sort((a, b) => (b.id || 0) - (a.id || 0));
  return tiles;
}

function setPinboardFilter(onlyNew) {
  state.pinboardOnlyNew = onlyNew;
  rerender();
}

const pinboardSelection = createSelectionController("pinboardSelectMode", "pinboardSelected");

function togglePinboardSelectMode() {
  pinboardSelection.toggleMode();
}

function enterPinboardSelectMode(key) {
  pinboardSelection.enter(key);
}

function exitPinboardSelectMode() {
  pinboardSelection.exit();
}

function togglePinboardSelected(key) {
  pinboardSelection.toggleItem(key);
}

function pinboardSelectionBar() {
  const count = state.pinboardSelected.length;
  const disabled = count === 0 ? "disabled" : null;
  const buttons = [
    el("button", { class: "btn slim ghost", type: "button", disabled, onclick: bulkMarkPinboardRead }, [icon("check", 16), t("pinboard.action.markRead")]),
    el("button", { class: "btn slim ghost", type: "button", disabled, onclick: bulkMarkPinboardUnread }, [icon("restore", 16), t("pinboard.action.markUnread")]),
  ];
  return selectionBar(count, exitPinboardSelectMode, buttons);
}

async function bulkSetPinboardSeen(unseen) {
  const keys = state.pinboardSelected.slice();
  if (!keys.length) return;
  try {
    await postJson("api/pinboard/seen", { keys, unseen });
    toast(t(unseen ? "pinboard.toast.markedUnread" : "pinboard.toast.markedRead"));
  } catch (error) {
    toast(t("pinboard.toast.changeFailed"), "bad");
  }
  exitPinboardSelectMode();
  state.pinboard = null;
  loadPinboard();
}

function bulkMarkPinboardRead() {
  return bulkSetPinboardSeen(false);
}

function bulkMarkPinboardUnread() {
  return bulkSetPinboardSeen(true);
}

function attachPinboardLongPress(row, tile) {
  let longPressTimer = 0;
  let moved = false;
  let startX = 0;
  let startY = 0;
  const clear = () => {
    window.clearTimeout(longPressTimer);
    longPressTimer = 0;
  };
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    moved = false;
    startX = event.clientX;
    startY = event.clientY;
    longPressTimer = window.setTimeout(() => {
      if (!moved) enterPinboardSelectMode(tileKey(tile));
    }, 480);
  });
  row.addEventListener("pointermove", (event) => {
    if (Math.abs(event.clientX - startX) > 10 || Math.abs(event.clientY - startY) > 10) {
      moved = true;
      clear();
    }
  });
  row.addEventListener("pointerup", clear);
  row.addEventListener("pointercancel", clear);
}

function folderTechEntries(folder) {
  return [
    { label: t("pinboard.tech.author"), value: folder.author, kind: "text" },
    { label: t("pinboard.tech.studentsCanCreate"), value: folder.students_can_create_tiles, kind: "bool" },
  ];
}

function folderSheet() {
  const data = state.pinboard || {};
  const sortedFolders = (data.folders || [])
    .slice()
    .sort((a, b) => (a.title || "").localeCompare(b.title || "", currentLanguage(), { numeric: true, sensitivity: "base" }));
  const rows = sortedFolders.map((folder) =>
    el("div", { class: "opt", "aria-pressed": String(folderKey(folder) === state.pinboardFolder) }, [
      el("button", {
        class: "opt-main",
        type: "button",
        onclick: () => { state.pinboardFolder = folderKey(folder); closeSheet(); },
      }, [
        icon("folder", 20),
        el("span", {}, [
          iservText("b", {}, folder.title || t("pinboard.folder.fallback")),
        ]),
        folder.unread ? el("span", { class: "badge" }, badgeText(folder.unread)) : null,
      ]),
      techDetailsButton(folderTechEntries(folder)),
    ])
  );
  rows.unshift(
    el("div", { class: "opt", "aria-pressed": String(!state.pinboardFolder) }, [
      el("button", {
        class: "opt-main",
        type: "button",
        onclick: () => { state.pinboardFolder = null; closeSheet(); },
      }, [icon("pinboard", 20), el("span", {}, [el("b", {}, t("pinboard.folder.all")), el("small", {}, t("pinboard.folder.allHint"))])])
    ])
  );
  return sheet(t("pinboard.folder.sheet"), [el("div", { class: "opt-list" }, rows)]);
}

function filenameHitFor(tile, query) {
  if (!query) return null;
  const textHaystack = `${tile.title || ""} ${stripHtml(tile.text || "")}`.toLowerCase();
  if (textHaystack.includes(query)) return null;
  const attachments = tile.attachments || [];
  const hit = attachments.find((attachment) => (attachment.filename || "").toLowerCase().includes(query));
  return hit ? hit.filename : null;
}

function postRow(tile, insideFolder, query) {
  const preview = stripHtml(tile.text).slice(0, 140);
  const title = tile.title && tile.title !== "..." ? tile.title : (preview.split(". ")[0] || t("pinboard.post.fallback"));
  const filenameHit = filenameHitFor(tile, query);
  const sub = filenameHit || (preview && preview !== title ? preview : "");
  const tagNodes = [
    schoolTag(tile),
    !insideFolder && tile.folder_title ? el("span", { class: "tag" }, tile.folder_title) : null,
    tile.column_title ? el("span", { class: "tag" }, tile.column_title) : null,
  ].filter(Boolean);
  const tags = tagNodes.length ? el("div", { class: "row-tags" }, tagNodes) : null;
  const selectMode = state.pinboardSelectMode;
  const selected = state.pinboardSelected.includes(tileKey(tile));
  const row = el("button", {
    class: openRowClass(`${tile.unread ? "row" : "row read"}${selected ? " selected" : ""}`, "post", tileKey(tile)),
    type: "button",
    onclick: () => {
      if (selectMode) togglePinboardSelected(tileKey(tile));
      else openPost(tile);
    },
  }, [
    selectMode
      ? el("span", { class: `row-check${selected ? " on" : ""}` }, selected ? [icon("check", 14)] : [])
      : el("span", { class: "row-dot" }, tile.unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags,
      el("div", { class: "row-title" }, title),
      sub ? el("div", { class: "row-sub" }, sub) : null,
    ]),
    el("div", { class: "row-side" }, [
      (tile.attachments || []).length ? el("span", { class: "row-clip" }, [icon("clip", 14)]) : null,
    ]),
  ]);
  if (!selectMode) attachPinboardLongPress(row, tile);
  return row;
}

function postTechEntries(tile) {
  const entries = [
    { label: t("pinboard.tech.tileId"), value: tile.id, kind: "text" },
    { label: t("pinboard.tech.color"), value: tile.color, kind: "text" },
  ];
  const attachments = tile.attachments || [];
  attachments.forEach((attachment, index) => {
    const prefix = attachments.length > 1
      ? t("pinboard.tech.attachmentIndexed", { index: formatNumber(index + 1) })
      : t("pinboard.tech.attachment");
    entries.push(
      { label: t("pinboard.tech.uploaded", { prefix }), value: attachment.created_at, kind: "epoch" },
      { label: t("pinboard.tech.changed", { prefix }), value: attachment.updated_at, kind: "epoch" }
    );
    if ((attachment.mimetype || "").startsWith("image/") && attachment.image_width && attachment.image_height) {
      entries.push({
        label: t("pinboard.tech.imageSize", { prefix }),
        value: t("common.imageSize", {
          width: formatNumber(attachment.image_width),
          height: formatNumber(attachment.image_height),
        }),
        kind: "text",
      });
    }
  });
  return entries;
}

function postDetailParts(tile) {
  const body = [];
  const meta = [tile.folder_title || "", tile.column_title || "", tile.owner || ""].filter(Boolean).join(" · ");
  if (meta) body.push(el("div", { class: "row-meta", style: "margin-bottom:12px" }, meta));
  body.push(el("div", { class: "body-html", dir: "auto", html: tile.text || "" }));

  const attachments = tile.attachments || [];
  if (attachments.length) {
    const rows = attachmentRows(attachments);
    rows.style.marginTop = "16px";
    body.push(rows);
  }
  const foot = el("button", {
    class: "btn ghost",
    type: "button",
    onclick: () => togglePostRead(tile),
  }, [icon(tile.unread ? "check" : "restore", 18), t(tile.unread ? "pinboard.post.markRead" : "pinboard.post.markUnread")]);
  return {
    title: tile.title && tile.title !== "..." ? tile.title : t("pinboard.post.title"),
    body,
    foot: [foot],
    extra: techDetailsButton(postTechEntries(tile)),
  };
}

function openPost(tile) {
  markPostRead(tile);
  const detail = { kind: "post", tile };
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") return openDetail(detail);
  openSheet(detailSheetFactory(detail));
}

async function togglePostRead(tile) {
  const target = !tile.unread;
  tile.unread = target;
  state.detail = null;
  closeSheet();
  try {
    await postJson("api/pinboard/seen", { keys: [tileKey(tile)], unseen: target });
    toast(t(target ? "pinboard.toast.markedUnreadAgain" : "pinboard.toast.markedRead"));
  } catch (error) {
    tile.unread = !target;
    toast(t("pinboard.toast.changeFailed"), "bad");
  }
  rerender();
}

async function markPostRead(tile) {
  if (!tile.unread) return;
  tile.unread = false;
  try {
    await postJson("api/pinboard/seen", { keys: [tileKey(tile)] });
  } catch (error) {
    tile.unread = true;
    routeOrIgnoreBackgroundFailure(error);
    if (state.view === "post" && postSegmentIs("pinboard")) rerender();
  }
}

async function markAllPostsRead() {
  try {
    await postJson("api/pinboard/seen", { all: true });
    toast(t("pinboard.toast.allRead"));
  } catch (error) {
    toast(t("pinboard.toast.markFailed"), "bad");
  }
  state.pinboard = null;
  loadPinboard();
}

const MESSENGER_POLL_MS = 25000;
const MESSENGER_LOAD_KEY = "messenger";
const MESSENGER_ROOM_LOAD_KEY = "messengerRoom";
const MESSENGER_OLDER_LOAD_KEY = "messengerRoomOlder";
const MESSENGER_SYSTEM_KEYS = {
  join: "messenger.system.join",
  leave: "messenger.system.leave",
  invite: "messenger.system.invite",
};
const CHAT_BOTTOM_SLACK = 40;
const CHAT_OLDER_TRIGGER = 80;
const CHAT_COMPOSER_MAX = 132;

let messengerPollTimer = 0;
let chatViewportBound = false;

function inMessengerRoom() {
  return state.view === "messenger" && !!state.messengerRoom;
}

function messengerUnreadTotal() {
  const data = state.messengerRooms;
  if (data && !data.error) {
    return (data.rooms || []).reduce((sum, entry) => sum + (Number(entry.unread_count) || 0), 0);
  }
  let stored = 0;
  for (const entry of readySchools()) {
    const count = Number(((entry.poll_state || {}).messenger_unread) || 0);
    if (Number.isFinite(count) && count > 0) stored += count;
  }
  return stored;
}

function messengerRoomUnread() {
  const room = state.messengerRoom;
  return room ? Number(room.unread) || 0 : 0;
}

function messengerRoomLastEventId() {
  const room = state.messengerRoom;
  if (!room) return "";
  for (let index = room.messages.length - 1; index >= 0; index--) {
    const eventId = room.messages[index].event_id;
    if (eventId) return eventId;
  }
  return "";
}

function messengerReadButton() {
  const room = state.messengerRoom;
  const button = el("button", {
    class: "icon-btn messenger-read",
    type: "button",
    "aria-label": t("messenger.read.action"),
    "aria-busy": room && room.marking ? "true" : "false",
  }, [room && room.marking ? el("span", { class: "spin" }) : icon("check", 18)]);
  button.disabled = !!(room && room.marking) || !messengerRoomLastEventId();
  button.addEventListener("click", () => markMessengerRoomRead());
  return button;
}

async function markMessengerRoomRead() {
  const room = state.messengerRoom;
  const eventId = messengerRoomLastEventId();
  if (!room || room.marking || !eventId) return;
  room.marking = true;
  rerender();
  let result = null;
  try {
    result = await postJson("api/messenger/read", { room_id: room.room_id, event_id: eventId, connection_id: room.connectionId || "" });
  } catch (error) {
    if (handleApiFailure(error)) return;
    result = null;
  }
  if (state.messengerRoom !== room) return;
  room.marking = false;
  if (!result || !result.ok) {
    rerender();
    toast(apiMessage(result, "api.messenger.read.failed"), "bad");
    return;
  }
  room.unread = 0;
  rerender();
  toast(apiMessage(result, "api.messenger.read.ok"));
  await loadMessengerRooms();
}

function messengerRoomHeadTitle() {
  const room = state.messengerRoom;
  return iservText("h1", { class: "header-title" }, room.name || t("messenger.title"));
}

async function loadMessengerRooms() {
  const keep = !!(state.messengerRooms && !state.messengerRooms.error);
  const outcome = await reload(MESSENGER_LOAD_KEY, () => getJson("api/messenger/rooms"), keep);
  if (!outcome) return;
  if (outcome.data) state.messengerRooms = outcome.data;
  else if (outcome.error) {
    state.messengerRooms = {
      error: outcome.error,
      body: outcome.body || null,
      timedOut: !!outcome.timedOut,
    };
  }
  rerender();
}

function messengerFailureText(failure, fallbackKey) {
  const body = failure && failure.body;
  if (body && body.message_key) return t(body.message_key, body.message_vars);
  if (failure && failure.timedOut) return t("api.messenger.error.timeout");
  return t(fallbackKey || "messenger.error.text");
}

function diagnosisValueText(value) {
  if (typeof value === "boolean") return t(value ? "common.yes" : "common.no");
  if (Array.isArray(value)) return value.map(diagnosisValueText).join(", ");
  if (value && typeof value === "object") {
    return Object.keys(value).map((key) => `${key}: ${diagnosisValueText(value[key])}`).join(", ");
  }
  if (value === null || value === undefined || value === "") return t("common.none");
  return String(value);
}

function diagnosisLabel(key) {
  const candidate = `diagnosis.${key}`;
  return hasMessage(candidate) ? t(candidate) : key;
}

function diagnosisEntries(diagnosis) {
  if (!diagnosis || typeof diagnosis !== "object") return [];
  return Object.keys(diagnosis).map((key) => ({
    label: diagnosisLabel(key),
    value: diagnosisValueText(diagnosis[key]),
  }));
}

function messengerDiagnosisEntries(failure) {
  return diagnosisEntries(failure && failure.body && failure.body.diagnosis);
}

async function retryMessengerRooms() {
  if (state.messengerRetrying) return;
  state.messengerRetrying = true;
  state.messengerRetryFailed = false;
  rerender();
  state.messengerRooms = null;
  await loadMessengerRooms();
  state.messengerRetrying = false;
  state.messengerRetryFailed = !!(state.messengerRooms && state.messengerRooms.error);
  rerender();
}

function messengerUnavailableBlock(data) {
  const failure = data && data.messages_unavailable;
  if (!failure) return null;
  const entry = teacherRoomEntry("btn");
  if (failure.diagnosis && failure.diagnosis.stage === "no_credentials") {
    const calm = emptyBlock("messages", t("messenger.empty.title"), t("messenger.empty.withheld"), entry);
    const details = diagnosisEntries(failure.diagnosis);
    if (details.length) calm.append(techDetailsButton(details));
    return calm;
  }
  const retry = retryButton(retryMessengerRooms);
  if (entry) retry.classList.add("ghost");
  const block = emptyBlock(
    "alert",
    t("messenger.unavailable.title"),
    t("messenger.unavailable.text", { reason: t(failure.message_key || "messenger.error.text") }),
    entry || retry
  );
  if (entry) block.append(retry);
  const entries = diagnosisEntries(failure.diagnosis);
  if (entries.length) block.append(techDetailsButton(entries));
  return block;
}

function messengerErrorBlock() {
  const failure = state.messengerRooms || {};
  const block = emptyBlock(
    "alert",
    t("messenger.error.title"),
    messengerFailureText(failure),
    retryButton(retryMessengerRooms)
  );
  if (state.messengerRetryFailed) {
    block.insertBefore(noteBlock(t("messenger.error.retryFailed")), block.lastChild);
  }
  const entries = messengerDiagnosisEntries(failure);
  if (entries.length) block.append(techDetailsButton(entries));
  return block;
}

function matchesRoomQuery(room, query) {
  return [room.name || "", (room.members || []).join(" "), room.last_message || ""]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function messengerDate(value) {
  const stamp = Number(value);
  if (!stamp) return null;
  const date = new Date(stamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

function messengerStamp(value) {
  const date = messengerDate(value);
  if (!date) return "";
  return isoDate(date) === isoDate(new Date()) ? formatTime(date) : formatShortDate(date);
}

function messengerTime(value) {
  const date = messengerDate(value);
  return date ? formatTime(date) : "";
}

function messengerDayKey(value) {
  const date = messengerDate(value);
  return date ? isoDate(date) : "";
}

function messengerDayLabel(value) {
  const date = messengerDate(value);
  return date ? formatWeekdayDay(date) : "";
}

function messengerRoomRow(room) {
  const unread = Number(room.unread_count) || 0;
  const dot = el("span", { class: "row-dot" }, unread ? el("i") : null);
  const school = schoolTag(room);
  const main = el("div", { class: "row-main" }, [
    school ? el("div", { class: "row-tags" }, [school]) : null,
    iservText("div", { class: "row-title" }, room.name || t("messenger.title")),
  ]);
  if (room.last_message) main.append(iservText("div", { class: "row-sub" }, room.last_message));
  const side = el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, messengerStamp(room.last_message_at))]);
  if (unread) side.append(el("span", { class: "badge" }, badgeText(unread)));
  return el("button", {
    type: "button",
    class: openRowClass(unread ? "row" : "row read", "room", room.room_id),
    onclick: () => openMessengerRoom(room),
  }, [dot, main, side]);
}

function messengerView() {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  view.append(head);
  if (state.messengerRetrying) {
    view.append(noteBlock(t("messenger.error.retrying")));
    view.append(loadingBlock());
    return view;
  }
  const data = state.messengerRooms;
  if (!data) {
    autoLoad(MESSENGER_LOAD_KEY, loadMessengerRooms);
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage() ? outageEmptyBlock() : messengerErrorBlock());
    return view;
  }
  const note = refreshFailureNote(MESSENGER_LOAD_KEY);
  if (note) head.append(note);
  const rooms = data.rooms || [];
  if (!rooms.length) {
    const unavailable = messengerUnavailableBlock(data);
    if (unavailable) {
      view.append(unavailable);
      return view;
    }
    view.append(
      emptyBlock("messages", t("messenger.empty.title"), t("messenger.empty.text"), teacherRoomEntry("btn"))
    );
    return view;
  }
  const entry = teacherRoomEntry("btn slim");
  if (entry) head.append(el("div", { class: "list-actions" }, [entry]));
  const schoolBar = schoolFilterBar(rooms, state.messengerSchoolFilter, setMessengerSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  const hitCount = el("span", { class: "search-hits" });
  const rowsHost = el("div", {});
  function renderRoomRows() {
    const query = (state.messengerSearch || "").trim().toLowerCase();
    const bySchool = filterBySchool(rooms, state.messengerSchoolFilter);
    const filtered = query ? bySchool.filter((room) => matchesRoomQuery(room, query)) : bySchool;
    hitCount.textContent = query ? tCount("common.hits", filtered.length) : "";
    if (!filtered.length) {
      rowsHost.replaceChildren(emptyBlock("search", t("messenger.search.emptyTitle"), t("messenger.search.emptyText")));
      return;
    }
    const list = el("div", { class: "rows" });
    for (const room of filtered) list.append(messengerRoomRow(room));
    rowsHost.replaceChildren(list);
  }
  head.append(searchField(state.messengerSearch, t("messenger.search.placeholder"), (value) => {
    state.messengerSearch = value;
    renderRoomRows();
  }, hitCount));
  view.append(rowsHost);
  renderRoomRows();
  return view;
}

function openMessengerRoom(room) {
  state.messengerRoom = {
    room_id: room.room_id,
    connectionId: room.connection_id || "",
    name: room.name || "",
    memberNames: room.member_names || {},
    selfUserId: room.self_user_id || (state.messengerRooms && state.messengerRooms.self_user_id) || "",
    unread: Number(room.unread_count) || 0,
    marking: false,
    messages: [],
    before: "",
    loading: true,
    loadingOlder: false,
    error: "",
    draft: "",
    sending: false,
    atBottom: true,
    stickBottom: true,
    logScroll: null,
    restoreFromEnd: null,
  };
  rerender();
  startMessengerPoll();
  loadMessengerHistory();
}

function closeMessengerRoom() {
  stopMessengerPoll();
  state.messengerRoom = null;
  rerender();
  loadMessengerRooms();
}

function mergeMessengerMessages(existing, page) {
  const arrived = new Set(page.map((entry) => entry.event_id));
  return existing.filter((entry) => !arrived.has(entry.event_id)).concat(page);
}

function applyMessengerHistory(room, data, older) {
  const page = (data.messages || []).slice().reverse();
  if (data.self_user_id) room.selfUserId = data.self_user_id;
  if (older) {
    room.messages = page.concat(room.messages);
    room.before = data.before || "";
    return;
  }
  const first = !room.messages.length;
  const grown = mergeMessengerMessages(room.messages, page);
  const changed = grown.length !== room.messages.length;
  room.messages = grown;
  if (first) room.before = data.before || "";
  if (first || (changed && room.atBottom)) room.stickBottom = true;
}

async function loadMessengerHistory(options) {
  const room = state.messengerRoom;
  if (!room) return;
  const older = !!(options && options.older);
  if (older && (!room.before || room.loadingOlder)) return;
  if (older) {
    room.loadingOlder = true;
    rerender();
  }
  const query = older ? `&before=${encodeURIComponent(room.before)}` : "";
  const outcome = await reload(
    older ? MESSENGER_OLDER_LOAD_KEY : MESSENGER_ROOM_LOAD_KEY,
    () => getJson(`api/messenger/room?id=${encodeURIComponent(room.room_id)}&connection=${encodeURIComponent(room.connectionId || "")}${query}`),
    !older && room.messages.length > 0
  );
  if (!outcome || state.messengerRoom !== room) return;
  room.loading = false;
  room.loadingOlder = false;
  if (outcome.data) {
    room.error = "";
    room.errorBody = null;
    room.errorTimedOut = false;
    applyMessengerHistory(room, outcome.data, older);
  } else if (outcome.error) {
    room.error = outcome.error;
    room.errorBody = outcome.body || null;
    room.errorTimedOut = !!outcome.timedOut;
  }
  rerender();
}

function messengerSenderName(room, message) {
  return (room.memberNames || {})[message.sender] || "";
}

function messengerImage(message) {
  const label = message.body || t("messenger.image");
  const button = el("button", { type: "button", class: "chat-image", "aria-label": label }, [
    el("img", { class: "chat-thumb", src: apiUrl(message.media_url), alt: "", loading: "lazy", draggable: "false" }),
  ]);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await openAppFile(message.media_url, label, button);
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function messengerBody(message) {
  if (message.kind === "image" && message.media_url) return messengerImage(message);
  if (message.kind === "file" && message.media_url) {
    return attachmentRows([{ filename: message.body || "", url: message.media_url }]);
  }
  return iservText("div", { class: "chat-text" }, message.body || "");
}

function messengerSystemRow(message) {
  return el("div", { class: "chat-system", role: "note" }, t(MESSENGER_SYSTEM_KEYS[message.system_kind] || "messenger.system.change"));
}

function messengerBubble(room, message) {
  const mine = !!room.selfUserId && message.sender === room.selfUserId;
  const bubble = el("div", { class: mine ? "chat-msg mine" : "chat-msg" });
  if (!mine) {
    const sender = messengerSenderName(room, message);
    if (sender) bubble.append(iservText("div", { class: "chat-from" }, sender));
  }
  bubble.append(messengerBody(message));
  bubble.append(el("div", { class: "chat-time" }, messengerTime(message.sent_at)));
  return bubble;
}

function messengerOlderStrip(room) {
  const strip = el("div", { class: "chat-older" });
  if (room.loadingOlder) {
    strip.append(el("span", { class: "spin" }));
    return strip;
  }
  strip.append(
    el("button", {
      class: "chat-older-btn",
      type: "button",
      onclick: () => loadMessengerHistory({ older: true }),
    }, t("messenger.room.loadOlder"))
  );
  return strip;
}

function messengerLogScroll(log, room) {
  room.logScroll = log.scrollTop;
  room.atBottom = log.scrollHeight - log.scrollTop - log.clientHeight <= CHAT_BOTTOM_SLACK;
  if (log.scrollTop > CHAT_OLDER_TRIGGER || !room.before || room.loadingOlder) return;
  if (log.scrollHeight <= log.clientHeight) return;
  room.restoreFromEnd = log.scrollHeight - log.scrollTop;
  loadMessengerHistory({ older: true });
}

function placeMessengerLog(log, room) {
  if (room.restoreFromEnd !== null && room.restoreFromEnd !== undefined) {
    log.scrollTop = Math.max(log.scrollHeight - room.restoreFromEnd, 0);
    room.restoreFromEnd = null;
  } else if (room.stickBottom || room.logScroll === null || room.logScroll === undefined) {
    log.scrollTop = log.scrollHeight;
    room.stickBottom = false;
  } else {
    log.scrollTop = room.logScroll;
  }
  room.logScroll = log.scrollTop;
}

function messengerStream(room) {
  const stream = el("div", { class: "chat-stream" });
  let lastDay = "";
  for (const message of room.messages) {
    const day = messengerDayKey(message.sent_at);
    if (day && day !== lastDay) {
      lastDay = day;
      stream.append(el("div", { class: "chat-day" }, messengerDayLabel(message.sent_at)));
    }
    stream.append(message.kind === "system" ? messengerSystemRow(message) : messengerBubble(room, message));
  }
  return stream;
}

function messengerLog(room) {
  const log = el("div", { class: "chat-log", role: "log" });
  if (room.loading && !room.messages.length) {
    log.append(loadingBlock());
    return log;
  }
  if (room.error && !room.messages.length) {
    const failure = { error: room.error, body: room.errorBody, timedOut: room.errorTimedOut };
    const block = emptyBlock("alert", t("messenger.room.error.title"), messengerFailureText(failure, "messenger.room.error.text"), retryButton(() => {
      room.error = "";
      room.errorBody = null;
      room.errorTimedOut = false;
      room.loading = true;
      rerender();
      loadMessengerHistory();
    }));
    const entries = messengerDiagnosisEntries(failure);
    if (entries.length) block.append(techDetailsButton(entries));
    log.append(block);
    return log;
  }
  if (!room.messages.length) {
    log.append(emptyBlock("messages", t("messenger.room.empty.title"), t("messenger.room.empty.text")));
    return log;
  }
  const note = refreshFailureNote(MESSENGER_ROOM_LOAD_KEY);
  if (note) log.append(note);
  if (room.before) log.append(messengerOlderStrip(room));
  log.append(messengerStream(room));
  log.addEventListener("scroll", () => messengerLogScroll(log, room));
  window.setTimeout(() => placeMessengerLog(log, room), 0);
  return log;
}

function growComposer(input) {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, CHAT_COMPOSER_MAX) + "px";
}

function messengerComposer(room) {
  const input = el("textarea", {
    class: "composer-input",
    rows: "1",
    dir: "auto",
    placeholder: t("messenger.compose.placeholder"),
    "aria-label": t("messenger.compose.placeholder"),
  });
  input.value = room.draft || "";
  input.addEventListener("input", () => {
    room.draft = input.value;
    growComposer(input);
  });
  const button = el("button", {
    class: "composer-send",
    type: "button",
    "aria-label": t("messenger.compose.send"),
  }, [room.sending ? el("span", { class: "spin" }) : icon("send", 18)]);
  button.disabled = !!room.sending;
  button.addEventListener("click", () => sendMessengerMessage(input));
  window.setTimeout(() => growComposer(input), 0);
  return el("div", { class: "composer" }, [el("div", { class: "composer-inner" }, [input, button])]);
}

async function sendMessengerMessage(input) {
  const room = state.messengerRoom;
  if (!room || room.sending) return;
  const text = (input.value || "").trim();
  if (!text) {
    toast(t("api.messenger.send.empty"), "bad");
    input.focus();
    return;
  }
  room.draft = input.value;
  room.sending = true;
  rerender();
  let result = null;
  try {
    result = await postJson("api/messenger/send", { room_id: room.room_id, text, connection_id: room.connectionId || "" });
  } catch (error) {
    if (handleApiFailure(error)) return;
    result = null;
  }
  if (state.messengerRoom !== room) return;
  room.sending = false;
  if (!result || !result.ok) {
    rerender();
    toast(apiMessage(result, "api.messenger.send.failed"), "bad");
    return;
  }
  room.draft = "";
  room.stickBottom = true;
  rerender();
  await loadMessengerHistory();
}

function messengerRoomView() {
  const room = state.messengerRoom;
  return el("div", { class: "chat" }, [messengerLog(room), messengerComposer(room)]);
}

function messengerComposing() {
  const active = document.activeElement;
  return !!(active && active.classList && active.classList.contains("composer-input"));
}

function pollMessengerRoom() {
  const room = state.messengerRoom;
  if (!room || state.view !== "messenger" || document.hidden) return;
  if (room.sending || room.loadingOlder || messengerComposing()) return;
  loadMessengerHistory();
  loadMessengerRooms();
}

function startMessengerPoll() {
  stopMessengerPoll();
  messengerPollTimer = window.setInterval(pollMessengerRoom, MESSENGER_POLL_MS);
}

function stopMessengerPoll() {
  if (!messengerPollTimer) return;
  window.clearInterval(messengerPollTimer);
  messengerPollTimer = 0;
}

function applyChatViewport() {
  const view = window.visualViewport;
  if (!view) return;
  const app = root();
  if (!app) return;
  if (!inMessengerRoom()) {
    app.style.removeProperty("--chat-vh");
    return;
  }
  app.style.setProperty("--chat-vh", Math.round(view.height) + "px");
}

function setupChatViewport() {
  if (chatViewportBound || !window.visualViewport) return;
  chatViewportBound = true;
  window.visualViewport.addEventListener("resize", applyChatViewport);
  window.visualViewport.addEventListener("scroll", applyChatViewport);
}

const TEACHER_SEARCH_DEBOUNCE_MS = 250;
const TEACHER_ROOM_TIMEOUT_MS = 30000;
const TEACHER_ROOM_FLOW_TEXTS = {
  back: "messenger.create.back",
  goal: "messenger.create.goal",
  progress: "messenger.create.progress",
  progressTotal: "messenger.create.progress.total",
  failed: "messenger.create.failed",
};

let teacherRoomFlow = null;
let teacherResultsHost = null;
let teacherSearchTimer = 0;
let teacherSearchAbort = null;

function teacherRoomEntry(className) {
  const data = state.messengerRooms;
  if (!data || data.error || !data.can_write_to_teacher) return null;
  return el("button", { class: className, type: "button", onclick: startTeacherRoom }, [
    icon("plus", 16),
    el("span", {}, t("messenger.create.action")),
  ]);
}

function startTeacherRoom() {
  state.teacherRoom = {
    teacher: null,
    query: "",
    results: null,
    searching: false,
    failed: false,
    allowed: true,
    childOptions: null,
    childrenFailed: false,
    childIds: [],
    addOtherParents: false,
    duplicate: null,
  };
  dropSheet();
  teacherRoomFlowStart();
  render();
  loadTeacherRoomChildren();
}

async function loadTeacherRoomChildren() {
  const form = state.teacherRoom;
  if (!form) return;
  form.childrenFailed = false;
  let data = null;
  try {
    data = await getJson(`api/messenger/room/teacher/children?connection=${encodeURIComponent(currentConnectionId())}`);
  } catch (error) {
    if (state.teacherRoom !== form) return;
    form.childrenFailed = true;
    teacherRoomRefresh();
    return;
  }
  if (state.teacherRoom !== form) return;
  form.childOptions = (data && data.children) || [];
  form.allowed = !data || data.allowed !== false;
  form.childIds = form.childOptions.length === 1 ? [form.childOptions[0].id] : [];
  teacherRoomRefresh();
}

function closeTeacherRoom() {
  cancelTeacherSearch();
  window.clearTimeout(teacherSearchTimer);
  teacherSearchTimer = 0;
  if (teacherRoomFlow) teacherRoomFlow.destroy();
  teacherRoomFlow = null;
  teacherResultsHost = null;
  state.teacherRoom = null;
}

function exitTeacherRoom() {
  closeTeacherRoom();
  render();
}

function teacherRoomFlowStart() {
  if (teacherRoomFlow) teacherRoomFlow.destroy();
  teacherRoomFlow = window.StepFlow.create({
    text: teacherRoomText,
    steps: teacherRoomPath,
    step: teacherRoomStep,
    title: () => t("messenger.create.title"),
    trailing: teacherRoomTrailing,
    onExit: exitTeacherRoom,
  });
  teacherRoomFlow.start(teacherRoomPath()[0]);
}

function teacherRoomText(name, vars) {
  const key = TEACHER_ROOM_FLOW_TEXTS[name];
  return key ? t(key, vars) : "";
}

function teacherRoomTrailing() {
  return el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": t("messenger.create.exit"),
    onclick: exitTeacherRoom,
  }, [icon("close", 18)]);
}

function teacherRoomPath() {
  const form = state.teacherRoom;
  if (!form) return ["teacher"];
  const path = ["teacher"];
  if (!form.childOptions || form.childOptions.length !== 1) path.push("children");
  path.push("parents");
  if (form.duplicate) path.push("duplicate");
  path.push("review");
  return path;
}

function teacherRoomRefresh() {
  if (teacherRoomFlow) teacherRoomFlow.render();
}

function cancelTeacherSearch() {
  if (!teacherSearchAbort) return;
  teacherSearchAbort.abort();
  teacherSearchAbort = null;
}

function queueTeacherSearch(value) {
  const form = state.teacherRoom;
  if (!form) return;
  form.query = value;
  window.clearTimeout(teacherSearchTimer);
  cancelTeacherSearch();
  const query = value.trim();
  form.failed = false;
  if (!query) {
    form.results = null;
    form.searching = false;
    renderTeacherResults();
    return;
  }
  form.searching = true;
  renderTeacherResults();
  teacherSearchTimer = window.setTimeout(() => runTeacherSearch(query), TEACHER_SEARCH_DEBOUNCE_MS);
}

async function runTeacherSearch(query) {
  const form = state.teacherRoom;
  if (!form) return;
  const controller = window.AbortController ? new window.AbortController() : null;
  teacherSearchAbort = controller;
  let data = null;
  try {
    data = await getJson(`api/messenger/teachers?query=${encodeURIComponent(query)}&connection=${encodeURIComponent(currentConnectionId())}`, controller ? controller.signal : undefined);
  } catch (error) {
    if (controller && controller.signal.aborted) return;
    if (handleApiFailure(error)) return;
    data = null;
  }
  if (state.teacherRoom !== form || form.query.trim() !== query) return;
  teacherSearchAbort = null;
  form.searching = false;
  form.failed = !data;
  form.allowed = !data || data.allowed !== false;
  form.results = data ? data.teachers || [] : [];
  renderTeacherResults();
}

function findDuplicateRoom(label) {
  const data = state.messengerRooms;
  const name = String(label || "").trim().toLowerCase();
  if (!data || data.error || !name) return null;
  return (data.rooms || []).find((room) =>
    String(room.name || "").toLowerCase().includes(name) ||
    (room.members || []).some((member) => String(member).trim().toLowerCase() === name)
  ) || null;
}

function chooseTeacher(hit) {
  const form = state.teacherRoom;
  if (!form) return;
  form.teacher = hit;
  form.duplicate = findDuplicateRoom(hit.label);
  renderTeacherResults();
  if (teacherRoomFlow) teacherRoomFlow.sync();
}

function teacherHitRow(hit) {
  const form = state.teacherRoom;
  const chosen = !!(form.teacher && form.teacher.value === hit.value);
  const lines = [iservText("b", {}, hit.label)];
  if (hit.extra) lines.push(iservText("small", {}, hit.extra));
  return el("button", {
    class: "opt",
    type: "button",
    "aria-pressed": String(chosen),
    onclick: () => chooseTeacher(hit),
  }, [el("span", {}, lines)]);
}

function teacherResultNodes() {
  const form = state.teacherRoom;
  if (!form) return [];
  if (form.searching) return [loadingBlock()];
  if (form.failed) {
    return [emptyBlock("alert", t("messenger.create.search.failed.title"), t("messenger.create.search.failed.text"))];
  }
  if (!form.allowed) {
    return [emptyBlock("alert", t("messenger.create.search.forbidden.title"), t("messenger.create.search.forbidden.text"))];
  }
  if (form.results === null) {
    return [emptyBlock("search", t("messenger.create.search.start.title"), t("messenger.create.search.start.text"))];
  }
  if (!form.results.length) {
    return [emptyBlock("search", t("messenger.create.search.empty.title"), t("messenger.create.search.empty.text"))];
  }
  return [el("div", { class: "sw-list" }, form.results.map(teacherHitRow))];
}

function renderTeacherResults() {
  if (!teacherResultsHost) return;
  teacherResultsHost.replaceChildren(...teacherResultNodes());
}

function teacherSearchField() {
  const form = state.teacherRoom;
  const input = el("input", {
    class: "search-input",
    type: "search",
    dir: "auto",
    value: form.query || "",
    placeholder: t("messenger.create.search.placeholder"),
    "aria-label": t("messenger.create.search.placeholder"),
    autocomplete: "off",
    autocapitalize: "none",
    spellcheck: "false",
  });
  input.addEventListener("input", () => queueTeacherSearch(input.value));
  return el("div", { class: "search-field" }, [input]);
}

function toggleTeacherRoomChild(childId, on) {
  const form = state.teacherRoom;
  const kept = form.childIds.filter((value) => value !== childId);
  form.childIds = on ? kept.concat([childId]) : kept;
}

function teacherRoomChildRow(child) {
  const form = state.teacherRoom;
  const box = el("input", { type: "checkbox" });
  box.checked = form.childIds.includes(child.id);
  box.addEventListener("change", () => {
    toggleTeacherRoomChild(child.id, box.checked);
    if (teacherRoomFlow) teacherRoomFlow.sync();
  });
  return el("label", { class: "cell check" }, [box, iservText("span", {}, child.name || child.id)]);
}

function teacherRoomChildNodes() {
  const form = state.teacherRoom;
  if (form.childrenFailed) {
    return [
      emptyBlock(
        "alert",
        t("messenger.create.children.failed.title"),
        t("messenger.create.children.failed.text"),
        retryButton(loadTeacherRoomChildren)
      ),
    ];
  }
  if (!form.childOptions) return [loadingBlock()];
  if (!form.childOptions.length) {
    return [
      emptyBlock(
        "conferences",
        t("messenger.create.children.empty.title"),
        t("messenger.create.children.empty.text")
      ),
    ];
  }
  return [el("div", { class: "field-group" }, form.childOptions.map(teacherRoomChildRow))];
}

function teacherRoomParentsField() {
  const form = state.teacherRoom;
  const box = el("input", { type: "checkbox" });
  box.checked = !!form.addOtherParents;
  box.addEventListener("change", () => {
    form.addOtherParents = box.checked;
  });
  return el("div", { class: "field-group" }, [
    el("label", { class: "cell check" }, [box, el("span", {}, t("messenger.create.parents.label"))]),
    el("p", { class: "hint" }, t("messenger.create.parents.origin")),
  ]);
}

function teacherRoomChildNames() {
  const form = state.teacherRoom;
  return (form.childOptions || [])
    .filter((child) => form.childIds.includes(child.id))
    .map((child) => child.name || child.id)
    .filter(Boolean)
    .join(", ");
}

function teacherRoomReviewBody() {
  const form = state.teacherRoom;
  return el("div", { class: "sw-review" }, [
    el("div", { class: "create-name" }, [iservText("b", {}, form.teacher ? form.teacher.label : "")]),
    factList([
      [t("messenger.create.review.children"), teacherRoomChildNames()],
      [
        t("messenger.create.review.parents"),
        t(form.addOtherParents ? "messenger.create.review.parents.yes" : "messenger.create.review.parents.no"),
      ],
    ]),
    el("p", { class: "hint" }, t("messenger.create.parents.origin")),
  ]);
}

function openDuplicateRoom() {
  const form = state.teacherRoom;
  const room = form && form.duplicate;
  if (!room) return;
  closeTeacherRoom();
  setView("messenger");
  openMessengerRoom(room);
}

const TEACHER_ROOM_STEPS = {
  teacher(form) {
    teacherResultsHost = el("div", { class: "sw-results" });
    window.setTimeout(renderTeacherResults, 0);
    return {
      list: true,
      question: t("messenger.create.step.teacher"),
      body: [teacherSearchField(), teacherResultsHost],
      block: form.teacher ? "" : t("messenger.create.block.teacher"),
    };
  },
  children(form) {
    return {
      list: true,
      question: t("messenger.create.step.children"),
      body: teacherRoomChildNodes(),
      block: form.childIds.length ? "" : t("messenger.create.block.children"),
    };
  },
  parents() {
    return {
      question: t("messenger.create.step.parents"),
      body: [teacherRoomParentsField()],
    };
  },
  duplicate(form) {
    const room = form.duplicate;
    return {
      question: t("messenger.create.step.duplicate"),
      body: [
        el("div", { class: "sw-review" }, [
          el("div", { class: "create-name" }, [iservText("b", {}, room ? room.name || "" : "")]),
          el("p", { class: "dlg-text" }, t("messenger.create.duplicate.text")),
          el("button", { class: "btn", type: "button", onclick: openDuplicateRoom }, t("messenger.create.duplicate.open")),
        ]),
      ],
      nextLabel: t("messenger.create.duplicate.continue"),
    };
  },
  review(form) {
    return {
      question: t("messenger.create.step.review"),
      body: [teacherRoomReviewBody()],
      hint: t("messenger.create.review.warning", { name: form.teacher ? form.teacher.label : "" }),
      nextLabel: t("messenger.create.submit"),
      busyLabel: t("common.sending"),
      danger: true,
      onNext: submitTeacherRoom,
    };
  },
};

function teacherRoomStep(id) {
  const form = state.teacherRoom;
  if (!form) return { question: "", body: [], nextLabel: "" };
  const builder = TEACHER_ROOM_STEPS[id];
  if (!builder) return { question: "", body: [], nextLabel: t("common.next") };
  const step = builder(form);
  if (!step.nextLabel) step.nextLabel = t("common.next");
  return step;
}

async function submitTeacherRoom() {
  const form = state.teacherRoom;
  if (!form || !form.teacher) return t("messenger.create.block.teacher");
  if (!form.childIds.length) return t("messenger.create.block.children");
  let result = null;
  try {
    result = await postJson("api/messenger/room/teacher", {
      connection_id: currentConnectionId(),
      teacher: form.teacher.value,
      child_ids: form.childIds,
      add_other_parents: !!form.addOtherParents,
    }, TEACHER_ROOM_TIMEOUT_MS);
  } catch (error) {
    if (handleApiFailure(error)) return false;
    result = null;
  }
  if (state.teacherRoom !== form) return false;
  if (!result || !result.ok) return teacherRoomFailure(form, result);
  return finishTeacherRoom(form, result);
}

async function teacherRoomFailure(form, result) {
  const message = apiMessage(result, "api.messenger.room.failed");
  await loadMessengerRooms();
  if (state.teacherRoom !== form) return false;
  form.duplicate = findDuplicateRoom(form.teacher.label);
  if (form.duplicate) return { step: "duplicate" };
  return message;
}

async function finishTeacherRoom(form, result) {
  const roomId = result.room_id || "";
  const message = apiMessage(result, "api.messenger.room.ok");
  closeTeacherRoom();
  await loadMessengerRooms();
  const rooms = (state.messengerRooms && state.messengerRooms.rooms) || [];
  const created = rooms.find((room) => room.room_id === roomId) || null;
  setView("messenger");
  if (created) openMessengerRoom(created);
  toast(message);
  return true;
}

async function loadConferences() {
  const keep = !!(state.conferences && !state.conferences.error);
  const outcome = await reload("conferences", () => getJson("api/conferences"), keep);
  if (!outcome) return;
  if (outcome.data) state.conferences = outcome.data;
  else if (outcome.error) state.conferences = { error: outcome.error };
  if (state.view === "overview" || state.view === "conferences") rerender();
}

function conferencesView() {
  const view = el("div", {});
  const data = state.conferences;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage()
      ? outageEmptyBlock()
      : emptyBlock("alert", t("conferences.error.title"), t("conferences.error.text"), retryButton(() => { state.conferences = null; rerender(); loadConferences(); })));
    return view;
  }
  const conferencesNote = refreshFailureNote("conferences");
  if (conferencesNote) view.append(conferencesNote);
  const items = data.items || [];
  if (data.empty || !items.length) {
    view.append(emptyBlock("conferences", t("conferences.empty.title"), t("conferences.empty.text")));
    return view;
  }
  const rows = el("div", { class: "rows" });
  for (const item of items) {
    const cells = (item.cells || []).map((cell) => String(cell || "").trim()).filter(Boolean);
    if (!cells.length) continue;
    const link = (item.links || [])[0];
    const attrs = link ? { class: "row read", href: link, target: "_blank", rel: "noopener" } : { class: "row read" };
    rows.append(
      el(link ? "a" : "div", attrs, [
        el("span", { class: "row-dot" }),
        el("div", { class: "row-main" }, [
          el("div", { class: "row-title" }, cells[0]),
          cells.length > 1 ? el("div", { class: "row-sub" }, cells.slice(1).join(" · ")) : null,
        ]),
      ])
    );
  }
  view.append(rows);
  return view;
}

async function loadAbsences() {
  const school = currentConnectionId();
  const keep = !!(state.absence && !state.absence.error && (!state.absence.connectionId || state.absence.connectionId === school));
  const outcome = await reload("absence", () => getJson(`api/absences?connection=${encodeURIComponent(school)}`), keep, school);
  if (!outcome) return;
  if (outcome.data) state.absence = { data: outcome.data, connectionId: school };
  else if (outcome.error) state.absence = { error: outcome.error, connectionId: school };
  rerender();
}

function absenceStale(box) {
  return !box || (!!box.connectionId && box.connectionId !== currentConnectionId());
}

function absenceView() {
  const view = el("div", {});
  if (childPillsShown()) view.append(childPills(state.childId, selectChild));
  const banner = schoolIssueBanner([currentConnectionId()]);
  if (banner) view.append(banner);
  const box = state.absence;
  if (absenceStale(box)) {
    autoLoad("absence", loadAbsences);
    view.append(loadingBlock());
    return view;
  }
  if (box.error) {
    view.append(schoolInOutage(box.connectionId || currentConnectionId())
      ? outageEmptyBlock()
      : emptyBlock("alert", t("absence.error.title"), t("absence.error.text"), retryButton(() => { state.absence = null; rerender(); })));
    return view;
  }
  const data = box.data;
  const note = refreshFailureNote("absence");
  if (note) view.append(note);
  if (Array.isArray(data.children) && !data.children.length) {
    view.append(emptyBlock("absence", t("absence.children.empty.title"), t("absence.children.empty.text")));
  } else {
    view.append(el("button", { class: "btn", type: "button", onclick: () => startAbsenceForm() }, [icon("plus", 18), t("absence.report")]));
  }
  const phones = (data.phones || []).filter((entry) => entry.number);
  const entries = data.entries || [];
  view.append(el("div", { class: "section-head", style: "margin-top:28px" }, [el("span", { class: "overline" }, t("absence.reported"))]));
  if (!entries.length) {
    view.append(emptyBlock("check", t("absence.empty.title"), t("absence.empty.text")));
    return view;
  }
  const today = isoDate(new Date());
  const current = entries.filter((entry) => (entry.till_date || entry.from_date || "") >= today);
  const past = entries.filter((entry) => (entry.till_date || entry.from_date || "") < today);
  if (current.length) {
    const rows = el("div", { class: "rows" });
    for (const entry of current) rows.append(absenceRow(entry));
    view.append(rows);
  } else if (!past.length) {
    view.append(emptyBlock("check", t("absence.empty.title"), t("absence.empty.text")));
  } else {
    view.append(noteBlock(t("absence.none")));
  }
  if (past.length) view.append(absenceHistorySection(past));
  if (phones.length) view.append(absencePhonesSection(phones));
  return view;
}

function absencePhonesSection(phones) {
  const wrap = el("div", { style: "margin-top:28px" });
  wrap.append(el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("absence.phones.title"))]));
  const rows = el("div", { class: "rows" });
  for (const phone of phones) {
    const number = phone.number || "";
    rows.append(
      el("a", { class: "row read", href: `tel:${number}` }, [
        el("span", { class: "row-dot" }, [icon("phone", 14)]),
        el("div", { class: "row-main" }, [
          iservText("div", { class: "row-title" }, phone.label || t("absence.phone.fallback")),
          iservText("div", { class: "row-sub" }, number),
        ]),
      ])
    );
  }
  wrap.append(rows);
  return wrap;
}

function absenceHistorySection(past) {
  const wrap = el("div", { style: "margin-top:20px" });
  const open = state.absenceHistoryOpen;
  wrap.append(
    el("button", {
      class: "section-head",
      type: "button",
      style: "width:100%;background:none;border:0;padding:0;cursor:pointer;",
      "aria-expanded": String(open),
      onclick: () => { state.absenceHistoryOpen = !state.absenceHistoryOpen; rerender(); },
    }, [
      el("span", { class: "overline" }, t("absence.history.title", { count: formatNumber(past.length) })),
      el("span", { class: `ico-slot chev-toggle${open ? " open" : ""}`, html: iconSvg("chevron", 16) }),
    ])
  );
  if (open) {
    const rows = el("div", { class: "rows" });
    for (const entry of past) rows.append(absenceRow(entry));
    wrap.append(rows);
  }
  return wrap;
}

function absenceDates(entry) {
  const from = showDate(entry.from_date);
  const till = showDate(entry.till_date);
  if (from && till && from !== till) return dateRange(from, till);
  return from || till || "";
}

function absenceChildName(entry, full) {
  const children = (state.absence && state.absence.data && state.absence.data.children) || [];
  if (children.length < 2) return "";
  const found = children.find((child) => String(child.id) === String(entry.student_id));
  if (!found) return "";
  return full ? found.name : firstName(found.name) || found.name;
}

function absenceEntryLabel(entry) {
  if (entry.label_key) {
    const base = t(entry.label_key);
    return entry.target_key ? t("absence.label.withTarget", { label: base, target: t(entry.target_key) }) : base;
  }
  return entry.label || t("absence.entry.fallback");
}

function absenceLockedReason(entry) {
  if (entry.locked_reason_key) return t(entry.locked_reason_key);
  return entry.locked_reason || t("absence.locked.fallback");
}

function dayOptions(list) {
  return (list || []).map((option) => ({
    value: option.value,
    label: option.label_key ? t(option.label_key) : formatWeekdayDate(option.value) || option.label,
  }));
}

function absenceRow(entry) {
  const statusTag = entry.status ? STATUS_TAGS[entry.status] || null : null;
  const sub = [
    absenceChildName(entry),
    absenceDates(entry),
    entry.pickup_time ? t("absence.pickup", { time: entry.pickup_time }) : "",
    entry.comment || entry.subject || "",
  ]
    .filter(Boolean)
    .join(" · ");
  const tags = [];
  if (entry.from_history) tags.push(el("span", { class: "tag" }, t("absence.tag.history")));
  if (statusTag) tags.push(el("span", { class: `tag ${statusTag[0]}` }, t(statusTag[1])));
  if ((entry.attachments || []).length) tags.push(el("span", { class: "row-clip" }, [icon("clip", 14)]));
  return el("button", {
    class: openRowClass("row read", "absence", entry.id),
    type: "button",
    onclick: () => openAbsenceSheet(entry),
  }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, absenceEntryLabel(entry)),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
    tags.length ? el("div", { class: "row-side" }, tags) : null,
  ]);
}

function absenceTechEntries(entry) {
  const technical = entry.technical || {};
  const entries = [
    { label: t("absence.tech.id"), value: technical.id, kind: "text" },
    { label: t("absence.tech.createdAt"), value: technical.created_at, kind: "epoch" },
  ];
  if (entry.kind === "sick") {
    entries.push(
      { label: t("absence.tech.reporter"), value: technical.reporter, kind: "text" },
      { label: t("absence.tech.dutyToReport"), value: technical.duty_to_report, kind: "bool" },
      { label: t("absence.tech.classCode"), value: technical.class_code, kind: "text" },
      { label: t("absence.tech.writtenConfirmation"), value: technical.has_written_confirmation, kind: "bool" },
      { label: t("absence.tech.needsOfficial"), value: technical.needs_official_confirmation, kind: "bool" },
      { label: t("absence.tech.hasOfficial"), value: technical.has_official_confirmation, kind: "bool" },
      { label: t("absence.tech.counted"), value: technical.counted_in_statistics, kind: "bool" }
    );
  } else {
    entries.push(
      { label: t("absence.tech.updatedAt"), value: technical.updated_at, kind: "epoch" },
      { label: t("absence.tech.author"), value: technical.author, kind: "text" },
      { label: t("absence.tech.responseAuthor"), value: technical.response_author, kind: "text" }
    );
  }
  return entries;
}

function sickNotePdfBlock(entry) {
  const rules = (state.absence && state.absence.data && state.absence.data.rules) || {};
  const dutyHint = (rules.duty_hint || "").trim();
  const path = `api/absences/sick-note-pdf?id=${encodeURIComponent(entry.id)}`;
  const button = el("button", { type: "button", class: "btn" }, [icon("clip", 18), t("absence.sickNote.pdf")]);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await openAppFile(path, t("absence.sickNote.pdfFilename"), button);
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return el("div", { style: "margin-top:24px" }, [button, dutyHint ? noteBlock(dutyHint) : null]);
}

function absenceDetailParts(entry) {
  const facts = [
    [t("absence.fact.kind"), absenceEntryLabel(entry)],
    [t("absence.fact.range"), absenceDates(entry) || t("common.none")],
  ];
  const who = absenceChildName(entry, true);
  if (who) facts.splice(1, 0, [t("absence.fact.child"), who]);
  if (entry.from_period) {
    facts.push([
      t("absence.fact.hours"),
      t("absence.fact.hoursRange", {
        from: formatNumber(entry.from_period),
        till: formatNumber(entry.till_period || entry.from_period),
      }),
    ]);
  }
  if (entry.pickup_time) facts.push([t("absence.fact.pickup"), t("absence.fact.time", { time: entry.pickup_time })]);
  if (entry.subject) facts.push([t("absence.fact.subject"), entry.subject]);
  if (entry.comment) facts.push([t("absence.fact.comment"), entry.comment]);
  if (entry.weekly) facts.push([t("absence.fact.repeat"), t("absence.fact.weekly")]);
  if (entry.weekly && entry.repeat_until) facts.push([t("absence.fact.repeatUntil"), showDate(entry.repeat_until)]);
  if (entry.status && STATUS_TAGS[entry.status]) facts.push([t("absence.fact.status"), t(STATUS_TAGS[entry.status][1])]);
  const body = [factList(facts)];
  if (entry.answer) body.push(el("div", { class: "card", style: "margin-top:16px" }, [el("div", { class: "body-html", dir: "auto", html: entry.answer })]));
  const attachments = entry.attachments || [];
  if (attachments.length) {
    body.push(el("div", { class: "section-head", style: "margin-top:24px" }, [el("span", { class: "overline" }, t("common.attachments"))]));
    body.push(attachmentRows(attachments));
  }
  if (entry.kind === "sick") body.push(sickNotePdfBlock(entry));
  const foot = entry.deletable
    ? el("button", { class: "btn destructive", type: "button", onclick: () => withdrawAbsence(entry) }, [icon("trash", 18), t("absence.withdraw")])
    : noteBlock(absenceLockedReason(entry));
  return { title: absenceEntryLabel(entry), body, foot: [foot], extra: techDetailsButton(absenceTechEntries(entry)) };
}

function openAbsenceSheet(entry) {
  const detail = { kind: "absence", entry };
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") return openDetail(detail);
  openSheet(detailSheetFactory(detail));
}

async function withdrawAbsence(entry) {
  const ok = await confirmAction({
    title: t("absence.withdraw.confirmTitle", { label: absenceEntryLabel(entry) }),
    text: t("absence.withdraw.text"),
    confirmLabel: t("absence.withdraw"),
    destructive: true,
  });
  if (!ok) {
    openAbsenceSheet(entry);
    return;
  }
  dropSheet();
  state.detail = null;
  state.absence = null;
  rerender();
  try {
    const result = await postJson("api/absences/delete", {
      connection_id: currentConnectionId(),
      type: entry.kind,
      id: entry.id,
      target: entry.target || "",
    });
    const good = !!(result && result.ok);
    toast(apiMessage(result, good ? "absence.withdraw.done" : "absence.withdraw.failed"), good ? "good" : "bad");
  } catch (error) {
    if (!handleApiFailure(error)) toast(t("absence.withdraw.failed"), "bad");
  }
  loadAbsences();
}

function absenceChildColor(children, id) {
  const index = children.findIndex((c) => String(c.id) === String(id));
  return CHILD_COLORS[(index < 0 ? 0 : index) % CHILD_COLORS.length];
}

function daycareLeadDays(rules) {
  const lead = Math.max(0, rules.daycare_min_days || 0);
  if (lead > 0) return lead;
  const cutoff = /^(\d{1,2}):(\d{2})$/.exec(rules.daycare_cutoff || "");
  if (!cutoff) return 0;
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes() >= Number(cutoff[1]) * 60 + Number(cutoff[2]) ? 1 : 0;
}

const ABSENCE_DEFAULT_FROM_TIME = "08:00";
const ABSENCE_DEFAULT_TILL_TIME = "14:00";
const ABSENCE_CONDITIONAL_STEPS = ["sickHours", "leaveFrom", "leaveDayTime", "deregisterWhen", "daycareWhen"];
const ABSENCE_FLOW_TEXTS = {
  back: "absence.wizard.back",
  goal: "absence.wizard.progress.goal",
  progress: "absence.wizard.progress",
  progressTotal: "absence.wizard.progress.total",
  pending: "absence.wizard.progress.pending",
  failed: "absence.submit.failed",
};

let absenceFlow = null;

function absenceTypeList(data) {
  return ((data && data.types) || []).filter((key) => ABSENCE_TYPES[key]);
}

function absenceDefaultType(data) {
  const types = absenceTypeList(data);
  if (types.includes("sick")) return "sick";
  return types[0] || "sick";
}

const ABSENCE_STEP_TITLES = {
  sickPeriods: "absence.wizard.step.sick.periods",
  leaveTill: "absence.wizard.step.leave.till",
  leaveTimes: "absence.wizard.step.leave.times",
  repeatUntil: "absence.wizard.step.repeatUntil",
  daycarePickup: "absence.wizard.step.daycare.pickup",
};

const ABSENCE_REVEALS = {
  sickHours: { step: "sickPeriods", when: (form) => form.hours_mode === "byLesson" },
  daycareKind: { step: "daycarePickup", when: (form) => form.daycare_kind === "early_end" },
};

function absenceStepHost(id) {
  for (const host of Object.keys(ABSENCE_REVEALS)) {
    if (ABSENCE_REVEALS[host].step === id) return host;
  }
  return id;
}

function absenceRevealedStep(id, form) {
  const reveal = ABSENCE_REVEALS[id];
  return reveal && form && reveal.when(form) ? reveal.step : "";
}

function absenceRevealName(id) {
  const reveal = ABSENCE_REVEALS[id];
  return reveal ? t(ABSENCE_STEP_TITLES[reveal.step]) : "";
}

function absenceAnnounceReveal(id, shown) {
  const name = absenceRevealName(id);
  if (!name || !absenceFlow) return;
  absenceFlow.announce(t(shown ? "absence.wizard.fieldShown" : "absence.wizard.fieldHidden", { name }));
}

function absenceAnnounceStep(stepId, added) {
  if (!absenceFlow) return;
  absenceFlow.announce(
    t(added ? "absence.wizard.stepAdded" : "absence.wizard.stepRemoved", { name: t(ABSENCE_STEP_TITLES[stepId]) })
  );
}

function absencePath(form, data) {
  if (!form || !data) return [];
  const rules = data.rules || {};
  const ids = [];
  if (absenceTypeList(data).length > 1) ids.push("type");
  if ((data.children || []).length > 1) ids.push("child");
  if (form.type === "sick") {
    ids.push("sickWhen");
    if (rules.sick_by_lesson) {
      ids.push("sickHours");
      if (form.hours_mode === "byLesson") ids.push("sickPeriods");
    }
  } else if (form.type === "leave") {
    ids.push("leaveFrom");
    if (form.duration === "more") ids.push("leaveTill");
    ids.push("leaveDayTime");
    if (form.time_mode === "custom") ids.push("leaveTimes");
    ids.push("leaveSubject", "leaveBody");
  } else if (form.type === "deregister") {
    if ((data.deregister_options || []).length !== 1) ids.push("deregisterTarget");
    ids.push("deregisterWhen");
    if (form.repeat === "weekly") ids.push("repeatUntil");
  } else {
    ids.push("daycareKind");
    if (form.daycare_kind === "early_end") ids.push("daycarePickup");
    ids.push("daycareWhen");
    if (form.repeat === "weekly") ids.push("repeatUntil");
    if (rules.daycare_reason_required) ids.push("daycareReason");
  }
  ids.push("review");
  return ids.filter((id) => {
    const host = absenceStepHost(id);
    return host === id || !ids.includes(host);
  });
}

function absenceCurrentPath() {
  return absencePath(state.absenceForm, state.absence && state.absence.data);
}

function absenceIsDetour(id) {
  return !!id && !absenceCurrentPath().includes(id);
}

function absenceFlowText(name, vars) {
  const key = ABSENCE_FLOW_TEXTS[name];
  return key ? t(key, vars) : "";
}

function absenceFlowLead() {
  const data = state.absence.data;
  const children = data.children || [];
  if (children.length < 2) return null;
  const child = children.find((entry) => String(entry.id) === String(state.absenceForm.student_id));
  if (!child) return null;
  const name = child.name || "";
  const avatar = iservText("span", { class: "avatar" }, (name || "?").trim().charAt(0).toUpperCase());
  avatar.style.background = absenceChildColor(children, child.id);
  return el("button", {
    class: "sw-lead-btn",
    type: "button",
    "aria-label": name,
    onclick: () => absenceOpenStep("child"),
  }, [avatar]);
}

function absenceFlowTrailing() {
  return el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": t("absence.wizard.exit"),
    onclick: absenceExit,
  }, [icon("close", 18)]);
}

function absenceExit() {
  leaveAbsenceForm(() => {
    closeAbsenceForm();
    render();
  });
}

function closeAbsenceForm() {
  if (absenceFlow) absenceFlow.destroy();
  absenceFlow = null;
  document.removeEventListener("visibilitychange", absenceRecheckLimits);
  state.absenceForm = null;
  state.absenceFormDefault = null;
}

function wizRefresh() {
  if (absenceFlow) absenceFlow.render();
}

function absenceOpenStep(id) {
  if (!absenceFlow) return;
  absenceFlow.returnTo("review");
  absenceFlow.go(absenceStepHost(id));
}

function absenceRecheckLimits() {
  if (document.hidden || !absenceFlow || !state.absenceForm) return;
  absenceFlow.sync();
}

function absenceRedirect(id) {
  if (id !== "review" || !state.absenceForm) return id;
  const problem = absenceProblemEntry(state.absenceForm, state.absence.data);
  if (!problem) return id;
  return { step: problem.step, status: problem.text };
}

function absenceFlowStart(startAt) {
  if (absenceFlow) absenceFlow.destroy();
  absenceFlow = window.StepFlow.create({
    text: absenceFlowText,
    steps: absenceCurrentPath,
    detour: absenceIsDetour,
    redirect: absenceRedirect,
    step: absenceStep,
    pending: (id) => ABSENCE_CONDITIONAL_STEPS.includes(id) && !ABSENCE_REVEALS[id],
    title: () => absenceTypeLabel(state.absenceForm.type),
    lead: absenceFlowLead,
    trailing: absenceFlowTrailing,
    onExit: absenceExit,
  });
  document.addEventListener("visibilitychange", absenceRecheckLimits);
  absenceFlow.start(startAt || absenceCurrentPath()[0]);
}

function startAbsenceForm(type, studentId) {
  const data = state.absence.data;
  const children = data.children || [];
  const rules = data.rules || {};
  const chosen = type || absenceDefaultType(data);
  const form = {
    type: chosen,
    student_id: studentId != null ? String(studentId) : children.length === 1 ? String(children[0].id) : "",
  };
  if (chosen === "sick") {
    const options = data.day_options || { from: [], till: [] };
    form.day_from = (options.from[0] || {}).value || "";
    form.day_till = (options.till[0] || {}).value || "";
    form.hours_mode = "full";
    form.from_period = "";
    form.till_period = "";
    form.duty_to_report = false;
    form.comment = "";
  } else if (chosen === "leave") {
    const first = isoDate(addDays(new Date(), Math.max(0, rules.leave_min_days || 0)));
    form.from_date = first;
    form.till_date = first;
    form.duration = "one";
    form.from_time = ABSENCE_DEFAULT_FROM_TIME;
    form.till_time = ABSENCE_DEFAULT_TILL_TIME;
    form.time_mode = "school";
    form.subject = t("absence.leave.subjectPlaceholder", { date: showDate(first) });
    form.subject_auto = true;
    form.body = "";
    form.attachments = [];
  } else if (chosen === "deregister") {
    form.deregister_from = (data.deregister_options || [])[0] || "";
    form.date = isoDate(new Date());
    form.repeat = "once";
    form.repeat_until = "";
  } else {
    form.daycare_kind = "deregister";
    form.date = isoDate(addDays(new Date(), daycareLeadDays(rules)));
    form.pickup_time = (rules.daycare_pickup_times || [])[0] || "";
    form.repeat = "once";
    form.repeat_until = "";
    form.reason = "";
  }
  dropSheet();
  state.absenceForm = form;
  state.absenceFormDefault = copy(form);
  absenceFlowStart();
  render();
}

function absenceChildLabel(child) {
  const name = firstName(child.name) || child.name || "";
  const className = child.class_name || "";
  return className ? t("absence.wizard.childLine", { name, class: className }) : name;
}

function absenceChoice(title, active, onclick) {
  return el("button", { class: "opt", type: "button", "aria-pressed": String(active), onclick }, [el("b", {}, title)]);
}

function absenceSegment(options) {
  return el("div", { class: "opt-row" }, options.map((option) =>
    el("button", { class: "opt", type: "button", "aria-pressed": String(option.active), onclick: option.onclick }, [
      el("b", {}, option.label),
    ])
  ));
}

function withHint(field, text) {
  if (text) field.append(el("span", { class: "hint" }, text));
  return field;
}

function absenceChooseType(key) {
  if (key === state.absenceForm.type) return;
  const keep = state.absenceForm.student_id;
  leaveAbsenceForm(() => startAbsenceForm(key, keep || undefined));
}

function absenceSetHoursMode(key) {
  const form = state.absenceForm;
  if ((form.hours_mode || "full") === key) return;
  const dropped = key === "full" && !!(form.from_period || form.till_period);
  form.hours_mode = key;
  if (key === "full") {
    form.from_period = "";
    form.till_period = "";
  } else {
    const numbers = (state.absence.data.period_labels || []).map((entry) => String(entry.number));
    form.from_period = numbers[0] || "";
    form.till_period = numbers[numbers.length - 1] || "";
  }
  wizRefresh();
  if (dropped) absenceFlow.status(t("absence.wizard.periodsDropped"), "");
  absenceAnnounceReveal("sickHours", key === "byLesson");
}

function absenceSetRepeat(key) {
  const form = state.absenceForm;
  if (form.repeat === key) return;
  form.repeat = key;
  if (key === "once") form.repeat_until = "";
  wizRefresh();
  absenceAnnounceStep("repeatUntil", key === "weekly");
}

function absenceSyncSubject() {
  const form = state.absenceForm;
  if (!form.subject_auto) return;
  form.subject = t("absence.leave.subjectPlaceholder", { date: showDate(form.from_date) });
}

function absenceSickCutoffHint(rules) {
  if (!rules.sick_cutoff) return "";
  return rules.sick_cutoff_message || t("absence.sick.cutoff", { time: rules.sick_cutoff });
}

function absenceStep(id) {
  const form = state.absenceForm;
  const data = state.absence && state.absence.data;
  if (!form || !data) return { question: "", body: [], nextLabel: "" };
  const builder = ABSENCE_STEP_BUILDERS[id];
  if (!builder) return { question: "", body: [], nextLabel: t("common.next") };
  const step = builder(form, data, data.rules || {});
  const revealed = absenceRevealedStep(id, form);
  if (revealed) {
    step.body = [].concat(step.body || [], [
      el("div", { class: "sw-reveal" }, [].concat(ABSENCE_STEP_BUILDERS[revealed](form, data, data.rules || {}).body || [])),
    ]);
  }
  if (!step.nextLabel) step.nextLabel = t("common.next");
  const blocker = absenceStepBlock(id, form, data);
  if (blocker) {
    step.block = blocker.hint;
    step.blockFocus = () => document.querySelector(".sw-body .inp, .sw-body .sel, .sw-body .txt");
  }
  if (absenceIsDetour(id)) {
    step.nextLabel = t("absence.wizard.toReview");
    step.nextTarget = "review";
  }
  return step;
}

const ABSENCE_STEP_BUILDERS = {
  type(form, data) {
    return {
      list: true,
      question: t("absence.sheet.type"),
      hint: ABSENCE_TYPES[form.type] ? t(ABSENCE_TYPES[form.type].hint) : "",
      body: [
        el("div", { class: "sw-list" }, absenceTypeList(data).map((key) =>
          absenceChoice(t(ABSENCE_TYPES[key].label), form.type === key, () => absenceChooseType(key))
        )),
      ],
    };
  },
  child(form, data) {
    const children = data.children || [];
    return {
      list: true,
      question: t("absence.sheet.child"),
      body: [
        el("div", { class: "sw-list" }, children.map((child) =>
          absenceChoice(
            absenceChildLabel(child),
            String(child.id) === String(form.student_id),
            () => {
              form.student_id = String(child.id);
              wizRefresh();
            }
          )
        )),
      ],
    };
  },
  sickWhen(form, data, rules) {
    const options = data.day_options || { from: [], till: [] };
    return {
      question: t("absence.wizard.step.sick.when"),
      body: [
        withHint(
          selectField(t("absence.field.fromDay"), form.day_from, dayOptions(options.from), (value) => {
            form.day_from = value;
            if (form.day_till < value) form.day_till = value;
            wizRefresh();
          }),
          absenceSickCutoffHint(rules)
        ),
        selectField(
          t("absence.field.tillDay"),
          form.day_till,
          dayOptions(options.till).filter((item) => item.value >= form.day_from),
          (value) => {
            form.day_till = value;
          }
        ),
      ],
    };
  },
  sickHours(form) {
    const mode = form.hours_mode || "full";
    return {
      question: t("absence.wizard.step.sick.hours"),
      body: [
        absenceSegment([
          { label: t("absence.hours.full"), active: mode === "full", onclick: () => absenceSetHoursMode("full") },
          { label: t("absence.hours.byLesson"), active: mode === "byLesson", onclick: () => absenceSetHoursMode("byLesson") },
        ]),
      ],
    };
  },
  sickPeriods(form, data) {
    const periods = (data.period_labels || []).map((entry) => ({ value: String(entry.number), label: entry.label }));
    return {
      question: t("absence.wizard.step.sick.periods"),
      body: [
        selectField(t("absence.field.fromPeriod"), form.from_period, periods, (value) => {
          form.from_period = value;
          wizRefresh();
        }),
        selectField(t("absence.field.tillPeriod"), form.till_period, periods, (value) => {
          form.till_period = value;
          wizRefresh();
        }),
      ],
    };
  },
  sickComment(form) {
    return {
      question: t("absence.wizard.step.sick.comment"),
      body: [
        textField(t("absence.field.optionalComment"), form.comment, (value) => {
          form.comment = value;
        }),
      ],
    };
  },
  leaveFrom(form, data, rules) {
    const min = isoDate(addDays(new Date(), Math.max(0, rules.leave_min_days || 0)));
    const lead = rules.leave_min_days
      ? t("absence.leave.lead", { days: formatNumber(rules.leave_min_days), date: showDate(min) })
      : "";
    return {
      question: t("absence.wizard.step.leave.from"),
      body: [
        withHint(
          dateField(t("absence.field.fromDay"), form.from_date, min, (value) => {
            form.from_date = value;
            if (form.till_date < value) form.till_date = value;
            absenceSyncSubject();
            wizRefresh();
          }),
          lead
        ),
        absenceSegment([
          {
            label: t("absence.duration.oneDay"),
            active: form.duration !== "more",
            onclick: () => {
              if (form.duration === "one") return;
              form.duration = "one";
              form.till_date = form.from_date;
              wizRefresh();
              absenceAnnounceStep("leaveTill", false);
            },
          },
          {
            label: t("absence.duration.moreDays"),
            active: form.duration === "more",
            onclick: () => {
              if (form.duration === "more") return;
              form.duration = "more";
              wizRefresh();
              absenceAnnounceStep("leaveTill", true);
            },
          },
        ]),
      ],
    };
  },
  leaveTill(form) {
    return {
      question: t("absence.wizard.step.leave.till"),
      body: [
        dateField(t("absence.field.tillDay"), form.till_date, form.from_date, (value) => {
          form.till_date = value;
          wizRefresh();
        }),
      ],
    };
  },
  leaveDayTime(form) {
    return {
      question: t("absence.wizard.step.leave.dayTime"),
      body: [
        absenceSegment([
          {
            label: t("absence.time.schoolDay", { from: ABSENCE_DEFAULT_FROM_TIME, till: ABSENCE_DEFAULT_TILL_TIME }),
            active: form.time_mode !== "custom",
            onclick: () => {
              if (form.time_mode === "school") return;
              form.time_mode = "school";
              form.from_time = ABSENCE_DEFAULT_FROM_TIME;
              form.till_time = ABSENCE_DEFAULT_TILL_TIME;
              wizRefresh();
              absenceAnnounceStep("leaveTimes", false);
            },
          },
          {
            label: t("absence.time.custom"),
            active: form.time_mode === "custom",
            onclick: () => {
              if (form.time_mode === "custom") return;
              form.time_mode = "custom";
              wizRefresh();
              absenceAnnounceStep("leaveTimes", true);
            },
          },
        ]),
      ],
    };
  },
  leaveTimes(form) {
    return {
      question: t("absence.wizard.step.leave.times"),
      body: [
        timeField(t("absence.field.start"), form.from_time, (value) => {
          form.from_time = value;
          wizRefresh();
        }),
        timeField(t("absence.field.end"), form.till_time, (value) => {
          form.till_time = value;
          wizRefresh();
        }),
      ],
    };
  },
  leaveSubject(form) {
    return {
      question: t("absence.wizard.step.leave.subject"),
      body: [
        inputField(t("absence.field.subject"), form.subject, "", (value) => {
          form.subject = value;
          form.subject_auto = false;
          absenceFlow.sync();
        }),
      ],
    };
  },
  leaveBody(form) {
    return {
      question: t("absence.wizard.step.leave.body"),
      body: [
        withHint(
          textField(t("absence.field.request"), form.body, (value) => {
            form.body = value;
            absenceFlow.sync();
          }),
          t("absence.leave.requestHint")
        ),
      ],
    };
  },
  leaveAttachments(form) {
    return {
      question: t("absence.wizard.step.leave.attachments"),
      body: [absenceAttachmentsField(form)],
    };
  },
  deregisterTarget(form, data) {
    return {
      list: true,
      question: t("absence.deregister.target"),
      body: [
        el("div", { class: "sw-list" }, (data.deregister_options || []).map((key) =>
          absenceChoice(targetLabel(key), form.deregister_from === key, () => {
            form.deregister_from = key;
            wizRefresh();
          })
        )),
      ],
    };
  },
  deregisterWhen(form) {
    return {
      question: t("absence.wizard.step.deregister.when"),
      body: [
        dateField(t("absence.field.on"), form.date, isoDate(new Date()), (value) => {
          form.date = value;
          wizRefresh();
        }),
        absenceRepeatSegment(form),
      ],
    };
  },
  repeatUntil(form) {
    return {
      question: t("absence.wizard.step.repeatUntil"),
      body: [
        withHint(
          dateField(t("absence.repeat.until"), form.repeat_until, form.date, (value) => {
            form.repeat_until = value;
            wizRefresh();
          }),
          t("absence.repeat.info")
        ),
      ],
    };
  },
  daycareKind(form) {
    return {
      list: true,
      question: t("absence.wizard.step.daycare.kind"),
      hint: t(form.daycare_kind === "early_end" ? "absence.daycare.earlyEnd.hint" : "absence.daycare.deregister.hint"),
      body: [
        el("div", { class: "sw-list" }, [
          absenceChoice(t("absence.daycare.deregister.title"), form.daycare_kind === "deregister", () =>
            absenceSetDaycareKind("deregister")
          ),
          absenceChoice(t("absence.daycare.earlyEnd.title"), form.daycare_kind === "early_end", () =>
            absenceSetDaycareKind("early_end")
          ),
        ]),
      ],
    };
  },
  daycarePickup(form, data, rules) {
    const times = rules.daycare_pickup_times || [];
    const free = rules.daycare_custom_pickup || !times.length;
    return {
      question: t("absence.wizard.step.daycare.pickup"),
      body: [
        free
          ? timeField(t("absence.field.pickup"), form.pickup_time, (value) => {
              form.pickup_time = value;
              wizRefresh();
            })
          : selectField(
              t("absence.field.pickup"),
              form.pickup_time,
              times.map((time) => ({ value: time, label: t("absence.fact.time", { time }) })),
              (value) => {
                form.pickup_time = value;
                wizRefresh();
              }
            ),
      ],
    };
  },
  daycareWhen(form, data, rules) {
    const lead = daycareLeadDays(rules);
    const hint = lead > 0 && rules.daycare_cutoff ? t("absence.daycare.cutoff", { time: rules.daycare_cutoff }) : "";
    return {
      question: t("absence.wizard.step.daycare.when"),
      body: [
        withHint(
          dateField(t("absence.field.date"), form.date, isoDate(addDays(new Date(), lead)), (value) => {
            form.date = value;
            wizRefresh();
          }),
          hint
        ),
        absenceRepeatSegment(form),
      ],
    };
  },
  daycareReason(form, data, rules) {
    return {
      question: t("absence.wizard.step.daycare.reason"),
      body: [
        textField(t(rules.daycare_reason_required ? "absence.field.reason" : "absence.field.reasonOptional"), form.reason, (value) => {
          form.reason = value;
          absenceFlow.sync();
        }),
      ],
    };
  },
  review(form, data) {
    const sick = form.type === "sick";
    const hint = sick
      ? t("absence.review.sendsNow") + " " + t("absence.sick.warning")
      : t("absence.review.sendsNow");
    return {
      question: t("absence.wizard.step.review"),
      body: [absenceReviewBody(form, data)],
      hint,
      nextLabel: t(sick ? "absence.confirm.sick.button" : "absence.confirm.button"),
      busyLabel: t("common.sending"),
      onNext: submitAbsence,
    };
  },
};

function absenceSetDaycareKind(kind) {
  const form = state.absenceForm;
  if (form.daycare_kind === kind) return;
  form.daycare_kind = kind;
  wizRefresh();
  absenceAnnounceReveal("daycareKind", kind === "early_end");
}

function absenceRepeatSegment(form) {
  return absenceSegment([
    { label: t("absence.repeat.once"), active: form.repeat !== "weekly", onclick: () => absenceSetRepeat("once") },
    { label: t("absence.repeat.weekly"), active: form.repeat === "weekly", onclick: () => absenceSetRepeat("weekly") },
  ]);
}

function absenceReviewBody(form, data) {
  const wrap = el("div", { class: "sw-review" });
  if (form.type === "sick") wrap.append(absenceDutyCard(form, data));
  wrap.append(absenceFactCard(form, data));
  return wrap;
}

function absenceDutyText(data) {
  const rules = (data && data.rules) || {};
  return String(rules.duty_hint || "").trim() || t("absence.sick.dutyHint");
}

function absenceDutySheet(text) {
  return sheet(t("absence.review.dutyExplain"), [iservText("p", { class: "dlg-text" }, text)]);
}

function absenceDutyCard(form, data) {
  const box = el("input", { type: "checkbox" });
  box.checked = !!form.duty_to_report;
  box.addEventListener("change", () => {
    form.duty_to_report = box.checked;
  });
  const text = absenceDutyText(data);
  return el("div", { class: "field-group sw-duty" }, [
    el("label", { class: "cell check" }, [box, el("span", {}, t("absence.field.dutyToReport"))]),
    el("button", {
      class: "cell sw-duty-more",
      type: "button",
      onclick: () => openSheet(() => absenceDutySheet(text)),
    }, [
      el("span", {}, t("absence.review.dutyExplain")),
      el("span", { class: "sw-fact-go chev-next", html: iconSvg("chevron", 14) }),
    ]),
  ]);
}

function absenceFactCard(form, data) {
  const card = el("div", { class: "sw-facts" });
  for (const fact of absenceReviewFacts(form, data)) {
    const parts = [
      el("span", { class: "sw-fact-label" }, fact.label),
      el("span", { class: "sw-fact-value", dir: "auto" }, fact.value),
    ];
    if (!fact.step) {
      card.append(el("div", { class: "sw-fact fixed" }, parts));
      continue;
    }
    card.append(
      el("button", {
        class: "sw-fact",
        type: "button",
        "aria-label": t("absence.wizard.change", { field: fact.label }),
        onclick: () => absenceOpenStep(fact.step),
      }, parts.concat([el("span", { class: "sw-fact-go chev-next", html: iconSvg("chevron", 14) })]))
    );
  }
  return card;
}

function absenceSickHoursText(form, data) {
  if (form.from_period) {
    return t("absence.fact.hoursRange", {
      from: formatNumber(form.from_period),
      till: formatNumber(form.till_period || form.from_period),
    });
  }
  const last = lastAvailablePeriod(data);
  return last ? t("absence.confirm.hoursDefault", { till: formatNumber(last) }) : "";
}

function absenceRange(from, till) {
  return from === till ? showDate(from) : t("absence.confirm.range", { from: showDate(from), till: showDate(till) });
}

function absenceJoin(first, second) {
  return second ? t("absence.wizard.factJoin", { first, second }) : first;
}

function absenceReviewFacts(form, data) {
  data = data || {};
  const rules = data.rules || {};
  const children = data.children || [];
  const facts = [];
  facts.push({
    label: t("absence.fact.child"),
    value: childNameForForm(),
    step: children.length > 1 ? "child" : "",
  });
  facts.push({ label: t("absence.fact.kind"), value: absenceTypeLabel(form.type), step: "" });
  if (form.type === "sick") {
    facts.push({
      label: t("absence.fact.range"),
      value: absenceJoin(absenceRange(form.day_from, form.day_till), absenceSickHoursText(form, data)),
      step: "sickWhen",
    });
    if (rules.sick_comment) {
      facts.push({
        label: t("absence.fact.comment"),
        value: form.comment || t("absence.wizard.none"),
        step: "sickComment",
      });
    }
    return facts;
  }
  if (form.type === "leave") {
    const times = form.time_mode === "custom" ? `${form.from_time}–${form.till_time}` : "";
    facts.push({
      label: t("absence.fact.range"),
      value: absenceJoin(absenceRange(form.from_date, form.till_date), times),
      step: "leaveFrom",
    });
    facts.push({ label: t("absence.fact.subject"), value: form.subject, step: "leaveSubject" });
    facts.push({
      label: t("absence.fact.attachments"),
      value: (form.attachments || []).length
        ? tCount("absence.attachments.count", (form.attachments || []).length)
        : t("absence.wizard.none"),
      step: "leaveAttachments",
    });
    return facts;
  }
  const repeat = form.repeat === "weekly" && form.repeat_until ? t("absence.confirm.weeklyUntil") + " " + showDate(form.repeat_until) : "";
  if (form.type === "deregister") {
    facts.push({ label: t("absence.confirm.target"), value: targetLabel(form.deregister_from), step: "deregisterTarget" });
    facts.push({ label: t("absence.fact.range"), value: absenceJoin(showDate(form.date), repeat), step: "deregisterWhen" });
    return facts;
  }
  facts.push({
    label: t("absence.confirm.daycareKind"),
    value: t(form.daycare_kind === "early_end" ? "absence.daycare.earlyEnd.title" : "absence.daycare.deregister.title"),
    step: "daycareKind",
  });
  if (form.daycare_kind === "early_end") {
    facts.push({
      label: t("absence.fact.pickup"),
      value: form.pickup_time ? t("absence.fact.time", { time: form.pickup_time }) : t("absence.wizard.none"),
      step: "daycarePickup",
    });
  }
  facts.push({ label: t("absence.fact.range"), value: absenceJoin(showDate(form.date), repeat), step: "daycareWhen" });
  facts.push({
    label: t("absence.fact.reason"),
    value: form.reason || t("absence.wizard.none"),
    step: "daycareReason",
  });
  return facts;
}

function absenceAttachmentsField(form) {
  form.attachments = form.attachments || [];
  const wrap = el("div", { class: "field-group" }, [el("span", { class: "lbl" }, t("absence.attachments.label"))]);
  const list = el("div", { class: "rows" });
  const input = el("input", { type: "file", multiple: "multiple", style: "display:none" });
  const renderList = () => {
    list.replaceChildren();
    form.attachments.forEach((file, index) => {
      const oversized = file.size > MAX_ATTACHMENT_BYTES;
      const attachmentName = file.name || "";
      const remove = el("button", { class: "search-clear", type: "button", "aria-label": t("absence.attachments.remove", { name: attachmentName }) }, [icon("close", 14)]);
      remove.addEventListener("click", () => {
        form.attachments.splice(index, 1);
        renderList();
        if (absenceFlow) absenceFlow.sync();
      });
      list.append(
        el("div", { class: "row read disabled" }, [
          el("span", { class: "row-dot" }, [icon("clip", 14)]),
          el("div", { class: "row-main" }, [
            iservText("div", { class: "row-title full" }, attachmentName),
            oversized ? el("div", { class: "row-sub", style: "color:var(--danger)" }, t("absence.attachments.oversized")) : null,
          ]),
          remove,
        ])
      );
    });
  };
  renderList();
  input.addEventListener("change", () => {
    form.attachments = form.attachments.concat(Array.from(input.files));
    input.value = "";
    renderList();
    if (absenceFlow) absenceFlow.sync();
  });
  const addBtn = el("button", { class: "btn ghost slim", type: "button" }, [icon("plus", 14), t("absence.attachments.add")]);
  addBtn.addEventListener("click", () => input.click());
  wrap.append(list, addBtn, input);
  return wrap;
}

function selectField(label, value, options, onchange) {
  const select = el("select", { class: "sel" });
  for (const option of options) {
    const node = el("option", { value: option.value }, option.label);
    if (String(option.value) === String(value)) node.selected = true;
    select.append(node);
  }
  select.addEventListener("change", () => onchange(select.value));
  return el("label", { class: "field" }, [
    el("span", { class: "lbl" }, label),
    el("div", { class: "sel-wrap" }, [select, el("span", { class: "caret", html: iconSvg("chevron", 14) })]),
  ]);
}

function inputField(label, value, placeholder, oninput) {
  const input = el("input", {
    class: "inp",
    type: "text",
    value: value || "",
    placeholder: placeholder || "",
    autocomplete: "off",
    enterkeyhint: "next",
    "aria-label": label,
  });
  input.addEventListener("input", () => oninput(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function textField(label, value, oninput) {
  const area = el("textarea", { class: "txt", rows: "4", autocomplete: "off", "aria-label": label });
  area.value = value || "";
  area.addEventListener("input", () => oninput(area.value));
  return el("label", { class: "field text" }, [el("span", { class: "lbl" }, label), area]);
}

function dateField(label, value, min, onchange) {
  const input = el("input", { class: "inp", type: "date", value: value || "", min: min || null });
  input.addEventListener("change", () => onchange(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function timeField(label, value, onchange) {
  const input = el("input", { class: "inp", type: "time", value: value || "" });
  input.addEventListener("change", () => onchange(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function absenceAttachmentsProblem(form) {
  const attachments = form.attachments || [];
  if (attachments.some((file) => file.size > MAX_ATTACHMENT_BYTES)) {
    return { text: t("absence.attachments.oversized"), hint: t("absence.attachments.oversized.short") };
  }
  const total = attachments.reduce((sum, file) => sum + file.size, 0);
  if (total > MAX_TOTAL_ATTACHMENT_BYTES) {
    return { text: t("absence.attachments.totalOversized"), hint: t("absence.attachments.totalOversized.short") };
  }
  return null;
}

function absenceNeed(labelKey) {
  return t("absence.wizard.need", { field: t(labelKey) });
}

function absenceDayStale(form) {
  return !!form.day_from && form.day_from < isoDate(new Date());
}

function absenceDaycareStale(form, rules) {
  return !!form.date && form.date < isoDate(addDays(new Date(), daycareLeadDays(rules)));
}

function absenceProblems(form, data) {
  data = data || {};
  const rules = data.rules || {};
  const children = data.children || [];
  const list = [];
  const push = (step, text, hint) => list.push({ step: absenceStepHost(step), text, hint: hint || text });
  if (!form.student_id) push("child", t("absence.problem.child"), t("absence.wizard.required"));
  const attachments = absenceAttachmentsProblem(form);
  if (attachments) push("leaveAttachments", attachments.text, attachments.hint);
  if (form.type === "sick") {
    if (form.from_period && !form.till_period) {
      push("sickPeriods", t("absence.problem.periodIncomplete"), absenceNeed("absence.field.tillPeriod"));
    } else if (form.from_period && form.till_period && Number(form.till_period) < Number(form.from_period)) {
      push("sickPeriods", t("absence.problem.periodOrder"), t("absence.problem.periodOrder"));
    }
    if (absenceDayStale(form)) push("sickWhen", t("absence.problem.dateStale"), t("absence.problem.dateStale"));
  }
  if (form.type === "leave") {
    if (form.till_date < form.from_date) push("leaveTill", t("absence.problem.range"), t("absence.problem.range"));
    if (
      form.from_date === form.till_date &&
      form.from_time &&
      form.till_time &&
      form.till_time <= form.from_time
    ) {
      push("leaveTimes", t("absence.problem.timeOrder"), t("absence.problem.timeOrder"));
    }
    if (!String(form.subject || "").trim()) {
      push("leaveSubject", t("absence.problem.subject"), absenceNeed("absence.field.subject"));
    }
    if (!String(form.body || "").trim()) push("leaveBody", t("absence.problem.body"), absenceNeed("absence.field.request"));
  }
  if (form.type === "deregister" && !form.deregister_from) {
    push("deregisterTarget", t("absence.problem.deregisterTarget"), t("absence.wizard.required"));
  }
  if (form.type === "daycare") {
    if (form.daycare_kind === "early_end" && !form.pickup_time) {
      push("daycarePickup", t("absence.problem.pickup"), absenceNeed("absence.field.pickup"));
    }
    if (rules.daycare_reason_required && !String(form.reason || "").trim()) {
      push("daycareReason", t("absence.problem.reason"), absenceNeed("absence.field.reason"));
    }
    if (absenceDaycareStale(form, rules)) push("daycareWhen", t("absence.problem.dateStale"), t("absence.problem.dateStale"));
  }
  if (form.repeat === "weekly") {
    if (!form.repeat_until) push("repeatUntil", t("absence.problem.repeatUntil"), absenceNeed("absence.repeat.until"));
    else if (form.repeat_until < (form.date || "")) {
      push("repeatUntil", t("absence.problem.repeatBeforeDate"), t("absence.problem.repeatBeforeDate"));
    }
  }
  return list;
}

function absenceProblemEntry(form, data) {
  return absenceProblems(form, data)[0] || null;
}

function absenceProblem(form, data) {
  const entry = absenceProblemEntry(form, data);
  return entry ? entry.text : "";
}

function absenceStepBlock(id, form, data) {
  return absenceProblems(form, data).find((entry) => entry.step === id) || null;
}

function lastAvailablePeriod(data) {
  const numbers = (data.period_labels || []).map((entry) => Number(entry.number)).filter((number) => !Number.isNaN(number));
  return numbers.length ? Math.max(...numbers) : null;
}

function childNameForForm() {
  const data = state.absence.data;
  const children = data.children || [];
  const found = children.find((child) => String(child.id) === String(state.absenceForm.student_id));
  return (found && found.name) || (children[0] && children[0].name) || t("absence.child.fallback");
}

function absencePayload(form, children) {
  const payload = Object.assign({}, form, {
    student_id: form.student_id || (children[0] ? children[0].id : ""),
    connection_id: (state.absence && state.absence.connectionId) || currentConnectionId(),
  });
  delete payload.attachments;
  delete payload.duration;
  delete payload.time_mode;
  delete payload.subject_auto;
  if (form.repeat !== "weekly") payload.repeat_until = "";
  if (form.type === "deregister") {
    payload.weekly = form.repeat === "weekly";
    delete payload.repeat;
  }
  return payload;
}

async function submitAbsence() {
  const form = state.absenceForm;
  const data = state.absence.data;
  const problem = absenceProblemEntry(form, data);
  if (problem) return problem.text;
  const attachments = form.attachments || [];
  const payload = absencePayload(form, data.children || []);
  try {
    const result = attachments.length
      ? await postFormData("api/absences", payload, attachments)
      : await postJson("api/absences", payload);
    if (result && result.ok) {
      closeAbsenceForm();
      state.absence = null;
      toast(apiMessage(result, "absence.submit.ok"));
      loadAbsences();
      return true;
    }
    toast(apiMessage(result, "absence.submit.rejected"), "bad");
    return t("absence.review.rejected");
  } catch (error) {
    toast(t("absence.submit.failed"), "bad");
    return t("absence.submit.failed");
  }
}

function settingsView() {
  const config = state.config || {};
  const view = el("div", {});
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
  if (moduleOn("timetable")) {
    rows.push(periodsSettingRow(id, config));
    rows.push(settingRow(t("settings.names"), "", openNamesPage, "names-setting", SETTINGS_PAGE_NAMES));
    rows.push(...courseSettingRows(id));
  }
  rows.push(settingRow(t("settings.phones"), t("settings.phones.count", { count: formatNumber((config.phones || []).filter((p) => p.number).length) }), () => openSheet(phonesSheet)));
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
  if (state.haStatus === null && !state.haStatusLoading) loadHaStatus();
  if (!state.calendar) autoLoad("calendarSettings", loadSettingsCalendar);
  return settingsSection("settings.section.notifications", false, [
    settingRow(t("settings.notify.service"), notifyServicesSummaryLabel(config.notify_services), () => openSheet(notifySheet), "notify-setting"),
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
  return state.modules.unsupported.map(catalogueModuleName)
    .concat(state.modules.unknown.map((entry) => entry.label || entry.segment));
}

function moduleEntries() {
  return state.modules.unsupported.concat(state.modules.unknown);
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

function moduleIssueUrl() {
  const segments = moduleSegments();
  const title = segments.length ? t("help.issue.title", { segments: segments.join(", ") }) : t("help.issue.titlePlain");
  const params = new URLSearchParams({ title, body: helpIssueBody() });
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
  if (!moduleEntries().length) return null;
  if (unreportedModuleEntries().length) return el("div", { class: "modules-help-block" }, [moduleCard(false)]);
  return el("div", { class: "modules-help-block" }, [
    el("p", { class: "cal-hint modules-unknown" }, t("settings.modules.unknown", { labels: unknownModuleLabels().join(", ") })),
    el("button", { class: "btn ghost slim modules-report", type: "button", onclick: openHelpPage }, [icon("info", 16), t("settings.modules.report")]),
  ]);
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
    ? t("help.issue.versions", { app: facts.app || "?", home_assistant: facts.home_assistant || "?", iserv: facts.iserv || "?" })
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
  const saveButton = el("button", { class: "btn help-save", type: "button", onclick: saveHelpReport }, [icon("download", 18), t(preparing ? "help.preparing" : "help.save")]);
  if (!ready || preparing) saveButton.disabled = true;
  const issueLink = el("a", { class: "btn ghost help-issue", href: moduleIssueUrl(), target: "_blank", rel: "noopener" }, [externalIcon(18), t("help.issue")]);
  issueLink.addEventListener("click", () => { rememberReportedModules(); });
  const copyButton = el("button", { class: "btn ghost slim help-copy", type: "button", onclick: copyHelpReport }, [icon("clip", 16), t("help.copy")]);
  if (!ready) copyButton.disabled = true;
  return el("div", { class: "help-page" }, [
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

async function recheckModules() {
  if (state.modulesRechecking) return;
  state.modulesRechecking = true;
  rerender();
  let result = null;
  try {
    result = await postJson("api/modules/recheck", { connection_id: editingConnectionId() });
  } catch (error) {
    result = null;
  }
  state.modulesRechecking = false;
  if (result && result.modules) state.modules = applyModules(result.modules);
  if (result === null) toast(t("app.error.service.text"), "bad");
  else toast(apiMessage(result, "api.modules.rechecked"), result.ok ? "good" : "bad");
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
  if (!result.ok) {
    toast(result.message || t("common.saveFailed"), "bad");
    rerender();
    return;
  }
  toast(result.message || t("api.courses.saved"), result.reloadFailed ? "bad" : "good");
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

async function saveLayout(patch) {
  if (!state.config) state.config = {};
  Object.assign(state.config, patch);
  rerender();
  try {
    await postJson("api/config", patch);
  } catch (error) {
    toast(t("common.saveFailed"), "bad");
  }
}

function blockTitle(key) {
  return t(`blocks.${key}.title`);
}

function blockExplain(key) {
  return t(`blocks.${key}.explain`);
}

function switchButton(checked, label, onclick) {
  return el("button", {
    class: "switch",
    type: "button",
    role: "switch",
    "aria-checked": String(!!checked),
    "aria-label": label,
    onclick,
  });
}

function orderButtons(name, canUp, canDown, onMove, key) {
  const arrow = (direction, enabled, label) => el("button", {
    class: "icon-btn",
    type: "button",
    "data-dir": direction < 0 ? "up" : "down",
    "aria-label": label,
    "aria-disabled": enabled ? null : "true",
    onclick: () => {
      if (enabled) onMove(direction);
    },
  }, [el("span", { class: direction < 0 ? "ico-slot chev-up" : "ico-slot", html: iconSvg("chevron", 18) })]);
  return el("div", { class: "order-btns", "data-order": key }, [
    arrow(-1, canUp, t("settings.order.up", { name })),
    arrow(1, canDown, t("settings.order.down", { name })),
  ]);
}

function liveAnnouncement() {
  return el("p", { class: "visually-hidden", "aria-live": "polite" }, state.layoutAnnouncement || "");
}

function announceMove(name, position) {
  state.layoutAnnouncement = t("settings.order.moved", { name, position: formatNumber(position) });
}

function sizeSegment(key, size, onPick) {
  const sizes = layoutBlocks().SIZES;
  return el("div", { class: "segment mini", role: "radiogroup", "aria-label": t("settings.blocks.size", { name: blockTitle(key) }) }, sizes.map((option) => el("button", {
    type: "button",
    role: "radio",
    "aria-checked": String(option === size),
    "aria-selected": String(option === size),
    onclick: () => onPick(option),
  }, [el("span", { class: "seg-label" }, t(`settings.blocks.size.${option}`))])));
}

function blockInfoSheet(key) {
  const block = layoutBlocks().blockOf(key);
  const facts = [
    [t("settings.blocks.info.module"), t(`settings.modules.name.${block.module}`)],
    [t("settings.blocks.info.when"), t(`blocks.${key}.when`)],
    [t("settings.blocks.info.compact"), t(`blocks.${key}.compact`)],
    [t("settings.blocks.info.normal"), t(`blocks.${key}.normal`)],
    [t("settings.blocks.info.target"), t(`blocks.${key}.target`)],
  ];
  return sheet(blockTitle(key), [
    el("p", { class: "cal-hint" }, blockExplain(key)),
    el("dl", { class: "block-facts" }, facts.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
  ]);
}

function moveOverviewBlock(key, direction) {
  const enabled = enabledOverviewBlocks();
  const keys = enabled.map((entry) => entry.key);
  const moved = layoutBlocks().moveKey(keys, key, direction);
  const bySize = new Map(enabled.map((entry) => [entry.key, entry.size]));
  announceMove(blockTitle(key), moved.indexOf(key) + 1);
  focusAfterRender(`.block-row[data-block="${key}"] .order-btns [data-dir="${direction < 0 ? "up" : "down"}"]`);
  saveLayout({ overview_blocks: moved.map((item) => ({ key: item, size: bySize.get(item) })) });
}

function setOverviewBlockSize(key, size) {
  const listed = enabledOverviewBlocks().map((entry) => (entry.key === key ? { key, size } : entry));
  saveLayout({ overview_blocks: listed });
}

function toggleOverviewBlock(key, on) {
  const enabled = enabledOverviewBlocks();
  const listed = on
    ? enabled.concat([{ key, size: layoutBlocks().blockOf(key).size }])
    : enabled.filter((entry) => entry.key !== key);
  focusAfterRender(`.block-row[data-block="${key}"] .switch`);
  saveLayout({ overview_blocks: listed });
}

function blockRow(key, entry, index, total) {
  const on = !!entry;
  const name = blockTitle(key);
  const row = el("div", { class: on ? "block-row" : "block-row off", "data-block": key }, [
    el("div", { class: "block-text" }, [
      el("div", { class: "block-name" }, [
        el("span", { class: "lbl" }, name),
        el("button", { class: "info-btn", type: "button", "aria-label": t("settings.blocks.info", { name }), onclick: () => openSheet(() => blockInfoSheet(key)) }, [icon("info", 18)]),
      ]),
      el("div", { class: "block-desc" }, blockExplain(key)),
    ]),
    switchButton(on, t("settings.blocks.show", { name }), () => toggleOverviewBlock(key, !on)),
    on ? el("div", { class: "block-tools" }, [
      sizeSegment(key, entry.size, (size) => setOverviewBlockSize(key, size)),
      orderButtons(name, index > 0, index < total - 1, (direction) => moveOverviewBlock(key, direction), key),
    ]) : null,
  ]);
  return row;
}

function blockSearchThreshold() {
  return layoutBlocks().BLOCK_SEARCH_FROM;
}

function blockMatchesQuery(key, query) {
  return blockTitle(key).toLowerCase().includes(query);
}

function blockGroupBody(list, query, emptyKey, renderRow) {
  if (list.length) return el("div", { class: "rows block-rows" }, list.map(renderRow));
  return el("p", { class: "cal-hint" }, query ? t("settings.blocks.search.empty") : t(emptyKey));
}

function overviewSettingsPage() {
  const enabled = enabledOverviewBlocks();
  const hidden = hiddenOverviewBlocks();
  const searchOn = enabled.length + hidden.length >= blockSearchThreshold();
  const shownBody = el("div", {});
  const hiddenBody = el("div", {});
  function renderGroups() {
    const query = searchOn ? (state.blocksSearch || "").trim().toLowerCase() : "";
    const filteredEnabled = query ? enabled.filter((entry) => blockMatchesQuery(entry.key, query)) : enabled;
    const filteredHidden = query ? hidden.filter((block) => blockMatchesQuery(block.key, query)) : hidden;
    shownBody.replaceChildren(blockGroupBody(filteredEnabled, query, "settings.blocks.none", (entry) => blockRow(entry.key, entry, enabled.indexOf(entry), enabled.length)));
    hiddenBody.replaceChildren(blockGroupBody(filteredHidden, query, "settings.blocks.hiddenNone", (block) => blockRow(block.key, null, 0, 0)));
  }
  renderGroups();
  const shown = el("section", { class: "settings-group" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.blocks.shown"))]),
    el("p", { class: "section-lead" }, t("settings.blocks.lead")),
    shownBody,
  ]);
  const rest = el("section", { class: "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.blocks.hidden"))]),
    el("p", { class: "section-lead" }, t("settings.blocks.hiddenLead")),
    hiddenBody,
  ]);
  const searchNode = searchOn
    ? searchField(state.blocksSearch, t("settings.blocks.search.placeholder"), (value) => {
        state.blocksSearch = value;
        renderGroups();
      })
    : null;
  return el("div", { class: "blocks-page" }, [
    searchNode,
    shown,
    rest,
    el("p", { class: "sheet-hint layout-foot" }, t("settings.blocks.foot")),
  ]);
}

function moveNavigationArea(area, direction) {
  const areas = navigationAreas();
  const moved = layoutBlocks().moveKey(areas, area, direction);
  const full = layoutBlocks().normalizeNavigation(state.config && state.config.navigation);
  const rest = full.filter((entry) => !areas.includes(entry));
  announceMove(areaLabel(area), moved.indexOf(area) + 2);
  focusAfterRender(`.nav-row[data-area="${area}"] .order-btns [data-dir="${direction < 0 ? "up" : "down"}"]`);
  saveLayout({ navigation: moved.concat(rest) });
}

function navigationModuleNames(area, label) {
  const names = (VIEW_MODULES[area] || []).filter(moduleOn).map((name) => t(`settings.modules.name.${name}`));
  const joined = names.join(" · ");
  return joined && joined !== label ? joined : "";
}

function navigationRow(area, index, total) {
  const item = VIEW_BY_KEY[area];
  const label = t(item.label);
  const sub = navigationModuleNames(area, label);
  const row = el("div", { class: "nav-row", "data-area": area, tabindex: "0" }, [
    el("span", { class: "pos" }, formatNumber(index + 2)),
    el("span", { class: "nav-ico" }, [icon(item.icon, 22)]),
    el("span", { class: "lbl" }, [label, sub ? el("small", {}, sub) : null]),
    orderButtons(label, index > 0, index < total - 1, (direction) => moveNavigationArea(area, direction), area),
  ]);
  row.addEventListener("keydown", (event) => {
    if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    const direction = event.key === "ArrowUp" ? -1 : 1;
    if ((direction < 0 && index === 0) || (direction > 0 && index === total - 1)) return;
    event.preventDefault();
    moveNavigationArea(area, direction);
  });
  return row;
}

function navigationBand(key, textKey) {
  return el("div", { class: "rows-band", "data-band": key }, [icon(key === "bar" ? "overview" : "more", 14), el("span", {}, t(textKey))]);
}

function navigationSettingsPage() {
  const areas = navigationAreas();
  const layout = navigationLayout();
  const rows = [];
  if (areas.length) {
    rows.push(navigationBand("bar", "settings.nav.band.bar"));
    rows.push(el("div", { class: "nav-row fixed", "data-area": "overview" }, [
      el("span", { class: "pos" }, formatNumber(1)),
      el("span", { class: "nav-ico" }, [icon("overview", 22), el("span", { class: "nav-lock" }, [icon("lock", 12)])]),
      el("span", { class: "lbl" }, t("nav.overview")),
      el("span", { class: "val" }, t("settings.nav.fixed")),
    ]));
    areas.forEach((area, index) => {
      if (layout.more.length && layout.more[0] === area) rows.push(navigationBand("more", "settings.nav.band.more"));
      rows.push(navigationRow(area, index, areas.length));
    });
  }
  const body = areas.length
    ? el("div", { class: "rows nav-rows" }, rows)
    : emptyBlock("overview", t("settings.nav.empty.title"), t("modules.empty.text"), modulesRecheckButton());
  return el("div", { class: "nav-page" }, [
    el("section", { class: "settings-group" }, [
      el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.nav.order"))]),
      el("p", { class: "section-lead" }, t("settings.nav.lead")),
      body,
    ]),
  ]);
}

function layoutPart(key, titleKey, first, body) {
  return el("section", { class: first ? "layout-part" : "layout-part spaced", "data-part": key }, [
    el("h2", { class: "layout-part-title" }, t(titleKey)),
    body,
  ]);
}

function layoutSettingsPage() {
  return el("div", { class: "layout-page app-layout-page" }, [
    layoutPart("overview", "settings.blocks.title", true, overviewSettingsPage()),
    layoutPart("navigation", "settings.nav.title", false, navigationSettingsPage()),
    liveAnnouncement(),
  ]);
}

function setModuleDisabled(name, off) {
  const listed = modulesDisabled().filter((entry) => entry !== name);
  if (off) listed.push(name);
  focusAfterRender(`.module-row[data-module="${name}"] .switch`);
  saveLayout({ modules_disabled: listed });
}

function moduleRow(name) {
  const label = t(`settings.modules.name.${name}`);
  return el("div", { class: "module-row switchable", "data-module": name }, [
    el("span", { class: "lbl" }, label),
    switchButton(!moduleDisabled(name), t("settings.modules.switch", { name: label }), () => setModuleDisabled(name, !moduleDisabled(name))),
  ]);
}

function overviewEmptyState() {
  return el("div", { class: "overview-empty" }, [
    emptyBlock("overview", t("blocks.overview.emptyTitle"), t("blocks.overview.emptyText"), el("button", {
      class: "btn ghost slim",
      type: "button",
      onclick: () => openSettingsPage(SETTINGS_PAGE_LAYOUT),
    }, t("settings.blocks.title"))),
  ]);
}

function modulesSection(everySchool) {
  const available = MODULE_NAMES.filter(moduleAvailable);
  const block = el("div", { class: "modules-block" });
  block.append(el("p", { class: "section-lead" }, t(everySchool ? "settings.modules.leadAll" : "settings.modules.lead")));
  if (available.length) block.append(el("div", { class: "module-rows" }, available.map(moduleRow)));
  else block.append(el("p", { class: "cal-hint modules-none" }, t("settings.modules.none")));
  if (!everySchool) block.append(el("div", { class: "cal-action-row" }, [modulesRecheckButton()]));
  const help = modulesHelpBlock();
  if (help) block.append(help);
  return el("section", { class: "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("settings.section.modules"))]),
    block,
  ]);
}

function noModulesView() {
  const help = modulesHelpBlock();
  return el("div", { class: "modules-empty" }, [
    emptyBlock("overview", t("modules.empty.title"), t("modules.empty.text")),
    help,
  ]);
}

const HA_INSTALL_URL = "https://my.home-assistant.io/redirect/hacs_repository/?owner=githuber110&repository=ranzenpost&category=integration";

async function loadHaStatus() {
  if (state.haStatusLoading) return;
  state.haStatusLoading = true;
  try {
    const data = await getJson("api/integration-status");
    state.haStatus = { data, error: false };
  } catch (error) {
    state.haStatus = { data: null, error: true };
  }
  state.haStatusLoading = false;
  rerender();
}

function haRowValue() {
  const loaded = state.haStatus && state.haStatus.data;
  if (!loaded) return "";
  return t(loaded.connected ? "settings.ha.status.connected" : "settings.ha.status.disconnected");
}

async function openHomeAssistantSheet() {
  state.haStatus = null;
  state.haBusy = false;
  openSheet(homeAssistantSheet);
  await loadHaStatus();
}

function homeAssistantSheet() {
  const body = [el("p", { class: "cal-hint" }, t("settings.ha.text"))];
  const loaded = state.haStatus;
  if (!loaded) body.push(loadingBlock());
  else if (loaded.error || !loaded.data) body.push(plainCard(t("settings.ha.loadFailed")));
  else {
    body.push(haStatusBlock(loaded.data));
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
  await loadHaStatus();
  toast(apiMessage(result, "api.integration.token.rotated"));
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
    const result = await postJson("api/account/disconnect", { connection_id: editingConnectionId() });
    if (result && (result.message_key || result.message)) message = apiMessage(result);
    good = !result || result.removed || !result.attempted;
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
    .filter((number) => Number.isInteger(number) && number > 0)
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
  toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
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
  rememberLanguageChoice(currentLanguageChoice(), !!result.ok);
  if (!result.ok) toast(result.message, "bad");
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
    toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
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
  let response;
  try {
    response = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    return { ok: false, message: t("common.saveFailed") };
  }
  if (!response.ok) {
    const body = await response.json().then((data) => data, () => ({}));
    return { ok: false, message: apiMessage(body, "common.saveFailed") };
  }
  state.timetable = null;
  state.overviewWeeks = {};
  state.absence = null;
  try {
    state.config = await getJson("api/config");
  } catch (error) {
    if (handleApiFailure(error)) return { ok: true };
    return { ok: true, message: t("settings.save.reloadFailed"), reloadFailed: true };
  }
  reloadTimetable();
  return { ok: true };
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

function openNamesPage() {
  state.namesPage = { connectionId: editingConnectionId(), schoolId: state.settingsSchoolId, saving: false };
  discardPageForm();
  openSettingsPage(SETTINGS_PAGE_NAMES);
}

function closeNamesPage() {
  const page = state.namesPage;
  state.namesPage = null;
  discardPageForm();
  state.settingsPage = null;
  dropSheet();
  if (page && page.schoolId && connectionOf(page.schoolId)) state.settingsSchoolId = page.schoolId;
  showSettingsChange();
}

function namesPageConnection() {
  return (state.namesPage && state.namesPage.connectionId) || editingConnectionId();
}

function namesPageView() {
  const config = connectionConfig(namesPageConnection());
  const draft = pageState(() => ({
    subjects: copy(config.subjects || {}),
    teachers: copy(config.teachers || {}),
  }));
  const saving = !!(state.namesPage && state.namesPage.saving);
  const save = el("button", {
    class: "btn names-save",
    type: "button",
    disabled: saving ? "disabled" : null,
    onclick: saveNamesPage,
  }, saving ? [el("span", { class: "spin" }), t("common.saving")] : t("common.save"));
  return el("div", { class: "names-page" }, [
    namesGroup("subjects", draft.subjects, (code) => subjectRow(code, draft.subjects[code])),
    namesGroup("teachers", draft.teachers, (code) => teacherRow(code, draft.teachers[code])),
    el("div", { class: "btn-stack names-actions" }, [save]),
  ]);
}

async function saveNamesPage() {
  const page = state.namesPage;
  const draft = state.pageForm;
  if (!page || !draft || page.saving) return;
  page.saving = true;
  rerender();
  const result = await persistConnection(page.connectionId, { subjects: draft.subjects, teachers: draft.teachers });
  page.saving = false;
  if (!result.ok) {
    toast(result.message || t("common.saveFailed"), "bad");
    return;
  }
  if (state.namesPage === page) closeNamesPage();
  toast(result.message || t("common.saved"), result.reloadFailed ? "bad" : "good");
}

function namesGroup(kind, entries, build) {
  const codes = sortedCodes(entries);
  const head = el("div", { class: "section-head names-head" }, [
    el("span", { class: "overline" }, t(`settings.${kind}`)),
    el("span", { class: "names-count" }, t(`settings.${kind}.count`, { count: formatNumber(codes.length) })),
  ]);
  const inner = codes.length
    ? el("div", { class: "field-group" }, codes.map(build))
    : el("p", { class: "dlg-text" }, t(`settings.${kind}.empty`));
  return el("div", { class: "names-block" }, [head, inner]);
}

function sortedCodes(entries) {
  return Object.keys(entries || {}).sort((a, b) => a.localeCompare(b, currentLanguage(), { numeric: true, sensitivity: "base" }));
}

function subjectRow(code, subject) {
  const swatch = el("button", { class: "swatch swatch-trigger", type: "button", "aria-label": t("settings.subjects.color", { code }) });
  const applySwatchColor = () => {
    const vars = RanzenpostColour.cellVars(subject.color || SUBJECT_COLOR_NAMES[hashIndex(code, SUBJECT_COLOR_NAMES.length)]);
    swatch.style.background = vars.fill;
  };
  applySwatchColor();
  swatch.addEventListener("click", () => openColorDialog(subject, applySwatchColor, subject.code || code));
  const input = iservText("input", { class: "inp", type: "text", value: subject.label || "", placeholder: code, "aria-label": t("settings.subjects.name", { code }) });
  input.addEventListener("input", () => { subject.label = input.value; });
  const codeInput = iservText("input", {
    class: "inp subject-code-input",
    type: "text",
    value: subject.code || code,
    placeholder: code,
    maxlength: "6",
    "aria-label": t("settings.subjects.code", { code }),
  });
  codeInput.addEventListener("input", () => {
    subject.code = codeInput.value.trim().toUpperCase();
    delete subject.derived;
  });
  const codeOpen = !!subject.code && subject.code !== code && !subject.derived;
  const codeField = el("label", { class: "field subject-code", hidden: codeOpen ? null : "hidden" }, [el("span", { class: "lbl" }, t("settings.names.code")), codeInput]);
  const fields = el("div", { class: codeOpen ? "subject-fields code-open" : "subject-fields" }, [
    el("label", { class: "field subject-name" }, [el("span", { class: "lbl" }, t("settings.names.name")), input]),
    codeField,
  ]);
  const codeToggle = el("button", {
    class: "link-btn subject-code-toggle",
    type: "button",
    hidden: codeOpen ? "hidden" : null,
    "aria-label": t("settings.names.codeChangeFor", { code }),
    onclick: () => {
      codeField.hidden = false;
      codeToggle.hidden = true;
      fields.classList.add("code-open");
      codeInput.focus();
    },
  }, t("settings.names.codeChange"));
  return el("div", { class: "cell" }, [
    el("div", { class: "cell-head" }, [swatch, iservText("span", { class: "field-label" }, code), codeToggle]),
    fields,
  ]);
}

function closeColorDialog() {
  const close = state.colorDialogClose;
  state.colorDialogClose = null;
  if (close) close();
}

function colourSwatch(name, selected, onPick) {
  const button = el("button", {
    class: "swatch-btn",
    type: "button",
    "data-color": name,
    "aria-label": t(`colour.${name}`),
    title: t(`colour.${name}`),
    "aria-pressed": String(selected),
    onclick: () => onPick(name),
  }, [icon("check", 18)]);
  button.style.background = `var(--subject-${name}-fill)`;
  button.style.color = `var(--subject-${name}-ink)`;
  return button;
}

function colourPreviewCell(code, tone) {
  const cell = el("div", { class: "tt-cell subject subject-bar colour-preview-cell" }, [iservText("span", { class: "sub" }, code)]);
  cell.style.setProperty("--subject-cell-fill", tone.fill);
  cell.style.setProperty("--subject-cell-ink", tone.ink);
  cell.style.setProperty("--subject-bar", tone.bar);
  return cell;
}

function colourPreview(code, value) {
  const colour = RanzenpostColour.resolve(value || RanzenpostColour.DEFAULT_NAME);
  return el("div", { class: "colour-preview" }, [
    el("div", { class: "colour-stage light" }, [colourPreviewCell(code, colour.light), el("span", { class: "colour-stage-label" }, t("settings.color.preview.light"))]),
    el("div", { class: "colour-stage dark" }, [colourPreviewCell(code, colour.dark), el("span", { class: "colour-stage-label" }, t("settings.color.preview.dark"))]),
  ]);
}

function openColorDialog(subject, onChange, code) {
  closeColorDialog();
  let close = () => {};
  const initialHex = RanzenpostColour.isHex(subject.color) ? subject.color.toLowerCase() : RanzenpostColour.resolve(subject.color || RanzenpostColour.DEFAULT_NAME).hex;
  const pickName = (name) => {
    subject.color = name;
    subject.color_source = COLOR_SOURCE_USER;
    onChange();
    close();
  };
  const swatches = SUBJECT_COLOR_NAMES.map((name) => colourSwatch(name, subject.color === name, pickName));
  swatches.push(
    el("button", {
      class: "swatch-btn auto",
      type: "button",
      "aria-label": t("settings.color.auto"),
      "aria-pressed": String(!subject.color),
      onclick: () => { subject.color = ""; subject.color_source = COLOR_SOURCE_AUTO; onChange(); close(); },
    }, [icon("restore", 16)])
  );
  const picker = el("input", { class: "colour-picker", type: "color", value: initialHex, "aria-label": t("settings.color.picker") });
  const hexField = el("input", {
    class: "inp colour-hex",
    type: "text",
    dir: "ltr",
    value: initialHex,
    maxlength: "7",
    autocomplete: "off",
    spellcheck: "false",
    inputmode: "text",
    "aria-label": t("settings.color.hex"),
    "aria-invalid": "false",
  });
  const ownChosen = RanzenpostColour.isHex(subject.color);
  const own = el("div", { class: "colour-own", id: "colour-own", "aria-pressed": String(ownChosen), hidden: ownChosen ? null : "hidden" });
  const ownToggle = el("button", {
    class: "link-btn colour-own-toggle",
    type: "button",
    "aria-expanded": String(ownChosen),
    "aria-controls": "colour-own",
    onclick: () => {
      const open = own.hidden;
      own.hidden = !open;
      ownToggle.setAttribute("aria-expanded", String(open));
    },
  }, t("settings.color.own"));
  let preview = colourPreview(code, subject.color);
  const applyHex = (hex) => {
    subject.color = hex;
    subject.color_source = COLOR_SOURCE_USER;
    onChange();
    own.setAttribute("aria-pressed", "true");
    for (const button of swatches) button.setAttribute("aria-pressed", "false");
    const next = colourPreview(code, hex);
    preview.replaceWith(next);
    preview = next;
  };
  picker.addEventListener("input", () => {
    const hex = RanzenpostColour.parseHex(picker.value);
    if (!hex) return;
    hexField.value = hex;
    hexField.setAttribute("aria-invalid", "false");
    applyHex(hex);
  });
  hexField.addEventListener("input", () => {
    const hex = RanzenpostColour.parseHex(hexField.value);
    hexField.setAttribute("aria-invalid", String(!hex));
    if (!hex) return;
    picker.value = hex;
    applyHex(hex);
  });
  hexField.addEventListener("blur", () => {
    const hex = RanzenpostColour.parseHex(hexField.value);
    if (hex) hexField.value = hex;
  });
  own.append(
    el("span", { class: "hint" }, t("settings.color.own.hint")),
    el("div", { class: "colour-own-fields" }, [picker, hexField]),
    preview
  );
  const dialog = el("div", { class: "sheet color-dialog", role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "sheet-head" }, [
      el("div", { class: "sheet-title", tabindex: "-1" }, t("settings.subjects.color", { code })),
      el("div", { class: "sheet-head-actions" }, [
        el("button", { class: "sheet-close", type: "button", "aria-label": t("common.close"), onclick: () => close() }, [icon("close", 16)]),
      ]),
    ]),
    el("div", { class: "sheet-body" }, [
      el("div", { class: "swatch-grid" }, swatches),
      ownToggle,
      own,
    ]),
  ]);
  dialog.addEventListener("click", (event) => event.stopPropagation());
  const scrim = el("div", { class: layoutMode() === "phone" ? "color-dialog-scrim" : "color-dialog-scrim dialog" });
  scrim.addEventListener("click", (event) => { event.stopPropagation(); close(); });
  const onKey = (event) => { if (event.key === "Escape") close(); };
  close = () => {
    scrim.remove();
    document.removeEventListener("keydown", onKey);
    state.colorDialogClose = null;
  };
  document.addEventListener("keydown", onKey);
  scrim.append(dialog);
  (root().querySelector(".scrim") || root()).append(scrim);
  state.colorDialogClose = close;
  window.setTimeout(() => {
    const heading = dialog.querySelector(".sheet-title");
    if (heading && document.contains(heading)) heading.focus();
  }, 0);
}

function teacherRow(code, teacher) {
  const input = iservText("input", { class: "inp", type: "text", value: teacher.label || "", placeholder: code, "aria-label": t("settings.teachers.name", { code }) });
  input.addEventListener("input", () => { teacher.label = input.value; teacher.label_source = ""; });
  return el("div", { class: "cell" }, [
    el("div", { class: "cell-head" }, [iservText("span", { class: "field-label" }, code)]),
    el("label", { class: "field teacher-name" }, [el("span", { class: "lbl" }, t("settings.names.person")), input]),
  ]);
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
    toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
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
  ["outage", "settings.notify.event.outage"],
];

function notifyEvents() {
  return NOTIFY_EVENTS.filter(([key]) => moduleOn(key));
}

const NOTIFY_CATEGORY_ORDER = ["mobile", "group", "other"];

const NOTIFY_CATEGORY_KEYS = {
  mobile: "settings.notify.push",
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
      const result = await postJson("api/password", { current: draft.current, new: draft.next, connection_id: editingConnectionId() });
      if (result && result.ok) {
        resetSheetForm();
        closeSheet();
        toast(apiMessage(result, "settings.password.done"));
        return;
      }
      toast(apiMessage(result, "settings.password.failed"), "bad");
    } catch (error) {
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

function troubledSchools() {
  return connections().filter((entry) => schoolTroubled(entry.id));
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
      : el("span", { class: "val" }, tCount("schools.children", schoolChildrenCount(id))),
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
  if (!data) return "";
  const port = String(calendarPort());
  return t(data.port_open ? "schools.calendar.portOpen" : "schools.calendar.portClosed", { port });
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
    const result = await postJson(`api/connections/${encodeURIComponent(id)}/disconnect`, {});
    if (result && (result.message_key || result.message)) message = apiMessage(result);
    good = !result || result.removed || !result.attempted;
  } catch (error) {
    good = false;
    message = t("settings.disconnect.failed");
  }
  toast(message, good ? "good" : "bad");
  state.settingsSchoolId = null;
  state.schoolModules = null;
  state.absence = null;
  state.overviewWeeks = {};
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
  for (const entry of connections()) {
    try {
      await postJson(`api/connections/${encodeURIComponent(entry.id)}/disconnect`, {});
    } catch (error) {
      good = false;
    }
  }
  toast(good ? t("settings.disconnect.done") : t("settings.disconnect.failed"), good ? "good" : "bad");
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
  toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
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

function stepper(label, value, onStep, canLower, canRaise, name) {
  return el("div", { class: `stepper ${name}` }, [
    el("button", { class: "sbtn", type: "button", "aria-label": t("periods.earlier", { minutes: formatNumber(PERIOD_STEP) }), disabled: canLower ? null : "disabled", onclick: () => onStep(-PERIOD_STEP) }, [icon("minus", 18)]),
    el("span", { class: "val", "aria-label": label }, value),
    el("button", { class: "sbtn", type: "button", "aria-label": t("periods.later", { minutes: formatNumber(PERIOD_STEP) }), disabled: canRaise ? null : "disabled", onclick: () => onStep(PERIOD_STEP) }, [icon("plus", 18)]),
  ]);
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
    days: [Math.min(6, Math.max(0, P.weekdayOf(day) || 0))],
    interval: ENTRY_INTERVAL_MIN,
    date: day < today ? today : day,
    from: day < today ? today : day,
    until: data.until_max,
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
    stepper(t("periods.field.start"), clockLabel(form.start), (delta) => { form.start += delta; form.note = ""; refit(); }, form.start - PERIOD_STEP >= found.minStart, found.max > PERIOD_STEP && form.start + 2 * PERIOD_STEP <= P.DAY_MINUTES, "entry-start"),
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
  return el("div", { class: "field entry-range" }, [
    el("div", { class: "two" }, [
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.from")), from]),
      el("label", {}, [el("span", { class: "flabel" }, t("periods.field.until")), until]),
    ]),
    el("span", { class: form.untilClamped ? "hint warn" : "hint" }, hint),
    el("label", { class: "check entry-holidays-check" }, [holidays, el("span", {}, [t("periods.holidays"), el("small", {}, t("periods.holidays.hint"))])]),
  ]);
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
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    const iso = isoDate(addDays(monday, day));
    const holiday = holidayDay(iso, school);
    const spans = blocked[day] ? [] : P.spansFor(rows, regular[iso] || []);
    for (const item of P.resolveDay(box.entries, spans, iso, child, !!(blocked[day] || (holiday && holiday.free)))) {
      if (item.state === P.STATE_HIDDEN) continue;
      if (blocked[day] && item.entry.type === P.TYPE_PAUSE) continue;
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
      style: `grid-column:2 / -1;grid-row:${line}`,
      "data-entry": shown.entry.id,
      onclick: () => openEntryDetail(school, shown.entry.id),
    }, [iservText("span", {}, [...names, durationLabel(shown.end - shown.start)].join(" · "))]),
  ];
}

function planOwnNodes(school, group, line, blocked) {
  const P = periodRules();
  const nodes = [el("div", { class: "tt-hour own", style: `grid-column:1;grid-row:${line}` }, [el("span", {}, clockLabel(group.start))])];
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
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

boot();
