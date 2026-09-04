import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const READY = `
  state.children = [{ child_id: "c1", name: "Alice", class_name: "3b" }];
  state.childId = "c1";
  state.weekOffset = 0;
  state.me = { forename: "Alice" };
  state.timetable = { lessons: [{ day_of_week: 2, period: 1, start_time: "08:00", subject_code: "D" }], period_times: {} };
  state.letters = { letters: [], tab: "current" };
  state.pinboard = { folders: [], feed: [] };
  state.conferences = { items: [] };
  state.absence = { data: { entries: [], children: [] } };
  state.messengerRooms = { rooms: [], self_user_id: "@me" };
`;

function renderOverview(window, seed) {
  const run = window.eval(`
    (function (seed) {
      ${READY}
      window.eval(seed);
      return overviewView();
    })
  `);
  return run(seed || "");
}

function areas(view) {
  return [...view.querySelectorAll(".panel")].map((panel) => panel.dataset.area);
}

function futureAbsence(window) {
  const iso = window.eval("isoDate(addDays(new Date(), 3))");
  return `state.absence = { data: { entries: [{ id: "a1", from_date: "${iso}", till_date: "${iso}", kind: "sick", status: "accepted" }], children: [] } };`;
}

describe("[R2-13] the frozen order waits for every chapter that takes part in it", () => {
  test("upcoming that only resolves after letters/pinboard/chat still lands directly behind Heute", () => {
    const { window } = loadApp();
    renderOverview(window, "state.conferences = null; state.absence = null;");
    expect(window.eval("state._overviewOrder")).toBe(null);

    const view = renderOverview(window, futureAbsence(window));
    expect(areas(view)[0]).toBe("today");
    expect(areas(view)[1]).toBe("upcoming");
  });

  test("the order does not freeze while the upcoming sources are still unknown", () => {
    const { window } = loadApp();
    renderOverview(window, "state.conferences = null;");
    expect(window.eval("state._overviewOrder")).toBe(null);
    renderOverview(window, "state.absence = null;");
    expect(window.eval("state._overviewOrder")).toBe(null);
  });

  test("once everything is loaded the order freezes exactly once", () => {
    const { window } = loadApp();
    renderOverview(window);
    const first = window.eval("JSON.stringify(state._overviewOrder)");
    expect(first).not.toBe("null");
    renderOverview(window, 'state.pinboard = { folders: [], feed: [{ id: "p1", unread: true, title: "Neu" }] };');
    expect(window.eval("JSON.stringify(state._overviewOrder)")).toBe(first);
  });
});

describe("[R2-14] leaving the overview into a letter remembers the panel that was left", () => {
  test("openLetterFromOverview captures the anchor before it navigates away", () => {
    const { window } = loadApp();
    renderOverview(window);
    window.eval("state._overviewAnchor = null; rememberOverviewAnchor = function () { state.__remembered = true; };");
    window.eval('openLetterFromOverview({ letter_id: "l1", recipient_id: "r1", title: "Brief" });');
    expect(window.eval("state.__remembered")).toBe(true);
  });

  test("the capture happens before the view switches, not after", () => {
    const { window } = loadApp();
    renderOverview(window);
    window.eval(`
      state.__order = [];
      rememberOverviewAnchor = function () { state.__order.push("anchor"); };
      const realSetView = setView;
      setView = function (name, options) { state.__order.push("view:" + name); };
    `);
    window.eval('openLetterFromOverview({ letter_id: "l1", recipient_id: "r1", title: "Brief" });');
    expect(window.eval("JSON.stringify(state.__order)")).toBe('["anchor","view:post"]');
  });
});

