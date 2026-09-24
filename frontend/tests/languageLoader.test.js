import { describe, expect, test } from "vitest";
import { BASE_LANGUAGE, createI18n } from "../lib/i18n.js";
import {
  createLanguageLoader,
  normalizeLanguage,
  preferredLanguages,
  resolveLanguage,
} from "../lib/language.js";

function fakePage(labelled = []) {
  const attributes = {};
  return {
    attributes,
    documentElement: { setAttribute: (name, value) => { attributes[name] = String(value); } },
    querySelectorAll: (selector) => (selector === "[data-i18n]" ? labelled : []),
  };
}

function fakeLabel(key) {
  return { textContent: "", getAttribute: (name) => (name === "data-i18n" ? key : null) };
}

function bundles(table, requested = []) {
  return (path) => {
    requested.push(path);
    return Object.prototype.hasOwnProperty.call(table, path)
      ? Promise.resolve(table[path])
      : Promise.reject(new Error(`unexpected ${path}`));
  };
}

function setup({ table = {}, agent = { languages: ["de-DE"] }, labelled = [] } = {}) {
  const core = createI18n();
  const page = fakePage(labelled);
  const requested = [];
  const loader = createLanguageLoader(core, { getJson: bundles(table, requested), page, agent });
  return { core, page, requested, loader };
}

describe("language resolution runs without a browser", () => {
  test("no browser global is needed", () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");
  });

  test("a language tag is cut to a supported language or to nothing", () => {
    expect(normalizeLanguage("tr-TR")).toBe("tr");
    expect(normalizeLanguage("UK")).toBe("uk");
    expect(normalizeLanguage("kl")).toBe("");
    expect(normalizeLanguage(undefined)).toBe("");
  });

  test("the preferred languages come from the list and fall back to the single language", () => {
    expect(preferredLanguages({ languages: ["en-GB", "", "de"], language: "fr" })).toEqual(["en-GB", "de"]);
    expect(preferredLanguages({ languages: [], language: "ar-EG" })).toEqual(["ar-EG"]);
    expect(preferredLanguages({ language: undefined })).toEqual([]);
  });

  test("an explicit choice wins, system takes the first supported preference, else the base", () => {
    expect(resolveLanguage("tr", ["en"])).toBe("tr");
    expect(resolveLanguage("kl", ["en"])).toBe(BASE_LANGUAGE);
    expect(resolveLanguage("system", ["fr-FR", "uk-UA", "en"])).toBe("uk");
    expect(resolveLanguage("", ["en"])).toBe("en");
    expect(resolveLanguage("system", ["fr"])).toBe(BASE_LANGUAGE);
  });

  test("the loader resolves system from the agent it was given, read at call time", () => {
    const agent = { languages: ["en-US"] };
    const { loader } = setup({ agent });
    expect(loader.resolveLanguage("system")).toBe("en");
    agent.languages = ["ru"];
    expect(loader.resolveLanguage("system")).toBe("ru");
  });
});

describe("loading the bundles", () => {
  test("the base bundle is loaded once and marks the page", async () => {
    const label = fakeLabel("a");
    const { core, page, requested, loader } = setup({ table: { "i18n/de.json": { a: "Laden" } }, labelled: [label] });
    await loader.loadBaseLanguage();
    await loader.loadBaseLanguage();
    expect(requested).toEqual(["i18n/de.json"]);
    expect(core.t("a")).toBe("Laden");
    expect(page.attributes).toEqual({ lang: "de", dir: "ltr" });
    expect(label.textContent).toBe("Laden");
  });

  test("a failed or malformed base bundle still marks the page and shows the keys", async () => {
    const label = fakeLabel("a");
    const failing = setup({ labelled: [label] });
    await failing.loader.loadBaseLanguage();
    expect(failing.page.attributes).toEqual({ lang: "de", dir: "ltr" });
    expect(label.textContent).toBe("a");
    const malformed = setup({ table: { "i18n/de.json": ["a"] } });
    await malformed.loader.loadBaseLanguage();
    expect(malformed.core.t("a")).toBe("a");
  });

  test("a choice loads its bundle over the base and turns arabic right to left", async () => {
    const table = { "i18n/de.json": { a: "A-de", b: "B-de" }, "i18n/ar.json": { a: "A-ar" } };
    const { core, page, loader } = setup({ table });
    await loader.loadBaseLanguage();
    await loader.applyLanguageChoice("ar");
    expect(core.currentLanguageChoice()).toBe("ar");
    expect(core.currentLanguage()).toBe("ar");
    expect(core.t("a")).toBe("A-ar");
    expect(core.t("b")).toBe("B-de");
    expect(page.attributes).toEqual({ lang: "ar", dir: "rtl" });
  });

  test("a missing bundle or an unknown choice falls back to the base language", async () => {
    const table = { "i18n/de.json": { a: "A-de" } };
    const { core, page, requested, loader } = setup({ table });
    await loader.loadBaseLanguage();
    await loader.applyLanguageChoice("uk");
    expect(core.currentLanguageChoice()).toBe("uk");
    expect(core.currentLanguage()).toBe("de");
    expect(core.t("a")).toBe("A-de");
    expect(page.attributes.lang).toBe("de");
    await loader.applyLanguageChoice("kl");
    expect(core.currentLanguageChoice()).toBe("system");
    expect(requested).toEqual(["i18n/de.json", "i18n/uk.json"]);
  });

  test("a malformed bundle for another language falls back to the base language", async () => {
    const table = { "i18n/de.json": { a: "A-de" }, "i18n/ar.json": ["A-ar"] };
    const { core, page, loader } = setup({ table });
    await loader.loadBaseLanguage();
    await loader.applyLanguageChoice("ar");
    expect(core.currentLanguageChoice()).toBe("ar");
    expect(core.currentLanguage()).toBe("de");
    expect(core.t("a")).toBe("A-de");
    expect(page.attributes).toEqual({ lang: "de", dir: "ltr" });
  });

  test("marked labels are rewritten in the new language after a switch", async () => {
    const label = fakeLabel("a");
    const table = { "i18n/de.json": { a: "Laden" }, "i18n/tr.json": { a: "Yükleniyor" } };
    const { loader } = setup({ table, labelled: [label] });
    await loader.loadBaseLanguage();
    expect(label.textContent).toBe("Laden");
    await loader.applyLanguageChoice("tr");
    expect(label.textContent).toBe("Yükleniyor");
  });

  test("the system choice loads the bundle of the first supported browser language", async () => {
    const table = { "i18n/de.json": { a: "A-de" }, "i18n/uk.json": { a: "A-uk" } };
    const { core, page, requested, loader } = setup({ table, agent: { languages: ["fr-FR", "uk-UA", "en"] } });
    await loader.loadBaseLanguage();
    await loader.applyLanguageChoice("system");
    expect(core.currentLanguageChoice()).toBe("system");
    expect(core.currentLanguage()).toBe("uk");
    expect(core.t("a")).toBe("A-uk");
    expect(page.attributes.lang).toBe("uk");
    expect(requested).toEqual(["i18n/de.json", "i18n/uk.json"]);
  });
});
