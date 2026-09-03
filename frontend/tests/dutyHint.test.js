import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

function reviewBody(window, rules) {
  const wz = openWizard(window, "sick", {
    children: [{ id: 1 }],
    types: ["sick"],
    rules,
    day_options: { from: [{ value: "2126-09-01", label: "heute" }], till: [{ value: "2126-09-01", label: "heute" }] },
  });
  wz.go("review");
  return wz;
}

describe("[P106] duty-to-report hint", () => {
  test("uses the school's duty_hint when it is filled", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, { duty_hint: "Schul-spezifischer Hinweistext." });
    expect(wz.body.textContent).toContain("Schul-spezifischer Hinweistext.");
  });

  test("falls back to the generic IfSG hint when duty_hint is empty", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, { duty_hint: "" });
    expect(wz.body.textContent).toContain("Infektionsschutzgesetz");
  });
});

describe("[E2] the duty-to-report switch is the first thing on the review card", () => {
  test("sick: the switch sits above the fact list and defaults to off", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, {});
    const review = wz.body.querySelector(".sw-review");
    expect(review.firstElementChild.classList.contains("sw-duty")).toBe(true);
    const box = review.querySelector('input[type="checkbox"]');
    expect(box.checked).toBe(false);
    expect(wz.form.duty_to_report).toBe(false);
    box.checked = true;
    box.dispatchEvent(new window.Event("change"));
    expect(wz.form.duty_to_report).toBe(true);
  });

  test("the hint is behind a disclosure line, not a block that eats the step", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, {});
    const details = wz.body.querySelector(".sw-duty details");
    expect(details).not.toBeNull();
    expect(details.open).toBe(false);
    expect(details.querySelector("summary").textContent).toBe("Was ist meldepflichtig?");
  });

  test("no other type shows the duty switch", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", {
      children: [{ id: 1 }],
      types: ["deregister"],
      rules: {},
      deregister_options: ["bus"],
    });
    wz.go("review");
    expect(wz.body.querySelector(".sw-duty")).toBeNull();
  });
});
