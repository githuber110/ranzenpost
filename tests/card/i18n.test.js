import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];
const PLACEHOLDER = /\{[a-z]+\}/g;

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("languages", () => {
  it("speaks German by default and Arabic from right to left", async () => {
    const german = await mountCard({ view: "today", child: "alex" }, makeHass({ language: "de" }));
    expect(texts(german.shadowRoot, ".row-when, .tag")).toEqual(["Jetzt", "Nächste", "Vertretung", "Entfällt"]);
    expect(german.shadowRoot.querySelector("ha-card").getAttribute("lang")).toBe("de");

    document.documentElement.dir = "rtl";
    const arabic = await mountCard({ view: "today", child: "alex" }, makeHass({ language: "ar" }), "rtl");
    const root = arabic.shadowRoot;
    expect(root.querySelector("ha-card").getAttribute("dir")).toBe("rtl");
    expect(root.querySelector("ha-card").getAttribute("lang")).toBe("ar");
    expect(texts(root, ".row-when, .tag")).toEqual(["الآن", "التالية", "حصة بديلة", "ملغاة"]);
    expect(root.querySelector(".row-note .dlg-text").textContent).toContain("تنتهي الحصة الأخيرة");
    expect(root.querySelector(".panel-head .panel-meta").textContent).toContain("الأربعاء");
    expect([...root.querySelectorAll(".row-title")].every((node) => node.getAttribute("dir") === "auto")).toBe(true);
    const style = root.querySelector("style").textContent;
    expect(style).toContain('ha-card[lang="ar"] * { letter-spacing: normal; text-transform: none; }');
    expect(style).not.toMatch(/(margin|padding|border|inset)-(left|right)/);
    expect(style).not.toMatch(/text-align: (left|right)/);
    expect(style).not.toMatch(/(?<![a-z-])(left|right): /);
  });

  it("keeps the arabic week grid readable from the end side", async () => {
    document.documentElement.dir = "rtl";
    const card = await mountCard({ view: "week", child: "alex" }, makeHass({ language: "ar" }), "rtl");
    const root = card.shadowRoot;
    expect(root.querySelector("ha-card").getAttribute("dir")).toBe("rtl");
    expect(root.querySelector(".tt-cell.out .room").textContent).toBe("ملغاة");
    expect(texts(root, ".legend > span")).toEqual(["حصة بديلة", "×ملغاة"]);
    expect(root.querySelector(".stamp").textContent).toContain("آخر تحديث");
  });

  it("falls back to English for a language it does not carry and reads regional tags", async () => {
    const unknown = await mountCard({ view: "today", child: "kim" }, makeHass({ language: "xx" }));
    expect(unknown.shadowRoot.querySelector(".row-note .dlg-text").textContent).toBe("No school today.");

    const regional = await mountCard({ view: "today", child: "kim" }, makeHass({ language: "tr-TR" }));
    expect(regional.shadowRoot.querySelector(".row-note .dlg-text").textContent).toBe("Bugün okul yok.");
  });

  it("carries every key with the same placeholders in every language", () => {
    const dictionary = CardClass.texts;
    expect(Object.keys(dictionary).sort()).toEqual([...LANGUAGES].sort());
    const base = dictionary.de;
    for (const language of LANGUAGES) {
      expect(Object.keys(dictionary[language]).sort(), language).toEqual(Object.keys(base).sort());
      for (const [key, value] of Object.entries(dictionary[language])) {
        expect(value.trim(), `${language}.${key}`).not.toBe("");
        const expected = [...base[key].matchAll(PLACEHOLDER)].map((match) => match[0]).sort();
        const found = [...value.matchAll(PLACEHOLDER)].map((match) => match[0]).sort();
        expect(found, `${language}.${key}`).toEqual(expected);
      }
    }
  });

  it("keeps every user visible string in the dictionary", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(join(here, "..", "..", "custom_components", "ranzenpost", "frontend", "ranzenpost-card.js"), "utf8");
    const markup = source.slice(source.indexOf("function subjectDot("));
    const plain = "[^<>${}`\\n]*";
    const words = markup.match(new RegExp(`>${plain}[A-Za-z\\u00c0-\\u017f]{3,}${plain}<`, "g")) || [];
    expect(words).toEqual([]);
  });
});
