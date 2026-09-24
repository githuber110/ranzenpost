import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const i18nDir = path.join(dirname, "..", "i18n");
const LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];
const bundles = Object.fromEntries(
  LANGUAGES.map((language) => [language, JSON.parse(fs.readFileSync(path.join(i18nDir, `${language}.json`), "utf8"))])
);
const de = bundles.de;

const NOTIFY_KEYS = Object.keys(de).filter((key) => key.startsWith("settings.notify."));
const SETTINGS_KEYS = Object.keys(de).filter((key) => /^(settings|schools|language|help)\./.test(key));

describe("settings wording: one word per concept, no jargon", () => {
  test("the notification texts speak of devices only, never of targets or services", () => {
    for (const key of NOTIFY_KEYS) {
      expect(de[key], key).not.toMatch(/\bZiel|\bDienst/);
    }
    expect(de["settings.notify.service"]).toBe("Push aufs Handy");
    expect(de["settings.notify.summary.none"]).toBe("Kein Gerät");
  });

  test("the help entry carries the same name as its page in every language", () => {
    for (const language of LANGUAGES) {
      expect(bundles[language]["help.title"], language).toBe(bundles[language]["help.row"]);
    }
  });

  test("no settings text uses Endgerät, Post-Chips, Profil-Pills, 2FA-Token or a port number", () => {
    for (const key of SETTINGS_KEYS) {
      expect(de[key], key).not.toMatch(/Endgerät|Post-Chips|Profil-Pills|2FA-Token|Lehrer-Kürzel/);
    }
    for (const language of LANGUAGES) {
      expect(bundles[language]["schools.calendar.portOpen"], language).not.toContain("{port}");
      expect(bundles[language]["schools.calendar.portClosed"], language).not.toContain("{port}");
    }
  });
});
