import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function touchEvent(window, type, y) {
  const event = new window.Event(type, { bubbles: true, cancelable: true });
  event.touches = [{ clientY: y }];
  return event;
}

function mouseEvent(window, type, y) {
  return new window.MouseEvent(type, { bubbles: true, cancelable: true, clientY: y });
}

function makeScreen(window) {
  return window.eval(`
    (function () {
      const screen = document.createElement("div");
      screen.className = "screen";
      document.body.appendChild(screen);
      setupPullToRefresh(screen);
      return screen;
    })();
  `);
}

describe("[P121] pull-to-refresh: shared touch mechanism on .screen", () => {
  test("pulling past the 70px threshold at scrollTop 0 triggers a reload via refreshActiveView", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 0;
    screen.dispatchEvent(touchEvent(window, "touchstart", 0));
    screen.dispatchEvent(touchEvent(window, "touchmove", 90));
    screen.dispatchEvent(touchEvent(window, "touchend", 90));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(1);
  });

  test("pulling below the threshold releases without triggering a reload", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 0;
    screen.dispatchEvent(touchEvent(window, "touchstart", 0));
    screen.dispatchEvent(touchEvent(window, "touchmove", 30));
    screen.dispatchEvent(touchEvent(window, "touchend", 30));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("does not fire while a sheet is open", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
      state.sheet = () => document.createElement("div");
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 0;
    screen.dispatchEvent(touchEvent(window, "touchstart", 0));
    screen.dispatchEvent(touchEvent(window, "touchmove", 90));
    screen.dispatchEvent(touchEvent(window, "touchend", 90));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("does not fire while an absence form is open", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
      state.absenceForm = { type: "sick" };
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 0;
    screen.dispatchEvent(touchEvent(window, "touchstart", 0));
    screen.dispatchEvent(touchEvent(window, "touchmove", 90));
    screen.dispatchEvent(touchEvent(window, "touchend", 90));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("does not fire for mouse drag events — touch only", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 0;
    screen.dispatchEvent(mouseEvent(window, "mousedown", 0));
    screen.dispatchEvent(mouseEvent(window, "mousemove", 90));
    screen.dispatchEvent(mouseEvent(window, "mouseup", 90));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(0);
  });

  test("does not fire when the screen is already scrolled (scrollTop > 0)", async () => {
    const { window } = loadApp();
    window.eval(`
      window.__calls = 0;
      loadPinboard = () => { window.__calls += 1; return Promise.resolve(); };
      state.view = "pinboard";
    `);
    const screen = makeScreen(window);
    screen.scrollTop = 40;
    screen.dispatchEvent(touchEvent(window, "touchstart", 0));
    screen.dispatchEvent(touchEvent(window, "touchmove", 90));
    screen.dispatchEvent(touchEvent(window, "touchend", 90));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(window.eval("window.__calls")).toBe(0);
  });
});
