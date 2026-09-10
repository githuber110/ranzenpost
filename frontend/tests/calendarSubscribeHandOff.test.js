import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function asWebView(window) {
  Object.defineProperty(window.navigator, "userAgent", {
    value: "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36 homeassistant",
    configurable: true,
  });
}

function seed(window) {
  window.eval(`
    state.calendar = { data: { host: "homeassistant.local", port: 8100, port_open: true, supervisor: true, host_source: "internal_url" } };
    state.config = { children: [] };
  `);
}

const SUBSCRIPTION = {
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
};

function actions(window) {
  seed(window);
  return window.eval(`(function (s, c) { return calendarActions(s, c); })`)(SUBSCRIPTION, {
    child_id: "c1",
    name: "Mia",
  });
}

function buttonTexts(nodes) {
  const found = [];
  for (const node of nodes) {
    if (node.classList && node.classList.contains("btn")) found.push(node.textContent);
    for (const inner of node.querySelectorAll ? node.querySelectorAll(".btn") : []) found.push(inner.textContent);
  }
  return found;
}

function onScreen(window, focused) {
  Object.defineProperty(window.document, "hidden", { value: false, configurable: true });
  Object.defineProperty(window.document, "visibilityState", { value: "visible", configurable: true });
  window.document.hasFocus = () => focused;
}

function trackNavigation(window) {
  const opened = [];
  window.HTMLAnchorElement.prototype.click = function click() {
    opened.push(this.getAttribute("href"));
  };
  return opened;
}

describe("[P255] the companion app never offers the hand-off it swallows", () => {
  test("no subscribe button, copying leads", () => {
    const { window } = loadApp();
    asWebView(window);
    const labels = buttonTexts(actions(window));
    expect(labels).not.toContain(window.eval("t('calendar.subscribe.add')"));
    expect(labels[0]).toContain(window.eval("t('calendar.subscribe.copy')"));
  });

  test("copying and the manual steps stay available", () => {
    const { window } = loadApp();
    asWebView(window);
    const nodes = actions(window);
    expect(buttonTexts(nodes).join(" ")).toContain(window.eval("t('calendar.subscribe.copy')"));
    expect(nodes.some((node) => node.querySelector && node.querySelector(".cal-step-list"))).toBe(true);
  });
});

describe("[P254] a hand-off that goes nowhere says what to do instead", () => {
  test("the browser button hands the address over through a link, not a page navigation", () => {
    const { window } = loadApp();
    const opened = trackNavigation(window);
    const nodes = actions(window);
    const add = nodes.find((node) => node.classList && node.classList.contains("cal-add"));
    add.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    expect(opened).toEqual(["webcal://homeassistant.local:8100/calendar/t.ics"]);
  });

  test("when the page keeps the focus afterwards, a way out appears", async () => {
    const { window } = loadApp();
    trackNavigation(window);
    onScreen(window, true);
    const nodes = actions(window);
    const add = nodes.find((node) => node.classList && node.classList.contains("cal-add"));
    add.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 2200));
    expect(window.eval("state.calendarHandOffStalled")).toBe("s1");
    const after = actions(window);
    expect(after.map((node) => node.textContent).join(" ")).toContain(
      window.eval("t('calendar.subscribe.add.stalled.title')")
    );
  });

  test("when another app took the focus, no such note appears", async () => {
    const { window } = loadApp();
    trackNavigation(window);
    onScreen(window, false);
    const nodes = actions(window);
    const add = nodes.find((node) => node.classList && node.classList.contains("cal-add"));
    add.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 2200));
    expect(window.eval("state.calendarHandOffStalled")).toBeNull();
  });
});
