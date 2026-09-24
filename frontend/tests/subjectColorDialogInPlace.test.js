import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("subject color dialog updates one row in place", () => {
  test("picking a color leaves the names page node untouched and preserves its scroll position", () => {
    const { window, document } = loadApp();
    window.eval(`
      state.config = { connections: [{ id: "s1", subjects: { D: { label: "Deutsch", color: "" }, M: { label: "Mathe", color: "" } } }] };
      openNamesPage();
    `);

    const pageNode = document.querySelector(".names-page");
    const screen = document.querySelector(".screen");
    expect(pageNode).not.toBeNull();
    screen.scrollTop = 123;

    const rows = document.querySelectorAll(".field-group .cell");
    const firstSwatch = rows[0].querySelector(".swatch-trigger");
    const secondSwatch = rows[1].querySelector(".swatch-trigger");
    const secondSwatchBackgroundBefore = secondSwatch.style.background;

    firstSwatch.click();
    const dialog = document.querySelector(".color-dialog");
    const paletteButton = dialog.querySelectorAll(".swatch-grid .swatch-btn")[1];
    const pickedBackground = paletteButton.style.background;
    const names = window.eval("SUBJECT_COLOR_NAMES");
    paletteButton.click();

    expect(document.querySelector(".names-page")).toBe(pageNode);
    expect(document.querySelector(".screen").scrollTop).toBe(123);
    expect(firstSwatch.style.background).toBe(pickedBackground);
    expect(secondSwatch.style.background).toBe(secondSwatchBackgroundBefore);
    expect(window.eval("state.pageForm.subjects.D.color")).toBe(names[1]);
    expect(window.eval("state.pageForm.subjects.M.color")).toBe("");
  });

  test("the dialog is a nested sheet over the names page and its close button dismisses it", () => {
    const { document } = loadApp();
    const { window } = { window: document.defaultView };
    window.eval(`
      state.config = { connections: [{ id: "s1", subjects: { D: { label: "Deutsch", color: "green" } } }] };
      openNamesPage();
    `);
    document.querySelector(".swatch-trigger").click();
    const dialog = document.querySelector(".color-dialog-scrim .sheet.color-dialog");
    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute("role")).toBe("dialog");
    expect(dialog.querySelector(".sheet-title").textContent).toContain("D");
    dialog.querySelector(".sheet-close").click();
    expect(document.querySelector(".color-dialog")).toBeNull();
    expect(document.querySelector(".names-page")).not.toBeNull();
  });
});
