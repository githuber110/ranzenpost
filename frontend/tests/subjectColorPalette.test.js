import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { loadApp } from "./loadApp.js";

function renderSubjectsSheet(window, subjects) {
  const run = window.eval(`
    (function (subjects) {
      state.config = { connections: [{ id: "s1", subjects }] };
      state.pageForm = null;
      return namesPageView();
    })
  `);
  return run(subjects);
}

function openDialog(window, document, subjects) {
  const sheet = renderSubjectsSheet(window, subjects || { D: { label: "Deutsch", color: "" } });
  sheet.querySelector(".swatch-trigger").click();
  return { sheet, dialog: document.querySelector(".color-dialog") };
}

describe("subject colour palette", () => {
  test("shows one swatch per palette colour plus an automatic option in a grid", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document);
    const names = window.eval("SUBJECT_COLOR_NAMES");
    expect(names.length).toBe(24);
    const buttons = dialog.querySelectorAll(".swatch-grid .swatch-btn");
    expect(buttons.length).toBe(names.length + 1);
    expect(dialog.querySelector(".swatch-btn.auto")).not.toBeNull();
    expect([...buttons].slice(0, names.length).map((button) => button.getAttribute("data-color"))).toEqual(names);
  });

  test("every swatch fills from its theme token, carries its translated name and a check mark", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document);
    const de = JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "i18n", "de.json"), "utf8"));
    for (const button of dialog.querySelectorAll(".swatch-grid .swatch-btn:not(.auto)")) {
      const name = button.getAttribute("data-color");
      expect(button.style.background).toBe(`var(--subject-${name}-fill)`);
      expect(button.style.color).toBe(`var(--subject-${name}-ink)`);
      expect(button.getAttribute("aria-label")).toBe(de[`colour.${name}`]);
      expect(button.querySelector(".ico-slot svg")).not.toBeNull();
    }
  });

  test("clicking a palette colour stores its name; clicking automatic clears the colour", () => {
    const { window, document } = loadApp();
    const { sheet, dialog } = openDialog(window, document);
    dialog.querySelectorAll(".swatch-grid .swatch-btn")[1].click();
    let draft = window.eval("state.pageForm.subjects");
    expect(draft.D.color).toBe("yellow");
    expect(document.querySelector(".color-dialog")).toBeNull();

    sheet.querySelector(".swatch-trigger").click();
    const reopened = document.querySelector(".color-dialog");
    expect(reopened.querySelector('.swatch-btn[data-color="yellow"]').getAttribute("aria-pressed")).toBe("true");
    expect(reopened.querySelectorAll('.swatch-btn[aria-pressed="true"]').length).toBe(1);
    reopened.querySelector(".swatch-btn.auto").click();
    draft = window.eval("state.pageForm.subjects");
    expect(draft.D.color).toBe("");
  });

  test("a picked colour is marked as chosen by the user, automatic hands it back", () => {
    const { window, document } = loadApp();
    const { sheet, dialog } = openDialog(window, document);
    dialog.querySelectorAll(".swatch-grid .swatch-btn")[3].click();
    expect(window.eval("state.pageForm.subjects").D.color_source).toBe("user");

    sheet.querySelector(".swatch-trigger").click();
    document.querySelector(".color-dialog").querySelector(".swatch-btn.auto").click();
    expect(window.eval("state.pageForm.subjects").D.color_source).toBe("auto");
  });

  test("the palette matches the backend palette exactly", () => {
    const { window } = loadApp();
    const source = fs.readFileSync(path.resolve(__dirname, "..", "..", "backend", "app", "mapping.py"), "utf8");
    const block = source.slice(source.indexOf("PALETTE = ("), source.indexOf("\n)\n", source.indexOf("PALETTE = (")));
    const backend = [...block.matchAll(/\("([a-z]+)", ("#[0-9a-f]{6}"(?:, "#[0-9a-f]{6}"){4})\)/g)].map((match) => [match[1], ...JSON.parse(`[${match[2]}]`)]);
    const frontend = window.eval("RanzenpostColour.PALETTE").map((entry) => [entry.name, entry.base, entry.lightFill, entry.lightBar, entry.darkFill, entry.darkBar]);
    expect(backend.length).toBe(24);
    expect(frontend).toEqual(backend);
  });

  test("the palette tokens in styles.css are the ones colour.js derives", () => {
    const { window } = loadApp();
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    const rootBlock = css.slice(css.indexOf(":root {"), css.indexOf("\n}\n", css.indexOf(":root {")));
    const darkStart = css.indexOf(':root[data-theme="dark"] {');
    const darkBlock = css.slice(darkStart, css.indexOf("\n}\n", darkStart));
    const read = (block) => Object.fromEntries([...block.matchAll(/--(subject-[a-z]+-(?:fill|bar|ink)):\s*(#[0-9a-f]{6});/g)].map((match) => [match[1], match[2]]));
    expect(read(rootBlock)).toEqual(window.eval('RanzenpostColour.tokens("light")'));
    expect(read(darkBlock)).toEqual(window.eval('RanzenpostColour.tokens("dark")'));
  });
});

describe("own colour", () => {
  test("the picker and the hex field start from the current colour and stay in sync both ways", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document, { D: { label: "Deutsch", color: "blue" } });
    const picker = dialog.querySelector(".colour-picker");
    const hex = dialog.querySelector(".colour-hex");
    expect(picker.getAttribute("type")).toBe("color");
    expect(picker.value).toBe("#2a66d6");
    expect(hex.value).toBe("#2a66d6");
    expect(hex.getAttribute("dir")).toBe("ltr");

    hex.value = "ABCDEF";
    hex.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(picker.value).toBe("#abcdef");
    expect(window.eval("state.pageForm.subjects").D.color).toBe("#abcdef");
    expect(window.eval("state.pageForm.subjects").D.color_source).toBe("user");
    expect(dialog.querySelector(".colour-own").getAttribute("aria-pressed")).toBe("true");
    expect(dialog.querySelectorAll('.swatch-grid .swatch-btn[aria-pressed="true"]').length).toBe(0);

    picker.value = "#123456";
    picker.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(hex.value).toBe("#123456");
    expect(window.eval("state.pageForm.subjects").D.color).toBe("#123456");
  });

  test("an invalid hex value is flagged and leaves the stored colour alone", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document, { D: { label: "Deutsch", color: "blue" } });
    const hex = dialog.querySelector(".colour-hex");
    hex.value = "#12345";
    hex.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(hex.getAttribute("aria-invalid")).toBe("true");
    expect(window.eval("state.pageForm.subjects").D.color).toBe("blue");
    hex.value = "#123456";
    hex.dispatchEvent(new window.Event("input", { bubbles: true }));
    expect(hex.getAttribute("aria-invalid")).toBe("false");
  });

  test("the preview shows the subject code on the fill for light and dark", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document, { D: { label: "Deutsch", color: "#abcdef", code: "DE" } });
    const cells = dialog.querySelectorAll(".colour-preview .colour-stage .tt-cell.subject");
    expect(cells.length).toBe(2);
    expect([...cells].map((cell) => cell.textContent)).toEqual(["DE", "DE"]);
    expect(cells[0].style.getPropertyValue("--subject-cell-fill")).toBe("#abcdef");
    expect(cells[0].style.getPropertyValue("--subject-cell-ink")).toBe("#000000");
    expect(dialog.querySelector(".colour-stage.light")).not.toBeNull();
    expect(dialog.querySelector(".colour-stage.dark")).not.toBeNull();

    const hex = dialog.querySelector(".colour-hex");
    hex.value = "#1a2a66";
    hex.dispatchEvent(new window.Event("input", { bubbles: true }));
    const after = dialog.querySelectorAll(".colour-preview .tt-cell.subject");
    expect(after[0].style.getPropertyValue("--subject-cell-fill")).toBe("#1a2a66");
    expect(after[0].style.getPropertyValue("--subject-cell-ink")).toBe("#ffffff");
    expect(after[1].style.getPropertyValue("--subject-cell-ink")).toBe("#ffffff");
  });

  test("a palette colour previews its light and dark fills as literal hex", () => {
    const { window, document } = loadApp();
    const { dialog } = openDialog(window, document, { D: { label: "Deutsch", color: "navy" } });
    const cells = dialog.querySelectorAll(".colour-preview .tt-cell.subject");
    expect(cells[0].style.getPropertyValue("--subject-cell-fill")).toBe("#1a2a66");
    expect(cells[1].style.getPropertyValue("--subject-cell-fill")).toBe("#243580");
    expect(cells[1].style.getPropertyValue("--subject-bar")).toBe("#9db0ff");
  });
});
