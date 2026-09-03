import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

const SICK_DATA = {
  children: [{ id: 1 }],
  types: ["sick"],
  rules: { sick_by_lesson: true },
  day_options: { from: [{ value: "2126-09-01", label: "Di" }], till: [{ value: "2126-09-01", label: "Di" }] },
  period_labels: [
    { number: 1, label: "1. Stunde" },
    { number: 2, label: "2. Stunde" },
  ],
};

describe("[C06] sick wizard: Ganztaegig/Stundenweise is its own step", () => {
  test("defaults to Ganztaegig, the periods step is not in the path, from_period stays empty", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    const options = wz.options();
    expect(options.length).toBe(2);
    expect(options[0].getAttribute("aria-pressed")).toBe("true");
    expect(options[1].getAttribute("aria-pressed")).toBe("false");
    expect(wz.path).not.toContain("sickPeriods");
    expect(wz.form.from_period).toBe("");
  });

  test("choosing Stundenweise adds the periods step and prefills first/last lesson", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    wz.options()[1].click();
    expect(wz.form.hours_mode).toBe("byLesson");
    expect(wz.path).toContain("sickPeriods");
    expect(wz.form.from_period).toBe("1");
    expect(wz.form.till_period).toBe("2");
    wz.go("sickPeriods");
    expect(wz.body.textContent).toContain("Ab Stunde");
    expect(wz.body.textContent).toContain("Bis Stunde");
  });

  test("choosing Ganztaegig again drops the periods and says so in the status line", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", SICK_DATA);
    wz.go("sickHours");
    wz.options()[1].click();
    wz.options()[0].click();
    expect(wz.form.hours_mode).toBe("full");
    expect(wz.form.from_period).toBe("");
    expect(wz.form.till_period).toBe("");
    expect(wz.status).toBe("Die Stundenangaben werden verworfen.");
    expect(wz.path).not.toContain("sickPeriods");
  });

  test("without sick_by_lesson the hours step never appears", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", {
      children: [{ id: 1 }],
      types: ["sick"],
      rules: {},
      day_options: { from: [{ value: "2126-09-01" }], till: [{ value: "2126-09-01" }] },
    });
    expect(wz.path).toEqual(["sickWhen", "review"]);
  });
});

describe("[C06] leave wizard: prefilled subject and the reasoning hint", () => {
  test("the subject step carries the date-specific text as a real value, not a placeholder", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", { children: [{ id: 1 }], types: ["leave"], rules: {} });
    const expected = window.eval(`showDate(${JSON.stringify(wz.form.from_date)})`);
    wz.go("leaveSubject");
    const input = wz.body.querySelector('input[aria-label="Betreff"]');
    expect(input.value).toBe(`z. B. Beurlaubung am ${expected}`);
  });

  test("the request step keeps the reasoning hint under the field", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", { children: [{ id: 1 }], types: ["leave"], rules: {} });
    wz.go("leaveBody");
    expect(wz.body.textContent).toContain("Begründung für die Schule");
  });
});

describe("[C06] daycare wizard: weekly repeat is a segment on the date step", () => {
  test("defaults to once and offers exactly two repeat options", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} });
    expect(wz.form.repeat).toBe("once");
    wz.go("daycareWhen");
    const segment = Array.from(wz.body.querySelectorAll(".opt-row .opt"));
    expect(segment.map((node) => node.textContent)).toEqual(["Einmalig", "Wöchentlich wiederholen"]);
    expect(segment[0].getAttribute("aria-pressed")).toBe("true");
    expect(wz.path).not.toContain("repeatUntil");
  });

  test("choosing weekly adds the repeat-until step", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", { children: [{ id: 1 }], types: ["daycare"], rules: {} });
    wz.go("daycareWhen");
    wz.body.querySelectorAll(".opt-row .opt")[1].click();
    expect(wz.form.repeat).toBe("weekly");
    expect(wz.path).toContain("repeatUntil");
    wz.go("repeatUntil");
    expect(wz.body.textContent).toContain("Wiederholen bis");
  });
});

describe("[C06] the footer status line replaces the validation toast", () => {
  test("a missing mandatory answer explains itself in the status line, no toast", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", {
      children: [{ id: 1 }],
      types: ["deregister"],
      rules: {},
      deregister_options: [],
    });
    expect(wz.step).toBe("deregisterTarget");
    wz.nextButton.click();
    expect(wz.nextButton.getAttribute("aria-disabled")).toBe("true");
    expect(wz.status).toBe("Pflichtangabe");
    expect(window.eval("!!state.toast")).toBe(false);
  });

  test("answering clears the status line and unlocks the button", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", {
      children: [{ id: 1 }],
      types: ["deregister"],
      rules: {},
      deregister_options: ["bus", "lunch"],
    });
    wz.form.deregister_from = "";
    wz.go("deregisterTarget");
    wz.nextButton.click();
    expect(wz.status).toBe("Pflichtangabe");
    wz.options()[1].click();
    expect(wz.form.deregister_from).toBe("lunch");
    expect(wz.status).toBe("");
    expect(wz.nextButton.getAttribute("aria-disabled")).toBe("false");
  });
});
