import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard, wizard } from "./absenceWizard.js";

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function today(window) {
  return window.eval("isoDate(new Date())");
}

function sickData(window, extra) {
  const day = today(window);
  return Object.assign(
    {
      children: [{ id: 1, name: "Mia" }],
      types: ["sick"],
      rules: {},
      day_options: { from: [{ value: day, label: "Heute" }], till: [{ value: day, label: "Heute" }] },
      period_labels: [
        { number: 1, label: "1. Stunde" },
        { number: 2, label: "2. Stunde" },
        { number: 3, label: "3. Stunde" },
        { number: 4, label: "4. Stunde" },
        { number: 5, label: "5. Stunde" },
      ],
    },
    extra || {}
  );
}

describe("[P177] the 7:10 case costs four taps", () => {
  test("report -> type -> when -> Krankmelden, no scrolling detour, no keyboard", async () => {
    const { window, document } = loadApp();
    const day = today(window);
    const data = sickData(window, { types: ["sick", "leave", "deregister", "daycare"], deregister_options: ["bus"] });
    window.eval(`state.absence = { data: ${JSON.stringify(data)} }`);
    window.eval("state.view = 'absence'; render();");

    let taps = 0;
    const reportButton = Array.from(document.querySelectorAll(".btn")).find((node) =>
      node.textContent.includes("Abwesenheit melden")
    );
    expect(reportButton).toBeTruthy();
    reportButton.click();
    taps += 1;

    const wz = wizard(window);
    expect(wz.path).toEqual(["type", "sickWhen", "review"]);
    expect(wz.step).toBe("type");
    expect(wz.form.type).toBe("sick");
    expect(wz.form.day_from).toBe(day);
    expect(wz.form.day_till).toBe(day);

    wz.nextButton.click();
    taps += 1;
    expect(wz.step).toBe("sickWhen");

    wz.nextButton.click();
    taps += 1;
    expect(wz.step).toBe("review");
    expect(wz.nextButton.textContent).toBe("Krankmelden");

    const calls = [];
    window.fetch = (url, opts) => {
      calls.push({ url, opts });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    };
    wz.nextButton.click();
    taps += 1;
    await flush();
    await flush();

    expect(taps).toBe(4);
    expect(calls.filter((call) => call.opts && call.opts.method === "POST").length).toBe(1);
    expect(window.eval("state.absenceForm")).toBeNull();
  });

  test("a school with only sick reporting drops the type step and costs one tap less", () => {
    const { window, document } = loadApp();
    window.eval(`state.absence = { data: ${JSON.stringify(sickData(window))} }`);
    window.eval("state.view = 'absence'; render();");
    Array.from(document.querySelectorAll(".btn"))
      .find((node) => node.textContent.includes("Abwesenheit melden"))
      .click();
    const wz = wizard(window);
    expect(wz.path).toEqual(["sickWhen", "review"]);
    wz.nextButton.click();
    expect(wz.step).toBe("review");
    expect(wz.nextButton.textContent).toBe("Krankmelden");
  });

  test("with a second child and lesson-wise reporting the path grows, it never reorders", () => {
    const { window } = loadApp();
    const wz = openWizard(
      window,
      "sick",
      sickData(window, {
        children: [{ id: 1, name: "Mia" }, { id: 2, name: "Ben" }],
        types: ["sick", "leave"],
        rules: { sick_by_lesson: true },
      })
    );
    expect(wz.path).toEqual(["type", "child", "sickWhen", "sickHours", "review"]);
    wz.form.hours_mode = "byLesson";
    expect(wz.path).toEqual(["type", "child", "sickWhen", "sickHours", "sickPeriods", "review"]);
  });
});

describe("[P177] the review page shows every mandatory answer", () => {
  test("each type lists a row for every step that carries an answer, and review is last", () => {
    const { window } = loadApp();
    const cases = {
      sick: sickData(window, { rules: { sick_comment: true, sick_by_lesson: true } }),
      leave: { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} },
      deregister: {
        children: [{ id: 1, name: "Mia" }],
        types: ["deregister"],
        rules: {},
        deregister_options: ["bus", "lunch"],
      },
      daycare: { children: [{ id: 1, name: "Mia" }], types: ["daycare"], rules: { daycare_reason_required: true } },
    };
    for (const [type, data] of Object.entries(cases)) {
      const wz = openWizard(window, type, data);
      expect(wz.path[wz.path.length - 1], type).toBe("review");
      const answered = wz.path.filter((id) => id !== "review" && id !== "type" && id !== "child");
      const rows = window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
      const targets = rows.map((row) => row.step);
      for (const id of answered) {
        const covered = targets.includes(id) || id === "sickHours" || id === "sickPeriods" || id === "leaveDayTime" || id === "leaveTill" || id === "leaveBody" || id === "repeatUntil";
        expect(covered, `${type}/${id}`).toBe(true);
      }
      expect(targets, type).toContain("");
    }
  });

  test("the review question and the consequence sentence are always present", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", sickData(window));
    wz.go("review");
    expect(wz.question).toBe("Stimmt das so?");
    expect(wz.status).toContain("Beim Absenden geht die Meldung sofort an die Schule.");
    expect(wz.status).toContain("lässt sich in IServ nicht zurückziehen");
  });
});

