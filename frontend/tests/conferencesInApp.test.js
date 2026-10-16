import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function teacherPage(extra) {
  return Object.assign({
    page: "a".repeat(24),
    title: "Frau Muster",
    connection_id: "s1",
    notices: [],
    blocks: [
      { kind: "text", text: "Raum R 101" },
      { kind: "facts", facts: [{ label: "Termindauer", value: "10 Minuten" }] },
      { kind: "table", caption: "", headers: ["Zeit", "Lehrkraft"], rows: [{ cells: ["14:00", "Frau Muster"], links: [], forms: [1] }] },
      { kind: "form", form: 0 },
    ],
    forms: [
      {
        id: 0,
        check: "c".repeat(16),
        method: "post",
        title: "",
        fields: [
          { key: "slot", name: "slot", kind: "radio", label: "Zeit", required: true, error: "", options: [
            { value: "101", label: "14:00 - 14:10", selected: false, disabled: false },
            { value: "102", label: "14:10 - 14:20", selected: false, disabled: true },
          ] },
          { key: "child", name: "child", kind: "select", label: "Für", required: true, disabled: false, readonly: false, error: "", multiple: false, options: [
            { value: "", label: "Bitte wählen", group: "", selected: false, disabled: false },
            { value: "501", label: "Kim", group: "", selected: false, disabled: false },
          ] },
          { key: "note", name: "note", kind: "textarea", label: "Anmerkung", required: false, disabled: false, readonly: false, error: "", value: "", maxlength: 500 },
        ],
        submits: [{ id: 0, label: "Buchen", destructive: false }],
        errors: [],
        unsupported: false,
        destructive: false,
      },
      {
        id: 1,
        check: "d".repeat(16),
        method: "post",
        title: "",
        fields: [],
        submits: [{ id: 0, label: "Absagen", destructive: true }],
        errors: [],
        unsupported: false,
        destructive: true,
      },
    ],
  }, extra || {});
}

function openPage(window, page) {
  window.eval("(function (page) { state.view = 'conferences'; state.conferenceDetail = { stack: [], origin: null }; pushConferencePage({ page: page.page, connection_id: 's1', title: page.title }, page); })")(page);
}

function pageNode(window) {
  return window.eval("conferencesView()");
}

function stubFetch(window, answers, calls) {
  window.fetch = (url, options) => {
    const target = String(url);
    if (!target.includes("api/conferences/submit")) return new Promise(() => {});
    calls.push({ url: target, body: options && options.body ? JSON.parse(options.body) : null });
    const next = answers.length > 1 ? answers.shift() : answers[0];
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(next) });
  };
}

function sheetNode(window) {
  return window.eval("state.sheet && state.sheet()");
}

function choose(view, window) {
  const radio = view.querySelector('input[type="radio"][value="101"]');
  radio.checked = true;
  radio.dispatchEvent(new window.Event("change"));
  const select = view.querySelector("select.sel");
  select.value = "501";
  select.dispatchEvent(new window.Event("change"));
}

function noSchoolLinks(node) {
  expect(node.querySelectorAll("a[href]").length).toBe(0);
  expect(node.querySelectorAll('[target="_blank"]').length).toBe(0);
  expect(node.innerHTML).not.toContain("/iserv/");
}

