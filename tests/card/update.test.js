import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard } from "./loadCard.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, "..", "..", "custom_components", "ranzenpost", "frontend", "ranzenpost-card.js"), "utf8");
const MANIFEST = JSON.parse(readFileSync(join(HERE, "..", "..", "custom_components", "ranzenpost", "manifest.json"), "utf8"));
const CARD_VERSION = /const CARD_VERSION = "([^"]+)";/.exec(SOURCE)[1];
const [YEAR_MONTH, LINE, FIX] = CARD_VERSION.split(".").map((part) => Number.parseInt(part, 10));
const NEWER_FEATURE = `${YEAR_MONTH}.${LINE + 1}.0`;
const NEWER_FIX = `${YEAR_MONTH}.${LINE}.${FIX + 1}`;
const OLDER = `${YEAR_MONTH}.${LINE - 1}.0`;

function hassWith(integrationVersion, language = "de") {
  const hass = makeHass({ language });
  for (const [entityId, entry] of Object.entries(hass.states)) {
    if (!entityId.endsWith("_connection")) continue;
    entry.attributes = { ...entry.attributes };
    if (integrationVersion !== null) entry.attributes.integration_version = integrationVersion;
  }
  return hass;
}

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a card older than the integration", () => {
  it("ships the version of the integration it belongs to", () => {
    expect(CARD_VERSION).toBe(MANIFEST.version);
  });

  it.each([NEWER_FEATURE, NEWER_FIX])("asks to reload the page when the integration runs %s", async (version) => {
    const card = await mountCard({ view: "today", child: "alex" }, hassWith(version));
    const notice = card.shadowRoot.querySelector(".card-update");

    expect(notice).not.toBeNull();
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice.textContent).toBe("Lade die Seite neu, um das Update abzuschließen.");
    expect(card.shadowRoot.querySelector("ha-card").firstElementChild).toBe(notice);
    expect(card.shadowRoot.querySelector(".rows.flat")).not.toBeNull();
  });

  it("speaks the language of Home Assistant", async () => {
    const card = await mountCard({ view: "today", child: "alex" }, hassWith(NEWER_FEATURE, "en"));

    expect(card.shadowRoot.querySelector(".card-update").textContent).toBe("Reload the page to finish the update.");
  });

  it.each([CARD_VERSION, OLDER, "garbage", "", null])("stays quiet when the integration runs %s", async (version) => {
    const card = await mountCard({ view: "today", child: "alex" }, hassWith(version));

    expect(card.shadowRoot.querySelector(".card-update")).toBeNull();
  });

  it("keeps the notice free of physical directions", () => {
    const rule = /\.card-update \{[^}]*\}/.exec(SOURCE)[0];
    expect(rule).not.toMatch(/(margin|padding|border|inset)-(left|right)/);
    expect(rule).toContain("border-inline-start");
  });
});
