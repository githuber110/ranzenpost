import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";

function single(window, connection = {}, extra = "") {
  window.eval(`
    state.config = { connections: [Object.assign({ id: ${JSON.stringify(ONE)}, setup_complete: true, phones: [], subjects: {}, teachers: {} }, ${JSON.stringify(connection)})], notify_services: [], notify_events: {} };
    state.children = [{ key: ${JSON.stringify(`${ONE}:c1`)}, child_id: "c1", connection_id: ${JSON.stringify(ONE)}, name: "Mia Example", class_name: "7b" }];
    state.childId = ${JSON.stringify(`${ONE}:c1`)};
    ${extra}
  `);
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

describe("a subject's code sits behind Change code", () => {
  function names(window, subjects) {
    single(window, { subjects });
    window.eval("openNamesPage();");
    return window.document.querySelector(".names-page");
  }

  test("the field is hidden until the link is pressed, then it shows and takes the focus", () => {
    const { window } = loadApp();
    const sheet = names(window, { D: { label: "Deutsch", color: "" } });
    const field = sheet.querySelector("label.subject-code");
    const toggle = sheet.querySelector(".subject-code-toggle");
    expect(field.hidden).toBe(true);
    expect(toggle.hidden).toBe(false);
    expect(toggle.textContent).toBe(label(window, "settings.names.codeChange"));
    expect(toggle.getAttribute("aria-label")).toBe(label(window, "settings.names.codeChangeFor", { code: "D" }));
    toggle.click();
    expect(field.hidden).toBe(false);
    expect(toggle.hidden).toBe(true);
    expect(window.document.activeElement).toBe(field.querySelector("input.subject-code-input"));
    expect(sheet.querySelector(".subject-fields").classList.contains("code-open")).toBe(true);
  });

  test("an own code shows the field open, a derived one does not", () => {
    const { window } = loadApp();
    const sheet = names(window, {
      D: { label: "Deutsch", color: "", code: "DE" },
      Mathematik: { label: "Mathematik", color: "", code: "MA", derived: true },
    });
    const fields = [...sheet.querySelectorAll("label.subject-code")];
    expect(fields.map((field) => field.hidden)).toEqual([false, true]);
  });
});

describe("the own colour waits behind a disclosure", () => {
  function dialog(window, color) {
    single(window, { subjects: { D: { label: "Deutsch", color } } });
    window.eval("openNamesPage();");
    window.document.querySelector(".swatch-trigger").click();
    return window.document.querySelector(".color-dialog");
  }

  test("swatches and automatic come first, hex and picker only after the toggle", () => {
    const { window } = loadApp();
    const node = dialog(window, "blue");
    const body = node.querySelector(".sheet-body");
    expect([...body.children].map((child) => child.className)).toEqual(["swatch-grid", "link-btn colour-own-toggle", "colour-own"]);
    expect(node.querySelector(".swatch-grid .swatch-btn.auto")).not.toBeNull();
    const toggle = node.querySelector(".colour-own-toggle");
    const own = node.querySelector(".colour-own");
    expect(toggle.textContent).toBe(label(window, "settings.color.own"));
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(own.hidden).toBe(true);
    toggle.click();
    expect(own.hidden).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(own.querySelector(".colour-hex")).not.toBeNull();
    expect(own.querySelector(".colour-picker")).not.toBeNull();
    toggle.click();
    expect(own.hidden).toBe(true);
  });

  test("a subject with an own colour opens the dialog with the fields shown", () => {
    const { window } = loadApp();
    const node = dialog(window, "#abcdef");
    expect(node.querySelector(".colour-own").hidden).toBe(false);
    expect(node.querySelector(".colour-own-toggle").getAttribute("aria-expanded")).toBe("true");
  });
});
