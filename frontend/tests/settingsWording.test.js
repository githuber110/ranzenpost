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
    expect(de["settings.notify.sheet"]).toBe("Mitteilungen");
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
  });
});

describe("the English area with letters and noticeboard is called Letters", () => {
  test("tab, page title and block targets use Letters and no English text calls the area Mail", () => {
    const en = bundles.en;
    expect(en["nav.post"]).toBe("Letters");
    expect(en["post.title"]).toBe("Letters");
    expect(en["blocks.letters.target"]).toBe(en["nav.post"]);
    expect(Object.values(en).filter((value) => value.includes("Letters › Letters"))).toEqual([]);
    expect(en["blocks.noticeboard.target"].startsWith(`${en["nav.post"]} › `)).toBe(true);
    expect(Object.entries(en).filter(([, value]) => /\bMail\b(?! merge)/.test(value))).toEqual([]);
  });
});
