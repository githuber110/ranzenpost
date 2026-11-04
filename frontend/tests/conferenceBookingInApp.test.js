import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function bookingPage(extra) {
  return {
    page: "a".repeat(24),
    title: "Elternsprechtag",
    connection_id: "s1",
    blocks: [],
    forms: [],
    notices: [],
    booking: Object.assign({
      description: "Bitte tragen Sie sich ein.",
      window: { state: "open", begin: "2026-11-04", end: "2026-11-12" },
      hosts: [
        { id: "host-1", name: "Frau Muster", short: "MU", location: "R 101" },
        { id: "host-2", name: "Herr Beispiel", short: "", location: "" },
      ],
      days: [
        { date: "2026-11-17", slots: [
          { id: "slot-1", begin: "15:00", end: "15:15", closed: false },
          { id: "slot-2", begin: "15:20", end: "15:35", closed: false },
          { id: "slot-3", begin: "15:40", end: "15:55", closed: true },
        ] },
      ],
      taken: [{ slot: "slot-1", host: "host-1" }],
      mine: [],
      children: [{ id: "kim", name: "Kim Muster" }],
      withheld: 0,
      profiles_missing: false,
    }, extra || {}),
  };
}

function open(window, page) {
  window.eval("(function (page) { state.view = 'conferences'; state.conferenceDetail = { stack: [], origin: null }; pushConferencePage({ page: page.page, connection_id: 's1', title: page.title }, page); })")(page);
  return window.eval("conferencesView()");
}

function stubFetch(window, answers, calls) {
  window.fetch = (url, options) => {
    const target = String(url);
    if (!target.includes("api/conferences/booking")) return new Promise(() => {});
    calls.push(JSON.parse(options.body));
    const next = answers.shift();
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(next) });
  };
}

function sheetNode(window) {
  return window.eval("state.sheet && state.sheet()");
}

function buttons(node, text) {
  return [...node.querySelectorAll("button")].filter((button) => button.textContent.includes(text));
}

async function answerConfirm(window, approve) {
  await settle();
  const confirm = sheetNode(window);
  const stack = confirm.querySelector(".btn-stack, .sheet-actions") || confirm;
  const choice = [...stack.querySelectorAll("button")].find((button) => (approve ? !button.classList.contains("ghost") : button.classList.contains("ghost")));
  choice.click();
  await settle();
  await settle();
}

