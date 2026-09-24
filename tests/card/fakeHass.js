import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "..", "components", "ranzenpost", "fixtures");
export const FROZEN_NOW = "2026-09-02T07:15:00Z";
export const ENTRY_ID = "0123456789abcdef0123456789abcdef";
export const SCHOOL = "a1b2c3d4";
export const SECOND_SCHOOL = "b2c3d4e5";
export const SCHOOLS = [
  { id: SCHOOL, deviceId: "device-school", name: "Sample School", slug: "" },
  { id: SECOND_SCHOOL, deviceId: "device-school-two", name: "Other School", slug: "other_school" },
];
export const CHILDREN = [
  { id: `${SCHOOL}:child-1`, deviceId: "device-1", name: "Alex", slug: "alex", school: SCHOOL, entitySlug: "alex" },
  { id: `${SCHOOL}:child-2`, deviceId: "device-2", name: "Kim", slug: "kim", school: SCHOOL, entitySlug: "kim" },
];
export const OTHER_CHILDREN = [
  { id: `${SECOND_SCHOOL}:child-1`, deviceId: "device-3", name: "Alex", slug: "alex", school: SECOND_SCHOOL, entitySlug: "alex_other_school" },
  { id: `${SECOND_SCHOOL}:child-9`, deviceId: "device-4", name: "Robin", slug: "robin", school: SECOND_SCHOOL, entitySlug: "robin" },
];
const CHILD_KEYS = {
  sensor: [
    "current_lesson",
    "next_lesson",
    "school_end_today",
    "next_school_day",
    "changes_today",
    "next_exam",
    "exams_upcoming",
    "unread_letters",
    "unread_posts",
    "open_absences",
    "timetable_last_updated",
  ],
  binary_sensor: ["school_day_today", "timetable_changed_today"],
  calendar: ["lessons", "exams", "absences"],
  event: ["timetable_changed"],
};
const SCHOOL_KEYS = { sensor: ["next_holiday", "next_conference", "connection"], calendar: ["holidays"] };

export function fixture(name) {
  return JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), "utf8"));
}

const EXTRA_LESSONS = [
  {
    uid: "lesson-20260902-p2@sample",
    summary: "English",
    description: "Mr Stand-in, R202",
    location: "R202",
    start: "2026-09-02T09:50:00+02:00",
    end: "2026-09-02T10:35:00+02:00",
    all_day: false,
    cancelled: false,
    color: "#cc9933",
  },
  {
    uid: "lesson-20260904-p1@sample",
    summary: "Sport",
    description: "Mr Whistle, Gym",
    location: "Gym",
    start: "2026-09-04T08:00:00+02:00",
    end: "2026-09-04T09:30:00+02:00",
    all_day: false,
    cancelled: false,
    color: "#9933cc",
  },
];

function hasLessons(childId) {
  return childId === CHILDREN[0].id;
}

export function lessonsOf(childId) {
  if (!hasLessons(childId)) return [];
  return [...fixture("events_lessons"), ...EXTRA_LESSONS];
}

function eventsOf(kind, childId) {
  if (kind === "lessons") return lessonsOf(childId);
  if (kind === "holidays") return fixture("events_holidays");
  if (!hasLessons(childId)) return [];
  return fixture(`events_${kind}`);
}

function eventsOverride(overrides, entityId, kind) {
  const table = overrides.events || {};
  if (Object.prototype.hasOwnProperty.call(table, entityId)) return table[entityId];
  if (Object.prototype.hasOwnProperty.call(table, kind)) return table[kind];
  return null;
}

function eventsOfWithOverrides(overrides, entityId, kind, childId) {
  const override = eventsOverride(overrides, entityId, kind);
  return override || eventsOf(kind, childId);
}

function toApiEvent(event) {
  const bound = (value) => (event.all_day ? { date: value } : { dateTime: value });
  return {
    summary: event.summary,
    description: event.description || null,
    location: event.location || null,
    uid: event.uid,
    recurrence_id: null,
    rrule: null,
    start: bound(event.start),
    end: bound(event.end),
    color: event.color,
    cancelled: event.cancelled,
    subject_code: event.subject_code || "",
    subject: event.subject || "",
  };
}

function instant(value) {
  return new Date(value.length === 10 ? `${value}T00:00:00+02:00` : value).getTime();
}

function lessonState(lesson) {
  return lesson ? lesson.subject : "none";
}

