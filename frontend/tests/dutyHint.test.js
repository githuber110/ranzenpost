import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));

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

function openDutySheet(window, wz) {
  wz.body.querySelector(".sw-duty-more").click();
  return window.eval("state.sheet()");
}

describe("[P106] duty-to-report hint", () => {
  test("uses the school's duty_hint when it is filled", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, { duty_hint: "Schul-spezifischer Hinweistext." });
    expect(openDutySheet(window, wz).textContent).toContain("Schul-spezifischer Hinweistext.");
  });

  test("falls back to the generic IfSG hint when duty_hint is empty", () => {
    const { window } = loadApp();
    const wz = reviewBody(window, { duty_hint: "" });
    expect(openDutySheet(window, wz).textContent).toContain("Infektionsschutzgesetz");
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
    const more = wz.body.querySelector(".sw-duty .sw-duty-more");
    expect(more).not.toBeNull();
    expect(more.tagName).toBe("BUTTON");
    expect(more.textContent).toBe("Was ist meldepflichtig?");
  });

  test("[P192] the legal text is never clipped: it arrives whole, in a container that scrolls", () => {
    const { window } = loadApp();
    const long = "Meldepflichtig ist eine ganze Reihe von Krankheiten. ".repeat(12).trim();
    const wz = reviewBody(window, { duty_hint: long });
    expect(wz.body.textContent).not.toContain("…");
    expect(wz.body.querySelector(".row-sub")).toBeNull();
    const panel = openDutySheet(window, wz);
    const paragraph = panel.querySelector(".sheet-body p");
    expect(paragraph.textContent).toBe(long);
    expect(paragraph.className).toBe("dlg-text");
    expect(paragraph.getAttribute("dir")).toBe("auto");
  });

  test("[P192] a fact row that cannot be tapped is allowed to wrap instead of clipping", () => {
    const css = fs.readFileSync(path.resolve(dirname, "..", "wizard.css"), "utf8");
    const clipped = /\.sw-fact-value\s*\{([^}]*)\}/.exec(css);
    expect(clipped[1]).toMatch(/text-overflow:\s*ellipsis/);
    const fixed = /\.sw-fact\.fixed\s+\.sw-fact-value\s*\{([^}]*)\}/.exec(css);
    expect(fixed).not.toBeNull();
    expect(fixed[1]).toMatch(/white-space:\s*normal/);
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
