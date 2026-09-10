import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const NOW_MS = Date.UTC(2026, 8, 10, 12, 0, 0);

function seed(window, subscription) {
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
    },
    extra || {}
  );
}

describe("[P253] the subscribe screen shows whether a calendar app ever fetched", () => {
  test("a link nobody has fetched says so instead of staying silent", () => {
    const { window } = loadApp();
    const nodes = seed(window, subscription());
    expect(textOf(nodes)).toContain(window.eval("t('calendar.subscribe.fetched.never')"));
  });

  test("a fetched link names how long ago that was", () => {
    const { window } = loadApp();
    window.Date.now = () => NOW_MS;
    const nodes = seed(window, subscription({ last_fetched_at: Math.floor(NOW_MS / 1000) - 3 * 3600 }));
    const shown = textOf(nodes);
    expect(shown).toContain(window.eval("t('calendar.subscribe.fetched', { when: 'vor 3 Stunden' })"));
    expect(shown).not.toContain(window.eval("t('calendar.subscribe.fetched.never')"));
  });

  test("the screen says that the calendar app decides when changes arrive", () => {
    const { window } = loadApp();
    const nodes = seed(window, subscription());
    expect(textOf(nodes)).toContain(window.eval("t('calendar.subscribe.refresh')"));
  });
});

describe("[P253] relativeSince names the distance in the reader's language", () => {
  function since(window, seconds) {
    window.Date.now = () => NOW_MS;
    return window.eval(`(function (s) { return relativeSince(s); })`)(Math.floor(NOW_MS / 1000) - seconds);
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