describe("booking a parent-teacher appointment inside the app", () => {
  test("the page lists teachers with free counts and never links to the school", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage());
    const rows = view.querySelectorAll(".conference-host");
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain("Frau Muster (MU)");
    expect(rows[0].textContent).toContain("R 101");
    expect(rows[0].textContent).toMatch(/1\b/);
    expect(rows[1].textContent).toMatch(/2\b/);
    expect(view.textContent).toContain("Bitte tragen Sie sich ein.");
    expect(view.querySelectorAll("a[href]").length).toBe(0);
    expect(view.querySelectorAll('[target="_blank"]').length).toBe(0);
  });

  test("a teacher's sheet offers only free times", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage());
    view.querySelector(".conference-host").click();
    const slots = sheetNode(window).querySelectorAll(".conference-slot");
    expect([...slots].map((slot) => slot.disabled)).toEqual([true, false, true]);
    expect(slots[0].textContent).toContain("15:00");
    expect(sheetNode(window).querySelectorAll(".conference-slot.is-free").length).toBe(1);
  });

  test("nothing can be chosen while booking is closed", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage({ window: { state: "after", begin: "2026-11-04", end: "2026-11-12" } }));
    view.querySelector(".conference-host").click();
    expect(sheetNode(window).querySelectorAll(".conference-slot.is-free").length).toBe(0);
  });

  test("nothing can be chosen when no child of this account is known", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage({ children: [], profiles_missing: true }));
    expect(view.querySelector(".conference-no-profile")).not.toBeNull();
    view.querySelector(".conference-host").click();
    expect(sheetNode(window).querySelectorAll(".conference-slot.is-free").length).toBe(0);
  });

  test("booking with one child asks first, sends once and shows the school's new state", async () => {
    const { window } = loadApp();
    const calls = [];
    const after = bookingPage({
      taken: [{ slot: "slot-1", host: "host-1" }, { slot: "slot-2", host: "host-1" }],
      mine: [{ id: "b1", slot: "slot-2", host: "host-1", teacher: "Frau Muster", location: "R 101", begin: "15:20", end: "15:35", date: "2026-11-17", children: [{ id: "kim", name: "Kim Muster" }], editable: true }],
    });
    stubFetch(window, [{ ok: true, state: "done", message_key: "api.conferences.booking.booked", message: "Der Termin ist gebucht.", page: after }], calls);
    const view = open(window, bookingPage());
    view.querySelector(".conference-host").click();
    sheetNode(window).querySelector(".conference-slot.is-free").click();
    await settle();
    expect(calls.length).toBe(0);
    expect(sheetNode(window).textContent).toContain("Frau Muster");
    await answerConfirm(window, true);
    expect(calls.length).toBe(1);
    expect(calls[0]).toMatchObject({ connection_id: "s1", action: "book", slot: "slot-2", host: "host-1", children: ["kim"], confirmed: true });
    expect(calls[0].request_id.length).toBeGreaterThanOrEqual(16);
    const shown = window.eval("conferencesView()");
    expect(shown.querySelector(".conference-outcome.good").textContent).toContain("Der Termin ist gebucht.");
    expect(buttons(shown, window.eval("t('conferences.booking.cancel')")).length).toBe(1);
  });

  test("declining the question sends nothing", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [], calls);
    const view = open(window, bookingPage());
    view.querySelector(".conference-host").click();
    sheetNode(window).querySelector(".conference-slot.is-free").click();
    await answerConfirm(window, false);
    expect(calls.length).toBe(0);
  });

  test("with two children a child has to be chosen before the question comes", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true, state: "done", message: "ok", page: bookingPage() }], calls);
    const view = open(window, bookingPage({ children: [{ id: "kim", name: "Kim Muster" }, { id: "lou", name: "Lou Muster" }] }));
    view.querySelector(".conference-host").click();
    sheetNode(window).querySelector(".conference-slot.is-free").click();
    const sheet = sheetNode(window);
    const send = sheet.querySelector(".conference-submit");
    expect(send.disabled).toBe(true);
    const box = sheet.querySelector('input[type="checkbox"]');
    box.checked = true;
    box.dispatchEvent(new window.Event("change"));
    expect(send.disabled).toBe(false);
    send.click();
    await answerConfirm(window, true);
    expect(calls[0].children).toEqual(["kim"]);
  });

  test("the own booking can be cancelled after a question", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true, state: "done", message: "abgesagt", page: bookingPage() }], calls);
    const view = open(window, bookingPage({
      mine: [{ id: "b1", slot: "slot-2", host: "host-1", teacher: "Frau Muster", location: "R 101", begin: "15:20", end: "15:35", date: "2026-11-17", children: [{ id: "kim", name: "Kim Muster" }], editable: true }],
    }));
    expect(view.textContent).toContain("Kim Muster");
    expect(view.textContent).toContain("15:20");
    buttons(view, window.eval("t('conferences.booking.cancel')"))[0].click();
    await answerConfirm(window, true);
    expect(calls[0]).toMatchObject({ action: "cancel", booking: "b1", confirmed: true });
  });

  test("a read-only booking offers no change", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage({
      mine: [{ id: "b1", slot: "slot-2", host: "host-1", teacher: "Frau Muster", location: "", begin: "15:20", end: "15:35", date: "2026-11-17", children: [], editable: false }],
    }));
    expect(view.querySelectorAll(".conference-row-actions").length).toBe(0);
  });

  test("the school's own refusal is shown in its words", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: false, state: "invalid", message: "Nicht angenommen", errors: ["Schon vergeben"], page: bookingPage() }], calls);
    const view = open(window, bookingPage());
    view.querySelector(".conference-host").click();
    sheetNode(window).querySelector(".conference-slot.is-free").click();
    await answerConfirm(window, true);
    const shown = window.eval("conferencesView()");
    expect(shown.querySelector(".conference-outcome.bad").textContent).toContain("Schon vergeben");
  });

  test("a lost connection never claims success", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [new Error("offline")], calls);
    const view = open(window, bookingPage());
    view.querySelector(".conference-host").click();
    sheetNode(window).querySelector(".conference-slot.is-free").click();
    await answerConfirm(window, true);
    const shown = window.eval("conferencesView()");
    expect(shown.querySelector(".conference-outcome.good")).toBeNull();
    expect(shown.querySelector(".conference-outcome")).not.toBeNull();
  });

  test("after a failed reload an old state is not shown as current", () => {
    const { window } = loadApp();
    open(window, bookingPage());
    window.eval("conferenceEntry().error = 'network'");
    const shown = window.eval("conferencesView()");
    expect(shown.querySelector(".conference-host")).toBeNull();
    expect(shown.querySelectorAll("button").length).toBe(1);
  });

  test("an unknown booking period claims nothing and still lets the school decide", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage({ window: { state: "unknown", begin: "", end: "" } }));
    expect(view.textContent).not.toContain(window.eval("t('conferences.booking.window.after')"));
    view.querySelector(".conference-host").click();
    expect(sheetNode(window).querySelectorAll(".conference-slot.is-free").length).toBe(1);
  });

  test("while booking is closed no free count is promised", () => {
    const { window } = loadApp();
    const view = open(window, bookingPage({ window: { state: "after", begin: "2026-11-04", end: "2026-11-12" } }));
    expect(view.querySelector(".conference-host").textContent).not.toContain(window.eval("tCount('conferences.booking.free', 1)"));
  });

  test("an older read does not overwrite a newer answer", async () => {
    const { window } = loadApp();
    open(window, bookingPage());
    let finish = null;
    window.fetch = () => new Promise((resolve) => { finish = resolve; });
    window.eval("loadConferencePage(conferenceEntry())");
    window.eval("(function (page) { applyConferenceBookingResult(conferenceEntry(), { ok: true, state: 'done', message: 'gebucht', page }); })")(bookingPage({ description: "Neu" }));
    finish({ ok: true, status: 200, json: () => Promise.resolve(bookingPage({ description: "Alt" })) });
    await settle();
    await settle();
    expect(window.eval("conferenceEntry().data.booking.description")).toBe("Neu");
  });

  test("a long teacher list can be searched", () => {
    const { window } = loadApp();
    const hosts = Array.from({ length: 9 }, (_, index) => ({ id: `h${index}`, name: `Lehrkraft ${index}`, short: "", location: "" }));
    const view = open(window, bookingPage({ hosts, taken: [] }));
    const search = view.querySelector(".conference-search");
    expect(view.querySelectorAll(".conference-host").length).toBe(9);
    search.value = "kraft 3";
    search.dispatchEvent(new window.Event("input"));
    expect(view.querySelectorAll(".conference-host").length).toBe(1);
  });
});
