import { describe, expect, test } from "vitest";
import {
  addDays,
  createFormat,
  formatGlobals,
  isoDate,
  isoWeek,
  pad2,
  parseAnyDate,
  parseGermanDate,
  parseGermanDateTime,
  parseIsoDateTime,
  parseIsoDay,
  startOfWeek,
  timeMinutes,
  weekdayIndex,
} from "../lib/format.js";

const NOW = new Date(2026, 8, 24, 10, 30);

function setup(start = "de") {
  let language = start;
  let clock = NOW.getTime();
  const format = createFormat({
    dateFormatter: (options) => new Intl.DateTimeFormat(language, options),
    relativeFormatter: () => new Intl.RelativeTimeFormat(language, { numeric: "auto" }),
    currentLanguage: () => language,
    formatNumber: (value) => `n${value}`,
    now: () => new Date(clock),
    nowMs: () => clock,
  });
  return {
    format,
    speak: (next) => {
      language = next;
    },
    travel: (ms) => {
      clock = ms;
    },
  };
}

describe("the calendar arithmetic works on local days", () => {
  test("pad2, isoDate and addDays stay on the local calendar", () => {
    expect(pad2(7)).toBe("07");
    expect(isoDate(new Date(2026, 0, 1, 0, 5))).toBe("2026-01-01");
    expect(isoDate(addDays(new Date(2026, 11, 31), 1))).toBe("2027-01-01");
  });

  test("the week starts on Monday and counts ISO weeks", () => {
    expect(weekdayIndex(new Date(2026, 8, 20))).toBe(7);
    expect(weekdayIndex(new Date(2026, 8, 21))).toBe(1);
    expect(isoDate(startOfWeek(new Date(2026, 8, 24)))).toBe("2026-09-21");
    expect(isoWeek(new Date(2026, 8, 24))).toBe(39);
    expect(isoWeek(new Date(2027, 0, 1))).toBe(53);
  });

  test("the parsers read German and ISO dates and refuse the rest", () => {
    expect(isoDate(parseGermanDate("7.9.2026"))).toBe("2026-09-07");
    expect(parseGermanDate("2026-09-07")).toBe(null);
    expect(isoDate(parseAnyDate(" 2026-09-07 "))).toBe("2026-09-07");
    expect(isoDate(parseAnyDate("07.09.2026"))).toBe("2026-09-07");
    expect(parseAnyDate("")).toBe(null);
    expect(parseGermanDateTime("07.09.2026 08:15").hasTime).toBe(true);
    expect(parseGermanDateTime("07.09.2026").hasTime).toBe(false);
    expect(parseIsoDateTime("2026-09-07T08:15:00").getHours()).toBe(8);
    expect(parseIsoDateTime("2026-09-07")).toBe(null);
    expect(isoDate(parseIsoDay("2026-09-07T08:15"))).toBe("2026-09-07");
    expect(parseIsoDay("morgen")).toBe(null);
    expect(timeMinutes("8:05")).toBe(485);
    expect(timeMinutes("")).toBe(null);
  });
});

describe("the formatters read the language when they run", () => {
  test("a language switch after creation changes the next result", () => {
    const { format, speak } = setup("de");
    expect(format.showDate("2026-09-07")).toBe("07.09.2026");
    speak("en");
    expect(format.showDate("2026-09-07")).toBe("09/07/2026");
    expect(format.dateLabel("2026-09-07")).toBe("09/07/2026");
  });

  test("unparsable input is shown as it came", () => {
    const { format } = setup();
    expect(format.showDate("bald")).toBe("bald");
    expect(format.showDateTime("")).toBe("");
    expect(format.isoLabel("x")).toBe("x");
    expect(format.formatWeekdayDate("x")).toBe("");
    expect(format.formatEpoch(0)).toBe("");
    expect(format.formatIsoMoment("not a date")).toBe("");
  });

  test("date and time pieces keep their shape", () => {
    const { format } = setup();
    expect(format.showDateTime("07.09.2026 08:15")).toBe("07.09.2026 08:15");
    expect(format.showTimestamp("2026-09-07T08:15:00")).toBe("07.09.2026 08:15");
    expect(format.showTimestamp("07.09.2026")).toBe("07.09.2026");
    expect(format.clockOf("13:05")).toBe("13:05");
    expect(format.clockOf("x")).toBe("");
    expect(format.clockText(-15)).toBe("23:45");
  });
});

describe("the clock comes from outside", () => {
  test("the weekday row starts at the Monday of the injected day", () => {
    const { format, travel } = setup();
    expect(format.weekdayLabel(0)).toBe(new Intl.DateTimeFormat("de", { weekday: "short" }).format(new Date(2026, 8, 21)));
    travel(new Date(2026, 8, 28, 9).getTime());
    expect(format.weekdayLabel(6)).toBe(new Intl.DateTimeFormat("de", { weekday: "short" }).format(new Date(2026, 9, 4)));
  });

  test("relativeSince measures against the injected milliseconds", () => {
    const { format } = setup("en");
    const now = NOW.getTime() / 1000;
    expect(format.relativeSince(0)).toBe("");
    expect(format.relativeSince(now - 30)).toBe("30 seconds ago");
    expect(format.relativeSince(now - 3 * 3600)).toBe("3 hours ago");
    expect(format.relativeSince(now - 2 * 86400)).toBe("2 days ago");
  });

  test("minutesUntilLabel switches to hours from two hours on and falls back to the number", () => {
    const { format, speak } = setup("en");
    expect(format.minutesUntilLabel(5)).toBe("in 5 minutes");
    expect(format.minutesUntilLabel(150)).toBe("in 3 hours");
    speak("");
    expect(format.minutesUntilLabel(5)).toBe("n5");
  });
});

test("the globals hand out the pure helpers and the factory, frozen", () => {
  const globals = formatGlobals();
  expect(Object.isFrozen(globals)).toBe(true);
  expect(globals.isoDate).toBe(isoDate);
  expect(globals.createFormat).toBe(createFormat);
  expect(Object.keys(globals)).not.toContain("showDate");
});
