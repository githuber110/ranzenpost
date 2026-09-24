import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function namesSheetBody(window, subjects) {
  return window.eval(`
    (function (subjects) {
      state.config = { connections: [{ id: "s1", subjects, teachers: {} }] };
      return namesPageView();
    })
  `)(subjects || {});
}

function label(window, key, vars) {
  return window.eval(`t(${JSON.stringify(key)}, ${JSON.stringify(vars || {})})`);
}

describe("a derived subject code is editable next to the name", () => {
  test("the code field shows the derived code and falls back to the key", () => {
    const { window } = loadApp();
    const sheet = namesSheetBody(window, {
      Mathematik: { label: "Mathematik", color: "", code: "MA", derived: true },
      D: { label: "Deutsch", color: "" },
    });
    const codeInputs = [...sheet.querySelectorAll(".subject-code-input")];
    expect(codeInputs.map((input) => input.value)).toEqual(["D", "MA"]);
  });

  test("editing the code marks it as user-owned so it is never derived again", () => {
    const { window } = loadApp();
    const sheet = namesSheetBody(window, {
      Mathematik: { label: "Mathematik", color: "", code: "MA", derived: true },
    });
    const input = sheet.querySelector(".subject-code-input");
    input.value = "MTH";
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    const draft = window.eval("state.pageForm.subjects.Mathematik");
    expect(draft.code).toBe("MTH");
    expect(draft.derived).toBeUndefined();
  });

  test("the code field has its own accessible label", () => {
    const { window } = loadApp();
    const sheet = namesSheetBody(window, { D: { label: "Deutsch", color: "" } });
    const input = sheet.querySelector(".subject-code-input");
    expect(input.getAttribute("aria-label")).toBe(label(window, "settings.subjects.code", { code: "D" }));
  });
});

describe("the name and the code field carry visible labels", () => {
  test("every subject row labels both fields on screen, every teacher row labels its name", () => {
    const { window } = loadApp();
    const sheet = window.eval(`
      (function () {
        state.config = { connections: [{ id: "s1", subjects: { D: { label: "Deutsch", color: "" } }, teachers: { BEH: { label: "" } } }] };
        return namesPageView();
      })
    `)();
    const subject = sheet.querySelector(".subject-fields");
    const name = subject.querySelector("label.subject-name");
    const code = subject.querySelector("label.subject-code");
    expect(name.querySelector(".lbl").textContent).toBe(label(window, "settings.names.name"));
    expect(name.querySelector("input").value).toBe("Deutsch");
    expect(code.querySelector(".lbl").textContent).toBe(label(window, "settings.names.code"));
    expect(code.querySelector("input.subject-code-input")).not.toBeNull();
    const teacher = sheet.querySelector("label.teacher-name");
    expect(teacher.querySelector(".lbl").textContent).toBe(label(window, "settings.names.person"));
    expect(teacher.querySelector("input")).not.toBeNull();
  });
});