function childStates(child, state) {
  const prefix = `ranzenpost_${child.entitySlug}`;
  const stamp = state.timetable_last_updated;
  return {
    [`sensor.${prefix}_current_lesson`]: { state: lessonState(state.now_lesson), attributes: state.now_lesson || {} },
    [`sensor.${prefix}_next_lesson`]: { state: lessonState(state.next_lesson), attributes: state.next_lesson || {} },
    [`sensor.${prefix}_school_end_today`]: { state: state.school_end_today || "unknown", attributes: {} },
    [`sensor.${prefix}_next_school_day`]: {
      state: state.next_school_day ? state.next_school_day.start : "unknown",
      attributes: state.next_school_day || {},
    },
    [`sensor.${prefix}_changes_today`]: {
      state: String(state.changes_today.length),
      attributes: { changes: state.changes_today },
    },
    [`sensor.${prefix}_next_exam`]: {
      state: state.next_exam ? state.next_exam.subject : "none",
      attributes: state.next_exam || {},
    },
    [`sensor.${prefix}_exams_upcoming`]: {
      state: String(state.exams_upcoming.count),
      attributes: { exams: state.exams_upcoming.items, days: state.exams_upcoming.days },
    },
    [`sensor.${prefix}_unread_letters`]: {
      state: String(state.unread_letters.count),
      attributes: { letters: state.unread_letters.items },
    },
    [`sensor.${prefix}_unread_posts`]: {
      state: String(state.unread_posts.count),
      attributes: { posts: state.unread_posts.items },
    },
    [`sensor.${prefix}_open_absences`]: {
      state: String(state.open_absences.count),
      attributes: { absences: state.open_absences.items },
    },
    [`sensor.${prefix}_timetable_last_updated`]: { state: stamp || "unknown", attributes: {} },
    [`binary_sensor.${prefix}_school_day_today`]: { state: state.school_day_today ? "on" : "off", attributes: {} },
    [`binary_sensor.${prefix}_timetable_changed_today`]: {
      state: state.timetable_changed_today ? "on" : "off",
      attributes: {},
    },
    [`calendar.${prefix}_lessons`]: { state: "off", attributes: {} },
    [`calendar.${prefix}_exams`]: { state: "off", attributes: {} },
    [`calendar.${prefix}_absences`]: { state: "off", attributes: {} },
  };
}

function schoolPrefix(school, many) {
  return many && school.slug ? `ranzenpost_school_${school.slug}` : "ranzenpost_school";
}

export const INGRESS_PATH = "/hassio/ingress/ranzenpost";

function schoolStates(school, listed, many) {
  const holiday = school.next_holiday;
  const conference = school.next_conference;
  const prefix = schoolPrefix(listed, many);
  return {
    [`sensor.${prefix}_next_holiday`]: {
      state: holiday ? holiday.name : "none",
      attributes: holiday ? { start: holiday.start, end: holiday.end, days_until: holiday.days_until } : {},
    },
    [`sensor.${prefix}_next_conference`]: {
      state: "2026-11-05T00:00:00+01:00",
      attributes: conference ? { date: conference.date, title: conference.title, details: conference.details, days_until: conference.days_until } : {},
    },
    [`sensor.${prefix}_connection`]: {
      state: "ok",
      attributes: {
        modules: { timetable: true, letters: true, pinboard: true, absences: true, conferences: true, messenger: true },
        modules_disabled: [],
        ingress_path: INGRESS_PATH,
      },
    },
    [`calendar.${prefix}_holidays`]: { state: "off", attributes: {} },
  };
}

function registryEntries(children, schools, without = [], ownEntries = false) {
  const entries = [];
  const many = schools.length > 1;
  const childKeys = ownEntries ? { ...CHILD_KEYS, calendar: [...CHILD_KEYS.calendar, "own_entries"] } : CHILD_KEYS;
  for (const child of children) {
    for (const [platform, keys] of Object.entries(childKeys)) {
      for (const key of keys) {
        if (without.includes(key)) continue;
        entries.push({
          entity_id: `${platform}.ranzenpost_${child.entitySlug}_${key}`,
          unique_id: `ranzenpost_${ENTRY_ID}_${child.id}_${key}`,
          platform: "ranzenpost",
          device_id: child.deviceId,
          translation_key: key,
        });
      }
    }
  }
  for (const school of schools) {
    for (const [platform, keys] of Object.entries(SCHOOL_KEYS)) {
      for (const key of keys) {
        entries.push({
          entity_id: `${platform}.${schoolPrefix(school, many)}_${key}`,
          unique_id: `ranzenpost_${ENTRY_ID}_school_${school.id}_${key}`,
          platform: "ranzenpost",
          device_id: school.deviceId,
          translation_key: key,
        });
      }
    }
  }
  entries.push({
    entity_id: "sensor.other_thing",
    unique_id: "other_thing",
    platform: "other",
    device_id: "device-other",
    translation_key: null,
  });
  return entries;
}

