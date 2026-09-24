import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");

function bundle(language) {
  return JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", `${language}.json`), "utf8"));
}

const EXPECTED = {
  de: { morning: "08:00", afternoon: "13:00" },
  en: { morning: "08:00 AM", afternoon: "01:00 PM" },
  ar: { morning: "08:00 ص", afternoon: "01:00 م" },
};

const LESSON = {
  day_of_week: 2,
  period: 1,
  subject_code: "D",
  subject_label: "Deutsch",
  room: "R1",
  start_time: "08:00",
  end_time: "08:45",
  change_kind: "",
};

function setLanguage(window, language) {
  if (language === "de") return;
  window.setLanguageBundle(language, bundle(language), bundle("de"));
}

describe("period time formatting follows Intl per language", () => {
  for (const language of ["de", "en", "ar"]) {
    test(`lessonTime formats the raw period start for ${language}`, () => {
      const { window } = loadApp();
      setLanguage(window, language);
      const result = window.eval(`(function (lesson, times) { return lessonTime(lesson, times); })`)(
        LESSON,
        { 1: "08:00" }
      );
      expect(result).toBe(EXPECTED[language].morning);
    });

    test(`clockOf formats a raw HH:MM table entry for ${language}`, () => {
      const { window } = loadApp();
      setLanguage(window, language);
      const morning = window.eval(`(function (raw) { return clockOf(raw); })`)("08:00");
      const afternoon = window.eval(`(function (raw) { return clockOf(raw); })`)("13:00");
      expect(morning).toBe(EXPECTED[language].morning);
      expect(afternoon).toBe(EXPECTED[language].afternoon);
    });

    test(`the week grid's period row shows the same formatted time for ${language}`, () => {
      const { window } = loadApp();
      setLanguage(window, language);
      window.eval(`
        state.config = { subjects: {}, teachers: {}, period_times: {} };
        state.childId = "c1";
        state.children = [{ key: "c1", name: "Mia" }];
      `);
      const grid = window.eval(`
        (function () {
          const data = { lessons: [], period_times: { 1: "08:00", 3: "13:00" } };
          return timetableGrid(data, "c1", { swipe: false });
        })()
      `);
      const spans = [...grid.querySelectorAll(".tt-hour:not(.own) span")].map((node) => node.textContent);
      expect(spans).toContain(EXPECTED[language].morning);
      expect(spans).toContain(EXPECTED[language].afternoon);
    });
  }

  test("a raw table entry that cannot be parsed stays empty instead of leaking through unformatted", () => {
    const { window } = loadApp();
    expect(window.eval(`(function (raw) { return clockOf(raw); })`)("")).toBe("");
    expect(window.eval(`(function (raw) { return clockOf(raw); })`)("not-a-time")).toBe("");
  });
});
