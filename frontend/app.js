const CHILD_COLORS = ["#0e6b70", "#7a4b9c", "#b4602a", "#2f6b3a", "#9c3b5e", "#3a5a9c"];
const SUBJECT_COLORS = [
  "#84142a", "#f7703e", "#ec932f", "#7b791d", "#404f0e",
  "#2dae4b", "#208068", "#135859", "#31aed2", "#2486ed",
  "#372daa", "#834ac9", "#a639a3", "#7a1362",
];
const SUBJECT_COLOR_KEYS = [
  "settings.color.crimson", "settings.color.orange", "settings.color.amber",
  "settings.color.olive", "settings.color.moss", "settings.color.green",
  "settings.color.emerald", "settings.color.teal", "settings.color.sky",
  "settings.color.blue", "settings.color.indigo", "settings.color.violet",
  "settings.color.magenta", "settings.color.plum",
];
const COLOR_SOURCE_USER = "user";
const COLOR_SOURCE_AUTO = "auto";
const WEEK_MIN = 0;
const WEEK_MAX = 8;
const MS_PER_WEEK = 604800000;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 40 * 1024 * 1024;

const CALENDAR_COMPONENT_TIMETABLE = "timetable";
const CALENDAR_COMPONENT_SCHOOL_HOLIDAYS = "school_holidays";
const CALENDAR_COMPONENT_PUBLIC_HOLIDAYS = "public_holidays";
const CALENDAR_COMPONENT_MARKS = "marks";
const CALENDAR_COMPONENT_ABSENCES = "absences";
const CALENDAR_COMPONENTS = [
  CALENDAR_COMPONENT_TIMETABLE,
  CALENDAR_COMPONENT_SCHOOL_HOLIDAYS,
  CALENDAR_COMPONENT_PUBLIC_HOLIDAYS,
  CALENDAR_COMPONENT_MARKS,
  CALENDAR_COMPONENT_ABSENCES,
];
const CALENDAR_DEFAULT_COLOR = "#135859";
const CALENDAR_DEFAULT_PORT = 8100;
const CALENDAR_MAX_LABEL_LENGTH = 60;
const CALENDAR_HOST_KEY = "calendarHost";
const CALENDAR_SETUP_KEY = "calendarSetupSeen";
const CALENDAR_REMOTE_SUFFIX = ".ui.nabu.casa";
const CALENDAR_LOCAL_HOSTS = ["localhost", "127.0.0.1", "::1"];
const CALENDAR_SETUP_STEPS = 4;
const CALENDAR_SCHEME_WEB = "webcal";
const CALENDAR_SCHEME_PLAIN = "http";

const MARK_NAMES_KEY = "markNames";
const MARK_NAME_CHIPS = 4;
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

const BASE_LANGUAGE = "de";
const LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];
const LANGUAGE_CHOICES = ["system"].concat(LANGUAGES);
const RTL_LANGUAGES = ["ar"];
const PLACEHOLDER_PATTERN = /\{(\w+)\}/g;

const i18n = { choice: "system", language: BASE_LANGUAGE, messages: {}, base: {} };

function formatTemplate(text, vars) {
  if (!vars) return text;
  return text.replace(PLACEHOLDER_PATTERN, (match, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
  );
}

function t(key, vars) {
  const message = i18n.messages[key] || i18n.base[key];
  if (!message) return key;
  return formatTemplate(message, vars);
}

function hasMessage(key) {
  return !!(i18n.messages[key] || i18n.base[key]);
}

function pluralCategory(count) {
  try {
    return new Intl.PluralRules(i18n.language).select(count);
  } catch (error) {
    return count === 1 ? "one" : "other";
  }
}

function tCount(key, count, vars) {
  const candidate = `${key}.${pluralCategory(count)}`;
  const merged = Object.assign({ count: formatNumber(count) }, vars || {});
  return t(hasMessage(candidate) ? candidate : `${key}.other`, merged);
}

function setLanguageBundle(language, messages, base) {
  i18n.language = language;
  if (base) i18n.base = base;
  i18n.messages = messages || i18n.base;
}

function normalizeLanguage(value) {
  const tag = String(value || "").toLowerCase().split("-")[0];
  return LANGUAGES.includes(tag) ? tag : "";
}

function preferredLanguages() {
  const list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
  return [].concat(list).filter(Boolean);
}

function resolveLanguage(choice) {
  if (choice && choice !== "system") return normalizeLanguage(choice) || BASE_LANGUAGE;
  for (const tag of preferredLanguages()) {
    const match = normalizeLanguage(tag);
    if (match) return match;
  }
  return BASE_LANGUAGE;
}

function fetchBundle(language) {
  return getJson(`i18n/${encodeURIComponent(language)}.json`).then((data) =>
    data && typeof data === "object" && !Array.isArray(data) ? data : null
  );
}

function applyDocumentLanguage() {
  document.documentElement.setAttribute("lang", i18n.language);
  document.documentElement.setAttribute("dir", RTL_LANGUAGES.includes(i18n.language) ? "rtl" : "ltr");
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.getAttribute("data-i18n"));
  }
}

async function loadBaseLanguage() {
  if (Object.keys(i18n.base).length) return;
  try {
    const data = await fetchBundle(BASE_LANGUAGE);
    if (data) setLanguageBundle(BASE_LANGUAGE, data, data);
  } catch (error) {}
  applyDocumentLanguage();
}

async function applyLanguageChoice(choice) {
  i18n.choice = LANGUAGE_CHOICES.includes(choice) ? choice : "system";
  const language = resolveLanguage(i18n.choice);
  let messages = null;
  if (language !== BASE_LANGUAGE) {
    try {
      messages = await fetchBundle(language);
    } catch (error) {
      messages = null;
    }
  }
  setLanguageBundle(messages ? language : BASE_LANGUAGE, messages || i18n.base, i18n.base);
  applyDocumentLanguage();
}

function languageChoices() {
  return LANGUAGE_CHOICES.slice();
}

function currentLanguageChoice() {
  return i18n.choice;
}

function formatNumber(value) {
  try {
    return new Intl.NumberFormat(i18n.language).format(value);
  } catch (error) {
    return String(value);
  }
}

function dateFormatter(options) {
  try {
    return new Intl.DateTimeFormat(i18n.language, options);
  } catch (error) {
    return new Intl.DateTimeFormat(BASE_LANGUAGE, options);
  }
}

const VIEWS = [
  { key: "overview", label: "nav.overview", icon: "overview" },
  { key: "timetable", label: "nav.timetable", icon: "timetable" },
  { key: "absence", label: "nav.absence", icon: "absence" },
  { key: "letters", label: "nav.letters", icon: "letters" },
  { key: "pinboard", label: "nav.pinboard", icon: "pinboard" },
];

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

function apiMessage(result, fallbackKey) {
  if (result && result.message_key) return t(result.message_key, result.message_vars);
  if (result && result.message) return result.message;
  return fallbackKey ? t(fallbackKey) : "";
}

const state = {
  config: null,
  me: null,
  notifyServices: [],
  notifySupervisor: null,
  children: [],
  childId: null,
  view: "overview",
  sheet: null,
  toast: null,
  timetable: null,
  timetableAvailable: true,
  weekOffset: 0,
  marks: null,
  holidays: null,
  holidayRegions: null,
  holidaySuggestion: null,
  overviewWeeks: {},
  overviewChildId: null,
  _overviewAnchor: null,
  _overviewNow: true,
  pinboard: null,
  pinboardFolder: null,
  pinboardOnlyNew: false,
  pinboardSearch: "",
  pinboardSelectMode: false,
  pinboardSelected: [],
  letters: null,
  lettersTab: "current",
  lettersSelectMode: false,
  lettersSelected: [],
  lettersSearch: "",
  letterDetail: null,
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
  calendarSetupOpen: false,
  calendarQr: "",
  calendarHost: "",
  calendarBusy: "",
  loads: {},
  pending: {},
  refreshFailed: {},
  bulkProgress: null,
  sheetFocused: false,
  colorDialogClose: null,
  sheetFormDefault: null,
  sheetDiscardAsk: false,
  detached: false,
};

function documentBase() {
  const url = new URL(document.baseURI || window.location.href);
  url.search = "";
  url.hash = "";
  const path = url.pathname;
  const cut = path.lastIndexOf("/") + 1;
  const last = path.slice(cut);
  url.pathname = last.includes(".") ? path.slice(0, cut) : path.endsWith("/") ? path : `${path}/`;
  return url.toString();
}
const API_BASE = documentBase();
function apiUrl(path) {
  return new URL(path, API_BASE).toString();
}
const checkResponse = (r) => {
  if (!r.ok) throw new Error("http " + r.status);
  return r;
};
const API_ERROR = "ApiError";
const ERROR_NETWORK = "network";
const ERROR_AUTH_FAILED = "auth_failed";
const ERROR_NOT_CONFIGURED = "not_configured";

function apiError(code, body) {
  const failure = new Error(code || ERROR_NETWORK);
  failure.name = API_ERROR;
  failure.code = code || ERROR_NETWORK;
  failure.body = body || null;
  return failure;
}

function errorCode(error) {
  return error && error.name === API_ERROR && error.code ? error.code : ERROR_NETWORK;
}

const REQUEST_TIMEOUT_MS = 15000;
const UPLOAD_TIMEOUT_MS = 120000;
const BOOT_TIMEOUT_MS = 25000;

function requestSignal(timeout) {
  const factory = window.AbortSignal && window.AbortSignal.timeout;
  return factory ? window.AbortSignal.timeout(timeout) : undefined;
}

const raiseCarriedError = (data) => {
  if (data && data.error) throw apiError(data.error, data);
  return data;
};
const getJson = (path) =>
  fetch(apiUrl(path), { signal: requestSignal(REQUEST_TIMEOUT_MS) })
    .then(checkResponse)
    .then((r) => r.json())
    .then(raiseCarriedError);
const postJson = (path, body) =>
  fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: requestSignal(REQUEST_TIMEOUT_MS),
  })
    .then(checkResponse)
    .then((r) => r.json());
const postFormData = (path, body, files) => {
  const form = new FormData();
  form.append("data", JSON.stringify(body));
  for (const file of files) form.append("files", file);
  return fetch(apiUrl(path), { method: "POST", body: form, signal: requestSignal(UPLOAD_TIMEOUT_MS) })
    .then(checkResponse)
    .then((r) => r.json());
};

const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
};

const iservText = (tag, attrs, children) => el(tag, Object.assign({ dir: "auto" }, attrs || {}), children);

const ICON_SHAPES = {
  timetable: '<rect x="3.2" y="5.2" width="17.6" height="15.6" rx="3.6"/><path d="M8 2.9v4.4M16 2.9v4.4M3.2 10.4h17.6"/>',
  absence: '<path d="M14 14.3V5.4a2 2 0 0 0-4 0v8.9a3.9 3.9 0 1 0 4 0z"/><path d="M14 8.6h-2.3M14 11.4h-2.3"/>',
  overview: '<path d="M3.9 10.5 12 3.6l8.1 6.9v9.2a1.4 1.4 0 0 1-1.4 1.4H5.3a1.4 1.4 0 0 1-1.4-1.4z"/><path d="M9.4 21.1v-6.2h5.2v6.2"/>',
  letters: '<rect x="3.2" y="5.2" width="17.6" height="13.6" rx="3.6"/><path d="m4.4 7.8 6.7 4.6a1.6 1.6 0 0 0 1.8 0l6.7-4.6"/>',
  pinboard: '<path d="M9 3.4h6"/><path d="M10 3.4v6.3L7.1 14h9.8L14 9.7V3.4"/><path d="M12 14v6.6"/>',
  settings: '<circle cx="12" cy="12" r="3.1"/><circle cx="12" cy="12" r="7.3"/><path d="M12 2.8v1.9M12 19.3v1.9M21.2 12h-1.9M4.7 12H2.8M18.5 5.5l-1.3 1.3M6.8 17.2l-1.3 1.3M18.5 18.5l-1.3-1.3M6.8 6.8 5.5 5.5"/>',
  chevron: '<path d="m7.4 10.3 4.6 4.6 4.6-4.6"/>',
  today: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.3v5.1l3.3 1.9"/>',
  upcoming: '<rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3.4"/><path d="M8 3v4.4M16 3v4.4M3.4 10.4h17.2"/><path d="m8.7 15 2.3 2.3 4.3-4.3"/>',
  conferences: '<circle cx="9.2" cy="8.4" r="3.3"/><path d="M3.7 19.6a5.5 5.5 0 0 1 11 0"/><path d="M16.4 5.6a3.3 3.3 0 0 1 0 6.4"/><path d="M17.6 14.5a5.5 5.5 0 0 1 2.7 4.5"/>',
  clip: '<path d="M19.7 10.5 11 19.2a4.6 4.6 0 0 1-6.5-6.5l8.7-8.7a3.1 3.1 0 0 1 4.4 4.4l-8.7 8.7a1.5 1.5 0 0 1-2.2-2.2l8-8"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m5 12.6 4.6 4.6L19 7.4"/>',
  alert: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.6v5M12 15.8v.6"/>',
  phone: '<path d="M6.2 3.6h3.1l1.6 3.9-2 1.2a11 11 0 0 0 5 5l1.2-2 3.9 1.6v3.1a1.8 1.8 0 0 1-2 1.8A15.6 15.6 0 0 1 4.4 5.6a1.8 1.8 0 0 1 1.8-2z"/>',
  back: '<path d="M14.6 5.4 8 12l6.6 6.6"/>',
  folder: '<path d="M3.4 6.6a2 2 0 0 1 2-2h3.4l2 2.4h7.8a2 2 0 0 1 2 2v8.4a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2z"/>',
  trash: '<path d="M4.6 6.8h14.8M9.4 6.8V4.6h5.2v2.2M6.6 6.8l.9 12.2a1.6 1.6 0 0 0 1.6 1.5h5.8a1.6 1.6 0 0 0 1.6-1.5l.9-12.2"/>',
  archive: '<rect x="3.4" y="4.4" width="17.2" height="4.4" rx="1.6"/><path d="M5.2 8.8v9.2a2 2 0 0 0 2 2h9.6a2 2 0 0 0 2-2V8.8"/><path d="M10 12.6h4"/>',
  restore: '<path d="M4.4 10.6a8 8 0 1 1 .6 6"/><path d="M3.6 4.8v5.8h5.8"/>',
  inbox: '<path d="M3.4 13.2h4.2l1.4 2.6h6l1.4-2.6h4.2"/><path d="M5.4 4.6h13.2l2 8.6v4.4a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2v-4.4z"/>',
  plus: '<path d="M12 5.4v13.2M5.4 12h13.2"/>',
  info: '<circle cx="12" cy="12" r="8.4"/><path d="M12 8.1h.01"/><path d="M12 11.4v5"/>',
  search: '<circle cx="10.6" cy="10.6" r="6.6"/><path d="m20 20-4.8-4.8"/>',
  calendarAdd: '<rect x="3.4" y="5.4" width="17.2" height="15.2" rx="3.4"/><path d="M8 3v4.4M16 3v4.4M3.4 10.4h17.2"/><path d="M12 13.6v4.8M9.6 16h4.8"/>',
  exam: '<path d="M12 3.4 14.7 9l6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.9 9.3 9z" fill="currentColor" stroke-linejoin="round"/>',
  qr: '<rect x="3.6" y="3.6" width="6.6" height="6.6" rx="1.6"/><rect x="13.8" y="3.6" width="6.6" height="6.6" rx="1.6"/><rect x="3.6" y="13.8" width="6.6" height="6.6" rx="1.6"/><path d="M13.8 13.8h3v3h-3z"/><path d="M20.4 13.8v3M20.4 20.4h-3.6M13.8 20.4h.01"/>',
};

