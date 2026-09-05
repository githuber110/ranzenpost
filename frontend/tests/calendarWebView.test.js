import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const SUBSCRIPTION = {
  id: "sub-1",
  child_id: "c1",
  label: "3b",
  components: ["timetable"],
  color: "#135859",
  token: "token-1",
  path: "/calendar/token-1.ics",
};

const SAFARI_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
  + "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const COMPANION_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
  + "(KHTML, like Gecko) Mobile/15E148 Home Assistant/2026.8 (io.robbie.HomeAssistant; build:1)";
const ANDROID_WEBVIEW_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP1A; wv) AppleWebKit/537.36 "
  + "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36";

function actionsFor(agent) {
  const { window } = loadApp();
  Object.defineProperty(window.navigator, "userAgent", { value: agent, configurable: true });
  window.eval(`
    state.children = [{ child_id: "c1", name: "Mia", class_name: "3b" }];
    state.childId = "c1";
    state.calendar = { data: {
      subscriptions: [],
      components: ["timetable"],
      path_template: "/calendar/{token}.ics",
      port: 8100,
      host: "10.10.2.2",
      host_source: "config_entry",
      supervisor: true,
      port_open: true,
      mapped_port: 8100,
    } };
  `);
  const host = window.document.createElement("div");
  const run = window.eval("(function (sub) { return calendarActions(sub, null); })");
  for (const node of run(SUBSCRIPTION)) host.append(node);
  return { window, host };
}

describe("[P225] the subscription path fits the device it is shown on", () => {
  test("a real browser keeps the direct webcal button", () => {
    const { window, host } = actionsFor(SAFARI_UA);
    const add = host.querySelector(".cal-add");
    expect(add).not.toBeNull();
    expect(add.textContent).toContain(window.eval('t("calendar.subscribe.add")'));
    expect(host.querySelector(".cal-copy-primary")).toBeNull();
    expect(host.querySelector(".cal-webview")).toBeNull();
    expect(host.querySelector(".cal-copy")).not.toBeNull();
  });

  test("the companion web view leads with copying and a two step instruction", () => {
    const { window, host } = actionsFor(COMPANION_UA);
    const copy = host.querySelector(".cal-copy-primary");
    expect(copy).not.toBeNull();
    expect(copy.textContent).toContain(window.eval('t("calendar.subscribe.copy")'));
    const steps = host.querySelector(".cal-webview");
    expect(steps).not.toBeNull();
    expect([...steps.querySelectorAll("li")].map((node) => node.textContent)).toEqual([
      window.eval('t("calendar.subscribe.webview.step1")'),
      window.eval('t("calendar.subscribe.webview.step2")'),
    ]);
    expect(steps.textContent).toContain(window.eval('t("calendar.subscribe.webview.hint")'));
  });

  test("the web view never offers the dead webcal handoff", () => {
    const { window, host } = actionsFor(COMPANION_UA);
    const buttons = [...host.querySelectorAll("button")].map((node) => node.textContent);
    expect(buttons).not.toContain(window.eval('t("calendar.subscribe.add")'));
  });

  test("an android web view is recognised as one as well", () => {
    const { host } = actionsFor(ANDROID_WEBVIEW_UA);
    expect(host.querySelector(".cal-copy-primary")).not.toBeNull();
  });

  test("an android web view is never told to open the address in safari", () => {
    const { window, host } = actionsFor(ANDROID_WEBVIEW_UA);
    const steps = host.querySelector(".cal-webview");
    expect(steps).not.toBeNull();
    const first = steps.querySelector("li").textContent;
    expect(first).toBe(window.eval('t("calendar.subscribe.webview.step1Other")'));
    expect(first).not.toContain("Safari");
  });

  test("without a reachable address the web view shows no dead copy button", () => {
    const { window } = loadApp();
    Object.defineProperty(window.navigator, "userAgent", { value: COMPANION_UA, configurable: true });
    window.eval(`
      state.children = [{ child_id: "c1", name: "Mia", class_name: "3b" }];
      state.childId = "c1";
      state.calendar = { data: {
        subscriptions: [],
        components: ["timetable"],
        path_template: "/calendar/{token}.ics",
        port: 8100,
        host: "",
        host_source: "",
        supervisor: true,
        port_open: true,
        mapped_port: 8100,
      } };
    `);
    const host = window.document.createElement("div");
    const run = window.eval("(function (sub) { return calendarActions(sub, null); })");
    for (const node of run(SUBSCRIPTION)) host.append(node);
    expect(host.querySelector(".cal-copy-primary")).toBeNull();
    expect(host.querySelector(".cal-webview")).toBeNull();
    expect(host.textContent).toContain(window.eval('t("calendar.subscribe.host.missing")'));
  });

  test("a bare wkwebview without a companion signature is caught too", () => {
    const bare =
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
      + "(KHTML, like Gecko) Mobile/15E148";
    const { host } = actionsFor(bare);
    expect(host.querySelector(".cal-copy-primary")).not.toBeNull();
  });

  test("a desktop browser is never mistaken for a web view", () => {
    const desktop =
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      + "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";
    const { host } = actionsFor(desktop);
    expect(host.querySelector(".cal-copy-primary")).toBeNull();
    expect(host.querySelector(".cal-add")).not.toBeNull();
  });
});
