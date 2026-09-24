import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("absence empty state: two sentences, no dangling reference", () => {
  test("absence.empty.text keeps exactly two sentences and drops the dead 'Vergangene Abwesenheiten' pointer", () => {
    const { window } = loadApp();
    const text = window.t("absence.empty.text");
    expect(text).toBe(
      "Aktuelle und zukünftige Meldungen erscheinen hier. Vergangene Krankmeldungen blendet IServ automatisch aus."
    );
    expect(text).not.toContain("Vergangene Abwesenheiten");
    expect(text.split(". ").length).toBe(2);
  });
});