describe("parent-teacher conferences stay inside the app", () => {
  test("the list opens rows in the app and links nowhere", () => {
    const { window } = loadApp();
    evalWith(window, "state.view = 'conferences'; state.conferences = testArgs[0]", {
      empty: false,
      items: [
        { cells: ["Elternsprechtag Herbst", "05.11.2026"], headers: [], page: "b".repeat(24), connection_id: "s1" },
        { cells: ["Elternsprechtag Frühjahr"], headers: [], page: "", connection_id: "s1" },
      ],
    });
    const view = pageNode(window);
    noSchoolLinks(view);
    const rows = view.querySelectorAll(".conference-row");
    expect(rows.length).toBe(2);
    expect(rows[0].tagName).toBe("BUTTON");
    expect(rows[1].tagName).toBe("DIV");
    expect(view.querySelectorAll(".chipbar.segmented [role=tab]").length).toBe(2);
  });

  test("a page shows facts, labelled table rows and the booking form with one primary button", () => {
    const { window } = loadApp();
    openPage(window, teacherPage());
    const view = pageNode(window);
    noSchoolLinks(view);
    expect(view.textContent).toContain("Raum R 101");
    expect(view.textContent).toContain("Termindauer");
    expect(view.querySelector(".conference-row .row-sub").textContent).toBe("Lehrkraft: Frau Muster");
    expect(view.querySelectorAll('input[type="radio"]').length).toBe(2);
    expect(view.querySelector('input[type="radio"][value="102"]').disabled).toBe(true);
    expect(view.querySelectorAll("select.sel option").length).toBe(2);
    expect(view.querySelector("textarea.txt").getAttribute("maxlength")).toBe("500");
    const primary = view.querySelectorAll(".conference-form .btn:not(.ghost)");
    expect(primary.length).toBe(1);
    expect(primary[0].textContent).toBe("Buchen");
    expect(view.querySelector(".conference-row-actions .btn.ghost").textContent).toBe("Absagen");
  });

  test("a missing required choice stops before anything is sent", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{}], calls);
    openPage(window, teacherPage());
    pageNode(window).querySelector(".conference-form .btn").click();
    await settle();
    expect(calls).toEqual([]);
    expect(pageNode(window).querySelector(".conference-outcome").textContent).toContain("Zeit");
  });

  test("booking asks first, sends the form once and shows the page read again", async () => {
    const { window } = loadApp();
    const calls = [];
    const after = teacherPage({ notices: [{ tone: "success", text: "Gebucht" }] });
    stubFetch(window, [{ ok: true, state: "done", message_key: "api.conferences.submit.ok", notices: ["Gebucht"], page: after }], calls);
    openPage(window, teacherPage());
    const view = pageNode(window);
    choose(view, window);
    view.querySelector(".conference-form .btn").click();
    await settle();
    const confirm = sheetNode(window);
    expect(confirm.querySelector(".dlg-quote").textContent).toContain("Zeit: 14:00 - 14:10");
    expect(confirm.querySelector(".dlg-quote").textContent).toContain("Für: Kim");
    expect(calls).toEqual([]);
    confirm.querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle();
    await settle();
    const sent = calls.find((call) => call.url.includes("api/conferences/submit"));
    expect(sent.body).toMatchObject({ connection_id: "s1", page: "a".repeat(24), form: 0, check: "c".repeat(16), submit: 0, confirmed: true });
    expect(sent.body.values).toMatchObject({ slot: "101", child: "501", note: "" });
    expect(sent.body.request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(calls.filter((call) => call.url.includes("api/conferences/submit")).length).toBe(1);
    const shown = pageNode(window);
    expect(shown.querySelector(".conference-outcome.good").textContent).toContain("Gebucht");
  });

  test("an uncertain answer is shown and never sent again by itself", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: false, state: "uncertain", message_key: "api.conferences.submit.uncertain", page: teacherPage() }], calls);
    openPage(window, teacherPage());
    const view = pageNode(window);
    choose(view, window);
    view.querySelector(".conference-form .btn").click();
    await settle();
    sheetNode(window).querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle();
    await settle();
    await settle();
    expect(calls.filter((call) => call.url.includes("api/conferences/submit")).length).toBe(1);
    const outcome = pageNode(window).querySelector(".conference-outcome");
    expect(outcome.className).not.toContain("good");
    expect(outcome.textContent).toContain(window.eval('t("api.conferences.submit.uncertain")'));
  });

  test("a validation answer of the school shows its notes on the form", async () => {
    const { window } = loadApp();
    const calls = [];
    const invalid = teacherPage();
    invalid.forms[0].errors = ["Das Formular enthält Fehler.", "Bitte wählen."];
    invalid.forms[0].fields[1].error = "Bitte wählen.";
    stubFetch(window, [{ ok: false, state: "invalid", message_key: "api.conferences.submit.invalid", errors: invalid.forms[0].errors, page: invalid }], calls);
    openPage(window, teacherPage());
    const view = pageNode(window);
    choose(view, window);
    view.querySelector(".conference-form .btn").click();
    await settle();
    sheetNode(window).querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle();
    await settle();
    const shown = pageNode(window);
    expect(shown.querySelector(".conference-form .note.bad").textContent).toContain("Das Formular enthält Fehler.");
    expect(shown.querySelector(".field .err").textContent).toBe("Bitte wählen.");
    expect(shown.querySelectorAll(".conference-form .note.bad").length).toBe(1);
    expect(shown.querySelector("select.sel").className).toContain("bad");
  });

  test("cancelling a booking is confirmed as a destructive action", async () => {
    const { window } = loadApp();
    const calls = [];
    stubFetch(window, [{ ok: true, state: "done", message_key: "api.conferences.submit.ok", page: teacherPage() }], calls);
    openPage(window, teacherPage());
    pageNode(window).querySelector(".conference-row-actions .btn").click();
    await settle();
    const confirm = sheetNode(window);
    expect(confirm.querySelector(".btn.destructive")).not.toBeNull();
    confirm.querySelector(".btn.destructive").click();
    await settle();
    await settle();
    const sent = calls.find((call) => call.url.includes("api/conferences/submit"));
    expect(sent.body).toMatchObject({ form: 1, check: "d".repeat(16), confirmed: true });
  });

  test("a reading form opens the next page without asking", async () => {
    const { window } = loadApp();
    const calls = [];
    const chooser = teacherPage({
      blocks: [{ kind: "form", form: 0 }],
      forms: [{ id: 0, check: "e".repeat(16), method: "get", title: "", errors: [], unsupported: false, destructive: false,
        fields: [{ key: "teacher", name: "teacher", kind: "select", label: "Lehrkraft", required: false, disabled: false, readonly: false, error: "", multiple: false,
          options: [{ value: "12", label: "Frau Muster", group: "Deutsch", selected: false, disabled: false }] }],
        submits: [{ id: 0, label: "Anzeigen", destructive: false }] }],
    });
    stubFetch(window, [{ ok: true, state: "opened", message_key: "api.conferences.submit.opened", page: teacherPage({ page: "f".repeat(24) }) }], calls);
    openPage(window, chooser);
    expect(pageNode(window).querySelector(".conference-form select option").textContent).toBe("Deutsch: Frau Muster");
    pageNode(window).querySelector(".conference-form .btn").click();
    await settle();
    await settle();
    expect(sheetNode(window)).toBeFalsy();
    expect(calls[0].body).toMatchObject({ confirmed: false, request_id: "", values: { teacher: "12" } });
    expect(window.eval("state.conferenceDetail.stack.length")).toBe(2);
    expect(window.eval("conferenceEntry().page")).toBe("f".repeat(24));
  });

  test("a get action that changes something asks first and sends a request id", async () => {
    const { window } = loadApp();
    const calls = [];
    const page = teacherPage({
      blocks: [{ kind: "table", caption: "", headers: [], rows: [{ cells: ["14:00", "Frau Muster", "Absagen"], links: [], forms: [0] }] }],
      forms: [{ id: 0, check: "h".repeat(16), method: "get", writes: true, title: "", errors: [], unsupported: false, destructive: true,
        fields: [], row: ["14:00", "Frau Muster", "Absagen"], submits: [{ id: "a1b2c3d4e5f6", label: "Absagen", destructive: true }] }],
    });
    stubFetch(window, [{ ok: true, state: "opened", message_key: "api.conferences.submit.opened", page: teacherPage({ page: "k".repeat(24), title: "Wirklich absagen?" }) }], calls);
    openPage(window, page);
    pageNode(window).querySelector(".conference-row-actions .btn").click();
    await settle();
    expect(calls).toHaveLength(0);
    const confirm = sheetNode(window);
    expect(confirm.querySelector(".btn.destructive")).not.toBeNull();
    confirm.querySelector(".btn.destructive").click();
    await settle();
    await settle();
    expect(calls[0].body).toMatchObject({ form: 0, submit: "a1b2c3d4e5f6", confirmed: true });
    expect(calls[0].body.request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(window.eval("state.conferenceDetail.stack.length")).toBe(2);
    expect(window.eval("conferenceEntry().page")).toBe("k".repeat(24));
  });

  test("going back walks the pages and then returns to the list", () => {
    const { window } = loadApp();
    window.fetch = () => new Promise(() => {});
    openPage(window, teacherPage());
    evalWith(window, "pushConferencePage({ page: 'g'.repeat(24), connection_id: 's1', title: 'X' }, testArgs[0])", teacherPage({ page: "g".repeat(24) }));
    expect(window.eval("conferenceHeader().text")).toBe("Frau Muster");
    window.eval("leaveConferencePage()");
    expect(window.eval("state.conferenceDetail.stack.length")).toBe(1);
    window.eval("leaveConferencePage()");
    expect(window.eval("state.conferenceDetail")).toBe(null);
  });

  test("an overview row with a date inside a longer cell keeps its day", () => {
    const { window } = loadApp();
    expect(window.eval("isoDate(conferenceCellDate('Donnerstag, 05.11.2026, 14:00 Uhr'))")).toBe("2026-11-05");
    expect(window.eval("conferenceCellDate('Raum 101')")).toBe(null);
  });
});