describe("[P177] regression: the three bugs the rebuild had to close", () => {
  test("a rejection keeps the type-specific button label instead of silently resetting it", async () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", sickData(window));
    wz.go("review");
    expect(wz.nextButton.textContent).toBe("Krankmelden");
    window.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: false }) });
    wz.nextButton.click();
    await flush();
    await flush();
    expect(wz.step).toBe("review");
    expect(wz.nextButton.textContent).toBe("Krankmelden");
    expect(wz.status).toBe("IServ hat die Meldung nicht angenommen. Deine Angaben stehen noch.");
    expect(window.eval("state.absenceForm")).not.toBeNull();
  });

  test("a rejection leaves every entered value in place", async () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} });
    wz.form.subject = "Arzttermin";
    wz.form.body = "Kieferorthopaede";
    wz.go("review");
    window.fetch = () => Promise.reject(new Error("offline"));
    wz.nextButton.click();
    await flush();
    await flush();
    expect(wz.form.subject).toBe("Arzttermin");
    expect(wz.form.body).toBe("Kieferorthopaede");
    expect(wz.step).toBe("review");
  });

  test("the dirty check sees attachments, so leaving with a file still asks", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} });
    expect(window.eval("isAbsenceFormDirty()")).toBe(false);
    wz.go("leaveAttachments");
    const input = wz.body.querySelector('input[type="file"]');
    Object.defineProperty(input, "files", {
      value: [new window.File(["x"], "attest.pdf", { type: "application/pdf" })],
      configurable: true,
    });
    input.dispatchEvent(new window.Event("change"));
    expect(wz.form.attachments.length).toBe(1);
    expect(window.eval("isAbsenceFormDirty()")).toBe(true);
    const asked = window.eval(`
      (function () {
        let called = false;
        leaveAbsenceForm(() => { called = true; });
        return { called, sheetOpen: !!state.sheet };
      })()
    `);
    expect(asked.called).toBe(false);
    expect(asked.sheetOpen).toBe(true);
  });

  test("'from lesson 5 till lesson 2' is caught here instead of going through", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", sickData(window, { rules: { sick_by_lesson: true } }));
    wz.form.hours_mode = "byLesson";
    wz.form.from_period = "5";
    wz.form.till_period = "2";
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.text).toBe("Die Bis-Stunde darf nicht vor der Ab-Stunde liegen.");
    expect(entry.step).toBe("sickPeriods");
    wz.go("review");
    expect(wz.step).toBe("sickPeriods");
    expect(wz.status).toBe("Die Bis-Stunde darf nicht vor der Ab-Stunde liegen.");
  });

  test("a start lesson without an end lesson is caught too", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", sickData(window, { rules: { sick_by_lesson: true } }));
    wz.form.hours_mode = "byLesson";
    wz.form.from_period = "3";
    wz.form.till_period = "";
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.text).toBe("Bitte auch die Bis-Stunde wählen.");
    expect(entry.step).toBe("sickPeriods");
  });
});

describe("[P177] the wizard never leaves a lock without a step to jump to", () => {
  test("every problem the validator can raise names a reachable step", () => {
    const { window } = loadApp();
    const day = today(window);
    const cases = [
      ["sick", sickData(window, { rules: { sick_by_lesson: true } }), (form) => { form.from_period = "5"; form.till_period = "1"; }],
      ["sick", sickData(window), (form) => { form.day_from = "2000-01-01"; }],
      ["leave", { children: [{ id: 1 }], types: ["leave"], rules: {} }, (form) => { form.subject = ""; }],
      ["leave", { children: [{ id: 1 }], types: ["leave"], rules: {} }, (form) => { form.body = ""; }],
      ["leave", { children: [{ id: 1 }], types: ["leave"], rules: {} }, (form) => {
        form.duration = "more";
        form.till_date = "2000-01-01";
      }],
      ["leave", { children: [{ id: 1 }], types: ["leave"], rules: {} }, (form) => {
        form.body = "x";
        form.time_mode = "custom";
        form.from_time = "12:00";
        form.till_time = "09:00";
      }],
      ["deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus", "lunch"] }, (form) => {
        form.deregister_from = "";
      }],
      ["deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] }, (form) => {
        form.repeat = "weekly";
      }],
      ["daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} }, (form) => {
        form.daycare_kind = "early_end";
        form.pickup_time = "";
      }],
      ["daycare", { children: [{ id: 1 }], types: ["daycare"], rules: { daycare_reason_required: true } }, () => {}],
      ["daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} }, (form) => { form.date = "2000-01-01"; }],
    ];
    for (const [type, data, mutate] of cases) {
      const wz = openWizard(window, type, data);
      mutate(wz.form);
      const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
      expect(entry, `${type} ${JSON.stringify(wz.form)}`).not.toBeNull();
      expect(entry.text.length).toBeGreaterThan(0);
      expect(entry.hint.length).toBeGreaterThan(0);
      wz.go("review");
      expect(wz.step, `${type}/${entry.step}`).toBe(entry.step);
      expect(wz.status).toBe(entry.text);
    }
    expect(day.length).toBe(10);
  });

  test("a complete form raises no problem at all, for every type", () => {
    const { window } = loadApp();
    const complete = [
      ["sick", sickData(window), () => {}],
      ["leave", { children: [{ id: 1 }], types: ["leave"], rules: {} }, (form) => { form.body = "Begruendung"; }],
      ["deregister", { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] }, () => {}],
      ["daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} }, () => {}],
    ];
    for (const [type, data, mutate] of complete) {
      const wz = openWizard(window, type, data);
      mutate(wz.form);
      expect(window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)"), type).toBeNull();
      wz.go("review");
      expect(wz.step, type).toBe("review");
    }
  });
});
