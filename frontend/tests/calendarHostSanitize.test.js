import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const SUBSCRIPTION = { id: "sub-1", path: "/calendar/token-1.ics" };

const CASES = [
  ["10.10.2.2:8123", "10.10.2.2"],
  ["example.local", "example.local"],
  ["http://homeassistant.local:8123/lovelace", "homeassistant.local"],
  ["webcal://host/x.ics", "host"],
  ["[fd00::1]:8123", "fd00::1"],
  ["fd00::1", "fd00::1"],
  ["example.local.", "example.local"],
  ["EXAMPLE.LOCAL", "example.local"],
  ["", ""],
  ["   ", ""],
];

describe("[P214] sanitizeCalendarHost", () => {
  test.each(CASES)("%s -> %s", (input, expected) => {
    const { window } = loadApp();
    expect(window.eval(`sanitizeCalendarHost(${JSON.stringify(input)})`)).toBe(expected);
  });

  test("a bare IPv6 host is not truncated at its first colon", () => {
    const { window } = loadApp();
    expect(window.eval('sanitizeCalendarHost("fd00::1")')).toBe("fd00::1");
  });

  test("the regression host composes a feed URL with exactly one port", () => {
    const { window } = loadApp();
    window.eval(
      `state.calendar = { data: { host: "10.10.2.2:8123", port: 8100, subscriptions: [] }, error: false };`
    );
    const url = window.eval(`calendarFeedUrl(${JSON.stringify(SUBSCRIPTION)}, "http")`);

    expect(url).toBe("http://10.10.2.2:8100/calendar/token-1.ics");
    expect((url.match(/:\d+/g) || [])).toHaveLength(1);
  });
  test("[P214] an IPv6 host gets its brackets back in the composed feed URL", () => {
    const { window } = loadApp();
    window.eval(
      `state.calendar = { data: { host: "[fd00::1]", port: 8100, subscriptions: [] }, error: false };`
    );
    const url = window.eval(`calendarFeedUrl(${JSON.stringify(SUBSCRIPTION)}, "webcal")`);

    expect(url).toBe("webcal://[fd00::1]:8100/calendar/token-1.ics");
    expect(() => new URL(url.replace("webcal:", "http:"))).not.toThrow();
    expect(new URL(url.replace("webcal:", "http:")).port).toBe("8100");
  });

  test("[P214] an IPv4 host keeps its plain form, no stray brackets", () => {
    const { window } = loadApp();
    window.eval(
      `state.calendar = { data: { host: "10.10.2.2", port: 8100, subscriptions: [] }, error: false };`
    );
    const url = window.eval(`calendarFeedUrl(${JSON.stringify(SUBSCRIPTION)}, "http")`);

    expect(url).toBe("http://10.10.2.2:8100/calendar/token-1.ics");
    expect(url).not.toContain("[");
  });
});

describe("[P214] the fallback host never overrules a host the browser can actually reach", () => {
  function withHost(hostname, data) {
    const { window } = loadApp({ url: `http://${hostname}/` });
    window.eval(
      `state.calendar = { data: ${JSON.stringify(Object.assign({ port: 8100, subscriptions: [] }, data))}, error: false };`
    );
    return window;
  }

  test("host_source 'fallback' yields to the address this page was opened from", () => {
    const window = withHost("10.10.2.2", { host: "homeassistant.local", host_source: "fallback" });
    expect(window.eval("calendarHost()")).toBe("10.10.2.2");
  });

  test("a resolved internal_url still wins over the browser host", () => {
    const window = withHost("10.10.2.2", { host: "ha.example", host_source: "internal_url" });
    expect(window.eval("calendarHost()")).toBe("ha.example");
  });

  test("on a fallback with an unusable browser host the default is still used", () => {
    const window = withHost("localhost", { host: "homeassistant.local", host_source: "fallback" });
    expect(window.eval("calendarHost()")).toBe("homeassistant.local");
  });

  test("on a fallback from a Nabu Casa session the default is used, never the remote host", () => {
    const window = withHost("abc123.ui.nabu.casa", { host: "homeassistant.local", host_source: "fallback" });
    expect(window.eval("calendarHost()")).toBe("homeassistant.local");
  });

  test("on a fallback a stored legacy host beats the default when the browser host is unusable", () => {
    const window = withHost("localhost", { host: "homeassistant.local", host_source: "fallback" });
    window.eval('writeStoredText("calendarHost", "http://10.0.0.5:8123/lovelace");');
    expect(window.eval("calendarHost()")).toBe("10.0.0.5");
  });
});