describe("the child choice of a conference form", () => {
  test("without a matching profile the form says so and offers no send button", () => {
    const { window } = loadApp();
    const page = teacherPage();
    page.forms[0].fields[1] = Object.assign({}, page.forms[0].fields[1], {
      options: [{ value: "", label: "Bitte wählen", group: "", selected: false, disabled: false }],
      profile: true,
      withheld: 1,
      profiles_missing: true,
    });
    openPage(window, page);
    const view = pageNode(window);
    expect(view.querySelector(".conference-no-profile").textContent).toBe(window.eval('t("conferences.form.noProfile")'));
    expect(view.querySelectorAll(".conference-form .conference-submit").length).toBe(0);
    expect(view.querySelectorAll("select.sel option").length).toBe(1);
  });
});

describe("after an unclear send", () => {
  test("a lost answer reloads the page instead of offering the old buttons again", async () => {
    const { window } = loadApp();
    const pageCalls = [];
    window.fetch = (url) => {
      const target = String(url);
      if (target.includes("api/conferences/submit")) return Promise.reject(new Error("offline"));
      if (target.includes("api/conferences/page")) pageCalls.push(target);
      return new Promise(() => {});
    };
    openPage(window, teacherPage());
    const view = pageNode(window);
    choose(view, window);
    view.querySelector(".conference-form .btn").click();
    await settle();
    sheetNode(window).querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle();
    await settle();
    expect(pageCalls.length).toBe(1);
    expect(pageCalls[0]).toContain("page=" + "a".repeat(24));
  });

  test("an answer without a page reloads the page", async () => {
    const { window } = loadApp();
    const pageCalls = [];
    window.fetch = (url) => {
      const target = String(url);
      if (target.includes("api/conferences/submit")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: false, state: "uncertain", message_key: "api.conferences.submit.uncertain" }) });
      }
      if (target.includes("api/conferences/page")) pageCalls.push(target);
      return new Promise(() => {});
    };
    openPage(window, teacherPage());
    const view = pageNode(window);
    choose(view, window);
    view.querySelector(".conference-form .btn").click();
    await settle();
    sheetNode(window).querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle();
    await settle();
    expect(pageCalls.length).toBe(1);
  });
});

describe("the confirmation names the row", () => {
  test("cancelling shows the time and teacher of the booking", async () => {
    const { window } = loadApp();
    window.fetch = () => new Promise(() => {});
    const page = teacherPage();
    page.forms[1].row = ["14:00", "Frau Muster"];
    openPage(window, page);
    pageNode(window).querySelector(".conference-row-actions .btn").click();
    await settle();
    expect(sheetNode(window).querySelector(".dlg-quote").textContent).toContain("14:00 · Frau Muster");
  });
});

describe("a form with an unknown profile id", () => {
  test("says so and offers no send button", () => {
    const { window } = loadApp();
    const page = teacherPage();
    page.forms[0].profiles_missing = true;
    openPage(window, page);
    const view = pageNode(window);
    expect(view.querySelectorAll(".conference-form .conference-no-profile").length).toBe(1);
    expect(view.querySelectorAll(".conference-form .conference-submit").length).toBe(0);
  });
});
