import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

const TODAY = { blocks: ["today"], children: ["alex"] };

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
  document.documentElement.removeAttribute("lang");
});

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

function hassWith(locale) {
  const hass = makeHass();
  hass.language = locale.language;
  hass.locale = { number_format: "language", time_format: "language", date_format: "language", ...locale };
  return hass;
}

describe("numbers follow the number format of Home Assistant", () => {
  it("writes the digits of the language when Home Assistant follows the language", async () => {
    const card = await mountCard(TODAY, hassWith({ language: "ar" }));
    const expected = new Intl.NumberFormat("ar").format(2);

    expect(block(card.shadowRoot, "today").querySelector(".panel-head .count").textContent).toBe(expected);
  });

  it("writes western digits when Home Assistant asks for a comma as decimal sign", async () => {
    const card = await mountCard(TODAY, hassWith({ language: "ar", number_format: "comma_decimal" }));

    expect(block(card.shadowRoot, "today").querySelector(".panel-head .count").textContent).toBe("2");
  });

  it("writes western digits without grouping when Home Assistant formats no numbers", async () => {
    const card = await mountCard(TODAY, hassWith({ language: "ar", number_format: "none" }));

    expect(block(card.shadowRoot, "today").querySelector(".panel-head .count").textContent).toBe("2");
  });
});

describe("day keys and rejected locale tags", () => {
  it("finds the lessons of the day even when the en-CA layout of the browser changes", async () => {
    const Original = Intl.DateTimeFormat;
    class Shuffled extends Original {
      constructor(locale, options) {
        super(locale, options);
        this.shuffled = locale === "en-CA";
      }

      format(date) {
        const text = super.format(date);
        return this.shuffled ? text.split("-").reverse().join("/") : text;
      }
    }
    Intl.DateTimeFormat = Shuffled;
    try {
      const card = await mountCard(TODAY, makeHass());
      expect(texts(block(card.shadowRoot, "today"), ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
    } finally {
      Intl.DateTimeFormat = Original;
    }
  });

  it("keeps the language when the browser rejects the full locale tag", async () => {
    const card = await mountCard(TODAY, hassWith({ language: "de_DE" }));
    const shown = block(card.shadowRoot, "today");

    expect(texts(shown, ".panel-head .section-label")).toEqual(["Heute"]);
    expect(texts(shown, ".panel-head .panel-meta")).toEqual(["Mi., 02.09."]);
  });
});

describe("messages before Home Assistant hands over its settings", () => {
  it("speaks the language of the page when the configuration is wrong", async () => {
    document.documentElement.setAttribute("lang", "de");
    const card = document.createElement("ranzenpost-card");

    expect(() => card.setConfig({ blocks: ["bogus"] })).toThrow("Unbekannter Baustein „bogus“.");
  });
});
