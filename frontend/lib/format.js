const MS_PER_WEEK = 604800000;
const ISO_DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})/;
const RELATIVE_STEPS = Object.freeze([
  Object.freeze({ limit: 60, unit: "second", per: 1 }),
  Object.freeze({ limit: 3600, unit: "minute", per: 60 }),
  Object.freeze({ limit: 86400, unit: "hour", per: 3600 }),
  Object.freeze({ limit: Infinity, unit: "day", per: 86400 }),
]);

export const pad2 = (value) => String(value).padStart(2, "0");
export const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
export const weekdayIndex = (date) => ((date.getDay() + 6) % 7) + 1;
export const startOfWeek = (date) => addDays(date, 1 - weekdayIndex(date));
export const isoDate = (date) => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

export function isoWeek(date) {
  const thursday = addDays(date, 4 - weekdayIndex(date));
  const jan4 = new Date(thursday.getFullYear(), 0, 4);
  const anchor = addDays(jan4, 4 - weekdayIndex(jan4));
  return 1 + Math.round((thursday.getTime() - anchor.getTime()) / MS_PER_WEEK);
}

export function parseGermanDate(text) {
  const match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(String(text || "").trim());
  if (!match) return null;
  const date = new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function parseAnyDate(text) {
  const value = String(text || "").trim();
  if (!value) return null;
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (iso) return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
  return parseGermanDate(value);
}

export function parseGermanDateTime(text) {
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

export function parseIsoDateTime(text) {
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

export function parseIsoDay(value) {
  const match = ISO_DAY_PATTERN.exec(String(value || ""));
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null;
}

export function timeMinutes(value) {
  const parts = /^(\d{1,2}):(\d{2})/.exec(String(value || ""));
  return parts ? Number(parts[1]) * 60 + Number(parts[2]) : null;
}

export function createFormat({ dateFormatter, relativeFormatter, currentLanguage, formatNumber, now, nowMs }) {
  const formatDate = (date) => dateFormatter({ day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
  const formatShortDate = (date) => dateFormatter({ day: "2-digit", month: "2-digit" }).format(date);
  const formatTime = (date) => dateFormatter({ hour: "2-digit", minute: "2-digit" }).format(date);
  const formatWeekdayShort = (date) => dateFormatter({ weekday: "short" }).format(date);
  const formatDayNumber = (date) => dateFormatter({ day: "2-digit" }).format(date);
  const formatWeekdayDay = (date) => dateFormatter({ weekday: "short", day: "2-digit", month: "2-digit" }).format(date);

  function formatWeekdayDate(value) {
    const date = parseAnyDate(value);
    return date ? dateFormatter({ weekday: "long", day: "2-digit", month: "2-digit" }).format(date) : "";
  }

  function showDate(text) {
    const date = parseAnyDate(text);
    return date ? formatDate(date) : String(text || "");
  }

  function showDateTime(text) {
    const parsed = parseGermanDateTime(text);
    if (!parsed) return String(text || "");
    return parsed.hasTime ? `${formatDate(parsed.date)} ${formatTime(parsed.date)}` : formatDate(parsed.date);
  }

  function showTimestamp(text) {
    const date = parseIsoDateTime(text);
    if (date) return `${formatDate(date)} ${formatTime(date)}`;
    return showDateTime(text);
  }

  function formatEpoch(value) {
    const n = Number(value);
    if (!n) return "";
    const date = new Date(n * 1000);
    if (Number.isNaN(date.getTime())) return "";
    return dateFormatter({ dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function formatIsoMoment(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return dateFormatter({ dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function clockText(minutes) {
    const total = ((minutes % 1440) + 1440) % 1440;
    const date = now();
    date.setHours(Math.floor(total / 60), total % 60, 0, 0);
    return formatTime(date);
  }

  function clockOf(rawTime) {
    const minutes = timeMinutes(rawTime);
    return minutes === null ? "" : clockText(minutes);
  }

  function weekdayLabel(index) {
    return formatWeekdayShort(addDays(startOfWeek(now()), index));
  }

  function isoLabel(iso) {
    const day = parseIsoDay(iso);
    return day ? formatWeekdayDay(day) : iso;
  }

  function dateLabel(iso) {
    const day = parseIsoDay(iso);
    return day ? formatDate(day) : iso;
  }

  function relativeSince(epochSeconds) {
    const stamp = Number(epochSeconds) || 0;
    if (stamp <= 0) return "";
    const seconds = Math.max(0, Math.round(nowMs() / 1000 - stamp));
    const step = RELATIVE_STEPS.find((entry) => seconds < entry.limit) || RELATIVE_STEPS[RELATIVE_STEPS.length - 1];
    return relativeFormatter().format(-Math.round(seconds / step.per), step.unit);
  }

  function minutesUntilLabel(minutes) {
    try {
      const format = new Intl.RelativeTimeFormat(currentLanguage(), { numeric: "always" });
      if (minutes >= 120) return format.format(Math.round(minutes / 60), "hour");
      return format.format(minutes, "minute");
    } catch (error) {
      return formatNumber(minutes);
    }
  }

  return {
    formatShortDate,
    formatTime,
    formatWeekdayShort,
    formatDayNumber,
    formatWeekdayDay,
    formatWeekdayDate,
    showDate,
    showDateTime,
    showTimestamp,
    formatEpoch,
    formatIsoMoment,
    clockText,
    clockOf,
    weekdayLabel,
    isoLabel,
    dateLabel,
    relativeSince,
    minutesUntilLabel,
  };
}

export function formatGlobals() {
  return Object.freeze({
    addDays,
    weekdayIndex,
    startOfWeek,
    isoDate,
    isoWeek,
    parseAnyDate,
    parseIsoDay,
    timeMinutes,
    createFormat,
  });
}
