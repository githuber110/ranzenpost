import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const WEEK = {
  lessons: [{ day_of_week: 1, period: 1, subject_code: "D", start_time: "08:00" }],
  period_times: { 1: "08:00" },
};

function prepare(window, offset) {
  const run = window.eval(`
    (function (week, offset) {
      state.timetable = week;
      state.weekOffset = offset;
      state.config = { period_times: week.period_times };
      state.shifted = [];
      shiftWeek = function (step) { state.shifted.push(step); };
      return timetableGrid(week);
    })
  `);
  return run(WEEK, offset);
}

function touch(clientX, clientY) {
  return { clientX, clientY };
}

function swipe(window, grid, from, to) {
  const start = new window.Event("touchstart", { bubbles: true });
  start.touches = [touch(from[0], from[1])];
  grid.dispatchEvent(start);
  const move = new window.Event("touchmove", { bubbles: true });
  move.touches = [touch(to[0], to[1])];
  grid.dispatchEvent(move);
  const end = new window.Event("touchend", { bubbles: true });
  end.changedTouches = [touch(to[0], to[1])];
  grid.dispatchEvent(end);
}

function shifted(window) {
  return window.eval("state.shifted");
}

describe("[P205] swiping the grid pages through the weeks", () => {
  test("a clear swipe towards the past goes back one week", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    swipe(window, grid, [60, 300], [240, 306]);
    expect(shifted(window)).toEqual([-1]);
  });

  test("a clear swipe towards the future goes forward one week", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    swipe(window, grid, [240, 300], [60, 306]);
    expect(shifted(window)).toEqual([1]);
  });

  test("on the current week the past direction is refused", () => {
    const { window } = loadApp();
    const grid = prepare(window, 0);
    swipe(window, grid, [60, 300], [240, 306]);
    expect(shifted(window)).toEqual([]);
  });

  test("on the last loadable week the future direction is refused", () => {
    const { window } = loadApp();
    const grid = prepare(window, 8);
    swipe(window, grid, [240, 300], [60, 306]);
    expect(shifted(window)).toEqual([]);
  });

  test("a short drag is a tap, not a swipe", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    swipe(window, grid, [200, 300], [212, 302]);
    expect(shifted(window)).toEqual([]);
  });

  test("a mostly vertical drag stays a scroll", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    swipe(window, grid, [200, 300], [140, 520]);
    expect(shifted(window)).toEqual([]);
  });
});

describe("[P205] the edge arrows only promise what is possible", () => {
  test("the current week offers the future arrow only", () => {
    const { window } = loadApp();
    const arrows = window.eval("state.weekOffset = 0; [!!weekSwipeHint(-1, 'a'), !!weekSwipeHint(1, 'b')]");
    expect(arrows).toEqual([false, true]);
  });

  test("a middle week offers both", () => {
    const { window } = loadApp();
    const arrows = window.eval("state.weekOffset = 4; [!!weekSwipeHint(-1, 'a'), !!weekSwipeHint(1, 'b')]");
    expect(arrows).toEqual([true, true]);
  });

  test("the last week offers the past arrow only", () => {
    const { window } = loadApp();
    const arrows = window.eval("state.weekOffset = 8; [!!weekSwipeHint(-1, 'a'), !!weekSwipeHint(1, 'b')]");
    expect(arrows).toEqual([true, false]);
  });

  test("the arrows never take a tap away from the grid", () => {
    const { window } = loadApp();
    const hint = window.eval("state.weekOffset = 4; weekSwipeHint(1, 'tt-edge-next')");
    expect(hint.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("[R2-20] a nudge of jitter must not kill the swipe", () => {
  function jitterThenSwipe(window, grid, jitter, to) {
    const start = new window.Event("touchstart", { bubbles: true });
    start.touches = [{ clientX: 200, clientY: 300 }];
    grid.dispatchEvent(start);
    const nudge = new window.Event("touchmove", { bubbles: true });
    nudge.touches = [{ clientX: 200 + jitter[0], clientY: 300 + jitter[1] }];
    grid.dispatchEvent(nudge);
    const move = new window.Event("touchmove", { bubbles: true });
    move.touches = [{ clientX: to[0], clientY: to[1] }];
    grid.dispatchEvent(move);
    const end = new window.Event("touchend", { bubbles: true });
    end.changedTouches = [{ clientX: to[0], clientY: to[1] }];
    grid.dispatchEvent(end);
  }

  test("3px down / 2px right at the start does not cancel a clean horizontal swipe", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    jitterThenSwipe(window, grid, [2, 3], [50, 306]);
    expect(shifted(window)).toEqual([1]);
  });

  test("a slight thumb arc still resolves as a swipe", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    jitterThenSwipe(window, grid, [4, 6], [60, 320]);
    expect(shifted(window)).toEqual([1]);
  });

  test("a decisively vertical drag still cancels the swipe", () => {
    const { window } = loadApp();
    const grid = prepare(window, 3);
    jitterThenSwipe(window, grid, [4, 40], [140, 520]);
    expect(shifted(window)).toEqual([]);
  });
});

describe("[R2-21] pull-to-refresh keeps out of horizontal gestures", () => {
  function pull(window, screen, from, to) {
    const start = new window.Event("touchstart", { bubbles: true });
    start.touches = [{ clientX: from[0], clientY: from[1] }];
    screen.dispatchEvent(start);
    const move = new window.Event("touchmove", { bubbles: true });
    move.touches = [{ clientX: to[0], clientY: to[1] }];
    screen.dispatchEvent(move);
  }

  function armedScreen(window) {
    const screen = window.document.createElement("div");
    Object.defineProperty(screen, "scrollTop", { value: 0, writable: true });
    window.document.body.append(screen);
    window.eval("state.view = 'timetable';");
    const setup = window.eval("setupPullToRefresh");
    setup(screen);
    return screen;
  }

  test("a mostly horizontal drag never grows the indicator", () => {
    const { window } = loadApp();
    const screen = armedScreen(window);
    pull(window, screen, [240, 300], [110, 340]);
    expect(screen.querySelector(".pull-indicator")).toBeNull();
  });

  test("the diagonal that satisfied both detectors no longer arms the refresh", () => {
    const { window } = loadApp();
    const screen = armedScreen(window);
    pull(window, screen, [240, 300], [110, 375]);
    const indicator = screen.querySelector(".pull-indicator");
    expect(indicator === null || !indicator.classList.contains("armed")).toBe(true);
  });

  test("a straight downward pull still arms as before", () => {
    const { window } = loadApp();
    const screen = armedScreen(window);
    pull(window, screen, [200, 100], [204, 260]);
    const indicator = screen.querySelector(".pull-indicator");
    expect(indicator).not.toBeNull();
    expect(indicator.classList.contains("armed")).toBe(true);
  });
});
