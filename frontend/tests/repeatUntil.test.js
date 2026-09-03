import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

const DEREGISTER = { children: [{ id: 1 }], types: ["deregister"], rules: {}, deregister_options: ["bus"] };
const DAYCARE = { children: [{ id: 1 }], types: ["daycare"], rules: {} };

describe("[P107] weekly repeat asks for an end date", () => {
  test("deregister: weekly adds a 'Wiederholen bis' step with the honest info text", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", DEREGISTER);
    wz.form.repeat = "weekly";
    wz.go("repeatUntil");
    expect(wz.body.textContent).toContain("Wiederholen bis");
    expect(wz.body.textContent).toContain("Wiederholt sich wöchentlich bis zum gewählten Datum.");
    expect(wz.body.textContent).not.toContain("ungeprüft");
  });

  test("deregister: weekly without an end date is a named problem with a step to jump to", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", DEREGISTER);
    wz.form.repeat = "weekly";
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.text).toBe("Bitte ein Enddatum für die Wiederholung wählen.");
    expect(entry.step).toBe("repeatUntil");
    expect(window.eval("absenceProblem(state.absenceForm, state.absence.data)")).toBe(entry.text);
  });

  test("deregister: an end date before the start date is rejected too", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", DEREGISTER);
    wz.form.repeat = "weekly";
    wz.form.date = "2126-09-10";
    wz.form.repeat_until = "2126-09-01";
    const entry = window.eval("absenceProblemEntry(state.absenceForm, state.absence.data)");
    expect(entry.text).toBe("Das Wiederholungs-Ende darf nicht vor dem Startdatum liegen.");
    expect(entry.step).toBe("repeatUntil");
  });

  test("daycare: weekly reveals the same shared 'Wiederholen bis' step", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "daycare", DAYCARE);
    wz.form.repeat = "weekly";
    expect(wz.path).toContain("repeatUntil");
    wz.go("repeatUntil");
    expect(wz.body.textContent).toContain("Wiederholen bis");
  });

  test("deregister keeps the weekly boolean in the payload, daycare keeps the repeat string", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "deregister", DEREGISTER);
    wz.form.repeat = "weekly";
    wz.form.repeat_until = "2126-09-30";
    const deregisterPayload = window.eval("absencePayload(state.absenceForm, state.absence.data.children)");
    expect(deregisterPayload.weekly).toBe(true);
    expect(deregisterPayload.repeat).toBeUndefined();

    const wz2 = openWizard(window, "daycare", DAYCARE);
    wz2.form.repeat = "weekly";
    wz2.form.repeat_until = "2126-09-30";
    const daycarePayload = window.eval("absencePayload(state.absenceForm, state.absence.data.children)");
    expect(daycarePayload.repeat).toBe("weekly");
    expect(daycarePayload.weekly).toBeUndefined();
  });
});
