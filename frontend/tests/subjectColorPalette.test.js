import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderSubjectsSheet(window, subjects) {
  const run = window.eval(`
    (function (subjects) {
      state.config = { subjects };
      state.sheetForm = null;
      return namesSheet();
    })
  `);
  return run(subjects);
}

describe("[P108] subject color palette", () => {
  test("shows one swatch button per palette color plus an Automatisch option in the color dialog", () => {
    const { window, document } = loadApp();
    const sheet = renderSubjectsSheet(window, { D: { label: "Deutsch", color: "" } });
    const swatchColors = window.eval("SUBJECT_COLORS");
    sheet.querySelector(".swatch-trigger").click();
    const dialog = document.querySelector(".color-dialog");
    const buttons = dialog.querySelectorAll(".swatch-row .swatch-btn");
    expect(buttons.length).toBe(swatchColors.length + 1);
    expect(dialog.querySelector(".swatch-btn.auto")).not.toBeNull();
  });

  test("clicking a palette color marks it pressed; clicking Automatisch clears the color", () => {
    const { window, document } = loadApp();
    const sheet = renderSubjectsSheet(window, { D: { label: "Deutsch", color: "" } });
    const swatchColors = window.eval("SUBJECT_COLORS");

    sheet.querySelector(".swatch-trigger").click();
    let dialog = document.querySelector(".color-dialog");
    dialog.querySelectorAll(".swatch-row .swatch-btn")[0].click();
    let draft = window.eval("state.sheetForm.subjects");
    expect(draft.D.color).toBe(swatchColors[0]);
    expect(document.querySelector(".color-dialog")).toBeNull();

    sheet.querySelector(".swatch-trigger").click();
    dialog = document.querySelector(".color-dialog");
    dialog.querySelector(".swatch-btn.auto").click();
    draft = window.eval("state.sheetForm.subjects");
    expect(draft.D.color).toBe("");
  });

  test("[P174] a picked color is marked as chosen by the user, Automatisch hands it back", () => {
    const { window, document } = loadApp();
    const sheet = renderSubjectsSheet(window, { D: { label: "Deutsch", color: "" } });

    sheet.querySelector(".swatch-trigger").click();
    document.querySelector(".color-dialog").querySelectorAll(".swatch-row .swatch-btn")[3].click();
    expect(window.eval("state.sheetForm.subjects").D.color_source).toBe("user");

    sheet.querySelector(".swatch-trigger").click();
    document.querySelector(".color-dialog").querySelector(".swatch-btn.auto").click();
    expect(window.eval("state.sheetForm.subjects").D.color_source).toBe("auto");
  });

  test("[P174] the palette matches the backend palette exactly", () => {
    const fs = require("node:fs");
    const path = require("node:path");
    const { window } = loadApp();
    const source = fs.readFileSync(path.resolve(__dirname, "..", "..", "backend", "app", "mapping.py"), "utf8");
    const block = source.slice(source.indexOf("DEFAULT_COLORS = ["), source.indexOf("]", source.indexOf("DEFAULT_COLORS = [")));
    const backend = block.match(/#[0-9a-f]{6}/g);
    expect(backend).toEqual(window.eval("SUBJECT_COLORS"));
  });
});
