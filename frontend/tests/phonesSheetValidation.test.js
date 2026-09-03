import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P125] phones sheet drops empty rows and blocks half-filled ones", () => {
  test("a fully empty row is silently dropped on save, no error shown", () => {
    const { window } = loadApp();
    window.fetch = (url, options) => {
      if (String(url).includes("api/config") && options && options.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ phones: [{ label: "Oma", number: "123" }] }),
        });
      }
      return Promise.reject(new Error("network disabled in tests"));
    };
    const result = window.eval(`
      (function () {
        state.config = { phones: [{ label: "Oma", number: "123" }, { label: "", number: "" }] };
        state.sheetForm = null;
        const view = phonesSheet();
        document.body.appendChild(view);
        const save = [...view.querySelectorAll(".sheet-foot button")].find((b) => b.textContent.includes("Sichern"));
        save.click();
        return new Promise((resolve) => setTimeout(() => resolve({
          errText: view.querySelector(".err") ? view.querySelector(".err").textContent : "",
          phones: state.config.phones,
        }), 0));
      })()
    `);
    return result.then((r) => {
      expect(r.errText).toBe("");
      expect(r.phones).toEqual([{ label: "Oma", number: "123" }]);
    });
  });

  test("a half-filled row shows an error and is not saved", () => {
    const { window } = loadApp();
    let fetchCalled = false;
    window.fetch = (url, options) => {
      if (String(url).includes("api/config") && options && options.method === "POST") {
        fetchCalled = true;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      return Promise.reject(new Error("network disabled in tests"));
    };
    const result = window.eval(`
      (function () {
        state.config = { phones: [{ label: "Oma", number: "" }] };
        state.sheetForm = null;
        const view = phonesSheet();
        document.body.appendChild(view);
        const save = [...view.querySelectorAll(".sheet-foot button")].find((b) => b.textContent.includes("Sichern"));
        save.click();
        return new Promise((resolve) => setTimeout(() => resolve({
          errText: view.querySelector(".err").textContent,
          sheetStillInDom: document.body.contains(view),
        }), 0));
      })()
    `);
    return result.then((r) => {
      expect(r.errText).toBe(
        "Bitte bei jeder Nummer sowohl Beschreibung als auch Nummer ausfüllen, oder beide Felder leer lassen."
      );
      expect(r.sheetStillInDom).toBe(true);
      expect(fetchCalled).toBe(false);
    });
  });
});
