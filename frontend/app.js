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
const LETTER_UNKNOWN_KEY = "api.letters.unknown";
const TIMETABLE_REFUSED_KEY = "api.timetable.refused";
const LETTERS_TAB_CURRENT = "current";
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024;

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
const { apiUrl, requestSignal, getJson, postJson, postFormData, getFile, requestJson, postJsonSafe } = requests;

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
  formatWeekdayLong,
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
const { createSelection } = window.RanzenpostSelection;

const VIEWS = [
  { key: "overview", label: "nav.overview", icon: "overview" },
  { key: "timetable", label: "nav.timetable", icon: "timetable" },
  { key: "absence", label: "nav.absence", icon: "absence" },
  { key: "post", label: "nav.post", icon: "inbox" },
  { key: "messenger", label: "nav.messenger", icon: "messages" },
  { key: "conferences", label: "nav.conferences", icon: "conferences" },
  { key: "calendar", label: "nav.calendar", icon: "upcoming" },
  { key: "tasks", label: "nav.tasks", icon: "tasks" },
  { key: "news", label: "nav.news", icon: "news" },
  { key: "mail", label: "nav.mail", icon: "letters" },
  { key: "files", label: "nav.files", icon: "folder" },
  { key: "contacts", label: "nav.contacts", icon: "conferences" },
  { key: "forums", label: "nav.forums", icon: "forums" },
  { key: "texts", label: "nav.texts", icon: "texts" },
  { key: "infodisplay", label: "nav.infodisplay", icon: "screen" },
  { key: "whiteboards", label: "nav.whiteboards", icon: "board" },
];
const VIEW_BY_KEY = Object.fromEntries(VIEWS.map((item) => [item.key, item]));
const MORE_VIEW = { key: "more", label: "nav.more", icon: "more" };

const ACCOUNT_MODULES = ["forums", "texts", "infodisplay", "whiteboards"];
const MODULE_NAMES = ["timetable", "letters", "pinboard", "absences", "conferences", "messenger", "calendar", "tasks", "news", ...ACCOUNT_MODULES];
const CONFIRMED_ONLY_MODULES = ["calendar", "tasks", "news", ...ACCOUNT_MODULES];
const VIEW_MODULES = {
  overview: [],
  timetable: ["timetable"],
  absence: ["absences"],
  post: ["letters", "pinboard"],
  messenger: ["messenger"],
  conferences: ["conferences"],
  calendar: ["calendar"],
  tasks: ["tasks"],
  news: ["news"],
  mail: ["mail"],
  files: ["file"],
  contacts: ["addressbook", "mailinglist"],
  forums: ["forums"],
  texts: ["texts"],
  infodisplay: ["infodisplay"],
  whiteboards: ["whiteboards"],
  settings: [],
};
const MODULE_ISSUE_URL = "https://github.com/githuber110/ranzenpost/issues/new";

function defaultModules() {
  const available = {};
  for (const name of MODULE_NAMES) available[name] = !CONFIRMED_ONLY_MODULES.includes(name);
  return { available, unsupported: [], unknown: [], checkedAt: 0, iservVersion: "" };
}

function webUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" && url.hostname ? url.href : "";
  } catch (error) {
    return "";
  }
}

function applyModules(payload) {
  const parsed = defaultModules();
  const data = payload && typeof payload === "object" ? payload : {};
  const flags = data.modules && typeof data.modules === "object" ? data.modules : {};
  for (const name of MODULE_NAMES) parsed.available[name] = CONFIRMED_ONLY_MODULES.includes(name) ? flags[name] === true : flags[name] !== false;
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
  if (name === "mail") return mailOffered();
  if (ACCOUNT_MODULE_NAMES.includes(name)) return accountModuleOffered(name);
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
  return layoutBlocks().offeredBlocks(moduleOn, surface, noChildren());
}

function enabledOverviewBlocks() {
  const raw = state.config && Array.isArray(state.config.overview_blocks) ? state.config.overview_blocks : null;
  return layoutBlocks().normalizeOverviewBlocks(raw, offeredBlocks("overview"), noChildren());
}

function hiddenOverviewBlocks() {
  return layoutBlocks().hiddenBlocks(enabledOverviewBlocks(), offeredBlocks("overview"));
}

function navigationAreas() {
  const raw = state.config && Array.isArray(state.config.navigation) ? state.config.navigation : null;
  return layoutBlocks().normalizeNavigation(raw).filter((area) => VIEW_BY_KEY[area] && viewAvailable(area));
}

function navigationLayout() {
  return layoutBlocks().barLayout(navigationAreas(), layoutBlocks().BAR_LIMIT);
}

