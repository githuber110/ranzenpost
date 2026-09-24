import { describe, expect, test } from "vitest";
import {
  BASE_LANGUAGE,
  LANGUAGE_CHOICES,
  LANGUAGES,
  RTL_LANGUAGES,
  createI18n,
  formatTemplate,
} from "../lib/i18n.js";
import { i18nGlobals } from "../lib/i18nGlobals.js";

const GLOBAL_NAMES = [
  "BASE_LANGUAGE",
  "LANGUAGES",
  "LANGUAGE_CHOICES",
  "RTL_LANGUAGES",
  "formatTemplate",
  "createLanguageLoader",
  "t",
  "hasMessage",
  "pluralCategory",
  "tCount",
  "setLanguageBundle",
  "languageChoices",
  "currentLanguageChoice",
  "currentLanguage",
  "formatNumber",
  "dateFormatter",
  "relativeFormatter",
];

describe("the translation core runs without a browser", () => {
  test("no browser global is needed to load or use it", () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");
    const core = createI18n();
    core.setLanguageBundle("en", { "a.b": "Hello {name}" }, { "a.b": "Hallo {name}" });
    expect(core.t("a.b", { name: "Ada" })).toBe("Hello Ada");
  });

  test("the language lists stay the six supported languages and cannot be changed", () => {
    expect(BASE_LANGUAGE).toBe("de");
    expect(LANGUAGES).toEqual(["de", "en", "ar", "tr", "ru", "uk"]);
    expect(LANGUAGE_CHOICES).toEqual(["system", "de", "en", "ar", "tr", "ru", "uk"]);
    expect(RTL_LANGUAGES).toEqual(["ar"]);
    expect(Object.isFrozen(LANGUAGES)).toBe(true);
    expect(Object.isFrozen(LANGUAGE_CHOICES)).toBe(true);
    expect(Object.isFrozen(RTL_LANGUAGES)).toBe(true);
  });

  test("a fresh core starts on the base language with no messages", () => {
    const { i18n } = createI18n();
    expect(i18n).toEqual({ choice: "system", language: "de", messages: {}, base: {} });
  });
});

describe("messages and placeholders", () => {
  test("placeholders are filled and unknown ones stay visible", () => {
    expect(formatTemplate("{a} and {b}", { a: 1 })).toBe("1 and {b}");
    expect(formatTemplate("{a}", undefined)).toBe("{a}");
    expect(formatTemplate("{a} {a}", { a: "x" })).toBe("x x");
    expect(formatTemplate("{toString}", {})).toBe("{toString}");
  });

  test("a missing message falls back to the base bundle and then to the key", () => {
    const core = createI18n();
    core.setLanguageBundle("en", { only: "english" }, { only: "deutsch", base: "nur deutsch" });
    expect(core.t("only")).toBe("english");
    expect(core.t("base")).toBe("nur deutsch");
    expect(core.t("missing.key")).toBe("missing.key");
    expect(core.hasMessage("base")).toBe(true);
    expect(core.hasMessage("missing.key")).toBe(false);
  });

  test("a bundle without its own base keeps the earlier base, and no messages means the base", () => {
    const core = createI18n();
    core.setLanguageBundle("de", null, { a: "A" });
    expect(core.i18n.messages).toBe(core.i18n.base);
    core.setLanguageBundle("en", { b: "B" });
    expect(core.i18n.language).toBe("en");
    expect(core.t("a")).toBe("A");
    expect(core.t("b")).toBe("B");
  });

  test("two cores do not share their state", () => {
    const first = createI18n();
    const second = createI18n();
    first.setLanguageBundle("en", { a: "first" }, { a: "first" });
    expect(second.t("a")).toBe("a");
    expect(second.i18n.language).toBe("de");
  });
});

