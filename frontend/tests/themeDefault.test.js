import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

describe("new installs follow the system appearance", () => {
  test("nothing stored reads as system and writes nothing", () => {
    const { window } = loadApp();
    window.localStorage.removeItem("theme");
    expect(window.eval("readTheme()")).toBe("system");
    expect(window.localStorage.getItem("theme")).toBeNull();
    expect(window.eval("THEMES")).toContain("system");
    expect(window.eval("themeLabel(undefined)")).toBe(label(window, "settings.theme.system.label"));
  });

  test("a stored choice stays, an unknown value falls back to system", () => {
    const { window } = loadApp();
    for (const value of ["light", "dark", "system"]) {
      window.localStorage.setItem("theme", value);
      expect(window.eval("readTheme()")).toBe(value);
      expect(window.localStorage.getItem("theme")).toBe(value);
    }
    window.localStorage.setItem("theme", "sepia");
    expect(window.eval("readTheme()")).toBe("system");
  });
});
