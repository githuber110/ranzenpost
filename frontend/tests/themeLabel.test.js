import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("theme label", () => {
  test("system option is labelled 'System' with the this-device description, internal value stays 'system'", () => {
    const { window } = loadApp();
    const themes = window.eval("THEMES");
    expect(themes).toContain("system");
    expect(window.themeLabel("system")).toBe("System");
    expect(window.t("settings.theme.system.hint")).toBe("Wie auf diesem Gerät eingestellt");
    expect(window.t("language.system.hint")).toBe(window.t("settings.theme.system.hint"));
  });

  test("every theme key resolves to a translated label and hint", () => {
    const { window } = loadApp();
    for (const key of window.eval("THEMES")) {
      expect(window.t(`settings.theme.${key}.label`)).not.toBe(`settings.theme.${key}.label`);
      expect(window.t(`settings.theme.${key}.hint`)).not.toBe(`settings.theme.${key}.hint`);
    }
  });
});
