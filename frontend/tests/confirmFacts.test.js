import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

function facts(window, type, data, mutate) {
  const wz = openWizard(window, type, data);
  if (mutate) mutate(wz.form);
  return window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
}

const SICK = {
  children: [{ id: 1, name: "Mia" }],
  types: ["sick"],
  rules: {},
  day_options: { from: [{ value: "2126-09-02" }], till: [{ value: "2126-09-02" }] },
};

describe("[C07] review page: structured, tappable facts instead of prose", () => {
  test("sick: one row per fact, Art is fixed, the range row carries the hours", () => {
    const { window } = loadApp();
    const rows = facts(window, "sick", Object.assign({}, SICK, {
      period_labels: [{ number: 1 }, { number: 2 }, { number: 3 }],
    }));
    expect(rows.map((row) => row.label)).toEqual(["Art", "Zeitraum"]);
    expect(rows[0].step).toBe("");
    expect(rows[1].step).toBe("sickWhen");
    expect(rows[1].value).toBe("02.09.2126, 1. bis 3. Stunde");
  });

  test("sick: the child row only exists with more than one child and points at the child step", () => {
    const { window } = loadApp();
    const rows = facts(window, "sick", Object.assign({}, SICK, {
      children: [{ id: 1, name: "Mia" }, { id: 2, name: "Ben" }],
    }), (form) => {
      form.student_id = "2";
    });
    expect(rows[0]).toMatchObject({ label: "Kind", value: "Ben", step: "child" });
  });

  test("sick: the optional comment shows its real value, never an empty line", () => {
    const { window } = loadApp();
    const rows = facts(window, "sick", Object.assign({}, SICK, { rules: { sick_comment: true } }));
    const comment = rows.find((row) => row.label === "Kommentar");
    expect(comment.value).toBe("keine Angabe");
    expect(comment.step).toBe("sickComment");
  });

  test("deregister: a weekly repeat is folded into the date row", () => {
    const { window } = loadApp();
    const rows = facts(
      window,
      "deregister",
      { children: [{ id: 1, name: "Mia" }], types: ["deregister"], rules: {}, deregister_options: ["bus"] },
      (form) => {
        form.date = "2126-09-01";
        form.repeat = "weekly";
        form.repeat_until = "2126-10-01";
      }
    );
    const range = rows.find((row) => row.label === "Zeitraum");
    expect(range.value).toBe("01.09.2126, Wöchentlich bis 01.10.2126");
    expect(range.step).toBe("deregisterWhen");
  });

  test("leave: the range row covers the full from/till span", () => {
    const { window } = loadApp();
    const rows = facts(window, "leave", { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} }, (form) => {
      form.from_date = "2126-09-10";
      form.till_date = "2126-09-12";
    });
    expect(rows.find((row) => row.label === "Zeitraum").value).toBe("10.09.2126 bis 12.09.2126");
  });

  test("leave: custom times ride in the same row as the dates", () => {
    const { window } = loadApp();
    const rows = facts(window, "leave", { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} }, (form) => {
      form.from_date = "2126-09-10";
      form.till_date = "2126-09-10";
      form.time_mode = "custom";
      form.from_time = "09:00";
      form.till_time = "11:00";
    });
    expect(rows.find((row) => row.label === "Zeitraum").value).toBe("10.09.2126, 09:00–11:00");
  });

  test("daycare: pickup only appears for an early end", () => {
    const { window } = loadApp();
    const base = { children: [{ id: 1, name: "Mia" }], types: ["daycare"], rules: {} };
    const off = facts(window, "daycare", base);
    expect(off.map((row) => row.label)).not.toContain("Abholzeit");
    const on = facts(window, "daycare", base, (form) => {
      form.daycare_kind = "early_end";
      form.pickup_time = "13:30";
    });
    expect(on.find((row) => row.label === "Abholzeit").value).toBe("13:30 Uhr");
  });

  test("every tappable row names a step the wizard can actually open", () => {
    const { window } = loadApp();
    for (const type of ["sick", "leave", "deregister", "daycare"]) {
      const wz = openWizard(window, type, {
        children: [{ id: 1, name: "Mia" }],
        types: [type],
        rules: { sick_comment: true, daycare_reason_required: false },
        deregister_options: ["bus"],
        day_options: { from: [{ value: "2126-09-02" }], till: [{ value: "2126-09-02" }] },
      });
      const rows = window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
      for (const row of rows.filter((entry) => entry.step)) {
        wz.go(row.step);
        expect(wz.step, `${type}/${row.label}`).toBe(row.step);
      }
    }
  });
});