function iconSvg(name, size) {
  const shape = ICON_SHAPES[name];
  if (!shape) return "";
  const sized = size ? ` style="width:${size}px;height:${size}px"` : "";
  return `<svg class="ico" viewBox="0 0 24 24" stroke="currentColor" fill="none" aria-hidden="true"${sized}>${shape}</svg>`;
}

const icon = (name, size) => el("span", { class: "ico-slot", html: iconSvg(name, size) });

const pad2 = (value) => String(value).padStart(2, "0");
const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
const weekdayIndex = (date) => ((date.getDay() + 6) % 7) + 1;
const startOfWeek = (date) => addDays(date, 1 - weekdayIndex(date));
const isoDate = (date) => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
const formatDate = (date) => dateFormatter({ day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
const formatShortDate = (date) => dateFormatter({ day: "2-digit", month: "2-digit" }).format(date);
const formatTime = (date) => dateFormatter({ hour: "2-digit", minute: "2-digit" }).format(date);
const formatWeekdayShort = (date) => dateFormatter({ weekday: "short" }).format(date);
const formatDayNumber = (date) => dateFormatter({ day: "2-digit" }).format(date);
const formatWeekdayDay = (date) => dateFormatter({ weekday: "short", day: "2-digit", month: "2-digit" }).format(date);

function isoWeek(date) {
  const thursday = addDays(date, 4 - weekdayIndex(date));
  const jan4 = new Date(thursday.getFullYear(), 0, 4);
  const anchor = addDays(jan4, 4 - weekdayIndex(jan4));
  return 1 + Math.round((thursday.getTime() - anchor.getTime()) / MS_PER_WEEK);
}

function parseGermanDate(text) {
  const match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(String(text || "").trim());
  if (!match) return null;
  const date = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function parseAnyDate(text) {
  const value = String(text || "").trim();
  if (!value) return null;
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (iso) return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
  return parseGermanDate(value);
}

function showDate(text) {
  const date = parseAnyDate(text);
  return date ? formatDate(date) : String(text || "");
}

function parseGermanDateTime(text) {
  const match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/.exec(String(text || "").trim());
  if (!match) return null;
  const hasTime = match[4] !== undefined;
  const date = new Date(
    Number(match[3]),
    Number(match[2]) - 1,
    Number(match[1]),
    hasTime ? Number(match[4]) : 0,
    hasTime ? Number(match[5]) : 0
  );
  return Number.isNaN(date.getTime()) ? null : { date, hasTime };
}

function showDateTime(text) {
  const parsed = parseGermanDateTime(text);
  if (!parsed) return String(text || "");
  return parsed.hasTime ? `${formatDate(parsed.date)} ${formatTime(parsed.date)}` : formatDate(parsed.date);
}

function parseIsoDateTime(text) {
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(text || "").trim());
  if (!match) return null;
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
    Number(match[4]),
    Number(match[5])
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

function showTimestamp(text) {
  const date = parseIsoDateTime(text);
  if (date) return `${formatDate(date)} ${formatTime(date)}`;
  return showDateTime(text);
}

function hashIndex(text, length) {
  let sum = 0;
  for (const char of String(text || "")) sum = (sum * 31 + char.charCodeAt(0)) % 100003;
  return sum % length;
}

function childColor(childId) {
  const index = state.children.findIndex((c) => c.child_id === childId);
  return CHILD_COLORS[(index < 0 ? 0 : index) % CHILD_COLORS.length];
}

function subjectColor(lesson) {
  return lesson.color || SUBJECT_COLORS[hashIndex(lesson.subject_code || lesson.subject_label, SUBJECT_COLORS.length)];
}

const htmlParser = new DOMParser();

function stripHtml(html) {
  const text = String(html || "");
  if (!text) return "";
  const doc = htmlParser.parseFromString(text, "text/html");
  return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
}

const THEMES = ["light", "dark", "system"];

function readTheme() {
  try {
    const value = window.localStorage.getItem("theme");
    return THEMES.includes(value) ? value : "light";
  } catch (error) {
    return "light";
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

function sheetScrollTop() {
  const body = root().querySelector(".sheet-body");
  return body ? body.scrollTop : 0;
}

function restoreSheetScroll(offset) {
  if (!offset) return;
  const body = root().querySelector(".sheet-body");
  if (body) body.scrollTop = offset;
}

function render() {
  if (state.detached) return;
  const app = root();
  closeColorDialog();
  const keptSheetScroll = sheetScrollTop();
  if (state.absenceForm && absenceFlow) {
    const wizard = [absenceFlow.node];
    if (state.sheet) wizard.push(state.sheet());
    if (state.toast) wizard.push(toastNode());
    app.replaceChildren(...wizard);
    restoreSheetScroll(keptSheetScroll);
    return;
  }
  const hasSelectBar =
    (state.view === "letters" && state.lettersSelectMode) || (state.view === "pinboard" && state.pinboardSelectMode);
  const screen = el("div", { class: hasSelectBar ? "screen has-select-bar" : "screen" });
  screen.append(header(state.view));
  screen.append(el("div", { class: "wrap" }, [viewFor(state.view)]));
  screen.addEventListener("scroll", () => {
    const bar = screen.querySelector(".header");
    if (bar) bar.classList.toggle("scrolled", screen.scrollTop > 4);
  });
  setupPullToRefresh(screen);
  const nodes = [screen, tabbar()];
  if (state.sheet) nodes.push(state.sheet());
  if (state.toast) nodes.push(toastNode());
  app.replaceChildren(...nodes);
  restoreSheetScroll(keptSheetScroll);
  if (state._keepScroll) {
    screen.scrollTop = state._keepScroll;
    state._keepScroll = 0;
  }
  applyOverviewPagination();
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

const VIEW_ENTRY_RESETS = {
  letters: resetLettersEntryState,
  pinboard: resetPinboardEntryState,
};

function resetLettersEntryState() {
  state.lettersTab = "current";
  state.lettersSelectMode = false;
  state.lettersSelected = [];
  state.lettersSearch = "";
}

function resetPinboardEntryState() {
  state.pinboardSelectMode = false;
  state.pinboardSelected = [];
  state.pinboardSearch = "";
  state.pinboardOnlyNew = false;
  state.pinboardFolder = null;
}

function setView(name, options) {
  leaveAbsenceForm(() => {
    const changed = state.view !== name;
    const keepEntryState = !!(options && options.keepEntryState);
    state.view = name;
    state.sheet = null;
    state.onSheetClose = null;
    state.letterDetail = null;
    closeAbsenceForm();
    if (changed && !keepEntryState && VIEW_ENTRY_RESETS[name]) VIEW_ENTRY_RESETS[name]();
    if (changed && name === "overview") {
      state._overviewAnchor = null;
      state._overviewNow = true;
    }
    render();
  });
}

function openSheet(factory) {
  state.sheet = factory;
  state.sheetFocused = false;
  rerender();
}

function discardSheet() {
  const after = state.onSheetClose;
  state.sheet = null;
  state.onSheetClose = null;
  state.sheetForm = null;
  state.sheetFormDefault = null;
  state.sheetDiscardAsk = false;
  if (after) return after();
  rerender();
}

function isSheetFormDirty() {
  if (!state.sheetForm || !state.sheetFormDefault) return false;
  return JSON.stringify(state.sheetForm) !== JSON.stringify(state.sheetFormDefault);
}

function closeSheet() {
  if (isSheetFormDirty()) {
    state.sheetDiscardAsk = true;
    return rerender();
  }
  return discardSheet();
}

function sheetDiscardPanel() {
  return el("div", {
    class: "sheet-confirm",
    role: "alertdialog",
    "aria-modal": "true",
    "aria-label": t("sheet.discard.title"),
  }, [
    el("p", { class: "dlg-text" }, t("sheet.discard.text")),
    el("div", { class: "btn-stack" }, [
      el("button", { class: "btn destructive", type: "button", onclick: discardSheet }, t("sheet.discard.confirm")),
      el("button", { class: "btn ghost", type: "button", onclick: () => { state.sheetDiscardAsk = false; rerender(); } }, t("sheet.discard.keep")),
    ]),
  ]);
}

function sheetState(build) {
  if (!state.sheetForm) {
    state.sheetForm = build();
    state.sheetFormDefault = copy(state.sheetForm);
  }
  return state.sheetForm;
}

function copy(value) {
  return JSON.parse(JSON.stringify(value === undefined ? null : value));
}

function sheet(title, body, foot, headerExtra) {
  const panel = el("div", { class: "sheet", role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "sheet-head" }, [
      el("div", { class: "sheet-title", tabindex: "-1" }, title),
      el("div", { class: "sheet-head-actions" }, [
        headerExtra || null,
        el("button", { class: "sheet-close", type: "button", "aria-label": t("common.close"), onclick: closeSheet }, [icon("close", 16)]),
      ]),
    ]),
    el("div", { class: "sheet-body" }, body),
    foot ? el("div", { class: "sheet-foot" }, foot) : null,
  ]);
  if (state.sheetDiscardAsk) panel.append(sheetDiscardPanel());
  panel.addEventListener("click", (event) => event.stopPropagation());
  const scrim = el("div", { class: "scrim", onclick: closeSheet });
  scrim.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSheet();
  });
  scrim.append(panel);
  window.setTimeout(() => {
    if (state.sheetFocused) return;
    const heading = panel.querySelector(".sheet-title");
    if (!heading) return;
    heading.focus();
    state.sheetFocused = true;
  }, 0);
  return scrim;
}

let toastTimer = 0;

function toast(message, kind = "good") {
  window.clearTimeout(toastTimer);
  state.toast = { message, kind };
  toastTimer = window.setTimeout(() => {
    state.toast = null;
    rerender();
  }, 3200);
  rerender();
}

function toastNode() {
  return el("div", { class: `toast ${state.toast.kind}`, role: "status" }, [
    icon(state.toast.kind === "bad" ? "alert" : "check", 16),
    el("span", {}, state.toast.message),
  ]);
}

function confirmAction({ title, text, confirmLabel, destructive }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      state.sheet = null;
      state.onSheetClose = null;
      rerender();
      resolve(value);
    };
    state.onSheetClose = () => finish(false);
    const body = [];
    if (text) body.push(el("p", { class: "dlg-text" }, text));
    openSheet(() =>
      sheet(title, body, [
        el("div", { class: "btn-stack" }, [
          el("button", { class: destructive ? "btn destructive" : "btn", type: "button", onclick: () => finish(true) }, confirmLabel),
          el("button", { class: "btn ghost", type: "button", onclick: () => finish(false) }, t("common.cancel")),
        ]),
      ])
    );
  });
}

function currentChild() {
  return state.children.find((c) => c.child_id === state.childId) || state.children[0] || null;
}

