import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P124] subject color dialog updates one row in place", () => {
  test("picking a color leaves the sheet body node untouched and preserves its scroll position", () => {
    const { window, document } = loadApp();
    window.eval(`
      state.config = { subjects: { D: { label: "Deutsch", color: "" }, M: { label: "Mathe", color: "" } } };
      openSheet(namesSheet);
    `);

    const sheetBody = document.querySelector(".sheet-body");
    expect(sheetBody).not.toBeNull();
    sheetBody.scrollTop = 123;

    const rows = document.querySelectorAll(".field-group .cell");
    const firstSwatch = rows[0].querySelector(".swatch-trigger");
    const secondSwatch = rows[1].querySelector(".swatch-trigger");
    const secondSwatchBackgroundBefore = secondSwatch.style.background;

    firstSwatch.click();
    const dialog = document.querySelector(".color-dialog");
    const paletteButton = dialog.querySelectorAll(".swatch-row .swatch-btn")[1];
    const pickedBackground = paletteButton.style.background;
    const swatchColors = window.eval("SUBJECT_COLORS");
    paletteButton.click();

    expect(document.querySelector(".sheet-body")).toBe(sheetBody);
    expect(sheetBody.scrollTop).toBe(123);
    expect(firstSwatch.style.background).toBe(pickedBackground);
    expect(secondSwatch.style.background).toBe(secondSwatchBackgroundBefore);
    expect(window.eval("state.sheetForm.subjects.D.color")).toBe(swatchColors[1]);
    expect(window.eval("state.sheetForm.subjects.M.color")).toBe("");
  });
});
