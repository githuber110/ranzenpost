(() => {
  const DAY_MINUTES = 24 * 60;
  const DEFAULT_MINUTES = 45;
  const TYPE_PAUSE = "pause";
  const TYPE_CLUB = "club";
  const TYPE_APPOINTMENT = "appointment";
  const TYPES = [TYPE_PAUSE, TYPE_CLUB, TYPE_APPOINTMENT];
  const REPEAT_ONCE = "once";
  const REPEAT_DAILY = "daily";
  const REPEAT_WEEKLY = "weekly";
  const REPEAT_WEEKS = "weeks";
  const REPEATS = [REPEAT_ONCE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_WEEKS];
  const SCHOOL_DAYS = [0, 1, 2, 3, 4];
  const STATE_OK = "ok";
  const STATE_CUT = "cut";
  const STATE_HIDDEN = "hidden";
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  const CLOCK = /^([01]?\d|2[0-3]):([0-5]\d)$/;

  function minutesOf(value) {
    const match = CLOCK.exec(String(value == null ? "" : value).trim());
    return match ? Number(match[1]) * 60 + Number(match[2]) : null;
  }

  function clockOf(minutes) {
    if (minutes === null || minutes === undefined) return "";
    const value = Math.max(0, Math.min(DAY_MINUTES, Math.round(minutes)));
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
  }

  function dayNumber(iso) {
    const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
    if (!parts) return null;
    return Math.round(Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3])) / MS_PER_DAY);
  }

  function isoOfDay(number) {
    return new Date(number * MS_PER_DAY).toISOString().slice(0, 10);
  }

  function weekdayOf(iso) {
    const number = dayNumber(iso);
    return number === null ? null : (((number + 3) % 7) + 7) % 7;
  }

  function mondayOf(number) {
    return number - ((((number + 3) % 7) + 7) % 7);
  }

  function addDaysIso(iso, days) {
    const number = dayNumber(iso);
    return number === null ? "" : isoOfDay(number + days);
  }

  function lessonIso(value) {
    const text = String(value || "").trim();
    const german = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(text);
    if (german) return `${german[3]}-${german[2].padStart(2, "0")}-${german[1].padStart(2, "0")}`;
    return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : "";
  }

  function startOf(entry) {
    return minutesOf(entry.start);
  }

  function endOf(entry) {
    const start = startOf(entry);
    return start === null ? null : start + (Number(entry.duration) || 0);
  }

  function occursOn(entry, iso) {
    const day = dayNumber(iso);
    if (day === null) return false;
    if (entry.repeat === REPEAT_ONCE) return dayNumber(entry.date) === day;
    const first = dayNumber(entry.from);
    const last = dayNumber(entry.until);
    if (first === null || last === null || day < first || day > last) return false;
    if (!(entry.days || []).includes(weekdayOf(iso))) return false;
    if (entry.repeat === REPEAT_WEEKS) {
      const weeks = Math.round((mondayOf(day) - mondayOf(first)) / 7);
      return weeks % Math.max(1, Number(entry.interval) || 1) === 0;
    }
    return true;
  }

  function weekdaysOf(entry) {
    if (entry.repeat === REPEAT_ONCE) {
      const weekday = weekdayOf(entry.date);
      return weekday === null ? [] : [weekday];
    }
    return [...new Set(entry.days || [])].sort((a, b) => a - b);
  }

  function occurrenceDays(entry) {
    if (entry.repeat === REPEAT_ONCE) {
      const day = dayNumber(entry.date);
      return day === null ? [] : [day];
    }
    const first = dayNumber(entry.from);
    const last = dayNumber(entry.until);
    const found = [];
    if (first === null || last === null) return found;
    for (let day = first; day <= last; day += 1) {
      if (occursOn(entry, isoOfDay(day))) found.push(day);
    }
    return found;
  }

  function appliesTo(entry, childId) {
    const owner = String(entry.child || "");
    return !owner || owner === String(childId);
  }

  function childrenOfEntry(entry, children) {
    const owner = String(entry.child || "");
    return owner ? [owner] : children.slice();
  }

  function clip(start, end, blockers) {
    let by = null;
    let from = start;
    let to = end;
    const ordered = blockers.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    for (const [blockStart, blockEnd, number] of ordered) {
      if (blockStart <= from && from < blockEnd) {
        from = blockEnd;
        if (by === null) by = number;
      }
      if (from < blockStart && blockStart < to) {
        to = blockStart;
        if (by === null) by = number;
      }
    }
    return [from, to, by];
  }

  function pauseCounts(entry, spans) {
    if (entry.type !== TYPE_PAUSE || spans === null || spans === undefined) return true;
    const start = startOf(entry);
    return spans.some((span) => span[0] <= start) && spans.some((span) => span[0] >= start);
  }

  function compareText(a, b) {
    const left = String(a || "");
    const right = String(b || "");
    return left < right ? -1 : left > right ? 1 : 0;
  }

  function order(a, b) {
    return (startOf(a) || 0) - (startOf(b) || 0) || compareText(a.id, b.id);
  }

  function clipped(entry, blockers) {
    const first = startOf(entry);
    const last = endOf(entry);
    const [start, end, by] = clip(first, last, blockers);
    const state = end <= start ? STATE_HIDDEN : start !== first || end !== last ? STATE_CUT : STATE_OK;
    return { entry, start, end, state, number: state === STATE_OK ? null : by };
  }

  function resolveDay(entries, spans, iso, childId, free) {
    const blockers = (spans || []).slice();
    const chosen = entries.filter((entry) => appliesTo(entry, childId) && occursOn(entry, iso));
    const items = [];
    const taken = [];
    for (const entry of chosen.filter((item) => item.repeat === REPEAT_ONCE).sort(order)) {
      const item = clipped(entry, blockers);
      items.push(item);
      if (item.state !== STATE_HIDDEN) taken.push([item.start, item.end, null]);
    }
    for (const entry of chosen.filter((item) => item.repeat !== REPEAT_ONCE).sort(order)) {
      if (free && !entry.holidays) continue;
      items.push(clipped(entry, blockers.concat(taken)));
    }
    return items.sort((a, b) => a.start - b.start || compareText(a.entry.id, b.entry.id));
  }

  function gridRows(grid) {
    return (grid || []).map((row) => ({
      number: Number(row.number),
      start: minutesOf(row.start),
      end: row.end === "24:00" ? DAY_MINUTES : minutesOf(row.end),
      duration: Number(row.duration) || DEFAULT_MINUTES,
      row,
    })).filter((row) => row.start !== null && row.end !== null);
  }

  function spansFor(rows, periods) {
    const wanted = new Set((periods || []).map(Number));
    return rows.filter((row) => wanted.has(row.number)).map((row) => [row.start, row.end, row.number]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  }

  function profileDays(profiles, child) {
    const raw = (profiles || {})[child];
    if (!raw || typeof raw !== "object") return null;
    const days = {};
    for (const [key, numbers] of Object.entries(raw)) {
      if (/^[0-6]$/.test(key) && Array.isArray(numbers)) days[Number(key)] = numbers.map(Number);
    }
    return days;
  }

  function entryStatus(entry, rows, profiles, children) {
    let worst = { state: STATE_OK, number: null, start: null, end: null };
    for (const child of childrenOfEntry(entry, children)) {
      const days = profileDays(profiles, child) || {};
      for (const weekday of weekdaysOf(entry)) {
        if (!(weekday in days)) continue;
        const spans = spansFor(rows, days[weekday]);
        if (!pauseCounts(entry, spans)) continue;
        const [start, end, by] = clip(startOf(entry), endOf(entry), spans);
        if (end <= start) return { state: STATE_HIDDEN, number: by, start: null, end: null };
        if (by !== null && worst.state === STATE_OK) worst = { state: STATE_CUT, number: by, start, end };
      }
    }
    return worst;
  }

  function rawChild(key) {
    const text = String(key || "");
    const cut = text.indexOf(":");
    return cut >= 0 ? text.slice(cut + 1) : text;
  }

  function overlaps(firstStart, firstEnd, secondStart, secondEnd) {
    return firstStart < secondEnd && secondStart < firstEnd;
  }

  function limits(candidate, entries, rows, profiles, children) {
    const start = startOf(candidate);
    const weekdays = weekdaysOf(candidate);
    const result = { weekdays, max: DAY_MINUTES - start, limit: null, minStart: 0, minWhat: null, conflict: null, noDays: !weekdays.length };
    if (!weekdays.length) return result;
    const once = candidate.repeat === REPEAT_ONCE;
    const ownDays = new Set(occurrenceDays(candidate));
    const kids = childrenOfEntry(candidate, children);
    const consider = (weekday, block) => {
      if (block.start <= start && start < block.end && !result.conflict) result.conflict = { weekday, block };
      if (block.end <= start && block.end >= result.minStart) {
        result.minStart = block.end;
        result.minWhat = { weekday, block };
      }
      if (block.start > start && block.start - start < result.max) {
        result.max = block.start - start;
        result.limit = { weekday, block };
      }
    };
    for (const child of kids) {
      const days = profileDays(profiles, child);
      for (const weekday of weekdays) {
        const spans = days && weekday in days ? spansFor(rows, days[weekday]) : null;
        if (!pauseCounts(candidate, spans)) continue;
        for (const [blockStart, blockEnd, number] of spans || []) consider(weekday, { start: blockStart, end: blockEnd, number });
        for (const other of entries) {
          if (other.id === candidate.id || (other.repeat === REPEAT_ONCE) !== once || !appliesTo(other, child)) continue;
          if (!pauseCounts(other, spans)) continue;
          const shared = occurrenceDays(other).some((day) => ownDays.has(day) && (((day + 3) % 7) + 7) % 7 === weekday);
          if (!shared) continue;
          const [otherStart, otherEnd] = clip(startOf(other), endOf(other), spans || []);
          if (otherEnd > otherStart) consider(weekday, { start: otherStart, end: otherEnd, entry: other });
        }
      }
    }
    return result;
  }

  function defaultDuration(max) {
    return max <= 120 ? max : 60;
  }

  function regularPeriods(lessons) {
    const days = {};
    for (const lesson of lessons || []) {
      const iso = lessonIso(lesson && lesson.date);
      if (!iso) continue;
      const found = days[iso] || (days[iso] = new Set());
      const number = Number(lesson.period);
      if (Number.isInteger(number) && number > 0 && lesson.change_kind !== "added") found.add(number);
    }
    const out = {};
    for (const [iso, numbers] of Object.entries(days)) out[iso] = [...numbers].sort((a, b) => a - b);
    return out;
  }

  window.RanzenpostPeriods = {
    DAY_MINUTES,
    DEFAULT_MINUTES,
    TYPE_PAUSE,
    TYPE_CLUB,
    TYPE_APPOINTMENT,
    TYPES,
    REPEAT_ONCE,
    REPEAT_DAILY,
    REPEAT_WEEKLY,
    REPEAT_WEEKS,
    REPEATS,
    SCHOOL_DAYS,
    STATE_OK,
    STATE_CUT,
    STATE_HIDDEN,
    minutesOf,
    clockOf,
    dayNumber,
    isoOfDay,
    weekdayOf,
    addDaysIso,
    lessonIso,
    startOf,
    endOf,
    occursOn,
    weekdaysOf,
    occurrenceDays,
    appliesTo,
    clip,
    pauseCounts,
    resolveDay,
    gridRows,
    spansFor,
    profileDays,
    entryStatus,
    rawChild,
    overlaps,
    limits,
    defaultDuration,
    regularPeriods,
  };
})();