function headerTitleFor(view) {
  const child = currentChild();
  const many = state.children.length > 1;
  if (view === "timetable") {
    if (child && many) return null;
    return { text: t("timetable.title") };
  }
  if (view === "absence") return { text: t("absence.title") };
  if (view === "letters") {
    if (state.letterDetail) {
      const { letter } = state.letterDetail;
      return {
        text: letter.title || t("letters.detail.title"),
        onBack: () => { state.letterDetail = null; rerender(); loadLetters(state.lettersTab); },
        extra: techDetailsButton(letterTechEntries(letter)),
      };
    }
    return { text: t("letters.title") };
  }
  if (view === "pinboard") return { text: t("pinboard.title") };
  if (view === "conferences") return { text: t("conferences.title"), onBack: () => setView("overview") };
  if (view === "settings") {
    return {
      text: t("settings.title"),
      onBack: () => setView(state.settingsReturn || "overview", { keepEntryState: true }),
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
  if (child && view === "timetable" && many) {
    const name = child.name || "";
    const className = child.class_name || "";
    const avatar = iservText("span", { class: "avatar" }, (name || "?").trim().charAt(0).toUpperCase());
    avatar.style.background = childColor(child.child_id);
    actions.push(
      el("button", {
        class: "child-switch",
        type: "button",
        "aria-label": t("child.switch"),
        onclick: () => openSheet(childSheet),
      }, [
        avatar,
        el("span", {}, [
          iservText("span", { class: "who" }, name),
          className ? iservText("span", { class: "cls" }, className) : null,
        ]),
        icon("chevron", 16),
      ])
    );
  }
  if (view === "timetable" && state.timetableAvailable) {
    actions.push(el("button", {
      class: "icon-btn",
      type: "button",
      "aria-label": t("calendar.subscribe.open"),
      onclick: openCalendarSheet,
    }, [icon("calendarAdd", 18)]));
  }
  if (view !== "settings") {
    actions.push(el("button", {
      class: "icon-btn",
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
  const name = c.name || "";
  const className = c.class_name || "";
  const avatar = iservText("span", { class: "avatar" }, (name || "?").trim().charAt(0).toUpperCase());
  avatar.style.background = childColor(c.child_id);
  const lines = [iservText("b", {}, name)];
  if (className) lines.push(iservText("small", {}, t("child.class", { name: className })));
  return el("div", { class: "opt", "aria-pressed": String(c.child_id === state.childId) }, [
    el("button", {
      class: "opt-main",
      type: "button",
      onclick: () => selectChild(c.child_id),
    }, [avatar, el("span", {}, lines)]),
    techDetailsButton(childTechEntries(c)),
  ]);
}

function childSheet() {
  const options = state.children.map(childOption);
  return sheet(t("child.sheet"), [el("div", { class: "opt-list" }, options)]);
}

async function selectChild(childId) {
  state.sheet = null;
  if (childId === state.childId) return rerender();
  state.childId = childId;
  state.timetable = null;
  rerender();
  await reloadTimetable();
}

function tabbar() {
  const bar = el("nav", { class: "tabbar", "aria-label": t("nav.aria") });
  const items = state.timetableAvailable ? VIEWS : VIEWS.filter((item) => item.key !== "timetable");
  for (const item of items) {
    const count = badgeCount(item.key);
    bar.append(
      el("button", {
        class: "tab",
        type: "button",
        "aria-current": (state.view === item.key || (item.key === "overview" && state.view === "conferences")) ? "page" : null,
        onclick: () => setView(item.key),
      }, [
        icon(item.icon, 22),
        el("span", {}, t(item.label)),
        count ? el("span", { class: "badge" }, badgeText(count)) : null,
      ])
    );
  }
  return bar;
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

function badgeCount(key) {
  if (key === "letters") {
    const data = state.letters;
    if (!data || data.error || data.tab !== "current") return 0;
    return (data.letters || []).filter((entry) => entry.unread || letterConfirmationOpen(entry)).length;
  }
  if (key === "pinboard") {
    const data = state.pinboard;
    if (!data || data.error) return 0;
    return (data.feed || []).filter((tile) => tile.unread).length;
  }
  return 0;
}

function loadingBlock() {
  return el("div", { class: "loading" }, t("common.loading"));
}

function emptyBlock(iconName, title, text, action) {
  return el("div", { class: "empty" }, [icon(iconName, 40), el("b", {}, title), el("p", {}, text), action || null]);
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

const VIEWABLE_EXTENSION_PATTERN = /\.(pdf|png|jpe?g|gif|webp|bmp|avif|heic|heif)$/i;
const VIEWABLE_TYPE_PATTERN = /^(application\/pdf|image\/(png|jpeg|gif|webp|bmp|avif|heic|heif))\b/i;
const OPAQUE_TYPES = ["", "application/octet-stream", "binary/octet-stream"];
const VIEWER_REVOKE_DELAY = 60000;
const DOWNLOAD_REVOKE_DELAY = 4000;

function fileIsViewable(filename, type) {
  const mime = String(type || "").split(";")[0].trim().toLowerCase();
  if (VIEWABLE_TYPE_PATTERN.test(mime)) return true;
  if (!OPAQUE_TYPES.includes(mime)) return false;
  return VIEWABLE_EXTENSION_PATTERN.test(filename || "");
}

function reserveViewerWindow() {
  try {
    return window.open("", "_blank") || null;
  } catch (error) {
    return null;
  }
}

function releaseViewerWindow(viewer) {
  if (!viewer) return;
  try {
    viewer.close();
  } catch (error) {
    return;
  }
}

function downloadBlob(objectUrl, filename) {
  const link = el("a", { href: objectUrl, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), DOWNLOAD_REVOKE_DELAY);
}

async function openAppFile(path, fallbackFilename) {
  const viewer = fileIsViewable(fallbackFilename, "") ? reserveViewerWindow() : null;
  let response;
  try {
    response = await fetch(apiUrl(path));
  } catch (error) {
    releaseViewerWindow(viewer);
    throw error;
  }
  if (!response.ok) {
    releaseViewerWindow(viewer);
    const failure = new Error("http " + response.status);
    failure.userMessage = await responseUserMessage(response);
    throw failure;
  }
  const filename = filenameFromDisposition(response.headers.get("content-disposition")) || fallbackFilename;
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  if (viewer && !viewer.closed && fileIsViewable(filename, blob.type)) {
    try {
      viewer.location.replace(objectUrl);
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), VIEWER_REVOKE_DELAY);
      return;
    } catch (error) {
      releaseViewerWindow(viewer);
      downloadBlob(objectUrl, filename);
      return;
    }
  }
  releaseViewerWindow(viewer);
  downloadBlob(objectUrl, filename);
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

function attachmentButton(file) {
  const filename = file.filename || t("common.attachment");
  const button = el(
    "button",
    { type: "button", class: "row read" },
    attachmentRowContent(filename)
  );
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    button.classList.add("disabled");
    try {
      await openAppFile(file.url, filename);
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
      button.classList.remove("disabled");
    }
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

function formatEpoch(value) {
  const n = Number(value);
  if (!n) return "";
  const date = new Date(n * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return dateFormatter({ dateStyle: "medium", timeStyle: "short" }).format(date);
}

function techValue(entry) {
  if (entry.kind === "bool") return entry.value ? t("common.yes") : t("common.no");
  if (entry.kind === "epoch") return formatEpoch(entry.value);
  return entry.value;
}

function techDetailsSheet(entries) {
  const rows = (entries || [])
    .filter((entry) => entry.value !== null && entry.value !== undefined && entry.value !== "")
    .map((entry) => [entry.label, techValue(entry)])
    .filter(([, value]) => value !== null && value !== undefined && value !== "");
  const body = [
    el("p", { class: "dlg-text" }, t("common.techDetails.text")),
    rows.length ? factList(rows) : el("p", { class: "dlg-text" }, t("common.techDetails.empty")),
  ];
  return sheet([icon("info", 16), el("span", {}, t("common.techDetails"))], body);
}

function openNestedSheet(factory) {
  const previous = state.sheet;
  const previousForm = state.sheetForm;
  if (!previous) return openSheet(factory);
  state.onSheetClose = () => {
    state.onSheetClose = null;
    state.sheet = previous;
    state.sheetForm = previousForm;
    state.sheetFocused = false;
    rerender();
  };
  state.sheet = factory;
  state.sheetFocused = false;
  return rerender();
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
    renderNotice(root(), t("app.error.service.title"), t("app.error.service.text"), true);
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
    if (!health.configured) return renderWizard(app, boot);
    if (health.connection === "auth_failed") return renderReconnect(app, health.username || "");
    if (health.connection === "network") {
      return renderNotice(app, t("app.error.unreachable.title"), t("app.error.unreachable.text"), true);
    }
    state.account = health.username || "";
    state.config = await getJson("api/config");
    state.children = await getJson("api/children");
    state.childId = Array.isArray(state.children) && state.children.length ? state.children[0].child_id : null;
    if (state.childId) {
      try {
        await loadTimetable();
      } catch (error) {
        if (handleApiFailure(error)) return;
        state.timetable = { lessons: [], error: errorCode(error) };
      }
    }
    try {
      const availability = await getJson("api/timetable-availability");
      state.timetableAvailable = !availability || availability.available !== false;
    } catch (error) {
      if (handleApiFailure(error)) return;
      state.timetableAvailable = true;
    }
    render();
    loadRest();
    setupVisibilityRefresh();
  } catch (error) {
    if (handleApiFailure(error)) return;
    renderNotice(app, t("app.error.service.title"), t("app.error.service.text"), true);
  }
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
  loadLetters("current");
  loadPinboard();
  loadConferences();
  loadMarks();
  loadAbsences();
}

const VISIBILITY_REFRESH_MS = 5 * 60 * 1000;
let lastVisibilityRefreshAt = Date.now();

function hasOpenFormGuard() {
  return !!(state.sheet || state.absenceForm || state.letterDetail);
}

function setupVisibilityRefresh() {
  const maybeRefresh = () => {
    if (document.hidden) return;
    if (hasOpenFormGuard()) return;
    if (Date.now() - lastVisibilityRefreshAt < VISIBILITY_REFRESH_MS) return;
    refreshActiveView();
  };
  document.addEventListener("visibilitychange", maybeRefresh);
  window.addEventListener("pageshow", maybeRefresh);
}

async function refreshActiveView() {
  lastVisibilityRefreshAt = Date.now();
  switch (state.view) {
    case "overview": {
      await Promise.all([
        ...state.children.map((child) => loadOverviewWeek(child.child_id, 0)),
        loadHolidays(),
        loadAbsences(),
        loadMarks(),
        loadLetters(state.lettersTab),
        loadPinboard(),
        loadConferences(),
      ]);
      rerender();
      break;
    }
    case "timetable":
      await Promise.all([loadHolidays(), loadMarks(), reloadTimetable()]);
      rerender();
      break;
    case "absence":
      await loadAbsences();
      break;
    case "letters":
      await loadLetters(state.lettersTab);
      break;
    case "pinboard":
      await loadPinboard();
      break;
    case "conferences":
      await loadConferences();
      break;
    default:
      rerender();
  }
}

const PULL_REFRESH_THRESHOLD = 70;
const PULL_REFRESH_MAX = 90;

function pullIndicator() {
  return el("div", { class: "pull-indicator" }, [el("span", { class: "spin" })]);
}

function setupPullToRefresh(screen) {
  let startY = 0;
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
  });

  screen.addEventListener("touchmove", (event) => {
    if (!tracking || refreshing) return;
    const dy = event.touches[0].clientY - startY;
    if (dy <= 0 || screen.scrollTop > 1) {
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
      Promise.resolve(refreshActiveView()).finally(() => {
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
      ]),
    ])
  );
}

function renderReconnect(app, username) {
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
      const result = await postJson("api/password/repair", { password: input.value });
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
  const wrap = el("div", { class: "wrap" }, [
    el("h1", { class: "page-title", style: "margin-top:28px" }, t("account.reconnect.title")),
    el("p", { class: "dlg-text" }, t("account.reconnect.text")),
    form,
    message,
    el("p", { class: "dlg-text", style: "margin-top:28px" }, t("account.reconnect.resetText")),
  ]);
  const runReset = async (panel, confirmButton) => {
    confirmButton.disabled = true;
    confirmButton.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.pleaseWait")));
    try {
      await postJson("api/wizard/reset", {});
    } catch (error) {
      panel.remove();
      message.textContent = t("account.reconnect.resetFailed");
      return;
    }
    renderWizard(app, boot);
  };
  const askReset = () => {
    if (wrap.querySelector(".sheet-confirm")) return;
    const confirmButton = el("button", { class: "btn destructive", type: "button" }, t("account.reconnect.reset"));
    const panel = el("div", {
      class: "sheet-confirm",
      role: "alertdialog",
      "aria-modal": "true",
      "aria-label": t("account.reconnect.reset"),
    }, [
      el("p", { class: "dlg-text" }, t("account.reconnect.resetNote")),
      el("div", { class: "btn-stack" }, [
        confirmButton,
        el("button", { class: "btn ghost", type: "button", onclick: () => panel.remove() }, t("common.cancel")),
      ]),
    ]);
    confirmButton.addEventListener("click", () => runReset(panel, confirmButton));
    wrap.append(panel);
  };
  wrap.append(el("button", { class: "btn ghost", type: "button", onclick: askReset }, t("account.reconnect.reset")));
  app.replaceChildren(el("div", { class: "screen" }, [wrap]));
}

async function loadTimetable() {
  state.timetable = await getJson(`api/timetable?child_id=${encodeURIComponent(state.childId)}&week=${state.weekOffset}`);
  state.config = await getJson("api/config");
}

function viewFor(view) {
  switch (view) {
    case "timetable": return timetableView();
    case "absence": return absenceView();
    case "letters": return state.letterDetail ? letterDetailView() : lettersView();
    case "pinboard": return pinboardView();
    case "conferences": return conferencesView();
    case "settings": return settingsView();
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
    () => getJson(`api/timetable?child_id=${encodeURIComponent(childId)}&week=${weekIdx}`),
    keep
  );
  if (!outcome) return;
  if (!state.overviewWeeks[childId]) state.overviewWeeks[childId] = {};
  if (outcome.data) state.overviewWeeks[childId][weekIdx] = outcome.data;
  else if (outcome.error) state.overviewWeeks[childId][weekIdx] = { lessons: [], error: outcome.error };
  if (state.view === "overview") rerender();
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
  return [{ child_id: state.childId }];
}

function overviewActiveChild() {
  const list = overviewChildList();
  return (
    list.find((child) => child.child_id === state.overviewChildId)
    || list.find((child) => child.child_id === state.childId)
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
  if (child && child.child_id && child.child_id !== state.childId) {
    state.childId = child.child_id;
    state.timetable = null;
    setView("timetable");
    reloadTimetable();
    return;
  }
  setView("timetable");
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
  return overviewBlock(key, el("div", { class: "card overview-failed" }, [
    el("p", { class: "dlg-text", style: "margin:0 0 12px" }, t("overview.partial.failed")),
    retryButton(run),
  ]));
}

function overviewListRow(title, sub, meta, unread, onclick) {
  return el("button", { class: unread ? "row" : "row read", type: "button", onclick }, [
    el("span", { class: "row-dot" }, unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
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
  return { area, title, link: link || null, meta: null, pills: null, bodyClass: "rows", blocks: [], loading: false, nowKey: null };
}

function overviewRest(chapter, key, text) {
  chapter.bodyClass = "panel-rest";
  chapter.blocks = [overviewRestBlock(key, text)];
  return chapter;
}

function overviewChildLabel(child) {
  const name = child.name || "";
  const className = child.class_name || "";
  if (name && className) return t("child.nameWithClass", { name, class: className });
  return name || className || t("child.sheet");
}

function overviewChildHasChange(child) {
  const week = overviewWeekData(child.child_id, 0);
  if (!week || week.error || !Array.isArray(week.lessons)) return false;
  return todayLessons(week, weekdayIndex(new Date())).some((lesson) => !!lesson.change_kind);
}

function overviewPills(activeId) {
  const bar = el("div", { class: "chipbar overview-pills" });
  const list = overviewChildList();
  if (!list.length || !list[0].child_id) {
    bar.append(el("span", { class: "chip chip-skeleton" }), el("span", { class: "chip chip-skeleton" }));
    return bar;
  }
  for (const child of list) {
    const active = child.child_id === activeId;
    const marked = !active && overviewChildHasChange(child);
    const label = overviewChildLabel(child);
    bar.append(el("button", {
      class: "chip",
      type: "button",
      "aria-pressed": String(active),
      onclick: () => overviewSelectChild(child.child_id),
    }, [
      iservText("span", {}, label),
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

function overviewDayEnd(schedule, groups) {
  for (let index = groups.length - 1; index >= 0; index -= 1) {
    const info = schedule.get(groups[index].period);
    if (!info) continue;
    const end = new Date(2000, 0, 1, Math.floor(info.end / 60), info.end % 60);
    return formatTime(end);
  }
  return "";
}

function todayChapter() {
  const chapter = overviewChapter("today", t("overview.today"), {
    label: t("overview.toTimetable"),
    onclick: overviewOpenTimetable,
  });
  const now = new Date();
  chapter.meta = formatWeekdayDay(now);
  if (!state.timetableAvailable) return overviewRest(chapter, "today:locked", t("overview.timetable.locked"));
  if (!state.children.length && !state.childId && !state.timetable) {
    return overviewRest(chapter, "today:nochild", t("overview.noChild"));
  }
  const child = overviewActiveChild();
  if (state.children.length !== 1) chapter.pills = { active: child.child_id };
  const week = overviewWeekData(child.child_id, 0);
  if (!week) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("today:loading")];
    chapter.loading = true;
    return chapter;
  }
  if (week.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("today:failed", () => loadOverviewWeek(child.child_id, 0))];
    return chapter;
  }
  if (!Array.isArray(week.lessons)) return overviewRest(chapter, "today:unreachable", t("overview.timetable.unreachable"));
  const index = weekdayIndex(now);
  const lessons = todayLessons(week, index);
  const holiday = holidayTodayCard(isoDate(now), lessons.length);
  if (holiday) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewBlock(`today:holiday:${child.child_id}`, holiday)];
    return chapter;
  }
  if (!lessons.length) return todayFreeChapter(chapter, child, isoDate(now));
  const times = periodTimes(week);
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const groups = groupTodayLessons(lessons);
  const brackets = overviewBrackets(groups);
  const { schedule, nowPeriod, nextPeriod } = currentPeriodStatus(groups.map((group) => group.period), minutesNow);
  const displayMinutes = lessons.map((lesson) => {
    const time = lesson.start_time || times[String(lesson.period)] || "";
    const parts = /^(\d{1,2}):(\d{2})/.exec(time);
    return parts ? Number(parts[1]) * 60 + Number(parts[2]) : -1;
  });
  const dayOver = displayMinutes.every((minutes) => minutes >= 0 && minutes + 45 < minutesNow);
  chapter.bodyClass = "rows flat";
  const todayIso = isoDate(now);
  for (const node of todayLeadingRows(child.child_id, todayIso)) {
    chapter.blocks.push(overviewBlock(node.key, node.node));
  }
  const firstLessonIndex = chapter.blocks.length;
  groups.forEach((group, position) => {
    const isNow = group.period === nowPeriod;
    const isNext = group.period === nextPeriod;
    const isPast = periodStatus(schedule, group.period, minutesNow) === "past";
    const nowLabel = isNow ? t("overview.now") : isNext ? t("overview.next") : null;
    const entries = group.lessons.map((lesson) => ({
      lesson,
      time: lesson.start_time || times[String(lesson.period)] || "",
      childId: child.child_id,
      mark: markAt(child.child_id, lessonIso(lesson), lesson.period),
    }));
    const node = entries.length > 1
      ? compactLessonPair(entries, isNow || isNext, nowLabel, isPast)
      : compactLesson(entries[0], isNow || isNext, nowLabel, isPast);
    if (isNow) node.setAttribute("aria-current", "true");
    const changed = group.lessons.some((lesson) => !!lesson.change_kind);
    chapter.blocks.push(overviewBlock(`${child.child_id}:${group.period}`, node, brackets[position], changed));
  });
  if (dayOver) {
    chapter.blocks.push(overviewBlock(
      `${child.child_id}:dayOver`,
      el("div", { class: "row row-note" }, [el("p", { class: "dlg-text", style: "margin:0" }, t("overview.dayOver"))])
    ));
  }
  const anchorPeriod = nowPeriod !== null ? nowPeriod : nextPeriod;
  if (anchorPeriod !== null && anchorPeriod !== undefined) chapter.nowKey = `${child.child_id}:${anchorPeriod}`;
  else chapter.nowKey = dayOver ? chapter.blocks[chapter.blocks.length - 1].key : chapter.blocks[firstLessonIndex].key;
  const end = overviewDayEnd(schedule, groups);
  if (end) chapter.link = { label: t("overview.head.until", { time: end }), onclick: overviewOpenTimetable };
  return chapter;
}

function todayFreeChapter(chapter, child, iso) {
  const leading = todayLeadingRows(child.child_id, iso);
  if (!leading.length) return overviewRest(chapter, "today:free", t("overview.noSchool"));
  chapter.bodyClass = "rows flat";
  chapter.blocks = leading.map((row) => overviewBlock(row.key, row.node));
  chapter.blocks.push(overviewBlock(
    `${child.child_id}:free`,
    el("div", { class: "row row-note" }, [el("p", { class: "dlg-text", style: "margin:0" }, t("overview.noSchool"))])
  ));
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

function lettersChapter() {
  const chapter = overviewChapter("letters", t("overview.chapter.letters"), {
    label: t("overview.viewAll"),
    onclick: () => setView("letters"),
  });
  const data = state.letters;
  if (!data) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("letters:loading")];
    chapter.loading = true;
    return chapter;
  }
  if (data.error) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("letters:failed", () => loadLetters("current"))];
    return chapter;
  }
  const unread = (data.letters || [])
    .filter((letter) => letter.unread || letterConfirmationOpen(letter))
    .slice(0, OVERVIEW_ENTRY_CAP);
  if (!unread.length) return overviewRest(chapter, "letters:none", t("overview.letters.none"));
  chapter.blocks = unread.map((letter) => overviewBlock(
    `letter:${letterKey(letter)}`,
    overviewListRow(
      letter.title || t("letters.untitled"),
      letter.sender || "",
      letter.published ? showDate(letter.published) : "",
      true,
      () => setView("letters")
    )
  ));
  chapter.blocks.push(overviewAllRow("letters:all", t("overview.all.letters"), () => setView("letters")));
  return chapter;
}

function overviewPostTitle(tile) {
  const preview = stripHtml(tile.text).slice(0, 140);
  if (tile.title && tile.title !== "...") return tile.title;
  return preview.split(". ")[0] || t("pinboard.post.fallback");
}

function pinboardChapter() {
  const chapter = overviewChapter("pinboard", t("overview.chapter.pinboard"), {
    label: t("overview.viewAll"),
    onclick: () => setView("pinboard"),
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
  const feed = data.feed || [];
  const unread = feed.filter((tile) => tile.unread);
  const seen = feed.filter((tile) => !tile.unread);
  const shown = unread.concat(seen).slice(0, OVERVIEW_ENTRY_CAP);
  if (!shown.length) return overviewRest(chapter, "pinboard:none", t("overview.pinboard.none"));
  chapter.blocks = shown.map((tile) => overviewBlock(
    `post:${tile.id}`,
    overviewListRow(overviewPostTitle(tile), tile.folder_title || "", "", !!tile.unread, () => setView("pinboard"))
  ));
  chapter.blocks.push(overviewAllRow("pinboard:all", t("overview.all.pinboard"), () => setView("pinboard")));
  return chapter;
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

function overviewUpcomingEntries(limitIso, todayIso) {
  const rows = [];
  const conferences = state.conferences;
  if (conferences && !conferences.error) {
    (conferences.items || []).forEach((item, index) => {
      const cells = overviewConferenceCells(item);
      if (!cells.length) return;
      const day = overviewConferenceDate(cells);
      if (day && (day < todayIso || day > limitIso)) return;
      rows.push({ key: `conference:${day || index}:${index}`, day, title: cells[0], sub: cells.slice(1, 4).join(" · "), view: "conferences" });
    });
  }
  const absence = state.absence && state.absence.data;
  if (absence) {
    for (const entry of absence.entries || []) {
      const from = entry.from_date || entry.till_date || "";
      const till = entry.till_date || entry.from_date || "";
      if (!till || till < todayIso) continue;
      if (from && from > limitIso) continue;
      const sub = [absenceChildName(entry), absenceDates(entry)].filter(Boolean).join(" · ");
      rows.push({ key: `absence:${entry.id}`, day: from, title: absenceEntryLabel(entry), sub, view: "absence" });
    }
  }
  rows.sort((left, right) => (left.day || "9999-12-31").localeCompare(right.day || "9999-12-31"));
  return rows.slice(0, OVERVIEW_ENTRY_CAP);
}

function upcomingChapter() {
  const chapter = overviewChapter("upcoming", t("overview.chapter.upcoming"), {
    label: t("overview.upcoming.report"),
    onclick: () => setView("absence"),
  });
  const conferences = state.conferences;
  const absence = state.absence;
  if (conferences === null || absence === null) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewLoadingBlock("upcoming:loading")];
    chapter.loading = true;
    return chapter;
  }
  const conferencesFailed = !!(conferences && conferences.error);
  const absenceFailed = !!(absence && absence.error);
  if (conferencesFailed && absenceFailed) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock("upcoming:failed", () => {
      loadConferences();
      loadAbsences();
    })];
    return chapter;
  }
  const now = new Date();
  const rows = overviewUpcomingEntries(isoDate(addDays(now, OVERVIEW_UPCOMING_DAYS)), isoDate(now));
  if (!rows.length && !conferencesFailed && !absenceFailed) {
    return overviewRest(chapter, "upcoming:none", t("overview.upcoming.none"));
  }
  if (conferencesFailed) chapter.blocks.push(overviewFailureBlock("upcoming:conferences", loadConferences));
  if (absenceFailed) chapter.blocks.push(overviewFailureBlock("upcoming:absence", loadAbsences));
  for (const row of rows) {
    chapter.blocks.push(overviewBlock(row.key, overviewListRow(row.title, row.sub, "", false, () => setView(row.view))));
  }
  chapter.blocks.push(overviewAllRow("upcoming:all", t("overview.all.upcoming"), () => setView("conferences")));
  return chapter;
}

function overviewChapters() {
  return [todayChapter(), lettersChapter(), pinboardChapter(), upcomingChapter()];
}

function overviewPanelHead(chapter, pageIndex, pageCount, panelIndex) {
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
  } else {
    head.append(el("span", { class: "panel-dot", "aria-hidden": "true" }));
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

function overviewPanelArrow(chapter, pageIndex, pageCount, nextTitle, changesAhead) {
  const last = pageIndex === pageCount - 1;
  if (last && !nextTitle) return null;
  const current = formatNumber(pageIndex + 2);
  const total = formatNumber(pageCount);
  const label = last
    ? t("overview.arrow.area", { area: nextTitle })
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
    last ? el("span", { class: "panel-arrow-name" }, nextTitle) : null,
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
    "data-page": String(pageIndex),
    "aria-label": label,
  });
  panel.dataset.blocks = chapter.blocks.map((block) => block.key).join(" ");
  panel.append(overviewPanelHead(chapter, pageIndex, pageCount, snap ? panelIndex : 0));
  if (chapter.pills) panel.append(overviewPills(chapter.pills.active));
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
  if (!(panelHeight > 0) || !overviewPortrait()) return null;
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
    const nextTitle = chapterIndex + 1 < chapters.length ? chapters[chapterIndex + 1].title : null;
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
  const today = chapters[0];
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
  for (const child of state.children) {
    if (!overviewWeekData(child.child_id, 0)) {
      autoLoad(`ovWeek:${child.child_id}:0`, () => loadOverviewWeek(child.child_id, 0));
    }
  }
  if (!state.absence) autoLoad("absence", loadAbsences);
  const chapters = overviewChapters();
  overviewModel = { chapters, plan: null, panelHeight: 0 };
  const container = el("div", { class: "overview", "data-snap": "off" });
  container.addEventListener("focusin", overviewFocusIn);
  overviewFlatten(container, chapters);
  return container;
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

function periodTimes(week) {
  return (week && week.period_times) || (state.config && state.config.period_times) || {};
}

function configuredPeriodTimes() {
  return (state.config && state.config.period_times) || {};
}

function periodStartMinutes(times, period) {
  const raw = times[String(period)];
  const parts = raw ? /^(\d{1,2}):(\d{2})/.exec(raw) : null;
  return parts ? Number(parts[1]) * 60 + Number(parts[2]) : null;
}

function buildPeriodSchedule() {
  const times = configuredPeriodTimes();
  const known = Object.keys(times)
    .map((raw) => ({ period: Number(raw), start: periodStartMinutes(times, Number(raw)) }))
    .filter((entry) => entry.start !== null)
    .sort((a, b) => a.start - b.start);
  const schedule = new Map();
  known.forEach((entry, i) => {
    const end = i + 1 < known.length ? known[i + 1].start : entry.start + 45;
    schedule.set(entry.period, { start: entry.start, end });
  });
  return schedule;
}

function periodStatus(schedule, period, minutesNow) {
  const info = schedule.get(period);
  if (!info) return "unknown";
  if (minutesNow >= info.start && minutesNow < info.end) return "now";
  if (minutesNow < info.start) return "future";
  return "past";
}

function currentPeriodStatus(periods, minutesNow) {
  const schedule = buildPeriodSchedule();
  const dayPeriods = [...new Set(periods)].sort((a, b) => a - b);
  let nowPeriod = null;
  let nextPeriod = null;
  let allPast = dayPeriods.length > 0;
  for (const period of dayPeriods) {
    const status = periodStatus(schedule, period, minutesNow);
    if (status !== "past") allPast = false;
    if (status === "now") nowPeriod = period;
    if (status === "future" && nextPeriod === null) nextPeriod = period;
  }
  return { schedule, nowPeriod, nextPeriod, dayOver: allPast };
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

function overviewToday() {
  const chapter = todayChapter();
  return overviewPanel(chapter, 0, 1, chapter.blocks, 0, null, false, 0);
}

function changeTag(kind) {
  if (!kind) return null;
  return el("span", { class: kind === "cancelled" ? "tag no" : "tag open" }, changeLabel(kind));
}

function rowClassNames(highlight, isPast) {
  return ["row", highlight ? "next" : "", isPast ? "past" : ""].filter(Boolean).join(" ");
}

function markTag(mark) {
  if (!mark) return null;
  return el("span", { class: "tag exam" }, [
    el("span", { class: "ico-slot", html: iconSvg("exam", 11) }),
    iservText("span", {}, markLabel(mark)),
  ]);
}

function compactLesson(entry, highlight, nowLabel, isPast) {
  const lesson = entry.lesson;
  const dot = el("span", { class: "row-dot" }, [el("i", {})]);
  dot.firstChild.style.background = subjectColor(lesson);
  const title = iservText("div", { class: "row-title" }, lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback"));
  if (lesson.change_kind === "cancelled") title.style.textDecoration = "line-through";
  const sub = [lesson.room ? t("timetable.room", { room: lesson.room }) : "", lesson.teacher_label || ""].filter(Boolean).join(" · ");
  const row = el("button", {
    class: rowClassNames(highlight, isPast),
    type: "button",
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId),
  }, [
    dot,
    el("div", { class: "row-main" }, [title, sub ? el("div", { class: "row-sub" }, sub) : null, markTag(entry.mark)]),
    el("div", { class: "row-side" }, [
      highlight && nowLabel ? el("span", { class: "row-now-label" }, nowLabel) : null,
      el("span", { class: "row-meta" }, entry.time || periodShort(lesson.period)),
      changeTag(lesson.change_kind),
    ]),
  ]);
  if (entry.mark) row.classList.add("marked");
  return row;
}

function compactLessonPairItem(entry) {
  const lesson = entry.lesson;
  const dot = el("span", { class: "row-dot" }, [el("i", {})]);
  dot.firstChild.style.background = subjectColor(lesson);
  const title = iservText("div", { class: "row-title" }, lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback"));
  if (lesson.change_kind === "cancelled") title.style.textDecoration = "line-through";
  const sub = [lesson.room ? t("timetable.room", { room: lesson.room }) : "", lesson.teacher_label || ""].filter(Boolean).join(" · ");
  const item = el("button", {
    class: "row-pair-item",
    type: "button",
    onclick: () => openLessonSheet(lesson, entry.time, entry.childId),
  }, [
    dot,
    el("div", { class: "row-main" }, [title, sub ? el("div", { class: "row-sub" }, sub) : null, markTag(entry.mark)]),
    changeTag(lesson.change_kind),
  ]);
  if (entry.mark) item.classList.add("marked");
  return item;
}

function compactLessonPair(entries, highlight, nowLabel, isPast) {
  const time = entries[0].time;
  const items = entries.map((entry) => compactLessonPairItem(entry));
  return el("div", { class: rowClassNames(highlight, isPast) }, [
    el("div", { class: "row-pair" }, items),
    el("div", { class: "row-side" }, [
      highlight && nowLabel ? el("span", { class: "row-now-label" }, nowLabel) : null,
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
const ISO_DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})/;

function parseIsoDay(value) {
  const match = ISO_DAY_PATTERN.exec(String(value || ""));
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null;
}

function holidayData() {
  const data = state.holidays;
  return data && data.status === HOLIDAY_STATUS_OK ? data : null;
}

function holidayDay(iso) {
  const data = holidayData();
  return (data && data.days && data.days[iso]) || null;
}

function holidayWeek(mondayIso) {
  const data = holidayData();
  if (!data || !Array.isArray(data.weeks)) return null;
  return data.weeks.find((week) => week.start === mondayIso) || null;
}

function holidayPeriod(periodId) {
  const data = holidayData();
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
  const region = holidayRegionLabel((state.config || {}).holiday_region);
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

function holidayTodayCard(iso, lessonCount) {
  const day = holidayDay(iso);
  if (!day || !day.free) return null;
  if (lessonCount && !day.overrides_lessons) return null;
  const name = holidayName(day);
  if (!name) return null;
  const date = parseIsoDay(iso);
  const detail = day.kind === HOLIDAY_KIND_PUBLIC
    ? t("holidays.day.public")
    : (date ? holidayResumeLabel(date, holidayPeriod(day.period_id)) : "");
  return el("div", { class: "card" }, [
    el("p", { class: "dlg-text", style: "margin:0" }, [el("b", { lang: holidayNameLang(day) }, name)]),
    detail ? el("p", { class: "dlg-text", style: "margin:4px 0 0" }, detail) : null,
  ]);
}

async function loadHolidays() {
  const monday = startOfWeek(new Date());
  const start = isoDate(addDays(monday, 7 * WEEK_MIN));
  const end = isoDate(addDays(monday, 7 * WEEK_MAX + HOLIDAY_WINDOW_TRAIL_DAYS));
  try {
    const data = await getJson(`api/holidays?start=${start}&end=${end}`);
    state.holidays = data && typeof data === "object" ? data : null;
  } catch (error) {
    state.holidays = null;
  }
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
    const data = await getJson("api/holidays/region-suggestion");
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
  if (!state.timetableAvailable) {
    view.append(emptyBlock("timetable", t("timetable.locked.title"), t("timetable.locked.text")));
    return view;
  }
  if (!state.children.length && !state.childId && !state.timetable) {
    view.append(plainCard(t("overview.noChild")));
    return view;
  }
  view.append(weekBar());
  const data = state.timetable;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  if (data.error || !Array.isArray(data.lessons)) {
    view.append(emptyBlock("alert", t("timetable.error.title"), t("timetable.error.text"), retryButton(() => { state.timetable = null; rerender(); reloadTimetable(); })));
    return view;
  }
  const monday = weekMonday();
  const fullWeek = holidayFullWeek(monday, data);
  view.append(timetableGrid(data));
  if (!fullWeek) {
    view.append(
      el("div", { class: "legend" }, [
        legendItem("var(--warn)", t("timetable.legend.changed"), true),
        legendSymbol("var(--danger)", t("timetable.legend.cancelled"), "×"),
      ])
    );
  }
  const stamp = timetableStamp(data, monday, !!fullWeek);
  if (stamp) view.append(stamp);
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
  if (shown && state.holidays && state.holidays.stale) parts.push(t("holidays.status.stale"));
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
  const outcome = await reload("timetable", () => loadTimetable(), keep);
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

function calendarHost() {
  return state.calendarHost || calendarDetectedHost();
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
  return !!(data && data.holiday_region);
}

function calendarFeedUrl(subscription, scheme) {
  const host = calendarHost();
  const path = (subscription && subscription.path) || "";
  if (!host || !path) return "";
  return `${scheme}://${host}:${calendarPort()}${path}`;
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

async function openCalendarSheet() {
  state.calendar = null;
  state.calendarDraft = null;
  state.calendarQr = "";
  state.calendarBusy = "";
  state.calendarHost = readStoredText(CALENDAR_HOST_KEY);
  state.calendarSetupOpen = readStoredText(CALENDAR_SETUP_KEY) !== "1";
  writeStoredText(CALENDAR_SETUP_KEY, "1");
  openSheet(calendarSheet);
  await loadCalendarSubscriptions();
  if (state.sheet === calendarSheet) rerender();
}

function calendarSheet() {
  const body = [noteBlock(t("calendar.subscribe.warning")), calendarSetupBlock()];
  body.push(el("p", { class: "cal-hint" }, t(calendarIsRemoteSession() ? "calendar.subscribe.reach.remote" : "calendar.subscribe.reach")));
  const loaded = state.calendar;
  if (!loaded) body.push(loadingBlock());
  else if (loaded.error || !loaded.data) body.push(plainCard(t("calendar.subscribe.loadFailed")));
  else {
    if ((loaded.data.subscriptions || []).length) body.push(calendarHostField());
    for (const node of calendarChildCards(loaded.data)) body.push(node);
  }
  return sheet(t("calendar.subscribe.title"), body);
}

function calendarSetupBlock() {
  const open = state.calendarSetupOpen;
  const wrap = el("div", { class: "cal-setup" });
  wrap.append(
    el("button", {
      class: "cal-setup-head",
      type: "button",
      "aria-expanded": String(open),
      onclick: () => { state.calendarSetupOpen = !state.calendarSetupOpen; rerender(); },
    }, [
      el("span", { class: "overline" }, t("calendar.subscribe.setup.title")),
      el("span", { class: `ico-slot chev-toggle${open ? " open" : ""}`, html: iconSvg("chevron", 16) }),
    ])
  );
  if (!open) return wrap;
  wrap.append(el("p", { class: "cal-hint" }, t("calendar.subscribe.setup.intro")));
  const steps = el("ol", { class: "cal-steps" });
  for (let step = 1; step <= CALENDAR_SETUP_STEPS; step += 1) {
    steps.append(el("li", {}, t(`calendar.subscribe.setup.step${step}`, { port: String(calendarPort()) })));
  }
  wrap.append(steps);
  return wrap;
}

function calendarChildCards(data) {
  const subscriptions = Array.isArray(data.subscriptions) ? data.subscriptions : [];
  if (!state.children.length) return [plainCard(t("overview.noChild"))];
  return state.children.map((child) => {
    const found = subscriptions.find((entry) => entry.child_id === child.child_id) || null;
    return calendarChildCard(child, found);
  });
}

function calendarChildCard(child, subscription) {
  const card = el("div", { class: "cal-card" });
  card.append(iservText("span", { class: "overline" }, t("calendar.subscribe.forChild", { name: child.name })));
  const draft = state.calendarDraft;
  if (draft && draft.childId === child.child_id) {
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

function calendarNewDraft(child) {
  return {
    id: "",
    childId: child.child_id,
    components: [calendarRegionSet() ? CALENDAR_COMPONENT_TIMETABLE : CALENDAR_COMPONENT_SCHOOL_HOLIDAYS],
    label: "",
    placeholder: child.class_name || "",
    color: CALENDAR_DEFAULT_COLOR,
    error: "",
    busy: false,
  };
}

function calendarEditDraft(subscription, child) {
  return {
    id: subscription.id,
    childId: subscription.child_id,
    components: (subscription.components || []).slice(),
    label: subscription.label || "",
    placeholder: (child && child.class_name) || "",
    color: subscription.color || CALENDAR_DEFAULT_COLOR,
    error: "",
    busy: false,
  };
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
    el("span", { class: "hint" }, t("calendar.subscribe.label.hint")),
  ]);
}

function calendarColorField(draft, refresh) {
  const swatches = SUBJECT_COLORS.map((color) => {
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
  wrap.append(el("div", { class: "field-group" }, CALENDAR_COMPONENTS.map((component) => calendarComponentRow(draft, component, refresh))));
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
  closeSheet();
  if (state.view !== "settings") state.settingsReturn = state.view;
  setView("settings");
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
    child_id: draft.childId,
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
}

function calendarSubscriptionBlock(subscription, child) {
  const nodes = [];
  const dot = el("span", { class: "cal-dot" });
  dot.style.background = subscription.color || CALENDAR_DEFAULT_COLOR;
  nodes.push(el("div", { class: "cal-name-row" }, [
    dot,
    el("b", { class: "cal-name" }, subscription.label || t("calendar.name.fallback")),
  ]));
  const parts = (subscription.components || []).map((component) =>
    el("span", { class: "tag" }, t(`calendar.subscribe.component.${component}`))
  );
  if (parts.length) nodes.push(el("div", { class: "cal-parts" }, parts));
  const host = calendarHost();
  if (!host) nodes.push(el("p", { class: "cal-hint" }, t("calendar.subscribe.host.missing")));
  else nodes.push(el("code", { class: "cal-url", dir: "ltr" }, calendarFeedUrl(subscription, CALENDAR_SCHEME_PLAIN)));
  for (const node of calendarActions(subscription, child)) nodes.push(node);
  return nodes;
}

function calendarHostField() {
  const input = el("input", {
    class: "inp",
    type: "text",
    value: calendarHost(),
    placeholder: t("calendar.subscribe.host.placeholder"),
    autocomplete: "off",
    spellcheck: "false",
    dir: "ltr",
    "aria-label": t("calendar.subscribe.host"),
  });
  input.addEventListener("input", () => {
    state.calendarHost = input.value.trim();
    writeStoredText(CALENDAR_HOST_KEY, state.calendarHost);
  });
  input.addEventListener("change", rerender);
  return el("label", { class: "field cal-host" }, [
    el("span", { class: "lbl" }, t("calendar.subscribe.host")),
    input,
    el("span", { class: "hint" }, t("calendar.subscribe.host.hint")),
  ]);
}

function calendarActions(subscription, child) {
  const nodes = [];
  const feedUrl = calendarFeedUrl(subscription, CALENDAR_SCHEME_WEB);
  const plainUrl = calendarFeedUrl(subscription, CALENDAR_SCHEME_PLAIN);
  const busy = !!state.calendarBusy;
  if (feedUrl) {
    nodes.push(el("a", { class: "btn cal-add", href: feedUrl, rel: "noreferrer" }, [
      icon("calendarAdd", 18),
      t("calendar.subscribe.add"),
    ]));
  }
  const row = el("div", { class: "cal-action-row" });
  row.append(calendarCopyButton(plainUrl));
  if (typeof qrMatrix === "function" && feedUrl) row.append(calendarQrButton(subscription));
  nodes.push(row);
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
  openSheet(calendarSheet);
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
  openSheet(calendarSheet);
  if (!ok) return;
  state.calendarQr = "";
  await runCalendarAction(
    calendarActionKey("revoke", subscription),
    () => calendarRequest(calendarSubscriptionPath(subscription), { method: "DELETE" }),
    "calendar.subscribe.delete.done"
  );
}

function timetableGrid(data) {
  const times = periodTimes(data);
  const monday = weekMonday();
  const todayIso = isoDate(new Date());
  const fullWeek = holidayFullWeek(monday, data);
  const blocked = [];
  for (let day = 0; day < HOLIDAY_SCHOOL_DAYS; day += 1) {
    blocked.push(!!fullWeek || holidayBlocksLessons(isoDate(addDays(monday, day))));
  }
  const grid = el("div", { class: "tt" });
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
  const byKey = new Map();
  for (const lesson of visible) {
    const key = `${lesson.day_of_week}:${lesson.period}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(lesson);
  }
  for (const period of rows) {
    grid.append(
      el("div", { class: "tt-hour", style: `grid-column:1;grid-row:${period + 1}` }, [
        el("b", {}, formatNumber(period)),
        times[String(period)] ? el("span", {}, times[String(period)]) : null,
      ])
    );
    for (let day = 1; day <= HOLIDAY_SCHOOL_DAYS; day += 1) {
      if (blocked[day - 1]) continue;
      const lessons = byKey.get(`${day}:${period}`) || [];
      const cell = lessons.length ? gridCell(lessons, times[String(period)] || "") : el("div", { class: "tt-cell free" });
      cell.style.gridColumn = String(day + 1);
      cell.style.gridRow = String(period + 1);
      grid.append(cell);
    }
  }
  for (const field of holidayRunFields(monday, blocked, maxPeriod)) grid.append(field);
  return grid;
}

function gridCell(lessons, time) {
  if (lessons.length === 1) return lessonCell(lessons[0], time, false);
  return el(
    "div",
    { class: "tt-stack" },
    lessons.map((lesson) => lessonCell(lesson, time, true))
  );
}

function lessonCell(lesson, time, compact) {
  const kind = lesson.change_kind;
  const mark = markOfLesson(lesson, state.childId);
  const base = kind === "cancelled" ? "tt-cell out" : kind ? "tt-cell subbed" : "tt-cell";
  const roomLabel = kind === "cancelled" ? t("timetable.change.cancelled") : kind === "changed" ? t("timetable.cell.substitute") : lesson.room;
  const cell = el("button", {
    class: compact ? `${base} chip` : base,
    type: "button",
    "aria-label": lessonAriaLabel(lesson, kind, mark),
    onclick: () => openLessonSheet(lesson, time, state.childId),
  }, [
    kind && kind !== "cancelled" ? el("span", { class: "bar" }) : null,
    iservText("span", { class: "sub" }, lesson.subject_code || lesson.subject_label || "?"),
    roomLabel ? el("span", { class: "room" }, roomLabel) : null,
    mark ? el("span", { class: "exam-flag", html: iconSvg("exam", 11) }) : null,
  ]);
  if (mark) cell.classList.add("marked");
  if (!kind) {
    const color = subjectColor(lesson);
    cell.style.background = `color-mix(in srgb, ${color} var(--subject-fill), var(--surface))`;
    cell.style.color = `color-mix(in srgb, ${color} var(--subject-ink), var(--ink))`;
    cell.classList.add("subject-bar");
    cell.style.setProperty("--subject-bar", color);
  }
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

function openLessonSheet(lesson, time, childId) {
  openSheet(() => lessonSheet(lesson, time, markChildOf(childId)));
}

function lessonSheet(lesson, time, childId) {
  const facts = [
    [t("timetable.field.subject"), lesson.subject_label || lesson.subject_code || t("common.none")],
    [t("timetable.fact.period"), lessonPeriodFact(lesson, time)],
    [t("timetable.field.room"), lesson.room || t("common.none")],
    [t("timetable.field.teacher"), lesson.teacher_label || lesson.teacher_code || t("common.none")],
  ];
  if (lesson.date) facts.splice(1, 0, [t("timetable.fact.day"), showDate(lesson.date)]);
  if (lesson.is_class_teacher) facts.push([t("timetable.fact.role"), t("timetable.fact.classTeacher")]);
  const mark = markOfLesson(lesson, childId);
  const body = [];
  const banner = changeBanner(lesson);
  if (banner) body.push(banner);
  if (mark) body.push(markPanel(mark, childId, lesson, time));
  const details = changeDetails(lesson);
  if (details) {
    body.push(el("div", { class: "section-head", style: "margin-top:16px" }, [el("span", { class: "overline" }, t("timetable.changes.title"))]));
    body.push(details);
    body.push(el("div", { class: "section-head", style: "margin-top:20px" }, [el("span", { class: "overline" }, t("timetable.lesson.section"))]));
  }
  body.push(factList(facts));
  const title = lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback");
  return sheet(title, body, lessonSheetFoot(mark, childId, lesson, time));
}

function lessonSheetFoot(mark, childId, lesson, time) {
  if (!markLessonAnchor(lesson, childId)) return null;
  if (!mark) return [markAddButton(childId, lesson, time)];
  const rename = el("button", { class: "btn ghost", type: "button", onclick: () => openMarkForm(childId, lesson, time, mark) }, t("marks.action.rename"));
  if (markNeedsCheck(mark)) return [rename];
  return [
    el("div", { class: "btn-stack" }, [
      rename,
      el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.action.remove")),
    ]),
  ];
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
    (entry) => entry.child_id === childId && entry.date === iso && Number(entry.period) === Number(period)
  ) || null;
}

function markLessonAnchor(lesson, childId) {
  const iso = lessonIso(lesson);
  if (!iso || !childId) return null;
  const period = Number(lesson.period);
  if (!Number.isInteger(period) || period <= 0) return null;
  const subject = lesson.subject_code || lesson.subject_label || "";
  return subject ? { child_id: childId, date: iso, period, subject_code: subject } : null;
}

function markOfLesson(lesson, childId) {
  return markAt(markChildOf(childId), lessonIso(lesson), lesson && lesson.period);
}

function markLabel(mark) {
  return (mark && mark.name) || t("marks.default");
}

function markSubjectLabel(mark) {
  const code = (mark && mark.subject_code) || "";
  const subjects = (state.config && state.config.subjects) || {};
  const stored = subjects[code];
  return (stored && stored.label) || code;
}

function markNeedsCheck(mark) {
  return !!(mark && MARK_CLARIFY_KEYS[mark.state]);
}

function marksOfDay(childId, iso) {
  return markList().filter((entry) => entry.child_id === childId && entry.date === iso);
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

function rememberMarkName(name) {
  const text = String(name || "").trim();
  if (!text) return;
  const next = [text].concat(markNameHistory().filter((value) => value !== text)).slice(0, MARK_NAME_CHIPS);
  writeStoredText(MARK_NAMES_KEY, JSON.stringify(next));
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
    if (lesson.change_kind === MARK_STATE_CANCELLED) return false;
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
      el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, lesson.start_time || periodShort(lesson.period))]),
    ]);
  });
  return sheet(t("marks.move.title"), [el("div", { class: "rows" }, rows)]);
}

function markRequest(path, options) {
  return fetch(apiUrl(path), options)
    .then((response) => response.json().catch(() => null).then((body) => ({ response, body })))
    .then(({ response, body }) => {
      if (response.ok) return { ok: true, data: body };
      return { ok: false, message: apiMessage(body, "marks.error.failed") };
    })
    .catch(() => ({ ok: false, message: t("marks.error.failed") }));
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
  state.sheetForm = null;
  state.sheetFormDefault = null;
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
  return el("div", { class: "mark-chips" }, [
    el("span", { class: "overline" }, t("marks.form.recent")),
    el("div", { class: "chip-row" }, names.map((name) => iservText("button", {
      class: "chip mark-chip",
      type: "button",
      onclick: () => {
        form.name = name;
        input.value = name;
        input.focus();
      },
    }, name))),
  ]);
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

function handleApiFailure(error) {
  const code = errorCode(error);
  if (code === ERROR_AUTH_FAILED) {
    state.sheet = null;
    state.detached = true;
    renderReconnect(root(), state.account);
    return true;
  }
  if (code === ERROR_NOT_CONFIGURED) {
    state.sheet = null;
    state.detached = true;
    renderWizard(root(), boot);
    return true;
  }
  return false;
}

async function reload(key, run, keepOnFailure) {
  const ticket = nextLoad(key);
  try {
    const data = await run();
    if (!isCurrentLoad(key, ticket)) return null;
    delete state.refreshFailed[key];
    return { data };
  } catch (error) {
    if (handleApiFailure(error)) return null;
    if (!isCurrentLoad(key, ticket)) return null;
    const code = errorCode(error);
    if (keepOnFailure) {
      state.refreshFailed[key] = code;
      return { kept: true };
    }
    delete state.refreshFailed[key];
    return { error: code };
  }
}

function refreshFailureNote(key) {
  if (!state.refreshFailed[key]) return null;
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

function lettersView() {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  head.append(
    el("div", { class: "segment", role: "tablist" }, [
      segmentButton(t("letters.tab.current"), state.lettersTab === "current", () => switchLetters("current")),
      segmentButton(t("letters.tab.archive"), state.lettersTab === "archive", () => switchLetters("archive")),
    ])
  );
  view.append(head);
  const data = state.letters;
  if (!data || data.tab !== state.lettersTab) {
    autoLoad(lettersLoadKey(state.lettersTab), () => loadLetters(state.lettersTab));
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(emptyBlock("alert", t("letters.error.title"), t("letters.error.text"), retryButton(() => { state.letters = null; rerender(); })));
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
  const hitCount = el("span", { class: "search-hits" });
  const rowsHost = el("div", {});
  function renderLetterRows() {
    const query = (state.lettersSearch || "").trim().toLowerCase();
    const filtered = query ? letters.filter((letter) => matchesLetterQuery(letter, query)) : letters;
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
  return `${letter.letter_id}:${letter.recipient_id}`;
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

async function bulkMarkLettersRead() {
  const keys = state.lettersSelected.slice();
  if (!keys.length) return;
  try {
    const result = await postJson("api/letters/seen", { keys });
    toast(result && result.read ? t("letters.toast.marked", { count: formatNumber(result.read) }) : t("letters.toast.nothingToMark"));
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
    const result = await postJson("api/letters/archive", { letter_id: letter.letter_id, recipient_id: letter.recipient_id });
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
    const result = await postJson("api/letters/restore", { letter_id: letter.letter_id, recipient_id: letter.recipient_id });
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
  if (!isArchive && letter.unread) {
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
    toast(result && result.read ? t("letters.toast.markedSingle") : t("letters.toast.nothingToMark"));
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

function segmentButton(text, selected, onclick) {
  return el("button", { type: "button", role: "tab", "aria-selected": String(selected), onclick }, text);
}

function switchLetters(tab) {
  if (tab === state.lettersTab) return;
  state.lettersTab = tab;
  state.letters = null;
  exitLetterSelectMode();
}

function letterRow(letter) {
  const key = letterKey(letter);
  const selectMode = state.lettersSelectMode;
  const selected = state.lettersSelected.includes(key);
  const sub = letter.sender || "";
  const swipe = { wasSwipe: false };
  const showChildTag = letter.child && state.children.length > 1;
  const confirmOpen = letterConfirmationOpen(letter);
  const tags = (letter.recipients || showChildTag || confirmOpen)
    ? el("div", { class: "row-tags" }, [
        confirmOpen ? el("span", { class: "tag confirm" }, t("letters.confirm.badge")) : null,
        letter.recipients ? el("span", { class: "tag" }, letter.recipients) : null,
        showChildTag ? el("span", { class: "tag soft" }, letter.child) : null,
      ])
    : null;
  const row = el("button", {
    class: `row${letter.unread ? "" : " read"}${selected ? " selected" : ""}`,
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
    toast(result && result.read ? t("letters.toast.marked", { count: formatNumber(result.read) }) : t("letters.toast.nothingToMark"));
  } catch (error) {
    toast(t("letters.toast.markFailed"), "bad");
  }
  state.letters = null;
  rerender();
}

function restoreUnreadMark(letter) {
  letter.unread = true;
  if (state.view === "letters") rerender();
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

async function openLetter(letter) {
  state.letterDetail = { letter, loading: true };
  state.sheet = null;
  if (letter.unread) markLetterSeen(letter);
  render();
  try {
    const detail = await getJson(
      `api/letters/detail?letter_id=${encodeURIComponent(letter.letter_id)}&recipient_id=${encodeURIComponent(letter.recipient_id)}`
    );
    state.letterDetail = { letter, detail };
  } catch (error) {
    if (handleApiFailure(error)) return;
    state.letterDetail = { letter, error: errorCode(error) };
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
  const meta = [letter.sender || "", letter.published ? showDate(letter.published) : "", letter.child || ""].filter(Boolean).join(" · ");
  if (meta) view.append(el("div", { class: "row-meta", style: "margin:0 0 20px" }, meta));
  if (loading) {
    view.append(loadingBlock());
    return view;
  }
  if (error || !detail) {
    view.append(emptyBlock("alert", t("letters.detail.errorTitle"), t("letters.detail.errorText"), retryButton(() => openLetter(letter))));
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
  return el("div", { class: "card confirm-card" }, [
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
    sendable
      ? el("button", { class: "btn confirm-action", type: "button", onclick: () => confirmLetterRead(letter) }, [
          icon("check", 18),
          t("letters.confirm.action"),
        ])
      : null,
  ]);
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

async function confirmLetterRead(letter) {
  const ok = await confirmAction({
    title: t("letters.confirm.sheetTitle"),
    text: t("letters.confirm.sheetText"),
    confirmLabel: t("letters.confirm.action"),
  });
  if (!ok) return;
  try {
    const result = await postJson("api/letters/confirm", {
      letter_id: letter.letter_id,
      recipient_id: letter.recipient_id,
    });
    if (result && result.ok) {
      applyLetterConfirmed(letter, result.confirmed_at || "");
      toast(t("letters.confirm.sent"), "good");
    } else {
      toast(apiMessage(result, "letters.confirm.failed"), "bad");
    }
  } catch (error) {
    if (handleApiFailure(error)) return;
    toast(t("letters.confirm.failed"), "bad");
  }
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
    const result = await postJson("api/letters/archive", { letter_id: letter.letter_id, recipient_id: letter.recipient_id });
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
    const result = await postJson("api/letters/restore", { letter_id: letter.letter_id, recipient_id: letter.recipient_id });
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

function pinboardView() {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  view.append(head);
  const data = state.pinboard;
  if (!data) {
    autoLoad("pinboard", loadPinboard);
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(emptyBlock("alert", t("pinboard.error.title"), t("pinboard.error.text"), retryButton(() => { state.pinboard = null; rerender(); })));
    return view;
  }
  const pinboardNote = refreshFailureNote("pinboard");
  if (pinboardNote) head.append(pinboardNote);
  const folders = data.folders || [];
  const unread = (data.feed || []).filter((tile) => tile.unread).length;
  const folder = state.pinboardFolder ? folders.find((f) => f.id === state.pinboardFolder) : null;
  head.append(
    el("div", { class: "chipbar" }, [
      el("button", { class: "chip", type: "button", "aria-pressed": String(!state.pinboardOnlyNew), onclick: () => setPinboardFilter(false) }, t("pinboard.filter.all")),
      el("button", { class: "chip", type: "button", "aria-pressed": String(state.pinboardOnlyNew), onclick: () => setPinboardFilter(true) }, [
        el("span", {}, t("pinboard.filter.new")),
        unread ? el("span", { class: "n" }, formatNumber(unread)) : null,
      ]),
      el("button", { class: "chip", type: "button", "aria-pressed": String(!!folder), onclick: () => openSheet(folderSheet) }, [
        icon("folder", 14),
        el("span", {}, t("pinboard.filter.folder")),
      ]),
    ])
  );
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
    keepSelectionVisible(state.pinboardSelected, tiles.map((tile) => tile.id));
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
  let tiles = folder ? (folder.columns || []).flatMap((column) => column.tiles || []) : (data.feed || []).slice();
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
  const ids = state.pinboardSelected.slice();
  if (!ids.length) return;
  try {
    await postJson("api/pinboard/seen", { tile_ids: ids, unseen });
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
      if (!moved) enterPinboardSelectMode(tile.id);
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
    .sort((a, b) => (a.title || "").localeCompare(b.title || "", i18n.language, { numeric: true, sensitivity: "base" }));
  const rows = sortedFolders.map((folder) =>
    el("div", { class: "opt", "aria-pressed": String(folder.id === state.pinboardFolder) }, [
      el("button", {
        class: "opt-main",
        type: "button",
        onclick: () => { state.pinboardFolder = folder.id; closeSheet(); },
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
    !insideFolder && tile.folder_title ? el("span", { class: "tag" }, tile.folder_title) : null,
    tile.column_title ? el("span", { class: "tag" }, tile.column_title) : null,
  ].filter(Boolean);
  const tags = tagNodes.length ? el("div", { class: "row-tags" }, tagNodes) : null;
  const selectMode = state.pinboardSelectMode;
  const selected = state.pinboardSelected.includes(tile.id);
  const row = el("button", {
    class: `${tile.unread ? "row" : "row read"}${selected ? " selected" : ""}`,
    type: "button",
    onclick: () => {
      if (selectMode) togglePinboardSelected(tile.id);
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

function openPost(tile) {
  markPostRead(tile);
  openSheet(() => {
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
    return sheet(tile.title && tile.title !== "..." ? tile.title : t("pinboard.post.title"), body, [foot], techDetailsButton(postTechEntries(tile)));
  });
}

async function togglePostRead(tile) {
  const target = !tile.unread;
  tile.unread = target;
  closeSheet();
  try {
    await postJson("api/pinboard/seen", { tile_ids: [tile.id], unseen: target });
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
    await postJson("api/pinboard/seen", { tile_ids: [tile.id] });
  } catch (error) {
    tile.unread = true;
    routeOrIgnoreBackgroundFailure(error);
    if (state.view === "pinboard") rerender();
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
    view.append(emptyBlock("alert", t("conferences.error.title"), t("conferences.error.text"), retryButton(() => { state.conferences = null; rerender(); loadConferences(); })));
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
  const keep = !!(state.absence && !state.absence.error);
  const outcome = await reload("absence", () => getJson("api/absences"), keep);
  if (!outcome) return;
  if (outcome.data) state.absence = { data: outcome.data };
  else if (outcome.error) state.absence = { error: outcome.error };
  rerender();
}

function absenceView() {
  const view = el("div", {});
  const box = state.absence;
  if (!box) {
    autoLoad("absence", loadAbsences);
    view.append(loadingBlock());
    return view;
  }
  if (box.error) {
    view.append(emptyBlock("alert", t("absence.error.title"), t("absence.error.text"), retryButton(() => { state.absence = null; rerender(); })));
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

function absenceChildName(entry) {
  const children = (state.absence && state.absence.data && state.absence.data.children) || [];
  if (children.length < 2) return "";
  const found = children.find((child) => String(child.id) === String(entry.student_id));
  return found ? found.name : "";
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

function formatWeekdayDate(value) {
  const date = parseAnyDate(value);
  return date ? dateFormatter({ weekday: "long", day: "2-digit", month: "2-digit" }).format(date) : "";
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
    class: "row read",
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
      await openAppFile(path, t("absence.sickNote.pdfFilename"));
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return el("div", { style: "margin-top:24px" }, [button, dutyHint ? noteBlock(dutyHint) : null]);
}

function openAbsenceSheet(entry) {
  openSheet(() => {
    const facts = [
      [t("absence.fact.kind"), absenceEntryLabel(entry)],
      [t("absence.fact.range"), absenceDates(entry) || t("common.none")],
    ];
    const who = absenceChildName(entry);
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
    return sheet(absenceEntryLabel(entry), body, [foot], techDetailsButton(absenceTechEntries(entry)));
  });
}

async function withdrawAbsence(entry) {
  const ok = await confirmAction({
    title: t("absence.withdraw.confirmTitle", { label: absenceEntryLabel(entry) }),
    text: t("absence.withdraw.text"),
    confirmLabel: t("absence.withdraw"),
    destructive: true,
  });
  if (!ok) return;
  state.sheet = null;
  state.absence = null;
  rerender();
  try {
    const result = await postJson("api/absences/delete", { type: entry.kind, id: entry.id, target: entry.target || "" });
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
  state.sheet = null;
  state.sheetForm = null;
  state.sheetFormDefault = null;
  state.absenceForm = form;
  state.absenceFormDefault = copy(form);
  absenceFlowStart();
  render();
}

function absenceChildLabel(child) {
  const name = child.name || "";
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
  if (children.length > 1) facts.push({ label: t("absence.fact.child"), value: childNameForForm(), step: "child" });
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
  view.append(settingsSection("settings.section.school", true, [
    settingRow(t("holidays.settings.title"), holidayRegionValueLabel(), () => openSheet(holidayRegionSheet)),
    settingRow(t("settings.phones"), t("settings.phones.count", { count: formatNumber((config.phones || []).filter((p) => p.number).length) }), () => openSheet(phonesSheet)),
    settingRow(t("settings.names"), "", () => openSheet(namesSheet)),
    settingRow(t("settings.periods.sheet"), periodTimesLabel(config), () => openSheet(periodSheet)),
  ]));

  view.append(settingsSection("settings.section.display", false, [
    settingRow(t("settings.language"), languageLabel(i18n.choice), () => openSheet(languageSheet)),
    settingRow(t("settings.theme"), themeLabel(state.theme), () => openSheet(themeSheet)),
  ]));

  view.append(settingsSection("settings.section.notifications", false, [
    settingRow(t("settings.notify.service"), notifyServicesSummaryLabel(config.notify_services), () => openSheet(notifySheet), "notify-setting"),
  ]));

  view.append(settingsSection("settings.section.account", false, [
    settingRow(t("settings.profile"), "", () => openSheet(() => techDetailsSheet(meTechEntries()))),
    settingRow(t("settings.password"), "", () => openSheet(passwordSheet)),
    settingRow(t("settings.disconnect"), "", disconnectAccount, "destructive"),
  ]));
  return view;
}

function settingsSection(labelKey, first, rows) {
  return el("section", { class: first ? "settings-group" : "settings-group spaced" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, t(labelKey))]),
    el("div", { class: "rows" }, rows),
  ]);
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
    const result = await postJson("api/account/disconnect", {});
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

function periodTimesLabel(config) {
  return tCount("settings.periods.count", Object.keys(config.period_times || {}).length);
}

function themeLabel(value) {
  return t(`settings.theme.${THEMES.includes(value) ? value : "light"}.label`);
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
  const code = (state.config || {}).holiday_region || "";
  if (!code) return t("holidays.settings.off");
  const name = holidayRegionLabel(code) || code;
  if (state.holidays && state.holidays.status === HOLIDAY_STATUS_UNKNOWN) {
    return t("holidays.settings.valueUnknown", { region: name });
  }
  return name;
}

function holidaySortedRegions(regions, suggestion) {
  const list = regions.slice().sort((a, b) =>
    holidayRegionOptionLabel(a).localeCompare(holidayRegionOptionLabel(b), i18n.language)
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
  const current = (state.config || {}).holiday_region || "";
  const regions = state.holidayRegions || [];
  const suggestion = current ? "" : holidaySuggestionCode();
  const rows = [holidayRegionOption({ code: "" }, current, suggestion)];
  for (const region of holidaySortedRegions(regions, suggestion)) {
    rows.push(holidayRegionOption(region, current, suggestion));
  }
  const body = [el("div", { class: "opt-list" }, rows)];
  if (!regions.length) body.push(loadingBlock());
  if (suggestion) body.push(el("p", { class: "sheet-hint" }, t("holidays.suggestion.confirm")));
  body.push(el("p", { class: "sheet-hint" }, t("holidays.settings.hint")));
  body.push(el("p", { class: "sheet-hint" }, t("holidays.source")));
  return sheet(t("holidays.settings.sheet"), body);
}

async function selectHolidayRegion(code) {
  const config = state.config || {};
  if ((config.holiday_region || "") === (code || "")) return;
  config.holiday_region = code || "";
  state.config = config;
  const result = await persistConfig();
  if (result.ok) await loadHolidays();
  toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
}

function languageLabel(choice) {
  const value = LANGUAGE_CHOICES.includes(choice) ? choice : "system";
  return t(`language.${value}`);
}

function languageSheet() {
  const current = i18n.choice;
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
  if (choice === i18n.choice) return;
  await applyLanguageChoice(choice);
  render();
  if (!state.config) return;
  state.config.language = i18n.choice;
  const result = await persistConfig();
  rememberLanguageChoice(i18n.choice, !!result.ok);
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
  if (!service || service === "persistent_notification.create") return t("settings.notify.ha");
  return notifyName(service) || service;
}

function notifyServicesSummaryLabel(services) {
  const list = services || [];
  if (!list.length) return t("settings.notify.ha");
  if (list.length === 1) return notifyLabel(list[0]);
  return t("settings.notify.summary.more", {
    name: notifyLabel(list[0]),
    count: formatNumber(list.length - 1),
  });
}

function settingRow(label, value, onclick, variant) {
  return el("button", { class: variant ? `setting-row ${variant}` : "setting-row", type: "button", onclick }, [
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
    apply();
    const result = await persistConfig();
    state.sheetForm = null;
    state.sheetFormDefault = null;
    closeSheet();
    toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
  });
  return button;
}

async function persistConfig() {
  let response;
  try {
    response = await fetch(apiUrl("api/config"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.config),
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

function namesSheet() {
  const draft = sheetState(() => ({
    subjects: copy(state.config.subjects || {}),
    teachers: copy(state.config.teachers || {}),
  }));
  const body = [
    namesGroup("subjects", draft.subjects, (code) => subjectRow(code, draft.subjects[code])),
    namesGroup("teachers", draft.teachers, (code) => teacherRow(code, draft.teachers[code])),
  ];
  const foot = [saveSheet(() => {
    state.config.subjects = draft.subjects;
    state.config.teachers = draft.teachers;
  })];
  return sheet(t("settings.names.sheet"), body, foot);
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
  return Object.keys(entries || {}).sort((a, b) => a.localeCompare(b, i18n.language, { numeric: true, sensitivity: "base" }));
}

function subjectRow(code, subject) {
  const swatch = el("button", { class: "swatch swatch-trigger", type: "button", "aria-label": t("settings.subjects.color", { code }) });
  const applySwatchColor = () => {
    swatch.style.background = subject.color || SUBJECT_COLORS[hashIndex(code, SUBJECT_COLORS.length)];
  };
  applySwatchColor();
  swatch.addEventListener("click", () => openColorDialog(subject, applySwatchColor));
  const input = iservText("input", { class: "inp", type: "text", value: subject.label || "", placeholder: code, "aria-label": t("settings.subjects.name", { code }) });
  input.addEventListener("input", () => { subject.label = input.value; });
  return el("div", { class: "cell" }, [
    el("div", { class: "cell-head" }, [swatch, iservText("span", { class: "field-label" }, code)]),
    input,
  ]);
}

function closeColorDialog() {
  const close = state.colorDialogClose;
  state.colorDialogClose = null;
  if (close) close();
}

function openColorDialog(subject, onChange) {
  closeColorDialog();
  let close = () => {};
  const buttons = SUBJECT_COLORS.map((color, index) => {
    const button = el("button", {
      class: "swatch-btn",
      type: "button",
      "aria-label": t(SUBJECT_COLOR_KEYS[index] || "settings.color.auto"),
      "aria-pressed": String(subject.color === color),
      onclick: () => { subject.color = color; subject.color_source = COLOR_SOURCE_USER; onChange(); close(); },
    });
    button.style.background = color;
    return button;
  });
  buttons.push(
    el("button", {
      class: "swatch-btn auto",
      type: "button",
      "aria-label": t("settings.color.auto"),
      "aria-pressed": String(!subject.color),
      onclick: () => { subject.color = ""; subject.color_source = COLOR_SOURCE_AUTO; onChange(); close(); },
    }, [icon("restore", 16)])
  );
  const dialog = el("div", { class: "color-dialog", role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "swatch-row" }, buttons),
  ]);
  dialog.addEventListener("click", (event) => event.stopPropagation());
  const scrim = el("div", { class: "color-dialog-scrim" });
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
}

function teacherRow(code, teacher) {
  const input = iservText("input", { class: "inp", type: "text", value: teacher.label || "", placeholder: code, "aria-label": t("settings.teachers.name", { code }) });
  input.addEventListener("input", () => { teacher.label = input.value; });
  return el("div", { class: "cell" }, [el("div", { class: "cell-head" }, [iservText("span", { class: "field-label" }, code)]), input]);
}

function periodSheet() {
  const times = sheetState(() => copy(state.config.period_times || {}));
  const school = (state.timetable && state.timetable.school_period_times) || {};
  const numbers = Object.keys(times).map(Number).filter((n) => Number.isInteger(n) && n > 0).sort((a, b) => a - b);
  const list = numbers.length ? numbers : [1, 2, 3, 4, 5, 6, 7, 8];
  const differing = list.filter((number) => school[String(number)] && school[String(number)] !== times[String(number)]);
  const group = el("div", { class: "field-group" });
  const draw = () => {
    group.replaceChildren();
    for (const number of list) {
      const key = String(number);
      const label = t("settings.periods.label", { number: formatNumber(number) });
      const input = el("input", { class: "inp", type: "time", value: times[key] || "", "aria-label": label });
      input.addEventListener("change", () => { times[key] = input.value; });
      const mismatch = school[key] && school[key] !== times[key];
      group.append(
        el("div", { class: "cell" }, [
          el("div", { class: "cell-head" }, [el("span", { class: "overline" }, label)]),
          input,
          mismatch ? el("span", { class: "hint" }, t("settings.periods.iserv", { time: school[key] })) : null,
        ])
      );
    }
  };
  draw();
  const body = [
    el("p", { class: "dlg-text" }, t("settings.periods.text")),
  ];
  if (differing.length) {
    body.push(noteBlock(tCount("settings.periods.differ", differing.length)));
    body.push(
      el("button", {
        class: "btn ghost",
        type: "button",
        style: "margin-bottom:16px",
        onclick: () => {
          for (const number of differing) times[String(number)] = school[String(number)];
          draw();
        },
      }, [icon("restore", 16), t("settings.periods.adopt")])
    );
  }
  body.push(group);
  return sheet(t("settings.periods.sheet"), body, [saveSheet(() => { state.config.period_times = times; })]);
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
  const phones = sheetState(() => copy(Array.isArray(state.config.phones) ? state.config.phones : []));
  const group = el("div", { class: "field-group" });
  const err = el("div", { class: "err", style: "margin:0 0 8px" }, "");
  const draw = () => {
    group.replaceChildren();
    phones.forEach((row, index) => {
      const label = iservText("input", {
        class: "inp",
        type: "text",
        value: row.label || "",
        placeholder: t("common.phone.label"),
        autocomplete: "organization",
        "aria-label": t("common.phone.label"),
      });
      label.addEventListener("input", () => { row.label = label.value; err.textContent = ""; });
      const number = iservText("input", {
        class: "inp",
        type: "tel",
        inputmode: "tel",
        autocomplete: "tel",
        value: row.number || "",
        placeholder: t("common.phone.number"),
        "aria-label": t("common.phone.number"),
      });
      number.addEventListener("input", () => { row.number = number.value; err.textContent = ""; });
      const remove = el("button", {
        class: "btn ghost slim",
        type: "button",
        onclick: () => { phones.splice(index, 1); draw(); },
      }, [icon("trash", 16), t("settings.phones.remove")]);
      group.append(el("div", { class: "cell stack" }, [label, number, remove]));
    });
    if (!phones.length) {
      group.append(el("div", { class: "cell" }, [el("p", { class: "dlg-text", style: "margin:0" }, t("settings.phones.empty"))]));
    }
  };
  draw();
  const save = el("button", { class: "btn", type: "button" }, t("common.save"));
  save.addEventListener("click", async () => {
    if (phones.some(phonesRowIsHalfFilled)) {
      err.textContent = t("settings.phones.error");
      return;
    }
    save.disabled = true;
    save.replaceChildren(el("span", { class: "spin" }), document.createTextNode(t("common.saving")));
    state.config.phones = phones.filter((entry) => !phonesRowIsEmpty(entry));
    const result = await persistConfig();
    state.sheetForm = null;
    state.sheetFormDefault = null;
    closeSheet();
    toast(result.message || t("common.saved"), result.ok && !result.reloadFailed ? "good" : "bad");
  });
  return sheet(t("settings.phones.sheet"), [
    el("p", { class: "dlg-text" }, t("settings.phones.text")),
    group,
    el("button", { class: "btn ghost", type: "button", onclick: () => { phones.push({ label: "", number: "" }); draw(); } }, [icon("plus", 16), t("settings.phones.add")]),
    err,
  ], [save]);
}

const NOTIFY_EVENTS = [
  ["timetable", "settings.notify.event.timetable"],
  ["letters", "settings.notify.event.letters"],
  ["pinboard", "settings.notify.event.pinboard"],
  ["conferences", "settings.notify.event.conferences"],
];

const DEFAULT_NOTIFY_SERVICE = "persistent_notification.create";

const NOTIFY_CATEGORY_ORDER = ["mobile", "persistent", "group", "other"];

const NOTIFY_CATEGORY_KEYS = {
  mobile: "settings.notify.push",
  persistent: "settings.notify.category.persistent",
  group: "settings.notify.category.group",
  other: "settings.notify.category.other",
};

function notifyCategoryKey(category) {
  return NOTIFY_CATEGORY_KEYS[category] || NOTIFY_CATEGORY_KEYS.other;
}

function notifySectionHead(key) {
  return el("div", { class: "section-head notify-head" }, [el("span", { class: "overline" }, t(key))]);
}

function notifySheet() {
  const draft = sheetState(() => ({
    services: copy(state.config.notify_services || []),
    events: copy(state.config.notify_events || {}),
    advanced: false,
    testing: null,
  }));
  const options = notifyOptions().filter((entry) => entry.service !== DEFAULT_NOTIFY_SERVICE);
  const known = options.map((entry) => entry.service);
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
        result = await postJson("api/notify-test", { service, language: i18n.language });
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

  const targetRow = (service, title, hint, trailing) => {
    const check = el("input", { type: "checkbox" });
    check.checked = draft.services.includes(service);
    check.addEventListener("change", () => toggleService(service, check.checked));
    return el("div", { class: "cell notify-row" }, [
      el("label", { class: "check notify-pick" }, [
        check,
        el("span", { class: "notify-text" }, [
          el("b", {}, title),
          hint ? el("small", { class: "notify-id" }, hint) : null,
        ]),
      ]),
      trailing || null,
    ]);
  };

  const defaultGroup = el("div", { class: "field-group notify-default-group" }, [
    targetRow(
      DEFAULT_NOTIFY_SERVICE,
      t("settings.notify.default.title"),
      t("settings.notify.default.hint"),
      testButton(DEFAULT_NOTIFY_SERVICE, t("settings.notify.default.title"))
    ),
  ]);

  const categoryBlocks = [];
  for (const category of NOTIFY_CATEGORY_ORDER) {
    const entries = options.filter((entry) => (entry.category || "other") === category);
    if (!entries.length) continue;
    categoryBlocks.push(notifySectionHead(notifyCategoryKey(category)));
    categoryBlocks.push(el("div", { class: "field-group notify-services-group", "data-category": category },
      entries.map((entry) => {
        const label = entry.name || entry.service;
        return targetRow(entry.service, label, entry.name ? entry.service : null, testButton(entry.service, label));
      })
    ));
  }

  const manualHead = notifySectionHead("settings.notify.category.manual");
  const manualGroup = el("div", { class: "field-group notify-manual-group" });
  const drawManual = () => {
    const manual = draft.services.filter((value) => value !== DEFAULT_NOTIFY_SERVICE && !known.includes(value));
    manualHead.hidden = !manual.length;
    manualGroup.hidden = !manual.length;
    manualGroup.replaceChildren(...manual.map((value) => el("div", { class: "cell notify-row" }, [
      el("span", { class: "notify-text notify-manual-name", dir: "ltr" }, value),
      testButton(value, value),
      el("button", {
        class: "icon-btn notify-remove",
        type: "button",
        "aria-label": t("settings.notify.remove", { value }),
        onclick: () => { draft.services = draft.services.filter((entry) => entry !== value); drawManual(); },
      }, [icon("trash", 16)]),
    ])));
  };
  drawManual();

  const addInput = el("input", {
    class: "inp",
    type: "text",
    dir: "ltr",
    placeholder: t("settings.notify.add.placeholder"),
    autocomplete: "off",
    "aria-label": t("settings.notify.add.label"),
  });
  const addEntity = () => {
    const value = addInput.value.trim();
    if (!value) return;
    if (!draft.services.includes(value)) draft.services = draft.services.concat(value);
    addInput.value = "";
    drawManual();
  };
  addInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); addEntity(); }
  });
  const addButton = el("button", { class: "btn ghost slim", type: "button", onclick: addEntity }, [icon("plus", 16), t("settings.notify.add.button")]);
  const advancedPanel = el("div", { class: "notify-advanced" }, [
    el("p", { class: "dlg-text" }, t("settings.notify.advanced.hint")),
    el("div", { class: "field-group" }, [el("div", { class: "cell stack" }, [addInput, addButton])]),
  ]);
  advancedPanel.hidden = !draft.advanced;
  const advancedToggle = el("button", {
    class: "btn ghost slim notify-advanced-toggle",
    type: "button",
    "aria-expanded": String(!!draft.advanced),
  }, [icon("plus", 16), t("settings.notify.advanced")]);
  advancedToggle.addEventListener("click", () => {
    draft.advanced = !draft.advanced;
    advancedPanel.hidden = !draft.advanced;
    advancedToggle.setAttribute("aria-expanded", String(draft.advanced));
    if (draft.advanced) addInput.focus();
  });

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
    notifySectionHead("settings.notify.where"),
    el("p", { class: "dlg-text" }, t("settings.notify.both")),
    defaultGroup,
    ...categoryBlocks,
    emptyHint,
    manualHead,
    manualGroup,
    advancedToggle,
    advancedPanel,
    notifySectionHead("settings.notify.events"),
    el("div", { class: "field-group" }, NOTIFY_EVENTS.map(([key, label]) => {
      const check = el("input", { type: "checkbox" });
      check.checked = draft.events[key] !== false;
      check.addEventListener("change", () => { draft.events[key] = check.checked; });
      return el("label", { class: "cell check" }, [check, el("span", {}, t(label))]);
    })),
  ];
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
    value: state.account || "",
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
      const result = await postJson("api/password", { current: draft.current, new: draft.next });
      if (result && result.ok) {
        state.sheetForm = null;
        state.sheetFormDefault = null;
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

boot();
