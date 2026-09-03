import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function settingsView(window, config) {
  return window.eval(`
    (function (config) {
      state.config = config;
      return settingsView();
    })
  `)(config || {});
}

function label(window, key) {
  return window.eval(`t(${JSON.stringify(key)})`);
}

const CONFIG = {
  subjects: { MA: { label: "Mathe", color: "" }, D: { label: "Deutsch", color: "" } },
  teachers: { BEH: { label: "Fr. Behrend" } },
  phones: [{ label: "Sekretariat", number: "0511" }],
  period_times: { 1: "07:00" },
};

describe("[P181] the top level of the settings is grouped, not longer", () => {
  test("four named groups in a fixed order", () => {
    const { window } = loadApp();
    const view = settingsView(window, CONFIG);
    const heads = [...view.querySelectorAll(".settings-group .section-head .overline")].map((n) => n.textContent);
    expect(heads).toEqual([
      label(window, "settings.section.school"),
      label(window, "settings.section.display"),
      label(window, "settings.section.notifications"),
      label(window, "settings.section.account"),
    ]);
  });

  test("every group holds exactly the rows it promises", () => {
    const { window } = loadApp();
    const groups = [...settingsView(window, CONFIG).querySelectorAll(".settings-group")].map((group) =>
      [...group.querySelectorAll(".setting-row .lbl")].map((node) => node.textContent)
    );
    expect(groups).toEqual([
      [
        label(window, "holidays.settings.title"),
        label(window, "settings.phones"),
        label(window, "settings.names"),
        label(window, "settings.periods.sheet"),
      ],
      [label(window, "settings.language"), label(window, "settings.theme")],
      [label(window, "settings.notify.service")],
      [label(window, "settings.profile"), label(window, "settings.password"), label(window, "settings.disconnect")],
    ]);
  });

  test("nothing was lost: every setting that existed before is still one tap away", () => {
    const { window } = loadApp();
    const view = settingsView(window, CONFIG);
    const rows = [...view.querySelectorAll(".setting-row .lbl")].map((node) => node.textContent);
    expect(rows.length).toBe(10);
    for (const key of [
      "settings.language",
      "settings.theme",
      "settings.periods.sheet",
      "holidays.settings.title",
      "settings.phones",
      "settings.notify.service",
      "settings.profile",
      "settings.password",
      "settings.disconnect",
    ]) {
      expect(rows).toContain(label(window, key));
    }
    expect(rows).toContain(label(window, "settings.names"));
  });
});

describe("[P181] subjects and teachers share one sheet", () => {
  test("both lists are in the sheet, each under its own heading with its count", () => {
    const { window } = loadApp();
    const node = window.eval(`
      (function (config) {
        state.config = config;
        state.sheetForm = null;
        return namesSheet();
      })
    `)(CONFIG);

    expect(node.querySelector(".sheet-title").textContent).toBe(label(window, "settings.names.sheet"));
    const blocks = [...node.querySelectorAll(".names-block")];
    expect(blocks.length).toBe(2);
    expect(blocks[0].querySelector(".overline").textContent).toBe(label(window, "settings.subjects"));
    expect(blocks[1].querySelector(".overline").textContent).toBe(label(window, "settings.teachers"));
    expect(blocks[0].querySelector(".names-count").textContent).toBe(
      window.eval(`t("settings.subjects.count", { count: formatNumber(2) })`)
    );
    expect(blocks[1].querySelector(".names-count").textContent).toBe(
      window.eval(`t("settings.teachers.count", { count: formatNumber(1) })`)
    );
    expect(blocks[0].querySelectorAll(".swatch-trigger").length).toBe(2);
    expect(blocks[1].querySelectorAll(".swatch-trigger").length).toBe(0);
  });

  test("one save writes both drafts back", () => {
    const { window, document } = loadApp();
    window.eval(`
      (function (config) {
        state.config = config;
        state.sheetForm = null;
        openSheet(namesSheet);
      })
    `)(JSON.parse(JSON.stringify(CONFIG)));

    const inputs = document.querySelectorAll(".sheet-body .names-block .inp");
    inputs[0].value = "Deutsch LK";
    inputs[0].dispatchEvent(new window.Event("input"));
    const teacherInput = document.querySelectorAll(".sheet-body .names-block")[1].querySelector(".inp");
    teacherInput.value = "Frau Behrend";
    teacherInput.dispatchEvent(new window.Event("input"));

    expect(window.eval("state.sheetForm.subjects.D.label")).toBe("Deutsch LK");
    expect(window.eval("state.sheetForm.teachers.BEH.label")).toBe("Frau Behrend");
  });

  test("an empty side says so instead of showing an empty group", () => {
    const { window } = loadApp();
    const node = window.eval(`
      (function () {
        state.config = { subjects: {}, teachers: {} };
        state.sheetForm = null;
        return namesSheet();
      })()
    `);
    const blocks = [...node.querySelectorAll(".names-block")];
    expect(blocks[0].textContent).toContain(label(window, "settings.subjects.empty"));
    expect(blocks[1].textContent).toContain(label(window, "settings.teachers.empty"));
    expect(node.querySelector(".field-group")).toBeNull();
  });
});
