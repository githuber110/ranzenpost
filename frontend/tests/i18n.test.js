import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const i18nDir = path.join(dirname, "..", "i18n");
const LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];
const bundles = Object.fromEntries(
  LANGUAGES.map((language) => [language, JSON.parse(fs.readFileSync(path.join(i18nDir, `${language}.json`), "utf8"))])
);
const base = bundles.de;

function bundleFetch(language) {
  return (url) =>
    String(url).includes(`i18n/${language}.json`)
      ? jsonResponse(bundles[language])
      : Promise.reject(new Error(`unexpected fetch ${url}`));
}

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

describe("[P134] t() lookup layer", () => {
  test("resolves a key from the active bundle", () => {
    const { window } = loadApp();
    expect(window.t("absence.title")).toBe("Abwesenheit");
  });

  test("renders the key itself when it is missing, so gaps are visible", () => {
    const { window } = loadApp();
    expect(window.t("does.not.exist")).toBe("does.not.exist");
  });

  test("substitutes named placeholders and leaves unknown ones untouched", () => {
    const { window } = loadApp();
    expect(window.t("timetable.room", { room: "B12" })).toBe("Raum B12");
    expect(window.t("timetable.room")).toBe("Raum {room}");
  });

  test("falls back to the base bundle when the active language misses a key", () => {
    const { window } = loadApp();
    window.setLanguageBundle("en", { "absence.title": "Absence" }, base);
    expect(window.t("absence.title")).toBe("Absence");
    expect(window.t("letters.title")).toBe(base["letters.title"]);
  });
});

describe("[P134] plural selection", () => {
  test("picks the singular and plural forms through Intl.PluralRules", () => {
    const { window } = loadApp();
    expect(window.tCount("letters.count", 1)).toBe("1 Brief");
    expect(window.tCount("letters.count", 4)).toBe("4 Briefe");
  });

  test("falls back to the 'other' form when a language lacks a category", () => {
    const { window } = loadApp();
    window.setLanguageBundle("de", { "x.other": "{count} Stück" }, base);
    expect(window.tCount("x", 1)).toBe("1 Stück");
  });
});

describe("[P134] language resolution", () => {
  test("system follows navigator.language and falls back to the base language", () => {
    const { window } = loadApp();
    expect(window.resolveLanguage("system")).toBe("de");
    expect(window.resolveLanguage("tr")).toBe("tr");
    expect(window.resolveLanguage("kl")).toBe("de");
  });

  test("an explicit choice loads that bundle and marks the document", async () => {
    const { window, document } = loadApp();
    window.fetch = (url) =>
      String(url).includes("i18n/tr.json")
        ? jsonResponse({ "absence.title": "Devamsızlık" })
        : Promise.reject(new Error("unexpected fetch " + url));
    await window.applyLanguageChoice("tr");
    expect(window.t("absence.title")).toBe("Devamsızlık");
    expect(document.documentElement.getAttribute("lang")).toBe("tr");
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
  });

  test("arabic switches the document to right-to-left", async () => {
    const { window, document } = loadApp();
    window.fetch = () => jsonResponse({ "absence.title": "الغياب" });
    await window.applyLanguageChoice("ar");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
  });

  test("a missing bundle falls back to german instead of showing keys", async () => {
    const { window, document } = loadApp();
    window.fetch = () => Promise.reject(new Error("no such bundle"));
    await window.applyLanguageChoice("uk");
    expect(window.t("absence.title")).toBe("Abwesenheit");
    expect(document.documentElement.getAttribute("lang")).toBe("de");
  });

  test("the offered choices are system plus the six supported languages", () => {
    const { window } = loadApp();
    expect(window.languageChoices()).toEqual(["system", "de", "en", "ar", "tr", "ru", "uk"]);
  });
});

describe("[P134] formats follow the active language", () => {
  test("dates render in the active locale", () => {
    const { window } = loadApp();
    expect(window.showDate("2026-09-07")).toBe("07.09.2026");
    window.setLanguageBundle("en", base, base);
    expect(window.showDate("2026-09-07")).toBe("09/07/2026");
  });

  test("numbers render in the active locale", () => {
    const { window } = loadApp();
    expect(window.formatNumber(1234)).toBe("1.234");
    window.setLanguageBundle("en", base, base);
    expect(window.formatNumber(1234)).toBe("1,234");
  });
});

describe("[P134] backend messages arrive as keys", () => {
  test("message_key wins over the transitional german message", () => {
    const { window } = loadApp();
    const result = { ok: false, message_key: "api.notConfigured", message: "irgendwas" };
    expect(window.apiMessage(result)).toBe(base["api.notConfigured"]);
  });

  test("a raw message from IServ still shows when no key is given", () => {
    const { window } = loadApp();
    expect(window.apiMessage({ message: "IServ sagt nein" }, "absence.submit.failed")).toBe("IServ sagt nein");
  });

  test("the fallback key is used when the response carries nothing", () => {
    const { window } = loadApp();
    expect(window.apiMessage({}, "absence.submit.failed")).toBe(base["absence.submit.failed"]);
  });
});

describe("[P134] language choice is reachable from settings", () => {
  test("the display section opens a language sheet with every choice", () => {
    const { window } = loadApp();
    const view = window.eval("(function () { state.config = {}; return settingsView(); })()");
    const rows = [...view.querySelectorAll(".setting-row .lbl")].map((node) => node.textContent);
    expect(rows).toContain("Sprache");
    const sheetNode = window.eval("languageSheet()");
    expect(sheetNode.querySelectorAll(".opt-list .opt").length).toBe(7);
  });
});