describe("plural forms and numbers follow the current language", () => {
  test("the plural category comes from Intl and falls back for a broken language tag", () => {
    const core = createI18n();
    core.setLanguageBundle("ar", {}, {});
    expect(core.pluralCategory(3)).toBe("few");
    core.setLanguageBundle("not a language", {}, {});
    expect(core.pluralCategory(1)).toBe("one");
    expect(core.pluralCategory(2)).toBe("other");
  });

  test("a counted message picks its form, formats the count and falls back to other", () => {
    const core = createI18n();
    core.setLanguageBundle("de", { "x.one": "{count} Brief", "x.other": "{count} Briefe", "y.other": "{count} {what}" }, {});
    expect(core.tCount("x", 1)).toBe("1 Brief");
    expect(core.tCount("x", 1200)).toBe("1.200 Briefe");
    expect(core.tCount("y", 1, { what: "z" })).toBe("1 z");
  });

  test("numbers and dates use the current language and survive a broken tag", () => {
    const core = createI18n();
    core.setLanguageBundle("en", {}, {});
    expect(core.formatNumber(1200)).toBe("1,200");
    expect(core.dateFormatter({ month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 0, 5)))).toBe("January");
    core.setLanguageBundle("not a language", {}, {});
    expect(core.formatNumber(1200)).toBe("1200");
    expect(core.dateFormatter({ month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 0, 5)))).toBe("Januar");
  });

  test("relative times use the current language and survive a broken tag", () => {
    const core = createI18n();
    core.setLanguageBundle("en", {}, {});
    expect(core.relativeFormatter().format(-1, "day")).toBe("yesterday");
    core.setLanguageBundle("not a language", {}, {});
    expect(core.relativeFormatter().format(-1, "day")).toBe("gestern");
  });

  test("the language choices are a copy and the current choice is read from the state", () => {
    const core = createI18n();
    const choices = core.languageChoices();
    choices.push("xx");
    expect(core.languageChoices()).toEqual(LANGUAGE_CHOICES);
    core.i18n.choice = "tr";
    expect(core.currentLanguageChoice()).toBe("tr");
  });

  test("a choice outside the offered list is stored as system and the stored choice comes back", () => {
    const core = createI18n();
    expect(core.setLanguageChoice("uk")).toBe("uk");
    expect(core.currentLanguageChoice()).toBe("uk");
    expect(core.setLanguageChoice("kl")).toBe("system");
    expect(core.currentLanguageChoice()).toBe("system");
    expect(core.setLanguageChoice(undefined)).toBe("system");
    expect(core.i18n.language).toBe("de");
  });

  test("the current language is the language of the last bundle, not the choice", () => {
    const core = createI18n();
    expect(core.currentLanguage()).toBe("de");
    core.setLanguageChoice("tr");
    expect(core.currentLanguage()).toBe("de");
    core.setLanguageBundle("tr", {}, {});
    expect(core.currentLanguage()).toBe("tr");
  });
});

describe("the globals handed to the classic scripts", () => {
  test("carry exactly the names app.js binds, frozen", () => {
    const globals = i18nGlobals();
    expect(Object.keys(globals).sort()).toEqual([...GLOBAL_NAMES].sort());
    expect(Object.isFrozen(globals)).toBe(true);
  });

  test("bind the functions to the state they expose", () => {
    const globals = i18nGlobals();
    globals.setLanguageBundle("en", { a: "A" }, {});
    expect(globals.currentLanguage()).toBe("en");
    expect(globals.t("a")).toBe("A");
    expect(i18nGlobals().t("a")).toBe("a");
  });

  test("hand over no raw state and no way to change the choice without loading its bundle", () => {
    const globals = i18nGlobals(createI18n());
    expect(Object.prototype.hasOwnProperty.call(globals, "i18n")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(globals, "setLanguageChoice")).toBe(false);
  });

  test("the language loader they create works on the same core", async () => {
    const core = createI18n();
    const globals = i18nGlobals(core);
    const attributes = {};
    const loader = globals.createLanguageLoader({
      getJson: () => Promise.resolve({ a: "Merhaba" }),
      page: { documentElement: { setAttribute: (name, value) => { attributes[name] = value; } }, querySelectorAll: () => [] },
      agent: { languages: [] },
    });
    await loader.applyLanguageChoice("tr");
    expect(core.i18n.choice).toBe("tr");
    expect(globals.t("a")).toBe("Merhaba");
    expect(attributes.lang).toBe("tr");
  });
});