function devices(children, schools) {
  const byId = new Map(schools.map((school) => [school.id, school]));
  const shared = (child) => children.some((other) => other !== child && other.slug === child.slug);
  return [
    ...children.map((child) => ({
      id: child.deviceId,
      name: shared(child) ? `Ranzenpost ${child.name} (${byId.get(child.school).name})` : `Ranzenpost ${child.name}`,
      name_by_user: null,
      via_device_id: byId.get(child.school).deviceId,
      identifiers: [["ranzenpost", `child:${ENTRY_ID}:${child.id}`]],
    })),
    ...schools.map((school) => ({
      id: school.deviceId,
      name: `Ranzenpost ${school.name}`,
      name_by_user: null,
      identifiers: [["ranzenpost", `school:${ENTRY_ID}:${school.id}`]],
    })),
  ];
}

export function ownEntriesKey(child) {
  return `calendar.ranzenpost_${child.entitySlug}_own_entries`;
}

function ownEntriesOf(overrides, children, message) {
  const child = children.find((item) => item.deviceId === message.device_id);
  if (!child) throw Object.assign(new Error("no Ranzenpost child with this device"), { code: "not_found" });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(message.start) || !/^\d{4}-\d{2}-\d{2}$/.test(message.end) || message.end < message.start) {
    throw Object.assign(new Error("bad range"), { code: "bad_range" });
  }
  if (overrides.ownEntriesError) throw Object.assign(new Error("the add-on could not be read"), { code: "unavailable" });
  const day = (value) => value.slice(0, 10);
  const listed = eventsOverride(overrides, ownEntriesKey(child), "own_entries") || (overrides.ownEntryList && hasLessons(child.id) ? fixture("events_own_entries") : []);
  return listed
    .filter((event) => day(event.start) >= message.start && day(event.start) <= message.end)
    .map(toApiEvent);
}

export function ownEntriesCalls(hass) {
  return hass.calls.ws.filter((call) => call.type === "ranzenpost/own_entries");
}

export function makeHass(overrides = {}) {
  const schools = overrides.twoSchools ? SCHOOLS : SCHOOLS.slice(0, 1);
  const children = overrides.twoSchools ? [...CHILDREN, ...OTHER_CHILDREN] : CHILDREN;
  const many = schools.length > 1;
  const states = {
    ...childStates(CHILDREN[0], fixture("state_child_1")),
    ...childStates(CHILDREN[1], fixture("state_child_2")),
    ...(overrides.twoSchools ? childStates(OTHER_CHILDREN[0], fixture("state_child_2")) : {}),
    ...(overrides.twoSchools ? childStates(OTHER_CHILDREN[1], fixture("state_child_2")) : {}),
    ...Object.assign({}, ...schools.map((school) => schoolStates(fixture("school"), school, many))),
    ...(overrides.states || {}),
  };
  for (const [entityId, entry] of Object.entries(states)) {
    entry.entity_id = entityId;
    entry.last_updated = entry.last_updated || "2026-09-02T07:00:00+00:00";
  }
  const calls = { api: [], ws: [] };
  const language = overrides.language || "de";
  return {
    language,
    locale: { language },
    config: { time_zone: "Europe/Berlin" },
    states,
    calls,
    async callWS(message) {
      calls.ws.push(message);
      if (message.type === "config/entity_registry/list") return registryEntries(children, schools, overrides.withoutKeys || [], !!overrides.ownEntries);
      if (message.type === "config/device_registry/list") return devices(children, schools);
      if (message.type === "ranzenpost/own_entries") return ownEntriesOf(overrides, children, message);
      throw new Error(`unexpected websocket call ${message.type}`);
    },
    async callApi(method, path) {
      calls.api.push({ method, path });
      const match = /^calendars\/([^?]+)\?start=([^&]+)&end=(.+)$/.exec(path);
      if (!match) throw new Error(`unexpected api call ${path}`);
      const entityId = match[1];
      const start = new Date(decodeURIComponent(match[2])).getTime();
      const end = new Date(decodeURIComponent(match[3])).getTime();
      const parts = /^calendar\.ranzenpost_([a-z0-9_]+)_(lessons|exams|absences|holidays|own_entries)$/.exec(entityId);
      if (!parts) throw new Error(`unknown calendar ${entityId}`);
      const child = children.find((item) => item.entitySlug === parts[1]);
      const events = eventsOfWithOverrides(overrides, entityId, parts[2], child ? child.id : "");
      return events
        .filter((event) => instant(event.start) < end && instant(event.end) > start)
        .map(toApiEvent);
    },
  };
}

export function apiCallsFor(hass, entityId) {
  return hass.calls.api.filter((call) => call.path.startsWith(`calendars/${entityId}?`));
}
