import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("sheet header controls", () => {
  test("sheets close via the X button", () => {
    const { window } = loadApp();
    window.eval("openSheet(() => sheet('Titel', [document.createElement('div')]));");
    expect(window.eval("!!state.sheet")).toBe(true);
    window.eval("closeSheet();");
    expect(window.eval("state.sheet")).toBeNull();
  });
});