function areaLabel(key) {
  return key === "overview" ? t("nav.overview") : t(VIEW_BY_KEY[key].label);
}

function anyModuleOn() {
  return MODULE_NAMES.some(moduleOn) || Object.values(VIEW_MODULES).some((names) => names.some(moduleOn));
}

const CHILD_VIEWS = ["timetable", "absence"];

function noChildren() {
  return state.childrenRead === true && !state.childrenFailure && !state.children.length;
}

function viewAvailable(key) {
  if (key === "settings") return true;
  if (noChildren() && CHILD_VIEWS.includes(key)) return false;
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
const PANE_VIEWS = ["post", "messenger", "absence", "mail"];
const PAGE_DETAILS = ["letter", "room", "mail"];
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
  if (state.view === "mail" && state.mailDetail && !state.mailCompose && !state.mailSettings) return { kind: "mail", entry: state.mailDetail.entry };
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
  if (kind === "mail") return mailKey(detail.entry) === id;
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
  unconfirmed: ["warn", "absence.status.unconfirmed"],
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
  childrenRead: false,
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
  absenceSchool: "",
  absenceForm: null,
  absenceFormDefault: null,
  absenceHistoryOpen: false,
  conferences: null,
  conferencesArchive: null,
  conferencesTab: "current",
  conferenceDetail: null,
  schoolEvents: null,
  tasks: null,
  tasksPastOpen: false,
  taskOpen: null,
  taskDetails: {},
  news: null,
  newsSearch: "",
  newsFilter: "",
  newsSections: {},
  newsDetailLoading: "",
  forums: null,
  forumsBusy: false,
  texts: null,
  textsSearch: "",
  textsFilter: "",
  infodisplay: null,
  whiteboards: null,
  mail: null,
  mailCountsError: null,
  mailAccount: null,
  mailSettings: null,
  mailSchool: "",
  mailFolders: null,
  mailFolder: "",
  mailList: null,
  mailDetail: null,
  mailFilter: {},
  mailSelectMode: false,
  mailSelected: [],
  mailBusy: false,
  mailCompose: null,
  mailComposeFiles: [],
  mailShowText: false,
  mailAddressesOpen: false,
  mailSpamUndo: null,
  accountModules: null,
  accountModulesError: null,
  filesSchool: "",
  filesPath: "",
  filesQuery: "",
  filesFilter: "",
  filesListing: null,
  filesTrail: [],
  filesRoot: "own",
  filesUpload: null,
  listDetail: null,
  listImport: null,
  composeLists: null,
  contactsSchool: "",
  contactsTab: "",
  contactsQuery: "",
  contactsPeople: null,
  mailingLists: null,
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
  sheetShown: false,
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
const stateStore = createStore(state, {
  reportError: (error) => (window.reportError ? window.reportError(error) : window.console.error(error)),
});

const OUTAGE_VIEWS = ["overview", "timetable", "absence", "post", "messenger", "conferences", "calendar", "tasks", "news", "mail", "files", "contacts", ...ACCOUNT_MODULES];
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
  const hasSelectBar = (state.view === "post" && (postSegmentIs("letters")
    ? state.lettersSelectMode
    : state.pinboardSelectMode)) || (state.view === "mail" && state.mailSelectMode && !state.mailCompose && !state.mailDetail);
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
  conferences: { conferencesTab: "current", conferenceDetail: null },
  calendar: {},
  tasks: { tasksPastOpen: false },
  news: { newsSearch: "", newsFilter: "" },
  mail: { mailSelectMode: false, mailSelected: [], mailFilter: {}, mailAddressesOpen: false, mailSpamUndo: null },
  files: { filesFilter: "" },
  contacts: {},
  forums: {},
  texts: { textsSearch: "", textsFilter: "" },
  infodisplay: {},
  whiteboards: {},
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
  const fresh = {};
  for (const key of Object.keys(defaults)) {
    const value = defaults[key];
    fresh[key] = Array.isArray(value) ? value.slice() : value;
  }
  stateStore.patch(fresh);
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
    state.mailDetail = null;
    state.mailSettings = null;
    closeMailCompose();
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

const selection = createSelection({
  slot: { read: (key) => stateStore.get(key), patch: (partial) => stateStore.patch(partial) },
  rerender: () => rerender(),
  vibrate: (ms) => {
    if (navigator.vibrate) navigator.vibrate(ms);
  },
  progress: () => stateStore.get("bulkProgress"),
  t: (...args) => t(...args),
  tCount: (...args) => tCount(...args),
  formatNumber: (value) => formatNumber(value),
  dom,
});
const { letters: letterSelection, pinboard: pinboardSelection } = selection;

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

function soleSchoolId() {
  const ready = readySchools();
  const pool = ready.length ? ready : connections();
  return pool.length === 1 ? pool[0].id : "";
}

function currentConnectionId() {
  const fromChild = connectionOfKey(state.childId);
  if (fromChild && connectionOf(fromChild)) return fromChild;
  const listed = state.children.map(schoolOfChild).find((id) => id && connectionOf(id));
  return listed || soleSchoolId();
}

function greetingSchoolId() {
  const first = readySchools()[0] || connections()[0];
  return currentConnectionId() || (first ? first.id : "");
}

function schoolChoiceSheet(ids, chosen, onChoose) {
  return sheet(t("schools.choose.title"), [
    el("div", { class: "opt-list school-choice" }, ids.map((id) => {
      const short = schoolShortName(id);
      const full = schoolFullName(id);
      const lines = [iservText("b", {}, full)];
      if (short && short !== full) lines.push(iservText("small", {}, short));
      return el("button", {
        class: "opt",
        type: "button",
        "aria-pressed": String(id === chosen),
        onclick: () => { dropSheet(); onChoose(id); },
      }, [el("span", {}, lines)]);
    })),
  ]);
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
  if (view === "conferences") return conferenceHeader();
  if (view === "calendar") return { text: t("schoolEvents.title") };
  if (view === "tasks") return { text: t("tasks.title") };
  if (view === "news") return { text: t("news.title") };
  if (ACCOUNT_MODULES.includes(view)) return { text: t(`${view}.title`) };
  if (view === "mail") {
    if (state.mailCompose) return { text: mailComposeTitle(), onBack: leaveMailCompose };
    if (state.mailSettings) return { text: mailSettingsTitle(), onBack: leaveMailSettings };
    if (state.mailDetail && !paneOpen()) return { text: mailDetailTitle(), onBack: leaveMailDetail };
    return { text: t("mail.title") };
  }
  if (view === "files") return filesHeader();
  if (view === "contacts") return { text: t("contacts.title") };
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
  if (view === "mail" && !state.mailCompose && !state.mailSettings && !(state.mailDetail && !paneOpen()) && mailSchools().length) actions.push(mailComposeButton());
  const areaAction = view === "files" ? filesUploadButton() : view === "contacts" ? listImportButton() : null;
  if (areaAction) actions.push(areaAction);
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
    if (key === layoutBlocks().MORE_KEY) {
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
  if (detail.kind === "mail") {
    return {
      title: mailDetailTitle(),
      extra: null,
      body: [mailDetailView()],
      foot: null,
      onClose: leaveMailDetail,
      chat: false,
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
  if (detail.kind === "news") return Object.assign({ onClose: closeDetail, chat: false }, newsDetailParts(detail.item));
  if (detail.kind === "task") return Object.assign({ onClose: closeDetail, chat: false }, taskDetailParts(detail.item));
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
  if (key === "mail") return mailUnreadTotal();
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

const START_SEGMENTS = ["letters", "pinboard"];

function startLinkParams() {
  const own = new URLSearchParams(window.location.search);
  if (own.has("view")) return own;
  try {
    return window.parent && window.parent !== window ? new URLSearchParams(window.parent.location.search) : own;
  } catch (error) {
    return own;
  }
}

function startLink() {
  const params = startLinkParams();
  const view = params.get("view");
  if (!view || !VIEW_BY_KEY[view] || !viewAvailable(view)) return null;
  const segment = params.get("segment");
  return { view, segment: view === "post" && START_SEGMENTS.includes(segment) ? segment : null };
}

function followStartLink(link) {
  if (!link || link.view === state.view) return;
  setView(link.view, link.segment ? { segment: link.segment } : undefined);
}

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
        applyTimetable(await loadTimetable());
      } catch (error) {
        if (handleApiFailure(error)) return;
        state.timetable = failedWeek(errorCode(error), error && error.body);
      }
    }
    render();
    loadRest();
    followStartLink(startLink());
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
    state.childrenRead = false;
    return;
  }
  const list = Array.isArray(answer) ? answer : [];
  state.childrenFailure = null;
  state.childrenRead = true;
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
  const greeting = greetingSchoolId();
  getJson(greeting ? `api/me?connection=${encodeURIComponent(greeting)}` : "api/me").then((data) => {
    state.me = data && !data.error ? data : {};
    writeCachedForename(state.me.forename || "");
    rerender();
  }).catch(routeOrIgnoreBackgroundFailure);
  loadNotifyServices();
  loadMailCounts();
  loadAccountModules();
  loadHolidays().then(rerender).catch(routeOrIgnoreBackgroundFailure);
  if (moduleOn("letters")) loadLetters("current");
  if (moduleOn("pinboard")) loadPinboard();
  if (moduleOn("conferences")) loadConferences();
  if (moduleOn("calendar")) loadSchoolEvents();
  if (moduleOn("tasks")) loadTasks();
  if (moduleOn("news")) loadNews();
  loadAccountLists();
  if (moduleOn("timetable")) {
    loadMarks();
    loadCancellations();
  }
  if (moduleOn("absences")) loadAbsences();
  if (moduleOn("messenger")) loadMessengerRooms();
}

const VISIBILITY_REFRESH_MS = 5 * 60 * 1000;
let lastVisibilityRefreshAt = Date.now();
let visibilityRefreshBound = false;

function hasOpenFormGuard() {
  return !!(state.sheet || state.detail || state.absenceForm || state.teacherRoom || state.letterDetail || state.mailCompose || state.mailDetail);
}

const VIEW_STALE_MS = 2 * 60 * 1000;

function activeViewLoadKeys() {
  switch (state.view) {
    case "post":
      return [postSegmentIs("letters") ? lettersLoadKey(state.lettersTab) : "pinboard"];
    case "messenger":
      return [MESSENGER_LOAD_KEY];
    case "conferences":
      return [conferencesLoadKey(state.conferencesTab)];
    case "calendar":
      return ["schoolEvents"];
    case "tasks":
      return ["tasks"];
    case "news":
      return ["news"];
    case "forums":
    case "texts":
    case "infodisplay":
    case "whiteboards":
      return [state.view];
    case "mail":
      return ["mailList"];
    case "files":
      return ["filesListing"];
    case "contacts":
      return ["mailingLists"];
    case "absence":
      return ["absence"];
    case "timetable":
      return ["timetable", "marks", "cancellations"];
    case "overview":
      return ["pinboard", lettersLoadKey(state.lettersTab), "marks", "cancellations", "absence", "conferences", "schoolEvents", "tasks", "news", ...ACCOUNT_MODULES, MESSENGER_LOAD_KEY];
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
  if (visibilityRefreshBound) return;
  visibilityRefreshBound = true;
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
        moduleOn("calendar") ? loadSchoolEvents() : null,
        moduleOn("tasks") ? loadTasks() : null,
        moduleOn("news") ? loadNews() : null,
        loadAccountLists(),
        loadMessengerRooms(),
        loadMailCounts(),
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
      await refreshConferencesView();
      break;
    case "calendar":
      await loadSchoolEvents();
      break;
    case "tasks":
      await loadTasks();
      break;
    case "news":
      await loadNews();
      break;
    case "forums":
      await loadForums();
      break;
    case "texts":
      await loadTexts();
      break;
    case "infodisplay":
      await loadInfodisplay();
      break;
    case "whiteboards":
      await loadWhiteboards();
      break;
    case "mail":
      await refreshMail();
      break;
    case "files":
      await Promise.all([loadAccountModules(), refreshFiles()]);
      break;
    case "contacts":
      await Promise.all([loadAccountModules(), refreshContacts()]);
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
  if (moduleOn("calendar")) jobs.push(loadSchoolEvents());
  if (moduleOn("tasks")) jobs.push(loadTasks());
  if (moduleOn("news")) jobs.push(loadNews());
  jobs.push(loadAccountLists());
  if (moduleOn("messenger")) jobs.push(loadMessengerRooms());
  if (state.messengerRoom) jobs.push(loadMessengerHistory());
  if (state.view === "mail") jobs.push(loadMailFolders(), loadMailList(false));
  jobs.push(loadMailCounts());
  jobs.push(loadAccountModules());
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

function viewFor(view) {
  if (!anyModuleOn() && view !== "settings") return noModulesView();
  switch (view) {
    case "timetable": return timetableView();
    case "absence": return absenceView();
    case "post": return state.letterDetail && !paneOpen() ? letterDetailView() : postView();
    case "messenger": return state.messengerRoom && !paneOpen() ? messengerRoomView() : messengerView();
    case "conferences": return conferencesView();
    case "calendar": return schoolEventsView();
    case "tasks": return tasksView();
    case "news": return newsView();
    case "forums": return forumsView();
    case "texts": return textsView();
    case "infodisplay": return infodisplayView();
    case "whiteboards": return whiteboardsView();
    case "mail": return state.mailCompose ? mailComposeView() : state.mailSettings ? mailSettingsView() : state.mailDetail && !paneOpen() ? mailDetailView() : mailView();
    case "files": return filesView();
    case "contacts": return contactsView();

    case "settings": return settingsPaneActive() ? settingsView() : state.helpPage ? helpPageView() : state.settingsPage ? settingsPageView() : state.settingsSchoolId && !paneOpen() ? schoolPageView() : settingsView();
    default: return overviewView();
  }
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

boot();
