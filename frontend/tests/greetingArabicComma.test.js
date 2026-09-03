import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");

describe("[P146] Begruessung: arabisches Komma statt lateinischem Komma", () => {
  test("ar.json uses the Arabic comma for the greeting separator, not a Latin comma", () => {
    const ar = JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", "ar.json"), "utf8"));
    expect(ar["overview.greeting.separator"]).toBe("، ");
  });

  test("greetingHeadline renders the Arabic comma when the language is ar", () => {
    const { window } = loadApp();
    const ar = JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", "ar.json"), "utf8"));
    window.setLanguageBundle("ar", ar, ar);
    const headline = window.eval(`
      (function () {
        state.me = { forename: "Layla" };
        return greetingHeadline(new Date("2026-09-01T08:00:00"));
      })()
    `);
    expect(headline.textContent).toContain("، Layla");
    expect(headline.textContent).not.toContain(", Layla");
  });
});