describe("[R2-15] the retry in a letter keeps the way back to the overview", () => {
  test("a retry after a failed detail keeps the overview origin", () => {
    const { window } = loadApp();
    window.eval(`
      state.letterDetail = { letter: { letter_id: "l1", recipient_id: "r1", title: "Brief" }, error: "network", origin: "overview" };
      state.__openedWith = "unset";
      openLetter = function (letter, origin) { state.__openedWith = String(origin); };
    `);
    const view = window.eval("letterDetailView()");
    view.querySelector(".empty button").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    expect(window.eval("state.__openedWith")).toBe("overview");
  });

  test("a letter opened from the Post tab keeps having no origin after a retry", () => {
    const { window } = loadApp();
    window.eval(`
      state.letterDetail = { letter: { letter_id: "l1", recipient_id: "r1", title: "Brief" }, error: "network", origin: null };
      state.__openedWith = "unset";
      openLetter = function (letter, origin) { state.__openedWith = String(origin); };
    `);
    const view = window.eval("letterDetailView()");
    view.querySelector(".empty button").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    expect(window.eval("state.__openedWith")).toBe("null");
  });
});

describe("[R2-16] a failed chat load is shown, not swallowed", () => {
  test("the chat chapter appears with a failure block and a retry", () => {
    const { window } = loadApp();
    const view = renderOverview(window, 'state.messengerRooms = { error: "network" };');
    expect(areas(view)).toContain("messenger");
    const panel = view.querySelector('.panel[data-area="messenger"]');
    expect(panel.querySelector(".overview-failed")).toBeTruthy();
    expect(panel.querySelector(".overview-failed button")).toBeTruthy();
  });

  test("a healthy but empty chat list still hides the chapter", () => {
    const { window } = loadApp();
    const view = renderOverview(window, 'state.messengerRooms = { rooms: [] };');
    expect(areas(view)).not.toContain("messenger");
  });
});

describe("[R2-17] the letters chapter never renders a folder the counter does not count", () => {
  test("archive data does not masquerade as the unread current letters", () => {
    const { window } = loadApp();
    const view = renderOverview(
      window,
      'state.letters = { tab: "archive", letters: [{ letter_id: "a1", recipient_id: "r1", title: "Alt", unread: true }] };'
    );
    const panel = view.querySelector('.panel[data-area="letters"]');
    expect(panel.querySelector(".loading")).toBeTruthy();
    expect(panel.textContent).not.toContain("Alt");
  });

  test("current data renders as before", () => {
    const { window } = loadApp();
    const view = renderOverview(
      window,
      'state.letters = { tab: "current", letters: [{ letter_id: "c1", recipient_id: "r1", title: "Neuer Brief", unread: true }] };'
    );
    const panel = view.querySelector('.panel[data-area="letters"]');
    expect(panel.textContent).toContain("Neuer Brief");
  });
});

describe("[R2-18] the noticeboard does not re-sort under the reader's thumb", () => {
  test("a post that becomes read keeps its place for the rest of the visit", () => {
    const { window } = loadApp();
    const feed = '[{ id: "p1", unread: true, title: "Eins" }, { id: "p2", unread: true, title: "Zwei" }, { id: "p3", unread: false, title: "Drei" }]';
    renderOverview(window, `state.pinboard = { folders: [], feed: ${feed} };`);
    const before = window.eval("JSON.stringify(state._overviewPinboardOrder)");
    expect(before).toBe('["p1","p2","p3"]');

    const view = renderOverview(
      window,
      'state.pinboard = { folders: [], feed: [{ id: "p1", unread: false, title: "Eins" }, { id: "p2", unread: true, title: "Zwei" }, { id: "p3", unread: false, title: "Drei" }] };'
    );
    const keys = [...view.querySelectorAll('.panel[data-area="pinboard"] [data-block]')].map((node) => node.dataset.block);
    expect(keys.slice(0, 3)).toEqual(["post:p1", "post:p2", "post:p3"]);
  });

  test("entering the overview again re-sorts unread first", () => {
    const { window } = loadApp();
    renderOverview(window, 'state.pinboard = { folders: [], feed: [{ id: "p1", unread: true, title: "Eins" }, { id: "p2", unread: false, title: "Zwei" }] };');
    expect(window.eval("JSON.stringify(state._overviewPinboardOrder)")).toBe('["p1","p2"]');

    window.eval('state.pinboard = { folders: [], feed: [{ id: "p1", unread: false, title: "Eins" }, { id: "p2", unread: true, title: "Zwei" }] };');
    window.eval('state.view = "settings"; setView("overview");');
    expect(window.eval("JSON.stringify(state._overviewPinboardOrder)")).toBe('["p2","p1"]');
  });
});
