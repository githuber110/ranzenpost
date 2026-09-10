import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const NOW_MS = Date.UTC(2026, 8, 10, 12, 0, 0);
const NOW_S = Math.floor(NOW_MS / 1000);
const IPHONE_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

function seed(window, subscription) {
  window.Date.now = () => NOW_MS;
  window.eval(`
    state.calendar = { data: { host: "homeassistant.local", port: 8100, port_open: true, supervisor: true, host_source: "internal_url" } };
    state.config = { children: [] };
  `);
  return window.eval(`(function (s, c) { return calendarSubscriptionBlock(s, c); })`)(
    subscription,
    { child_id: "c1", name: "Mia", class_name: "5A" }
  );
}

function textOf(nodes) {
  return nodes.map((node) => node.textContent).join(" ");
}

function subscription(extra) {
  return Object.assign(
    {
      id: "s1",
      child_id: "c1",
      label: "5A",
      components: ["timetable"],
      color: "#2486ed",
      token: "t",
      path: "/calendar/t.ics",
      created_at: 1,
      rotated_at: 0,
      last_fetched_at: 0,
      watched_since: 0,
    },
    extra || {}
  );
}

describe("[P255] the fetch line always carries a date", () => {
  test("a link nobody has fetched says since when that is known", () => {
    const { window } = loadApp();
    const since = NOW_S - 3600;
    const shown = textOf(seed(window, subscription({ watched_since: since })));
    expect(shown).toContain(window.eval(`t('calendar.subscribe.fetched.since', { date: formatEpoch(${since}) })`));
    expect(shown).not.toContain(window.eval("t('calendar.subscribe.fetched.never')"));
  });

  test("without any known start it falls back to the plain sentence", () => {
    const { window } = loadApp();
    const shown = textOf(seed(window, subscription({ created_at: 0 })));
    expect(shown).toContain(window.eval("t('calendar.subscribe.fetched.never')"));
  });

  test("a fetched link names the date and how long ago it was", () => {
    const { window } = loadApp();
    const stamp = NOW_S - 3 * 3600;
    const shown = textOf(seed(window, subscription({ last_fetched_at: stamp, watched_since: NOW_S - 86400 })));
    expect(shown).toContain(
      window.eval(`t('calendar.subscribe.fetched', { date: formatEpoch(${stamp}), when: 'vor 3 Stunden' })`)
    );
  });
});

describe("[P255] the screen names the one-time setting that makes changes arrive on their own", () => {
  test("anywhere it names the calendar app's own refresh setting", () => {
    const { window } = loadApp();
    const shown = textOf(seed(window, subscription()));
    expect(shown).toContain(window.eval("t('calendar.subscribe.refresh')"));
  });

  test("on an iPhone it names the iPhone setting instead", () => {
    const { window } = loadApp();
    Object.defineProperty(window.navigator, "userAgent", { value: IPHONE_UA, configurable: true });
    const shown = textOf(seed(window, subscription()));
    expect(shown).toContain(window.eval("t('calendar.subscribe.refresh.apple')"));
    expect(shown).not.toContain(window.eval("t('calendar.subscribe.refresh')"));
  });
});

describe("[P253] relativeSince names the distance in the reader's language", () => {
  function since(window, seconds) {
    window.Date.now = () => NOW_MS;
    return window.eval(`(function (s) { return relativeSince(s); })`)(NOW_S - seconds);
  }

  test("seconds, minutes, hours and days each get their own unit", () => {
    const { window } = loadApp();
    expect(since(window, 30)).toContain("Sekunden");
    expect(since(window, 20 * 60)).toContain("Minuten");
    expect(since(window, 5 * 3600)).toContain("Stunden");
    expect(since(window, 3 * 86400)).toContain("Tagen");
  });

  test("a missing or future stamp never reads as a negative age", () => {
    const { window } = loadApp();
    window.Date.now = () => NOW_MS;
    expect(window.eval("relativeSince(0)")).toBe("");
    expect(since(window, -600)).not.toContain("-");
  });
});
