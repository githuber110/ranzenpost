import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

const SICK_DATA = {
  children: [{ id: 1, name: "Mia" }],
  types: ["sick"],
  rules: { sick_by_lesson: true },
  day_options: { from: [{ value: "2126-09-01", label: "heute" }], till: [{ value: "2126-09-01", label: "heute" }] },
  period_labels: [
    { number: 1, label: "1. Stunde" },
    { number: 2, label: "2. Stunde" },
  ],
};

const DAYCARE_DATA = {
  children: [{ id: 1, name: "Mia" }],
  types: ["daycare"],
  rules: { daycare_pickup_times: ["13:30", "14:30"] },
};

const LEAVE_DATA = { children: [{ id: 1, name: "Mia" }], types: ["leave"], rules: {} };

describe("[P194] a mode choice unfolds its small follow-up inside the very same step", () => {
  test("sick: lesson-wise reporting shows the lesson pickers below the segment, without a new step", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    const before = wz.path.length;
    expect(wz.body.querySelector(".sw-reveal")).toBeNull();
    wz.options()[1].click();
    expect(wz.step).toBe("sickHours");
    expect(wz.path.length).toBe(before);
    expect(wz.body.querySelector(".sw-reveal .sel")).not.toBeNull();
    wz.options()[0].click();
    expect(wz.body.querySelector(".sw-reveal")).toBeNull();
  });

  test("daycare: an early pickup shows the time right below the choice, without a new step", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", DAYCARE_DATA);
    wz.go("daycareKind");
    const before = wz.path.length;
    expect(wz.body.querySelector(".sw-reveal")).toBeNull();
    wz.options()[1].click();
    expect(wz.step).toBe("daycareKind");
    expect(wz.path.length).toBe(before);
    expect(wz.body.querySelector(".sw-reveal .sel")).not.toBeNull();
    expect(wz.path).not.toContain("daycarePickup");
  });

  test("the table of unfolding pairs is the single source of truth for the path", () => {
    const { window } = loadApp();
    const reveals = window.eval("Object.keys(ABSENCE_REVEALS).map((host) => [host, ABSENCE_REVEALS[host].step])");
    expect(reveals.length).toBeGreaterThan(0);
    for (const [host, revealed] of reveals) {
      expect(window.eval(`absenceStepHost(${JSON.stringify(revealed)})`)).toBe(host);
      expect(window.eval(`absenceStepHost(${JSON.stringify(host)})`)).toBe(host);
      expect(window.eval(`ABSENCE_STEP_TITLES[${JSON.stringify(revealed)}]`)).toBeTruthy();
      expect(window.eval(`absenceRevealName(${JSON.stringify(host)})`).length).toBeGreaterThan(0);
      expect(window.eval(`ABSENCE_STEP_BUILDERS[${JSON.stringify(revealed)}]`)).toBeTruthy();
    }
  });

  test("a revealed step never turns up in the path, whatever the answers are", () => {
    const { window } = loadApp();
    const revealed = window.eval("Object.keys(ABSENCE_REVEALS).map((host) => ABSENCE_REVEALS[host].step)");
    const cases = [
      ["sick", SICK_DATA, { hours_mode: "byLesson", from_period: "1", till_period: "2" }],
      ["sick", SICK_DATA, { hours_mode: "full" }],
      ["daycare", DAYCARE_DATA, { daycare_kind: "early_end", pickup_time: "13:30" }],
      ["daycare", DAYCARE_DATA, { daycare_kind: "deregister" }],
    ];
    for (const [type, data, patch] of cases) {
      const wz = openWizard(window, type, data);
      Object.assign(wz.form, patch);
      for (const id of revealed) expect(wz.path, `${type}/${id}`).not.toContain(id);
    }
  });
});

describe("[P194] the progress dots follow the shorter path", () => {
  test("a step that unfolds in place carries no dashed 'maybe' dot any more", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    expect(wz.dots.filter((dot) => dot.classList.contains("maybe")).length).toBe(0);
    expect(wz.dots.length).toBe(wz.path.length);
    wz.options()[1].click();
    expect(wz.dots.filter((dot) => dot.classList.contains("maybe")).length).toBe(0);
    expect(wz.dots.length).toBe(wz.path.length);
  });

  test("a step that still adds a real step keeps its dashed dot", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", LEAVE_DATA);
    wz.go("leaveFrom");
    expect(wz.dots.filter((dot) => dot.classList.contains("maybe")).length).toBe(1);
  });
});

describe("[P194] everything that points at a step points at the one that is shown", () => {
  test("a lock on the lesson order names the step the user can actually see", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    Object.assign(wz.form, { hours_mode: "byLesson", from_period: "2", till_period: "1" });
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.step).toBe("sickHours");
    wz.go("review");
    expect(wz.step).toBe("sickHours");
    expect(wz.body.querySelector(".sw-reveal")).not.toBeNull();
  });

  test("a missing pickup time sends the user to the choice step that holds the field", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} });
    Object.assign(wz.form, { daycare_kind: "early_end", pickup_time: "" });
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.step).toBe("daycareKind");
    wz.go("review");
    expect(wz.step).toBe("daycareKind");
  });

  test("the review row for the pickup opens the step that shows it", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", DAYCARE_DATA);
    Object.assign(wz.form, { daycare_kind: "early_end", pickup_time: "13:30" });
    wz.go("review");
    const rows = window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
    const pickup = rows.find((row) => row.step === "daycarePickup");
    expect(pickup).not.toBeUndefined();
    window.eval('absenceOpenStep("daycarePickup")');
    expect(wz.step).toBe("daycareKind");
  });
});

describe("[P194] the follow-ups that do not fit the measured budget keep their own step", () => {
  test("second leave day, own times and the weekly end date stay separate steps", () => {
    const { window } = loadApp();
    const leave = openWizard(window, "leave", LEAVE_DATA);
    Object.assign(leave.form, { duration: "more", time_mode: "custom" });
    expect(leave.path).toContain("leaveTill");
    expect(leave.path).toContain("leaveTimes");

    const deregister = openWizard(window, "deregister", {
      children: [{ id: 1 }],
      types: ["deregister"],
      rules: {},
      deregister_options: ["bus"],
    });
    deregister.form.repeat = "weekly";
    expect(deregister.path).toContain("repeatUntil");

    const daycare = openWizard(window, "daycare", DAYCARE_DATA);
    daycare.form.repeat = "weekly";
    expect(daycare.path).toContain("repeatUntil");
  });
});

describe("[P194] the screen reader is told about a field, not about a step", () => {
  test("unfolding and folding announce the field keys", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    const spoken = [];
    window.eval("absenceFlow.announce = function (text) { window.__spoken.push(text); }");
    window.__spoken = spoken;
    wz.options()[1].click();
    wz.options()[0].click();
    expect(spoken).toEqual([
      window.eval(`t("absence.wizard.fieldShown", { name: t("absence.wizard.step.sick.periods") })`),
      window.eval(`t("absence.wizard.fieldHidden", { name: t("absence.wizard.step.sick.periods") })`),
    ]);
  });
});
