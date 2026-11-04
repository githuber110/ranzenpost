import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

function seed(window, term) {
  evalWith(window, "state.absence = { data: { sick_note_term: testArgs[0], types: ['sick', 'leave'] }, connectionId: '' }", term);
}

describe("the school's own word for a sick note", () => {
  test("it replaces the sick note label in German", () => {
    const { window } = loadApp();
    seed(window, "Fehlzeitenmeldung");
    expect(window.eval("absenceTypeLabel('sick')")).toBe("Fehlzeitenmeldung");
    expect(window.eval("absenceEntryLabel({ kind: 'sick', label_key: 'absence.entry.kind.sick' })")).toBe("Fehlzeitenmeldung");
  });

  test("the other types and a school without a word keep the usual label", () => {
    const { window } = loadApp();
    seed(window, "Fehlzeitenmeldung");
    expect(window.eval("absenceTypeLabel('leave')")).toBe(window.t("absence.type.leave.label"));
    seed(window, "");
    expect(window.eval("absenceTypeLabel('sick')")).toBe("Krankmeldung");
    expect(window.eval("absenceEntryLabel({ kind: 'sick', label_key: 'absence.entry.kind.sick' })")).toBe("Krankmeldung");
  });
});

describe("the first load of the app", () => {
  test("letters and absences that are already loading are not asked for again", async () => {
    const { window } = loadApp();
    const asked = [];
    window.fetch = (input) => {
      asked.push(String(input));
      return new Promise(() => {});
    };
    window.eval("autoLoad(lettersLoadKey('current'), () => loadLetters('current'))");
    window.eval("autoLoad(lettersLoadKey('current'), () => loadLetters('current'))");
    window.eval("autoLoad('absence', loadAbsences)");
    window.eval("autoLoad('absence', loadAbsences)");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(asked.filter((url) => url.includes("api/letters")).length).toBe(1);
    expect(asked.filter((url) => url.includes("api/absences")).length).toBeLessThanOrEqual(1);
  });
});