describe("[P134] switching the language re-renders the visible text", () => {
  const settingLabels = (window) =>
    [...window.eval("(function () { state.config = {}; return settingsView(); })()").querySelectorAll(".setting-row .lbl")]
      .map((node) => node.textContent);

  test("rendered settings labels follow the active language and switch back", async () => {
    const { window } = loadApp();
    expect(settingLabels(window)).toContain(base["settings.language"]);
    window.fetch = bundleFetch("en");
    await window.applyLanguageChoice("en");
    const english = settingLabels(window);
    expect(english).toContain(bundles.en["settings.language"]);
    expect(english).not.toContain(base["settings.language"]);
    await window.applyLanguageChoice("de");
    expect(settingLabels(window)).toContain(base["settings.language"]);
  });

  test("the tab bar labels are rewritten too, not only the sheet", async () => {
    const { window } = loadApp();
    const tabLabels = () => [...window.eval("tabbar()").querySelectorAll(".tab span")].map((node) => node.textContent);
    expect(tabLabels()).toContain(base["nav.overview"]);
    window.fetch = bundleFetch("ru");
    await window.applyLanguageChoice("ru");
    expect(tabLabels()).toContain(bundles.ru["nav.overview"]);
  });

  test("pre-boot markup marked with data-i18n is rewritten on every switch", async () => {
    const { window, document } = loadApp();
    const node = document.createElement("p");
    node.setAttribute("data-i18n", "common.loading");
    document.body.appendChild(node);
    window.fetch = bundleFetch("tr");
    await window.applyLanguageChoice("tr");
    expect(node.textContent).toBe(bundles.tr["common.loading"]);
    window.fetch = bundleFetch("uk");
    await window.applyLanguageChoice("uk");
    expect(node.textContent).toBe(bundles.uk["common.loading"]);
  });
});

describe("[P134] every shipped language is reachable and complete", () => {
  test("each bundle loads and answers with its own words, not with keys", async () => {
    for (const language of LANGUAGES) {
      const { window } = loadApp();
      window.fetch = bundleFetch(language);
      await window.applyLanguageChoice(language);
      expect(window.t("nav.overview")).toBe(bundles[language]["nav.overview"]);
      expect(window.t("nav.overview")).not.toBe("nav.overview");
    }
  });

  test("the language sheet offers every language under its own native name", () => {
    const { window } = loadApp();
    const sheetNode = window.eval("languageSheet()");
    const names = [...sheetNode.querySelectorAll(".opt b")].map((node) => node.textContent);
    expect(names).toEqual([
      base["language.system"],
      "Deutsch",
      "English",
      "العربية",
      "Türkçe",
      "Русский",
      "Українська",
    ]);
  });

  test("every bundle spells the native names identically, whatever the ui language is", () => {
    for (const language of LANGUAGES) {
      expect(LANGUAGES.map((tag) => bundles[language][`language.${tag}`])).toEqual([
        "Deutsch",
        "English",
        "العربية",
        "Türkçe",
        "Русский",
        "Українська",
      ]);
    }
  });

  test("the first wizard step offers the same choices as the settings sheet", async () => {
    const { window, document } = loadApp();
    window.fetch = (url) =>
      String(url).includes("api/wizard")
        ? jsonResponse({ step: "url", has_2fa: false })
        : jsonResponse({});
    const app = document.getElementById("app");
    window.renderWizard(app, () => {});
    for (let tick = 0; tick < 8; tick += 1) await new Promise((resolve) => setImmediate(resolve));
    const select = app.querySelector(".wz-language");
    expect(select).toBeTruthy();
    expect([...select.querySelectorAll("option")].map((node) => node.value)).toEqual(window.languageChoices());
    expect([...select.querySelectorAll("option")].map((node) => node.textContent)).toEqual([
      base["language.system"],
      "Deutsch",
      "English",
      "العربية",
      "Türkçe",
      "Русский",
      "Українська",
    ]);
  });
});

describe("[P134] right-to-left is switched on for arabic and off again for everyone else", () => {
  test("arabic sets rtl and any following choice resets it", async () => {
    const { window, document } = loadApp();
    window.fetch = bundleFetch("ar");
    await window.applyLanguageChoice("ar");
    expect(document.documentElement.getAttribute("dir")).toBe("rtl");
    expect(document.documentElement.getAttribute("lang")).toBe("ar");
    window.fetch = bundleFetch("uk");
    await window.applyLanguageChoice("uk");
    expect(document.documentElement.getAttribute("dir")).toBe("ltr");
    expect(document.documentElement.getAttribute("lang")).toBe("uk");
  });

  test("direction-sensitive icons carry a class the stylesheet can mirror", () => {
    const { window } = loadApp();
    const bar = window.eval("weekBar()");
    expect(bar.querySelector(".chev-prev")).toBeTruthy();
    expect(bar.querySelector(".chev-next")).toBeTruthy();
    expect(window.eval("backButton(function () {})").className).toContain("nav-back");
  });

  test("content that comes from iserv keeps its own direction", () => {
    const css = fs.readFileSync(path.join(dirname, "..", "app.js"), "utf8");
    const bodyBlocks = css.match(/class: "body-html"[^)]*/g) || [];
    expect(bodyBlocks.length).toBeGreaterThan(0);
    for (const block of bodyBlocks) expect(block).toContain('dir: "auto"');
  });
});
