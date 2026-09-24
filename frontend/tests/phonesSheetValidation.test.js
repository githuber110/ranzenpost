import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function openPhones(window, phones, onPost) {
  window.fetch = (url, options) => {
    if (String(url).includes("api/connections/s1") && options && options.method === "POST") {
      onPost(JSON.parse(options.body));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    return Promise.reject(new Error("network disabled in tests"));
  };
  window.eval(`
    state.config = { connections: [{ id: "s1", phones: ${JSON.stringify(phones)} }] };
    state.sheetForm = null;
    openSheet(phonesSheet);
  `);
  return window.document.querySelector(".sheet");
}

function type(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input"));
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("phones sheet drops empty rows and blocks half-filled ones", () => {
  test("a fully empty row is silently dropped on save, no error shown", async () => {
    const { window } = loadApp();
    const posted = [];
    const sheet = openPhones(window, [{ label: "Oma", number: "123" }], (body) => posted.push(body));
    sheet.querySelector(".phones-add").click();
    const current = window.document.querySelector(".sheet");
    current.querySelector(".phones-save").click();
    await settle();

    expect(current.querySelector(".err").textContent).toBe("");
    expect(posted).toEqual([{ phones: [{ label: "Oma", number: "123" }] }]);
  });

  test("a half-filled row shows an error and is not saved", async () => {
    const { window } = loadApp();
    const posted = [];
    openPhones(window, [], (body) => posted.push(body));
    window.document.querySelector(".phones-add").click();
    const sheet = window.document.querySelector(".sheet");
    type(window, sheet.querySelector(".phones-list input"), "Oma");
    sheet.querySelector(".phones-save").click();
    await settle();

    expect(sheet.querySelector(".err").textContent).toBe(
      "Bitte bei jeder Nummer sowohl Beschreibung als auch Nummer ausfüllen, oder beide Felder leer lassen."
    );
    expect(window.eval("state.sheet === phonesSheet")).toBe(true);
    expect(posted).toEqual([]);
  });
});

describe("the phones sheet only offers to save a change", () => {
  test("without numbers the empty state is plain text, not a boxed field", () => {
    const { window } = loadApp();
    const sheet = openPhones(window, [], () => {});
    const empty = sheet.querySelector(".phones-empty");
    expect(empty.tagName).toBe("P");
    expect(empty.textContent).toBe(window.eval('t("settings.phones.empty")'));
    expect(empty.closest(".field-group, .cell")).toBeNull();
    expect(sheet.querySelector(".phones-list .field-group")).toBeNull();
  });

  test("save stays disabled until a number is added, typed or removed, and again once undone", () => {
    const { window } = loadApp();
    const sheet = openPhones(window, [{ label: "Oma", number: "123" }], () => {});
    const save = sheet.querySelector(".phones-save");
    expect(save.disabled).toBe(true);
    const number = sheet.querySelector('.phones-list input[type="tel"]');
    type(window, number, "1234");
    expect(save.disabled).toBe(false);
    type(window, number, "123");
    expect(save.disabled).toBe(true);
    sheet.querySelector(".phones-list .btn.ghost").click();
    expect(save.disabled).toBe(false);
    expect(sheet.querySelector(".phones-empty")).not.toBeNull();
  });
});
