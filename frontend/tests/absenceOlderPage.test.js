import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";
import { wizard } from "./absenceWizard.js";

function render(window, data) {
  const run = window.eval("(function (box) { state.absence = box; return absenceView(); })");
  return run({ data });
}

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function olderData(extra) {
  return Object.assign(
    {
      source: "older_page",
      children: [{ id: "c-mia", name: "Mia Muster" }, { id: "c-tom", name: "Tom Beispiel" }],
      types: [],
      rules: {},
      day_options: { from: [], till: [] },
      entries: [
        {
          id: "older:481",
          kind: "absence",
          source: "older_page",
          label_key: "absence.entry.kind.absence",
          from_date: "2126-09-14",
          till_date: "2126-09-16",
          student_id: "c-mia",
          status: "accepted",
          deletable: false,
          locked_reason_key: "api.absence.older.locked",
          technical: { id: "481", created_at: "2126-09-13", class_code: "2b" },
        },
      ],
      withheld: 0,
      phones: [],
    },
    extra || {}
  );
}

function fullSchema(extra) {
  return Object.assign(
    {
      profiles: [{ id: "c-mia", name: "Mia Muster" }, { id: "c-tom", name: "Tom Beispiel" }],
      profile_options: 3,
      till: true,
      times: true,
      whole_day: true,
      min: "",
      reason: { name: "absence[reason]", type: "textarea", label: "Bemerkung", required: false, options: [] },
      kind: { name: "absence[type]", type: "select", label: "Art", required: true, options: [{ value: "ill", label: "Krankheit" }, { value: "other", label: "Sonstiges" }] },
      extras: [{ name: "absence[phone]", type: "text", label: "Telefon", required: true, options: [] }],
    },
    extra || {}
  );
}

