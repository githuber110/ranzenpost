import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P101] theme label", () => {
  test("system option is labelled 'System' with the endgeraet description, internal value stays 'system'", () => {
    const { window } = loadApp();
    const themes = window.eval("THEMES");
    expect(themes).toContain("system");
    expect(window.themeLabel("system")).toBe("System");
    expect(window.t("settings.theme.system.hint")).toContain("Endgerätes");
  });

  test("[P134] every theme key resolves to a translated label and hint", () => {
    const { window } = loadApp();
    for (const key of window.eval("THEMES")) {
      expect(window.t(`settings.theme.${key}.label`)).not.toBe(`settings.theme.${key}.label`);
      expect(window.t(`settings.theme.${key}.hint`)).not.toBe(`settings.theme.${key}.hint`);
    }
  });
});
