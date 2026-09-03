import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

const twoChildren = [
  { id: 11, name: "Alice", class_name: "3b" },
  { id: 22, name: "Bella", class_name: "1a" },
];

function data(children, extra) {
  return Object.assign(
    {
      children,
      rules: {},
      types: ["sick", "leave"],
      deregister_options: ["bus"],
      day_options: { from: [{ value: "2126-09-01" }], till: [{ value: "2126-09-01" }] },
    },
    extra || {}
  );
}

describe("[C08] >1 child: the child question is a real wizard step, never a sheet", () => {
  test("the type step is first, choosing a type does not navigate on its own", () => {
    const { window } = loadApp();
    const wz = openWizard(window, null, data(twoChildren));
    expect(wz.step).toBe("type");
    expect(wz.path.slice(0, 2)).toEqual(["type", "child"]);
    expect(wz.form.type).toBe("sick");
    wz.options()[1].click();
    expect(wz.step).toBe("type");
    expect(wz.form.type).toBe("leave");
  });

  test("the child step lists both children and only Weiter moves on", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", data(twoChildren));
    wz.go("child");
    const names = wz.options().map((node) => node.querySelector("b").textContent);
    expect(names).toEqual(["Alice · 3b", "Bella · 1a"]);
    expect(wz.form.student_id).toBe("");
    expect(wz.nextButton.getAttribute("aria-disabled")).toBe("true");
    wz.options()[1].click();
    expect(wz.step).toBe("child");
    expect(wz.form.student_id).toBe("22");
    expect(wz.nextButton.getAttribute("aria-disabled")).toBe("false");
  });

  test("no child chosen blocks the review page and names the child step as the target", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", data(twoChildren));
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.text).toBe("Bitte das Kind auswählen.");
    expect(entry.step).toBe("child");
    wz.go("review");
    expect(wz.step).toBe("child");
    expect(wz.status).toBe("Bitte das Kind auswählen.");
  });

  test("the chosen child rides in the progress row and the review facts, not in a dead chip", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", data(twoChildren), 22);
    expect(wz.node.querySelector(".child-switch")).toBeNull();
    const lead = wz.node.querySelector(".sw-lead-btn");
    expect(lead).not.toBeNull();
    expect(lead.getAttribute("aria-label")).toBe("Bella");
    lead.click();
    expect(wz.step).toBe("child");
    const facts = window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
    expect(facts[0].label).toBe("Kind");
    expect(facts[0].value).toBe("Bella");
    expect(facts[0].step).toBe("child");
  });
});

describe("[C08] exactly 1 child: the child step is skipped entirely", () => {
  test("the path has no child step and the single child is preselected", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "sick", data([{ id: 1, name: "Alice", class_name: "3b" }]));
    expect(wz.path).not.toContain("child");
    expect(wz.form.student_id).toBe("1");
    expect(wz.node.querySelector(".sw-lead-btn")).toBeNull();
    const facts = window.eval("absenceReviewFacts(state.absenceForm, state.absence.data)");
    expect(facts.map((fact) => fact.label)).not.toContain("Kind");
  });
});