function answer(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function serve(window, routes) {
  const sent = [];
  window.fetch = (url, options) => {
    const path = new URL(String(url)).pathname;
    sent.push({ path, method: (options && options.method) || "GET", body: options && options.body ? JSON.parse(options.body) : null });
    const route = routes[path];
    return route ? answer(typeof route === "function" ? route(sent[sent.length - 1]) : route) : Promise.reject(new Error("unexpected " + path));
  };
  return sent;
}

async function openOlderWizard(window, document, schema, data) {
  const sent = serve(window, { "/api/absences/older-form": { ok: true, form: schema } });
  evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", data || olderData());
  window.eval("state.view = 'absence'; render();");
  const button = Array.from(document.querySelectorAll(".btn")).find((node) => node.textContent.includes(window.t("absence.report")));
  button.click();
  await settle(window);
  return sent;
}

describe("a school that offers absences only on the older IServ page", () => {
  test("offers the in-app report and never a link to the school server", () => {
    const { window } = loadApp();
    const view = render(window, olderData({ withheld: 1 }));
    expect(view.textContent).toContain(window.t("absence.report"));
    expect(view.querySelector("a.absence-older-open")).toBeNull();
    expect(view.querySelectorAll("a[target=_blank]").length).toBe(0);
    expect(Array.from(view.querySelectorAll("a[href]")).filter((link) => /\/iserv\/|^https?:/.test(link.getAttribute("href")))).toEqual([]);
    expect(view.textContent).toContain(window.t("absence.older.withheld"));
    expect(window.t("absence.older.open")).toBe("absence.older.open");
    expect(window.t("absence.older.text")).toBe("absence.older.text");
  });

  test("lists the older entries with profile, range and status", () => {
    const { window } = loadApp();
    const view = render(window, olderData());
    const row = view.querySelector(".rows .row");
    expect(row.textContent).toContain(window.t("absence.entry.kind.absence"));
    expect(row.textContent).toContain("Mia");
    expect(row.textContent).toContain(window.t("absence.status.accepted"));
  });

  test("an unconfirmed report is listed with its own tag and explains itself without a hand-off", () => {
    const { window } = loadApp();
    const pending = {
      id: "older:pending:x", kind: "absence", source: "older_page", label_key: "absence.entry.kind.absence",
      from_date: "2126-10-20", till_date: "2126-10-20", student_id: "c-mia", status: "unconfirmed", unconfirmed: true,
      deletable: false, locked_reason_key: "api.absence.older.pending", technical: { id: "", created_at: "2126-10-14", class_code: "" },
    };
    const view = render(window, olderData({ entries: [pending] }));
    const tag = view.querySelector(".rows .row .tag.warn");
    expect(tag.textContent).toBe(window.t("absence.status.unconfirmed"));
    const parts = window.eval("absenceDetailParts")(pending);
    expect(parts.foot[0].textContent).toBe(window.t("api.absence.older.pending"));
    expect(parts.foot[0].querySelector("a")).toBeNull();
  });

  test("an older entry the school lets withdraw offers the withdraw button", () => {
    const { window } = loadApp();
    const entry = Object.assign({}, olderData().entries[0], { deletable: true, locked_reason_key: "" });
    render(window, olderData({ entries: [entry] }));
    const parts = window.eval("absenceDetailParts")(entry);
    expect(parts.foot[0].classList.contains("destructive")).toBe(true);
  });

  test("the report walks the steps the school form asks for and sends what was chosen", async () => {
    const { window, document } = loadApp();
    const sent = await openOlderWizard(window, document, fullSchema());
    const wz = wizard(window);
    expect(wz.form.type).toBe("absence");
    expect(wz.path).toEqual(["child", "olderWhen", "olderDayTime", "olderKind", "olderReason", "olderDetails", "review"]);
    evalWith(window, "state.absenceForm.student_id = 'c-tom'; state.absenceForm.kind = 'ill'; state.absenceForm.extra['absence[phone]'] = '0123'; state.absenceForm.reason = 'Fieber'");
    window.eval("absenceSetOlderDuration('more')");
    expect(wz.path).toEqual(["child", "olderWhen", "olderTill", "olderKind", "olderReason", "olderDetails", "review"]);
    const later = window.eval("isoDate(addDays(new Date(), 2))");
    evalWith(window, "state.absenceForm.till_date = testArgs[0]", later);
    const wholeDays = window.eval("olderAbsencePayload(state.absenceForm)");
    expect([wholeDays.till_date, wholeDays.whole_day, wholeDays.from_time]).toEqual([later, true, ""]);
    window.eval("absenceSetOlderDuration('one'); absenceSetOlderTimeMode('custom')");
    expect(wz.path).toEqual(["child", "olderWhen", "olderDayTime", "olderTimes", "olderKind", "olderReason", "olderDetails", "review"]);
    const day = window.eval("state.absenceForm.from_date");
    evalWith(window, "state.absenceForm.from_time = '09:00'; state.absenceForm.till_time = '11:00'");
    serve(window, { "/api/absences": { ok: true, message_key: "api.absence.older.sent" }, "/api/absences/older-form": { ok: true, form: fullSchema() } });
    const posted = [];
    const original = window.fetch;
    window.fetch = (url, options) => {
      if (options && options.method === "POST") posted.push(JSON.parse(options.body));
      return original(url, options);
    };
    wz.go("review");
    const facts = wz.body.textContent;
    expect(facts).toContain("Krankheit");
    expect(facts).toContain("Telefon");
    expect(facts).toContain("09:00–11:00");
    wz.next();
    await settle(window);
    expect(sent[0].path).toBe("/api/absences/older-form");
    expect(posted).toHaveLength(1);
    const body = posted[0];
    expect(body).toMatchObject({
      type: "absence", student_id: "c-tom", till_date: day, whole_day: false, from_time: "09:00", till_time: "11:00",
      reason: "Fieber", kind: "ill", extra: { "absence[phone]": "0123" },
    });
    expect(window.eval("state.absenceForm")).toBeNull();
  });

  test("a whole-day report sends no times and a form with one profile skips the profile step", async () => {
    const { window, document } = loadApp();
    const schema = fullSchema({ profiles: [{ id: "c-mia", name: "Mia Muster" }], kind: null, reason: null, extras: [], till: false });
    await openOlderWizard(window, document, schema);
    const wz = wizard(window);
    expect(wz.path).toEqual(["olderWhen", "olderDayTime", "review"]);
    const body = window.eval("olderAbsencePayload(state.absenceForm)");
    expect(body.whole_day).toBe(true);
    expect([body.from_time, body.till_time]).toEqual(["", ""]);
    expect(body.till_date).toBe(body.from_date);
    expect(body.student_id).toBe("c-mia");
  });

  test("a required kind and a required extra field block the review until they are filled", async () => {
    const { window, document } = loadApp();
    await openOlderWizard(window, document, fullSchema());
    const problems = window.eval("absenceProblems(state.absenceForm, state.absence.data)").map((problem) => problem.step);
    expect(problems).toEqual(["child", "olderKind", "olderDetails"]);
  });

  test("errors the school returns land on the matching step and field", async () => {
    const { window, document } = loadApp();
    await openOlderWizard(window, document, fullSchema());
    evalWith(window, "state.absenceForm.student_id = 'c-mia'; state.absenceForm.kind = 'ill'; state.absenceForm.extra['absence[phone]'] = '0123'");
    serve(window, { "/api/absences": { ok: false, message_key: "api.absence.older.rejected", field_errors: { from: "Datum liegt in der Vergangenheit." }, errors: [] } });
    const wz = wizard(window);
    wz.go("review");
    wz.next();
    await settle(window);
    expect(wz.step).toBe("olderWhen");
    const error = wz.body.querySelector(".err");
    expect(error.textContent).toBe("Datum liegt in der Vergangenheit.");
    expect(wz.body.querySelector(".inp.bad")).not.toBeNull();
    const input = wz.body.querySelector("input[type=date]");
    input.value = "2126-10-21";
    input.dispatchEvent(new window.Event("change"));
    expect(wz.body.querySelector(".err")).toBeNull();
  });

  test("an unconfirmed report closes the form and reloads the list instead of offering a resend", async () => {
    const { window, document } = loadApp();
    await openOlderWizard(window, document, fullSchema({ profiles: [{ id: "c-mia", name: "Mia Muster" }], kind: null, extras: [] }));
    serve(window, {
      "/api/absences": (request) => (request.method === "POST" ? { ok: false, uncertain: true, message_key: "api.absence.older.uncertain" } : olderData()),
    });
    const wz = wizard(window);
    wz.go("review");
    wz.next();
    await settle(window);
    expect(window.eval("state.absenceForm")).toBeNull();
    expect(window.eval("state.toast && state.toast.message")).toBe(window.t("api.absence.older.uncertain"));
    expect(window.eval("state.toast.kind")).toBe("bad");
    expect(window.eval("state.absence.data.source")).toBe("older_page");
  });

  test("a form the app cannot use says why and opens nothing", async () => {
    const { window, document } = loadApp();
    serve(window, { "/api/absences/older-form": { ok: false, message_key: "api.absence.older.noProfile" } });
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", olderData());
    window.eval("state.view = 'absence'; render();");
    Array.from(document.querySelectorAll(".btn")).find((node) => node.textContent.includes(window.t("absence.report"))).click();
    await settle(window);
    expect(window.eval("state.absenceForm")).toBeNull();
    expect(window.eval("state.toast && state.toast.message")).toBe(window.t("api.absence.older.noProfile"));
    expect(window.eval("state.toast.kind")).toBe("bad");
  });

  test("shows a time next to the day when the older page names one", () => {
    const { window } = loadApp();
    const dates = window.eval("absenceDates")({ from_date: "2126-09-14", from_time: "08:00", till_date: "2126-09-14", till_time: "" });
    expect(dates).toContain("08:00");
    const plain = window.eval("absenceDates")({ from_date: "2126-09-14", till_date: "2126-09-14" });
    expect(plain).toBe(window.eval("showDate('2126-09-14')"));
  });

  test("the technical details of an older entry carry its IServ id and class", () => {
    const { window } = loadApp();
    const entries = window.eval("absenceTechEntries")(olderData().entries[0]);
    const values = entries.map((entry) => entry.value);
    expect(values).toContain("481");
    expect(values).toContain("2b");
  });
});
