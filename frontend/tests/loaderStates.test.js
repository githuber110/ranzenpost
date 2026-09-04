import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

function routeFetch(window, routes) {
  window.fetch = (input) => {
    const url = String(input);
    for (const [fragment, reply] of routes) {
      if (url.includes(fragment)) return reply(url);
    }
    return Promise.reject(new Error(`unrouted ${url}`));
  };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await settle();
  window.clearTimeout(window.eval("bootWatchdog"));
}

const LOADERS = [
  {
    name: "letters",
    route: "api/letters?tab=",
    good: { letters: [{ letter_id: "1", recipient_id: "1", title: "Klassenfahrt", unread: false }] },
    view: "post",
    seed: "state.postTab = 'letters'; state.lettersTab = 'current';",
    call: "loadLetters('current')",
    stock: "Klassenfahrt",
    errorTitle: "letters.error.title",
    reset: "state.letters = null;",
  },
  {
    name: "pinboard",
    route: "api/pinboard",
    good: { feed: [{ id: 7, title: "Sommerfest", unread: false }], folders: [] },
    view: "post",
    seed: "state.postTab = 'pinboard';",
    call: "loadPinboard()",
    stock: "Sommerfest",
    errorTitle: "pinboard.error.title",
    reset: "state.pinboard = null;",
  },
  {
    name: "timetable",
    route: "api/timetable?child_id=",
    good: { lessons: [{ day_of_week: 1, period: 1, subject_label: "Mathe" }] },
    view: "timetable",
    seed: "state.childId = 'c1'; state.children = [{ child_id: 'c1', name: 'Alex' }]; state.timetableAvailable = true;",
    call: "reloadTimetable()",
    stock: "Mathe",
    errorTitle: "timetable.error.title",
    reset: "state.timetable = null;",
  },
];

describe("[W8] every loader tells the truth about first load, refresh and retry", () => {
  for (const loader of LOADERS) {
    test(`${loader.name}: a failed first load shows the error state with a retry button`, async () => {
      const { window, document } = loadApp();
      await quiet(window);
      window.eval(`state.view = "${loader.view}"; ${loader.seed} ${loader.reset}`);
      routeFetch(window, [
        [loader.route, () => Promise.reject(new Error("offline"))],
        ["api/config", () => jsonResponse({})],
      ]);
      await window.eval(loader.call);
      await settle();

      const text = document.getElementById("app").textContent;
      expect(text).toContain(window.eval(`t("${loader.errorTitle}")`));
      const retry = [...document.querySelectorAll("button")].find(
        (node) => node.textContent.trim() === window.eval('t("common.retry")')
      );
      expect(retry).toBeTruthy();
    });

    test(`${loader.name}: a failed refresh keeps the stock that is already on screen`, async () => {
      const { window, document } = loadApp();
      await quiet(window);
      window.eval(`state.view = "${loader.view}"; ${loader.seed}`);
      routeFetch(window, [
        [loader.route, () => jsonResponse(loader.good)],
        ["api/config", () => jsonResponse({})],
      ]);
      await window.eval(loader.call);
      await settle();
      expect(document.getElementById("app").textContent).toContain(loader.stock);

      routeFetch(window, [
        [loader.route, () => Promise.reject(new Error("offline"))],
        ["api/config", () => jsonResponse({})],
      ]);
      await window.eval(loader.call);
      await settle();

      const text = document.getElementById("app").textContent;
      expect(text).toContain(loader.stock);
      expect(text).not.toContain(window.eval(`t("${loader.errorTitle}")`));
      expect(text).toContain(window.eval('t("common.refreshFailed")'));
      expect(document.querySelector(".stamp.warn")).not.toBeNull();
    });

    test(`${loader.name}: the retry button drops the stale error and shows a loading state`, async () => {
      const { window, document } = loadApp();
      await quiet(window);
      window.eval(`state.view = "${loader.view}"; ${loader.seed} ${loader.reset}`);
      routeFetch(window, [
        [loader.route, () => Promise.reject(new Error("offline"))],
        ["api/config", () => jsonResponse({})],
      ]);
      await window.eval(loader.call);
      await settle();

      const retry = [...document.querySelectorAll("button")].find(
        (node) => node.textContent.trim() === window.eval('t("common.retry")')
      );
      let pending = null;
      routeFetch(window, [
        [loader.route, () => new Promise((resolve) => { pending = resolve; })],
        ["api/config", () => jsonResponse({})],
      ]);
      retry.click();

      const text = document.getElementById("app").textContent;
      expect(text).toContain(window.eval('t("common.loading")'));
      expect(text).not.toContain(window.eval(`t("${loader.errorTitle}")`));
      if (pending) pending(jsonResponse(loader.good));
    });
  }
});

describe("[W6c] one error switch decides where a failure lands", () => {
  test("auth_failed from any loader shows the reconnect screen, not a network empty state", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.view = 'post'; state.postTab = 'letters'; state.account = 'erika'; state.letters = null;");
    routeFetch(window, [["api/letters", () => jsonResponse({ error: "auth_failed" })]]);

    await window.eval("loadLetters('current')");
    await new Promise((resolve) => setTimeout(resolve, 0));

    const text = document.getElementById("app").textContent;
    expect(text).toContain(window.eval('t("account.reconnect.title")'));
    expect(text).not.toContain(window.eval('t("letters.error.title")'));

    window.eval("rerender()");
    expect(document.getElementById("app").textContent).toContain(
      window.eval('t("account.reconnect.title")')
    );
  });

  test("not_configured from any loader starts the wizard", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.view = 'pinboard'; state.pinboard = null;");
    routeFetch(window, [
      ["api/pinboard", () => jsonResponse({ error: "not_configured" })],
      ["api/wizard", () => jsonResponse({ step: "url" })],
    ]);

    await window.eval("loadPinboard()");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(document.querySelector(".sw, .wz")).not.toBeNull();
    expect(document.getElementById("app").textContent).not.toContain(
      window.eval('t("pinboard.error.title")')
    );
  });

  test("getJson turns a carried error code into a thrown ApiError", async () => {
    const { window } = loadApp();
    await quiet(window);
    routeFetch(window, [["api/pinboard", () => jsonResponse({ error: "network" })]]);
    const caught = await window.eval(
      "getJson('api/pinboard').then(() => null, (error) => ({ name: error.name, code: error.code }))"
    );
    expect(caught).toEqual({ name: "ApiError", code: "network" });
  });

  test("a letter detail that answers with an error code never renders as an empty letter", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.view = 'post'; state.postTab = 'letters'; state.children = [];");
    routeFetch(window, [
      ["api/letters/detail", () => jsonResponse({ error: "network" })],
      ["api/letters/seen", () => jsonResponse({ read: 1 })],
    ]);

    await window.eval(
      "openLetter({ letter_id: '1', recipient_id: '1', title: 'Wichtig', unread: false })"
    );
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(window.eval("state.letterDetail.error")).toBe("network");
    expect(document.querySelector(".body-html")).toBeNull();
    expect(document.getElementById("app").textContent).toContain(
      window.eval('t("letters.detail.errorTitle")')
    );
  });
});
